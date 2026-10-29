"""Pretend Excel pieces for the session tests: no Excel, no real time.

`FakeCom` stands in for the COM thread: work runs at once and timers wait until the test moves the
fake clock on. `FakeApp` is a tiny Excel object graph that records the calls that matter and raises if
anything touches it while an event handler is running (handlers may only ask for a read).
"""
from __future__ import annotations

import heapq
import itertools
import traceback
from concurrent.futures import Future
from pathlib import Path

import pywintypes

BUSY = -2147417846                 # RPC_E_SERVERCALL_RETRYLATER
GONE = -2147023174                 # RPC_S_SERVER_UNAVAILABLE: the Excel process was killed
DISCONNECTED = -2147417848         # the workbook object was closed


def com_error(hresult: int, text: str = "fake") -> pywintypes.com_error:
    return pywintypes.com_error(hresult, text, None, None)


class FakeCom:
    def __init__(self) -> None:
        self.now = 0.0
        self.errors: list[str] = []
        self.stopped = False
        self._timers: list = []
        self._seq = itertools.count()
        self._teardown = None

    def start(self, setup, teardown) -> None:
        self._teardown = teardown
        try:
            setup()
        except Exception:   # noqa: BLE001 - like ComThread: the error is kept and start raises
            self.errors.append(traceback.format_exc())
            self.stop()
            raise RuntimeError("fake com failed to start:\n" + "\n".join(self.errors))

    def submit(self, fn) -> Future:
        f: Future = Future()
        if self.stopped:
            f.cancel()
            return f
        try:
            f.set_result(fn())
        except Exception as exc:   # noqa: BLE001
            f.set_exception(exc)
        return f

    def call_later(self, delay_s: float, fn) -> None:
        heapq.heappush(self._timers, (self.now + max(0.0, delay_s), next(self._seq), fn))

    def on_thread(self) -> bool:
        return True

    def advance(self, seconds: float) -> None:
        end = self.now + seconds
        while self._timers and self._timers[0][0] <= end and not self.stopped:
            due, _seq, fn = heapq.heappop(self._timers)
            self.now = max(self.now, due)
            try:
                fn()
            except Exception:   # noqa: BLE001 - like ComThread: one bad timer never stops the rest
                self.errors.append(traceback.format_exc())
        self.now = end

    def pending(self) -> int:
        return len(self._timers)

    def stop(self) -> None:
        if not self.stopped:
            self.stopped = True
            self._timers.clear()
            if self._teardown is not None:
                self._teardown()


class Recorder:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.in_handler = False

    def touch(self, what: str, record: bool = False) -> None:
        if self.in_handler:
            raise AssertionError(f"Excel was called from an event handler: {what}")
        if record:
            self.calls.append(what)


class FakeWorkbook:
    def __init__(self, app: FakeApp, path: Path) -> None:
        self._app = app
        self.path = Path(path)
        self.open = True
        self.saved_to: Path | None = None

    @property
    def Name(self) -> str:
        self._app.rec.touch("wb.Name")
        self._app.check_alive()
        if not self.open:
            raise com_error(DISCONNECTED)
        return self.path.name

    def Close(self, SaveChanges=False) -> None:
        self._app.rec.touch(f"Close(SaveChanges={SaveChanges})", record=True)
        if SaveChanges:
            self.path.write_text("saved by the fake", encoding="utf-8")
        self.open = False
        if self in self._app.books:
            self._app.books.remove(self)

    def learner_closes(self) -> None:
        self.open = False
        self._app.books.remove(self)


class FakeWorkbooks:
    def __init__(self, app: FakeApp) -> None:
        self._app = app

    @property
    def Count(self) -> int:
        self._app.rec.touch("Workbooks.Count")
        self._app.check_alive()
        if self._app.busy:
            raise com_error(BUSY)
        return len(self._app.books)

    def Open(self, path: str) -> FakeWorkbook:
        self._app.rec.touch(f"Open({Path(path).name})", record=True)
        if self._app.fail_open:
            raise com_error(-2146827284, "the file could not be opened")
        wb = FakeWorkbook(self._app, Path(path))
        self._app.books.append(wb)
        self._app.opened.append(Path(path))
        return wb


