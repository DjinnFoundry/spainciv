"""Spain's reservoirs week by week (embalses.json, embalses_semanas.json) for the reservoirs lens (web/js/ext/embalses).

* **Basins** (E92): a land hex goes to the Boletín basin (DDHH polygon) that holds its centre; a peninsular one
  outside every polygon (the 1:… coast of the layer is simplified) to the nearest polygon within SNAP_KM, else to
  none. The hexes of the island provinces, Ceuta and Melilla get none, by province code: the Boletín covers the
  peninsula only.
* **Basin figures**: per week, Σ water stored and Σ capacity of the basin's reservoirs that report that week
  (pipeline/sources/es/embalses.py), the Boletín's own formula.
* **Positions** (E92): (1) the Boletín map's point with the identical basin and name, which every reservoir of the
  latest week must have; (2) for a reservoir it no longer reports, the Wikidata reservoirs and dams one of whose names
  normalises to the same as its own (`name_key`) and that lie inside its basin or within WIKIDATA_KM of it: their mean
  when they all lie within WIKIDATA_KM of each other (core.geo.spread_mean, the beaches' rule, E74); when they split,
  the one dam item among them, else none. No fuzzy matching.
* A point goes to the hex that holds it, or the nearest land hex when it falls off the drawn land.
* **Names**: `name` is the Boletín's name tidied to read (`display_name`), `boletin_name` the name as BD-Embalses and
  its map write it, the key every match uses.
"""

from __future__ import annotations

import json
import re
from bisect import bisect_right
from collections import defaultdict
from functools import partial
from pathlib import Path

from ..core import names
from ..core.geo import Shape, row_crossings, spread_mean
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from ..countries import active
from ..sources.es.embalses import TOLERANCE_HM3, basin_totals, capacity_at, layer_week
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
# A reservoir's name for matching: 'Breña, La' and 'Embalse de La Breña' → 'brena'; 'Malpasillo ( Jauja )' →
# 'malpasillo jauja'.
name_key = partial(names.name_key, dropped=NAME_WORDS)

ARTICLES = ("El", "La", "Los", "Las", "Lo", "Os", "As", "O", "A", "Els", "Les", "L'")


