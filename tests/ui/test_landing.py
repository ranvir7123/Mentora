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
    from PySide6.QtCore import QPointF, QRectF, QSizeF

    from app.ui.bridge import Bridge
    from app.ui.demo_backend import DemoBackend

    bridge = Bridge(DemoBackend("pointer_watching"))
    spot = bridge.landingSpot(QRectF(300, 300, 64, 20), 48, 23, QSizeF(100, 40))
    assert (spot.x(), spot.y()) == (300 - 8 - 48, 310 - 24)
    beside_panel = bridge.landingSpot(QRectF(420, 300, 10, 20), 48, 23, QSizeF(100, 40))
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


# The budget lesson on the laptop's screen, measured from a real Excel run at 200% (physical px): Excel left
# of the 360 px panel, the taskbar along the bottom. The sheet's visible cells are the room Excel gives;
# above them are the ribbon, the formula bar, the Name Box and the column headings.
WORK = Rect(0, 0, 2560, 1504)
LIVE_PANEL = Rect(1840, 0, 720, 1504)
CELLS = Rect(55, 470, 1743, 923)
_COLS = {"A": (55, 210), "B": (265, 180), "C": (445, 151)}
_ROW = 38
RING = 16                                     # the ring and its pulse reach 8 logical px past the target
MASCOT, HEADROOM = 96, 46
WORDS = ((186, 74), (400, 74))                # "This one!" and "Type it in this cell"


def _cells(first: str, last: str = "") -> Rect:
    (c0, r0), (c1, r1) = ((ref[0], int(ref[1:])) for ref in (first, last or first))
    x0, y0 = _COLS[c0][0], CELLS.y + (r0 - 1) * _ROW
    return Rect(x0, y0, _COLS[c1][0] + _COLS[c1][1] - x0, CELLS.y + r1 * _ROW - y0)


BUDGET_CELL_STEPS = {1: _cells("A1", "C1"), 2: _cells("B8"), 3: _cells("B2", "B8"), 4: _cells("C2"),
                     5: _cells("C2", "C6"), 6: _cells("C2", "C6")}
BUDGET_BUTTON_STEPS = {7: Rect(612, 168, 96, 112), 8: Rect(838, 168, 120, 112), 9: Rect(452, 176, 64, 96)}
FILLED = _cells("A1", "C8")                   # the budget's items, amounts and shares, from the first step


def test_on_a_cell_step_the_mascot_and_its_words_stay_on_the_sheets_empty_cells():
    # Step 1's live run: the headings fill the sheet's top row, so the mascot went up onto the formula bar
    # and its words onto Bold, the very button the step needs. On the sheet they keep off what the learner
    # reads, such as the rent in B2 while working out its share.
    # The mascot picks its side knowing its words, so long words never leave it stuck in a narrow strip.
    for step, target in BUDGET_CELL_STEPS.items():
        ring = target.inflate(RING)
        for size in WORDS:
            x, y = landing_spot(ring, MASCOT, WORK, LIVE_PANEL, room=CELLS, filled=FILLED, headroom=HEADROOM,
                                words=size)
            body = Rect(x, y - HEADROOM, MASCOT, MASCOT + HEADROOM)
            assert _inside(body, CELLS), f"step {step}: the mascot at {body} leaves the cells {CELLS}"
            assert not body.intersects(ring.inflate(6)), f"step {step}: the mascot covers the ring"
            assert not body.intersects(FILLED), f"step {step}: the mascot at {body} covers the filled cells"
            bx, by = bubble_spot(ring, body, size, WORK, LIVE_PANEL, room=CELLS, filled=FILLED)
            words = Rect(bx, by, *size)
            assert _inside(words, CELLS), f"step {step}: the words at {words} leave the cells"
            assert not words.intersects(FILLED), f"step {step}: the words at {words} cover the filled cells"
            assert not words.intersects(ring.inflate(6)) and not words.intersects(body), f"step {step}"
            assert words.intersects(body.inflate(12)), f"step {step}: the words are not by the mascot"


def test_with_no_empty_cells_beside_the_target_the_mascot_still_stays_on_the_sheet():
    # A sheet filled past the edge of the window: the mascot covers some cells rather than the ribbon.
    ring = _cells("B8").inflate(RING)
    spot = landing_spot(ring, MASCOT, WORK, LIVE_PANEL, room=CELLS, filled=CELLS, headroom=HEADROOM, words=WORDS[0])
    assert spot == landing_spot(ring, MASCOT, WORK, LIVE_PANEL, room=CELLS, headroom=HEADROOM, words=WORDS[0])


