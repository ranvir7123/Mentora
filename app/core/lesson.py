"""One lesson, as one JSON file in its own folder.

A lesson holds where it came from (the tutorial video), the goal, the app's starting data and the steps.
Each step has an instruction, a target to point at, a fixed check that says when it is done, the
operation that does it (used to prove the check), three hints and predicted mistakes. A lesson also
records whether its proof and its test passed; only lessons with both reach the shelf.

`lesson_from_dict` checks the file's shape and names the first missing or wrong field. `validate` checks
the rules a learner would notice (instruction length, banned words, three hints) and, given a plug-in,
that every check and operation is on that app's menu.
"""
from __future__ import annotations

import copy
import json
import math
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Mapping

from app.core.types import Call, Target, validate_args

if TYPE_CHECKING:
    from app.core.plugin import AppPlugin

FORMAT = 1
MAX_WORDS = 12
BANNED = re.compile(r"\b(simply|just)\b", re.IGNORECASE)


class LessonError(ValueError):
    """The lesson file is missing a field or has one of the wrong kind; the message names it."""


@dataclass(frozen=True)
class Source:
    url: str
    title: str
    creator: str
    channel_url: str
    licence: str
    length_s: int


@dataclass(frozen=True)
class Goal:
    sentence: str
    picture: str | None          # relative to the lesson folder


@dataclass(frozen=True)
class Mistake:
    replay: Call
    not_yet: str
    code: str = ""               # the check's verdict code, filled in by the mistake hunter


@dataclass(frozen=True)
class Clip:
    start: float
    end: float


@dataclass(frozen=True)
class Step:
    id: str
    instruction: str
    why: str
    target: Target
    check: Call
    replay: Call
    hints: tuple[str, ...]
    mistakes: tuple[Mistake, ...]
    clip: Clip | None


@dataclass(frozen=True)
class Proof:
    passed: bool
    at: str
    dropped: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class TestResult:
    __test__ = False             # not a pytest test class

    passed: bool
    at: str
    mode: Literal["mouse", "keyboard", "skipped"]
    runs: int
    passes: int


@dataclass(frozen=True)
class Lesson:
    format: int
    id: str
    title: str
    app: str
    course: str
    source: Source | None
    goal: Goal
    starter: Mapping[str, Any]
    steps: tuple[Step, ...]
    made_by: Literal["hand", "generated"]
    edited_by_hand: bool
    proof: Proof | None
    test: TestResult | None
    folder: Path | None = field(default=None, compare=False)


# Reading a lesson from plain data. `where` is the path so far, such as "steps[2].check.".

def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _typed(d: Mapping, key: str, where: str, fits, what: str, *, nullable: bool = False) -> Any:
    if key not in d and not nullable:
        raise LessonError(f"{where}{key} is missing")
    value = d.get(key)
    if value is None and nullable:
        return None
    if not fits(value):
        raise LessonError(f"{where}{key} should be {what}")
    return value


def _text(d: Mapping, key: str, where: str, *, nullable: bool = False) -> str | None:
    return _typed(d, key, where, lambda v: isinstance(v, str), "text", nullable=nullable)


def _number(d: Mapping, key: str, where: str) -> float:
    return _typed(d, key, where, _is_number, "a number")


def _whole(d: Mapping, key: str, where: str) -> int:
    return _typed(d, key, where, lambda v: isinstance(v, int) and not isinstance(v, bool), "a whole number")


def _flag(d: Mapping, key: str, where: str) -> bool:
    return _typed(d, key, where, lambda v: isinstance(v, bool), "true or false")


def _choice(d: Mapping, key: str, where: str, choices: tuple[str, ...]) -> str:
    return _typed(d, key, where, lambda v: v in choices, f"one of {', '.join(choices)}")


def _object(d: Mapping, key: str, where: str, *, nullable: bool = False) -> Mapping | None:
    return _typed(d, key, where, lambda v: isinstance(v, Mapping), "an object", nullable=nullable)


