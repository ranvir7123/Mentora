"""The program's backend, driven with the fake app, a fake coach and a fake lesson maker: what the screens are
told when the learner works in the app, and what each button does."""
import threading
import time
from concurrent.futures import Future
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.coach.coach import CoachUnavailable
from app.core.fake_plugin import FakePlugin, FakeSession
from app.core.library import Library
from app.core.lesson import load_lesson
from app.core.progress import Progress
from app.core.services import MakeResult
from app.core.types import Call, Rect, Spot, Target
from app.excel.snapshot import Cell, Sheet, Snapshot
from app.integration.backend import SAVE_NOTE, Backend, coach_state, save_note
from app.meta.client import NoKey
from tests.integration.helpers import fake_step, lesson_dict, write_courses, write_lesson

APP_RECT, PANEL_RECT = Rect(0, 0, 1840, 1500), Rect(1840, 0, 720, 1500)
TODAY = date(2026, 10, 30)
VIDEO = "https://www.youtube.com/watch?v=k7RM-ot2NWY"


class RecordingPlugin(FakePlugin):
    """The fake app, keeping every session it opens. `close_reason` is what the session says when the
    learner closes it; `open_error` makes the next open fail."""
    def __init__(self):
        super().__init__()
        self.sessions: list[FakeSession] = []
        self.opens: list[dict] = []
        self.open_error: Exception | None = None
        self.close_gate: threading.Event | None = None
        self.held_places: list[Future] | None = None    # a list: each move waits there until the test ends it

    def open(self, lesson, workdir, *, visible=True, resume=False, on_snapshot, on_closed):
        self.opens.append({"lesson": lesson.id, "workdir": workdir, "resume": resume, "visible": visible})
        if self.open_error is not None:
            error, self.open_error = self.open_error, None
            raise error
        session = super().open(lesson, workdir, visible=visible, resume=resume, on_snapshot=on_snapshot,
                               on_closed=on_closed)
        session.close_reason = ""
        gate, plain_close = self.close_gate, session.close
        calls = session.close_calls = []

        def close(save=False):
            calls.append(save)
            if gate is not None:
                gate.wait(5)
            plain_close(save)
        session.close = close
        number = 1000 + len(self.sessions)                 # each app's own window
        session.hwnd = lambda: number
        held, plain_place = self.held_places, session.place

        def place(rect):
            if held is None:
                return plain_place(rect)
            moving = Future()
            moving.add_done_callback(lambda _: plain_place(rect))
            held.append(moving)
            return moving
        session.place = place
        self.sessions.append(session)
        return session

    @property
    def session(self) -> FakeSession:
        return self.sessions[-1]


class FakeCoach:
    def __init__(self):
        self.answer_text = "Look at the key's name."
        self.failure: Exception | None = None
        self.asked: list[tuple[str, dict]] = []
        self.tips_asked: list[list] = []
        self.gate: threading.Event | None = None     # holds answers back until the test lets them go

    def tips(self, log):
        self.tips_asked.append(list(log))
        if self.failure is not None:
            raise self.failure
        return f"You finished {len(log)} steps. Try the next lesson." if log else ""

    def answer(self, question, context):
        self.asked.append((question, dict(context)))
        if self.gate is not None:
            self.gate.wait(5)
        if self.failure is not None:
            raise self.failure
        return self.answer_text


class FakeMaker:
    """Makes a lesson folder in the library, reporting each stage, or says why it couldn't."""
    def __init__(self, root: Path):
        self.root = root
        self.reason = ""
        self.gate: threading.Event | None = None
        self.made: list[tuple[str, str]] = []

    def make(self, url, plugin, on_stage):
        self.made.append((url, plugin.app_id))
        on_stage("download", "running", "Getting the video")
        if self.gate is not None:
            self.gate.wait(5)
        on_stage("download", "done", "Got 6:12 of video")
        if self.reason:
            on_stage("read", "failed", "No steps found")
            return MakeResult(None, self.reason)
        for name in ("read", "write", "prove", "test", "publish"):
            on_stage(name, "done", "")
        folder = write_lesson(self.root, "made-sum", title="Add up with SUM",
                              source={"url": url, "title": "SUM in 5 minutes", "creator": "Sheet School",
                                      "channel_url": "", "licence": "Creative Commons", "length_s": 372})
        return MakeResult(load_lesson(folder), "")


class Later:
    """Stands in for the timer: runs what was put off when the test says so."""
    def __init__(self):
        self.waiting: list[tuple[float, object]] = []

    def __call__(self, seconds, fn):
        self.waiting.append((seconds, fn))

    def run(self):
        waiting, self.waiting = self.waiting, []
        for _, fn in waiting:
            fn()


