"""Where a step's target is on screen: a cell or range, a ribbon button, the formula bar, a sheet tab.

Cells come from Excel's own numbers. Each pane of the window (one, or up to four with frozen panes)
is asked for one thing: the screen position of its first visible cell, `pane.PointsToScreenPixelsX/Y`
of its `VisibleRange.Left/Top`. Everything else is sums done here: a cell's offset from that first cell
in points, times zoom, times the screen's pixels per point (DPI / 72). Two facts measured on this
laptop in the earlier project decide this:
- Excel's conversion is exact for that one point, but it scales any further offset at 1 pixel per
  point instead of DPI / 72, so offsets are never handed to it.
- The window-level conversion is right only while A1 is the top-left cell; each pane's own is right
  in every scroll and freeze state measured. The window-level one is never used.
Whether PointsToScreenPixels gives physical pixels at 200% here is measured again by
probes/excel_locate.py.

Buttons, boxes and tabs come from UI Automation (app/win/uia.py), found by name. When a button cannot
be seen, the pointer goes where the learner must click first, with the words "open this first": the
ribbon tab when another tab is open, or the drop-down a folded group has become when Excel is too
narrow to show the group. Once that is open, the button itself.

All of it runs on the COM thread.
"""
from __future__ import annotations

import threading
from dataclasses import astuple, dataclass, replace
from typing import Any, Callable, Iterable, Protocol, Sequence

from app.core.types import Rect, Spot, Target
from app.excel.address import Area, parse_area
from app.win import windows

WATCH_S = 0.1                     # a watched target is looked at this often
ROUTE_REFIND_TICKS = 5            # while pointing at a route (or at nothing), search again this often
OPEN_FIRST = "open this first"
OPEN_SHEET_FIRST = "open this sheet first"
POINTS_PER_INCH = 72

_CLICKABLE = frozenset({"Button", "SplitButton", "MenuItem", "CheckBox", "ComboBox", "RadioButton",
                        "ListItem", "Hyperlink"})
_BOXES = frozenset({"Edit", "ComboBox"})
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­"))
_GROUP_DEPTH = 6                  # how far up from a hidden button to look for its group


# ------------------------------------------------------------------ cells: pure sums

@dataclass(frozen=True)
class PaneInfo:
    """One pane of Excel's window: where its first visible cell is on screen, and how to scale."""
    screen_x0: float              # physical px of the pane's first visible cell's left edge
    screen_y0: float
    scroll_left_pt: float         # that cell's Left and Top on the sheet, in points
    scroll_top_pt: float
    zoom: float                   # 1.0 at 100%
    px_per_pt: float              # the screen's pixels per point at 100% zoom (DPI / 72)
    visible: Rect                 # the part of the screen this pane shows


def cell_rect(pane: PaneInfo, left_pt: float, top_pt: float, width_pt: float, height_pt: float) -> Rect:
    k = pane.zoom * pane.px_per_pt
    return Rect(pane.screen_x0 + (left_pt - pane.scroll_left_pt) * k,
                pane.screen_y0 + (top_pt - pane.scroll_top_pt) * k, width_pt * k, height_pt * k)


def clip_to(rect: Rect, visible: Rect) -> Rect | None:
    """The part of rect inside visible; None when nothing of it shows."""
    x0, y0 = max(rect.x, visible.x), max(rect.y, visible.y)
    x1, y1 = min(rect.x + rect.w, visible.x + visible.w), min(rect.y + rect.h, visible.y + visible.h)
    if x1 <= x0 or y1 <= y0:
        return None
    return Rect(x0, y0, x1 - x0, y1 - y0)


def _union(rects: Iterable[Rect]) -> Rect | None:
    rects = list(rects)
    if not rects:
        return None
    x0, y0 = min(r.x for r in rects), min(r.y for r in rects)
    x1, y1 = max(r.x + r.w for r in rects), max(r.y + r.h for r in rects)
    return Rect(x0, y0, x1 - x0, y1 - y0)


