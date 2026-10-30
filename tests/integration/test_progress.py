import json
from datetime import date, timedelta

from app.core.progress import LessonProgress, Progress
from app.core.runner import LessonDone, StepRecord

DAY = date(2026, 10, 30)


class Clock:
    """A calendar the test moves by hand."""
    def __init__(self, day=DAY):
        self.day = day

    def __call__(self):
        return self.day

    def next_day(self, days=1):
        self.day += timedelta(days=days)


def test_points_and_steps_survive_a_restart(tmp_path):
    p = Progress(tmp_path, today=Clock())
    p.step_passed("budget", 0, 10)
    p.step_passed("budget", 1, 10)
    p.lesson_done("other", LessonDone(seconds=95.0, points=30, first_try=3, steps=3))

    again = Progress(tmp_path, today=Clock())
    assert again.points_today() == 20
    assert again.lesson_state("budget") == LessonProgress(step=2, done=False, best_seconds=None)
    assert again.lesson_state("other") == LessonProgress(step=0, done=True, best_seconds=95.0)
    assert again.lesson_state("never-opened") == LessonProgress(step=0, done=False, best_seconds=None)


def test_streak_counts_days_in_a_row_without_guilt(tmp_path):
    clock = Clock()
    p = Progress(tmp_path, today=clock)
    assert p.streak() == 0
    for _ in range(3):
        p.step_passed("budget", 0, 10)
        clock.next_day()
    clock.day -= timedelta(days=1)
    assert p.streak() == 3

    clock.next_day()                     # the day after: yesterday still counts until today ends
    assert p.streak() == 3
    clock.next_day()                     # a whole day skipped
    assert p.streak() == 0
    p.step_passed("budget", 1, 10)
    assert p.streak() == 1
    assert Progress(tmp_path, today=clock).streak() == 1


def test_points_today_start_again_each_day(tmp_path):
    clock = Clock()
    p = Progress(tmp_path, today=clock)
    p.step_passed("budget", 0, 10)
    clock.next_day()
    assert p.points_today() == 0
    p.step_passed("budget", 1, 10)
    assert p.points_today() == 10


def test_a_broken_progress_file_is_set_aside(tmp_path):
    (tmp_path / "progress.json").write_text('{"format": 1, "days": {"2026-10-', encoding="utf-8")
    p = Progress(tmp_path, today=Clock())
    assert p.streak() == 0 and p.points_today() == 0
    set_aside = list(tmp_path.glob("progress.broken-*.json"))
    assert len(set_aside) == 1
    assert set_aside[0].read_text(encoding="utf-8") == '{"format": 1, "days": {"2026-10-'
    p.step_passed("budget", 0, 10)
    assert Progress(tmp_path, today=Clock()).points_today() == 10


def test_a_progress_file_of_the_wrong_shape_is_set_aside_too(tmp_path):
    (tmp_path / "progress.json").write_text('{"format": 1, "days": [1, 2], "lessons": "no"}', encoding="utf-8")
    p = Progress(tmp_path, today=Clock())
    assert p.points_today() == 0
    assert len(list(tmp_path.glob("progress.broken-*.json"))) == 1


def test_a_failed_save_keeps_the_last_good_file(tmp_path, monkeypatch):
    p = Progress(tmp_path, today=Clock())
    p.step_passed("budget", 0, 10)
    before = (tmp_path / "progress.json").read_text(encoding="utf-8")

    def power_cut(*_):
        raise OSError("disk went away")
    monkeypatch.setattr("app.core.progress.os.replace", power_cut)
    p.step_passed("budget", 1, 10)                       # no crash
    assert (tmp_path / "progress.json").read_text(encoding="utf-8") == before
    assert not list(tmp_path.glob("*.tmp"))
    assert p.points_today() == 20                        # the program still counts it until it closes


def test_attempts_are_kept_in_order(tmp_path):
    p = Progress(tmp_path, today=Clock())
    first = StepRecord(step_id="bold", tries=1, hints=0, seconds=4.5, first_try=True)
    second = StepRecord(step_id="total", tries=3, hints=1, seconds=40.0, first_try=False)
    third = StepRecord(step_id="run", tries=2, hints=0, seconds=12.0, first_try=False)
    p.log_attempt("monthly-budget", first)
    p.log_attempt("monthly-budget", second)
    p.log_attempt("vscode-first-program", third)

    # Two lessons can both have a step called "run", so each step is named with its lesson.
    assert Progress(tmp_path, today=Clock()).attempts() == [
        StepRecord("monthly-budget/bold", 1, 0, 4.5, True),
        StepRecord("monthly-budget/total", 3, 1, 40.0, False),
        StepRecord("vscode-first-program/run", 2, 0, 12.0, False)]


