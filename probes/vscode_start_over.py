"""Live check: starting a lesson over, then writing its file again, works every time in the real VS Code.

Run from the repository root, with real VS Code installed and the add-on built:
    <python> probes\\vscode_start_over.py

It opens "Your first Python program" minimised in %LOCALAPPDATA%\\mentora\\work\\probe-start-over and
four times makes hello.py, writes it, prints the saved text and starts over, as the prover does
between a step's planted mistakes. Before the add-on deleted files through VS Code's own edits,
every second write failed with "VS Code could not write hello.py".
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.lesson import load_lesson  # noqa: E402
from app.core.types import Call  # noqa: E402
from app.vscode.plugin import VsCodePlugin  # noqa: E402

ROUNDS = 4
WAIT_S = 30


def main() -> int:
    lesson = load_lesson(ROOT / "lessons" / "vscode-first-program")
    workdir = Path(os.environ["LOCALAPPDATA"]) / "mentora" / "work" / "probe-start-over"
    session = VsCodePlugin().open(lesson, workdir, visible=False, resume=False,
                                  on_snapshot=lambda snap: None, on_closed=lambda: None)
    failed = 0
    try:
        session.read_now().result(timeout=90)
        for i in range(ROUNDS):
            for op in (Call("new_file", {"path": "hello.py"}),
                       Call("write_file", {"path": "hello.py", "text": f"print({i})\n"})):
                try:
                    session.perform(op).result(timeout=WAIT_S)
                    print(f"round {i} {op.kind}: ok")
                except Exception as exc:
                    failed += 1
                    print(f"round {i} {op.kind}: FAILED {exc}")
            files = session.read_now().result(timeout=WAIT_S).files
            print(f"  saved: {({path: f.text for path, f in files.items()})!r}")
            session.reset().result(timeout=WAIT_S)
    finally:
        session.close(save=False)
        time.sleep(4)
        print(f"errors: {session.errors}")
    print("all rounds passed" if not failed else f"{failed} operations failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
