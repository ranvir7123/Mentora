"""A laptop with a second monitor: the panel docks at the right edge of the laptop's screen (the primary
screen, where Excel and the pointer's maths are), and home opens in the middle of that screen.

The off-screen drawer reads its screens once, when the program starts, so this runs in a program of its own
with two pretend screens: the laptop (primary) and a bigger monitor to its right."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

_CHILD = r"""
import json, os, sys, time
sys.path.insert(0, os.getcwd())
os.environ["QT_QPA_PLATFORM"] = "offscreen:configfile=" + sys.argv[1]
os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickWindow
app = QGuiApplication([])
from app.ui.app import load_window, make_engine
from app.ui.bridge import Bridge
from app.ui.demo_backend import DemoBackend
out = {"screens": [s.geometry().getRect() for s in app.screens()]}
for name, state in (("panel", "lesson_step"), ("home", "home_progress"), ("overlay", "pointer_watching")):
    backend = DemoBackend(state)
    engine = make_engine(Bridge(backend))
    window = load_window(engine, name, backend.view.get(name))
    backend.replay()
    end = time.monotonic() + 0.3
    while time.monotonic() < end:
        app.processEvents()
    out[name] = window.geometry().getRect()
print(json.dumps(out))
"""


def _windows(tmp_path) -> dict:
    config = tmp_path / "screens.json"
    config.write_text(json.dumps({"screens": [
        {"name": "laptop", "x": 0, "y": 0, "width": 1280, "height": 800,
         "logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1},
        {"name": "monitor", "x": 1280, "y": 0, "width": 1920, "height": 1080,
         "logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1}]}))
    # The drawer's option parser splits on ":", so the path goes without its drive letter (the same drive).
    run = subprocess.run([sys.executable, "-c", _CHILD, config.as_posix()[2:]], cwd=ROOT,
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[-2000:]
    return json.loads(run.stdout.strip().splitlines()[-1])


def test_with_a_second_monitor_the_screens_stay_on_the_laptop(tmp_path):
    seen = _windows(tmp_path)
    assert seen["screens"] == [[0, 0, 1280, 800], [1280, 0, 1920, 1080]]
    assert seen["panel"] == [1280 - 360, 0, 360, 800], "the panel docks at the laptop screen's right edge"
    x, y, w, h = seen["home"]
    assert 0 <= x and x + w <= 1280 and 0 <= y and y + h <= 800, f"home at {seen['home']} leaves the laptop"
    assert abs((x + w / 2) - 640) <= 1 and abs((y + h / 2) - 400) <= 1, "home is in the middle of the laptop"
    assert seen["overlay"] == [0, 0, 1280, 800], "the pointer's layer covers the laptop's screen"
