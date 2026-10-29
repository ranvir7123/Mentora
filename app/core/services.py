"""The two services the app asks for help: the lesson maker and the coach.

The lesson maker turns a tutorial link into a lesson; the coach writes tips and answers questions.
Both may be slow (they call Meta's models), so callers run them off the screen's thread.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Protocol

from app.core.lesson import Lesson
from app.core.plugin import AppPlugin
from app.core.runner import StepRecord


@dataclass(frozen=True)
class MakeResult:
    lesson: Lesson | None        # None when no lesson was good enough to publish
    reason: str                  # why not, in plain words; empty when a lesson was made


class LessonMaker(Protocol):
    def make(self, url: str, plugin: AppPlugin,
             on_stage: Callable[[str, str, str], None]) -> MakeResult:
        """`on_stage(name, state, detail)` uses the FactoryStage names and states in app/core/screen.py."""


class Coach(Protocol):
    def tips(self, log: list[StepRecord]) -> str: ...
    def answer(self, question: str, context: Mapping) -> str: ...
