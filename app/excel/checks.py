"""The Excel check menu: fixed rules that judge one snapshot. The AI never ticks a step.

Each rule accepts every right way to do a step: =SUM(B2:B6), =B2+B3+B4+B5+B6 and
=SUM(B2:B4)+SUM(B5:B6) all total B2:B6. For a wrong try it names the one difference, as a short
code (`covers_missing:B6`) and a "Not yet" line. A lesson's own mistake lines are matched to these
codes, so the codes stay stable.

`attempted` (in the Verdict) is False while the snapshot shows nothing done at the step's target;
the coach then stays quiet instead of saying "Not yet" to someone who has not started.

Addresses may carry a sheet (Budget!B8); without one they mean the active sheet. Formula
references are read without their sheet (see formula.py), so a formula is judged on its own sheet.
"""
from __future__ import annotations

import math
import re
from typing import Any, Callable, Mapping

from app.core.types import CheckKind, Param, Verdict
from app.excel.address import Area, cell_name, col_index, parse_area
from app.excel.formula import absolute_refs_of, functions_of, is_formula, moved, plain, refs_of
from app.excel.snapshot import GENERAL, Cell, Chart, Sheet, Snapshot, col_letters

NUMBER_FORMAT_KINDS = ("currency", "percent", "date", "decimal2", "whole")
CHART_TYPES = ("column", "bar", "line", "pie")

# Excel's XlChartType numbers, by the family a learner would name.
CHART_FAMILIES = {
    "column": {51, 52, 53, 54, 55, 56, -4100},
    "bar": {57, 58, 59, 60, 61, 62},
    "line": {4, 63, 64, 65, 66, 67, -4101},
    "pie": {5, -4102, 68, 69, 70, 71},
    "area": {1, 76, 77, -4098, 78, 79},
    "scatter": {-4169, 72, 73, 74, 75},
    "doughnut": {-4120, 80},
}

_FORMAT_NAMES = {"currency": "currency", "percent": "percent", "date": "a date", "decimal2": "two decimals",
                 "whole": "whole numbers", "general": "General", "other": "a different format"}


# ------------------------------------------------------------------ reading the snapshot

def _sheet_of(snap: Snapshot, area: Area) -> Sheet | None:
    return snap.sheet(area.sheet_or(snap.active_sheet))


def _cell(snap: Snapshot, address: str) -> tuple[str, Cell]:
    area = parse_area(address)
    return area.first, snap.cell(area.sheet_or(snap.active_sheet), area.first)


def _cells(snap: Snapshot, address: str) -> list[tuple[str, Cell]]:
    area = parse_area(address)
    sheet = area.sheet_or(snap.active_sheet)
    return [(a, snap.cell(sheet, a)) for a in area.cells()]


def _empty(c: Cell) -> bool:
    return c.formula is None and c.value in (None, "")


def _filled_or_all(cells: list[tuple[str, Cell]]) -> list[tuple[str, Cell]]:
    """Judge the cells that hold something; a row with a blank gap in it is not "half done"."""
    filled = [(a, c) for a, c in cells if not _empty(c)]
    return filled or cells


# ------------------------------------------------------------------ values

def _box(a: Area) -> tuple[int, int, int, int]:
    return a.top, a.left, a.bottom, a.right


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _as_number(text: Any) -> float | None:
    if not isinstance(text, str):
        return None
    try:
        return float(text.strip().lstrip("'").replace(",", ""))
    except ValueError:
        return None


def _same(have: Any, want: Any, rel: float) -> bool:
    if _is_number(want):
        return _is_number(have) and math.isclose(have, want, rel_tol=rel, abs_tol=rel)
    return isinstance(have, str) and have.strip().casefold() == str(want).strip().casefold()


def _show(v: Any) -> str:
    if _is_number(v):
        if float(v).is_integer() and abs(v) < 1e15:
            return f"{int(v):,}"
        return f"{v:,.4f}".rstrip("0").rstrip(".")
    return str(v).strip()


# ------------------------------------------------------------------ value_equals

def _value_equals(snap: Snapshot, args: Mapping) -> Verdict:
    _a, c = _cell(snap, args["cell"])
    want = args["value"]
    if _empty(c):
        return Verdict.waiting()
    if _same(c.value, want, 1e-9):
        return Verdict.right()
    if _is_number(want) and _as_number(c.value) is not None and math.isclose(_as_number(c.value), want,
                                                                             rel_tol=1e-9, abs_tol=1e-9):
        return Verdict.wrong("as_text", "Not yet: Excel is keeping that number as text. Type it again as a plain number.")
    return Verdict.wrong("differs", f"Not yet: that says {_show(c.value)}. It should say {_show(want)}.")


