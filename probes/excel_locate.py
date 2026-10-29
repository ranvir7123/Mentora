"""Live proof that the pointer lands on the right place: cells and ribbon buttons, on real Excel.

Run:   C:\\dev\\meta-hackathon\\.venv\\Scripts\\python.exe probes\\excel_locate.py
Needs: Excel installed and about 600 MB of free memory. A visible Excel window opens on the left
920 px of the screen, beside an empty 360 px strip where the panel will go. Nothing is clicked or
typed; the probe switches Excel's ribbon tabs through UI Automation. Leave that window alone while
it runs (about a minute).

1. Whether Excel's PointsToScreenPixels gives real (physical) pixels at this screen's scaling:
       first visible cell: Excel says (x, y), UI Automation says (x, y) -> physical: yes/no
2. For B8, C2 and A1:C1, at zoom 100, 150 and 200, plain, scrolled, with row 1 frozen, and frozen and
   scrolled: the box locate.py works out against the box UI Automation gives for the same cells.
       zoom 150 scrolled      B8     ours Rect(..) uia Rect(..) diff 1 px
   Pass: 2 px or less everywhere ("both hidden" also passes).
3. For Insert > Pie, View > Freeze Panes and Data > Sort Largest to Smallest: the spot and its words
   with the Home tab open, then again with the right tab opened, and how long one search takes.
Last, the number of EXCEL.EXE processes left behind (want 0 new). Exit code 0 means all passed.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.lesson import load_lesson               # noqa: E402
from app.core.types import Call, Rect, Target         # noqa: E402
from app.excel import locate                          # noqa: E402
from app.excel.address import cell_name, parse_area   # noqa: E402
from app.excel.session import ExcelSession            # noqa: E402
from app.win import uia, windows                      # noqa: E402

WAIT_S = 30
SETTLE_S = 0.6                     # Excel redraws, and UI Automation catches up, after a change
PANEL_W = 360                      # logical px kept free for the panel
PASS_PX = 2
CELLS = ("B8", "C2", "A1:C1")
ZOOMS = (100, 150, 200)
STATES = ("plain", "scrolled", "row 1 frozen", "frozen+scrolled")
CONTROLS = ("Insert > Pie", "View > Freeze Panes", "Data > Sort Largest to Smallest")


def excel_pids() -> set[int]:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq EXCEL.EXE", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return {int(line.split('","')[1]) for line in out.splitlines() if line.startswith('"EXCEL.EXE"')}


def on_com(s: ExcelSession, fn):
    """Run fn on the session's COM thread (a probe may reach inside; the program never does)."""
    return s._com.submit(fn).result(WAIT_S)


def edges(r: Rect) -> tuple[float, float, float, float]:
    return r.x, r.y, r.x + r.w, r.y + r.h


def union(rects: list[Rect]) -> Rect | None:
    if not rects:
        return None
    x0, y0 = min(r.x for r in rects), min(r.y for r in rects)
    x1, y1 = max(r.x + r.w for r in rects), max(r.y + r.h for r in rects)
    return Rect(x0, y0, x1 - x0, y1 - y0)


def uia_cells(hwnd: int) -> list:
    return [n for n in uia.roots_for(hwnd)[0].descendants({"DataItem"}) if not n.offscreen and n.rect]


def uia_box(cells: list, ref: str) -> Rect | None:
    area = parse_area(ref)
    found = []
    for row in range(area.top, area.bottom + 1):
        for col in range(area.left, area.right + 1):
            name = re.compile(rf"(?<![A-Z]){cell_name(row, col)}(?!\d)")
            found += [n.rect for n in cells if name.search(n.name.upper())]
    return union(found)


def set_state(s: ExcelSession, zoom: int, state: str) -> None:
    s.perform(Call("freeze", {"rows": 0, "cols": 0})).result(WAIT_S)
    if "frozen" in state:
        s.perform(Call("freeze", {"rows": 1, "cols": 0})).result(WAIT_S)

    def view() -> None:
        win = s._wb.Windows(1)
        win.Zoom = zoom
        if state == "scrolled":
            win.ScrollRow, win.ScrollColumn = 3, 2
        elif state == "frozen+scrolled":
            win.Panes.Item(win.Panes.Count).ScrollRow = 4
    on_com(s, view)
    time.sleep(SETTLE_S)


def check_pixels(s: ExcelSession, hwnd: int) -> None:
    def measure():
        pane = s._wb.Windows(1).ActivePane
        seen = pane.VisibleRange
        first = str(seen.Cells(1, 1).Address).replace("$", "")
        ours = (pane.PointsToScreenPixelsX(seen.Left), pane.PointsToScreenPixelsY(seen.Top))
        return first, ours, uia_box(uia_cells(hwnd), first)
    first, ours, box = on_com(s, measure)
    theirs = (box.x, box.y) if box else None
    physical = theirs is not None and max(abs(a - b) for a, b in zip(ours, theirs)) <= PASS_PX
    print(f"first visible cell {first}: Excel says {ours}, UI Automation says {theirs} -> physical: "
          f"{'yes' if physical else 'no'}", flush=True)


