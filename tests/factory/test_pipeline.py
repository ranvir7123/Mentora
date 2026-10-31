import shutil
import struct

import pytest

from app.core.fake_plugin import FakePlugin
from app.core.lesson import TestResult, load_lesson, shelf_badge
from app.factory import tester as tester_module
from app.factory.input import UserTookOver
from app.factory.pipeline import STAGES, LessonFactory, run_test
from app.factory.prove import ProveError
from app.factory.video import Fetched, VideoInfo, VideoRefused
from app.factory.writer import BROKE_RULES
from app.meta.client import NoKey, SpendLimitReached
from tests.core.conftest import build_fake_lesson

URL = "https://youtu.be/vid1"
INFO = VideoInfo("vid1", URL, "Fill in the keys", "Key Teacher", "https://youtube.com/@keys",
                 "Creative Commons Attribution license (reuse allowed)", 3)
VTT = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nset k1 to one\n\n00:00:01.000 --> 00:00:02.000\nnow k2\n"


def _step(i, **over):
    """Muse Spark's step i for the fake app: set k{i} to i, shown in the video's second i."""
    step = {"id": f"s{i}", "instruction": f"Set k{i} to {i}.", "why": f"k{i} needs a value.",
            "target": {"kind": "key", "ref": f"k{i}"},
            "check": {"kind": "equals", "args": {"key": f"k{i}", "value": i}},
            "replay": {"kind": "set", "args": {"key": f"k{i}", "value": i}},
            "hints": [f"Find k{i}.", f"k{i} needs a number.", f"Set k{i} to {i}."],
            "mistakes": [{"replay": {"kind": "set", "args": {"key": f"k{i}", "value": -i}},
                          "not_yet": f"k{i} should be {i}, not {-i}."}],
            "clip": {"start": i - 1.0, "end": float(i)}}
    step.update(over)
    return step


def _lesson(steps=None):
    return {"title": "Fill in the keys", "goal": {"sentence": "Every key holds its number."}, "starter": {"k0": 0},
            "steps": steps if steps is not None else [_step(1), _step(2), _step(3)]}


class FakeFetch:
    """The download: a real 3-second video and its captions, put where yt-dlp would put them."""

    def __init__(self, clip, error=None):
        self.clip, self.error, self.calls = clip, error, []

    def __call__(self, url, dest):
        self.calls.append((url, dest))
        if self.error:
            raise self.error
        shutil.copyfile(self.clip, dest / "video.mp4")
        (dest / "video.en.vtt").write_text(VTT, encoding="utf-8")
        return Fetched(INFO, dest / "video.mp4", dest / "video.en.vtt")


def outcome(passes, runs=5, mode="mouse"):
    return TestResult(passed=passes >= 4, at="2026-10-29T12:00:00+00:00", mode=mode, runs=runs, passes=passes)


class FakeTester:
    """Meta's agent playing the learner, with results from a script."""

    def __init__(self, *results, during=None):
        self.results, self.calls, self.during = list(results), [], during

    def __call__(self, lesson, plugin, workdir, client, *, runs, mode, hands, on_line, on_progress=None):
        self.calls.append({"lesson": lesson, "workdir": workdir, "runs": runs, "mode": mode, "hands": hands})
        if self.during:
            self.during()
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        if on_progress:
            on_progress(f"run 1 of {runs} is playing")
        on_line("refused keypress win: That key would leave the app. Stay in the app's window.")
        on_line("run 1 passed" if result.passed else "run 1 failed: Meta is busy right now (503: upstream reset)")
        return result


class Stages:
    """What the screen is told: (stage, state, detail) in order."""

    def __init__(self):
        self.calls = []

    def __call__(self, name, state, detail):
        assert name in STAGES and state in ("waiting", "running", "done", "failed")
        self.calls.append((name, state, detail))

    def last(self):
        return {name: (state, detail) for name, state, detail in self.calls}

    def changes(self):
        """Each stage's states in the order they changed, leaving out detail updates."""
        seen = []
        for name, state, _ in self.calls:
            if (name, state) not in seen:
                seen.append((name, state))
        return seen


