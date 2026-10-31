"""Muse Spark writes a lesson from a prepared tutorial video.

It is sent the small MP4 (or, when Meta refuses the video, the still frames), the transcript with its
times, the plug-in's menus and the lesson rules, and asked for JSON matching `lesson_json_schema`. The
answer is read and checked with the same rules every lesson keeps; a broken answer goes back once with
its problems listed, and a second broken answer becomes a plain "not ready" reason.

A written lesson must stay inside the app. Proving and testing it types its steps into the real app, and
the steps come from a stranger's video, so no text in it may hold a link, a network path or another
workbook, and its formulas may use only everyday functions that work on the workbook's own values.
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from app.core.lesson import FORMAT, MAX_WORDS, Lesson, LessonError, lesson_from_dict, lesson_json_schema, validate
from app.core.plugin import AppPlugin
from app.core.types import Param
from app.factory.video import Prepared, VideoInfo
from app.meta.client import Answer, MetaClient, MetaRefused

WRITER_MODEL = "muse-spark-1.3"
SHOWN_PROBLEMS = 3
SHORT_TEXT = 60
BROKE_RULES = "Muse Spark could not write a lesson that keeps the rules from this video. Try another video."
REFUSED = "Meta would not take this video, so the lesson could not be written. Try another video."

# Text that reaches outside the app anywhere in a lesson: a link of any kind, or a network path.
LINK = re.compile(r"\w+://|file:/|www\.|mailto:|search-ms:|ms-[a-z-]+:|\\\\[^\\\s]+\\", re.IGNORECASE)

# The only functions a lesson's formulas may use: everyday ones that work out values from the workbook
# itself. Any other is refused, so a function that fetches, reads files, calls a program or runs a macro
# cannot slip in, nor can one added to Excel later; nor can one that calls a function it is handed (LET,
# LAMBDA, MAP and the like), which could hand it one of those.
ALLOWED_FUNCTIONS = frozenset("""
    ABS ADDRESS AGGREGATE AND ARABIC AVERAGE AVERAGEA AVERAGEIF AVERAGEIFS CEILING CEILING.MATH CHAR CHOOSE
    CHOOSECOLS CHOOSEROWS CLEAN CODE COLUMN COLUMNS COMBIN CONCAT CONCATENATE CONVERT CORREL COS COUNT COUNTA
    COUNTBLANK COUNTIF COUNTIFS DATE DATEDIF DATEVALUE DAY DAYS DB DDB DEGREES DOLLAR DROP EDATE EOMONTH
    ERROR.TYPE EVEN EXACT EXP EXPAND FACT FALSE FILTER FIND FIXED FLOOR FLOOR.MATH FORECAST FORECAST.LINEAR
    FORMULATEXT FREQUENCY FV GCD GEOMEAN HARMEAN HLOOKUP HOUR HSTACK IF IFERROR IFNA IFS INDEX INT IPMT IRR
    ISBLANK ISERR ISERROR ISEVEN ISFORMULA ISLOGICAL ISNA ISNONTEXT ISNUMBER ISODD ISOWEEKNUM ISREF ISTEXT
    LARGE LCM LEFT LEN LN LOG LOG10 LOOKUP LOWER MATCH MAX MAXA MAXIFS MEDIAN MID MIN MINA MINIFS MINUTE
    MMULT MOD MODE MODE.SNGL MONTH MROUND N NA NETWORKDAYS NETWORKDAYS.INTL NOT NOW NPER NPV NUMBERVALUE ODD
    OFFSET OR PERCENTILE PERCENTILE.EXC PERCENTILE.INC PERCENTRANK PI PMT POWER PPMT PRODUCT PROPER PV
    QUARTILE QUARTILE.EXC QUARTILE.INC QUOTIENT RADIANS RAND RANDARRAY RANDBETWEEN RANK RANK.AVG RANK.EQ RATE
    REGEXEXTRACT REGEXREPLACE REGEXTEST REPLACE REPT RIGHT ROMAN ROUND ROUNDDOWN ROUNDUP ROW ROWS SEARCH
    SECOND SEQUENCE SIGN SIN SLN SMALL SORT SORTBY SQRT STDEV STDEV.P STDEV.S STDEVA SUBSTITUTE SUBTOTAL SUM
    SUMIF SUMIFS SUMPRODUCT SUMSQ SWITCH T TAKE TAN TEXT TEXTAFTER TEXTBEFORE TEXTJOIN TEXTSPLIT TIME
    TIMEVALUE TOCOL TODAY TOROW TRANSPOSE TREND TRIM TRIMMEAN TRUE TRUNC TYPE UNICHAR UNICODE UNIQUE UPPER
    VALUE VAR VAR.P VAR.S VLOOKUP VSTACK WEEKDAY WEEKNUM WORKDAY WORKDAY.INTL WRAPCOLS WRAPROWS XIRR XLOOKUP
    XMATCH XNPV XOR YEAR YEARFRAC
