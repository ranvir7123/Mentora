"""Every screen state on demand, with no real app behind it.

`DemoBackend` is a `ScreenBackend` that makes up its shapes from the hand-written budget lesson
(`lessons/monthly-budget`) and a small made-up library. It is how the screens are built, shot at 200% and
load-tested without Excel, Meta or a network. Pick a state by name (`STATES`); `walkthrough()` plays the
budget lesson step by step, with one planted "Not yet", on a background thread like a real backend.

Pointer rectangles are physical pixels on a 2560 x 1600 screen with Excel on the left and the 720 px
(360 logical) panel on the right.
"""
from __future__ import annotations

import copy
import re
import threading
from pathlib import Path
from typing import Any, Callable, Mapping

from app.core.lesson import Lesson, load_lesson
from app.core.screen import CLOSED_LESSON, EMPTY_HOME, HIDDEN_POINTER

STATES: tuple[str, ...] = (
    "first_run", "home_progress", "home_long_text", "home_no_key", "home_offline", "course_empty",
    "factory_running", "factory_not_ready",
    "lesson_goal", "lesson_step", "lesson_right", "lesson_not_yet", "lesson_hints", "lesson_changed",
    "lesson_clip", "lesson_clip_missing", "lesson_ask", "lesson_app_closed", "lesson_complete",
    "pointer_flying", "pointer_watching", "pointer_right", "long_text",
)

_ROOT = Path(__file__).resolve().parents[2]
_BUDGET = _ROOT / "lessons" / "monthly-budget"
_DEMO = Path(__file__).resolve().with_name("demo")
_CLIP = _ROOT / "recordings" / "demo" / "clip.mp4"      # made by probes/ui_make_demo_clip.py; never committed
_VIDEO_URL = "https://www.youtube.com/watch?v=demo"

_budget: Lesson | None = None


def _lesson_file() -> Lesson:
    global _budget
    if _budget is None:
        _budget = load_lesson(_BUDGET)
    return _budget


# Where things sit on the made-up screen (physical px): Excel's grid starts under its ribbon.

_COLS = {"A": (60, 200), "B": (260, 170), "C": (430, 140), "D": (570, 140)}
_ROW1, _ROW_H = 470, 40
_CONTROLS = {
    "Insert > Pie": (612, 168, 96, 112),
    "View > Freeze Panes": (838, 168, 120, 112),
    "Data > Sort Largest to Smallest": (452, 176, 64, 96),
}


def _cell_rect(ref: str) -> tuple[int, int, int, int]:
    ref = ref.split("!")[-1]
    corners = []
    for part in ref.split(":"):
        m = re.fullmatch(r"\$?([A-Z]+)\$?(\d+)", part)
        col, row = m.group(1), int(m.group(2))
        x, w = _COLS.get(col, (710, 140))
        y = _ROW1 + (row - 1) * _ROW_H
        corners.append((x, y, x + w, y + _ROW_H))
    x0, y0 = min(c[0] for c in corners), min(c[1] for c in corners)
    x1, y1 = max(c[2] for c in corners), max(c[3] for c in corners)
    return x0, y0, x1 - x0, y1 - y0


def target_rect(step_index: int) -> tuple[int, int, int, int]:
    target = _lesson_file().steps[step_index].target
    if target.kind == "control":
        return _CONTROLS.get(target.ref, (600, 176, 96, 96))
    return _cell_rect(target.ref)


# Home.

_LEARNER = {"name": "Ranvir", "streak": 4, "pointsToday": 30, "dailyGoal": 50}

_EXCEL_LESSONS = ("Grade sheet", "Monthly budget", "Sales chart", "Clean up a messy list",
                  "Find prices with a lookup", "Habit tracker")
_PYTHON_LESSONS = ("Your first Python file", "Ask for a name", "Build your first app with Meta's AI")


