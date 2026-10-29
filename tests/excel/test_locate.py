from dataclasses import astuple

import pytest

from app.core.types import Rect, Spot, Target
from app.excel import locate
from app.excel.address import parse_area
from app.excel.locate import PaneInfo, cell_rect, clip_to, find_target, pane_for, split_area, spot_rect
from app.excel.session import VISION_STILL_S
from app.win import windows
from tests.excel.fakes import BUSY, FakeNode, com_error

PX = 192 / 72          # physical pixels per point at 200% scaling


def xywh(r: Rect) -> tuple:
    return pytest.approx(astuple(r))


def pane(x0=100.0, y0=200.0, left=0.0, top=0.0, zoom=1.0, visible=Rect(100, 200, 2000, 1000)) -> PaneInfo:
    return PaneInfo(x0, y0, left, top, zoom, PX, visible)


# ------------------------------------------------------------------ cells (pure)

def test_cell_rect_at_100_and_200_percent_zoom():
    assert astuple(cell_rect(pane(), 48, 105, 48, 15)) == xywh(Rect(228, 480, 128, 40))
    assert astuple(cell_rect(pane(zoom=2.0), 48, 105, 48, 15)) == xywh(Rect(356, 760, 256, 80))
    assert astuple(cell_rect(pane(zoom=1.5), 48, 105, 48, 15)) == xywh(Rect(292, 620, 192, 60))


def test_scrolled_cell_moves_left_by_the_scroll():
    still = cell_rect(pane(), 96, 15, 48, 15)
    scrolled = cell_rect(pane(left=48, top=15), 96, 15, 48, 15)
    assert scrolled.x == pytest.approx(still.x - 48 * PX)
    assert scrolled.y == pytest.approx(still.y - 15 * PX)
    assert (scrolled.w, scrolled.h) == (still.w, still.h)


def test_cell_in_frozen_rows_uses_the_top_pane():
    assert pane_for(1, 2, 0, 0) == 1
    assert pane_for(1, 2, 1, 0) == 1 and pane_for(8, 2, 1, 0) == 2
    assert pane_for(3, 1, 0, 1) == 1 and pane_for(3, 2, 0, 1) == 2
    assert [pane_for(r, c, 2, 2) for r, c in ((1, 1), (1, 3), (3, 1), (3, 3))] == [1, 2, 3, 4]

    assert split_area(parse_area("A1:C8"), 1, 0) == [(1, parse_area("A1:C1")), (2, parse_area("A2:C8"))]
    assert split_area(parse_area("B2:B6"), 0, 0) == [(1, parse_area("B2:B6"))]
    assert split_area(parse_area("Budget!B2:B6"), 1, 0) == [(2, parse_area("Budget!B2:B6"))]
    assert [n for n, _ in split_area(parse_area("A1:D4"), 2, 2)] == [1, 2, 3, 4]

    # Row 1 frozen (15 pt = 40 px); the pane below is scrolled so row 7 (Top 90 pt) is its first row.
    top = pane(visible=Rect(100, 200, 2000, 40))
    rest = pane(y0=240, top=90, visible=Rect(100, 240, 2000, 960))
    assert astuple(spot_rect([(top, 0, 0, 144, 15)])) == xywh(Rect(100, 200, 384, 40))       # A1:C1 stays
    assert astuple(spot_rect([(rest, 48, 105, 48, 15)])) == xywh(Rect(228, 280, 128, 40))    # B8 below
    # A1:A8 straddles the split: the part scrolled under the frozen row is cut off.
    assert astuple(spot_rect([(top, 0, 0, 48, 15), (rest, 0, 15, 48, 105)])) == xywh(Rect(100, 200, 128, 120))


