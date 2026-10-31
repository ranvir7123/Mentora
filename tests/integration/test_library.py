from pathlib import Path

import pytest

from app.core.library import CourseInfo, Library
from tests.integration.helpers import PROVEN, TESTED, write_courses, write_lesson

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def shelf(tmp_path):
    write_courses(tmp_path)
    return tmp_path


def ids(lessons):
    return [lesson.id for lesson in lessons]


def test_only_proven_lessons_are_on_the_shelf(shelf):
    write_lesson(shelf, "tested", title="A tested one")
    write_lesson(shelf, "proven-only", title="B proven only", test={**TESTED, "mode": "skipped", "passed": False})
    write_lesson(shelf, "test-failed", title="C test failed", test={**TESTED, "passed": False, "passes": 2})
    write_lesson(shelf, "never-proven", title="D never proven", proof=None, test=None)
    write_lesson(shelf, "proof-failed", title="E proof failed", proof={**PROVEN, "passed": False})
    write_lesson(shelf, "proven-untested", title="F proven, test not run", test=None)

    library = Library(shelf)
    assert ids(library.lessons("sheets")) == ["tested", "proven-only"]
    assert library.badge(library.lesson("tested")) == "proven and tested"
    assert library.badge(library.lesson("proven-only")) == "proven"
    for off in ("test-failed", "never-proven", "proof-failed", "proven-untested"):
        with pytest.raises(KeyError):
            library.lesson(off)


def test_the_developer_switch_shows_unproven_lessons_marked(shelf):
    write_lesson(shelf, "tested", title="A tested one")
    write_lesson(shelf, "never-proven", title="B never proven", proof=None, test=None)

    library = Library(shelf, show_unproven=True)
    assert ids(library.lessons("sheets")) == ["tested", "never-proven"]
    assert library.badge(library.lesson("never-proven")) == "not proven yet"
    assert library.badge(library.lesson("tested")) == "proven and tested"


def test_a_broken_lesson_folder_is_skipped_and_noted(shelf):
    write_lesson(shelf, "good")
    (shelf / "bad-json").mkdir()
    (shelf / "bad-json" / "lesson.json").write_text('{"format": 1, "id": ', encoding="utf-8")
    (shelf / "no-file").mkdir()
    write_lesson(shelf, "lost-course", course="cooking")
    write_lesson(shelf, "too-wordy", steps=[{"id": "s0", "instruction": "Now set the key called k zero to the "
                                                                       "number one, then press Enter and wait.",
                                             "why": "k0 needs a value.", "target": {"kind": "key", "ref": "k0"},
                                             "check": {"kind": "equals", "args": {"key": "k0", "value": 1}},
                                             "replay": {"kind": "set", "args": {"key": "k0", "value": 1}},
                                             "hints": ["a", "b", "c"], "mistakes": [], "clip": None}])

    library = Library(shelf)
    assert ids(library.lessons("sheets")) == ["good"]
    noted = {name for name, _ in library.problems}
    assert noted == {"bad-json", "no-file", "lost-course", "too-wordy"}
    assert "cooking" in dict(library.problems)["lost-course"]


def test_two_folders_with_the_same_lesson_id_keep_the_first(shelf):
    write_lesson(shelf, "a-budget")
    copy = write_lesson(shelf, "b-copy")
    (copy / "lesson.json").write_text((shelf / "a-budget" / "lesson.json").read_text(encoding="utf-8"),
                                      encoding="utf-8")
    library = Library(shelf)
    assert ids(library.lessons("sheets")) == ["a-budget"]
    assert [name for name, _ in library.problems] == ["b-copy"]


def test_a_course_with_no_ready_lessons_is_coming_soon(shelf):
    write_lesson(shelf, "sum", title="Add up a column")
    write_lesson(shelf, "draft", course="code", proof=None, test=None)

    library = Library(shelf)
    assert library.courses() == [CourseInfo("sheets", "Sheets", "fake", "courseExcel"),
                                 CourseInfo("code", "Code", "fake", "coursePython")]
    assert ids(library.lessons("code")) == []           # listed, with nothing ready yet
    assert ids(library.lessons("sheets")) == ["sum"]


def test_lessons_come_in_title_order(shelf):
    write_lesson(shelf, "z", title="Average a column")
    write_lesson(shelf, "a", title="Total a row")
    write_lesson(shelf, "m", title="Bold the headings")
    assert ids(Library(shelf).lessons("sheets")) == ["z", "m", "a"]


def test_reload_finds_a_newly_published_lesson(shelf):
    library = Library(shelf)
    assert library.lessons("sheets") == []
    write_lesson(shelf, "new-one")
    library.reload()
    assert ids(library.lessons("sheets")) == ["new-one"]
    assert library.lesson("new-one").folder == shelf / "new-one"


def test_the_real_lessons_all_load_into_a_known_course():
    library = Library(REPO / "lessons", show_unproven=True)
    assert library.problems == []
    assert [c.id for c in library.courses()] == ["excel", "python", "meta-ai"]
    # by title, so the budget lesson the demo opens stays first, never locked behind a newer one
    assert ids(library.lessons("excel")) == ["monthly-budget", "pet-survey-chart", "running-balance", "student-grades"]
    assert ids(library.lessons("python")) == ["vscode-first-program"]
    assert ids(library.lessons("meta-ai")) == ["vscode-meta-ai-app"]
