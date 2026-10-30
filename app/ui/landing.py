"""Where the mascot lands beside its target, where its words go, and the curve it flies there.

Pure geometry, so it can be tested without a screen. Every rectangle is in one unit (the bridge uses
physical pixels, so the 8 px gap stays 8 real pixels at any scaling). The rules: the mascot sits beside
the target, never on it (it keeps clear of the target grown by 6 px), stays on the screen and out of the
lesson panel, and tries the target's left first, then above, right and below. It takes a side only where its
words fit beside it too, if any side has that. When the app gives a room (for a cell, the sheet's visible
cells), the mascot and its words stay inside it, so they never cover the app's own buttons and bars; only
when nothing fits there do the screen's rules apply. Inside it they keep off the filled cells the app
gives, when there is space, so the learner can still read them.
"""
from __future__ import annotations

import math

from app.core.types import Rect

GAP = 8           # between the target and the mascot, and between the mascot and its words
CLEAR = 6         # how far from the target nothing may come


def _inside(r: Rect, screen: Rect) -> bool:
    return (screen.x <= r.x and r.x + r.w <= screen.x + screen.w
            and screen.y <= r.y and r.y + r.h <= screen.y + screen.h)


def _fits(r: Rect, keep_clear: list[Rect], screen: Rect) -> bool:
    return _inside(r, screen) and not any(r.intersects(k) for k in keep_clear)


def _clamp(v: float, low: float, high: float) -> float:
    return max(low, min(v, high))


def _common(a: Rect, b: Rect) -> Rect | None:
    x0, y0 = max(a.x, b.x), max(a.y, b.y)
    x1, y1 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    return Rect(x0, y0, x1 - x0, y1 - y0) if x1 > x0 and y1 > y0 else None


def _areas(target: Rect, screen: Rect, room: Rect | None) -> list[Rect]:
    """Where to look, in turn: the part of the room on the screen (only a room that holds the target; any
    other is out of date), then the whole screen."""
    inside = _common(room, screen) if room is not None and room.intersects(target) else None
    return ([inside] if inside is not None else []) + [screen]


def _overlap(a: Rect, b: Rect) -> float:
    w = min(a.x + a.w, b.x + b.w) - max(a.x, b.x)
    h = min(a.y + a.h, b.y + b.h) - max(a.y, b.y)
    return w * h if w > 0 and h > 0 else 0.0


def _onto_screen(r: Rect, screen: Rect, avoid: Rect | None) -> Rect:
    """`r` slid onto the screen, then out of `avoid` the shortest way that stays on the screen."""
    r = Rect(_clamp(r.x, screen.x, screen.x + screen.w - r.w), _clamp(r.y, screen.y, screen.y + screen.h - r.h),
             r.w, r.h)
    if avoid is None or not r.intersects(avoid):
        return r
    ways = [Rect(avoid.x - r.w, r.y, r.w, r.h), Rect(avoid.x + avoid.w, r.y, r.w, r.h),
            Rect(r.x, avoid.y - r.h, r.w, r.h), Rect(r.x, avoid.y + avoid.h, r.w, r.h)]
    ways = [w for w in ways if _inside(w, screen)]
    return min(ways, key=lambda w: abs(w.x - r.x) + abs(w.y - r.y)) if ways else r


def _sides(target: Rect, mascot: float, area: Rect, headroom: float, gap: float) -> list[Rect]:
    """The footprint (body plus headroom) on each side of the target, `gap` from it, centred on it and slid
    along the side to stay in `area`: left, above, right, below."""
    full = mascot + headroom
    cx, cy = target.center
    level = _clamp(cy - mascot / 2 - headroom, area.y, area.y + area.h - full)
    middle = _clamp(cx - mascot / 2, area.x, area.x + area.w - mascot)
    return [Rect(target.x - gap - mascot, level, mascot, full), Rect(middle, target.y - gap - full, mascot, full),
            Rect(target.x + target.w + gap, level, mascot, full), Rect(middle, target.y + target.h + gap, mascot, full)]


def _keep_offs(avoid: Rect | None, filled: Rect | None) -> list[list[Rect]]:
    """What to keep clear of, besides the target, in turn: `avoid` and the filled cells, then `avoid` alone."""
    always = [avoid] if avoid is not None else []
    return ([always + [filled]] if filled is not None else []) + [always]


