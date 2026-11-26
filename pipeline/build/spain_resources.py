"""Spain's tile resources: the power plants (resources.json, same contract as the US build).

Thresholds are lower than the US ones (Spain's grid is about a tenth of the US's, and its hexes are 10 km wide):
single plants count from PLANT_MIN MW of their fuel; wind, solar and battery plants are summed per hex and shown from
CLUSTER_MIN MW. Plants of the same type in one hex are one site (two OSM objects for Jinámar, Ascó I and II). Every
nuclear plant in service is shown. Mines and oil and gas fields are not mapped yet (ROADMAP.md).
"""

from __future__ import annotations

import re
from collections import defaultdict

from ..core.store import load_interim, load_interim_payload, load_web, write_web
from .resources import Placer, _cluster_name, _fmt, _n, _settle, _t, _tidy, summarize

REQUIRES = ["_world", "power_plants_es", "cities.json", "world.json"]
PRODUCES = ["resources.json"]
COUNTRIES = ("es",)

PLANT_MIN = {"hydro": 200, "pumped_storage": 400, "coal": 500, "gas": 750, "oil": 150}
CLUSTER_MIN = {"wind": 150, "solar": 150, "battery": 50}
OFFSHORE_RINGS = 3
SRC = "power_plants_es"
PER_HEX = "Plants of this type in one hex are summed and shown as one site."
SUMMARY_NOTE = ("Totals of the mapped sites only: each type has a size threshold (see its description), so these are "
                "not a province's or Spain's full capacity.")
UNIT = re.compile(r"\s+(\d+|[IVX]+|Phase)$")  # 'Almaraz 1' and 'Almaraz 2' are units of 'Almaraz'
TYPE_OF = {"coal": "coal_plant", "gas": "gas_plant", "oil": "oil_plant"}

TYPES = [
    _t("nuclear", "Nuclear plant", "energy", "☢️", "#e8d44d", "MW",
       "Every nuclear power plant in service (powerplantmatching): Almaraz, Ascó, Cofrentes, Vandellós and Trillo. "
       "Value is the plant's capacity; retired plants (Garoña, Zorita, Vandellós I) are not shown.", SRC),
    _t("hydro", "Hydroelectric dam", "energy", "💧", "#3fa7d6", "MW",
       f"Hydro plants (reservoir or run-of-river) of at least {PLANT_MIN['hydro']} MW. {PER_HEX}", SRC),
    _t("coal_plant", "Coal power plant", "energy", "🏭", "#5a5a5a", "MW",
       f"Coal plants of at least {PLANT_MIN['coal']} MW not yet retired in powerplantmatching. {PER_HEX}", SRC),
    _t("gas_plant", "Gas power plant", "energy", "⚡", "#f08a24", "MW",
       f"Gas plants (mostly combined cycle) of at least {PLANT_MIN['gas']} MW. {PER_HEX}", SRC),
    {**_t("oil_plant", "Oil-fired power plant", "energy", "🛢️", "#3a2f2a", "MW",
          f"Fuel-oil and diesel plants of at least {PLANT_MIN['oil']} MW: the island grids (Canary Islands from "
          f"OpenStreetMap, the Balearics, Ceuta and Melilla). {PER_HEX}", SRC), "icon": "r-oil"},
    _t("pumped_storage", "Pumped-storage hydro", "energy", "🔄", "#2f7fb8", "MW",
       f"Pumped-storage plants of at least {PLANT_MIN['pumped_storage']} MW: grid batteries made of two reservoirs. "
       f"{PER_HEX}", SRC),
    _t("wind", "Wind farms", "energy", "🌬️", "#9fd8cb", "MW",
       f"Wind capacity, shown where a hex totals at least {CLUSTER_MIN['wind']} MW. {PER_HEX}", SRC),
    _t("solar", "Solar farms", "energy", "☀️", "#ffc93c", "MW",
       f"Solar capacity (photovoltaic and solar thermal), shown where a hex totals at least {CLUSTER_MIN['solar']} MW "
       f"(rooftop solar is not included). {PER_HEX}", SRC),
    _t("battery", "Battery storage", "energy", "🔋", "#7bc96f", "MW",
       f"Battery-storage capacity, shown where a hex totals at least {CLUSTER_MIN['battery']} MW. {PER_HEX}", SRC),
]
RANK = {t["id"]: i for i, t in enumerate(TYPES)}


