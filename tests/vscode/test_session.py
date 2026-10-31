"""The VS Code session, tested against a pretend VS Code that speaks the add-on's JSON lines over a
real socket: it reads the link file, says hello, keeps the lesson's files on disk and answers each
operation. The pretend computer (`FakeHost`) stands in for starting VS Code, its window and UI
Automation."""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

from app.core.lesson import Goal, Lesson
from app.core.types import Call, Rect, Spot, Target
from app.vscode import session as session_module
from app.vscode.bridge import OUT_OF_DATE
from app.vscode.launch import LaunchError
from app.vscode.plugin import VsCodePlugin
from app.vscode.protocol import PROTOCOL_VERSION
from app.vscode.session import VsCodeSession, editor_line_spot
from app.vscode.snapshot import Active, VsSnapshot

WINDOW = 4242


def wait_for(condition, timeout: float = 5.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.01)
    return condition()


class FakeVsCode:
    """VS Code with the Mentora add-on, as the program sees it on the wire."""

    def __init__(self, folder: Path, link_file: Path, *, version: int = PROTOCOL_VERSION,
                 hang: bool = False, output: str = "Hello\n"):
        self.folder = folder
        self.link_file = link_file
        self.version = version
        self.hang = hang
        self.output = output
        self.ops: list[dict] = []
        self.envs: list[dict] = []
        self.pings = 0
        self.asked_to_close = False
        self.active: dict | None = None
        self.run: dict | None = None
        self.tokens: list[str] = []
        self._sock: socket.socket | None = None
        self._send_lock = threading.Lock()

    def connect(self) -> None:
        info = json.loads(self.link_file.read_text(encoding="utf-8"))
        assert Path(info["folder"]) == self.folder.resolve()
        self.tokens.append(info["token"])
        sock = socket.create_connection(("127.0.0.1", info["port"]), timeout=5)
        self._sock = sock
        self._send({"type": "hello", "token": info["token"], "version": self.version})
        if self.version != PROTOCOL_VERSION:
            return
        self._send(self.state())
        threading.Thread(target=self._loop, args=(sock,), daemon=True).start()

    def state(self) -> dict:
        files = {}
        for path in sorted(self.folder.rglob("*")):
            rel = path.relative_to(self.folder).as_posix()
            if path.is_file() and not rel.startswith(".vscode/"):
                files[rel] = {"text": path.read_text(encoding="utf-8"), "saved": True}
        return {"type": "state", "files": files, "active": self.active, "problems": [],
                "run": None if self.run is None else dict(self.run)}

    def quit(self) -> None:
        """The learner closes VS Code."""
        if self._sock is not None:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self._sock.close()

    def reload(self) -> None:
        """The window reloads: the add-on restarts and connects again with the new link file."""
        self.quit()
        old = self.tokens[-1]
        assert wait_for(lambda: json.loads(self.link_file.read_text(encoding="utf-8"))["token"] != old)
        self.connect()

    def _send(self, message: dict) -> None:
        with self._send_lock:
            self._sock.sendall((json.dumps(message) + "\n").encode("utf-8"))

    def _loop(self, sock: socket.socket) -> None:
        reader = sock.makefile("r", encoding="utf-8")
        try:
            for line in reader:
                message = json.loads(line)
                if message["type"] == "do":
                    self.ops.append(message["op"])
                    error = self._perform(message["op"])
                    self._send(self.state())
                    self._send({"type": "done", "id": message["id"], "ok": error is None, "error": error})
                elif message["type"] == "ping":
                    self.pings += 1
                    self._send(self.state())
                elif message["type"] == "env":
                    self.envs.append(message)
                elif message["type"] == "close":
                    self.asked_to_close = True
                    sock.close()
                    return
        except (OSError, ValueError):
            pass

    def _perform(self, op: dict) -> str | None:
        kind, args = op["kind"], op["args"]
        path = self.folder / args.get("path", "")
        if kind == "write_file":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args["text"], encoding="utf-8")
        elif kind == "delete_file":
            path.unlink()
        elif kind == "open_file":
            if not path.exists():
                return f"{args['path']} is not there"
            self.active = {"path": args["path"], "line": 1, "column": 1, "visible_from": 1,
                           "visible_to": 30, "line_height": 19, "font_size": 14}
        elif kind == "clear_terminal":
            self.run = None
        elif kind == "run_file":
            if not path.exists():
                return f"{args['path']} is not there"
            self.run = {"command": f"python {args['path']}", "exit_code": None, "output": "", "finished": False}
            if not self.hang:
                threading.Thread(target=self._finish, args=(self.run,), daemon=True).start()
        else:
            return f"the add-on has no operation {kind}"
        return None

    def _finish(self, run: dict) -> None:
        time.sleep(0.05)
        run.update(exit_code=0, output=self.output, finished=True)
        if self.run is run:
            self._send(self.state())


