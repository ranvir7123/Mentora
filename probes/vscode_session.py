"""Live check: the VS Code plug-in opens a lesson, carries out its steps, points at its parts, starts
over and closes, all in the real VS Code.

Run from the repository root, with real VS Code installed and the add-on built:
    <python> probes\\vscode_session.py            (VS Code shows on screen)
    <python> probes\\vscode_session.py --hidden   (VS Code opens minimised, as the prover uses it)

It opens a scratch two-step lesson in %LOCALAPPDATA%\\projectx\\work\\probe-session through
VsCodePlugin, prints the state after each step's replay with that step's check, prints where line 3
of hello.py, the file's explorer row, the editor, the terminal and the Run button are on screen,
starts the lesson over and prints the files, then closes VS Code.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.lesson import Goal, Lesson, Step  # noqa: E402
from app.core.types import Call, Target  # noqa: E402
from app.vscode.checks import CHECKS  # noqa: E402
from app.vscode.plugin import VsCodePlugin  # noqa: E402
from app.vscode.snapshot import VsSnapshot  # noqa: E402

WAIT_S = 30
PROGRAM = 'print("Hello!")\nname = input("What is your name? ")\nprint(f"Nice to meet you, {name}!")\n'


def step(n: int, target: Target, check: Call, replay: Call) -> Step:
    return Step(id=f"s{n}", instruction=f"Step {n}", why="", target=target, check=check, replay=replay,
                hints=("", "", ""), mistakes=(), clip=None)


LESSON = Lesson(
    format=1, id="probe-session", title="Probe session", app="vscode", course="", source=None,
    goal=Goal("Greet the learner by name", None),
    starter={"files": {"hello.py": "", "notes/readme.txt": "Read me\n"}, "open": "hello.py"},
    steps=(
        step(1, Target("editor_line", "hello.py:2"), Call("calls", {"path": "hello.py", "name": "input"}),
             Call("write_file", {"path": "hello.py", "text": PROGRAM})),
        step(2, Target("terminal", ""), Call("run_output", {"contains": "Nice to meet you, Ranvir"}),
             Call("run_file", {"path": "hello.py", "input": "Ranvir"})),
    ),
    made_by="hand", edited_by_hand=False, proof=None, test=None,
)


def show(label: str, snap: VsSnapshot | None) -> None:
    print(f"--- {label}")
    if snap is None:
        print("no state")
        return
    for path, file in sorted(snap.files.items()):
        print(f"{path} (saved: {file.saved}): {file.text!r}")
    print(f"active: {snap.active}")
    print(f"problems: {list(snap.problems)}")
    print(f"run: {snap.run}")


def main() -> None:
    hidden = "--hidden" in sys.argv[1:]
    workdir = Path(os.environ["LOCALAPPDATA"]) / "projectx" / "work" / LESSON.id
    events: list[str] = []
    plugin = VsCodePlugin()
    print(f"starter problems: {plugin.validate_starter(LESSON.starter)}")
    started = time.monotonic()
    session = plugin.open(LESSON, workdir, visible=not hidden, resume=False,
                          on_snapshot=lambda snap: None, on_closed=lambda: events.append("on_closed"))
    try:
        show("first state", session.read_now().result(timeout=90))
        print(f"opened in {time.monotonic() - started:.1f} s; window {session.hwnd()}; "
              f"errors so far: {session.errors}")
        for s in LESSON.steps:
            session.perform(s.replay).result(timeout=WAIT_S)
            snap = session.read_now().result(timeout=WAIT_S)
            show(f"after {s.id}: {s.replay.kind}", snap)
            print(f"check {s.check.kind}: {CHECKS[s.check.kind].run(snap, s.check.args)}")

        for target in (Target("editor_line", "hello.py:3"), Target("editor_line", "notes/readme.txt:1"),
                       Target("explorer_item", "hello.py"), Target("editor", "hello.py"),
                       Target("terminal", ""), Target("run_button", "")):
            print(f"locate {target.kind} {target.ref!r}: {session.locate(target).result(timeout=WAIT_S)}")

        session.reset().result(timeout=WAIT_S)
        show("after reset", session.read_now().result(timeout=WAIT_S))
    finally:
        session.close(save=True)
        time.sleep(4)
        print(f"close reason: {session.close_reason!r}; events: {events}; errors: {session.errors}")


if __name__ == "__main__":
    main()
