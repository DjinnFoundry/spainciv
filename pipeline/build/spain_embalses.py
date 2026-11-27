"""Spain's reservoirs week by week (embalses.json, embalses_semanas.json) for the reservoirs lens (web/js/ext/embalses).

* **Basins** (E87): a land hex goes to the Boletín basin (DDHH polygon) that holds its centre; a peninsular one
  outside every polygon (the 1:… coast of the layer is simplified) to the nearest polygon within SNAP_KM, else to
  none. The hexes of the island provinces, Ceuta and Melilla get none, by province code: the Boletín covers the
  peninsula only.
* **Basin figures**: per week, Σ water stored and Σ capacity of the basin's reservoirs that report that week
  (pipeline/sources/es/embalses.py), the Boletín's own formula.
* **Positions** (E87): (1) the Boletín map's point with the identical basin and name, which every reservoir of the
  latest week must have; (2) for a reservoir it no longer reports, the Wikidata reservoirs and dams one of whose names
  normalises to the same as its own (`name_key`) and that lie inside its basin or within WIKIDATA_KM of it: their mean
  when they all lie within WIKIDATA_KM of each other, else none. No fuzzy matching (E74's rule).
* A point goes to the hex that holds it, or the nearest land hex when it falls off the drawn land.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path

from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from ..countries import active
from ..sources.es.embalses import basin_totals, capacity_at
from .cities import nearest_land

REQUIRES = ["_world", "boletin_hidrologico", "wikidata_presas"]
FILE, WEEKS_FILE = "embalses", "embalses_semanas"
PRODUCES = [f"{FILE}.json", f"{WEEKS_FILE}.json"]
COUNTRIES = ("es",)

SNAP_KM = 10.0  # a peninsular land hex outside every basin polygon joins the nearest one this close
WIKIDATA_KM = 2.0  # a Wikidata item this far outside the basin still counts; candidates this close are one place
# Illes Balears, Las Palmas, Santa Cruz de Tenerife, Ceuta, Melilla: outside the Boletín.
OFF_BOLETIN = frozenset({"07", "35", "38", "51", "52"})

# Words a reservoir's name may carry or not ("Embalse de La Breña", "Breña, La", "Pantà de Sau", "Ercina (Lago)",
# "Presa y embalse de Derivación del Retortillo"): the kind of water body in the languages of Spain, articles,
# prepositions and the "and" of "presa y embalse".
NAME_WORDS = frozenset(
    "embalse presa pantano embassament panta encoro urtegia lago estany ibon azud "
    "el la los las lo l de del d els les o os a as da do das dos y i".split())


def name_key(name: str) -> str:
    """A reservoir's name for matching: lowercase, no accents, punctuation or parentheses, without NAME_WORDS.
    'Breña, La' and 'Embalse de La Breña' → 'brena'; 'Malpasillo ( Jauja )' → 'malpasillo jauja'."""
    s = "".join(c for c in unicodedata.normalize("NFKD", name.lower()) if not unicodedata.combining(c))
    return " ".join(w for w in re.sub(r"[^a-z0-9]+", " ", s).split() if w not in NAME_WORDS)


# --- polygons in map km --------------------------------------------------------------------------------------------

def crossings(rings: list[list[tuple[float, float]]], y0: float, dy: float, rows: int) -> list[list[float]]:
    """For each hex row k (centre y = y0 + k·dy), the sorted x where the rings' edges cross it: a point of that row is
    inside (even-odd rule, holes included) when an odd number of crossings lie left of it."""
    out: list[list[float]] = [[] for _ in range(rows)]
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
            if y1 == y2:
                continue
            lo, hi = (y1, y2) if y1 < y2 else (y2, y1)
            for k in range(max(0, math.ceil((lo - y0) / dy)), min(rows, math.floor((hi - y0) / dy) + 1)):
                y = y0 + k * dy
                if lo <= y < hi:  # half-open, like ring_contains
                    out[k].append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    for xs in out:
        xs.sort()
    return out


def segment_km(px: float, py: float, a: tuple, b: tuple) -> float:
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


class Edges:
    """Polygon edges bucketed in squares of `cell` km, for the distance from a point to each polygon up to `cell`."""

    def __init__(self, shapes: list[list[list[tuple[float, float]]]], cell: float):
        self.cell = cell
        self.buckets: dict[tuple[int, int], list[tuple[int, tuple, tuple]]] = defaultdict(list)
        for k, rings in enumerate(shapes):
            for ring in rings:
                for a, b in zip(ring, ring[1:] + ring[:1]):
                    for gx in range(int(min(a[0], b[0]) // cell), int(max(a[0], b[0]) // cell) + 1):
                        for gy in range(int(min(a[1], b[1]) // cell), int(max(a[1], b[1]) // cell) + 1):
                            self.buckets[(gx, gy)].append((k, a, b))

    def nearest(self, x: float, y: float) -> dict[int, float]:
        """Distance (km) from (x, y) to the edges of each polygon that has one within `cell`."""
        gx, gy = int(x // self.cell), int(y // self.cell)
        best: dict[int, float] = {}
        for i in (gx - 1, gx, gx + 1):
            for j in (gy - 1, gy, gy + 1):
                for k, a, b in self.buckets.get((i, j), ()):
                    d = segment_km(x, y, a, b)
                    if d <= self.cell and d < best.get(k, math.inf):
                        best[k] = d
        return best


def inside(rings, x: float, y: float) -> bool:
    """Even-odd point in polygon over all rings (holes included)."""
    n = 0
    for ring in rings:
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                n += 1
    return n % 2 == 1


def basin_cells(grid: HexGrid, owner: list[int], codes: list[str], shapes: list, snap_km: float = SNAP_KM,
                off: frozenset = OFF_BOLETIN) -> tuple[list[int], dict]:
    """The basin (index into `shapes`, map-km rings) of each hex, -1 for none: the polygon holding its centre; for a
    land hex outside all of them, the nearest within `snap_km`; never for a hex of a province in `off` (`codes`: the
    province code of each owner index). Also counts {inside, snapped, outside, off}."""
    dy = 1.5 * grid.radius
    rows = [crossings(rings, 0.0, dy, grid.rows) for rings in shapes]
    edges = Edges(shapes, snap_km)
    out = [-1] * grid.size
    stats = {"inside": 0, "snapped": 0, "outside": 0, "off": 0}
    for c in range(grid.size):
        if owner[c] < 0:
            continue
        if codes[owner[c]] in off:
            stats["off"] += 1
            continue
        col, row = grid.col_row(c)
        x, _ = grid.center(col, row)
        hit = next((k for k, r in enumerate(rows) if bisect_right(r[row], x) % 2), -1)
        if hit < 0:
            near = edges.nearest(*grid.center(col, row))
            hit = min(near, key=near.get) if near else -1
            stats["snapped" if hit >= 0 else "outside"] += 1
        else:
            stats["inside"] += 1
        out[c] = hit
    return out, stats


def in_basin(rings, edges: Edges, k: int, x: float, y: float, km: float) -> bool:
    """Is (x, y) inside polygon k or within `km` of it?"""
    return inside(rings, x, y) or edges.nearest(x, y).get(k, math.inf) <= km


def match_wikidata(name: str, basin: int, items: dict[str, list[tuple]], rings, edges: Edges, proj,
                   km: float = WIKIDATA_KM) -> dict | None:
    """The Wikidata position of a reservoir: the items with a name of the same name_key (items: key → [(qid, lon,
    lat)]) inside its basin polygon or within `km` of it; their mean when all lie within `km` of each other, else
    None (also None without candidates)."""
    cands = []
    for q, lon, lat in items.get(name_key(name), []):
        x, y = proj(lon, lat)
        if in_basin(rings, edges, basin, x, y, km):
            cands.append((q, lon, lat, x, y))
    if not cands or any(math.dist(a[3:], b[3:]) > km for a in cands for b in cands):
        return None
    return {"lon": round(sum(c[1] for c in cands) / len(cands), 5), "lat": round(sum(c[2] for c in cands) / len(cands), 5),
            "qids": sorted({c[0] for c in cands}, key=lambda q: int(q[1:]))}


def wikidata_index(items: list[dict]) -> dict[str, list[tuple]]:
    """name_key → [(qid, lon, lat)], one entry per item and position."""
    out: dict[str, list[tuple]] = defaultdict(list)
    for it in items:
        for key in {name_key(n) for n in it["names"]} - {""}:
            for lon, lat in it["points"]:
                out[key].append((it["id"], lon, lat))
    return out


def build() -> None:
    world = load_interim("_world")
    src = load_interim("boletin_hidrologico")
    wd = load_interim("wikidata_presas")
    proj = active().world_projection(world)
    grid = HexGrid(**world["grid"])
    owner, codes = world["owner"], world["states"]
    dates, basins = src["dates"], src["basins"]
    last = len(dates) - 1
    order = {b["name"]: k for k, b in enumerate(basins)}
    shapes = [[[proj(lon, lat) for lon, lat in ring] for ring in b["rings"]] for b in basins]
    edges = Edges(shapes, WIKIDATA_KM)

    cell_basin, stats = basin_cells(grid, owner, codes, shapes)
    print(f"    hexes: {stats['inside']} inside a basin, {stats['snapped']} within {SNAP_KM:g} km of one, "
          f"{stats['outside']} peninsular without one, {stats['off']} outside the Boletín (islands, Ceuta, Melilla)")

    points = {(p["basin"], p["name"]): p for p in src["points"]}
    by_key = wikidata_index(wd["items"])
    reservoirs = sorted(src["reservoirs"], key=lambda r: (order[r["basin"]], r["name"]))
    out, placed_wd, unplaced = [], [], []
    for r in reservoirs:
        k = order[r["basin"]]
        p, where = points.get((r["basin"], r["name"])), None
        if p:
            where = {"lon": p["lon"], "lat": p["lat"], "placed": "boletin"}
        elif r["last"] == last:
            raise ValueError(f"{r['name']} ({r['basin']}) reports in the latest week and has no Boletín map point")
        elif m := match_wikidata(r["name"], k, by_key, shapes[k], edges, proj):
            where = {"lon": m["lon"], "lat": m["lat"], "placed": "wikidata", "qids": m["qids"]}
            placed_wd.append(r["name"])
        else:
            unplaced.append(r["name"])
        caps = r["capacity"]
        entry = {"name": r["name"], "basin": k, "use": r["use"], "lon": None, "lat": None, "x": None, "y": None,
                 "cell": None, "placed": None, "first": r["first"], "last": r["last"],
                 "capacity": caps[-1][1] if caps else None, "actual": r["actual"][r["last"]] if r["last"] is not None else None}
        if where:
            x, y = proj(where["lon"], where["lat"])
            cell = grid.cell_at(x, y)
            if cell < 0 or owner[cell] < 0:
                cell = nearest_land(grid, owner, max(cell, 0), x, y, -1)
            entry.update({k2: where[k2] for k2 in ("lon", "lat", "placed")}, x=round(x, 2), y=round(y, 2), cell=cell)
            if "qids" in where:
                entry["qids"] = where["qids"]
        out.append(entry)
    print(f"    {len(out)} reservoirs: {sum(e['placed'] == 'boletin' for e in out)} at the Boletín's point, "
          f"{len(placed_wd)} placed from Wikidata ({', '.join(placed_wd)}), {len(unplaced)} unplaced "
          f"({', '.join(unplaced)})")

    totals = basin_totals(reservoirs, [b["name"] for b in basins], len(dates))
    cells: list[list[int]] = [[] for _ in basins]
    for c, k in enumerate(cell_basin):
        if k >= 0:
            cells[k].append(c)
    write_web(f"{FILE}.json", {
        "vintage": dates[-1], "provisional": True, "dates": dates,
        "basins": [{"name": b["name"], "cells": cells[k], **totals[b["name"]]} for k, b in enumerate(basins)],
        "reservoirs": out})
    write_web(f"{WEEKS_FILE}.json", {
        "vintage": dates[-1],
        "actual": [[r["actual"][i] for r in reservoirs] for i in range(len(dates))],
        "capacity": [r["capacity"] for r in reservoirs]})


def check(web_dir) -> list[tuple[str, str]]:
    """embalses.json against embalses_semanas.json and the Boletín: the basin series are the sums of the weekly matrix,
    the latest week's total is the Boletín map's, every placed point lies in its basin (WIKIDATA_KM), the dates are
    Tuesdays a week apart and each reservoir's first and last weeks are those its values say. Nothing to check on a
    map without the files."""
    from datetime import date, timedelta

    web_dir = Path(web_dir)
    if not (web_dir / f"{FILE}.json").exists():
        return []
    doc = json.loads((web_dir / f"{FILE}.json").read_text())
    path = web_dir / f"{WEEKS_FILE}.json"
    if not path.exists():
        return [("FAIL", f"{WEEKS_FILE}.json: missing next to {FILE}.json")]
    weeks = json.loads(path.read_text())
    dates, basins, res = doc["dates"], doc["basins"], doc["reservoirs"]
    out, bad = [], []
    days = [date.fromisoformat(d) for d in dates]
    if any(d.weekday() != 1 for d in days) or any(b - a != timedelta(days=7) for a, b in zip(days, days[1:])):
        bad.append("dates are not Tuesdays a week apart")
    if len(weeks["actual"]) != len(dates) or any(len(row) != len(res) for row in weeks["actual"]) \
            or len(weeks["capacity"]) != len(res):
        return [("FAIL", f"{WEEKS_FILE}.json: its matrix is not {len(dates)} weeks × {len(res)} reservoirs")]
    sums = [{"actual": [None] * len(dates), "capacity": [None] * len(dates)} for _ in basins]
    for i, row in enumerate(weeks["actual"]):
        for j, v in enumerate(row):
            if v is None:
                continue
            s = sums[res[j]["basin"]]
            s["actual"][i] = (s["actual"][i] or 0) + v
            s["capacity"][i] = (s["capacity"][i] or 0) + capacity_at(weeks["capacity"][j], i)
    off = [b["name"] for b, s in zip(basins, sums) if b["actual"] != s["actual"] or b["capacity"] != s["capacity"]]
    if off:
        bad.append(f"basin series differ from the weekly matrix ({', '.join(off)})")
    for j, r in enumerate(res):
        seen = [i for i, row in enumerate(weeks["actual"]) if row[j] is not None]
        if (seen[0] if seen else None, seen[-1] if seen else None) != (r["first"], r["last"]):
            bad.append(f"{r['name']}: first/last weeks disagree with its values")
            break
    try:
        src = load_interim("boletin_hidrologico")
    except FileNotFoundError:
        src = None
    if src is None:
        out.append(("NOTE", f"{FILE}.json: no boletin_hidrologico interim; the Boletín map and basins not compared"))
    else:
        latest = [p for p in src["points"] if p["date"] == dates[-1]]
        if latest:
            n = len(dates) - 1
            mine = sum(b["actual"][n] or 0 for b in basins)
            theirs = sum(p["actual"] for p in latest)
            if mine != theirs:
                bad.append(f"latest week {mine} hm³, the Boletín map {theirs} hm³")
        world = load_interim("_world")
        proj = active().world_projection(world)
        shapes = [[[proj(lon, lat) for lon, lat in ring] for ring in b["rings"]] for b in src["basins"]]
        edges = Edges(shapes, WIKIDATA_KM)
        away = [r["name"] for r in res if r["placed"]
                and not in_basin(shapes[r["basin"]], edges, r["basin"], *proj(r["lon"], r["lat"]), WIKIDATA_KM)]
        if away:
            bad.append(f"{len(away)} points outside their basin ({', '.join(away[:5])})")
    if bad:
        return out + [("FAIL", f"{FILE}.json: " + "; ".join(bad))]
    placed = sum(r["placed"] is not None for r in res)
    return out + [("PASS", f"{FILE}.json: {len(res)} reservoirs ({placed} placed) in {len(basins)} basins, "
                           f"{len(dates)} weeks {dates[0]}…{dates[-1]}, basin sums = the weekly matrix")]
