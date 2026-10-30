"""See the program start the way a learner starts it, and the panel dock beside the lesson's app.

    <py> probes\\app_start.py                # demo data, drawn off screen at 200%: nothing shows on the desktop
    <py> probes\\app_start.py --on-screen    # demo data on the real screen (the windows appear and take focus)
    <py> probes\\app_start.py --live         # the real program: opens real Excel. Check free memory first.

Demo: runs the code of `python -m app --demo first_run`, grabs home (runs\\shots\\app-first_run.png), opens the
budget lesson, checks that home stepped aside and that the panel sits on the right 360 px at full height, grabs
the docked panel over a pretend spreadsheet (runs\\shots\\app-docked.png), closes the lesson, checks home came
back, then closes home and checks the program ended.

Live: the same on the real backend, with the learner's progress kept in runs\\app_start\\ instead of the real
one. It clicks home's Continue button with the real mouse, as a learner would (a click is what lets Mentora
bring Excel to the front), checks the budget lesson opened, waits until Excel is ready, checks Excel came to
the front and the panel against where the program put Excel, grabs the whole screen (runs\\shots\\app-live.png),
closes the lesson and quits, then waits up to 15 s for the EXCEL.EXE processes it started to end (want 0
left). Needs Excel and about 3 GB of free memory; leave the mouse and keyboard alone while it runs (about a
minute): it does not click if the mouse moved after home opened, and clicks only where home is on top.

Each check prints "ok" or "FAILED"; exit code 0 means every check passed.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SHOTS = ROOT / "runs" / "shots"
LESSON = "monthly-budget"


class Probe:
    """Runs a script of steps on the program's own event loop, while `main()` runs it."""

    def __init__(self) -> None:
        self.failed = 0

    def check(self, ok: bool, what: str) -> None:
        print(f"{'ok    ' if ok else 'FAILED'}  {what}", flush=True)
        self.failed += not ok

    def run(self, script: Iterator[tuple[Callable[[], bool], float, str]]) -> None:
        """Each step the script yields is (condition, seconds allowed, what it means): the next step waits
        until the condition holds, and a step that times out fails and ends the program (exit code 1)."""
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QGuiApplication

        def advance() -> None:
            try:
                condition, seconds, what = next(script)
            except StopIteration:
                return
            except Exception as e:                        # a broken step must not leave the program running
                self.check(False, f"the probe itself broke: {e!r}")
                QGuiApplication.exit(1)
                return
            deadline = time.monotonic() + seconds

            def poll() -> None:
                if condition():
                    advance()
                elif time.monotonic() > deadline:
                    self.check(False, f"{what} (waited {seconds:g} s)")
                    QGuiApplication.exit(1)          # not quit(): the panel refuses that while a lesson is open
                else:
                    QTimer.singleShot(50, poll)
            poll()

        QTimer.singleShot(0, advance)


def _parts():
    """The program's pieces once `main()` has opened them: the bridge, the windows by name and the layout."""
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance()
    bridge, engine = app._screens
    home, panel, overlay = engine.rootObjects()[:3]
    _lock, layout, _docking = app._program
    return bridge, {"home": home, "panel": panel, "overlay": overlay}, layout


def _physical(window) -> tuple[int, int, int, int]:
    """A window's place in physical px on the main screen."""
    from PySide6.QtGui import QGuiApplication
    screen = QGuiApplication.primaryScreen()
    g, dpr = screen.geometry(), screen.devicePixelRatio()
    r = window.geometry()
    return (round(g.x() + (r.x() - g.x()) * dpr), round(g.y() + (r.y() - g.y()) * dpr),
            round(r.width() * dpr), round(r.height() * dpr))


def _expected_split():
    """Where the program puts the app and the panel on this screen, from the same sum it uses."""
    from PySide6.QtGui import QGuiApplication

    from app.core.types import Rect
    from app.main import split_screen
    screen = QGuiApplication.primaryScreen()
    g, a = screen.geometry(), screen.availableGeometry()
    return split_screen(Rect(a.x(), a.y(), a.width(), a.height()), origin=(g.x(), g.y()),
                        dpr=screen.devicePixelRatio())