class World:
    def __init__(self, tmp_path, *, lessons=None, coach=True, maker=True, key="k"):
        self.tmp = tmp_path
        self.lessons_dir = tmp_path / "lessons"
        write_courses(self.lessons_dir)
        for lesson_id, given in (lessons or {"two-keys": {"title": "Two keys"}}).items():
            write_lesson(self.lessons_dir, lesson_id, **given)
        self.plugin = RecordingPlugin()
        self.coach = FakeCoach() if coach else None
        self.maker = FakeMaker(self.lessons_dir) if maker else None
        self.key = key
        self.later = Later()
        self.sent: list[tuple[str, dict]] = []
        self.fronts: list[int] = []                         # the windows brought to the front, in order
        self.stills: list = []                              # with each, whether its lesson is still open
        self.start()

    def start(self):
        self.library = Library(self.lessons_dir)
        self.progress = Progress(self.tmp / "mentora", today=lambda: TODAY)
        self.backend = Backend(self.library, self.progress, {"fake": self.plugin}, self.coach, self.maker,
                               workdir=self.tmp / "mentora" / "work", layout=lambda: (APP_RECT, PANEL_RECT),
                               later=self.later, find_key=lambda: (self.key, "test"),
                               recordings=self.tmp / "recordings", maker_app="fake", login_name="ranvir",
                               front=self._front)
        self.backend.subscribe(lambda name, payload: self.sent.append((name, payload)))
        return self.backend

    def _front(self, hwnd, still):
        self.fronts.append(hwnd)
        self.stills.append(still)

    def idle(self):
        assert self.backend.wait_idle(5), "the backend's work never finished"

    def run_later(self):
        self.later.run()
        self.idle()

    def cues(self):
        return [p["name"] for n, p in self.sent if n == "cue"]

    def last(self, name):
        return [p for n, p in self.sent if n == name][-1]

    def open(self, lesson_id="two-keys"):
        self.backend.open_lesson(lesson_id)
        self.idle()
        return self.plugin.session

    def learner_sets(self, key, value):
        self.plugin.session.learner_sets(key, value)
        self.idle()


@pytest.fixture
def world(tmp_path):
    w = World(tmp_path)
    yield w
    w.backend.shutdown()


def test_a_lesson_opens_on_its_first_step_with_the_app_placed_beside_the_panel(world):
    session = world.open()
    lesson = world.backend.lesson()
    assert (lesson["open"], lesson["id"], lesson["title"], lesson["appState"]) == (True, "two-keys", "Two keys", "ready")
    assert (lesson["stepIndex"], lesson["stepCount"]) == (0, 2)
    assert lesson["step"]["instruction"] == "Set k0 to 1."
    assert lesson["badge"] == "proven and tested" and lesson["appName"] == "Fake app"
    assert session.placed == APP_RECT
    assert world.plugin.opens[0]["workdir"] == world.tmp / "mentora" / "work" / "two-keys"
    assert session.watching.ref == "k0" and session.waiting
    pointer = world.backend.pointer()
    assert pointer["visible"] and (pointer["x"], pointer["y"], pointer["w"], pointer["h"]) == (100, 100, 80, 24)
    assert pointer["mascot"] == "flying" and "hop" in world.cues()
    world.run_later()
    assert world.backend.pointer()["mascot"] == "watching"


def test_a_right_step_updates_banner_points_cue_and_pointer(world):
    session = world.open()
    session.spots["k1"] = Spot(Rect(300, 400, 80, 24), bubble="Type it here")
    world.run_later()
    world.learner_sets("k0", 1)

    lesson = world.backend.lesson()
    assert lesson["banner"] == {"kind": "right", "text": "", "stepIndex": 0}
    assert lesson["points"] == 10 and lesson["stepIndex"] == 0      # the cheer stays on the step just done
    assert world.last("cue") == {"name": "right", "points": 10}       # the points the step earned float up
    assert world.progress.points_today() == 10
    pointer = world.backend.pointer()
    assert (pointer["mascot"], pointer["ring"]) == ("cheering", "right")

    world.run_later()                                                 # then on to the next step
    lesson = world.backend.lesson()
    assert (lesson["stepIndex"], lesson["banner"]) == (1, None)
    assert lesson["step"]["instruction"] == "Set k1 to 2."
    assert session.watching.ref == "k1"
    pointer = world.backend.pointer()
    assert (pointer["x"], pointer["y"], pointer["bubble"], pointer["mascot"]) == (300, 400, "Type it here", "flying")
    assert world.backend.home()["learner"]["pointsToday"] == 10


def test_a_step_passed_again_cues_no_points(world):
    world.progress.step_passed("two-keys", 0, 10)       # passed before, but the work copy lost it
    world.open()
    world.learner_sets("k0", 1)
    assert world.last("cue") == {"name": "right", "points": 0}        # so no "+10" floats up
    assert world.backend.lesson()["points"] == 0 and world.progress.points_today() == 10


def test_not_yet_shows_the_line_and_takes_nothing_away(world):
    world.open()
    world.learner_sets("k0", 1)
    world.run_later()
    world.learner_sets("k1", 7)

    lesson = world.backend.lesson()
    assert lesson["banner"] == {"kind": "not_yet", "text": "Not yet: k1 says 7. It should say 2.", "stepIndex": 1}
    assert lesson["points"] == 10 and world.progress.points_today() == 10
    assert world.cues().count("not_yet") == 1

    # The same mistake again, after clearing the key: the screen's state is the same, so only the sound
    # can bring Not yet back after Try again.
    world.plugin.session.perform(Call("delete", {"key": "k1"}))
    world.idle()
    world.learner_sets("k1", 7)
    assert world.cues().count("not_yet") == 2
    assert world.backend.lesson()["banner"]["kind"] == "not_yet"
    assert world.progress.points_today() == 10


