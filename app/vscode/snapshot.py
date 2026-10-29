"""What the program knows about a lesson's VS Code window at one moment, built from the add-on's
`state` message (see app/vscode/protocol.py). Anything malformed in the message is left out."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FileState:
    text: str            # the text saved on disk
    saved: bool          # False while the editor holds changes not yet saved


@dataclass(frozen=True)
class Active:
    path: str
    line: int            # 1-based
    column: int          # 1-based
    visible_from: int    # first line on screen, 1-based
    visible_to: int      # last line on screen, 1-based
    line_height: float   # CSS pixels, window zoom included
    font_size: float     # CSS pixels, window zoom included


@dataclass(frozen=True)
class Problem:
    path: str
    line: int            # 1-based
    severity: str        # error, warning, info or hint
    message: str


@dataclass(frozen=True)
class Run:
    command: str
    exit_code: int | None    # None while running, or when VS Code could not tell
    output: str              # the last 4096 characters, colour codes removed
    finished: bool


@dataclass(frozen=True)
class VsSnapshot:
    files: Mapping[str, FileState] = field(default_factory=dict)
    active: Active | None = None
    problems: tuple[Problem, ...] = ()
    run: Run | None = None

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> VsSnapshot:
        files = state.get("files")
        problems = state.get("problems")
        return cls(
            files={path: f for path, f in ((p, _file(v)) for p, v in files.items())
                   if isinstance(path, str) and f is not None} if isinstance(files, Mapping) else {},
            active=_active(state.get("active")),
            problems=tuple(p for p in map(_problem, problems) if p is not None)
            if isinstance(problems, list) else (),
            run=_run(state.get("run")),
        )

    def file(self, path: str) -> tuple[str, FileState] | None:
        """The lesson file at `path` and its name as VS Code shows it. Windows file names ignore capitals."""
        want = clean_path(path).lower()
        for name, state in self.files.items():
            if clean_path(name).lower() == want:
                return name, state
        return None


def clean_path(path: str) -> str:
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _file(v: Any) -> FileState | None:
    if isinstance(v, Mapping) and isinstance(v.get("text"), str) and isinstance(v.get("saved"), bool):
        return FileState(v["text"], v["saved"])
    return None


def _active(v: Any) -> Active | None:
    if not isinstance(v, Mapping) or not isinstance(v.get("path"), str):
        return None
    ints = ("line", "column", "visible_from", "visible_to")
    if not all(_is_int(v.get(k)) for k in ints) or not all(_is_number(v.get(k)) for k in ("line_height", "font_size")):
        return None
    return Active(v["path"], *(v[k] for k in ints), float(v["line_height"]), float(v["font_size"]))


def _problem(v: Any) -> Problem | None:
    if (isinstance(v, Mapping) and isinstance(v.get("path"), str) and _is_int(v.get("line"))
            and isinstance(v.get("severity"), str) and isinstance(v.get("message"), str)):
        return Problem(v["path"], v["line"], v["severity"], v["message"])
    return None


def _run(v: Any) -> Run | None:
    if (isinstance(v, Mapping) and isinstance(v.get("command"), str) and isinstance(v.get("output"), str)
            and isinstance(v.get("finished"), bool) and (v.get("exit_code") is None or _is_int(v.get("exit_code")))):
        return Run(v["command"], v.get("exit_code"), v["output"], v["finished"])
    return None
