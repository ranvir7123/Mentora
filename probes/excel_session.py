"""Live check of the Excel session: real Excel, real typing, a real close by hand.

Run:   C:\\dev\\meta-hackathon\\.venv\\Scripts\\python.exe probes\\excel_session.py
Needs: Excel installed and about 600 MB of free memory. It types into Excel, so keep your hands off
the keyboard and mouse until it asks you to close Excel. Then close Excel with its X button and
pick "Don't Save".

It prints one line per snapshot (B8's value and formula), then "closed reported" once the session
notices the close, the read counts, and how many EXCEL.EXE processes were left behind (want 0 new).
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.lesson import load_lesson               # noqa: E402
from app.core.types import Rect                       # noqa: E402
from app.excel.session import ExcelSession            # noqa: E402
from app.win import windows                           # noqa: E402

PANEL_PX = 360                     # the panel's width in screen points; Excel gets the rest
TYPED = "=SUM(B2:B6)"

user32 = ctypes.WinDLL("user32", use_last_error=True)
INPUT_KEYBOARD, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 1, 0x0002, 0x0004
VK_RETURN, VK_MENU = 0x0D, 0x12


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def send_keys(*events: tuple[int, int, int]) -> None:
    arr = (INPUT * len(events))()
    for i, (vk, scan, flags) in enumerate(events):
        arr[i].type = INPUT_KEYBOARD
        arr[i].ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    if user32.SendInput(len(events), arr, ctypes.sizeof(INPUT)) != len(events):
        raise ctypes.WinError(ctypes.get_last_error())


def type_text(text: str) -> None:
    for ch in text:
        send_keys((0, ord(ch), KEYEVENTF_UNICODE), (0, ord(ch), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
        time.sleep(0.03)


def bring_to_front(hwnd: int) -> bool:
    send_keys((VK_MENU, 0, 0), (VK_MENU, 0, KEYEVENTF_KEYUP))   # lets this program change the front window
    user32.SetForegroundWindow(hwnd)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if user32.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.1)
    return False


def excel_pids() -> set[int]:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq EXCEL.EXE", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return {int(line.split('","')[1]) for line in out.splitlines() if line.startswith('"EXCEL.EXE"')}


def main() -> int:
    lesson = load_lesson(ROOT / "lessons" / "monthly-budget")
    workdir = Path(os.environ["LOCALAPPDATA"]) / "projectx" / "probe" / lesson.id
    before = excel_pids()
    t0 = time.perf_counter()
    closed = threading.Event()

    def on_snapshot(snap) -> None:
        b8 = snap.cell("Budget", "B8")
        print(f"{time.perf_counter() - t0:7.2f}s  snapshot: B8 value={b8.value!r} formula={b8.formula!r}",
              flush=True)

    def on_closed() -> None:
        print(f"{time.perf_counter() - t0:7.2f}s  closed reported", flush=True)
        closed.set()

    s = ExcelSession(lesson, workdir, visible=True, on_snapshot=on_snapshot, on_closed=on_closed)
    print(f"{time.perf_counter() - t0:7.2f}s  Excel open, window {s.hwnd()}, file {s.path}", flush=True)
    try:
        area = windows.work_area(s.hwnd())
        scale = windows.dpi_scale(s.hwnd())
        want = Rect(area.x, area.y, area.w - PANEL_PX * scale, area.h)
        s.place(want).result(10)
        print(f"placed: asked {want}, visible frame now {windows.window_rect(s.hwnd())}, scale {scale}")

        s._com.submit(lambda: s._wb.Worksheets("Budget").Range("B8").Select()).result(10)
        if not bring_to_front(s.hwnd()):
            print("Excel did not come to the front, so nothing was typed.")
        else:
            type_text(TYPED)
            time.sleep(1.5)                                  # still in the cell: no event yet
            send_keys((VK_RETURN, 0, 0), (VK_RETURN, 0, KEYEVENTF_KEYUP))
            print(f"{time.perf_counter() - t0:7.2f}s  typed {TYPED} and Enter", flush=True)
        time.sleep(2)

        print("\nNow close Excel with its X button and pick Don't Save. Waiting up to 2 minutes.", flush=True)
        if not closed.wait(120):
            print("closed was NOT reported within 2 minutes")
        sched = s._scheduler
        print(f"reads={sched.reads} events={sched.events} busy_retries={sched.busy_retries} "
              f"errors={sched.error_count} max_lag_ms={sched.max_lag_ns / 1e6:.1f}")
        for err in sched.errors[:3] + s._com.errors[:3]:
            print("error:", err)
    finally:
        s.close()
    time.sleep(3)
    left = excel_pids() - before
    print(f"Excel processes left behind: {len(left)} {sorted(left)}")
    return 0 if closed.is_set() and not left else 1


if __name__ == "__main__":
    sys.exit(main())
