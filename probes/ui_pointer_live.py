"""Live check on the real screen: the pointer lets clicks through and the panel never takes focus.

    <py> probes\\ui_pointer_live.py

Opens the lesson panel and the pointer overlay on demo data (the mascot lands beside a cell, the ring
pulses), exactly as the program does, then asks Windows, without moving the mouse or typing:

- which window a click on the mascot and on the ring would reach: it must be the window underneath, not ours
- which window a click on the panel would reach: ours (this shows the check can see our windows at all)
- whether the window you were using is still the one with the keyboard after the panel opens, and again
  after it closes and opens
- the overlay's and the panel's Windows style bits

Prints one line per check and PASS or FAIL. Closes itself after about two seconds.
"""
from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402,F401  (so windows come back as Quick windows)

from app.core.types import Rect  # noqa: E402
from app.ui import landing, winstyle  # noqa: E402
from app.ui.app import attach_window, load_window, make_engine  # noqa: E402
from app.ui.bridge import Bridge  # noqa: E402
from app.ui.demo_backend import DemoBackend  # noqa: E402

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.WindowFromPoint.restype = wintypes.HWND
_user32.WindowFromPoint.argtypes = (wintypes.POINT,)
_user32.GetAncestor.restype = wintypes.HWND
_user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
_user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
_user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
GA_ROOT = 2


def _settle(app: QGuiApplication, ms: int) -> None:
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.005)


def _owner(hwnd) -> tuple[int, str]:
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    name = ctypes.create_unicode_buffer(128)
    _user32.GetClassNameW(hwnd, name, 128)
    return pid.value, name.value


def _under(x: float, y: float) -> tuple[int, str]:
    """The process and window class a click at physical (x, y) would reach."""
    hwnd = _user32.WindowFromPoint(wintypes.POINT(round(x), round(y)))
    return _owner(_user32.GetAncestor(hwnd, GA_ROOT) or hwnd)


def _physical(window, p: QPointF) -> tuple[float, float]:
    screen = window.screen()
    origin = screen.geometry().topLeft()
    r = landing.to_physical(Rect(p.x(), p.y(), 0, 0), (origin.x(), origin.y()), screen.devicePixelRatio())
    return r.x, r.y


def _find(item, prefix: str):
    if item.metaObject().className().startswith(prefix):
        return item
    for child in item.childItems():
        found = _find(child, prefix)
        if found is not None:
            return found
    return None


def main() -> int:
    app = QGuiApplication(sys.argv)
    if QGuiApplication.platformName() != "windows":
        print(f"FAIL: this check needs the real Windows screen, not {QGuiApplication.platformName()!r}")
        return 1
    before = _user32.GetForegroundWindow()
    print(f"the window you were using: {_owner(before)[1]!r} of process {_owner(before)[0]}")

    bridge = Bridge(DemoBackend("pointer_watching"))
    engine = make_engine(bridge)
    windows = {}
    for name in ("panel", "overlay"):
        windows[name] = load_window(engine, name)
        if windows[name] is None:
            print(f"FAIL: the {name} did not load")
            return 1
        attach_window(bridge, name, windows[name])
    try:
        checks = _measure(app, bridge, windows["panel"], windows["overlay"], before)
    finally:
        if _user32.GetForegroundWindow() != before:
            _user32.SetForegroundWindow(before)    # hand the keyboard back to the window you were using
        for window in windows.values():
            window.close()
        _settle(app, 100)

    for what, ok, detail in checks:
        print(f"{'yes' if ok else 'NO '}  {what} ({detail})")
    passed = all(ok for _, ok, _ in checks)
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


def _measure(app, bridge, panel, overlay, before) -> list[tuple[str, bool, str]]:
    me = os.getpid()
    _settle(app, 1500)                       # the mascot has flown out and landed
    checks = []
    focus = _user32.GetForegroundWindow()
    checks.append(("the panel opened without taking the keyboard", focus == before,
                   f"now {_owner(focus)[1]!r} of process {_owner(focus)[0]}"))

    over, pane = winstyle.ex_style(int(overlay.winId())), winstyle.ex_style(int(panel.winId()))
    checks.append(("the overlay lets clicks through and never takes focus",
                   over & winstyle.CLICK_THROUGH == winstyle.CLICK_THROUGH, f"style {over:#x}"))
    checks.append(("the panel never takes focus when clicked", bool(pane & winstyle.WS_EX_NOACTIVATE),
                   f"style {pane:#x}"))

    mascot = _find(overlay.contentItem(), "Mascot")
    size = mascot.property("size")
    centre = _physical(overlay, mascot.mapToGlobal(QPointF(size / 2, size / 2)))
    pid, cls = _under(*centre)
    checks.append(("a click on the mascot reaches the window underneath", pid != me,
                   f"at {centre[0]:.0f},{centre[1]:.0f}: {cls!r} of process {pid}"))

    target = bridge.pointerRect                # logical; the ring's band runs 1 to 4 px outside it
    ring = _physical(overlay, QPointF(target.x() - 2.5, target.y() + target.height() / 2))
    pid, cls = _under(*ring)
    checks.append(("a click on the ring reaches the window underneath", pid != me,
                   f"at {ring[0]:.0f},{ring[1]:.0f}: {cls!r} of process {pid}"))

    g = panel.geometry()
    middle = _physical(panel, QPointF(g.x() + g.width() / 2, g.y() + g.height() / 2))
    pid, cls = _under(*middle)
    checks.append(("a click on the panel reaches the panel (the check can see our windows)", pid == me,
                   f"at {middle[0]:.0f},{middle[1]:.0f}: {cls!r} of process {pid}"))

    panel.hide()
    _settle(app, 200)
    panel.show()
    _settle(app, 300)
    focus = _user32.GetForegroundWindow()
    checks.append(("the panel opened again without taking the keyboard", focus == before,
                   f"now {_owner(focus)[1]!r} of process {_owner(focus)[0]}"))
    return checks


if __name__ == "__main__":
    sys.exit(main())
