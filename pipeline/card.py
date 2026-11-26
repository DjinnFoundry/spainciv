"""The social card (og-image.png, 1200×630) of a country with a `page`, drawn from its built web data.

The map is the terrain view of world.json: each hex in its land-cover colour with the relief and hill-shading of the
web map (mirrors `terrainRGB` in web/js/world.js; the colours themselves come from world.json `tables`), the sea by
depth, foreign land fogged, region borders, the national border, the coast and the rivers. It is framed on the
country's own hexes, insets included (their boxes outlined), and the largest cities are labelled. A side panel
carries the product name, `page.card_title`, the address and the licence notices the map must show.

Everything comes from the built data and Country.page, so `pipeline package` redraws the card whenever they change.
Standard library only: core.raster draws, core.font reads the bundled Cinzel, core.png encodes.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from .build.world import FOREIGN, WATER
from .core.font import Font, cinzel
from .core.hexgrid import HexGrid
from .core.raster import Canvas, circle, hex_rgb, mix
from .countries import Country, active

WIDTH, HEIGHT = 1200, 630
PANEL_X = 800  # the text panel starts here; the map is framed in the space to its left
SUPERSAMPLE = 2  # map samples per pixel along each axis
PAD_KM = 25.0  # sea around the country's hexes
N_CITIES = 8

OCEAN_DEEP = hex_rgb("#0d2a47")
GOLD, GOLD_LIGHT, CREAM, MUTED, INK = hex_rgb("#c9a45c"), hex_rgb("#ecd08e"), hex_rgb("#f3e6c4"), hex_rgb("#b9ab88"), (18, 14, 8)
PANEL = (12, 22, 34)
RIVER = hex_rgb("#4f93c4")
REGION_LINE, NATION_LINE, COAST_LINE = ((24, 16, 8), 0.5), ((255, 232, 160), 0.85), ((240, 226, 180), 0.45)

# pct group → the cover id whose colour stands for it (web/js/world.js PCT_COVER).
PCT_COVER = {"forest": 3, "crop": 7, "pasture": 6, "grass": 5, "shrub": 4, "wetland": 8, "developed": 9}
# Elevation ramp for land without land cover (web/js/terrain.js ELEV_STOPS).
ELEV_STOPS = [(e, hex_rgb(c)) for e, c in ((-100, "#5d8a39"), (250, "#7c9744"), (700, "#a39c58"), (1400, "#b09366"), (2200, "#9a8068"), (3000, "#8c8078"), (3800, "#d8dde0"))]


# --- hex colours: the web map's terrain view (web/js/world.js) -------------------------------------------------

def shade(c, k: float):
    """k > 0 lightens toward white, k < 0 darkens toward black."""
    return mix(c, (255, 255, 255), k) if k >= 0 else mix(c, (0, 0, 0), -k)


def desaturate(c, t: float):
    g = 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2]
    return mix(c, (g, g, g), t)


def hash01(i: int, salt: int = 0) -> float:
    """web/js/hex.js hash01: the web map's per-cell jitter."""
    h = (i * 374761393 + salt * 668265263) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return (h ^ (h >> 16)) / 4294967296


def elev_colour(e: float):
    if e <= ELEV_STOPS[0][0]:
        return ELEV_STOPS[0][1]
    for (e0, c0), (e1, c1) in zip(ELEV_STOPS, ELEV_STOPS[1:]):
        if e <= e1:
            return mix(c0, c1, (e - e0) / (e1 - e0))
    return ELEV_STOPS[-1][1]


def grid_of(world: dict) -> HexGrid:
    g = world["grid"]
    return HexGrid(g["radius"], g["cols"], g["rows"])


def hill_shade(world: dict, grid: HexGrid, i: int) -> float:
    """Light from the north-west, from the neighbours' elevation differences (web/js/world.js shadeK)."""
    elev, water = world["elev"], world["water"]
    z = elev[i]

    def e(d):
        j = grid.neighbour(i, d)
        return z if j < 0 or water[j] else elev[j]

    illum = (e(0) - e(3)) / (2 * math.sqrt(3) * grid.radius) + ((e(1) + e(2)) / 2 - (e(4) + e(5)) / 2) / (3 * grid.radius)
    return max(-0.32, min(0.32, illum * 0.03))


