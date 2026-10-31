"""Your common mistakes: the steps that took you more than one try, with what kind of slip it was and a tip.

A mistake is a "Not yet" a fixed check said; the AI never decides one. Each finished step in the attempt
log carries the code of every "Not yet" its check said, such as `typed_value` or `partial:C1`. The part
before the colon is the kind of slip; with the step's kind of check it picks a label and a tip in fixed
words below, so this works with no Meta key. Lines from before the codes were kept get the tip for the
kind of check alone.

The steps that went wrong most come first. A step you have since done right first time stays on the list,
marked fixed, after the ones still to practise.
"""
from __future__ import annotations

from collections import Counter
from typing import Mapping

from app.core.lesson import Lesson
from app.core.runner import StepRecord

LIMIT = 3
MAX_TIP_WORDS = 16

# The tip for each kind of check, when the kind of slip is not known or has no tip of its own.
_CHECK_TIPS = {
    # Excel
    "value_equals": "Type the value exactly as the step says, then press Enter.",
    "formula": "Start with = and click each cell the formula needs.",
    "filled_formula": "Drag the small square at the cell's corner down to the last row.",
    "number_format": "Select the cells, then pick the format in the Number box on Home.",
    "bold": "Select every heading cell first, then press Bold once.",
    "chart": "Select the cells first, then pick the chart type the step names.",
    "frozen": "Use Freeze Panes on the View tab, and pick the one the step names.",
    "filter": "Click inside the table, then turn on Filter from the Data tab.",
    "sorted": "Click a cell in the column to sort by, then pick the order.",
    "selected": "Drag from the first cell to the last cell the step names.",
    "sheet_named": "Double-click the sheet's tab at the bottom and type the new name.",
    # VS Code
    "file_exists": "Check the file's name letter by letter, ending in .py.",
    "defines_function": "Start the line with def, then the name, brackets and a colon.",
    "calls": "Write the name in small letters, with brackets right after it.",
    "prints": "Put f before the quotes, then the name inside curly brackets.",
    "imports": "Copy the module's name from the step, letter for letter.",
    "assigns": "Write the name, then =, then the value, all on one line.",
    "uses_text": "Copy the text from the step exactly, then save with Ctrl+S.",
    "reads_setting": "Read the key with os.environ, never paste the key itself.",
    "run_ok": "Save first, then press Run and read the terminal.",
    "run_output": "Save first, then run it again and check what it prints.",
    "no_problems": "Fix the line VS Code underlines in red, then save.",
    "no_key_in_code": "Take the key out and read it with os.environ instead.",
}

