"""Where a window is on screen, and moving it, in physical pixels.

Two facts measured on this laptop (1280 px wide at 200%) in the earlier project shape this file:
- A thread that is not per-monitor DPI aware gets every rectangle at half size. dpi_aware_thread()
  is called first on any thread that measures or moves windows.
- A window is wider than what you see: Windows 11 adds invisible borders (11 px a side at 200%) for
  grabbing the edge. window_rect() is the visible frame; place_window() grows the target by the
  borders so the visible frame lands exactly on the rectangle asked for.

location_hook() tells a thread when a window moves; it needs the thread to pump messages, as the
COM thread does. screenshot_png() takes a picture of part of the screen, for the vision fallback.
open_process() and end_process() let a session end its own Excel when that Excel will not quit.
"""
from __future__ import annotations

import ctypes
import struct
import zlib
from ctypes import wintypes
from typing import Callable

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
EVENT_OBJECT_LOCATIONCHANGE = 0x800B
WINEVENT_OUTOFCONTEXT = 0x0000
OBJID_WINDOW = 0
CHILDID_SELF = 0
SRCCOPY, CAPTUREBLT = 0x00CC0020, 0x40000000
DIB_RGB_COLORS = 0
PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


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
_user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
_user32.FindWindowExW.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
_WINEVENTPROC = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG,
                                   wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
_user32.SetWinEventHook.argtypes = [wintypes.UINT, wintypes.UINT, wintypes.HMODULE, _WINEVENTPROC,
                                    wintypes.DWORD, wintypes.DWORD, wintypes.UINT]
_user32.SetWinEventHook.restype = wintypes.HANDLE
_user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
_user32.GetDC.argtypes = [wintypes.HWND]
_user32.GetDC.restype = wintypes.HDC
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = wintypes.HDC
_gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
_gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
_gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
_gdi32.SelectObject.restype = wintypes.HGDIOBJ
_gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                          wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
_gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                             ctypes.c_void_p, wintypes.UINT]
_gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
_gdi32.DeleteDC.argtypes = [wintypes.HDC]
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_kernel32.OpenProcess.restype = wintypes.HANDLE
_kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                 ctypes.POINTER(wintypes.DWORD)]
_kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


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


def find_child(hwnd: int, *classes: str) -> int:
    """The child window reached by following window classes down, e.g. ("XLDESK", "EXCEL7"); 0 if none."""
    for name in classes:
        hwnd = _user32.FindWindowExW(hwnd, None, name, None) or 0
        if not hwnd:
            return 0
    return hwnd


def process_windows(hwnd: int) -> list[int]:
    """The other visible top-level windows of hwnd's program: its pop-ups and opened drop-downs."""
    pid = process_id(hwnd)
    return [w for w in program_windows(pid) if w != hwnd] if pid else []


def program_windows(pid: int) -> list[int]:
    """Every visible top-level window of program `pid`."""
    found: list[int] = []

    def visit(other, _lparam) -> bool:
        owner = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(other, ctypes.byref(owner))
        if owner.value == pid and _user32.IsWindowVisible(other):
            found.append(other)
        return True
    _user32.EnumWindows(_WNDENUMPROC(visit), 0)
    return found


def class_name(hwnd: int) -> str:
    """The kind of window, as Windows names it; each Excel workbook window is an XLMAIN."""
    buf = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(hwnd, buf, len(buf))
    return buf.value


def process_id(hwnd: int) -> int:
    """The number of the program that owns hwnd; 0 when there is no such window."""
    pid = wintypes.DWORD()
    if hwnd:
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def open_process(pid: int, named: str | None = None) -> int:
    """A handle that lets that program be ended later; 0 if there is none or it is not called `named`.

    While the handle is held it names that one program, even after the program has gone and its
    number has been given to another.
    """
    if not pid:
        return 0
    handle = _kernel32.OpenProcess(PROCESS_TERMINATE | PROCESS_QUERY_LIMITED_INFORMATION, False, pid) or 0
    if handle and named is not None and _program_file(handle).lower() != named.lower():
        _kernel32.CloseHandle(handle)
        return 0
    return handle


def _program_file(handle: int) -> str:
    size = wintypes.DWORD(1024)
    buf = ctypes.create_unicode_buffer(size.value)
    if not _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
        return ""
    return buf.value.rsplit("\\", 1)[-1]


def end_process(handle: int) -> None:
    """End the program at once, as Task Manager's End task does."""
    if not _kernel32.TerminateProcess(handle, 1):
        raise ctypes.WinError(ctypes.get_last_error())


def close_handle(handle: int) -> None:
    _kernel32.CloseHandle(handle)


def location_hook(hwnd: int, fn: Callable[[], None]) -> Callable[[], None]:
    """Call fn on this thread whenever hwnd moves or changes size; returns the function that stops it."""
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

    def on_event(_hook, _event, event_hwnd, id_object, id_child, _thread, _time) -> None:
        if event_hwnd == hwnd and id_object == OBJID_WINDOW and id_child == CHILDID_SELF:
            fn()
    proc = _WINEVENTPROC(on_event)
    handle = _user32.SetWinEventHook(EVENT_OBJECT_LOCATIONCHANGE, EVENT_OBJECT_LOCATIONCHANGE, None, proc,
                                     pid.value, 0, WINEVENT_OUTOFCONTEXT)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())

    def stop(_keep_alive=proc) -> None:       # holding proc here keeps Windows' callback valid
        _user32.UnhookWinEvent(handle)
    return stop


def png_bytes(width: int, height: int, bgra: bytes) -> bytes:
    """A PNG of a top-down picture given as blue, green, red, alpha bytes per pixel."""
    rgba = bytearray(bgra)
    rgba[0::4], rgba[2::4] = bgra[2::4], bgra[0::4]
    stride = width * 4
    raw = b"".join(b"\x00" + bytes(rgba[y * stride:(y + 1) * stride]) for y in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 6))
            + chunk(b"IEND", b""))


def screenshot_png(rect: Rect) -> bytes:
    """A picture of this part of the screen as PNG bytes, in physical pixels."""
    x, y, w, h = round(rect.x), round(rect.y), round(rect.w), round(rect.h)
    screen = _user32.GetDC(None)
    memory = _gdi32.CreateCompatibleDC(screen)
    bitmap = _gdi32.CreateCompatibleBitmap(screen, w, h)
    old = _gdi32.SelectObject(memory, bitmap)
    try:
        if not _gdi32.BitBlt(memory, 0, 0, w, h, screen, x, y, SRCCOPY | CAPTUREBLT):
            raise ctypes.WinError(ctypes.get_last_error())
        info = _BitmapInfoHeader(ctypes.sizeof(_BitmapInfoHeader), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        if _gdi32.GetDIBits(memory, bitmap, 0, h, buf, ctypes.byref(info), DIB_RGB_COLORS) != h:
            raise ctypes.WinError(ctypes.get_last_error())
        return png_bytes(w, h, buf.raw)
    finally:
        _gdi32.SelectObject(memory, old)
        _gdi32.DeleteObject(bitmap)
        _gdi32.DeleteDC(memory)
        _user32.ReleaseDC(None, screen)
