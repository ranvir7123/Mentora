from app.core.fake_plugin import FakePlugin
from app.core.runner import LessonDone, LessonRun, NotYet, StepChanged, StepFixed, StepPassed, StepRecord
from app.core.types import CheckKind

AB = [{"key": "a", "value": 1}, {"key": "b", "value": 2}]


def start(lesson, checks=None):
    now = [0.0]
    run = LessonRun(lesson, checks or FakePlugin().checks, clock=lambda: now[0])
    return run, now


def test_right_step_ticks_and_moves_on(fake_lesson):
    run, _ = start(fake_lesson({}, AB))
    assert run.on_snapshot({"a": 1}) == [StepPassed(0, True, 10)]
    assert run.index == 1 and not run.done


def test_untouched_target_stays_quiet(fake_lesson):
    run, _ = start(fake_lesson({}, AB))
    assert run.on_snapshot({}) == []
    assert run.on_snapshot({"b": 7}) == []          # something changed, but not at this step's target
    assert run.index == 0


def test_wrong_try_says_not_yet_once_until_it_changes(fake_lesson):
    run, _ = start(fake_lesson({}, AB))
    assert run.on_snapshot({"a": 2}) == [NotYet(0, "Not yet: a says 2. It should say 1.", "differs:a")]
    assert run.on_snapshot({"a": 2}) == []          # the same answer, re-read a second later
    assert run.on_snapshot({"a": 3}) == [NotYet(0, "Not yet: a says 3. It should say 1.", "differs:a")]
    assert run.on_snapshot({}) == []                # cleared: nothing to say
    assert len(run.on_snapshot({"a": 3})) == 1      # trying the same wrong answer again is a new try


def test_predicted_mistake_uses_its_own_line(fake_lesson):
    mistake = {"replay": {"kind": "set", "args": {"key": "a", "value": 2}},
               "not_yet": "Not yet: a wants 1, not 2.", "code": "differs:a"}
    run, _ = start(fake_lesson({}, [{"key": "a", "value": 1, "mistakes": [mistake]}]))
    assert run.on_snapshot({"a": 2}) == [NotYet(0, "Not yet: a wants 1, not 2.", "differs:a")]


def test_doing_two_steps_at_once_ticks_both(fake_lesson):
    run, _ = start(fake_lesson({}, AB + [{"key": "c", "value": 3}]))
    assert run.on_snapshot({"a": 1, "b": 2}) == [StepPassed(0, True, 10), StepPassed(1, True, 10)]
    assert run.index == 2


def test_undoing_a_done_step_says_it_changed_and_fixing_it_clears(fake_lesson):
    run, _ = start(fake_lesson({}, AB))
    run.on_snapshot({"a": 1})
    assert run.on_snapshot({}) == [StepChanged(0)]
    assert run.changed == frozenset({0})
    assert run.on_snapshot({}) == []                # said once
    assert run.index == 1                           # nothing goes backwards
    assert run.on_snapshot({"a": 1}) == [StepFixed(0)]
    assert run.changed == frozenset()


def test_hints_come_one_at_a_time_and_are_counted(fake_lesson):
    run, _ = start(fake_lesson({}, AB))
    assert [run.hint() for _ in range(4)] == ["Find a.", "a needs a value.", "Set a to 1.", None]
    assert run.hints_shown() == ("Find a.", "a needs a value.", "Set a to 1.")
    run.on_snapshot({"a": 1})
    assert run.records()[0].hints == 3
    assert run.hints_shown() == ()                  # the next step starts with none


def test_finishing_the_last_step_reports_points_time_and_first_tries(fake_lesson):
    run, now = start(fake_lesson({}, AB))
    now[0] = 10.0
    run.on_snapshot({"a": 1})
    now[0] = 50.0
    run.on_snapshot({"a": 1, "b": 9})
    now[0] = 95.0
    assert run.on_snapshot({"a": 1, "b": 2}) == [StepPassed(1, False, 10), LessonDone(95.0, 20, 1, 2)]
    assert run.done and run.index == 2
    assert run.records() == [StepRecord("s0", 1, 0, 10.0, True), StepRecord("s1", 2, 0, 85.0, False, ("differs:b",))]
    assert run.on_snapshot({"a": 1, "b": 2}) == []  # done is said once


def test_a_check_that_raises_on_a_done_step_changes_nothing(fake_lesson):
    equals = FakePlugin().checks["equals"]

    def odd(snap, args):
        if "odd" in snap:
            raise KeyError("Budget")
        return equals.run(snap, args)
    run, _ = start(fake_lesson({}, AB), {"equals": CheckKind("equals", (), odd, "")})
    run.on_snapshot({"a": 1})
    assert run.on_snapshot({"a": 1, "odd": True}) == []    # no false "Step 1 changed"
    assert run.changed == frozenset() and run.errors
    assert run.on_snapshot({"a": 1}) == []


def test_the_lesson_is_not_done_while_a_step_is_changed(fake_lesson):
    run, now = start(fake_lesson({}, AB))
    run.on_snapshot({"a": 1})
    assert run.on_snapshot({"b": 2}) == [StepChanged(0), StepPassed(1, True, 10)]
    assert not run.done and run.hint() is None and run.hints_shown() == ()
    now[0] = 40.0
    assert run.on_snapshot({"a": 1, "b": 2}) == [StepFixed(0), LessonDone(40.0, 20, 2, 2)]
    assert run.done


def test_resume_skips_steps_already_done_without_points_or_records(fake_lesson):
    run, now = start(fake_lesson({}, AB + [{"key": "c", "value": 3}]))
    now[0] = 100.0
    assert run.resume({"a": 1, "b": 2}) == 2
    assert run.index == 2 and run.records() == [] and run.hints_shown() == ()
    now[0] = 130.0
    assert run.on_snapshot({"a": 1, "b": 2, "c": 3}) == [StepPassed(2, True, 10), LessonDone(30.0, 10, 1, 1)]
    assert run.records() == [StepRecord("s2", 1, 0, 30.0, True)]
    gap, _ = start(fake_lesson({}, AB + [{"key": "c", "value": 3}]))
    assert gap.resume({"a": 1, "c": 3}) == 1          # stops at the first step not done
    finished, _ = start(fake_lesson({}, AB))
    assert finished.resume({"a": 1, "b": 2}) == 2
    assert finished.done and finished.on_snapshot({"a": 1, "b": 2}) == []   # nothing was done in this run


def test_a_check_that_raises_is_treated_as_waiting_and_recorded(fake_lesson):
    def broken(snap, args):
        raise KeyError("Budget")
    run, _ = start(fake_lesson({}, AB), {"equals": CheckKind("equals", (), broken, "")})
    for _ in range(25):
        assert run.on_snapshot({"a": 1}) == []
    assert run.index == 0
    assert len(run.errors) == 20 and run.errors[0] == "KeyError: 'Budget'"


def test_a_record_keeps_the_kind_of_each_not_yet_the_check_named(fake_lesson):
    run, _ = start(fake_lesson({}, AB))
    run.on_snapshot({"a": 2})
    run.on_snapshot({"a": 2})                       # the same answer re-read is not a new slip
    run.on_snapshot({"a": 3})
    run.on_snapshot({"a": 1})
    assert run.records()[0].mistakes == ("differs:a", "differs:a")
    run.on_snapshot({"a": 1, "b": 2})
    assert run.records()[1].mistakes == ()
