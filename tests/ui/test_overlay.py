"""The see-through layer over the screen, as a window: when it is up and when it is gone."""
import time

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtQuick import QQuickWindow  # noqa: F401  (so windows come back as Quick windows)

from app.ui.app import load_window, make_engine
from app.ui.bridge import Bridge
from app.ui.demo_backend import DemoBackend


def _settle(qapp, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.005)


def test_the_layer_is_put_on_screen_once_at_start_then_hides(qapp):
    """Its first appearance is slow (its surface is made then); doing that at start, while it is empty,
    keeps the mascot's first flight smooth. With no pointer it must not stay up."""
    backend = DemoBackend("lesson_step")
    bridge = Bridge(backend)
    engine = make_engine(bridge)
    root = load_window(engine, "overlay", backend.view.get("overlay"))
    frames = []
    root.frameSwapped.connect(lambda: frames.append(1))
    backend.replay()
    _settle(qapp, 0.3)
    try:
        assert frames, "the layer never drew a frame before its first flight"
        assert not root.isVisible(), "the layer stayed up with no pointer to show"
    finally:
        root.close()
        root.deleteLater()
        engine.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)    # no event loop runs to do it
