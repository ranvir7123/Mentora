import json

import pytest

from app.coach.coach import CoachUnavailable, MetaCoach
from app.core.runner import StepRecord
from app.meta.client import SpendLimitReached
from tests.factory.conftest import Saved

LOG = [StepRecord("total", 1, 0, 12.0, True), StepRecord("chart", 3, 2, 95.5, False),
       StepRecord("total", 2, 1, 30.0, False)]
CONTEXT = {"instruction": "Total the costs in B6.", "why": "The total shows what the month costs.",
           "hints": ["Click B6.", "Type =SUM(.", "Type =SUM(B2:B5) and press Enter."], "hints_shown": 1,
           "verdict": "Not yet: B6 holds 12000, not a total.",
           "state": {"B6 value": 12000, "B6 formula": "", "selected cell": "B6"}}


class Spy:
    """Passes calls on to the real client and keeps what was sent."""

    def __init__(self, inner):
        self.inner, self.responds = inner, []

    def respond(self, model, input, *, label, **extra):
        self.responds.append({"model": model, "input": input, "label": label})
        return self.inner.respond(model, input, label=label, **extra)


class Broke:
    """A client whose every call fails with `error`."""

    def __init__(self, error):
        self.error = error

    def respond(self, *args, **kwargs):
        raise self.error


@pytest.fixture
def saved(tmp_path):
    return Saved(tmp_path / "saved")


@pytest.fixture
def spy(saved):
    return Spy(saved.client)


def _said(call):
    """The user's part of what was sent."""
    return "\n".join(m["content"] for m in call["input"] if m["role"] == "user")


def test_tips_are_short_plain_and_from_the_log_only(saved, spy):
    saved.answer("coach_tips", "You are simply quick with totals. Charts took 3 tries, so just try the Budget "
                               "chart lesson next.")
    coach = MetaCoach(spy, shelf=lambda: ["Monthly budget", "Budget chart"])

    tips = coach.tips(LOG)

    assert tips == "You are quick with totals. Charts took 3 tries, so try the Budget chart lesson next."
    (call,) = spy.responds
    assert call["model"] == "muse-spark-1.3" and call["label"] == "coach_tips"
    assert _said(call) == (
        "The learner's finished steps, by step:\n"
        "- total: finished 2 times, 1.5 tries on average, 1 hint in all, 21 s on average, right first try 1 of 2\n"
        "- chart: finished 1 time, 3 tries on average, 2 hints in all, 96 s on average, right first try 0 of 1")
    rules = json.dumps(call["input"][0])
    assert "at most 40 words" in rules and "Monthly budget; Budget chart" in rules


def test_long_tips_keep_whole_sentences_up_to_forty_words(saved, spy):
    first = "You total columns fast and right the first time."                        # 9 words
    second = "Charts took you three tries and two hints, which is normal when they are new to you."   # 17
    third = "Practise one more chart in the Budget chart lesson before you move on to sorting and filters."  # 17
    saved.answer("coach_tips", f"{first} {second} {third}")

    assert MetaCoach(spy).tips(LOG) == f"{first} {second}"


def test_no_finished_steps_means_no_tips(spy):
    assert MetaCoach(spy).tips([]) == "" and spy.responds == []


def test_an_answer_uses_the_step_and_the_hints_already_shown(saved, spy):
    saved.answer("coach_answer", "SUM adds up a range of cells. In B6, just type =SUM( and pick your costs.")

    answer = MetaCoach(spy).answer("What does SUM do?", CONTEXT)

    assert answer == "SUM adds up a range of cells. In B6, type =SUM( and pick your costs."
    (call,) = spy.responds
    assert call["label"] == "coach_answer"
    said = _said(call)
    for part in ("Total the costs in B6.", "The total shows what the month costs.", "Click B6.",
                 "Not yet: B6 holds 12000, not a total.", "B6 value: 12000", "selected cell: B6",
                 "What does SUM do?"):
        assert part in said
    assert "Type =SUM(B2:B5)" not in said                    # hints not yet shown are not given away


@pytest.mark.parametrize("app, named", [("excel", "Microsoft Excel"), ("vscode", "VS Code")])
def test_an_answer_names_the_app_and_says_the_laptop_runs_windows(saved, spy, app, named):
    # Told nothing, Claude answered "press Ctrl+S (or Cmd+S on a Mac)" on a Windows laptop.
    saved.answer("coach_answer", "Press Ctrl+S to save.")

    MetaCoach(spy).answer("How do I save?", {**CONTEXT, "app": app})

    (call,) = spy.responds
    assert f"The app: {named} on Windows" in _said(call)
    rules = call["input"][0]["content"]
    assert "Windows" in rules and "Cmd" in rules and "Mac" in rules and "ribbon" in rules


def test_an_answer_for_an_unknown_app_still_says_windows(saved, spy):
    saved.answer("coach_answer", "Press Ctrl+S to save.")

    MetaCoach(spy).answer("How do I save?", CONTEXT)              # no "app" given

    assert "The app: the lesson's app on Windows" in _said(spy.responds[0])


