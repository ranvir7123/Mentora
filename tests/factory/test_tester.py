import json
from concurrent.futures import Future

import pytest

from app.core.fake_plugin import FakePlugin
from app.core.types import Rect
from app.factory import tester
from app.factory.input import UserTookOver
from app.factory.prove import ProveError
from app.meta.client import Answer, MetaRefused, MetaUnavailable, SpendLimitReached
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
    learner would; typing "close" closes the app, "move" drags its window aside and "away" puts another
    window in front. Points inside `foreign` are over another window, such as the desktop."""

    def __init__(self, plugin, took_over_at=None, in_front=True, covered_for=0, foreign=None):
        self.plugin, self.done, self.grabs, self.took_over_at = plugin, [], [], took_over_at
        self.front_ok, self.fronted, self.covered_for, self.seen = in_front, 0, covered_for, []
        self.frame, self.foreign = APP, foreign

    def work_area(self):
        return Rect(0, 0, 2560, 1540)

    def scale(self):
        return 2.0

    def grab(self, rect, width, height):
        self.grabs.append((rect, width, height))
        self.seen.append("grab")
        return b"\x89PNG fake"

    def covered(self, hwnd, rect):
        """Another program's window is over the app for the first `covered_for` checks."""
        if self.covered_for > 0:
            self.covered_for -= 1
            self.seen.append("covered")
            return True
        return False

    def in_front(self, hwnd):
        return self.front_ok

    def to_front(self, hwnd):
        self.fronted += 1

    def bounds(self, hwnd):
        return self.frame

    def app_at(self, hwnd, x, y):
        f = self.foreign
        return f is None or not (f.x <= x < f.x + f.w and f.y <= y < f.y + f.h)

    def do(self, action):
        if self.took_over_at is not None and len(self.done) == self.took_over_at:
            raise UserTookOver("You moved the mouse, so the test stopped.")
        self.done.append(action)
        if action["type"] == "type" and action["text"] == "close":
            self.plugin.session.closed_by_learner()
        elif action["type"] == "type" and action["text"] == "move":
            self.frame = Rect(300, 200, 1840, 1540)
        elif action["type"] == "type" and action["text"] == "away":
            self.front_ok = False
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


def test_progress_is_plain_words_while_the_log_keeps_what_meta_and_the_checks_said(tmp_path):
    progress, lines = [], []
    script = Script(act({"type": "keypress", "keys": ["win"]}), act(typed("k0", 1)), act(typed("k1", 2)),
                    act(typed("k2", 3)), MetaUnavailable("Meta is busy right now (503: upstream reset)"))

    plugin = Recording()
    tester.test_lesson(three_steps(), plugin, tmp_path, script, hands=FakeHands(plugin), runs=2,
                       on_line=lines.append, on_progress=progress.append)

    assert progress == ["run 1 of 2 is playing", "run 2 of 2 is playing, 1 passed so far"]
    assert "run 2 failed: Meta is busy right now (503: upstream reset)" in lines
    assert "refused keypress win: That key would leave the app. Stay in the app's window." in lines


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


def test_keys_held_with_any_action_are_checked():
    assert tester.allowed({"type": "type", "text": "x", "keys": ["win"]}, APP, "mouse") == (False, tester.LEAVES_NOTE)
    assert tester.allowed({"type": "screenshot", "keys": ["alt", "tab"]}, APP, "keyboard") == (False, tester.LEAVES_NOTE)
    assert tester.allowed({"type": "wait", "keys": ["hyper"]}, APP, "mouse") == (False, "There is no key called hyper.")
    assert tester.allowed({"type": "keypress", "keys": "ctrl+c"}, APP, "mouse") == (False, tester.KEYS_NOTE)


def test_the_window_menu_and_the_security_screen_are_refused_but_the_apps_own_keys_are_not():
    for keys in (["alt", "space"], ["ctrl", "alt", "delete"], ["ctrl", "shift", "esc"], ["win", "r"]):
        assert tester.allowed({"type": "keypress", "keys": keys}, APP, "mouse") == (False, tester.LEAVES_NOTE)
    for keys in (["alt", "enter"], ["shift", "f10"], ["apps"], ["f2"], ["ctrl", "shift", "enter"]):
        assert tester.allowed({"type": "keypress", "keys": keys}, APP, "mouse") == (True, "")   # Excel's own


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


