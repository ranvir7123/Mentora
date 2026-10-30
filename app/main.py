"""Start Mentora: `python -m app` opens the home screen on the real program; `--demo STATE` opens it on demo
data instead, with no app, Meta or network behind it.

While a lesson is open, home steps aside: the panel docks at the right edge of the main screen (360 logical
px, full height above the taskbar) and the lesson's app fills the rest. When the lesson closes, home comes
back. Closing home ends the program; the lesson's app is saved and closed on the way out.

The learner's progress, the log and the lessons' working copies live in `%LOCALAPPDATA%\\mentora\\`. Only
one copy of the program runs at a time, since two would both write the learner's progress.
"""
from __future__ import annotations

import argparse
import importlib
import logging
import math
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, Mapping

from PySide6.QtCore import QEvent, QLockFile, QObject, Qt, Signal, Slot
from PySide6.QtGui import QGuiApplication, QScreen, QWindow
from PySide6.QtQuick import QQuickWindow  # noqa: F401  (so windows come back as QQuickWindow)

from app.core.library import Library
from app.core.plugin import AppPlugin
from app.core.progress import Progress, default_root
from app.core.types import Rect
from app.ui import winstyle
from app.ui.bridge import PANEL_WIDTH, Bridge

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]

# Each app a lesson can run in, as "module:class".
PLUGINS = {"excel": "app.excel.plugin:ExcelPlugin", "vscode": "app.vscode.plugin:VsCodePlugin"}


# Where the lesson's app and the panel go.

def split_screen(area: Rect, *, origin: tuple[float, float], dpr: float) -> tuple[Rect, Rect]:
    """(the app's place, the panel's place) in physical px, from the work area (the screen without the
    taskbar) in logical px. The panel is the right 360 logical px at full height; the app gets the rest.
    Edges land on whole pixels inside the work area, and the two meet with no gap."""
    ox, oy = origin

    def px(v: float) -> float:          # 800 x 1.15 comes out as 919.9999999999999, which is 920
        return round(v, 6)
    left = math.ceil(px(ox + (area.x - ox) * dpr))
    top = math.ceil(px(oy + (area.y - oy) * dpr))
    right = math.floor(px(ox + (area.x + area.w - ox) * dpr))
    bottom = math.floor(px(oy + (area.y + area.h - oy) * dpr))
    panel_left = right - round(PANEL_WIDTH * dpr)
    return (Rect(left, top, panel_left - left, bottom - top),
            Rect(panel_left, top, right - panel_left, bottom - top))


class Layout:
    """Where the app and the panel go on the main screen, the one the panel docks on. Worked out on the
    screens' thread whenever that screen, its scaling or its taskbar changes; read from any thread (the
    backend reads it on its app worker). `on_change` runs after a change, so the app can be put back."""

    def __init__(self, app: QGuiApplication, on_change: Callable[[], None] = lambda: None):
        self.on_change = on_change
        self._lock = threading.Lock()
        self._value: tuple[Rect, Rect] | None = None
        self._screen: QScreen | None = None
        app.primaryScreenChanged.connect(self._watch)
        self._watch(app.primaryScreen())

    def __call__(self) -> tuple[Rect, Rect]:
        with self._lock:
            return self._value

    def _watch(self, screen: QScreen) -> None:
        for signal in ("availableGeometryChanged", "geometryChanged", "logicalDotsPerInchChanged"):
            if self._screen is not None:
                getattr(self._screen, signal).disconnect(self._update)
            getattr(screen, signal).connect(self._update)
        self._screen = screen
        self._update()

    def _update(self, *_ignored) -> None:
        screen = self._screen
        g, a = screen.geometry(), screen.availableGeometry()
        value = split_screen(Rect(a.x(), a.y(), a.width(), a.height()), origin=(g.x(), g.y()),
                             dpr=screen.devicePixelRatio())
        with self._lock:
            before, self._value = self._value, value
        if before is not None and value != before:
            log.info("the screen changed: the app goes to %s, the panel to %s", value[0], value[1])
            self.on_change()