""".split())
FORMULA_START = ("=", "+", "-", "@")         # how a spreadsheet knows a cell holds a formula
FILE_PREFIXES = ("_XLFN.", "_XLWS.")         # how a saved file marks newer functions
NEXT_CELL = re.compile(r"[\r\n\t]")         # Enter and Tab move to the next cell when a value is typed
# In running text a formula can start at any "=", or at a "+", "-" or "@" that begins a word.
FORMULA_IN_TEXT = re.compile(r"=|(?:^|(?<=[\s\"'(]))[+\-@](?=[A-Za-z_(])")
CALLED = re.compile(r"([A-Za-z_][A-Za-z0-9_.]*)\s*\(")
# In a sentence, "total (net)" is not a call, but a name with a space before "(" right after a formula sign,
# an operator or a comma is, as in "=WEBSERVICE (A1)".
CALLED_IN_TEXT = re.compile(r"([A-Za-z_][A-Za-z0-9_.]*)\(|(?<=[=+\-*/^&,;(<>@{])\s*([A-Za-z_][A-Za-z0-9_.]*)\s+\(")
QUOTED = re.compile(r'"[^"]*"')
JOINED = re.compile(r'"\s*&\s*"')           # where "&" glues two pieces of text into one
# What reaches outside in a formula: the "|" of a DDE link to another program, another file, or a drive.
REACHING = re.compile(r"\||\.(?:xl[a-z]{1,2}|csv|ods|txt)\b|\b[a-z]:\\", re.IGNORECASE)

# What each app's `starter` holds. A plug-in may say it itself with a `starter_help` attribute.
STARTER_HELP = {
    "excel": (
        'The starter is the workbook before the tutorial\'s first step: {"sheets": [{"name": "Sheet1", '
        '"cells": {"A1": "Item", "B2": 12000, "B6": "=B2+B3"}, "bold": ["A1:C1"], "formats": {"B2:B6": "#,##0"}, '
        '"widths": {"A": 14}}], "active": "Sheet1"}. Cells hold numbers, text, or formulas starting with "=". '
        "It must fit 920 px wide: use columns A to M at most, fewer when you widen any."),
}


@dataclass(frozen=True)
class NotReady:
    reason: str                                  # plain words, shown to the learner
    detail: str = ""                             # what went wrong exactly, for the log only


def write_lesson(prepared: Prepared, info: VideoInfo, plugin: AppPlugin, client: MetaClient, *,
                 feedback: str = "", lessons_dir: Path = Path("lessons"), label: str | None = None
                 ) -> Lesson | NotReady:
    """One lesson from the video, or why there is none. `feedback` is the prover's reason on a retry."""
    label = label or f"writer_{info.id}" + ("_fix" if feedback else "")
    schema = lesson_json_schema(plugin)
    messages = [{"role": "system", "content": _rules(plugin)}]
    try:
        file_id = client.upload(prepared.small_mp4, label=f"{label}_upload")
        sent = messages + [{"role": "user", "content": _request(prepared, info, feedback, [
            {"type": "input_file", "file_id": file_id}])}]
        answer = client.respond(WRITER_MODEL, sent, label=label, schema=schema)
    except MetaRefused:
        label = f"{label}_frames"                # Meta would not take the video: send the still frames
        sent = messages + [{"role": "user", "content": _request(prepared, info, feedback, _frames(prepared))}]
        try:
            answer = client.respond(WRITER_MODEL, sent, label=label, schema=schema)
        except MetaRefused as exc:
            return NotReady(REFUSED, detail=str(exc))

    for retry in (False, True):
        if answer.refusal:
            return NotReady(f"Muse Spark would not write this lesson: {answer.refusal}")
        lesson, problems = _read(answer, info, plugin, lessons_dir)
        if not problems:
            return lesson
        if retry:
            break
        sent = sent + [{"role": "assistant", "content": answer.text},
                       {"role": "user", "content": "That lesson broke these rules:\n"
                        + "\n".join(f"- {p}" for p in problems)
                        + "\nWrite the whole lesson again, fixing every one."}]
        try:
            answer = client.respond(WRITER_MODEL, sent, label=f"{label}_retry", schema=schema)
        except MetaRefused as exc:
            return NotReady(REFUSED, detail=str(exc))
    shown = "; ".join(problems[:SHOWN_PROBLEMS])
    more = len(problems) - SHOWN_PROBLEMS
    return NotReady(BROKE_RULES,
                    detail=f"Muse Spark's lesson broke the rules: {shown}{f'; and {more} more' if more > 0 else ''}.")


