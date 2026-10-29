from app.excel.busy import ExcelBusy, is_busy, next_delay


class FakeComError(Exception):
    def __init__(self, hresult):
        super().__init__(hresult, "msg", None, None)
        self.hresult = hresult


def test_the_three_busy_codes_are_busy():
    for code in (-2147417846, -2147418111, -2146777998):
        assert is_busy(FakeComError(code))
    assert is_busy(ExcelBusy("x"))


def test_other_failures_are_not_busy():
    assert not is_busy(FakeComError(-2147352567))   # DISP_E_EXCEPTION: a real error
    assert not is_busy(ValueError("nope"))


def test_delay_doubles_and_caps():
    d, seen = 0.0, []
    for _ in range(7):
        d = next_delay(d)
        seen.append(d)
    assert seen[:4] == [0.02, 0.04, 0.08, 0.16]
    assert max(seen) == 0.25
