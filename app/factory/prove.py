"""Proving a lesson in the real app, the way a learner would go through it.

For each step in order: its check must be false before the step; each predicted mistake, performed
from that state, must be noticed and rejected by the check (its verdict code is kept, so the learner
sees that mistake's own "Not yet" line); then the step's replay must make the check true and leave every
earlier step's check true (a step that undoes one would stop the lesson from ever celebrating). A step that
fails goes back to Muse Spark once with the reason; if it fails again it is dropped and the whole lesson
is proven again from the start without it, so a later step that needed it is dropped too. A dropped step
stays out: Muse Spark is told to leave it out of any later rewrite, and it is taken out if it comes back.
"""
from __future__ import annotations

import traceback
from concurrent.futures import Future
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.core.lesson import Lesson, Proof, Step
from app.core.plugin import AppPlugin, AppSession
from app.core.types import Call, Verdict
from app.factory.writer import NotReady

MIN_STEPS = 3
TIMEOUT_S = 30.0

Fix = Callable[[Lesson, str], "Lesson | NotReady"]


class ProveError(Exception):
    """The app itself got in the way (it would not open or stopped answering); no step is to blame."""


@dataclass(frozen=True)
class Proved:
    lesson: Lesson                               # with `proof` filled and each mistake's `code`
    dropped: list[str]                           # ids of the steps taken out
    notes: list[str]                             # plain words: what went back, what was dropped and why
    why: dict[str, str]                          # each dropped step's id: why it was dropped


@dataclass(frozen=True)
class _Failed:
    step_id: str
    reason: str