class FakeHost:
    """The computer: starting VS Code, its window, and UI Automation's answers."""

    def __init__(self, link_file: Path, *, starts: bool = True, launch_error: str = "", hello_after: float = 0.0,
                 **vscode_options):
        self.link_file = link_file
        self.starts = starts
        self.launch_error = launch_error
        self.hello_after = hello_after           # seconds VS Code takes to start before its add-on says hello
        self.vscode_options = vscode_options
        self.vscode: FakeVsCode | None = None
        self.launched: list[tuple[Path, Path | None, dict]] = []
        self.alive = False
        self.placed: list[tuple[int, Rect]] = []
        self.minimized: list[int] = []
        self.rects: dict[tuple[str, str], Rect] = {}
        self.asked: list[tuple[int, str, str]] = []
        self.scale_factor = 2.0

    def launch(self, folder: Path, open_file: Path | None, env: dict) -> None:
        self.launched.append((folder, open_file, dict(env)))
        if self.launch_error:
            raise LaunchError(self.launch_error)
        if self.starts:
            self.alive = True
            self.vscode = FakeVsCode(folder, self.link_file, **self.vscode_options)
            vscode = self.vscode

            def start() -> None:
                time.sleep(self.hello_after)
                vscode.connect()
            threading.Thread(target=start, daemon=True).start()

    def find_window(self, folder: Path) -> int:
        return WINDOW if self.alive else 0

    def is_window(self, hwnd: int) -> bool:
        return self.alive and hwnd == WINDOW

    def scale(self, hwnd: int) -> float:
        return self.scale_factor

    def place(self, hwnd: int, rect: Rect) -> None:
        self.placed.append((hwnd, rect))

    def minimize(self, hwnd: int) -> None:
        self.minimized.append(hwnd)

    def find(self, hwnd: int, kind: str, ref: str) -> Rect | None:
        self.asked.append((hwnd, kind, ref))
        return self.rects.get((kind, ref))

    def screen_setup(self) -> None:
        pass


def lesson(starter: dict) -> Lesson:
    return Lesson(format=1, id="scratch", title="Scratch", app="vscode", course="", source=None,
                  goal=Goal("Say hello", None), starter=starter, steps=(), made_by="hand",
                  edited_by_hand=False, proof=None, test=None)


STARTER = {"files": {"hello.py": "print('hi')\n", "notes/readme.txt": "Read me\n"}, "open": "hello.py"}


@pytest.fixture(autouse=True)
def quick_reads(monkeypatch):
    monkeypatch.setattr(session_module, "QUIET_S", 0.05)


@pytest.fixture
def opened(tmp_path):
    """Open a lesson; yields (session, host, snapshots, closed, workdir). Closes it afterwards."""
    made = []

    def open_lesson(starter=STARTER, *, resume=False, visible=True, key="made-up-key", **host_options):
        workdir = tmp_path / "work"
        host = FakeHost(tmp_path / "vscode.json", **host_options)
        snapshots: list[VsSnapshot] = []
        closed: list[int] = []

        def key_reader(name: str) -> str:
            if key is None:
                raise RuntimeError(f"{name} is not set")
            return key
        session = VsCodeSession(lesson(starter), workdir, visible=visible, resume=resume,
                                on_snapshot=snapshots.append, on_closed=lambda: closed.append(1),
                                host=host, link_file=tmp_path / "vscode.json", key_reader=key_reader)
        made.append(session)
        return session, host, snapshots, closed, workdir

    yield open_lesson
    for session in made:
        session.close()


# Opening.

def test_open_writes_the_starter_and_waits_for_hello(opened):
    session, host, snapshots, closed, workdir = opened()
    assert (workdir / "hello.py").read_text(encoding="utf-8") == "print('hi')\n"
    assert (workdir / "notes" / "readme.txt").read_text(encoding="utf-8") == "Read me\n"
    snap = session.read_now().result(timeout=5)
    assert set(snap.files) == {"hello.py", "notes/readme.txt"}
    assert snapshots and snapshots[-1] == snap and session.latest() == snap
    folder, open_file, env = host.launched[0]
    assert folder == workdir and open_file == workdir / "hello.py"
    assert env == {"MENTORA_VSCODE": str(host.link_file)}
    assert session.hwnd() == WINDOW and not closed and session.close_reason == ""


