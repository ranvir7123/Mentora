"""One lesson's Excel: our own copy of Excel, the lesson's workbook, its events, and a clean exit.

The session starts a new Excel (never the learner's own), opens the lesson's workbook from the
work folder, and listens to the workbook's events. Before any workbook opens, macros are forced off
in that Excel (AutomationSecurity 3), so no file it opens can run one; this lasts only for that Excel
and changes none of the learner's settings. An Excel that will not take it never opens the lesson.
Events only say "something changed", and Excel must not be called from inside one, so each handler
just asks the read scheduler for a read.

Closing is noticed two ways. BeforeClose says the learner asked to close, but they can still press
Cancel at the "save your changes?" box, so it only brings the next check forward. The check itself
runs every second on the COM thread and confirms the close: no workbooks left, our workbook gone,
the window gone, or Excel itself gone (killed outright). A busy Excel means "can't tell yet".
on_closed() then fires once; it never fires when the program closes the session itself. The owner
calls close() afterwards to let this Excel go.

perform() carries out one operation from the menu in ops.py; reset() puts the lesson's starter
back. Both run on the COM thread and ask for a read when they finish.

locate() says where a target is on screen now; watch() keeps saying it while the learner scrolls,
zooms, opens tabs or moves the window. A watch looks every 100 ms and at once when the window moves,
and tells on_spot only when the answer changes. When UI Automation cannot find a button, a picture of
the window can be shown to a model (set_vision_fallback); its answer is used only if UI Automation
finds a control of the same name at the middle of the rectangle it gave. The answer is kept for the
window's size and moves with the window; a new size is asked about once it stops changing. The
finding is in locate.py.

close() waits up to TEARDOWN_BUSY_LIMIT_S for a busy Excel (a learner who left a cell half-typed
keeps it busy for good). If it is still busy, this Excel is ended, unless it also shows workbooks
of the learner's own; either way it is said in `errors`. Every Future a caller holds fails once
the session closes, even one that was waiting out a busy Excel.

Every Excel call happens on the COM thread. on_snapshot and on_closed run there too and must
return at once.
"""
from __future__ import annotations

import gc
import threading
import time
import traceback
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app.core.lesson import Lesson
from app.core.types import Call, Rect, Spot, Target
from app.excel import locate, ops
from app.excel.busy import ExcelBusy, is_busy, next_delay
from app.excel.com_thread import ComThread
from app.excel.reads import ReadScheduler
from app.excel.snapshot import read_snapshot
from app.excel.starter import build_starter
from app.win import windows

CLOSED_CHECK_S = 1.0
CLOSED_CHECK_SOON_S = 0.25         # after BeforeClose: the learner is probably closing
IDLE_REREAD_S = 1.0                # while a step waits: freezing panes and renaming fire no event
PERFORM_BUSY_LIMIT_S = 30.0        # an operation Excel refuses for this long has failed
LOCATE_BUSY_LIMIT_S = 5.0          # a busy Excel for this long means "can't say where it is"
TEARDOWN_BUSY_LIMIT_S = 5.0        # closing waits this long for a busy Excel, then ends it
VISION_STILL_S = 0.3               # a picture is taken once the window has stopped changing this long
MACROS_FORCED_OFF = 3              # msoAutomationSecurityForceDisable


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


@dataclass
class _Watch:
    target: Target
    on_spot: Callable[[Spot | None], None]
    token: int
    tracker: Any = None                # made at the first look, and again after a reset
    told: bool = False
    last: Spot | None = None
    failed: bool = False


