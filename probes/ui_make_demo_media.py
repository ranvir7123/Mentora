"""Make the demo lesson's goal picture and its step clip, so the demo states show real pictures.

- app/ui/demo/goal.png: the finished monthly budget, as the goal card shows it before you start.
- recordings/demo/clip.mp4: 20 seconds of a dark spreadsheet. From 12 s to 19.5 s (the stretch the lesson's
  second step plays) someone clicks B8, types =SUM(, drags over B2 to B6, closes the bracket, presses Enter,
  then clicks B8 again to show the formula. Never committed: recordings/ is ignored.

Drawn with Qt, encoded with ffmpeg (it must be on PATH). Run: <py> probes/ui_make_demo_media.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QImage, QPainter, QPen, QPolygonF

ROOT = Path(__file__).resolve().parents[1]
GOAL = ROOT / "app" / "ui" / "demo" / "goal.png"
CLIP = ROOT / "recordings" / "demo" / "clip.mp4"

ITEMS = [("Rent", 12000), ("Food", 6000), ("Travel", 2500), ("Phone", 500), ("Fun", 2000)]
TOTAL = sum(amount for _, amount in ITEMS)

# A dark spreadsheet, close to a real one in dark mode.
PAGE = QColor("#1e1e1e")
CELL = QColor("#242424")
GRID = QColor("#3a3a3a")
HEAD = QColor("#2e2e2e")
HEAD_ON = QColor("#3b4a41")
HEAD_TEXT = QColor("#b8b8b8")
TEXT = QColor("#f0f0f0")
MUTED = QColor("#9a9a9a")
SELECT = QColor("#4fae7b")
REF = QColor("#6ea8f7")
REF_FILL = QColor(110, 168, 247, 38)
BAR = QColor(79, 174, 123, 90)

FONT = "Segoe UI"


def _font(px, bold=False, italic=False):
    font = QFont(FONT)
    font.setPixelSize(round(px))
    font.setBold(bold)
    font.setItalic(italic)
    return font


class Grid:
    """Where each cell sits: column widths for A, B, C…, one row height, and the header sizes."""

    def __init__(self, x, y, widths, row_h, head_w, head_h, rows, px):
        self.x, self.y, self.widths, self.row_h = x, y, widths, row_h
        self.head_w, self.head_h, self.rows, self.px = head_w, head_h, rows, px

    def col_x(self, c):
        return self.x + self.head_w + sum(self.widths[:c])

    def row_y(self, r):
        return self.y + self.head_h + (r - 1) * self.row_h

    def rect(self, ref):
        c, r = ord(ref[0]) - ord("A"), int(ref[1:])
        return QRectF(self.col_x(c), self.row_y(r), self.widths[c], self.row_h)

    def span(self, first, last):
        return self.rect(first).united(self.rect(last))

    def row_at(self, y):
        return int((y - self.y - self.head_h) // self.row_h) + 1

    @property
    def width(self):
        return self.head_w + sum(self.widths)

    @property
    def height(self):
        return self.head_h + self.rows * self.row_h


def _parts(p, x, rect, parts, font):
    """Draw (text, colour) pieces one after another from x; returns where the last one ends."""
    p.setFont(font)
    metrics = QFontMetricsF(font)
    for text, colour in parts:
        p.setPen(colour)
        p.drawText(QRectF(x, rect.y(), metrics.horizontalAdvance(text) + 2, rect.height()),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
        x += metrics.horizontalAdvance(text)
    return x


def _formula_parts(text, ref):
    """A formula with its cell reference in the reference colour, as a spreadsheet shows it while editing."""
    if ref and ref in text:
        before, after = text.split(ref, 1)
        return [(before, TEXT), (ref, REF), (after, TEXT)]
    return [(text, TEXT)]


def draw_grid(p, g, cells, *, selected=None, ref_range=None, bold=(), bars=None, editing=None,
              caret=False, total_row=None):
    """The headers, the cells and their text, the referenced range and the selected cell."""
    line = max(1.0, g.px / 22)
    pad = g.px * 0.45
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    p.fillRect(QRectF(g.x, g.y, g.width, g.height), CELL)
    p.fillRect(QRectF(g.x, g.y, g.width, g.head_h), HEAD)
    p.fillRect(QRectF(g.x, g.y, g.head_w, g.height), HEAD)
    if selected:
        c, r = ord(selected[0]) - ord("A"), int(selected[1:])
        p.fillRect(QRectF(g.col_x(c), g.y, g.widths[c], g.head_h), HEAD_ON)
        p.fillRect(QRectF(g.x, g.row_y(r), g.head_w, g.row_h), HEAD_ON)
        p.fillRect(QRectF(g.col_x(c), g.y + g.head_h - 2 * line, g.widths[c], 2 * line), SELECT)
        p.fillRect(QRectF(g.x + g.head_w - 2 * line, g.row_y(r), 2 * line, g.row_h), SELECT)

    p.setPen(QPen(GRID, line))
    for c in range(len(g.widths) + 1):
        x = round(g.col_x(c))
        p.drawLine(QPointF(x, g.y), QPointF(x, g.y + g.height))
    for r in range(g.rows + 1):
        y = round(g.y + g.head_h + r * g.row_h)
        p.drawLine(QPointF(g.x, y), QPointF(g.x + g.width, y))
    if total_row:
        p.setPen(QPen(MUTED, 2 * line))
        y = round(g.row_y(total_row)) + line
        p.drawLine(QPointF(g.col_x(0), y), QPointF(g.col_x(len(g.widths)), y))

    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setFont(_font(g.px * 0.78))
    p.setPen(HEAD_TEXT)
    for c in range(len(g.widths)):
        p.drawText(QRectF(g.col_x(c), g.y, g.widths[c], g.head_h), Qt.AlignmentFlag.AlignCenter, chr(ord("A") + c))
    for r in range(1, g.rows + 1):
        p.drawText(QRectF(g.x, g.row_y(r), g.head_w, g.row_h), Qt.AlignmentFlag.AlignCenter, str(r))

    for ref, share in (bars or {}).items():
        box = g.rect(ref).adjusted(pad * 0.6, g.row_h * 0.18, -pad * 0.6, -g.row_h * 0.18)
        box.setWidth(box.width() * share)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(BAR)
        p.drawRoundedRect(box, line * 2, line * 2)

    for ref, value in cells.items():
        box = g.rect(ref).adjusted(pad, 0, -pad, 0)
        font = _font(g.px, bold=ref in bold)
        if ref == editing:
            end = _parts(p, box.x(), box, _formula_parts(value, ref_range and _ref_text(ref_range)), font)
            if caret:
                p.fillRect(QRectF(end + line, box.y() + g.row_h * 0.22, line * 1.5, g.row_h * 0.56), TEXT)
            continue
        numeric = isinstance(value, int) or str(value).endswith("%")
        text = f"{value:,}" if isinstance(value, int) else str(value)
        p.setFont(font)
        p.setPen(TEXT)
        align = Qt.AlignmentFlag.AlignRight if numeric else Qt.AlignmentFlag.AlignLeft
        p.drawText(box, align | Qt.AlignmentFlag.AlignVCenter, text)

    if ref_range:
        box = g.span(*ref_range).adjusted(line, line, -line, -line)
        p.setPen(QPen(REF, 2 * line))
        p.setBrush(REF_FILL)
        p.drawRect(box)
    if selected:
        box = g.rect(selected).adjusted(line, line, -line, -line)
        p.setPen(QPen(SELECT, 2.5 * line))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(box)
        handle = 7 * line
        p.setPen(QPen(CELL, line))
        p.setBrush(SELECT)
        p.drawRect(QRectF(box.right() - handle / 2, box.bottom() - handle / 2, handle, handle))


def _ref_text(ref_range):
    first, last = ref_range
    return first if first == last else f"{first}:{last}"


def draw_formula_bar(p, x, y, w, h, name, content, ref, caret, px):
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.fillRect(QRectF(x, y, w, h), PAGE)
    box = QRectF(x + 12, y + 8, 120, h - 16)
    p.setPen(QPen(GRID, 1))
    p.setBrush(CELL)
    p.drawRect(box)
    p.setFont(_font(px * 0.82))
    p.setPen(TEXT)
    p.drawText(box, Qt.AlignmentFlag.AlignCenter, name)
    p.setFont(_font(px * 0.82, italic=True))
    p.setPen(MUTED)
    p.drawText(QRectF(x + 148, y, 40, h), Qt.AlignmentFlag.AlignCenter, "fx")
    field = QRectF(x + 196, y + 8, w - 196 - 12, h - 16)
    p.setPen(QPen(GRID, 1))
    p.setBrush(CELL)
    p.drawRect(field)
    end = _parts(p, field.x() + 12, field, _formula_parts(content, ref), _font(px * 0.9))
    if caret:
        p.fillRect(QRectF(end + 1, field.y() + 7, 1.5, field.height() - 14), TEXT)


def draw_cursor(p, at, scale):
    shape = [(0, 0), (0, 17), (4.2, 13.2), (7.2, 20), (9.8, 18.9), (6.9, 12.3), (12.2, 12.3)]
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setPen(QPen(QColor("#000000"), 1.3 * scale))
    p.setBrush(QColor("#ffffff"))
    p.drawPolygon(QPolygonF([QPointF(at.x() + a * scale, at.y() + b * scale) for a, b in shape]))


def _starter():
    cells = {"A1": "Item", "B1": "Amount", "C1": "Share", "A8": "Total"}
    for row, (item, amount) in enumerate(ITEMS, start=2):
        cells[f"A{row}"], cells[f"B{row}"] = item, amount
    return cells


def make_goal():
    """The finished budget: bold headings, the total, and each item's share with a bar."""
    g = Grid(0, 0, [300, 240, 300], 60, 64, 44, 8, 28)
    image = QImage(round(g.width), round(g.height), QImage.Format.Format_RGB32)
    image.fill(PAGE)
    cells = _starter()
    cells["B8"] = TOTAL
    biggest = max(amount for _, amount in ITEMS)
    bars = {}
    for row, (_, amount) in enumerate(ITEMS, start=2):
        cells[f"C{row}"] = f"{round(amount / TOTAL * 100)}%"
        bars[f"C{row}"] = amount / biggest
    cells["C8"] = "100%"
    p = QPainter(image)
    draw_grid(p, g, cells, bold={"A1", "B1", "C1", "A8", "B8", "C8"}, bars=bars, total_row=8)
    p.end()
    GOAL.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(GOAL))
    return GOAL