def pane_for(cell_row: int, cell_col: int, frozen_rows: int, frozen_cols: int) -> int:
    """Which pane (1-4, Excel's order: top-left, top-right, bottom-left, bottom-right) shows a cell."""
    below = bool(frozen_rows) and cell_row > frozen_rows
    right = bool(frozen_cols) and cell_col > frozen_cols
    if frozen_rows and frozen_cols:
        return 1 + right + 2 * below
    return 1 + (below or right)


def split_area(area: Area, frozen_rows: int, frozen_cols: int) -> list[tuple[int, Area]]:
    """The pieces of a range that fall in each pane, in pane order."""
    def spans(lo: int, hi: int, cut: int) -> list[tuple[int, int]]:
        if not cut:
            return [(lo, hi)]
        return [(a, b) for a, b in ((lo, min(hi, cut)), (max(lo, cut + 1), hi)) if a <= b]
    return [(pane_for(top, left, frozen_rows, frozen_cols), replace(area, top=top, bottom=bottom, left=left, right=right))
            for top, bottom in spans(area.top, area.bottom, frozen_rows)
            for left, right in spans(area.left, area.right, frozen_cols)]


def spot_rect(pieces: Iterable[tuple[PaneInfo, float, float, float, float]]) -> Rect | None:
    """The on-screen box around a range's pieces, each placed in its own pane and cut to what shows."""
    shown = (clip_to(cell_rect(pane, *geometry), pane.visible) for pane, *geometry in pieces)
    return _union(r for r in shown if r is not None)


def moved(old: Spot | None, new: Spot | None) -> bool:
    """True when the pointer should be told: it appeared, went, changed words, or moved 1 px or more."""
    if old is None or new is None:
        return (old is None) != (new is None)
    if old.bubble != new.bubble:
        return True
    return any(abs(a - b) >= 1 for a, b in zip(astuple(old.rect), astuple(new.rect)))


# ------------------------------------------------------------------ cells: Excel's numbers (COM thread)

def _pane_info(pane, zoom: float, px_per_pt: float, grid: Rect) -> PaneInfo:
    seen = pane.VisibleRange
    left, top = float(seen.Left), float(seen.Top)
    info = PaneInfo(float(pane.PointsToScreenPixelsX(left)), float(pane.PointsToScreenPixelsY(top)),
                    left, top, zoom, px_per_pt, grid)
    shows = clip_to(cell_rect(info, left, top, float(seen.Width), float(seen.Height)), grid)
    return replace(info, visible=shows or Rect(info.screen_x0, info.screen_y0, 0, 0))


def _grid_rect(hwnd: int) -> Rect:
    """The workbook's part of the window (cells, headings, scroll bars), or the whole window."""
    grid = windows.find_child(hwnd, "XLDESK", "EXCEL7")
    return windows.outer_rect(grid) if grid else windows.window_rect(hwnd)


def cell_spot(wb, hwnd: int, area: Area) -> Spot | None:
    """The range's box on screen, or None when none of it shows (scrolled away, or another sheet)."""
    win = wb.Windows(1)
    sheet = win.ActiveSheet
    zoom = float(win.Zoom) / 100
    px_per_pt = windows.dpi_scale(hwnd) * windows.BASE_DPI / POINTS_PER_INCH
    grid = _grid_rect(hwnd)
    frozen_rows = frozen_cols = 0
    if bool(win.FreezePanes):
        first = win.Panes.Item(1)
        if int(win.SplitRow):
            frozen_rows = int(first.ScrollRow) - 1 + int(win.SplitRow)
        if int(win.SplitColumn):
            frozen_cols = int(first.ScrollColumn) - 1 + int(win.SplitColumn)
        panes = {n: _pane_info(win.Panes.Item(n), zoom, px_per_pt, grid) for n in range(1, int(win.Panes.Count) + 1)}
    else:
        panes = {1: _pane_info(win.ActivePane, zoom, px_per_pt, grid)}   # a plain split scrolls as one
    pieces = []
    for n, part in split_area(area, frozen_rows, frozen_cols):
        if n in panes:
            cells = sheet.Range(part.a1)
            pieces.append((panes[n], float(cells.Left), float(cells.Top), float(cells.Width), float(cells.Height)))
    rect = spot_rect(pieces)
    return Spot(rect) if rect is not None else None


