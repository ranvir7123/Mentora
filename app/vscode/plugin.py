"""The VS Code plug-in: its menus of checks and operations, the rules for a lesson's starting files,
and opening a lesson in VS Code.

A VS Code lesson starts with `{"files": {path: text}, "open": path, "env": ["META_API_KEY"]}`, all
optional: the files to put in the lesson's folder, the one to show first, and the settings its
terminal needs (only the Meta key, which never leaves the computer's memory)."""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PureWindowsPath
from typing import Any, Callable

from app.core.lesson import Lesson
from app.meta.key import require_key
from app.vscode.checks import CHECKS
from app.vscode.ops import OPS
from app.vscode.session import TARGET_KINDS, VsCodeSession

MAX_STARTER_FILES = 20
MAX_STARTER_BYTES = 256 * 1024           # per file, the same limit the add-on reads up to
STARTER_KEYS = ("files", "open", "env")
ALLOWED_ENV = frozenset({"META_API_KEY"})
_BAD_CHARS = set('<>:"|?*')


def _inside_folder(path: Any) -> bool:
    if not isinstance(path, str) or not path or path.startswith(("/", "\\")) or PureWindowsPath(path).drive:
        return False
    return all(part and part not in (".", "..") and not (_BAD_CHARS & set(part)) and part == part.rstrip(" .")
               for part in path.replace("\\", "/").split("/"))


def starter_problems(starter: Any) -> list[str]:
    if not isinstance(starter, Mapping):
        return ["starter: must be an object with the lesson's files"]
    problems = [f"starter.{key}: a VS Code lesson starts with files, open and env only"
                for key in starter if key not in STARTER_KEYS]
    files = starter.get("files", {})
    if not isinstance(files, Mapping):
        problems.append("starter.files: must map each file's path to its text")
        files = {}
    if len(files) > MAX_STARTER_FILES:
        problems.append(f"starter.files: {len(files)} files; keep it to {MAX_STARTER_FILES}")
    seen: dict[str, str] = {}
    for path, text in files.items():
        if not _inside_folder(path):
            problems.append(f"starter.files: {path} must be a path inside the lesson folder")
            continue
        clean = path.replace("\\", "/").lower()
        if clean.split("/")[0] == ".vscode":
            problems.append(f"starter.files: {path} is in .vscode, which the program keeps for itself")
        if clean in seen:
            problems.append(f"starter.files: {path} and {seen[clean]} are the same file on Windows")
        seen.setdefault(clean, path)
        if not isinstance(text, str):
            problems.append(f"starter.files: {path} must be the file's text")
        elif len(text.encode("utf-8")) > MAX_STARTER_BYTES:
            problems.append(f"starter.files: {path} is over {MAX_STARTER_BYTES // 1024} KB")
    if "open" in starter:
        open_file = starter["open"]
        if not isinstance(open_file, str) or open_file.replace("\\", "/").lower() not in seen:
            problems.append("starter.open: must name one of the starter's files")
    env = starter.get("env", [])
    if not isinstance(env, list) or any(name not in ALLOWED_ENV for name in env):
        problems.append("starter.env: only META_API_KEY can be given to VS Code's terminal")
    return problems


class VsCodePlugin:
    app_id = "vscode"
    title = "VS Code"
    target_kinds = TARGET_KINDS

    def __init__(self, *, host: Any = None, link_file: Path | None = None,
                 key_reader: Callable[[str], str] = require_key) -> None:
        self.checks = CHECKS
        self.ops = OPS
        self._host = host
        self._link_file = link_file
        self._key_reader = key_reader

    def validate_starter(self, starter: Mapping) -> list[str]:
        return starter_problems(starter)

    def open(self, lesson: Lesson, workdir: Path, *, visible: bool = True, resume: bool = False,
             on_snapshot: Callable[[Any], None], on_closed: Callable[[], None]) -> VsCodeSession:
        return VsCodeSession(lesson, workdir, visible=visible, resume=resume, on_snapshot=on_snapshot,
                             on_closed=on_closed, host=self._host, link_file=self._link_file,
                             key_reader=self._key_reader)
