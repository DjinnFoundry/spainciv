"""clima.json: the climate of each month on Spain's hexes, at AEMET's stations and by province (1991-2020).

* **Grid** (temperature, rain, frost): AEMET's daily ROCIO grids averaged by spainciv over 1991-2020 for each point
  and month (sources/es/aemet_rocio.py). Each point is projected with the map's projection (the Canaries into their
  inset) and a land hex takes the mean of the points inside it; a land hex with none takes the nearest point within
  one grid spacing of its centre, else it has no grid value (Ceuta and Melilla, which ROCIO does not cover). The mean
  temperature is (tmax + tmin) / 2, as AEMET derives its own 1991-2020 mean-temperature maps; the browser computes it.
* **Stations**: the WMO 1991-2020 normals of AEMET's 83 stations (sources/es/omm_normales.py), each on the land hex
  holding it or the nearest land hex. Sunshine exists only there and is never spread to other hexes.
* **Provinces**: AEMET's official 1991-2020 province normals (sources/es/aemet_normales.py), for the Walter-Lieth
  chart, Ceuta and Melilla, and the check that compares the grid with them; "ESPAÑA PENINSULAR" gives the month strip.
* **Domains**: the 2nd-98th percentile of the hex values over all 12 months (of the station values for sunshine), so
  every month is drawn on one scale.
"""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

from ..core.hexgrid import HexGrid
from ..core.lang import tr
from ..core.store import load_interim, load_interim_payload, write_web
from ..countries import active
from .cities import nearest_land, ring_search
from .lenses import percentile_domain

REQUIRES = ["_world", "aemet_rocio", "omm_normales_es", "aemet_normales_provincias"]
PRODUCES = ["clima.json"]
COUNTRIES = ("es",)

FILE = "clima.json"
VERSION = 1
GRID_VARS = ["tmax", "tmin", "prec", "frost"]
STATION_VARS = {"tmed": "tmean", "tmax": "tmax", "tmin": "tmin", "prec": "prec", "frost": "frost_lt0", "sun": "sun"}
RANGES = {"temp": (-25, 45), "prec": (0, 1000), "frost": (0, 31), "sun": (0, 450)}
GAP_WARN = 0.01  # share of the land hexes without a grid value
STATION_KM = 15.0  # a station farther than this from its hex's centre is misplaced (1.5 hexes)
T_WARN, P_WARN = 0.7, 0.15  # °C on the province mean maximum and minimum; share of the annual rain

RULES = {
    "grid": tr("Rejilla diaria ROCIO de AEMET, media 1991-2020 calculada por spainciv: la media de los puntos de la "
               "rejilla (cada 5 km; 2,5 km en Canarias) que caen en el hexágono.",
               "AEMET's ROCIO daily grid, 1991-2020 mean computed by spainciv: the mean of the grid points (every 5 km; "
               "2.5 km in the Canaries) inside the hex."),
    "province": tr("Media provincial de AEMET 1991-2020: los datos de las estaciones interpolados a una rejilla y "
                   "promediados en la provincia por AEMET.",
                   "AEMET's 1991-2020 province mean: station data interpolated to a grid and averaged over the "
                   "province by AEMET."),
    "station": tr("Normal OMM 1991-2020 de la estación, enviada por AEMET a la Organización Meteorológica Mundial.",
                  "The station's WMO 1991-2020 normal, sent by AEMET to the World Meteorological Organization."),
    "frost": tr("Días de helada: días con la mínima a 0 °C o menos en la rejilla. Las estaciones de la OMM cuentan los "
                "días por debajo de 0 °C, y en los valles fríos la rejilla suaviza las heladas.",
                "Frost days: days with a minimum at or below 0 °C on the grid. The WMO stations count days below "
                "0 °C, and the grid smooths frost in cold valleys."),
    "sun": tr("Horas de sol: solo en las 76 estaciones que las miden; no se interpolan entre estaciones.",
              "Sunshine hours: only at the 76 stations that measure them; they are not interpolated between stations."),
    "rain": tr("Lluvia: total del mes, con los días fechados como en los ficheros de AEMET (de 07 h a 07 h, por el día "
               "en que empieza).",
               "Rainfall: the month's total, each day dated as AEMET's files date it (07 h to 07 h, by the day it "
               "starts)."),
}


