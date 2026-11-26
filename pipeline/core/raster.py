"""An RGB canvas with anti-aliased polygon fills (standard library only), for images the pipeline draws itself.

Polygons are filled with the non-zero winding rule, so overlapping parts (the segments and joints of a stroked line,
the contours of a glyph) merge instead of cancelling, and coverage is exact along each of SUBSAMPLES sub-scanlines
per pixel row. Colours are (r, g, b) tuples of 0..255; png() encodes the canvas with core.png.
"""

from __future__ import annotations

import math
from collections import defaultdict

from .png import encode

SUBSAMPLES = 4

Colour = tuple[int, int, int]


def mix(a, b, t: float) -> tuple[float, float, float]:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def hex_rgb(value: str) -> Colour:
    n = int(value.lstrip("#"), 16)
    return (n >> 16) & 255, (n >> 8) & 255, n & 255


class Canvas:
    def __init__(self, width: int, height: int, colour: Colour = (0, 0, 0)):
        self.width, self.height = width, height
        self.px = bytearray(bytes(_byte(v) for v in colour) * (width * height))  # RGB, row by row

    def get(self, x: int, y: int) -> Colour:
        i = 3 * (y * self.width + x)
        return tuple(self.px[i:i + 3])

    def set(self, x: int, y: int, colour) -> None:
        i = 3 * (y * self.width + x)
        self.px[i:i + 3] = bytes(_byte(v) for v in colour)

    def blend(self, x: int, y: int, colour, alpha: float) -> None:
        i = 3 * (y * self.width + x)
        p = self.px
        for k in range(3):
            p[i + k] = _byte(p[i + k] + (colour[k] - p[i + k]) * alpha)

    def rect(self, x0: float, y0: float, x1: float, y1: float, colour, alpha: float = 1.0) -> None:
        self.fill([[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]], colour, alpha)

    def fill(self, polygons, colour, alpha: float = 1.0) -> None:
        """Fill the union of `polygons` (lists of (x, y) in pixels; each closes on itself)."""
        rows = defaultdict(list)  # pixel row → edges crossing it: (y0, y1, x at y0, dx/dy, winding)
        for poly in polygons:
            n = len(poly)
            for i in range(n):
                (xa, ya), (xb, yb) = poly[i], poly[(i + 1) % n]
                if ya == yb:
                    continue
                wind = 1 if yb > ya else -1
                if ya > yb:
                    xa, ya, xb, yb = xb, yb, xa, ya
                edge = (ya, yb, xa, (xb - xa) / (yb - ya), wind)
                for r in range(max(0, math.floor(ya)), min(self.height, math.ceil(yb))):
                    rows[r].append(edge)
        for r, edges in rows.items():
            cover = defaultdict(float)
            for s in range(SUBSAMPLES):
                y = r + (s + 0.5) / SUBSAMPLES
                hits = sorted((x0 + (y - y0) * k, w) for y0, y1, x0, k, w in edges if y0 <= y < y1)
                wind = 0
                for (xa, wa), (xb, _) in zip(hits, hits[1:]):
                    wind += wa
                    if wind:
                        _span(cover, max(0.0, xa), min(float(self.width), xb))
            for x, c in cover.items():
                if 0 <= x < self.width and c > 0:
                    self.blend(x, r, colour, alpha * min(1.0, c / SUBSAMPLES))

    def stroke(self, points, width: float, colour, alpha: float = 1.0) -> None:
        """A polyline `width` px wide with round joins and caps."""
        h = width / 2
        polys = [_ccw(circle(x, y, h)) for x, y in points]
        for (xa, ya), (xb, yb) in zip(points, points[1:]):
            d = math.hypot(xb - xa, yb - ya)
            if d:
                nx, ny = -(yb - ya) / d * h, (xb - xa) / d * h
                polys.append(_ccw([(xa + nx, ya + ny), (xb + nx, yb + ny), (xb - nx, yb - ny), (xa - nx, ya - ny)]))
        self.fill(polys, colour, alpha)

    def text(self, font, text: str, size: float, x: float, baseline: float, colour, alpha: float = 1.0, tracking: float = 0.0,
             align: str = "left", halo: tuple | None = None) -> float:
        """Draw `text` (align "left", "center" or "right" of x); halo = (colour, alpha, px) draws an outline under it.
        Returns its width."""
        w = font.width(text, size, tracking)
        x -= {"left": 0, "center": w / 2, "right": w}[align]
        if halo:  # the text's outlines shifted around a circle, filled as one union: the text dilated by `px`
            hc, ha, hpx = halo
            ring = [(hpx * math.cos(a), hpx * math.sin(a)) for a in (2 * math.pi * k / 12 for k in range(12))]
            self.fill([p for dx, dy in ring for p in font.outline(text, size, x + dx, baseline + dy, tracking)], hc, ha)
        self.fill(font.outline(text, size, x, baseline, tracking), colour, alpha)
        return w

    def png(self) -> bytes:
        return encode(self.width, self.height, bytes(self.px))


def _byte(v: float) -> int:
    return 0 if v <= 0 else 255 if v >= 255 else int(v + 0.5)


def _span(cover, xa: float, xb: float) -> None:
    """Add one sub-scanline's coverage of [xa, xb) to the row's pixels."""
    if xb <= xa:
        return
    ia, ib = math.floor(xa), math.floor(xb)
    if ia == ib:
        cover[ia] += xb - xa
        return
    cover[ia] += ia + 1 - xa
    for x in range(ia + 1, ib):
        cover[x] += 1.0
    if xb > ib:
        cover[ib] += xb - ib


def circle(x: float, y: float, r: float, n: int = 12) -> list[tuple[float, float]]:
    """A regular n-gon of radius r around (x, y), standing in for a circle."""
    return [(x + r * math.cos(2 * math.pi * k / n), y + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def _ccw(poly: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """The same polygon, wound one fixed way, so non-zero filling unites overlapping pieces."""
    area = sum(xa * yb - xb * ya for (xa, ya), (xb, yb) in zip(poly, poly[1:] + poly[:1]))
    return poly if area >= 0 else poly[::-1]
