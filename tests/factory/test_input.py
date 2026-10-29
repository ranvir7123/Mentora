"""The parts of real input that never move the mouse or press a key."""
import struct
import sys
import zlib

import pytest

from app.core.types import Rect
from app.factory.input import Shown, covers, encode_png, held_keys, vk_for, wheel_clicks


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
    from app.factory.input import WindowsHands
    png = WindowsHands().grab(Rect(0, 0, 128, 80), 64, 40)     # read-only: nothing is clicked or saved
    assert struct.unpack(">II", _chunks(png)[b"IHDR"][:8]) == (64, 40)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows windows")
def test_the_real_windows_above_one_can_be_read():
    import ctypes
    from app.factory.input import WindowsHands
    front = ctypes.WinDLL("user32").GetForegroundWindow()
    assert WindowsHands().covered(front, Rect(-100_000, -100_000, 10, 10)) is False   # nothing is that far off