# The request.

def _param(p: Param) -> str:
    kind = f"one of {', '.join(p.choices)}" if p.type == "enum" else p.type
    return f"{p.name}: {kind}{'' if p.required else ' (optional)'}"


def _menu(menu: Mapping) -> str:
    return "\n".join(f"- {k.name}({', '.join(_param(p) for p in k.params)}): {k.summary}" for k in menu.values())


def _rules(plugin: AppPlugin) -> str:
    title = plugin.title
    starter = getattr(plugin, "starter_help", None) or STARTER_HELP.get(
        plugin.app_id, "The starter is the app's state before the tutorial's first step, as keys and values.")
    return f"""You turn a {title} tutorial video into a hands-on lesson. The learner does every step
themselves in the real {title}, and a fixed check that reads {title} decides when each step is done.

Answer with JSON matching the schema. The rules:
- Follow the tutorial: the same task, the same starting data, the same order. Leave out talk that is not a step.
- title: short, naming the task. goal.sentence: one sentence saying what the learner will have made.
- starter: {starter} Leave empty everything a step fills in, so every check starts false.
- Each step is one thing the learner does that leaves a change the check can see.
- instruction: at most {MAX_WORDS} words, plain everyday words, speaking to the learner. Never say "simply" or "just".
- why: one short sentence on why the step matters.
- target: where the learner acts, one of these kinds: {', '.join(sorted(plugin.target_kinds))}.
- check: the one check from the check menu that is true only once the step is done right, with its arguments.
- replay: the operation from the operation menu that does the step exactly right.
- hints: exactly 3, from a gentle nudge to the full answer.
- mistakes: 1 or 2 wrong answers a learner is likely to give, each an operation from the operation menu that
  the check must reject, with its own not_yet line (at most {MAX_WORDS} words) naming the one thing to change.
- clip: the start and end second where the video shows this step, or null when it is not shown.
- Use only kinds on the menus below, and only the arguments each kind takes.

Check menu:
{_menu(plugin.checks)}

Operation menu:
{_menu(plugin.ops)}"""


def _t(seconds: float) -> str:
    return str(round(float(seconds), 2))


def _request(prepared: Prepared, info: VideoInfo, feedback: str, media: list[dict]) -> list[dict]:
    lines = "\n".join(f"[{_t(a)}-{_t(b)} s] {words}" for a, b, words in prepared.transcript)
    text = (f'The tutorial: "{info.title}" by {info.creator}, {info.length_s} seconds long.\n'
            + (f"Transcript, with seconds into the video:\n{lines}" if lines
               else "There is no transcript: nobody speaks in the video."))
    if feedback:
        text += (f"\n\nA lesson written from this video before failed its proof: {feedback}\n"
                 "Write the whole lesson again and fix that.")
    return [{"type": "input_text", "text": text}, *media]


def _frames(prepared: Prepared) -> list[dict]:
    parts: list[dict] = []
    for t, path in prepared.frames:
        picture = base64.b64encode(Path(path).read_bytes()).decode("ascii")
        parts += [{"type": "input_text", "text": f"Frame at {_t(t)} s:"},
                  {"type": "input_image", "image_url": f"data:image/png;base64,{picture}"}]
    return parts


# The answer.