class FakeApp:
    def __init__(self) -> None:
        self.rec = Recorder()
        self.books: list[FakeWorkbook] = []
        self.opened: list[Path] = []
        self.dead = False
        self.busy = False
        self.fail_open = False
        self._visible = False
        self._alerts = True

    def check_alive(self) -> None:
        if self.dead:
            raise com_error(GONE)

    @property
    def Workbooks(self) -> FakeWorkbooks:
        self.rec.touch("Workbooks")
        return FakeWorkbooks(self)

    @property
    def Hwnd(self) -> int:
        self.rec.touch("Hwnd")
        return 4242

    @property
    def Visible(self) -> bool:
        return self._visible

    @Visible.setter
    def Visible(self, v: bool) -> None:
        self.rec.touch(f"Visible={v}", record=True)
        self._visible = v

    @property
    def DisplayAlerts(self) -> bool:
        return self._alerts

    @DisplayAlerts.setter
    def DisplayAlerts(self, v: bool) -> None:
        self.rec.touch(f"DisplayAlerts={v}", record=True)
        self._alerts = v

    def Quit(self) -> None:
        self.rec.touch("Quit", record=True)
        self.check_alive()


class FakeEvents:
    """Stands in for the workbook event sink: the test fires events by name."""

    def __init__(self, rec: Recorder) -> None:
        self.rec = rec
        self.handler = None
        self.attached_to = None

    def attach(self, wb, handler):
        self.attached_to, self.handler = wb, handler
        return self

    def close(self) -> None:
        self.rec.calls.append("sink.close")

    def fire(self, name: str) -> None:
        self.rec.in_handler = True
        try:
            getattr(self.handler, name)()
        finally:
            self.rec.in_handler = False


class FakeReader:
    """The snapshot reader: counts reads and can be told to find Excel busy for a while."""

    def __init__(self, app: FakeApp, com: FakeCom | None = None) -> None:
        self.app = app
        self.com = com
        self.reads = 0
        self.busy_until = -1.0

    def __call__(self, wb):
        self.app.rec.touch("read")
        if self.com is not None and self.com.now < self.busy_until:
            raise com_error(-2146777998)   # VBA_E_IGNORE: the learner is typing in a cell
        self.reads += 1
        return {"read": self.reads, "book": wb.path.name}


class ComRecorder:
    """A pretend Excel object that writes down every property set and method call made on it.

    Reading an attribute gives another recorder whose name is the path so far, so
    `wb.Worksheets("Budget").Range("B8").Formula = "=SUM(B2:B6)"` is logged as exactly that.
    Looking things up (Worksheets(...), Range(...)) is not logged, only what is done with them.
    A few position properties read as numbers, so code can do sums with them.
    """
    NUMBERS = {"Left": 10.0, "Top": 20.0, "Width": 300.0, "Height": 100.0}
    LOOKUPS = {"Worksheets", "Sheets", "Range", "Cells", "Windows", "Item"}

    def __init__(self, log: list[str], path: str, values: dict | None = None) -> None:
        object.__setattr__(self, "_log", log)
        object.__setattr__(self, "_path", path)
        object.__setattr__(self, "_values", values if values is not None else {})

    def __getattr__(self, name: str):
        if name.startswith("__"):
            raise AttributeError(name)
        path = f"{self._path}.{name}"
        if path in self._values:
            return self._values[path]
        if name in self.NUMBERS:
            return self.NUMBERS[name]
        return ComRecorder(self._log, path, self._values)

    def __setattr__(self, name: str, value) -> None:
        self._log.append(f"{self._path}.{name} = {_shown(value)}")

    def __call__(self, *args, **kwargs):
        parts = [_shown(a) for a in args] + [f"{k}={_shown(v)}" for k, v in kwargs.items()]
        path = f"{self._path}({', '.join(parts)})"
        if self._path.rsplit(".", 1)[-1] not in self.LOOKUPS:
            self._log.append(path)
        return ComRecorder(self._log, path, self._values)


def _shown(value) -> str:
    return value._path if isinstance(value, ComRecorder) else repr(value)


class FakeNode:
    """A pretend UI Automation element: a name, a kind, where it is, and its children."""

    def __init__(self, control_type: str, name: str = "", rect=None, *, offscreen: bool | None = None,
                 selected: bool | None = None, children=()) -> None:
        self.control_type = control_type
        self.name = name
        self.rect = rect
        self.offscreen = rect is None if offscreen is None else offscreen
        self.selected = selected
        self.gone = False
        self.children = list(children)
        self._parent = None
        for child in self.children:
            child._parent = self

    def descendants(self, types=None):
        for child in self.children:
            if types is None or child.control_type in types:
                yield child
            yield from child.descendants(types)

    def parent(self):
        return self._parent

    def refresh(self) -> bool:
        return not self.gone

    def __repr__(self) -> str:
        return f"FakeNode({self.control_type}, {self.name!r}, {self.rect})"