def place_points(regions: dict, proj, grid: HexGrid, owner: list[int]) -> tuple[dict[int, list], list]:
    """(land hex → [(region, k)] of the grid points inside it, every point as (x, y, region, k))."""
    inside: dict[int, list] = {}
    points = []
    for name, r in regions.items():
        for k, (lon, lat) in enumerate(zip(r["lon"], r["lat"])):
            if proj.occluded(lon, lat):
                continue
            x, y = proj(lon, lat)
            points.append((x, y, name, k))
            c = grid.cell_at(x, y)
            if c >= 0 and owner[c] >= 0:
                inside.setdefault(c, []).append((name, k))
    return inside, points


def nearest_point(grid: HexGrid, cell: int, by_cell: dict[int, list], regions: dict):
    """The grid point nearest the centre of `cell` within one grid spacing of it, or None. by_cell: every point by
    the hex it falls in (land or sea)."""
    cx, cy = grid.center(*grid.col_row(cell))
    reach = max(r["spacing_km"] for r in regions.values())
    rings = math.ceil(reach / (math.sqrt(3) * grid.radius)) + 1
    best = None
    for _, c in ring_search(grid, cell, rings):
        for x, y, name, k in by_cell.get(c, []):
            d = math.hypot(x - cx, y - cy)
            if d <= regions[name]["spacing_km"] and (best is None or d < best[0]):
                best = (d, name, k)
    return None if best is None else best[1:]


def hex_values(regions: dict, members: list, var: str) -> list:
    """The 12 monthly means of `var` over a hex's points (nulls left out; null when every point is null)."""
    out = []
    for m in range(12):
        vals = [regions[name][var][k][m] for name, k in members if regions[name][var][k][m] is not None]
        out.append(round(sum(vals) / len(vals), 1) if vals else None)
    return out


def grid_layer(regions: dict, proj, grid: HexGrid, owner: list[int]) -> tuple[list[int], list[int], dict]:
    """(cells, points per cell (0: the nearest point), {var: [12][len(cells)]})."""
    inside, points = place_points(regions, proj, grid, owner)
    by_cell: dict[int, list] = {}
    for p in points:
        c = grid.cell_at(p[0], p[1])
        if c >= 0:
            by_cell.setdefault(c, []).append(p)
    held = []  # (cell, points averaged, its points)
    for c in range(grid.size):
        if owner[c] < 0:
            continue
        if c in inside:
            held.append((c, len(inside[c]), inside[c]))
        elif (near := nearest_point(grid, c, by_cell, regions)) is not None:
            held.append((c, 0, [near]))
    cells, counts, members = [h[0] for h in held], [h[1] for h in held], [h[2] for h in held]
    per_hex = {v: [hex_values(regions, ms, v) for ms in members] for v in GRID_VARS}
    return cells, counts, {v: [[h[m] for h in per_hex[v]] for m in range(12)] for v in GRID_VARS}


def station_cell(grid: HexGrid, owner: list[int], x: float, y: float, province: int) -> int:
    """The land hex holding the station when it is of the station's province, else the nearest land hex, a hex of
    its province first (a station near a provincial boundary can sit on a hex most of which is the neighbour's)."""
    c = grid.cell_at(x, y)
    return c if c >= 0 and owner[c] == province else nearest_land(grid, owner, max(c, 0), x, y, province)


def stations_doc(stations: list[dict], proj, grid: HexGrid, owner: list[int], provinces: list[str]) -> list[dict]:
    out = []
    for s in stations:
        cell = station_cell(grid, owner, *proj(s["lon"], s["lat"]), provinces.index(s["province"]))
        out.append({"wmo": s["wmo"], "aemet": s["aemet"], "name": s["name"], "province": s["province"],
                    "lon": s["lon"], "lat": s["lat"], "alt": s["alt"], "coords": s["coords"], "cell": cell,
                    **{k: s[src] for k, src in STATION_VARS.items()}})
    return out


def domains(grid_vals: dict, stations: list[dict]) -> dict:
    temp = [None if a is None or b is None else (a + b) / 2
            for m in range(12) for a, b in zip(grid_vals["tmax"][m], grid_vals["tmin"][m])]
    flat = lambda v: [x for m in range(12) for x in grid_vals[v][m]]  # noqa: E731
    return {"temp": percentile_domain(temp, False), "prec": percentile_domain(flat("prec"), True),
            "frost": [0, percentile_domain(flat("frost"), False)[1]],
            "sun": percentile_domain([x for s in stations if s["sun"] for x in s["sun"]], False)}