def test_nothing_is_seen_or_done_until_another_programs_window_moves_off_the_app(tmp_path, monkeypatch):
    monkeypatch.setattr(tester, "COVER_WAIT_S", 0)
    plugin = Recording()
    hands = FakeHands(plugin, covered_for=3)                 # a notification, gone after three checks
    script = Script(act(typed("k0", 1)), act(typed("k1", 2)), act(typed("k2", 3)))

    result, _, _ = run(script, plugin=plugin, hands=hands, workdir=tmp_path)

    assert result.passed
    assert hands.seen[:4] == ["covered", "covered", "covered", "grab"]


def test_a_window_that_stays_over_the_app_fails_the_run_with_nothing_sent(tmp_path, monkeypatch):
    monkeypatch.setattr(tester, "COVER_WAIT_S", 0)
    plugin = Recording()
    hands = FakeHands(plugin, covered_for=10_000)
    script = Script()

    result, _, lines = run(script, plugin=plugin, hands=hands, workdir=tmp_path)

    assert result.passed is False
    assert hands.grabs == [] and hands.done == [] and script.calls == []
    assert "run 1 failed: another program's window stayed over Fake app, so nothing more was done" in lines


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


def test_a_window_that_moved_or_changed_size_fails_the_run_with_nothing_more_done(tmp_path):
    script = Script(act({"type": "type", "text": "move"}, typed("k0", 1)))     # the agent dragged the title bar

    result, hands, lines = run(script, workdir=tmp_path)

    assert result.passed is False
    assert [a["text"] for a in hands.done] == ["move"] and len(hands.grabs) == 1
    assert "run 1 failed: Fake app's window moved or changed size, so nothing more was done" in lines
    assert tester.holds(Rect(1, 2, 1838, 1537), APP)                          # a pixel or two off is the same place
    assert not tester.holds(Rect(0, 0, 1840, 1200), APP)


def test_a_click_over_another_window_is_refused_even_inside_the_apps_area(tmp_path):
    plugin = Recording()
    hands = FakeHands(plugin, foreign=Rect(1000, 1000, 400, 300))             # the desktop shows through here
    script = Script(act(click(600, 600), typed("k0", 1)), act(typed("k0", 1)), act(typed("k1", 2)),
                    act(typed("k2", 3)))

    result, _, lines = run(script, plugin=plugin, hands=hands, workdir=tmp_path)

    assert result.passed
    assert [a["type"] for a in hands.done] == ["type", "type", "type"]
    assert "refused click at 1200, 1200: That is outside the app. Use the app's window." in lines
    assert tester.OUTSIDE_NOTE in _texts(script.calls[1]["input"])


def test_another_window_coming_to_the_front_stops_the_test_and_the_app_is_not_taken_back(tmp_path):
    plugin = Recording()
    hands = FakeHands(plugin)
    script = Script(act({"type": "type", "text": "away"}, typed("k0", 1)))     # a person pressed Alt+Tab

    with pytest.raises(UserTookOver, match="^Another window came to the front, so the test stopped.$"):
        run(script, plugin=plugin, hands=hands, workdir=tmp_path, runs=5)

    assert hands.fronted == 0 and [a["text"] for a in hands.done] == ["away"]
    assert plugin.opened == 1 and plugin.session.closed is True


@pytest.mark.parametrize("action, note", [
    ({"type": "click", "x": "10", "y": 5}, tester.POINT_NOTE),
    ({"type": "click", "x": True, "y": 5}, tester.POINT_NOTE),
    ({"type": "double_click", "y": 5}, tester.POINT_NOTE),
    ({"type": "move", "x": float("nan"), "y": 5}, tester.POINT_NOTE),
    ({"type": "drag", "path": [1, 2]}, tester.PATH_NOTE),
    ({"type": "drag", "path": "10,10 20,20"}, tester.PATH_NOTE),
    ({"type": "drag", "path": [{"x": 1, "y": None}]}, tester.PATH_NOTE),
    ({"type": "scroll", "x": 5, "y": 5, "scroll_y": "down"}, tester.SCROLL_NOTE),
    ({"type": "keypress"}, tester.KEYS_NOTE),
    ({"type": "keypress", "keys": []}, tester.KEYS_NOTE),
    ({"type": "type"}, tester.TEXT_NOTE),
    ({"type": "type", "text": 5}, tester.TEXT_NOTE),
    ({"x": 5, "y": 5}, tester.SHAPE_NOTE),
    ("click at 5, 5", tester.SHAPE_NOTE),
])
def test_a_malformed_action_is_refused_and_the_run_goes_on(tmp_path, action, note):
    script = Script(act(action), act(typed("k0", 1)), act(typed("k1", 2)), act(typed("k2", 3)))

    result, hands, lines = run(script, workdir=tmp_path)

    assert result.passed
    assert [a["type"] for a in hands.done] == ["type", "type", "type"]
    told = [part["text"] for m in script.calls[1]["input"] if m.get("role") == "user" for part in m["content"]]
    assert told == [note]
    assert any(line.startswith("refused ") and line.endswith(note) for line in lines)


