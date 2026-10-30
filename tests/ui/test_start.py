"""Starting the program: where the panel and the lesson's app go, home stepping aside while a lesson is
open, one copy at a time, and the real pieces joined up."""
import logging
import time

import pytest

from app.core.types import Rect
from tests.integration.helpers import write_courses, write_lesson


def _settle(qapp, seconds=0.2):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.005)


# Where things go. The work area is the screen without the taskbar, in logical px; the answer is physical.

def test_at_200_percent_the_panel_takes_the_right_360_px_and_the_app_the_rest():
    from app.main import split_screen
    app, panel = split_screen(Rect(0, 0, 1280, 752), origin=(0, 0), dpr=2.0)
    assert panel == Rect(1840, 0, 720, 1504)
    assert app == Rect(0, 0, 1840, 1504)


def test_at_150_percent_the_two_meet_exactly_on_whole_pixels():
    from app.main import split_screen
    app, panel = split_screen(Rect(0, 0, 1707, 1067), origin=(0, 0), dpr=1.5)
    for r in (app, panel):
        assert all(float(v).is_integer() for v in (r.x, r.y, r.w, r.h))
    assert app.x + app.w == panel.x                       # no gap and no overlap
    assert panel.x + panel.w == 2560 and panel.w == 540   # flush with the right edge, 360 logical px wide
    assert app.h == panel.h == 1600


def test_a_taskbar_on_the_left_is_kept_clear():
    from app.main import split_screen
    app, panel = split_screen(Rect(40, 0, 1240, 800), origin=(0, 0), dpr=2.0)
    assert app.x == 80 and app.x + app.w == panel.x and panel.x + panel.w == 2560


def test_the_layout_is_read_from_any_thread_and_follows_the_screen(qapp):
    import threading

    from app.main import Layout
    changes = []
    layout = Layout(qapp, on_change=lambda: changes.append(1))
    app, panel = layout()
    seen = []
    worker = threading.Thread(target=lambda: seen.append(layout()))
    worker.start()
    worker.join()
    assert seen == [(app, panel)]
    assert panel.w > 0 and app.x + app.w == panel.x
    layout._update()                                      # the same screen again: nothing to redo
    assert changes == []


# Home steps aside while a lesson is open.

@pytest.fixture
def screens(qapp):
    from app.main import Docking
    from app.ui.app import open_screens
    from app.ui.demo_backend import DemoBackend
    backend = DemoBackend("first_run")
    quits = []
    bridge, engine, windows = open_screens(backend, show=("home", "panel"))
    docking = Docking(bridge, windows["home"], quit=lambda: quits.append(1))
    _settle(qapp)
    yield backend, windows, quits
    docking.deleteLater()
    for window in windows.values():
        window.hide()
        window.deleteLater()
    _settle(qapp, 0.05)


def test_home_hides_while_a_lesson_is_open_and_comes_back_after(screens, qapp):
    backend, windows, quits = screens
    home, panel = windows["home"], windows["panel"]
    assert home.isVisible() and not panel.isVisible()
    backend.open_lesson("monthly-budget")
    _settle(qapp)
    assert not home.isVisible() and panel.isVisible()
    backend.close_lesson()
    _settle(qapp)
    assert home.isVisible() and not panel.isVisible()
    backend.open_lesson("monthly-budget")
    _settle(qapp)
    backend.go_home()
    _settle(qapp)
    assert home.isVisible()
    assert quits == []                                    # hiding home never ends the program


def test_closing_home_ends_the_program(screens, qapp):
    _, windows, quits = screens
    windows["home"].close()
    _settle(qapp)
    assert quits == [1]


# One copy at a time: two would both write the learner's progress.

def test_a_second_copy_does_not_start(tmp_path, qapp):
    from app.main import only_copy
    first = only_copy(tmp_path)
    assert first is not None
    assert only_copy(tmp_path) is None
    first.unlock()
    again = only_copy(tmp_path)
    assert again is not None
    again.unlock()


# The real pieces.

def test_the_real_apps_load():
    from app.main import load_plugins
    plugins = load_plugins()
    assert {k: (p.app_id, p.title) for k, p in plugins.items()} == {
        "excel": ("excel", "Excel"), "vscode": ("vscode", "VS Code")}


def test_an_app_that_cannot_load_is_left_out_and_logged(monkeypatch, caplog):
    import app.main as main
    monkeypatch.setattr(main, "PLUGINS", {"excel": "app.excel.plugin:ExcelPlugin",
                                          "paint": "app.paint.plugin:PaintPlugin"})
    with caplog.at_level(logging.ERROR, logger="app.main"):
        plugins = main.load_plugins()
    assert list(plugins) == ["excel"]
    assert "paint" in caplog.text


def test_the_backend_reads_the_shelf_and_the_developer_switch(tmp_path):
    from app.main import build_backend
    lessons = tmp_path / "lessons"
    write_courses(lessons)
    write_lesson(lessons, "proven", title="Proven one")
    write_lesson(lessons, "draft", title="Draft one", proof=None, test=None)
    layout = lambda: (Rect(0, 0, 1840, 1504), Rect(1840, 0, 720, 1504))  # noqa: E731

    def shelf(environ):
        backend = build_backend(lessons=lessons, data=tmp_path / "data", recordings=tmp_path / "rec",
                                layout=layout, environ=environ)
        try:
            return [c["title"] for c in backend.home()["courses"][0]["lessons"]]
        finally:
            backend.shutdown()

    assert shelf({}) == ["Proven one"]
    assert sorted(shelf({"MENTORA_SHOW_UNPROVEN": "1"})) == ["Draft one", "Proven one"]


def test_the_program_keeps_a_log_on_the_laptop(tmp_path):
    from app.main import keep_log
    handler = keep_log(tmp_path)
    try:
        logging.getLogger("app.test").warning("hello from the test")
        handler.flush()
        assert "hello from the test" in (tmp_path / "mentora.log").read_text(encoding="utf-8")
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()


def test_an_unknown_demo_state_is_refused(capsys):
    from app.main import main
    with pytest.raises(SystemExit) as stop:
        main(["--demo", "no_such_state"])
    assert stop.value.code == 2
    assert "first_run" in capsys.readouterr().err
