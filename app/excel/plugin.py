"""Excel as one of the apps a lesson can run in: its menus, its starter rules, and its session.

The core program only sees this object. The check menu (checks.py) and the operation menu (ops.py)
are what Muse Spark may write into a lesson; the target kinds are what locate.py can point at.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from app.core.lesson import Lesson
from app.excel.checks import CHECKS
from app.excel.ops import OPS
from app.excel.session import ExcelSession
from app.excel.starter import validate_starter


class ExcelPlugin:
    app_id = "excel"
    title = "Excel"
    checks = CHECKS
    ops = OPS
    target_kinds = frozenset({"cell", "range", "control", "formula_bar", "name_box", "sheet_tab"})

    def validate_starter(self, starter: Mapping) -> list[str]:
        return validate_starter(starter)

    def open(self, lesson: Lesson, workdir: Path, *, visible: bool = True, resume: bool = False,
             on_snapshot: Callable[[Any], None], on_closed: Callable[[], None]) -> ExcelSession:
        return ExcelSession(lesson, workdir, visible=visible, resume=resume,
                            on_snapshot=on_snapshot, on_closed=on_closed)
