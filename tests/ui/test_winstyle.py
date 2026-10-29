import pytest
import win32api
import win32con
import win32gui

from app.ui import winstyle
from app.ui.bridge import Bridge
from app.ui.demo_backend import DemoBackend

_CLASS = "ProjectXStyleTest"


@pytest.fixture
def hwnd():
    """A plain top-level window of our own, never shown, so its style bits are real Windows bits."""
    try:
        wc = win32gui.WNDCLASS()
        wc.lpszClassName = _CLASS
        wc.lpfnWndProc = {}
        wc.hInstance = win32api.GetModuleHandle(None)
        win32gui.RegisterClass(wc)
    except win32gui.error:
        pass                                    # already registered by an earlier test
    handle = win32gui.CreateWindowEx(0, _CLASS, "style test", win32con.WS_OVERLAPPEDWINDOW,
                                     0, 0, 100, 100, 0, 0, win32api.GetModuleHandle(None), None)
    yield handle
    win32gui.DestroyWindow(handle)


CLICK_THROUGH = (win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOOLWINDOW
                 | winstyle.WS_EX_NOACTIVATE)


def test_click_through_style_bits(hwnd):
    assert winstyle.ex_style(hwnd) & CLICK_THROUGH == 0
    winstyle.make_click_through(hwnd)
    assert winstyle.ex_style(hwnd) & CLICK_THROUGH == CLICK_THROUGH


def test_no_activate_turns_on_and_off(hwnd):
    winstyle.make_no_activate(hwnd, True)
    assert winstyle.ex_style(hwnd) & winstyle.WS_EX_NOACTIVATE
    winstyle.make_no_activate(hwnd, False)
    assert not winstyle.ex_style(hwnd) & winstyle.WS_EX_NOACTIVATE


def test_a_window_of_another_program_is_never_touched():
    desktop = win32gui.GetDesktopWindow()      # owned by Windows, not by us
    before = winstyle.ex_style(desktop)
    with pytest.raises(ValueError):
        winstyle.make_click_through(desktop)
    assert winstyle.ex_style(desktop) == before


def test_panel_never_takes_focus_except_the_ask_box(qapp, hwnd):
    bridge = Bridge(DemoBackend("lesson_step"))
    bridge.set_panel_window(hwnd)
    assert winstyle.ex_style(hwnd) & winstyle.WS_EX_NOACTIVATE           # clicks never pull focus off Excel
    bridge.askFocused(True)
    assert not winstyle.ex_style(hwnd) & winstyle.WS_EX_NOACTIVATE       # typing a question needs the keyboard
    bridge.askFocused(False)
    assert winstyle.ex_style(hwnd) & winstyle.WS_EX_NOACTIVATE
