"""The one object the screens talk to.

`Bridge` wraps any `ScreenBackend` (see `app/core/screen.py`) for QML: the backend's three shapes become
the properties `home`, `lesson` and `pointer`, its sounds become the `cue` signal, and every button the
learner presses becomes one slot that calls the backend. It also does the pointer's geometry for the
overlay (where the mascot lands, where its words go, the curve it flies), in logical pixels on the primary
screen, and keeps the lesson panel from taking the keyboard away from the app.

The backend may call its listener from any thread, many times a second. Updates are parked under a lock
and handed to the GUI thread in one queued call; a burst collapses to its latest shape per name, so the
screens draw only the newest state, in order, and sounds play after the state they belong to.
"""
from __future__ import annotations

import copy
import threading
from typing import Any, Mapping

from PySide6.QtCore import Property, QObject, QPointF, QRectF, QSizeF, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QGuiApplication, QWindow

from app.core.screen import ScreenBackend
from app.core.types import Rect
from app.ai import SWITCH, key_name
from app.ui import landing, winstyle

_STATES = ("home", "lesson", "pointer")
PANEL_WIDTH = 360          # logical px; the panel docks on the right edge of the screen


def _cue(payload: Any) -> tuple[str, int]:
    """(name, points): the sound, and the points a right step earned, 0 for any other sound."""
    if isinstance(payload, Mapping):
        return str(payload.get("name", "")), int(payload.get("points", 0) or 0)
    return str(payload), 0


_VIDEO_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def _video_link(url: str) -> QUrl | None:
    """The YouTube link to open for `url`, always over https; None for anything else: another site, a file,
    another program's kind of link, or a link carrying a name or a port."""
    text = url.strip()
    if "://" not in text:
        text = "https://" + text
    link = QUrl(text, QUrl.ParsingMode.StrictMode)
    if (not link.isValid() or link.scheme().lower() not in ("http", "https")
            or link.host().lower() not in _VIDEO_HOSTS or link.userInfo() or link.port() != -1):
        return None
    link.setScheme("https")
    return link


