"""The program's backend: what the screens show, made from the real app and the learner's progress.

It is the `ScreenBackend` of app/core/screen.py. The screens call its actions on their own thread and
each returns at once. The app's plug-in calls back on its own thread, and those calls only queue work.

Threads. Opening, placing and closing the app, judging its snapshots and following the step's target all
run one at a time on the "app" worker, so a slow app (Excel can take 5 s to close) never freezes the
screens. The coach and the key check run on the "meta" worker and the lesson maker on its own, since each
may take many seconds. One lock guards the state; slow calls to an app or to Meta are made outside it.
Each opening of an app has its own number (`gen`): news from an app that was closed or replaced is
dropped.

What the learner sees, step by step:
- A right step: the banner says so, the "right" sound plays, points are saved and the mascot cheers on the
  spot for a moment (`CHEER_SECONDS`) before flying to the next step's target. More news from the app
  ends the cheer at once.
- Not yet: the line from the check, with its sound every time, even for the same mistake again (the
  screens drop a state identical to the last one, so the sound is what brings the banner back after Try
  again). Nothing is ever taken away.
- A done step that came undone is listed in `changed`; the learner can ask to be pointed at it. When the
  last step is done while one is undone, the banner says which one to fix and the lesson finishes once it
  is fixed.
- The app closed: the panel says so, with the app's own reason when it gives one, and Reopen carries on
  from the saved work copy, ticking the steps already done without a sound.
- Ask: the coach answers in words only. Only a check ever ticks a step.
"""
from __future__ import annotations

import copy
import logging
import os
import re
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, urlsplit

from app.coach.coach import CoachUnavailable
from app.core.lesson import Lesson, Step
from app.core.library import Library
from app.core.plugin import AppPlugin, AppSession
from app.core.progress import Progress
from app.core.runner import LessonDone, LessonRun, NotYet, StepPassed
from app.core.screen import CLOSED_LESSON, EMPTY_HOME, HIDDEN_POINTER, Box
from app.core.services import Coach, LessonMaker
from app.core.types import Rect, Spot
from app.meta.client import NoKey
from app.meta.key import find_key as _find_key

log = logging.getLogger(__name__)

CHEER_SECONDS = 1.5              # the mascot cheers on a right step this long before moving on
FLIGHT_SECONDS = 0.6             # a flight to the target takes this long; then the mascot watches
KEY_CHECK_SECONDS = 2.0          # after the key's setup line is copied, look for the key this often
KEY_CHECKS = 300                 # for up to 10 minutes

STAGES = ("download", "read", "write", "prove", "test", "publish")
_STAGE_STATES = ("waiting", "running", "done", "failed")

NO_COACH = "The Ask box isn't set up on this computer. Try Hint or Show me."
COACH_BROKE = "The Ask box can't answer right now. Your lesson still works: try Hint or Show me."
TIPS_BROKE = "Tips are offline right now. Your lessons still work."
NO_MAKER = "Making lessons isn't set up on this computer."
MAKER_BROKE = "Something went wrong while making this lesson. Try another video."
NOT_ON_SHELF = "This lesson didn't pass its checks, so it isn't on your shelf."
SAVE_NOTE = "Press Ctrl+S to save, then your work gets checked."
MAX_COACH_CELLS = 4

_VIDEO_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _timer(seconds: float, fn: Callable[[], None]) -> None:
    t = threading.Timer(seconds, fn)
    t.daemon = True
    t.start()


# Helpers the screens' shapes are made with.

def youtube_id(url: str) -> str | None:
    """The video's id when `url` is a YouTube link (watch, youtu.be, shorts, embed or live); else None."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or (parts.hostname or "").lower() not in _VIDEO_HOSTS:
        return None
    path = [p for p in parts.path.split("/") if p]
    if (parts.hostname or "").lower() == "youtu.be":
        found = path[0] if path else None
    elif path[:1] == ["watch"]:
        found = (parse_qs(parts.query).get("v") or [None])[0]
    elif len(path) >= 2 and path[0] in ("shorts", "embed", "live"):
        found = path[1]
    else:
        found = None
    return found if found and _VIDEO_ID.match(found) else None


def clip_view(lesson: Lesson, step: Step, recordings: Path) -> dict:
    """The step's clip: "available" when the lesson's video is saved here, "missing" when it isn't (the
    screens then offer the YouTube link at the clip's start), "none" when the step has no clip."""
    if step.clip is None:
        return {"state": "none", "file": "", "start": 0.0, "end": 0.0, "videoUrl": ""}
    video_id = youtube_id(lesson.source.url) if lesson.source is not None else None
    start, end = float(step.clip.start), float(step.clip.end)
    url = f"https://www.youtube.com/watch?v={video_id}&t={int(start)}s" if video_id else ""
    video = recordings / video_id / "video.mp4" if video_id else None
    if video is not None and video.is_file():
        return {"state": "available", "file": str(video), "start": start, "end": end, "videoUrl": url}
    return {"state": "missing", "file": "", "start": start, "end": end, "videoUrl": url}