def display_name(name: str) -> str:
    """A Boletín name as it reads: spacing tidied and a trailing article first. 'Breña, La' → 'La Breña',
    'Vellón,El-(Pedrezuela)' → 'El Vellón (Pedrezuela)', 'Loteta (La)' → 'La Loteta', 'Malpasillo ( Jauja )' →
    'Malpasillo (Jauja)', 'Agavanzal, Nª Sª de' → 'Nª Sª de Agavanzal'. '(Lago)' and 'Jerte - Plasencia' stay."""
    s = re.sub(r"\(\s*(.*?)\s*\)", r"(\1)", name)
    s = re.sub(r"\s*-?\s*\(", " (", s)
    s = re.sub(r",\s*", ", ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if m := re.fullmatch(r"(.+?) \((%s)\)" % "|".join(ARTICLES), s):
        return f"{m[2]} {m[1]}"
    if m := re.fullmatch(r"([^,]+), ([^,()]+?)( \(.*\))?", s):
        return f"{m[2]} {m[1]}{m[3] or ''}"
    return s


def basin_cells(grid: HexGrid, owner: list[int], codes: list[str], shapes: list[Shape], snap_km: float = SNAP_KM,
                off: frozenset = OFF_BOLETIN) -> tuple[list[int], dict]:
    """The basin (index into `shapes`, in map km) of each hex, -1 for none: the polygon holding its centre; for a land
    hex outside all of them, the nearest within `snap_km`; never for a hex of a province in `off` (`codes`: the
    province code of each owner index). Also counts {inside, snapped, outside, off}."""
    rows = [row_crossings(s.rings, 1.5 * grid.radius) for s in shapes]  # hex row k has its centres at y = 1.5·R·k
    out = [-1] * grid.size
    stats = {"inside": 0, "snapped": 0, "outside": 0, "off": 0}
    for c in range(grid.size):
        if owner[c] < 0:
            continue
        if codes[owner[c]] in off:
            stats["off"] += 1
            continue
        col, row = grid.col_row(c)
        x, y = grid.center(col, row)
        hit = next((k for k, r in enumerate(rows) if bisect_right(r.get(row, ()), x) % 2), -1)
        if hit < 0:
            near = {k: d for k, s in enumerate(shapes) if near_box(s, x, y, snap_km) and (d := s.distance(x, y)) <= snap_km}
            hit = min(near, key=near.get) if near else -1
            stats["snapped" if hit >= 0 else "outside"] += 1
        else:
            stats["inside"] += 1
        out[c] = hit
    return out, stats


def near_box(shape: Shape, x: float, y: float, km: float) -> bool:
    x0, y0, x1, y1 = shape.bbox
    return x0 - km <= x <= x1 + km and y0 - km <= y <= y1 + km


def in_basin(shape: Shape, x: float, y: float, km: float = WIKIDATA_KM) -> bool:
    """Is (x, y) inside the basin polygon or within `km` of it?"""
    return near_box(shape, x, y, km) and shape.distance(x, y) <= km


def match_wikidata(name: str, shape: Shape, items: dict[str, list[tuple]], proj, km: float = WIKIDATA_KM) -> dict | None:
    """The Wikidata position of a reservoir from the items with a name of the same name_key (items: key → [(qid, lon,
    lat, dam)]) inside its basin polygon or within `km` of it: their mean when all lie within `km` of each other;
    when they split, the dam item's position if exactly one of them is a dam (a dam and its reservoir's lake are
    often further apart); else None (also None without candidates)."""
    cands = [c for c in items.get(name_key(name), []) if in_basin(shape, *proj(c[1], c[2]), km)]
    if not cands:
        return None
    rule = "same"
    if not (where := spread_mean([c[1:3] for c in cands], km)):
        dams = {c[0] for c in cands if c[3]}
        if len(dams) != 1:
            return None
        cands = [c for c in cands if c[0] in dams]
        rule = "dam"
        if not (where := spread_mean([c[1:3] for c in cands], km)):
            return None
    return {"lon": where[0], "lat": where[1], "qids": sorted({c[0] for c in cands}, key=lambda q: int(q[1:])),
            "rule": rule}


def wikidata_index(items: list[dict]) -> dict[str, list[tuple]]:
    """name_key → [(qid, lon, lat, dam)], one entry per item and position."""
    out: dict[str, list[tuple]] = defaultdict(list)
    for it in items:
        for key in {name_key(n) for n in it["names"]} - {""}:
            for lon, lat in it["points"]:
                out[key].append((it["id"], lon, lat, it["dam"]))
    return out


def unplaced_share(reservoirs: list[dict], unplaced: set[int], n: int) -> dict:
    """The largest share of a week's capacity, and of its water stored, that the `unplaced` reservoirs (indices) hold
    among those reporting that week: {capacity: (share, week), actual: (share, week)}."""
    best = {"capacity": (0.0, None), "actual": (0.0, None)}
    for i in range(n):
        tot = {"capacity": 0, "actual": 0}
        off = {"capacity": 0, "actual": 0}
        for j, r in enumerate(reservoirs):
            if (a := r["actual"][i]) is None:
                continue
            c = capacity_at(r["capacity"], i)
            tot["capacity"] += c
            tot["actual"] += a
            if j in unplaced:
                off["capacity"] += c
                off["actual"] += a
        for key in best:
            if tot[key] and off[key] / tot[key] > best[key][0]:
                best[key] = (off[key] / tot[key], i)
    return best


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
    shapes = basin_shapes(basins, proj)

    cell_basin, stats = basin_cells(grid, owner, codes, shapes)
    print(f"    hexes: {stats['inside']} inside a basin, {stats['snapped']} within {SNAP_KM:g} km of one, "
          f"{stats['outside']} peninsular without one, {stats['off']} outside the Boletín (islands, Ceuta, Melilla)")

    points = {(p["basin"], p["name"]): p for p in src["points"]}
    by_key = wikidata_index(wd["items"])
    reservoirs = sorted(src["reservoirs"], key=lambda r: (order[r["basin"]], r["name"]))
    out, placed_wd, unplaced = [], [], []
    for j, r in enumerate(reservoirs):
        k = order[r["basin"]]
        p, where = points.get((r["basin"], r["name"])), None
        if p:
            where = {"lon": p["lon"], "lat": p["lat"], "placed": "boletin"}
        elif r["last"] == last:
            raise ValueError(f"{r['name']} ({r['basin']}) reports in the latest week and has no Boletín map point")
        elif m := match_wikidata(r["name"], shapes[k], by_key, proj):
            where = {"lon": m["lon"], "lat": m["lat"], "placed": "wikidata", "qids": m["qids"]}
            placed_wd.append(display_name(r["name"]) + (" (the dam)" if m["rule"] == "dam" else ""))
        else:
            unplaced.append(j)
        caps = r["capacity"]
        entry = {"name": display_name(r["name"]), "boletin_name": r["name"], "basin": k, "use": r["use"],
                 "lon": None, "lat": None, "x": None, "y": None, "cell": None, "placed": None, "first": r["first"],
                 "last": r["last"], "capacity": caps[-1][1] if caps else None,
                 "actual": r["actual"][r["last"]] if r["last"] is not None else None}
        if where:
            x, y = proj(where["lon"], where["lat"])
            cell = grid.cell_at(x, y)
            if cell < 0 or owner[cell] < 0:
                cell = nearest_land(grid, owner, max(cell, 0), x, y, -1)
            entry.update({k2: where[k2] for k2 in ("lon", "lat", "placed")}, x=round(x, 2), y=round(y, 2), cell=cell)
            if "qids" in where:
                entry["qids"] = where["qids"]
        out.append(entry)
    share = unplaced_share(reservoirs, set(unplaced), len(dates))
    print(f"    {len(out)} reservoirs: {sum(e['placed'] == 'boletin' for e in out)} at the Boletín's point, "
          f"{len(placed_wd)} placed from Wikidata ({', '.join(placed_wd)}), {len(unplaced)} unplaced "
          f"({', '.join(out[j]['name'] for j in unplaced)})")
    print("    the unplaced hold at most " + ", ".join(
        f"{100 * v:.2f} % of a week's {what} ({dates[i] if i is not None else '-'})" for what, (v, i) in share.items()))

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


def basin_shapes(basins: list[dict], proj) -> list[Shape]:
    """The Boletín's basin polygons in map km."""
    return [Shape([[proj(lon, lat) for lon, lat in ring] for ring in b["rings"]]) for b in basins]


def check(web_dir) -> list[tuple[str, str]]:
    """embalses.json against embalses_semanas.json and the Boletín: the basin series are the sums of the weekly matrix,
    the Boletín map's week (the latest, or one a week off, with a NOTE) has its total, every placed point lies in its
    basin (WIKIDATA_KM), the dates are Tuesdays a week apart and each reservoir's first and last weeks are those its
    values say. Nothing to check on a map without the files."""
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
        by_day: dict[str, list[dict]] = defaultdict(list)
        for p in src["points"]:
            by_day[p["date"]].append(p)
        for day, pts in sorted(by_day.items()):
            try:
                k, note = layer_week(dates, day, "the Boletín map (Embalses_Mapa)")
            except ValueError as e:
                bad.append(str(e))
                continue
            if note:
                out.append(("NOTE", f"{FILE}.json: {note}"))
            if k is not None:
                mine = sum(b["actual"][k] or 0 for b in basins)
                theirs = sum(p["actual"] for p in pts)
                if abs(mine - theirs) > TOLERANCE_HM3:
                    bad.append(f"week {day}: {mine} hm³, the Boletín map {theirs} hm³")
        world = load_interim("_world")
        proj = active().world_projection(world)
        shapes = basin_shapes(src["basins"], proj)
        away = [r["name"] for r in res if r["placed"] and not in_basin(shapes[r["basin"]], *proj(r["lon"], r["lat"]))]
        if away:
            bad.append(f"{len(away)} points outside their basin ({', '.join(away[:5])})")
    if bad:
        return out + [("FAIL", f"{FILE}.json: " + "; ".join(bad))]
    placed = sum(r["placed"] is not None for r in res)
    return out + [("PASS", f"{FILE}.json: {len(res)} reservoirs ({placed} placed) in {len(basins)} basins, "
                           f"{len(dates)} weeks {dates[0]}…{dates[-1]}, basin sums = the weekly matrix")]
