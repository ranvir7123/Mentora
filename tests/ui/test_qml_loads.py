import time

from PySide6.QtCore import QtMsgType, qInstallMessageHandler

from app.ui.app import WINDOWS, load_window, make_engine
from app.ui.bridge import Bridge
from app.ui.demo_backend import STATES, DemoBackend


def _settle(qapp, seconds=0.06):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.005)


def test_every_window_loads_in_every_state_without_qml_warnings(qapp):
    problems = []

    def on_message(kind, context, text):
        if kind != QtMsgType.QtDebugMsg and kind != QtMsgType.QtInfoMsg:
            problems.append(f"[{current}] {text}")

    previous = qInstallMessageHandler(on_message)
    try:
        for window in WINDOWS:
            for state in STATES:
                current = f"{window} / {state}"
                backend = DemoBackend(state)
                bridge = Bridge(backend)
                engine = make_engine(bridge)
                engine.warnings.connect(lambda errors, c=current: problems.extend(
                    f"[{c}] {e.toString()}" for e in errors))
                root = load_window(engine, window, backend.view.get(window))
                if root is None:
                    problems.append(f"[{current}] did not load")
                    continue
                backend.replay()          # the state's sound and moment, as the screens see them live
                _settle(qapp)
                root.close()
                root.deleteLater()
                engine.deleteLater()
                _settle(qapp, 0.01)
    finally:
        qInstallMessageHandler(previous)
    assert problems == []
