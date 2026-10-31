"""The library: the courses, and the lessons ready for learners.

`lessons/courses.json` lists the courses in the order the home screen shows them. Each folder under
`lessons/` holds one lesson. A lesson is on the shelf only when it passed its proof and has a test result
(`shelf_badge`); a developer switch (`MENTORA_SHOW_UNPROVEN=1`, read by the program at start-up) also
shows the others, marked "not proven yet". It is never on in recordings.

A folder that can't be read, breaks a lesson rule or names a course that isn't listed is skipped. Its
problem is kept in `problems` and written to the log, never shown on screen.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from app.core.lesson import Lesson, LessonError, load_lesson, shelf_badge, validate

log = logging.getLogger(__name__)

UNPROVEN = "not proven yet"


class LibraryError(RuntimeError):
    """`courses.json` is missing or broken: the program itself is broken, not a lesson."""


@dataclass(frozen=True)
class CourseInfo:
    id: str
    title: str
    app: str
    colour: str                  # a Theme colour name, such as "courseExcel"


def _read_courses(path: Path) -> list[CourseInfo]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        courses = [CourseInfo(id=c["id"], title=c["title"], app=c["app"], colour=c["colour"]) for c in data]
    except (OSError, ValueError, TypeError, KeyError) as e:
        raise LibraryError(f"{path} could not be read ({e})") from None
    if not all(isinstance(v, str) and v for c in courses for v in (c.id, c.title, c.app, c.colour)):
        raise LibraryError(f"{path}: every course needs a text id, title, app and colour")
    return courses


class Library:
    def __init__(self, root: Path, *, show_unproven: bool = False):
        self._root = Path(root)
        self._show_unproven = show_unproven
        self._lock = threading.Lock()
        self._courses: list[CourseInfo] = []
        self._lessons: dict[str, Lesson] = {}
        self.problems: list[tuple[str, str]] = []     # (folder name, what is wrong)
        self.reload()

    def reload(self) -> None:
        """Read `courses.json` and every lesson folder again, such as after a lesson is made."""
        courses = _read_courses(self._root / "courses.json")
        known = {c.id for c in courses}
        lessons: dict[str, Lesson] = {}
        problems: list[tuple[str, str]] = []
        for folder in sorted(p for p in self._root.iterdir() if p.is_dir() and not p.name.startswith(".")):
            try:
                lesson = load_lesson(folder)
                broken = validate(lesson)
                if lesson.course not in known:
                    broken.append(f'its course "{lesson.course}" is not in courses.json')
                if lesson.id in lessons:
                    broken.append(f'the folder {lessons[lesson.id].folder.name} already has the id "{lesson.id}"')
            except LessonError as e:
                broken = [str(e)]
            if broken:
                problems.append((folder.name, "; ".join(broken)))
                log.warning("lesson folder %s skipped: %s", folder.name, "; ".join(broken))
                continue
            lessons[lesson.id] = lesson
        with self._lock:
            self._courses, self._lessons, self.problems = courses, lessons, problems

    def badge(self, lesson: Lesson) -> str | None:
        """The shelf badge, "not proven yet" when the developer switch shows an unproven lesson, else None."""
        badge = shelf_badge(lesson)
        if badge is None and self._show_unproven:
            return UNPROVEN
        return badge

    def courses(self) -> list[CourseInfo]:
        with self._lock:
            return list(self._courses)

    def lessons(self, course_id: str) -> list[Lesson]:
        """The lessons on this course's shelf: the hand-written path first, then the ones made from videos,
        each by title, so a lesson made later never jumps ahead and locks the one a learner starts with."""
        with self._lock:
            found = [lesson for lesson in self._lessons.values()
                     if lesson.course == course_id and self.badge(lesson) is not None]
        return sorted(found, key=lambda lesson: (lesson.made_by != "hand", lesson.title.casefold(), lesson.id))

    def lesson(self, lesson_id: str) -> Lesson:
        """A lesson on the shelf; KeyError for any other, so nothing unproven ever opens."""
        with self._lock:
            lesson = self._lessons.get(lesson_id)
        if lesson is None or self.badge(lesson) is None:
            raise KeyError(lesson_id)
        return lesson