def _save(image, name: str) -> Path:
    SHOTS.mkdir(parents=True, exist_ok=True)
    out = SHOTS / name
    if not image.save(str(out)):
        raise RuntimeError(f"could not save {out}")
    print(f"        saved {out}", flush=True)
    return out


def _settle(seconds: float):
    """A step that just lets the screens draw for `seconds`."""
    end = time.monotonic() + seconds
    return (lambda: time.monotonic() >= end), seconds + 5, "the screens settle"


def demo(probe: Probe, *, off_screen: bool):
    from PySide6.QtGui import QGuiApplication, QPainter

    yield (lambda: True), 1, "the program starts"
    bridge, windows, _ = _parts()
    home, panel = windows["home"], windows["panel"]
    yield (lambda: home.isVisible() and home.isExposed()), 5, "home opens"
    probe.check(not panel.isVisible(), "the panel stays hidden while no lesson is open")
    probe.check(_carry_on_button(home) is not None, "home shows a Continue or Start button")
    yield _settle(1.5)
    _save(home.grabWindow(), "app-first_run.png")

    bridge.openLesson(LESSON)
    yield (lambda: panel.isVisible() and not home.isVisible()), 5, "home steps aside and the panel opens"
    yield _settle(1.5)
    app_spot, panel_spot = _expected_split()
    probe.check(_physical(panel) == (panel_spot.x, panel_spot.y, panel_spot.w, panel_spot.h),
                f"the panel sits at {tuple(map(int, (panel_spot.x, panel_spot.y, panel_spot.w, panel_spot.h)))}"
                f" (it is at {_physical(panel)}), beside the app's {tuple(map(int, (app_spot.x, app_spot.y, app_spot.w, app_spot.h)))}")
    if off_screen:
        from ui_shot import _sheet_backdrop               # the pretend spreadsheet the overlay's shots use
        shot = panel.grabWindow()
        screen = QGuiApplication.primaryScreen()
        size = screen.geometry().size() * screen.devicePixelRatio()
        picture = _sheet_backdrop(size.width(), size.height(), shot.width())
        p = QPainter(picture)
        p.drawImage(size.width() - shot.width(), 0, shot)
        p.end()
    else:
        picture = QGuiApplication.primaryScreen().grabWindow(0).toImage()
    _save(picture, "app-docked.png")

    bridge.closeLesson()
    yield (lambda: home.isVisible() and not panel.isVisible()), 5, "home comes back when the lesson closes"
    probe.check(True, "home came back and the panel hid")
    home.close()
    yield (lambda: False), 5, "closing home ends the program"


def excel_pids() -> set[int]:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq EXCEL.EXE", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return {int(line.split('","')[1]) for line in out.splitlines() if line.startswith('"EXCEL.EXE"')}


def _carry_on_button(home):
    """Where home's Continue (or Start) button is, in physical px on the main screen; None if it isn't showing."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QGuiApplication
    items = [home.contentItem()]
    while items:
        item = items.pop()
        items.extend(item.childItems())
        if item.metaObject().className().startswith("ChunkyButton") and item.isVisible() \
                and item.property("text") in ("Continue", "Start"):
            p = item.mapToGlobal(QPointF(item.width() / 2, item.height() / 2))
            screen = QGuiApplication.primaryScreen()
            g, dpr = screen.geometry(), screen.devicePixelRatio()
            return round(g.x() + (p.x() - g.x()) * dpr), round(g.y() + (p.y() - g.y()) * dpr)
    return None


def _on_top(window) -> None:
    """Puts `window` above the other programs' windows without giving it the keyboard. A program started from
    a terminal opens in front; this probe is started from a background shell, so home may open behind."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32")
    user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    ctypes.c_int, wintypes.UINT)
    keep = 0x0001 | 0x0002 | 0x0010                      # no size, move or keyboard change
    for after in (-1, -2):                               # always on top, then back to normal: it stays above
        user32.SetWindowPos(int(window.winId()), after, 0, 0, 0, 0, keep)


