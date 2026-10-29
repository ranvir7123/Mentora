"""Every check: three right ways, three wrong ways (each naming its one difference), and the
untouched budget starter, which must always be "waiting" so no "Not yet" is said before the
learner has done anything."""
import pytest

from app.excel.checks import CHECKS, format_kind
from app.excel.formula import moved, plain, row_locked_refs_of
from app.excel.snapshot import Cell, Chart, Filter, Sheet, Snapshot

STARTER = {"A1": "Item", "B1": "Amount", "C1": "Share", "A2": "Rent", "B2": 12000.0, "A3": "Food",
           "B3": 6000.0, "A4": "Travel", "B4": 2500.0, "A5": "Phone", "B5": 500.0, "A6": "Fun",
           "B6": 2000.0, "A8": "Total"}
TOTAL = 23000.0


def snap(changes=None, *, base=STARTER, charts=(), filter=None, selection="A1", frozen=(0, 0),
         more_sheets=(), active="Budget") -> Snapshot:
    cells = {a: Cell(value=v) for a, v in base.items()}
    for a, c in (changes or {}).items():
        if c is None:
            cells.pop(a, None)
        else:
            cells[a] = c if isinstance(c, Cell) else Cell(value=c)
    budget = Sheet("Budget", cells, tuple(charts), filter)
    return Snapshot((budget, *more_sheets), active, selection, frozen[0], frozen[1])


def f(formula: str, value) -> Cell:
    return Cell(value=value, formula=formula)


def fmt(fmt_text: str, value=1.0, **kw) -> Cell:
    return Cell(value=value, number_format=fmt_text, **kw)


def run(kind: str, args: dict, s: Snapshot):
    return CHECKS[kind].run(s, args)


def assert_right(kind, args, s):
    v = run(kind, args, s)
    assert v.ok and v.attempted, v


def assert_wrong(kind, args, s, code):
    v = run(kind, args, s)
    assert (v.ok, v.attempted, v.code) == (False, True, code), v
    assert v.text.startswith("Not yet: "), v.text


def assert_waiting(kind, args, s):
    v = run(kind, args, s)
    assert (v.ok, v.attempted) == (False, False), v


def test_the_menu_has_every_kind_in_order():
    assert list(CHECKS) == ["value_equals", "formula", "filled_formula", "number_format", "bold",
                            "chart", "frozen", "filter", "sorted", "selected", "sheet_named"]
    for name, kind in CHECKS.items():
        assert kind.name == name and kind.summary


# ------------------------------------------------------------------ value_equals

VALUE_ARGS = {"cell": "Budget!A8", "value": "Total spent"}


@pytest.mark.parametrize("typed", ["Total spent", "  total SPENT ", "TOTAL SPENT"])
def test_value_equals_right(typed):
    assert_right("value_equals", VALUE_ARGS, snap({"A8": typed}))


def test_value_equals_numbers():
    args = {"cell": "B7", "value": 0.1}
    assert_right("value_equals", args, snap({"B7": 0.1 + 1e-12}))
    assert_wrong("value_equals", args, snap({"B7": 0.2}), "differs")
    assert_wrong("value_equals", args, snap({"B7": "0.1"}), "as_text")


@pytest.mark.parametrize("typed", ["Total", "Totl spent", "Spent"])
def test_value_equals_wrong(typed):
    assert_wrong("value_equals", VALUE_ARGS, snap({"A8": typed}), "differs")
    assert typed in run("value_equals", VALUE_ARGS, snap({"A8": typed})).text


def test_value_equals_waits_for_an_empty_cell():
    assert_waiting("value_equals", {"cell": "B7", "value": 5}, snap())


# ------------------------------------------------------------------ formula: the total

TOTAL_ARGS = {"cell": "Budget!B8", "value": 23000, "covers": "Budget!B2:B6"}


@pytest.mark.parametrize("formula", ["=SUM(B2:B6)", "=B2+B3+B4+B5+B6", "=SUM(B2:B4)+SUM(B5:B6)"])
def test_total_right(formula):
    assert_right("formula", TOTAL_ARGS, snap({"B8": f(formula, TOTAL)}))