# ------------------------------------------------------------------ controls: by name (pure over a tree)

class Node(Protocol):
    """What the control search needs of a UI Automation element (app/win/uia.Element, or a fake)."""
    name: str
    control_type: str
    rect: Rect | None
    offscreen: bool
    selected: bool | None

    def descendants(self, kinds=None) -> Iterable[Node]: ...
    def parent(self) -> Node | None: ...
    def refresh(self) -> bool: ...


def _key(text: str) -> str:
    return "".join(text.translate(_ZERO_WIDTH).split()).casefold()


def _words(text: str) -> list[str]:
    return text.translate({k: " " for k in _ZERO_WIDTH}).casefold().split()


def same_name(a: str, b: str) -> bool:
    """Names match ignoring case, spacing and the invisible break marks Office puts in long labels."""
    return _key(a) == _key(b)


def _has_words(name: str, wanted: str) -> bool:
    have, want = _words(name), _words(wanted)
    return bool(want) and any(have[i:i + len(want)] == want for i in range(len(have) - len(want) + 1))


def _shown(node: Node) -> bool:
    return not node.offscreen and node.rect is not None


def _all(roots: Sequence[Node], kinds) -> list[Node]:
    return [n for root in roots for n in root.descendants(kinds)]


def _named(roots: Sequence[Node], kinds, name: str) -> tuple[list[Node], list[Node]]:
    """Elements named exactly `name`, and elements whose longer names contain its words."""
    every = _all(roots, kinds)
    exact = [n for n in every if same_name(n.name, name)]
    loose = [n for n in every if not same_name(n.name, name) and _has_words(n.name, name)]
    return exact, loose


def _group_of(node: Node) -> Node | None:
    for _ in range(_GROUP_DEPTH):
        node = node.parent()
        if node is None:
            return None
        if node.control_type == "Group":
            return node
    return None


def _dropdown(roots: Sequence[Node], group: Node) -> Node | None:
    """What a folded group shows instead of its buttons: a drop-down with the group's name."""
    for place in ([group], roots):
        for node in _all(place, _CLICKABLE):
            if same_name(node.name, group.name) and _shown(node):
                return node
    return group if _shown(group) else None


def _find_control(roots: Sequence[Node], path: str) -> tuple[Node, str] | None:
    parts = [p.strip() for p in path.split(">")]
    if len(parts) < 2 or not all(parts):
        return None
    tab_name, groups, name = parts[0], parts[1:-1], parts[-1]
    tabs = [n for n in _all(roots[:1], {"TabItem"}) if same_name(n.name, tab_name)]
    if not tabs:
        return None
    tab = tabs[0]                                     # the ribbon comes before the sheet tabs
    if tab.selected is False:
        return (tab, OPEN_FIRST) if _shown(tab) else None
    exact, loose = _named(roots, _CLICKABLE, name)
    for found in (exact, loose):
        for node in found:
            if _shown(node):
                return node, ""
    for node in exact + loose:                        # there, but hidden: its group is folded
        group = _group_of(node)
        drop = _dropdown(roots, group) if group is not None else None
        if drop is not None:
            return drop, OPEN_FIRST
    if groups:
        for node in _all(roots, _CLICKABLE):
            if same_name(node.name, groups[-1]) and _shown(node):
                return node, OPEN_FIRST
    return None