class _StepFailed(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def prove(lesson: Lesson, plugin: AppPlugin, workdir: Path, *, fix: Fix | None = None) -> Proved:
    current, dropped, notes, why = lesson, [], [], {}
    said: dict[str, str] = {}                    # each dropped step's instruction, for the writer
    sent_back: set[str] = set()
    fixes_left = len(lesson.steps)               # a fix may rename steps; this keeps the retries finite
    changed = False
    while True:
        failed, codes = _run(current, plugin, Path(workdir))
        if failed is None:
            break
        changed = True
        at = f"step {failed.step_id}"
        if fix is not None and failed.step_id not in sent_back and fixes_left > 0:
            sent_back.add(failed.step_id)
            fixes_left -= 1
            left_out = "".join(f'; leave out step {d} ("{said[d]}"), which was dropped' for d in dropped)
            fixed = fix(current, f"{at}: {failed.reason}{left_out}")
            if isinstance(fixed, Lesson):
                notes.append(f"{at} went back to Muse Spark: {failed.reason}")
                current = replace(fixed, steps=tuple(s for s in fixed.steps if s.id not in dropped))
                continue
            notes.append(f"{at} went back to Muse Spark, which could not fix it: {fixed.detail or fixed.reason}")
        if failed.step_id not in dropped:
            dropped.append(failed.step_id)
            said[failed.step_id] = next(s.instruction for s in current.steps if s.id == failed.step_id)
        why[failed.step_id] = failed.reason
        notes.append(f"{at} was dropped: {failed.reason}")
        current = replace(current, steps=tuple(s for s in current.steps if s.id != failed.step_id))

    steps = tuple(replace(s, mistakes=tuple(replace(m, code=codes[(s.id, j)]) for j, m in enumerate(s.mistakes)))
                  for s in current.steps)
    notes += _same_code_notes(steps)
    n = len(steps)
    if n < MIN_STEPS:
        left = "no steps are left" if n == 0 else f"only {n} step{'' if n == 1 else 's'} {'is' if n == 1 else 'are'} left"
        notes.append(f"{left}; a lesson needs at least {MIN_STEPS}")
    proof = Proof(passed=n >= MIN_STEPS, at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                  dropped=tuple(dropped), notes=tuple(notes))
    proven = replace(current, steps=steps, proof=proof, test=None if changed else current.test)
    return Proved(proven, dropped, notes, why)


def _run(lesson: Lesson, plugin: AppPlugin, workdir: Path) -> tuple[_Failed | None, dict[tuple[str, int], str]]:
    """One run through every step; the first failure, or None and every mistake's verdict code."""
    try:
        session = plugin.open(lesson, workdir, visible=False, resume=False,
                              on_snapshot=lambda snap: None, on_closed=lambda: None)
    except Exception as exc:
        raise ProveError(f"{plugin.title} could not be opened: {_said(exc)}") from exc
    codes: dict[tuple[str, int], str] = {}
    try:
        for i, step in enumerate(lesson.steps):
            try:
                _prove_step(session, plugin, lesson.steps[:i], step, codes)
            except _StepFailed as failed:
                return _Failed(step.id, failed.reason), codes
    finally:
        session.close(save=False)
    return None, codes


def _prove_step(session: AppSession, plugin: AppPlugin, before: tuple[Step, ...], step: Step,
                codes: dict[tuple[str, int], str]) -> None:
    if _judge(plugin, step, _snap(session, plugin)).ok:
        raise _StepFailed("its check was already true before the step")
    for j, mistake in enumerate(step.mistakes):
        what = f"mistake {j + 1} ({_said_call(mistake.replay)})"
        _perform(session, plugin, mistake.replay, f"the app refused mistake {j + 1}")
        verdict = _judge(plugin, step, _snap(session, plugin))
        if verdict.ok:
            raise _StepFailed(f"its check accepted {what}, so the check is too loose")
        if not verdict.attempted:
            raise _StepFailed(f"its check did not notice {what}, so the learner would get no Not yet line")
        codes[(step.id, j)] = verdict.code
        _back_to(session, plugin, before)
    _perform(session, plugin, step.replay, "the app refused the step's replay")
    snap = _snap(session, plugin)
    if not _judge(plugin, step, snap).ok:
        raise _StepFailed("its check was still not true after the step")
    for earlier in before:                       # the lesson celebrates only while every earlier step still holds
        try:
            held = _judge(plugin, earlier, snap).ok
        except _StepFailed:
            continue                             # as the lesson does: a crashed check says nothing here
        if not held:
            raise _StepFailed(f"it undid step {earlier.id}, whose check is no longer true")


def _back_to(session: AppSession, plugin: AppPlugin, before: tuple[Step, ...]) -> None:
    """Back to the state just before this step: the starter, then every kept step before it."""
    try:
        _wait(session.reset(), plugin)
        for earlier in before:
            _wait(session.perform(earlier.replay), plugin)
    except ProveError:
        raise
    except Exception as exc:
        raise ProveError(f"{plugin.title} could not go back to the start of the step: {_said(exc)}") from exc


def _perform(session: AppSession, plugin: AppPlugin, op: Call, refused: str) -> None:
    try:
        _wait(session.perform(op), plugin)
    except ProveError:
        raise
    except Exception as exc:
        raise _StepFailed(f"{refused} ({_said(exc)})") from exc


def _snap(session: AppSession, plugin: AppPlugin) -> Any:
    try:
        return _wait(session.read_now(), plugin)
    except ProveError:
        raise
    except Exception as exc:
        raise ProveError(f"{plugin.title} could not be read: {_said(exc)}") from exc


def _judge(plugin: AppPlugin, step: Step, snap: Any) -> Verdict:
    try:
        return plugin.checks[step.check.kind].run(snap, step.check.args)
    except Exception as exc:
        raise _StepFailed(f"its check crashed ({traceback.format_exception_only(exc)[-1].strip()})") from exc


def _wait(future: Future, plugin: AppPlugin) -> Any:
    try:
        return future.result(timeout=TIMEOUT_S)
    except TimeoutError:
        raise ProveError(f"{plugin.title} did not answer within {TIMEOUT_S:g} s") from None


def _said(exc: BaseException) -> str:
    return str(exc) or type(exc).__name__


def _said_call(call: Call) -> str:
    return " ".join([call.kind, *(f"{k}={v}" for k, v in call.args.items())])


def _same_code_notes(steps: tuple[Step, ...]) -> list[str]:
    notes = []
    for step in steps:
        first: dict[str, int] = {}
        for j, mistake in enumerate(step.mistakes, 1):
            if mistake.code in first:
                notes.append(f"step {step.id}: mistakes {first[mistake.code]} and {j} get the same verdict "
                             f"({mistake.code}), so only mistake {first[mistake.code]}'s Not yet line can show")
            else:
                first[mistake.code] = j
    return notes
