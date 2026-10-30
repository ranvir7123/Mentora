"""Live proof of the budget lesson's checks: every step's replay and every known mistake, on real Excel.

Run:   C:\\dev\\meta-hackathon\\.venv\\Scripts\\python.exe probes\\excel_ops.py
Needs: Excel installed and about 600 MB of free memory. Excel stays invisible and nothing is typed,
so the computer can be used while it runs.

For each step, in order, it checks the workbook, replays the step, and checks again:
    <step id>: before=<ok> after=<ok>          (want before=False after=True, all nine)
Then for each known mistake it resets to the starter, replays the steps before it, replays the
mistake, and checks:
    <step id> mistake <n>: ok=<ok> code=<code>  (want ok=False, and a code that names the mistake)
Then a filter on column B with no criteria, as a lesson replay would set it:
    filter: range=<range> on=<filtered columns> hidden rows=<n>   (want range=A1:C6 on={} hidden rows=0)
Last, the number of EXCEL.EXE processes left behind (want 0 new).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.lesson import load_lesson               # noqa: E402
from app.core.types import Call                       # noqa: E402
from app.excel.checks import CHECKS                   # noqa: E402
from app.excel.session import ExcelSession            # noqa: E402

WAIT_S = 30


def excel_pids() -> set[int]:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq EXCEL.EXE", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return {int(line.split('","')[1]) for line in out.splitlines() if line.startswith('"EXCEL.EXE"')}


def judge(session: ExcelSession, step):
    return CHECKS[step.check.kind].run(session.read_now().result(WAIT_S), step.check.args)


def main() -> int:
    lesson = load_lesson(ROOT / "lessons" / "monthly-budget")
    workdir = Path(os.environ["LOCALAPPDATA"]) / "mentora" / "probe" / f"{lesson.id}-ops"
    before = excel_pids()
    t0 = time.perf_counter()
    bad = 0
    s = ExcelSession(lesson, workdir, visible=False, on_snapshot=lambda snap: None,
                     on_closed=lambda: print("closed reported (not expected)", flush=True))
    try:
        for step in lesson.steps:
            was = judge(s, step)
            s.perform(step.replay).result(WAIT_S)
            now = judge(s, step)
            extra = "" if now.ok else f"  code={now.code} text={now.text!r}"
            print(f"{step.id}: before={was.ok} after={now.ok}{extra}", flush=True)
            bad += was.ok or not now.ok

        for i, step in enumerate(lesson.steps):
            for n, mistake in enumerate(step.mistakes, 1):
                s.reset().result(WAIT_S)
                for earlier in lesson.steps[:i]:
                    s.perform(earlier.replay).result(WAIT_S)
                s.perform(mistake.replay).result(WAIT_S)
                v = judge(s, step)
                print(f"{step.id} mistake {n}: ok={v.ok} code={v.code}  text={v.text!r}", flush=True)
                bad += v.ok or not v.attempted

        s.reset().result(WAIT_S)
        s.perform(Call("filter", {"range": "Budget!A1:C6", "column": "B"})).result(WAIT_S)
        sheet = s.read_now().result(WAIT_S).sheet("Budget")
        rows = s._com.submit(lambda: sum(bool(s._wb.Worksheets("Budget").Rows(r).Hidden)
                                         for r in range(1, 7))).result(WAIT_S)
        f = sheet.filter
        print(f"filter: range={f and f.range} on={f and f.on} hidden rows={rows}", flush=True)
        bad += f is None or f.range != "A1:C6" or bool(f.on) or rows != 0
        print(f"took {time.perf_counter() - t0:.1f}s; errors in the session: {len(s.errors)}")
        for err in s.errors[:3] + s._com.errors[:3]:
            print("error:", err)
    finally:
        s.close()
    time.sleep(3)
    left = excel_pids() - before
    print(f"Excel processes left behind: {len(left)} {sorted(left)}")
    return 0 if bad == 0 and not left else 1


if __name__ == "__main__":
    sys.exit(main())
