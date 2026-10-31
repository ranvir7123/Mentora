"""Go / no-go: can a shape-built mascot fly smoothly over the whole screen at 200% scaling?

    <py> probes\\ui_mascot_smoothness.py [--real]

Opens a full-screen, see-through, click-through, always-on-top window (on the real screen, like the
pointer overlay) and flies a 48 px mascot 20 times between random points, 450 ms per arc, timing every
frame. Prints one line:

    frames=<n> p50=<ms> p95=<ms> p99=<ms> dropped_over_33ms=<n>

Pass: p95 <= 20 ms and dropped <= 2% of frames. `--real` flies the real mascot (app/ui/qml/mascot) instead
of the placeholder. Nothing here moves the mouse or takes the keyboard; it closes itself after the run.
"""
from __future__ import annotations

import argparse
import ctypes
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402,F401

GWL_EXSTYLE = -20
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x80000, 0x20, 0x80, 0x8000000
ARCS, ARC_MS = 20, 450

_PLACEHOLDER = """
    Item {
        id: flyer
        width: 48; height: 48
        // a soft shadow, the body, two eyes with pupils
        Shape { anchors.fill: parent; preferredRendererType: Shape.CurveRenderer
            ShapePath { fillColor: "#55000000"; strokeColor: "transparent"
                PathAngleArc { centerX: 24; centerY: 46; radiusX: 16; radiusY: 4; sweepAngle: 360 } }
            ShapePath { fillColor: "#FF7A45"; strokeColor: "transparent"
                PathAngleArc { centerX: 24; centerY: 24; radiusX: 22; radiusY: 22; sweepAngle: 360 } }
            ShapePath { fillColor: "#FFFFFF"; strokeColor: "transparent"
                PathAngleArc { centerX: 17; centerY: 21; radiusX: 6; radiusY: 7; sweepAngle: 360 } }
            ShapePath { fillColor: "#FFFFFF"; strokeColor: "transparent"
                PathAngleArc { centerX: 31; centerY: 21; radiusX: 6; radiusY: 7; sweepAngle: 360 } }
            ShapePath { fillColor: "#1C1B19"; strokeColor: "transparent"
                PathAngleArc { centerX: 18; centerY: 22; radiusX: 3; radiusY: 3.5; sweepAngle: 360 } }
            ShapePath { fillColor: "#1C1B19"; strokeColor: "transparent"
                PathAngleArc { centerX: 32; centerY: 22; radiusX: 3; radiusY: 3.5; sweepAngle: 360 } }
        }
    }
"""

_REAL = """
    Mascot {
        id: flyer
        state: "flying"
        // The flight's direction: the slope of the curve at this moment.
        heading: Math.atan2(2 * (1 - win.t) * (win.c.y - win.a.y) + 2 * win.t * (win.b.y - win.c.y),
                            2 * (1 - win.t) * (win.c.x - win.a.x) + 2 * win.t * (win.b.x - win.c.x)) * 180 / Math.PI
    }
"""

_WINDOW = """
import QtQuick
import QtQuick.Window
import QtQuick.Shapes
%(imports)s

Window {
    id: win
    x: Screen.virtualX; y: Screen.virtualY; width: Screen.width; height: Screen.height
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
           | Qt.WindowDoesNotAcceptFocus | Qt.Tool
    color: "transparent"
    visible: true
    signal arcStarted()
    signal finished()
    property int arcs: 0
    property real t: 0
    property point a: Qt.point(100, 100)
    property point b: Qt.point(600, 400)
    property point c: Qt.point(350, 50)

    %(flyer)s

    Binding { target: flyer; property: "x"
        value: (1 - win.t) * (1 - win.t) * win.a.x + 2 * (1 - win.t) * win.t * win.c.x + win.t * win.t * win.b.x }
    Binding { target: flyer; property: "y"
        value: (1 - win.t) * (1 - win.t) * win.a.y + 2 * (1 - win.t) * win.t * win.c.y + win.t * win.t * win.b.y }

    NumberAnimation { id: fly; target: win; property: "t"; from: 0; to: 1; duration: %(ms)d; easing.type: Easing.OutCubic
        onFinished: win.next() }

    function next() {
        if (arcs >= %(arcs)d) { finished(); return }
        arcs += 1
        a = b
        b = Qt.point(48 + Math.random() * (width - 144), 48 + Math.random() * (height - 144))
        var d = Math.hypot(b.x - a.x, b.y - a.y)
        c = Qt.point((a.x + b.x) / 2, Math.max(0, (a.y + b.y) / 2 - 0.25 * d))
        arcStarted()
        fly.restart()
    }
}
"""


def _set_click_through(hwnd: int) -> tuple[int, int]:
    user32 = ctypes.windll.user32
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    before = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE,
                             ctypes.c_ssize_t(before | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE))
    return before, user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true", help="fly the real mascot instead of the placeholder")
    args = parser.parse_args()

    app = QGuiApplication(sys.argv)
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(ROOT / "app" / "ui" / "qml"))
    mascot_dir = QUrl.fromLocalFile(str(ROOT / "app" / "ui" / "qml" / "mascot")).toString()
    imports = 'import Theme\nimport "%s"' % mascot_dir if args.real else ""
    source = _WINDOW % {"imports": imports, "flyer": _REAL if args.real else _PLACEHOLDER, "ms": ARC_MS,
                        "arcs": ARCS}
    engine.loadData(source.encode(), QUrl.fromLocalFile(str(ROOT / "probes" / "smoothness.qml")))
    if not engine.rootObjects():
        print("the window did not load")
        return 1
    win = engine.rootObjects()[0]
    before, after = _set_click_through(int(win.winId()))

    stamps: list[int] = []
    flying = {"on": False}
    win.frameSwapped.connect(lambda: stamps.append(time.perf_counter_ns()) if flying["on"] else None)
    arc_marks: list[int] = []

    def on_arc() -> None:
        flying["on"] = True
        arc_marks.append(len(stamps))

    def on_done() -> None:
        flying["on"] = False
        app.quit()

    win.arcStarted.connect(on_arc)
    win.finished.connect(on_done)
    QTimer.singleShot(800, win.next)                 # let the window settle first
    QTimer.singleShot(ARCS * ARC_MS + 10_000, app.quit)   # never outstays its welcome
    app.exec()

    # Frame gaps inside arcs only (the gap across an arc boundary includes no idle time either way).
    gaps = [(b - a) / 1e6 for a, b in zip(stamps, stamps[1:])]
    if len(gaps) < 20:
        print(f"too few frames timed ({len(stamps)}); the window may not have been shown")
        return 1
    q = statistics.quantiles(gaps, n=100)
    dropped = sum(1 for g in gaps if g > 33.3)
    print(f"renderer={win.rendererInterface().graphicsApi().name} dpr={win.devicePixelRatio()} "
          f"exstyle_before={before:#x} exstyle_after={after:#x}")
    print(f"frames={len(stamps)} p50={q[49]:.1f} p95={q[94]:.1f} p99={q[98]:.1f} dropped_over_33ms={dropped}")
    ok = q[94] <= 20 and dropped <= 0.02 * len(gaps)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
