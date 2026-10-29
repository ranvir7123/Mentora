"""Real mouse, keyboard and screenshots on Windows, for Meta's agent when it tests a lesson.

Everything here is in physical screen pixels. The tester decides what is allowed; these hands only do it.
They stop the test the moment the mouse moves by itself, because that means a person is using the computer,
and they tell the tester when another program's window is over the app, so no screenshot can show it.
"""
from __future__ import annotations

import ctypes
import struct
import sys
import time
import zlib
from ctypes import wintypes
from dataclasses import dataclass
from typing import Iterable

from app.core.types import Rect

PAUSE_S = 0.25                   # after each action, so the app has handled it before the next look
WAIT_S = 1.0                     # what the agent's "wait" means
MOVED_PX = 3                     # the pointer moving this far by itself means a person took over
WHEEL_PX = 100                   # screenshot pixels per wheel click
POINTER_ACTIONS = frozenset({"click", "double_click", "drag", "move", "scroll"})


class UserTookOver(Exception):
    """A person moved the mouse while the test ran; the test stops at once."""


# The parts that never touch the screen.

def encode_png(bgra: bytes, width: int, height: int) -> bytes:
    """Pixels as Windows hands them over (blue, green, red, unused; top row first) as an RGB PNG."""
    rgb = bytearray(width * height * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = bgra[2::4], bgra[1::4], bgra[0::4]
    row = width * 3
    raw = b"".join(b"\x00" + bytes(rgb[y * row:(y + 1) * row]) for y in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


_KEYS = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "option": 0x12, "menu": 0x12,
    "win": 0x5B, "windows": 0x5B, "meta": 0x5B, "super": 0x5B, "cmd": 0x5B, "command": 0x5B,
    "enter": 0x0D, "return": 0x0D, "esc": 0x1B, "escape": 0x1B, "tab": 0x09, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "ins": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pgup": 0x21, "pagedown": 0x22, "pgdn": 0x22,
    "left": 0x25, "arrowleft": 0x25, "up": 0x26, "arrowup": 0x26,
    "right": 0x27, "arrowright": 0x27, "down": 0x28, "arrowdown": 0x28,
    "capslock": 0x14, "apps": 0x5D, "contextmenu": 0x5D,
    ";": 0xBA, "=": 0xBB, "plus": 0xBB, ",": 0xBC, "-": 0xBD, "minus": 0xBD, ".": 0xBE, "/": 0xBF,
    "`": 0xC0, "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
}
_EXTENDED = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x5B, 0x5D}


def vk_for(name: str) -> int:
    """The Windows key code for a key name such as "ctrl", "Enter", "a" or "F5"."""
    key = name.strip().lower().replace("_", "").replace(" ", "")
    if len(key) == 1 and key.isascii() and key.isalnum():
        return ord(key.upper())
    if key[:1] == "f" and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        return 0x6F + int(key[1:])
    if key in _KEYS:
        return _KEYS[key]
    raise ValueError(f"there is no key called {name}")


def held_keys(action: dict) -> list[int]:
    """The keys held down around a mouse action (ctrl-click, shift-drag). No other action holds keys."""
    if action.get("type") not in POINTER_ACTIONS:
        return []
    return [vk_for(k) for k in action.get("keys") or []]


@dataclass(frozen=True)
class Shown:
    """A window above the app's, as Windows reports it."""
    process: int
    bounds: Rect                     # where it shows on the screen, without its invisible edges
    visible: bool = True
    cloaked: bool = False            # Windows keeps it hidden (on another desktop, a closed Start menu)
    minimised: bool = False


def covers(above: Iterable[Shown], process: int, rect: Rect) -> bool:
    """True when a window of another program shows anywhere over `rect`."""
    return any(w.visible and not w.cloaked and not w.minimised and w.process != process and w.bounds.intersects(rect)
               for w in above)


def wheel_clicks(pixels: float) -> int:
    """Wheel clicks for a scroll of this many screenshot pixels; any scroll is at least one click."""
    if not pixels:
        return 0
    return (1 if pixels > 0 else -1) * max(1, round(abs(pixels) / WHEEL_PX))


# Windows itself.

_ULONG_PTR = ctypes.c_size_t


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", _ULONG_PTR)]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", _ULONG_PTR)]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