def build() -> None:
    world = load_interim("_world")
    rocio_p = load_interim_payload("aemet_rocio")
    rocio = rocio_p["data"]
    omm = load_interim("omm_normales_es")
    official = load_interim("aemet_normales_provincias")
    proj = active().world_projection(world)
    grid = HexGrid(**world["grid"])
    owner = world["owner"]

    cells, counts, grid_vals = grid_layer(rocio["regions"], proj, grid, owner)
    stations = stations_doc(omm["stations"], proj, grid, owner, world["states"])
    print(f"    {len(cells)} land hexes with a grid value ({counts.count(0)} from the nearest point), "
          f"{len(stations)} stations, {sum(s['sun'] is not None for s in stations)} with sunshine")
    write_web(FILE, {
        "version": VERSION, "vintage": rocio_p["vintage"],
        "sources": ["aemet_rocio", "omm_normales_es", "aemet_normales_provincias"],
        "rules": RULES, "cells": cells, "points": counts, "grid": grid_vals,
        "provinces": official["provinces"],
        "peninsular": {k: official["peninsula"][k] for k in ("tmed", "prec")},
        "stations": stations, "domains": domains(grid_vals, stations),
    })


# --- check ---------------------------------------------------------------------------------------------------------

def _range_errors(name: str, rows, lo: float, hi: float) -> list[str]:
    bad = [v for row in rows for v in row if v is not None and not lo <= v <= hi]
    return [f"{name}: {len(bad)} values outside {lo}..{hi} (e.g. {bad[0]})"] if bad else []


def shape_errors(doc: dict, size: int) -> list[str]:
    errs = []
    cells = doc.get("cells", [])
    if cells != sorted(set(cells)) or any(not 0 <= c < size for c in cells):
        errs.append("cells: not ascending distinct hex indices")
    if len(doc.get("points", [])) != len(cells):
        errs.append("points: not one per cell")
    for v in GRID_VARS:
        rows = doc.get("grid", {}).get(v)
        if not isinstance(rows, list) or len(rows) != 12 or any(len(r) != len(cells) for r in rows):
            errs.append(f"grid.{v}: not 12 months × {len(cells)} cells")
    if not errs:
        g = doc["grid"]
        errs += _range_errors("grid.tmax", g["tmax"], *RANGES["temp"]) + _range_errors("grid.tmin", g["tmin"], *RANGES["temp"])
        errs += _range_errors("grid.prec", g["prec"], *RANGES["prec"]) + _range_errors("grid.frost", g["frost"], *RANGES["frost"])
        if any(a is not None and b is not None and b > a for m in range(12) for a, b in zip(g["tmax"][m], g["tmin"][m])):
            errs.append("grid: a minimum above its maximum")
    for code, p in doc.get("provinces", {}).items():
        if sorted(p) != ["prec", "tmax", "tmed", "tmin"] or any(len(p[k]) != 12 for k in p):
            errs.append(f"provinces.{code}: not tmed, tmax, tmin and prec for 12 months")
    if len(doc.get("provinces", {})) != 52:
        errs.append(f"provinces: {len(doc.get('provinces', {}))}, not 52")
    for s in doc.get("stations", []):
        for k in STATION_VARS:
            if s.get(k) is None and k == "sun":
                continue
            if not isinstance(s.get(k), list) or len(s[k]) != 12:
                errs.append(f"station {s.get('wmo')}: {k} not 12 months")
        errs += _range_errors(f"station {s.get('wmo')} tmed", [s.get("tmed") or []], *RANGES["temp"])
        if s.get("sun"):
            errs += _range_errors(f"station {s.get('wmo')} sun", [s["sun"]], *RANGES["sun"])
    for k, (lo, hi) in doc.get("domains", {}).items():
        if not (isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and lo < hi):
            errs.append(f"domains.{k}: {lo}..{hi}")
    if sorted(doc.get("domains", {})) != sorted(RANGES):
        errs.append("domains: not temp, prec, frost and sun")
    return errs


def province_deviations(doc: dict, province_of: list) -> list[str]:
    """Provinces whose hexes' grid means differ from AEMET's normal by more than T_WARN (max, min; the mean of the
    12 months) or P_WARN of the annual rain."""
    by: dict[str, list[int]] = {}
    for k, c in enumerate(doc["cells"]):
        if province_of[c] is not None:
            by.setdefault(province_of[c], []).append(k)
    out = []
    g = doc["grid"]
    for code, ks in sorted(by.items()):
        ref = doc["provinces"].get(code)
        if ref is None:
            continue

        def mean_of(var):
            vals = [statistics.fmean(g[var][m][k] for m in range(12)) for k in ks
                    if all(g[var][m][k] is not None for m in range(12))]
            return statistics.fmean(vals) if vals else None

        tx, tn = mean_of("tmax"), mean_of("tmin")
        rain = [sum(g["prec"][m][k] for m in range(12)) for k in ks if all(g["prec"][m][k] is not None for m in range(12))]
        dx = None if tx is None else tx - statistics.fmean(ref["tmax"])
        dn = None if tn is None else tn - statistics.fmean(ref["tmin"])
        dp = statistics.fmean(rain) / sum(ref["prec"]) - 1 if rain else None
        if (dx is not None and abs(dx) > T_WARN) or (dn is not None and abs(dn) > T_WARN) or (dp is not None and abs(dp) > P_WARN):
            out.append(f"{code} (max {dx:+.1f} °C, min {dn:+.1f} °C, rain {dp:+.0%})")
    return out


