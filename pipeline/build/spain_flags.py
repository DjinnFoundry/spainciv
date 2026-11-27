"""The flags of the autonomous communities and cities, simplified for the Unciv mod's nation icons and colours.

Each flag is laid out as its Statute (or the law on its symbols) describes it, in the BOE's consolidated text: the
fields, stripes, crosses and figures, without the coats of arms that some carry in the centre (Aragón, La Rioja,
Ceuta, Melilla), which a 100-pixel disc cannot show. The figures that are the flag itself are kept, drawn plainly:
the castles and lions of Castilla y León, the castle of Castilla-La Mancha and of the Balearic canton, the castles
and crowns of Murcia, the stars of Madrid, the cross of Asturias, and the chains of Navarra's arms (without their
crown and emerald), which are all its flag shows on the red. A flag is
drawn in a unit square (x right, y down; a real flag's 3:2 or 2:1 is squeezed into it), as layers of one colour each,
the first the whole field.

Colours: the Statutes name them (verde, rojo carmesí, azul celeste…) and only Asturias fixes values in a law (Ley
4/1990: Pantone 829 and 109); the RGB values here are the game's convention for each named colour, darkened where
Unciv needs it to read (its RulesetValidator asks for a WCAG contrast of 3 between a nation's two colours). `outer`
and `inner` are the two Unciv colours of the nation (outerColor, the field of its emblem and its borders; innerColor,
its icon), two of the flag's own, chosen so that no two nations share both.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Colour = tuple[int, int, int]
Polygon = list[tuple[float, float]]

WHITE, BLACK = (255, 255, 255), (0, 0, 0)
GREEN = (0, 122, 61)  # verde (Andalucía, Extremadura, La Rioja)
RED = (218, 18, 26)  # rojo de las barras (the Senyera: Aragón, Cataluña, Illes Balears, Comunitat Valenciana)
YELLOW = (252, 221, 9)  # amarillo / oro
CRIMSON = (153, 0, 51)  # rojo carmesí (Castilla-La Mancha)
MADRID_CRIMSON = (196, 16, 48)  # rojo carmesí (Madrid)
CARTAGENA = (155, 0, 32)  # rojo carmesí o cartagena (Murcia)
NAVARRA_RED = (200, 0, 0)  # rojo (Navarra)
GULES = (198, 12, 48)  # gules (Castilla y León)
PURPLE = (102, 0, 153)  # morado, púrpura (the Balearic canton, the lions of Castilla y León)
ASTURIAS_BLUE, ASTURIAS_YELLOW = (0, 102, 204), (255, 209, 0)  # Pantone 829 and 109 (Ley 4/1990), approximated
CANARIAS_BLUE = (0, 82, 165)  # azul
VALENCIA_BLUE = (0, 56, 168)  # franja azul
CELESTE = (0, 122, 195)  # azul celeste (Galicia's band, Melilla), darkened so white reads on it
IKURRINA_RED, IKURRINA_GREEN = (218, 41, 28), (0, 154, 68)  # Pantone 485 C and 347 C (Basque Government)
CANTABRIA_RED = (213, 43, 30)  # roja


@dataclass(frozen=True)
class Flag:
    outer: Colour
    inner: Colour
    layers: tuple[tuple[Colour, tuple[Polygon, ...]], ...]  # (colour, polygons), drawn in order

    def json(self) -> list:
        """The layers as unciv.json keeps them: [[r, g, b], [[[x, y], ...], ...]], coordinates to 4 decimals."""
        return [[list(c), [[[round(x, 4), round(y, 4)] for x, y in p] for p in polys]] for c, polys in self.layers]


def box(x0: float, y0: float, x1: float, y1: float) -> Polygon:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


FIELD = box(0, 0, 1, 1)


def hstripes(n: int, which) -> tuple[Polygon, ...]:
    return tuple(box(0, k / n, 1, (k + 1) / n) for k in which)


def vstripes(n: int, which) -> tuple[Polygon, ...]:
    return tuple(box(k / n, 0, (k + 1) / n, 1) for k in which)


def band(x0: float, y0: float, x1: float, y1: float, width: float) -> Polygon:
    """A straight band `width` wide from (x0, y0) to (x1, y1), its ends cut square and running past the square."""
    d = math.hypot(x1 - x0, y1 - y0)
    ux, uy = (x1 - x0) / d, (y1 - y0) / d
    nx, ny = -uy * width / 2, ux * width / 2
    ax, ay, bx, by = x0 - ux, y0 - uy, x1 + ux, y1 + uy
    return [(ax + nx, ay + ny), (bx + nx, by + ny), (bx - nx, by - ny), (ax - nx, ay - ny)]


def star(cx: float, cy: float, r: float, points: int = 5) -> Polygon:
    """A star of `points` points, one up."""
    return [(cx + (r if k % 2 == 0 else r * 0.382) * math.sin(math.pi * k / points),
             cy - (r if k % 2 == 0 else r * 0.382) * math.cos(math.pi * k / points)) for k in range(2 * points)]


def castle(cx: float, cy: float, w: float, towers: int = 3) -> tuple[Polygon, ...]:
    """A castle `w` wide standing on (cx, cy): a wall with a gate-less block and `towers` crenellated towers."""
    h, t = w * 0.9, w / (2 * towers - 1)
    wall = box(cx - w / 2, cy - h * 0.55, cx + w / 2, cy)
    out = [wall]
    for k in range(towers):
        x = cx - w / 2 + 2 * k * t
        top = cy - h * (1.0 if k == towers // 2 else 0.8)
        out.append(box(x, top, x + t, cy - h * 0.5))
    return tuple(out)


def crown(cx: float, cy: float, w: float) -> Polygon:
    """A royal crown `w` wide on (cx, cy): a band with three points."""
    h = w * 0.7
    return [(cx - w / 2, cy), (cx + w / 2, cy), (cx + w / 2, cy - h), (cx + w / 4, cy - h * 0.55), (cx, cy - h),
            (cx - w / 4, cy - h * 0.55), (cx - w / 2, cy - h)]


def lion(cx: float, cy: float, s: float) -> tuple[Polygon, ...]:
    """A rampant lion facing the hoist side's right, `s` tall, centred on (cx, cy): body, head, legs and tail."""
    p = lambda pts: [(cx + x * s, cy + y * s) for x, y in pts]
    return (p([(-0.15, -0.25), (0.12, -0.3), (0.18, 0.2), (-0.1, 0.25)]),  # body, leaning up
            p([(0.0, -0.5), (0.22, -0.48), (0.26, -0.3), (0.05, -0.25)]),  # head
            p([(0.12, -0.25), (0.38, -0.38), (0.42, -0.3), (0.16, -0.12)]),  # forelegs up
            p([(-0.1, 0.2), (-0.05, 0.5), (0.05, 0.5), (0.05, 0.2)]), p([(0.1, 0.18), (0.25, 0.48), (0.33, 0.45), (0.2, 0.15)]),
            p([(-0.15, 0.05), (-0.42, -0.2), (-0.38, -0.26), (-0.12, -0.05)]))  # tail


