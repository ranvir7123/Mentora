import pytest

from app.excel.address import Area, col_index, is_address, parse_area, quote_sheet


def test_a_cell_a_range_and_a_sheet():
    assert parse_area("B8") == Area(None, 8, 2, 8, 2)
    assert parse_area("Budget!A1:C1") == Area("Budget", 1, 1, 1, 3)
    assert parse_area("'My ''own'' sheet'!$B$2:b6") == Area("My 'own' sheet", 2, 2, 6, 2)


def test_corners_in_any_order_make_the_same_rectangle():
    assert parse_area("C6:A2") == parse_area("A2:C6")


def test_cells_come_row_by_row():
    a = parse_area("A1:B2")
    assert a.cells() == ["A1", "B1", "A2", "B2"]
    assert (a.first, a.last, a.a1, a.size) == ("A1", "B2", "A1:B2", 4)
    assert parse_area("Budget!B8").a1 == "B8"


def test_not_addresses():
    for bad in ("B0", "8B", "A1:", "Sheet1!", "XFE1", "A1048577", "", None, 5):
        assert not is_address(bad), bad
    with pytest.raises(ValueError, match="B0"):
        parse_area("B0")


def test_columns_and_quoting():
    assert [col_index(c) for c in ("A", "z", "AA", "XFD")] == [1, 26, 27, 16384]
    assert quote_sheet("Budget") == "Budget"
    assert quote_sheet("My sheet") == "'My sheet'"
    assert quote_sheet("Bob's") == "'Bob''s'"
