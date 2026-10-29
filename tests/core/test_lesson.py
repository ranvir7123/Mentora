import json
from dataclasses import replace

import pytest

from app.core.fake_plugin import FakePlugin
from app.core.lesson import (LessonError, edited, lesson_from_dict, lesson_json_schema, lesson_to_dict,
                             load_lesson, save_lesson, shelf_badge, validate)


def step_dict(step_id="s1", **over):
    d = {"id": step_id, "instruction": "Set a to 1.", "why": "So a holds ₹1.",
         "target": {"kind": "key", "ref": "a"},
         "check": {"kind": "equals", "args": {"key": "a", "value": 1}},
         "replay": {"kind": "set", "args": {"key": "a", "value": 1}},
         "hints": ["Look at a.", "a needs a value.", "Set a to 1."],
         "mistakes": [{"replay": {"kind": "set", "args": {"key": "a", "value": 2}},
                       "not_yet": "Not yet: a should be 1.", "code": "differs:a"}],
         "clip": {"start": 1.5, "end": 4.0}}
    d.update(over)
    return d


def lesson_dict(steps=None, **over):
    d = {"format": 1, "id": "t", "title": "Test lesson", "app": "fake", "course": "fake",
         "source": {"url": "https://www.youtube.com/watch?v=x", "title": "A video", "creator": "Someone",
                    "channel_url": "https://www.youtube.com/@someone", "licence": "CC BY", "length_s": 300},
         "goal": {"sentence": "Make a hold 1.", "picture": "goal.png"},
         "starter": {"a": 0},
         "steps": [step_dict()] if steps is None else steps,
         "made_by": "generated", "edited_by_hand": False,
         "proof": {"passed": True, "at": "2026-10-30T10:00:00", "dropped": ["x"], "notes": ["fine"]},
         "test": {"passed": True, "at": "2026-10-30T11:00:00", "mode": "mouse", "runs": 5, "passes": 5}}
    d.update(over)
    return d


def test_round_trip_keeps_every_field(tmp_path):
    original = lesson_from_dict(lesson_dict(), folder=tmp_path)
    save_lesson(original)
    loaded = load_lesson(tmp_path)
    assert loaded == original and loaded.folder == tmp_path
    assert lesson_to_dict(loaded) == lesson_dict()
    assert list(json.loads((tmp_path / "lesson.json").read_text(encoding="utf-8"))) == [
        "format", "id", "title", "app", "course", "source", "goal", "starter", "steps", "made_by",
        "edited_by_hand", "proof", "test"]


def test_missing_field_is_named():
    d = lesson_dict()
    del d["steps"]
    with pytest.raises(LessonError, match="steps"):
        lesson_from_dict(d)
    d = lesson_dict()
    del d["steps"][0]["check"]["kind"]
    with pytest.raises(LessonError, match=r"steps\[0\]\.check\.kind"):
        lesson_from_dict(d)


def test_validate_names_every_problem():
    steps = [step_dict("long", instruction="Put the number one into the key called a right now please ok."),
             step_dict("easy", hints=["Look at a.", "Just set it.", "Set a to 1."]),
             step_dict("short", hints=["Look at a.", "Set a to 1."]),
             step_dict("clip", clip={"start": 5, "end": 3}),
             step_dict("menu", check={"kind": "nope", "args": {}}),
             step_dict("long")]
    problems = validate(lesson_from_dict(lesson_dict(steps)), FakePlugin())
    assert len(problems) == 6
    for step_id, problem in zip(["long", "easy", "short", "clip", "menu", "long"], problems):
        assert step_id in problem


def test_shelf_badge():
    base = lesson_from_dict(lesson_dict())
    assert shelf_badge(replace(base, proof=None)) is None
    assert shelf_badge(replace(base, proof=replace(base.proof, passed=False))) is None
    assert shelf_badge(replace(base, test=None)) is None
    assert shelf_badge(replace(base, test=replace(base.test, passed=False))) is None
    assert shelf_badge(base) == "proven and tested"
    assert shelf_badge(replace(base, test=replace(base.test, mode="keyboard"))) == "proven and tested"
    assert shelf_badge(replace(base, test=replace(base.test, mode="skipped", passed=False))) == "proven"


def test_editing_clears_proof_and_test_and_marks_the_lesson():
    base = lesson_from_dict(lesson_dict())
    changed = edited(base, title="Better title")
    assert changed.title == "Better title" and changed.edited_by_hand
    assert changed.proof is None and changed.test is None
    assert base.proof is not None and not base.edited_by_hand


def test_schema_lists_only_menu_kinds():
    s = lesson_json_schema(FakePlugin())
    step = s["properties"]["steps"]["items"]
    assert step["properties"]["check"]["properties"]["kind"]["enum"] == ["equals", "has"]
    assert step["properties"]["replay"]["properties"]["kind"]["enum"] == ["set", "delete"]
    mistake = step["properties"]["mistakes"]["items"]
    assert mistake["properties"]["replay"]["properties"]["kind"]["enum"] == ["set", "delete"]
    assert step["properties"]["target"]["properties"]["kind"]["enum"] == ["key"]
    assert s["additionalProperties"] is False and step["additionalProperties"] is False
