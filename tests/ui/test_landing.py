import pytest

from app.core.types import Rect
from app.ui.landing import arc_control, bubble_spot, flight_control, landing_spot

SCREEN = Rect(0, 0, 2560, 1600)
PANEL = Rect(1840, 0, 720, 1600)


def _inside(r: Rect, screen: Rect) -> bool:
    return screen.x <= r.x and r.x + r.w <= screen.x + screen.w and screen.y <= r.y and r.y + r.h <= screen.y + screen.h


def test_landing_spot_never_covers_the_target():
    for t in (Rect(0, 300, 128, 40), Rect(1700, 0, 128, 40), Rect(900, 1560, 128, 40), Rect(1000, 700, 128, 40)):
        x, y = landing_spot(t, 96, SCREEN, PANEL)
        m = Rect(x, y, 96, 96)
        assert not m.intersects(t.inflate(6)) and not m.intersects(PANEL)
        assert _inside(m, SCREEN)


def test_landing_prefers_the_left_side():
    t = Rect(1000, 700, 128, 40)
    x, y = landing_spot(t, 96, SCREEN, PANEL)
    assert x + 96 == t.x - 8                       # an 8 px gap on the left
    assert y + 48 == t.y + 20                      # level with the target's middle


def test_landing_goes_above_when_the_left_is_off_screen_then_right_then_below():
    above = landing_spot(Rect(0, 300, 128, 40), 96, SCREEN, PANEL)
    assert above[1] + 96 == 300 - 8
    right = landing_spot(Rect(0, 0, 128, 40), 96, SCREEN, PANEL)
    assert right[0] == 128 + 8
    below = landing_spot(Rect(0, 0, 2560 - 720 - 50, 40), 96, SCREEN, PANEL)   # no room left, above or right
    assert below[1] == 40 + 8


def test_landing_keeps_the_headroom_clear_of_the_target_and_the_screen():
    # The curl and the cheering hop stick up above the body; landing below must leave room for them.
    t = Rect(0, 0, 2560 - 720 - 50, 40)
    x, y = landing_spot(t, 96, SCREEN, PANEL, headroom=46)
    assert not Rect(x, y - 46, 96, 96 + 46).intersects(t.inflate(6))
    x, y = landing_spot(Rect(1700, 0, 128, 40), 96, SCREEN, PANEL, headroom=46)
    assert y - 46 >= 0


def test_a_target_that_fills_the_screen_still_lands_on_screen_and_off_the_panel():
    t = Rect(0, 0, 1840, 1600)
    x, y = landing_spot(t, 96, SCREEN, PANEL)
    m = Rect(x, y, 96, 96)
    assert _inside(m, SCREEN) and not m.intersects(PANEL)


def test_arc_bends_upward():
    start, end = (2000.0, 800.0), (200.0, 900.0)
    cx, cy = arc_control(start, end)
    assert cx == 1100.0                                    # over the middle
    distance = ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5
    assert cy == 850.0 - 0.25 * distance                   # lifted by a quarter of the distance


def test_bubble_sits_by_the_mascot_and_off_the_target():
    for t in (Rect(1000, 700, 128, 40), Rect(260, 510, 170, 200), Rect(0, 300, 128, 40), Rect(0, 0, 1790, 40)):
        mx, my = landing_spot(t, 96, SCREEN, PANEL, headroom=46)
        bx, by = bubble_spot(t, Rect(mx, my - 46, 96, 142), (220, 56), SCREEN, PANEL)
        b = Rect(bx, by, 220, 56)
        assert not b.intersects(t.inflate(6)) and not b.intersects(PANEL) and _inside(b, SCREEN)
        assert not b.intersects(Rect(mx, my - 46, 96, 142))                  # beside the mascot, not on it
        near = Rect(mx, my - 46, 96, 142).inflate(12)
        assert b.intersects(near)                                            # and close enough to be its words


def test_arc_never_rises_above_the_screen():
    cx, cy = arc_control((2000.0, 100.0), (200.0, 120.0), top=0.0)
    assert cy == 0.0


def test_logical_and_physical_pixels_convert_both_ways():
    from app.ui.landing import to_logical, to_physical

    assert to_physical(Rect(100, 50, 64, 20), (0, 0), 2.0) == Rect(200, 100, 128, 40)
    assert to_physical(Rect(1380, 50, 64, 20), (1280, 0), 2.0) == Rect(1480, 100, 128, 40)
    assert to_logical((1480, 100), (1280, 0), 2.0) == (1380, 50)


