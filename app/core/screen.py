"""What the screens show: the home screen, the lesson panel and the pointer.

The screens (QML) only draw these shapes; the backend decides what is in them. Keys are camelCase
because QML reads them. The backend sends a whole new shape on every change, under the names `home`,
`lesson` and `pointer`, and short sounds under `cue`, as {"name", "points"}: the points a "right" step
earned (0 when it was passed before), and 0 for every other sound.

The defaults below are what every screen starts from. Never change them in place: copy them first.
"""
from __future__ import annotations

from typing import Callable, Literal, Mapping, Protocol, TypedDict


class Learner(TypedDict):
    name: str
    streak: int
    pointsToday: int
    dailyGoal: int


class ContinueCard(TypedDict):
    lessonId: str
    title: str
    step: int
    of: int


class LessonCard(TypedDict):
    id: str
    title: str
    state: Literal["done", "current", "locked"]
    badge: str | None


class Course(TypedDict):
    id: str
    title: str
    app: str
    colour: str                  # a theme token name, such as courseExcel
    progress: float
    credits: list[str]
    ready: bool                  # False shows "Coming soon"
    lessons: list[LessonCard]


class Tips(TypedDict):
    state: Literal["none", "loading", "ready", "error"]
    text: str


class FactoryStage(TypedDict):
    name: Literal["download", "read", "write", "prove", "test", "publish"]
    state: Literal["waiting", "running", "done", "failed"]
    detail: str


class Factory(TypedDict):
    state: Literal["idle", "running", "ready", "not_ready"]
    url: str
    stages: list[FactoryStage]
    reason: str
    lessonId: str | None


class HomeState(TypedDict):
    learner: Learner
    continueCard: ContinueCard | None
    courses: list[Course]
    tips: Tips
    factory: Factory
    meta: Literal["ok", "no_key", "unreachable"]
    muted: bool


class ClipView(TypedDict):
    state: Literal["none", "available", "missing"]     # "missing" shows "Get the video"
    file: str
    start: float
    end: float
    videoUrl: str


class StepView(TypedDict):
    index: int
    instruction: str
    why: str
    hints: list[str]
    hintsLeft: int
    clip: ClipView
    note: str                    # a line under the step, such as "Press Ctrl+S to save"; "" for none


class Banner(TypedDict):
    kind: Literal["right", "not_yet", "changed", "app_closed", "error"]
    text: str
    stepIndex: int


class AskView(TypedDict):
    state: Literal["idle", "thinking", "answered", "error"]
    question: str
    answer: str


class Complete(TypedDict):
    points: int
    seconds: float
    firstTry: int
    steps: int
    streak: int
    streakBefore: int            # the streak when the lesson opened: the same when today already counted


class GoalView(TypedDict):
    sentence: str
    picture: str | None


class LessonState(TypedDict):
    open: bool
    id: str
    title: str
    goal: GoalView
    stepIndex: int
    stepCount: int
    step: StepView | None
    banner: Banner | None
    points: int
    changed: list[int]
    complete: Complete | None
    ask: AskView
    appState: Literal["opening", "ready", "closed"]
    appName: str                 # the app the lesson runs in, such as "Excel"
    closedReason: str            # why the app closed, when known; "" says "<app> was closed"
    badge: str | None


class Box(TypedDict):
    x: int                       # physical screen pixels, like the pointer's own
    y: int
    w: int
    h: int


class PointerState(TypedDict):
    visible: bool
    x: int                       # x, y, w, h are physical screen pixels; the screens divide by the
    y: int                       # screen's device pixel ratio
    w: int
    h: int
    mascot: Literal["resting", "flying", "watching", "thinking", "cheering"]
    bubble: str
    ring: Literal["pulse", "right", "none"]
    room: Box | None             # where the mascot and its words go (a cell's: the sheet's visible cells, clear
                                 # of the app's buttons and bars); None: anywhere on the screen beside the target
    filled: Box | None           # what they keep off when there is space (a cell's: the sheet's filled cells on
                                 # screen, so the learner can still read them); None: nothing


CUES = ("click", "right", "not_yet", "complete", "hop")

EMPTY_HOME: HomeState = {
    "learner": {"name": "", "streak": 0, "pointsToday": 0, "dailyGoal": 50},
    "continueCard": None,
    "courses": [],
    "tips": {"state": "none", "text": ""},
    "factory": {"state": "idle", "url": "", "stages": [], "reason": "", "lessonId": None},
    "meta": "ok",
    "muted": False,
}

CLOSED_LESSON: LessonState = {
    "open": False, "id": "", "title": "", "goal": {"sentence": "", "picture": None},
    "stepIndex": 0, "stepCount": 0, "step": None, "banner": None, "points": 0, "changed": [],
    "complete": None, "ask": {"state": "idle", "question": "", "answer": ""},
    "appState": "closed", "appName": "", "closedReason": "", "badge": None,
}

HIDDEN_POINTER: PointerState = {
    "visible": False, "x": 0, "y": 0, "w": 0, "h": 0, "mascot": "resting", "bubble": "", "ring": "none",
    "room": None, "filled": None,
}


class ScreenBackend(Protocol):
    """What the screens talk to. Every action returns at once; results arrive through `subscribe`."""

    def subscribe(self, listener: Callable[[str, Mapping], None]) -> None:
        """`listener(name, payload)`: name is home, lesson, pointer or cue. May be called from any thread."""

    def home(self) -> HomeState: ...
    def lesson(self) -> LessonState: ...
    def pointer(self) -> PointerState: ...
    def open_lesson(self, lesson_id: str) -> None: ...
    def continue_lesson(self) -> None: ...
    def show_me(self) -> None: ...
    def next_hint(self) -> None: ...
    def watch_clip(self) -> None: ...
    def ask(self, text: str) -> None: ...
    def close_lesson(self) -> None: ...
    def next_lesson(self) -> None: ...
    def go_home(self) -> None: ...
    def make_lesson(self, url: str) -> None: ...
    def set_muted(self, on: bool) -> None: ...
    def reopen_app(self) -> None: ...
    def go_to_step(self, index: int) -> None: ...
    def dismiss_factory(self) -> None: ...
    def key_setup_copied(self) -> None: ...
