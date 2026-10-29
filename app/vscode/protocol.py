"""The messages the program and the VS Code add-on send each other.

One JSON object per line, each with a `type`. `extensions/vscode/src/protocol.ts` names the same
messages and fields; `tests/vscode/test_protocol_in_step.py` keeps the two in step.

Add-on to program:
- `hello{token, version}` first, or the link is dropped.
- `state{files, active, problems, run}` after any edit, save, cursor move, problems change or terminal
  run, at most every 100 ms, and at once after a `ping`. `files[path].text` is the text saved on disk;
  `saved` is false while the editor holds changes not yet saved.
- `done{id, ok, error}` when an operation finished (`run_file`: when the run started).

Program to add-on:
- `do{id, op: {kind, args}}` performs one operation from the plug-in's menu.
- `ping{}` asks for a fresh `state`.
- `env{set, path_prepend}` sets variables for terminals opened from now on. Never saved anywhere.
- `close{}` saves the lesson's files and closes the window.
"""
from __future__ import annotations

PROTOCOL_VERSION = 1
OUTPUT_LIMIT = 4096              # characters of a run's output the add-on keeps

MESSAGES: dict[str, tuple[str, ...]] = {
    "hello": ("token", "version"),
    "state": ("files", "active", "problems", "run"),
    "done": ("id", "ok", "error"),
    "do": ("id", "op"),
    "ping": (),
    "env": ("set", "path_prepend"),
    "close": (),
}

PARTS: dict[str, tuple[str, ...]] = {
    "FileState": ("text", "saved"),
    "Active": ("path", "line", "column", "visible_from", "visible_to", "line_height", "font_size"),
    "Problem": ("path", "line", "severity", "message"),
    "Run": ("command", "exit_code", "output", "finished"),
    "Op": ("kind", "args"),
}

TS_NAMES = {"hello": "Hello", "state": "State", "done": "Done", "do": "Do", "ping": "Ping", "env": "Env",
            "close": "Close"}