def test_app_closed_shows_reopen_and_reopen_resumes(world):
    session = world.open()
    world.learner_sets("k0", 1)
    world.run_later()
    session.close(save=True)                     # the learner saves and closes the app
    session.close_reason = ""
    session.closed_by_learner()
    world.idle()

    lesson = world.backend.lesson()
    assert (lesson["open"], lesson["appState"], lesson["closedReason"]) == (True, "closed", "")
    assert not world.backend.pointer()["visible"]

    cues = len(world.cues())
    world.backend.reopen_app()
    world.idle()
    assert len(world.plugin.sessions) == 2 and world.plugin.opens[-1]["resume"]
    lesson = world.backend.lesson()
    assert (lesson["appState"], lesson["stepIndex"], lesson["banner"]) == ("ready", 1, None)
    assert "right" not in world.cues()[cues:]
    assert world.plugin.session.placed == APP_RECT


def test_the_reason_an_app_closed_is_shown(world):
    session = world.open()
    session.close_reason = "lost touch with VS Code"
    session.closed_by_learner()
    world.idle()
    assert world.backend.lesson()["closedReason"] == "Lost touch with VS Code"


def test_resuming_ticks_done_steps_quietly(world):
    world.open()
    world.learner_sets("k0", 1)
    world.run_later()
    world.backend.close_lesson()
    world.idle()
    assert world.plugin.sessions[0].closed

    world.backend.shutdown()                     # the program closes; tomorrow it starts again
    world.sent.clear()
    world.start()
    home = world.backend.home()
    assert home["continueCard"] == {"lessonId": "two-keys", "title": "Two keys", "step": 2, "of": 2}
    world.backend.continue_lesson()
    world.idle()

    lesson = world.backend.lesson()
    assert world.plugin.opens[-1]["resume"]
    assert (lesson["stepIndex"], lesson["banner"], lesson["points"]) == (1, None, 0)
    assert "right" not in world.cues() and "not_yet" not in world.cues()
    assert world.progress.points_today() == 10                        # never counted twice


def test_opening_twice_opens_one_app(world):
    world.backend.open_lesson("two-keys")
    world.backend.open_lesson("two-keys")
    world.backend.continue_lesson()
    world.idle()
    world.backend.open_lesson("two-keys")
    world.idle()
    assert len(world.plugin.opens) == 1


def test_opening_another_lesson_saves_and_closes_the_first(tmp_path):
    w = World(tmp_path, lessons={"a": {"title": "A first"}, "b": {"title": "B second", "course": "code"}})
    try:
        w.open("a")
        first = w.plugin.session
        w.learner_sets("k0", 1)
        w.backend.open_lesson("b")
        w.idle()
        assert first.closed and (w.tmp / "mentora" / "work" / "a" / "state.json").exists()
        assert [o["lesson"] for o in w.plugin.opens] == ["a", "b"]
        assert w.backend.lesson()["id"] == "b"
    finally:
        w.backend.shutdown()


def test_closing_a_lesson_goes_home_at_once_and_closes_the_app_off_the_screens_thread(world):
    world.plugin.close_gate = threading.Event()       # this app takes its time to close, like a busy Excel
    session = world.open()
    world.backend.close_lesson()                      # returns at once
    assert not world.backend.lesson()["open"]
    assert not world.backend.pointer()["visible"]
    assert not session.closed
    world.plugin.close_gate.set()
    world.idle()
    assert session.closed


def test_a_closed_lessons_late_news_is_ignored(world):
    session = world.open()
    world.backend.close_lesson()
    world.idle()
    session.learner_sets("k0", 1)                     # a last snapshot from the app as it closes
    world.idle()
    assert not world.backend.lesson()["open"]
    assert world.progress.points_today() == 0


def test_an_app_that_cannot_open_says_so_and_can_be_tried_again(world):
    world.plugin.open_error = ValueError("the work folder holds files the program did not make")
    world.backend.open_lesson("two-keys")
    world.idle()
    lesson = world.backend.lesson()
    assert (lesson["open"], lesson["appState"]) == (True, "closed")
    assert lesson["closedReason"] == "Fake app couldn't open"
    world.backend.reopen_app()
    world.idle()
    assert world.backend.lesson()["appState"] == "ready"


def test_a_lesson_not_on_the_shelf_never_opens(world):
    write_lesson(world.lessons_dir, "draft", proof=None, test=None)
    world.library.reload()
    world.backend.open_lesson("draft")
    world.idle()
    assert world.plugin.opens == [] and not world.backend.lesson()["open"]


def test_hints_come_one_at_a_time(world):
    world.open()
    world.backend.next_hint()
    world.idle()
    step = world.backend.lesson()["step"]
    assert (step["hints"], step["hintsLeft"]) == (["Find k0."], 2)
    world.backend.next_hint()
    world.backend.next_hint()
    world.backend.next_hint()
    world.idle()
    assert world.backend.lesson()["step"]["hintsLeft"] == 0


def test_show_me_flies_the_mascot_to_the_target_again(world):
    world.open()
    world.run_later()
    before = world.cues().count("hop")
    world.backend.show_me()
    world.idle()
    assert world.backend.pointer()["mascot"] == "flying" and world.cues().count("hop") == before + 1
    world.run_later()
    assert world.backend.pointer()["mascot"] == "watching"


