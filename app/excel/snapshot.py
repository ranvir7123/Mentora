"""A snapshot: everything a step check may ask about the workbook, as plain data.

Checks never talk to Excel. They judge snapshots, so the same rule judges the live learner, the
before/after proof made from an expert's recording, and the tests that run with no Excel at all.

read_snapshot() is the one place that reads Excel, and it must run on the COM thread. It reads in
bulk (a whole used range in one call) and falls back to a column, then a cell, only where a
format is mixed, so a read stays cheap enough to run after every change. It never activates a
sheet or moves the selection: a reader that fires Excel's events would trigger itself forever.

A cell that is empty, in the General format and not bold is left out, so "B7 is empty" and
"B7 is missing" read the same.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

# Value2 hands back an error cell (#DIV/0! and the rest) as one of these numbers.
ERRORS = {
    -2146826281: "#DIV/0!",
    -2146826246: "#N/A",
    -2146826259: "#NAME?",
    -2146826288: "#NULL!",
    -2146826252: "#NUM!",
    -2146826265: "#REF!",
    -2146826273: "#VALUE!",
}
GENERAL = "General"
XL_WORKSHEET = -4167


@dataclass(frozen=True)
class Cell:
    value: float | str | bool | None = None
    formula: str | None = None          # only when the cell holds a formula
    number_format: str = GENERAL
    bold: bool = False


@dataclass(frozen=True)
class Chart:
    name: str
    chart_type: int                     # Excel's XlChartType number, e.g. 51 = clustered column
    title: str | None
    series: tuple[str, ...]             # each series' =SERIES(...) formula


@dataclass(frozen=True)
class Filter:
    range: str                          # e.g. "A1:D20"
    on: dict[int, str] = field(default_factory=dict)   # filtered column (1 = first) -> criteria


@dataclass(frozen=True)
class Sheet:
    name: str
    cells: dict[str, Cell] = field(default_factory=dict)
    charts: tuple[Chart, ...] = ()
    filter: Filter | None = None
    is_worksheet: bool = True           # False for a chart sheet, which has no cells


@dataclass(frozen=True)
class Snapshot:
    sheets: tuple[Sheet, ...]
    active_sheet: str
    selection: str                      # e.g. "B2" or "B2:C5", on the active sheet
    frozen_rows: int = 0                # rows kept on screen at the top of the active sheet
    frozen_cols: int = 0
    taken_ns: int = 0

    def sheet(self, name: str) -> Sheet | None:
        return next((s for s in self.sheets if s.name == name), None)

    def cell(self, sheet: str, address: str) -> Cell:
        s = self.sheet(sheet)
        return s.cells.get(address.replace("$", "").upper(), Cell()) if s else Cell()


# ------------------------------------------------------------------ pure helpers, no Excel

def col_letters(col: int) -> str:
    out = ""
    while col:
        col, rem = divmod(col - 1, 26)
        out = chr(65 + rem) + out
    return out


def as_grid(block, rows: int, cols: int) -> list[list]:
    """Excel returns one value for a one-cell range and rows of values otherwise; always rows."""
    if rows == 1 and cols == 1 and not isinstance(block, tuple):
        return [[block]]
    return [list(r) for r in block]


def clean_value(v):
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, int) and v in ERRORS:
        return ERRORS[v]
    if isinstance(v, (int, float)):
        return float(v)
    return "" if v == "" else str(v)


def cells_from_block(top: int, left: int, values, formulas, formats, bolds) -> dict[str, Cell]:
    """Build the cells of one rectangle from grids of the same shape; leave out blank ones."""
    out: dict[str, Cell] = {}
    for r, row in enumerate(values):
        for c, raw in enumerate(row):
            value = clean_value(raw)
            if value == "":
                value = None
            f = formulas[r][c]
            formula = f if isinstance(f, str) and f.startswith("=") else None
            fmt = formats[r][c] or GENERAL
            bold = bool(bolds[r][c])
            if value is None and formula is None and fmt == GENERAL and not bold:
                continue
            out[f"{col_letters(left + c)}{top + r}"] = Cell(value, formula, fmt, bold)
    return out


# ------------------------------------------------------------------ the COM side

def uniform_grid(read_span, rows: int, cols: int) -> list[list]:
    """One property over a rectangle, in as few reads as possible.

    read_span(r0, r1, c) reads rows r0..r1 of column c (c=None: every column). Excel answers None
    when the cells asked about differ, so a mixed column is halved until each half is uniform:
    a bold header over a plain column costs about two reads per halving, not one per cell.
    """
    whole = read_span(0, rows - 1, None)
    if whole is not None:
        return [[whole] * cols for _ in range(rows)]
    grid = [[None] * cols for _ in range(rows)]

    def fill(r0: int, r1: int, c: int) -> None:
        v = read_span(r0, r1, c)
        if v is not None or r0 == r1:
            for r in range(r0, r1 + 1):
                grid[r][c] = v
            return
        mid = (r0 + r1) // 2
        fill(r0, mid, c)
        fill(mid + 1, r1, c)

    for c in range(cols):
        fill(0, rows - 1, c)
    return grid


def _read_cells(ws) -> dict[str, Cell]:
    ur = ws.UsedRange
    top, left = int(ur.Row), int(ur.Column)
    rows, cols = int(ur.Rows.Count), int(ur.Columns.Count)
    values = as_grid(ur.Value2, rows, cols)
    formulas = as_grid(ur.Formula, rows, cols)

    def span(r0, r1, c):
        if c is None:
            return ur
        letter = col_letters(left + c)
        return ws.Range(f"{letter}{top + r0}:{letter}{top + r1}")

    formats = uniform_grid(lambda r0, r1, c: span(r0, r1, c).NumberFormat, rows, cols)
    bolds = uniform_grid(lambda r0, r1, c: span(r0, r1, c).Font.Bold, rows, cols)
    return cells_from_block(top, left, values, formulas, formats, bolds)


def _read_charts(ws) -> tuple[Chart, ...]:
    # BINDING (measured in the old project): Worksheet.ChartObjects, not Workbook.Charts. A chart
    # on the sheet shows in ChartObjects; F11's separate chart sheet shows only in Workbook.Charts.
    charts = []
    objs = ws.ChartObjects()
    for i in range(1, int(objs.Count) + 1):
        co = objs.Item(i)
        ch = co.Chart
        title = str(ch.ChartTitle.Text) if bool(ch.HasTitle) else None
        sc = ch.SeriesCollection()
        series = tuple(str(sc.Item(j).Formula) for j in range(1, int(sc.Count) + 1))
        charts.append(Chart(str(co.Name), int(ch.ChartType), title, series))
    return tuple(charts)


def _read_filter(ws) -> Filter | None:
    if not bool(ws.AutoFilterMode):
        return None
    af = ws.AutoFilter
    on: dict[int, str] = {}
    filters = af.Filters
    for i in range(1, int(filters.Count) + 1):
        f = filters.Item(i)
        if bool(f.On):
            on[i] = str(f.Criteria1)
    return Filter(str(af.Range.Address).replace("$", ""), on)


def read_snapshot(wb) -> Snapshot:
    """Read the whole workbook. COM thread only; a busy Excel raises, and the caller retries."""
    sheets = []
    for i in range(1, int(wb.Sheets.Count) + 1):
        sh = wb.Sheets.Item(i)
        name = str(sh.Name)
        if int(sh.Type) != XL_WORKSHEET:
            sheets.append(Sheet(name, is_worksheet=False))
            continue
        sheets.append(Sheet(name, _read_cells(sh), _read_charts(sh), _read_filter(sh)))

    app = wb.Application
    win = wb.Windows(1)
    active = str(win.ActiveSheet.Name)
    selection = ""
    try:
        selection = str(app.Selection.Address).replace("$", "")
    except AttributeError:   # a chart or a shape is selected, not cells
        pass
    frozen_rows = frozen_cols = 0
    if bool(win.FreezePanes):
        # The top-left pane stays put; it starts at its own scroll row and runs SplitRow rows.
        first = win.Panes.Item(1)
        if int(win.SplitRow):
            frozen_rows = int(first.ScrollRow) - 1 + int(win.SplitRow)
        if int(win.SplitColumn):
            frozen_cols = int(first.ScrollColumn) - 1 + int(win.SplitColumn)
    return Snapshot(tuple(sheets), active, selection, frozen_rows, frozen_cols,
                    time.perf_counter_ns())
