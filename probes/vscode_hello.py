"""Live check: the VS Code add-on connects, reports its state, and writes a file when asked.

Run from the repository root, with real VS Code installed and the add-on built:
    <python> probes\\vscode_hello.py

It installs extensions/vscode/mentora-<version>.vsix, opens a scratch lesson folder in a new VS Code
window, prints the hello and the first state, writes a line through the add-on's write_file
operation and prints the next state, runs the file and prints the run, then closes the window.
"""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.types import Call  # noqa: E402
from app.vscode.bridge import Bridge  # noqa: E402

EXT = ROOT / "extensions" / "vscode"


def show(label: str, state: dict) -> None:
    files = {p: {"saved": f["saved"], "text": f["text"]} for p, f in state["files"].items()}
    print(f"--- {label}")
    print(json.dumps({"files": files, "active": state["active"], "problems": state["problems"],
                      "run": state["run"]}, indent=2))


def next_state(states: queue.Queue, want, timeout: float = 15.0) -> dict:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            state = states.get(timeout=0.2)
        except queue.Empty:
            continue
        if want(state):
            return state
    raise SystemExit(f"no matching state within {timeout} s")


def main() -> None:
    version = json.loads((EXT / "package.json").read_text(encoding="utf-8"))["version"]
    vsix = EXT / f"mentora-{version}.vsix"
    if not vsix.exists():
        raise SystemExit(f"{vsix} is missing: run `npm install` and `npm run package` in {EXT}")
    code = shutil.which("code")
    if code is None:
        raise SystemExit("VS Code's `code` command is not on PATH")
    print(subprocess.run([code, "--install-extension", str(vsix), "--force"],
                         capture_output=True, text=True, timeout=120).stdout.strip())

    base = Path(os.environ["LOCALAPPDATA"]) / "mentora"
    folder = base / "work" / "probe-hello"
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True)
    (folder / "hello.py").write_text("print('Hello from the probe')\n", encoding="utf-8")

    states: queue.Queue = queue.Queue()
    closed: list[str] = []
    bridge = Bridge(on_state=states.put, on_closed=lambda: closed.append("closed"))
    port = bridge.start()
    (base / "vscode.json").write_text(json.dumps({"port": port, "token": bridge.token, "folder": str(folder)}),
                                      encoding="utf-8")
    started = time.monotonic()
    subprocess.Popen([code, "--new-window", str(folder), str(folder / "hello.py")])
    try:
        if not bridge.wait_connected(60):
            raise SystemExit(f"no hello within 60 s (refused: {bridge.refused or 'no'})")
        print(f"hello after {time.monotonic() - started:.1f} s on port {port}")
        show("first state", next_state(states, lambda s: "hello.py" in s["files"]))

        line = "print('A line the program typed')\n"
        bridge.send_op(Call("write_file", {"path": "hello.py",
                                           "text": "import sys\nprint('Hello from the probe, run by', sys.executable)\n"
                                                   + line})).result(15)
        # VS Code keeps the file's own line endings (\r\n on Windows), so look for the line's words.
        show("after write_file", next_state(states, lambda s: line.strip() in s["files"].get("hello.py", {}).get("text", "")))

        bridge.send_op(Call("run_file", {"path": "hello.py"})).result(40)   # the shell may take 20 s to start
        show("after run_file", next_state(states, lambda s: bool(s["run"] and s["run"]["finished"]), timeout=25))
    finally:
        bridge.close_window()
        time.sleep(2)
        bridge.stop()
        print(f"on_closed calls: {closed}; errors: {bridge.errors}")


if __name__ == "__main__":
    main()
