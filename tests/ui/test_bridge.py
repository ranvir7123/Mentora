import copy
import threading
import time

from app.core.screen import CLOSED_LESSON, EMPTY_HOME, HIDDEN_POINTER, HomeState, LessonState, PointerState
from app.ui.bridge import Bridge
from app.ui.demo_backend import STATES, DemoBackend
from tests.screen_shapes import shape_problems


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
    bridge.cue.connect(lambda name, points: cues.append((name, points)))

    def burst():
        for i in range(200):
            backend.listener("lesson", {**CLOSED_LESSON, "open": True, "stepIndex": i})
        backend.listener("cue", {"name": "right", "points": 10})

    worker = threading.Thread(target=burst)
    worker.start()
    worker.join()
    assert _pump(qapp, lambda: bridge.lesson["stepIndex"] == 199 and cues)
    assert seen and seen == sorted(seen) and seen[-1] == 199
    assert cues == [("right", 10)]


def test_every_demo_state_has_every_key():
    problems = []
    for s in STATES:
        d = DemoBackend(s)
        problems += shape_problems(d.home(), HomeState, f"{s} home")
        problems += shape_problems(d.lesson(), LessonState, f"{s} lesson")
        problems += shape_problems(d.pointer(), PointerState, f"{s} pointer")
    assert problems == []


def test_pointing_at_a_changed_step_clearing_the_maker_and_copying_the_key_line_reach_the_backend(qapp):
    backend = DemoBackend("lesson_changed")
    bridge = Bridge(backend)
    bridge.goToStep(1)
    bridge.dismissFactory()
    bridge.copyKeySetup("meta")
    assert backend.actions == [("go_to_step", (1,)), ("dismiss_factory", ()), ("key_setup_copied", ())]


def test_before_the_panel_opens_its_column_is_the_right_360_px_of_the_work_area(qapp):
    bridge = Bridge(DemoBackend("first_run"))
    area = bridge.workArea
    # The mascot rests 16 px into the panel's column; the column ends flush with the work area's right edge.
    assert bridge.mascotHome.x() == area.x() + area.width() - 360 + 16
