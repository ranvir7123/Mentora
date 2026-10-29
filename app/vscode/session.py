"""One lesson's VS Code: the lesson's folder, a VS Code window on it, and the link to its add-on.

Opening writes the starter files into the work folder, starts the link (bridge.py), writes the link
file the add-on looks for, and starts VS Code. The rest happens on a start thread, so `open` returns
at once: wait for the add-on's hello, give it the terminal settings (the Meta key when the lesson needs
it, and this program's Python first on PATH), and find the window. If any of that fails,
`close_reason` says why in plain words and on_closed() fires once.

The add-on also goes away when the window reloads (trusting the folder, an update), not only when the
learner closes VS Code. So a lost link starts a new one at once and rewrites the link file; the add-on
finds it within seconds. Only when the window is gone, or nothing comes back within RECONNECT_S, does
the session count as closed.

Every snapshot comes from the add-on's `state` messages. `read_now` asks for a fresh one; an operation
waits for the add-on's `done`, and `run_file` also waits for the run to finish.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from app.core.lesson import Lesson
from app.core.types import Call, Rect, Spot, Target
from app.meta.key import require_key
from app.vscode.bridge import Bridge
from app.vscode.snapshot import Active, VsSnapshot, clean_path

HELLO_TIMEOUT_S = 30.0       # VS Code's start, from asking to the add-on's hello
WINDOW_WAIT_S = 5.0          # after hello, for the window's title to name the folder
RECONNECT_S = 20.0           # a reloading window's add-on is back well within this
OP_TIMEOUT_S = 15.0
RUN_TIMEOUT_S = 20.0         # a learner's program still running after this is stopped
READ_TIMEOUT_S = 5.0
QUIET_S = 0.25               # a fresh read waits until no state has come for this long
IDLE_REREAD_S = 1.0          # while a step waits
WATCH_EVERY_S = 0.1
CLOSE_WAIT_S = 3.0           # for VS Code to close its window when the program closes the lesson

DIDNT_START = "VS Code didn't start"
CLOSED = "VS Code was closed"
LOST_TOUCH = "lost touch with VS Code"
STOPPED = "this lesson's VS Code was closed"

TARGET_KINDS = frozenset({"editor_line", "explorer_item", "run_button", "terminal"})
MARKER = Path(".vscode") / "projectx.json"     # says the folder is the program's own work copy
SETTINGS = {
    "editor.stickyScroll.enabled": False,      # it covers the top lines, so a line would be elsewhere
    "editor.wordWrap": "off",                  # one screen line per line of code
    "editor.minimap.enabled": False,
    "window.title": "${dirty}${activeEditorShort}${separator}${rootName}${separator}${appName}",
    "files.exclude": {"**/.vscode": True, "**/__pycache__": True},
    "python.defaultInterpreterPath": sys.executable,   # the Run button's Python, the one that has openai
    "terminal.integrated.defaultProfile.windows": "PowerShell",  # runs are seen only in a shell VS Code reports on
    # The add-on's terminal settings reach only terminals made after it starts: none from last time.
    "terminal.integrated.enablePersistentSessions": False,
    "terminal.integrated.hideOnStartup": "always",
    "code-runner.showRunIconInEditorTitleMenu": False,  # its Run Code runs where input() can't be answered
}

_ENDED = ("closed", "stopped")
_UNSET = object()


def default_link_file() -> Path:
    """Where the add-on looks for the port and token (extensions/vscode/src/extension.ts, linkFile)."""
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "projectx" / "vscode.json"


def parse_line_ref(ref: str) -> tuple[str, int] | None:
    """"hello.py:3" -> ("hello.py", 3)."""
    path, sep, line = ref.rpartition(":")
    if not sep or not path or not line.isdigit() or int(line) < 1:
        return None
    return path, int(line)


def editor_line_spot(area: Rect, active: Active, line: int, scale: float) -> Spot:
    """Where `line` of the open file is, from the editor's text area (physical px), the lines on
    screen and the line height. A line off screen points at the edge it is past, saying which way to
    scroll. A line scrolled partly out of view at the top can put the rest up to one line out."""
    height = active.line_height * scale
    top = area.y + (line - active.visible_from) * height
    if line < active.visible_from:
        return Spot(Rect(area.x, area.y, area.w, height), f"Scroll up to line {line}")
    if line > active.visible_to or top >= area.y + area.h:
        return Spot(Rect(area.x, area.y + area.h - height, area.w, height), f"Scroll down to line {line}")
    return Spot(Rect(area.x, top, area.w, min(height, area.y + area.h - top)))


def _moved(last: Any, spot: Spot | None) -> bool:
    if last is _UNSET or (last is None) != (spot is None):
        return True
    if spot is None:
        return False
    if last.bubble != spot.bubble:
        return True
    a, b = last.rect, spot.rect
    return any(abs(p - q) >= 1 for p, q in ((a.x, b.x), (a.y, b.y), (a.w, b.w), (a.h, b.h)))


def _failed(error: BaseException) -> Future:
    future: Future = Future()
    future.set_exception(error)
    return future


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    part.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(part, path)


def _prepare_folder(folder: Path, files: dict[str, str], resume: bool, lesson_id: str) -> None:
    """Put the starter in the work folder. Without `resume`, everything else in it goes first, but
    only in a folder the program made: anything else is left alone."""
    folder.mkdir(parents=True, exist_ok=True)
    if not resume:
        leftovers = [p for p in folder.iterdir() if p.name != ".vscode"]
        if leftovers and not (folder / MARKER).is_file():
            raise ValueError(f"The work folder {folder} holds files Project X didn't make, so it was left alone.")
        for p in leftovers:
            if p.is_dir() and not p.is_symlink():
                shutil.rmtree(p)
            else:
                p.unlink()
    for rel, text in files.items():
        dest = folder / rel
        if resume and dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8", newline="")
    _write_json(folder / ".vscode" / "settings.json", SETTINGS)
    _write_json(folder / MARKER, {"lesson": lesson_id})


class VsCodeSession:
    def __init__(self, lesson: Lesson, workdir: Path, *, visible: bool = True, resume: bool = False,
                 on_snapshot: Callable[[Any], None], on_closed: Callable[[], None],
                 host: Any = None, link_file: Path | None = None,
                 key_reader: Callable[[str], str] = require_key) -> None:
        self.folder = Path(workdir).resolve()
        self._files: dict[str, str] = dict(lesson.starter.get("files", {}))
        self._open: str | None = lesson.starter.get("open")
        self._env_names: list[str] = list(lesson.starter.get("env", []))
        self._visible = visible
        self._on_snapshot = on_snapshot
        self._on_closed = on_closed
        if host is None:
            from app.vscode.host import WindowsHost
            host = WindowsHost()
        self._host = host
        self._link_file = link_file or default_link_file()
        self._key_reader = key_reader
        self.close_reason = ""                   # why the session closed on its own, in plain words
        self.errors: list[str] = []              # what went wrong without closing it, for the logs

        self._cond = threading.Condition()       # guards _phase, _latest, _count, _window, _bridge
        self._phase = "starting"                 # starting, ready, reconnecting, closed, stopped
        self._latest: VsSnapshot | None = None
        self._count = 0                          # states received so far
        self._window = 0
        self._greeted = False
        self._watch_lock = threading.RLock()     # guards the watch; held while on_spot runs
        self._watch: tuple[Target, Callable[[Spot | None], None]] | None = None
        self._last_spot: Any = _UNSET
        self._waiting = False
        self._wake = threading.Event()

        _prepare_folder(self.folder, self._files, resume, lesson.id)
        self._bridge = self._new_bridge()
        self._work = ThreadPoolExecutor(4, thread_name_prefix="vscode-work")
        self._screen = ThreadPoolExecutor(1, thread_name_prefix="vscode-screen", initializer=self._screen_setup)
        threading.Thread(target=self._start, name="vscode-start", daemon=True).start()
        threading.Thread(target=self._tick, name="vscode-watch", daemon=True).start()

    # ------------------------------------------------------------ from any thread

    def hwnd(self) -> int:
        return self._window if self._visible and self._host.is_window(self._window) else 0

    def latest(self) -> VsSnapshot | None:
        return self._latest

    def read_now(self) -> Future:
        return self._submit(self._work, self._read_now)

    def perform(self, op: Call) -> Future:
        return self._submit(self._work, self._perform, op)

    def reset(self) -> Future:
        return self._submit(self._work, self._reset)

    def locate(self, target: Target) -> Future:
        return self._submit(self._screen, self._locate, target)

    def place(self, rect: Rect) -> Future:
        return self._submit(self._screen, self._place, rect)

    def watch(self, target: Target | None, on_spot: Callable[[Spot | None], None]) -> None:
        with self._watch_lock:
            self._watch = None if target is None else (target, on_spot)
            self._last_spot = _UNSET
        self._wake.set()

    def set_waiting(self, waiting: bool) -> None:
        self._waiting = waiting
        self._wake.set()

    def close(self, save: bool = False) -> None:
        """Ask VS Code to save the lesson's files and close its window. The add-on always saves, so
        VS Code never stops to ask; on_closed is not called."""
        with self._cond:
            if self._phase == "stopped":
                return
            self._phase = "stopped"
            self._cond.notify_all()
            bridge = self._bridge
        self._wake.set()
        with self._watch_lock:
            self._watch = None
        self._work.shutdown(wait=False, cancel_futures=True)
        self._screen.shutdown(wait=False, cancel_futures=True)
        threading.Thread(target=self._shut, args=(bridge,), name="vscode-close", daemon=True).start()

    # ------------------------------------------------------------ starting and losing touch

    def _new_bridge(self) -> Bridge:
        made: list[Bridge] = []
        bridge = Bridge(self._on_state, lambda: self._link_lost(made[0]))
        made.append(bridge)
        bridge.start()
        _write_json(self._link_file, {"port": bridge.port, "token": bridge.token, "folder": str(self.folder)})
        return bridge

    def _start(self) -> None:
        open_file = self.folder / self._open if self._open else None
        try:
            self._host.launch(self.folder, open_file, {"PROJECTX_VSCODE": str(self._link_file)})
        except Exception as exc:                 # LaunchError says why in plain words
            self._fail(str(exc) or DIDNT_START)
            return
        bridge = self._bridge
        deadline = time.monotonic() + HELLO_TIMEOUT_S
        while not bridge.wait_connected(0.05):
            if self._ended(bridge):
                return
            if bridge.refused:
                self._fail(bridge.refused)
                return
            if time.monotonic() > deadline:
                self._fail(DIDNT_START)
                return
        self._greet(bridge)

    def _greet(self, bridge: Bridge) -> None:
        """The add-on is here: give it the terminal settings, find the window, and get going."""
        values = {}
        for name in self._env_names:
            try:
                values[name] = self._key_reader(name)
            except Exception as exc:             # the lesson still opens; its run steps will say why
                self._note(str(exc))
        bridge.send_env(values, [os.path.dirname(sys.executable)])
        hwnd = self._window if self._host.is_window(self._window) else self._find_window(bridge)
        with self._cond:
            if self._ended(bridge):
                return
            first = not self._greeted
            self._window, self._greeted, self._phase = hwnd, True, "ready"
            self._cond.notify_all()
        if not hwnd:
            self._note("VS Code's window was not found, so nothing in it can be pointed at")
        elif first and not self._visible:
            self._host.minimize(hwnd)

    def _find_window(self, bridge: Bridge) -> int:
        deadline = time.monotonic() + WINDOW_WAIT_S
        while not self._ended(bridge):
            hwnd = self._host.find_window(self.folder)
            if hwnd or time.monotonic() > deadline:
                return hwnd
            time.sleep(0.1)
        return 0

    def _link_lost(self, bridge: Bridge) -> None:
        """On the link's thread: start looking for the add-on again elsewhere, and return at once."""
        with self._cond:
            if self._ended(bridge):
                return
            self._phase = "reconnecting"
        threading.Thread(target=self._reconnect, args=(bridge,), name="vscode-reconnect", daemon=True).start()

    def _reconnect(self, old: Bridge) -> None:
        old.stop()
        try:
            new = self._new_bridge()
        except OSError as exc:
            self._note(f"the new link could not start: {exc}")
            self._fail(LOST_TOUCH)
            return
        with self._cond:
            if self._phase in _ENDED:
                new.stop()
                return
            self._bridge = new
        deadline = time.monotonic() + RECONNECT_S
        while not new.wait_connected(0.1):
            if self._ended(new):
                return
            if new.refused:
                self._fail(new.refused)
                return
            if not self._host.is_window(self._window) and not self._host.find_window(self.folder):
                self._fail(CLOSED)
                return
            if time.monotonic() > deadline:
                self._fail(LOST_TOUCH)
                return
        self._greet(new)

    def _ended(self, bridge: Bridge) -> bool:
        return self._phase in _ENDED or bridge is not self._bridge

    def _fail(self, reason: str) -> None:
        with self._cond:
            if self._phase in _ENDED:
                return
            self._phase, self.close_reason = "closed", reason
            self._cond.notify_all()
            bridge = self._bridge
        self._wake.set()
        bridge.stop()
        self._forget_link_file(bridge)
        try:
            self._on_closed()
        except Exception as exc:
            self._note(f"on_closed: {exc!r}")

    def _shut(self, bridge: Bridge) -> None:
        if bridge.connected and bridge.close_window():
            deadline = time.monotonic() + CLOSE_WAIT_S
            while bridge.connected and time.monotonic() < deadline:
                time.sleep(0.05)
        bridge.stop()
        self._forget_link_file(bridge)

    def _forget_link_file(self, bridge: Bridge) -> None:
        """Remove the link file, unless a newer lesson has written its own since."""
        try:
            if json.loads(self._link_file.read_text(encoding="utf-8")).get("token") == bridge.token:
                self._link_file.unlink()
        except (OSError, ValueError, AttributeError):
            pass

    def _note(self, text: str) -> None:
        if len(self.errors) < 50:
            self.errors.append(text)

    # ------------------------------------------------------------ snapshots, operations and reads

    def _on_state(self, state: dict) -> None:
        snap = VsSnapshot.from_state(state)
        with self._cond:
            self._latest = snap
            self._count += 1
            self._cond.notify_all()
        self._on_snapshot(snap)

    def _submit(self, pool: ThreadPoolExecutor, fn: Callable, *args: Any) -> Future:
        try:
            return pool.submit(fn, *args)
        except RuntimeError:                     # the pool was shut down by close()
            return _failed(RuntimeError(STOPPED))

    def _raise_if_ended(self) -> None:
        if self._phase == "closed":
            raise RuntimeError(self.close_reason)
        if self._phase == "stopped":
            raise RuntimeError(STOPPED)

    def _ready(self) -> Bridge:
        """The link, once the add-on is there; raises if the session ended or never got going."""
        with self._cond:
            ok = self._cond.wait_for(lambda: self._phase in ("ready", *_ENDED),
                                     HELLO_TIMEOUT_S + WINDOW_WAIT_S + RECONNECT_S)
            self._raise_if_ended()
            if not ok:
                raise RuntimeError(LOST_TOUCH if self._greeted else DIDNT_START)
            return self._bridge

    def _do(self, op: Call) -> None:
        future = self._ready().send_op(op)
        try:
            future.result(OP_TIMEOUT_S)
        except TimeoutError:
            raise RuntimeError(f"VS Code did not finish {op.kind} within {OP_TIMEOUT_S:g} s") from None

    def _perform(self, op: Call) -> None:
        if op.kind != "run_file":
            self._do(op)
            return
        # Forget the last run first, so the run that finishes next can only be this one.
        self._do(Call("clear_terminal", {}))
        with self._cond:
            mark = self._count
        self._do(op)
        with self._cond:
            finished = self._cond.wait_for(
                lambda: self._phase in _ENDED or (self._count > mark and self._latest is not None
                                                  and self._latest.run is not None and self._latest.run.finished),
                RUN_TIMEOUT_S)
            self._raise_if_ended()
        if not finished:
            try:
                self._do(Call("clear_terminal", {}))
            except Exception as exc:
                self._note(f"could not stop the run: {exc}")
            raise RuntimeError(f"{op.args.get('path')} was still running after {RUN_TIMEOUT_S:g} s, so it was "
                               f"stopped. A program that waits for typing needs the run's input.")

    def _read_now(self) -> VsSnapshot:
        self._ready()                            # VS Code may still be starting: the read's time starts after
        deadline = time.monotonic() + READ_TIMEOUT_S
        while True:
            bridge = self._ready()
            with self._cond:
                mark = self._count
            if bridge.ping():
                break
            if time.monotonic() > deadline:
                raise RuntimeError(f"VS Code did not answer within {READ_TIMEOUT_S:g} s")
            time.sleep(0.05)
        with self._cond:
            if not self._cond.wait_for(lambda: self._count > mark or self._phase in _ENDED,
                                       max(0.0, deadline - time.monotonic())):
                raise RuntimeError(f"VS Code did not answer within {READ_TIMEOUT_S:g} s")
            # A state built before the ping can arrive first; the add-on sends the next one within
            # 100 ms, so take the last one once they stop coming.
            while True:
                self._raise_if_ended()
                seen = self._count
                self._cond.wait_for(lambda: self._count > seen or self._phase in _ENDED, QUIET_S)
                if self._count == seen or time.monotonic() > deadline:
                    self._raise_if_ended()
                    return self._latest

    def _reset(self) -> None:
        snap = self._read_now()
        for path, text in self._files.items():
            self._do(Call("write_file", {"path": path, "text": text}))
        keep = {clean_path(p).lower() for p in self._files}
        for name in snap.files:
            if clean_path(name).lower() not in keep:
                self._do(Call("delete_file", {"path": name}))
        self._do(Call("clear_terminal", {}))
        if self._open:
            self._do(Call("open_file", {"path": self._open}))

    # ------------------------------------------------------------ the screen thread

    def _screen_setup(self) -> None:
        try:
            self._host.screen_setup()
        except Exception as exc:                 # nothing can be pointed at, but the lesson goes on
            self._note(f"UI Automation could not start: {exc!r}")

    def _locate(self, target: Target) -> Spot | None:
        hwnd = self._window
        if not hwnd or not self._host.is_window(hwnd):
            return None
        if target.kind == "editor_line":
            return self._locate_line(hwnd, target.ref)
        if target.kind in TARGET_KINDS:
            rect = self._host.find(hwnd, target.kind, target.ref)
            return None if rect is None else Spot(rect)
        return None

    def _locate_line(self, hwnd: int, ref: str) -> Spot | None:
        parsed = parse_line_ref(ref)
        if parsed is None:
            return None
        path, line = parsed
        active = self._latest.active if self._latest is not None else None
        if active is None or clean_path(active.path).lower() != clean_path(path).lower():
            rect = self._host.find(hwnd, "explorer_item", path)
            name = clean_path(path).rsplit("/", 1)[-1]
            return None if rect is None else Spot(rect, f"Open {name} first")
        area = self._host.find(hwnd, "editor", path)
        if area is None:
            return None
        return editor_line_spot(area, active, line, self._host.scale(hwnd))

    def _place(self, rect: Rect) -> None:
        self._ready()
        if not self._visible or not self._host.is_window(self._window):
            raise RuntimeError("this lesson's VS Code has no window to move")
        self._host.place(self._window, rect)

    # ------------------------------------------------------------ the watch thread

    def _tick(self) -> None:
        next_ping = 0.0
        while True:
            self._wake.wait(WATCH_EVERY_S)
            self._wake.clear()
            if self._phase in _ENDED:
                return
            with self._watch_lock:
                watch = self._watch
            if watch is not None:
                try:
                    spot = self._screen.submit(self._locate, watch[0]).result(timeout=5)
                except Exception:                # shut down, or UI Automation failed this once
                    spot = None
                with self._watch_lock:
                    if self._watch is watch and _moved(self._last_spot, spot):
                        self._last_spot = spot
                        try:
                            watch[1](spot)
                        except Exception as exc:
                            self._note(f"on_spot: {exc!r}")
            if self._waiting and self._phase == "ready" and time.monotonic() >= next_ping:
                self._bridge.ping()
                next_ping = time.monotonic() + IDLE_REREAD_S