@pytest.mark.parametrize("cell, code", [
    (f("=SUM(B2:B5)", 21000.0), "covers_missing:B6"),
    (Cell(value=TOTAL), "typed_value"),
    (f("=SUM(B3:B7)", 11000.0), "covers_missing:B2"),
])
def test_total_wrong(cell, code):
    assert_wrong("formula", TOTAL_ARGS, snap({"B8": cell}), code)


def test_total_more_wrong_ways():
    assert_wrong("formula", TOTAL_ARGS, snap({"B8": f("=SUM(B1:B6)", TOTAL)}), "refers_extra:B1")
    assert_wrong("formula", {**TOTAL_ARGS, "uses": "SUM"}, snap({"B8": f("=B2+B3+B4+B5+B6", TOTAL)}),
                 "uses_missing:SUM")
    assert_wrong("formula", {"cell": "B8", "value": 23000}, snap({"B8": f("=B2*2", 24000.0)}), "value:24,000")
    assert_wrong("formula", TOTAL_ARGS, snap({"B8": f("=SUM(B2:B6)", "#NAME?")}), "value:#NAME?")


def test_formula_waits_for_an_empty_cell():
    assert_waiting("formula", TOTAL_ARGS, snap())


def test_a_huge_range_is_judged_without_listing_its_cells():
    assert_wrong("formula", TOTAL_ARGS, snap({"B8": f("=SUM(B2:XFD1048576)", TOTAL)}), "refers_extra:C2")


# ------------------------------------------------------------------ formula: the share

SHARE_ARGS = {"cell": "Budget!C2", "value": 0.52173913, "covers": "Budget!B2", "absolute": ["Budget!B8"]}
SHARE = 12000 / 23000


# B$8 locks the row, which is all that filling down needs, so it counts as locked (as filled_formula
# already accepts). $B8 locks only the column: filled down it becomes $B9, $B10...
@pytest.mark.parametrize("formula", ["=B2/$B$8", "=B2/B$8", "=$B2/$B$8", "=b2 / $b$8"])
def test_share_right(formula):
    assert_right("formula", SHARE_ARGS, snap({"B8": f("=SUM(B2:B6)", TOTAL), "C2": f(formula, SHARE)}))


@pytest.mark.parametrize("formula, value, code", [
    ("=B2/$B8", SHARE, "not_absolute:B8"),
    ("=B2/B8", SHARE, "not_absolute:B8"),
    ("=B2/$B$9", "#DIV/0!", "covers_missing:B8"),
])
def test_share_wrong(formula, value, code):
    assert_wrong("formula", SHARE_ARGS, snap({"B8": f("=SUM(B2:B6)", TOTAL), "C2": f(formula, value)}), code)


def test_not_absolute_names_the_lock():
    v = run("formula", SHARE_ARGS, snap({"C2": f("=B2/B8", SHARE)}))
    assert v.text == "Not yet: lock B8 as $B$8 so it stays put."


# ------------------------------------------------------------------ filled_formula

FILL_ARGS = {"range": "Budget!C2:C6", "first": "=B2/$B$8"}


def filled(fmt_first="=B{r}/$B$8", rows=range(2, 7)) -> dict:
    return {f"C{r}": f(fmt_first.format(r=r), 0.1) for r in rows}


@pytest.mark.parametrize("pattern", ["=B{r}/$B$8", "=B{r}/B$8", "=b{r}/$B$8"])
def test_filled_formula_right(pattern):
    assert_right("filled_formula", FILL_ARGS, snap(filled(pattern)))


def test_filled_formula_wrong():
    assert_wrong("filled_formula", FILL_ARGS, snap(filled(rows=range(2, 5))), "gap:C6")
    assert "fill all the way down to C6" in run("filled_formula", FILL_ARGS, snap(filled(rows=range(2, 5)))).text
    relative = {f"C{r}": f(f"=B{r}/B{r + 6}", 0.1) for r in range(2, 7)}
    assert_wrong("filled_formula", FILL_ARGS, snap(relative), "differs:C3")
    typed = {**filled(), "C5": Cell(value=0.02)}
    assert_wrong("filled_formula", FILL_ARGS, snap(typed), "differs:C5")


def test_filled_formula_waits_until_something_below_the_first_is_filled():
    assert_waiting("filled_formula", FILL_ARGS, snap())
    assert_waiting("filled_formula", FILL_ARGS, snap(filled(rows=[2])))