@pytest.mark.parametrize("claim", [
    "Yes, that step is done now, nice work!",
    "You've finished this step.",
    "It's ticked! Move on to the next one.",
    "Your total is correct, well done.",
    "Great, B6 is complete.",
])
def test_answers_never_claim_a_step_is_done(saved, spy, claim):
    saved.answer("coach_answer", claim)

    assert MetaCoach(spy).answer("Did I do it?", CONTEXT) == "Type =SUM(."           # the next hint instead


@pytest.mark.parametrize("plain_answer", [
    "Press Enter when you have typed the formula.",
    "The total goes in B6, the cell under your costs.",
    "Once you're done typing, press Enter and the app checks it.",
])
def test_ordinary_answers_are_not_taken_for_claims(saved, spy, plain_answer):
    saved.answer("coach_answer", plain_answer)

    assert MetaCoach(spy).answer("How?", CONTEXT) == plain_answer


def test_with_every_hint_shown_a_claim_becomes_the_last_hint(saved, spy):
    saved.answer("coach_answer", "That's done!")

    assert MetaCoach(spy).answer("Done?", {**CONTEXT, "hints_shown": 3}) == "Type =SUM(B2:B5) and press Enter."


def test_a_long_answer_is_cut_to_sixty_words(saved, spy):
    words = ["Word"] + ["word"] * 69                        # one 70-word sentence
    saved.answer("coach_answer", " ".join(words) + ".")

    answer = MetaCoach(spy).answer("Tell me everything", CONTEXT)

    assert answer == " ".join(words[:60]) + "â€¦"


def test_an_empty_question_is_not_sent(spy):
    assert MetaCoach(spy).answer("   ", CONTEXT) == "Type a question about this step, and I'll help."
    assert spy.responds == []


def test_a_question_muse_spark_will_not_answer_gets_a_calm_line(saved, spy):
    saved.refusal("coach_answer", "I can't help with that.")

    assert MetaCoach(spy).answer("Write my essay", CONTEXT) == "I can't help with that one. Ask me about this step."


@pytest.mark.parametrize("error, tips, ask", [
    ({"type": "unavailable", "message": "Meta could not be reached"},
     "Tips are offline right now. Your lessons still work.",
     "The Ask box can't answer right now. Your lesson still works: try Hint or Show me."),
    ({"type": "no_key", "message": "No Meta key is saved."},
     "Tips need a Meta key, which isn't set up yet. Your lessons still work.",
     "The Ask box needs a Meta key, which isn't set up yet. Try Hint or Show me."),
    ({"type": "refused", "status": 400, "message": "bad request"},
     "Tips are offline right now. Your lessons still work.",
     "The Ask box can't answer right now. Your lesson still works: try Hint or Show me."),
])
def test_coach_failures_become_plain_messages(saved, error, tips, ask):
    saved.error("coach_tips", **error)
    saved.error("coach_answer", **error)
    coach = MetaCoach(saved.client)

    with pytest.raises(CoachUnavailable, match=f"^{tips}$"):
        coach.tips(LOG)
    with pytest.raises(CoachUnavailable, match=f"^{ask}$"):
        coach.answer("What does SUM do?", CONTEXT)


def test_the_spending_limit_pauses_the_coach_calmly():
    coach = MetaCoach(Broke(SpendLimitReached("Meta spending has reached $100.00 of the $100.00 limit.")))

    with pytest.raises(CoachUnavailable, match="^Tips are paused: Meta spending reached its limit. Your lessons "
                                               "still work.$"):
        coach.tips(LOG)
    with pytest.raises(CoachUnavailable, match="^The Ask box is paused: Meta spending reached its limit. Try Hint "
                                               "or Show me.$"):
        coach.answer("What does SUM do?", CONTEXT)


def test_tips_muse_spark_will_not_write_are_offline_not_empty(saved):
    saved.refusal("coach_tips", "No.")

    with pytest.raises(CoachUnavailable, match="^Tips are offline right now"):
        MetaCoach(saved.client).tips(LOG)


def test_plain_takes_out_markdown_stars_and_backticks():
    from app.coach.coach import plain
    assert plain("Click the **B** (Bold) button, or press *Ctrl+B*. Type `=SUM(B2:B5)`.") \
        == "Click the B (Bold) button, or press Ctrl+B. Type =SUM(B2:B5)."
    assert plain("Type =B2*C2 in D2.") == "Type =B2*C2 in D2."


def test_plain_keeps_the_space_before_a_file_ending():
    # Claude wrote "a name ending in .py" and the screen showed "ending in.py".
    from app.coach.coach import plain
    assert plain("Type a name ending in .py, like hello.py .") == "Type a name ending in .py, like hello.py."
    assert plain("Press Enter , then save .") == "Press Enter, then save."
