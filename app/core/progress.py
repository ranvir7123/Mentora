"""The learner's progress, kept on the laptop in `%LOCALAPPDATA%\\mentora\\`.

`progress.json` holds the points earned each day, where each lesson is up to, the last lesson opened, the
lessons the learner made, the last tips and the learner's name. It is written whole to a temporary file
and then swapped in, so a power cut leaves either the old file or the new one, never half of one. A file
that is broken is set aside as `progress.broken-<time>.json` and the learner starts afresh. A file that
can't be opened (another program holding it) is tried again; if it still can't be, this run's progress is
counted but never saved, so the file is left as it was.

A step's points are earned once: passing it again after reopening a lesson gives none. A finished lesson
played again earns them again.

`attempts.jsonl` is the attempt log the coach reads: one line per finished step, added as it happens. A
half-written last line is skipped.

The streak counts days in a row with at least one step passed, up to today or yesterday. A missed day
resets it quietly: nothing is said and nothing is taken away.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from app.core.runner import LessonDone, StepRecord

log = logging.getLogger(__name__)

FORMAT = 1
READ_TRIES = 3
READ_GAP_S = 0.2


def default_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "mentora"


@dataclass(frozen=True)
class LessonProgress:
    step: int                    # the next step to do, counted from 0 (steps passed so far)
    done: bool
    best_seconds: float | None


class _Broken(ValueError):
    pass


def _check(fits: bool, what: str) -> None:
    if not fits:
        raise _Broken(what)


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _read(data: Any) -> dict:
    """The saved record, checked field by field; any surprise means the file is broken."""
    _check(isinstance(data, dict) and data.get("format") == FORMAT, "not a progress file")
    days = data.get("days", {})
    _check(isinstance(days, dict) and all(isinstance(k, str) and _is_number(v) for k, v in days.items()),
           "days")
    for day in days:
        date.fromisoformat(day)
    lessons = data.get("lessons", {})
    _check(isinstance(lessons, dict), "lessons")
    for state in lessons.values():
        _check(isinstance(state, dict) and isinstance(state.get("step"), int)
               and isinstance(state.get("done"), bool)
               and (state.get("best_seconds") is None or _is_number(state["best_seconds"])), "a lesson")
    made = data.get("made", [])
    _check(isinstance(made, list) and all(isinstance(m, str) for m in made), "made")
    last, tips, name = data.get("last_lesson"), data.get("tips", ""), data.get("name", "")
    _check(last is None or isinstance(last, str), "last_lesson")
    _check(isinstance(tips, str) and isinstance(name, str), "tips or name")
    goal = data.get("daily_goal", 30)
    _check(isinstance(goal, int) and not isinstance(goal, bool) and goal > 0, "daily_goal")
    return {"days": days, "lessons": lessons, "made": made, "last_lesson": last, "tips": tips,
            "name": name, "daily_goal": goal}


class Progress:
    def __init__(self, root: Path, *, today: Callable[[], date] = date.today):
        self._root = Path(root)
        self._today = today
        self._lock = threading.RLock()
        self._unreadable = False
        saved = self._load()
        self._days: dict[str, float] = saved.get("days", {})
        self._lessons: dict[str, dict] = saved.get("lessons", {})
        self.made: list[str] = saved.get("made", [])
        self.last_lesson: str | None = saved.get("last_lesson")
        self.tips: str = saved.get("tips", "")
        self.name: str = saved.get("name", "")
        self.daily_goal: int = saved.get("daily_goal", 30)

    @property
    def _file(self) -> Path:
        return self._root / "progress.json"

    @property
    def _log(self) -> Path:
        return self._root / "attempts.jsonl"

    def _load(self) -> dict:
        for attempt in range(1, READ_TRIES + 1):
            try:
                try:
                    text: str | bytes = self._file.read_text(encoding="utf-8-sig")   # skips an editor's BOM
                except UnicodeDecodeError:
                    text = self._file.read_bytes()   # json works out UTF-16 or UTF-32 from the bytes
                break
            except FileNotFoundError:
                return {}
            except OSError:
                if attempt == READ_TRIES:
                    log.exception("progress.json could not be read; this run is counted but not saved, so the "
                                  "file stays as it was")
                    self._unreadable = True
                    return {}
                time.sleep(READ_GAP_S)
        try:
            return _read(json.loads(text))
        except (ValueError, TypeError) as e:     # UnicodeDecodeError too: bytes that are no kind of text
            aside = self._root / f"progress.broken-{datetime.now():%Y%m%d-%H%M%S-%f}.json"
            log.warning("progress.json is broken (%s); set aside as %s", e, aside.name)
            try:
                os.replace(self._file, aside)
            except OSError:
                log.exception("could not set the broken progress.json aside")
            return {}

    # Saving

    def save(self) -> None:
        """Write the whole record to a temporary file, then swap it in. A failure is logged and the last
        good file stays; the program keeps counting in memory."""
        with self._lock:
            if self._unreadable:                 # the file on disk holds progress this run never read
                return
            data = {"format": FORMAT, "days": self._days, "lessons": self._lessons, "made": self.made,
                    "last_lesson": self.last_lesson, "tips": self.tips, "name": self.name,
                    "daily_goal": self.daily_goal}
            temp = self._file.with_name("progress.json.tmp")
            try:
                self._root.mkdir(parents=True, exist_ok=True)
                with open(temp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=1)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp, self._file)
            except OSError:
                log.exception("progress.json could not be saved; the last good copy is kept")
                temp.unlink(missing_ok=True)

    # Points and the streak

    def _day(self, d: date) -> str:
        return d.isoformat()

    def streak(self) -> int:
        with self._lock:
            day = self._today()
            if self._day(day) not in self._days:
                day -= timedelta(days=1)
            count = 0
            while self._day(day) in self._days:
                count += 1
                day -= timedelta(days=1)
            return count

    def points_today(self) -> int:
        with self._lock:
            return int(self._days.get(self._day(self._today()), 0))

    # Lessons

    def lesson_state(self, lesson_id: str) -> LessonProgress:
        with self._lock:
            state = self._lessons.get(lesson_id)
            if state is None:
                return LessonProgress(step=0, done=False, best_seconds=None)
            return LessonProgress(step=state["step"], done=state["done"], best_seconds=state.get("best_seconds"))

    def _lesson(self, lesson_id: str) -> dict:
        return self._lessons.setdefault(lesson_id, {"step": 0, "done": False, "best_seconds": None})

    def step_passed(self, lesson_id: str, index: int, points: int) -> int:
        """Counts a passed step and gives the points it earned: none when it was passed before."""
        with self._lock:
            state = self._lesson(lesson_id)
            earned = points if state["done"] or index >= state["step"] else 0
            state["step"] = max(state["step"], index + 1)
            today = self._day(self._today())
            self._days[today] = self._days.get(today, 0) + earned
            self.save()
            return earned

    def lesson_done(self, lesson_id: str, done: LessonDone | None) -> None:
        """`done` is None when the lesson's saved work already passed every step on reopening: it is done,
        with no time to keep."""
        with self._lock:
            state = self._lesson(lesson_id)
            state["done"] = True
            best = state.get("best_seconds")
            if done is not None:
                state["best_seconds"] = done.seconds if best is None else min(best, done.seconds)
            self.save()

    def opened(self, lesson_id: str) -> None:
        with self._lock:
            self.last_lesson = lesson_id
            self.save()

    def lesson_made(self, lesson_id: str) -> None:
        with self._lock:
            if lesson_id not in self.made:
                self.made.append(lesson_id)
                self.save()

    def keep_tips(self, text: str) -> None:
        with self._lock:
            self.tips = text
            self.save()

    # The attempt log

    def log_attempt(self, lesson_id: str, record: StepRecord) -> None:
        line = json.dumps({"lesson": lesson_id, "step_id": record.step_id, "tries": record.tries,
                           "hints": record.hints, "seconds": record.seconds, "first_try": record.first_try,
                           "at": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False)
        with self._lock:
            try:
                self._root.mkdir(parents=True, exist_ok=True)
                self._end_last_line()
                with open(self._log, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                log.exception("attempts.jsonl could not be written")

    def _end_last_line(self) -> None:
        """A line cut short by a power cut would swallow the next one; start a fresh line after it."""
        try:
            with open(self._log, "rb") as f:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    with open(self._log, "a", encoding="utf-8") as g:
                        g.write("\n")
        except (FileNotFoundError, OSError):
            pass

    def attempts(self) -> list[StepRecord]:
        """Every finished step, oldest first. Each step is named "<lesson>/<step>", since two lessons can
        both have a step called "run"."""
        with self._lock:
            try:
                lines = self._log.read_text(encoding="utf-8").splitlines()
            except FileNotFoundError:
                return []
            except OSError:
                log.exception("attempts.jsonl could not be read")
                return []
        records = []
        for line in lines:
            try:
                d = json.loads(line)
                records.append(StepRecord(step_id=f"{d['lesson']}/{d['step_id']}", tries=int(d["tries"]),
                                          hints=int(d["hints"]), seconds=float(d["seconds"]),
                                          first_try=bool(d["first_try"])))
            except (ValueError, TypeError, KeyError):
                continue
        return records