def save_note(snap: Any) -> str:
    """Asks the learner to save when the code they typed isn't saved yet: only saved files get checked."""
    files = getattr(snap, "files", None)
    if isinstance(files, Mapping) and any(getattr(f, "saved", True) is False for f in files.values()):
        return SAVE_NOTE
    return ""


def coach_state(snap: Any, step: Step) -> dict:
    """A small look at the app for the coach: for Excel the target cells' values and formulas and the
    selected cell; for VS Code the open file, whether it is saved, the problem count and the last run's
    exit code, never the code itself; for the fake app its keys."""
    if snap is None:
        return {}
    if isinstance(snap, Mapping):
        return {str(k): v for k, v in list(snap.items())[:12]}
    if hasattr(snap, "cell") and hasattr(snap, "selection"):
        state: dict[str, Any] = {}
        if step.target.kind in ("cell", "range"):
            from app.excel.address import parse_area
            try:
                area = parse_area(step.target.ref)
            except ValueError:
                area = None
            if area is not None:
                sheet = area.sheet_or(snap.active_sheet)
                for address in area.cells()[:MAX_COACH_CELLS]:
                    cell = snap.cell(sheet, address)
                    state[f"{sheet}!{address}"] = cell.value
                    if cell.formula:
                        state[f"{sheet}!{address} formula"] = cell.formula
        state["selected cell"] = f"{snap.active_sheet}!{snap.selection}"
        return state
    if hasattr(snap, "files") and hasattr(snap, "problems"):
        active = getattr(snap, "active", None)
        name = Path(active.path).name if active is not None else "none"
        file = snap.files.get(active.path) if active is not None else None
        state = {"open file": name, "saved": True if file is None else bool(file.saved),
                 "problems": len(snap.problems)}
        run = getattr(snap, "run", None)
        if run is not None:
            state["last run exit code"] = "still running" if run.exit_code is None else run.exit_code
        return state
    return {}


def _undone_text(changed: list[int], app_name: str) -> str:
    """The banner while every step is done but some earlier ones came undone, so the lesson can't finish."""
    numbers = [str(i + 1) for i in changed]
    if len(numbers) == 1:
        return f"Every step is done, but step {numbers[0]} changed. Fix it in {app_name} to finish."
    listed = ", ".join(numbers[:-1]) + f" and {numbers[-1]}"
    return f"Every step is done, but steps {listed} changed. Fix them in {app_name} to finish."


def _capitalised(text: str) -> str:
    text = (text or "").strip()
    return text[:1].upper() + text[1:]


def _box(r: Rect) -> Box:
    """A rectangle as the screens get it: whole physical pixels."""
    return {"x": int(round(r.x)), "y": int(round(r.y)), "w": int(round(r.w)), "h": int(round(r.h))}


def _box_or_none(r: Rect | None) -> Box | None:
    return None if r is None else _box(r)


@dataclass
class _Open:
    """The lesson open in the panel, and its app."""
    lesson: Lesson
    plugin: AppPlugin
    gen: int
    run: LessonRun | None = None
    session: AppSession | None = None
    app_state: str = "opening"
    closed_reason: str = ""
    resuming: bool = False           # the next snapshot is the first after reopening a saved work copy
    snap: Any = None
    shown: int = 0                   # the step the panel shows; lags the run while the mascot cheers
    banner: dict | None = None
    points: int = 0
    verdict: tuple[int, str] | None = None   # the last Not yet: its step and line, for the coach
    hints: dict[int, list[str]] = field(default_factory=dict)
    logged: int = 0                  # the run's records already in the attempt log
    complete: dict | None = None
    ask: dict = field(default_factory=lambda: {"state": "idle", "question": "", "answer": ""})
    asked: int = 0
    cheering: int | None = None      # the step just done, while the mascot cheers
    cheer: int = 0
    goto: int | None = None          # a changed step the learner asked to be pointed at
    pointing: int | None = None      # the step whose target the app watches
    watch: int = 0
    landed: bool = False
    flight: int = 0
    pointer: dict = field(default_factory=lambda: copy.deepcopy(HIDDEN_POINTER))
    streak_before: int = 0           # the days in a row when the lesson opened, so the celebration ticks
                                     # the streak up only when this lesson made today count