_INPUT_MOUSE, _INPUT_KEYBOARD = 0, 1
_KEYUP, _UNICODE, _EXTENDEDKEY = 0x0002, 0x0004, 0x0001
_WHEEL, _HWHEEL = 0x0800, 0x1000
_BUTTONS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "wheel": (0x0020, 0x0040),
            "middle": (0x0020, 0x0040)}
_SRCCOPY, _CAPTUREBLT, _HALFTONE = 0x00CC0020, 0x40000000, 4
_SPI_GETWORKAREA = 0x0030
_GA_ROOT, _GW_HWNDPREV = 2, 3
_DWMWA_EXTENDED_FRAME_BOUNDS, _DWMWA_CLOAKED = 9, 14
_MAX_ABOVE = 2000                # windows looked at above the app; the z-order can change while it is read


def _api():
    """The Windows functions used here, with their argument types set so 64-bit handles survive."""
    user32, gdi32, kernel32 = ctypes.WinDLL("user32", use_last_error=True), ctypes.WinDLL("gdi32"), \
        ctypes.WinDLL("kernel32")
    dwmapi = ctypes.WinDLL("dwmapi")
    for fn, res, args in [
        (user32.GetDC, wintypes.HDC, [wintypes.HWND]),
        (user32.ReleaseDC, ctypes.c_int, [wintypes.HWND, wintypes.HDC]),
        (user32.GetCursorPos, wintypes.BOOL, [ctypes.POINTER(wintypes.POINT)]),
        (user32.SetCursorPos, wintypes.BOOL, [ctypes.c_int, ctypes.c_int]),
        (user32.SendInput, wintypes.UINT, [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]),
        (user32.GetForegroundWindow, wintypes.HWND, []),
        (user32.SetForegroundWindow, wintypes.BOOL, [wintypes.HWND]),
        (user32.BringWindowToTop, wintypes.BOOL, [wintypes.HWND]),
        (user32.ShowWindow, wintypes.BOOL, [wintypes.HWND, ctypes.c_int]),
        (user32.IsIconic, wintypes.BOOL, [wintypes.HWND]),
        (user32.GetWindowThreadProcessId, wintypes.DWORD, [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]),
        (user32.AttachThreadInput, wintypes.BOOL, [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]),
        (user32.SystemParametersInfoW, wintypes.BOOL, [wintypes.UINT, wintypes.UINT, ctypes.c_void_p,
                                                        wintypes.UINT]),
        (user32.GetDpiForSystem, wintypes.UINT, []),
        (user32.GetAncestor, wintypes.HWND, [wintypes.HWND, wintypes.UINT]),
        (user32.GetWindow, wintypes.HWND, [wintypes.HWND, wintypes.UINT]),
        (user32.IsWindowVisible, wintypes.BOOL, [wintypes.HWND]),
        (user32.GetWindowRect, wintypes.BOOL, [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]),
        (dwmapi.DwmGetWindowAttribute, ctypes.c_long, [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p,
                                                        wintypes.DWORD]),
        (kernel32.GetCurrentThreadId, wintypes.DWORD, []),
        (gdi32.CreateCompatibleDC, wintypes.HDC, [wintypes.HDC]),
        (gdi32.CreateCompatibleBitmap, wintypes.HBITMAP, [wintypes.HDC, ctypes.c_int, ctypes.c_int]),
        (gdi32.SelectObject, wintypes.HGDIOBJ, [wintypes.HDC, wintypes.HGDIOBJ]),
        (gdi32.SetStretchBltMode, ctypes.c_int, [wintypes.HDC, ctypes.c_int]),
        (gdi32.SetBrushOrgEx, wintypes.BOOL, [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]),
        (gdi32.StretchBlt, wintypes.BOOL, [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                           ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_int, wintypes.DWORD]),
        (gdi32.GetDIBits, ctypes.c_int, [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                                         ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]),
        (gdi32.DeleteObject, wintypes.BOOL, [wintypes.HGDIOBJ]),
        (gdi32.DeleteDC, wintypes.BOOL, [wintypes.HDC]),
    ]:
        fn.restype, fn.argtypes = res, args
    return user32, gdi32, kernel32, dwmapi


def make_dpi_aware() -> None:
    """Ask Windows for real pixels (not scaled ones). Harmless when the program already asked."""
    user32 = ctypes.WinDLL("user32")
    try:
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):      # per monitor, version 2
            return
    except AttributeError:
        pass
    try:
        ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        user32.SetProcessDPIAware()


