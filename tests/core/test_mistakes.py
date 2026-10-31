"""Your common mistakes: the steps that took more than one try, read from the attempt log, each with the kind
of slip a fixed check named and a tip in fixed words, so it works with no AI at all."""
from pathlib import Path

import pytest

from app.core.lesson import load_lesson
from app.core.mistakes import MAX_TIP_WORDS, common_mistakes, tip_for
from app.core.runner import StepRecord
from app.excel.checks import CHECKS as EXCEL_CHECKS
from app.vscode.checks import CHECKS as VSCODE_CHECKS

ROOT = Path(__file__).resolve().parents[2] / "lessons"


@pytest.fixture(scope="module")
def shelf():
    lessons = [load_lesson(ROOT / name) for name in ("monthly-budget", "vscode-first-program")]
    return {lesson.id: lesson for lesson in lessons}


def rec(step, tries=1, mistakes=()):
    return StepRecord(step, tries, 0, 10.0, tries == 1, tuple(mistakes))


def test_with_no_tries_there_are_no_mistakes(shelf):
    assert common_mistakes([], shelf) == []


def test_a_step_done_first_time_is_not_a_mistake(shelf):
    assert common_mistakes([rec("monthly-budget/bold"), rec("monthly-budget/total")], shelf) == []


def test_a_step_that_took_three_tries_is_named_with_its_tries_and_a_tip(shelf):
    # A record from before the log kept the kinds of slip: the tip comes from the kind of check.
    [card] = common_mistakes([StepRecord("monthly-budget/bold", 3, 0, 29.3, False)], shelf)
    assert card == {"lessonId": "monthly-budget", "lessonTitle": "Monthly budget", "stepIndex": 0,
                    "instruction": "Make the headings bold.", "kind": "", "tries": 3, "times": 1,
                    "tip": tip_for("bold", ""), "fixed": False}
    assert "select" in card["tip"].lower()


def test_the_kind_of_slip_the_check_named_most_gives_the_label_and_the_tip(shelf):
    log = [rec("monthly-budget/total", 3, ["typed_value", "covers_missing:B6"]),
           rec("monthly-budget/total", 2, ["typed_value"])]
    [card] = common_mistakes(log, shelf)
    assert card["kind"] == "Typed the answer instead of a formula"
    assert card["tip"] == tip_for("formula", "typed_value") and card["tip"] != tip_for("formula", "")
    assert (card["stepIndex"], card["tries"], card["times"]) == (1, 3, 2)


def test_the_steps_that_went_wrong_most_come_first_and_ones_since_got_right_go_last(shelf):
    log = [rec("monthly-budget/bold", 2, ["partial:C1"]),
           rec("monthly-budget/total", 4, ["typed_value", "covers_missing:B6", "value:9"]),
           rec("monthly-budget/share", 5, ["not_absolute:B8"] * 4),
           rec("monthly-budget/share"),                                   # practised, and right first time
           rec("vscode-first-program/print", 3, ["named:Print", "syntax"])]
    cards = common_mistakes(log, shelf, limit=4)
    assert [(c["lessonId"], c["stepIndex"], c["fixed"]) for c in cards] == [
        ("monthly-budget", 1, False), ("vscode-first-program", 1, False), ("monthly-budget", 0, False),
        ("monthly-budget", 3, True)]
    assert cards[1]["kind"] == "Wrote a name with different capitals or spelling"


def test_only_the_top_few_are_shown(shelf):
    log = [rec(f"monthly-budget/{step}", 2) for step in ("bold", "total", "rupees", "share", "chart")]
    assert len(common_mistakes(log, shelf)) == 3


def test_tries_on_a_lesson_or_step_no_longer_on_the_shelf_are_left_out(shelf):
    assert common_mistakes([rec("gone-lesson/bold", 4), rec("monthly-budget/renamed", 4)], shelf) == []


@pytest.mark.parametrize("kind", sorted(set(EXCEL_CHECKS) | set(VSCODE_CHECKS)))
def test_every_check_on_every_apps_menu_has_a_short_plain_tip(kind):
    tip = tip_for(kind, "")
    assert tip and tip[0].isupper() and tip.endswith(".")
    assert len(tip.split()) <= MAX_TIP_WORDS
    assert not any(word in tip.lower().split() for word in ("simply", "just"))
