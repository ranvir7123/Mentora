import json

import pytest

from app.core.fake_plugin import FakePlugin
from app.core.types import Rect
from app.factory import tester
from app.factory.input import UserTookOver
from app.meta.client import Answer, MetaRefused, SpendLimitReached
from app.meta.prices import Usage
from tests.core.conftest import build_fake_lesson

APP = Rect(0, 0, 1840, 1540)          # 920 px at 200%, beside the 360 px strip, above the taskbar


class Recording(FakePlugin):
    """The fake app, keeping the session each run opens."""

    def open(self, *args, **kwargs):
        self.session = super().open(*args, **kwargs)
        self.opened = getattr(self, "opened", 0) + 1
        return self.session


class FakeHands:
    """A 2560 x 1600 screen at 200%, taskbar below 1540. Typing "k0=1" makes the fake app hold k0 = 1, as a
    learner would; typing "close" closes the app."""

    def __init__(self, plugin, took_over_at=None, in_front=True):
        self.plugin, self.done, self.grabs, self.took_over_at = plugin, [], [], took_over_at
        self.front_ok, self.fronted = in_front, 0

    def work_area(self):
        return Rect(0, 0, 2560, 1540)

    def scale(self):
        return 2.0

    def grab(self, rect, width, height):
        self.grabs.append((rect, width, height))
        return b"\x89PNG fake"

    def in_front(self, hwnd):
        return self.front_ok

    def to_front(self, hwnd):
        self.fronted += 1

    def do(self, action):
        if self.took_over_at is not None and len(self.done) == self.took_over_at:
            raise UserTookOver("You moved the mouse, so the test stopped.")
        self.done.append(action)
        if action["type"] == "type" and action["text"] == "close":
            self.plugin.session.closed_by_learner()
        elif action["type"] == "type":
            key, value = action["text"].split("=")
            self.plugin.session.learner_sets(key, int(value))


