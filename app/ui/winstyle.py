"""Windows settings for the screens' own windows.

The pointer overlay must let every click through to the app below and never take focus. The lesson panel
must take clicks without pulling the keyboard away from Excel, except while the learner types a question.
Only windows that belong to this program are ever changed; asking to change another program's window is
refused with ValueError.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x20          # clicks fall through to the window below
WS_EX_TOOLWINDOW = 0x80           # not in the taskbar or Alt+Tab
WS_EX_LAYERED = 0x80000           # see-through drawing (Qt draws see-through windows this way already)
WS_EX_NOACTIVATE = 0x8000000      # clicking it never takes focus from the app
CLICK_THROUGH = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE

_SWP_REFRESH = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020 | 0x0200   # no size, move, z-order or focus change

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
_user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
_user32.IsWindow.restype = wintypes.BOOL
_user32.IsWindow.argtypes = (wintypes.HWND,)
_user32.SetWindowPos.restype = wintypes.BOOL
_user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_int, wintypes.UINT)


def ex_style(hwnd: int) -> int:
    """The window's extended style bits."""
    return _user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE) & 0xFFFFFFFF


def _ours(hwnd: int) -> None:
    pid = wintypes.DWORD()
    if not _user32.IsWindow(hwnd) or not _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)) \
            or pid.value != os.getpid():
        raise ValueError(f"window {hwnd:#x} is not one of this program's windows")


def _change(hwnd: int, add: int = 0, remove: int = 0) -> None:
    _ours(hwnd)
    before = ex_style(hwnd)
    after = (before | add) & ~remove
    if after == before:
        return
    ctypes.set_last_error(0)
    if _user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, after) == 0 and ctypes.get_last_error():
        raise ctypes.WinError(ctypes.get_last_error())
    _user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, _SWP_REFRESH)     # so Windows notices at once


def make_click_through(hwnd: int) -> None:
    """Clicks pass through, never focused, not in the taskbar."""
    _change(hwnd, add=CLICK_THROUGH)


def make_no_activate(hwnd: int, on: bool) -> None:
    """While on, clicking the window works but never takes focus (or the keyboard) from the app."""
    _change(hwnd, add=WS_EX_NOACTIVATE if on else 0, remove=0 if on else WS_EX_NOACTIVATE)
