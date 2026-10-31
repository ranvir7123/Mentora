"""Meta's computer-use agent plays a lesson as a learner, in the real app, to show a person can do it.

One run opens the app, puts its window where a lesson puts it (the screen beside the 360 px strip) and
gives the agent one step at a time, each step in a fresh conversation. The agent sees screenshots of the
app's window only, taken only while the app is in front, still where it was put, and no other program's
window is over it, so nothing else on the screen reaches Meta. Every action it asks for is checked first:
it must be well formed, the pointer stays inside the app and over the app's own windows, keys that Windows
itself acts on (leaving or closing the app) and keys that open the app's macros, add a link or open a new
workbook are refused, text it types keeps the rules a lesson's own text keeps (what it types into a cell is
checked as a whole, so a link or a forbidden formula cannot be split over several actions, and Tab is refused
while a formula is being typed so Excel's AutoComplete cannot finish a function name for it), and in keyboard
mode the mouse is not used at all.
Once the run has looked at the app, another window coming to the front means a person took over, and the test stops. Only the lesson's own checks decide when a step is done.
A test passes when at least 4 runs in 5 reach the end; it stops early once that can no longer happen.
"""
from __future__ import annotations

import base64
import math
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
from app.factory.input import POINTER_ACTIONS, UserTookOver, WindowsHands, vk_for
from app.factory.prove import ProveError, app_trouble
from app.factory.writer import FORMULA_START, NEXT_CELL, _reaches
from app.meta.client import MetaError, NoKey, SpendLimitReached

MODEL = "muse-wonder-1.0"
TOOLS = [{"type": "computer"}]
STRIP_PX = 360                   # the lesson panel, in logical pixels, at the screen's right edge
MAX_SHOT = (1280, 800)
TIMEOUT_S = 30.0
PASS_OF = (4, 5)                 # at least 4 runs in 5
COVER_WAIT_S, COVER_TRIES = 1.0, 10   # a notification over the app is gone within about 5 s
PLACE_PX = 2                     # how far the window may be from where it was put

OUTSIDE_NOTE = "That is outside the app. Use the app's window."
KEYBOARD_NOTE = "This test uses the keyboard only. Use keys, not the mouse."
LEAVES_NOTE = "That key would leave the app. Stay in the app's window."
BUTTON_NOTE = "Use the left, right or middle mouse button."
KEYS_NOTE = 'Send keys as a list, like ["ctrl", "c"].'
SHAPE_NOTE = "Send each action as an object with a type, such as click or type."
POINT_NOTE = "Give x and y as numbers in the screenshot."
PATH_NOTE = "Give a drag's path as a list of points, each with x and y as numbers."
SCROLL_NOTE = "Give scroll_x and scroll_y as numbers."
TEXT_NOTE = "Give the text to type."
MACROS_NOTE = "That key opens the app's macros, which a lesson never needs."
LINK_KEY_NOTE = "That key adds a link, which would reach outside the app."
NEW_WORKBOOK_NOTE = "That key opens a new workbook outside the lesson. Stay in this one."
TAB_NOTE = "Type the whole formula yourself; Tab here would let Excel finish a function name for you."

Mode = Literal["mouse", "keyboard"]
_BUTTONS = {"left", "right", "wheel", "middle"}
# Keys that end or move a cell's edit, so what was typed into it starts over. Tab is here too: Tab is only
# ever allowed when no formula is being typed (see `allowed`), and then it moves to the next cell.
_ENDS_EDIT = {vk_for(k) for k in ("enter", "return", "esc", "escape", "tab")}
_ARROWS = {vk_for(k) for k in ("left", "right", "up", "down")}
_TAB = vk_for("tab")
# Pointer actions that put the edit in another cell (a button press lands somewhere new on the sheet).
_MOVES_CELL = {"click", "double_click", "drag"}
# Combinations Windows itself acts on: they switch, close or cover the app, or open the security screen.
# Only keys input.py knows can be sent at all, so Print Screen, media and browser keys never are.
# Keys that act inside the app stay allowed (alt+enter is a new line in an Excel cell, shift+f10 its menu).
_LEAVING = [{vk_for(k) for k in keys} for keys in
            (["win"], ["alt", "tab"], ["alt", "esc"], ["ctrl", "esc"], ["alt", "f4"], ["ctrl", "f4"], ["ctrl", "w"],
             ["alt", "space"], ["ctrl", "alt", "delete"])]
# An app's own keys a lesson never needs, each with the note the agent is told: those that open its macros,
# where code runs, those that add a link to a web page or a file, and the one that opens a new workbook in a
# window of its own, which would look like a person switching away and stop the whole test.
APP_REFUSED = {"excel": [({vk_for(k) for k in keys}, note) for keys, note in
                         ((["alt", "f11"], MACROS_NOTE), (["alt", "f8"], MACROS_NOTE), (["ctrl", "k"], LINK_KEY_NOTE),
                          (["ctrl", "n"], NEW_WORKBOOK_NOTE))]}
