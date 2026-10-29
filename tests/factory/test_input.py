"""The parts of real input that never move the mouse or press a key."""
import struct
import sys
import zlib

import pytest

from app.factory.input import encode_png, vk_for, wheel_clicks


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


def test_scroll_pixels_become_wheel_clicks():
    assert [wheel_clicks(p) for p in (0, 40, 100, 300, -50, -260)] == [0, 1, 1, 3, -1, -3]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows screenshots")
def test_a_real_screenshot_has_the_size_asked_for():
    from app.core.types import Rect
    from app.factory.input import WindowsHands
    png = WindowsHands().grab(Rect(0, 0, 128, 80), 64, 40)     # read-only: nothing is clicked or saved
    assert struct.unpack(">II", _chunks(png)[b"IHDR"][:8]) == (64, 40)
