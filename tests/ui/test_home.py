"""The home screen, used the way a learner uses it: what it shows in each home state, and what each part
asks the backend to do."""
import copy
import time

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QWheelEvent
from PySide6.QtQuick import QQuickItem, QQuickWindow  # noqa: F401  (so windows come back as Quick windows)
from PySide6.QtTest import QTest

from app.ui.app import load_window, make_engine
from app.ui.bridge import Bridge
from app.ui.demo_backend import DemoBackend

LINK = "https://www.youtube.com/watch?v=k7RM-ot2NWY"


def _settle(qapp, seconds=0.06):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.005)


@pytest.fixture
def home(qapp):
    """Opens the home window in a demo state at its full size, as the program does, and closes it after."""
    opened = []

    def open_home(state, wait=0.4, size=(1120, 720)):
        backend = DemoBackend(state)
        bridge = Bridge(backend)
        engine = make_engine(bridge)
        root = load_window(engine, "home", backend.view.get("home"))
        assert root is not None, f"the home window did not load in {state}"
        root.setWidth(size[0])
        root.setHeight(size[1])
        backend.replay()
        _settle(qapp, wait)
        opened.append((root, engine))
        return backend, bridge, root

    yield open_home
    for root, engine in opened:
        root.close()
        root.deleteLater()
        engine.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)    # no event loop runs to do it


def _items(item):
    yield item
    for child in item.childItems():
        yield from _items(child)


def _shown(item) -> bool:
    """Whether the learner can see the item: it and every parent are visible and not faded out."""
    if not item.isVisible():
        return False
    while item is not None:
        if item.opacity() < 0.05:
            return False
        item = item.parentItem()
    return True


def _is_text(item) -> bool:
    name = item.metaObject().className()
    return name == "QQuickText" or name.startswith("QQuickText_QML")


def _texts(root) -> list[str]:
    return [i.property("text") for i in _items(root.contentItem())
            if _is_text(i) and _shown(i) and i.property("text")]


def _text_item(root, text):
    found = [i for i in _items(root.contentItem()) if _is_text(i) and i.property("text") == text and _shown(i)]
    assert found, f"no {text!r} on the home screen; it shows {_texts(root)}"
    return found[0]


def _of(root, kind):
    return [i for i in _items(root.contentItem()) if i.metaObject().className().startswith(kind) and _shown(i)]


def _buttons(root) -> list[str]:
    return [b.property("text") for b in _of(root, "ChunkyButton")]


def _button(root, text):
    found = [b for b in _of(root, "ChunkyButton") if b.property("text") == text]
    assert found, f"no {text!r} button on the home screen; it shows {_buttons(root)}"
    return found[0]


def _click(qapp, root, item):
    centre = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
    QTest.mouseClick(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centre)
    _settle(qapp, 0.3)


def _scroll_to(qapp, root, item):
    """Turns the mouse wheel over the page until `item` is wholly inside the window, then waits for the page
    to stop gliding: a click on a moving page only stops it."""
    for _ in range(40):
        if _scene_rect(item).bottom() <= root.height() - 8:
            was = None
            while was != _scene_rect(item).y():
                was = _scene_rect(item).y()
                _settle(qapp, 0.1)
            return
        centre = QPointF(root.width() / 2, root.height() / 2)
        wheel = QWheelEvent(centre, root.mapToGlobal(centre), QPoint(0, 0), QPoint(0, -120),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase,
                            False)
        QGuiApplication.sendEvent(root, wheel)
        _settle(qapp, 0.05)
    raise AssertionError("could not scroll the item into view")


def _link_field(root):
    found = [i for i in _items(root.contentItem())
             if i.metaObject().className() == "QQuickTextInput" and _shown(i)]
    assert found, f"no link field on the home screen; it shows {_texts(root)}"
    return found[0]


def _type(qapp, root, text):
    for letter in text:                 # keyClicks only takes widgets; one key at a time works on a window
        QTest.keyClick(root, letter)
    _settle(qapp, 0.05)


def _scene_rect(item) -> QRectF:
    return item.mapRectToScene(QRectF(0, 0, item.width(), item.height()))


# The top of the screen.

def test_the_top_greets_you_and_shows_your_streak_and_todays_points(home):
    _, _, root = home("home_progress")
    texts = _texts(root)
    assert "Hi Ranvir" in texts
    assert "days in a row" in texts
    assert "30 points today" in texts and "Your goal is 50" in texts


