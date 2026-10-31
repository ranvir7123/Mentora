"""Screenshot any window in any demo state at 200% scaling, without showing anything on the real screen.

    <py> probes\\ui_shot.py <window> --state <state> --out runs\\shots\\<window>-<state>.png
    <py> probes\\ui_shot.py --all            # every window in every state it has, into runs\\shots\\
    <py> probes\\ui_shot.py --sheet          # only the contact sheet, runs\\shots\\all.png, from the shots there

The windows are drawn off screen on a pretend 2560 x 1600 screen at 200% (Ranvir's laptop), so nothing
flashes on the desktop and nothing steals the mouse or keyboard from a live Excel run. The overlay is
see-through, so its shot is laid over a plain spreadsheet grid with the panel's strip on the right.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# A pretend 2560 x 1600 screen, scaled by 2 (1280 x 800 logical, like the real one at 200%). The
# off-screen drawer's option parser splits on ":", so the config path is given without its drive letter.
_config = Path(tempfile.gettempdir()) / "mentora_ui_shot_screen.json"
_config.write_text(json.dumps({"screens": [{"name": "laptop", "x": 0, "y": 0, "width": 2560, "height": 1600,
                                            "logicalDpi": 96, "logicalBaseDpi": 96, "dpr": 1}]}))
os.environ["QT_QPA_PLATFORM"] = "offscreen:configfile=" + _config.as_posix()[2:]
os.environ["QT_SCALE_FACTOR"] = "2"
os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

from PySide6.QtCore import QRectF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402,F401  (so windows come back as QQuickWindow)

from app.ui.app import QML_DIR, WINDOWS, load_window, make_engine  # noqa: E402
from app.ui.bridge import Bridge  # noqa: E402
from app.ui.demo_backend import STATES, DemoBackend  # noqa: E402

EXTRA = {"gallery": "Gallery.qml"}          # windows only the builders look at

HOME_STATES = ("first_run", "home_progress", "home_long_text", "home_no_key", "home_offline", "course_empty",
               "factory_running", "factory_not_ready")
PANEL_STATES = ("lesson_goal", "lesson_step", "lesson_right", "lesson_not_yet", "lesson_hints", "lesson_changed",
                "lesson_clip", "lesson_clip_missing", "lesson_ask", "lesson_app_closed", "lesson_complete",
                "lesson_undone", "lesson_note", "lesson_ask_error", "lesson_app_lost", "long_text")
OVERLAY_STATES = ("pointer_flying", "pointer_watching", "pointer_right", "pointer_top_row", "pointer_button",
                  "lesson_not_yet", "long_text")
ALL = {"home": HOME_STATES, "panel": PANEL_STATES, "overlay": OVERLAY_STATES, "gallery": ("gallery",)}


def _settle(app: QGuiApplication, ms: int) -> None:
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.004)


def _sheet_backdrop(width: int, height: int, panel_w: int) -> QImage:
    """A plain light spreadsheet grid, the way Excel looks behind the pointer, with the panel's strip."""
    img = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor("#F3F3F3"))
    p = QPainter(img)
    p.fillRect(0, 0, width - panel_w, 300, QColor("#E9E9E9"))            # ribbon
    p.fillRect(0, 420, width - panel_w, height - 420, QColor("#FFFFFF"))  # cells
    p.setPen(QPen(QColor("#D4D4D4"), 2))
    xs = [60, 260, 430, 570, 710, 850, 990, 1130, 1270, 1410, 1550, 1690, 1830]
    for x in xs:
        p.drawLine(x, 430, x, height)
    for y in range(430, height, 40):
        p.drawLine(0, y, width - panel_w, y)
    p.setPen(QColor("#444444"))
    font = QFont("Calibri")
    font.setPixelSize(22)
    p.setFont(font)
    for i, x in enumerate(xs[:-1]):
        p.drawText(QRectF(x, 430, xs[i + 1] - x, 40), Qt.AlignmentFlag.AlignCenter, chr(ord("A") + i))
    for r in range(1, (height - 470) // 40 + 1):
        p.drawText(QRectF(0, 430 + r * 40, 60, 40), Qt.AlignmentFlag.AlignCenter, str(r))
    for (col, row), text in {("A", 1): "Item", ("B", 1): "Amount", ("C", 1): "Share", ("A", 2): "Rent",
                             ("B", 2): "12000", ("A", 3): "Food", ("B", 3): "6000", ("A", 4): "Travel",
                             ("B", 4): "2500", ("A", 5): "Phone", ("B", 5): "500", ("A", 6): "Fun",
                             ("B", 6): "2000", ("A", 8): "Total"}.items():
        i = ord(col) - ord("A")
        p.drawText(QRectF(xs[i] + 8, 470 + (row - 1) * 40, xs[i + 1] - xs[i] - 16, 40),
                   Qt.AlignmentFlag.AlignVCenter | (Qt.AlignmentFlag.AlignRight if col == "B" else Qt.AlignmentFlag.AlignLeft),
                   text)
    p.fillRect(width - panel_w, 0, panel_w, height, QColor("#1C1B19"))
    p.end()
    return img


def shoot(window: str, state: str, out: Path, wait_ms: int = 1500) -> Path:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    backend = DemoBackend(state if state in STATES else "lesson_step")
    bridge = Bridge(backend)
    engine = make_engine(bridge)
    if window in EXTRA:
        engine.load(QUrl.fromLocalFile(str(QML_DIR / EXTRA[window])))
        root = engine.rootObjects()[-1] if engine.rootObjects() else None
    else:
        root = load_window(engine, window, backend.view.get(window))
    if root is None:
        raise SystemExit(f"{window} did not load in {state}")
    root.setVisible(True)
    backend.replay()
    _settle(app, wait_ms)
    image = root.grabWindow()
    if window == "overlay":
        backdrop = _sheet_backdrop(image.width(), image.height(), 720)
        p = QPainter(backdrop)
        p.drawImage(0, 0, image)
        p.end()
        image = backdrop
    out.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(out)):
        raise SystemExit(f"could not save {out}")
    root.close()
    engine.deleteLater()
    _settle(app, 30)
    return out


