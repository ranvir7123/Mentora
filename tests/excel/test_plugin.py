from pathlib import Path

from app.core.lesson import lesson_json_schema, load_lesson, validate
from app.core.types import Rect, Target
from app.excel import locate, plugin
from app.excel.checks import CHECKS
from app.excel.ops import OPS
from app.excel.plugin import VISION_TIMEOUT_S, ExcelPlugin
from app.win.windows import png_bytes
from tests.excel.fakes import FakeMeta, box

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


class FakeSession:
    def __init__(self, *a, **kw) -> None:
        self.fallback = None

    def set_vision_fallback(self, fn) -> None:
        self.fallback = fn


def open_budget(p: ExcelPlugin, tmp_path):
    lesson = load_lesson(Path("lessons/monthly-budget"))
    return p.open(lesson, tmp_path, on_snapshot=lambda s: None, on_closed=lambda: None)


def test_with_a_meta_key_every_lesson_can_ask_muse_spark_where_a_button_is(monkeypatch, tmp_path):
    made = []
    meta = FakeMeta(box(250, 100, 300, 200))
    monkeypatch.setattr(plugin, "ExcelSession", FakeSession)
    monkeypatch.setattr(plugin, "find_key", lambda: ("a key", "environment"))
    monkeypatch.setattr(plugin, "MetaClient", lambda **kw: made.append(kw) or meta)
    p = ExcelPlugin()
    first, second = open_budget(p, tmp_path), open_budget(p, tmp_path)
    assert made == [{"timeout_s": VISION_TIMEOUT_S}]                 # one client, shared by every lesson
    picture = png_bytes(400, 300, bytes(400 * 300 * 4))
    assert first.fallback(picture, "Insert > Pie") == Rect(100, 30, 20, 30)
    assert second.fallback(picture, "Insert > Pie") == Rect(100, 30, 20, 30)
    assert [a["label"] for a in meta.asked] == ["point_fallback", "point_fallback"]


def test_with_no_meta_key_no_lesson_asks_muse_spark(monkeypatch, tmp_path):
    made = []
    monkeypatch.setattr(plugin, "ExcelSession", FakeSession)
    monkeypatch.setattr(plugin, "MetaClient", lambda **kw: made.append(kw))
    assert open_budget(ExcelPlugin(), tmp_path).fallback is None
    assert made == []


def test_a_key_saved_while_the_program_runs_is_used_from_the_next_lesson(monkeypatch, tmp_path):
    keys = iter([(None, "missing"), ("a key", "saved user settings")])
    monkeypatch.setattr(plugin, "ExcelSession", FakeSession)
    monkeypatch.setattr(plugin, "find_key", lambda: next(keys))
    monkeypatch.setattr(plugin, "MetaClient", lambda **kw: FakeMeta())
    p = ExcelPlugin()
    assert open_budget(p, tmp_path).fallback is None
    assert open_budget(p, tmp_path).fallback is not None
