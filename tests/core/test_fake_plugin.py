from types import SimpleNamespace

from app.core.fake_plugin import FakePlugin
from app.core.types import Call, Verdict


def open_fake(tmp_path, starter=None, *, resume=False):
    snaps, closed = [], []
    lesson = SimpleNamespace(id="t", starter={"a": 1} if starter is None else starter)
    session = FakePlugin().open(lesson, tmp_path, resume=resume,
                                on_snapshot=snaps.append, on_closed=lambda: closed.append(True))
    return session, snaps, closed


def test_perform_changes_state_and_delivers_a_snapshot(tmp_path):
    session, snaps, _ = open_fake(tmp_path)
    assert session.latest() == {"a": 1}
    assert session.perform(Call("set", {"key": "b", "value": 2})).result() is None
    assert snaps[-1] == {"a": 1, "b": 2}
    assert session.latest() == {"a": 1, "b": 2}


def test_reset_goes_back_to_the_starter(tmp_path):
    session, snaps, _ = open_fake(tmp_path)
    session.perform(Call("delete", {"key": "a"}))
    assert snaps[-1] == {}
    session.reset().result()
    assert snaps[-1] == {"a": 1}


def test_learner_changes_arrive_as_snapshots(tmp_path):
    session, snaps, _ = open_fake(tmp_path)
    session.learner_sets("a", 5)
    assert snaps[-1] == {"a": 5}
    assert session.read_now().result() == {"a": 5}


def test_refused_operation_fails_its_future(tmp_path):
    session, snaps, _ = open_fake(tmp_path)
    session.refuse_next(1)
    assert session.perform(Call("set", {"key": "b", "value": 2})).exception() is not None
    assert session.latest() == {"a": 1}
    assert session.perform(Call("set", {"key": "b", "value": 2})).exception() is None
    assert session.latest() == {"a": 1, "b": 2}


def test_closing_by_the_learner_calls_on_closed(tmp_path):
    session, _, closed = open_fake(tmp_path)
    session.close()
    assert closed == []                   # the program closing it is not the learner closing it
    session, _, closed = open_fake(tmp_path)
    session.closed_by_learner()
    assert closed == [True]


def test_resume_opens_the_saved_state(tmp_path):
    session, _, _ = open_fake(tmp_path, resume=True)
    assert session.latest() == {"a": 1}   # nothing saved yet: the starter
    session.perform(Call("set", {"key": "b", "value": 2}))
    session.close(save=True)
    session, _, _ = open_fake(tmp_path, resume=True)
    assert session.latest() == {"a": 1, "b": 2}
    session, _, _ = open_fake(tmp_path)
    assert session.latest() == {"a": 1}   # without resume: a fresh start


def test_equals_check_waits_until_the_key_exists():
    run = FakePlugin().checks["equals"].run
    assert run({}, {"key": "a", "value": 1}) == Verdict.waiting()
    assert run({"a": 2}, {"key": "a", "value": 1}).code == "differs:a"
    assert run({"a": 1}, {"key": "a", "value": 1}).ok