class Excel(Recording):
    app_id, title = "excel", "Excel"


def test_excels_macro_keys_are_refused_in_excel(tmp_path):
    script = Script(act({"type": "keypress", "keys": ["alt", "f11"]}), act({"type": "keypress", "keys": ["alt", "f8"]}),
                    act(typed("k0", 1)), act(typed("k1", 2)), act(typed("k2", 3)))

    result, hands, lines = run(script, plugin=Excel(), workdir=tmp_path)

    assert result.passed and [a["type"] for a in hands.done] == ["type", "type", "type"]
    assert "refused keypress alt+f11: That key opens the app's macros, which a lesson never needs." in lines
    assert "refused keypress alt+f8: That key opens the app's macros, which a lesson never needs." in lines
    # Without the Excel list it is no longer the macro note, but an Alt chord still opens the ribbon, so it
    # is refused everywhere; only the wording differs.
    assert tester.allowed({"type": "keypress", "keys": ["alt", "f11"]}, APP, "mouse") == (False, tester.ALT_NOTE)


def test_text_the_agent_types_is_held_to_the_lessons_own_rules(tmp_path):
    fetch = {"type": "type", "text": "=WEBSERVICE(A1)"}
    link = {"type": "type", "text": "see www.evil.example"}
    script = Script(act(fetch), act(link), act({"type": "keypress", "keys": ["ctrl", "K"]}),
                    act(typed("k0", 1)), act(typed("k1", 2)), act(typed("k2", 3)))

    result, hands, lines = run(script, plugin=Excel(), workdir=tmp_path)

    assert result.passed and [a["text"] for a in hands.done] == ["k0=1", "k1=2", "k2=3"]
    assert "refused type: That text uses WEBSERVICE, which a lesson may not use." in lines
    assert "refused type: That text reaches outside Excel; a lesson must stay inside it." in lines
    assert "refused keypress ctrl+K: That key adds a link, which would reach outside the app." in lines
    assert tester.allowed({"type": "type", "text": "=SUM(B2:B6)"}, APP, "mouse", plugin=Excel()) == (True, "")


class NewWorkbookHands(FakeHands):
    """Ctrl+N opens a new workbook, a window of its own, in front of the lesson's."""

    def do(self, action):
        if action["type"] == "keypress" and {k.lower() for k in action["keys"]} == {"ctrl", "n"}:
            self.done.append(action)
            self.front_ok = False
        else:
            super().do(action)


def test_the_agent_may_not_open_a_new_workbook_and_no_person_is_blamed(tmp_path):
    plugin = Excel()
    script = Script(act({"type": "keypress", "keys": ["ctrl", "n"]}), act(typed("k0", 1)), act(typed("k1", 2)),
                    act(typed("k2", 3)))

    result, hands, lines = run(script, plugin=plugin, hands=NewWorkbookHands(plugin), workdir=tmp_path)

    assert result.passed and [a["type"] for a in hands.done] == ["type", "type", "type"]
    assert "refused keypress ctrl+n: That key opens a new workbook outside the lesson. Stay in this one." in lines


class TypingHands(FakeHands):
    """Records every piece of text the agent types, without reading it as a learner's k{n}={v} step, so a
    formula split over several type actions can be watched. The lesson's own k{n}={v} steps still land."""

    def do(self, action):
        if action["type"] == "type" and action["text"].startswith("k") and "=" in action["text"]:
            super().do(action)
        else:
            self.done.append(action)


def test_a_formula_split_over_several_type_actions_is_caught_as_a_whole(tmp_path):
    # Each piece looks harmless on its own; together they spell a banned function in one cell.
    start = {"type": "type", "text": "=WEBSERVICE"}
    rest = {"type": "type", "text": "(A1)"}
    script = Script(act(start, rest), act(typed("k0", 1)), act(typed("k1", 2)), act(typed("k2", 3)))
    plugin = Excel()

    result, hands, lines = run(script, plugin=plugin, hands=TypingHands(plugin), workdir=tmp_path)

    assert result.passed
    assert [a["text"] for a in hands.done] == ["=WEBSERVICE", "k0=1", "k1=2", "k2=3"]   # the rest is refused
    assert "refused type: That text uses WEBSERVICE, which a lesson may not use." in lines