def test_with_no_streak_yet_the_top_invites_you_to_start_one(home):
    _, _, root = home("first_run")
    assert "Start a streak today" in _texts(root)


def test_the_sound_switch_asks_the_backend(home, qapp):
    backend, _, root = home("home_progress")
    switch = [b for b in _of(root, "IconButton") if b.property("label") == "Turn sound off"]
    assert switch, "no sound switch at the top"
    _click(qapp, root, switch[0])
    assert ("set_muted", (True,)) in backend.actions


# Continue, or the first lesson.

def test_continue_names_the_lesson_and_step_and_carries_on(home, qapp):
    backend, _, root = home("home_progress")
    assert "Monthly budget, step 4 of 9" in _texts(root)
    _click(qapp, root, _button(root, "Continue"))
    assert ("continue_lesson", ()) in backend.actions


def test_on_the_first_run_the_first_lesson_is_offered_instead(home, qapp):
    backend, _, root = home("first_run")
    assert "Continue" not in _buttons(root)
    assert "Start with Grade sheet" in _texts(root)
    _click(qapp, root, _button(root, "Start"))
    assert ("open_lesson", ("grade-sheet",)) in backend.actions


def _holder(item, kind):
    """The nearest part of the screen of type `kind` that holds `item`."""
    while item is not None and not item.metaObject().className().startswith(kind):
        item = item.parentItem()
    assert item is not None, f"nothing of type {kind} holds it"
    return item


def test_continue_is_the_biggest_thing_on_the_screen(home):
    _, _, root = home("home_progress")
    resume = _holder(_text_item(root, "Monthly budget, step 4 of 9"), "ContinueCard")
    for title in ("Excel", "Python in VS Code", "Build with Meta's AI"):
        course = _holder(_text_item(root, title), "CourseCard")
        assert resume.width() * resume.height() > course.width() * course.height(), title


# The course shelf and a course's path.

def test_the_shelf_shows_each_course_with_its_credits_and_what_is_coming(home):
    _, _, root = home("home_progress")
    texts = _texts(root)
    for title in ("Excel", "Python in VS Code", "Build with Meta's AI"):
        assert title in texts
    assert "From videos by Sheet School and Priya Makes Spreadsheets" in texts
    assert "From videos by Code With Tomas" in texts
    assert "Coming soon" in texts
    assert "1 of 6" in texts


def test_the_course_you_are_in_shows_its_lessons_in_miniature_with_who_made_it_at_the_foot(home):
    _, _, root = home("home_progress")
    card = _scene_rect(_holder(_text_item(root, "Excel"), "CourseCard"))
    minis = [m for m in _of(root, "MiniPath") if card.contains(_scene_rect(m))]
    assert minis, "the Excel card does not show its lessons in miniature"
    assert minis[0].property("count") == 6 and minis[0].property("current") == 1
    credits = _scene_rect(_text_item(root, "From videos by Sheet School and Priya Makes Spreadsheets"))
    assert card.bottom() - credits.bottom() <= 24 + 4 + 2, "who made the videos is not at the foot of the card"


def test_the_course_you_are_in_names_the_lesson_up_next_even_with_no_credits(home, qapp):
    _, _, root = home("home_progress")
    card = _holder(_text_item(root, "Excel"), "CourseCard")
    inside = _scene_rect(card)
    up_next = _scene_rect(_text_item(root, "Up next"))
    assert inside.contains(up_next) and inside.contains(_scene_rect(_text_item(root, "Monthly budget")))
    assert _texts(root).count("Up next") == 1, "a small card names its next lesson too"

    card.setProperty("course", {**_long_course(3, 1), "credits": []})       # a course with no credits
    _settle(qapp)
    lesson = _scene_rect(_text_item(root, "Lesson 1"))
    assert _scene_rect(card).bottom() - lesson.bottom() <= 24 + 4 + 2, "the lesson up next is not at the foot"


