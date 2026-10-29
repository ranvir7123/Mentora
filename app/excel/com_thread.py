"""One thread that owns every Excel object, and sleeps until something happens.

A COM object may only be used from the thread that made it, and Excel delivers its events only
to a thread that pumps Windows messages. So one thread does both: it waits in the kernel on
(stop, queued work, the next timer, a message from Excel) and burns no processor while waiting.

Work from other threads arrives through submit(); the thread's own code schedules retries with
call_later(). Nothing here talks to Excel by itself.
"""
from __future__ import annotations

import concurrent.futures
import heapq
import itertools
import queue
import threading
import time
import traceback
from typing import Any, Callable

import pythoncom
import win32event

READY_TIMEOUT_S = 120
STOP_TIMEOUT_S = 30


class ComThread:
    def __init__(self, name: str = "excel-com"):
        self.name = name
        self.errors: list[str] = []
        self._work: queue.Queue = queue.Queue()
        self._timers: list[tuple[float, int, Callable[[], None]]] = []
        self._seq = itertools.count()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._stop_evt = win32event.CreateEvent(None, True, False, None)    # manual reset
        self._work_evt = win32event.CreateEvent(None, False, False, None)   # auto reset

    # ------------------------------------------------------------ from any thread

    def start(self, setup: Callable[[], None], teardown: Callable[[], None]) -> None:
        """Run setup() on the new thread, then pump until stop(); teardown() runs on the way out."""
        self._thread = threading.Thread(target=self._main, args=(setup, teardown),
                                        name=self.name, daemon=True)
        self._thread.start()
        if not self._ready.wait(READY_TIMEOUT_S):
            self.stop()
            raise RuntimeError(f"{self.name} did not start within {READY_TIMEOUT_S}s")
        if self.errors:
            raise RuntimeError(f"{self.name} failed to start:\n" + "\n".join(self.errors))

    def submit(self, fn: Callable[[], Any]) -> concurrent.futures.Future:
        """Run fn on this thread; the Future holds its result or its exception."""
        fut: concurrent.futures.Future = concurrent.futures.Future()
        self._work.put((fn, fut))
        win32event.SetEvent(self._work_evt)
        return fut

    def stop(self) -> None:
        win32event.SetEvent(self._stop_evt)
        if self._thread is not None:
            self._thread.join(STOP_TIMEOUT_S)

    def on_thread(self) -> bool:
        return threading.current_thread() is self._thread

    # ------------------------------------------------------------ on this thread only

    def call_later(self, delay_s: float, fn: Callable[[], None]) -> None:
        assert self.on_thread(), "call_later is for the COM thread's own code"
        heapq.heappush(self._timers, (time.perf_counter() + max(0.0, delay_s), next(self._seq), fn))

    def _main(self, setup, teardown) -> None:
        pythoncom.CoInitialize()
        try:
            try:
                setup()
            except Exception:   # noqa: BLE001
                self.errors.append(traceback.format_exc())
                return
            finally:
                self._ready.set()
            self._pump()
        finally:
            self._drain_work(cancel=True)
            try:
                teardown()
            except Exception:   # noqa: BLE001
                self.errors.append(traceback.format_exc())
            pythoncom.CoUninitialize()

    def _pump(self) -> None:
        handles = (self._stop_evt, self._work_evt)
        while True:
            timeout_ms = win32event.INFINITE
            if self._timers:
                timeout_ms = max(0, int((self._timers[0][0] - time.perf_counter()) * 1000))
            rc = win32event.MsgWaitForMultipleObjects(handles, False, timeout_ms,
                                                      win32event.QS_ALLINPUT)
            if rc == win32event.WAIT_OBJECT_0:            # stop
                return
            if rc == win32event.WAIT_OBJECT_0 + 1:        # work queued
                self._drain_work()
            elif rc == win32event.WAIT_OBJECT_0 + 2:      # Excel posted messages (its events)
                pythoncom.PumpWaitingMessages()
            elif rc != win32event.WAIT_TIMEOUT:           # abandoned or failed wait
                return
            self._run_due_timers()

    def _run_due_timers(self) -> None:
        now = time.perf_counter()
        while self._timers and self._timers[0][0] <= now:
            _due, _seq, fn = heapq.heappop(self._timers)
            try:
                fn()
            except Exception:   # noqa: BLE001 - one bad callback must not stop the pump
                self.errors.append(traceback.format_exc())

    def _drain_work(self, *, cancel: bool = False) -> None:
        while True:
            try:
                fn, fut = self._work.get_nowait()
            except queue.Empty:
                return
            if cancel:
                fut.cancel()
                continue
            try:
                fut.set_result(fn())
            except Exception as exc:   # noqa: BLE001
                fut.set_exception(exc)
