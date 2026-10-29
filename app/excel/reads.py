"""When to read Excel: after every change, never twice at once, and never giving up.

Excel's events only say "something changed". Each one asks for a read; a read already waiting
covers every event that arrives before it starts. Events that arrive while a read is running
(Excel can deliver them during our own calls to it) get one more read straight after, so the
last change is always read. A busy Excel is retried after 20 ms, doubling to at most 250 ms,
for as long as it takes: no change goes unread.

Everything here runs on the COM thread. call_later is that thread's timer, read() takes a
snapshot, deliver() hands it on and must return at once.
"""
from __future__ import annotations

import time
import traceback
from typing import Any, Callable

from app.excel.busy import is_busy, next_delay

MAX_ERRORS_KEPT = 20


class ReadScheduler:
    def __init__(self, call_later: Callable[[float, Callable[[], None]], None],
                 read: Callable[[], Any], deliver: Callable[[Any], None], *,
                 clock: Callable[[], int] = time.perf_counter_ns):
        self._call_later = call_later
        self._read = read
        self._deliver = deliver
        self._clock = clock
        self._queued = False                 # a read is waiting or running
        self._unread_since: int | None = None  # the oldest change no finished read has seen
        self._delay = 0.0
        self.latest: Any = None
        self.events = 0
        self.reads = 0
        self.busy_retries = 0
        self.errors: list[str] = []
        self.error_count = 0
        self.max_lag_ns = 0                  # change -> a snapshot that includes it

    def changed(self) -> None:
        """Excel said something changed. Returns at once; safe inside an event handler."""
        self.events += 1
        if self._unread_since is None:
            self._unread_since = self._clock()
        self.read_soon()

    def read_soon(self) -> None:
        if not self._queued:
            self._queued = True
            self._call_later(0.0, self._run)

    def _run(self) -> None:
        since, self._unread_since = self._unread_since, None
        try:
            snap = self._read()
        except Exception as exc:   # noqa: BLE001 - every failure is retried, none is fatal
            if is_busy(exc):
                self.busy_retries += 1
            else:
                self.error_count += 1
                if len(self.errors) < MAX_ERRORS_KEPT:
                    self.errors.append(traceback.format_exc())
            if since is not None:
                self._unread_since = since if self._unread_since is None \
                    else min(since, self._unread_since)
            self._delay = next_delay(self._delay)
            self._call_later(self._delay, self._run)   # still queued
            return

        self._delay = 0.0
        self.reads += 1
        if since is not None:
            self.max_lag_ns = max(self.max_lag_ns, self._clock() - since)
        self.latest = snap
        self._queued = False
        self._deliver(snap)
        if self._unread_since is not None:   # changes arrived while we were reading
            self.read_soon()

    @property
    def idle(self) -> bool:
        return not self._queued and self._unread_since is None
