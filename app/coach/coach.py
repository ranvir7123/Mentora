"""The coach: AI tips from the learner's own attempts, and answers to questions about the current step.

Both ask Muse Spark and send it only a small summary: for tips, how each finished step went (tries, hints,
seconds), never what is in the workbook; for answers, the step, the hints already shown, the last "Not yet"
and a few lines the plug-in reads from the app. The coach cannot tick a step and never says one is done: an
answer that claims so is replaced by the step's next hint, because only the app's own check decides. When
Meta cannot be reached, the coach raises CoachUnavailable with a calm line for the screen; lessons go on.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Mapping, Sequence

from app.core.runner import StepRecord
from app.meta.client import Answer, MetaClient, MetaError, NoKey, SpendLimitReached

COACH_MODEL = "muse-spark-1.3"
TIP_WORDS, ANSWER_WORDS = 40, 60
RECENT_STEPS = 100               # tips look at the most recent finished steps only
MAX_STATE, MAX_VALUE, MAX_QUESTION, MAX_SHELF = 12, 120, 500, 30

EMPTY_QUESTION = "Type a question about this step, and I'll help."
WONT_ANSWER = "I can't help with that one. Ask me about this step."
_DOWN = {
    "tips": {
        "offline": "Tips are offline right now. Your lessons still work.",
        "no_key": "Tips need a {ai} key, which isn't set up yet. Your lessons still work.",
        "paused": "Tips are paused: {ai} spending reached its limit. Your lessons still work.",
    },
    "answer": {
        "offline": "The Ask box can't answer right now. Your lesson still works: try Hint or Show me.",
        "no_key": "The Ask box needs a {ai} key, which isn't set up yet. Try Hint or Show me.",
        "paused": "The Ask box is paused: {ai} spending reached its limit. Try Hint or Show me.",
    },
}

_TIPS_RULES = (
    "You are a calm, friendly coach for a student learning an app step by step. From how their finished steps "
    "went, write two or three short, plain sentences, at most 40 words in all. Speak to the learner as \"you\". "
    "Name one thing they do well and one thing to practise, using the step names given. Never use the words "
    "\"simply\" or \"just\". No lists, headings or emoji.")
_ANSWER_RULES = (
    "You are a calm, friendly coach helping a student with the one step of a lesson they are on. Answer their "
    "question in at most 60 words, plainly, speaking to them as \"you\". Help them do the step themselves. You "
    "cannot see or change the app and you cannot tick a step: only the app's own check does that, so never say "
    "the step is done, finished, correct or ticked. If the question is not about this step or the app, say "
    "kindly that you can help with this step. Never use the words \"simply\" or \"just\". The learner is on a "
    "Windows laptop: name only Windows keys such as Ctrl and Alt, never Cmd or Option, and never mention a Mac. "
    "In Microsoft Excel, the buttons at the top are the ribbon, not a toolbar.")
_APPS = {"excel": "Microsoft Excel", "vscode": "VS Code"}      # how the Ask box's question names the app
_SOME_APP = "the lesson's app"

_FILLER = re.compile(r"\b(?:simply|just)\b,?\s*", re.I)
_MARKS = re.compile(r"(?<![\w*])\*(?=\S)([^*]+?)(?<=\S)\*(?![\w*])")      # *word*, not =B2*C2
_CLAIM = re.compile(
    r"\b(?:ticked|tick(?:s|ed)? off|well done|nailed it|you did it|you got it|all set)\b"
    r"|(?:\bis|\bare|\bwas|\bhas been|\bhave been|['â€™]s|['â€™]re|['â€™]ve|\bhave)\s+(?:now\s+|already\s+|all\s+)?"
    r"(?:done|complete|completed|finished|correct|right|passed)\b"
    r"|\b(?:check|step)\s+(?:has\s+)?pass(?:ed|es)\b", re.I)
_IF = re.compile(r"^\s*(?:once|when|whenever|after|if|until|before|as soon as)\b", re.I)


class CoachUnavailable(Exception):
    """Meta could not help just now; the message is a calm line for the screen."""


class MetaCoach:
    """The coach the app asks for (app/core/services.py). `shelf` gives the titles of the lessons a learner
    can open, so a tip may suggest one of them and never one that does not exist."""

    def __init__(self, client: MetaClient, *, shelf: Callable[[], Sequence[str]] | None = None):
        self.client, self.shelf = client, shelf

    def tips(self, log: list[StepRecord]) -> str:
        """Two or three sentences from the learner's attempts; "" when nothing is finished yet."""
        if not log:
            return ""
        messages = [{"role": "system", "content": _TIPS_RULES + self._shelf_rule()},
                    {"role": "user", "content": summary(log[-RECENT_STEPS:])}]
        answer = self._ask(messages, "coach_tips", "tips")
        text = plain(answer.text)
        if answer.refusal or not text:
            raise CoachUnavailable(_DOWN["tips"]["offline"])
        return fit(text, TIP_WORDS)

    def answer(self, question: str, context: Mapping) -> str:
        """An answer about the current step. `context` holds the lesson's "app", the step's "instruction" and
        "why", its "hints" and how many are shown ("hints_shown"), the last "Not yet" line ("verdict") and a small
        "state" mapping the plug-in reads from the app (for Excel: the target cell's value and formula and
        the selected cell)."""
        question = " ".join(question.split())[:MAX_QUESTION]
        if not question:
            return EMPTY_QUESTION
        messages = [{"role": "system", "content": _ANSWER_RULES},
                    {"role": "user", "content": _step_summary(context) + f"\n\nThe learner asks: {question}"}]
        answer = self._ask(messages, "coach_answer", "answer")
        if answer.refusal:
            return WONT_ANSWER
        text = plain(answer.text)
        if not text or claims_done(text):
            return next_hint(context)
        return fit(text, ANSWER_WORDS)

    def _ask(self, messages: list[dict], label: str, what: str) -> Answer:
        try:
            return self.client.respond(COACH_MODEL, messages, label=label)
        except MetaError as exc:
            cause = "no_key" if isinstance(exc, NoKey) else "paused" if isinstance(exc, SpendLimitReached) \
                else "offline"
            ai = getattr(self.client, "name", "Meta")
            raise CoachUnavailable(_DOWN[what][cause].format(ai=ai)) from exc

    def _shelf_rule(self) -> str:
        titles = [t for t in (self.shelf() if self.shelf else ()) if t][:MAX_SHELF]
        if not titles:
            return " Do not name a lesson; name the skill to practise."
        return f" To suggest practice, name one of these lessons exactly as written: {'; '.join(titles)}. " \
               "Name no other lesson."