# (label, tip) for each kind of slip a check names, by kind of check; "*" is any check.
_SLIPS: dict[tuple[str, str], tuple[str, str]] = {
    ("formula", "typed_value"): ("Typed the answer instead of a formula",
                                 "Start with = so Excel works it out and keeps it up to date."),
    ("formula", "covers_missing"): ("Formula left out a cell",
                                    "Drag over every cell the total needs, from the first to the last."),
    ("formula", "refers_extra"): ("Formula used a cell it shouldn't",
                                  "Check the cells your formula names against the step."),
    ("formula", "not_absolute"): ("Total not locked with $ signs",
                                  "Press F4 on the total's address so it stays put when copied."),
    ("formula", "uses_missing"): ("Used a different function", "Use the function the step names, like SUM."),
    ("formula", "value"): ("Formula gave a different answer", "Divide the amount by the total, in that order."),
    ("value_equals", "as_text"): ("Number kept as text", "Type the number again with nothing before it."),
    ("filled_formula", "gap"): ("Stopped before the last row",
                                "Drag the corner square all the way to the last row."),
    ("filled_formula", "differs"): ("A copied cell has another formula",
                                    "Fill down from the first cell instead of typing each one."),
    ("number_format", "partial"): ("Some cells missed the format",
                                   "Select every cell first, then pick the format once."),
    ("number_format", "kind"): ("Picked another number format",
                                "Open the Number box on Home and pick the one the step names."),
    ("bold", "partial"): ("Some headings missed the bold",
                          "Select every heading cell first, then press Bold once."),
    ("chart", "type"): ("Picked another chart type", "Pick the chart type the step names, like Pie."),
    ("chart", "over"): ("Chart uses other cells", "Select only the cells the step names before you insert."),
    ("frozen", "frozen"): ("Froze another part of the sheet", "Pick Freeze Top Row on the View tab."),
    ("sorted", "order"): ("Sorted the other way round",
                          "Pick Largest to Smallest for biggest first, or the other for smallest."),
    ("sorted", "column"): ("Sorted by another column", "Click a cell in the right column before you sort."),
    ("*", "named"): ("Wrote a name with different capitals or spelling",
                     "Python reads every letter exactly, capitals too. Copy the name from the step."),
    ("*", "syntax"): ("Brackets or quotes missing", "Every open bracket and quote needs its closing one."),
    ("*", "not_called"): ("Forgot the brackets that run it", "Add brackets right after the name to run it."),
    ("*", "no_f"): ("Forgot the f before the quotes", "Put f before the quotes so Python fills in the name."),
    ("*", "key"): ("Pasted the key into the code", "Never paste the key. Read it with os.environ."),
    ("*", "quoted"): ("Wrote the setting's name in quotes only",
                      'Wrap the name in os.environ[...], like os.environ["META_API_KEY"].'),
}

_DEFAULT_TIP = "Read the step again, then try it slowly one part at a time."


def _slip(check: str, code: str) -> tuple[str, str] | None:
    kind = code.split(":", 1)[0]
    return _SLIPS.get((check, kind)) or _SLIPS.get(("*", kind))


def tip_for(check: str, code: str) -> str:
    """The tip for a slip with this code on a step with this kind of check, in fixed words."""
    slip = _slip(check, code) if code else None
    return slip[1] if slip else _CHECK_TIPS.get(check, _DEFAULT_TIP)


def common_mistakes(records: list[StepRecord], lessons: Mapping[str, Lesson], *,
                    limit: int = LIMIT) -> list[dict]:
    """The steps that took more than one try, most slips first, as the home screen's cards. `records` is
    the attempt log, oldest first, each step named "<lesson>/<step>"; `lessons` the shelf by id."""
    found: dict[tuple[str, str], dict] = {}
    for order, record in enumerate(records):
        lesson_id, _, step_id = record.step_id.partition("/")
        lesson = lessons.get(lesson_id)
        index = next((i for i, s in enumerate(lesson.steps) if s.id == step_id), None) if lesson else None
        if index is None:
            continue
        seen = found.setdefault((lesson_id, step_id), {
            "lesson": lesson, "index": index, "slips": 0, "times": 0, "tries": 0, "codes": Counter(),
            "last": order, "fixed": False})
        seen["last"] = order
        if record.tries <= 1:
            seen["fixed"] = seen["times"] > 0
            continue
        seen["slips"] += record.tries - 1
        seen["times"] += 1
        seen["tries"] = max(seen["tries"], record.tries)
        seen["codes"].update(code.split(":", 1)[0] for code in record.mistakes if code)
        seen["fixed"] = False

    cards = []
    for seen in sorted((s for s in found.values() if s["times"]),
                       key=lambda s: (s["fixed"], -s["slips"], -s["last"])):
        lesson, index = seen["lesson"], seen["index"]
        step = lesson.steps[index]
        check = step.check.kind
        top = next((code for code, _ in seen["codes"].most_common() if _slip(check, code)), "")
        cards.append({"lessonId": lesson.id, "lessonTitle": lesson.title, "stepIndex": index,
                      "instruction": step.instruction, "kind": _slip(check, top)[0] if top else "",
                      "tries": seen["tries"], "times": seen["times"], "tip": tip_for(check, top),
                      "fixed": seen["fixed"]})
    return cards[:limit]
