"""One lesson's Excel: our own copy of Excel, the lesson's workbook, its events, and a clean exit.

The session starts a new Excel (never the learner's own), opens the lesson's workbook from the
work folder, and listens to the workbook's events. Events only say "something changed", and Excel
must not be called from inside one, so each handler just asks the read scheduler for a read.

Closing is noticed two ways. BeforeClose says the learner asked to close, but they can still press
Cancel at the "save your changes?" box, so it only brings the next check forward. The check itself
runs every second on the COM thread and confirms the close: no workbooks left, our workbook gone,
the window gone, or Excel itself gone (killed outright). A busy Excel means "can't tell yet".
on_closed() then fires once; it never fires when the program closes the session itself. The owner
calls close() afterwards to let this Excel go.

Every Excel call happens on the COM thread. on_snapshot and on_closed run there too and must
return at once.
"""
from __future__ import annotations

import gc
import traceback
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Callable

from app.core.lesson import Lesson
from app.core.types import Rect
from app.excel.busy import is_busy
from app.excel.com_thread import ComThread
from app.excel.reads import ReadScheduler
from app.excel.snapshot import read_snapshot
from app.excel.starter import build_starter
from app.win import windows

CLOSED_CHECK_S = 1.0
CLOSED_CHECK_SOON_S = 0.25         # after BeforeClose: the learner is probably closing
IDLE_REREAD_S = 1.0                # while a step waits: freezing panes and renaming fire no event


def _new_excel():
    import win32com.client
    return win32com.client.DispatchEx("Excel.Application")   # a new Excel, not the learner's


class _WorkbookSink:
    """Excel's workbook events. pywin32 makes this object itself; `handler` is set just after."""

    def _changed(self) -> None:
        handler = getattr(self, "handler", None)
        if handler is not None:
            handler.changed()

    def OnSheetChange(self, Sh, Target):
        self._changed()

    def OnSheetCalculate(self, Sh):
        self._changed()

    def OnSheetSelectionChange(self, Sh, Target):
        self._changed()

    def OnSheetActivate(self, Sh):
        self._changed()

    def OnWindowResize(self, Wn):
        self._changed()

    def OnBeforeClose(self, Cancel):
        handler = getattr(self, "handler", None)
        if handler is not None:
            handler.before_close()


def attach_workbook_events(wb, handler):
    """Start listening to wb's events; the returned sink's close() stops it."""
    import win32com.client
    sink = win32com.client.WithEvents(wb, _WorkbookSink)
    sink.handler = handler
    return sink


class _Handler:
    """What an event does. Never calls Excel: it only asks for a read or an early close check."""

    def __init__(self, session: ExcelSession) -> None:
        self._session = session

    def changed(self) -> None:
        self._session._on_change()

    def before_close(self) -> None:
        self._session._on_before_close()