class Script:
    """Meta's agent, answering from a script and keeping every request."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def respond(self, model, input, *, label, tools=None, previous_response_id=None, **extra):
        self.calls.append({"model": model, "input": input, "label": label, "tools": tools,
                           "previous_response_id": previous_response_id, "extra": extra})
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


_n = iter(range(1, 10_000))


def act(*actions, safety=()):
    n = next(_n)
    return Answer(text="", data=None, usage=Usage(), response_id=f"resp_{n}", cost=0.0,
                  output=[{"type": "computer_call", "call_id": f"call_{n}", "actions": list(actions),
                           "pending_safety_checks": list(safety), "status": "completed"}])


def say(text):
    n = next(_n)
    return Answer(text=text, data=None, usage=Usage(), response_id=f"resp_{n}", cost=0.0,
                  output=[{"type": "message", "role": "assistant",
                           "content": [{"type": "output_text", "text": text}]}])


def typed(key, value):
    return {"type": "type", "text": f"{key}={value}"}


def click(x, y):
    return {"type": "click", "x": x, "y": y, "button": "left"}


def three_steps():
    return build_fake_lesson({}, [{}, {}, {}])           # step i: set k{i} to i + 1


def run(script, lesson=None, *, plugin=None, hands=None, lines=None, **kwargs):
    plugin = plugin or Recording()
    hands = hands or FakeHands(plugin)
    lines = [] if lines is None else lines
    result = tester.test_lesson(lesson or three_steps(), plugin, kwargs.pop("workdir"), script, hands=hands,
                                on_line=lines.append, **{"runs": 1, **kwargs})
    return result, hands, lines


def _texts(sent):
    return json.dumps(sent, ensure_ascii=False)


def test_the_app_gets_the_screen_beside_the_strip_and_screenshots_show_only_the_app():
    assert tester.layout(FakeHands(None)) == APP
    assert tester.shot_size(APP, 2.0) == (920, 770)                        # the app at the size a person sees
    assert tester.shot_size(Rect(0, 0, 920, 1040), 1.0) == (708, 800)      # never taller than 800
    assert tester.to_screen(click(100, 50), APP, (920, 770)) == click(200, 100)
    assert tester.to_screen(click(100, 50), Rect(100, 40, 1840, 1540), (920, 770)) == click(300, 140)
    drag = {"type": "drag", "path": [{"x": 10, "y": 10}, {"x": 20, "y": 30}]}
    assert tester.to_screen(drag, APP, (920, 770))["path"] == [{"x": 20, "y": 20}, {"x": 40, "y": 60}]


def test_clicks_outside_the_app_window_are_refused(tmp_path):
    first = act(click(100, 50), click(1000, 300), typed("k0", 1))              # past the app's edge, at x 2000
    script = Script(first, act(click(640, 790)),                               # below it, at y 1580
                    act(typed("k0", 1)), act(typed("k1", 2)), act(typed("k2", 3)))

    result, hands, lines = run(script, workdir=tmp_path)

    assert result.passed and result.passes == 1
    assert hands.done[0] == click(200, 100)                  # inside: done, in screen pixels
    assert [a["type"] for a in hands.done] == ["click", "type", "type", "type"]   # the rest of a refused batch waits
    second = script.calls[1]
    assert second["previous_response_id"] == first.response_id
    assert {"type": "computer_call_output", "call_id": first.output[0]["call_id"],
            "output": {"type": "computer_screenshot", "image_url": "data:image/png;base64,iVBORyBmYWtl"}
            } == second["input"][0]
    assert "That is outside the app. Use the app's window." in _texts(second["input"])
    assert "refused click at 2000, 600: That is outside the app. Use the app's window." in lines
    assert "refused click at 1280, 1580: That is outside the app. Use the app's window." in lines


def test_keyboard_mode_refuses_every_click(tmp_path):
    script = Script(act(click(100, 50)), act(typed("k0", 1)), act(typed("k1", 2)), act(typed("k2", 3)))

    result, hands, lines = run(script, workdir=tmp_path, mode="keyboard")

    assert result.passed and result.mode == "keyboard"
    assert [a["type"] for a in hands.done] == ["type", "type", "type"]
    assert tester.KEYBOARD_NOTE in _texts(script.calls[1]["input"])
    assert tester.allowed(click(200, 100), APP, "keyboard") == (False, tester.KEYBOARD_NOTE)
    assert tester.allowed({"type": "keypress", "keys": ["ctrl", "home"]}, APP, "keyboard") == (True, "")


def test_keys_that_leave_the_app_are_refused():
    for keys in (["win"], ["alt", "tab"], ["ctrl", "esc"], ["alt", "f4"]):
        assert tester.allowed({"type": "keypress", "keys": keys}, APP, "mouse") == (False, tester.LEAVES_NOTE)
    assert tester.allowed({"type": "keypress", "keys": ["ENTER"]}, APP, "mouse") == (True, "")
    assert tester.allowed({"type": "type", "text": "=SUM(B2:B6)"}, APP, "mouse") == (True, "")
    assert tester.allowed({"type": "drag", "path": [{"x": 10, "y": 10}, {"x": 1900, "y": 10}]}, APP, "mouse") \
        == (False, tester.OUTSIDE_NOTE)
    assert tester.allowed({"type": "keypress", "keys": ["hyper"]}, APP, "mouse") == (False, "There is no key called hyper.")
    assert tester.allowed({"type": "teleport"}, APP, "mouse") == (False, "teleport is not something this test can do.")


def test_a_run_passes_when_the_runner_ticks_every_step(tmp_path):
    lesson = three_steps()
    script = Script(act(typed("k0", 1)), act(typed("k1", 2)), act(typed("k2", 3)))

    result, hands, lines = run(script, lesson, workdir=tmp_path)

    assert (result.passed, result.runs, result.passes, result.mode) == (True, 1, 1, "mouse")
    assert [c["previous_response_id"] for c in script.calls] == [None, None, None]   # a fresh talk per step
    for call, step in zip(script.calls, lesson.steps):
        assert call["model"] == "muse-wonder-1.0" and call["tools"] == [{"type": "computer"}]
        (message,) = call["input"]
        assert f"Do only this step, then stop: {step.instruction}" in message["content"][0]["text"]
        assert message["content"][1] == {"type": "input_image", "image_url": "data:image/png;base64,iVBORyBmYWtl"}
    assert set(hands.grabs) == {(APP, 920, 770)}                  # only the app, one size for the whole run
    assert lines[-1] == "1 of 1 runs passed"


def test_a_step_that_runs_out_of_actions_fails_the_run(tmp_path):
    wait = {"type": "wait"}
    script = Script(act(wait, wait), act(wait))

    result, hands, lines = run(script, workdir=tmp_path, max_actions_per_step=3)

    assert (result.passed, result.runs, result.passes) == (False, 1, 0)
    assert "run 1 failed: step s0 was not done after 3 actions" in lines


def test_safety_checks_stop_the_run(tmp_path):
    check = {"id": "sc_1", "code": "malicious_instructions", "message": "The screen asks the agent to do something else."}
    script = Script(act(typed("k0", 1), safety=[check]))

    result, hands, lines = run(script, workdir=tmp_path)

    assert result.passed is False and hands.done == []            # nothing done, nothing acknowledged
    assert len(script.calls) == 1
    assert ("run 1 failed: Meta's agent raised a safety check (malicious_instructions): "
            "The screen asks the agent to do something else.") in lines


def test_four_of_five_is_a_pass(tmp_path):
    one_step = build_fake_lesson({}, [{}])
    script = Script(act(typed("k0", 1)), act(typed("k0", 1)), act({"type": "wait"}), act(typed("k0", 1)),
                    act(typed("k0", 1)))

    result, _, lines = run(script, one_step, workdir=tmp_path, runs=5, max_actions_per_step=1)

    assert (result.passed, result.runs, result.passes) == (True, 5, 4)
    assert lines[-1] == "4 of 5 runs passed"


def test_a_test_that_can_no_longer_pass_stops_early(tmp_path):
    one_step = build_fake_lesson({}, [{}])
    script = Script(act({"type": "wait"}), act({"type": "wait"}))

    result, _, lines = run(script, one_step, workdir=tmp_path, runs=5, max_actions_per_step=1)

    assert (result.passed, result.runs, result.passes) == (False, 2, 0)
    assert lines[-1] == "0 of 2 runs passed (stopped: it can no longer pass 4 of 5)"


def test_the_agent_hears_the_not_yet_line_and_is_told_when_it_stops_too_soon(tmp_path):
    done_too_soon = say("Done.")
    script = Script(act(typed("k0", 5)), done_too_soon, act(typed("k0", 1)), act(typed("k1", 2)), act(typed("k2", 3)))

    result, _, _ = run(script, workdir=tmp_path)

    assert result.passed
    assert "The lesson says: Not yet: k0 says 5. It should say 1." in _texts(script.calls[1]["input"])
    third = script.calls[2]
    assert third["previous_response_id"] == done_too_soon.response_id
    assert third["input"][0]["role"] == "user"
    assert "This step is not done yet." in _texts(third["input"])


def test_a_refused_request_fails_the_run_and_the_app_is_closed(tmp_path):
    plugin = Recording()
    script = Script(MetaRefused(400, "the computer tool is not available"))

    result, _, lines = run(script, plugin=plugin, workdir=tmp_path)

    assert result.passed is False
    assert "run 1 failed: Meta refused the request (400): the computer tool is not available" in lines
    assert plugin.session.closed is True


def test_the_user_taking_over_stops_the_test(tmp_path):
    plugin = Recording()
    hands = FakeHands(plugin, took_over_at=0)
    with pytest.raises(UserTookOver, match="You moved the mouse"):
        run(Script(act(typed("k0", 1))), plugin=plugin, hands=hands, workdir=tmp_path)
    assert plugin.session.closed is True


def test_nothing_is_seen_or_done_while_another_window_is_in_front(tmp_path):
    plugin = Recording()
    hands = FakeHands(plugin, in_front=False)
    script = Script()

    result, _, lines = run(script, plugin=plugin, hands=hands, workdir=tmp_path)

    assert result.passed is False and hands.fronted == 1
    assert hands.grabs == [] and hands.done == [] and script.calls == []
    assert "run 1 failed: Fake app's window would not come to the front, so nothing more was done" in lines


def test_closing_the_app_fails_the_run(tmp_path):
    script = Script(act({"type": "type", "text": "close"}))

    result, _, lines = run(script, workdir=tmp_path)

    assert result.passed is False
    assert "run 1 failed: Fake app was closed" in lines


def test_running_out_of_budget_stops_the_whole_test(tmp_path):
    plugin = Recording()
    with pytest.raises(SpendLimitReached):
        run(Script(SpendLimitReached("The call log has reached the 100 dollar limit.")), plugin=plugin,
            workdir=tmp_path, runs=5)
    assert plugin.opened == 1 and plugin.session.closed is True
