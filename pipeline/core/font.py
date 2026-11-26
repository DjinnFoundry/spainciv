"""A small TrueType reader (standard library only): glyph outlines and advances, to draw text into generated images.

It reads the `glyf` outlines (simple and composite glyphs), a format 4 `cmap` and the horizontal metrics; a variable
font gives its default instance. There is no kerning, hinting or shaping: enough for titles in a Latin font. Curves
come back flattened into polygons, in pixels with y down, ready for core.raster.Canvas.fill.

The bundled font is Cinzel (pipeline/core/fonts/, SIL Open Font License 1.1, see OFL.txt there).
"""

from __future__ import annotations

import struct
from functools import cached_property, lru_cache
from pathlib import Path

FONTS = Path(__file__).parent / "fonts"
CURVE_STEPS = 6  # line segments per quadratic curve

# Composite glyph flags (TrueType `glyf`).
_WORDS, _XY, _SCALE, _MORE, _XY_SCALE, _TWO_BY_TWO = 0x1, 0x2, 0x8, 0x20, 0x40, 0x80


class Font:
    def __init__(self, data: bytes):
        self.data = data
        (n,) = struct.unpack(">H", data[4:6])
        self.tables = {}
        for i in range(n):
            tag, _, off, length = struct.unpack(">4sIII", data[12 + 16 * i:28 + 16 * i])
            self.tables[tag.decode("latin-1")] = (off, length)
        if "glyf" not in self.tables:
            raise ValueError("only TrueType (glyf) outlines are supported")
        head = self.tables["head"][0]
        (self.units_per_em,) = struct.unpack(">H", data[head + 18:head + 20])
        (self._long_loca,) = struct.unpack(">h", data[head + 50:head + 52])
        hhea = self.tables["hhea"][0]
        (self._n_hmetrics,) = struct.unpack(">H", data[hhea + 34:hhea + 36])

    @classmethod
    def load(cls, path: Path) -> "Font":
        return cls(path.read_bytes())

    def _u16(self, pos: int) -> int:
        return struct.unpack(">H", self.data[pos:pos + 2])[0]

    @cached_property
    def cmap(self) -> dict[int, int]:
        """code point → glyph id, from the Unicode BMP subtable (format 4)."""
        base = self.tables["cmap"][0]
        for i in range(self._u16(base + 2)):
            platform, encoding, offset = struct.unpack(">HHI", self.data[base + 4 + 8 * i:base + 12 + 8 * i])
            sub = base + offset
            if (platform, encoding) in ((3, 1), (0, 3)) and self._u16(sub) == 4:
                return self._cmap4(sub)
        raise ValueError("no Unicode BMP cmap (format 4)")

    def _cmap4(self, sub: int) -> dict[int, int]:
        segs = self._u16(sub + 6) // 2
        ends, starts, deltas, ranges = (sub + 14, sub + 16 + 2 * segs, sub + 16 + 4 * segs, sub + 16 + 6 * segs)
        out = {}
        for s in range(segs):
            end, start = self._u16(ends + 2 * s), self._u16(starts + 2 * s)
            delta, range_off = self._u16(deltas + 2 * s), self._u16(ranges + 2 * s)
            for c in range(start, min(end, 0xFFFE) + 1):
                if range_off:
                    g = self._u16(ranges + 2 * s + range_off + 2 * (c - start))
                    g = (g + delta) & 0xFFFF if g else 0
                else:
                    g = (c + delta) & 0xFFFF
                if g:
                    out[c] = g
        return out

    def glyph(self, char: str) -> int:
        """Glyph id of a character (0, the .notdef box, when the font lacks it)."""
        return self.cmap.get(ord(char), 0)

    def advance(self, gid: int) -> int:
        hmtx = self.tables["hmtx"][0]
        return self._u16(hmtx + 4 * min(gid, self._n_hmetrics - 1))

    def _glyph_range(self, gid: int) -> tuple[int, int]:
        loca, glyf = self.tables["loca"][0], self.tables["glyf"][0]
        if self._long_loca:
            a, b = struct.unpack(">II", self.data[loca + 4 * gid:loca + 4 * gid + 8])
        else:
            a, b = (2 * v for v in struct.unpack(">HH", self.data[loca + 2 * gid:loca + 2 * gid + 4]))
        return glyf + a, glyf + b

    @lru_cache(maxsize=None)
    def contours(self, gid: int) -> tuple[tuple[tuple[float, float], ...], ...]:
        """The glyph's outline in font units (y up), each contour flattened into a closed polygon."""
        start, end = self._glyph_range(gid)
        if end <= start:
            return ()
        (n_contours,) = struct.unpack(">h", self.data[start:start + 2])
        if n_contours >= 0:
            return tuple(_flatten(c) for c in self._simple(start, n_contours))
        return self._composite(start + 10)

    def _simple(self, pos: int, n_contours: int) -> list[list[tuple[int, int, bool]]]:
        d = self.data
        ends = struct.unpack(f">{n_contours}H", d[pos + 10:pos + 10 + 2 * n_contours])
        n_points = ends[-1] + 1 if ends else 0
        p = pos + 10 + 2 * n_contours
        p += 2 + self._u16(p)  # instructions
        flags = []
        while len(flags) < n_points:
            f = d[p]
            p += 1
            repeat = 0
            if f & 8:
                repeat = d[p]
                p += 1
            flags.extend([f] * (repeat + 1))
        coords = []
        for short, same in ((0x02, 0x10), (0x04, 0x20)):
            v, values = 0, []
            for f in flags:
                if f & short:
                    v += d[p] if f & same else -d[p]
                    p += 1
                elif not f & same:
                    v += struct.unpack(">h", d[p:p + 2])[0]
                    p += 2
                values.append(v)
            coords.append(values)
        points = [(x, y, bool(f & 1)) for x, y, f in zip(coords[0], coords[1], flags)]
        out, first = [], 0
        for e in ends:
            out.append(points[first:e + 1])
            first = e + 1
        return out

    def _composite(self, p: int) -> tuple[tuple[tuple[float, float], ...], ...]:
        d, out = self.data, []
        while True:
            flags, gid = struct.unpack(">HH", d[p:p + 4])
            p += 4
            if flags & _WORDS:
                dx, dy = struct.unpack(">hh", d[p:p + 4])
                p += 4
            else:
                dx, dy = struct.unpack(">bb", d[p:p + 2])
                p += 2
            if not flags & _XY:
                raise ValueError("composite glyphs placed by point numbers are not supported")
            a, b, c, e = 1.0, 0.0, 0.0, 1.0
            f2 = lambda q: struct.unpack(">h", d[q:q + 2])[0] / 16384  # F2Dot14
            if flags & _SCALE:
                a = e = f2(p)
                p += 2
            elif flags & _XY_SCALE:
                a, e = f2(p), f2(p + 2)
                p += 4
            elif flags & _TWO_BY_TWO:
                a, b, c, e = f2(p), f2(p + 2), f2(p + 4), f2(p + 6)
                p += 8
            for contour in self.contours(gid):
                out.append(tuple((a * x + c * y + dx, b * x + e * y + dy) for x, y in contour))
            if not flags & _MORE:
                return tuple(out)

    def width(self, text: str, size: float, tracking: float = 0.0) -> float:
        """Advance width of `text` in pixels at `size` px per em, with `tracking` px between letters."""
        k = size / self.units_per_em
        return sum(self.advance(self.glyph(ch)) * k for ch in text) + tracking * max(0, len(text) - 1)

    def outline(self, text: str, size: float, x: float, baseline: float, tracking: float = 0.0) -> list[list[tuple[float, float]]]:
        """Polygons of `text` in pixels (y down), its first letter's origin at (x, baseline)."""
        k = size / self.units_per_em
        polys = []
        for ch in text:
            gid = self.glyph(ch)
            polys += [[(x + px * k, baseline - py * k) for px, py in c] for c in self.contours(gid)]
            x += self.advance(gid) * k + tracking
        return polys