def test_bridge_lands_the_mascot_in_logical_pixels(qapp):
    # The test screen is 800 x 600 at scale 1 with no panel open: the docked panel's column (the right
    # 360 px) is kept clear anyway.
    from PySide6.QtCore import QPointF, QRectF

    from app.ui.bridge import Bridge
    from app.ui.demo_backend import DemoBackend

    bridge = Bridge(DemoBackend("pointer_watching"))
    spot = bridge.landingSpot(QRectF(300, 300, 64, 20), 48, 23)
    assert (spot.x(), spot.y()) == (300 - 8 - 48, 310 - 24)
    beside_panel = bridge.landingSpot(QRectF(420, 300, 10, 20), 48, 23)
    assert beside_panel.x() + 48 <= 420 - 8
    words = bridge.bubbleSpot(QRectF(300, 300, 64, 20), QRectF(spot.x(), spot.y() - 23, 48, 71), 100, 40)
    assert isinstance(words, QPointF) and words.y() + 40 <= spot.y() - 23
    bend = bridge.flightControl(QPointF(400, 300), QPointF(100, 300), 48, 23, QRectF(300, 500, 64, 20))
    assert bend == [QPointF(300, 250), QPointF(200, 250)]   # the usual arc through (250, 225): nothing is in the way


def _point(start, bend, end, t):
    (c1, c2), u = bend, 1 - t
    return tuple(u ** 3 * start[i] + 3 * u * u * t * c1[i] + 3 * u * t * t * c2[i] + t ** 3 * end[i] for i in (0, 1))


def _crosses(start, bend, end, size, headroom, keep_clear):
    """Whether the mascot, flying the curve, ever covers `keep_clear` once it has been clear of it."""
    been_clear = False
    for i in range(0, 401):
        x, y = _point(start, bend, end, i / 400)
        over = Rect(x, y - headroom, size, size + headroom).intersects(keep_clear)
        been_clear = been_clear or not over
        if over and been_clear:
            return True
    return False


def _usual_arc(start, end, top):
    """The quadratic arc through arc_control, written as the cubic curve the mascot flies."""
    q = arc_control(start, end, top)
    return tuple(tuple(p[i] + 2 / 3 * (q[i] - p[i]) for i in (0, 1)) for p in (start, end))


def test_the_flight_keeps_the_usual_arc_when_nothing_is_in_its_way():
    start, end = (1872.0, 752.0), (1100.0, 700.0)          # from the panel to the right of a target
    clear = Rect(900, 700, 180, 60)
    bend = flight_control(start, end, 96, clear, SCREEN, headroom=46)
    assert [v for c in bend for v in c] == pytest.approx([v for c in _usual_arc(start, end, 46) for v in c])


def test_the_flight_never_crosses_the_target_on_the_way_in_or_home():
    # Budget step 2: the panel's mascot flies to the left of B8, then home again.
    home, target = (1872.0, 752.0), Rect(260, 750, 170, 40)
    clear = target.inflate(16)                             # the ring and its pulse
    spot = landing_spot(clear, 96, SCREEN, PANEL, headroom=46)
    for start, end in ((home, spot), (spot, home)):
        bend = flight_control(start, end, 96, clear, SCREEN, headroom=46)
        assert not _crosses(start, bend, end, 96, 46, clear)
        assert all(46 <= c[1] <= 1600 - 96 for c in bend)  # and stays on the screen


def test_landing_below_a_target_rises_into_place():
    home, target = (1872.0, 752.0), Rect(0, 0, 1790, 40)
    clear = target.inflate(16)
    spot = landing_spot(clear, 96, SCREEN, PANEL, headroom=46)
    bend = flight_control(home, spot, 96, clear, SCREEN, headroom=46)
    assert not _crosses(home, bend, spot, 96, 46, clear)


def test_a_flight_that_starts_on_the_target_leaves_it_and_does_not_come_back():
    # The target moved under the landed mascot: it flies off to its new spot and never crosses again.
    target = Rect(260, 750, 170, 40)
    clear = target.inflate(16)
    start, spot = (300.0, 740.0), landing_spot(clear, 96, SCREEN, PANEL, headroom=46)
    bend = flight_control(start, spot, 96, clear, SCREEN, headroom=46)
    assert not _crosses(start, bend, spot, 96, 46, clear)