def test_the_typed_record_starts_over_when_the_cell_edit_ends(tmp_path):
    # "=WEBSERVICE" then Enter commits that cell; "(A1)" lands in a fresh cell, so it is allowed.
    start = {"type": "type", "text": "=WEBSERVICE"}
    commit = {"type": "keypress", "keys": ["enter"]}
    rest = {"type": "type", "text": "(A1)"}
    script = Script(act(start, commit, rest), act(typed("k0", 1)), act(typed("k1", 2)), act(typed("k2", 3)))
    plugin = Excel()

    result, hands, lines = run(script, plugin=plugin, hands=TypingHands(plugin), workdir=tmp_path)

    assert result.passed
    assert [a["text"] for a in hands.done if a["type"] == "type"] == ["=WEBSERVICE", "(A1)", "k0=1", "k1=2", "k2=3"]
    assert not any("WEBSERVICE" in line and "refused" in line for line in lines)


def test_typed_text_is_checked_together_with_what_came_before():
    excel = Excel()
    assert tester.allowed({"type": "type", "text": "=WEBSERVICE"}, APP, "mouse", plugin=excel) == (True, "")
    assert tester.allowed({"type": "type", "text": "(A1)"}, APP, "mouse", plugin=excel, typed="=WEBSERVICE") \
        == (False, "That text uses WEBSERVICE, which a lesson may not use.")


def test_a_bare_alt_press_is_refused_so_the_ribbon_key_tips_never_open():
    assert tester.allowed({"type": "keypress", "keys": ["alt"]}, APP, "mouse") == (False, tester.ALT_NOTE)
    assert tester.allowed({"type": "keypress", "keys": ["ALT"]}, APP, "mouse") == (False, tester.ALT_NOTE)
    # Alt held with another key still acts inside the cell (Alt+Enter is a new line), so it stays allowed.
    assert tester.allowed({"type": "keypress", "keys": ["alt", "enter"]}, APP, "mouse") == (True, "")


def test_the_agent_may_not_open_the_ribbon_key_tips_with_a_bare_alt(tmp_path):
    bare_alt = {"type": "keypress", "keys": ["alt"]}
    script = Script(act(bare_alt), act(typed("k0", 1)), act(typed("k1", 2)), act(typed("k2", 3)))
    plugin = Excel()

    result, hands, lines = run(script, plugin=plugin, hands=TypingHands(plugin), workdir=tmp_path)

    assert result.passed
    assert bare_alt not in hands.done
    assert any(line.startswith("refused keypress alt") and line.endswith(tester.ALT_NOTE) for line in lines)


def test_a_formula_typed_one_key_at_a_time_is_caught(tmp_path):
    # The agent presses letter and symbol keys one by one to build a banned function, dodging type actions.
    letters = [{"type": "keypress", "keys": [k]} for k in "=webservice"]
    paren = {"type": "keypress", "keys": ["shift", "9"]}          # "(" completes the call
    script = Script(act(*letters, paren), act(typed("k0", 1)), act(typed("k1", 2)), act(typed("k2", 3)))
    plugin = Excel()

    result, hands, lines = run(script, plugin=plugin, hands=TypingHands(plugin), workdir=tmp_path)

    assert result.passed
    assert paren not in hands.done                               # the key that completes the call is refused
    assert any("uses WEBSERVICE" in line and line.startswith("refused") for line in lines)


def test_keys_that_produce_text_are_checked_together_with_what_came_before():
    excel = Excel()
    assert tester.allowed({"type": "keypress", "keys": ["e"]}, APP, "mouse", plugin=excel, typed="=WEBSERVIC") \
        == (True, "")
    assert tester.allowed({"type": "keypress", "keys": ["shift", "9"]}, APP, "mouse", plugin=excel,
                          typed="=WEBSERVICE") == (False, "That text uses WEBSERVICE, which a lesson may not use.")


