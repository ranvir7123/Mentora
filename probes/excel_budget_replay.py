"""Live proof that the budget lesson runs start to finish on real Excel through the plug-in.

Run:   C:\\dev\\meta-hackathon\\.venv\\Scripts\\python.exe probes\\excel_budget_replay.py
Needs: Excel installed and about 600 MB of free memory. A visible Excel window opens on the left
920 px of the screen. Nothing is clicked or typed: each step's replay is done through Excel's own
programming interface, one second apart. Leave that window alone while it runs (about 20 seconds).

The lesson runner sees every snapshot Excel delivers and prints its events as they come:
    StepPassed(index=0, first_try=True, points=10)      (want nine of these, in order)
    LessonDone(...)                                      (then this, once)
Last, the number of EXCEL.EXE processes left behind (want 0 new). Exit code 0 means all of that.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.lesson import load_lesson                       # noqa: E402
from app.core.runner import LessonDone, LessonRun, StepPassed  # noqa: E402
from app.core.types import Rect                               # noqa: E402
from app.excel.plugin import ExcelPlugin                      # noqa: E402
from app.win import windows                                   # noqa: E402

WAIT_S = 30
STEP_GAP_S = 1.0
PANEL_W = 360


def excel_pids() -> set[int]:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq EXCEL.EXE", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return {int(line.split('","')[1]) for line in out.splitlines() if line.startswith('"EXCEL.EXE"')}


def main() -> int:
    lesson = load_lesson(ROOT / "lessons" / "monthly-budget")
    workdir = Path(os.environ["LOCALAPPDATA"]) / "projectx" / "probe" / f"{lesson.id}-replay"
    plugin = ExcelPlugin()
    run = LessonRun(lesson, plugin.checks)
    events: list[object] = []
    finished = threading.Event()
    t0 = time.perf_counter()

    def on_snapshot(snap) -> None:                    # on the COM thread; the checks are quick
        for event in run.on_snapshot(snap):
            events.append(event)
            print(f"{time.perf_counter() - t0:5.1f} s  {event}", flush=True)
            if isinstance(event, LessonDone):
                finished.set()

    before = excel_pids()
    s = plugin.open(lesson, workdir, visible=True, on_snapshot=on_snapshot,
                    on_closed=lambda: print("closed reported (not expected)", flush=True))
    try:
        hwnd = s.hwnd()
        work = windows.work_area(hwnd)
        s.place(Rect(work.x, work.y, work.w - round(PANEL_W * windows.dpi_scale(hwnd)), work.h)).result(WAIT_S)
        s.read_now().result(WAIT_S)
        for step in lesson.steps:
            time.sleep(STEP_GAP_S)
            print(f"{time.perf_counter() - t0:5.1f} s  replaying {step.id}: {step.replay.kind} {dict(step.replay.args)}",
                  flush=True)
            s.perform(step.replay).result(WAIT_S)
        if not finished.wait(WAIT_S):
            print(f"no LessonDone within {WAIT_S} s", flush=True)
    finally:
        s.close()
    time.sleep(3)
    left = excel_pids() - before
    passed = [e.index for e in events if isinstance(e, StepPassed)]
    done = sum(isinstance(e, LessonDone) for e in events)
    print(f"steps passed in order: {passed}; LessonDone: {done}; runner errors: {len(run.errors)}; "
          f"session errors: {len(s.errors)}; EXCEL.EXE left behind: {len(left)}", flush=True)
    for e in run.errors + s.errors:
        print(e)
    ok = passed == list(range(len(lesson.steps))) and done == 1 and not (run.errors or s.errors or left)
    print("ALL PASSED" if ok else "PROBLEM", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