def _texts(d: Mapping, key: str, where: str) -> tuple[str, ...]:
    items = _typed(d, key, where, lambda v: isinstance(v, list), "a list")
    for i, item in enumerate(items):
        if not isinstance(item, str):
            raise LessonError(f"{where}{key}[{i}] should be text")
    return tuple(items)


def _objects(d: Mapping, key: str, where: str) -> list[tuple[Mapping, str]]:
    items = _typed(d, key, where, lambda v: isinstance(v, list), "a list")
    for i, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise LessonError(f"{where}{key}[{i}] should be an object")
    return [(item, f"{where}{key}[{i}].") for i, item in enumerate(items)]


def _call(d: Mapping, key: str, where: str) -> Call:
    c = _object(d, key, where)
    w = f"{where}{key}."
    return Call(_text(c, "kind", w), copy.deepcopy(dict(_object(c, "args", w))))


def _step(d: Mapping, where: str) -> Step:
    target = _object(d, "target", where)
    mistakes = tuple(
        Mistake(_call(m, "replay", w), _text(m, "not_yet", w), _text(m, "code", w, nullable=True) or "")
        for m, w in _objects(d, "mistakes", where))
    clip = _object(d, "clip", where, nullable=True)
    return Step(
        id=_text(d, "id", where),
        instruction=_text(d, "instruction", where),
        why=_text(d, "why", where),
        target=Target(_text(target, "kind", f"{where}target."), _text(target, "ref", f"{where}target.")),
        check=_call(d, "check", where),
        replay=_call(d, "replay", where),
        hints=_texts(d, "hints", where),
        mistakes=mistakes,
        clip=None if clip is None else Clip(_number(clip, "start", f"{where}clip."),
                                            _number(clip, "end", f"{where}clip.")))


def lesson_from_dict(d: Mapping, folder: Path | None = None) -> Lesson:
    if not isinstance(d, Mapping):
        raise LessonError("the lesson should be an object")
    fmt = _whole(d, "format", "")
    if fmt != FORMAT:
        raise LessonError(f"format {fmt} is not one this program reads (it reads {FORMAT})")
    source = _object(d, "source", "", nullable=True)
    goal = _object(d, "goal", "")
    proof = _object(d, "proof", "", nullable=True)
    test = _object(d, "test", "", nullable=True)
    return Lesson(
        format=fmt,
        id=_text(d, "id", ""),
        title=_text(d, "title", ""),
        app=_text(d, "app", ""),
        course=_text(d, "course", ""),
        source=None if source is None else Source(
            _text(source, "url", "source."), _text(source, "title", "source."),
            _text(source, "creator", "source."), _text(source, "channel_url", "source."),
            _text(source, "licence", "source."), _whole(source, "length_s", "source.")),
        goal=Goal(_text(goal, "sentence", "goal."), _text(goal, "picture", "goal.", nullable=True)),
        starter=copy.deepcopy(dict(_object(d, "starter", ""))),
        steps=tuple(_step(s, w) for s, w in _objects(d, "steps", "")),
        made_by=_choice(d, "made_by", "", ("hand", "generated")),
        edited_by_hand=_flag(d, "edited_by_hand", ""),
        proof=None if proof is None else Proof(
            _flag(proof, "passed", "proof."), _text(proof, "at", "proof."),
            _texts(proof, "dropped", "proof."), _texts(proof, "notes", "proof.")),
        test=None if test is None else TestResult(
            _flag(test, "passed", "test."), _text(test, "at", "test."),
            _choice(test, "mode", "test.", ("mouse", "keyboard", "skipped")),
            _whole(test, "runs", "test."), _whole(test, "passes", "test.")),
        folder=folder)


# Writing a lesson back out, keys in the file's order.

def _call_dict(c: Call) -> dict:
    return {"kind": c.kind, "args": copy.deepcopy(dict(c.args))}


def _step_dict(s: Step) -> dict:
    return {
        "id": s.id, "instruction": s.instruction, "why": s.why,
        "target": {"kind": s.target.kind, "ref": s.target.ref},
        "check": _call_dict(s.check), "replay": _call_dict(s.replay),
        "hints": list(s.hints),
        "mistakes": [{"replay": _call_dict(m.replay), "not_yet": m.not_yet, "code": m.code} for m in s.mistakes],
        "clip": None if s.clip is None else {"start": s.clip.start, "end": s.clip.end},
    }