@pytest.fixture
def make(tmp_path, saved, clip):
    """Runs the factory on the fake app; returns the result, what the screen was told, and the log."""
    def go(*, tester=None, fetch=None, plugin=None, **kwargs):
        lines, stages = [], Stages()
        tester = tester or FakeTester(outcome(5))
        factory = LessonFactory(saved.client, tmp_path / "lessons", tmp_path / "recordings",
                                fetch=fetch or FakeFetch(clip), tester=tester, hands="the hands", hands_off_s=0,
                                on_line=lines.append, **kwargs)
        result = factory.make(URL, plugin or FakePlugin(), stages)
        return result, stages, lines, tester
    return go


def _written(saved, label="writer_vid1", lesson=None):
    saved.file(f"{label}_upload")
    saved.answer(label, lesson or _lesson())


def _png_size(path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def test_a_good_video_lands_on_the_shelf_with_its_stages_reported(tmp_path, saved, make):
    _written(saved)

    result, stages, lines, tester = make()

    assert result.reason == "" and result.lesson is not None
    lesson = load_lesson(tmp_path / "lessons" / "fill-in-the-keys")
    assert lesson == result.lesson
    assert shelf_badge(lesson) == "proven and tested"
    assert [s.id for s in lesson.steps] == ["s1", "s2", "s3"] and lesson.source.url == URL
    assert lesson.goal.picture == "goal.png"
    assert _png_size(lesson.folder / "goal.png") == (1280, 720)        # the video at the end of the last step

    assert stages.calls[:6] == [(name, "waiting", "") for name in STAGES]
    assert stages.changes()[6:] == [(name, state) for name in STAGES for state in ("running", "done")]
    assert stages.last() == {
        "download": ("done", '"Fill in the keys" by Key Teacher, 0:03 long'),
        "read": ("done", "3 still frames, 2 lines of transcript"),
        "write": ("done", "3 steps written"),
        "prove": ("done", "3 of 3 steps proven"),
        "test": ("done", "5 of 5 test runs passed"),
        "publish": ("done", 'On the shelf as "Fill in the keys", with the proven and tested badge'),
    }
    assert "test: Mouse test: run 1 passed" in lines
    assert f"The lesson is saved in {lesson.folder}" in lines

    [call] = tester.calls
    assert call["mode"] == "mouse" and call["runs"] == 5 and call["hands"] == "the hands"
    assert call["lesson"].proof.passed                                   # the agent plays the proven lesson
    assert call["workdir"] == tmp_path / "recordings" / "vid1" / "test" / "mouse"
    assert sorted(p.name for p in (tmp_path / "recordings").iterdir()) == ["vid1"]   # no half downloads left
    assert (tmp_path / "recordings" / "vid1" / "video.mp4").exists()


def test_a_failed_proof_publishes_nothing_and_says_why(tmp_path, saved, make):
    already_true = _step(2, check={"kind": "equals", "args": {"key": "k0", "value": 0}})
    _written(saved, lesson=_lesson([_step(1), already_true, _step(3)]))
    _written(saved, "writer_vid1_fix1", _lesson([_step(1), already_true, _step(3)]))   # sent back once, still wrong

    result, stages, lines, tester = make()

    reason = "Only 2 of 3 steps could be proven, and a lesson needs at least 3. Try another video."
    assert result.lesson is None and result.reason == reason
    assert stages.last()["prove"] == ("failed", reason)
    assert stages.last()["test"] == ("waiting", "") and stages.last()["publish"] == ("waiting", "")
    assert f"prove failed: {reason}" in lines
    assert "prove: Step s2 was dropped: its check was already true before the step." in lines   # for Ranvir
    assert tester.calls == []
    assert not (tmp_path / "lessons").exists()


def test_a_step_sent_back_is_said_plainly_on_screen_and_in_full_in_the_log(saved, make):
    already_true = _step(2, check={"kind": "equals", "args": {"key": "k0", "value": 0}})
    _written(saved, lesson=_lesson([_step(1), already_true, _step(3)]))
    _written(saved, "writer_vid1_fix1", _lesson())

    result, stages, lines, _ = make()

    assert result.lesson is not None
    assert [d for name, state, d in stages.calls if name == "prove" and d] == [
        "A step did not pass its proof, so it goes back to Muse Spark to be fixed", "3 of 3 steps proven"]
    assert "prove: Step s2: its check was already true before the step; it goes back to Muse Spark" in lines


def test_a_step_that_was_dropped_is_counted_but_the_lesson_still_goes_on(tmp_path, saved, make):
    loose = _step(4, mistakes=[{"replay": {"kind": "set", "args": {"key": "k4", "value": 4}},
                                "not_yet": "k4 should be 4."}])                 # the mistake is the right answer
    steps = [_step(1), _step(2), _step(3), loose]
    _written(saved, lesson=_lesson(steps))
    _written(saved, "writer_vid1_fix1", _lesson(steps))

    result, stages, lines, _ = make()

    assert [s.id for s in result.lesson.steps] == ["s1", "s2", "s3"]
    assert stages.last()["prove"] == ("done", "3 of 4 steps proven, 1 dropped")
    assert ("prove: 3 of 4 steps proven, 1 dropped (s4: its check accepted mistake 1 (set key=k4 value=4), so the "
            "check is too loose)") in lines


def test_test_fallback_goes_keyboard_then_proven_only(tmp_path, saved, make):
    _written(saved)
    tester = FakeTester(outcome(2), outcome(1, mode="keyboard"))

    result, stages, lines, _ = make(tester=tester)

    assert [c["mode"] for c in tester.calls] == ["mouse", "keyboard"]
    assert tester.calls[1]["workdir"] == tmp_path / "recordings" / "vid1" / "test" / "keyboard"
    assert result.lesson.test.mode == "skipped" and shelf_badge(result.lesson) == "proven"
    assert load_lesson(result.lesson.folder).test.mode == "skipped"
    switch = "The mouse test passed 2 of 5 runs, so the keyboard-only test runs now"
    assert ("test", "running", switch) in stages.calls and f"test: {switch}" in lines
    last = ("The keyboard-only test passed 1 of 5 runs too, so the lesson goes on the shelf with the proven badge, "
            "not proven and tested")
    assert stages.last()["test"] == ("done", last) and f"test done: {last}" in lines
    assert stages.last()["publish"] == ("done", 'On the shelf as "Fill in the keys", with the proven badge')


def test_the_card_hears_only_plain_progress_while_the_test_runs_and_the_log_hears_everything(saved, make):
    _written(saved)

    result, stages, lines, _ = make(tester=FakeTester(outcome(2), outcome(4, mode="keyboard")))

    assert [d for name, state, d in stages.calls if name == "test" and state == "running" and d] == [
        "Mouse test: run 1 of 5 is playing",
        "The mouse test passed 2 of 5 runs, so the keyboard-only test runs now",
        "Keyboard-only test: run 1 of 5 is playing",
    ]
    assert "test: Mouse test: run 1 failed: Meta is busy right now (503: upstream reset)" in lines   # for Ranvir
    assert ("test: Keyboard-only test: refused keypress win: That key would leave the app. Stay in the app's "
            "window.") in lines


def test_a_lesson_the_agent_can_play_by_keyboard_is_proven_and_tested(saved, make):
    _written(saved)

    result, stages, _, _ = make(tester=FakeTester(outcome(3), outcome(4, mode="keyboard")))

    assert result.lesson.test.mode == "keyboard" and shelf_badge(result.lesson) == "proven and tested"
    assert stages.last()["test"] == ("done", "4 of 5 test runs passed, using the keyboard only")


@pytest.mark.parametrize("stop, said, logged", [
    (UserTookOver("You moved the mouse, so the test stopped."), "You moved the mouse, so the test stopped.", ""),
    (ProveError("Fake app did not answer within 30 s"), "The test could not run.",
     "Fake app did not answer within 30 s. "),
    (ProveError("Fake app could not be read.", detail="Fake app could not be read: the workbook is busy"),
     "The test could not run.", "Fake app could not be read: the workbook is busy. "),
    (SpendLimitReached("Meta spending has reached $100.00 of the $100.00 limit. Tell Ranvir before spending more."),
     "The test could not run.", "Meta spending has reached $100.00 of the $100.00 limit. Tell Ranvir before spending "
     "more. "),
])
def test_a_test_that_cannot_finish_leaves_the_lesson_proven_only(tmp_path, saved, make, stop, said, logged):
    _written(saved)
    tester = FakeTester(stop)

    result, stages, lines, _ = make(tester=tester)

    assert [c["mode"] for c in tester.calls] == ["mouse"]                 # no keyboard test after a stop
    assert shelf_badge(result.lesson) == "proven"
    assert stages.last()["test"] == ("done", f"{said} The lesson goes on the shelf with the proven badge.")
    folder = (tmp_path / "lessons" / "fill-in-the-keys").as_posix()     # the command is for Ranvir, in the log
    assert f"test: {logged}Test it later with: python -m app.factory test {folder}" in lines


class WontOpen(FakePlugin):
    def __init__(self, error):
        super().__init__()
        self.error = error

    def open(self, *args, **kwargs):
        raise self.error


@pytest.mark.parametrize("error, said", [
    (OSError("(-2147352567, 'Exception occurred.', (0, None, None, None, 0, -2147024891), None)"),
     "(-2147352567, 'Exception occurred.', (0, None, None, None, 0, -2147024891), None)"),
    (KeyError(), "KeyError"),
])
def test_an_app_that_will_not_open_is_said_plainly_with_its_own_words_in_the_log(saved, make, error, said):
    _written(saved)

    result, stages, lines, _ = make(plugin=WontOpen(error))

    assert result.reason == "Fake app could not be opened."
    assert stages.last()["prove"] == ("failed", result.reason)
    assert f"prove: Fake app could not be opened: {said}" in lines


def test_switching_the_test_off_gives_the_proven_badge(saved, make):
    _written(saved)
    tester = FakeTester()

    result, stages, _, _ = make(tester=tester, test=False)

    assert tester.calls == [] and shelf_badge(result.lesson) == "proven"
    assert stages.last()["test"] == ("done", "Not tested: the test was switched off, so the lesson goes on the shelf "
                                             "with the proven badge")


def test_a_refused_video_stops_at_the_download_with_its_reason(tmp_path, saved, clip, make):
    fetch = FakeFetch(clip, error=VideoRefused("That is a live stream. Pick a finished video."))

    result, stages, _, _ = make(fetch=fetch)

    assert result.lesson is None and result.reason == "That is a live stream. Pick a finished video."
    assert stages.last()["download"] == ("failed", result.reason)
    assert stages.last()["read"] == ("waiting", "")
    assert list((tmp_path / "recordings").iterdir()) == []              # the half download is cleared away
    assert not (tmp_path / "lessons").exists()


def test_a_lesson_muse_spark_will_not_write_stops_at_the_write_stage(saved, make):
    saved.file("writer_vid1_upload")
    saved.refusal("writer_vid1", "I cannot help with that video.")

    result, stages, _, _ = make()

    assert result.reason == "Muse Spark would not write this lesson: I cannot help with that video."
    assert stages.last()["write"] == ("failed", result.reason)


def test_something_unexpected_fails_its_stage_plainly_and_is_logged(tmp_path, clip, make):
    result, stages, lines, _ = make(fetch=FakeFetch(clip, error=RuntimeError("the download fell over")))

    assert result.lesson is None
    assert result.reason == "Something unexpected went wrong. Try another video."
    assert stages.last()["download"] == ("failed", result.reason)
    assert any("Traceback" in line and "the download fell over" in line for line in lines)
    assert "download: Something went wrong in the download stage: the download fell over" in lines
    assert not (tmp_path / "lessons").exists()


def test_an_answer_from_meta_missing_a_part_is_said_plainly_not_as_its_name(saved, make):
    saved._write("writer_vid1_upload", {"response": {"object": "file"}})     # the upload's answer has no "id"

    result, stages, lines, _ = make()

    assert result.reason == "Something unexpected went wrong. Try another video."
    assert stages.last()["write"] == ("failed", result.reason)
    assert "write: Something went wrong in the write stage: 'id'" in lines


@pytest.mark.parametrize("error, said", [
    (SpendLimitReached("Meta spending has reached $100.00 of the $100.00 limit. Tell Ranvir before spending more."),
     "Meta's spending limit has been reached, so no more lessons can be made for now."),
    (NoKey('META_API_KEY is not set. Save it in PowerShell with '
           '[Environment]::SetEnvironmentVariable("META_API_KEY", "<your key>", "User")'),
     "Meta's key is missing or was not accepted. Add your Meta key, then try again."),
    (VideoRefused("The video could not be downloaded. Try another video.",
                  detail="ERROR: [youtube] vid1: HTTP Error 403: Forbidden"),
     "The video could not be downloaded. Try another video."),
])
def test_trouble_is_said_plainly_on_screen_and_in_full_in_the_log(clip, make, error, said):
    result, stages, lines, _ = make(fetch=FakeFetch(clip, error=error))

    assert result.reason == said
    assert stages.last()["download"] == ("failed", said)
    assert f"download: {getattr(error, 'detail', '') or error}" in lines


def test_meta_being_busy_is_said_plainly_and_its_answer_kept_in_the_log(saved, make):
    saved.error("writer_vid1_upload", type="unavailable", message="Meta is busy right now (503: upstream reset)")

    result, stages, lines, _ = make()

    assert result.reason == "Meta could not be reached or was busy. Try again in a few minutes."
    assert stages.last()["write"] == ("failed", result.reason)
    assert "write: Meta is busy right now (503: upstream reset)" in lines


def test_meta_refusing_the_video_and_its_frames_is_said_plainly(saved, make):
    saved.error("writer_vid1_upload", type="refused", status=400, message="video input is not supported")
    saved.error("writer_vid1_frames", type="refused", status=400, message="too many images")

    result, stages, lines, _ = make()

    assert result.reason == "Meta would not take this video, so the lesson could not be written. Try another video."
    assert stages.last()["write"] == ("failed", result.reason)
    assert "write: Meta refused the request (400): too many images" in lines


def test_a_lesson_that_broke_the_rules_is_said_plainly_with_the_rules_in_the_log(saved, make):
    bad = _lesson([_step(1, hints=["one"]), _step(2), _step(3)])
    _written(saved, lesson=bad)
    saved.answer("writer_vid1_retry", bad)

    result, stages, lines, _ = make()

    assert result.reason == BROKE_RULES
    assert stages.last()["write"] == ("failed", BROKE_RULES)
    assert "write: Muse Spark's lesson broke the rules: step s1: it has 1 hints; it needs exactly 3." in lines


def test_something_unexpected_in_the_test_keeps_the_proven_lesson_and_is_logged(tmp_path, saved, make):
    _written(saved)

    result, stages, lines, _ = make(tester=FakeTester(RuntimeError("the tester fell over")))

    assert shelf_badge(result.lesson) == "proven"
    assert stages.last()["test"] == ("done", "The test could not run. The lesson goes on the shelf with the proven "
                                             "badge.")
    assert any("Traceback" in line and "the tester fell over" in line for line in lines)
    folder = (tmp_path / "lessons" / "fill-in-the-keys").as_posix()
    assert ("test: Something unexpected went wrong (the tester fell over). Test it later with: python -m app.factory "
            f"test {folder}") in lines


def test_one_pair_of_hands_plays_both_tests(tmp_path, monkeypatch):
    made, played = [], []

    class Hands:
        def __init__(self):
            made.append(self)

    def play(lesson, plugin, workdir, client, *, runs, mode, hands, on_line, on_progress):
        played.append(hands)
        return outcome(0, mode=mode)

    monkeypatch.setattr(tester_module, "WindowsHands", Hands)
    monkeypatch.setattr(tester_module, "test_lesson", play)

    run_test(build_fake_lesson({}, [{}, {}, {}]), FakePlugin(), tmp_path, None, say=lambda line: None)

    assert len(made) == 1 and played == [made[0], made[0]]    # so a person moving the mouse in between is seen


class CodeApp(FakePlugin):
    app_id, title = "vscode", "VS Code"


class NewApp(FakePlugin):
    app_id, title = "paint", "Paint"


@pytest.mark.parametrize("plugin, why", [
    (CodeApp(), "its steps write and run code, and code taken from a video must not run on this computer"),
    (NewApp(), "nobody has checked yet that its lessons are safe to make from a video"),
])
def test_lessons_are_made_from_videos_only_for_apps_checked_for_it(tmp_path, clip, make, plugin, why):
    fetch = FakeFetch(clip)

    result, stages, lines, tester = make(fetch=fetch, plugin=plugin)

    assert result.lesson is None
    assert result.reason == f"Lessons for {plugin.title} are not made from videos: {why}."
    assert "download: Write one by hand and prove it with: python -m app.factory prove <lesson folder>" in lines
    assert stages.last()["download"] == ("failed", result.reason)
    assert stages.last()["read"] == ("waiting", "")
    assert fetch.calls == [] and tester.calls == []
    assert not (tmp_path / "recordings").exists()


def test_a_name_taken_while_the_lesson_was_made_gets_a_new_folder(tmp_path, saved, make):
    _written(saved)
    other = tmp_path / "lessons" / "fill-in-the-keys"
    tester = FakeTester(outcome(5), during=lambda: other.mkdir(parents=True))   # someone else's lesson lands first

    result, _, _, _ = make(tester=tester)

    assert result.lesson.id == "fill-in-the-keys-2"
    assert load_lesson(tmp_path / "lessons" / "fill-in-the-keys-2").id == "fill-in-the-keys-2"
    assert list(other.iterdir()) == []                                   # the other lesson is left alone


def test_without_a_clip_on_the_last_step_the_goal_picture_is_the_last_still_frame(tmp_path, saved, make):
    _written(saved, lesson=_lesson([_step(1), _step(2), _step(3, clip=None)]))

    result, _, _, _ = make()

    frames = sorted((tmp_path / "recordings" / "vid1" / "frames").glob("frame_*.png"))
    assert (result.lesson.folder / "goal.png").read_bytes() == frames[-1].read_bytes()


class NoCaptions(FakeFetch):
    """A video with no captions: Claude cannot listen to the sound, so there is no transcript."""

    def __call__(self, url, dest):
        fetched = super().__call__(url, dest)
        return Fetched(fetched.info, fetched.video, None)


def test_claude_makes_a_lesson_from_the_still_frames_and_the_screen_names_claude(tmp_path, clip):
    import json

    from app.claude.client import ClaudeClient
    from tests.claude.test_client import FakeApi, _reply, _text

    api = FakeApi(_reply(_text(json.dumps(_lesson()))))
    client = ClaudeClient(api=api, log_path=tmp_path / "claude_calls.jsonl")
    lines, stages, tester = [], Stages(), FakeTester()
    factory = LessonFactory(client, tmp_path / "lessons", tmp_path / "recordings", fetch=NoCaptions(clip),
                            tester=tester, hands_off_s=0, test=False, on_line=lines.append)

    result = factory.make(URL, FakePlugin(), stages)

    assert result.reason == "" and shelf_badge(result.lesson) == "proven" and tester.calls == []
    [request] = api.sent
    assert len([b for b in request["messages"][0]["content"] if b["type"] == "image"]) == 3
    assert stages.last()["read"] == ("done", "3 still frames, no transcript (no captions or speech)")
    assert stages.last()["test"] == ("done", "Not tested: only Meta's agent tests lessons, and Claude wrote this "
                                             "one, so it goes on the shelf with the proven badge")


def test_claude_trouble_names_claude_on_screen(tmp_path, clip):
    from app.claude.client import ClaudeClient
    from tests.claude.test_client import FakeApi

    client = ClaudeClient(api=FakeApi(NoKey("Claude did not accept the key")), log_path=tmp_path / "c.jsonl")
    stages = Stages()
    factory = LessonFactory(client, tmp_path / "lessons", tmp_path / "recordings", fetch=FakeFetch(clip),
                            hands_off_s=0, test=False)

    result = factory.make(URL, FakePlugin(), stages)

    assert result.reason == "Claude's key is missing or was not accepted. Add your Claude key, then try again."