def test_filling_across_says_across():
    args = {"range": "B9:E9", "first": "=B2*2"}
    v = run("filled_formula", args, snap({"B9": f("=B2*2", 1), "C9": f("=C2*2", 1)}))
    assert v.code == "gap:E9" and "across to E9" in v.text


def test_row_locked_refs_are_the_ones_filling_down_keeps():
    assert row_locked_refs_of("=B2/B$8+$C$9+$D10+Budget!E$2:$E$4") == ["B8", "C9", "E2", "E4"]
    assert row_locked_refs_of('="$A$1"&B1') == [] and row_locked_refs_of("12") == []


def test_moved_and_plain():
    assert moved("=B2/$B$8+SUM(A$1:$C3)", 2, 1) == "=C4/$B$8+SUM(B$1:$C5)"
    assert moved('=IF(A1>0,"B2",LOG10(A1))', 1, 0) == '=IF(A2>0,"B2",LOG10(A2))'
    assert moved("=Budget!B2", 1, 0) == "=Budget!B3"
    assert moved("=A1", -1, 0) == "=#REF!"
    assert plain('= sum( $b$2 : B6 ) & "a B"') == '=SUM(B2:B6)&"a B"'


# ------------------------------------------------------------------ number_format

def formatted(fmt_text: str, cells=("B2", "B3", "B4", "B5", "B6")) -> dict:
    return {a: fmt(fmt_text, STARTER[a]) for a in cells}


RUPEE_ARGS = {"range": "Budget!B2:B8", "kind": "currency"}


@pytest.mark.parametrize("fmt_text", ['"₹"#,##0', "[$₹-4009] #,##0.00", '_("$"* #,##0.00_)'])
def test_currency_right(fmt_text):
    total = {"B8": Cell(value=TOTAL, formula="=SUM(B2:B6)", number_format=fmt_text)}
    assert_right("number_format", RUPEE_ARGS, snap({**formatted(fmt_text), **total}))


def test_currency_wrong():
    total = {"B8": Cell(value=TOTAL, formula="=SUM(B2:B6)", number_format="0%")}
    assert_wrong("number_format", RUPEE_ARGS, snap({**formatted("0%"), **total}), "kind:percent")
    assert run("number_format", RUPEE_ARGS, snap(formatted("0%"))).text == \
        "Not yet: that's percent. Pick currency instead."
    assert_wrong("number_format", RUPEE_ARGS, snap(formatted('"₹"#,##0', ["B2", "B3"])), "partial:B4")
    assert_wrong("number_format", RUPEE_ARGS, snap(formatted("[$-en-IN]#,##0.00")), "kind:decimal2")


def test_number_format_waits_while_everything_is_general():
    assert_waiting("number_format", RUPEE_ARGS, snap())
    assert_waiting("number_format", {"range": "C2:C6", "kind": "percent"}, snap())


@pytest.mark.parametrize("fmt_text, kind", [
    ("General", "general"), ("0%", "percent"), ("0.00%", "percent"), ('"₹"#,##0', "currency"),
    ("[$€-x-euro2] #,##0.00", "currency"), ("£#,##0", "currency"), ("dd-mmm-yyyy", "date"),
    ("[$-en-IN]d/m/yyyy", "date"), ("m/d/yy h:mm", "date"), ("0.00", "decimal2"),
    ("#,##0.00", "decimal2"), ("0", "whole"), ("#,##0", "whole"), ("@", "other"),
    ('0.00" kg"', "decimal2"), ('"Day "0', "whole"), ("\\$#,##0.00", "currency"),
    ("#,##0;[Red]-#,##0", "whole"), ("0.00E+00", "other"),
])
def test_format_kinds(fmt_text, kind):
    assert format_kind(fmt_text) == kind


# ------------------------------------------------------------------ bold

BOLD_ARGS = {"range": "Budget!A1:C1"}


def bolded(*cells) -> dict:
    return {a: Cell(value=STARTER[a], bold=True) for a in cells}


def test_bold_right():
    assert_right("bold", BOLD_ARGS, snap(bolded("A1", "B1", "C1")))
    assert_right("bold", {"range": "A1:D1"}, snap(bolded("A1", "B1", "C1")))   # D1 is empty
    assert_right("bold", {"range": "C1"}, snap(bolded("C1")))


