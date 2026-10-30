"""Where VS Code's parts are on screen, read through Windows UI Automation.

VS Code draws its window with Chromium, which describes the page to UI Automation: each element has a
control type, a name and, from the page's HTML, a class name. One read takes the whole list in a
single call (a cache request) and `pick` chooses from it, so the choosing is plain code that tests
can drive. A read is kept for READ_EVERY_S, because the pointer asks ten times a second.

Chromium describes the page only once someone asks: in real VS Code the first read held just the
window's frame (13 parts), and a read 0.28 s later held the whole page (281). So the first ask for a
window reads again until the page is there, for at most PAGE_WAIT_S.

What each kind is (probes/vscode_session.py prints what each one finds in the real VS Code):
- editor: the open file's text area, the element whose class list holds "monaco-editor" (the
  biggest one, since the search box and other small inputs are editors too).
- explorer_item: the file's row in the "Files Explorer" tree, or its top folder's row while the
  folder is shut.
- terminal: the terminal's text area (class "xterm").
- run_button: the Python add-on's "Run Python File" button, when the learner has it.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Iterable

from app.core.types import Rect

READ_EVERY_S = 0.5
PAGE_WAIT_S = 3.0

# UI Automation's numbers for what is read (UIAutomationClient.h).
TREE_SCOPE_DESCENDANTS = 4
NAME, CLASS_NAME, CONTROL_TYPE, RECT, OFFSCREEN = 30005, 30012, 30003, 30001, 30022
CONTROL_TYPES = {50000: "button", 50004: "edit", 50023: "tree", 50024: "tree_item", 50025: "custom",
                 50026: "group", 50030: "document", 50033: "pane", 50008: "list", 50020: "text"}
FILES_EXPLORER = "Files Explorer"


@dataclass(frozen=True)
class Element:
    control: str          # one of CONTROL_TYPES' names, or "other"
    name: str
    class_name: str
    rect: Rect


def _inside(inner: Rect, outer: Rect) -> bool:
    return (inner.x >= outer.x and inner.y >= outer.y and inner.x + inner.w <= outer.x + outer.w
            and inner.y + inner.h <= outer.y + outer.h)


def _area(e: Element) -> float:
    return e.rect.w * e.rect.h


def _classes(e: Element) -> set[str]:
    return set(e.class_name.split())


def _has_page(elements: list[Element]) -> bool:
    return any(e.control == "document" for e in elements)


def pick(elements: Iterable[Element], kind: str, ref: str) -> Rect | None:
    """The rectangle of `kind` (with `ref`, a file's path, where it needs one) among `elements`."""
    shown = [e for e in elements if e.rect.w > 0 and e.rect.h > 0]
    if kind == "editor":
        editors = [e for e in shown if "monaco-editor" in _classes(e)]
        return max(editors, key=_area).rect if editors else None
    if kind == "terminal":
        terminals = [e for e in shown if "xterm" in _classes(e)]
        return max(terminals, key=_area).rect if terminals else None
    if kind == "run_button":
        buttons = [e for e in shown if e.control == "button" and e.name.startswith("Run Python File")]
        return buttons[0].rect if buttons else None
    if kind == "explorer_item":
        trees = [e for e in shown if e.control == "tree" and e.name == FILES_EXPLORER]
        if not trees:
            return None
        rows = [e for e in shown if e.control == "tree_item" and _inside(e.rect, trees[0].rect)]
        parts = [p for p in ref.replace("\\", "/").split("/") if p and p != "."]
        for wanted in ([parts[-1], parts[0]] if len(parts) > 1 else parts):
            for row in rows:
                if row.name.lower() == wanted.lower():
                    return row.rect
        return None
    return None


class Finder:
    """Reads VS Code's elements through UI Automation. Call `find` from one thread only (the screen
    thread), after `init_thread` ran on it."""

    def __init__(self) -> None:
        self._uia = None
        self._cache_request = None
        self._read: tuple[float, int, list[Element]] | None = None
        self._asked: set[int] = set()           # windows whose page Chromium was asked for
        self._lock = threading.Lock()

    def init_thread(self) -> None:
        import comtypes
        import comtypes.client
        comtypes.CoInitializeEx(comtypes.COINIT_APARTMENTTHREADED)
        comtypes.client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient as uia
        self._uia = comtypes.client.CreateObject(uia.CUIAutomation, interface=uia.IUIAutomation)
        request = self._uia.CreateCacheRequest()
        for prop in (NAME, CLASS_NAME, CONTROL_TYPE, RECT, OFFSCREEN):
            request.AddProperty(prop)
        self._cache_request = request

    def find(self, hwnd: int, kind: str, ref: str) -> Rect | None:
        if self._uia is None or not hwnd:
            return None
        with self._lock:
            now = time.monotonic()
            if self._read is None or self._read[1] != hwnd or now - self._read[0] > READ_EVERY_S:
                elements = self._elements(hwnd)
                if hwnd not in self._asked:
                    self._asked.add(hwnd)
                    deadline = now + PAGE_WAIT_S
                    while not _has_page(elements) and time.monotonic() < deadline:
                        time.sleep(0.1)
                        elements = self._elements(hwnd)
                self._read = (time.monotonic(), hwnd, elements)
            elements = self._read[2]
        return pick(elements, kind, ref)

    def _elements(self, hwnd: int) -> list[Element]:
        try:
            root = self._uia.ElementFromHandle(hwnd)
            found = root.FindAllBuildCache(TREE_SCOPE_DESCENDANTS, self._uia.CreateTrueCondition(),
                                           self._cache_request)
        except Exception:                        # the window went away, or is busy: nothing to point at
            return []
        elements = []
        for i in range(found.Length if found else 0):
            e = found.GetElement(i)
            try:
                if e.CachedIsOffscreen:
                    continue
                r = e.CachedBoundingRectangle
                elements.append(Element(CONTROL_TYPES.get(e.CachedControlType, "other"), e.CachedName or "",
                                        e.CachedClassName or "", Rect(r.left, r.top, r.right - r.left, r.bottom - r.top)))
            except Exception:
                continue
        return elements