class ExcelSession:
    def __init__(self, lesson: Lesson, workdir: Path, *, visible: bool = True, resume: bool = False,
                 on_snapshot: Callable[[Any], None], on_closed: Callable[[], None],
                 excel_factory: Callable[[], Any] | None = None, com=None,
                 attach_events: Callable[[Any, Any], Any] | None = None,
                 reader: Callable[[Any], Any] = read_snapshot,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._lesson = lesson
        self.path = Path(workdir) / f"{lesson.id}.xlsx"
        self._visible = visible
        self._on_snapshot = on_snapshot
        self._on_closed = on_closed
        self._factory = excel_factory or _new_excel
        self._com = com or ComThread(f"excel-{lesson.id}")
        self._attach = attach_events or attach_workbook_events
        self._reader = reader
        self._sleep = sleep
        self.errors: list[str] = []
        self._app = None
        self._wb = None
        self._sink = None
        self._hwnd = 0                     # the window, when the learner can see it
        self._excel_hwnd = 0               # the window even when hidden
        self._pid = 0
        self._process = 0                  # a handle on this Excel, kept so it can be ended
        self._pending: set[Future] = set()   # every unfinished Future a caller holds
        self._pending_lock = threading.Lock()
        self._scheduler: ReadScheduler | None = None
        self._latest: Any = None
        self._closed = False           # the learner closed the workbook (or Excel went away)
        self._stopping = False         # the program is closing the session
        self._save = False
        self._check_token = 0
        self._waiting = False
        self._waiting_token = 0
        self._read_waiters: list[Future] = []
        self._watch: _Watch | None = None
        self._watch_token = 0
        self._unhook: Callable[[], None] | None = None
        self._look_queued = False
        self._vision: Callable[[bytes, str], Rect | None] | None = None
        self._vision_round = 0             # a new fallback forgets the old one's answers
        self._vision_known: dict[tuple, Rect | None] = {}   # (target, w, h) -> box from the window's corner
        self._vision_asking: set[tuple] = set()
        self._vision_place: Rect | None = None
        self._vision_still = True          # the window has not changed for VISION_STILL_S
        self._vision_settle = 0

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
        fut = self._promise()
        if fut.done():
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

    def perform(self, op: Call) -> Future:
        """Carry out one operation; the Future fails if Excel refuses it or stays busy too long."""
        fut = self._promise()
        if fut.done():
            return fut
        self._com.submit(lambda: self._attempt(op, fut, 0.0, 0.0))
        return fut

    def reset(self) -> Future:
        """Throw away the learner's changes: close without saving, rebuild the starter, reopen it."""
        fut = self._promise()
        if fut.done():
            return fut

        def run() -> None:
            try:
                self._reopen_starter()
            except Exception as exc:   # noqa: BLE001 - the caller sees why; the close check notices
                fut.set_exception(exc)
                return
            fut.set_result(None)
        self._com.submit(run)
        return fut

    def locate(self, target: Target) -> Future:
        """Where the target is on screen now (a Spot), or None when it can't be seen.

        This asks Excel and UI Automation only; the picture fallback is for watch(), where its slow
        answer can arrive later.
        """
        fut = self._promise()
        if fut.done():
            return fut

        def start() -> None:
            try:
                tracker = locate.tracker_for(target, self._app, self._wb, self._hwnd)
            except Exception as exc:   # noqa: BLE001 - a target Excel can't point at
                fut.set_exception(exc)
                return
            self._locate_attempt(tracker, fut, 0.0, 0.0)
        self._com.submit(start)
        return fut

    def watch(self, target: Target | None, on_spot: Callable[[Spot | None], None]) -> None:
        """Keep telling on_spot where target is (on the COM thread); None stops watching."""
        self._com.submit(lambda: self._set_watch(target, on_spot))

    def set_vision_fallback(self, fn: Callable[[bytes, str], Rect | None] | None) -> None:
        """fn(png of the window, target ref) -> the target's rectangle in pixels of that picture, from its
        top-left corner, or None. Asked off the COM thread, so it may be slow."""
        def change() -> None:
            self._vision = fn
            self._vision_round += 1
            self._vision_known.clear()
            self._vision_asking.clear()
        self._com.submit(change)

    def close(self, save: bool = False) -> None:
        """Close the workbook (saving it into the work folder if asked) and quit this Excel.

        Takes a moment, or up to about TEARDOWN_BUSY_LIMIT_S when Excel is busy (see the top).
        """
        if self._stopping:
            return
        self._stopping = True
        self._save = save
        self._com.stop()

    def _promise(self) -> Future:
        """A Future for a caller: failed now if the session is closed, and by close() if left unfinished."""
        fut: Future = Future()
        with self._pending_lock:
            if self._closed or self._stopping:
                fut.set_exception(RuntimeError("Excel was closed"))
                return fut
            self._pending.add(fut)
        fut.add_done_callback(self._forget)
        return fut

    def _forget(self, fut: Future) -> None:
        with self._pending_lock:
            self._pending.discard(fut)

    def _fail_pending(self) -> None:
        # A retry booked for later never runs once the COM thread stops, so its Future is failed here.
        with self._pending_lock:
            pending, self._pending = self._pending, set()
        for fut in pending:
            if not fut.done():
                fut.set_exception(RuntimeError("Excel was closed"))

    # ------------------------------------------------------------ on the COM thread

    def _setup(self) -> None:
        windows.dpi_aware_thread()
        self._app = self._factory()
        self._force_macros_off()
        self._app.Visible = self._visible
        # Held before anything can go wrong, so a closing that finds Excel stuck can still end it.
        self._pid = windows.process_id(int(self._app.Hwnd))
        self._process = windows.open_process(self._pid, named="excel.exe")
        self._wb = self._app.Workbooks.Open(str(self.path))
        self._sink = self._attach(self._wb, _Handler(self))
        self._excel_hwnd = int(self._app.Hwnd)     # read again: each workbook has its own window
        self._hwnd = self._excel_hwnd if self._visible else 0
        self._scheduler = ReadScheduler(self._com.call_later, self._read, self._deliver)
        self._scheduler.read_soon()
        self._schedule_check(CLOSED_CHECK_S)

    def _force_macros_off(self) -> None:
        self._app.AutomationSecurity = MACROS_FORCED_OFF
        if self._app.AutomationSecurity != MACROS_FORCED_OFF:
            raise RuntimeError("Excel would not turn macros off, so the lesson was not opened")

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

    def _attempt(self, op: Call, fut: Future, delay_s: float, waited_s: float) -> None:
        if self._closed or self._stopping:
            fut.set_exception(RuntimeError("Excel was closed"))
            return
        try:
            ops.do(self._app, self._wb, op)
        except Exception as exc:   # noqa: BLE001 - busy is waited out; anything else is the answer
            if not is_busy(exc):
                fut.set_exception(exc)
            elif waited_s >= PERFORM_BUSY_LIMIT_S:
                fut.set_exception(ExcelBusy(f"Excel stayed busy for {waited_s:.0f} s; {op.kind} was not done"))
            else:
                # Waiting is counted from the pauses, not the clock, so the limit means the same
                # in tests. An op that half-ran before the refusal (a chart) may run twice.
                pause = next_delay(delay_s)
                self._com.call_later(pause, lambda: self._attempt(op, fut, pause, waited_s + pause))
            return
        fut.set_result(None)
        self._scheduler.read_soon()

    def _reopen_starter(self) -> None:
        # The events go first, so the workbook closing is never taken for the learner closing it.
        self._close_sink()
        wb, self._wb = self._wb, None
        wb.Close(SaveChanges=False)
        del wb
        gc.collect()
        build_starter(self._lesson.starter, self.path)
        self._wb = self._app.Workbooks.Open(str(self.path))
        self._sink = self._attach(self._wb, _Handler(self))
        if self._watch is not None:
            self._watch.tracker = None     # it knew the old workbook
        self._scheduler.read_soon()

    def _locate_attempt(self, tracker, fut: Future, delay_s: float, waited_s: float) -> None:
        if self._closed or self._stopping:
            fut.set_exception(RuntimeError("Excel was closed"))
            return
        try:
            spot = tracker.spot()
        except Exception as exc:   # noqa: BLE001 - busy is waited out; any other refusal shows nothing
            if is_busy(exc) and waited_s < LOCATE_BUSY_LIMIT_S:
                pause = next_delay(delay_s)
                self._com.call_later(pause, lambda: self._locate_attempt(tracker, fut, pause, waited_s + pause))
                return
            spot = None
        fut.set_result(spot)

    def _set_watch(self, target: Target | None, on_spot: Callable[[Spot | None], None]) -> None:
        self._watch_token += 1             # the old watch's pending look finds a newer token
        self._stop_hook()
        self._watch = None
        if target is None or self._closed or self._stopping:
            return
        self._watch = _Watch(target, on_spot, self._watch_token)
        if self._hwnd:
            try:
                self._unhook = windows.location_hook(self._hwnd, self._look_soon)
            except Exception:   # noqa: BLE001 - the hook only makes looks quicker; the 100 ms looks go on
                self.errors.append(traceback.format_exc())
        self._look()
        self._watch_tick(self._watch_token)

    def _watch_tick(self, token: int) -> None:
        self._com.call_later(locate.WATCH_S, lambda: self._watch_tock(token))

    def _watch_tock(self, token: int) -> None:
        if token != self._watch_token or self._closed or self._stopping:
            return
        self._watch_tick(token)            # the next look is booked first, so a bad look never ends the watch
        self._look()

    def _look_soon(self) -> None:
        """The window moved: look at once, but only once for a burst of moves."""
        if self._look_queued:
            return
        self._look_queued = True

        def run() -> None:
            self._look_queued = False
            self._look()
        self._com.call_later(0, run)

    def _look(self) -> None:
        w = self._watch
        if w is None or w.token != self._watch_token or self._closed or self._stopping:
            return
        try:
            if w.tracker is None:
                w.tracker = locate.tracker_for(w.target, self._app, self._wb, self._hwnd)
            spot = w.tracker.spot()
        except Exception as exc:   # noqa: BLE001 - busy: skip this look; anything else: nothing on screen
            if is_busy(exc):
                return
            if not w.failed:           # kept once, not ten times a second
                w.failed = True
                self.errors.append(traceback.format_exc())
            spot = None
        if spot is None:
            spot = self._vision_spot(w.target)
        if not w.told or locate.moved(w.last, spot):
            w.told, w.last = True, spot
            w.on_spot(spot)

    def _vision_spot(self, target: Target) -> Spot | None:
        """The fallback's checked answer for this window size, moved to where the window is now.

        A drag only moves the answer. A new size may fold the ribbon differently, so it is asked
        about afresh, but only once the window has stopped changing: not once per pixel of a drag.
        """
        if self._vision is None or target.kind != "control" or not self._hwnd:
            return None
        place = windows.window_rect(self._hwnd)
        if self._vision_place is not None and place != self._vision_place:
            self._vision_still = False
            self._vision_settle += 1
            token = self._vision_settle
            self._com.call_later(VISION_STILL_S, lambda: self._vision_settled(token))
        self._vision_place = place
        key = (target, place.w, place.h)
        if self._vision_still and key not in self._vision_known and key not in self._vision_asking:
            self._ask_vision(key, target, place)
        box = self._vision_known.get(key)        # there already if the answer came back at once
        return None if box is None else Spot(Rect(place.x + box.x, place.y + box.y, box.w, box.h))

    def _vision_settled(self, token: int) -> None:
        if token != self._vision_settle or self._closed or self._stopping:
            return
        self._vision_still = True
        self._look_soon()

    def _ask_vision(self, key: tuple, target: Target, place: Rect) -> None:
        self._vision_asking.add(key)
        ask, round_ = self._vision, self._vision_round

        def run() -> None:                       # the picture is taken here too, off the COM thread
            try:
                windows.dpi_aware_thread()       # or the picture is of half the window
                rect = ask(windows.screenshot_png(place), target.ref)
            except Exception:   # noqa: BLE001 - a fallback that fails has found nothing
                rect = None
            self._com.submit(lambda: self._vision_answered(key, round_, target, place, rect))
        locate.background(run)

    def _vision_answered(self, key: tuple, round_: int, target: Target, asked_at: Rect,
                         rect: Rect | None) -> None:
        if round_ != self._vision_round or self._closed or self._stopping:
            return
        self._vision_asking.discard(key)
        place = windows.window_rect(self._hwnd)
        if (place.w, place.h) != (asked_at.w, asked_at.h):
            self._look_soon()                    # resized while the model thought: ask about the new size
            return
        box = rect                               # in the picture, so from the window's corner
        if box is not None and not locate.confirm_vision(Rect(place.x + box.x, place.y + box.y, box.w, box.h),
                                                         target):
            box = None
        # Answers for other sizes are dropped: a window is rarely put back to an old size.
        self._vision_known = {k: v for k, v in self._vision_known.items() if k[1:] == key[1:]}
        self._vision_known[key] = box
        self._look_soon()

    def _stop_hook(self) -> None:
        unhook, self._unhook = self._unhook, None
        if unhook is not None:
            unhook()

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
        """Let go of Excel in the order that leaves no EXCEL.EXE behind; every step runs.

        A busy Excel is waited out, TEARDOWN_BUSY_LIMIT_S in all. Past that, each step is tried
        once more and this Excel is ended (see _let_go_of_process).
        """
        self._closed = True
        self._fail_read_waiters()
        self._fail_pending()
        self._watch = None
        waited_s, stuck = 0.0, False
        for step in (self._stop_hook, self._close_sink, self._no_alerts, self._close_workbook):
            waited_s, busy = self._patiently(step, waited_s)
            stuck = stuck or busy
        self._sink = None
        self._wb = None
        gc.collect()
        waited_s, busy = self._patiently(self._quit, waited_s)
        stuck = stuck or busy
        self._app = None
        gc.collect()
        self._let_go_of_process(stuck)

    def _patiently(self, step: Callable[[], None], waited_s: float) -> tuple[float, bool]:
        """Run one closing step, waiting out "busy"; gives the time waited so far and whether it gave up."""
        delay_s = 0.0
        while True:
            try:
                step()
                return waited_s, False
            except Exception as exc:   # noqa: BLE001 - a failed step must not stop the ones after it
                if not is_busy(exc):
                    self.errors.append(traceback.format_exc())
                    return waited_s, False
                if waited_s >= TEARDOWN_BUSY_LIMIT_S:
                    return waited_s, True
            delay_s = next_delay(delay_s)
            self._sleep(delay_s)                 # on the COM thread, which has nothing else left to do
            waited_s += delay_s

    def _let_go_of_process(self, stuck: bool) -> None:
        """Close the handle on this Excel; first end it if it stayed busy and shows nothing of the learner's."""
        handle, self._process = self._process, 0
        try:
            if not stuck:
                return
            unsaved = " Its workbook was not saved." if self._save else ""
            if not handle:
                self.errors.append(f"Excel stayed busy while closing and could not be ended; it may still be "
                                   f"running.{unsaved}")
                return
            others = [w for w in windows.program_windows(self._pid)
                      if w != self._excel_hwnd and windows.class_name(w) == "XLMAIN"]
            if others:
                self.errors.append("Excel stayed busy while closing. It was left running because it also shows "
                                   f"workbooks of the learner's own.{unsaved}")
                return
            windows.end_process(handle)
            self.errors.append(f"Excel stayed busy for {TEARDOWN_BUSY_LIMIT_S:.0f} s while closing, so it was "
                               f"ended.{unsaved}")
        except Exception:   # noqa: BLE001 - kept; there is nothing left to try
            self.errors.append(traceback.format_exc())
        finally:
            if handle:
                windows.close_handle(handle)

    def _close_sink(self) -> None:
        if self._sink is not None:
            self._sink.close()
            self._sink = None

    def _no_alerts(self) -> None:
        if self._app is not None:
            self._app.DisplayAlerts = False

    def _close_workbook(self) -> None:
        if self._wb is not None:
            self._wb.Close(SaveChanges=self._save)

    def _quit(self) -> None:
        if self._app is not None:
            self._app.Quit()