def test_the_lesson_up_next_comes_back_after_a_course_had_nothing_up_next(home, qapp):
    _, _, root = home("home_progress")
    card = _holder(_text_item(root, "Excel"), "CourseCard")
    finished = {**_long_course(1, 0), "credits": []}
    finished["lessons"] = [{**finished["lessons"][0], "state": "done"}]
    card.setProperty("course", finished)                                  # all done, no credits: an empty foot
    _settle(qapp)
    card.setProperty("course", {**_long_course(1, 0), "credits": []})     # then a lesson is up next again
    _settle(qapp)
    lesson = _scene_rect(_text_item(root, "Lesson 0"))
    assert _scene_rect(card).contains(lesson) and "Up next" in _texts(root)


def _long_course(count, done):
    states = ["done"] * done + ["current"] + ["locked"] * (count - done - 1)
    return {"id": "excel", "title": "Excel", "colour": "courseExcel", "credits": ["Sheet School"], "ready": True,
            "lessons": [{"id": f"lesson-{i}", "title": f"Lesson {i}", "state": s} for i, s in enumerate(states)]}


def test_a_longer_course_keeps_its_lessons_apart_and_a_very_long_one_shows_a_bar(home, qapp):
    _, _, root = home("home_progress")
    card = _holder(_text_item(root, "Excel"), "CourseCard")
    card.setProperty("course", _long_course(12, 5))
    _settle(qapp)
    minis = _of(root, "MiniPath")
    assert minis, "a 12 lesson course does not show its lessons in miniature"
    dots = sorted((_scene_rect(d) for d in minis[0].childItems() if d.property("kind") is not None),
                  key=lambda r: r.x())
    assert len(dots) == 12
    assert all(_scene_rect(card).contains(d) for d in dots), "a lesson dot spills out of the card"
    assert all(a.right() < b.left() for a, b in zip(dots, dots[1:])), "the lesson dots run into each other"

    card.setProperty("course", _long_course(40, 12))
    _settle(qapp)
    assert not _of(root, "MiniPath"), "40 lessons are squeezed into the miniature"
    assert "12 of 40" in _texts(root)


def test_opening_a_course_shows_its_winding_path_with_the_mascot_on_your_lesson(home, qapp):
    _, _, root = home("home_progress")
    _click(qapp, root, _text_item(root, "Excel"))
    nodes = _of(root, "PathNode")
    assert [n.property("state") for n in nodes] == ["done", "current"] + ["locked"] * 4
    assert "proven and tested" in _texts(root)
    centres = [_scene_rect(n).center() for n in nodes]
    assert len({round(c.y()) for c in centres}) > 1, "the path is a straight line, not a winding one"
    mascot = _of(root, "Mascot")
    assert mascot, "the mascot is not on the path"
    sits = _scene_rect(mascot[0])
    current = _scene_rect(nodes[1])
    assert abs(sits.center().x() - current.center().x()) < 4
    assert current.top() - 24 <= sits.bottom() <= current.top() + 40, "the mascot is not sitting on the circle"


def test_a_lesson_on_the_path_opens_and_a_locked_one_does_not(home, qapp):
    backend, _, root = home("home_progress")
    _click(qapp, root, _text_item(root, "Excel"))
    nodes = _of(root, "PathNode")
    _click(qapp, root, nodes[3])
    assert not [a for a in backend.actions if a[0] == "open_lesson"]
    _click(qapp, root, nodes[1])
    assert ("open_lesson", ("monthly-budget",)) in backend.actions


def test_all_courses_goes_back_to_the_shelf(home, qapp):
    _, _, root = home("home_progress")
    _click(qapp, root, _text_item(root, "Excel"))
    _click(qapp, root, _button(root, "All courses"))
    assert not _of(root, "PathNode")
    assert "Coming soon" in _texts(root)


def test_a_course_that_is_coming_soon_does_not_open(home, qapp):
    _, _, root = home("home_progress")
    _click(qapp, root, _text_item(root, "Build with Meta's AI"))
    assert "All courses" not in _buttons(root)


def test_a_course_with_no_lessons_invites_you_to_make_one(home, qapp):
    _, _, root = home("course_empty")
    assert "No lessons here yet" in _texts(root)
    _click(qapp, root, _button(root, "Make a lesson"))
    assert "Coming soon" in _texts(root)                              # back on the shelf
    assert _link_field(root).hasActiveFocus(), "the link field is not ready to paste into"


# Tips.

def test_tips_show_what_meta_wrote_from_your_tries(home):
    _, _, root = home("home_progress")
    assert "Formulas: fast. Charts took 3 tries. Try the chart review next." in _texts(root)