def test_the_pointer_carries_the_room_the_app_gives_its_mascot_and_the_cells_to_keep_off(world):
    session = world.open()
    world.run_later()
    pointer = world.backend.pointer()
    assert pointer["visible"] and pointer["room"] is None              # no room given: anywhere on the screen
    assert pointer["filled"] is None
    session.spots["k1"] = Spot(Rect(300, 400, 80, 24), room=Rect(55.4, 470, 1785, 930.2),
                               filled=Rect(55.4, 470, 544.6, 320))
    world.learner_sets("k0", 1)
    world.run_later()
    assert world.backend.pointer()["room"] == {"x": 55, "y": 470, "w": 1785, "h": 930}
    assert world.backend.pointer()["filled"] == {"x": 55, "y": 470, "w": 545, "h": 320}


def test_a_target_the_app_cannot_find_hides_the_pointer(world):
    session = world.open()
    world.run_later()
    session.spots["k1"] = None
    world.learner_sets("k0", 1)
    world.run_later()
    assert not world.backend.pointer()["visible"]


def clip_lessons(url=VIDEO):
    step = fake_step(0, clip={"start": 12.0, "end": 19.5})
    return {"clipped": {"title": "Clipped", "steps": [step, fake_step(1)],
                        "source": {"url": url, "title": "SUM", "creator": "Sheet School", "channel_url": "",
                                   "licence": "Creative Commons", "length_s": 372}}}


def test_clip_missing_offers_the_video_link(tmp_path):
    w = World(tmp_path, lessons=clip_lessons())
    try:
        w.open("clipped")
        clip = w.backend.lesson()["step"]["clip"]
        assert clip == {"state": "missing", "file": "", "start": 12.0, "end": 19.5,
                        "videoUrl": "https://www.youtube.com/watch?v=k7RM-ot2NWY&t=12s"}

        video = w.tmp / "recordings" / "k7RM-ot2NWY" / "video.mp4"
        video.parent.mkdir(parents=True)
        video.write_bytes(b"\x00")
        w.backend.watch_clip()
        w.idle()
        clip = w.backend.lesson()["step"]["clip"]
        assert (clip["state"], clip["file"]) == ("available", str(video))
    finally:
        w.backend.shutdown()


def test_a_clip_from_anywhere_but_youtube_offers_no_link(tmp_path):
    w = World(tmp_path, lessons=clip_lessons("https://example.com/watch?v=k7RM-ot2NWY"))
    try:
        w.open("clipped")
        assert w.backend.lesson()["step"]["clip"]["videoUrl"] == ""
        w.learner_sets("k0", 1)
        w.run_later()
        assert w.backend.lesson()["step"]["clip"]["state"] == "none"     # step 2 has no clip
    finally:
        w.backend.shutdown()


def test_ask_never_ticks_a_step(world):
    world.coach.answer_text = "Done! You finished this step."
    world.open()
    world.learner_sets("k0", 5)                           # a wrong try first, so the coach hears it
    world.backend.next_hint()
    world.backend.ask("Is it done?")
    world.idle()

    lesson = world.backend.lesson()
    assert lesson["ask"] == {"state": "answered", "question": "Is it done?",
                             "answer": "Done! You finished this step."}
    assert (lesson["stepIndex"], lesson["points"]) == (0, 0) and "right" not in world.cues()
    question, context = world.coach.asked[0]
    assert context["instruction"] == "Set k0 to 1." and context["why"] == "k0 needs a value."
    assert context["hints"] == ["Find k0.", "k0 needs a value.", "Set k0 to 1."] and context["hints_shown"] == 1
    assert context["verdict"] == "Not yet: k0 says 5. It should say 1."
    assert context["state"] == {"k0": 5}


def test_a_coach_that_cannot_answer_says_its_calm_line(world):
    world.open()
    world.coach.failure = CoachUnavailable("Meta can't be reached right now. Lessons still work.")
    world.backend.ask("Why?")
    world.idle()
    assert world.backend.lesson()["ask"] == {"state": "error", "question": "Why?",
                                             "answer": "Meta can't be reached right now. Lessons still work."}
    assert world.backend.home()["meta"] == "unreachable"


def test_a_missing_key_shows_on_home(tmp_path):
    w = World(tmp_path, key=None)
    try:
        assert w.backend.home()["meta"] == "no_key"
        w.open()
        failure = CoachUnavailable("Ask needs a Meta key.")
        failure.__cause__ = NoKey("no key")
        w.coach.failure = failure
        w.backend.ask("Why?")
        w.idle()
        assert w.backend.home()["meta"] == "no_key"
    finally:
        w.backend.shutdown()


def test_the_key_is_checked_again_after_the_setup_line_is_copied(tmp_path):
    w = World(tmp_path, key=None)
    try:
        w.backend.key_setup_copied()
        w.idle()
        w.run_later()
        assert w.backend.home()["meta"] == "no_key"
        w.key = "saved-now"
        w.run_later()
        assert w.backend.home()["meta"] == "ok"
        assert w.later.waiting == []                  # it stops looking once the key is there
    finally:
        w.backend.shutdown()


