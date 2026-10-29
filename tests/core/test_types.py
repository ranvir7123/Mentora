from app.core.types import OpKind, Param, Rect, Verdict, validate_args


def test_cell_and_range_params_accept_excel_addresses():
    k = OpKind("x", (Param("c", "cell"), Param("r", "range")), "")
    for c in ("B7", "$B$7", "Budget!B7", "'My sheet'!C3"):
        assert validate_args(k, {"c": c, "r": "A1:B6"}) == []
    assert validate_args(k, {"c": "B7", "r": "Budget!A1:B6"}) == []
    assert validate_args(k, {"c": "B7", "r": "C3"}) == []          # one cell is a range


def test_validate_names_every_problem():
    k = OpKind("set_bold", (Param("range", "range"), Param("on", "bool", required=False)), "")
    problems = validate_args(k, {"range": "A1:", "colour": "red"})
    assert any("range" in p and "A1:" in p for p in problems)
    assert any("colour" in p for p in problems)


def test_enum_number_function_and_path_params():
    k = OpKind("x", (Param("e", "enum", choices=("pie", "line")), Param("n", "number"),
                     Param("f", "function"), Param("p", "path")), "")
    assert validate_args(k, {"e": "pie", "n": 3.5, "f": "SUM", "p": "app/main.py"}) == []
    assert len(validate_args(k, {"e": "donut", "n": True, "f": "sum(", "p": "../x.py"})) == 4


def test_missing_required_arg_is_named():
    k = OpKind("x", (Param("cell", "cell"),), "")
    assert validate_args(k, {}) == ["x: cell is missing"]


def test_verdict_constructors():
    assert Verdict.right() == Verdict(True, True)
    assert Verdict.waiting() == Verdict(False, False)
    assert Verdict.wrong("covers_missing:B6", "Not yet: include B6.").attempted


def test_rect_helpers():
    r = Rect(10, 10, 20, 10)
    assert r.inflate(2) == Rect(8, 8, 24, 14)
    assert r.intersects(Rect(25, 15, 10, 10)) and not r.intersects(Rect(31, 0, 5, 5))
    assert r.center == (20, 15)
