"""Cell and range addresses as lessons write them: "B8", "A1:C1", "Budget!B8", "'My sheet'!A1:B2".

A lesson may name the sheet; without one an address means the active sheet. `$` signs are allowed and
mean nothing here (they matter only inside formulas). Pure string work, no Excel.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.excel.snapshot import col_letters

MAX_ROW = 1_048_576
MAX_COL = 16_384                     # XFD

_AREA = re.compile(r"^(?:(?P<sheet>'(?:[^']|'')+'|[^'!]+)!)?"
                   r"\$?(?P<c1>[A-Za-z]{1,3})\$?(?P<r1>\d+)"
                   r"(?::\$?(?P<c2>[A-Za-z]{1,3})\$?(?P<r2>\d+))?$")


def col_index(letters: str) -> int:
    n = 0
    for ch in letters.upper():
        n = n * 26 + ord(ch) - 64
    return n


def cell_name(row: int, col: int) -> str:
    return f"{col_letters(col)}{row}"


@dataclass(frozen=True)
class Area:
    """A rectangle of cells; `sheet` is None when the address named no sheet."""
    sheet: str | None
    top: int
    left: int
    bottom: int
    right: int

    @property
    def first(self) -> str:
        return cell_name(self.top, self.left)

    @property
    def last(self) -> str:
        return cell_name(self.bottom, self.right)

    @property
    def a1(self) -> str:
        """The address without its sheet: "B2:B6", or "B2" for one cell."""
        return self.first if self.size == 1 else f"{self.first}:{self.last}"

    @property
    def size(self) -> int:
        return (self.bottom - self.top + 1) * (self.right - self.left + 1)

    def contains(self, row: int, col: int) -> bool:
        return self.top <= row <= self.bottom and self.left <= col <= self.right

    def positions(self) -> list[tuple[int, int]]:
        """(row, column) of every cell, row by row."""
        return [(r, c) for r in range(self.top, self.bottom + 1) for c in range(self.left, self.right + 1)]

    def cells(self) -> list[str]:
        return [cell_name(r, c) for r, c in self.positions()]

    def sheet_or(self, active: str) -> str:
        return self.sheet if self.sheet is not None else active


def parse_area(text: str) -> Area:
    """Read an address; raises ValueError naming it when it is not one."""
    m = _AREA.match(text.strip()) if isinstance(text, str) else None
    if m is None:
        raise ValueError(f"{text!r} is not a cell or range address")
    sheet = m.group("sheet")
    if sheet is not None and sheet.startswith("'"):
        sheet = sheet[1:-1].replace("''", "'")
    r1, c1 = int(m.group("r1")), col_index(m.group("c1"))
    r2, c2 = (int(m.group("r2")), col_index(m.group("c2"))) if m.group("c2") else (r1, c1)
    for r, c in ((r1, c1), (r2, c2)):
        if not (1 <= r <= MAX_ROW and 1 <= c <= MAX_COL):
            raise ValueError(f"{text!r} is outside the sheet")
    return Area(sheet, min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2))


def is_address(text) -> bool:
    try:
        parse_area(text)
    except ValueError:
        return False
    return True


def quote_sheet(name: str) -> str:
    """The sheet's name as Excel writes it before "!": quoted when it holds anything but letters and digits."""
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", name):
        return name
    return "'" + name.replace("'", "''") + "'"