def test_finished_lesson_refreshes_tips(world):
    assert world.backend.home()["tips"] == {"state": "none", "text": ""}
    world.open()
    world.learner_sets("k0", 1)
    world.learner_sets("k1", 2)

    lesson = world.backend.lesson()
    assert lesson["complete"] == {"points": 20, "seconds": lesson["complete"]["seconds"], "firstTry": 2,
                                  "steps": 2, "streak": 1, "streakBefore": 0}
    assert world.cues()[-1] == "complete" and not world.backend.pointer()["visible"]
    assert world.progress.lesson_state("two-keys").done
    assert [r.step_id for r in world.progress.attempts()] == ["two-keys/s0", "two-keys/s1"]
    assert world.coach.tips_asked[-1] == world.progress.attempts()
    assert world.backend.home()["tips"] == {"state": "ready", "text": "You finished 2 steps. Try the next lesson."}
    assert world.progress.tips == "You finished 2 steps. Try the next lesson."
    assert not world.plugin.session.waiting


def test_a_second_lesson_on_the_same_day_keeps_the_streak_as_it_was(tmp_path):
    w = World(tmp_path, lessons={"a": {"title": "A first"}, "b": {"title": "B second"}})
    try:
        w.open("a")
        w.learner_sets("k0", 1)
        w.learner_sets("k1", 2)
        complete = w.backend.lesson()["complete"]
        assert (complete["streakBefore"], complete["streak"]) == (0, 1)     # today counts now: it ticks up
        w.backend.next_lesson()
        w.idle()
        w.learner_sets("k0", 1)
        w.learner_sets("k1", 2)
        complete = w.backend.lesson()["complete"]
        assert (complete["streakBefore"], complete["streak"]) == (1, 1)     # today already counted
    finally:
        w.backend.shutdown()


def test_tips_that_cannot_come_say_so_on_home(world):
    world.coach.failure = CoachUnavailable("Meta can't be reached right now.")
    world.open()
    world.learner_sets("k0", 1)
    world.learner_sets("k1", 2)
    assert world.backend.home()["tips"]["state"] == "error"


def test_a_step_that_came_undone_is_listed_and_can_be_pointed_at(tmp_path):
    w = World(tmp_path, lessons={"three": {"title": "Three", "steps": 3}})
    try:
        session = w.open("three")
        session.spots["k0"] = Spot(Rect(10, 20, 30, 40))
        w.learner_sets("k0", 1)
        w.run_later()
        w.learner_sets("k1", 2)
        w.run_later()
        w.learner_sets("k0", 9)                        # step 1 undone while on step 3
        assert w.backend.lesson()["changed"] == [0]

        w.backend.go_to_step(0)
        w.idle()
        pointer = w.backend.pointer()
        assert (pointer["x"], pointer["y"], pointer["mascot"]) == (10, 20, "flying")
        assert session.watching.ref == "k0"

        w.learner_sets("k0", 1)                        # fixed: back to the step it was on
        assert w.backend.lesson()["changed"] == []
        assert session.watching.ref == "k2"
    finally:
        w.backend.shutdown()


def test_the_last_step_done_with_an_earlier_one_undone_points_at_what_to_fix(world):
    world.open()
    world.learner_sets("k0", 1)
    world.run_later()
    world.learner_sets("k0", 3)
    world.learner_sets("k1", 2)
    lesson = world.backend.lesson()
    assert lesson["complete"] is None and lesson["changed"] == [0]
    assert lesson["banner"] == {"kind": "changed", "stepIndex": 0,
                                "text": "Every step is done, but step 1 changed. Fix it in Fake app to finish."}
    assert lesson["step"]["index"] == 0                  # the panel shows the step to fix,
    assert lesson["stepIndex"] == lesson["stepCount"]    # while the bar stays full: nothing was lost
    assert world.plugin.session.watching.ref == "k0"
    world.learner_sets("k0", 1)
    assert world.backend.lesson()["complete"] is not None


def test_a_change_in_the_app_after_lesson_done_leaves_the_top_bar_full(world):
    world.open()
    world.learner_sets("k0", 1)
    world.learner_sets("k1", 2)
    assert world.backend.lesson()["complete"] is not None
    world.learner_sets("k0", 9)                           # undone after the celebration
    lesson = world.backend.lesson()
    assert (lesson["stepIndex"], lesson["stepCount"], lesson["banner"]) == (2, 2, None)
    world.learner_sets("k0", 1)                           # and fixed again
    lesson = world.backend.lesson()
    assert (lesson["stepIndex"], lesson["stepCount"], lesson["banner"]) == (2, 2, None)


def test_home_shows_the_learner_their_courses_and_what_is_locked(tmp_path):
    w = World(tmp_path, lessons={"a": {"title": "A first"}, "b": {"title": "B second"},
                                 "c": {"title": "C third"}})
    try:
        home = w.backend.home()
        assert home["learner"] == {"name": "Ranvir", "streak": 0, "pointsToday": 0, "dailyGoal": 30}
        assert home["continueCard"] is None
        sheets, code = home["courses"]
        assert (sheets["id"], sheets["title"], sheets["app"], sheets["colour"], sheets["ready"]) == (
            "sheets", "Sheets", "fake", "courseExcel", True)
        assert [(c["id"], c["state"], c["badge"]) for c in sheets["lessons"]] == [
            ("a", "current", "proven and tested"), ("b", "locked", "proven and tested"),
            ("c", "locked", "proven and tested")]
        assert (code["ready"], code["lessons"], code["progress"]) == (False, [], 0.0)

        w.open("a")
        w.learner_sets("k0", 1)
        w.learner_sets("k1", 2)
        sheets = w.backend.home()["courses"][0]
        assert [c["state"] for c in sheets["lessons"]] == ["done", "current", "locked"]
        assert sheets["progress"] == pytest.approx(1 / 3)
        assert w.backend.home()["learner"]["streak"] == 1
    finally:
        w.backend.shutdown()