# Apps whose lessons Meta's agent may play. Its keys and clicks land on this computer, so an app is added only
# once nothing the agent can reach in it would let it run commands of its own.
AGENT_APPS = {"excel", "fake"}
NOT_FOR_AGENT = {"vscode": "its terminal would let the agent run any command on this computer, with your Meta key "
                           "in reach"}


class NotForAgent(Exception):
    """Meta's agent may not play this app's lessons; the message says why in plain words."""


def agent_refusal(plugin: AppPlugin) -> str | None:
    """Why Meta's agent may not test this app's lessons, or None when it may."""
    if plugin.app_id in AGENT_APPS:
        return None
    why = NOT_FOR_AGENT.get(plugin.app_id, "nobody has checked yet what the agent could reach there")
    return f"Meta's agent does not test {plugin.title} lessons: {why}."


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


def holds(frame: Rect, app: Rect) -> bool:
    """True when the window's frame still fills the app's place, give or take a pixel or two."""
    return (frame.x <= app.x + PLACE_PX and frame.y <= app.y + PLACE_PX
            and frame.x + frame.w >= app.x + app.w - PLACE_PX and frame.y + frame.h >= app.y + app.h - PLACE_PX)


def well_formed(action: Any) -> str:
    """Nothing when the action has every part it needs, each of the right kind; else the note the agent is told."""
    if not isinstance(action, dict) or not isinstance(action.get("type"), str):
        return SHAPE_NOTE
    kind = action["type"]
    if kind in POINTER_ACTIONS - {"drag"} and not _point(action):
        return POINT_NOTE
    if kind == "drag":
        path = action.get("path")
        if not isinstance(path, list) or not path or not all(_point(p) for p in path):
            return PATH_NOTE
    if kind == "scroll" and not all(_number(action.get(k, 0)) for k in ("scroll_x", "scroll_y")):
        return SCROLL_NOTE
    if kind == "keypress" and not (isinstance(action.get("keys"), list) and action["keys"]):
        return KEYS_NOTE
    if kind == "type" and not isinstance(action.get("text"), str):
        return TEXT_NOTE
    return ""


def _point(p: Any) -> bool:
    return isinstance(p, dict) and _number(p.get("x")) and _number(p.get("y"))


def _number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def allowed(action: dict, app: Rect, mode: Mode, refused=(), plugin: AppPlugin | None = None,
            typed: str = "") -> tuple[bool, str]:
    """Whether to do this well-formed action (in screen pixels); when not, the note the agent is told.
    `refused` lists the app's own key combinations to refuse, each with its note (APP_REFUSED). `typed` is
    what the agent has already typed into the cell it is editing: text to type is held to the rules of
    `plugin`'s lessons together with `typed`, since the cell ends up holding the whole of it, so a link or
    a forbidden formula split over several actions is caught as one."""
    kind = action.get("type")
    ok, note = _keys_allowed(action.get("keys") or [])       # any action may carry keys; all are checked
    if not ok:
        return ok, note
    codes = {vk_for(str(k)) for k in action.get("keys") or []}
    for combo, note in refused:
        if combo <= codes:
            return False, note
    if kind == "keypress" and _TAB in codes and typed.lstrip().startswith(FORMULA_START):
        return False, TAB_NOTE
    if kind in POINTER_ACTIONS:
        if mode == "keyboard":
            return False, KEYBOARD_NOTE
        if action.get("button", "left") not in _BUTTONS:
            return False, BUTTON_NOTE
        points = action.get("path") if kind == "drag" else [action]
        if not points or not all(_inside(p, app) for p in points):
            return False, OUTSIDE_NOTE
        return True, ""
    if kind == "type" and plugin is not None:
        if _tab_autocompletes(typed, action["text"]):
            return False, TAB_NOTE
        what = _reaches(typed + action["text"], plugin)
        if what:
            return False, f"That text {what}."
    if kind in ("keypress", "type", "wait", "screenshot"):
        return True, ""
    return False, f"{kind} is not something this test can do."


def _tab_autocompletes(typed: str, text: str) -> bool:
    """True when `text`, typed on top of `typed`, sends a Tab while a formula is open — the moment Excel's
    AutoComplete could finish a function name the agent never spelled out in full."""
    pending = typed
    for ch in text:
        if ch in "\r\n":
            pending = ""
        elif ch == "\t":
            if pending.lstrip().startswith(FORMULA_START):
                return True
            pending = ""                                 # Tab in a plain cell just moves to the next one
        else:
            pending += ch
    return False