# ------------------------------------------------------------------ formula

def _ref_areas(formula: str) -> list[Area]:
    return [parse_area(r) for r in refs_of(formula)]


def _plain_cell(address: str) -> str:
    return parse_area(address).first


def _first_outside(areas: list[Area], allowed: set[tuple[int, int]]) -> str | None:
    """The first referenced cell (row by row) that is not allowed. Stops early, so a huge range
    costs no more than the allowed cells plus one."""
    for area in areas:
        for row in range(area.top, area.bottom + 1):
            for col in range(area.left, area.right + 1):
                if (row, col) not in allowed:
                    return cell_name(row, col)
    return None


def _formula(snap: Snapshot, args: Mapping) -> Verdict:
    _a, c = _cell(snap, args["cell"])
    if _empty(c):
        return Verdict.waiting()
    if c.formula is None or not is_formula(c.formula):
        what = "number" if _is_number(c.value) else "value"
        return Verdict.wrong("typed_value", f"Not yet: that's a typed {what}. Start with = instead.")
    formula = c.formula

    uses = args.get("uses")
    if uses and uses.upper() not in functions_of(formula):
        return Verdict.wrong(f"uses_missing:{uses.upper()}", f"Not yet: use {uses.upper()} here.")

    areas = _ref_areas(formula)
    covers = parse_area(args["covers"]) if args.get("covers") else None
    fixed = [_plain_cell(a) for a in args.get("absolute") or ()]
    required = (covers.positions() if covers else []) + [(parse_area(a).top, parse_area(a).left) for a in fixed]
    for row, col in required:
        if not any(area.contains(row, col) for area in areas):
            missing = cell_name(row, col)
            return Verdict.wrong(f"covers_missing:{missing}", f"Not yet: your formula skips {missing}.")

    if covers is not None:
        extra = _first_outside(areas, set(required))
        if extra:
            return Verdict.wrong(f"refers_extra:{extra}", f"Not yet: your formula also uses {extra}. Leave it out.")

    locked = set(absolute_refs_of(formula))
    for a in fixed:
        if a not in locked:
            lock = f"${a.rstrip('0123456789')}${parse_area(a).top}"
            return Verdict.wrong(f"not_absolute:{a}", f"Not yet: lock {a} as {lock} so it stays put.")

    want = args.get("value")
    if want is not None and not _same(c.value, want, 1e-6):
        shown = _show(c.value)
        return Verdict.wrong(f"value:{shown}", f"Not yet: that gives {shown}. Check the cells it uses.")
    return Verdict.right()


# ------------------------------------------------------------------ filled_formula

def _filled_formula(snap: Snapshot, args: Mapping) -> Verdict:
    area = parse_area(args["range"])
    cells = _cells(snap, args["range"])
    if all(_empty(c) for _a, c in cells[1:]):
        return Verdict.waiting()
    way = "across" if area.top == area.bottom and area.left != area.right else "down"
    for (a, c), (row, col) in zip(cells, area.positions()):
        if _empty(c):
            return Verdict.wrong(f"gap:{area.last}", f"Not yet: fill all the way {way} to {area.last}.")
        want = plain(moved(args["first"], row - area.top, col - area.left))
        if c.formula is None or plain(c.formula) != want:
            return Verdict.wrong(f"differs:{a}", f"Not yet: {a} has a different formula.")
    return Verdict.right()


# ------------------------------------------------------------------ number_format

_LOCALE = re.compile(r"\[\$-[^\]]*\]")           # [$-en-IN], [$-409]: language only, no symbol
_QUOTED = re.compile(r'"[^"]*"')
_BRACKETS = re.compile(r"\[[^\]]*\]")             # [Red], [h], [$₹-4009]
_ESCAPED = re.compile(r"\\.|_.|\*.")              # \x shows x; _x pads by x's width; *x repeats x
_CURRENCY = re.compile(r"[₹$€£¥]|\[\$")


