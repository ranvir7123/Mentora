import pytest

from app.core.lesson import lesson_from_dict


def build_fake_lesson(starter, steps):
    """A FakePlugin lesson. Each step may give `key` and `value` (step i defaults to key ki, value i+1)
    and override any step field; everything left out gets a valid default."""
    full = []
    for i, given in enumerate(steps):
        given = dict(given)
        key, value = given.pop("key", f"k{i}"), given.pop("value", i + 1)
        step = {"id": f"s{i}", "instruction": f"Set {key} to {value}.", "why": f"{key} needs a value.",
                "target": {"kind": "key", "ref": key},
                "check": {"kind": "equals", "args": {"key": key, "value": value}},
                "replay": {"kind": "set", "args": {"key": key, "value": value}},
                "hints": [f"Find {key}.", f"{key} needs a value.", f"Set {key} to {value}."],
                "mistakes": [], "clip": None}
        step.update(given)
        full.append(step)
    return lesson_from_dict({
        "format": 1, "id": "fake", "title": "Fake lesson", "app": "fake", "course": "fake", "source": None,
        "goal": {"sentence": "Fill in the keys.", "picture": None}, "starter": starter, "steps": full,
        "made_by": "hand", "edited_by_hand": False, "proof": None, "test": None})


@pytest.fixture
def fake_lesson():
    return build_fake_lesson
