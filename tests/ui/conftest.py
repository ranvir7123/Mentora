import os

import pytest

# Screens are drawn off screen in tests: nothing flashes on the learner's desktop and no display is needed.
# The off-screen drawer reads fonts from a folder, so it gets Windows' own, as the real screens do.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])
    yield app