def format_kind(number_format: str) -> str:
    """The kind of a number format: currency, percent, date, decimal2, whole, general or other."""
    text = (number_format or GENERAL).split(";")[0]
    if text.strip().casefold() in ("general", ""):
        return "general"
    text = _LOCALE.sub("", text)
    bare = _ESCAPED.sub("", _BRACKETS.sub("", _QUOTED.sub("", text)))
    if _CURRENCY.search(text):                   # quoted ("₹"), escaped (\$) or bracketed ([$₹-4009])
        return "currency"
    if "%" in bare:
        return "percent"
    if re.search(r"[dmyhs]", bare, re.IGNORECASE):
        return "date"
    if re.search(r"E[+-]", bare, re.IGNORECASE) or "/" in bare or "@" in bare:
        return "other"
    decimals = re.search(r"\.([0#?]*)", bare)
    if decimals:
        return "decimal2" if len(decimals.group(1)) == 2 else "other"
    return "whole" if re.search(r"[0#?]", bare) else "other"


def _number_format(snap: Snapshot, args: Mapping) -> Verdict:
    want = args["kind"]
    judged = _filled_or_all(_cells(snap, args["range"]))
    kinds = [(a, format_kind(c.number_format)) for a, c in judged]
    if all(k == "general" for _a, k in kinds):
        return Verdict.waiting()
    wrong = [(a, k) for a, k in kinds if k != want]
    if not wrong:
        return Verdict.right()
    if len(wrong) < len(kinds):
        a = wrong[0][0]
        return Verdict.wrong(f"partial:{a}", f"Not yet: {a} needs {_FORMAT_NAMES[want]} too.")
    have = next(k for _a, k in kinds if k != "general")
    return Verdict.wrong(f"kind:{have}",
                         f"Not yet: that's {_FORMAT_NAMES[have]}. Pick {_FORMAT_NAMES[want]} instead.")


# ------------------------------------------------------------------ bold

def _bold(snap: Snapshot, args: Mapping) -> Verdict:
    judged = _filled_or_all(_cells(snap, args["range"]))
    if not any(c.bold for _a, c in judged):
        return Verdict.waiting()
    for a, c in judged:
        if not c.bold:
            return Verdict.wrong(f"partial:{a}", f"Not yet: {a} needs bold too.")
    return Verdict.right()


# ------------------------------------------------------------------ chart

def _family(chart_type: int) -> str:
    return next((name for name, numbers in CHART_FAMILIES.items() if chart_type in numbers), "other")


def _split_args(text: str) -> list[str]:
    """Split at top-level commas, keeping quoted text and brackets together."""
    out, depth, quoted, start = [], 0, False, 0
    for i, ch in enumerate(text):
        if ch == "'" or ch == '"':
            quoted = not quoted
        elif not quoted and ch == "(":
            depth += 1
        elif not quoted and ch == ")":
            depth -= 1
        elif not quoted and depth == 0 and ch == ",":
            out.append(text[start:i])
            start = i + 1
    out.append(text[start:])
    return [part.strip() for part in out]


def _series_values(series: str) -> list[Area]:
    """The cells a =SERIES(name, categories, values, order) formula plots."""
    m = re.match(r"^\s*=\s*SERIES\s*\((.*)\)\s*$", series, re.IGNORECASE | re.DOTALL)
    if not m:
        return []
    parts = _split_args(m.group(1))
    if len(parts) < 3:
        return []
    values = parts[2].strip()
    if values.startswith("(") and values.endswith(")"):
        values = values[1:-1]
    areas = []
    for ref in _split_args(values):
        try:
            areas.append(parse_area(ref))
        except ValueError:
            pass                                  # a typed list of numbers, not cells
    return areas


def _same_sheet(a: str | None, b: str) -> bool:
    return a is None or a.casefold() == b.casefold()


def _plots_over(chart: Chart, over: Area, sheet: str) -> bool:
    """The chart's values hold every cell of `over` and nothing else but its header row or column."""
    areas = [a for s in chart.series for a in _series_values(s)]
    if not areas or not all(_same_sheet(a.sheet, sheet) for a in areas):
        return False
    with_header_row = Area(None, max(1, over.top - 1), over.left, over.bottom, over.right)
    with_header_col = Area(None, over.top, max(1, over.left - 1), over.bottom, over.right)
    inside = all(_within(a, with_header_row) or _within(a, with_header_col) for a in areas)
    covered = all(any(a.contains(r, c) for a in areas) for r, c in over.positions())
    return inside and covered


def _within(a: Area, outer: Area) -> bool:
    return outer.top <= a.top and a.bottom <= outer.bottom and outer.left <= a.left and a.right <= outer.right


