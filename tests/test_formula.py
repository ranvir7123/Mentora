from app.excel.formula import absolute_refs_of, functions_of, is_formula, refs_of


def test_spellings_of_one_formula_read_the_same():
    for text in ("=SUM(B2:B6)", "=sum(b2:b6)", "= SUM( $B$2:$B$6 )", "=SUM(B2:B6)+0*0"):
        assert refs_of(text) == ["B2:B6"]
        assert functions_of(text) == ["SUM"]
    assert refs_of("=(B4-C4)") == refs_of("=B4-C4") == ["B4", "C4"]


def test_a_different_formula_reads_differently():
    assert refs_of("=SUM(B2:B5)") != refs_of("=SUM(B2:B6)")
    assert functions_of("=AVERAGE(B2:B6)") != functions_of("=SUM(B2:B6)")


def test_quoted_text_and_function_names_are_not_cells():
    assert refs_of('=IF(B2>50,"B2 passed","no")') == ["B2"]
    assert refs_of("=LOG10(A1)") == ["A1"]


def test_constants_are_not_formulas():
    assert not is_formula("150")
    assert not is_formula(None)
    assert refs_of("150") == [] and functions_of("150") == []


def test_absolute_refs():
    assert absolute_refs_of("=B2*$E$1") == ["E1"]
    assert absolute_refs_of("=B2*E$1") == []
    assert absolute_refs_of("=B2*E1") == []