class WindowsHands:
    """The real screen, mouse and keyboard."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise OSError("the tester's hands work only on Windows")
        make_dpi_aware()
        self._user32, self._gdi32, self._kernel32, self._dwmapi = _api()
        self._last = self._cursor()                  # where the pointer was left; it must stay there

    def work_area(self) -> Rect:
        r = wintypes.RECT()
        if not self._user32.SystemParametersInfoW(_SPI_GETWORKAREA, 0, ctypes.byref(r), 0):
            raise ctypes.WinError(ctypes.get_last_error())
        return Rect(r.left, r.top, r.right - r.left, r.bottom - r.top)

    def scale(self) -> float:
        return self._user32.GetDpiForSystem() / 96

    def grab(self, rect: Rect, width: int, height: int) -> bytes:
        """What the screen shows inside `rect`, shrunk to width x height, as a PNG."""
        u, g = self._user32, self._gdi32
        screen = u.GetDC(None)
        memory = g.CreateCompatibleDC(screen)
        bitmap = g.CreateCompatibleBitmap(screen, width, height)
        try:
            old = g.SelectObject(memory, bitmap)
            g.SetStretchBltMode(memory, _HALFTONE)
            g.SetBrushOrgEx(memory, 0, 0, None)
            ok = g.StretchBlt(memory, 0, 0, width, height, screen, round(rect.x), round(rect.y),
                              round(rect.w), round(rect.h), _SRCCOPY | _CAPTUREBLT)
            g.SelectObject(memory, old)
            if not ok:
                raise OSError("Windows would not copy the screen")
            header = _BITMAPINFOHEADER(biSize=ctypes.sizeof(_BITMAPINFOHEADER), biWidth=width,
                                       biHeight=-height, biPlanes=1, biBitCount=32, biCompression=0)
            pixels = ctypes.create_string_buffer(width * height * 4)
            if g.GetDIBits(memory, bitmap, 0, height, pixels, ctypes.byref(header), 0) != height:
                raise OSError("Windows would not hand over the screenshot")
        finally:
            g.DeleteObject(bitmap)
            g.DeleteDC(memory)
            u.ReleaseDC(None, screen)
        return encode_png(pixels.raw, width, height)

    def in_front(self, hwnd: int) -> bool:
        """True when the window in front is this one or one of its program's own (a dialog box)."""
        front = self._user32.GetForegroundWindow()
        return bool(hwnd and front) and self._process(front) == self._process(hwnd)

    def covered(self, hwnd: int, rect: Rect) -> bool:
        """True when a window of another program (a notification, an always-on-top window) shows over `rect`.
        With no window to go by, it counts as covered: nothing can be said about what is on top."""
        if not hwnd:
            return True
        u, mine = self._user32, self._process(hwnd)
        above, h = [], u.GetWindow(u.GetAncestor(hwnd, _GA_ROOT), _GW_HWNDPREV)
        while h and len(above) < _MAX_ABOVE:
            above.append(self._shown(h))
            h = u.GetWindow(h, _GW_HWNDPREV)
        return covers(above, mine, rect)

    def _shown(self, hwnd: int) -> Shown:
        u, d = self._user32, self._dwmapi
        r, cloaked = wintypes.RECT(), wintypes.DWORD()
        if d.DwmGetWindowAttribute(hwnd, _DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) != 0:
            u.GetWindowRect(hwnd, ctypes.byref(r))
        if d.DwmGetWindowAttribute(hwnd, _DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) != 0:
            cloaked.value = 0
        return Shown(self._process(hwnd), Rect(r.left, r.top, r.right - r.left, r.bottom - r.top),
                     visible=bool(u.IsWindowVisible(hwnd)), cloaked=bool(cloaked.value),
                     minimised=bool(u.IsIconic(hwnd)))

    def to_front(self, hwnd: int) -> None:
        if not hwnd:
            return
        u = self._user32
        theirs = u.GetWindowThreadProcessId(u.GetForegroundWindow(), None)
        mine = self._kernel32.GetCurrentThreadId()
        attached = bool(theirs) and theirs != mine and u.AttachThreadInput(mine, theirs, True)
        try:
            if u.IsIconic(hwnd):
                u.ShowWindow(hwnd, 9)                # restore a minimised window
            u.BringWindowToTop(hwnd)
            u.SetForegroundWindow(hwnd)
        finally:
            if attached:
                u.AttachThreadInput(mine, theirs, False)

    def do(self, action: dict) -> None:
        """One action, in screen pixels. Raises UserTookOver if the pointer moved since the last one."""
        x, y = self._cursor()
        if abs(x - self._last[0]) >= MOVED_PX or abs(y - self._last[1]) >= MOVED_PX:
            raise UserTookOver("You moved the mouse, so the test stopped.")
        kind = action["type"]
        held = held_keys(action)
        self._keys(held, up=False)
        try:
            if kind in ("click", "double_click"):
                self._point(action["x"], action["y"])
                down, up = _BUTTONS[action.get("button", "left")]
                for _ in range(2 if kind == "double_click" else 1):
                    self._send([self._mouse(down), self._mouse(up)])
            elif kind == "drag":
                path = action["path"]
                self._point(path[0]["x"], path[0]["y"])
                self._send([self._mouse(_BUTTONS["left"][0])])
                for p in path[1:]:
                    time.sleep(0.05)
                    self._point(p["x"], p["y"])
                self._send([self._mouse(_BUTTONS["left"][1])])
            elif kind == "move":
                self._point(action["x"], action["y"])
            elif kind == "scroll":
                self._point(action["x"], action["y"])
                down, right = wheel_clicks(action.get("scroll_y", 0)), wheel_clicks(action.get("scroll_x", 0))
                if down:
                    self._send([self._mouse(_WHEEL, -120 * down)])
                if right:
                    self._send([self._mouse(_HWHEEL, 120 * right)])
            elif kind == "keypress":
                keys = [vk_for(k) for k in action["keys"]]
                self._keys(keys, up=False)
                self._keys(list(reversed(keys)), up=True)
            elif kind == "type":
                self._type(action["text"])
            elif kind == "wait":
                time.sleep(WAIT_S)
            elif kind != "screenshot":
                raise ValueError(f"{kind} is not an action the hands know")
        finally:
            self._keys(list(reversed(held)), up=True)
        time.sleep(PAUSE_S)
        self._last = self._cursor()

    def _process(self, hwnd: int) -> int:
        pid = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def _cursor(self) -> tuple[int, int]:
        p = wintypes.POINT()
        if not self._user32.GetCursorPos(ctypes.byref(p)):
            raise ctypes.WinError(ctypes.get_last_error())
        return p.x, p.y

    def _point(self, x: float, y: float) -> None:
        if not self._user32.SetCursorPos(round(x), round(y)):
            raise ctypes.WinError(ctypes.get_last_error())

    @staticmethod
    def _mouse(flags: int, data: int = 0) -> _INPUT:
        return _INPUT(type=_INPUT_MOUSE, u=_INPUTUNION(mi=_MOUSEINPUT(mouseData=data & 0xFFFFFFFF, dwFlags=flags)))

    @staticmethod
    def _key(vk: int = 0, scan: int = 0, flags: int = 0) -> _INPUT:
        return _INPUT(type=_INPUT_KEYBOARD, u=_INPUTUNION(ki=_KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags)))

    def _keys(self, vks: list[int], *, up: bool) -> None:
        if vks:
            self._send([self._key(vk, flags=(_KEYUP if up else 0) | (_EXTENDEDKEY if vk in _EXTENDED else 0))
                        for vk in vks])

    def _type(self, text: str) -> None:
        for ch in text:
            if ch in "\r\n\t":
                vk = 0x09 if ch == "\t" else 0x0D
                self._send([self._key(vk), self._key(vk, flags=_KEYUP)])
                continue
            units = ch.encode("utf-16-le")
            for i in range(0, len(units), 2):
                scan = int.from_bytes(units[i:i + 2], "little")
                self._send([self._key(scan=scan, flags=_UNICODE), self._key(scan=scan, flags=_UNICODE | _KEYUP)])

    def _send(self, inputs: list[_INPUT]) -> None:
        array = (_INPUT * len(inputs))(*inputs)
        if self._user32.SendInput(len(inputs), array, ctypes.sizeof(_INPUT)) != len(inputs):
            raise OSError("Windows blocked the test's input (is the app running as administrator?)")
