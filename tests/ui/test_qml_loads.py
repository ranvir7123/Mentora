import contextlib
import time

from PySide6.QtCore import QtMsgType, QUrl, qInstallMessageHandler

from app.ui.app import QML_DIR, WINDOWS, load_window, make_engine
from app.ui.bridge import Bridge
from app.ui.demo_backend import STATES, DemoBackend


def _settle(qapp, seconds=0.06):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.005)


@contextlib.contextmanager
def _warnings():
    """Every Qt warning (QML errors included) raised inside the block, labelled with `where[0]`."""
    problems, where = [], ["start"]

    def on_message(kind, context, text):
        if kind not in (QtMsgType.QtDebugMsg, QtMsgType.QtInfoMsg):
            problems.append(f"[{where[0]}] {text}")

    previous = qInstallMessageHandler(on_message)
    try:
        yield problems, where
    finally:
        qInstallMessageHandler(previous)


def _watch(engine, problems, label):
    engine.warnings.connect(lambda errors: problems.extend(f"[{label}] {e.toString()}" for e in errors))


def test_every_window_loads_in_every_state_without_qml_warnings(qapp):
    with _warnings() as (problems, where):
        for window in WINDOWS:
            for state in STATES:
                where[0] = f"{window} / {state}"
                backend = DemoBackend(state)
                engine = make_engine(Bridge(backend))
                _watch(engine, problems, where[0])
                root = load_window(engine, window, backend.view.get(window))
                if root is None:
                    problems.append(f"[{where[0]}] did not load")
                    continue
                backend.replay()          # the state's sound and moment, as the screens see them live
                _settle(qapp)
                root.close()
                root.deleteLater()
                engine.deleteLater()
                _settle(qapp, 0.01)
    assert problems == []


def test_gallery_shows_every_component_without_qml_warnings(qapp):
    with _warnings() as (problems, where):
        where[0] = "gallery"
        engine = make_engine(Bridge(DemoBackend("lesson_step")))
        _watch(engine, problems, "gallery")
        engine.load(QUrl.fromLocalFile(str(QML_DIR / "Gallery.qml")))
        assert engine.rootObjects(), "Gallery.qml did not load"
        _settle(qapp, 0.6)          # let the slide-ins, the ring and the spinner run a little
        engine.rootObjects()[0].close()
        engine.deleteLater()
        _settle(qapp, 0.01)
    assert problems == []


def test_an_opened_panel_keeps_the_mascot_out_of_its_area(qapp):
    # The panel tells the bridge where it is once it opens, wherever the learner has put it.
    from PySide6.QtCore import QRect, QRectF

    from app.ui.app import attach_window

    bridge = Bridge(DemoBackend("lesson_step"))
    engine = make_engine(bridge)
    panel = load_window(engine, "panel")
    attach_window(bridge, "panel", panel)
    panel.setGeometry(QRect(0, 0, 360, 600))           # moved to the left edge
    spot = bridge.landingSpot(QRectF(400, 300, 64, 20), 48, 23)
    assert not QRectF(spot.x(), spot.y() - 23, 48, 71).intersects(QRectF(panel.geometry()))
    engine.deleteLater()