def _pending(typed: str, text: str) -> str:
    """What is left pending in the current cell after `text` is typed on top of `typed`: everything after
    the last Enter, Tab or new line, since each of those moves the edit to another cell."""
    return NEXT_CELL.split(typed + text)[-1]


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
                on_line: Callable[[str], None] | None = None,
                on_progress: Callable[[str], None] | None = None) -> TestResult:
    """Run the lesson `runs` times with Meta's agent as the learner. Raises NotForAgent before anything opens
    when the agent may not play this app, UserTookOver when a person moves the mouse, ProveError when the app
    itself gets in the way, and NoKey or SpendLimitReached from Meta. `on_line` hears everything, Meta's and
    the checks' own words too, for the log; `on_progress` hears only which run is playing, in plain words."""
    refusal = agent_refusal(plugin)
    if refusal:
        raise NotForAgent(refusal)
    hands = hands or WindowsHands()
    say = on_line or (lambda line: None)
    progress = on_progress or (lambda line: None)
    need = -(-runs * PASS_OF[0] // PASS_OF[1])
    passes = done = 0
    for number in range(1, runs + 1):
        progress(f"run {number} of {runs} is playing" + (f", {passes} passed so far" if number > 1 else ""))
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
        self.looked = False                          # once the agent has seen the app, it is never taken back
        self.refused = APP_REFUSED.get(plugin.app_id, ())
        self.typed = ""                              # what the agent has typed into the cell it is editing

    def go(self) -> str | None:
        """None when the run reached the end of the lesson, else why it failed."""
        title = self.plugin.title
        try:
            session = self.plugin.open(self.lesson, self.workdir, visible=True, resume=False,
                                       on_snapshot=lambda snap: None, on_closed=self.closed.set)
        except Exception as exc:
            raise app_trouble(title, "could not be opened", exc) from exc
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
                note = well_formed(action)
                if not note:
                    action = to_screen(action, self.app, self.shot)
                    ok, note = allowed(action, self.app, self.mode, self.refused, self.plugin, self.typed)
                if not note:
                    self._ready()
                    if not self._over_app(action):
                        note = OUTSIDE_NOTE
                if note:
                    self.say(f"refused {_said_action(action)}: {note}")
                    notes.append(note)
                    return used                          # the rest of the batch waits for a new look
                self.hands.do(action)
                self._track(action)
        return used

    def _track(self, action: dict) -> None:
        """Keep `self.typed`, what the agent has typed into the cell it is editing, so a link or a forbidden
        formula split over several actions is caught as a whole. It starts over when the edit ends or moves:
        Enter, Escape or Tab, an arrow key when no formula is being typed, or a click on another cell."""
        kind = action["type"]
        if kind == "type":
            self.typed = _pending(self.typed, action["text"])
        elif kind == "keypress":
            codes = {vk_for(str(k)) for k in action.get("keys") or []}
            if codes & _ENDS_EDIT or (codes & _ARROWS and not self.typed.lstrip().startswith(FORMULA_START)):
                self.typed = ""
        elif kind in _MOVES_CELL:
            self.typed = ""

    def _over_app(self, action: dict) -> bool:
        """True when every point of a pointer action is over the app's own windows, not one showing through."""
        if action["type"] not in POINTER_ACTIONS:
            return True
        hwnd = self.session.hwnd()
        points = action["path"] if action["type"] == "drag" else [action]
        return all(self.hands.app_at(hwnd, p["x"], p["y"]) for p in points)

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
        """Before looking or acting: the app is still open, its window is in front and still where it was
        put, and no other program's window is over it, so a screenshot shows the app alone and a click
        lands in it. The app is brought to the front only before the run's first look: after that, another
        window in front means a person switched to it, and their typing must not land in the app."""
        title = self.plugin.title
        if self.closed.is_set():
            raise _RunFailed(f"{title} was closed")
        hwnd = self.session.hwnd()
        if not self.hands.in_front(hwnd):
            if self.looked:
                raise UserTookOver("Another window came to the front, so the test stopped.")
            self.hands.to_front(hwnd)
            if not self.hands.in_front(hwnd):
                raise _RunFailed(f"{title}'s window would not come to the front, so nothing more was done")
        if not holds(self.hands.bounds(hwnd), self.app):
            raise _RunFailed(f"{title}'s window moved or changed size, so nothing more was done")
        waits = COVER_TRIES
        while self.hands.covered(hwnd, self.app):
            if waits == 0:
                raise _RunFailed(f"another program's window stayed over {title}, so nothing more was done")
            waits -= 1
            time.sleep(COVER_WAIT_S)

    def _look(self) -> str:
        self.looked = True
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
            raise app_trouble(title, failed, exc) from exc


def _message(text: str, image: str | None = None) -> dict:
    content: list[dict] = [{"type": "input_text", "text": text}]
    if image:
        content.append({"type": "input_image", "image_url": image})
    return {"role": "user", "content": content}


def _said(exc: BaseException) -> str:
    return str(exc) or type(exc).__name__


def _said_action(action: Any) -> str:
    if not isinstance(action, dict):
        return "an action that could not be read"
    kind = action.get("type")
    path = action.get("path")
    if kind == "drag" and isinstance(path, list) and path and all(isinstance(p, dict) for p in path):
        a, b = path[0], path[-1]
        return f"drag from {a.get('x')}, {a.get('y')} to {b.get('x')}, {b.get('y')}"
    if "x" in action and "y" in action:
        return f"{kind} at {action['x']}, {action['y']}"
    if kind == "keypress" and isinstance(action.get("keys"), list) and action["keys"]:
        return "keypress " + "+".join(str(k) for k in action["keys"])
    return str(kind)