def contact_sheet(paths: list[Path], out: Path, columns: int = 5, cell: tuple[int, int] = (640, 420)) -> Path:
    """Every shot scaled to fit its own cell with its name underneath, on the app's background: one picture
    to judge every window in every state side by side."""
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841  (drawing text needs one)
    gap, label = 24, 44
    rows = -(-len(paths) // columns)
    sheet = QImage(gap + columns * (cell[0] + gap), gap + rows * (cell[1] + label + gap),
                   QImage.Format.Format_RGB32)
    sheet.fill(QColor("#1C1B19"))
    painter = QPainter(sheet)
    font = QFont("Segoe UI")
    font.setPixelSize(22)
    painter.setFont(font)
    for i, path in enumerate(paths):
        x = gap + (i % columns) * (cell[0] + gap)
        y = gap + (i // columns) * (cell[1] + label + gap)
        thumb = QImage(str(path)).scaled(cell[0], cell[1], Qt.AspectRatioMode.KeepAspectRatio,
                                         Qt.TransformationMode.SmoothTransformation)
        left, top = x + (cell[0] - thumb.width()) // 2, y + (cell[1] - thumb.height()) // 2
        painter.drawImage(left, top, thumb)
        painter.setPen(QPen(QColor("#433F39"), 2))      # an edge, since most shots share the sheet's background
        painter.drawRect(left - 1, top - 1, thumb.width() + 1, thumb.height() + 1)
        painter.setPen(QColor("#ABA69C"))
        painter.drawText(QRectF(x, y + cell[1] + 8, cell[0], label - 8),
                         int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop), path.stem)
    painter.end()
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(str(out))
    return out


def _every_shot(shots: Path) -> list[Path]:
    return [shots / f"{window}-{state}.png" for window, states in ALL.items() for state in states
            if (shots / f"{window}-{state}.png").exists()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("window", nargs="?", choices=[*WINDOWS, *EXTRA])
    parser.add_argument("--state", default="first_run")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--wait", type=int, default=1500, help="ms to let animations settle")
    parser.add_argument("--all", action="store_true", help="every window in every state it has")
    parser.add_argument("--sheet", action="store_true", help="only the contact sheet, from the shots already taken")
    args = parser.parse_args()
    shots = ROOT / "runs" / "shots"
    if args.all:
        for window, states in ALL.items():
            if window in EXTRA and not (QML_DIR / EXTRA[window]).exists():
                continue
            for state in states:
                print(shoot(window, state, shots / f"{window}-{state}.png", args.wait))
        print(contact_sheet(_every_shot(shots), shots / "all.png"))
        return 0
    if args.sheet:
        print(contact_sheet(_every_shot(shots), shots / "all.png"))
        return 0
    if not args.window:
        parser.error("name a window, or use --all")
    out = args.out or shots / f"{args.window}-{args.state}.png"
    print(shoot(args.window, args.state, out, args.wait))
    return 0


if __name__ == "__main__":
    sys.exit(main())
