"""Runs one lesson: on every snapshot, the fixed checks decide which steps are done.

The AI never ticks a step; only a check does. `on_snapshot` takes the app's latest snapshot and returns
what the screens should show, as events in order. The clock is passed in, so tests control time.
"""
from __future__ import annotations

import time
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from app.core.lesson import Lesson, Step
from app.core.types import CheckKind, Verdict

MAX_ERRORS = 20


@dataclass(frozen=True)
class StepPassed:
    index: int
    first_try: bool
    points: int


@dataclass(frozen=True)
class NotYet:
    index: int
    text: str
    code: str


@dataclass(frozen=True)
class StepChanged:
    index: int                   # a done step's check now fails


@dataclass(frozen=True)
class StepFixed:
    index: int


@dataclass(frozen=True)
class LessonDone:
    seconds: float
    points: int
    first_try: int
    steps: int


@dataclass(frozen=True)
class StepRecord:
    step_id: str
    tries: int
    hints: int
    seconds: float
    first_try: bool


@dataclass
class _Progress:
    """What happened on one step so far."""
    tries: int = 0
    hints: int = 0
    said_not_yet: bool = False
    last_wrong: tuple[str, str] | None = None    # the (code, text) of the last Not yet said


class LessonRun:
    def __init__(self, lesson: Lesson, checks: Mapping[str, CheckKind], *,
                 clock: Callable[[], float] = time.monotonic, points_per_step: int = 10):
        self._steps = lesson.steps
        self._checks = checks
        self._clock = clock
        self._points_per_step = points_per_step
        self._started = clock()
        self._step_started = self._started
        self._progress = [_Progress() for _ in self._steps]
        self._records: list[StepRecord] = []
        self._changed: set[int] = set()
        self._points = 0
        self.index = 0
        self.done = False
        self.errors: list[str] = []

    @property
    def changed(self) -> frozenset[int]:
        return frozenset(self._changed)

    def on_snapshot(self, snap: Any) -> list[object]:
        events: list[object] = []
        for i in range(self.index):
            ok = self._judge(self._steps[i], snap).ok
            if not ok and i not in self._changed:
                self._changed.add(i)
                events.append(StepChanged(i))
            elif ok and i in self._changed:
                self._changed.discard(i)
                events.append(StepFixed(i))
        if self.done:
            return events

        verdict = self._judge(self._steps[self.index], snap)
        while verdict.ok:
            events.append(self._pass())
            if self.index == len(self._steps):
                self.done = True
                events.append(LessonDone(self._clock() - self._started, self._points,
                                         sum(r.first_try for r in self._records), len(self._steps)))
                return events
            verdict = self._judge(self._steps[self.index], snap)

        progress = self._progress[self.index]
        if not verdict.attempted:
            progress.last_wrong = None
        elif (verdict.code, verdict.text) != progress.last_wrong:
            progress.last_wrong = (verdict.code, verdict.text)
            progress.tries += 1
            progress.said_not_yet = True
            events.append(NotYet(self.index, self._not_yet_line(verdict), verdict.code))
        return events

    def hint(self) -> str | None:
        if self.done:
            return None
        step, progress = self._steps[self.index], self._progress[self.index]
        if progress.hints >= len(step.hints):
            return None
        progress.hints += 1
        return step.hints[progress.hints - 1]

    def hints_shown(self) -> tuple[str, ...]:
        if self.done:
            return ()
        return self._steps[self.index].hints[:self._progress[self.index].hints]

    def records(self) -> list[StepRecord]:
        return list(self._records)

    def _judge(self, step: Step, snap: Any) -> Verdict:
        try:
            return self._checks[step.check.kind].run(snap, step.check.args)
        except Exception as exc:
            if len(self.errors) < MAX_ERRORS:
                self.errors.append(traceback.format_exception_only(exc)[-1].strip())
            return Verdict.waiting()

    def _not_yet_line(self, verdict: Verdict) -> str:
        if verdict.code:
            for mistake in self._steps[self.index].mistakes:
                if mistake.code == verdict.code:
                    return mistake.not_yet
        return verdict.text

    def _pass(self) -> StepPassed:
        now, step, progress = self._clock(), self._steps[self.index], self._progress[self.index]
        first_try = not progress.said_not_yet
        self._records.append(StepRecord(step.id, progress.tries + 1, progress.hints,
                                        now - self._step_started, first_try))
        self._points += self._points_per_step
        self._step_started = now
        self.index += 1
        return StepPassed(self.index - 1, first_try, self._points_per_step)