def senyera(field: Colour = YELLOW, bars: Colour = RED, x0: float = 0.0) -> tuple:
    """Four red bars on yellow: nine equal stripes, the even ones yellow, from x0 to the fly."""
    return ((field, (FIELD,)), (bars, tuple(box(x0, k / 9, 1, (k + 1) / 9) for k in (1, 3, 5, 7))))


def ceuta_gyrons() -> tuple[Polygon, ...]:
    """The black four of Ceuta's eight triangles (LO 1/1995, art. 3): made by the diagonals and the lines through the
    centre of the sides, the first black one between the top-left corner, the centre and the middle of the top."""
    ring = [(0, 0), (0.5, 0), (1, 0), (1, 0.5), (1, 1), (0.5, 1), (0, 1), (0, 0.5)]  # clockwise from the top-left
    return tuple([ring[k], ring[k + 1], (0.5, 0.5)] for k in range(0, 8, 2))


def navarra_chains() -> tuple[Polygon, ...]:
    """The gold chains (LORAFNA, art. 7: chains of gold on red, eight arms joined in the centre): an orle, a cross and
    a saltire, drawn as plain bands."""
    w = 0.07
    frame = tuple(box(*b) for b in ((0.18, 0.18, 0.82, 0.18 + w), (0.18, 0.82 - w, 0.82, 0.82),
                                    (0.18, 0.18, 0.18 + w, 0.82), (0.82 - w, 0.18, 0.82, 0.82)))
    arms = (box(0.5 - w / 2, 0.18, 0.5 + w / 2, 0.82), box(0.18, 0.5 - w / 2, 0.82, 0.5 + w / 2))
    return frame + arms + saltire(w, 0.18, 0.82)


