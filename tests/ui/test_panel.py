"""The lesson panel, driven the way a learner uses it: what it shows in each lesson state, and what each
button asks the backend to do."""
import time

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPointF, QRectF, Qt, QUrl, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtQuick import QQuickItem, QQuickWindow  # noqa: F401  (so windows come back as Quick windows)
from PySide6.QtTest import QTest

from app.ui.app import load_window, make_engine
from app.ui.bridge import Bridge
from app.ui.demo_backend import DemoBackend


def _settle(qapp, seconds=0.06):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.005)


@pytest.fixture
def panel(qapp):
    """Opens the panel in a demo state, as the program does, and closes it afterwards."""
    opened = []

    def open_panel(state, wait=0.4):
        backend = DemoBackend(state)
        bridge = Bridge(backend)
        engine = make_engine(bridge)
        root = load_window(engine, "panel", backend.view.get("panel"))
        assert root is not None, f"the panel did not load in {state}"
        backend.replay()
        _settle(qapp, wait)
        opened.append((root, engine))
        return backend, bridge, root

    yield open_panel
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


def _texts(root) -> list[str]:
    return [i.property("text") for i in _items(root.contentItem())
            if i.metaObject().className() == "QQuickText" and _shown(i) and i.property("text")]


def _text_item(root, text):
    found = [i for i in _items(root.contentItem())
             if i.metaObject().className() == "QQuickText" and i.property("text") == text and _shown(i)]
    assert found, f"no {text!r} on the panel; it shows {_texts(root)}"
    return found[0]


def _button(root, text):
    found = [i for i in _items(root.contentItem())
             if i.metaObject().className().startswith("ChunkyButton") and i.property("text") == text and _shown(i)]
    assert found, f"no {text!r} button on the panel; it shows {_texts(root)}"
    return found[0]


def _click(qapp, root, item):
    centre = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
    QTest.mouseClick(root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, centre)
    _settle(qapp, 0.3)


def _mascot(root):
    return next(i for i in _items(root.contentItem()) if i.metaObject().className().startswith("Mascot"))


def test_the_step_says_what_to_do_why_and_how_far_along_you_are(panel):
    _, _, root = panel("lesson_step")
    texts = _texts(root)
    assert "Add up the amounts in B8." in texts
    assert "A formula keeps the total right when amounts change." in texts
    assert "2 of 9" in texts


def _chips(root):
    return [i for i in _items(root.contentItem()) if i.metaObject().className().startswith("GoalChip") and _shown(i)]


def test_the_goal_comes_first_then_folds_to_a_short_chip_that_opens_with_a_tap(panel, qapp):
    sentence = "Make a monthly budget that adds itself up and shows where money goes."
    _, _, root = panel("lesson_goal")
    assert not _text_item(root, sentence).property("truncated")       # step 1: the whole goal
    _, _, root = panel("lesson_step")
    folded = _text_item(root, sentence)
    assert _chips(root), "after step 1 the goal is not folded into its chip"
    assert not folded.property("truncated") and folded.property("lineCount") <= 3   # still whole, short
    _click(qapp, root, folded)
    assert not _chips(root), "a tap on the chip did not open the goal"


def test_show_me_and_hint_ask_the_backend_and_the_hint_appears(panel, qapp):
    backend, _, root = panel("lesson_step")
    _click(qapp, root, _button(root, "Show me"))
    assert ("show_me", ()) in backend.actions
    _click(qapp, root, _button(root, "Hint"))
    assert ("next_hint", ()) in backend.actions
    assert "Click B8, below the amounts." in _texts(root)
    assert "Show another hint (2 left)" in [b.property("text") for b in _items(root.contentItem())
                                            if b.metaObject().className().startswith("ChunkyButton") and _shown(b)]


def test_with_every_hint_shown_the_hint_button_says_so_and_lines_up_with_show_me(panel):
    _, _, root = panel("long_text")
    assert not _button(root, "No hints left").property("enabled")

    def middle(text):
        label = _text_item(root, text)
        return label.mapToScene(QPointF(0, label.height() / 2)).y()

    assert abs(middle("No hints left") - middle("Show me")) < 0.5


def _scroller(root):
    return next(i for i in _items(root.contentItem()) if i.metaObject().className() == "QQuickFlickable")


def test_a_lesson_opened_with_hints_already_shown_starts_at_the_top(panel):
    _, _, root = panel("long_text", wait=0.6)
    scroller = _scroller(root)
    assert scroller.property("contentHeight") > scroller.height()     # there is somewhere to scroll to
    assert scroller.property("contentY") == 0


def test_a_new_hint_below_the_fold_scrolls_into_view(panel, qapp):
    _, _, root = panel("lesson_hints")
    root.setHeight(480)                                               # a short screen: the step reaches the Ask box
    _settle(qapp, 0.1)
    scroller = _scroller(root)
    assert scroller.property("contentY") == 0
    _click(qapp, root, _button(root, "Hint"))                      # the one in view; it asks for the same
    _settle(qapp, 0.4)
    assert scroller.property("contentY") > 0


