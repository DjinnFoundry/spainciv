"""Spain's trade routes: the largest road freight flows between autonomous communities (EPTMC, `eptmc` interim), in
the trade.json contract of the US (pipeline/build/trade.py) with tonnes for dollars (`measure: "tons"`).

* A zone is an autonomous community (Ceuta and Melilla together, as the survey publishes them), drawn by its
  provinces' cells and anchored on its cell nearest the middle of them (trade.middle_anchor).
* The survey does not publish the flows of the Balearic and Canary Islands, Ceuta and Melilla (`..`): those zones are
  `significant: false`, have their totals, no routes and no anchor (nothing is drawn from them, and one cell would
  put Ceuta and Melilla's zone in one of the two cities).
* `updated` is the date the ministry last updated the workbook (its Last-Modified), which its reuse conditions ask to
  show.
* A route is a pair of the 15 mainland communities, both directions summed; the TOP_N largest by tonnes are kept (an
  editorial cut). The survey says where goods are loaded and unloaded, not the road they take, so a route has no
  `path`: the map draws a straight line between the two anchors.
* The average haul is the pair's tonne-kilometres over its tonnes, both from the survey.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path

from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_interim_payload, write_web
from ..countries import active
from ..sources.es.eptmc import CEUTA_MELILLA, CLASSES, NOT_SIGNIFICANT
from ..sources.es.provinces import COMMUNITIES, COMMUNITY_NAMES, COMMUNITY_SHORT_NAMES
from .texts_es import tr, vintage
from .trade import anchor_problem, load_doc, load_grid, middle_anchor, route_problems, size_warning

REQUIRES = ["_world", "eptmc"]
PRODUCES = ["trade.json"]
COUNTRIES = ("es",)

TOP_N = 30
PARTNERS = 5
ROAD = "truck"  # the mode id the map's art knows (render/art/improvements.js MODE_STYLE)
PROVINCES = {**{c: provs for c, (_, provs) in COMMUNITIES.items()}, CEUTA_MELILLA: COMMUNITIES["18"][1] + COMMUNITIES["19"][1]}
CEUTA_MELILLA_NAME = tr("Ceuta y Melilla", "Ceuta and Melilla")
NAMES = {code: (COMMUNITY_NAMES[code], COMMUNITY_SHORT_NAMES[code]) for code in COMMUNITY_NAMES}
NAMES[CEUTA_MELILLA] = (CEUTA_MELILLA_NAME, CEUTA_MELILLA_NAME)

RULE = tr(
    f"Los {TOP_N} mayores flujos de mercancías por carretera entre las 15 comunidades autónomas peninsulares en "
    "{year}, en toneladas, sumando los dos sentidos. Cuenta los camiones pesados matriculados en España (más de 3,5 t) "
    f"que muestrea la EPTMC. Quedarse con {TOP_N} es un corte editorial; los flujos con Baleares, Canarias, Ceuta y "
    "Melilla no se publican.",
    f"The {TOP_N} largest road freight flows between the 15 mainland autonomous communities in {{year}}, in tonnes, "
    "both directions summed. It counts the Spanish-registered heavy trucks (over 3.5 t) that the EPTMC samples. Keeping "
    f"{TOP_N} is an editorial cut; flows with the Balearic and Canary Islands, Ceuta and Melilla are not published.")
PATH_NOTE = tr(
    "La EPTMC da la comunidad de carga y la de descarga, no el recorrido: la línea es recta entre los centros de las dos "
    "comunidades.",
    "The EPTMC gives the community where goods are loaded and the one where they are unloaded, not the way they go: "
    "the line is straight between the centres of the two communities.")


def build_zones(world: dict, eptmc: dict) -> dict[str, dict]:
    """A zone per community code of the survey, with its anchor, totals, goods and leading partners."""
    grid = HexGrid(**world["grid"])
    prov_of_owner = world["states"]
    zone_of_prov = {p: code for code, provs in PROVINCES.items() for p in provs}
    cells = defaultdict(list)
    for i, o in enumerate(world["owner"]):
        if o >= 0 and prov_of_owner[o] in zone_of_prov:
            cells[zone_of_prov[prov_of_owner[o]]].append(i)
    tons, trips, goods = eptmc["tons_k"], eptmc["trips_k"], eptmc["goods_k"]
    r1 = lambda v: None if v is None else round(v, 1)  # noqa: E731
    zones = {}
    for code in eptmc["codes"]:
        name, short = NAMES[code]
        partners = []
        for other in eptmc["codes"]:
            ab, ba = tons[code][other], tons[other][code]
            if other != code and ab is not None and ba is not None:
                partners.append([other, round(ab + ba, 1), ROAD])
        partners.sort(key=lambda p: (-p[1], p[0]))
        t = trips[code]
        significant = code not in NOT_SIGNIFICANT
        zones[code] = {
            "id": code, "name": name, "short": short, "kind": "community", "provinces": PROVINCES[code],
            "significant": significant, "anchor": middle_anchor(grid, cells[code]) if significant else None,
            "partners": partners[:PARTNERS],
            "totals_k": {"within": r1(t["within"]), "sent": r1(t["sent"]), "received": r1(t["received"]),
                         "intl_sent": r1(t["intl_sent"]), "intl_received": r1(t["intl_received"])},
            "goods_k": {k: [r1(v) for v in goods[code][k]] for k in ("sent", "received")},
        }
    return zones


def build_routes(zones: dict, eptmc: dict) -> list[dict]:
    """The TOP_N largest pairs of significant, anchored zones, both directions summed."""
    tons, tkm = eptmc["tons_k"], eptmc["tkm_m"]
    ids = sorted(z for z, v in zones.items() if v["significant"] and v["anchor"])
    cands = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            ab, ba = tons[a][b], tons[b][a]
            if ab is None or ba is None or ab + ba <= 0:
                continue
            t = None if tkm[a][b] is None or tkm[b][a] is None else tkm[a][b] + tkm[b][a]
            cands.append((ab + ba, a, b, ab, ba, t))
    cands.sort(key=lambda c: (-c[0], c[1], c[2]))
    return [{"a": a, "b": b, "rank": rank, "tons_k": round(total, 1), "ab_k": round(ab, 1), "ba_k": round(ba, 1),
             "tkm_m": None if t is None else round(t, 1),
             "haul_km": None if t is None else round(t * 1e3 / total),  # million t·km × 1e6 / (thousand t × 1e3)
             "modes": {ROAD: 1.0}, "top_mode": ROAD, "top_commodity": None}
            for rank, (total, a, b, ab, ba, t) in enumerate(cands[:TOP_N], 1)]


def build() -> None:
    world = load_interim("_world")
    payload = load_interim_payload("eptmc")
    eptmc = payload["data"]
    zones = build_zones(world, eptmc)
    routes = build_routes(zones, eptmc)
    nat = eptmc["trips_k"]["national"]
    doc = {
        "version": 1,
        "vintage": vintage(payload["vintage"]),
        "year": eptmc["year"],
        "updated": eptmc["updated"],
        "sources": ["eptmc"],
        "measure": "tons",
        "rule": RULE.format(year=str(eptmc["year"])),
        "path_note": PATH_NOTE,
        "units": {"tons_k": tr("miles de toneladas", "thousand tonnes"),
                  "tkm_m": tr("millones de toneladas-kilómetro", "million tonne-kilometres")},
        "modes": [{"id": ROAD, "name": tr("Carretera", "Road")}],
        "commodities": {str(k): name for k, (_, name) in enumerate(CLASSES)},
        "national_k": {"interregional": round(nat["sent"], 1), "intra": round(nat["within"], 1),
                       "intl_sent": round(nat["intl_sent"], 1), "intl_received": round(nat["intl_received"], 1)},
        "zones": sorted(zones.values(), key=lambda z: z["id"]),
        "routes": routes,
    }
    write_web("trade.json", doc)
    top = routes[0] if routes else None
    print(f"    {len(zones)} communities ({sum(1 for z in zones.values() if z['significant'])} with published flows), "
          f"{len(routes)} routes; top: {zones[top['a']]['short']['es']} – {zones[top['b']]['short']['es']} "
          f"{top['tons_k'] / 1e3:.1f} M t" if top else "    no routes")


# ------------------------------------------------------------------ check


def iso_date(v) -> bool:
    try:
        return isinstance(v, str) and date.fromisoformat(v).isoformat() == v
    except ValueError:
        return False


ZONE_KEYS = ("id", "name", "short", "kind", "provinces", "significant", "anchor", "partners", "totals_k", "goods_k")


def check(web_dir: Path) -> list[tuple[str, str]]:
    if active().id not in COUNTRIES:  # the other country's trade.json has its own check
        return []
    path, doc, out = load_doc(web_dir, ("version", "vintage", "year", "updated", "sources", "measure", "rule", "modes",
                                        "commodities", "national_k", "zones", "routes"), "spain_trade")
    if doc is None:
        return out
    if doc["measure"] != "tons":
        out.append(("FAIL", f"trade.json measure {doc['measure']!r} (expected 'tons')"))
    if not iso_date(doc["updated"]):
        out.append(("FAIL", f"trade.json updated {doc['updated']!r}: the licence needs the data's update date"))
    grid, owner = load_grid(web_dir)
    zones, probs = {}, []
    for z in doc["zones"]:
        probs += [f"zone {z.get('id')} lacks {k}" for k in ZONE_KEYS if k not in z]
        zones[z.get("id")] = z
        if z.get("kind") != "community":
            probs.append(f"zone {z.get('id')} kind {z.get('kind')!r}")
        if (p := anchor_problem(z, grid, owner, "Spanish land")) is not None:
            probs.append(p)
        if z.get("anchor") and not z.get("significant"):
            probs.append(f"zone {z.get('id')}: an anchor without published flows")
        if z.get("significant") != (z.get("id") not in NOT_SIGNIFICANT):
            probs.append(f"zone {z.get('id')} significant {z.get('significant')!r}")
    if len(zones) != len(doc["zones"]):
        probs.append("duplicate zone ids")
    if probs:
        out.append(("FAIL", f"trade.json zones: {len(probs)} problems, e.g. {probs[:3]}"))
    else:
        out.append(("PASS", f"trade.json zones: {len(zones)} communities, "
                            f"{sum(1 for z in zones.values() if z['significant'])} with published flows"))

    mode_ids = {m["id"] for m in doc["modes"]}

    def each(r, a, b):
        p = []
        if not (a.get("significant") and b.get("significant")):
            p.append(f"route {r['rank']}: a community without published flows")
        if not (a.get("anchor") and b.get("anchor")):
            p.append(f"route {r['rank']}: a community without an anchor")
        nums = [r.get(k) for k in ("tons_k", "ab_k", "ba_k")]
        if not all(isinstance(v, (int, float)) and v > 0 for v in nums):
            p.append(f"route {r['rank']}: tonnes {nums!r}")
        elif abs(nums[1] + nums[2] - nums[0]) > 0.15:
            p.append(f"route {r['rank']}: the two directions do not add up to the total")
        if not isinstance(r.get("haul_km"), int) or r["haul_km"] <= 0:
            p.append(f"route {r['rank']}: haul_km {r.get('haul_km')!r}")
        if r.get("top_mode") not in mode_ids or set(r.get("modes", {})) - mode_ids:
            p.append(f"route {r['rank']}: unknown mode")
        if "path" in r:
            p.append(f"route {r['rank']}: a path (the survey gives none)")
        return p

    probs = route_problems(doc["routes"], zones, "tons_k", "tons", each)
    if probs:
        out.append(("FAIL", f"trade.json routes: {len(probs)} problems, e.g. {probs[:3]}"))
    elif doc["routes"]:
        top = doc["routes"][0]
        total = sum(r["tons_k"] for r in doc["routes"])
        out.append(("PASS", f"trade.json routes: {len(doc['routes'])} routes, {total / 1e3:,.1f} M t in all; "
                            f"#1 {zones[top['a']]['short']} – {zones[top['b']]['short']} {top['tons_k'] / 1e3:,.1f} M t"))
    else:
        out.append(("WARN", "trade.json has no routes"))
    return out + size_warning(path)