def test_cell_scrolled_out_of_view_is_none():
    vis = Rect(100, 240, 2000, 960)
    assert clip_to(Rect(100, 40, 128, 40), vis) is None
    assert clip_to(Rect(100, 1300, 128, 40), vis) is None
    assert clip_to(Rect(100, 200, 128, 40), vis) is None                  # touching is not showing
    assert astuple(clip_to(Rect(90, 220, 128, 40), vis)) == (100, 240, 118, 20)
    rest = pane(y0=240, top=90, visible=vis)
    assert spot_rect([(rest, 48, 30, 48, 15)]) is None                     # row 3, scrolled away
    assert spot_rect([]) is None


# ------------------------------------------------------------------ controls (fake UI Automation tree)

def window(*children) -> FakeNode:
    return FakeNode("Window", "Excel", Rect(0, 0, 1840, 1500), children=children)


def tab(name, rect=Rect(300, 20, 60, 30), selected=False) -> FakeNode:
    return FakeNode("TabItem", name, rect, selected=selected)


def button(name, rect=None, kind="Button") -> FakeNode:
    return FakeNode(kind, name, rect)


def group(name, *children, rect=None) -> FakeNode:
    return FakeNode("Group", name, rect, children=children)


def spot(roots, kind, ref):
    return locate.spot_of(find_target(roots, kind, ref))


def test_names_with_zero_width_spaces_match():
    assert locate.same_name("Freeze​ Panes", "freeze panes")
    assert locate.same_name("Sort​Largest to​ Smallest", "Sort Largest to Smallest")
    assert locate.same_name("  Sort   A to Z ", "sort a to z")
    assert not locate.same_name("Freeze Top Row", "Freeze Panes")
    main = window(tab("View", selected=True), button("Freeze​ Panes", Rect(900, 60, 80, 90), "SplitButton"))
    assert spot([main], "control", "View > Freeze Panes") == Spot(Rect(900, 60, 80, 90))


def test_folded_group_points_at_the_dropdown_first():
    pie = button("Pie")                                              # off screen: its group is folded
    charts = group("Charts", pie, button("Charts", Rect(700, 60, 60, 90), "MenuItem"))
    main = window(tab("Insert", selected=True), charts)
    assert spot([main], "control", "Insert > Pie") == Spot(Rect(700, 60, 60, 90), "open this first")
    popup = window(button("Pie", Rect(700, 160, 60, 60)))           # the learner opened Charts
    assert spot([main, popup], "control", "Insert > Pie") == Spot(Rect(700, 160, 60, 60))
    # A folded group that is itself the drop-down (no separate button) is pointed at the same way.
    main = window(tab("Insert", selected=True), group("Charts", button("Pie"), rect=Rect(700, 60, 60, 90)))
    assert spot([main], "control", "Insert > Pie") == Spot(Rect(700, 60, 60, 90), "open this first")


def test_a_tab_that_is_not_open_is_pointed_at_first():
    main = window(tab("Home", Rect(200, 20, 60, 30), selected=True), tab("Insert", Rect(300, 20, 60, 30)),
                  button("Bold", Rect(300, 60, 30, 30)))
    assert spot([main], "control", "Insert > Pie") == Spot(Rect(300, 20, 60, 30), "open this first")


def test_exact_names_win_over_longer_ones_and_a_missing_control_is_none():
    long = button("Insert Pie or Doughnut Chart", Rect(600, 60, 50, 90))
    main = window(tab("Insert", selected=True), long, button("Pie", Rect(700, 60, 50, 90)))
    assert spot([main], "control", "Insert > Pie") == Spot(Rect(700, 60, 50, 90))
    main = window(tab("Insert", selected=True), button("Insert Pie or Doughnut Chart", Rect(600, 60, 50, 90)),
                  button("Copies", Rect(800, 60, 50, 90)))
    assert spot([main], "control", "Insert > Pie") == Spot(Rect(600, 60, 50, 90))
    assert spot([main], "control", "Insert > Sparkle") is None
    assert spot([main], "control", "Draw > Pen") is None             # no such tab
    assert spot([main], "control", "Pie") is None                    # no tab named: not a path