def check_cells(s: ExcelSession, hwnd: int) -> int:
    bad = 0
    names_shown = False
    for zoom in ZOOMS:
        for state in STATES:
            set_state(s, zoom, state)
            cells = on_com(s, lambda: uia_cells(hwnd))
            if not names_shown:
                print(f"UI Automation cell names look like: {[n.name for n in cells[:3]]}", flush=True)
                names_shown = True
            for ref in CELLS:
                kind = "range" if ":" in ref else "cell"
                spot = s.locate(Target(kind, f"Budget!{ref}")).result(WAIT_S)
                ours = spot.rect if spot else None
                theirs = uia_box(cells, ref)
                if ours is None or theirs is None:
                    verdict = "both hidden" if ours is theirs else "ONE HIDDEN"
                    bad += ours is not theirs
                else:
                    diff = max(abs(a - b) for a, b in zip(edges(ours), edges(theirs)))
                    verdict = f"diff {diff:.1f} px" + ("" if diff <= PASS_PX else "  TOO FAR")
                    bad += diff > PASS_PX
                print(f"zoom {zoom} {state:<16} {ref:<6} ours {ours} uia {theirs} {verdict}", flush=True)
    set_state(s, 100, "plain")
    return bad


def open_tab(s: ExcelSession, hwnd: int, name: str) -> bool:
    def select() -> bool:
        c = uia._client()
        for tab in uia.roots_for(hwnd)[0].descendants({"TabItem"}):
            if locate.same_name(tab.name, name):
                pattern = tab._raw.GetCurrentPattern(c.UIA.UIA_SelectionItemPatternId)
                pattern.QueryInterface(c.UIA.IUIAutomationSelectionItemPattern).Select()
                return True
        return False
    opened = on_com(s, select)
    time.sleep(SETTLE_S)
    return opened


def check_controls(s: ExcelSession, hwnd: int) -> int:
    bad = 0
    for ref in CONTROLS:
        open_tab(s, hwnd, "Home")
        t0 = time.perf_counter()
        route = s.locate(Target("control", ref)).result(WAIT_S)
        took = time.perf_counter() - t0
        print(f"{ref}: with Home open -> {route} ({took * 1000:.0f} ms)", flush=True)
        tab = ref.split(">")[0].strip()
        if not open_tab(s, hwnd, tab):
            print(f"  could not open the {tab} tab through UI Automation", flush=True)
            bad += 1
            continue
        spot = s.locate(Target("control", ref)).result(WAIT_S)
        print(f"  with {tab} open -> {spot}", flush=True)
        bad += spot is None or route is None or route.bubble != locate.OPEN_FIRST

        def timing():
            tracker = locate.ControlTracker(lambda: uia.roots_for(hwnd), "control", ref)
            t1 = time.perf_counter()
            tracker.spot()
            t2 = time.perf_counter()
            tracker.spot()
            return (t2 - t1) * 1000, (time.perf_counter() - t2) * 1000
        search_ms, follow_ms = on_com(s, timing)
        print(f"  one search {search_ms:.0f} ms, one follow-up look {follow_ms:.0f} ms", flush=True)
    open_tab(s, hwnd, "Home")
    return bad


def main() -> int:
    lesson = load_lesson(ROOT / "lessons" / "monthly-budget")
    workdir = Path(os.environ["LOCALAPPDATA"]) / "projectx" / "probe" / f"{lesson.id}-locate"
    before = excel_pids()
    t0 = time.perf_counter()
    bad = 0
    s = ExcelSession(lesson, workdir, visible=True, on_snapshot=lambda snap: None,
                     on_closed=lambda: print("closed reported (not expected)", flush=True))
    try:
        hwnd = s.hwnd()
        work = windows.work_area(hwnd)
        panel = round(PANEL_W * windows.dpi_scale(hwnd))
        s.place(Rect(work.x, work.y, work.w - panel, work.h)).result(WAIT_S)
        time.sleep(SETTLE_S)
        print(f"Excel placed at {windows.window_rect(hwnd)}, scale {windows.dpi_scale(hwnd)}", flush=True)
        check_pixels(s, hwnd)
        bad += check_cells(s, hwnd)
        bad += check_controls(s, hwnd)
    finally:
        s.close()
    time.sleep(3)
    left = excel_pids() - before
    print(f"time {time.perf_counter() - t0:.1f} s; session errors: {len(s.errors)}; "
          f"EXCEL.EXE left behind: {len(left)}", flush=True)
    for e in s.errors:
        print(e)
    bad += bool(left) + bool(s.errors)
    print("ALL PASSED" if not bad else f"{bad} PROBLEM(S)", flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