def lesson_to_dict(lesson: Lesson) -> dict:
    s, p, t = lesson.source, lesson.proof, lesson.test
    return {
        "format": lesson.format, "id": lesson.id, "title": lesson.title, "app": lesson.app,
        "course": lesson.course,
        "source": None if s is None else {
            "url": s.url, "title": s.title, "creator": s.creator, "channel_url": s.channel_url,
            "licence": s.licence, "length_s": s.length_s},
        "goal": {"sentence": lesson.goal.sentence, "picture": lesson.goal.picture},
        "starter": copy.deepcopy(dict(lesson.starter)),
        "steps": [_step_dict(step) for step in lesson.steps],
        "made_by": lesson.made_by, "edited_by_hand": lesson.edited_by_hand,
        "proof": None if p is None else {
            "passed": p.passed, "at": p.at, "dropped": list(p.dropped), "notes": list(p.notes)},
        "test": None if t is None else {
            "passed": t.passed, "at": t.at, "mode": t.mode, "runs": t.runs, "passes": t.passes},
    }


def load_lesson(folder: Path) -> Lesson:
    path = Path(folder) / "lesson.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise LessonError(f"{path} is missing") from None
    except json.JSONDecodeError as e:
        raise LessonError(f"{path} is not valid JSON (line {e.lineno}: {e.msg})") from None
    except (OSError, UnicodeDecodeError) as e:
        raise LessonError(f"{path} could not be read ({e})") from None
    return lesson_from_dict(data, Path(folder))


def save_lesson(lesson: Lesson) -> None:
    """Write `lesson.json` in the lesson's folder; a half-written file never replaces a good one."""
    if lesson.folder is None:
        raise LessonError("the lesson has no folder to be saved in")
    lesson.folder.mkdir(parents=True, exist_ok=True)
    path = lesson.folder / "lesson.json"
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(lesson_to_dict(lesson), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp, path)


# The rules.

def _call_problems(call: Call, menu: Mapping, at: str, title: str) -> list[str]:
    kind = menu.get(call.kind)
    if kind is None:
        return [f"{at} {call.kind} is not on the {title} menu"]
    return [f"{at} {p}" for p in validate_args(kind, call.args)]


def validate(lesson: Lesson, plugin: AppPlugin | None = None) -> list[str]:
    """Every rule the lesson breaks, in plain words, each naming its step."""
    problems = []
    if not lesson.steps:
        problems.append("the lesson has no steps")
    seen = set()
    for step in lesson.steps:
        at = f"step {step.id}"
        if step.id in seen:
            problems.append(f"{at}: an earlier step already uses this id")
        seen.add(step.id)
        words = len(step.instruction.split())
        if words > MAX_WORDS:
            problems.append(f"{at}: the instruction has {words} words; keep it to {MAX_WORDS}")
        if len(step.hints) != 3:
            problems.append(f"{at}: it has {len(step.hints)} hints; it needs exactly 3")
        texts = [("the instruction", step.instruction), ("the why line", step.why)]
        texts += [(f"hint {i}", h) for i, h in enumerate(step.hints, 1)]
        texts += [(f"mistake {i}'s Not yet line", m.not_yet) for i, m in enumerate(step.mistakes, 1)]
        for name, text in texts:
            found = BANNED.search(text)
            if found:
                problems.append(f'{at}: {name} says "{found.group(0)}"; leave it out')
        if step.clip is not None and step.clip.end <= step.clip.start:
            problems.append(f"{at}: the clip ends at {step.clip.end} s, not after its start at {step.clip.start} s")
        if plugin is not None:
            if step.target.kind not in plugin.target_kinds:
                problems.append(f"{at}: {plugin.title} cannot point at a {step.target.kind}")
            problems += _call_problems(step.check, plugin.checks, f"{at}: check", plugin.title)
            problems += _call_problems(step.replay, plugin.ops, f"{at}: replay", plugin.title)
            for i, m in enumerate(step.mistakes, 1):
                problems += _call_problems(m.replay, plugin.ops, f"{at}: mistake {i}", plugin.title)
    if plugin is not None:
        problems += plugin.validate_starter(lesson.starter)
    return problems


