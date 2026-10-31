"""Excel as one of the apps a lesson can run in: its menus, its starter rules, and its session.

The core program only sees this object. The check menu (checks.py) and the operation menu (ops.py)
are what Muse Spark may write into a lesson; the target kinds are what locate.py can point at.

When a Meta key is saved, every session it opens can ask Muse Spark where a ribbon button is on a
picture of Excel (vision.py), for the times UI Automation cannot find it; with MENTORA_AI=claude it asks
Claude instead, when a Claude key is saved (app/ai.py). With no key it never asks.
The key is looked for at each lesson, so one saved while the program runs counts from the next lesson.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from app.core.lesson import Lesson
from app.excel.checks import CHECKS
from app.excel.ops import OPS
from app.excel.session import ExcelSession
from app.excel.starter import validate_starter
from app.ai import key_name, make_client
from app.excel.vision import point_fallback
from app.meta.key import find_key

VISION_TIMEOUT_S = 30.0            # an answer about where a button is, later than this, is no use


class ExcelPlugin:
    app_id = "excel"
    title = "Excel"
    checks = CHECKS
    ops = OPS
    target_kinds = frozenset({"cell", "range", "control", "formula_bar", "name_box", "sheet_tab"})

    def __init__(self) -> None:
        self._meta: Any | None = None      # made once a key is found, then shared by every lesson

    def validate_starter(self, starter: Mapping) -> list[str]:
        return validate_starter(starter)

    def open(self, lesson: Lesson, workdir: Path, *, visible: bool = True, resume: bool = False,
             on_snapshot: Callable[[Any], None], on_closed: Callable[[], None]) -> ExcelSession:
        session = ExcelSession(lesson, workdir, visible=visible, resume=resume,
                               on_snapshot=on_snapshot, on_closed=on_closed)
        meta = self._meta_client()
        if meta is not None:
            session.set_vision_fallback(point_fallback(meta))
        return session

    def _meta_client(self) -> Any | None:
        if self._meta is None and find_key(key_name())[0] is not None:
            self._meta = make_client(timeout_s=VISION_TIMEOUT_S)
        return self._meta
