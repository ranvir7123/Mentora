"""The Excel operation menu: what the program itself can do in the workbook.

Operations replay a step (or a known mistake) so the checks can be proved on real Excel before a
learner ever sees the lesson, and they drive the end-to-end tester. A learner's own clicks never
go through here.

do() runs on the COM thread. It finds each sheet by name and never activates one, except `select`,
which has to show its own sheet to select on it.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from app.core.types import Call, OpKind, Param
from app.excel.address import Area, col_index, parse_area
from app.excel.busy import ExcelBusy
from app.excel.checks import CHART_TYPES, NUMBER_FORMAT_KINDS

__all__ = ["OPS", "do", "ExcelBusy", "NUMBER_FORMATS", "CHART_TYPE_NUMBERS"]

NUMBER_FORMATS = {"currency": '"₹"#,##0', "percent": "0%", "date": "dd-mmm-yyyy", "decimal2": "0.00",
                  "whole": "0"}
CHART_TYPE_NUMBERS = {"column": 51, "bar": 57, "line": 4, "pie": 5}   # Excel's XlChartType
CHART_WIDTH_PT, CHART_HEIGHT_PT, CHART_GAP_PT = 360, 216, 12
XL_ASCENDING, XL_DESCENDING = 1, 2
XL_YES, XL_NO = 1, 2                                   # does the sort range have a header row


def _sheet(wb, area: Area):
    return wb.Worksheets(area.sheet) if area.sheet else wb.ActiveSheet


def _at(wb, address: str):
    """(sheet, range, area) for an address, found without activating anything."""
    area = parse_area(address)
    sheet = _sheet(wb, area)
    return sheet, sheet.Range(area.a1), area


def _set_value(app, wb, a: Mapping) -> None:
    _at(wb, a["cell"])[1].Value2 = a["value"]


def _set_formula(app, wb, a: Mapping) -> None:
    _at(wb, a["cell"])[1].Formula = a["formula"]


def _fill_down(app, wb, a: Mapping) -> None:
    sheet, target, area = _at(wb, a["range"])
    source = parse_area(a["source"])
    if (source.top, source.left) == (area.top, area.left):
        if area.left == area.right:
            target.FillDown()
            return
        if area.top == area.bottom:
            target.FillRight()
            return
    sheet.Range(source.a1).Copy(target)


def _set_format(app, wb, a: Mapping) -> None:
    _at(wb, a["range"])[1].NumberFormat = NUMBER_FORMATS[a["kind"]]


def _set_bold(app, wb, a: Mapping) -> None:
    _at(wb, a["range"])[1].Font.Bold = a.get("on", True)


def _add_chart(app, wb, a: Mapping) -> None:
    sheet, source, _area = _at(wb, a["source"])
    used = sheet.UsedRange
    left = used.Left + used.Width + CHART_GAP_PT          # beside the data, never on top of it
    shape = sheet.Shapes.AddChart2(-1, CHART_TYPE_NUMBERS[a["chart_type"]], left, used.Top,
                                   CHART_WIDTH_PT, CHART_HEIGHT_PT)
    chart = shape.Chart
    chart.SetSourceData(source)
    if a.get("title"):
        chart.HasTitle = True
        chart.ChartTitle.Text = a["title"]


def _freeze(app, wb, a: Mapping) -> None:
    # Freezing keeps the rows above and columns left of the split, counted from the top-left cell
    # on screen, so scroll home first. It acts on the window's own sheet: nothing is activated.
    window = wb.Windows(1)
    window.FreezePanes = False
    window.SplitRow = 0
    window.SplitColumn = 0
    if a["rows"] or a["cols"]:
        window.ScrollRow = 1
        window.ScrollColumn = 1
        window.SplitRow = a["rows"]
        window.SplitColumn = a["cols"]
        window.FreezePanes = True


def _filter(app, wb, a: Mapping) -> None:
    sheet, target, area = _at(wb, a["range"])
    if a.get("column"):
        target.AutoFilter(col_index(a["column"]) - area.left + 1, a.get("criteria") or "*")
    elif not sheet.AutoFilterMode:                   # AutoFilter() with nothing else switches it off
        target.AutoFilter()


def _sort(app, wb, a: Mapping) -> None:
    sheet, target, area = _at(wb, a["range"])
    key = sheet.Range(f"{a['column'].upper()}{area.top}")
    target.Sort(Key1=key, Order1=XL_ASCENDING if a["order"] == "asc" else XL_DESCENDING,
                Header=XL_YES if a["header"] else XL_NO)


def _rename_sheet(app, wb, a: Mapping) -> None:
    wb.Worksheets(a["old"]).Name = a["new"]


def _select(app, wb, a: Mapping) -> None:
    sheet, target, _area = _at(wb, a["range"])
    sheet.Activate()
    target.Select()


def _clear(app, wb, a: Mapping) -> None:
    _at(wb, a["range"])[1].ClearContents()           # like the Delete key: formats stay


_DO: dict[str, Callable[[Any, Any, Mapping], None]] = {
    "set_value": _set_value, "set_formula": _set_formula, "fill_down": _fill_down,
    "set_format": _set_format, "set_bold": _set_bold, "add_chart": _add_chart, "freeze": _freeze,
    "filter": _filter, "sort": _sort, "rename_sheet": _rename_sheet, "select": _select, "clear": _clear,
}


def do(app, wb, op: Call) -> None:
    """Carry out one operation on the COM thread; Excel's own refusal is raised as it is."""
    fn = _DO.get(op.kind)
    if fn is None:
        raise ValueError(f"there is no Excel operation called {op.kind!r}")
    fn(app, wb, op.args)


def _op(name: str, params: tuple[Param, ...], summary: str) -> tuple[str, OpKind]:
    return name, OpKind(name, params, summary)


OPS: dict[str, OpKind] = dict([
    _op("set_value", (Param("cell", "cell"), Param("value", "value")), "Type a value into the cell."),
    _op("set_formula", (Param("cell", "cell"), Param("formula", "text")), "Type a formula into the cell."),
    _op("fill_down", (Param("source", "cell"), Param("range", "range")),
        "Fill the source cell's formula through the range (down, across, or copied)."),
    _op("set_format", (Param("range", "range"), Param("kind", "enum", choices=NUMBER_FORMAT_KINDS)),
        "Give the range a number format."),
    _op("set_bold", (Param("range", "range"), Param("on", "bool", required=False)),
        "Make the range bold (or not bold, with on: false)."),
    _op("add_chart", (Param("chart_type", "enum", choices=CHART_TYPES), Param("source", "range"),
                      Param("title", "text", required=False)), "Insert a chart of the source cells."),
    _op("freeze", (Param("rows", "int"), Param("cols", "int")),
        "Freeze this many top rows and left columns (0 and 0 unfreezes)."),
    _op("filter", (Param("range", "range"), Param("column", "text", required=False),
                   Param("criteria", "text", required=False)),
        "Put a filter on the range, filtering one column (a letter) by the criteria."),
    _op("sort", (Param("range", "range"), Param("column", "text"),
                 Param("order", "enum", choices=("asc", "desc")), Param("header", "bool")),
        "Sort the range's rows by one column (a letter); header says whether its first row is headings."),
    _op("rename_sheet", (Param("old", "text"), Param("new", "text")), "Rename a sheet."),
    _op("select", (Param("range", "range"),), "Select the range (showing its sheet)."),
    _op("clear", (Param("range", "range"),), "Empty the range, like pressing Delete."),
])