def _read(answer: Answer, info: VideoInfo, plugin: AppPlugin, lessons_dir: Path) -> tuple[Lesson | None, list[str]]:
    data = answer.data
    if not isinstance(data, dict):
        return None, ["its answer was not a lesson in JSON"]
    title = data.get("title") if isinstance(data.get("title"), str) else info.title
    lesson_id = unique_id(title, lessons_dir)
    goal = data.get("goal")
    try:
        lesson = lesson_from_dict({
            "format": FORMAT, "id": lesson_id, "title": data.get("title"), "app": plugin.app_id,
            "course": plugin.app_id,
            "source": {"url": info.url, "title": info.title, "creator": info.creator,
                       "channel_url": info.channel_url, "licence": info.licence, "length_s": info.length_s},
            "goal": {"sentence": goal.get("sentence") if isinstance(goal, Mapping) else None, "picture": None},
            "starter": data.get("starter"), "steps": data.get("steps"),
            "made_by": "generated", "edited_by_hand": False, "proof": None, "test": None,
        }, lessons_dir / lesson_id)
    except LessonError as exc:
        return None, [str(exc)]
    return lesson, validate(lesson, plugin) + _writer_problems(lesson, info) + _outside(data, plugin)


def _writer_problems(lesson: Lesson, info: VideoInfo) -> list[str]:
    """Rules for a freshly written lesson that a finished lesson need not keep."""
    problems = []
    for step in lesson.steps:
        at = f"step {step.id}"
        if step.clip is not None and step.clip.end > info.length_s + 1:
            problems.append(f"{at}: the clip ends at {step.clip.end:g} s, after the video ends at {info.length_s} s")
        if not 1 <= len(step.mistakes) <= 2:
            n = len(step.mistakes)
            problems.append(f"{at}: it has {'no' if n == 0 else n} predicted mistakes; give 1 or 2")
    return problems


def _outside(data: dict, plugin: AppPlugin) -> list[str]:
    """Each piece of the lesson's text that reaches outside the app, named by where it is."""
    parts = [("the title", data.get("title")), ("the goal", data.get("goal")), ("the starter", data.get("starter"))]
    parts += [(f"step {step.get('id')}", step) for step in data.get("steps") or [] if isinstance(step, Mapping)]
    problems = []
    for where, part in parts:
        for text in _texts(part):
            what = _reaches(text, plugin)
            if what:
                short = text if len(text) <= SHORT_TEXT else text[:SHORT_TEXT - 1] + "\u2026"
                problems.append(f"{where}: {short} {what}")
    return problems


def _reaches(text: str, plugin: AppPlugin) -> str:
    """How this text leaves the app, in words, or "" when it stays inside."""
    outside = f"reaches outside {plugin.title}; a lesson must stay inside it"
    if LINK.search(text):
        return outside
    for formula, called in _formulas(text):
        bare = QUOTED.sub('""', formula)             # quoted text in a formula is only text
        if LINK.search(JOINED.sub("", formula)):
            return outside
        # In a sentence, quotes may wrap a formula to type, so its quoted text is searched too.
        searched = bare if called is CALLED else formula
        for found in called.finditer(searched):
            name = next(n for n in found.groups() if n).upper()
            for prefix in FILE_PREFIXES:
                name = name.removeprefix(prefix)
            if name not in ALLOWED_FUNCTIONS:
                return f"uses {name}, which a lesson may not use"
        if REACHING.search(bare):
            return outside
    return ""


def _formulas(text: str) -> list[tuple[str, re.Pattern]]:
    """The formulas a piece of text could put in a cell, each with the pattern that finds the functions it
    calls. A line starting with a formula sign is one, as a cell holds it or as typing puts it in the next
    cell. In a sentence, everything from any sign on could be typed as one, by the learner or by Meta's
    agent, who types what the step says."""
    found = [(line, CALLED) for line in NEXT_CELL.split(text) if line.lstrip().startswith(FORMULA_START)]
    found += [(text[sign.start():], CALLED_IN_TEXT) for sign in FORMULA_IN_TEXT.finditer(text)]
    return found


def _texts(value) -> list[str]:
    """Every string in a piece of JSON, its keys included (a key can be a cell or a sheet name)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        return [t for k, v in value.items() for t in _texts(k) + _texts(v)]
    if isinstance(value, list):
        return [t for v in value for t in _texts(v)]
    return []


def unique_id(title: str, lessons_dir: Path) -> str:
    """A folder name made from the title that no lesson in `lessons_dir` has yet."""
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60].strip("-") or "lesson"
    lesson_id, n = base, 1
    while (Path(lessons_dir) / lesson_id).exists():
        n += 1
        lesson_id = f"{base}-{n}"
    return lesson_id
