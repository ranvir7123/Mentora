"""The lesson factory: a tutorial link goes in, a proven (and, when it can be, tested) lesson comes out.

Six stages run in order and the screen is told about each as it goes, with `on_stage(name, state, detail)`:
download the video, read it (a small copy, still frames, a transcript), write the lesson with Muse Spark,
prove it in the real app, test it with Meta's agent playing the learner, and publish it to the shelf. A stage
that fails stops the factory with its reason in plain words, and nothing is written to `lessons/`. `on_line`
gets the same story as a log, one line at a time, for the command line and for Ranvir.

The test falls back as the design says: when the mouse test fails, a keyboard-only test runs; when that
fails too, the lesson goes on the shelf on its proof alone, with the "proven" badge. A test that cannot
finish (a person moved the mouse, the app stopped answering, Meta's spending limit) does the same, and says
how to test the lesson later.
"""
from __future__ import annotations

import re
import shutil
import time
import traceback
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from app.core.lesson import Lesson, TestResult, save_lesson, shelf_badge
from app.core.plugin import AppPlugin
from app.core.services import MakeResult
from app.factory import tester, video
from app.factory.input import UserTookOver
from app.factory.prove import MIN_STEPS, ProveError, prove
from app.factory.video import Fetched, Prepared, VideoError, frame_at
from app.factory.writer import NotReady, unique_id, write_lesson
from app.meta.client import MetaClient, MetaError

STAGES = ("download", "read", "write", "prove", "test", "publish")
HANDS_OFF_S = 5
TESTS = {"mouse": "Mouse test", "keyboard": "Keyboard-only test"}

Say = Callable[[str], None]