def test_bold_wrong():
    assert_wrong("bold", BOLD_ARGS, snap(bolded("A1", "B1")), "partial:C1")
    assert run("bold", BOLD_ARGS, snap(bolded("A1", "B1"))).text == "Not yet: C1 needs bold too."
    assert_wrong("bold", BOLD_ARGS, snap(bolded("B1")), "partial:A1")
    assert_wrong("bold", BOLD_ARGS, snap(bolded("C1")), "partial:A1")


def test_bold_waits_while_nothing_is_bold():
    assert_waiting("bold", BOLD_ARGS, snap())


# ------------------------------------------------------------------ chart

PIE_ARGS = {"chart_type": "pie", "over": "Budget!B2:B6"}


def chart(chart_type: int, values="Budget!$B$2:$B$6", title=None, extra=()) -> Chart:
    series = [f"=SERIES(Budget!$B$1,Budget!$A$2:$A$6,{values},1)", *extra]
    return Chart("Chart 1", chart_type, title, tuple(series))


@pytest.mark.parametrize("c", [chart(5), chart(-4102, "Budget!$B$1:$B$6"), chart(69, "'Budget'!$B$2:$B$6")])
def test_pie_right(c):
    assert_right("chart", PIE_ARGS, snap(charts=[c]))


def test_pie_wrong():
    assert_wrong("chart", PIE_ARGS, snap(charts=[chart(51)]), "type:column")
    assert run("chart", PIE_ARGS, snap(charts=[chart(51)])).text == \
        "Not yet: that's a column chart. Pick the pie."
    assert_wrong("chart", PIE_ARGS, snap(charts=[chart(5, "Budget!$B$2:$B$4")]), "over")
    assert_wrong("chart", PIE_ARGS, snap(charts=[chart(5, "Budget!$B$2:$C$6")]), "over")


def test_chart_title_and_any_matching_chart():
    args = {"chart_type": "line", "title": "Spending"}
    assert_right("chart", args, snap(charts=[chart(51), chart(4, title=" spending ")]))
    assert_wrong("chart", args, snap(charts=[chart(65, title="Chart Title")]), "title")


def test_a_union_of_cells_in_a_series_is_read():
    assert_right("chart", PIE_ARGS, snap(charts=[chart(5, "(Budget!$B$2:$B$4,Budget!$B$5:$B$6)")]))


def test_chart_waits_while_there_is_none():
    assert_waiting("chart", PIE_ARGS, snap())


# ------------------------------------------------------------------ frozen

def test_frozen_right_and_wrong():
    args = {"rows": 1, "cols": 0}
    assert_right("frozen", args, snap(frozen=(1, 0)))
    assert_right("frozen", {"rows": 2, "cols": 1}, snap(frozen=(2, 1)))
    assert_right("frozen", {"rows": 0, "cols": 1}, snap(frozen=(0, 1)))
    assert_wrong("frozen", args, snap(frozen=(1, 1)), "frozen:1,1")
    assert run("frozen", args, snap(frozen=(1, 1))).text == "Not yet: freeze only the top row."
    assert run("frozen", args, snap(frozen=(0, 1))).text == "Not yet: freeze the top row instead."
    assert run("frozen", {"rows": 2, "cols": 0}, snap(frozen=(1, 0))).text == \
        "Not yet: freeze the top 2 rows instead."


def test_frozen_waits_while_nothing_is_frozen():
    assert_waiting("frozen", {"rows": 1, "cols": 0}, snap())


# ------------------------------------------------------------------ filter

FILTER_ARGS = {"range": "A1:C6", "column": "A", "criteria": "=Food"}


def test_filter_right():
    assert_right("filter", FILTER_ARGS, snap(filter=Filter("A1:C6", {1: "=Food"})))
    assert_right("filter", FILTER_ARGS, snap(filter=Filter("$A$1:$C$6", {1: " =food"})))
    assert_right("filter", {"range": "A1:C6"}, snap(filter=Filter("A1:C6")))


def test_filter_wrong():
    assert_wrong("filter", FILTER_ARGS, snap(filter=Filter("A1:B6", {1: "=Food"})), "range")
    assert_wrong("filter", FILTER_ARGS, snap(filter=Filter("A1:C6", {2: ">1000"})), "column")
    assert_wrong("filter", FILTER_ARGS, snap(filter=Filter("A1:C6", {1: "=Rent"})), "criteria")