def test_the_lesson_folder_gets_its_editor_settings(opened):
    session, host, _, _, workdir = opened()
    settings = json.loads((workdir / ".vscode" / "settings.json").read_text(encoding="utf-8"))
    assert settings["editor.stickyScroll.enabled"] is False
    assert settings["editor.wordWrap"] == "off"
    # The Python add-on's Run button runs the Python it picked, not the first one on PATH; this one has openai.
    assert settings["python.defaultInterpreterPath"] == sys.executable
    # Runs are seen through VS Code's shell integration, which Command Prompt lacks; PowerShell has it.
    assert settings["terminal.integrated.defaultProfile.windows"] == "PowerShell"
    # The add-on's terminal settings reach only terminals made after it starts. In real VS Code the
    # terminal on show was one brought back from the last lesson ("environment is stale"), the 4th one.
    assert settings["terminal.integrated.enablePersistentSessions"] is False
    assert settings["terminal.integrated.hideOnStartup"] == "always"
    # With Code Runner installed, its "Run Code" took the Run button's place: it runs the program where
    # input() can't be answered and the run is never seen.
    assert settings["code-runner.showRunIconInEditorTitleMenu"] is False
    session.read_now().result(timeout=5)
    assert ".vscode/settings.json" not in session.latest().files


def test_open_without_resume_starts_over(opened):
    session, *_, workdir = opened()                         # a first open marks the folder as the program's
    session.read_now().result(timeout=5)
    session.close()
    (workdir / "hello.py").write_text("print('old work')\n", encoding="utf-8")
    (workdir / "helo.py").write_text("typo\n", encoding="utf-8")
    session, *_ = opened()
    snap = session.read_now().result(timeout=5)
    assert set(snap.files) == {"hello.py", "notes/readme.txt"}
    assert snap.files["hello.py"].text == "print('hi')\n"


def test_resume_keeps_the_learners_files(opened, tmp_path):
    workdir = tmp_path / "work"
    workdir.mkdir()
    (workdir / "hello.py").write_text("print('my own work')\n", encoding="utf-8")
    session, *_ = opened(resume=True)
    snap = session.read_now().result(timeout=5)
    assert snap.files["hello.py"].text == "print('my own work')\n"
    assert snap.files["notes/readme.txt"].text == "Read me\n"     # missing starter files come back


def test_a_folder_with_files_the_program_did_not_make_is_left_alone(opened, tmp_path):
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "thesis.docx").write_text("months of work", encoding="utf-8")
    (tmp_path / "work" / "hello.py").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="didn't make"):
        opened()
    assert (tmp_path / "work" / "thesis.docx").read_text(encoding="utf-8") == "months of work"


def test_no_hello_in_time_is_reported(opened, monkeypatch):
    monkeypatch.setattr(session_module, "HELLO_TIMEOUT_S", 0.3)
    session, host, _, closed, _ = opened(starts=False)
    assert wait_for(lambda: closed == [1])
    assert session.close_reason == "VS Code didn't start"
    with pytest.raises(RuntimeError, match="VS Code didn't start"):
        session.read_now().result(timeout=5)
    time.sleep(0.2)
    assert closed == [1]


def test_the_first_read_waits_for_a_slow_start(opened, monkeypatch):
    # In real VS Code the add-on said hello 10 to 13 s after launch; a read's own time limit starts
    # only once the add-on is there.
    monkeypatch.setattr(session_module, "READ_TIMEOUT_S", 0.5)
    session, *_ = opened(hello_after=1.0)
    snap = session.read_now().result(timeout=10)
    assert "hello.py" in snap.files


def test_vs_code_missing_is_reported(opened):
    session, _, _, closed, _ = opened(launch_error="VS Code isn't installed. Get it from code.visualstudio.com.")
    assert wait_for(lambda: closed == [1])
    assert session.close_reason == "VS Code isn't installed. Get it from code.visualstudio.com."


def test_an_out_of_date_add_on_is_reported(opened):
    session, _, _, closed, _ = opened(version=PROTOCOL_VERSION + 1)
    assert wait_for(lambda: closed == [1])
    assert session.close_reason == OUT_OF_DATE