def live(probe: Probe, before: set[int]):
    from PySide6.QtGui import QGuiApplication

    from app.factory.input import UserTookOver, WindowsHands
    from app.ui.winstyle import foreground
    from app.win.windows import process_id

    yield (lambda: True), 1, "the program starts"
    bridge, windows, layout = _parts()
    home, panel = windows["home"], windows["panel"]
    yield (lambda: home.isVisible() and home.isExposed()), 10, "home opens"
    hands = WindowsHands()                               # from here on, the mouse must stay where it is
    app_spot, panel_spot = layout()
    probe.check((app_spot, panel_spot) == _expected_split(), "the program's layout matches this screen")
    yield _settle(1.5)

    spot = _carry_on_button(home)
    probe.check(spot is not None, "home shows a Continue or Start button")
    if spot is None:
        QGuiApplication.exit(1)
        return
    _on_top(home)
    yield _settle(0.5)
    if not hands.app_at(int(home.winId()), *spot):
        probe.check(False, f"home is on top at {spot}, so the click lands on its button")
        QGuiApplication.exit(1)
        return
    try:
        hands.do({"type": "click", "x": spot[0], "y": spot[1]})
    except UserTookOver:
        probe.check(False, "the mouse stayed still until the click (someone moved it, so nothing was clicked)")
        QGuiApplication.exit(1)
        return
    yield (lambda: panel.isVisible() and not home.isVisible()), 10, "home steps aside and the panel opens"
    # Mentora's own doing, not Excel's: the panel holds the front from the click until Excel is ready.
    yield (lambda: foreground() == int(panel.winId())), 5, "the panel holds the front while Excel opens"
    probe.check(True, "the panel held the front while Excel opened")
    opened = bridge.lesson.get("id")
    probe.check(opened == LESSON, f"the click opened {LESSON} (it opened {opened})")
    yield (lambda: bridge.lesson.get("appState") == "ready"), 90, "Excel opens and gets ready"
    excel = excel_pids() - before
    probe.check(bool(excel), "the lesson started its own Excel")
    # A timeout here fails the check and ends the program; reaching the next line means Excel is in front.
    yield (lambda: process_id(foreground()) in excel), 15, "Excel comes to the front, so the learner can type in it"
    probe.check(True, "Excel came to the front")
    yield _settle(3)
    probe.check(_physical(panel) == (panel_spot.x, panel_spot.y, panel_spot.w, panel_spot.h),
                f"the panel sits at {(panel_spot.x, panel_spot.y, panel_spot.w, panel_spot.h)}"
                f" (it is at {_physical(panel)}); Excel was sent to {(app_spot.x, app_spot.y, app_spot.w, app_spot.h)}")
    _save(QGuiApplication.primaryScreen().grabWindow(0).toImage(), "app-live.png")

    bridge.closeLesson()
    yield (lambda: home.isVisible() and not panel.isVisible()), 10, "home comes back when the lesson closes"
    probe.check(True, "home came back and the panel hid")
    home.close()
    yield (lambda: False), 30, "closing home ends the program"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--on-screen", action="store_true", help="show the demo on the real screen")
    where.add_argument("--live", action="store_true", help="the real program, in real Excel")
    args = parser.parse_args()
    off_screen = not (args.on_screen or args.live)
    if off_screen:
        sys.path.insert(0, str(ROOT / "probes"))
        import ui_shot  # noqa: F401  (draws on a pretend 2560 x 1600 screen at 200%, off the desktop)

    import os

    from PySide6.QtGui import QGuiApplication

    import app.main as program
    QGuiApplication(sys.argv[:1])
    probe = Probe()
    if args.live:
        os.environ["MENTORA_SHOW_UNPROVEN"] = "1"         # the budget lesson has no proof yet
        data = ROOT / "runs" / "app_start"
        program.default_root = lambda: data              # keep the learner's real progress out of it
        program.Progress(data).opened(LESSON)             # so home's Continue button carries on with it
        before = excel_pids()
        probe.run(live(probe, before))
        code = program.main([])
        end = time.monotonic() + 15                       # Excel saves and quits after the program has gone
        while excel_pids() - before and time.monotonic() < end:
            time.sleep(0.5)
        probe.check(not (excel_pids() - before), "no Excel left running (waited up to 15 s)")
    else:
        probe.run(demo(probe, off_screen=off_screen))
        code = program.main(["--demo", "first_run"])
    probe.check(code == 0, f"the program ended cleanly (exit code {code})")
    print("all checks passed" if not probe.failed else f"{probe.failed} check(s) FAILED", flush=True)
    return 1 if probe.failed else 0


if __name__ == "__main__":
    sys.exit(main())