# Home steps aside while a lesson is open.

class Docking(QObject):
    """Hides home while a lesson is open and brings it back when the lesson closes. Closing home (its X)
    ends the program; hiding it never does. Closing the panel (Alt+F4) while a lesson is open closes the
    lesson, so home comes back instead of the program being left with no window. With no lesson open the
    panel lets itself close: Qt asks every window to close as the program quits, and one refusal stops it.

    Whenever the lesson's app starts opening (the learner opened a lesson, pressed Reopen or went on to the
    next lesson), `keep_front(panel)` gives the panel the keyboard, before home hides. Mentora then stays in
    front while the app opens, and Windows lets it bring the app forward once the app is in its place."""

    def __init__(self, bridge: Bridge, home: QObject, *, panel: QObject | None = None,
                 keep_front: Callable[[QObject], object], quit: Callable[[], None]):
        super().__init__(home)
        self._bridge, self._home, self._panel, self._quit = bridge, home, panel, quit
        self._keep_front = keep_front
        self._lesson_open = False
        self._app: tuple[object, bool] | None = None     # the open lesson, and whether its app is up or opening
        home.installEventFilter(self)
        if panel is not None:
            panel.installEventFilter(self)
        bridge.lessonChanged.connect(self._follow)
        self._follow()

    def _follow(self) -> None:
        lesson = self._bridge.lesson
        lesson_open = bool(lesson.get("open"))
        app = (lesson.get("id"), lesson.get("appState") != "closed") if lesson_open else None
        # News is merged, so an app that opens fast may never be seen "opening": a start is told by what changed.
        started = app is not None and (self._app is None or app[0] != self._app[0] or (app[1] and not self._app[1]))
        self._app = app
        if started and self._panel is not None:
            self._keep_front(self._panel)
        if lesson_open == self._lesson_open:
            return
        self._lesson_open = lesson_open
        if lesson_open:
            self._home.hide()
        else:
            self._home.show()
            self._home.raise_()
            self._home.requestActivate()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        # Qt may still call this while Python is tearing the program down, after this object's fields go.
        if event.type() != QEvent.Type.Close:
            return False
        home, panel = getattr(self, "_home", None), getattr(self, "_panel", None)
        if home is not None and watched is home:
            self._quit()
        elif panel is not None and watched is panel and self._lesson_open:
            event.ignore()                   # the panel stays; closing the lesson hides it
            self._bridge.closeLesson()
            return True
        return False


class Front(QObject):
    """Brings the lesson's app to the front, on the screens' thread (make it there). The backend asks from its
    worker; the ask joins the screens' queue behind the news already sent, so Docking has given the panel the
    keyboard (the app is opening) before the app is brought forward, never after, however fast the app opens.
    An ask whose lesson closed while it waited (`still()` is false) is dropped, so home stays in front."""
    _asked = Signal(object, object)

    def __init__(self, give: Callable[[int], object]):
        super().__init__()
        self._give = give
        self._asked.connect(self._bring, Qt.ConnectionType.QueuedConnection)

    def __call__(self, hwnd: int, still: Callable[[], bool]) -> None:
        self._asked.emit(hwnd, still)

    @Slot(object, object)
    def _bring(self, hwnd: int, still: Callable[[], bool]) -> None:
        if still() and not self._give(hwnd):
            log.info("the lesson's app stayed behind: it has no window yet, or Windows let only the program in "
                     "front bring it forward")


def keep_front(window: QWindow) -> None:
    """`window` takes the keyboard. Windows allows that while one of this program's windows has it, or the
    learner's last click was in one; otherwise nothing changes."""
    if not winstyle.give_keyboard_to(int(window.winId())):
        log.info("the panel could not take the keyboard, so the lesson's app may open behind other windows")