def landing_spot(target: Rect, mascot: float, screen: Rect, avoid: Rect | None, *, room: Rect | None = None,
                 filled: Rect | None = None, headroom: float = 0.0, words: tuple[float, float] | None = None,
                 gap: float = GAP) -> tuple[float, float]:
    """Top-left of the mascot's body (a `mascot`-sized square) beside `target`, inside `room` and off
    `filled` when a side fits there.

    `headroom` is the space kept free above the body for the parts that stick up (its curl, its hop), so
    they never reach the target either. `words` is the size (w, h) of what it will say: a side counts first
    only where those fit beside it in the same area. The order of what gives way first: the filled cells,
    then the room, then the words. If the target leaves no room on any side, the spot on the screen and out
    of `avoid` that covers the least of the target is used.
    """
    tries = [(area, with_words, off) for with_words in ([True] if words is not None else []) + [False]
             for area in _areas(target, screen, room) for off in _keep_offs(avoid, filled)]
    for area, with_words, off in tries:
        for s in _sides(target, mascot, area, headroom, gap):
            if _fits(s, [target.inflate(CLEAR)] + off, area) and (
                    not with_words or _words_in(target, s, words, area, off, gap) is not None):
                return s.x, s.y + headroom
    best = min((_onto_screen(s, screen, avoid) for s in _sides(target, mascot, screen, headroom, gap)),
               key=lambda s: _overlap(s, target.inflate(CLEAR)))
    return best.x, best.y + headroom


def _word_spots(target: Rect, mascot: Rect, bubble: tuple[float, float], area: Rect, gap: float) -> list[Rect]:
    """Where the words may go beside `mascot`, in order: above it leaning away from the target, above it
    centred, the same two below, then beside it on the far side and the near side; each slid along to stay
    in `area`."""
    w, h = bubble
    mx, my = mascot.center
    away_left = mx < target.center[0]       # the mascot is left of the target, so its words lean left
    lean = mascot.x + mascot.w - w if away_left else mascot.x
    centred = mx - w / 2
    above, below = mascot.y - gap - h, mascot.y + mascot.h + gap
    far = mascot.x - gap - w if away_left else mascot.x + mascot.w + gap
    near = mascot.x + mascot.w + gap if away_left else mascot.x - gap - w

    def across(x: float) -> float:
        return _clamp(x, area.x, area.x + area.w - w)
    level = _clamp(my - h / 2, area.y, area.y + area.h - h)
    return [Rect(across(lean), above, w, h), Rect(across(centred), above, w, h), Rect(across(lean), below, w, h),
            Rect(across(centred), below, w, h), Rect(far, level, w, h), Rect(near, level, w, h)]


def _words_in(target: Rect, mascot: Rect, bubble: tuple[float, float], area: Rect, off: list[Rect],
              gap: float) -> Rect | None:
    """The first spot for the words in `area` that is clear of the target, the mascot and everything in `off`."""
    keep_clear = [target.inflate(CLEAR), mascot] + off
    return next((s for s in _word_spots(target, mascot, bubble, area, gap) if _fits(s, keep_clear, area)), None)


def bubble_spot(target: Rect, mascot: Rect, bubble: tuple[float, float], screen: Rect, avoid: Rect | None,
                *, room: Rect | None = None, filled: Rect | None = None, gap: float = GAP) -> tuple[float, float]:
    """Top-left of the mascot's words (a `bubble` = (w, h) box) next to `mascot`, its whole footprint.

    Above the mascot first, leaning away from the target, then below, then beside it on the far side;
    inside `room` and off `filled` when one of those fits there; never on the target, the mascot, off the
    screen or in `avoid`.
    """
    for area in _areas(target, screen, room):
        for off in _keep_offs(avoid, filled):
            spot = _words_in(target, mascot, bubble, area, off, gap)
            if spot is not None:
                return spot.x, spot.y
    best = min((_onto_screen(s, screen, avoid) for s in _word_spots(target, mascot, bubble, screen, gap)),
               key=lambda s: _overlap(s, target.inflate(CLEAR)) + _overlap(s, mascot))
    return best.x, best.y


def arc_control(start: tuple[float, float], end: tuple[float, float],
                top: float = -math.inf) -> tuple[float, float]:
    """The flight curve's control point: over the middle, lifted by a quarter of the distance (screen y grows
    downward, so up is smaller y). It never goes above `top`, which keeps the whole curve below it."""
    (x0, y0), (x1, y1) = start, end
    distance = math.hypot(x1 - x0, y1 - y0)
    return (x0 + x1) / 2, max((y0 + y1) / 2 - 0.25 * distance, top)


