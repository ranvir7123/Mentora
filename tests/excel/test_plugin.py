from pathlib import Path

from app.core.lesson import lesson_json_schema, load_lesson, validate
from app.core.types import Target
from app.excel import locate, plugin
from app.excel.checks import CHECKS
from app.excel.ops import OPS
from app.excel.plugin import ExcelPlugin

REFS = {"cell": "Budget!B8", "range": "Budget!A1:C1", "control": "Insert > Pie", "formula_bar": "",
        "name_box": "", "sheet_tab": "Budget"}


def test_budget_lesson_is_valid_for_excel():
    assert validate(load_lesson(Path("lessons/monthly-budget")), ExcelPlugin()) == []


def test_schema_offers_only_excel_menus():
    step = lesson_json_schema(ExcelPlugin())["properties"]["steps"]["items"]["properties"]
    assert sorted(step["check"]["properties"]["kind"]["enum"]) == sorted(CHECKS)
    assert sorted(step["replay"]["properties"]["kind"]["enum"]) == sorted(OPS)
    assert step["target"]["properties"]["kind"]["enum"] == sorted(REFS)


def test_every_target_kind_it_offers_can_be_pointed_at():
    p = ExcelPlugin()
    assert p.target_kinds == frozenset(REFS)
    for kind in sorted(p.target_kinds):
        assert locate.tracker_for(Target(kind, REFS[kind]), None, None, 1) is not None


def test_a_starter_that_is_not_a_workbook_is_named_as_a_problem():
    p = ExcelPlugin()
    assert p.validate_starter(load_lesson(Path("lessons/monthly-budget")).starter) == []
    assert p.validate_starter({"sheets": []}) != []


def test_open_hands_everything_to_an_excel_session(monkeypatch, tmp_path):
    made = []
    monkeypatch.setattr(plugin, "ExcelSession", lambda *a, **kw: made.append((a, kw)) or "session")
    lesson = load_lesson(Path("lessons/monthly-budget"))
    snap, closed = (lambda s: None), (lambda: None)
    got = ExcelPlugin().open(lesson, tmp_path, visible=False, resume=True, on_snapshot=snap, on_closed=closed)
    assert got == "session"
    assert made == [((lesson, tmp_path), {"visible": False, "resume": True, "on_snapshot": snap, "on_closed": closed})]
