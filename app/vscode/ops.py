"""The VS Code operation menu: what a lesson's replays and the prover can ask the add-on to do.
The doing lives in the add-on (extensions/vscode/src/extension.ts), reached through the session."""
from __future__ import annotations

from app.core.types import OpKind, Param

_PATH = Param("path", "path")
_TEXT = Param("text", "text")

OPS: dict[str, OpKind] = {op.name: op for op in (
    OpKind("write_file", (_PATH, _TEXT), "Write the whole file, making it and its folder if needed, and save it"),
    OpKind("append_line", (_PATH, _TEXT), "Open the file and add a line at its end, then save it"),
    OpKind("open_file", (_PATH,), "Open the file in the editor"),
    OpKind("save_file", (_PATH,), "Save the file's changes"),
    OpKind("delete_file", (_PATH,), "Delete the file, closing it in the editor first"),
    OpKind("run_file", (_PATH, Param("input", "text", required=False)),
           "Run the file in VS Code's terminal with python and wait for it to finish; `input` is typed "
           "into the program, one line per answer"),
    OpKind("clear_terminal", (), "Stop a program still running, forget the last run and clear the terminal"),
)}
