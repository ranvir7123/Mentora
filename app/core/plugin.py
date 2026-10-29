"""The interface every app (Excel, VS Code, later others) plugs in through.

A plug-in offers fixed menus of checks and operations, and opens a session on the real app. The
core only ever sees snapshots: plain data the plug-in reads from the app. A new app is a new folder
that follows this interface, not a change to the core.

Rules every session keeps:
- `on_snapshot` and `on_spot` may be called from the plug-in's own thread and must return at once.
- The first snapshot may arrive before `open` returns (the fake delivers it inside `open`; a real app
  delivers it later, from its own thread), so set up everything `on_snapshot` needs before calling
  `open`. `latest()` holds it as well.
- `watch` re-locates while a target is set and calls `on_spot` only when the spot moved by 1 px or
  more; `watch(None, ...)` stops.
- `open(resume=True)` opens the program's own saved work copy in `workdir` when there is one (else
  the starter); `close(save=True)` saves that work copy so the learner can continue later. Neither
  ever touches a file of the learner's own.
- `on_closed` means the learner closed the app; closing it from the program does not call it.
"""
from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping, Protocol

from app.core.types import Call, CheckKind, OpKind, Rect, Spot, Target

if TYPE_CHECKING:
    from app.core.lesson import Lesson


class AppSession(Protocol):
    def hwnd(self) -> int: ...                   # 0 when invisible
    def latest(self) -> Any | None: ...          # last snapshot delivered
    def read_now(self) -> Future: ...            # -> snapshot
    def perform(self, op: Call) -> Future: ...   # -> None; the Future raises if the app refused
    def reset(self) -> Future: ...               # -> None; back to the starter state
    def locate(self, target: Target) -> Future: ...   # -> Spot | None
    def watch(self, target: Target | None, on_spot: Callable[[Spot | None], None]) -> None: ...
    def set_waiting(self, waiting: bool) -> None: ...  # the 1 s idle re-read while a step waits
    def place(self, rect: Rect) -> Future: ...   # put the app's window here (physical px)
    def close(self, save: bool = False) -> None: ...


class AppPlugin(Protocol):
    app_id: str                                  # "excel", "vscode"
    title: str                                   # "Excel"
    checks: Mapping[str, CheckKind]
    ops: Mapping[str, OpKind]
    target_kinds: frozenset[str]

    def validate_starter(self, starter: Mapping) -> list[str]: ...

    def open(self, lesson: Lesson, workdir: Path, *, visible: bool = True, resume: bool = False,
             on_snapshot: Callable[[Any], None], on_closed: Callable[[], None]) -> AppSession: ...
