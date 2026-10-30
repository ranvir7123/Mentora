"""Checks a shape the screens read against its description in app/core/screen.py: every key there, no
other keys, all the way down."""
import typing

from app.core.screen import (AskView, Banner, ClipView, Complete, ContinueCard, Course, Factory, FactoryStage,
                             GoalView, Learner, LessonCard, StepView, Tips)

_NESTED = {
    "learner": Learner, "continueCard": ContinueCard, "tips": Tips, "factory": Factory, "goal": GoalView,
    "step": StepView, "banner": Banner, "ask": AskView, "complete": Complete, "clip": ClipView,
}
_LISTS = {"courses": Course, "lessons": LessonCard, "stages": FactoryStage}


def shape_problems(value, shape, where):
    problems = []
    want = set(typing.get_type_hints(shape))
    if set(value) != want:
        problems.append(f"{where}: keys {sorted(set(value) ^ want)} differ")
    for key, inner in value.items():
        if key in _NESTED and isinstance(inner, dict):     # the continue card's "step" is a number
            problems += shape_problems(inner, _NESTED[key], f"{where}.{key}")
        if key in _LISTS:
            for i, item in enumerate(inner):
                problems += shape_problems(item, _LISTS[key], f"{where}.{key}[{i}]")
    return problems