def find_target(roots: Sequence[Node], kind: str, ref: str) -> tuple[Node, str] | None:
    """The element to point at for a target, and the words to show ("" for the usual ones)."""
    if not roots:
        return None
    if kind == "control":
        return _find_control(roots, ref)
    if kind in ("formula_bar", "name_box"):
        wanted = "Formula Bar" if kind == "formula_bar" else "Name Box"
        found = [n for n in _all(roots[:1], _BOXES) if same_name(n.name, wanted) and _shown(n)]
        return (found[0], "") if found else None
    if kind == "sheet_tab":
        found = [n for n in _all(roots[:1], {"TabItem"}) if same_name(n.name, ref) and _shown(n)]
        return (found[-1], "") if found else None   # the sheet tabs come after the ribbon's
    raise ValueError(f"Excel cannot point at a {kind!r}")


def spot_of(found: tuple[Node, str] | None) -> Spot | None:
    if found is None or found[0].rect is None:
        return None
    return Spot(found[0].rect, found[1])


class ControlTracker:
    """Follows one named control cheaply: after one search, each look only re-reads its rectangle.

    It searches again when the element goes or leaves the screen, and every few looks while it points
    at a route or at nothing, so it notices the learner opening the tab or the drop-down.
    """

    def __init__(self, roots: Callable[[], Sequence[Node]], kind: str, ref: str) -> None:
        self._roots = roots
        self._kind = kind
        self._ref = ref
        self._node: Node | None = None
        self._bubble = ""
        self._looked = False
        self._ticks = 0

    def spot(self) -> Spot | None:
        self._ticks += 1
        due = self._ticks >= ROUTE_REFIND_TICKS
        if self._looked:
            if self._node is not None and not (self._bubble and due):
                if self._node.refresh() and _shown(self._node):
                    return Spot(self._node.rect, self._bubble)
            elif self._node is None and not due:
                return None
        found = find_target(self._roots(), self._kind, self._ref)
        self._node, self._bubble = found if found is not None else (None, "")
        self._looked = True
        self._ticks = 0
        return spot_of(found)


class _CellTracker:
    """A cell or range: Excel is asked afresh on every look, since scrolling fires no event."""

    def __init__(self, wb, hwnd: int, ref: str) -> None:
        self._wb = wb
        self._hwnd = hwnd
        self._area = parse_area(ref)
        self._tab: ControlTracker | None = None

    def spot(self) -> Spot | None:
        shown = str(self._wb.Windows(1).ActiveSheet.Name)
        if self._area.sheet and self._area.sheet.casefold() != shown.casefold():
            if self._tab is None:
                self._tab = ControlTracker(lambda: _uia_roots(self._hwnd), "sheet_tab", self._area.sheet)
            tab = self._tab.spot()
            return Spot(tab.rect, OPEN_SHEET_FIRST) if tab is not None else None
        self._tab = None
        return cell_spot(self._wb, self._hwnd, self._area)


class _Nothing:
    def spot(self) -> None:
        return None


def _uia_roots(hwnd: int):
    from app.win import uia
    return uia.roots_for(hwnd)


def tracker_for(target: Target, app, wb, hwnd: int):
    """Something whose spot() says where the target is now (None when it isn't on screen)."""
    if not hwnd:
        return _Nothing()                               # an invisible Excel shows nothing
    if target.kind in ("cell", "range"):
        return _CellTracker(wb, hwnd, target.ref)
    if target.kind in ("control", "formula_bar", "name_box", "sheet_tab"):
        return ControlTracker(lambda: _uia_roots(hwnd), target.kind, target.ref)
    raise ValueError(f"Excel cannot point at a {target.kind!r}")


# ------------------------------------------------------------------ the vision fallback

def confirm_vision(rect: Rect, target: Target) -> bool:
    """Trust a rectangle from a picture only if UI Automation finds the named control at its centre."""
    from app.win import uia
    name = target.ref.split(">")[-1].strip()
    node: Any = uia.element_at(*rect.center)
    for _ in range(_GROUP_DEPTH):
        if node is None:
            return False
        if same_name(node.name, name) or _has_words(node.name, name):
            return True
        node = node.parent()
    return False


def background(fn: Callable[[], None]) -> None:
    """Run slow work (asking a model about a picture) away from the COM thread."""
    threading.Thread(target=fn, name="excel-vision", daemon=True).start()