def test_filter_waits_while_there_is_none():
    assert_waiting("filter", FILTER_ARGS, snap())


# ------------------------------------------------------------------ sorted

SORT_ARGS = {"range": "Budget!A2:C6", "column": "B", "order": "desc"}


def rows(*pairs) -> dict:
    out = {}
    for r, (item, amount) in enumerate(pairs, start=2):
        out[f"A{r}"], out[f"B{r}"] = item, amount
    return out


BY_AMOUNT = [("Rent", 12000.0), ("Food", 6000.0), ("Travel", 2500.0), ("Fun", 2000.0), ("Phone", 500.0)]


def test_sorted_right():
    assert_right("sorted", SORT_ARGS, snap(rows(*BY_AMOUNT)))
    assert_right("sorted", {**SORT_ARGS, "order": "asc"}, snap(rows(*reversed(BY_AMOUNT))))
    assert_right("sorted", {**SORT_ARGS, "column": "A", "order": "asc"},
                 snap(rows(*sorted(BY_AMOUNT, key=lambda p: p[0]))))


def test_sorted_wrong():
    assert_wrong("sorted", SORT_ARGS, snap(rows(*reversed(BY_AMOUNT))), "order")
    assert run("sorted", SORT_ARGS, snap(rows(*reversed(BY_AMOUNT)))).text == \
        "Not yet: that's smallest first. Flip it."
    assert_wrong("sorted", SORT_ARGS, snap(rows(*sorted(BY_AMOUNT, key=lambda p: p[0]))), "column:A")
    assert_wrong("sorted", SORT_ARGS, snap(rows(*sorted(BY_AMOUNT, key=lambda p: p[0], reverse=True))),
                 "column:A")


def test_sorted_waits_on_the_starting_order():
    assert_waiting("sorted", SORT_ARGS, snap())


# ------------------------------------------------------------------ selected

def test_selected():
    args = {"range": "Budget!B2:B6"}
    for sel in ("B2:B6", "$B$2:$B$6", "B6:B2"):
        assert_right("selected", args, snap(selection=sel))
    for sel, code in (("B2:B5", "selected:B2:B5"), ("A1:C6", "selected:A1:C6"), ("B6", "selected:B6")):
        assert_wrong("selected", args, snap(selection=sel), code)
    assert run("selected", args, snap(selection="B2:B5")).text == "Not yet: that's B2:B5, try B2:B6."
    assert_waiting("selected", args, snap(selection="A1"))


def test_selected_on_another_sheet_is_waiting():
    other = Sheet("Notes")
    assert_waiting("selected", {"range": "Budget!B2"}, snap(selection="B2", more_sheets=[other], active="Notes"))


# ------------------------------------------------------------------ sheet_named

def test_sheet_named():
    args = {"name": "Summary"}
    for names in (["Summary"], [" summary"], ["Notes", "SUMMARY"]):
        assert_right("sheet_named", args, snap(more_sheets=[Sheet(n) for n in names]))
    assert_right("sheet_named", {"name": "Budget", "index": 1}, snap(more_sheets=[Sheet("Summary")]))
    assert_wrong("sheet_named", {"name": "Summary", "index": 1}, snap(more_sheets=[Sheet("Summary")]), "index")
    assert_wrong("sheet_named", args, snap(more_sheets=[Sheet("Sumary")]), "name:Sumary")
    assert_wrong("sheet_named", args, snap(more_sheets=[Sheet("Summery")]), "name:Summery")
    assert_waiting("sheet_named", args, snap(more_sheets=[Sheet("Sheet1")]))


# ------------------------------------------------------------------ the untouched starter

@pytest.mark.parametrize("kind, args", [
    ("bold", BOLD_ARGS), ("formula", TOTAL_ARGS), ("number_format", RUPEE_ARGS), ("formula", SHARE_ARGS),
    ("filled_formula", FILL_ARGS), ("number_format", {"range": "Budget!C2:C6", "kind": "percent"}),
    ("chart", PIE_ARGS), ("frozen", {"rows": 1, "cols": 0}), ("sorted", SORT_ARGS),
])
def test_every_budget_step_waits_on_the_untouched_starter(kind, args):
    assert_waiting(kind, args, snap())