def _chart(snap: Snapshot, args: Mapping) -> Verdict:
    charts = [c for s in snap.sheets for c in s.charts]
    if not charts:
        return Verdict.waiting()
    want = args["chart_type"]
    over = parse_area(args["over"]) if args.get("over") else None
    sheet = over.sheet_or(snap.active_sheet) if over else snap.active_sheet
    title = args.get("title")

    def problem(c: Chart) -> Verdict | None:
        if _family(c.chart_type) != want:
            have = _family(c.chart_type)
            shown = f"a {have} chart" if have != "other" else "a different kind of chart"
            return Verdict.wrong(f"type:{have}", f"Not yet: that's {shown}. Pick the {want}.")
        if over is not None and not _plots_over(c, over, sheet):
            return Verdict.wrong("over", "Not yet: the chart uses other cells.")
        if title and (c.title or "").strip().casefold() != title.strip().casefold():
            return Verdict.wrong("title", f"Not yet: give the chart the title {title}.")
        return None

    problems = [problem(c) for c in charts]
    if any(p is None for p in problems):
        return Verdict.right()
    of_right_type = [p for p, c in zip(problems, charts) if _family(c.chart_type) == want]
    return (of_right_type or problems)[0]


# ------------------------------------------------------------------ frozen

def _rows_and_cols(rows: int, cols: int) -> str:
    def part(n: int, one: str, many: str) -> str:
        return one if n == 1 else many.format(n=n)
    bits = []
    if rows:
        bits.append(part(rows, "the top row", "the top {n} rows"))
    if cols:
        bits.append(part(cols, "the first column", "the first {n} columns"))
    return " and ".join(bits) or "nothing"


def _frozen(snap: Snapshot, args: Mapping) -> Verdict:
    want_rows, want_cols = args["rows"], args["cols"]
    rows, cols = snap.frozen_rows, snap.frozen_cols
    if (rows, cols) == (want_rows, want_cols):
        return Verdict.right()
    if (rows, cols) == (0, 0):
        return Verdict.waiting()
    what = _rows_and_cols(want_rows, want_cols)
    if (want_rows, want_cols) == (0, 0):
        text = "Not yet: unfreeze the panes."
    elif rows >= want_rows and cols >= want_cols:
        text = f"Not yet: freeze only {what}."
    else:
        text = f"Not yet: freeze {what} instead."
    return Verdict.wrong(f"frozen:{rows},{cols}", text)


# ------------------------------------------------------------------ filter

def _criteria(text: str) -> str:
    t = (text or "").strip().casefold()
    return t[1:].strip() if t.startswith("=") else t


def _filter(snap: Snapshot, args: Mapping) -> Verdict:
    want = parse_area(args["range"])
    sheet = _sheet_of(snap, want)
    if sheet is None or sheet.filter is None:
        return Verdict.waiting()
    have = parse_area(sheet.filter.range)
    if _box(have) != _box(want):
        return Verdict.wrong("range", f"Not yet: the filter covers {have.a1}. Put it on {want.a1}.")
    column = args.get("column")
    if column:
        index = col_index(column) - have.left + 1
        if index not in sheet.filter.on:
            return Verdict.wrong("column", f"Not yet: filter the {column.upper()} column.")
        criteria = args.get("criteria")
        if criteria and _criteria(sheet.filter.on[index]) != _criteria(criteria):
            return Verdict.wrong("criteria", f"Not yet: filter column {column.upper()} to {criteria.lstrip('=')}.")
    return Verdict.right()


# ------------------------------------------------------------------ sorted

def _sort_key(v: Any) -> tuple:
    if _is_number(v):
        return (0, float(v))
    if isinstance(v, bool):
        return (2, v)
    return (1, str(v).casefold())


def _order_of(values: list) -> str | None:
    """"asc", "desc", or None when not in order (or too few different values to tell)."""
    keys = [_sort_key(v) for v in values]
    if len(set(keys)) < 2:
        return None
    if all(a <= b for a, b in zip(keys, keys[1:])):
        return "asc"
    if all(a >= b for a, b in zip(keys, keys[1:])):
        return "desc"
    return None


def _sorted(snap: Snapshot, args: Mapping) -> Verdict:
    area = parse_area(args["range"])
    sheet = area.sheet_or(snap.active_sheet)
    want_col, want = col_index(args["column"]), args["order"]

    def column_values(col: int) -> list:
        cells = [snap.cell(sheet, cell_name(r, col)) for r in range(area.top, area.bottom + 1)]
        return [c.value for c in cells if not _empty(c)]

    have = _order_of(column_values(want_col))
    if have == want:
        return Verdict.right()
    if have is not None:
        now = "smallest first" if have == "asc" else "largest first"
        return Verdict.wrong("order", f"Not yet: that's {now}. Flip it.")
    for col in range(area.left, area.right + 1):
        if col != want_col and _order_of(column_values(col)) is not None:
            other = col_letters(col)
            return Verdict.wrong(f"column:{other}",
                                 f"Not yet: that's sorted by column {other}. Sort by {args['column'].upper()}.")
    return Verdict.waiting()