def _with_claude(qapp, backend, **over):
    state = {**backend.home(), "ai": "claude", **over}
    backend._publish(home=state)
    _settle(qapp, 0.1)


def test_tips_name_the_ai_that_wrote_them(home, qapp):
    backend, _, root = home("home_progress")
    assert "From Meta's AI" in _texts(root)
    _with_claude(qapp, backend)
    texts = _texts(root)
    assert "From Claude" in texts and "From Meta's AI" not in texts


def test_with_claude_unreachable_tips_name_claude(home, qapp):
    backend, _, root = home("home_offline")
    _with_claude(qapp, backend)
    assert "Claude can't be reached right now. Lessons still work." in _texts(root)


def test_with_claude_and_no_key_the_card_asks_for_the_claude_key_and_copies_its_line(home, qapp):
    backend, _, root = home("home_no_key")
    _with_claude(qapp, backend)
    texts = _texts(root)
    assert "Add your Claude key" in texts and "Add your Meta key" not in texts
    assert "Tips and the Ask box need it." in texts
    QGuiApplication.clipboard().clear()
    _click(qapp, root, _button(root, "Copy the setup line"))
    assert QGuiApplication.clipboard().text() == \
        '[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "<your key>", "User")'


def test_with_no_finished_lesson_tips_say_how_to_get_them(home):
    _, _, root = home("first_run")
    assert "Finish a lesson to get tips" in _texts(root)


def test_when_meta_cannot_be_reached_tips_say_lessons_still_work(home):
    _, _, root = home("home_offline")
    assert "Meta can't be reached right now. Lessons still work." in _texts(root)


def test_loading_tips_show_a_calm_placeholder_only_after_200_ms(home, qapp):
    backend, _, root = home("home_progress")
    state = backend.home()
    state["tips"] = {"state": "loading", "text": ""}
    backend._publish(home=state)
    _settle(qapp, 0.1)
    assert "Looking at your tries" not in _texts(root)
    _settle(qapp, 0.25)
    assert "Looking at your tries" in _texts(root)


def test_without_a_meta_key_the_card_says_how_to_add_one_and_copies_the_line(home, qapp):
    backend, _, root = home("home_no_key")
    texts = _texts(root)
    assert "Add your Meta key" in texts
    assert "Paste it in PowerShell, put your key in it, and press Enter." in texts
    assert "Make a lesson" not in _buttons(root)
    assert "Tips for you" not in texts
    QGuiApplication.clipboard().clear()
    _click(qapp, root, _button(root, "Copy the setup line"))
    assert QGuiApplication.clipboard().text() ==         '[Environment]::SetEnvironmentVariable("META_API_KEY", "<your key>", "User")'
    assert "Copied" in _buttons(root)
    assert ("key_setup_copied", ()) in backend.actions        # so the key is looked for again


# Making a lesson from a video.

def test_a_pasted_link_makes_a_lesson_and_its_stages_show(home, qapp):
    backend, _, root = home("home_progress")
    _click(qapp, root, _link_field(root))
    _type(qapp, root, LINK)
    _click(qapp, root, _button(root, "Make a lesson"))
    assert ("make_lesson", (LINK,)) in backend.actions
    assert _of(root, "StageList"), "the stages do not show"
    assert "Getting the video" in _texts(root)


def test_a_link_that_is_not_from_youtube_is_named_and_not_sent(home, qapp):
    backend, _, root = home("home_progress")
    _click(qapp, root, _link_field(root))
    _type(qapp, root, "my budget video")
    _click(qapp, root, _button(root, "Make a lesson"))
    assert not [a for a in backend.actions if a[0] == "make_lesson"]
    assert "That link isn't from YouTube. Copy it from the video's page." in _texts(root)


def test_a_lesson_being_made_shows_each_stage_live(home):
    _, _, root = home("factory_running")
    texts = _texts(root)
    assert "Writing the steps" in texts and "Writing step 5 of 9" in texts
    assert "Make a lesson" not in _buttons(root)


def test_a_video_that_cannot_become_a_lesson_says_why_and_offers_another(home, qapp):
    backend, _, root = home("factory_not_ready")
    assert backend.home()["factory"]["reason"] in _texts(root)
    _click(qapp, root, _button(root, "Try another video"))
    assert _link_field(root).hasActiveFocus()
    assert ("dismiss_factory", ()) in backend.actions


