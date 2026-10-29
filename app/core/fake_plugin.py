"""A pretend app for tests: its whole state is a dictionary.

Every part of the program (the runner, the screens' backend, the lesson factory) can be tested against
this instead of real Excel. A snapshot is a plain copy of the dictionary. Everything happens at once:
each Future it returns is already done.
"""
from __future__ import annotations

import json
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Callable, Mapping

from app.core.types import Call, CheckKind, OpKind, Param, Rect, Spot, Target, Verdict

DEFAULT_SPOT = Spot(Rect(100, 100, 80, 24))


def _done(result: Any = None, error: BaseException | None = None) -> Future:
    f: Future = Future()
    if error is not None:
        f.set_exception(error)
    else:
        f.set_result(result)
    return f


def _equals(snap: Mapping, args: Mapping) -> Verdict:
    key, want = args["key"], args["value"]
    if key not in snap:
        return Verdict.waiting()
    if snap[key] == want:
        return Verdict.right()
    return Verdict.wrong(f"differs:{key}", f"Not yet: {key} says {snap[key]}. It should say {want}.")


def _has(snap: Mapping, args: Mapping) -> Verdict:
    return Verdict.right() if args["key"] in snap else Verdict.waiting()


class FakeSession:
    def __init__(self, starter: Mapping, workdir: Path, *, resume: bool,
                 on_snapshot: Callable[[Any], None], on_closed: Callable[[], None]):
        self._starter = dict(starter)
        self._saved = workdir / "state.json"
        self._on_snapshot = on_snapshot
        self._on_closed = on_closed
        self._refuse = 0
        self._latest: dict | None = None
        self._state = (json.loads(self._saved.read_text(encoding="utf-8"))
                       if resume and self._saved.exists() else dict(self._starter))
        self.spots: dict[str, Spot] = {}       # tests may place keys; others get DEFAULT_SPOT
        self.watching: Target | None = None
        self.waiting = False
        self.placed: Rect | None = None
        self.closed = False
        self._deliver()

    def _deliver(self) -> None:
        self._latest = dict(self._state)
        self._on_snapshot(dict(self._state))

    def hwnd(self) -> int:
        return 0

    def latest(self) -> Any | None:
        return None if self._latest is None else dict(self._latest)

    def read_now(self) -> Future:
        return _done(dict(self._state))

    def perform(self, op: Call) -> Future:
        if self._refuse:
            self._refuse -= 1
            return _done(error=RuntimeError(f"the fake app refused {op.kind}"))
        if op.kind == "set":
            self._state[op.args["key"]] = op.args["value"]
        elif op.kind == "delete":
            self._state.pop(op.args["key"], None)
        else:
            return _done(error=ValueError(f"the fake app has no operation {op.kind!r}"))
        self._deliver()
        return _done()

    def reset(self) -> Future:
        self._state = dict(self._starter)
        self._deliver()
        return _done()

    def locate(self, target: Target) -> Future:
        if target.kind != "key":
            return _done(None)
        return _done(self.spots.get(target.ref, DEFAULT_SPOT))

    def watch(self, target: Target | None, on_spot: Callable[[Spot | None], None]) -> None:
        self.watching = target
        if target is not None:
            on_spot(self.locate(target).result())

    def set_waiting(self, waiting: bool) -> None:
        self.waiting = waiting

    def place(self, rect: Rect) -> Future:
        self.placed = rect
        return _done()

    def close(self, save: bool = False) -> None:
        if save:
            self._saved.parent.mkdir(parents=True, exist_ok=True)
            self._saved.write_text(json.dumps(self._state), encoding="utf-8")
        self.closed = True

    # Test helpers: what a learner (or a stubborn app) would do.

    def learner_sets(self, key: str, value: Any) -> None:
        self._state[key] = value
        self._deliver()

    def refuse_next(self, n: int) -> None:
        self._refuse = n

    def closed_by_learner(self) -> None:
        self.closed = True
        self._on_closed()


class FakePlugin:
    app_id = "fake"
    title = "Fake app"
    target_kinds = frozenset({"key"})

    def __init__(self) -> None:
        self.checks = {
            "equals": CheckKind("equals", (Param("key", "text"), Param("value", "value")), _equals,
                                "the key holds this value"),
            "has": CheckKind("has", (Param("key", "text"),), _has, "the key exists"),
        }
        self.ops = {
            "set": OpKind("set", (Param("key", "text"), Param("value", "value")), "set the key"),
            "delete": OpKind("delete", (Param("key", "text"),), "remove the key"),
        }

    def validate_starter(self, starter: Mapping) -> list[str]:
        return [] if isinstance(starter, Mapping) else ["starter: must be keys and values"]

    def open(self, lesson: Any, workdir: Path, *, visible: bool = True, resume: bool = False,
             on_snapshot: Callable[[Any], None], on_closed: Callable[[], None]) -> FakeSession:
        return FakeSession(lesson.starter, workdir, resume=resume,
                           on_snapshot=on_snapshot, on_closed=on_closed)
