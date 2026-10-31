from concurrent.futures import Future
from datetime import datetime

import pytest

from app.core.fake_plugin import FakePlugin
from app.core.lesson import Lesson
from app.core.types import CheckKind
from app.factory import prove as prove_module
from app.factory.prove import ProveError, Proved, prove
from app.factory.writer import NotReady
from tests.core.conftest import build_fake_lesson


def _wrong(key, value):
    """A predicted mistake: the learner types the wrong value."""
    return {"replay": {"kind": "set", "args": {"key": key, "value": value}}, "not_yet": f"{key} is not {value}."}


def _lesson(n=3, starter=None, **steps):
    """n good steps (step i sets k{i} to i+1, one mistake each); `s<i>=` overrides fields of step i."""
    given = [{"mistakes": [_wrong(f"k{i}", -1)], **steps.get(f"s{i}", {})} for i in range(n)]
    return build_fake_lesson(starter or {}, given)


class Fixer:
    """Stands in for the writer on a retry: records each reason and answers with the next lesson."""

    def __init__(self, *answers):
        self.answers, self.reasons = list(answers), []

    def __call__(self, lesson, reason):
        self.reasons.append(reason)
        return self.answers.pop(0)


def test_a_good_lesson_is_proven_and_mistake_codes_are_filled(tmp_path):
    proved = prove(_lesson(), FakePlugin(), tmp_path)

    assert isinstance(proved, Proved) and proved.dropped == [] and proved.notes == []
    proof = proved.lesson.proof
    assert proof.passed is True and proof.dropped == () and proof.notes == ()
    datetime.fromisoformat(proof.at)
    assert [m.code for s in proved.lesson.steps for m in s.mistakes] == ["differs:k0", "differs:k1", "differs:k2"]
    assert proved.lesson.edited_by_hand is False and proved.lesson.made_by == "hand"


def test_a_check_true_before_its_step_is_sent_back_once(tmp_path):
    bad = _lesson(starter={"k1": 2})                   # step s1 sets k1 to 2, which the starter already holds
    fixer = Fixer(_lesson())

    proved = prove(bad, FakePlugin(), tmp_path, fix=fixer)

    assert fixer.reasons == ["step s1: its check was already true before the step"]
    assert proved.lesson.proof.passed is True and proved.dropped == []
    assert proved.notes == ["step s1 went back to Muse Spark: its check was already true before the step"]


def test_a_mistake_the_check_accepts_is_sent_back_once(tmp_path):
    loose = _lesson(s0={"mistakes": [_wrong("k0", 1)]})            # 1 is the right answer, so the check takes it
    fixer = Fixer(_lesson())

    proved = prove(loose, FakePlugin(), tmp_path, fix=fixer)

    assert fixer.reasons == ["step s0: its check accepted mistake 1 (set key=k0 value=1), so the check is too loose"]
    assert proved.lesson.proof.passed is True


@pytest.mark.parametrize("fix", [None, "same lesson again"])
def test_dropping_a_step_reproves_the_rest_without_it(tmp_path, fix):
    # s1's check is true before it (k0 is set by s0), and its replay also sets k2, which would make s2's
    # check true before s2 too. Proven again without s1, s2 passes.
    lesson = _lesson(4, s1={"check": {"kind": "has", "args": {"key": "k0"}},
                            "replay": {"kind": "set", "args": {"key": "k2", "value": 3}}})
    fixer = Fixer(lesson) if fix else None

    proved = prove(lesson, FakePlugin(), tmp_path, fix=fixer)

    assert [s.id for s in proved.lesson.steps] == ["s0", "s2", "s3"]
    assert proved.dropped == ["s1"] and proved.lesson.proof.dropped == ("s1",)
    assert "step s1 was dropped: its check was already true before the step" in proved.notes
    assert proved.why == {"s1": "its check was already true before the step"}
    assert proved.lesson.proof.passed is True                  # three proven steps are left
    if fixer:
        assert len(fixer.reasons) == 1                         # sent back once, never twice


@pytest.mark.parametrize("fix", [None, "same lesson again"])
def test_a_step_that_undoes_an_earlier_step_is_dropped(tmp_path, fix):
    # s2 sets k1 to 99, so s1's check (k1 is 2) is no longer true: the lesson could never celebrate.
    lesson = _lesson(3, s2={"key": "k1", "value": 99, "mistakes": [_wrong("k1", -1)]})
    fixer = Fixer(lesson) if fix else None

    proved = prove(lesson, FakePlugin(), tmp_path, fix=fixer)

    assert [s.id for s in proved.lesson.steps] == ["s0", "s1"]
    assert proved.why == {"s2": "it undid step s1, whose check is no longer true"}
    assert proved.lesson.proof.passed is False
    if fixer:
        assert fixer.reasons == ["step s2: it undid step s1, whose check is no longer true"]


def test_fewer_than_three_steps_left_is_not_proven(tmp_path):
    lesson = _lesson(3, s2={"check": {"kind": "equals", "args": {"key": "k2", "value": 99}}})

    proved = prove(lesson, FakePlugin(), tmp_path)

    assert [s.id for s in proved.lesson.steps] == ["s0", "s1"]
    assert proved.lesson.proof.passed is False
    assert proved.notes == ["step s2 was dropped: its check was still not true after the step",
                            "only 2 steps are left; a lesson needs at least 3"]