def _lessons(titles, current: int) -> list[dict]:
    out = []
    for i, title in enumerate(titles):
        state = "done" if i < current else "current" if i == current else "locked"
        lesson_id = "monthly-budget" if title == "Monthly budget" else re.sub(r"\W+", "-", title.lower())
        out.append({"id": lesson_id, "title": title, "state": state, "badge": "proven and tested"})
    return out


def _courses(excel_current: int = 0, python_lessons: bool = True) -> list[dict]:
    excel = _lessons(_EXCEL_LESSONS, excel_current)
    python = _lessons(_PYTHON_LESSONS, 0) if python_lessons else []
    return [
        {"id": "excel", "title": "Excel", "app": "excel", "colour": "courseExcel",
         "progress": excel_current / len(excel), "credits": ["Sheet School", "Priya Makes Spreadsheets"],
         "ready": True, "lessons": excel},
        {"id": "python", "title": "Python in VS Code", "app": "vscode", "colour": "coursePython",
         "progress": 0.0, "credits": ["Code With Tomas"], "ready": True, "lessons": python},
        {"id": "meta", "title": "Build with Meta's AI", "app": "vscode", "colour": "courseMeta",
         "progress": 0.0, "credits": [], "ready": False, "lessons": []},
    ]


def _home(**over: Any) -> dict:
    home = copy.deepcopy(EMPTY_HOME)
    home.update(learner=dict(_LEARNER), courses=_courses(1),
                continueCard={"lessonId": "monthly-budget", "title": "Monthly budget", "step": 4, "of": 9},
                tips={"state": "ready",
                      "text": "Formulas: fast. Charts took 3 tries. Try the chart review next."})
    home.update(over)
    return home


def _stages(states: Mapping[str, tuple[str, str]]) -> list[dict]:
    names = ("download", "read", "write", "prove", "test", "publish")
    return [{"name": n, "state": states.get(n, ("waiting", ""))[0], "detail": states.get(n, ("waiting", ""))[1]}
            for n in names]


def _factory(state: str, stages: list[dict], reason: str = "") -> dict:
    return {"state": state, "url": "https://www.youtube.com/watch?v=k7RM-ot2NWY", "stages": stages,
            "reason": reason, "lessonId": None}


# The lesson panel.

def _clip(state: str = "none") -> dict:
    if state == "available" and not _CLIP.exists():
        state = "missing"           # like a real lesson whose video isn't saved on this computer
    if state == "available":
        return {"state": "available", "file": str(_CLIP), "start": 12.0, "end": 19.5, "videoUrl": _VIDEO_URL}
    if state == "missing":
        return {"state": "missing", "file": "", "start": 12.0, "end": 19.5, "videoUrl": _VIDEO_URL}
    return {"state": "none", "file": "", "start": 0.0, "end": 0.0, "videoUrl": ""}


def _step_view(index: int, hints_shown: int = 0, clip: str = "none") -> dict:
    step = _lesson_file().steps[index]
    return {"index": index, "instruction": step.instruction, "why": step.why,
            "hints": list(step.hints[:hints_shown]), "hintsLeft": len(step.hints) - hints_shown,
            "clip": _clip(clip)}


def _goal_picture() -> str | None:
    picture = _DEMO / "goal.png"
    return str(picture) if picture.exists() else None


def _lesson(index: int, **over: Any) -> dict:
    budget = _lesson_file()
    lesson = copy.deepcopy(CLOSED_LESSON)
    lesson.update(open=True, id=budget.id, title=budget.title,
                  goal={"sentence": budget.goal.sentence, "picture": _goal_picture()},
                  stepIndex=index, stepCount=len(budget.steps),
                  step=_step_view(index) if index < len(budget.steps) else None,
                  points=index * 10, appState="ready", badge=None)
    lesson.update(over)
    return lesson


def _banner(kind: str, text: str, index: int) -> dict:
    return {"kind": kind, "text": text, "stepIndex": index}


def _pointer(index: int, mascot: str, ring: str = "pulse", bubble: str = "") -> dict:
    x, y, w, h = target_rect(index)
    return {"visible": True, "x": x, "y": y, "w": w, "h": h, "mascot": mascot, "bubble": bubble, "ring": ring}