def test_formula_bar_name_box_and_sheet_tabs():
    main = window(tab("Home", Rect(200, 20, 60, 30), selected=True),
                  FakeNode("ComboBox", "Name Box", Rect(10, 250, 150, 40)),
                  FakeNode("Edit", "Formula Bar", Rect(200, 250, 1500, 40)),
                  tab("Budget", Rect(40, 1400, 90, 30), selected=True), tab("Home", Rect(130, 1400, 90, 30)))
    assert spot([main], "name_box", "") == Spot(Rect(10, 250, 150, 40))
    assert spot([main], "formula_bar", "") == Spot(Rect(200, 250, 1500, 40))
    assert spot([main], "sheet_tab", "Budget") == Spot(Rect(40, 1400, 90, 30))
    assert spot([main], "sheet_tab", "Home") == Spot(Rect(130, 1400, 90, 30))   # the sheet, not the ribbon tab
    assert spot([main], "sheet_tab", "Notes") is None


def test_a_found_control_is_followed_and_found_again_when_it_goes():
    pie = button("Pie", Rect(700, 60, 50, 90))
    main = window(tab("Insert", selected=True), pie)
    finds = []
    tracker = locate.ControlTracker(lambda: finds.append(1) or [main], "control", "Insert > Pie")
    assert tracker.spot() == Spot(Rect(700, 60, 50, 90))
    pie.rect = Rect(710, 60, 50, 90)                                 # the window moved
    assert tracker.spot() == Spot(Rect(710, 60, 50, 90)) and len(finds) == 1
    pie.gone = True                                                  # the learner switched tabs
    main.children.remove(pie)
    assert tracker.spot() is None and len(finds) == 2


def test_a_route_is_looked_up_again_every_few_ticks():
    main = window(tab("Home", selected=True), tab("Insert", Rect(300, 20, 60, 30)))
    finds = []
    tracker = locate.ControlTracker(lambda: finds.append(1) or [main], "control", "Insert > Pie")
    assert tracker.spot() == Spot(Rect(300, 20, 60, 30), "open this first")
    main.children[0].selected, main.children[1].selected = False, True          # the learner opened Insert
    main.children.append(button("Pie", Rect(700, 60, 50, 90)))
    seen = [tracker.spot() for _ in range(locate.ROUTE_REFIND_TICKS)]
    assert seen[-1] == Spot(Rect(700, 60, 50, 90)) and len(finds) == 2


# ------------------------------------------------------------------ through the session

class Script:
    """A pretend tracker that gives the spots it was handed, one per look."""

    def __init__(self, *spots) -> None:
        self.spots = list(spots)
        self.looks = 0

    def spot(self):
        self.looks += 1
        s = self.spots.pop(0) if len(self.spots) > 1 else self.spots[0]
        if isinstance(s, Exception):
            raise s
        return s


def at(x, y=100, w=50, h=20) -> Spot:
    return Spot(Rect(x, y, w, h))


def scripted(monkeypatch, *trackers):
    queue = list(trackers)
    made = []

    def make(target, app, wb, hwnd):
        made.append(target)
        return queue.pop(0) if len(queue) > 1 else queue[0]
    monkeypatch.setattr(locate, "tracker_for", make)
    return made


B8 = Target("cell", "Budget!B8")
PIE = Target("control", "Insert > Pie")


def test_watch_reports_the_first_spot_then_only_moves_of_a_pixel_or_more(rig, monkeypatch):
    scripted(monkeypatch, Script(at(100), at(100.4), at(101), None, None, at(101), Spot(Rect(101, 100, 50, 20), "open this first")))
    r = rig()
    got = []
    r.session.watch(B8, got.append)
    for _ in range(7):
        r.com.advance(locate.WATCH_S)
    assert got == [at(100), at(101), None, at(101), Spot(Rect(101, 100, 50, 20), "open this first")]