def test_the_cursor_cannot_move_or_click_inside_a_formula_being_typed():
    excel = Excel()
    for keys in (["left"], ["right"], ["home"], ["end"], ["backspace"], ["delete"], ["f2"], ["alt", "enter"]):
        assert tester.allowed({"type": "keypress", "keys": keys}, APP, "mouse", plugin=excel, typed="=SUM(A1") \
            == (False, tester.FORMULA_NOTE), keys
    assert tester.allowed(click(5, 5), APP, "mouse", plugin=excel, typed="=SUM(A1") == (False, tester.FORMULA_NOTE)
    # Out of a formula those same keys just move between cells, so they stay allowed.
    assert tester.allowed({"type": "keypress", "keys": ["left"]}, APP, "mouse", plugin=excel) == (True, "")
    assert tester.allowed({"type": "keypress", "keys": ["f2"]}, APP, "mouse", plugin=excel) == (True, "")
    assert tester.allowed(click(5, 5), APP, "mouse", plugin=excel) == (True, "")


def test_a_tab_held_on_any_action_is_refused_while_a_formula_is_being_typed():
    excel = Excel()
    assert tester.allowed({"type": "screenshot", "keys": ["tab"]}, APP, "mouse", plugin=excel, typed="=WEBS") \
        == (False, tester.TAB_NOTE)


def test_tab_is_refused_while_a_formula_is_being_typed():
    excel = Excel()
    # As a keypress, mid-formula: Excel's AutoComplete would finish a function name the agent never spelled out.
    assert tester.allowed({"type": "keypress", "keys": ["tab"]}, APP, "mouse", plugin=excel, typed="=WEBS") \
        == (False, tester.TAB_NOTE)
    # The same Tab buried inside typed text, mid-formula.
    assert tester.allowed({"type": "type", "text": "\t"}, APP, "mouse", plugin=excel, typed="=WEBS") \
        == (False, tester.TAB_NOTE)
    # Tab to move between plain values, with no formula open, is fine.
    assert tester.allowed({"type": "keypress", "keys": ["tab"]}, APP, "mouse", plugin=excel) == (True, "")
    assert tester.allowed({"type": "type", "text": "12\t34"}, APP, "mouse", plugin=excel) == (True, "")


def test_the_agent_may_not_press_tab_to_autocomplete_a_formula(tmp_path):
    start = {"type": "type", "text": "=WEBS"}
    finish = {"type": "keypress", "keys": ["tab"]}
    script = Script(act(start, finish), act(typed("k0", 1)), act(typed("k1", 2)), act(typed("k2", 3)))
    plugin = Excel()

    result, hands, lines = run(script, plugin=plugin, hands=TypingHands(plugin), workdir=tmp_path)

    assert result.passed
    assert finish not in hands.done                      # the Tab never reached the app
    assert any(line.startswith("refused keypress tab") and line.endswith(tester.TAB_NOTE) for line in lines)


class VsCode(Recording):
    app_id, title = "vscode", "VS Code"


class Paint(Recording):
    app_id, title = "paint", "Paint"


@pytest.mark.parametrize("plugin, why", [
    (VsCode(), "its terminal would let the agent run any command on this computer, with your Meta key in reach"),
    (Paint(), "nobody has checked yet what the agent could reach there"),
])
def test_the_agent_plays_lessons_only_in_apps_checked_for_it(tmp_path, plugin, why):
    script, hands = Script(), FakeHands(plugin)

    with pytest.raises(tester.NotForAgent) as refused:
        run(script, plugin=plugin, hands=hands, workdir=tmp_path)

    assert str(refused.value) == f"Meta's agent does not test {plugin.title} lessons: {why}."
    assert not hasattr(plugin, "opened") and script.calls == [] and hands.done == [] and hands.grabs == []


def test_an_app_that_will_not_open_stops_the_test_with_its_own_words_kept_apart(tmp_path):
    class WontOpen(Recording):
        def open(self, *args, **kwargs):
            raise OSError("(-2147352567, 'Exception occurred.', None, None)")

    with pytest.raises(ProveError) as caught:
        run(Script(), plugin=WontOpen(), workdir=tmp_path)

    assert str(caught.value) == "Fake app could not be opened."            # plain, for the screen
    assert caught.value.detail == "Fake app could not be opened: (-2147352567, 'Exception occurred.', None, None)"


def test_an_app_that_cannot_be_read_stops_the_test_with_its_own_words_kept_apart(tmp_path):
    class Unreadable(Recording):
        def open(self, *args, **kwargs):
            session = super().open(*args, **kwargs)
            broken = Future()
            broken.set_exception(OSError("the workbook is busy"))
            session.read_now = lambda: broken
            return session

    with pytest.raises(ProveError) as caught:
        run(Script(), plugin=Unreadable(), workdir=tmp_path)

    assert str(caught.value) == "Fake app could not be read."
    assert caught.value.detail == "Fake app could not be read: the workbook is busy"
