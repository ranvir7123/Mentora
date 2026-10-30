"""Live check of the macro guard: macros are forced off, and the macro editor is not one of Excel's own windows.

Run:   C:\\dev\\meta-hackathon\\.venv\\Scripts\\python.exe probes\\excel_macro_guard.py
Needs: Excel installed and about 600 MB of free memory. It presses no key and moves no mouse. Excel and
its macro editor show on screen for a few seconds, then close by themselves. It changes no setting:
macros are forced off only inside the Excel it starts, and the macro editor is opened the way its ribbon
button opens it, which needs no trust setting.

Why: Meta's tester clicks only in Excel's main window and the windows it owns (input.py `owned_by`).
The macro editor runs inside Excel too; if Excel owned it, the tester could click there and write a macro.

It prints:
    macros: AutomationSecurity=<n>                     (want 3: forced off)
    excel window <number> (XLMAIN)
    macro editor window <number> (wndclass_desked_gsk), owner chain: <number> -> ...
    tester would click there: <True or False>          (want False)
    new EXCEL.EXE left behind: <n>                     (want 0)
Last line:
    macro_guard ok=<True or False>
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
from app.excel.session import MACROS_FORCED_OFF, ExcelSession   # noqa: E402
from app.factory.input import owned_by                 # noqa: E402
from app.win import windows                           # noqa: E402

MACRO_EDITOR = "wndclass_desked_gsk"   # the macro editor's main window, as Windows names its kind
FIND_S = 10.0


def excel_pids() -> set[int]:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq EXCEL.EXE", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return {int(line.split('","')[1]) for line in out.splitlines() if line.startswith('"EXCEL.EXE"')}


def owner_chain(hwnd: int) -> list[int]:
    chain: list[int] = []
    while hwnd and hwnd not in chain and len(chain) < 50:
        chain.append(hwnd)
        hwnd = windows.owner(hwnd)
    return chain


def find_macro_editor(pid: int) -> int:
    deadline = time.monotonic() + FIND_S
    while time.monotonic() < deadline:
        for w in windows.program_windows(pid):
            if windows.class_name(w) == MACRO_EDITOR:
                return w
        time.sleep(0.2)
    return 0


def main() -> int:
    lesson = load_lesson(ROOT / "lessons" / "monthly-budget")
    workdir = Path(os.environ["LOCALAPPDATA"]) / "mentora" / "probe" / f"{lesson.id}-macros"
    before = excel_pids()
    s = ExcelSession(lesson, workdir, visible=True, on_snapshot=lambda snap: None, on_closed=lambda: None)
    ok = False
    try:
        security = s._com.submit(lambda: int(s._app.AutomationSecurity)).result(10)
        print(f"macros: AutomationSecurity={security}  (want {MACROS_FORCED_OFF}: forced off)", flush=True)
        excel = s.hwnd()
        print(f"excel window {excel} ({windows.class_name(excel)})", flush=True)
        try:
            s._com.submit(lambda: s._app.CommandBars.ExecuteMso("VisualBasic")).result(10)
        except Exception as exc:   # noqa: BLE001 - said plainly; the check cannot go on without the editor
            print(f"could not open the macro editor: {exc}", flush=True)
            return 1
        editor = find_macro_editor(windows.process_id(excel))
        if not editor:
            print(f"macro editor window not found within {FIND_S:.0f} s", flush=True)
            return 1
        chain = " -> ".join(str(w) for w in owner_chain(editor))
        print(f"macro editor window {editor} ({MACRO_EDITOR}), owner chain: {chain}", flush=True)
        clickable = owned_by(editor, excel, windows.owner)
        print(f"tester would click there: {clickable}  (want False)", flush=True)
        ok = security == MACROS_FORCED_OFF and not clickable
    finally:
        s.close()
        for err in s.errors[:3]:
            print("session error:", err.splitlines()[-1], flush=True)
        time.sleep(2)
        left = excel_pids() - before
        print(f"new EXCEL.EXE left behind: {len(left)}  (want 0)", flush=True)
        ok = ok and not left
        print(f"macro_guard ok={ok}", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