def test_the_meta_key_reaches_the_terminal_only(opened):
    session, host, _, _, workdir = opened({"files": {"ask.py": ""}, "env": ["META_API_KEY"]}, key="made-up-key")
    session.read_now().result(timeout=5)
    assert wait_for(lambda: host.vscode.envs)
    env = host.vscode.envs[0]
    assert env["set"] == {"META_API_KEY": "made-up-key"}
    assert env["path_prepend"] == [os.path.dirname(sys.executable)]
    for path in [host.link_file, *workdir.rglob("*")]:
        if path.is_file():
            assert "made-up-key" not in path.read_text(encoding="utf-8")


def test_a_missing_key_is_noted_and_the_lesson_still_opens(opened):
    session, host, _, closed, _ = opened({"files": {"ask.py": ""}, "env": ["META_API_KEY"]}, key=None)
    session.read_now().result(timeout=5)
    assert wait_for(lambda: host.vscode.envs)
    assert host.vscode.envs[0]["set"] == {}
    assert any("META_API_KEY is not set" in e for e in session.errors)
    assert not closed


def test_opened_invisible_the_window_is_minimized_and_hwnd_is_0(opened):
    session, host, *_ = opened(visible=False)
    session.read_now().result(timeout=5)
    assert host.minimized == [WINDOW]
    assert session.hwnd() == 0


# Operations.

def test_perform_writes_through_the_add_on(opened):
    session, host, _, _, workdir = opened()
    session.perform(Call("write_file", {"path": "hello.py", "text": "print('Hello')\n"})).result(timeout=5)
    assert (workdir / "hello.py").read_text(encoding="utf-8") == "print('Hello')\n"
    assert session.read_now().result(timeout=5).files["hello.py"].text == "print('Hello')\n"


def test_a_refused_operation_fails_with_the_add_on_s_reason(opened):
    session, *_ = opened()
    with pytest.raises(RuntimeError, match="missing.py is not there"):
        session.perform(Call("open_file", {"path": "missing.py"})).result(timeout=5)


def test_run_file_clears_the_last_run_then_waits_for_the_new_one_to_finish(opened):
    session, host, *_ = opened()
    session.perform(Call("run_file", {"path": "hello.py"})).result(timeout=5)
    run = session.latest().run
    assert run.finished and run.exit_code == 0 and run.output == "Hello\n"
    assert [op["kind"] for op in host.vscode.ops] == ["clear_terminal", "run_file"]


def test_a_hanging_run_is_reported(opened, monkeypatch):
    monkeypatch.setattr(session_module, "RUN_TIMEOUT_S", 0.3)
    session, host, *_ = opened(hang=True)
    with pytest.raises(RuntimeError, match="hello.py was still running after 0.3 s"):
        session.perform(Call("run_file", {"path": "hello.py"})).result(timeout=5)
    assert host.vscode.ops[-1]["kind"] == "clear_terminal"     # the stuck program is stopped


def test_reset_puts_the_starter_back(opened):
    session, host, _, _, workdir = opened()
    session.perform(Call("write_file", {"path": "hello.py", "text": "changed\n"})).result(timeout=5)
    session.perform(Call("write_file", {"path": "extra/new.py", "text": "x = 1\n"})).result(timeout=5)
    session.perform(Call("run_file", {"path": "hello.py"})).result(timeout=5)
    session.reset().result(timeout=5)
    snap = session.read_now().result(timeout=5)
    assert {name: f.text for name, f in snap.files.items()} == STARTER["files"]
    assert snap.run is None
    assert snap.active.path == "hello.py"


# Closing and losing touch.

def test_the_learner_closing_vs_code_calls_on_closed_once(opened):
    session, host, _, closed, _ = opened()
    session.read_now().result(timeout=5)
    host.alive = False
    host.vscode.quit()
    assert wait_for(lambda: closed == [1])
    assert session.close_reason == "VS Code was closed"
    time.sleep(0.3)
    assert closed == [1]


def test_a_reloaded_window_connects_again(opened):
    session, host, _, closed, _ = opened()
    session.read_now().result(timeout=5)
    host.vscode.reload()
    session.perform(Call("write_file", {"path": "hello.py", "text": "print('again')\n"})).result(timeout=5)
    assert session.read_now().result(timeout=5).files["hello.py"].text == "print('again')\n"
    assert len(host.vscode.envs) == 2                           # the terminal settings are sent again
    assert not closed


def test_no_reconnect_in_time_is_reported(opened, monkeypatch):
    monkeypatch.setattr(session_module, "RECONNECT_S", 0.3)
    session, host, _, closed, _ = opened()
    session.read_now().result(timeout=5)
    host.vscode.quit()                                          # the window stays, the add-on never returns
    assert wait_for(lambda: closed == [1])
    assert session.close_reason == "lost touch with VS Code"


