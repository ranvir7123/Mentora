"""Meta's computer-use agent plays a lesson as a learner, in the real app, to show a person can do it.

One run opens the app, puts its window where a lesson puts it (the screen beside the 360 px strip) and
gives the agent one step at a time, each step in a fresh conversation. The agent sees screenshots of the
app's window only, taken only while the app is in front and no other program's window is over it, so
nothing else on the screen reaches Meta. Every action it asks for is checked first: the pointer stays
inside the app, keys that Windows itself acts on (leaving or closing the app) are refused, and in keyboard
mode the mouse is not used at all. Only the lesson's own checks decide when a step is done, as for a learner.
A test passes when at least 4 runs in 5 reach the end; it stops early once that can no longer happen.
"""
from __future__ import annotations

import base64
import threading
import time
from concurrent.futures import Future
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from app.core.lesson import Lesson, Step, TestResult
from app.core.plugin import AppPlugin
from app.core.runner import LessonRun, NotYet, StepChanged
from app.core.types import Rect
from app.factory.input import POINTER_ACTIONS, WindowsHands, vk_for
from app.factory.prove import ProveError
from app.meta.client import MetaError, NoKey, SpendLimitReached

MODEL = "muse-wonder-1.0"
TOOLS = [{"type": "computer"}]
STRIP_PX = 360                   # the lesson panel, in logical pixels, at the screen's right edge
MAX_SHOT = (1280, 800)
TIMEOUT_S = 30.0
PASS_OF = (4, 5)                 # at least 4 runs in 5
COVER_WAIT_S, COVER_TRIES = 1.0, 10   # a notification over the app is gone within about 5 s

OUTSIDE_NOTE = "That is outside the app. Use the app's window."
KEYBOARD_NOTE = "This test uses the keyboard only. Use keys, not the mouse."
LEAVES_NOTE = "That key would leave the app. Stay in the app's window."
BUTTON_NOTE = "Use the left, right or middle mouse button."
KEYS_NOTE = 'Send keys as a list, like ["ctrl", "c"].'

Mode = Literal["mouse", "keyboard"]
_BUTTONS = {"left", "right", "wheel", "middle"}
# Combinations Windows itself acts on: they switch, close or cover the app, or open the security screen.
# Only keys input.py knows can be sent at all, so Print Screen, media and browser keys never are.
# Keys that act inside the app stay allowed (alt+enter is a new line in an Excel cell, shift+f10 its menu).
_LEAVING = [{vk_for(k) for k in keys} for keys in
            (["win"], ["alt", "tab"], ["alt", "esc"], ["ctrl", "esc"], ["alt", "f4"], ["ctrl", "f4"], ["ctrl", "w"],
             ["alt", "space"], ["ctrl", "alt", "delete"])]


# Where things go on the screen.

def layout(hands) -> Rect:
    """The app's window: the work area (the screen above the taskbar) beside the lesson panel's strip."""
    work = hands.work_area()
    return Rect(work.x, work.y, work.w - STRIP_PX * hands.scale(), work.h)


def shot_size(app: Rect, scale: float) -> tuple[int, int]:
    """The screenshot's size: the app as a person sees it (logical pixels), shrunk to fit 1280 x 800."""
    f = max(scale, app.w / MAX_SHOT[0], app.h / MAX_SHOT[1])
    return round(app.w / f), round(app.h / f)


def to_screen(action: dict, app: Rect, shot: tuple[int, int]) -> dict:
    """An action in screenshot pixels, moved to screen pixels."""
    fx, fy = app.w / shot[0], app.h / shot[1]

    def at(p: dict) -> dict:
        return {**p, "x": round(app.x + p["x"] * fx), "y": round(app.y + p["y"] * fy)}

    moved = dict(action)
    if "x" in action and "y" in action:
        moved.update(at(action))
    if isinstance(action.get("path"), list):
        moved["path"] = [at(p) for p in action["path"]]
    return moved


def allowed(action: dict, app: Rect, mode: Mode) -> tuple[bool, str]:
    """Whether to do this action (in screen pixels); when not, the note the agent is told."""
    kind = action.get("type")
    ok, note = _keys_allowed(action.get("keys") or [])       # any action may carry keys; all are checked
    if not ok:
        return ok, note
    if kind in POINTER_ACTIONS:
        if mode == "keyboard":
            return False, KEYBOARD_NOTE
        if action.get("button", "left") not in _BUTTONS:
            return False, BUTTON_NOTE
        points = action.get("path") if kind == "drag" else [action]
        if not points or not all(_inside(p, app) for p in points):
            return False, OUTSIDE_NOTE
        return True, ""
    if kind in ("keypress", "type", "wait", "screenshot"):
        return True, ""
    return False, f"{kind} is not something this test can do."