def test_a_mistake_the_check_does_not_notice_is_a_failure(tmp_path):
    lesson = _lesson(4, s0={"mistakes": [{"replay": {"kind": "delete", "args": {"key": "k0"}},
                                          "not_yet": "Put k0 back."}]})

    proved = prove(lesson, FakePlugin(), tmp_path)

    assert proved.dropped == ["s0"]
    assert proved.notes[0] == ("step s0 was dropped: its check did not notice mistake 1 (delete key=k0), "
                               "so the learner would get no Not yet line")


def test_two_mistakes_with_the_same_code_are_noted(tmp_path):
    lesson = _lesson(s0={"mistakes": [_wrong("k0", -1), _wrong("k0", -2)]})

    proved = prove(lesson, FakePlugin(), tmp_path)

    assert proved.lesson.proof.passed is True
    assert proved.notes == ["step s0: mistakes 1 and 2 get the same verdict (differs:k0), so only mistake 1's "
                            "Not yet line can show"]


def test_a_refused_operation_drops_the_step(tmp_path):
    class RefusesOnce(FakePlugin):
        opened = 0

        def open(self, *args, **kwargs):
            session = super().open(*args, **kwargs)
            RefusesOnce.opened += 1
            if RefusesOnce.opened == 1:
                session.refuse_next(1)                     # the very first operation of the first run
            return session

    proved = prove(_lesson(4), RefusesOnce(), tmp_path)

    assert proved.dropped == ["s0"]
    assert proved.notes[0] == "step s0 was dropped: the app refused mistake 1 (the fake app refused set)"


def test_a_crashing_check_drops_the_step(tmp_path):
    plugin = FakePlugin()

    def boom(snap, args):
        raise KeyError("value")

    plugin.checks["has"] = CheckKind("has", plugin.checks["has"].params, boom, "the key exists")
    lesson = _lesson(4, s3={"check": {"kind": "has", "args": {"key": "k3"}}})

    proved = prove(lesson, plugin, tmp_path)

    assert proved.dropped == ["s3"]
    assert proved.notes[0] == "step s3 was dropped: its check crashed (KeyError: 'value')"


def test_a_fix_that_is_not_ready_drops_the_step(tmp_path):
    fixer = Fixer(NotReady("Muse Spark's lesson broke the rules: step s1: it has 1 hints; it needs exactly 3."))

    proved = prove(_lesson(4, starter={"k1": 2}), FakePlugin(), tmp_path, fix=fixer)

    assert proved.dropped == ["s1"]
    assert proved.notes[:2] == [
        "step s1 went back to Muse Spark, which could not fix it: Muse Spark's lesson broke the rules: step s1: "
        "it has 1 hints; it needs exactly 3.",
        "step s1 was dropped: its check was already true before the step"]


def test_an_app_that_stops_answering_stops_the_proof(tmp_path, monkeypatch):
    class Hangs(FakePlugin):
        def open(self, *args, **kwargs):
            session = super().open(*args, **kwargs)
            session.read_now = lambda: Future()              # never answers
            return session

    monkeypatch.setattr(prove_module, "TIMEOUT_S", 0.05)
    with pytest.raises(ProveError, match="Fake app did not answer"):
        prove(_lesson(), Hangs(), tmp_path)


def test_the_proven_lesson_is_a_lesson(tmp_path):
    assert isinstance(prove(_lesson(), FakePlugin(), tmp_path).lesson, Lesson)


def test_an_app_that_cannot_be_read_stops_the_proof(tmp_path):
    class Unreadable(FakePlugin):
        def open(self, *args, **kwargs):
            session = super().open(*args, **kwargs)
            broken = Future()
            broken.set_exception(OSError("the workbook is busy"))
            session.read_now = lambda: broken
            return session

    with pytest.raises(ProveError) as caught:
        prove(_lesson(), Unreadable(), tmp_path)
    assert str(caught.value) == "Fake app could not be read."            # plain, for the screen
    assert caught.value.detail == "Fake app could not be read: the workbook is busy"


def test_an_app_that_will_not_open_stops_the_proof_with_its_own_words_kept_apart(tmp_path):
    class WontOpen(FakePlugin):
        def open(self, *args, **kwargs):
            raise KeyError()

    with pytest.raises(ProveError) as caught:
        prove(_lesson(), WontOpen(), tmp_path)
    assert str(caught.value) == "Fake app could not be opened."
    assert caught.value.detail == "Fake app could not be opened: KeyError"


def test_a_rewrite_never_brings_back_a_step_already_dropped(tmp_path):
    # s1 and s2 are true before their steps. s1 comes back from Muse Spark still broken and is dropped; when
    # s2 goes back, the whole lesson is written again with s1 fixed, and s1 stays out, as it was dropped.
    bad = _lesson(4, starter={"k1": 2, "k2": 3})
    fixer = Fixer(bad, _lesson(4))

    proved = prove(bad, FakePlugin(), tmp_path, fix=fixer)

    assert [s.id for s in proved.lesson.steps] == ["s0", "s2", "s3"]
    assert proved.dropped == ["s1"] and proved.lesson.proof.passed is True
    assert fixer.reasons == ["step s1: its check was already true before the step",
                             'step s2: its check was already true before the step; leave out step s1 '
                             '("Set k1 to 2."), which was dropped']