class Bridge(QObject):
    homeChanged = Signal()
    lessonChanged = Signal()
    pointerChanged = Signal()
    mutedChanged = Signal()
    mascotHomeChanged = Signal()
    mascotAwayChanged = Signal()
    workAreaChanged = Signal()
    cue = Signal(str, int)          # the sound's name, and the points a right step earned
    _wake = Signal()

    def __init__(self, backend: ScreenBackend, parent: QObject | None = None):
        super().__init__(parent)
        self._backend = backend
        self._state: dict[str, dict] = {
            "home": copy.deepcopy(dict(backend.home())),
            "lesson": copy.deepcopy(dict(backend.lesson())),
            "pointer": copy.deepcopy(dict(backend.pointer())),
        }
        self._muted = bool(self._state["home"].get("muted", False))
        self._lock = threading.Lock()
        self._pending: dict[str, dict] = {}
        self._cues: list[tuple[str, int]] = []
        self._scheduled = False
        self._panel: QWindow | None = None
        self._panel_hwnd: int | None = None
        self._typed_from = 0            # the window that had the keyboard before the Ask box took it
        self._home_spot = QRectF()
        self._away = False
        self._watched = None
        app = QGuiApplication.instance()
        if app is not None:
            app.primaryScreenChanged.connect(self._watch_screen)
            self._watch_screen(app.primaryScreen())
        self._wake.connect(self._flush, Qt.ConnectionType.QueuedConnection)
        backend.subscribe(self._receive)

    # From the backend, on any thread.

    def _receive(self, name: str, payload: Any) -> None:
        with self._lock:
            if name == "cue":
                self._cues.append(_cue(payload))
            elif name in _STATES:
                self._pending[name] = copy.deepcopy(dict(payload))
            else:
                return
            if self._scheduled:
                return
            self._scheduled = True
        self._wake.emit()

    # On the GUI thread.

    @Slot()
    def _flush(self) -> None:
        with self._lock:
            pending, self._pending = self._pending, {}
            cues, self._cues = self._cues, []
            self._scheduled = False
        for name, shape in pending.items():
            if shape == self._state[name]:
                continue
            self._state[name] = shape
            getattr(self, f"{name}Changed").emit()
            if name == "home" and bool(shape.get("muted", False)) != self._muted:
                self._muted = bool(shape.get("muted", False))
                self.mutedChanged.emit()
        for name, points in cues:
            self.cue.emit(name, points)

    def _get_home(self) -> dict:
        return self._state["home"]

    def _get_lesson(self) -> dict:
        return self._state["lesson"]

    def _get_pointer(self) -> dict:
        return self._state["pointer"]

    def _get_muted(self) -> bool:
        return self._muted

    home = Property("QVariantMap", _get_home, notify=homeChanged)
    lesson = Property("QVariantMap", _get_lesson, notify=lessonChanged)
    pointer = Property("QVariantMap", _get_pointer, notify=pointerChanged)
    muted = Property(bool, _get_muted, notify=mutedChanged)

    # The pointer's geometry. Rectangles from the backend are physical pixels; QML works in logical ones.

    def _screen(self) -> tuple[tuple[float, float], float, QRectF]:
        """The primary screen (Excel's): its top-left, its scaling and its area without the taskbar."""
        screen = QGuiApplication.primaryScreen()
        g = screen.geometry()
        return (g.x(), g.y()), screen.devicePixelRatio(), QRectF(screen.availableGeometry())

    def _watch_screen(self, screen) -> None:
        """Keeps `workArea` in step with the primary screen: a new primary screen, or its taskbar moving."""
        if self._watched is not None:
            self._watched.availableGeometryChanged.disconnect(self._work_area_moved)
        self._watched = screen
        if screen is not None:
            screen.availableGeometryChanged.connect(self._work_area_moved)
        self.workAreaChanged.emit()

    def _work_area_moved(self, _area) -> None:
        self.workAreaChanged.emit()

    def _get_work_area(self) -> QRectF:
        return self._screen()[2]

    # The primary screen's area free of the taskbar (logical): the panel docks at its right edge and home
    # opens in its middle, on the screen the pointer's maths uses. Not the whole desktop, which spans every
    # monitor.
    workArea = Property(QRectF, _get_work_area, notify=workAreaChanged)

    def _panel_area(self) -> QRectF:
        if self._panel is not None:
            return QRectF(self._panel.geometry())
        area = self._screen()[2]
        return QRectF(area.x() + area.width() - PANEL_WIDTH, area.y(), PANEL_WIDTH, area.height())

    def _physical(self, r: QRectF) -> Rect:
        origin, dpr, _ = self._screen()
        return landing.to_physical(Rect(r.x(), r.y(), r.width(), r.height()), origin, dpr)

    def _box(self, key: str) -> Rect | None:
        r = self._state["pointer"].get(key)
        return None if r is None else Rect(float(r["x"]), float(r["y"]), float(r["w"]), float(r["h"]))

    def _room(self) -> Rect | None:
        """Where the app lets the mascot and its words go, already in physical pixels; None: anywhere."""
        return self._box("room")

    def _filled(self) -> Rect | None:
        """What the mascot and its words keep off when there is space, in physical pixels; None: nothing."""
        return self._box("filled")

    def _logical(self, x: float, y: float) -> QPointF:
        origin, dpr, _ = self._screen()
        return QPointF(*landing.to_logical((x, y), origin, dpr))

    def _get_pointer_rect(self) -> QRectF:
        p = self._state["pointer"]
        _, dpr, _ = self._screen()
        top_left = self._logical(float(p.get("x", 0)), float(p.get("y", 0)))
        return QRectF(top_left.x(), top_left.y(), float(p.get("w", 0)) / dpr, float(p.get("h", 0)) / dpr)

    pointerRect = Property(QRectF, _get_pointer_rect, notify=pointerChanged)

    def _get_mascot_home(self) -> QRectF:
        if not self._home_spot.isNull():
            return self._home_spot
        column = self._panel_area()
        return QRectF(column.x() + 16, column.y() + column.height() / 2 - 24, 48, 48)

    def _set_mascot_home(self, spot: QRectF) -> None:
        if spot != self._home_spot:
            self._home_spot = QRectF(spot)
            self.mascotHomeChanged.emit()

    # Where the mascot rests in the panel (logical, screen coordinates). The panel sets it.
    mascotHome = Property(QRectF, _get_mascot_home, _set_mascot_home, notify=mascotHomeChanged)

    def _get_mascot_away(self) -> bool:
        return self._away

    def _set_mascot_away(self, away: bool) -> None:
        if away != self._away:
            self._away = away
            self.mascotAwayChanged.emit()

    # True while the overlay's mascot is out of the panel, so the panel hides its own.
    mascotAway = Property(bool, _get_mascot_away, _set_mascot_away, notify=mascotAwayChanged)

    @Slot(QRectF, float, float, QSizeF, result=QPointF)
    def landingSpot(self, target: QRectF, size: float, headroom: float, words: QSizeF) -> QPointF:
        """Top-left of the mascot's body beside `target` (logical, screen coordinates), with `headroom` kept
        free above the body for its curl and hop, on a side where its `words` fit too."""
        _, dpr, area = self._screen()
        said = None if words.isEmpty() else (words.width() * dpr, words.height() * dpr)
        x, y = landing.landing_spot(self._physical(target), size * dpr, self._physical(area),
                                    self._physical(self._panel_area()), room=self._room(), filled=self._filled(),
                                    headroom=headroom * dpr, words=said)
        return self._logical(x, y)

    @Slot(QRectF, QRectF, float, float, result=QPointF)
    def bubbleSpot(self, target: QRectF, mascot: QRectF, width: float, height: float) -> QPointF:
        """Top-left of the mascot's words, a `width` x `height` box beside `mascot` (its whole footprint)."""
        _, dpr, area = self._screen()
        x, y = landing.bubble_spot(self._physical(target), self._physical(mascot), (width * dpr, height * dpr),
                                   self._physical(area), self._physical(self._panel_area()), room=self._room(),
                                   filled=self._filled())
        return self._logical(x, y)

    @Slot(QPointF, QPointF, float, float, QRectF, result=list)
    def flightControl(self, start: QPointF, end: QPointF, size: float, headroom: float,
                      keep_clear: QRectF) -> list:
        """The two bends of the flight curve from `start` to `end` (the body's top-left) that never takes
        the mascot over `keep_clear` and stays on the screen."""
        area = self._screen()[2]
        bend = landing.flight_control((start.x(), start.y()), (end.x(), end.y()), size,
                                      Rect(keep_clear.x(), keep_clear.y(), keep_clear.width(), keep_clear.height()),
                                      Rect(area.x(), area.y(), area.width(), area.height()), headroom=headroom)
        return [QPointF(*b) for b in bend]

    # The lesson panel's window.

    def register_panel(self, window: QWindow) -> None:
        """The panel: the mascot keeps out of its area, and on Windows it never takes focus from the app."""
        self._panel = window
        if QGuiApplication.platformName() == "windows":
            self.set_panel_window(int(window.winId()))

    def set_panel_window(self, hwnd: int) -> None:
        self._panel_hwnd = hwnd
        winstyle.make_no_activate(hwnd, True)

    @Slot(bool)
    def askFocused(self, focused: bool) -> None:
        """The Ask box takes the keyboard (the panel may take focus while it does), or lets it go: then the
        panel never takes focus again, and if it still has the keyboard, the keyboard goes back to the window
        that had it before (the app's), so the learner's next keys land in the app, never in the panel."""
        if self._panel_hwnd is None:
            return
        if focused:
            before = winstyle.foreground()
            if before and before != self._panel_hwnd:
                self._typed_from = before
            winstyle.make_no_activate(self._panel_hwnd, False)
            return
        winstyle.make_no_activate(self._panel_hwnd, True)
        if self._typed_from and winstyle.foreground() == self._panel_hwnd:
            winstyle.give_keyboard_to(self._typed_from)
        self._typed_from = 0

    # The learner's actions. Each returns at once; results come back through the backend's updates.

    @Slot(str)
    def openLesson(self, lesson_id: str) -> None:
        self._backend.open_lesson(lesson_id)

    @Slot()
    def continueLesson(self) -> None:
        self._backend.continue_lesson()

    @Slot()
    def showMe(self) -> None:
        self._backend.show_me()

    @Slot()
    def nextHint(self) -> None:
        self._backend.next_hint()

    @Slot()
    def watchClip(self) -> None:
        self._backend.watch_clip()

    @Slot(str, result=bool)
    def isVideoLink(self, url: str) -> bool:
        """Whether `url` is a YouTube link, the only kind Get the video offers."""
        return _video_link(url) is not None

    @Slot(str)
    def openVideo(self, url: str) -> None:
        """The step's source video, in the browser. The link comes with the lesson, which a model wrote and
        which may have been shared, so anything but a YouTube link is never opened."""
        link = _video_link(url)
        if link is not None:
            QDesktopServices.openUrl(link)

    @Slot(str)
    def ask(self, text: str) -> None:
        self._backend.ask(text)

    @Slot()
    def closeLesson(self) -> None:
        self._backend.close_lesson()

    @Slot()
    def nextLesson(self) -> None:
        self._backend.next_lesson()

    @Slot()
    def goHome(self) -> None:
        self._backend.go_home()

    @Slot(str)
    def makeLesson(self, url: str) -> None:
        self._backend.make_lesson(url)

    @Slot()
    def copyKeySetup(self) -> None:
        """Puts the PowerShell line that saves the key of the AI home names (Meta's or Claude's) on the
        clipboard, with a gap where the key goes.
        The key itself is never read here. The backend then looks for the key for a while, so the card
        clears once the learner has saved it."""
        QGuiApplication.clipboard().setText(
            f'[Environment]::SetEnvironmentVariable("{key_name({SWITCH: self._state["home"].get("ai", "meta")})}", '
            '"<your key>", "User")')
        self._backend.key_setup_copied()

    @Slot()
    def dismissFactory(self) -> None:
        self._backend.dismiss_factory()

    @Slot(bool)
    def setMuted(self, on: bool) -> None:
        if on != self._muted:          # the sound stops now, not when the backend answers
            self._muted = on
            self.mutedChanged.emit()
        self._backend.set_muted(on)

    @Slot()
    def reopenApp(self) -> None:
        self._backend.reopen_app()

    @Slot(int)
    def goToStep(self, index: int) -> None:
        self._backend.go_to_step(index)

    @Slot(str, int)
    def practise(self, lesson_id: str, step_index: int) -> None:
        """Practise this again, from Your common mistakes on home."""
        self._backend.practise(lesson_id, step_index)