def _flatten(points: list[tuple[int, int, bool]]) -> tuple[tuple[float, float], ...]:
    """A TrueType contour (on- and off-curve points, implied on-curve midpoints) as a polygon."""
    if not points:
        return ()
    n = len(points)
    start = next((i for i, p in enumerate(points) if p[2]), None)
    if start is None:  # all off-curve: start from the midpoint of the first two
        (x0, y0, _), (x1, y1, _) = points[0], points[1 % n]
        pts = [((x0 + x1) / 2, (y0 + y1) / 2, True)] + points[1:] + points[:1]
    else:
        pts = points[start:] + points[:start]
    out = [(float(pts[0][0]), float(pts[0][1]))]
    ctrl = None
    for x, y, on in pts[1:] + pts[:1]:
        if on:
            if ctrl is None:
                out.append((float(x), float(y)))
            else:
                out += _quad(out[-1], ctrl, (x, y))
                ctrl = None
        elif ctrl is None:
            ctrl = (x, y)
        else:
            mid = ((ctrl[0] + x) / 2, (ctrl[1] + y) / 2)
            out += _quad(out[-1], ctrl, mid)
            ctrl = (x, y)
    return tuple(out[:-1]) if len(out) > 1 and out[-1] == out[0] else tuple(out)


def _quad(p0, c, p1) -> list[tuple[float, float]]:
    out = []
    for s in range(1, CURVE_STEPS + 1):
        t = s / CURVE_STEPS
        u = 1 - t
        out.append((u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0], u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1]))
    return out


@lru_cache(maxsize=None)
def cinzel() -> Font:
    """The bundled display font (Cinzel, OFL 1.1)."""
    return Font.load(FONTS / "Cinzel.ttf")
