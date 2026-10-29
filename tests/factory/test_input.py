"""The parts of real input that never move the mouse or press a key."""
import struct
import sys
import types
import zlib

import pytest

from app.core.types import Rect
from app.factory import input as hands_module
from app.factory.input import (Shown, UserTookOver, WindowsHands, covers, encode_png, held_keys, owned_by, vk_for,
                               wheel_clicks)


def _chunks(png):
    at, chunks = 8, {}
    while at < len(png):
        (size,), kind = struct.unpack(">I", png[at:at + 4]), png[at + 4:at + 8]
        chunks[kind] = chunks.get(kind, b"") + png[at + 8:at + 8 + size]
        at += 12 + size
    return chunks


def test_a_screenshot_becomes_a_png_holding_its_pixels():
    # 2 x 2, as Windows hands them over (blue, green, red, unused): red, green / blue, (30, 20, 10)
    bgra = bytes([0, 0, 255, 0, 0, 255, 0, 0, 255, 0, 0, 0, 10, 20, 30, 0])
    png = encode_png(bgra, 2, 2)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    chunks = _chunks(png)
    assert struct.unpack(">IIBB", chunks[b"IHDR"][:10]) == (2, 2, 8, 2)        # 8-bit RGB
    assert zlib.decompress(chunks[b"IDAT"]) == (b"\x00" + bytes([255, 0, 0, 0, 255, 0])
                                                + b"\x00" + bytes([0, 0, 255, 30, 20, 10]))
    assert b"IEND" in chunks


@pytest.mark.parametrize("name, vk", [("ctrl", 0x11), ("CTRL", 0x11), ("Control", 0x11), ("Enter", 0x0D),
                                      ("Return", 0x0D), ("a", 0x41), ("Z", 0x5A), ("7", 0x37), ("F5", 0x74),
                                      ("ArrowDown", 0x28), ("down", 0x28), ("PageUp", 0x21), ("esc", 0x1B),
                                      ("space", 0x20), ("shift", 0x10), ("alt", 0x12), ("Delete", 0x2E)])
def test_key_names_become_windows_keys(name, vk):
    assert vk_for(name) == vk


def test_an_unknown_key_name_is_refused():
    with pytest.raises(ValueError, match="there is no key called hyper"):
        vk_for("hyper")


def test_keys_are_held_down_only_around_mouse_actions():
    assert held_keys({"type": "click", "x": 1, "y": 1, "keys": ["ctrl", "shift"]}) == [0x11, 0x10]
    assert held_keys({"type": "drag", "path": [], "keys": ["alt"]}) == [0x12]
    assert held_keys({"type": "type", "text": "x", "keys": ["win"]}) == []
    assert held_keys({"type": "wait", "keys": ["alt"]}) == []
    assert held_keys({"type": "keypress", "keys": ["ctrl", "a"]}) == []      # pressed in turn, not held around


APP_PID, APP_RECT = 40, Rect(0, 0, 1840, 1504)


def test_another_programs_window_over_the_app_covers_it():
    toast = Shown(process=7, bounds=Rect(1500, 1300, 700, 200))
    assert covers([toast], APP_PID, APP_RECT)
    assert covers([Shown(7, Rect(0, 1504, 2560, 96)), toast], APP_PID, APP_RECT)   # the taskbar, then a toast


def test_windows_that_show_nothing_over_the_app_do_not_cover_it():
    assert not covers([], APP_PID, APP_RECT)
    assert not covers([Shown(7, Rect(0, 1504, 2560, 96))], APP_PID, APP_RECT)       # the taskbar, just below
    assert not covers([Shown(7, Rect(1840, 0, 720, 1504))], APP_PID, APP_RECT)      # the lesson strip, beside it
    assert not covers([Shown(APP_PID, Rect(300, 300, 400, 300))], APP_PID, APP_RECT)  # the app's own dialog box
    assert not covers([Shown(7, Rect(0, 0, 500, 500), visible=False),
                       Shown(7, Rect(0, 0, 500, 500), cloaked=True),
                       Shown(7, Rect(0, 0, 500, 500), minimised=True)], APP_PID, APP_RECT)


def test_scroll_pixels_become_wheel_clicks():
    assert [wheel_clicks(p) for p in (0, 40, 100, 300, -50, -260)] == [0, 1, 1, 3, -1, -3]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows screenshots")
def test_a_real_screenshot_has_the_size_asked_for():
    png = WindowsHands().grab(Rect(0, 0, 128, 80), 64, 40)     # read-only: nothing is clicked or saved
    assert struct.unpack(">II", _chunks(png)[b"IHDR"][:8]) == (64, 40)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows windows")
