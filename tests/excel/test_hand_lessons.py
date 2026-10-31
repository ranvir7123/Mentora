"""The hand-written Excel lessons keep every rule a lesson made from a video must keep."""
import json
from pathlib import Path

import pytest

from app.core.lesson import load_lesson, validate
from app.excel.plugin import ExcelPlugin
from app.excel.starter import fits_width
from app.factory.writer import _outside

LESSONS = {"monthly-budget": 9, "pet-survey-chart": 5, "student-grades": 6, "running-balance": 6}


@pytest.mark.parametrize("name,steps", sorted(LESSONS.items()))
def test_each_hand_lesson_loads_and_follows_the_rules(name, steps):
    lesson = load_lesson(Path("lessons") / name)
    assert validate(lesson, ExcelPlugin()) == []
    assert lesson.id == name and lesson.app == "excel" and lesson.course == "excel"
    assert lesson.made_by == "hand" and lesson.source is None
    assert len(lesson.steps) == steps
    assert all(len(s.hints) == 3 and 1 <= len(s.mistakes) <= 2 for s in lesson.steps)


@pytest.mark.parametrize("name", sorted(LESSONS))
def test_each_hand_lesson_stays_inside_excel_with_everyday_formulas_only(name):
    data = json.loads((Path("lessons") / name / "lesson.json").read_text(encoding="utf-8"))
    assert _outside(data, ExcelPlugin()) == []
    assert fits_width(data["starter"])