class Backend:
    def __init__(self, library: Library, progress: Progress, plugins: Mapping[str, AppPlugin],
                 coach: Coach | None, maker: LessonMaker | None, *, workdir: Path,
                 layout: Callable[[], tuple[Rect, Rect]], front: Callable[[int, Callable[[], bool]], object],
                 later: Callable[[float, Callable[[], None]], None] = _timer,
                 find_key: Callable[[], tuple[str | None, str]] = _find_key,
                 recordings: Path = Path("recordings"), maker_app: str = "excel",
                 login_name: str | None = None):
        """`layout()` gives (where the app goes, where the panel is) in physical px; it is called on the app
        worker, so it must not touch the screens. `front(hwnd, still)` is called on the app worker once the
        lesson's app is in its place as it opens, to bring it to the front; it must hand that to the screens'
        thread, after the news it has already been sent, and bring the app forward only if `still()` is true
        by then (the learner may have gone home in between). `later(seconds, fn)` runs `fn` once after
        `seconds`, on any thread. `recordings` holds the lesson maker's saved videos, one folder per YouTube id."""
        self._library = library
        self._progress = progress
        self._front = front
        self._plugins = dict(plugins)
        self._coach = coach
        self._maker = maker
        self._workdir = Path(workdir)
        self._layout = layout
        self._later = later
        self._find_key = find_key
        self._recordings = Path(recordings)
        self._maker_app = maker_app
        login = os.environ.get("USERNAME", "") if login_name is None else login_name
        self._login = login.title() if login.isalpha() else ""

        self._lock = threading.RLock()
        self._listeners: list[Callable[[str, Mapping], None]] = []
        self._open: _Open | None = None
        self._gen = 0
        self._muted = False
        self._tips = {"state": "ready", "text": progress.tips} if progress.tips else {"state": "none", "text": ""}
        self._factory = copy.deepcopy(EMPTY_HOME["factory"])
        self._key_hunt = 0
        try:
            self._meta = "ok" if self._find_key()[0] else "no_key"
        except Exception:
            log.exception("could not look for the Meta key")
            self._meta = "no_key"

        self._idle = threading.Condition()
        self._pending = 0
        self._stopped = False
        self._work = ThreadPoolExecutor(1, thread_name_prefix="backend-app")
        self._meta_pool = ThreadPoolExecutor(1, thread_name_prefix="backend-meta")
        self._factory_pool = ThreadPoolExecutor(1, thread_name_prefix="backend-factory")

        self._home_shape = self._home_view()
        self._lesson_shape = self._lesson_view(None)
        self._pointer_shape = copy.deepcopy(HIDDEN_POINTER)

    # The screens' side.

    def subscribe(self, listener: Callable[[str, Mapping], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def home(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._home_shape)

    def lesson(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._lesson_shape)

    def pointer(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._pointer_shape)

    def _send(self, name: str, payload: Mapping) -> None:
        for listener in list(self._listeners):
            try:
                listener(name, copy.deepcopy(payload))
            except Exception:
                log.exception("a screen listener failed on %s", name)

    def _publish_home(self) -> None:
        with self._lock:
            self._home_shape = self._home_view()
            self._send("home", self._home_shape)

    def _publish_lesson(self) -> None:
        with self._lock:
            self._lesson_shape = self._lesson_view(self._open)
            self._send("lesson", self._lesson_shape)

    def _publish_pointer(self) -> None:
        with self._lock:
            o = self._open
            self._pointer_shape = copy.deepcopy(o.pointer if o is not None else HIDDEN_POINTER)
            self._send("pointer", self._pointer_shape)

    def _cue(self, name: str, points: int = 0) -> None:
        with self._lock:
            self._send("cue", {"name": name, "points": points})

    # Work off the screens' thread.

    def _submit(self, pool: ThreadPoolExecutor, fn: Callable, *args: Any) -> None:
        with self._idle:
            if self._stopped:
                return
            self._pending += 1

        def job() -> None:
            try:
                fn(*args)
            except Exception:
                log.exception("backend job %s failed", getattr(fn, "__name__", fn))

        def finished(_: Future | None) -> None:  # it ran, or it was dropped as the program quit
            with self._idle:
                self._pending -= 1
                self._idle.notify_all()
        try:
            pool.submit(job).add_done_callback(finished)
        except RuntimeError:                     # shut down while this was being handed over
            finished(None)

    def _after(self, seconds: float, pool: ThreadPoolExecutor, fn: Callable, *args: Any) -> None:
        self._later(seconds, lambda: self._submit(pool, fn, *args))

    def wait_idle(self, timeout: float = 10.0) -> bool:
        """Waits until no work is queued or running (timers not yet due don't count). For tests and probes."""
        with self._idle:
            return self._idle.wait_for(lambda: self._pending == 0, timeout)

    def shutdown(self) -> None:
        """Saves and closes the lesson's app, then stops the workers. Call once, as the program quits.
        A question to the coach isn't waited for. A lesson being made is: it can't be stopped from here,
        and it records the made lesson in the learner's progress when it finishes. The screens are gone,
        so nothing more is sent to them."""
        with self._lock:
            self._key_hunt += 1
            o, self._open = self._open, None
            session = self._detach(o)
            self._listeners.clear()
        if session is not None:
            self._submit(self._work, self._close_app, session)
        with self._idle:
            self._stopped = True
        self._meta_pool.shutdown(wait=False, cancel_futures=True)
        for pool in (self._work, self._factory_pool):
            pool.shutdown(wait=True)

    # The home screen.

    def _card_states(self, lessons: list[Lesson]) -> dict[str, str]:
        """Done, current or locked. The first lesson not done is current; so is one the learner started or
        made. The rest wait their turn, so a new lesson on the shelf never locks one already under way."""
        made, last = set(self._progress.made), self._progress.last_lesson
        states, first = {}, True
        for lesson in lessons:
            state = self._progress.lesson_state(lesson.id)
            if state.done:
                states[lesson.id] = "done"
            elif lesson.id in made:
                states[lesson.id] = "current"
            elif first or state.step > 0 or lesson.id == last:
                states[lesson.id] = "current"
                first = False
            else:
                states[lesson.id] = "locked"
        return states

    def _locked(self, lesson: Lesson) -> bool:
        return self._card_states(self._library.lessons(lesson.course)).get(lesson.id, "locked") == "locked"

    def _continue_card(self) -> dict | None:
        last = self._progress.last_lesson
        if last is None:
            return None
        try:
            lesson = self._library.lesson(last)
        except KeyError:
            return None
        state = self._progress.lesson_state(last)
        if state.done:
            return None
        count = len(lesson.steps)
        return {"lessonId": lesson.id, "title": lesson.title, "step": min(state.step + 1, count), "of": count}

    def _home_view(self) -> dict:
        courses = []
        for info in self._library.courses():
            lessons = self._library.lessons(info.id)
            states = self._card_states(lessons)
            credits: list[str] = []
            for lesson in lessons:
                creator = lesson.source.creator.strip() if lesson.source is not None else ""
                if creator and creator not in credits:
                    credits.append(creator)
            done = sum(1 for s in states.values() if s == "done")
            courses.append({
                "id": info.id, "title": info.title, "app": info.app, "colour": info.colour,
                "progress": done / len(lessons) if lessons else 0.0, "credits": credits,
                "ready": bool(lessons),
                "lessons": [{"id": lesson.id, "title": lesson.title, "state": states[lesson.id],
                             "badge": self._library.badge(lesson)} for lesson in lessons],
            })
        name = self._progress.name or self._login
        return {
            "learner": {"name": name, "streak": self._progress.streak(),
                        "pointsToday": self._progress.points_today(), "dailyGoal": self._progress.daily_goal},
            "continueCard": self._continue_card(),
            "courses": courses,
            "tips": dict(self._tips),
            "factory": copy.deepcopy(self._factory),
            "meta": self._meta,
            "muted": self._muted,
        }

    # The lesson panel.

    def _step_view(self, o: _Open, index: int) -> dict:
        step = o.lesson.steps[index]
        shown = list(o.hints.get(index, []))
        return {"index": index, "instruction": step.instruction, "why": step.why, "hints": shown,
                "hintsLeft": max(0, len(step.hints) - len(shown)),
                "clip": clip_view(o.lesson, step, self._recordings), "note": save_note(o.snap)}

    def _lesson_view(self, o: _Open | None) -> dict:
        view = copy.deepcopy(CLOSED_LESSON)
        if o is None:
            return view
        lesson, count = o.lesson, len(o.lesson.steps)
        # Every step done but one came undone: the card shows the step to fix, the bar stays full.
        waiting = o.run is not None and o.run.index >= count and bool(o.run.changed) and o.complete is None
        picture = lesson.goal.picture
        picture_file = lesson.folder / picture if picture and lesson.folder is not None else None
        view.update({
            "open": True, "id": lesson.id, "title": lesson.title,
            "goal": {"sentence": lesson.goal.sentence,
                     "picture": str(picture_file) if picture_file is not None and picture_file.is_file() else None},
            "stepIndex": count if waiting else o.shown, "stepCount": count,
            "step": self._step_view(o, o.shown) if o.shown < count and o.complete is None else None,
            "banner": copy.deepcopy(o.banner), "points": o.points,
            "changed": sorted(o.run.changed) if o.run is not None else [],
            "complete": copy.deepcopy(o.complete), "ask": dict(o.ask), "appState": o.app_state,
            "badge": self._library.badge(lesson), "appName": o.plugin.title, "closedReason": o.closed_reason,
        })
        return view

    # Opening and closing a lesson.

    def open_lesson(self, lesson_id: str) -> None:
        with self._lock:
            o = self._open
            if o is not None and o.lesson.id == lesson_id:
                if o.app_state == "closed":
                    self.reopen_app()
                return
            try:
                lesson = self._library.lesson(lesson_id)
            except KeyError:
                log.warning("lesson %s is not on the shelf; not opened", lesson_id)
                return
            plugin = self._plugins.get(lesson.app)
            if plugin is None:
                log.warning("no plug-in for %s, which lesson %s needs", lesson.app, lesson_id)
                return
            if self._locked(lesson):
                log.warning("lesson %s is locked; not opened", lesson_id)
                return
            old = self._detach(self._open)
            self._gen += 1
            o = self._open = _Open(lesson=lesson, plugin=plugin, gen=self._gen,
                                   streak_before=self._progress.streak())
            resume = not self._progress.lesson_state(lesson_id).done
            self._publish_lesson()
            self._publish_pointer()
        if old is not None:
            self._submit(self._work, self._close_app, old)
        self._submit(self._work, self._start, o, o.gen, resume)

    def continue_lesson(self) -> None:
        with self._lock:
            card = self._continue_card()
        if card is not None:
            self.open_lesson(card["lessonId"])

    def reopen_app(self) -> None:
        with self._lock:
            o = self._open
            if o is None or o.app_state != "closed" or o.session is not None:
                return
            self._gen += 1
            o.gen = self._gen
            o.app_state, o.closed_reason, o.banner = "opening", "", None
            self._publish_lesson()
        self._submit(self._work, self._start, o, o.gen, True)

    def close_lesson(self) -> None:
        """Home at once; the app saves and closes on the app worker."""
        with self._lock:
            o, self._open = self._open, None
            session = self._detach(o)
            self._publish_lesson()
            self._publish_pointer()
            self._publish_home()
        if session is not None:
            self._submit(self._work, self._close_app, session)

    def go_home(self) -> None:
        self.close_lesson()

    def next_lesson(self) -> None:
        with self._lock:
            o = self._open
            if o is None:
                return
            lessons = self._library.lessons(o.lesson.course)
            states = self._card_states(lessons)
            ids = [lesson.id for lesson in lessons]
            after = ids[ids.index(o.lesson.id) + 1:] if o.lesson.id in ids else []
            following = next((i for i in after if states[i] != "locked"), None)
        if following is None:
            self.close_lesson()
        else:
            self.open_lesson(following)

    def _detach(self, o: _Open | None) -> AppSession | None:
        """Stops listening to `o`'s app and hands back its session to close. Call with the lock held."""
        if o is None:
            return None
        self._gen += 1
        o.gen = self._gen
        session, o.session = o.session, None
        return session

    def _current(self, o: _Open, gen: int) -> bool:
        return self._open is o and o.gen == gen

    def _from_app(self, o: _Open, gen: int, fn: Callable, *args: Any) -> None:
        """What an app's callback does: queue the news, and return at once."""
        self._submit(self._work, fn, o, gen, *args)

    def _start(self, o: _Open, gen: int, resume: bool) -> None:
        with self._lock:
            if not self._current(o, gen):
                return
            o.run = LessonRun(o.lesson, o.plugin.checks)
            o.logged, o.hints, o.resuming, o.cheering, o.goto, o.pointing = 0, {}, resume, None, None, None
            o.complete, o.snap = None, None
        self._progress.opened(o.lesson.id)
        try:
            session = o.plugin.open(o.lesson, self._workdir / o.lesson.id, visible=True, resume=resume,
                                    on_snapshot=lambda snap: self._from_app(o, gen, self._on_snapshot, snap),
                                    on_closed=lambda: self._from_app(o, gen, self._on_closed))
        except Exception:
            log.exception("%s could not open lesson %s", o.plugin.title, o.lesson.id)
            with self._lock:
                if self._current(o, gen):
                    o.app_state, o.closed_reason = "closed", f"{o.plugin.title} couldn't open"
                    self._publish_lesson()
            return
        with self._lock:
            stale = not self._current(o, gen)
            if not stale:
                o.session, o.app_state = session, "ready"
                self._publish_lesson()
                self._publish_home()
        if stale:                                # the lesson was closed while its app opened
            self._close_app(session)
            return
        self._place(session, then=lambda: self._from_app(o, gen, self._bring_forward, session))
        if not resume:                           # a resumed lesson points once its first snapshot says where
            self._follow(o, gen)

    def _place(self, session: AppSession, then: Callable[[], None] | None = None) -> None:
        """Puts the app's window beside the panel; `then()` runs once it is there, or could not be moved."""
        try:
            future = session.place(self._layout()[0])
        except Exception:
            log.exception("the app's window could not be placed")
            if then is not None:
                then()
            return

        def placed(f: Future) -> None:
            if f.exception() is not None:
                log.warning("the app's window could not be placed: %s", f.exception())
            if then is not None:
                then()
        future.add_done_callback(placed)

    def _bring_forward(self, o: _Open, gen: int, session: AppSession) -> None:
        """The app has just opened in its place: it comes to the front, so the learner sees it and types into
        it. Only as it opens, never when the screen changes: by then the learner may be in another window."""
        if self._still_open(o, gen):
            self._front(session.hwnd(), lambda: self._still_open(o, gen))

    def _still_open(self, o: _Open, gen: int) -> bool:
        with self._lock:
            return self._current(o, gen)

    def relayout(self) -> None:
        """The screen changed: put the app's window in its place again."""
        def again() -> None:
            with self._lock:
                session = self._open.session if self._open is not None else None
            if session is not None:
                self._place(session)
        self._submit(self._work, again)

    def _close_app(self, session: AppSession) -> None:
        try:
            session.close(save=True)
        except Exception:
            log.exception("the app did not close cleanly")

    def _on_closed(self, o: _Open, gen: int) -> None:
        with self._lock:
            if not self._current(o, gen):
                return
            session = self._detach(o)
            o.app_state = "closed"
            o.closed_reason = _capitalised(getattr(session, "close_reason", "") or "")
            o.cheering, o.pointing, o.landed = None, None, False
            o.pointer = copy.deepcopy(HIDDEN_POINTER)
            self._publish_lesson()
            self._publish_pointer()
        if session is not None:                  # let that app go (Excel quits), keeping any work left open
            self._close_app(session)

    # What the app says.

    def _on_snapshot(self, o: _Open, gen: int, snap: Any) -> None:
        with self._lock:
            if not self._current(o, gen) or o.run is None:
                return
            o.snap = snap
            if o.resuming:
                o.resuming = False
                o.run.resume(snap)
                if o.run.done:                   # the saved copy already passes every step
                    self._finish(o, None)
                else:
                    o.shown = o.run.index
                follow = True
            else:
                follow = self._apply(o, o.run.on_snapshot(snap))
            self._publish_lesson()
        if follow:
            self._follow(o, gen)

    def _apply(self, o: _Open, events: list) -> bool:
        """Turns the run's events into what the screens show; True when the pointer must follow a new
        target. Called with the lock held."""
        if not events:
            return False
        run, count = o.run, len(o.lesson.steps)
        if o.cheering is not None:               # news from the app ends the cheer at once
            o.cheering = None
            if o.banner is not None and o.banner["kind"] == "right":
                o.banner = None
        o.cheer += 1
        cues: list[str] = []
        earned = 0                               # the points the right steps here earned, sent with their cue
        passed: int | None = None
        done: LessonDone | None = None
        for event in events:
            if isinstance(event, StepPassed):
                points = self._progress.step_passed(o.lesson.id, event.index, event.points)
                o.points += points
                earned += points
                o.ask = {"state": "idle", "question": "", "answer": ""}
                o.asked += 1                     # the Ask box was about this step: an answer on its way is dropped
                o.banner = {"kind": "right", "text": "", "stepIndex": event.index}
                passed = event.index
                if "right" not in cues:
                    cues.append("right")
            elif isinstance(event, NotYet):
                o.banner = {"kind": "not_yet", "text": event.text, "stepIndex": event.index}
                o.verdict = (event.index, event.text)
                passed = None
                cues.append("not_yet")
            elif isinstance(event, LessonDone):
                done = event
        for record in run.records()[o.logged:]:
            self._progress.log_attempt(o.lesson.id, record)
        o.logged = len(run.records())
        if o.goto is not None and o.goto not in run.changed:
            o.goto = None
        if o.complete is not None:               # the lesson is done: a later change in the app moves nothing
            return False
        for cue in cues:
            self._cue(cue, earned if cue == "right" else 0)

        if done is not None:
            self._finish(o, done)
            return True
        if passed is not None:
            self._publish_home()
        if run.index >= count and run.changed:   # every step done, but an earlier one came undone
            first = min(run.changed)
            o.shown = first
            o.banner = {"kind": "changed", "text": _undone_text(sorted(run.changed), o.plugin.title),
                        "stepIndex": first}
            return self._pointing(o) != o.pointing
        if passed is not None and o.banner is not None and o.banner["kind"] == "right":
            o.shown = o.cheering = passed
            if o.pointer["visible"]:
                o.pointer.update(mascot="cheering", ring="right")
                self._publish_pointer()
            self._after(CHEER_SECONDS, self._work, self._end_cheer, o, o.gen, o.cheer)
            return False
        o.shown = min(run.index, count - 1)
        return self._pointing(o) != o.pointing

    def _end_cheer(self, o: _Open, gen: int, cheer: int) -> None:
        with self._lock:
            if not self._current(o, gen) or o.cheer != cheer or o.cheering is None:
                return
            o.cheering = None
            o.shown = min(o.run.index, len(o.lesson.steps) - 1)
            o.banner = None
            self._publish_lesson()
        self._follow(o, gen)

    def _finish(self, o: _Open, done: LessonDone | None) -> None:
        """The lesson is done. Called with the lock held."""
        self._progress.lesson_done(o.lesson.id, done)
        o.complete = {"points": o.points, "seconds": round(done.seconds, 1) if done else 0.0,
                      "firstTry": done.first_try if done else 0, "steps": done.steps if done else 0,
                      "streak": self._progress.streak(), "streakBefore": o.streak_before}
        o.shown, o.banner, o.cheering, o.goto = len(o.lesson.steps), None, None, None
        o.pointer = copy.deepcopy(HIDDEN_POINTER)
        self._publish_pointer()
        if done is not None:
            self._cue("complete")
        self._publish_home()
        self._refresh_tips()

    # The pointer.

    def _pointing(self, o: _Open) -> int | None:
        """The step whose target the mascot should point at."""
        run = o.run
        if run is None or o.complete is not None:
            return None
        if o.goto is not None and o.goto in run.changed:
            return o.goto
        if run.index < len(o.lesson.steps):
            return run.index
        changed = sorted(run.changed)
        return changed[0] if changed else None

    def _follow(self, o: _Open, gen: int) -> None:
        """Watches the target of the step to point at (none when the lesson is done)."""
        with self._lock:
            if not self._current(o, gen) or o.session is None:
                return
            session, index = o.session, self._pointing(o)
            o.pointing, o.landed = index, False
            o.watch += 1
            watch = o.watch
            if index is None and o.pointer["visible"]:
                o.pointer = copy.deepcopy(HIDDEN_POINTER)
                self._publish_pointer()
        target = o.lesson.steps[index].target if index is not None else None
        try:
            session.watch(target, lambda spot: self._from_app(o, gen, self._on_spot, watch, spot))
            session.set_waiting(index is not None)
        except Exception:
            log.exception("the app could not follow step %s's target", index)

    def _on_spot(self, o: _Open, gen: int, watch: int, spot: Spot | None) -> None:
        with self._lock:
            if not self._current(o, gen) or o.watch != watch:
                return
            if spot is None:
                o.landed = False
                o.pointer = copy.deepcopy(HIDDEN_POINTER)
            else:
                o.pointer.update(visible=True, **_box(spot.rect), bubble=spot.bubble, room=_box_or_none(spot.room),
                                 filled=_box_or_none(spot.filled))
                if not o.landed:
                    o.landed = True
                    self._fly(o)
            self._publish_pointer()

    def _fly(self, o: _Open) -> None:
        o.pointer.update(mascot="flying", ring="pulse")
        o.flight += 1
        self._cue("hop")
        self._after(FLIGHT_SECONDS, self._work, self._land, o, o.gen, o.flight)

    def _land(self, o: _Open, gen: int, flight: int) -> None:
        with self._lock:
            if not self._current(o, gen) or o.flight != flight or o.pointer["mascot"] != "flying":
                return
            o.pointer["mascot"] = "watching"
            self._publish_pointer()

    def show_me(self) -> None:
        self._submit(self._work, self._show_me)

    def _show_me(self) -> None:
        with self._lock:
            o = self._open
            if o is None or o.session is None or o.complete is not None:
                return
            if o.pointer["visible"] and o.cheering is None:
                self._fly(o)
                self._publish_pointer()
                return
            gen = o.gen
        self._follow(o, gen)

    def go_to_step(self, index: int) -> None:
        """Points at a done step that came undone, so the learner can fix it."""
        self._submit(self._work, self._go_to_step, index)

    def _go_to_step(self, index: int) -> None:
        with self._lock:
            o = self._open
            if o is None or o.run is None or index not in o.run.changed:
                return
            o.goto, gen = index, o.gen
        self._follow(o, gen)

    # Help on the step.

    def next_hint(self) -> None:
        self._submit(self._work, self._next_hint)

    def _next_hint(self) -> None:
        with self._lock:
            o = self._open
            if o is None or o.run is None or o.cheering is not None:
                return
            index = self._helped(o)
            if index != o.run.index:
                # Every step done, but the one shown came undone: its own hints, after those seen before.
                seen, hints = o.hints.get(index, []), o.lesson.steps[index].hints
                hint = hints[len(seen)] if len(seen) < len(hints) else None
            else:
                hint = o.run.hint()
            if hint is None:
                return
            o.hints.setdefault(index, []).append(hint)
            self._publish_lesson()

    @staticmethod
    def _helped(o: _Open) -> int:
        """The step a hint or a question is about: the one the run is on, or, with every step done, the one
        shown that came undone. Called with the lock held."""
        if o.run.index >= len(o.lesson.steps) and o.shown in o.run.changed:
            return o.shown
        return o.run.index

    def watch_clip(self) -> None:
        """The learner opened the clip: look again for the video, which may have been saved since."""
        self._submit(self._work, self._publish_lesson)

    def ask(self, text: str) -> None:
        with self._lock:
            o = self._open
            if o is None or o.run is None or o.complete is not None:
                return
            o.asked += 1
            asked = o.asked
            if self._coach is None:
                o.ask = {"state": "error", "question": text, "answer": NO_COACH}
            else:
                o.ask = {"state": "thinking", "question": text, "answer": ""}
            self._publish_lesson()
        if self._coach is not None:            # read the step on the app worker, after any hint queued
            self._submit(self._work, self._ask_coach, o, asked, text)

    def _ask_coach(self, o: _Open, asked: int, text: str) -> None:
        with self._lock:
            if self._open is not o or o.asked != asked:
                return
            index = min(self._helped(o), len(o.lesson.steps) - 1)
            step = o.lesson.steps[index]
            verdict = o.verdict[1] if o.verdict is not None and o.verdict[0] == index else ""  # never another step's
            context = {"instruction": step.instruction, "why": step.why, "hints": list(step.hints),
                       "hints_shown": len(o.hints.get(index, [])), "verdict": verdict,
                       "state": coach_state(o.snap, step)}
        self._submit(self._meta_pool, self._answer, o, asked, text, context)

    def _answer(self, o: _Open, asked: int, text: str, context: dict) -> None:
        try:
            answer, state, meta = self._coach.answer(text, context), "answered", "ok"
        except CoachUnavailable as e:
            answer, state, meta = str(e), "error", self._meta_after(e)
        except Exception:
            log.exception("the coach failed to answer")
            answer, state, meta = COACH_BROKE, "error", None
        with self._lock:
            if meta is not None and meta != self._meta:
                self._meta = meta
                self._publish_home()
            if self._open is not o or o.asked != asked:
                return                           # another question, or another lesson, since
            o.ask = {"state": state, "question": text, "answer": answer}
            self._publish_lesson()

    @staticmethod
    def _meta_after(e: CoachUnavailable) -> str:
        return "no_key" if isinstance(e.__cause__, NoKey) else "unreachable"

    def _refresh_tips(self) -> None:
        if self._coach is None:
            return
        with self._lock:
            self._tips = {"state": "loading", "text": ""}
            self._publish_home()
        self._submit(self._meta_pool, self._write_tips)

    def _write_tips(self) -> None:
        meta = None
        try:
            text = self._coach.tips(self._progress.attempts())
            meta = "ok"
            if text:
                self._progress.keep_tips(text)
            else:                                # nothing new to say: the last tips stay
                text = self._progress.tips
            tips = {"state": "ready", "text": text} if text else {"state": "none", "text": ""}
        except CoachUnavailable as e:
            tips, meta = {"state": "error", "text": str(e)}, self._meta_after(e)
        except Exception:
            log.exception("the coach failed to write tips")
            tips = {"state": "error", "text": TIPS_BROKE}
        with self._lock:
            self._tips = tips
            if meta is not None:
                self._meta = meta
            self._publish_home()

    # The Meta key.

    def key_setup_copied(self) -> None:
        """The learner copied the line that saves a Meta key: look for the key every few seconds."""
        with self._lock:
            self._key_hunt += 1
            hunt = self._key_hunt
        self._after(KEY_CHECK_SECONDS, self._meta_pool, self._look_for_key, hunt, 1)

    def _look_for_key(self, hunt: int, tries: int) -> None:
        with self._lock:
            if hunt != self._key_hunt:
                return
        try:
            found = bool(self._find_key()[0])
        except Exception:
            log.exception("could not look for the Meta key")
            found = False
        if found:
            with self._lock:
                self._meta = "ok"
                self._publish_home()
        elif tries < KEY_CHECKS:
            self._after(KEY_CHECK_SECONDS, self._meta_pool, self._look_for_key, hunt, tries + 1)

    # Making a lesson from a video.

    def make_lesson(self, url: str) -> None:
        with self._lock:
            if self._factory["state"] == "running":
                return
            if self._maker is None or self._maker_app not in self._plugins:
                self._factory = {"state": "not_ready", "url": url, "stages": [], "reason": NO_MAKER,
                                 "lessonId": None}
                self._publish_home()
                return
            self._factory = {"state": "running", "url": url, "reason": "", "lessonId": None,
                             "stages": [{"name": n, "state": "waiting", "detail": ""} for n in STAGES]}
            self._publish_home()
        self._submit(self._factory_pool, self._make, url)

    def _make(self, url: str) -> None:
        def on_stage(name: str, state: str, detail: str) -> None:
            if name not in STAGES or state not in _STAGE_STATES:
                return
            with self._lock:
                for stage in self._factory["stages"]:
                    if stage["name"] == name:
                        stage.update(state=state, detail=detail or "")
                self._publish_home()
        try:
            result = self._maker.make(url, self._plugins[self._maker_app], on_stage)
        except Exception:
            log.exception("making a lesson from %s failed", url)
            result = None
        lesson_id, reason = None, MAKER_BROKE
        if result is not None and result.lesson is not None:
            self._library.reload()
            try:
                lesson_id = self._library.lesson(result.lesson.id).id
                self._progress.lesson_made(lesson_id)
            except KeyError:
                reason = NOT_ON_SHELF
        elif result is not None:
            reason = result.reason or MAKER_BROKE
        with self._lock:
            if lesson_id is not None:
                self._factory.update(state="ready", lessonId=lesson_id, reason="")
            else:
                self._factory.update(state="not_ready", reason=reason)
            self._publish_home()

    def dismiss_factory(self) -> None:
        """The learner is done with the lesson maker's result: back to the empty link box."""
        with self._lock:
            if self._factory["state"] == "running":
                return
            self._factory = copy.deepcopy(EMPTY_HOME["factory"])
            self._publish_home()

    def set_muted(self, on: bool) -> None:
        with self._lock:
            self._muted = bool(on)
            self._publish_home()