def test_a_half_written_attempt_line_is_skipped(tmp_path):
    p = Progress(tmp_path, today=Clock())
    p.log_attempt("budget", StepRecord("bold", 1, 0, 4.5, True))
    with open(tmp_path / "attempts.jsonl", "a", encoding="utf-8") as f:
        f.write('{"lesson": "budget", "step_id": "to')
    p.log_attempt("budget", StepRecord("total", 2, 0, 9.0, False))
    assert [r.step_id for r in p.attempts()] == ["budget/bold", "budget/total"]


def test_a_finished_lesson_keeps_its_best_time(tmp_path):
    p = Progress(tmp_path, today=Clock())
    p.lesson_done("budget", LessonDone(seconds=120.0, points=90, first_try=7, steps=9))
    p.lesson_done("budget", LessonDone(seconds=200.0, points=90, first_try=9, steps=9))
    assert p.lesson_state("budget").best_seconds == 120.0
    p.lesson_done("budget", LessonDone(seconds=80.0, points=90, first_try=9, steps=9))
    assert p.lesson_state("budget").best_seconds == 80.0


def test_a_lesson_found_finished_on_reopening_is_done_with_no_time(tmp_path):
    p = Progress(tmp_path, today=Clock())
    p.lesson_done("budget", None)                 # its saved work already passed every step
    assert p.lesson_state("budget") == LessonProgress(step=0, done=True, best_seconds=None)
    p.lesson_done("sum", LessonDone(seconds=50.0, points=30, first_try=3, steps=3))
    p.lesson_done("sum", None)
    assert Progress(tmp_path, today=Clock()).lesson_state("sum").best_seconds == 50.0


def test_the_last_lesson_made_lessons_tips_and_name_are_kept(tmp_path):
    p = Progress(tmp_path, today=Clock())
    assert (p.last_lesson, p.made, p.tips, p.name, p.daily_goal) == (None, [], "", "", 30)
    p.opened("budget")
    p.lesson_made("sum-tutorial")
    p.lesson_made("sum-tutorial")
    p.keep_tips("Try the Name Box.")
    p.name = "Ranvir"
    p.save()

    again = Progress(tmp_path, today=Clock())
    assert (again.last_lesson, again.made, again.tips, again.name) == (
        "budget", ["sum-tutorial"], "Try the Name Box.", "Ranvir")


def test_the_file_is_plain_json_on_the_laptop(tmp_path):
    p = Progress(tmp_path / "mentora", today=Clock())
    p.step_passed("budget", 0, 10)
    data = json.loads((tmp_path / "mentora" / "progress.json").read_text(encoding="utf-8"))
    assert data["days"] == {"2026-10-30": 10}



def test_a_progress_file_that_cannot_be_read_is_never_overwritten(tmp_path, monkeypatch):
    good = Progress(tmp_path, today=Clock())
    good.step_passed("budget", 0, 10)
    before = (tmp_path / "progress.json").read_text(encoding="utf-8")

    real_read = type(tmp_path).read_text

    def locked(self, *args, **kwargs):
        if self.name == "progress.json":
            raise PermissionError("another program has the file open")
        return real_read(self, *args, **kwargs)
    monkeypatch.setattr(type(tmp_path), "read_text", locked)
    p = Progress(tmp_path, today=Clock())
    p.step_passed("budget", 1, 10)                       # counted while the program runs ...
    assert p.points_today() == 10
    monkeypatch.undo()
    assert (tmp_path / "progress.json").read_text(encoding="utf-8") == before   # ... but the good file stays


def test_a_file_locked_for_a_moment_is_read_on_a_second_try(tmp_path, monkeypatch):
    Progress(tmp_path, today=Clock()).step_passed("budget", 0, 10)
    real_read, fails = type(tmp_path).read_text, [1]

    def busy_once(self, *args, **kwargs):
        if self.name == "progress.json" and fails:
            fails.pop()
            raise PermissionError("an antivirus scan has the file open")
        return real_read(self, *args, **kwargs)
    monkeypatch.setattr(type(tmp_path), "read_text", busy_once)
    assert Progress(tmp_path, today=Clock()).points_today() == 10


def test_a_step_earns_its_points_once(tmp_path):
    p = Progress(tmp_path, today=Clock())
    assert p.step_passed("budget", 0, 10) == 10
    assert p.step_passed("budget", 0, 10) == 0           # passed again after reopening: nothing new
    assert p.step_passed("budget", 1, 10) == 10
    assert p.points_today() == 20
    p.lesson_done("budget", None)
    assert p.step_passed("budget", 0, 10) == 10          # a finished lesson played again earns again