def hex_colours(world: dict) -> list[tuple[float, float, float]]:
    """Terrain-view colour of every hex (web/js/world.js terrainRGB)."""
    grid = grid_of(world)
    owner, elev, water, relief, cover = world["owner"], world["elev"], world["water"], world["relief"], world["cover"]
    pct = {k: v for k, v in (world.get("pct") or {}).items() if k in PCT_COVER}
    cover_rgb = {t["id"]: hex_rgb(t["color"]) for t in world["tables"]["cover"] if t.get("color")}
    water_rgb = {t["id"]: hex_rgb(t["color"]) for t in world["tables"]["water"] if t.get("color")}
    out = []
    for i in range(grid.size):
        wt = water[i]
        if wt:
            base = water_rgb.get(wt, water_rgb[1])
            if wt == 1:
                base = mix(base, OCEAN_DEEP, min(1.0, max(0.0, -elev[i] / 4000)))
            elif wt == 2:
                base = shade(base, max(-0.08, min(0.06, (elev[i] + 100) / 1500)))
            out.append(base)
            continue
        cv = cover[i]
        c = cover_rgb[cv] if cv > 0 and cv in cover_rgb else elev_colour(elev[i])
        if cv > 0:
            # A little of the hex's mixture, so a farm hex with 40% forest reads greener than a pure one.
            parts = [(pct[k][i], cover_rgb[cid]) for k, cid in PCT_COVER.items() if k in pct and pct[k][i] and cid in cover_rgb]
            tot = sum(p for p, _ in parts)
            if tot > 0:
                c = mix(c, [sum(p * col[k] for p, col in parts) / tot for k in range(3)], 0.3)
            c = mix(c, (176, 160, 128), max(0.0, min(1.0, (elev[i] - 300) / 2800)) * 0.28)  # high country: dustier
        rel = relief[i]
        if rel >= 2:
            c = mix(c, (200, 204, 208) if rel == 3 else (128, 116, 102), 0.45 if rel == 3 else 0.32)
        elif rel == 1:
            c = shade(c, -0.05)
        c = shade(c, (hash01(i, 7) - 0.5) * 0.08 + hill_shade(world, grid, i))
        if owner[i] == FOREIGN:
            c = mix(shade(desaturate(c, 0.6), -0.3), (70, 82, 96), 0.25)  # fog of war
        out.append(c)
    return out


# --- framing ---------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class View:
    """Map km → card pixels: x_px = ox + x_km * scale."""

    scale: float
    ox: float
    oy: float

    def px(self, x: float, y: float) -> tuple[float, float]:
        return self.ox + x * self.scale, self.oy + y * self.scale


def inset_boxes(world: dict) -> list[tuple[float, float, float, float]]:
    """The inset boxes (e.g. the Canary Islands) in map km: x0, y0, x1, y1 with y down."""
    p = world.get("country", {}).get("projection", {})
    to_map = lambda x, y: (x - p["min_x"] + p["margin"], p["max_y"] - y + p["margin"])
    out = []
    for s in p.get("insets", []):
        x0, y0, x1, y1 = s["box"]  # base km, y up
        out.append((*to_map(x0, y1), *to_map(x1, y0)))
    return out


def frame(world: dict, width: float, height: float) -> View:
    """Fit the country's hexes (and its inset boxes) into width × height px, centred."""
    grid = grid_of(world)
    xs, ys = [], []
    for i, o in enumerate(world["owner"]):
        if o >= 0:
            x, y = grid.center(*grid.col_row(i))
            xs.append(x)
            ys.append(y)
    for x0, y0, x1, y1 in inset_boxes(world):
        xs += [x0, x1]
        ys += [y0, y1]
    x0, x1 = min(xs) - PAD_KM, max(xs) + PAD_KM
    y0, y1 = min(ys) - PAD_KM, max(ys) + PAD_KM
    scale = min(width / (x1 - x0), height / (y1 - y0))
    return View(scale, (width - (x1 - x0) * scale) / 2 - x0 * scale, (height - (y1 - y0) * scale) / 2 - y0 * scale)


# --- drawing ---------------------------------------------------------------------------------------------------