def _ease(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


def _between(a, b, u):
    return QPointF(a.x() + (b.x() - a.x()) * u, a.y() + (b.y() - a.y()) * u)


def clip_frame(t, g):
    """What the screen shows t seconds into the clip."""
    b8, b2, b6 = (g.rect(ref).center() for ref in ("B8", "B2", "B6"))
    rest = QPointF(1010, 610)
    if t < 11.6:
        cursor = rest
    elif t < 12.4:
        cursor = _between(rest, b8, _ease((t - 11.6) / 0.8))
    elif t < 14.2:
        cursor = b8
    elif t < 14.5:
        cursor = _between(b8, b2, _ease((t - 14.2) / 0.3))
    elif t < 15.9:
        cursor = _between(b2, b6, _ease((t - 14.5) / 1.4))
    elif t < 18.2:
        cursor = b6
    elif t < 18.6:
        cursor = _between(b6, b8, _ease((t - 18.2) / 0.4))
    else:
        cursor = b8

    frame = {"cells": _starter(), "selected": "A1", "formula": "", "ref_range": None, "editing": None,
             "caret": False, "cursor": cursor}
    if t >= 12.4:
        frame["selected"] = "B8"
    if 12.9 <= t < 17.0:
        typed = "=SUM("[:min(5, int((t - 12.9) / 0.2) + 1)]
        if t >= 14.5:
            last = max(2, min(6, g.row_at(cursor.y())))
            frame["ref_range"] = ("B2", f"B{last}")
            typed += _ref_text(frame["ref_range"])
        if t >= 16.3:
            typed += ")"
        frame.update(formula=typed, editing="B8", caret=t < 14.5 or int(t * 2.5) % 2 == 0)
        frame["cells"]["B8"] = typed
    if t >= 17.0:
        frame["cells"]["B8"] = TOTAL
        frame["selected"] = "B9"
    if t >= 18.6:
        frame.update(selected="B8", formula="=SUM(B2:B6)")
    return frame


def make_clip(seconds=20.0, fps=30, size=(1280, 720)):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        sys.exit("ffmpeg is not on PATH, so the clip can't be made.")
    w, h = size
    bar_h = 56
    g = Grid(0, bar_h, [250, 200, 170, 170, 170, 170, 170], 44, 56, 36, 15, 22)
    CLIP.parent.mkdir(parents=True, exist_ok=True)
    encode = subprocess.Popen(
        [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
         "-r", str(fps), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
         "-movflags", "+faststart", str(CLIP)],
        stdin=subprocess.PIPE)
    image = QImage(w, h, QImage.Format.Format_RGB888)
    for n in range(round(seconds * fps)):
        f = clip_frame(n / fps, g)
        image.fill(PAGE)
        p = QPainter(image)
        draw_formula_bar(p, 0, 0, w, bar_h, f["selected"], f["formula"],
                         f["ref_range"] and _ref_text(f["ref_range"]), f["caret"], 22)
        draw_grid(p, g, f["cells"], selected=f["selected"], ref_range=f["ref_range"], bold={"A1", "B1", "C1"},
                  editing=f["editing"], caret=f["caret"])
        draw_cursor(p, f["cursor"], 1.4)
        p.end()
        encode.stdin.write(bytes(image.constBits()))
    encode.stdin.close()
    if encode.wait() != 0:
        sys.exit("ffmpeg could not make the clip.")
    return CLIP


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    print("goal picture:", make_goal())
    print("clip:", make_clip())
