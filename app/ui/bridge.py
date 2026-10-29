"""The one object the screens talk to.

`Bridge` wraps any `ScreenBackend` (see `app/core/screen.py`) for QML: the backend's three shapes become
the properties `home`, `lesson` and `pointer`, its sounds become the `cue` signal, and every button the
learner presses becomes one slot that calls the backend.

The backend may call its listener from any thread, many times a second. Updates are parked under a lock
and handed to the GUI thread in one queued call; a burst collapses to its latest shape per name, so the
screens draw only the newest state, in order, and sounds play after the state they belong to.
"""
from __future__ import annotations

import copy
import threading
from typing import Any, Mapping

from PySide6.QtCore import Property, QObject, Qt, Signal, Slot

from app.core.screen import ScreenBackend

_STATES = ("home", "lesson", "pointer")


def _cue_name(payload: Any) -> str:
    if isinstance(payload, Mapping):
        return str(payload.get("name", ""))
    return str(payload)


class Bridge(QObject):
    homeChanged = Signal()
    lessonChanged = Signal()
    pointerChanged = Signal()
    mutedChanged = Signal()
    cue = Signal(str)
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
        self._cues: list[str] = []
        self._scheduled = False
        self._wake.connect(self._flush, Qt.ConnectionType.QueuedConnection)
        backend.subscribe(self._receive)

    # From the backend, on any thread.

    def _receive(self, name: str, payload: Any) -> None:
        with self._lock:
            if name == "cue":
                self._cues.append(_cue_name(payload))
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
        for name in cues:
            self.cue.emit(name)

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

    @Slot(bool)
    def setMuted(self, on: bool) -> None:
        if on != self._muted:          # the sound stops now, not when the backend answers
            self._muted = on
            self.mutedChanged.emit()
        self._backend.set_muted(on)

    @Slot()
    def reopenApp(self) -> None:
        self._backend.reopen_app()