STRETCH = 1.12    # the mascot is up to 12% longer along the way it flies (Mascot.qml's stretch)

Point = tuple[float, float]


def _covers_on_the_way(start: Point, bend: tuple[Point, Point], end: Point, size: float, headroom: float,
                       keep_clear: Rect) -> bool:
    """Whether the mascot, flying the curve, covers `keep_clear` at any moment after it has been clear of
    it (it may start on it, when the target moved under it). Its stretch along the way it goes counts."""
    (x0, y0), ((ax, ay), (bx, by)), (x1, y1) = start, bend, end
    legs = (math.hypot(ax - x0, ay - y0), math.hypot(bx - ax, by - ay), math.hypot(x1 - bx, y1 - by))
    steps = max(16, math.ceil(1.5 * max(legs)))        # no more than 2 units between two looks
    grow = (STRETCH - 1) / 2 * size
    kx, ky, kr, kb = keep_clear.x, keep_clear.y, keep_clear.x + keep_clear.w, keep_clear.y + keep_clear.h
    been_clear = False
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = u * u * u * x0 + 3 * u * u * t * ax + 3 * u * t * t * bx + t * t * t * x1
        y = u * u * u * y0 + 3 * u * u * t * ay + 3 * u * t * t * by + t * t * t * y1
        dx = u * u * (ax - x0) + 2 * u * t * (bx - ax) + t * t * (x1 - bx)
        dy = u * u * (ay - y0) + 2 * u * t * (by - ay) + t * t * (y1 - by)
        speed = math.hypot(dx, dy) or 1.0
        gx, gy = grow * abs(dx) / speed, grow * abs(dy) / speed
        over = (x - gx < kr and kx < x + size + gx and y - headroom - gy < kb and ky < y + size + gy)
        been_clear = been_clear or not over
        if over and been_clear:
            return True
    return False


def flight_control(start: Point, end: Point, size: float, keep_clear: Rect, screen: Rect,
                   *, headroom: float = 0.0) -> tuple[Point, Point]:
    """The two bends of the mascot's flight (a cubic curve of its body's top-left) from `start` to `end`
    that never takes it over `keep_clear` (the target and its ring).

    The usual arc when it is clear. Otherwise it swoops over and drops straight onto the spot, or under and
    rises onto it; leaves a spot beside the target straight up or down before swooping away; or does both.
    Every bend stays inside the screen (with `headroom`), so the whole curve does too.
    """
    (x0, y0), (x1, y1) = start, end
    top, bottom = screen.y + headroom, screen.y + screen.h - size
    lift = 0.25 * math.hypot(x1 - x0, y1 - y0)
    up, down = max(min(y0, y1) - lift, top), min(max(y0, y1) + lift, bottom)
    qx, qy = arc_control(start, end, top)
    usual = ((x0 + 2 / 3 * (qx - x0), y0 + 2 / 3 * (qy - y0)), (x1 + 2 / 3 * (qx - x1), y1 + 2 / 3 * (qy - y1)))
    tries = [
        usual,
        ((x1, up), (x1, up)),           # over, then straight down onto the spot
        ((x1, down), (x1, down)),       # under, then straight up onto it
        ((x0, up), (x0, up)),           # straight up off the spot, then away
        ((x0, down), (x0, down)),       # straight down off it, then away
        ((x0, up), (x1, up)),           # straight up off one spot, over, straight down onto the other
        ((x0, down), (x1, down)),
    ]
    for bend in tries:
        if not _covers_on_the_way(start, bend, end, size, headroom, keep_clear):
            return bend
    return usual


def to_physical(r: Rect, origin: tuple[float, float], dpr: float) -> Rect:
    """A logical rectangle on a screen whose top-left is `origin`, in physical pixels (Qt keeps a screen's
    top-left the same in both and scales the rest)."""
    ox, oy = origin
    return Rect(ox + (r.x - ox) * dpr, oy + (r.y - oy) * dpr, r.w * dpr, r.h * dpr)


def to_logical(p: tuple[float, float], origin: tuple[float, float], dpr: float) -> tuple[float, float]:
    ox, oy = origin
    return ox + (p[0] - ox) / dpr, oy + (p[1] - oy) / dpr
