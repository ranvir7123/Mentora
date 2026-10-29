"""What a formula refers to and which functions it calls, never how it is spelled.

A learner who types =(B4-C4) for =B4-C4, or =sum(b2:b6) for =SUM(B2:B6), has done the same
thing, and the checks must agree. These readings are equal for every spelling of one formula and
differ when the formula is a different one.

Pure string work, no Excel. Known limits: table references (Table1[Spent]) give no cells;
a cross-sheet reference ('Other'!A1) loses its sheet and reads as A1; named ranges are dropped.
No lesson here uses them.
"""
from __future__ import annotations

import re

_QUOTED = re.compile(r'"(?:[^"]|"")*"')
_REF = re.compile(r"(?<![A-Za-z0-9_])\$?([A-Za-z]{1,3})\$?(\d+)(?::\$?([A-Za-z]{1,3})\$?(\d+))?")
_FUNC = re.compile(r"([A-Za-z_][A-Za-z0-9_.]*)\s*\(")
_ABS = re.compile(r"(?<![A-Za-z0-9_])\$[A-Za-z]{1,3}\$\d+")


def is_formula(text) -> bool:
    return isinstance(text, str) and text.lstrip().startswith("=")


def _body(text: str) -> str:
    # Drop the leading = and every quoted string, so "B2" inside IF is not a reference.
    return _QUOTED.sub('""', text.lstrip()[1:])


def refs_of(text) -> list[str]:
    """Every cell or range the formula names: uppercase, $ removed, sorted, once each."""
    if not is_formula(text):
        return []
    body = _FUNC.sub(lambda m: " " * len(m.group(0)), _body(text))   # LOG10( is not cell LOG10
    found: set[str] = set()
    for m in _REF.finditer(body):
        a = f"{m.group(1).upper()}{m.group(2)}"
        if m.group(3):
            a = f"{a}:{m.group(3).upper()}{m.group(4)}"
        found.add(a)
    return sorted(found)


def functions_of(text) -> list[str]:
    """Every function the formula calls: uppercase, sorted, once each."""
    if not is_formula(text):
        return []
    return sorted({m.group(1).upper() for m in _FUNC.finditer(_body(text))})


def absolute_refs_of(text) -> list[str]:
    """The fully fixed references ($B$1), uppercase, $ removed: the "fixed rate cell" lessons ask for these."""
    if not is_formula(text):
        return []
    return sorted({m.group(0).replace("$", "").upper() for m in _ABS.finditer(_body(text))})
