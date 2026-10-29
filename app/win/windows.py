"""Where a window is on screen, and moving it, in physical pixels.

Two facts measured on this laptop (1280 px wide at 200%) in the earlier project shape this file:
- A thread that is not per-monitor DPI aware gets every rectangle at half size. dpi_aware_thread()
  is called first on any thread that measures or moves windows.
- A window is wider than what you see: Windows 11 adds invisible borders (11 px a side at 200%) for
  grabbing the edge. window_rect() is the visible frame; place_window() grows the target by the
  borders so the visible frame lands exactly on the rectangle asked for.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from app.core.types import Rect

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_dwmapi = ctypes.WinDLL("dwmapi")

PER_MONITOR_AWARE_V2 = -4          # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
DWMWA_EXTENDED_FRAME_BOUNDS = 9
MONITOR_DEFAULTTONEAREST = 2
SW_RESTORE = 9
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
BASE_DPI = 96


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


_user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
_user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
_user32.IsWindow.argtypes = [wintypes.HWND]
_user32.IsZoomed.argtypes = [wintypes.HWND]
_user32.IsIconic.argtypes = [wintypes.HWND]
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetDpiForWindow.argtypes = [wintypes.HWND]
_user32.GetDpiForWindow.restype = wintypes.UINT
_user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
_user32.MonitorFromWindow.restype = wintypes.HMONITOR
_user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MonitorInfo)]
_user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, wintypes.UINT]
_dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p,
                                          wintypes.DWORD]


def _rect(r: wintypes.RECT) -> Rect:
    return Rect(r.left, r.top, r.right - r.left, r.bottom - r.top)


def dpi_aware_thread() -> None:
    """Make this thread see real pixels. Safe to call more than once."""
    _user32.SetThreadDpiAwarenessContext(PER_MONITOR_AWARE_V2)


def is_window(hwnd: int) -> bool:
    return bool(hwnd) and bool(_user32.IsWindow(hwnd))


def outer_rect(hwnd: int) -> Rect:
    """The whole window, invisible borders included."""
    r = wintypes.RECT()
    if not _user32.GetWindowRect(hwnd, ctypes.byref(r)):
        raise ctypes.WinError(ctypes.get_last_error())
    return _rect(r)


def window_rect(hwnd: int) -> Rect:
    """What the learner sees of the window: the frame without the invisible borders."""
    r = wintypes.RECT()
    if _dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r),
                                     ctypes.sizeof(r)) != 0:
        return outer_rect(hwnd)
    return _rect(r)


def dpi_scale(hwnd: int) -> float:
    """2.0 at 200% scaling."""
    dpi = _user32.GetDpiForWindow(hwnd)
    return dpi / BASE_DPI if dpi else 1.0


def work_area(hwnd: int) -> Rect:
    """The screen the window is on, without the taskbar."""
    info = _MonitorInfo()
    info.cbSize = ctypes.sizeof(info)
    monitor = _user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if not monitor or not _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    return _rect(info.rcWork)


def outer_rect_for(want: Rect, window: Rect, frame: Rect) -> Rect:
    """The whole-window rectangle that puts the visible frame on `want`.

    `window` and `frame` are the window's current outer and visible rectangles; their difference
    is the invisible border on each side.
    """
    left = frame.x - window.x
    top = frame.y - window.y
    right = (window.x + window.w) - (frame.x + frame.w)
    bottom = (window.y + window.h) - (frame.y + frame.h)
    return Rect(want.x - left, want.y - top, want.w + left + right, want.h + top + bottom)


def place_window(hwnd: int, rect: Rect) -> None:
    """Put the window's visible frame on `rect` without bringing it to the front."""
    if _user32.IsZoomed(hwnd) or _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, SW_RESTORE)       # a maximised window ignores SetWindowPos
    outer = outer_rect_for(rect, outer_rect(hwnd), window_rect(hwnd))
    if not _user32.SetWindowPos(hwnd, None, round(outer.x), round(outer.y), round(outer.w),
                                round(outer.h), SWP_NOZORDER | SWP_NOACTIVATE):
        raise ctypes.WinError(ctypes.get_last_error())
