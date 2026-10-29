import copy
import threading
import time
import typing

from app.core.screen import (CLOSED_LESSON, EMPTY_HOME, HIDDEN_POINTER, AskView, Banner, ClipView, Complete,
                             ContinueCard, Course, Factory, FactoryStage, GoalView, HomeState, Learner,
                             LessonCard, LessonState, PointerState, StepView, Tips)
from app.ui.bridge import Bridge
from app.ui.demo_backend import STATES, DemoBackend


def _pump(qapp, until, timeout=2.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        qapp.processEvents()
        if until():
            return True
        time.sleep(0.005)
    return until()


class PushBackend:
    """A backend whose updates are pushed by the test, from whatever thread it likes."""

    def __init__(self):
        self.listener = None

    def subscribe(self, listener):
        self.listener = listener

    def home(self):
        return copy.deepcopy(EMPTY_HOME)

    def lesson(self):
        return copy.deepcopy(CLOSED_LESSON)

    def pointer(self):
        return copy.deepcopy(HIDDEN_POINTER)


def test_bridge_exposes_the_backend_state(qapp):
    bridge = Bridge(DemoBackend("lesson_step"))
    assert bridge.lesson["stepIndex"] == 1
    assert bridge.lesson["open"] is True


def test_actions_reach_the_backend(qapp):
    backend = DemoBackend("lesson_step")
    bridge = Bridge(backend)
    bridge.showMe()
    bridge.openLesson("monthly-budget")
    bridge.setMuted(True)
    names = [a[0] for a in backend.actions]
    assert names == ["show_me", "open_lesson", "set_muted"]
    assert backend.actions[1] == ("open_lesson", ("monthly-budget",))


def test_updates_from_other_threads_arrive_in_order(qapp):
    backend = PushBackend()
    bridge = Bridge(backend)
    seen, cues = [], []
    bridge.lessonChanged.connect(lambda: seen.append(bridge.lesson["stepIndex"]))
    bridge.cue.connect(cues.append)

    def burst():
        for i in range(200):
            backend.listener("lesson", {**CLOSED_LESSON, "open": True, "stepIndex": i})
        backend.listener("cue", {"name": "right"})

    worker = threading.Thread(target=burst)
    worker.start()
    worker.join()
    assert _pump(qapp, lambda: bridge.lesson["stepIndex"] == 199 and cues)
    assert seen and seen == sorted(seen) and seen[-1] == 199
    assert cues == ["right"]


_NESTED = {
    "learner": Learner, "continueCard": ContinueCard, "tips": Tips, "factory": Factory, "goal": GoalView,
    "step": StepView, "banner": Banner, "ask": AskView, "complete": Complete, "clip": ClipView,
}
_LISTS = {"courses": Course, "lessons": LessonCard, "stages": FactoryStage}


def _shape_problems(value, shape, where):
    problems = []
    want = set(typing.get_type_hints(shape))
    if set(value) != want:
        problems.append(f"{where}: keys {sorted(set(value) ^ want)} differ")
    for key, inner in value.items():
        if key in _NESTED and isinstance(inner, dict):     # the continue card's "step" is a number
            problems += _shape_problems(inner, _NESTED[key], f"{where}.{key}")
        if key in _LISTS:
            for i, item in enumerate(inner):
                problems += _shape_problems(item, _LISTS[key], f"{where}.{key}[{i}]")
    return problems


def test_every_demo_state_has_every_key():
    problems = []
    for s in STATES:
        d = DemoBackend(s)
        problems += _shape_problems(d.home(), HomeState, f"{s} home")
        problems += _shape_problems(d.lesson(), LessonState, f"{s} lesson")
        problems += _shape_problems(d.pointer(), PointerState, f"{s} pointer")
    assert problems == []