class ExcelSession:
    def __init__(self, lesson: Lesson, workdir: Path, *, visible: bool = True, resume: bool = False,
                 on_snapshot: Callable[[Any], None], on_closed: Callable[[], None],
                 excel_factory: Callable[[], Any] | None = None, com=None,
                 attach_events: Callable[[Any, Any], Any] | None = None,
                 reader: Callable[[Any], Any] = read_snapshot) -> None:
        self._lesson = lesson
        self.path = Path(workdir) / f"{lesson.id}.xlsx"
        self._visible = visible
        self._on_snapshot = on_snapshot
        self._on_closed = on_closed
        self._factory = excel_factory or _new_excel
        self._com = com or ComThread(f"excel-{lesson.id}")
        self._attach = attach_events or attach_workbook_events
        self._reader = reader
        self.errors: list[str] = []
        self._app = None
        self._wb = None
        self._sink = None
        self._hwnd = 0
        self._scheduler: ReadScheduler | None = None
        self._latest: Any = None
        self._closed = False           # the learner closed the workbook (or Excel went away)
        self._stopping = False         # the program is closing the session
        self._save = False
        self._check_token = 0
        self._waiting = False
        self._waiting_token = 0
        self._read_waiters: list[Future] = []

        if not (resume and self.path.exists()):
            build_starter(lesson.starter, self.path)
        self._com.start(self._setup, self._teardown)

    # ------------------------------------------------------------ from any thread

    def hwnd(self) -> int:
        return self._hwnd

    def latest(self) -> Any | None:
        return self._latest

    def read_now(self) -> Future:
        """A Future for the next snapshot delivered after this call."""
        fut: Future = Future()
        if self._closed or self._stopping:
            fut.set_exception(RuntimeError("Excel was closed"))
            return fut

        def ask() -> None:
            if self._closed or self._stopping or self._scheduler is None:
                fut.set_exception(RuntimeError("Excel was closed"))
                return
            self._read_waiters.append(fut)
            self._scheduler.read_soon()
        self._com.submit(ask)
        return fut

    def set_waiting(self, waiting: bool) -> None:
        """While a step waits, read once a second even when Excel says nothing changed."""
        self._com.submit(lambda: self._set_waiting(waiting))

    def place(self, rect: Rect) -> Future:
        def move() -> None:
            if not self._hwnd:
                raise ValueError("this Excel has no window to move (it was opened invisible)")
            windows.place_window(self._hwnd, rect)
        return self._com.submit(move)

    def close(self, save: bool = False) -> None:
        """Close the workbook (saving it into the work folder if asked) and quit this Excel."""
        if self._stopping:
            return
        self._stopping = True
        self._save = save
        self._com.stop()

    # ------------------------------------------------------------ on the COM thread

    def _setup(self) -> None:
        windows.dpi_aware_thread()
        self._app = self._factory()
        self._app.Visible = self._visible
        self._wb = self._app.Workbooks.Open(str(self.path))
        self._sink = self._attach(self._wb, _Handler(self))
        self._hwnd = int(self._app.Hwnd) if self._visible else 0
        self._scheduler = ReadScheduler(self._com.call_later, self._read, self._deliver)
        self._scheduler.read_soon()
        self._schedule_check(CLOSED_CHECK_S)

    def _read(self) -> Any:
        if self._closed or self._stopping:
            return None                # nothing to read; the scheduler stops here
        return self._reader(self._wb)

    def _deliver(self, snap: Any) -> None:
        if snap is None or self._closed or self._stopping:
            return
        self._latest = snap
        waiters, self._read_waiters = self._read_waiters, []
        for fut in waiters:
            fut.set_result(snap)
        self._on_snapshot(snap)

    def _fail_read_waiters(self) -> None:
        waiters, self._read_waiters = self._read_waiters, []
        for fut in waiters:
            fut.set_exception(RuntimeError("Excel was closed"))

    def _set_waiting(self, waiting: bool) -> None:
        if waiting == self._waiting:
            return
        self._waiting = waiting
        self._waiting_token += 1           # a stopped loop's pending tick finds a newer token
        if waiting:
            self._idle_tick(self._waiting_token)

    def _idle_tick(self, token: int) -> None:
        if token != self._waiting_token or self._closed or self._stopping:
            return
        self._com.call_later(IDLE_REREAD_S, lambda: self._idle_reread(token))

    def _idle_reread(self, token: int) -> None:
        if token != self._waiting_token or self._closed or self._stopping:
            return
        self._scheduler.read_soon()
        self._idle_tick(token)

    def _on_change(self) -> None:
        if not (self._closed or self._stopping) and self._scheduler is not None:
            self._scheduler.changed()

    def _on_before_close(self) -> None:
        if not (self._closed or self._stopping):
            self._schedule_check(CLOSED_CHECK_SOON_S)

    def _schedule_check(self, delay_s: float) -> None:
        """Only the newest scheduled check runs, so an early check never doubles the loop."""
        self._check_token += 1
        token = self._check_token
        self._com.call_later(delay_s, lambda: self._check_closed(token))

    def _check_closed(self, token: int) -> None:
        if token != self._check_token or self._closed or self._stopping:
            return
        state = self._workbook_state()
        if state == "closed":
            self._closed = True
            self._fail_read_waiters()
            self._on_closed()
            return
        self._schedule_check(CLOSED_CHECK_SOON_S if state == "unknown" else CLOSED_CHECK_S)

    def _workbook_state(self) -> str:
        """"open", "closed", or "unknown" while Excel is too busy to answer."""
        if self._visible and not windows.is_window(self._hwnd):
            return "closed"
        try:
            if self._app.Workbooks.Count == 0:
                return "closed"
            self._wb.Name                  # fails once our workbook has been closed
        except Exception as exc:   # noqa: BLE001 - any refusal other than "busy" means it is gone
            return "unknown" if is_busy(exc) else "closed"
        return "open"

    def _teardown(self) -> None:
        """Let go of Excel in the order that leaves no EXCEL.EXE behind; every step runs."""
        self._closed = True
        self._fail_read_waiters()
        steps = (self._close_sink, self._no_alerts, self._close_workbook, self._quit)
        for step in steps:
            try:
                step()
            except Exception:   # noqa: BLE001 - a failed step must not leave Excel running
                self.errors.append(traceback.format_exc())

    def _close_sink(self) -> None:
        sink, self._sink = self._sink, None
        if sink is not None:
            sink.close()

    def _no_alerts(self) -> None:
        if self._app is not None:
            self._app.DisplayAlerts = False

    def _close_workbook(self) -> None:
        wb, self._wb = self._wb, None
        try:
            if wb is not None:
                wb.Close(SaveChanges=self._save)
        finally:
            del wb
            gc.collect()

    def _quit(self) -> None:
        app, self._app = self._app, None
        try:
            if app is not None:
                app.Quit()
        finally:
            del app
            gc.collect()
