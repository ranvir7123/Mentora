from dataclasses import replace

from app.core.fake_plugin import FakePlugin
from app.core.lesson import Proof, TestResult, load_lesson, save_lesson
from app.core.services import MakeResult
from app.factory import __main__ as cli
from app.factory import tester
from app.factory.__main__ import main
from app.factory.input import UserTookOver
from tests.core.conftest import build_fake_lesson

AT = "2026-10-29T12:00:00+00:00"


def _saved(tmp_path, steps=({}, {}, {}), **over):
    """A fake-app lesson saved in its own folder, the way a hand-made lesson sits in lessons/."""
    lesson = replace(build_fake_lesson({}, list(steps)), folder=tmp_path / "fake", **over)
    save_lesson(lesson)
    return lesson.folder


def test_prove_saves_the_proof_when_every_step_passes(tmp_path, capsys):
    folder = _saved(tmp_path)

    assert main(["prove", str(folder)]) == 0

    assert load_lesson(folder).proof.passed is True
    assert f"Proven: all 3 steps passed. The proof is saved in {folder / 'lesson.json'}" in capsys.readouterr().out


def test_prove_saves_nothing_when_a_step_is_dropped(tmp_path, capsys):
    # s1's check is already true before it (s0 sets k0), so it is dropped; three steps would still be enough.
    folder = _saved(tmp_path, ({}, {"check": {"kind": "has", "args": {"key": "k0"}}}, {}, {}))
    before = (folder / "lesson.json").read_text(encoding="utf-8")

    assert main(["prove", str(folder)]) == 1

    assert (folder / "lesson.json").read_text(encoding="utf-8") == before      # the hand-made step is kept
    out = capsys.readouterr()
    assert "step s1 was dropped: its check was already true before the step" in out.out
    assert ("Not saved: 3 of 4 steps could be proven, and every step must pass. Fix the lesson and prove it "
            "again.") in out.err


def test_an_app_with_no_plugin_is_refused_plainly(capsys):
    assert main(["make", "https://youtu.be/vid1", "--app", "word"]) == 2
    assert "There is no plug-in for word. Pick one of: excel, fake, vscode." in capsys.readouterr().err


def test_a_plugin_missing_from_this_copy_is_named(tmp_path, monkeypatch, capsys):
    monkeypatch.setitem(cli.PLUGINS, "ghost", "app.ghost.plugin:GhostPlugin")
    folder = _saved(tmp_path, app="ghost")

    assert main(["prove", str(folder)]) == 2
    assert ("The ghost plug-in is not on this copy of Project X (app.ghost.plugin is missing)."
            in capsys.readouterr().err)


def test_make_runs_the_factory_with_the_choices_given(monkeypatch, capsys):
    made = []

    class SpyFactory:
        def __init__(self, client, lessons_dir, recordings, **kwargs):
            made.append(kwargs)

        def make(self, url, plugin, on_stage):
            made.append((url, type(plugin)))
            return MakeResult(None, "That is a live stream. Pick a finished video.")

    monkeypatch.setattr(cli, "LessonFactory", SpyFactory)

    assert main(["make", "https://youtu.be/vid1", "--app", "fake", "--no-test", "--runs", "3"]) == 1

    assert made[0]["test"] is False and made[0]["runs"] == 3
    assert made[1] == ("https://youtu.be/vid1", FakePlugin)
    assert "No lesson was made: That is a live stream. Pick a finished video." in capsys.readouterr().err


def test_testing_a_lesson_that_is_not_proven_is_refused(tmp_path, capsys):
    folder = _saved(tmp_path)

    assert main(["test", str(folder)]) == 1
    assert "prove it first with: python -m app.factory prove" in capsys.readouterr().err


def test_a_test_that_reaches_a_verdict_is_saved(tmp_path, monkeypatch, capsys):
    folder = _saved(tmp_path, proof=Proof(True, AT, (), ()))
    monkeypatch.setattr(cli, "HANDS_OFF_S", 0)
    calls = []

    def passes(lesson, plugin, workdir, client, *, runs, mode, hands, on_line):
        calls.append((runs, mode))
        on_line("run 1 passed")
        return TestResult(True, AT, mode, runs, runs)

    monkeypatch.setattr(tester, "test_lesson", passes)

    assert main(["test", str(folder), "--runs", "3"]) == 0

    assert calls == [(3, "mouse")]
    assert load_lesson(folder).test == TestResult(True, AT, "mouse", 3, 3)
    out = capsys.readouterr().out
    assert "Hands off the mouse and keyboard" in out
    assert "Mouse test: run 1 passed" in out and "3 of 3 test runs passed" in out


def test_a_test_stopped_by_a_person_saves_nothing(tmp_path, monkeypatch, capsys):
    folder = _saved(tmp_path, proof=Proof(True, AT, (), ()))
    monkeypatch.setattr(cli, "HANDS_OFF_S", 0)

    def stopped(*args, **kwargs):
        raise UserTookOver("You moved the mouse, so the test stopped.")

    monkeypatch.setattr(tester, "test_lesson", stopped)

    assert main(["test", str(folder)]) == 1

    assert load_lesson(folder).test is None
    assert "You moved the mouse, so the test stopped. Nothing was saved." in capsys.readouterr().err
