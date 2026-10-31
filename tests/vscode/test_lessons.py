"""The two VS Code lessons: they load and follow every rule, and they walk through the way the prover
walks them in VS Code. Each step's check is false before its step, each predicted mistake gets a Not yet
of its own, the step's replay makes the check true, and every step is still ticked at the end.

The walk keeps the lesson folder in memory and runs each program with the real Python. The Meta
lesson's program talks to a stand-in for the openai package, so it needs no key and no network; the
stand-in fails the run if the program uses the wrong address, model or key setting."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.lesson import Lesson, load_lesson, validate
from app.core.runner import LessonDone, LessonRun, StepPassed
from app.core.types import Call
from app.vscode.checks import CHECKS, MAX_WORDS
from app.vscode.plugin import VsCodePlugin
from app.vscode.snapshot import VsSnapshot

REPO = Path(__file__).resolve().parents[2]
FIRST = REPO / "lessons" / "vscode-first-program"
META = REPO / "lessons" / "vscode-meta-ai-app"
STAND_IN_KEY = "stand-in"

STAND_IN = '''"""A stand-in for the openai package: checks what the lesson's program asks for, answers offline."""
import os


class _Response:
    output_text = "Write a little, run it, and read what Python tells you."


class _Responses:
    def create(self, *, model, input, **extra):
        assert model == "muse-spark-1.3", f"asked model {model}"
        assert isinstance(input, str) and input.strip(), "asked no question"
        return _Response()


class OpenAI:
    def __init__(self, *, base_url, api_key, **extra):
        assert base_url == "https://api.meta.ai/v1", f"sent to {base_url}"
        assert api_key == os.environ["META_API_KEY"], "the key did not come from META_API_KEY"
        self.responses = _Responses()