def test_a_locked_lesson_does_not_open(tmp_path):
    w = World(tmp_path, lessons={"a": {"title": "A first"}, "b": {"title": "B second"}})
    try:
        w.backend.open_lesson("b")
        w.idle()
        assert w.plugin.opens == []
    finally:
        w.backend.shutdown()


def test_next_lesson_opens_the_one_after(tmp_path):
    w = World(tmp_path, lessons={"a": {"title": "A first"}, "b": {"title": "B second"}})
    try:
        w.open("a")
        w.learner_sets("k0", 1)
        w.learner_sets("k1", 2)
        w.backend.next_lesson()
        w.idle()
        assert [o["lesson"] for o in w.plugin.opens] == ["a", "b"]
        assert w.backend.lesson()["id"] == "b"
    finally:
        w.backend.shutdown()


def test_making_a_lesson_shows_each_stage_and_lands_it_unlocked_on_its_shelf(world):
    world.maker.gate = threading.Event()
    world.backend.make_lesson(VIDEO)
    deadline = time.monotonic() + 5
    while world.backend.home()["factory"]["stages"][0]["state"] != "running":
        assert time.monotonic() < deadline
        time.sleep(0.01)
    factory = world.backend.home()["factory"]
    assert (factory["state"], factory["url"]) == ("running", VIDEO)
    assert [s["name"] for s in factory["stages"]] == ["download", "read", "write", "prove", "test", "publish"]
    assert factory["stages"][0] == {"name": "download", "state": "running", "detail": "Getting the video"}
    world.backend.make_lesson(VIDEO)                  # one at a time
    world.maker.gate.set()
    world.idle()

    factory = world.backend.home()["factory"]
    assert (factory["state"], factory["lessonId"]) == ("ready", "made-sum")
    assert world.maker.made == [(VIDEO, "fake")]
    sheets = world.backend.home()["courses"][0]
    assert ("made-sum", "current") in [(c["id"], c["state"]) for c in sheets["lessons"]]
    assert sheets["credits"] == ["Sheet School"]
    assert world.progress.made == ["made-sum"]

    world.backend.dismiss_factory()
    world.idle()
    assert world.backend.home()["factory"] == {"state": "idle", "url": "", "stages": [], "reason": "",
                                               "lessonId": None}


def test_a_video_that_cannot_become_a_lesson_says_why(world):
    world.maker.reason = "No steps could be found in this video."
    world.backend.make_lesson(VIDEO)
    world.idle()
    factory = world.backend.home()["factory"]
    assert (factory["state"], factory["reason"]) == ("not_ready", "No steps could be found in this video.")
    assert factory["stages"][1] == {"name": "read", "state": "failed", "detail": "No steps found"}


def test_muting_is_shown_on_home(world):
    world.backend.set_muted(True)
    world.idle()
    assert world.backend.home()["muted"] is True
    assert world.last("home")["muted"] is True


def test_go_home_closes_the_lesson_and_refreshes_home(world):
    world.open()
    world.learner_sets("k0", 1)
    world.backend.go_home()
    world.idle()
    assert not world.backend.lesson()["open"]
    assert world.backend.home()["continueCard"]["lessonId"] == "two-keys"
    assert world.plugin.session.closed


def test_a_saved_copy_that_already_passes_every_step_opens_finished(world):
    world.progress.step_passed("two-keys", 0, 10)
    saved = world.tmp / "mentora" / "work" / "two-keys" / "state.json"
    saved.parent.mkdir(parents=True)
    saved.write_text('{"k0": 1, "k1": 2}', encoding="utf-8")
    world.open()
    lesson = world.backend.lesson()
    assert lesson["complete"] is not None and lesson["complete"]["steps"] == 0
    assert "complete" not in world.cues() and "right" not in world.cues()
    assert world.progress.lesson_state("two-keys").done


def test_the_coach_hears_the_target_cells_and_the_selection():
    snap = Snapshot(sheets=(Sheet("Budget", {"B8": Cell(23000, "=SUM(B2:B6)"), "B2": Cell(900)}),),
                    active_sheet="Budget", selection="B2")
    step = SimpleNamespace(target=Target("cell", "Budget!B8"))
    assert coach_state(snap, step) == {"Budget!B8": 23000, "Budget!B8 formula": "=SUM(B2:B6)",
                                       "selected cell": "Budget!B2"}


