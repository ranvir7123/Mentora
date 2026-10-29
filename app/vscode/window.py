"""Finding the lesson's VS Code window, and the few things done to it.

The lesson's settings fix VS Code's window title to "<file> - <folder> - Visual Studio Code" (see
session.SETTINGS), so the window is the one whose title names the lesson's folder. Moving the window
uses app/win/windows.py, shared with Excel; it is imported only when needed.
"""
from __future__ import annotations

import ctypes

import win32con
import win32gui

from app.core.types import Rect

WINDOW_CLASS = "Chrome_WidgetWin_1"
APP_NAME = "Visual Studio Code"
PER_MONITOR_AWARE_V2 = -4          # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
BASE_DPI = 96

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
_user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
_user32.GetDpiForWindow.restype = ctypes.c_uint
_user32.GetDpiForWindow.argtypes = [ctypes.c_void_p]


def is_lesson_title(title: str, folder_name: str) -> bool:
    """True for a VS Code window title that names this folder as its workspace."""
    if not folder_name or APP_NAME not in title:
        return False
    return f" - {folder_name.lower()} - " in f" - {title.lower()} - "


def find_lesson_window(folder_name: str) -> int:
    """The visible VS Code window showing this folder, or 0."""
    found: list[int] = []

    def visit(hwnd: int, _extra) -> bool:
        if (win32gui.IsWindowVisible(hwnd) and win32gui.GetClassName(hwnd) == WINDOW_CLASS
                and is_lesson_title(win32gui.GetWindowText(hwnd), folder_name)):
            found.append(hwnd)
        return True
    win32gui.EnumWindows(visit, None)
    return found[0] if found else 0


def is_window(hwnd: int) -> bool:
    return bool(hwnd) and bool(win32gui.IsWindow(hwnd))


def minimize(hwnd: int) -> None:
    win32gui.ShowWindow(hwnd, win32con.SW_SHOWMINNOACTIVE)


def dpi_aware_thread() -> None:
    """Make this thread see real pixels, for UI Automation's rectangles."""
    _user32.SetThreadDpiAwarenessContext(PER_MONITOR_AWARE_V2)


def dpi_scale(hwnd: int) -> float:
    dpi = _user32.GetDpiForWindow(hwnd)
    return dpi / BASE_DPI if dpi else 1.0


def place(hwnd: int, rect: Rect) -> None:
    try:
        from app.win import windows
    except ImportError as exc:
        raise RuntimeError("moving VS Code's window needs app/win/windows.py from the Excel work") from exc
    windows.place_window(hwnd, rect)
