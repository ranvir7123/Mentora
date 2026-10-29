"""Windows UI Automation: the names and places of an app's buttons, tabs and boxes.

Excel's ribbon is drawn by Excel itself, not made of windows, so the way to find "Insert > Pie" on
screen is UI Automation, the accessibility layer screen readers use. A search fetches every element
of the wanted kinds with its name, kind, rectangle and on-screen flag in one call into the app,
instead of one call per property.

Everything here runs on the thread that first used it (the COM thread). That thread must be per-monitor
DPI aware, or every rectangle comes back at half size on a 200% screen.
"""
from __future__ import annotations

import threading
from typing import Iterable, Iterator

from app.core.types import Rect
from app.win import windows

_KINDS = {50000: "Button", 50002: "CheckBox", 50003: "ComboBox", 50004: "Edit", 50005: "Hyperlink",
          50007: "ListItem", 50008: "List", 50009: "Menu", 50011: "MenuItem", 50013: "RadioButton",
          50018: "Tab", 50019: "TabItem", 50020: "Text", 50021: "ToolBar", 50025: "Custom", 50026: "Group",
          50028: "DataGrid", 50029: "DataItem", 50031: "SplitButton", 50032: "Window", 50033: "Pane"}
_KIND_IDS = {name: number for number, name in _KINDS.items()}

_local = threading.local()


class _Client:
    def __init__(self) -> None:
        import comtypes.client
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as UIA
        self.UIA = UIA
        self.uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
        self.cache = self.uia.CreateCacheRequest()
        for prop in (UIA.UIA_NamePropertyId, UIA.UIA_ControlTypePropertyId, UIA.UIA_BoundingRectanglePropertyId,
                     UIA.UIA_IsOffscreenPropertyId, UIA.UIA_IsSelectionItemPatternAvailablePropertyId,
                     UIA.UIA_SelectionItemIsSelectedPropertyId):
            self.cache.AddProperty(prop)
        self.walker = self.uia.ControlViewWalker

    def kinds_condition(self, kinds: Iterable[str] | None):
        ids = sorted(_KIND_IDS[k] for k in kinds) if kinds else []
        if not ids:
            return self.uia.CreateTrueCondition()
        cond = self.uia.CreatePropertyCondition(self.UIA.UIA_ControlTypePropertyId, ids[0])
        for number in ids[1:]:
            cond = self.uia.CreateOrCondition(
                cond, self.uia.CreatePropertyCondition(self.UIA.UIA_ControlTypePropertyId, number))
        return cond


def _client() -> _Client:
    client = getattr(_local, "client", None)
    if client is None:
        client = _local.client = _Client()
    return client


def _rect(r) -> Rect | None:
    if r.right <= r.left or r.bottom <= r.top:
        return None
    return Rect(r.left, r.top, r.right - r.left, r.bottom - r.top)


class Element:
    """One UI Automation element, read once; refresh() reads where it is now."""

    def __init__(self, raw) -> None:
        c = _client()
        self._raw = raw
        self.name = str(raw.CachedName or "")
        kind = int(raw.CachedControlType)
        self.control_type = _KINDS.get(kind, str(kind))
        self.rect = _rect(raw.CachedBoundingRectangle)
        self.offscreen = bool(raw.CachedIsOffscreen)
        selectable = raw.GetCachedPropertyValue(c.UIA.UIA_IsSelectionItemPatternAvailablePropertyId)
        self.selected = (bool(raw.GetCachedPropertyValue(c.UIA.UIA_SelectionItemIsSelectedPropertyId))
                         if selectable is True else None)

    def descendants(self, kinds: Iterable[str] | None = None) -> Iterator[Element]:
        c = _client()
        found = self._raw.FindAllBuildCache(c.UIA.TreeScope_Descendants, c.kinds_condition(kinds), c.cache)
        for i in range(found.Length):
            yield Element(found.GetElement(i))

    def parent(self) -> Element | None:
        c = _client()
        raw = c.walker.GetParentElementBuildCache(self._raw, c.cache)
        return Element(raw) if raw else None

    def refresh(self) -> bool:
        """Read the rectangle and on-screen flag again; False once the element is gone."""
        try:
            self.rect = _rect(self._raw.CurrentBoundingRectangle)
            self.offscreen = bool(self._raw.CurrentIsOffscreen)
        except Exception:   # noqa: BLE001 - UIA_E_ELEMENTNOTAVAILABLE and friends: it has gone
            return False
        return True

    def __repr__(self) -> str:
        return f"Element({self.control_type}, {self.name!r}, {self.rect}, offscreen={self.offscreen})"


def roots_for(hwnd: int) -> list[Element]:
    """The app's main window, then its other visible windows (an opened ribbon drop-down is one)."""
    c = _client()
    roots = [Element(c.uia.ElementFromHandleBuildCache(hwnd, c.cache))]
    for other in windows.process_windows(hwnd):
        try:
            roots.append(Element(c.uia.ElementFromHandleBuildCache(other, c.cache)))
        except Exception:   # noqa: BLE001 - a pop-up that closed while we looked
            continue
    return roots


def element_at(x: float, y: float) -> Element | None:
    """The element under a screen point, in physical pixels."""
    c = _client()
    try:
        raw = c.uia.ElementFromPointBuildCache(c.UIA.tagPOINT(round(x), round(y)), c.cache)
    except Exception:   # noqa: BLE001 - nothing there that UI Automation can describe
        return None
    return Element(raw) if raw else None