def test_the_coach_hears_about_code_but_never_the_code_itself():
    from app.vscode.snapshot import Active, FileState, Problem, Run, VsSnapshot
    code = "print('my secret plan')"
    snap = VsSnapshot(files={"C:/work/hello.py": FileState(code, saved=False)},
                      active=Active("C:/work/hello.py", 1, 1, 1, 1, 18.0, 14.0),
                      problems=(Problem("C:/work/hello.py", 1, "error", "bad"),),
                      run=Run("python hello.py", 1, "Traceback", True))
    step = SimpleNamespace(target=Target("editor", "hello.py"))
    state = coach_state(snap, step)
    assert state == {"open file": "hello.py", "saved": False, "problems": 1, "last run exit code": 1}
    assert "secret" not in repr(state)
    assert save_note(snap) == SAVE_NOTE
    assert save_note(VsSnapshot(files={"C:/work/hello.py": FileState(code, saved=True)})) == ""
    assert save_note({"k0": 1}) == ""


def test_the_waiting_line_names_every_undone_step():
    from app.integration.backend import _undone_text
    assert _undone_text([0], "Excel") == "Every step is done, but step 1 changed. Fix it in Excel to finish."
    assert _undone_text([0, 2, 4], "VS Code") == (
        "Every step is done, but steps 1, 3 and 5 changed. Fix them in VS Code to finish.")


def test_every_shape_the_backend_sends_has_exactly_the_keys_the_screens_read(world):
    from app.core.screen import HomeState, LessonState, PointerState
    from tests.screen_shapes import shape_problems

    world.open()
    world.learner_sets("k0", 1)
    world.run_later()
    world.learner_sets("k1", 7)                      # not yet
    world.backend.next_hint()
    world.backend.show_me()
    world.backend.ask("Why?")
    world.idle()
    world.coach.failure = CoachUnavailable("Meta can't be reached right now. Lessons still work.")
    world.backend.ask("Why again?")
    world.idle()
    world.plugin.session.closed_by_learner()         # the app closes
    world.idle()
    world.backend.reopen_app()
    world.idle()
    world.learner_sets("k0", 3)                      # step 1 comes undone
    world.learner_sets("k1", 2)
    world.backend.go_to_step(0)
    world.idle()
    world.learner_sets("k0", 1)                      # finished
    world.run_later()
    world.backend.make_lesson(VIDEO)
    world.idle()
    world.backend.dismiss_factory()
    world.backend.close_lesson()
    world.idle()

    shapes = {"home": HomeState, "lesson": LessonState, "pointer": PointerState}
    sent = [(name, payload) for name, payload in world.sent if name in shapes]
    assert {name for name, _ in sent} == set(shapes)
    assert any(p.get("complete") for n, p in sent if n == "lesson")
    problems = []
    for i, (name, payload) in enumerate(sent):
        problems += shape_problems(payload, shapes[name], f"#{i} {name}")
    assert problems == []



def _until(condition, timeout=5.0):
    end = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < end, "it never happened"
        time.sleep(0.01)


def test_an_app_the_learner_closed_is_let_go(world):
    session = world.open()
    session.closed_by_learner()
    world.idle()
    assert session.close_calls == [True]        # its own clean-up runs (Excel quits), keeping any work left


def test_a_step_passed_again_after_reopening_earns_nothing_new(world):
    session = world.open()
    world.learner_sets("k0", 1)
    world.run_later()
    session.closed_by_learner()
    world.idle()
    (world.tmp / "mentora" / "work" / "two-keys" / "state.json").unlink(missing_ok=True)  # Don't save
    world.backend.reopen_app()
    world.idle()
    assert world.backend.lesson()["stepIndex"] == 0
    world.learner_sets("k0", 1)
    assert world.backend.lesson()["banner"]["kind"] == "right"
    assert world.progress.points_today() == 10
    assert world.backend.lesson()["points"] == 10


def test_an_answer_that_arrives_after_the_step_is_passed_is_dropped(world):
    world.open()
    world.coach.gate = threading.Event()
    world.backend.ask("Which key?")
    _until(lambda: world.coach.asked)
    world.plugin.session.learner_sets("k0", 1)
    _until(lambda: (world.backend.lesson()["banner"] or {}).get("kind") == "right")
    world.later.run()                           # the cheer ends and the Ask box clears for the next step
    _until(lambda: world.backend.lesson()["ask"]["state"] == "idle")
    world.coach.gate.set()
    world.idle()
    assert world.backend.lesson()["ask"] == {"state": "idle", "question": "", "answer": ""}


def test_an_answer_about_a_passed_step_is_dropped_when_the_learner_carries_straight_on(world):
    world.open()
    world.coach.gate = threading.Event()
    world.backend.ask("Which key?")
    _until(lambda: world.coach.asked)
    world.plugin.session.learner_sets("k0", 1)
    _until(lambda: (world.backend.lesson()["banner"] or {}).get("kind") == "right")
    world.plugin.session.learner_sets("k1", 5)  # straight on to the next step, which ends the cheer at once
    _until(lambda: (world.backend.lesson()["banner"] or {}).get("kind") == "not_yet")
    world.coach.gate.set()
    world.idle()
    assert world.backend.lesson()["ask"] == {"state": "idle", "question": "", "answer": ""}


def test_tips_with_nothing_new_to_say_keep_the_last_ones(world):
    world.progress.keep_tips("Try the Name Box.")
    world.backend.shutdown()
    world.start()
    world.coach.tips = lambda log: ""
    world.open()
    world.learner_sets("k0", 1)
    world.learner_sets("k1", 2)
    assert world.backend.lesson()["complete"] is not None
    assert world.backend.home()["tips"] == {"state": "ready", "text": "Try the Name Box."}
    assert Progress(world.tmp / "mentora", today=lambda: TODAY).tips == "Try the Name Box."