# ------------------------------------------------------------------ selected

def _selected(snap: Snapshot, args: Mapping) -> Verdict:
    want = parse_area(args["range"])
    if not _same_sheet(want.sheet, snap.active_sheet):
        return Verdict.waiting()
    try:
        have = [parse_area(part) for part in snap.selection.split(",") if part.strip()]
    except ValueError:
        return Verdict.waiting()
    if len(have) == 1 and _box(have[0]) == _box(want):
        return Verdict.right()
    overlaps = any(a.top <= want.bottom and want.top <= a.bottom and a.left <= want.right
                   and want.left <= a.right for a in have)
    if not overlaps:
        return Verdict.waiting()
    shown = ",".join(a.a1 for a in have)
    return Verdict.wrong(f"selected:{shown}", f"Not yet: that's {shown}, try {want.a1}.")


# ------------------------------------------------------------------ sheet_named

def _distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _sheet_named(snap: Snapshot, args: Mapping) -> Verdict:
    want = args["name"].strip().casefold()
    names = [s.name for s in snap.sheets]
    found = [i for i, n in enumerate(names, 1) if n.strip().casefold() == want]
    index = args.get("index")
    if found:
        if index is None or index in found:
            return Verdict.right()
        return Verdict.wrong("index", f"Not yet: move {args['name']} to be sheet number {index}.")
    near = [n for n in names if _distance(n.strip().casefold(), want) <= 2]
    if near:
        return Verdict.wrong(f"name:{near[0]}", f"Not yet: that's {near[0]}. Name it {args['name']}.")
    return Verdict.waiting()


# ------------------------------------------------------------------ the menu

def _kind(name: str, params: tuple[Param, ...], run: Callable[[Snapshot, Mapping], Verdict],
          summary: str) -> tuple[str, CheckKind]:
    return name, CheckKind(name, params, run, summary)


CHECKS: dict[str, CheckKind] = dict([
    _kind("value_equals", (Param("cell", "cell"), Param("value", "value")), _value_equals,
          "The cell shows this value (text ignores case and outer spaces)."),
    _kind("formula", (Param("cell", "cell"), Param("value", "value", required=False),
                      Param("covers", "range", required=False), Param("uses", "function", required=False),
                      Param("absolute", "cells", required=False)), _formula,
          "The cell holds a formula that refers to every cell of `covers` and nothing else, calls `uses`, "
          "locks each `absolute` cell as $C$R, and gives `value`. Any spelling of it counts."),
    _kind("filled_formula", (Param("range", "range"), Param("first", "text")), _filled_formula,
          "The formula `first` (written for the range's first cell) is filled through the whole range."),
    _kind("number_format", (Param("range", "range"), Param("kind", "enum", choices=NUMBER_FORMAT_KINDS)),
          _number_format, "The filled cells of the range show numbers in this format."),
    _kind("bold", (Param("range", "range"),), _bold, "The filled cells of the range are bold."),
    _kind("chart", (Param("chart_type", "enum", choices=CHART_TYPES), Param("over", "range", required=False),
                    Param("title", "text", required=False)), _chart,
          "A chart of this type plots the cells `over` (their header may be included), with this title."),
    _kind("frozen", (Param("rows", "int"), Param("cols", "int")), _frozen,
          "Exactly this many top rows and left columns are frozen on the active sheet."),
    _kind("filter", (Param("range", "range"), Param("column", "text", required=False),
                     Param("criteria", "text", required=False)), _filter,
          "A filter is on the range, filtering column `column` (a letter) by `criteria`."),
    _kind("sorted", (Param("range", "range"), Param("column", "text"),
                     Param("order", "enum", choices=("asc", "desc"))), _sorted,
          "The range's rows are in this order by column `column` (a letter)."),
    _kind("selected", (Param("range", "range"),), _selected, "Exactly this range is selected."),
    _kind("sheet_named", (Param("name", "text"), Param("index", "int", required=False)), _sheet_named,
          "A sheet has this name (at this position, counting from 1, if given)."),
])