def saltire(width: float, lo: float = 0, hi: float = 1) -> tuple[Polygon, ...]:
    """Two diagonal bands `width` wide, corner to corner of the square [lo, hi]²."""
    return tuple(clip_square(band(a, b, c, d, width), lo, hi) for a, b, c, d in ((0, 0, 1, 1), (1, 0, 0, 1)))


def clip_square(poly: Polygon, lo: float, hi: float) -> Polygon:
    """`poly` clipped to the square [lo, hi]² (Sutherland–Hodgman, one side at a time)."""
    def clip(pts, inside, cross):
        out = []
        for a, b in zip(pts, pts[1:] + pts[:1]):
            if inside(b):
                if not inside(a):
                    out.append(cross(a, b))
                out.append(b)
            elif inside(a):
                out.append(cross(a, b))
        return out

    def at_x(x):
        return lambda a, b: (x, a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]))

    def at_y(y):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]), y)

    for inside, cross in ((lambda p: p[0] >= lo, at_x(lo)), (lambda p: p[0] <= hi, at_x(hi)),
                          (lambda p: p[1] >= lo, at_y(lo)), (lambda p: p[1] <= hi, at_y(hi))):
        poly = clip(poly, inside, cross)
    return poly


# INE code (pipeline/sources/es/provinces.py COMMUNITIES) → its flag, from the article quoted.
FLAGS = {
    # Andalucía, LO 2/2007 art. 3.1: three horizontal stripes, green, white and green, of equal width.
    "01": Flag(GREEN, WHITE, ((GREEN, (FIELD,)), (WHITE, hstripes(3, [1])))),
    # Aragón, LO 5/2007 art. 3: four red horizontal bars on yellow (the arms in the centre left out).
    "02": Flag(YELLOW, RED, senyera()),
    # Asturias, LO 7/1981 art. 3.1: the Cross of Victory in yellow on blue (drawn as a plain cross, nearer the hoist).
    "03": Flag(ASTURIAS_BLUE, ASTURIAS_YELLOW, ((ASTURIAS_BLUE, (FIELD,)),
                                               (ASTURIAS_YELLOW, (box(0.33, 0.15, 0.43, 0.85), box(0.18, 0.33, 0.58, 0.43))))),
    # Illes Balears, LO 1/2007 art. 6.1: four red bars on yellow, a purple canton at the top left with a white castle
    # of five towers.
    "04": Flag(PURPLE, WHITE, (*senyera(), (PURPLE, (box(0, 0, 0.5, 5 / 9),)), (WHITE, castle(0.25, 0.42, 0.3, 5)))),
    # Canarias, LO 1/2018 art. 7.1: three equal vertical stripes, from the hoist white, blue and yellow.
    "05": Flag(CANARIAS_BLUE, WHITE, ((CANARIAS_BLUE, (FIELD,)), (WHITE, vstripes(3, [0])), (YELLOW, vstripes(3, [2])))),
    # Cantabria, LO 8/1981 art. 3: two horizontal stripes of equal width, white above and red below.
    "06": Flag(WHITE, CANTABRIA_RED, ((WHITE, (FIELD,)), (CANTABRIA_RED, hstripes(2, [1])))),
    # Castilla y León, LO 14/2007 art. 6.3–6.4: quartered, gold castles on gules (1st and 4th), purple lions on silver
    # (2nd and 3rd).
    "07": Flag(WHITE, PURPLE, ((WHITE, (FIELD,)), (GULES, (box(0, 0, 0.5, 0.5), box(0.5, 0.5, 1, 1))),
                               (YELLOW, castle(0.25, 0.4, 0.28) + castle(0.75, 0.9, 0.28)),
                               (PURPLE, lion(0.75, 0.25, 0.4) + lion(0.25, 0.75, 0.4)))),
    # Castilla-La Mancha, LO 9/1982 art. 5.1: two squares, crimson with a gold castle by the hoist, then white.
    "08": Flag(WHITE, CRIMSON, ((WHITE, (FIELD,)), (CRIMSON, vstripes(2, [0])), (YELLOW, castle(0.25, 0.68, 0.32)))),
    # Cataluña, LO 6/2006 art. 8.2: four red bars on yellow.
    "09": Flag(RED, YELLOW, senyera()),
    # Comunitat Valenciana, LO 5/1982 art. 4.1: the Senyera, four red bars on yellow, crowned on a blue band by the
    # hoist (the crown drawn plain).
    "10": Flag(YELLOW, VALENCIA_BLUE, (*senyera(x0=0.25), (VALENCIA_BLUE, (box(0, 0, 0.25, 1),)),
                                       (YELLOW, (crown(0.125, 0.2, 0.16),)))),
    # Extremadura, LO 1/2011 art. 4.1: three equal horizontal stripes, green, white and black.
    "11": Flag(BLACK, GREEN, ((WHITE, (FIELD,)), (GREEN, hstripes(3, [0])), (BLACK, hstripes(3, [2])))),
    # Galicia, LO 1/1981 art. 6.1: white, crossed by a blue diagonal band from the top left to the bottom right.
    "12": Flag(WHITE, CELESTE, ((WHITE, (FIELD,)), (CELESTE, (clip_square(band(0, 0, 1, 1, 0.3), 0, 1),)))),
    # Madrid, LO 3/1983 art. 4.1: crimson, with seven white five-pointed stars, four and three, in the centre.
    "13": Flag(MADRID_CRIMSON, WHITE, ((MADRID_CRIMSON, (FIELD,)),
                                       (WHITE, tuple(star(0.2 + 0.2 * k, 0.4, 0.085) for k in range(4))
                                        + tuple(star(0.3 + 0.2 * k, 0.62, 0.085) for k in range(3))))),
    # Murcia, LO 4/1982 art. 4.1: crimson (cartagena), four gold castles two by two at the top left and seven royal
    # crowns in rows of one, three, two and one at the bottom right.
    "14": Flag(CARTAGENA, YELLOW, ((CARTAGENA, (FIELD,)),
                                   (YELLOW, tuple(p for x, y in ((0.3, 0.32), (0.48, 0.32), (0.3, 0.5), (0.48, 0.5))
                                                  for p in castle(x, y, 0.14))
                                    + tuple(crown(x, y, 0.09) for x, y in ((0.66, 0.56), (0.55, 0.66), (0.66, 0.66),
                                                                            (0.77, 0.66), (0.6, 0.76), (0.72, 0.76),
                                                                            (0.66, 0.86)))))),
    # Navarra, LORAFNA art. 7: red, with the arms in the centre, gold chains on red (drawn without the crown and the
    # emerald).
    "15": Flag(NAVARRA_RED, YELLOW, ((NAVARRA_RED, (FIELD,)), (YELLOW, navarra_chains()))),
    # Euskadi / País Vasco, LO 3/1979 art. 5.1: the bicrucífera, a green saltire under a white cross on red.
    "16": Flag(IKURRINA_RED, WHITE, ((IKURRINA_RED, (FIELD,)),
                                     (IKURRINA_GREEN, saltire(0.12)),
                                     (WHITE, (box(0.44, 0, 0.56, 1), box(0, 0.44, 1, 0.56))))),
    # La Rioja, LO 3/1982 art. 3.1: four equal horizontal stripes, red, white, green and yellow (the arms left out).
    "17": Flag(GREEN, YELLOW, ((RED, (FIELD,)), (WHITE, hstripes(4, [1])), (GREEN, hstripes(4, [2])),
                               (YELLOW, hstripes(4, [3])))),
    # Ceuta, LO 1/1995 art. 3.1: four white and four black triangles (the arms left out).
    "18": Flag(BLACK, WHITE, ((WHITE, (FIELD,)), (BLACK, ceuta_gyrons()))),
    # Melilla, LO 2/1995 art. 3.1: sky blue with the city's arms in the centre (left out).
    "19": Flag(CELESTE, WHITE, ((CELESTE, (FIELD,)),)),
}


def luminance(c: Colour) -> float:
    """WCAG relative luminance (as Unciv's Color.getRelativeLuminance)."""
    def lin(v: int) -> float:
        s = v / 255
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = map(lin, c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: Colour, b: Colour) -> float:
    """WCAG contrast ratio (Unciv's getContrastRatio), 1 to 21."""
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)