def test_hint_helps_with_the_step_that_came_undone(world):
    world.open()
    world.learner_sets("k0", 1)
    world.run_later()
    world.learner_sets("k0", 3)
    world.learner_sets("k1", 2)
    assert world.backend.lesson()["step"]["index"] == 0
    world.backend.next_hint()
    world.idle()
    step = world.backend.lesson()["step"]
    assert (step["hints"], step["hintsLeft"]) == (["Find k0."], 2)


def test_ask_is_about_the_step_that_came_undone(world):
    world.open()
    world.learner_sets("k0", 1)
    world.run_later()
    world.learner_sets("k0", 3)
    world.learner_sets("k1", 2)
    assert world.backend.lesson()["step"]["index"] == 0
    world.backend.next_hint()
    world.backend.ask("What do I fix?")
    world.idle()
    _, context = world.coach.asked[0]
    assert context["instruction"] == "Set k0 to 1." and context["hints_shown"] == 1
    assert context["hints"] == ["Find k0.", "k0 needs a value.", "Set k0 to 1."]


def test_the_coach_never_hears_another_steps_not_yet(world):
    world.open()
    world.learner_sets("k0", 5)                           # a Not yet on step 1
    world.learner_sets("k0", 1)
    world.run_later()
    world.backend.ask("Where do I start?")                # asked on step 2, which has no Not yet
    world.idle()
    _, context = world.coach.asked[0]
    assert context["instruction"] == "Set k1 to 2." and context["verdict"] == ""


def test_quitting_does_not_wait_for_an_answer_from_the_coach(world):
    world.coach.gate = threading.Event()
    world.open()
    world.backend.ask("Which key?")
    _until(lambda: world.coach.asked)
    started = time.monotonic()
    world.backend.shutdown()
    assert time.monotonic() - started < 1.0
    assert world.plugin.session.close_calls == [True]   # the lesson's app is still saved and closed
    world.coach.gate.set()


def test_after_quitting_nothing_more_reaches_the_screens(world):
    world.maker.gate = threading.Event()
    world.backend.make_lesson(VIDEO)
    _until(lambda: world.maker.made)
    quitting = threading.Thread(target=world.backend.shutdown)
    quitting.start()                            # waits for the lesson being made
    time.sleep(0.2)
    world.sent.clear()
    world.maker.gate.set()
    quitting.join(5)
    assert not quitting.is_alive()
    assert world.sent == []                     # the made lesson's news doesn't reach screens that are gone


def test_questions_dropped_as_the_program_quits_are_not_left_counted(world):
    world.coach.gate = threading.Event()
    world.open()
    world.backend.ask("Which key?")
    _until(lambda: world.coach.asked)
    world.backend.ask("Which cell?")            # waits in line behind the first question
    time.sleep(0.2)
    world.backend.shutdown()                    # drops the one waiting in line
    world.coach.gate.set()
    assert world.backend.wait_idle(2.0)


def test_the_app_comes_to_the_front_once_it_is_in_its_place(world):
    world.plugin.held_places = []
    session = world.open()
    assert world.fronts == []                    # still moving: not shown off in the wrong place
    world.plugin.held_places[0].set_result(None)
    world.idle()
    assert session.placed == APP_RECT and world.fronts == [session.hwnd()]


def test_an_app_that_would_not_move_still_comes_to_the_front(world):
    world.plugin.held_places = []
    session = world.open()
    world.plugin.held_places[0].set_exception(OSError("the window would not move"))
    world.idle()
    assert world.fronts == [session.hwnd()]      # the learner must still see it


def test_a_reopened_app_comes_to_the_front_too(world):
    first = world.open()
    first.closed_by_learner()
    world.idle()
    world.backend.reopen_app()
    world.idle()
    again = world.plugin.session
    assert again is not first and world.fronts == [first.hwnd(), again.hwnd()]


def test_the_screen_changing_never_pulls_the_app_to_the_front(world):
    session = world.open()
    world.backend.relayout()
    world.idle()
    assert world.fronts == [session.hwnd()]      # only as it opened: by now the learner may be in another window


def test_an_app_whose_lesson_closed_while_it_moved_stays_behind(world):
    world.plugin.held_places = []
    world.open()
    world.backend.close_lesson()
    world.idle()
    world.plugin.held_places[0].set_result(None)
    world.idle()
    assert world.fronts == []


def test_only_the_app_of_the_lesson_open_now_comes_to_the_front(world):
    world.plugin.held_places = []
    first = world.open()
    world.backend.close_lesson()
    again = world.open()                         # opened again while the first app was still moving
    world.plugin.held_places[0].set_result(None)
    world.idle()
    assert world.fronts == []
    world.plugin.held_places[1].set_result(None)
    world.idle()
    assert again is not first and world.fronts == [again.hwnd()]


def test_the_ask_to_bring_the_app_forward_lapses_when_its_lesson_closes(world):
    world.open()
    still = world.stills[0]
    assert still()                               # the screens bring the app forward only while this holds
    world.backend.close_lesson()                 # the learner went home before the screens got to the ask
    world.idle()
    assert not still()
    world.open()
    assert not still() and world.stills[1]()
