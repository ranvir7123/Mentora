"""The small shapes every part of the program shares.

A lesson step names a target to point at, a check that says when it is done, and an operation the
program can replay to prove the check. Each app plug-in offers a fixed menu of checks and operations;
`validate_args` keeps whatever a lesson asks of that menu inside its rules, and names every problem in
plain words so a broken lesson is caught when it is loaded, not on the learner's screen.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class Rect:
    """A rectangle in physical screen pixels."""
    x: float
    y: float
    w: float
    h: float

    def inflate(self, d: float) -> Rect:
        return Rect(self.x - d, self.y - d, self.w + 2 * d, self.h + 2 * d)

    def intersects(self, other: Rect) -> bool:
        return (self.x < other.x + other.w and other.x < self.x + self.w
                and self.y < other.y + other.h and other.y < self.y + self.h)

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.w / 2, self.y + self.h / 2)


@dataclass(frozen=True)
class Spot:
    """Where to point. `bubble` replaces the default words, e.g. "open this first" on a folded group.

    `room` is where the mascot and its words may go: for a cell, the sheet's visible cells, so they never
    cover the app's own buttons and bars. None lets them go anywhere on the screen beside the target.
    `filled` is what they keep off when there is space: for a cell, the sheet's filled cells on screen, so
    the learner can still read them."""
    rect: Rect
    bubble: str = ""
    room: Rect | None = None
    filled: Rect | None = None


@dataclass(frozen=True)
class Target:
    """What a step points at: a kind the plug-in knows (cell, control, editor_line...) and its reference."""
    kind: str
    ref: str


@dataclass(frozen=True)
class Call:
    """One check or one replay operation: a name from the plug-in's menu and its arguments."""
    kind: str
    args: Mapping[str, Any]


PARAM_TYPES = frozenset({"cell", "range", "cells", "text", "number", "value", "int", "bool", "enum",
                         "function", "path"})


@dataclass(frozen=True)
class Param:
    name: str
    type: str
    required: bool = True
    choices: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.type not in PARAM_TYPES:
            raise ValueError(f"{self.name}: unknown parameter type {self.type!r}")
        if self.type == "enum" and not self.choices:
            raise ValueError(f"{self.name}: an enum needs its choices")


@dataclass(frozen=True)
class Verdict:
    """A check's answer on one snapshot.

    `attempted` is True when the snapshot shows the learner did something at the target, so a wrong
    answer is worth a "Not yet". `code` is a short machine string such as `covers_missing:B6`; `text`
    is the "Not yet" line.
    """
    ok: bool
    attempted: bool
    code: str = ""
    text: str = ""

    @classmethod
    def right(cls) -> Verdict:
        return cls(True, True)

    @classmethod
    def waiting(cls) -> Verdict:
        return cls(False, False)

    @classmethod
    def wrong(cls, code: str, text: str) -> Verdict:
        return cls(False, True, code, text)


@dataclass(frozen=True)
class CheckKind:
    """One entry on a plug-in's check menu: a pure function from (snapshot, args) to a Verdict.

    `event`, for a check that judges something that happens, like the last run: what it judges in a
    snapshot. The step then counts only a new one, not one already there when the step opened."""
    name: str
    params: tuple[Param, ...]
    run: Callable[[Any, Mapping], Verdict]
    summary: str
    event: Callable[[Any], Any] | None = None


@dataclass(frozen=True)
class OpKind:
    """One entry on a plug-in's operation menu. The doing lives in the plug-in's session."""
    name: str
    params: tuple[Param, ...]
    summary: str


_SHEET = r"(?:[A-Za-z0-9_.]+|'(?:[^']|'')+')!"
_CELL = r"\$?[A-Z]{1,3}\$?[0-9]+"
_CELL_RE = re.compile(rf"^(?:{_SHEET})?{_CELL}$")
_RANGE_RE = re.compile(rf"^(?:{_SHEET})?{_CELL}(?::{_CELL})?$")
_FUNCTION_RE = re.compile(r"^[A-Z][A-Z0-9.]*$")

_WHAT = {
    "cell": "a cell address like B7",
    "range": "a range like A1:B6",
    "cells": "a list of cell addresses",
    "text": "text",
    "number": "a number",
    "value": "a number or text",
    "int": "a whole number",
    "bool": "true or false",
    "function": "a function name like SUM",
    "path": "a relative path inside the project",
}


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _is_cell(v: Any) -> bool:
    return isinstance(v, str) and bool(_CELL_RE.match(v))


def _is_path(v: Any) -> bool:
    if not isinstance(v, str) or not v or v.startswith(("/", "\\")) or PureWindowsPath(v).drive:
        return False
    return ".." not in PurePosixPath(v.replace("\\", "/")).parts


def _fits(p: Param, v: Any) -> bool:
    t = p.type
    if t == "cell":
        return _is_cell(v)
    if t == "range":
        return isinstance(v, str) and bool(_RANGE_RE.match(v))
    if t == "cells":
        return isinstance(v, (list, tuple)) and len(v) > 0 and all(_is_cell(c) for c in v)
    if t == "text":
        return isinstance(v, str) and v != ""
    if t == "number":
        return _is_number(v)
    if t == "value":
        return _is_number(v) or (isinstance(v, str) and v != "")
    if t == "int":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "bool":
        return isinstance(v, bool)
    if t == "enum":
        return v in p.choices
    if t == "function":
        return isinstance(v, str) and bool(_FUNCTION_RE.match(v))
    return _is_path(v)


def validate_args(kind: CheckKind | OpKind, args: Mapping) -> list[str]:
    """Every problem with these arguments, in plain words, each starting with the kind's name."""
    problems = []
    for p in kind.params:
        value = args.get(p.name)
        if value is None:
            if p.required:
                problems.append(f"{kind.name}: {p.name} is missing")
        elif not _fits(p, value):
            what = f"one of {', '.join(p.choices)}" if p.type == "enum" else _WHAT[p.type]
            problems.append(f"{kind.name}: {p.name} is {value!r}, which is not {what}")
    known = {p.name for p in kind.params}
    for name in args:
        if name not in known:
            problems.append(f"{kind.name}: {name} is not one of its settings")
    return problems
