from app.excel.snapshot import (Cell, Sheet, Snapshot, as_grid, cells_from_block, clean_value,
                                col_letters, uniform_grid)


def test_column_letters():
    assert [col_letters(n) for n in (1, 2, 26, 27, 52, 53, 702, 703)] == \
        ["A", "B", "Z", "AA", "AZ", "BA", "ZZ", "AAA"]


def test_one_cell_and_many_cells_come_back_as_rows():
    assert as_grid(5.0, 1, 1) == [[5.0]]
    assert as_grid(((1.0, 2.0), (3.0, 4.0)), 2, 2) == [[1.0, 2.0], [3.0, 4.0]]
    assert as_grid(((1.0,),), 1, 1) == [[1.0]]


def test_error_cells_read_as_their_error_text():
    assert clean_value(-2146826281) == "#DIV/0!"
    assert clean_value(-2146826246) == "#N/A"
    assert clean_value(3) == 3.0 and isinstance(clean_value(3), float)
    assert clean_value(True) is True
    assert clean_value("Rent") == "Rent"


def test_blank_cells_are_left_out_and_formulas_kept_only_when_they_are_formulas():
    values = [["Item", "Cost"], [None, 1200.0], ["", 300.0]]
    formulas = [["Item", "Cost"], ["", "1200"], ["", "=B2/4"]]
    formats = [["General", "General"], ["General", "0.00"], ["General", "General"]]
    bolds = [[True, True], [False, False], [False, False]]
    cells = cells_from_block(1, 1, values, formulas, formats, bolds)
    assert set(cells) == {"A1", "B1", "B2", "B3"}
    assert cells["A1"] == Cell("Item", None, "General", True)
    assert cells["B2"] == Cell(1200.0, None, "0.00", False)
    assert cells["B3"].formula == "=B2/4"


def test_a_block_that_starts_away_from_a1_keeps_its_addresses():
    cells = cells_from_block(3, 2, [[7.0]], [["7"]], [["General"]], [[False]])
    assert set(cells) == {"B3"}


def _fake_sheet(truth):
    """read_span over a known grid, answering None where the cells differ, like Excel."""
    calls = []

    def read_span(r0, r1, c):
        calls.append((r0, r1, c))
        cols = range(len(truth[0])) if c is None else [c]
        seen = {truth[r][cc] for r in range(r0, r1 + 1) for cc in cols}
        return seen.pop() if len(seen) == 1 else None

    return read_span, calls


def test_mixed_formats_are_read_exactly():
    truth = [["0.00", "General"], ["0.00", "0%"], ["0.00", "0%"]]
    read_span, _ = _fake_sheet(truth)
    assert uniform_grid(read_span, 3, 2) == truth


def test_a_uniform_range_is_one_read():
    read_span, calls = _fake_sheet([["General"] * 2] * 3)
    assert uniform_grid(read_span, 3, 2) == [["General"] * 2] * 3
    assert calls == [(0, 2, None)]


def test_a_bold_header_over_a_long_column_costs_few_reads():
    truth = [[True]] + [[False]] * 999
    read_span, calls = _fake_sheet(truth)
    assert uniform_grid(read_span, 1000, 1) == truth
    assert len(calls) < 25   # one read per cell would be 1000


def test_asking_for_a_missing_cell_gives_an_empty_one():
    snap = Snapshot((Sheet("Budget", {"B2": Cell(5.0)}),), "Budget", "B2")
    assert snap.cell("Budget", "$b$2").value == 5.0
    assert snap.cell("Budget", "C9") == Cell()
    assert snap.cell("Nope", "A1") == Cell()