def test_the_mouse_wheel_scrolls_the_panel(panel, qapp):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QWheelEvent
    _, _, root = panel("long_text", wait=0.6)
    scroller = _scroller(root)
    middle = scroller.mapToScene(QPointF(scroller.width() / 2, scroller.height() / 2))
    wheel = QWheelEvent(middle, root.mapToGlobal(middle), QPoint(0, 0), QPoint(0, -240),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase,
                        False)
    QCoreApplication.sendEvent(root, wheel)
    _settle(qapp, 0.4)
    assert scroller.property("contentY") > 0


def test_everything_scrolls_clear_of_a_tall_not_yet_banner(panel, qapp):
    _, _, root = panel("long_text")
    banner = next(i for i in _items(root.contentItem()) if i.metaObject().className().startswith("Banner"))
    scroller = _scroller(root)
    scroller.setProperty("contentY", max(0.0, scroller.property("contentHeight") - scroller.height()))
    _settle(qapp, 0.1)
    content = scroller.property("contentItem").childItems()[0]
    last = [i for i in content.childItems() if i.isVisible()][-1]
    bottom = last.mapToScene(QPointF(0, last.height())).y()
    assert bottom <= banner.y(), f"the last card ends at {bottom}, under the banner at {banner.y()}"


def test_a_step_without_a_clip_has_no_clip_button(panel):
    _, _, root = panel("lesson_step")
    buttons = [b.property("text") for b in _items(root.contentItem())
               if b.metaObject().className().startswith("ChunkyButton") and _shown(b)]
    assert "Watch the clip" not in buttons and "Show me" in buttons


class _Browser(QObject):
    def __init__(self):
        super().__init__()
        self.opened = []

    @Slot(QUrl)
    def open(self, url):
        self.opened.append(url.toString())


def test_a_missing_clip_offers_the_video_in_the_browser(panel, qapp):
    browser = _Browser()
    QDesktopServices.setUrlHandler("https", browser, "open")
    try:
        backend, _, root = panel("lesson_clip_missing")
        _click(qapp, root, _button(root, "Get the video"))
    finally:
        QDesktopServices.unsetUrlHandler("https")
    assert browser.opened == [backend.lesson()["step"]["clip"]["videoUrl"]]


_SCHEMES = ("https", "http", "file", "ms-msdt", "javascript")


def test_only_a_youtube_link_is_ever_opened(qapp):
    browser = _Browser()
    for scheme in _SCHEMES:
        QDesktopServices.setUrlHandler(scheme, browser, "open")
    try:
        bridge = Bridge(DemoBackend("lesson_clip_missing"))
        for bad in ("file:///C:/Windows/System32/calc.exe", "ms-msdt:/id PCWDiagnostic", "javascript:alert(1)",
                    "https://youtube.com.example.net/watch?v=demo", "https://example.net/youtube.com/watch",
                    "https://someone@www.youtube.com/watch?v=demo", "https://www.youtube.com:8080/watch?v=demo",
                    "", "youtube"):
            assert not bridge.isVideoLink(bad), bad
            bridge.openVideo(bad)
        for good in ("https://www.youtube.com/watch?v=demo&t=12s", "https://youtu.be/demo?t=12",
                     "https://m.youtube.com/watch?v=demo", "http://youtube.com/watch?v=demo",
                     "www.youtube.com/watch?v=demo"):
            assert bridge.isVideoLink(good), good
            bridge.openVideo(good)
    finally:
        for scheme in _SCHEMES:
            QDesktopServices.unsetUrlHandler(scheme)
    assert browser.opened == ["https://www.youtube.com/watch?v=demo&t=12s", "https://youtu.be/demo?t=12",
                              "https://m.youtube.com/watch?v=demo", "https://youtube.com/watch?v=demo",
                              "https://www.youtube.com/watch?v=demo"]          # always over https


def test_a_clip_with_a_strange_link_offers_no_button(panel, qapp):
    from app.ui.demo_backend import _lesson, _step_view
    backend, _, root = panel("lesson_clip_missing")
    step = _step_view(1, clip="missing")
    step["clip"]["videoUrl"] = "file:///C:/Windows/System32/calc.exe"
    backend._publish(lesson=_lesson(1, step=step))
    _settle(qapp, 0.3)
    assert "This step's video isn't saved\non this computer." in _texts(root)
    assert "Get the video" not in [b.property("text") for b in _items(root.contentItem())
                                   if b.metaObject().className().startswith("ChunkyButton") and _shown(b)]


