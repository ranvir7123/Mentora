import pytest


def test_busy_read_is_retried_until_the_cell_is_left(rig):
    r = rig()
    r.reader.busy_until = 3.0                    # the learner is typing in a cell for 3 s
    for _ in range(3):
        r.com.advance(0.5)
        r.events.fire("changed")                 # the fake raises if a handler touches Excel
    assert r.snapshots == []
    r.com.advance(2.0)
    assert len(r.snapshots) == 1
    sched = r.session._scheduler
    assert sched.busy_retries > 0 and sched.error_count == 0
    assert r.com.errors == [] and r.closed == 0


def test_idle_reread_runs_every_second_only_while_waiting(rig):
    r = rig()
    r.com.advance(0)
    r.session.set_waiting(True)
    r.session.set_waiting(True)                  # asking twice is still one loop
    r.com.advance(3.0)
    assert r.reader.reads == 1 + 3
    r.session.set_waiting(False)
    r.com.advance(5.0)
    assert r.reader.reads == 4


def test_read_now_resolves_with_the_next_snapshot(rig):
    r = rig()
    r.com.advance(0)
    fut = r.session.read_now()
    assert not fut.done()                        # the snapshot already delivered is not "next"
    r.com.advance(0)
    assert fut.result(0) == r.snapshots[-1] == {"read": 2, "book": "monthly-budget.xlsx"}


def test_read_now_after_the_close_fails_at_once(rig):
    r = rig()
    r.com.advance(0)
    r.session.close()
    with pytest.raises(RuntimeError, match="closed"):
        r.session.read_now().result(0)


def test_a_read_now_waiting_when_the_learner_closes_is_not_left_hanging(rig):
    r = rig()
    r.com.advance(0)
    r.reader.busy_until = 99.0
    fut = r.session.read_now()
    r.app.books[0].learner_closes()
    r.com.advance(1.1)
    assert r.closed == 1
    with pytest.raises(RuntimeError, match="closed"):
        fut.result(0)


def test_a_read_now_waiting_when_the_program_closes_is_not_left_hanging(rig):
    r = rig()
    r.com.advance(0)
    r.reader.busy_until = 99.0
    fut = r.session.read_now()
    r.session.close()
    with pytest.raises(RuntimeError, match="closed"):
        fut.result(0)