# One copy at a time, and a log.

def only_copy(folder: Path) -> QLockFile | None:
    """Holds the program's lock in `folder` for as long as the returned lock lives; None when another copy
    holds it. A lock left by a copy that crashed is taken over (its process is gone)."""
    folder.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(folder / "mentora.lock"))
    lock.setStaleLockTime(0)             # held for hours, so only a dead owner makes it stale
    return lock if lock.tryLock(100) else None


def keep_log(folder: Path) -> logging.Handler:
    """Everything the program logs goes to `folder/mentora.log`, kept to about 4 MB."""
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / "mentora.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)
    return handler


# The real pieces.

def load_plugins() -> dict[str, AppPlugin]:
    """Each app's plug-in. One that can't load is left out and logged; its lessons then can't open."""
    plugins: dict[str, AppPlugin] = {}
    for app_id, where in PLUGINS.items():
        module, name = where.split(":")
        try:
            plugins[app_id] = getattr(importlib.import_module(module), name)()
        except Exception:
            log.exception("the %s plug-in (%s) could not load", app_id, where)
    return plugins


def build_backend(*, lessons: Path, data: Path, recordings: Path, layout: Callable[[], tuple[Rect, Rect]],
                  environ: Mapping[str, str]):
    """The program's backend on the real library, progress, apps, coach and lesson maker."""
    from app.coach.coach import MetaCoach
    from app.factory.pipeline import LessonFactory
    from app.integration.backend import Backend
    from app.meta.client import MetaClient

    library = Library(lessons, show_unproven=environ.get("MENTORA_SHOW_UNPROVEN") == "1")
    plugins = load_plugins()
    client = MetaClient()

    def shelf() -> list[str]:
        return [lesson.title for course in library.courses() for lesson in library.lessons(course.id)]

    coach = MetaCoach(client, shelf=shelf)
    maker = LessonFactory(client, lessons, recordings, on_line=log.info) if "excel" in plugins else None
    return Backend(library, Progress(data), plugins, coach, maker, workdir=data / "work", layout=layout,
                   front=Front(winstyle.give_keyboard_to), recordings=recordings)


def main(argv: list[str] | None = None) -> int:
    from app.ui.app import open_screens
    from app.ui.demo_backend import STATES, DemoBackend

    parser = argparse.ArgumentParser(prog="python -m app", description="Start Mentora.")
    parser.add_argument("--demo", metavar="STATE",
                        help="open on demo data instead: walkthrough, or one of " + ", ".join(STATES))
    args = parser.parse_args(argv)
    if args.demo is not None and args.demo != "walkthrough" and args.demo not in STATES:
        parser.error(f"no demo state called {args.demo}; pick walkthrough or one of: {', '.join(STATES)}")

    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    app.setApplicationName("Mentora")
    app.setQuitOnLastWindowClosed(False)     # home hides while a lesson is open; closing home quits
    lock = layout = None
    if args.demo is not None:
        backend = DemoBackend("lesson_goal" if args.demo == "walkthrough" else args.demo)
        if args.demo == "walkthrough":
            backend.walkthrough()
    else:
        data = default_root()
        lock = only_copy(data)
        if lock is None:
            print("Mentora is already open.", file=sys.stderr)
            return 1
        keep_log(data)
        log.info("Mentora is starting")
        layout = Layout(app)
        backend = build_backend(lessons=ROOT / "lessons", data=data, recordings=ROOT / "recordings",
                                layout=layout, environ=os.environ)
        layout.on_change = backend.relayout
        app.aboutToQuit.connect(backend.shutdown)

    opened = open_screens(backend, show=("home", "panel", "overlay"))
    if opened is None:
        return 1
    bridge, _engine, windows = opened
    docking = Docking(bridge, windows["home"], panel=windows["panel"], keep_front=keep_front, quit=app.quit)
    app._program = (lock, layout, docking)   # kept alive as long as the program
    return app.exec()