def test_close_asks_vs_code_to_close_and_does_not_call_on_closed(opened):
    session, host, _, closed, _ = opened()
    session.read_now().result(timeout=5)
    session.close(save=True)
    assert wait_for(lambda: host.vscode.asked_to_close)
    assert wait_for(lambda: not host.link_file.exists())
    time.sleep(0.3)
    assert not closed
    with pytest.raises(RuntimeError):
        session.perform(Call("open_file", {"path": "hello.py"})).result(timeout=5)


# Pointing.

def test_editor_line_rect_from_visible_range():
    area = Rect(100, 200, 800, 600)
    active = Active("hello.py", 1, 1, visible_from=11, visible_to=40, line_height=19.0, font_size=14.0)
    assert editor_line_spot(area, active, 13, 2.0) == Spot(Rect(100, 276, 800, 38))
    assert editor_line_spot(area, active, 3, 2.0) == Spot(Rect(100, 200, 800, 38), "Scroll up to line 3")
    assert editor_line_spot(area, active, 90, 2.0) == Spot(Rect(100, 762, 800, 38), "Scroll down to line 90")
    shown = Active("hello.py", 1, 1, visible_from=11, visible_to=26, line_height=19.0, font_size=14.0)
    assert editor_line_spot(area, shown, 26, 2.0) == Spot(Rect(100, 770, 800, 30))   # cut at the bottom edge
    # A line the snapshot calls visible but that falls below the editor (an old snapshot) is below it.
    assert editor_line_spot(area, active, 40, 2.0) == Spot(Rect(100, 762, 800, 38), "Scroll down to line 40")


def test_editor_line_past_the_end_of_a_short_file_points_where_it_will_go():
    # A 2-line file: VS Code says lines 1-2 are on screen, and line 3 is the one the learner types next.
    area = Rect(100, 100, 800, 700)
    short = Active("hello.py", 2, 1, visible_from=1, visible_to=2, line_height=19.0, font_size=14.0)
    spot = editor_line_spot(area, short, 3, 2.0)
    assert "Scroll" not in spot.bubble
    assert area.y <= spot.rect.y < area.y + area.h
    assert spot == Spot(Rect(100, 176, 800, 38))
    # Far enough past the end that it would be below the editor: that still needs scrolling.
    assert editor_line_spot(area, short, 30, 2.0) == Spot(Rect(100, 762, 800, 38), "Scroll down to line 30")


def test_locate_a_line_of_the_open_file(opened):
    session, host, *_ = opened()
    session.perform(Call("open_file", {"path": "hello.py"})).result(timeout=5)
    session.read_now().result(timeout=5)
    host.rects[("editor", "hello.py")] = Rect(100, 200, 800, 600)
    spot = session.locate(Target("editor_line", "hello.py:3")).result(timeout=5)
    assert spot == Spot(Rect(100, 276, 800, 38))


def test_locate_a_line_of_another_file_points_at_it_in_the_explorer(opened):
    session, host, *_ = opened()
    session.perform(Call("open_file", {"path": "hello.py"})).result(timeout=5)
    session.read_now().result(timeout=5)
    host.rects[("explorer_item", "notes/readme.txt")] = Rect(10, 300, 200, 44)
    spot = session.locate(Target("editor_line", "notes/readme.txt:1")).result(timeout=5)
    assert spot == Spot(Rect(10, 300, 200, 44), "Open readme.txt first")


def test_locate_a_file_still_to_make_points_at_new_file(opened):
    # Lesson 1's first step: the row for the file to make is not there yet, so point where it is made.
    session, host, *_ = opened()
    session.read_now().result(timeout=5)
    host.rects[("new_file", "")] = Rect(200, 104, 32, 32)
    spot = session.locate(Target("explorer_item", "ask.py")).result(timeout=5)
    assert spot == Spot(Rect(200, 104, 32, 32), "New File here")
    # A file that is there but whose row cannot be seen (scrolled away) is not one to make.
    assert session.locate(Target("explorer_item", "hello.py")).result(timeout=5) is None


def test_locate_other_targets_asks_ui_automation(opened):
    session, host, *_ = opened()
    session.read_now().result(timeout=5)
    host.rects[("terminal", "")] = Rect(0, 900, 1200, 300)
    assert session.locate(Target("terminal", "")).result(timeout=5) == Spot(Rect(0, 900, 1200, 300))
    assert session.locate(Target("run_button", "")).result(timeout=5) is None
    assert session.locate(Target("editor_line", "hello.py:zero")).result(timeout=5) is None
    assert session.locate(Target("cell", "A1")).result(timeout=5) is None