def draw_map(canvas: Canvas, world: dict, view: View, width: int) -> None:
    """The hexes, supersampled, with the borders and the coast traced where neighbouring samples change hex owner."""
    grid = grid_of(world)
    colours = hex_colours(world)
    owner = world["owner"]
    s = SUPERSAMPLE
    step = 1 / (view.scale * s)
    cell = grid.cell_at

    xs = [(px + 0.5) * step - view.ox / view.scale for px in range(width * s)]
    prev = None
    for py in range(canvas.height):
        acc = [[0.0, 0.0, 0.0] for _ in range(width)]
        for sy in range(s):
            y = (py * s + sy + 0.5) * step - view.oy / view.scale
            line = [cell(x, y) for x in xs]
            for sx, c in enumerate(line):
                col = colours[c] if c >= 0 else OCEAN_DEEP
                o = owner[c] if c >= 0 else WATER
                for d in (line[sx + 1] if sx + 1 < len(line) else c, prev[sx] if prev else c):
                    od = owner[d] if d >= 0 else WATER
                    if od == o:
                        continue
                    if o >= 0 and od >= 0:
                        col = mix(col, *REGION_LINE)
                    elif WATER not in (o, od):
                        col = mix(col, *NATION_LINE)
                    else:
                        col = mix(col, *COAST_LINE)
                a = acc[sx // s]
                a[0] += col[0]
                a[1] += col[1]
                a[2] += col[2]
            prev = line
        n = s * s
        for x, a in enumerate(acc):
            canvas.set(x, py, (a[0] / n, a[1] / n, a[2] / n))


def draw_rivers(canvas: Canvas, world: dict, view: View) -> None:
    for river in world.get("rivers", []):
        pts = river["pts"]
        line = [view.px(pts[k], pts[k + 1]) for k in range(0, len(pts) - 1, 2)]
        canvas.stroke(line, max(0.9, 2.2 - 0.15 * river.get("rank", 6)), RIVER, 0.85)


def draw_insets(canvas: Canvas, world: dict, view: View) -> None:
    for box in inset_boxes(world):
        (x0, y0), (x1, y1) = view.px(*box[:2]), view.px(*box[2:])
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        canvas.stroke(corners, 3.0, INK, 0.45)
        canvas.stroke(corners, 1.2, GOLD, 0.9)


def draw_cities(canvas: Canvas, cities: list[dict], view: View, capital: str | None, font: Font) -> None:
    """The largest cities: a marker and the name, right of it, left of it, above or below, whichever is first clear
    of the names already placed and of the panel. A name with no room is left out (its marker stays)."""
    biggest = sorted((c for c in cities if c.get("population")), key=lambda c: -c["population"])[:N_CITIES]
    biggest.sort(key=lambda c: c["id"] != capital)
    taken: list[tuple[float, float, float, float]] = []
    for c in biggest:
        x, y = view.px(c["x"], c["y"])
        cap = c["id"] == capital
        r = 5.0 if cap else 3.6
        canvas.fill([_disc(x, y, r + 1.6)], INK, 0.85)
        canvas.fill([_disc(x, y, r)], GOLD_LIGHT if cap else CREAM)
        size = 19 if cap else 16
        w, h, gap = font.width(c["name"], size, 0.5), size * 0.8, r + 6
        for lx, base in ((x + gap, y + h / 2), (x - gap - w, y + h / 2), (x - w / 2, y - gap), (x - w / 2, y + gap + h)):
            box = (lx - 3, base - h - 3, lx + w + 3, base + 4)
            if box[0] > 4 and box[2] < PANEL_X - 6 and not any(_overlap(box, t) for t in taken):
                taken.append(box)
                canvas.text(font, c["name"], size, lx, base, CREAM, tracking=0.5, halo=(INK, 0.8, 2.2))
                break


def _overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def draw_panel(canvas: Canvas, country: Country, font: Font) -> None:
    page = country.page
    x0 = PANEL_X
    # A dark panel fading in over the map's edge, with a gold rule.
    fade = 90
    for k in range(fade):
        canvas.rect(x0 - fade + k, 0, x0 - fade + k + 1, HEIGHT, PANEL, ((k + 1) / fade) ** 1.6 * 0.92)
    canvas.rect(x0, 0, WIDTH, HEIGHT, PANEL, 0.92)
    canvas.rect(x0, 0, x0 + 2, HEIGHT, GOLD, 0.9)
    canvas.rect(x0 + 5, 0, x0 + 6, HEIGHT, GOLD_LIGHT, 0.25)
    cx = (x0 + 6 + WIDTH) / 2
    inner = WIDTH - x0 - 70

    # Emblem: the share image's gold ring and star.
    ey = 128
    canvas.fill([_disc(cx, ey, 40)], INK)
    canvas.fill([_disc(cx, ey, 37.5)], GOLD)
    canvas.fill([_disc(cx, ey, 32.5)], hex_rgb("#2a4d8f"))
    canvas.fill([_star(cx, ey + 1.5, 19, 8)], hex_rgb("#f8f0d8"))

    title = country.product.upper()
    size = 64.0
    while font.width(title, size, size * 0.08) > inner and size > 30:
        size -= 2
    canvas.text(font, title, size, cx, 248, GOLD_LIGHT, tracking=size * 0.08, align="center", halo=(INK, 0.6, 2.5))

    # A rule with a diamond, then the card title.
    ry = 282
    canvas.rect(cx - 120, ry, cx - 12, ry + 1.2, GOLD, 0.8)
    canvas.rect(cx + 12, ry, cx + 120, ry + 1.2, GOLD, 0.8)
    canvas.fill([[(cx, ry - 6), (cx + 6, ry + 0.6), (cx, ry + 7), (cx - 6, ry + 0.6)]], GOLD)
    y = 336
    for line in wrap(font, page.card_title, 30, inner, 0.6):
        canvas.text(font, line, 30, cx, y, CREAM, tracking=0.6, align="center")
        y += 42

    canvas.text(font, country.site_url, 21, cx, HEIGHT - 74, GOLD_LIGHT, tracking=1.0, align="center")
    y = HEIGHT - 44
    for notice in page.notices:
        for line in wrap(font, notice, 12, WIDTH - PANEL_X - 24, 0.2):
            canvas.text(font, line, 12, cx, y, MUTED, tracking=0.2, align="center")
            y += 17


def wrap(font: Font, text: str, size: float, width: float, tracking: float = 0.0) -> list[str]:
    """`text` in the fewest lines at most `width` px wide (a word wider than that gets a line of its own), broken
    where the longest line is shortest, so the lines come out even."""
    words = text.split()
    widest = lambda lines: max(font.width(line, size, tracking) for line in lines)
    for n in range(1, len(words) + 1):
        options = [[" ".join(words[a:b]) for a, b in zip((0, *cuts), (*cuts, len(words)))] for cuts in combinations(range(1, len(words)), n - 1)]
        best = min(options, key=widest)
        if widest(best) <= width or n == len(words):
            return best
    return [text]


def _disc(x: float, y: float, r: float) -> list[tuple[float, float]]:
    return circle(x, y, r, 28)


def _star(x: float, y: float, r: float, r_in: float) -> list[tuple[float, float]]:
    radii = [r if k % 2 == 0 else r_in for k in range(10)]
    return [(x + rk * math.sin(math.pi * k / 5), y - rk * math.cos(math.pi * k / 5)) for k, rk in enumerate(radii)]


def render(world: dict, cities: list[dict], country: Country) -> Canvas:
    font = cinzel()
    canvas = Canvas(WIDTH, HEIGHT, OCEAN_DEEP)
    view = frame(world, PANEL_X, HEIGHT)
    draw_map(canvas, world, view, WIDTH)
    draw_rivers(canvas, world, view)
    draw_insets(canvas, world, view)
    draw_cities(canvas, cities, view, country.capital_city, font)
    draw_panel(canvas, country, font)
    return canvas


def card_png(country: Country | None = None, data_dir: Path | None = None) -> bytes:
    """The country's og-image.png, from world.json and cities.json in its web data folder."""
    c = country or active()
    if c.page is None:
        raise ValueError(f"{c.id} has no page: its card is web/og-image.png")
    folder = data_dir or c.web_data_dir
    world = json.loads((folder / "world.json").read_text(encoding="utf-8"))
    cities = json.loads((folder / "cities.json").read_text(encoding="utf-8"))
    return render(world, cities, c).png()
