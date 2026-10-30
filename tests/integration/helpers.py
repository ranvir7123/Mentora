import json

PROVEN = {"passed": True, "at": "2026-10-30T09:00:00", "dropped": [], "notes": []}
TESTED = {"passed": True, "at": "2026-10-30T09:10:00", "mode": "mouse", "runs": 5, "passes": 5}

COURSES = [{"id": "sheets", "title": "Sheets", "app": "fake", "colour": "courseExcel"},
           {"id": "code", "title": "Code", "app": "fake", "colour": "coursePython"}]


def fake_step(i, key=None, value=None, **given):
    """A FakePlugin step: set key k<i> to i+1, unless told otherwise."""
    key = key or f"k{i}"
    value = i + 1 if value is None else value
    step = {"id": f"s{i}", "instruction": f"Set {key} to {value}.", "why": f"{key} needs a value.",
            "target": {"kind": "key", "ref": key},
            "check": {"kind": "equals", "args": {"key": key, "value": value}},
            "replay": {"kind": "set", "args": {"key": key, "value": value}},
            "hints": [f"Find {key}.", f"{key} needs a value.", f"Set {key} to {value}."],
            "mistakes": [], "clip": None}
    step.update(given)
    return step


def lesson_dict(lesson_id, *, title=None, course="sheets", steps=2, proof=PROVEN, test=TESTED, source=None,
                starter=None):
    return {"format": 1, "id": lesson_id, "title": title or lesson_id.title(), "app": "fake", "course": course,
            "source": source, "goal": {"sentence": "Fill in the keys.", "picture": None},
            "starter": starter or {}, "steps": [fake_step(i) for i in range(steps)] if isinstance(steps, int) else steps,
            "made_by": "hand", "edited_by_hand": False, "proof": proof, "test": test}


def write_courses(root, courses=COURSES):
    root.mkdir(parents=True, exist_ok=True)
    (root / "courses.json").write_text(json.dumps(courses), encoding="utf-8")


def write_lesson(root, lesson_id, **given):
    folder = root / lesson_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "lesson.json").write_text(json.dumps(lesson_dict(lesson_id, **given)), encoding="utf-8")
    return folder