def test_watch_skips_a_busy_look_quietly_and_a_failed_one_is_nothing_on_screen(rig, monkeypatch):
    script = Script(at(100), com_error(BUSY), at(120), RuntimeError("Excel said no"), at(120))
    scripted(monkeypatch, script)
    r = rig()
    got = []
    r.session.watch(B8, got.append)
    for _ in range(5):
        r.com.advance(locate.WATCH_S)
    assert got == [at(100), at(120), None, at(120)] and script.looks == 6 and r.com.errors == []


def test_watch_none_stops_and_a_new_target_replaces_the_old(rig, monkeypatch):
    first, second = Script(at(100)), Script(at(100))
    made = scripted(monkeypatch, first, second)
    r = rig()
    got = []
    r.session.watch(B8, got.append)
    r.com.advance(0.25)
    r.session.watch(PIE, got.append)
    r.com.advance(0.25)
    looked = first.looks
    assert made == [B8, PIE] and got == [at(100), at(100)]          # a new target's first spot is always told
    r.session.watch(None, got.append)
    r.com.advance(2)
    assert first.looks == looked and second.looks <= 4 and r.com.pending() < 3
    before = second.looks
    r.com.advance(2)
    assert second.looks == before


def test_locate_gives_the_spot_once_waiting_out_a_busy_excel(rig, monkeypatch):
    scripted(monkeypatch, Script(com_error(BUSY), com_error(BUSY), at(300)))
    r = rig()
    fut = r.session.locate(B8)
    r.com.advance(1)
    assert fut.result(0) == at(300)


def shown(monkeypatch) -> list:
    """Pretend the session's Excel has a window; returns the window-move hooks it sets."""
    hooks = []
    monkeypatch.setattr(windows, "is_window", lambda hwnd: True)
    monkeypatch.setattr(windows, "location_hook", lambda hwnd, fn: hooks.append(fn) or (lambda: hooks.remove(fn)))
    return hooks


def test_a_window_move_looks_again_at_once(rig, monkeypatch):
    hooks = shown(monkeypatch)
    script = Script(at(100), at(140))
    scripted(monkeypatch, script)
    r = rig(visible=True)
    got = []
    r.session.watch(B8, got.append)
    r.com.advance(0)
    assert script.looks == 1 and len(hooks) == 1
    hooks[0]()                                                       # Excel's window moved
    r.com.advance(0)
    assert script.looks == 2 and got == [at(100), at(140)]
    r.session.watch(None, got.append)
    assert hooks == []                                               # nothing is hooked while not watching


def test_vision_is_asked_only_when_ui_automation_finds_nothing_and_only_trusted_when_it_agrees(rig, monkeypatch):
    asked, agreed = [], []
    monkeypatch.setattr(locate, "background", lambda fn: fn())
    monkeypatch.setattr(windows, "screenshot_png", lambda rect: b"png")
    monkeypatch.setattr(windows, "window_rect", lambda hwnd: Rect(0, 0, 1840, 1500))
    monkeypatch.setattr(locate, "confirm_vision", lambda rect, target: agreed.append(rect) or rect.x == 10)
    shown(monkeypatch)
    scripted(monkeypatch, Script(at(700)))
    r = rig(visible=True)
    r.session.set_vision_fallback(lambda png, ref: asked.append((png, ref)) or Rect(10, 10, 20, 20))
    got = []
    r.session.watch(PIE, got.append)
    r.com.advance(0.25)
    assert asked == [] and got == [at(700)]                          # UI Automation found it: no picture

    scripted(monkeypatch, Script(None))
    r.session.watch(PIE, got.append)
    r.com.advance(0.25)
    assert asked == [(b"png", "Insert > Pie")] and got[-1] == Spot(Rect(10, 10, 20, 20))
    assert len(agreed) == 1                                          # asked once, not on every look

    r.session.set_vision_fallback(lambda png, ref: asked.append((png, ref)) or Rect(99, 10, 20, 20))
    r.session.watch(PIE, got.append)
    r.com.advance(0.25)
    assert got[-1] is None                                           # UI Automation disagreed