def check(web_dir) -> list[tuple[str, str]]:
    web_dir = Path(web_dir)
    path = web_dir / FILE
    world_path = web_dir / "world.json"
    world = json.loads(world_path.read_text()) if world_path.exists() else {}
    if world.get("country", {}).get("id") not in (None, "es") and not path.exists():
        return []  # not Spain's map: nothing to check
    if not path.exists():
        return [("NOTE", f"{FILE}: missing (the climate mode is off)")]
    doc = json.loads(path.read_text())
    owner = world.get("owner", [])
    fips = [s["fips"] for s in world.get("states", [])]
    province_of = [fips[o] if o >= 0 else None for o in owner]
    if errs := shape_errors(doc, len(owner)):
        return [("FAIL", f"{FILE}: {e}") for e in errs[:10]]
    lines = []
    grid = HexGrid(**world["grid"])
    pj = world.get("country", {}).get("projection")
    proj = active().map_projection(pj["min_x"], pj["max_y"], pj["margin"]) \
        if pj and world["country"].get("id") == active().id else None  # the map's projection, to measure distances

    def misplaced(s) -> bool:
        if not 0 <= s["cell"] < len(owner) or owner[s["cell"]] < 0 or province_of[s["cell"]] != s["province"]:
            return True
        if proj is None:
            return False
        x, y = proj(s["lon"], s["lat"])
        return math.dist((x, y), grid.center(*grid.col_row(s["cell"]))) > STATION_KM

    if stray := [f"{s['wmo']} {s['name']}" for s in doc["stations"] if misplaced(s)]:
        lines.append(("FAIL", f"{FILE}: stations off Spanish land, outside their province or over {STATION_KM:g} km "
                              f"from their hex: {', '.join(stray)}"))
    if dev := province_deviations(doc, province_of):
        lines.append(("WARN", f"{FILE}: grid means beyond {T_WARN} °C or {P_WARN:.0%} of AEMET's province normals: "
                              f"{'; '.join(dev)}"))
    held = set(doc["cells"])
    gaps = [c for c, p in enumerate(province_of) if p is not None and c not in held]
    if gaps:
        land = sum(p is not None for p in province_of)
        lines.append(("WARN" if len(gaps) > GAP_WARN * land else "NOTE",
                      f"{FILE}: {len(gaps)} land hexes with no grid point within one spacing take their province's "
                      f"AEMET normal for temperature and rain (hexes {gaps[:8]})"))
    index = {c: k for k, c in enumerate(doc["cells"])}
    g = doc["grid"]
    dt, df = [], []
    for s in doc["stations"]:
        k = index.get(s["cell"])
        if k is None:
            continue
        for m in range(12):
            a, b = g["tmax"][m][k], g["tmin"][m][k]
            if a is not None and b is not None:
                dt.append(abs((a + b) / 2 - s["tmed"][m]))
            if g["frost"][m][k] is not None and (g["frost"][m][k] or s["frost"][m]):  # months with frost
                df.append(g["frost"][m][k] - s["frost"][m])
    if dt:
        lines.append(("NOTE", f"{FILE}: at station hexes the grid's mean temperature is {statistics.median(dt):.1f} °C "
                              f"from the station's (median of |grid − station| over months), and frost days are "
                              f"{statistics.median(df) if df else 0:+.1f} days a month (median grid − station over "
                              "months with frost: the grid smooths "
                              "cold valleys, and the WMO counts < 0 °C where the grid counts ≤ 0 °C)"))
    lines.append(("PASS", f"{FILE}: {len(doc['cells'])} land hexes with a grid value "
                          f"({doc['points'].count(0)} from the nearest point), {len(doc['stations'])} stations "
                          f"({sum(bool(s['sun']) for s in doc['stations'])} with sunshine), "
                          f"{len(doc['provinces'])} province normals"))
    return lines