'''


class Folder:
    """The lesson folder as the add-on reports it, changed by the lesson's operations."""

    def __init__(self, lesson: Lesson, workdir: Path, stand_in: Path):
        self.files: dict[str, str] = dict(lesson.starter.get("files", {}))
        self.run: dict | None = None
        self._workdir, self._stand_in = workdir, stand_in

    def apply(self, op: Call) -> None:
        args = op.args
        if op.kind == "new_file":
            self.files.setdefault(args["path"], "")
        elif op.kind == "write_file":
            self.files[args["path"]] = args["text"]
        elif op.kind == "append_line":
            old = self.files.get(args["path"], "")
            self.files[args["path"]] = old + ("" if old == "" or old.endswith("\n") else "\n") + args["text"] + "\n"
        elif op.kind == "delete_file":
            self.files.pop(args["path"], None)
        elif op.kind == "clear_terminal":
            self.run = None
        elif op.kind == "run_file":
            self.run = self._run(args["path"], args.get("input"))
        elif op.kind not in ("open_file", "save_file"):
            raise AssertionError(f"the walk has no operation {op.kind}")

    def _run(self, path: str, answers: str | None) -> dict:
        for name, text in self.files.items():
            (self._workdir / name).parent.mkdir(parents=True, exist_ok=True)
            (self._workdir / name).write_text(text, encoding="utf-8")
        env = {**os.environ, "PYTHONPATH": str(self._stand_in), "META_API_KEY": STAND_IN_KEY}
        done = subprocess.run([sys.executable, path], cwd=self._workdir, env=env, capture_output=True, text=True,
                              input=None if answers is None else answers + "\n", timeout=20)
        return {"command": f"python {path}", "exit_code": done.returncode, "output": done.stdout + done.stderr,
                "finished": True}

    def snapshot(self) -> VsSnapshot:
        return VsSnapshot.from_state({"files": {p: {"text": t, "saved": True} for p, t in self.files.items()},
                                      "active": None, "problems": [], "run": self.run})


@pytest.fixture
def walk(tmp_path):
    stand_in = tmp_path / "stand_in"
    (stand_in / "openai").mkdir(parents=True)
    (stand_in / "openai" / "__init__.py").write_text(STAND_IN, encoding="utf-8")
    runs = iter(range(1000))

    def folder_after(lesson: Lesson, steps_done: int) -> Folder:
        workdir = tmp_path / f"run{next(runs)}"
        workdir.mkdir()
        folder = Folder(lesson, workdir, stand_in)
        for step in lesson.steps[:steps_done]:
            folder.apply(step.replay)
        return folder

    def run(lesson: Lesson) -> None:
        for i, step in enumerate(lesson.steps):
            check = CHECKS[step.check.kind]
            assert not check.run(folder_after(lesson, i).snapshot(), step.check.args).ok, \
                f"step {step.id}: its check is already true before the step"
            codes = []
            for j, mistake in enumerate(step.mistakes, 1):
                folder = folder_after(lesson, i)
                folder.apply(mistake.replay)
                verdict = check.run(folder.snapshot(), step.check.args)
                assert not verdict.ok and verdict.attempted, f"step {step.id}: mistake {j} got {verdict}"
                assert mistake.code == verdict.code, \
                    f"step {step.id}: mistake {j} says code {mistake.code!r}, so its line never shows ({verdict.code!r})"
                codes.append(verdict.code)
            assert len(set(codes)) == len(codes), f"step {step.id}: two mistakes get the same Not yet ({codes})"
            after = folder_after(lesson, i + 1).snapshot()
            assert check.run(after, step.check.args).ok, \
                f"step {step.id}: still not true after its replay: {check.run(after, step.check.args)} {after.run}"
        end = folder_after(lesson, len(lesson.steps)).snapshot()
        for step in lesson.steps:
            assert CHECKS[step.check.kind].run(end, step.check.args).ok, f"step {step.id} is undone by a later step"
    return run


@pytest.mark.parametrize("folder", [FIRST, META], ids=["first-program", "meta-ai-app"])
def test_the_lesson_loads_and_follows_every_rule(folder):
    lesson = load_lesson(folder)
    assert validate(lesson, VsCodePlugin()) == []
    assert lesson.app == "vscode" and lesson.made_by == "hand" and lesson.id == folder.name
    assert len(lesson.steps) == 6
    for step in lesson.steps:
        expected = (0,) if step.replay.kind == "run_file" else (1, 2)
        assert len(step.mistakes) in expected, step.id
        for mistake in step.mistakes:
            assert mistake.not_yet.startswith("Not yet: ") and len(mistake.not_yet.split()) <= MAX_WORDS, \
                f"step {step.id}: {mistake.not_yet!r}"
        if step.replay.kind in ("write_file", "append_line"):
            # Checks read the saved file, and VS Code does not save by itself, so each typing step says so.
            assert "save" in step.instruction.lower(), f"step {step.id}: {step.instruction!r} never says to save"


def test_your_first_program_walks_through_like_the_prover(walk):
    walk(load_lesson(FIRST))


def test_the_first_program_asks_a_name_and_greets_it(walk):
    lesson = load_lesson(FIRST)
    run = lesson.steps[-1].replay
    assert run == Call("run_file", {"path": "hello.py", "input": "Asha"})
    assert [s.check.kind for s in lesson.steps] == ["file_exists", "calls", "assigns", "prints", "calls", "run_ok"]


def test_a_run_from_before_the_run_step_opened_does_not_tick_it(tmp_path):
    """Running the greet version early, then adding input(), must not tick Run until the learner runs again."""
    lesson = load_lesson(FIRST)
    folder = Folder(lesson, tmp_path, tmp_path)
    for step in lesson.steps[:4]:                   # file, print, name, greet
        folder.apply(step.replay)
    folder.apply(Call("run_file", {"path": "hello.py"}))
    run = LessonRun(lesson, CHECKS, clock=lambda: 0.0)
    assert [e.index for e in run.on_snapshot(folder.snapshot()) if isinstance(e, StepPassed)] == [0, 1, 2, 3]
    folder.apply(lesson.steps[4].replay)            # ask: input() is in, the old run is still the last one
    assert run.on_snapshot(folder.snapshot()) == [StepPassed(4, True, 10)]
    assert run.index == 5 and not run.done
    assert run.on_snapshot(folder.snapshot()) == []         # re-read a second later: still waiting
    folder.apply(lesson.steps[5].replay)            # the learner runs it again
    events = run.on_snapshot(folder.snapshot())
    assert events[0] == StepPassed(5, True, 10) and isinstance(events[1], LessonDone) and run.done


def test_your_first_app_with_meta_s_ai_walks_through_like_the_prover(walk):
    walk(load_lesson(META))


def test_the_meta_lesson_keeps_the_key_out_and_credits_meta():
    lesson = load_lesson(META)
    assert lesson.starter["env"] == ["META_API_KEY"]
    assert lesson.starter["files"]["ask.py"] == ""
    assert "META_API_KEY" in lesson.starter["files"]["README.txt"]
    assert lesson.source is not None and lesson.source.creator == "Meta"
    assert lesson.source.url == "https://dev.meta.ai/docs/quickstart"
    key_step = next(s for s in lesson.steps if s.id == "key")
    assert key_step.check == Call("reads_setting", {"path": "ask.py", "name": "META_API_KEY"})
    assert {m.code for m in key_step.mistakes} == {"key", "quoted:META_API_KEY"}
    assert any(CHECKS[key_step.check.kind].run(_only(m.replay), key_step.check.args).code == "key"
               for m in key_step.mistakes), "pasting a key is a predicted mistake, refused with the key line"
    real_key = os.environ.get("META_API_KEY", "")
    text = (META / "lesson.json").read_text(encoding="utf-8")
    assert not real_key or real_key not in text


def _only(op: Call) -> VsSnapshot:
    return VsSnapshot.from_state({"files": {op.args["path"]: {"text": op.args["text"], "saved": True}},
                                  "active": None, "problems": [], "run": None})