def test_watch_reports_only_moves_of_1_px_or_more(opened, monkeypatch):
    monkeypatch.setattr(session_module, "WATCH_EVERY_S", 0.02)
    session, host, *_ = opened()
    session.read_now().result(timeout=5)
    host.rects[("terminal", "")] = Rect(0, 900, 1200, 300)
    spots: list = []
    session.watch(Target("terminal", ""), spots.append)
    assert wait_for(lambda: len(spots) == 1)
    host.rects[("terminal", "")] = Rect(0.4, 900, 1200, 300)
    time.sleep(0.2)
    assert len(spots) == 1
    host.rects[("terminal", "")] = Rect(0, 880, 1200, 320)
    assert wait_for(lambda: len(spots) == 2)
    del host.rects[("terminal", "")]
    assert wait_for(lambda: len(spots) == 3 and spots[-1] is None)
    session.watch(None, spots.append)
    host.rects[("terminal", "")] = Rect(5, 5, 5, 5)
    time.sleep(0.2)
    assert len(spots) == 3


def test_waiting_asks_for_a_fresh_state_every_second(opened, monkeypatch):
    monkeypatch.setattr(session_module, "IDLE_REREAD_S", 0.05)
    monkeypatch.setattr(session_module, "WATCH_EVERY_S", 0.02)
    session, host, *_ = opened()
    session.read_now().result(timeout=5)
    before = host.vscode.pings
    session.set_waiting(True)
    assert wait_for(lambda: host.vscode.pings >= before + 3)
    session.set_waiting(False)
    time.sleep(0.15)
    stopped = host.vscode.pings
    time.sleep(0.2)
    assert host.vscode.pings == stopped


def test_place_moves_the_window(opened):
    session, host, *_ = opened()
    session.read_now().result(timeout=5)
    session.place(Rect(0, 0, 1000, 800)).result(timeout=5)
    assert host.placed == [(WINDOW, Rect(0, 0, 1000, 800))]


# The plug-in.

def test_the_plugin_menus():
    plugin = VsCodePlugin()
    assert plugin.app_id == "vscode" and plugin.title == "VS Code"
    assert plugin.target_kinds == {"editor_line", "explorer_item", "run_button", "terminal"}
    assert {"new_file", "write_file", "append_line", "open_file", "save_file", "run_file", "clear_terminal",
            "delete_file"} == set(plugin.ops)
    assert [p.name for p in plugin.ops["run_file"].params] == ["path", "input"]


def test_a_good_starter_passes():
    plugin = VsCodePlugin()
    assert plugin.validate_starter(STARTER) == []
    assert plugin.validate_starter({"files": {}}) == []
    assert plugin.validate_starter({"files": {"ask.py": ""}, "open": "ask.py", "env": ["META_API_KEY"]}) == []


@pytest.mark.parametrize("starter, problem", [
    ("hello", "starter: must be an object with the lesson's files"),
    ({"files": {"hello.py": ""}, "sheet": "A1"}, "starter.sheet: a VS Code lesson starts with files, open and env only"),
    ({"files": ["hello.py"]}, "starter.files: must map each file's path to its text"),
    ({"files": {"../outside.py": ""}}, "starter.files: ../outside.py must be a path inside the lesson folder"),
    ({"files": {"C:/x.py": ""}}, "starter.files: C:/x.py must be a path inside the lesson folder"),
    ({"files": {".vscode/settings.json": "{}"}}, "starter.files: .vscode/settings.json is in .vscode, which the program keeps for itself"),
    ({"files": {"a.py": "", "A.py": ""}}, "starter.files: A.py and a.py are the same file on Windows"),
    ({"files": {"hello.py": 3}}, "starter.files: hello.py must be the file's text"),
    ({"files": {"big.py": "x" * (256 * 1024 + 1)}}, "starter.files: big.py is over 256 KB"),
    ({"files": {f"f{i}.py": "" for i in range(21)}}, "starter.files: 21 files; keep it to 20"),
    ({"files": {"hello.py": ""}, "open": "other.py"}, "starter.open: must name one of the starter's files"),
    ({"files": {}, "env": ["HOME"]}, "starter.env: only META_API_KEY can be given to VS Code's terminal"),
])
def test_a_bad_starter_names_its_problem(starter, problem):
    assert problem in VsCodePlugin().validate_starter(starter)
