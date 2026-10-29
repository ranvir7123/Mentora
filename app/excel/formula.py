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


# Moving and comparing whole formulas. Quoted text is kept as it is; everything else is formula.

_QUOTED_SPLIT = re.compile(r'("(?:[^"]|"")*")')
_CELL_PART = re.compile(r"(?<![A-Za-z0-9_.])(\$?)([A-Za-z]{1,3})(\$?)(\d+)(?![A-Za-z0-9_(!])")


def _col_index(letters: str) -> int:
    n = 0
    for ch in letters.upper():
        n = n * 26 + ord(ch) - 64
    return n


def _col_letters(col: int) -> str:
    out = ""
    while col:
        col, rem = divmod(col - 1, 26)
        out = chr(65 + rem) + out
    return out


def _outside_quotes(text: str, fn) -> str:
    parts = _QUOTED_SPLIT.split(text)
    return "".join(p if i % 2 else fn(p) for i, p in enumerate(parts))


def moved(text: str, rows: int, cols: int) -> str:
    """The formula as Excel writes it when copied `rows` down and `cols` right: $ parts stay put."""
    def shift(m: re.Match) -> str:
        col_fixed, letters, row_fixed, digits = m.groups()
        col = _col_index(letters) + (0 if col_fixed else cols)
        row = int(digits) + (0 if row_fixed else rows)
        if col < 1 or row < 1:
            return "#REF!"
        return f"{col_fixed}{_col_letters(col)}{row_fixed}{row}"
    return _outside_quotes(text, lambda part: _CELL_PART.sub(shift, part))


def plain(text: str) -> str:
    """The formula with $ signs, spaces and letter case taken out: the cells it points at, as written."""
    return _outside_quotes(text, lambda part: re.sub(r"\s+", "", part).replace("$", "").upper())