def vision_rig(rig, monkeypatch, where: list, asked: list):
    """A shown Excel whose window is at where[0]; the fallback finds Pie 10 px in from its corner."""
    monkeypatch.setattr(locate, "background", lambda fn: fn())
    monkeypatch.setattr(windows, "screenshot_png", lambda rect: b"png")
    monkeypatch.setattr(windows, "window_rect", lambda hwnd: where[0])
    monkeypatch.setattr(locate, "confirm_vision", lambda rect, target: True)
    hooks = shown(monkeypatch)
    scripted(monkeypatch, Script(None))
    r = rig(visible=True)
    r.session.set_vision_fallback(lambda png, ref: asked.append(where[0]) or Rect(where[0].x + 10, 10, 20, 20))
    return r, hooks


def test_vision_follows_a_dragged_window_without_asking_again(rig, monkeypatch):
    asked, where = [], [Rect(0, 0, 1840, 1500)]
    r, hooks = vision_rig(rig, monkeypatch, where, asked)
    got = []
    r.session.watch(PIE, got.append)
    r.com.advance(0.25)
    for x in range(1, 61):                       # dragged 60 px, one move every 10 ms
        where[0] = Rect(x, 0, 1840, 1500)
        hooks[0]()
        r.com.advance(0.01)
    r.com.advance(1)
    assert asked == [Rect(0, 0, 1840, 1500)] and got[-1] == Spot(Rect(70, 10, 20, 20))


def test_vision_asks_again_once_a_resized_window_has_stopped_changing(rig, monkeypatch):
    asked, where = [], [Rect(0, 0, 1840, 1500)]
    r, hooks = vision_rig(rig, monkeypatch, where, asked)
    got = []
    r.session.watch(PIE, got.append)
    r.com.advance(0.25)
    for w in range(1839, 1809, -1):              # its edge dragged 30 px, one change every 10 ms
        where[0] = Rect(0, 0, w, 1500)
        hooks[0]()
        r.com.advance(0.01)
    assert len(asked) == 1 and got[-1] is None   # the ribbon may fold differently: the old answer is not used
    r.com.advance(VISION_STILL_S + 0.1)
    assert asked == [Rect(0, 0, 1840, 1500), Rect(0, 0, 1810, 1500)] and got[-1] == Spot(Rect(10, 10, 20, 20))


def test_a_window_hook_that_fails_leaves_the_watch_looking(rig, monkeypatch):
    def refused(hwnd, fn):
        raise OSError("SetWinEventHook said no")
    monkeypatch.setattr(windows, "is_window", lambda hwnd: True)
    monkeypatch.setattr(windows, "location_hook", refused)
    script = Script(at(100), at(140))
    scripted(monkeypatch, script)
    r = rig(visible=True)
    got = []
    r.session.watch(B8, got.append)
    r.com.advance(0.25)
    assert got == [at(100), at(140)] and script.looks == 3
    assert len(r.session.errors) == 1 and "SetWinEventHook said no" in r.session.errors[0]


def test_a_locate_waiting_out_a_busy_excel_fails_when_the_session_closes(rig, monkeypatch):
    scripted(monkeypatch, Script(com_error(BUSY)))
    r = rig()
    fut = r.session.locate(B8)
    r.com.advance(0.1)
    r.session.close()                            # its next try was booked, and now never comes
    with pytest.raises(RuntimeError, match="Excel was closed"):
        fut.result(0)


def test_a_cell_watch_never_asks_vision(rig, monkeypatch):
    asked = []
    monkeypatch.setattr(locate, "background", lambda fn: fn())
    scripted(monkeypatch, Script(None))
    r = rig()
    r.session.set_vision_fallback(lambda png, ref: asked.append(ref))
    got = []
    r.session.watch(B8, got.append)
    r.com.advance(0.25)
    assert asked == [] and got == [None]
