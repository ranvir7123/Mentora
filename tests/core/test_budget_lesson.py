from pathlib import Path

from app.core.lesson import load_lesson, validate


def test_budget_lesson_loads_and_follows_the_rules():
    lesson = load_lesson(Path("lessons/monthly-budget"))
    assert validate(lesson) == []
    assert len(lesson.steps) == 9 and lesson.made_by == "hand"
    assert all(len(s.hints) == 3 for s in lesson.steps)
