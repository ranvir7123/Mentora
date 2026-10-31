"""The lesson factory from the command line.

    python -m app.factory make <video link> [--app excel] [--no-test] [--runs 5]
    python -m app.factory prove <lesson folder> [--no-test]
    python -m app.factory test <lesson folder> [--runs 5]

`make` runs the whole factory and prints each stage as it happens. `prove` proves a lesson in the real app
again (a hand-made one, say) and saves the proof only when every step passed; with `--no-test` it also
records the agent's test as skipped, as `make --no-test` does, so the lesson shows the proven badge. `test`
plays a proven lesson with Meta's agent as the learner. The test moves the real mouse, so leave the computer
alone while it runs: moving the mouse stops it.
"""
from __future__ import annotations

import argparse
import importlib
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from app.core.lesson import Lesson, LessonError, load_lesson, save_lesson
from app.core.plugin import AppPlugin
from app.factory.input import UserTookOver
from app.factory.pipeline import HANDS_OFF_S, LessonFactory, exact_words, not_tested, run_test
from app.factory.prove import ProveError, prove
from app.factory.tester import agent_refusal
from app.factory.video import VideoError
from app.meta.client import MetaClient, MetaError

# Where each app's plug-in lives, as "module:class". The fake app is for trying the factory without one.
PLUGINS = {"excel": "app.excel.plugin:ExcelPlugin", "vscode": "app.vscode.plugin:VsCodePlugin",
           "fake": "app.core.fake_plugin:FakePlugin"}


class _Refused(Exception):
    """The command stops here; the message says why in plain words."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.run(args)
    except _Refused as stop:
        print(stop, file=sys.stderr)
        return stop.code
    except (ProveError, MetaError, VideoError) as exc:
        print(exact_words(exc), file=sys.stderr)
        return 1


def plugin_for(app: str) -> AppPlugin:
    where = PLUGINS.get(app)
    if where is None:
        raise _Refused(f"There is no plug-in for {app}. Pick one of: {', '.join(sorted(PLUGINS))}.", 2)
    module, name = where.split(":")
    try:
        return getattr(importlib.import_module(module), name)()
    except ModuleNotFoundError as exc:
        if exc.name and (module == exc.name or module.startswith(exc.name + ".")):
            raise _Refused(f"The {app} plug-in is not on this copy of Mentora ({module} is missing).", 2) from None
        raise _Refused(f"The {app} plug-in could not load: {exc}", 2) from None


# The commands.

def _make(args: argparse.Namespace) -> int:
    plugin = plugin_for(args.app)
    factory = LessonFactory(MetaClient(), Path("lessons"), Path("recordings"), test=not args.no_test,
                            runs=args.runs, on_line=_say)
    result = factory.make(args.url, plugin, lambda name, state, detail: None)     # the log says it all
    if result.lesson is None:
        print(f"No lesson was made: {result.reason}", file=sys.stderr)
        return 1
    return 0


def _prove(args: argparse.Namespace) -> int:
    lesson = _load(args.folder)
    plugin = plugin_for(lesson.app)
    _say(f'Proving "{lesson.title}" in {plugin.title}: {len(lesson.steps)} steps')
    with tempfile.TemporaryDirectory(prefix="prove-", ignore_cleanup_errors=True) as work:
        proved = prove(lesson, plugin, Path(work))
    for note in proved.notes:
        _say(f"  {note}")
    kept = len(proved.lesson.steps)
    if not proved.lesson.proof.passed or proved.dropped:       # never save a lesson with its steps taken out
        raise _Refused(f"Not saved: {kept} of {kept + len(proved.dropped)} steps could be proven, and every step "
                       "must pass. Fix the lesson and prove it again.")
    proven = replace(proved.lesson, test=not_tested()) if args.no_test else proved.lesson
    save_lesson(proven)
    _say(f"Proven: all {kept} steps passed. The proof is saved in {proven.folder / 'lesson.json'}")
    if args.no_test:
        _say("The test with Meta's agent was skipped, so the lesson shows the proven badge.")
    return 0


def _test(args: argparse.Namespace) -> int:
    lesson = _load(args.folder)
    if lesson.proof is None or not lesson.proof.passed:
        raise _Refused(f'"{lesson.title}" is not proven yet, so it cannot be tested: prove it first with: '
                       f"python -m app.factory prove {Path(args.folder).as_posix()}")
    plugin = plugin_for(lesson.app)
    refusal = agent_refusal(plugin)
    if refusal:
        save_lesson(replace(lesson, test=not_tested()))     # the shelf needs a test result; this one says "proven"
        raise _Refused(f"{refusal} The lesson keeps its proven badge.")
    _say(f"Hands off the mouse and keyboard: Meta's agent takes over in {HANDS_OFF_S:g} s. "
         "Moving the mouse stops the test.")
    time.sleep(HANDS_OFF_S)
    with tempfile.TemporaryDirectory(prefix="test-", ignore_cleanup_errors=True) as work:
        try:
            tested = run_test(lesson, plugin, Path(work), MetaClient(), say=_say, runs=args.runs)
        except UserTookOver as exc:
            raise _Refused(f"{exc} Nothing was saved.") from None
        except (ProveError, MetaError, OSError) as exc:
            raise _Refused(f"The test could not run: {exact_words(exc).rstrip('.')}. Nothing was saved.") from None
    save_lesson(replace(lesson, test=tested.result))
    _say(tested.detail)
    _say(f"Saved in {lesson.folder / 'lesson.json'}")
    return 0 if tested.result.passed else 1


# Reading the command.

def _load(folder: str) -> Lesson:
    try:
        return load_lesson(Path(folder))
    except LessonError as exc:
        raise _Refused(str(exc)) from None


def _runs(text: str) -> int:
    try:
        n = int(text)
    except ValueError:
        n = 0
    if n < 1:
        raise argparse.ArgumentTypeError(f"--runs needs a whole number of 1 or more, not {text!r}")
    return n


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.factory", description="Make, prove and test lessons.")
    commands = parser.add_subparsers(dest="command", required=True)

    make = commands.add_parser("make", help="make a lesson from a tutorial video link")
    make.add_argument("url", help="the video's link")
    make.add_argument("--app", default="excel", help="the app the tutorial is about (default: excel)")
    make.add_argument("--no-test", action="store_true",
                      help="skip the test with Meta's agent; the lesson gets the proven badge")
    make.add_argument("--runs", type=_runs, default=5, help="test runs; 4 in 5 must pass (default: 5)")
    make.set_defaults(run=_make)

    prove_it = commands.add_parser("prove", help="prove a lesson in the real app again")
    prove_it.add_argument("folder", help="the lesson's folder, such as lessons/monthly-budget")
    prove_it.add_argument("--no-test", action="store_true",
                          help="record the test with Meta's agent as skipped; the lesson gets the proven badge")
    prove_it.set_defaults(run=_prove)

    test_it = commands.add_parser("test", help="test a proven lesson with Meta's agent as the learner")
    test_it.add_argument("folder", help="the lesson's folder, such as lessons/monthly-budget")
    test_it.add_argument("--runs", type=_runs, default=5, help="test runs; 4 in 5 must pass (default: 5)")
    test_it.set_defaults(run=_test)
    return parser


def _say(line: str) -> None:
    print(line, flush=True)


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")        # a title the console cannot show must not stop the run
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