def type_of(fuel: str) -> str:
    return TYPE_OF.get(fuel, fuel)


def minimum(fuel: str) -> float:
    return 0 if fuel == "nuclear" else PLANT_MIN.get(fuel, CLUSTER_MIN.get(fuel, float("inf")))


def site(type_id: str, group: list[tuple[dict, float, float]], cell: int) -> dict:
    """One map site from the (plant, x, y) of a type in a hex: the capacity-weighted position, the largest plant's
    name (or the plants' shared name), and the plants and online years in the detail."""
    group.sort(key=lambda g: -g[0]["mw"])
    lead = group[0][0]
    mw = sum(p["mw"] for p, _, _ in group)
    x = sum(gx * p["mw"] for p, gx, _ in group) / mw
    y = sum(gy * p["mw"] for p, _, gy in group) / mw
    years = sorted(p["year"] for p, _, _ in group if p["year"])
    online = "" if not years else f", online {years[0]}" + (f"–{years[-1]}" if years[-1] != years[0] else "")
    if len(group) == 1:
        name, detail = lead["name"], f"{_fmt(mw)} MW{online}"
    else:
        bases = {UNIT.sub("", p["name"]) for p, _, _ in group}
        name = (bases.pop() if len(bases) == 1 else None) \
            or _cluster_name([(p["name"], p["mw"]) for p, _, _ in group]) or f"{_tidy(lead['name'])} (+{len(group) - 1})"
        detail = f"{_n(len(group), 'plant')} incl. {lead['name']} ({_fmt(lead['mw'])} MW){online}"
    if any(p["offshore"] for p, _, _ in group):
        detail += "; offshore, shown on the nearest coast hex"
    if any(p["source"] == "osm" for p, _, _ in group):
        detail += "; OpenStreetMap"
    return {"type": type_id, "name": _tidy(name), "x": x, "y": y, "cell": cell, "value": round(mw), "detail": detail}


def build() -> None:
    world = load_interim("_world")
    payload = load_interim_payload("power_plants_es")
    place = Placer(world)
    groups: dict[tuple[str, int], list] = defaultdict(list)
    for p in payload["data"]["plants"]:
        x, y, cell = place(p["lon"], p["lat"], rings=OFFSHORE_RINGS if p["offshore"] else 1)
        if cell >= 0 and type_of(p["fuel"]) in RANK:
            groups[(type_of(p["fuel"]), cell)].append((p, x, y))
    items = []
    for (t, cell), group in groups.items():
        fuel = group[0][0]["fuel"]
        if fuel in CLUSTER_MIN:
            if sum(p["mw"] for p, _, _ in group) >= CLUSTER_MIN[fuel]:
                items.append(site(t, group, cell))
        else:
            big = [g for g in group if g[0]["mw"] >= minimum(fuel)]
            if big:
                items.append(site(t, big, cell))
    items.sort(key=lambda it: (RANK[it["type"]], -it["value"]))
    moved = _settle(items, place.grid)

    abbrs = [s["abbr"] for s in load_web("world.json")["states"]]
    city_of = {g: c["id"] for c in load_web("cities.json") for g in c.get("counties") or []}
    owner, county, geoids = world["owner"], world["county"], world["counties"]
    for it in items:
        c = it["cell"]
        it["state"] = abbrs[owner[c]]
        it["cbsa"] = city_of.get(geoids[county[c]]) if county[c] >= 0 else None
    present = {it["type"] for it in items}
    types = [t for t in TYPES if t["id"] in present]
    summary = summarize(items, types) | {"note": SUMMARY_NOTE}
    write_web("resources.json", {"types": types, "items": items, "summary": summary})
    counts = defaultdict(int)
    for it in items:
        counts[it["type"]] += 1
    print("    " + ", ".join(f"{t['id']} {counts[t['id']]}" for t in TYPES) + f"; {moved} moved to their hex centre")
