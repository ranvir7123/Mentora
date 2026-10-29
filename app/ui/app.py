"""Start the screens: the bundled fonts, the QML engine and the three windows.

From the command line, `python -m app.ui.app --demo <state or walkthrough> --show home,panel,overlay`
opens the windows on a `DemoBackend`, so every screen can be seen with no real app behind it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, Mapping

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from app.core.screen import ScreenBackend
from app.ui import winstyle
from app.ui.bridge import Bridge

QML_DIR = Path(__file__).resolve().with_name("qml")
FONTS_DIR = Path(__file__).resolve().with_name("fonts")
WINDOWS = {"home": "HomeWindow.qml", "panel": "PanelWindow.qml", "overlay": "OverlayWindow.qml"}

_fonts_loaded = False


def load_fonts() -> None:
    """Fredoka and Nunito, from the files that ship with the program (once per run)."""
    global _fonts_loaded
    if _fonts_loaded:
        return
    for font in sorted(FONTS_DIR.rglob("*.ttf")):
        if QFontDatabase.addApplicationFont(str(font)) < 0:
            raise RuntimeError(f"the font file {font.name} could not be loaded")
    _fonts_loaded = True


def make_engine(bridge: Bridge) -> QQmlApplicationEngine:
    """A QML engine that finds the screens' modules and hands every window the bridge."""
    load_fonts()
    engine = QQmlApplicationEngine()
    engine.addImportPath(str(QML_DIR))
    engine.setInitialProperties({"bridge": bridge})
    return engine


def load_window(engine: QQmlApplicationEngine, name: str, view: Mapping | None = None) -> QObject | None:
    """Load one window by name (home, panel or overlay). `view` sets window properties that only the
    screens decide, such as which course is open. Returns None when the file does not load."""
    before = len(engine.rootObjects())
    engine.load(QUrl.fromLocalFile(str(QML_DIR / WINDOWS[name])))
    roots = engine.rootObjects()
    if len(roots) == before:
        return None
    root = roots[-1]
    for key, value in (view or {}).items():
        root.setProperty(key, value)
    return root


def attach_window(bridge: Bridge, name: str, root: QObject) -> None:
    """Hook an opened window up. The panel tells the bridge where it is (the mascot keeps out of it, and on
    Windows it never takes focus from the app); the overlay lets every click through to the app below."""
    if name == "panel":
        bridge.register_panel(root)
    elif name == "overlay" and QGuiApplication.platformName() == "windows":
        winstyle.make_click_through(int(root.winId()))


def run_screens(backend: ScreenBackend, *, show: Iterable[str] = ("home",)) -> int:
    """Open the named windows on `backend` and run until the learner quits."""
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    app.setApplicationName("Project X")
    bridge = Bridge(backend)
    engine = make_engine(bridge)
    views = getattr(backend, "view", {}) or {}
    for name in show:
        root = load_window(engine, name, views.get(name))
        if root is None:
            return 1
        attach_window(bridge, name, root)
    app._screens = (bridge, engine)      # keep both alive as long as the application
    return app.exec()


def main(argv: list[str] | None = None) -> int:
    from app.ui.demo_backend import STATES, DemoBackend

    parser = argparse.ArgumentParser(prog="python -m app.ui.app", description="Open the screens on demo data.")
    parser.add_argument("--demo", default="first_run", help="a demo state, or walkthrough: " + ", ".join(STATES))
    parser.add_argument("--show", default="home", help="windows to open, comma separated: home,panel,overlay")
    args = parser.parse_args(argv)
    show = [w.strip() for w in args.show.split(",") if w.strip()]
    unknown = [w for w in show if w not in WINDOWS]
    if unknown:
        parser.error(f"no window called {', '.join(unknown)}; pick from {', '.join(WINDOWS)}")
    if args.demo == "walkthrough":
        backend = DemoBackend("lesson_goal")
        backend.walkthrough()
    else:
        backend = DemoBackend(args.demo)
    return run_screens(backend, show=show)


if __name__ == "__main__":
    sys.exit(main())
