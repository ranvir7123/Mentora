import pytest
import win32api
import win32con
import win32gui

from app.ui import winstyle
from app.ui.bridge import Bridge
from app.ui.demo_backend import DemoBackend

_CLASS = "MentoraStyleTest"


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


def test_done_asking_the_keyboard_goes_back_to_the_app(qapp, hwnd, monkeypatch):
    # Which window has the keyboard is played out here: a test can't move the real keyboard between programs.
    excel = 0x1234
    front = {"now": excel}
    given = []
    monkeypatch.setattr(winstyle, "foreground", lambda: front["now"])
    monkeypatch.setattr(winstyle, "give_keyboard_to", given.append)
    bridge = Bridge(DemoBackend("lesson_step"))
    bridge.set_panel_window(hwnd)
    bridge.askFocused(True)             # pressed into the Ask box while Excel had the keyboard
    front["now"] = hwnd                 # the panel came forward for the typing
    bridge.askFocused(True)
    bridge.askFocused(False)            # sent, Escape, or a press elsewhere in the panel
    assert given == [excel]
    assert winstyle.ex_style(hwnd) & winstyle.WS_EX_NOACTIVATE
    front["now"] = excel                # this time the learner clicked back into Excel themselves
    bridge.askFocused(True)
    bridge.askFocused(False)
    assert given == [excel], "the keyboard is already back; nothing to hand over"


def test_the_keyboard_is_never_handed_to_a_window_that_has_closed():
    assert winstyle.give_keyboard_to(0) is False
    assert isinstance(winstyle.foreground(), int)
