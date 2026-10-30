"""Asking Muse Spark where a ribbon button is on a picture of Excel, when UI Automation cannot find it.

point_fallback(client) gives the function ExcelSession.set_vision_fallback takes. It shows Muse Spark 1.3
the picture of Excel's window and the button's name ("Insert > Pie"), and asks for a box around the button
on a grid of 0 to 1000 across and down the picture: 0, 0 is the picture's top-left corner and 1000, 1000
its bottom-right. The box is turned into pixels of the picture by the picture's own size. The session
trusts it only if UI Automation then finds a control of that name at the box's middle
(locate.confirm_vision), so a wrong answer points at nothing rather than at the wrong thing.

Anything but a clear box is None, and the arrow waits for UI Automation instead: Muse Spark not seeing
the button, a refusal, an answer off the grid, no key, Meta down, or the spending limit reached.
"""
from __future__ import annotations

import base64
import struct
from typing import Any, Callable

from app.core.types import Rect
from app.meta.client import MetaError

POINT_MODEL = "muse-spark-1.3"
LABEL = "point_fallback"           # the name of these calls in Meta's cost log
GRID = 1000
_PNG = b"\x89PNG\r\n\x1a\n"
_EDGES = ("left", "top", "right", "bottom")

RULES = (
    "You look at a picture of Microsoft Excel's window and find one button in it. The button is named by "
    "its place in Excel, like \"Insert > Pie\": the ribbon tab, then the button on it. Give the box around "
    "that button on a grid from 0 to 1000 over the picture: left and right count across from the "
    "picture's left edge, top and bottom count down from its top edge, and 1000 is the far edge. If the "
    "button cannot be seen in the picture, answer found: false. Never guess."
)

SCHEMA = {
    "title": LABEL,
    "type": "object",
    "properties": {"found": {"type": "boolean"},
                   **{edge: {"type": "integer", "minimum": 0, "maximum": GRID} for edge in _EDGES}},
    "required": ["found", *_EDGES],
    "additionalProperties": False,
}


def point_fallback(client: Any) -> Callable[[bytes, str], Rect | None]:
    """fn(png of Excel's window, button ref) -> the button's box in pixels of that picture, or None."""
    def ask(png: bytes, ref: str) -> Rect | None:
        size = _png_size(png)
        if size is None:
            return None
        picture = base64.b64encode(png).decode("ascii")
        request = [{"role": "system", "content": RULES},
                   {"role": "user", "content": [
                       {"type": "input_text", "text": f"Find this button: {ref}"},
                       {"type": "input_image", "image_url": f"data:image/png;base64,{picture}"}]}]
        try:
            answer = client.respond(POINT_MODEL, request, label=LABEL, schema=SCHEMA)
        except MetaError:
            return None
        return None if answer.refusal else _pixels(answer.data, *size)
    return ask


def _png_size(png: bytes) -> tuple[int, int] | None:
    """(width, height) from a PNG's header; None for anything that is not a PNG."""
    if len(png) < 24 or not png.startswith(_PNG) or png[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", png[16:24])
    return (width, height) if width and height else None


def _pixels(data: Any, width: int, height: int) -> Rect | None:
    """The answer's box on the 0-1000 grid as pixels of a width x height picture; None unless it is clear."""
    if not isinstance(data, dict) or data.get("found") is not True:
        return None
    edges = [data.get(edge) for edge in _EDGES]
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= GRID for v in edges):
        return None
    left, top, right, bottom = edges
    if left >= right or top >= bottom:
        return None
    x0, x1 = round(left * width / GRID), round(right * width / GRID)
    y0, y1 = round(top * height / GRID), round(bottom * height / GRID)
    return Rect(x0, y0, max(1, x1 - x0), max(1, y1 - y0))