def test_the_real_windows_above_one_can_be_read():
    import ctypes
    front = ctypes.WinDLL("user32").GetForegroundWindow()
    hands = WindowsHands()                                      # read-only: nothing is clicked or moved
    assert hands.covered(front, Rect(-100_000, -100_000, 10, 10)) is False   # nothing is that far off
    assert hands.in_front(front) is True
    assert hands.bounds(front).w > 0
    assert hands.app_at(front, -100_000, -100_000) is False                 # no window is there


def test_a_window_counts_as_the_apps_only_when_the_app_owns_it():
    app, dialog, picker, editor, other = 1, 2, 3, 4, 5
    owner = {dialog: app, picker: dialog, editor: 0, other: 0, 8: 9, 9: 8}.get
    assert owned_by(app, app, owner) and owned_by(dialog, app, owner)
    assert owned_by(picker, app, owner)                     # a box opened from a dialog box
    assert not owned_by(editor, app, owner)                 # the same program's own separate window, such as Excel's macro editor
    assert not owned_by(other, app, owner) and not owned_by(0, app, owner) and not owned_by(8, app, owner)


class FakeWindows:
    """Stands in for Windows under real hands: where the pointer is, and every input sent."""

    def __init__(self):
        self.at, self.sent, self.fail_at, self.failing_sends, self.on_send = (100, 100), [], None, 0, None

    def hands(self):
        hands = object.__new__(WindowsHands)             # no real Windows calls are made
        hands._user32, hands._cursor, hands._send, hands._last = self, lambda: self.at, self.send, self.at
        return hands

    def SetCursorPos(self, x, y):                        # as Windows' own function is called
        if (x, y) == self.fail_at:
            raise OSError("Windows would not move the pointer")
        self.at = (x, y)
        return True

    def send(self, inputs):
        if self.failing_sends:
            self.failing_sends -= 1
            self.sent.append(self._said(inputs[0]))      # Windows took only the first
            raise OSError("Windows blocked the test's input")
        self.sent += [self._said(i) for i in inputs]
        if self.on_send:
            self.on_send()

    @staticmethod
    def _said(i):
        if i.type == 0:
            return {0x0002: "left down", 0x0004: "left up"}.get(i.u.mi.dwFlags, i.u.mi.dwFlags)
        key = chr(i.u.ki.wScan) if i.u.ki.dwFlags & 0x0004 else i.u.ki.wVk
        return key, "up" if i.u.ki.dwFlags & 0x0002 else "down"

    def mouse(self):
        return [s for s in self.sent if isinstance(s, str)]


@pytest.fixture
def no_pauses(monkeypatch):
    pause = types.SimpleNamespace(sleep=lambda s: None)
    monkeypatch.setattr(hands_module, "time", pause)
    return pause


DRAG = {"type": "drag", "path": [{"x": 10, "y": 10}, {"x": 50, "y": 10}, {"x": 90, "y": 10}]}


def test_a_person_moving_the_mouse_while_an_action_finishes_stops_the_next_one(no_pauses):
    win = FakeWindows()
    hands = win.hands()
    no_pauses.sleep = lambda s: setattr(win, "at", (500, 500))   # during the pause after the click
    hands.do({"type": "click", "x": 200, "y": 200})

    with pytest.raises(UserTookOver, match="You moved the mouse"):
        hands.do({"type": "type", "text": "a"})
    assert ("a", "down") not in win.sent


def test_typing_stops_when_the_mouse_moves_between_letters(no_pauses):
    win = FakeWindows()
    hands = win.hands()
    win.on_send = lambda: setattr(win, "at", (500, 500))         # a person moves it as the first letter goes in

    with pytest.raises(UserTookOver):
        hands.do({"type": "type", "text": "abc"})
    assert [key for key, state in win.sent if state == "down"] == ["a"]


def test_a_drag_lets_go_of_the_button_when_a_person_takes_the_mouse(no_pauses):
    win = FakeWindows()
    hands = win.hands()
    win.on_send = lambda: setattr(win, "at", (900, 900))         # grabbed once the button is down

    with pytest.raises(UserTookOver):
        hands.do(DRAG)
    assert win.mouse() == ["left down", "left up"]


def test_a_drag_lets_go_of_the_button_when_windows_stops_it(no_pauses):
    win = FakeWindows()
    hands = win.hands()
    win.fail_at = (50, 10)

    with pytest.raises(OSError, match="would not move the pointer"):
        hands.do(DRAG)
    assert win.mouse() == ["left down", "left up"]


def test_keys_are_let_go_when_pressing_them_fails(no_pauses):
    win = FakeWindows()
    hands = win.hands()
    win.failing_sends = 1                                         # only Ctrl went down

    with pytest.raises(OSError, match="blocked"):
        hands.do({"type": "keypress", "keys": ["ctrl", "c"]})
    assert win.sent == [(0x11, "down"), (0x43, "up"), (0x11, "up")]