_LONG_TITLE = "Track your monthly spending with a budget that adds itself up"
_LONG_NAME = "Anastasia-Maximiliane Oberhauser-Lindqvist"
_LONG_CREATOR = "Maximilian Großschädl-Württemberger Tabellenkalkulation"


def _build(state: str) -> tuple[dict, dict, dict, str | None, dict]:
    """(home, lesson, pointer, cue, view) for one named state. `view` holds what only the screens decide,
    such as which course is open, so a screenshot can show it."""
    if state not in STATES:
        raise ValueError(f"no demo state called {state!r}; pick one of {', '.join(STATES)}")
    budget = _lesson_file()
    home, lesson, pointer, cue, view = _home(), copy.deepcopy(CLOSED_LESSON), copy.deepcopy(HIDDEN_POINTER), None, {}
    total_mistake = budget.steps[1].mistakes[0].not_yet

    if state == "first_run":
        home = _home(learner={**_LEARNER, "streak": 0, "pointsToday": 0}, continueCard=None,
                     courses=_courses(0), tips={"state": "none", "text": ""})
    elif state == "home_long_text":
        courses = _courses(1)
        courses[0]["title"] = "Excel for people who have never opened a spreadsheet before"
        courses[0]["credits"] = [_LONG_CREATOR, "Priya Makes Spreadsheets", "Sheet School"]
        courses[0]["lessons"][1]["title"] = _LONG_TITLE
        home = _home(learner={**_LEARNER, "name": _LONG_NAME, "streak": 128, "pointsToday": 1240},
                     continueCard={"lessonId": "monthly-budget", "title": _LONG_TITLE, "step": 4, "of": 9},
                     courses=courses,
                     tips={"state": "ready", "text": (
                         "Formulas: fast, and you fixed the total on your own. Charts took 3 tries, mostly "
                         "picking the range. Try the chart review next, then the lookup lesson when you "
                         "feel ready for something new.")})
    elif state == "home_no_key":
        home = _home(meta="no_key", tips={"state": "none", "text": ""})
    elif state == "home_offline":
        home = _home(meta="unreachable", tips={"state": "error", "text": ""})
    elif state == "course_empty":
        home = _home(courses=_courses(1, python_lessons=False))
        view = {"home": {"courseId": "python"}}
    elif state == "factory_running":
        home = _home(factory=_factory("running", _stages({
            "download": ("done", "Got 6:12 of video and its captions"),
            "read": ("done", "Found 9 steps"),
            "write": ("running", "Writing step 5 of 9"),
        })))
    elif state == "factory_not_ready":
        home = _home(factory=_factory("not_ready", _stages({
            "download": ("done", "Got 6:12 of video and its captions"),
            "read": ("done", "Found 9 steps"),
            "write": ("done", "Wrote 9 steps"),
            "prove": ("failed", "Steps 6 and 7 could not be proven in Excel"),
        }), reason="Two steps could not be proven in Excel, so this video can't become a lesson yet."))
    elif state == "lesson_goal":
        lesson = _lesson(0)
    elif state == "lesson_step":
        lesson = _lesson(1)
    elif state == "lesson_right":
        lesson = _lesson(1, banner=_banner("right", "", 1), points=20)
        pointer, cue = _pointer(1, "cheering", ring="right"), "right"
    elif state == "lesson_not_yet":
        lesson = _lesson(1, banner=_banner("not_yet", total_mistake, 1))
        pointer, cue = _pointer(1, "watching"), "not_yet"
    elif state == "lesson_hints":
        lesson = _lesson(1, step=_step_view(1, hints_shown=2))
    elif state == "lesson_changed":
        lesson = _lesson(4, changed=[1])
    elif state == "lesson_clip":
        lesson = _lesson(1, step=_step_view(1, clip="available"))
        view = {"panel": {"clipOpen": True}}
    elif state == "lesson_clip_missing":
        lesson = _lesson(1, step=_step_view(1, clip="missing"))
        view = {"panel": {"clipOpen": True}}
    elif state == "lesson_ask":
        lesson = _lesson(1, ask={"state": "answered", "question": "Why can't I type 23000 in B8?",
                                 "answer": "A typed number stays 23000 even when rent changes. "
                                           "=SUM(B2:B6) adds the amounts again every time."})
    elif state == "lesson_app_closed":
        lesson = _lesson(3, appState="closed")
    elif state == "lesson_complete":
        lesson = _lesson(len(budget.steps), points=90,
                         complete={"points": 90, "seconds": 372.0, "firstTry": 7, "steps": 9, "streak": 5})
        cue = "complete"
    elif state == "pointer_flying":
        lesson, pointer = _lesson(1), _pointer(1, "flying")
    elif state == "pointer_watching":
        lesson, pointer = _lesson(1), _pointer(1, "watching")
    elif state == "pointer_right":
        lesson = _lesson(1, banner=_banner("right", "", 1), points=20)
        pointer = _pointer(1, "cheering", ring="right")
    elif state == "long_text":
        home = _build("home_long_text")[0]
        step = _step_view(3, hints_shown=3)
        step.update(instruction="Work out what share of the whole monthly total your rent takes up in C2",
                    why=("Shares show at a glance where most of your money goes each month, so you can "
                         "see which costs are worth cutting first."),
                    hints=["Share is the amount divided by the total, so divide B2 by the total in B8.",
                           "Type =B2/B8, then press F4 once so the total stays locked when you copy it.",
                           "Type =B2/$B$8 and press Enter. The dollar signs keep B8 fixed."])
        lesson = _lesson(3, title=_LONG_TITLE, step=step, changed=[0, 1],
                         banner=_banner("not_yet", "Not yet: you divided the total by the rent. Divide "
                                                   "the rent in B2 by the total in B8 instead.", 3))
        pointer, cue = _pointer(3, "watching", bubble="Type it in this cell"), "not_yet"
    return home, lesson, pointer, cue, view