# What is sent.

def summary(log: Sequence[StepRecord]) -> str:
    """How each step went, in the order the steps were first finished. Numbers only: no workbook contents."""
    by_step: dict[str, list[StepRecord]] = {}
    for record in log:
        by_step.setdefault(record.step_id, []).append(record)
    lines = ["The learner's finished steps, by step:"]
    for step_id, records in by_step.items():
        n = len(records)
        tries = round(sum(r.tries for r in records) / n, 1)
        hints = sum(r.hints for r in records)
        seconds = sum(r.seconds for r in records) / n
        first = sum(1 for r in records if r.first_try)
        lines.append(f"- {step_id}: finished {_count(n, 'time')}, {tries:g} tries on average, "
                     f"{_count(hints, 'hint')} in all, {seconds:.0f} s on average, right first try {first} of {n}")
    return "\n".join(lines)


def _step_summary(context: Mapping) -> str:
    hints = list(context.get("hints") or [])
    shown = hints[:max(0, int(context.get("hints_shown") or 0))]
    state = context.get("state") or {}
    seen = [f"- {key}: {_short(value)}" for key, value in list(state.items())[:MAX_STATE]]
    return "\n".join([
        f"The app: {_APPS.get(str(context.get('app') or ''), _SOME_APP)} on Windows",
        f"The step: {context.get('instruction') or ''}",
        f"Why: {context.get('why') or ''}",
        f"Hints already shown: {' '.join(shown) if shown else 'none'}",
        f"The last \"Not yet\": {context.get('verdict') or 'none yet'}",
        "What the app shows now:",
        *(seen or ["- nothing read"]),
    ])


def _short(value: Any) -> str:
    text = " ".join(str(value).split()) if value not in (None, "") else "(empty)"
    return text if len(text) <= MAX_VALUE else text[:MAX_VALUE - 1] + "â€¦"


# What comes back.

def plain(text: str) -> str:
    """Without "simply" and "just", without markdown's stars and backticks (the panel shows plain text; a
    star inside a formula like =B2*C2 stays), with tidy spaces and each sentence starting with a capital."""
    text = _MARKS.sub(r"\1", (text or "").replace("**", "").replace("`", ""))
    text = re.sub(r"\s+", " ", _FILLER.sub("", text)).strip()
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    return re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)


def claims_done(text: str) -> bool:
    """True when the text says the step is done, ticked or correct. "Once you're done typing, press Enter"
    is not a claim: a clause that starts with once, when, if and the like only says what to do next."""
    for match in _CLAIM.finditer(text):
        clause = re.split(r"[.!?,;:]", text[:match.start()])[-1]
        if not _IF.match(clause):
            return True
    return False


def fit(text: str, limit: int) -> str:
    """At most `limit` words: whole sentences while they fit, else the first sentence cut short."""
    kept, used = [], 0
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        words = len(sentence.split())
        if used + words > limit:
            break
        kept.append(sentence)
        used += words
    if kept:
        return " ".join(kept)
    return " ".join(text.split()[:limit]).rstrip(".,;:!?") + "â€¦"


def next_hint(context: Mapping) -> str:
    """The hint after the ones already shown (the last one when all are shown); else the instruction."""
    hints = list(context.get("hints") or [])
    if not hints:
        return str(context.get("instruction") or "")
    return hints[min(max(0, int(context.get("hints_shown") or 0)), len(hints) - 1)]


def _count(n: int, thing: str) -> str:
    return f"{n} {thing}{'' if n == 1 else 's'}"