class _Stopped(Exception):
    """A stage failed; `reason` is already plain words and the screen has been told."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# The test, with its fallback. The command line's `test` uses it too.

@dataclass(frozen=True)
class Tested:
    result: TestResult           # mode "skipped" when neither test passed
    detail: str                  # what happened, in plain words


def run_test(lesson: Lesson, plugin: AppPlugin, workdir: Path, client: MetaClient, *, say: Say, runs: int = 5,
             hands=None, play=None) -> Tested:
    """The mouse test, then the keyboard-only test if that fails. `say` hears each run and each switch.
    A test that cannot finish raises, as `test_lesson` does: UserTookOver, ProveError or a MetaError."""
    play = play or tester.test_lesson
    results = {}
    for mode in ("mouse", "keyboard"):
        where = Path(workdir) / mode
        where.mkdir(parents=True, exist_ok=True)
        name = TESTS[mode]
        got = play(lesson, plugin, where, client, runs=runs, mode=mode, hands=hands,
                   on_line=lambda line, name=name: say(f"{name}: {line}"))
        results[mode] = got
        if got.passed:
            keys = ", using the keyboard only" if mode == "keyboard" else ""
            return Tested(got, f"{got.passes} of {got.runs} test runs passed{keys}")
        if mode == "mouse":
            say(f"The mouse test passed {got.passes} of {got.runs} runs, so the keyboard-only test runs now")
    kb = results["keyboard"]
    return Tested(replace(kb, mode="skipped"),
                  f"The keyboard-only test passed {kb.passes} of {kb.runs} runs too, so the lesson goes on the "
                  "shelf with the proven badge, not proven and tested")


def not_tested() -> TestResult:
    return TestResult(passed=False, at=datetime.now(timezone.utc).isoformat(timespec="seconds"), mode="skipped",
                      runs=0, passes=0)


# The factory.

class LessonFactory:
    """Makes lessons from tutorial links: the lesson maker the app asks for (app/core/services.py)."""

    def __init__(self, client: MetaClient, lessons_dir: Path = Path("lessons"), recordings: Path = Path("recordings"),
                 *, fetch=None, tester=None, hands=None, test: bool = True, runs: int = 5,
                 hands_off_s: float = HANDS_OFF_S, on_line: Say | None = None):
        self.client, self.lessons_dir, self.recordings = client, Path(lessons_dir), Path(recordings)
        self.fetch, self.tester, self.hands = fetch or video.fetch, tester, hands
        self.test, self.runs, self.hands_off_s = test, runs, hands_off_s
        self.on_line = on_line or (lambda line: None)
        self._on_stage: Callable[[str, str, str], None] = lambda name, state, detail: None

    def make(self, url: str, plugin: AppPlugin, on_stage: Callable[[str, str, str], None]) -> MakeResult:
        self._on_stage = on_stage
        for name in STAGES:
            on_stage(name, "waiting", "")
        try:
            return MakeResult(self._make(url, plugin), "")
        except _Stopped as stop:
            return MakeResult(None, stop.reason)

    def _make(self, url: str, plugin: AppPlugin) -> Lesson:
        with self._stage("download"):
            fetched = self._download(url)
            info = fetched.info
            self._done("download", f'"{info.title}" by {info.creator}, {_length(info.length_s)} long')
        work = fetched.video.parent

        with self._stage("read"):
            prepared = video.prepare(fetched, self.client)
            lines = len(prepared.transcript)
            heard = f"{_count(lines, 'line')} of transcript" if lines else "no transcript (no captions or speech)"
            self._done("read", f"{_count(len(prepared.frames), 'still frame')}, {heard}")

        with self._stage("write"):
            written = write_lesson(prepared, info, plugin, self.client, lessons_dir=self.lessons_dir)
            if isinstance(written, NotReady):
                self._fail("write", written.reason)
            self._done("write", f"{_count(len(written.steps), 'step')} written")

        with self._stage("prove"):
            proven = self._prove(written, prepared, fetched, plugin, work / "prove")

        with self._stage("test"):
            lesson = replace(proven, test=self._test(proven, plugin, work / "test"))

        with self._stage("publish"):
            return self._publish(lesson, fetched, prepared)

    # The stages.

    def _download(self, url: str) -> Fetched:
        self.recordings.mkdir(parents=True, exist_ok=True)
        incoming = self.recordings / f"incoming-{uuid.uuid4().hex[:12]}"
        incoming.mkdir()
        try:
            fetched = self.fetch(url, incoming)
            return video.settle(fetched, self.recordings / _folder_name(fetched.info.id))
        finally:
            shutil.rmtree(incoming, ignore_errors=True)       # a half download; gone already when settled

    def _prove(self, lesson: Lesson, prepared: Prepared, fetched: Fetched, plugin: AppPlugin, workdir: Path) -> Lesson:
        fixes = 0

        def fix(current: Lesson, reason: str) -> Lesson | NotReady:
            nonlocal fixes
            fixes += 1
            self._update("prove", f"{reason[:1].upper()}{reason[1:]}; it goes back to Muse Spark")
            return write_lesson(prepared, fetched.info, plugin, self.client, feedback=reason,
                                lessons_dir=self.lessons_dir, label=f"writer_{fetched.info.id}_fix{fixes}")

        workdir.mkdir(parents=True, exist_ok=True)
        proved = prove(lesson, plugin, workdir, fix=fix)
        for note in proved.notes:
            self.on_line(f"prove: {note}")
        kept, dropped = len(proved.lesson.steps), proved.dropped
        total = kept + len(dropped)
        why = {d: proved.why.get(d, "it could not be proven").rstrip(".") for d in dropped}
        if not proved.lesson.proof.passed:
            if not dropped:
                said = f"The lesson has only {_count(kept, 'step')}, and a lesson needs at least {MIN_STEPS}."
            else:
                said = (f"{'None' if kept == 0 else f'Only {kept}'} of {total} steps could be proven, "
                        f"and a lesson needs at least {MIN_STEPS}.")
            self._fail("prove", " ".join([said] + [f"Step {d} was dropped: {why[d]}." for d in dropped]))
        detail = f"{kept} of {total} steps proven"
        if dropped:
            detail += f", {len(dropped)} dropped ({'; '.join(f'{d}: {why[d]}' for d in dropped)})"
        self._done("prove", detail)
        return proved.lesson

    def _test(self, lesson: Lesson, plugin: AppPlugin, workdir: Path) -> TestResult:
        if not self.test:
            self._done("test", "Not tested: the test was switched off, so the lesson goes on the shelf with the "
                               "proven badge")
            return not_tested()
        if self.hands_off_s > 0:
            self._update("test", f"Hands off the mouse and keyboard: Meta's agent takes over in {self.hands_off_s:g} s")
            time.sleep(self.hands_off_s)
        try:
            tested = run_test(lesson, plugin, workdir, self.client, say=lambda line: self._update("test", line),
                              runs=self.runs, hands=self.hands, play=self.tester)
        except UserTookOver as exc:
            said = str(exc)
        except (ProveError, MetaError, OSError) as exc:
            said = f"The test could not run: {str(exc).rstrip('.')}."
        else:
            self._done("test", tested.detail)
            return tested.result
        later = (self.lessons_dir / lesson.id).as_posix()
        self._done("test", f"{said} The lesson goes on the shelf with the proven badge; test it later with: "
                           f"python -m app.factory test {later}")
        return not_tested()

    def _publish(self, lesson: Lesson, fetched: Fetched, prepared: Prepared) -> Lesson:
        self.lessons_dir.mkdir(parents=True, exist_ok=True)
        lesson_id = lesson.id
        while True:                                  # another lesson may have taken the name meanwhile
            folder = self.lessons_dir / lesson_id
            try:
                folder.mkdir()
                break
            except FileExistsError:
                lesson_id = unique_id(lesson.title, self.lessons_dir)
        try:
            picture = self._goal_picture(lesson, fetched, prepared, folder / "goal.png")
            lesson = replace(lesson, id=lesson_id, folder=folder, goal=replace(lesson.goal, picture=picture))
            save_lesson(lesson)
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        self.on_line(f"The lesson is saved in {folder}")
        self._done("publish", f'On the shelf as "{lesson.title}", with the {shelf_badge(lesson)} badge')
        return lesson

    def _goal_picture(self, lesson: Lesson, fetched: Fetched, prepared: Prepared, goal: Path) -> str | None:
        """The video where the last step ends; else the last still frame; else no picture."""
        clip = lesson.steps[-1].clip
        if clip is not None:
            try:
                return frame_at(fetched.video, min(clip.end, fetched.info.length_s - 0.5), goal).name
            except VideoError as exc:
                self.on_line(f"publish: {exc}, so the goal picture is the last still frame")
        if not prepared.frames:
            return None
        shutil.copyfile(prepared.frames[-1][1], goal)
        return goal.name

    # Telling the screen and the log.

    @contextmanager
    def _stage(self, name: str) -> Iterator[None]:
        self._tell(name, "running", "")
        try:
            yield
        except _Stopped:
            raise
        except (VideoError, ProveError, MetaError) as exc:      # these already say what happened plainly
            self._fail(name, str(exc))
        except Exception as exc:
            self.on_line(traceback.format_exc().rstrip())
            self._fail(name, f"Something went wrong in the {name} stage: {exc}")

    def _update(self, name: str, detail: str) -> None:
        self._tell(name, "running", detail)

    def _done(self, name: str, detail: str) -> None:
        self._tell(name, "done", detail)

    def _fail(self, name: str, reason: str) -> None:
        self._tell(name, "failed", reason)
        raise _Stopped(reason)

    def _tell(self, name: str, state: str, detail: str) -> None:
        self._on_stage(name, state, detail)
        if state == "running":
            self.on_line(f"{name}: {detail}" if detail else f"{name} started")
        else:
            self.on_line(f"{name} {state}: {detail}")


def _folder_name(video_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", video_id) or "video"


def _length(seconds: int) -> str:
    h, rest = divmod(int(seconds), 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _count(n: int, thing: str) -> str:
    return f"{n} {thing}{'' if n == 1 else 's'}"