def test_the_clip_button_opens_and_hides_the_clip(panel, qapp):
    backend, _, root = panel("lesson_clip_missing")
    _click(qapp, root, _button(root, "Hide the clip"))
    assert "Get the video" not in [b.property("text") for b in _items(root.contentItem())
                                   if b.metaObject().className().startswith("ChunkyButton") and _shown(b)]
    _click(qapp, root, _button(root, "Watch the clip"))
    assert ("watch_clip", ()) in backend.actions
    _button(root, "Get the video")


def test_a_closed_app_says_so_and_reopens_it(panel, qapp):
    backend, _, root = panel("lesson_app_closed")
    assert "Excel was closed" in _texts(root)
    _click(qapp, root, _button(root, "Reopen Excel"))
    assert ("reopen_app", ()) in backend.actions


def test_a_step_that_came_undone_is_named(panel):
    _, _, root = panel("lesson_changed")
    assert any(t.startswith("Step 2 changed.") for t in _texts(root))
    _, _, root = panel("long_text")
    assert any(t.startswith("Steps 1 and 2 changed.") for t in _texts(root))


def test_a_right_try_cheers_and_floats_ten_points(panel):
    _, _, root = panel("lesson_right", wait=0.1)
    texts = _texts(root)
    assert "+10" in texts
    assert any(word in texts for word in ("Nailed it!", "That's it!", "Spot on!", "You got it!"))


def test_the_ten_points_ride_up_with_the_banner_not_ahead_of_it(panel, qapp):
    from app.ui.demo_backend import _banner, _lesson
    backend, _, root = panel("lesson_step")
    backend._publish(lesson=_lesson(1, banner=_banner("right", "", 1), points=20), cue="right")
    _settle(qapp, 0.06)                                               # the banner is still sliding up
    banner = next(i for i in _items(root.contentItem()) if i.metaObject().className().startswith("Banner"))
    sheet_top = banner.childItems()[0].mapToScene(QPointF(0, 0)).y()
    points = _text_item(root, "+10")
    middle = points.mapToScene(QPointF(0, points.height() / 2)).y()
    assert middle >= sheet_top, f"+10 floats at {middle}, above the banner's top at {sheet_top}"


def test_not_yet_is_gentle_and_can_be_put_away(panel, qapp):
    _, _, root = panel("lesson_not_yet")
    texts = _texts(root)
    assert "Not yet" in texts and "Your total skips B6. Include Fun too." in texts
    _click(qapp, root, _button(root, "Try again"))
    assert "Not yet" not in _texts(root)


def test_the_same_mistake_again_shows_not_yet_again(panel, qapp):
    from app.ui.demo_backend import _lesson
    backend, _, root = panel("lesson_not_yet")
    mistake = backend.lesson()["banner"]
    _click(qapp, root, _button(root, "Try again"))
    backend._publish(cue="not_yet")             # the same wrong try: the lesson is unchanged, only the sound
    _settle(qapp, 0.4)
    assert "Not yet" in _texts(root)
    _click(qapp, root, _button(root, "Try again"))
    backend._publish(lesson=_lesson(1))         # the banner goes while the learner edits the cell
    _settle(qapp, 0.1)
    backend._publish(lesson=_lesson(1, banner=mistake))
    _settle(qapp, 0.4)
    assert "Not yet" in _texts(root)


def test_asking_sends_the_question_and_shows_the_answer(panel, qapp):
    backend, _, root = panel("lesson_step")
    field = next(i for i in _items(root.contentItem()) if i.metaObject().className() == "QQuickTextInput")
    _click(qapp, root, field)
    for letter in "Why B8?":            # keyClicks only takes widgets; one key at a time works on a window
        QTest.keyClick(root, letter)
    QTest.keyClick(root, Qt.Key.Key_Return)
    _settle(qapp, 0.1)
    assert ("ask", ("Why B8?",)) in backend.actions
    assert "Why B8?" in _texts(root)
    _settle(qapp, 1.4)
    assert "Look at the step's check: it reads B8's formula, not the number." in _texts(root)


def test_the_ask_box_lets_go_of_the_keyboard_once_you_are_done_typing(panel, qapp):
    backend, _, root = panel("lesson_step")
    field = next(i for i in _items(root.contentItem()) if i.metaObject().className() == "QQuickTextInput")
    _click(qapp, root, field)
    assert field.hasActiveFocus()
    for letter in "Why?":
        QTest.keyClick(root, letter)
    QTest.keyClick(root, Qt.Key.Key_Return)                 # sent
    _settle(qapp, 0.05)
    assert ("ask", ("Why?",)) in backend.actions
    assert not field.hasActiveFocus()
    _click(qapp, root, field)
    QTest.keyClick(root, Qt.Key.Key_Escape)                 # changed your mind
    _settle(qapp, 0.05)
    assert not field.hasActiveFocus()
    _click(qapp, root, field)
    _click(qapp, root, _button(root, "Show me"))            # pressed something else in the panel
    assert not field.hasActiveFocus()
    assert ("show_me", ()) in backend.actions               # and the press still did its job


