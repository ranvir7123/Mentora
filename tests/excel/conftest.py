from pathlib import Path

import pytest

from app.core.lesson import load_lesson
from tests.excel.fakes import FakeApp, FakeCom, FakeEvents, FakeReader


@pytest.fixture
def budget():
    return load_lesson(Path("lessons/monthly-budget"))


class Rig:
    """An ExcelSession on fake Excel, with what it delivered."""

    def __init__(self, lesson, workdir: Path, *, resume: bool = False, app: FakeApp | None = None,
                 visible: bool = False) -> None:
        from app.excel.session import ExcelSession
        self.app = app or FakeApp()
        self.com = FakeCom()
        self.events = FakeEvents(self.app.rec)
        self.reader = FakeReader(self.app, self.com)
        self.snapshots: list = []
        self.closed = 0
        self.session = ExcelSession(
            lesson, workdir, visible=visible, resume=resume,
            on_snapshot=self.snapshots.append, on_closed=self._closed,
            excel_factory=lambda: self.app, com=self.com, attach_events=self.events.attach,
            reader=self.reader)

    def _closed(self) -> None:
        self.closed += 1


@pytest.fixture
def rig(budget, tmp_path):
    def make(**kw):
        return Rig(kw.pop("lesson", budget), kw.pop("workdir", tmp_path), **kw)
    return make
