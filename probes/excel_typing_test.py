"""Five minutes of real typing into the lesson's Excel while the program reads and points: nothing lost.

Run:   C:\\dev\\meta-hackathon\\.venv\\Scripts\\python.exe probes\\excel_typing_test.py
       (add --minutes 1 for a short run)
Needs: Excel installed, about 600 MB of free memory, and NOBODY AT THE MACHINE. It presses real keys
through Windows (SendInput). Before every key it checks that our Excel window has the keyboard; if
anything else does, it stops at once and types nothing more.

What runs at the same time, as in a lesson:
- the session reads Excel after every change and once a second while a step waits,
- a watch on Budget!B8 looks for it on screen every 100 ms (and Excel scrolls it away as rows fill).
What it types: down column E from E2, at a learner's pace (5 to 8 keys a second), Enter after each
cell. Every 8th cell stays half-typed for 3 s, which keeps Excel in edit mode and busy. Values are
whole numbers, numbers with a decimal point, and words like note0042 (all different, so Excel's
AutoComplete never finishes one for us).

At the end every typed cell is compared with what Excel holds. Last line:
    typed=<cells> lost=<cells that differ> max_lag_ms=<Enter to the first read showing it>
    busy_retries=<reads Excel refused while busy> errors=<n>
Want lost=0 and errors=0.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import random
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.lesson import load_lesson               # noqa: E402
from app.core.types import Call, Rect, Target         # noqa: E402
from app.excel.session import ExcelSession            # noqa: E402
from app.win import windows                           # noqa: E402

WAIT_S = 30
PANEL_W = 360
COLUMN = "E"
FIRST_ROW = 2
KEYS_PER_S = (5.0, 8.0)
HOLD_EVERY = 8                     # every 8th cell stays in edit mode for HOLD_S
HOLD_S = 3.0
SEED = 20261102

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_RETURN = 0x0D
VK_MENU = 0x12
GA_ROOTOWNER = 3


class _KeyboardInput(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _MouseInput(ctypes.Structure):           # only here so the union has Windows' full size
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _InputUnion(ctypes.Union):
    _fields_ = [("ki", _KeyboardInput), ("mi", _MouseInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _InputUnion)]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_Input), ctypes.c_int]
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetAncestor.restype = wintypes.HWND
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]


class KeyboardLost(RuntimeError):
    pass


def excel_pids() -> set[int]:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq EXCEL.EXE", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return {int(line.split('","')[1]) for line in out.splitlines() if line.startswith('"EXCEL.EXE"')}


def _send(*inputs: _Input) -> None:
    array = (_Input * len(inputs))(*inputs)
    if _user32.SendInput(len(inputs), array, ctypes.sizeof(_Input)) != len(inputs):
        raise ctypes.WinError(ctypes.get_last_error())


def _key(vk: int = 0, scan: int = 0, flags: int = 0) -> _Input:
    return _Input(INPUT_KEYBOARD, _InputUnion(ki=_KeyboardInput(vk, scan, flags, 0, 0)))


def has_keyboard(hwnd: int) -> bool:
    fg = _user32.GetForegroundWindow()
    return bool(fg) and (fg == hwnd or _user32.GetAncestor(fg, GA_ROOTOWNER) == hwnd)


def bring_forward(hwnd: int) -> None:
    """Give Excel the keyboard. A tap of Alt is what Windows needs before it lets a program do this."""
    _send(_key(VK_MENU), _key(VK_MENU, flags=KEYEVENTF_KEYUP))
    _user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    if not has_keyboard(hwnd):
        raise KeyboardLost("Excel could not be given the keyboard")


def press(hwnd: int, char: str | None) -> None:
    """One key: a character, or Enter when char is None. Never pressed unless Excel has the keyboard."""
    if not has_keyboard(hwnd):
        raise KeyboardLost("something other than our Excel has the keyboard")
    if char is None:
        _send(_key(VK_RETURN), _key(VK_RETURN, flags=KEYEVENTF_KEYUP))
    else:
        code = ord(char)
        _send(_key(scan=code, flags=KEYEVENTF_UNICODE), _key(scan=code, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))


def values(rng: random.Random):
    n = 0
    while True:
        n += 1
        pick = rng.random()
        if pick < 0.4:
            yield str(rng.randint(1, 99999))
        elif pick < 0.7:
            yield f"{rng.randint(0, 9999)}.{rng.randint(1, 9)}"
        else:
            yield f"note{n:04d}"


def same(typed: str, held) -> bool:
    try:
        return float(typed) == float(held)
    except (TypeError, ValueError):
        return str(held) == typed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, default=5.0)
    minutes = parser.parse_args().minutes

    lesson = load_lesson(ROOT / "lessons" / "monthly-budget")
    workdir = Path(os.environ["LOCALAPPDATA"]) / "projectx" / "probe" / f"{lesson.id}-typing"
    rng = random.Random(SEED)
    typed: dict[str, str] = {}             # cell -> what was typed
    entered: dict[str, float] = {}         # cell -> when Enter was pressed, until a read shows it
    lags: list[float] = []
    spots = [0]
    lock = threading.Lock()

    def on_snapshot(snap) -> None:         # on the COM thread: note which typed cells it shows
        now = time.perf_counter()
        sheet = next((sh for sh in snap.sheets if sh.name == "Budget"), None)
        if sheet is None:
            return
        with lock:
            for cell, at in list(entered.items()):
                held = sheet.cells.get(cell)
                if held is not None and same(typed[cell], held.value):
                    lags.append(now - at)
                    del entered[cell]

    def on_spot(spot) -> None:
        spots[0] += 1

    before = excel_pids()
    t0 = time.perf_counter()
    stopped = ""
    lost: list[str] = []
    busy = read_errors = 0
    s = ExcelSession(lesson, workdir, visible=True, on_snapshot=on_snapshot,
                     on_closed=lambda: print("closed reported (not expected)", flush=True))
    try:
        hwnd = s.hwnd()
        work = windows.work_area(hwnd)
        s.place(Rect(work.x, work.y, work.w - round(PANEL_W * windows.dpi_scale(hwnd)), work.h)).result(WAIT_S)
        s.perform(Call("select", {"range": f"Budget!{COLUMN}{FIRST_ROW}"})).result(WAIT_S)
        s.set_waiting(True)
        s.watch(Target("cell", "Budget!B8"), on_spot)
        bring_forward(hwnd)
        end = time.perf_counter() + minutes * 60
        row = FIRST_ROW
        try:
            for value in values(rng):
                if time.perf_counter() >= end:
                    break
                cell = f"{COLUMN}{row}"
                hold_at = len(value) // 2 if (row - FIRST_ROW) % HOLD_EVERY == HOLD_EVERY - 1 else -1
                for i, char in enumerate(value):
                    if i == hold_at:
                        time.sleep(HOLD_S)          # Excel stays in edit mode, so it answers "busy"
                    press(hwnd, char)
                    time.sleep(1 / rng.uniform(*KEYS_PER_S))
                with lock:
                    typed[cell] = value
                    entered[cell] = time.perf_counter()
                press(hwnd, None)
                time.sleep(1 / rng.uniform(*KEYS_PER_S))
                row += 1
        except KeyboardLost as exc:
            stopped = str(exc)
            print(f"STOPPED TYPING: {exc}", flush=True)
        time.sleep(2)
        snap = s.read_now().result(WAIT_S)
        sheet = next(sh for sh in snap.sheets if sh.name == "Budget")
        lost = [c for c, v in typed.items() if sheet.cells.get(c) is None or not same(v, sheet.cells[c].value)]
        for c in lost[:10]:
            held = sheet.cells.get(c)
            print(f"lost {c}: typed {typed[c]!r}, Excel holds {held.value if held else None!r}", flush=True)
        scheduler = s._scheduler                       # a probe may reach inside; the program never does
        busy, read_errors = scheduler.busy_retries, scheduler.error_count
        s.watch(None, on_spot)
        s.set_waiting(False)
    finally:
        s.close()
    time.sleep(3)
    left = excel_pids() - before
    with lock:
        max_lag_ms = round(max(lags) * 1000) if lags else 0
        never_seen = len(entered)
    errors = len(s.errors) + read_errors + bool(left) + bool(stopped)
    print(f"time {time.perf_counter() - t0:.0f} s; pointer updates {spots[0]}; typed cells no read ever "
          f"showed: {never_seen}; read errors {read_errors}; session errors {len(s.errors)}; "
          f"EXCEL.EXE left behind {len(left)}", flush=True)
    for e in s.errors:
        print(e)
    print(f"typed={len(typed)} lost={len(lost)} max_lag_ms={max_lag_ms} busy_retries={busy} errors={errors}",
          flush=True)
    return 0 if not lost and not errors else 1


if __name__ == "__main__":
    sys.exit(main())