def _inside(p: Any, app: Rect) -> bool:
    try:
        return app.x <= p["x"] < app.x + app.w and app.y <= p["y"] < app.y + app.h
    except (KeyError, TypeError):
        return False


def _keys_allowed(keys: Any) -> tuple[bool, str]:
    if not isinstance(keys, (list, tuple)):
        return False, KEYS_NOTE
    codes = set()
    for key in keys:
        try:
            codes.add(vk_for(str(key)))
        except ValueError:
            return False, f"There is no key called {key}."
    if any(combo <= codes for combo in _LEAVING):
        return False, LEAVES_NOTE
    return True, ""


# The test.

def test_lesson(lesson: Lesson, plugin: AppPlugin, workdir: Path, client, *, model: str = MODEL, runs: int = 5,
                mode: Mode = "mouse", max_actions_per_step: int = 25, hands=None,
                on_line: Callable[[str], None] | None = None) -> TestResult:
    """Run the lesson `runs` times with Meta's agent as the learner. Raises UserTookOver when a person moves
    the mouse, ProveError when the app itself gets in the way, and NoKey or SpendLimitReached from Meta."""
    hands = hands or WindowsHands()
    say = on_line or (lambda line: None)
    need = -(-runs * PASS_OF[0] // PASS_OF[1])
    passes = done = 0
    for number in range(1, runs + 1):
        failure = _Run(lesson, plugin, Path(workdir), client, hands, say, model=model, mode=mode, number=number,
                       budget=max_actions_per_step).go()
        done += 1
        if failure is None:
            passes += 1
            say(f"run {number} passed")
        else:
            say(f"run {number} failed: {failure}")
        if passes + runs - done < need:
            break
    stopped = f" (stopped: it can no longer pass {need} of {runs})" if done < runs else ""
    say(f"{passes} of {done} runs passed{stopped}")
    return TestResult(passed=passes >= need, at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                      mode=mode, runs=done, passes=passes)


class _RunFailed(Exception):
    """This run failed; the message says why, in plain words."""


class _Run:
    def __init__(self, lesson: Lesson, plugin: AppPlugin, workdir: Path, client, hands, say, *, model: str,
                 mode: Mode, number: int, budget: int):
        self.lesson, self.plugin, self.workdir, self.client, self.hands, self.say = \
            lesson, plugin, workdir, client, hands, say
        self.model, self.mode, self.number, self.budget = model, mode, number, budget
        self.closed = threading.Event()
        self.runner = LessonRun(lesson, plugin.checks)

    def go(self) -> str | None:
        """None when the run reached the end of the lesson, else why it failed."""
        title = self.plugin.title
        try:
            session = self.plugin.open(self.lesson, self.workdir, visible=True, resume=False,
                                       on_snapshot=lambda snap: None, on_closed=self.closed.set)
        except Exception as exc:
            raise ProveError(f"{title} could not be opened: {_said(exc)}") from exc
        try:
            self.session = session
            self.app = layout(self.hands)
            self._wait(session.place(self.app), "could not be put in place")
            self.shot = shot_size(self.app, self.hands.scale())
            self.runner.on_snapshot(self._read())
            steps = self.lesson.steps
            while self.runner.index < len(steps):
                self._step(steps[self.runner.index])
            if not self.runner.done:
                undone = ", ".join(steps[i].id for i in sorted(self.runner.changed))
                raise _RunFailed(f"a later step undid step {undone}")
            return None
        except _RunFailed as failed:
            return str(failed)
        except (NoKey, SpendLimitReached):
            raise
        except MetaError as exc:
            return str(exc)
        finally:
            try:
                session.close(save=False)
            except Exception as exc:
                self.say(f"{title} did not close cleanly: {_said(exc)}")

    def _step(self, step: Step) -> None:
        index, used, turn, previous, last_not_yet = self.runner.index, 0, 0, None, ""
        self._ready()
        sent: list = [_message(self._brief(step), self._look())]
        while True:
            turn += 1
            answer = self.client.respond(self.model, sent, label=self._label(step, turn), tools=TOOLS,
                                         previous_response_id=previous)
            previous = answer.response_id
            calls = [item for item in answer.output if item.get("type") == "computer_call"]
            checks = [c for call in calls for c in call.get("pending_safety_checks") or []]
            if checks:
                codes = ", ".join(str(c.get("code") or "unnamed") for c in checks)
                said = " ".join(str(c.get("message") or "") for c in checks).strip()
                raise _RunFailed(f"Meta's agent raised a safety check ({codes}): {said}")
            notes: list[str] = []
            if calls:
                used = self._do(calls, used, notes)
            else:
                used += 1                                # the agent stopped; that counts against the step
            for event in self._judge():
                if isinstance(event, NotYet):
                    last_not_yet = event.text
                    notes.append(f"The lesson says: {event.text}")
                elif isinstance(event, StepChanged):
                    notes.append(f"The lesson says: step {event.index + 1} is not done any more.")
            if self.runner.index > index:
                self.say(f"run {self.number}: step {step.id} done after {used} action{'' if used == 1 else 's'}")
                return
            if used >= self.budget:
                raise _RunFailed(f"step {step.id} was not done after {self.budget} actions")
            self._ready()
            image = self._look()
            if calls:
                sent = [{"type": "computer_call_output", "call_id": call.get("call_id"),
                         "output": {"type": "computer_screenshot", "image_url": image}} for call in calls]
                if notes:
                    sent.append(_message(" ".join(notes)))
            else:
                if not notes and last_not_yet:
                    notes.append(f"The lesson says: {last_not_yet}")
                sent = [_message(" ".join(["This step is not done yet.", *notes, "Look at the app and finish it."]),
                                 image)]

    def _do(self, calls: list[dict], used: int, notes: list[str]) -> int:
        """Do the actions asked for, until one is refused or the step's actions run out."""
        for call in calls:
            actions = call.get("actions") or ([call["action"]] if call.get("action") else [])
            if not actions:
                used += 1
            for action in actions:
                if used >= self.budget:
                    return used
                used += 1
                action = to_screen(action, self.app, self.shot)
                ok, note = allowed(action, self.app, self.mode)
                if not ok:
                    self.say(f"refused {_said_action(action)}: {note}")
                    notes.append(note)
                    return used                          # the rest of the batch waits for a new look
                self._ready()
                self.hands.do(action)
        return used

    def _brief(self, step: Step) -> str:
        app = self.plugin.title
        how = "Use the keyboard only, not the mouse." if self.mode == "keyboard" else "Use the mouse and keyboard."
        return (f"You are a learner doing a lesson in {app}. The lesson's goal: {self.lesson.goal.sentence} "
                f"The screenshot shows {app}'s window and nothing else. {how} Stay in {app}: do not open other "
                f"programs, files or web pages, and do not close anything. When the step is done, stop. "
                f"Do only this step, then stop: {step.instruction}")

    def _label(self, step: Step, turn: int) -> str:
        return f"tester_{self.lesson.id}_{self.mode}_run{self.number}_{step.id}_{turn}"

    def _ready(self) -> None:
        """Before looking or acting: the app is still open, its window is in front and no other program's
        window is over it, so a screenshot shows the app alone and a click lands in it."""
        title = self.plugin.title
        if self.closed.is_set():
            raise _RunFailed(f"{title} was closed")
        hwnd = self.session.hwnd()
        if not self.hands.in_front(hwnd):
            self.hands.to_front(hwnd)
            if not self.hands.in_front(hwnd):
                raise _RunFailed(f"{title}'s window would not come to the front, so nothing more was done")
        waits = COVER_TRIES
        while self.hands.covered(hwnd, self.app):
            if waits == 0:
                raise _RunFailed(f"another program's window stayed over {title}, so nothing more was done")
            waits -= 1
            time.sleep(COVER_WAIT_S)

    def _look(self) -> str:
        png = self.hands.grab(self.app, *self.shot)
        return "data:image/png;base64," + base64.b64encode(png).decode("ascii")

    def _judge(self) -> list[object]:
        if self.closed.is_set():
            raise _RunFailed(f"{self.plugin.title} was closed")
        return self.runner.on_snapshot(self._read())

    def _read(self) -> Any:
        try:
            return self._wait(self.session.read_now(), "could not be read")
        except ProveError:
            if self.closed.is_set():
                raise _RunFailed(f"{self.plugin.title} was closed") from None
            raise

    def _wait(self, future: Future, failed: str) -> Any:
        title = self.plugin.title
        try:
            return future.result(timeout=TIMEOUT_S)
        except TimeoutError:
            raise ProveError(f"{title} did not answer within {TIMEOUT_S:g} s") from None
        except Exception as exc:
            raise ProveError(f"{title} {failed}: {_said(exc)}") from exc


def _message(text: str, image: str | None = None) -> dict:
    content: list[dict] = [{"type": "input_text", "text": text}]
    if image:
        content.append({"type": "input_image", "image_url": image})
    return {"role": "user", "content": content}


def _said(exc: BaseException) -> str:
    return str(exc) or type(exc).__name__


def _said_action(action: dict) -> str:
    kind = action.get("type")
    if kind == "drag" and action.get("path"):
        a, b = action["path"][0], action["path"][-1]
        return f"drag from {a.get('x')}, {a.get('y')} to {b.get('x')}, {b.get('y')}"
    if "x" in action and "y" in action:
        return f"{kind} at {action['x']}, {action['y']}"
    if kind == "keypress":
        return "keypress " + "+".join(str(k) for k in action.get("keys") or [])
    return str(kind)
