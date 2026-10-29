from app.core.types import Rect
from app.win.windows import outer_rect_for


def test_the_window_is_grown_by_its_invisible_borders():
    # measured in the earlier project at 200%: GetWindowRect (1840,0)-(2560,1504), visible (1851,0)-(2549,1493)
    window = Rect(1840, 0, 720, 1504)
    frame = Rect(1851, 0, 698, 1493)
    want = Rect(0, 0, 1840, 1500)
    assert outer_rect_for(want, window, frame) == Rect(-11, 0, 1862, 1511)


def test_no_borders_means_the_same_rectangle():
    r = Rect(10, 20, 300, 400)
    assert outer_rect_for(Rect(0, 0, 100, 100), r, r) == Rect(0, 0, 100, 100)