def shelf_badge(lesson: Lesson) -> Literal["proven and tested", "proven"] | None:
    """The badge a lesson shows on the shelf, or None when it is not ready for learners."""
    if lesson.proof is None or not lesson.proof.passed or lesson.test is None:
        return None
    if lesson.test.mode == "skipped":
        return "proven"
    return "proven and tested" if lesson.test.passed else None


def edited(lesson: Lesson, **changes: Any) -> Lesson:
    """A copy with these changes, marked as edited by hand; its proof and test must run again."""
    return replace(lesson, **changes, edited_by_hand=True, proof=None, test=None)


# The form Muse Spark fills in when it writes a lesson from a video.

_ARG_SCHEMA = {
    "cell": {"type": "string"}, "range": {"type": "string"},
    "cells": {"type": "array", "items": {"type": "string"}},
    "text": {"type": "string"}, "number": {"type": "number"}, "value": {"type": ["number", "string"]},
    "int": {"type": "integer"}, "bool": {"type": "boolean"}, "function": {"type": "string"},
    "path": {"type": "string"},
}


def _args_schema(menu: Mapping) -> dict:
    """Every argument any kind on the menu takes; `validate` checks which belong to which kind."""
    props: dict[str, dict] = {}
    for kind in menu.values():
        for p in kind.params:
            s = ({"type": "string", "enum": list(p.choices)} if p.type == "enum" else dict(_ARG_SCHEMA[p.type]))
            have = props.get(p.name)
            if have is None:
                props[p.name] = s
            elif have != s:
                options = have["anyOf"] if "anyOf" in have else [have]
                props[p.name] = {"anyOf": options + ([s] if s not in options else [])}
    return {"type": "object", "properties": props, "additionalProperties": False}


def _call_schema(menu: Mapping) -> dict:
    return {"type": "object",
            "properties": {"kind": {"type": "string", "enum": list(menu)}, "args": _args_schema(menu)},
            "required": ["kind", "args"], "additionalProperties": False}


def lesson_json_schema(plugin: AppPlugin) -> dict:
    """JSON Schema (draft 2020-12) for the parts of a lesson Muse Spark writes.

    Check, operation and target kinds are limited to the plug-in's menus. `starter` is the one open
    object: its shape belongs to the plug-in, and `plugin.validate_starter` checks it afterwards.
    """
    text = {"type": "string"}
    step = {
        "type": "object",
        "properties": {
            "id": text, "instruction": text, "why": text,
            "target": {"type": "object",
                       "properties": {"kind": {"type": "string", "enum": sorted(plugin.target_kinds)}, "ref": text},
                       "required": ["kind", "ref"], "additionalProperties": False},
            "check": _call_schema(plugin.checks),
            "replay": _call_schema(plugin.ops),
            "hints": {"type": "array", "items": text, "minItems": 3, "maxItems": 3},
            "mistakes": {"type": "array", "items": {
                "type": "object", "properties": {"replay": _call_schema(plugin.ops), "not_yet": text},
                "required": ["replay", "not_yet"], "additionalProperties": False}},
            "clip": {"type": ["object", "null"],
                     "properties": {"start": {"type": "number"}, "end": {"type": "number"}},
                     "required": ["start", "end"], "additionalProperties": False},
        },
        "required": ["id", "instruction", "why", "target", "check", "replay", "hints", "mistakes", "clip"],
        "additionalProperties": False,
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"A {plugin.title} lesson",
        "type": "object",
        "properties": {
            "title": text,
            "goal": {"type": "object", "properties": {"sentence": text}, "required": ["sentence"],
                     "additionalProperties": False},
            "starter": {"type": "object"},
            "steps": {"type": "array", "items": step, "minItems": 1},
        },
        "required": ["title", "goal", "starter", "steps"],
        "additionalProperties": False,
    }