def test_a_ribbon_button_step_still_points_at_the_button_and_never_covers_it():
    # Excel gives no room for a button: the mascot lands right beside it, wherever that is.
    for step, target in BUDGET_BUTTON_STEPS.items():
        ring = target.inflate(RING)
        for size in WORDS:
            x, y = landing_spot(ring, MASCOT, WORK, LIVE_PANEL, headroom=HEADROOM, words=size)
            body = Rect(x, y - HEADROOM, MASCOT, MASCOT + HEADROOM)
            assert not body.intersects(ring.inflate(6)) and body.intersects(ring.inflate(6 + 8 + 1)), f"step {step}"
            words = Rect(*bubble_spot(ring, body, size, WORK, LIVE_PANEL), *size)
            assert not words.intersects(ring.inflate(6)) and _inside(words, WORK), f"step {step}"


def test_with_no_space_in_the_room_the_mascot_still_never_covers_the_target():
    ring = _cells("A1", "C6").inflate(RING)
    x, y = landing_spot(ring, MASCOT, WORK, LIVE_PANEL, room=ring.inflate(20), headroom=HEADROOM)
    body = Rect(x, y - HEADROOM, MASCOT, MASCOT + HEADROOM)
    assert not body.intersects(ring.inflate(6)) and _inside(body, WORK) and not body.intersects(LIVE_PANEL)


def test_a_room_that_does_not_hold_the_target_is_ignored():
    target = Rect(1000, 100, 128, 40)
    assert landing_spot(target, MASCOT, WORK, LIVE_PANEL, room=CELLS) == landing_spot(target, MASCOT, WORK, LIVE_PANEL)


def test_the_bridge_keeps_the_mascot_and_its_words_in_the_room_the_app_gives(qapp):
    # The test screen is 800 x 600 at scale 1; the docked panel's column is its right 360 px.
    from PySide6.QtCore import QRectF, QSizeF

    from app.ui.bridge import Bridge
    from app.ui.demo_backend import DemoBackend

    backend = DemoBackend("pointer_watching")
    bridge = Bridge(backend)
    room = {"x": 60, "y": 200, "w": 380, "h": 400}
    backend._publish(pointer=dict(backend.pointer(), x=60, y=200, w=200, h=20, room=room))
    qapp.processEvents()
    spot = bridge.landingSpot(QRectF(60, 200, 200, 20), 48, 23, QSizeF(100, 40))
    body = Rect(spot.x(), spot.y() - 23, 48, 71)
    cells = Rect(60, 200, 380, 400)
    assert _inside(body, cells), f"the mascot at {body} left the room {cells}"
    words = bridge.bubbleSpot(QRectF(60, 200, 200, 20), QRectF(body.x, body.y, body.w, body.h), 100, 40)
    assert _inside(Rect(words.x(), words.y(), 100, 40), cells)


def test_the_bridge_keeps_the_mascot_and_its_words_off_the_filled_cells_the_app_gives(qapp):
    # The target is in a filled row (like the budget's headings): the mascot goes under it, not beside it.
    from PySide6.QtCore import QRectF, QSizeF

    from app.ui.bridge import Bridge
    from app.ui.demo_backend import DemoBackend

    backend = DemoBackend("pointer_watching")
    bridge = Bridge(backend)
    room, filled = {"x": 60, "y": 200, "w": 380, "h": 400}, {"x": 60, "y": 200, "w": 300, "h": 20}
    backend._publish(pointer=dict(backend.pointer(), x=60, y=200, w=200, h=20, room=room, filled=filled))
    qapp.processEvents()
    spot = bridge.landingSpot(QRectF(60, 200, 200, 20), 48, 23, QSizeF(100, 40))
    body = Rect(spot.x(), spot.y() - 23, 48, 71)
    row = Rect(60, 200, 300, 20)
    assert _inside(body, Rect(60, 200, 380, 400)) and not body.intersects(row), f"the mascot at {body}"
    words = bridge.bubbleSpot(QRectF(60, 200, 200, 20), QRectF(body.x, body.y, body.w, body.h), 100, 40)
    assert not Rect(words.x(), words.y(), 100, 40).intersects(row)