def test_the_finished_lesson_celebrates_and_offers_what_next(panel, qapp):
    backend, _, root = panel("lesson_complete", wait=1.6)
    texts = _texts(root)
    for shown in ("90", "6:12", "7 of 9", "5"):
        assert shown in texts
    _click(qapp, root, _button(root, "Next lesson"))
    assert ("next_lesson", ()) in backend.actions
    backend, _, root = panel("lesson_complete", wait=1.6)
    _click(qapp, root, _button(root, "Home"))
    assert ("go_home", ()) in backend.actions


def test_the_mascot_rests_on_the_step_card_and_hides_while_it_is_out(panel, qapp):
    _, bridge, root = panel("lesson_step")
    mascot = _mascot(root)
    assert _shown(mascot)
    home, window = bridge.mascotHome, QRectF(root.geometry())
    assert window.contains(home) and home.center().x() > window.center().x()   # in the panel, on the right
    spot = mascot.mapToScene(QPointF(0, 0))
    assert (home.x(), home.y()) == (window.x() + spot.x(), window.y() + spot.y())
    bridge.mascotAway = True
    _settle(qapp)
    assert not _shown(mascot)


def test_close_and_mute_ask_the_backend(panel, qapp):
    backend, _, root = panel("lesson_step")
    buttons = {i.property("label"): i for i in _items(root.contentItem())
               if i.metaObject().className().startswith("IconButton")}
    _click(qapp, root, buttons["Turn sound off"])
    assert ("set_muted", (True,)) in backend.actions
    _click(qapp, root, buttons["Close the lesson"])
    assert ("close_lesson", ()) in backend.actions


def test_the_app_says_why_it_closed_when_it_knows(panel, qapp):
    from app.ui.demo_backend import _lesson
    backend, _, root = panel("lesson_app_closed")
    backend._publish(lesson=_lesson(3, appState="closed", appName="VS Code",
                                    closedReason="Lost touch with VS Code"))
    _settle(qapp, 0.2)
    texts = _texts(root)
    assert "Lost touch with VS Code" in texts and "Excel was closed" not in texts
    _click(qapp, root, _button(root, "Reopen VS Code"))
    assert ("reopen_app", ()) in backend.actions


def test_unsaved_code_is_asked_to_be_saved(panel, qapp):
    from app.ui.demo_backend import _lesson, _step_view
    backend, _, root = panel("lesson_step")
    backend._publish(lesson=_lesson(1, step={**_step_view(1), "note": "Press Ctrl+S to save, then your work gets checked."}))
    _settle(qapp, 0.2)
    assert "Press Ctrl+S to save, then your work gets checked." in _texts(root)


def test_a_step_that_came_undone_can_be_pointed_at(panel, qapp):
    backend, _, root = panel("lesson_changed")
    _click(qapp, root, _text_item(root, "Show me where"))
    assert ("go_to_step", (1,)) in backend.actions


def test_the_lesson_waits_for_an_undone_step_and_shows_where_it_is(panel, qapp):
    from app.ui.demo_backend import _banner, _lesson, _step_view
    backend, _, root = panel("lesson_step")
    line = "Every step is done, but step 2 changed. Fix it in Excel to finish."
    backend._publish(lesson=_lesson(1, changed=[1], banner=_banner("changed", line, 1)))
    _settle(qapp, 0.4)
    texts = _texts(root)
    assert line in texts
    assert not any(t.startswith("Step 2 changed.") for t in texts)   # the step on screen is that step
    backend._publish(lesson=_lesson(9, step=_step_view(1), changed=[1], appState="closed",
                                    banner=_banner("changed", line, 1)))
    _settle(qapp, 0.2)
    assert "Open it again to carry on with step 2." in _texts(root)
    backend._publish(lesson=_lesson(9, step=_step_view(1), changed=[1], banner=_banner("changed", line, 1)))
    _settle(qapp, 0.2)
    shown = [i for i in _items(root.contentItem())
             if i.metaObject().className() == "QQuickText" and i.property("text") == "Show me where" and _shown(i)]
    assert len(shown) == 1
    _click(qapp, root, shown[0])
    assert ("go_to_step", (1,)) in backend.actions


def test_a_question_the_coach_cannot_answer_gets_its_calm_line(panel, qapp):
    from app.ui.demo_backend import _lesson
    backend, _, root = panel("lesson_step")
    line = "The Ask box can't answer right now. Your lesson still works: try Hint or Show me."
    backend._publish(lesson=_lesson(1, ask={"state": "error", "question": "Why B8?", "answer": line}))
    _settle(qapp, 0.2)
    texts = _texts(root)
    assert "Why B8?" in texts and line in texts
