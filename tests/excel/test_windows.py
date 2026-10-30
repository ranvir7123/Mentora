import ctypes
import os
import struct
import subprocess
import sys
import zlib

from app.core.types import Rect
from ctypes import wintypes

from app.win.windows import (class_name, close_handle, end_process, open_process, outer_rect_for, owner,
                             png_bytes, process_id, program_windows)


def test_a_program_can_be_ended_through_the_handle_kept_on_it():
    # The real python.exe, not the venv's stand-in, which would start a second program and end only itself.
    child = subprocess.Popen([os.path.join(sys.base_exec_prefix, "python.exe"), "-c", "import time; time.sleep(30)"],
                             creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        assert open_process(child.pid, named="excel.exe") == 0     # a program of another name is never held
        handle = open_process(child.pid, named="PYTHON.EXE")
        assert handle
        end_process(handle)
        assert child.wait(5) == 1
        close_handle(handle)
    finally:
        child.kill()                             # only matters if something above failed


def test_no_window_means_no_program():
    assert process_id(0) == 0 and open_process(0) == 0


def test_a_window_is_listed_under_its_program():
    desktop_shell = ctypes.windll.user32.GetShellWindow()      # the desktop, always there while Windows runs
    assert desktop_shell in program_windows(process_id(desktop_shell))


def test_a_window_names_the_window_that_owns_it():
    # Two hidden pop-up windows, the second owned by the first, as an Excel dialog box is owned by Excel.
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                       wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    popup = 0x80000000                           # WS_POPUP, and no WS_VISIBLE: nothing shows on screen
    top = user32.CreateWindowExW(0, "STATIC", "owner", popup, 0, 0, 10, 10, None, None, None, None)
    owned = user32.CreateWindowExW(0, "STATIC", "owned", popup, 0, 0, 10, 10, top, None, None, None)
    try:
        assert top and owned
        assert owner(owned) == top
        assert owner(top) == 0
        assert owner(0) == 0
    finally:
        user32.DestroyWindow(owned)
        user32.DestroyWindow(top)


def test_a_window_kind_is_read():
    assert class_name(ctypes.windll.user32.GetDesktopWindow()) == "#32769"


def test_the_window_is_grown_by_its_invisible_borders():
    # measured in the earlier project at 200%: GetWindowRect (1840,0)-(2560,1504), visible (1851,0)-(2549,1493)
    window = Rect(1840, 0, 720, 1504)
    frame = Rect(1851, 0, 698, 1493)
    want = Rect(0, 0, 1840, 1500)
    assert outer_rect_for(want, window, frame) == Rect(-11, 0, 1862, 1511)


def test_no_borders_means_the_same_rectangle():
    r = Rect(10, 20, 300, 400)
    assert outer_rect_for(Rect(0, 0, 100, 100), r, r) == Rect(0, 0, 100, 100)


def test_a_screenshot_is_a_png_with_its_colours_in_the_right_order():
    png = png_bytes(2, 1, bytes([255, 0, 0, 255, 0, 0, 255, 255]))      # a blue pixel, then a red one
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", png[16:24]) == (2, 1)
    start = png.index(b"IDAT") + 4
    size = struct.unpack(">I", png[start - 8:start - 4])[0]
    assert zlib.decompress(png[start:start + size]) == bytes([0, 0, 0, 255, 255, 255, 0, 0, 255])