def test_a_reason_that_is_already_under_its_stage_is_not_said_twice(home, qapp):
    backend, _, root = home("factory_not_ready")
    state = copy.deepcopy(backend.home())
    [failed] = [s for s in state["factory"]["stages"] if s["state"] == "failed"]
    failed["detail"] = state["factory"]["reason"] = "This video is private."
    backend._publish(home=state)
    _settle(qapp)
    assert _texts(root).count("This video is private.") == 1


def test_a_ready_lesson_lands_on_the_shelf_with_a_short_highlight(home, qapp):
    backend, _, root = home("factory_running")
    state = copy.deepcopy(backend.home())
    state["courses"][0]["lessons"].append(
        {"id": "pivot-tables", "title": "Sum up with a pivot table", "state": "locked", "badge": "proven"})
    state["factory"] = {**state["factory"], "state": "ready", "lessonId": "pivot-tables",
                        "stages": [{**s, "state": "done"} for s in state["factory"]["stages"]]}
    backend._publish(home=state)
    _settle(qapp, 0.3)
    texts = _texts(root)
    assert "Your lesson is ready" in texts
    assert "Sum up with a pivot table is on your Excel shelf." in texts
    glow = [i for i in _items(root.contentItem()) if i.objectName() == "highlight" and _shown(i)]
    assert glow, "the course the lesson landed in is not highlighted"
    assert _scene_rect(glow[0]).contains(_scene_rect(_text_item(root, "Excel")).center())
    _click(qapp, root, _button(root, "Open the lesson"))
    assert ("open_lesson", ("pivot-tables",)) in backend.actions
    assert ("dismiss_factory", ()) in backend.actions
    _settle(qapp, 1.6)
    assert not [i for i in _items(root.contentItem()) if i.objectName() == "highlight" and _shown(i)]



# Your common mistakes.

def test_your_common_mistakes_name_each_step_its_slip_its_tries_and_a_tip(home):
    _, _, root = home("home_progress")
    texts = _texts(root)
    assert "Your common mistakes" in texts and "From your checks" in texts
    assert "Add up the amounts in B8." in texts
    assert "Typed the answer instead of a formula" in texts
    assert "Took 3 tries" in texts
    assert "Start with = so Excel works it out and keeps it up to date." in texts
    assert "Monthly budget, step 2" in texts


def test_practise_this_again_reopens_that_lesson_at_that_step(home, qapp):
    backend, _, root = home("home_progress")
    buttons = [b for b in _of(root, "ChunkyButton") if b.property("text") == "Practise this again"]
    assert len(buttons) == 2                          # the step got right since has none
    _scroll_to(qapp, root, buttons[0])                # the card sits under your courses
    _click(qapp, root, buttons[0])
    assert ("practise", ("monthly-budget", 1)) in backend.actions


def test_a_step_got_right_since_says_so(home):
    _, _, root = home("home_progress")
    assert "Got it right last time" in _texts(root)


def test_with_no_mistakes_yet_a_friendly_line_says_where_they_will_show(home):
    _, _, root = home("first_run")
    assert "Your common mistakes" in _texts(root)
    assert "No mistakes yet. Steps that take a few tries show up here, with a tip." in _texts(root)
    assert "Practise this again" not in _buttons(root)


# Long text and small windows.

def _inside(root):
    width = root.width()
    out = []
    for item in _items(root.contentItem()):
        if _is_text(item) and _shown(item) and item.property("text"):
            r = _scene_rect(item)
            painted = min(r.width(), item.property("contentWidth"))
            if r.left() < 0 or r.left() + painted > width + 0.5:
                out.append(item.property("text"))
    return out


def test_very_long_words_stay_inside_the_window(home):
    _, _, root = home("home_long_text")
    assert _inside(root) == []
    name = [t for t in _of(root, "QQuickText") if (t.property("text") or "").startswith("Hi ")]
    assert name and name[0].property("truncated"), "a very long name is not cut short"


def test_a_small_window_still_shows_everything_inside_it(home, qapp):
    _, _, root = home("home_progress", size=(760, 560))
    assert _inside(root) == []
    assert "Continue" in _buttons(root) and "Coming soon" in _texts(root)