class DemoBackend:
    """A `ScreenBackend` with made-up content. `actions` records every call, as (name, args)."""

    def __init__(self, state: str = "first_run"):
        self._listeners: list[Callable[[str, Mapping], None]] = []
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.actions: list[tuple[str, tuple]] = []
        self._load(state)

    def _load(self, state: str) -> None:
        self.state = state
        self._home, self._lesson, self._pointer, self._cue, self.view = _build(state)

    # The backend contract.

    def subscribe(self, listener: Callable[[str, Mapping], None]) -> None:
        self._listeners.append(listener)

    def home(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._home)

    def lesson(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._lesson)

    def pointer(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._pointer)

    def _send(self, name: str, payload: Mapping) -> None:
        for listener in list(self._listeners):
            listener(name, copy.deepcopy(payload))

    def _publish(self, *, home=None, lesson=None, pointer=None, cue=None) -> None:
        with self._lock:
            if home is not None:
                self._home = home
            if lesson is not None:
                self._lesson = lesson
            if pointer is not None:
                self._pointer = pointer
        for name, shape in (("home", home), ("lesson", lesson), ("pointer", pointer)):
            if shape is not None:
                self._send(name, shape)
        if cue:
            self._send("cue", {"name": cue})

    # Demo controls.

    def set_state(self, state: str) -> None:
        """Switch to a named state and tell every listener, with the state's sound."""
        self.stop()
        with self._lock:
            self._load(state)
        self.replay()

    def replay(self) -> None:
        """Send the current state and its sound again, as if it had just happened."""
        self._publish(home=self.home(), lesson=self.lesson(), pointer=self.pointer(), cue=self._cue)

    def walkthrough(self, interval: float = 2.0) -> None:
        """Play the budget lesson from the first step to the celebration on a background thread."""
        self.stop()
        self._stop = stop = threading.Event()

        def run() -> None:
            steps = _lesson_file().steps
            self._publish(home=self.home(), lesson=_lesson(0), pointer=copy.deepcopy(HIDDEN_POINTER))
            if stop.wait(interval):
                return
            for i in range(len(steps)):
                self._publish(lesson=_lesson(i), pointer=_pointer(i, "flying"), cue="hop")
                if stop.wait(interval / 2):
                    return
                self._publish(pointer=_pointer(i, "watching"))
                if stop.wait(interval):
                    return
                if i == 1:      # the planted wrong try: a typed number instead of a formula
                    self._publish(lesson=_lesson(i, banner=_banner("not_yet", steps[i].mistakes[1].not_yet, i)),
                                  cue="not_yet")
                    if stop.wait(interval * 1.5):
                        return
                self._publish(lesson=_lesson(i, banner=_banner("right", "", i), points=(i + 1) * 10),
                              pointer=_pointer(i, "cheering", ring="right"), cue="right")
                if stop.wait(interval):
                    return
            self._publish(lesson=_lesson(len(steps), points=90, complete={
                "points": 90, "seconds": 372.0, "firstTry": 8, "steps": len(steps), "streak": 5}),
                pointer=copy.deepcopy(HIDDEN_POINTER), cue="complete")

        self._thread = threading.Thread(target=run, name="demo-walkthrough", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _record(self, name: str, *args: Any) -> None:
        self.actions.append((name, args))

    # The learner's actions: each moves the demo somewhere sensible so it can be clicked through.

    def open_lesson(self, lesson_id: str) -> None:
        self._record("open_lesson", lesson_id)
        self._publish(lesson=_lesson(0), pointer=copy.deepcopy(HIDDEN_POINTER))

    def continue_lesson(self) -> None:
        self._record("continue_lesson")
        self._publish(lesson=_lesson(3))

    def show_me(self) -> None:
        self._record("show_me")
        lesson = self.lesson()
        if lesson["open"] and lesson["step"] is not None:
            self._publish(pointer=_pointer(lesson["stepIndex"], "flying"), cue="hop")

    def next_hint(self) -> None:
        self._record("next_hint")
        lesson = self.lesson()
        step = lesson["step"]
        if step is not None and step["hintsLeft"] > 0:
            shown = len(step["hints"]) + 1
            lesson["step"] = {**_step_view(step["index"], hints_shown=shown), "clip": step["clip"]}
            self._publish(lesson=lesson)

    def watch_clip(self) -> None:
        self._record("watch_clip")

    def ask(self, text: str) -> None:
        self._record("ask", text)
        lesson = self.lesson()
        lesson["ask"] = {"state": "thinking", "question": text, "answer": ""}
        self._publish(lesson=lesson)

        def answer() -> None:
            done = self.lesson()
            done["ask"] = {"state": "answered", "question": text,
                           "answer": "Look at the step's check: it reads B8's formula, not the number."}
            self._publish(lesson=done)

        timer = threading.Timer(1.2, answer)
        timer.daemon = True
        timer.start()

    def close_lesson(self) -> None:
        self._record("close_lesson")
        self.stop()
        self._publish(lesson=copy.deepcopy(CLOSED_LESSON), pointer=copy.deepcopy(HIDDEN_POINTER))

    def next_lesson(self) -> None:
        self._record("next_lesson")
        self._publish(lesson=_lesson(0), pointer=copy.deepcopy(HIDDEN_POINTER))

    def go_home(self) -> None:
        self._record("go_home")
        self.stop()
        self._publish(lesson=copy.deepcopy(CLOSED_LESSON), pointer=copy.deepcopy(HIDDEN_POINTER))

    def make_lesson(self, url: str) -> None:
        self._record("make_lesson", url)
        home = self.home()
        home["factory"] = {**_factory("running", _stages({"download": ("running", "Getting the video")})),
                           "url": url}
        self._publish(home=home)

    def set_muted(self, on: bool) -> None:
        self._record("set_muted", on)
        home = self.home()
        home["muted"] = bool(on)
        self._publish(home=home)

    def reopen_app(self) -> None:
        self._record("reopen_app")
        lesson = self.lesson()
        lesson["appState"] = "ready"
        self._publish(lesson=lesson)
