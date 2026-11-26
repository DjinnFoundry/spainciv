"""Spain's military layer: the installations as forts, the largest training grounds as restricted ground, and the
installations by province and urban area. Writes military.json in the US contract (pipeline/build/military.py), with
the US-only blocks (personnel by duty state, defence spending, the Encampment tier) left out.

* Installations: OpenStreetMap military land and military=* areas (osm_militar), each placed on its hex. A feature
  inside a larger one is a part of it; an unnamed one takes the name of its largest named part. Police posts (Guardia
  Civil, Policía), civil sites (Navantia, AENA) and former or heritage sites (old barracks, bunkers, museums) are left
  out, and so are training and danger areas outside military land (airsoft fields are tagged that way).
* Branch: the OSM operator, else the name ("Base Aérea", "Arsenal", "Acuartelamiento" …), else the OSM tag (airfield,
  naval_base), else the operator Wikidata records for the item within LINK_KM; otherwise "other".
* Tier: from the land inside the boundary, as in the US (no headcount is published per base).
* Rota and Morón carry `joint`: the two Spanish bases the United States uses under the 1988 Defence Cooperation
  Agreement.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from ..core.geo import Shape, ring_area, ring_centroid
from ..core.store import load_interim, load_interim_payload, load_web, write_web
from ..countries import active
from .spain_wonders import Placer
from .texts_es import num, vintage

REQUIRES = ["_world", "osm_militar", "wikidata_militar", "cities.json", "world.json", "states.json"]
PRODUCES = ["military.json"]
COUNTRIES = ("es",)

COMPONENTS = [
    {"id": "army", "name": "Ejército de Tierra"},
    {"id": "navy", "name": "Armada"},
    {"id": "air_force", "name": "Ejército del Aire y del Espacio"},
    {"id": "ume", "name": "Unidad Militar de Emergencias"},
    {"id": "other", "name": "Órgano Central, servicios comunes o rama sin identificar"},
]
COMPONENT_IDS = [c["id"] for c in COMPONENTS]
SHORT = {"army": "et", "navy": "arm", "air_force": "ea", "ume": "ume", "other": "oc"}  # id suffixes

MAJOR_KM2, BASE_KM2 = 10.0, 0.5
TIERS = ["major", "base", "site"]
COVER_KM2 = 20.0  # boundaries this large also list the hexes whose centre they cover (a hex is ~87 km²)
RANGES_N, RANGE_MIN_KM2 = 15, 20.0
SNAP_KM = 15.0  # a site off the drawn land goes on the nearest land hex when that hex's centre is this close (1.5 hexes)
LINK_KM = 1.5  # a Wikidata item this close to an installation (or inside it) is the same site
MILITARY_LAND_ONLY = {"training_area", "danger_area", "range"}

# The two bases used by the United States under the Convenio de Cooperación para la Defensa (1 December 1988, BOE
# 6 May 1989, amended in 2002, 2012 and 2015): OSM names → the agreement.
JOINT = ("Base Naval de Rota", "Base Aérea de Morón")
JOINT_SOURCE = "https://www.boe.es/eli/es/ai/1988/12/01/(1)"

_I = re.IGNORECASE
EXCLUDE = [  # (reason, pattern on name, official name and operator)
    ("police", re.compile(r"Gu[aà]rd[ií]?a (Civ[ií]l|Zibil)|Polic[ií]a|Polizia|Ertzaintza|Mossos|Casa[- ]?[Cc]uartel|"
                          r"^Control ", _I)),
    ("civil", re.compile(r"\bNavantia\b|\bAENA\b|\bENAIRE\b|\bMaxam\b|Aeropuert|Aeroport|A[eé]rodrome|European Space|"
                         r"Capitan[ií]a Mar[ií]tima|Autoridad portuaria|Forestal|Palomares|Tiro Ol[ií]mpico|Airsof|"
                         r"Conducci[oó]n de Aguas|Captaci[oó]n de Aguas|Central Telef[oó]nica|Coast Guard", _I)),
    ("former", re.compile(r"^(antigu[oa]s?|antic|antiga|antigo|old)\b|\bantigu[oa]\b|\bmuse[ou]\b|\bMUHBA\b|"
                          r"refugi|b[uú]n[kq]u?er|ru[ií]nas?\b|casamata|trinchera|fort[ií]n\b|\bbater[ií]as?\b|"
                          r"^Fortaleza|^Fuerte\b|^Castillo\b|Conjunto B[eé]lico|Nido de ametralladoras|Defensas Rep|"
                          r"^CAUTION", _I)),
]
BRANCH_NAMES = [  # (component, pattern on the name), in this order
    ("ume", re.compile(r"\bUME\b|Unidad Militar de Emergencias|\bBIEM\b", _I)),
    ("navy", re.compile(r"\bNaval\b|\bArmada\b|Arsenal|Infanter[ií]a de Marina|Tercio (de Armada|de Levante|del Norte|del Sur)|"
                        r"\bBRIMAR\b|Escola Naval|Escuela Naval|Real Instituto y Observatorio de la Armada|Flotilla|"
                        r"Estaci[oó]n Radio ?[Nn]aval|Radionaval|Sierra del Ret[ií]n|Base de Submarinos|Comandancia de Marina|"
                        r"Itsas Komandantzia|Poblaci[oó]n Militar de San Carlos|Calibraci[oó]n Magn[eé]tica|"
                        r"\bmariner[ií]a\b|Control Mar[ií]timo", _I)),
    ("air_force", re.compile(r"\bA[eé]re[oa]s?\b|\bA[eè]ria\b|Aerea\b|\bdel Aire\b|Ala \d|Escuadrilla|Escuadr[oó]n|"
                             r"Vigilancia A[eé]rea|Vixilancia A[eé]rea|Maestranza|Aer[oó]dromo Militar|Grupo de Escuelas|\bACAR\b|"
                             r"Bardenas", _I)),
    ("army", re.compile(r"Acuartelamiento|Cuartel|Regimiento|Brigada|\bBRI[A-Z]+\b|Legi[oó]n|\bTercio\b|"
                        r"Campo (Nacional )?de Maniobras|Campo de Tiro|Camp de [Mm]aniobres|Campo de Manobras|\bCMT\b|"
                        r"^Base (General|Coronel|Conde|El |Pr[ií]ncipe|Alfonso|Jaime|Militar|Logística|de |y Campo)|"
                        r"Academia (de Infanter[ií]a|de Artiller[ií]a|de Caballer[ií]a|de Ingenieros|General Militar)|"
                        r"Academia General B[aá]sica de Suboficiales|Ac[aà]d[eè]mia General B[aà]sica|\bFAMET\b|"
                        r"Ej[eé]rcito de Tierra|Agrupaci[oó]n de Apoyo Log[ií]stico|\bAALOG\b|\bPCMASA|Pol[vb]or[ií]n|"
                        r"Base Log[ií]stica|Mando de Ingenieros|Cuartel General Terrestre|Capitan[ií]a General|"
                        r"Campamento|Destacamento|\bE\.T\.|Ex[eé]rcito de Terra|Centro de Mantenimiento|Academia de Log[ií]stica|"
                        r"Escuela de Guerra del Ej[eé]rcito|Cr[ií]a Caballar|Escuela Militar Ecuestre|Quarter d|Caserna|"
                        r"Gobierno Militar|Gobernu Militarra|Fuerzas Especiales|base militarra|Archivo General Militar", _I)),
]
OPERATORS = [  # (component, pattern on the OSM or Wikidata operator)
    ("ume", re.compile(r"Emergencias|\bUME\b", _I)),
    ("navy", re.compile(r"Armada|Navy|Marina|Naval", _I)),
    ("air_force", re.compile(r"Aire|A[eé]re|Air Force", _I)),
    ("army", re.compile(r"Tierra|Infanter[ií]a|Artiller[ií]a|Caballer[ií]a|Ingenieros|Legi[oó]n|Brigada|Regimiento|"
                        r"FAMET|Log[ií]stic|\bArmy\b|BRIAC", _I)),
]
TAG_BRANCH = {"airfield": "air_force", "naval_base": "navy"}

RULES = {
    "installations": "Zonas militares de OpenStreetMap (landuse=military y military=base, barracks, airfield, naval_base, "
                     "range, office y, dentro de terreno militar, training_area y danger_area), cada una en el hexágono "
                     "donde cae su centro. Una zona dentro de otra mayor cuenta como parte de ella, y una sin nombre "
                     "toma el de su parte con nombre más grande. Quedan fuera los puestos de la Guardia Civil y la "
                     "policía, los sitios civiles (Navantia, AENA), los antiguos y los de patrimonio (cuarteles antiguos, "
                     "búnkeres, museos), y las zonas sin nombre.",
    "branch": "La rama sale del operador de OpenStreetMap; si no lo tiene, del nombre («Base Aérea», «Arsenal», "
              "«Acuartelamiento», «Campo de Maniobras y Tiro»…); si no, de la etiqueta (aeródromo o base naval), y si "
              f"no, del operador que Wikidata da al elemento a menos de {num(LINK_KM)} km. Lo demás queda como «otra».",
    "tier": f"No se publica la plantilla de cada base, así que el tamaño sale del terreno dentro de su límite: «grande» "
            f"desde {num(MAJOR_KM2)} km², «base» desde {num(BASE_KM2)} km² y «sitio» el resto, también las que solo "
            "son un punto.",
    "ranges": f"Los {RANGES_N} límites militares más grandes de OpenStreetMap, de al menos {num(RANGE_MIN_KM2)} km² "
              "(campos de maniobras y tiro, polígonos de tiro y las bases más extensas). Ocupan los hexágonos cuyo centro "
              "cae dentro; uno que no cubre ningún centro se dibuja en el hexágono de su punto. Un hexágono mide unos "
              "87 km², así que los campos pequeños se ven más grandes de lo que son.",
    "garrisons": "Un área urbana tiene guarnición cuando alguno de sus municipios tiene una instalación de nivel «grande» "
                 "o «base», o uno de sus hexágonos está en un campo de maniobras.",
    "joint": "Rota y Morón son de uso conjunto con Estados Unidos según el Convenio de Cooperación para la Defensa de "
             "1988 (BOE de 6 de mayo de 1989, enmendado en 2002, 2012 y 2015); siguen siendo bases españolas.",
}
RULE = RULES["garrisons"]
CAVEATS = ("El Ministerio de Defensa no publica una lista abierta de sus instalaciones ni de sus límites: los de este "
           "mapa son los de OpenStreetMap, que trazan voluntarios, y algunos solo cubren parte de un recinto (el campo "
           "de San Gregorio, por ejemplo). Tampoco publica la plantilla de cada base, así que se miden por superficie, "
           "no por efectivos. La rama se deduce del operador o del nombre y puede fallar en un recinto compartido.")


def norm(text: str) -> str:
    t = unicodedata.normalize("NFD", text.lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(ch for ch in t if unicodedata.category(ch) != "Mn")).strip()


def slug(text: str) -> str:
    return norm(text).replace(" ", "-")[:48].rstrip("-") or "sitio"


def excluded(tags: dict) -> str | None:
    """Why a feature is not a military installation of today (None when it is)."""
    text = " · ".join(tags.get(k, "") for k in ("name", "official_name", "operator"))
    return next((reason for reason, rx in EXCLUDE if rx.search(text)), None)


def name_of(tags: dict) -> str:
    return tags.get("name") or tags.get("official_name") or ""


def _component(patterns: list[tuple[str, re.Pattern]], text: str) -> str | None:
    """The component of the first pattern that matches text."""
    return next((comp for comp, rx in patterns if rx.search(text)), None)


def branch(tags: dict, wd_operators=()) -> tuple[str, str | None]:
    """(component id, how it was found: operator, name, tag, wikidata or None)."""
    comp = _component(OPERATORS, tags.get("operator") or tags.get("military_service") or "")
    if comp:
        return comp, "operator"
    comp = _component(BRANCH_NAMES, name_of(tags))
    if comp:
        return comp, "name"
    if tags.get("military") in TAG_BRANCH:
        return TAG_BRANCH[tags["military"]], "tag"
    for o in wd_operators:
        comp = _component(OPERATORS, o)
        if comp:
            return comp, "wikidata"
    return "other", None


def tier(area: float | None) -> str:
    if area is None or area < BASE_KM2:
        return "site"
    return "major" if area >= MAJOR_KM2 else "base"


class Feature:
    """One OSM item projected to map km: its shape, area and representative point."""

    def __init__(self, item: dict, proj):
        self.item, self.tags, self.osm = item, item["tags"], item["osm"]
        outer = [[proj(lon, lat) for lon, lat in r] for r in item["outer"]]
        inner = [[proj(lon, lat) for lon, lat in r] for r in item["inner"]]
        self.shape = Shape(outer + inner) if outer else None
        self.area = (sum(abs(ring_area(r)) for r in outer) - sum(abs(ring_area(r)) for r in inner)) if outer else None
        if outer:
            self.lonlat = ring_centroid(max(item["outer"], key=lambda r: abs(ring_area(r))))
        else:
            self.lonlat = tuple(item["point"])
        self.xy = proj(*self.lonlat)
        if self.shape and not self.shape.contains(*self.xy):  # a crescent: use a vertex inside its own ring
            self.lonlat = tuple(item["outer"][0][0])
            self.xy = proj(*self.lonlat)
        self.name = name_of(self.tags).strip()
        self.parts: list[Feature] = []

    @property
    def military_land(self) -> bool:
        return self.tags.get("landuse") == "military"


def _osm_order(f: Feature) -> tuple[str, int]:
    return f.osm[0], int(f.osm[1:])


def fold(features: list[Feature]) -> list[Feature]:
    """Each feature whose point lies inside a larger feature becomes a part of the smallest such one; returns the
    outermost features (heads), each with its parts (all descendants), largest first."""
    polys = sorted((f for f in features if f.shape), key=lambda f: f.area)
    parent = {}
    for f in features:
        own = f.area or 0
        for g in polys:  # smallest first, so the first that contains f is its direct parent
            # the same outline mapped twice (a tie within 1 %) folds into the older OSM element
            larger = g.area > own * 1.01 or (g.area >= own * 0.99 and _osm_order(g) < _osm_order(f))
            if g is not f and larger and g.shape.contains(*f.xy):
                parent[f.osm] = g
                break
    heads = [f for f in features if f.osm not in parent]
    for f in features:
        g = f
        while g.osm in parent:
            g = parent[g.osm]
        if g is not f:
            g.parts.append(f)
    for h in heads:
        h.parts.sort(key=lambda p: -(p.area or 0))
    return heads


def head_tags(h: Feature) -> dict:
    """The tags an installation is judged by: its own, with the name of its largest named part when it has none, and
    landuse=military when any part is military land."""
    tags = dict(h.tags)
    named = [p for p in h.parts if p.name]
    if not h.name and named:
        tags["name"] = named[0].name
        for k in ("operator", "military_service"):
            if k not in tags and k in named[0].tags:
                tags[k] = named[0].tags[k]
    if not h.military_land and any(p.military_land for p in h.parts):
        tags["landuse"] = "military"
    return tags


def keep(tags: dict) -> str | None:
    """Why a head is left out (None to keep it)."""
    if not tags.get("name"):
        return "unnamed"
    reason = excluded(tags)
    if reason:
        return reason
    if tags.get("military") in MILITARY_LAND_ONLY and tags.get("landuse") != "military":
        return "outside military land"
    return None


def wikidata_index(items: list[dict], proj):
    pts = [(proj(*i["coord"]), i) for i in items]

    def near(f: Feature) -> dict | None:
        """The Wikidata item inside the feature's boundary or within LINK_KM of its point, nearest first."""
        dist = [(0.0 if f.shape and f.shape.contains(x, y) else math.dist((x, y), f.xy), it["qid"], it) for (x, y), it in pts]
        hits = [d for d in dist if d[0] <= LINK_KM]
        return min(hits, key=lambda d: d[:2])[2] if hits else None

    return near


def installations(osm: dict, wd: list[dict], placer: Placer, proj):
    feats = [Feature(i, proj) for i in osm["items"]]
    near = wikidata_index(wd, proj)
    dropped, out, ids, off = Counter(), [], Counter(), []
    for h in fold(feats):
        tags = head_tags(h)
        reason = keep(tags)
        if reason:
            dropped[reason] += 1
            continue
        place = placer.place(*h.lonlat, unique=False)
        centre = placer.grid.center(*placer.grid.col_row(place["cell"]))
        if not placer.in_country(*h.lonlat) and math.dist(h.xy, centre) > SNAP_KM:
            dropped["off the map"] += 1  # an islet the map does not draw (Alborán, the peñones, Chafarinas)
            off.append(tags["name"])
            continue
        if placer.grid.cell_at(place["x"], place["y"]) != place["cell"]:  # snapped onto land: draw it on its hex
            place["x"], place["y"] = (round(v, 1) for v in centre)
        link = near(h)
        comp, how = branch(tags, link["operators"] if link else ())
        area = float(f"{h.area:.3g}") if h.area else None
        name = tags["name"]
        base_id = f"{slug(name)[:40].rstrip('-')}-{SHORT[comp]}"
        ids[base_id] += 1
        cells = placer.covered(h.item["outer"]) if area and area >= COVER_KM2 else None
        parts = sorted({p.name for p in h.parts if p.name and norm(p.name) != norm(name)})
        out.append({
            "id": base_id if ids[base_id] == 1 else f"{base_id}-{ids[base_id]}", "name": name, "component": comp,
            "branch_from": how, "joint": name in JOINT, "status": "act", "tier": tier(area), "curated": False,
            "area_km2": area, "cells": cells, "osm": h.osm, "qid": link["qid"] if link else None,
            **({"parts": parts} if parts else {}), **place,
        })
    if off:
        print(f"    off the map: {sorted(off)}")
    found = {i["name"] for i in out}
    missing = [n for n in JOINT if n not in found]
    if missing:
        print(f"    WARNING: joint bases not found in OSM: {missing}")
    out.sort(key=lambda i: (TIERS.index(i["tier"]), -(i["area_km2"] or 0), i["name"]))
    return out, dropped


def ranges(inst: list[dict]) -> list[dict]:
    largest = sorted((i for i in inst if (i["area_km2"] or 0) >= RANGE_MIN_KM2), key=lambda i: -i["area_km2"])
    return [{"id": i["id"], "name": i["name"], "component": i["component"], "area_km2": i["area_km2"],
             "cells": i["cells"] or [i["cell"]], "state": i["state"], "hex_state": i["state"], "installation": i["id"]}
            for i in largest[:RANGES_N]]


def provinces(inst: list[dict], states: list[dict]) -> dict:
    out = {}
    for s in states:
        mine = [i for i in inst if i["state"] == s["abbr"]]
        out[s["abbr"]] = {
            "installations": len(mine),
            "by_component": dict(Counter(i["component"] for i in mine)),
            "major": sum(i["tier"] == "major" for i in mine),
            "area_km2": round(sum(i["area_km2"] or 0 for i in mine), 1),
            "population": s.get("population"),
            "personnel": None, "spending": None,
        }
    return out


def garrisons(inst: list[dict], rngs: list[dict], cities: list[dict]) -> dict:
    range_cells = {c: r for r in rngs for c in r["cells"]}
    by_id = {i["id"]: i for i in inst}
    out = {}
    for city in cities:
        sites = [i for i in inst if i["cbsa"] == city["id"] and i["tier"] != "site"]
        for c in city.get("footprint") or []:
            r = range_cells.get(c)
            if r and by_id[r["installation"]] not in sites:
                sites.append(by_id[r["installation"]])
        if not sites:
            continue
        sites.sort(key=lambda i: (TIERS.index(i["tier"]), -(i["area_km2"] or 0)))
        comps = Counter(i["component"] for i in sites)
        out[city["id"]] = {"installations": [i["id"] for i in sites[:8]], "installation_count": len(sites),
                           "area_km2": round(sum(i["area_km2"] or 0 for i in sites), 1),
                           "naval": comps["navy"] > comps["army"] + comps["air_force"],
                           "components": dict(comps)}
    return dict(sorted(out.items(), key=lambda kv: (-kv[1]["area_km2"], kv[0])))


def build() -> None:
    world = load_interim("_world")
    proj = active().world_projection(world)
    placer = Placer(world)
    osm_p, wd_p = load_interim_payload("osm_militar"), load_interim_payload("wikidata_militar")
    inst, dropped = installations(osm_p["data"], wd_p["data"]["items"], placer, proj)
    rngs = ranges(inst)
    states = load_web("states.json")
    doc = {
        "version": 1,
        "vintage": {"installations": vintage(osm_p["vintage"]), "links": vintage(wd_p["vintage"])},
        "sources": ["osm_militar", "wikidata_militar"],
        "rule": RULE,
        "rules": RULES,
        "joint_source": JOINT_SOURCE,
        "caveats": CAVEATS,
        "components": COMPONENTS,
        "installations": inst,
        "ranges": rngs,
        "states": provinces(inst, states),
        "national": {"installations": len(inst), "area_km2": round(sum(i["area_km2"] or 0 for i in inst), 1),
                     "by_component": dict(Counter(i["component"] for i in inst)),
                     "linked": sum(1 for i in inst if i["qid"]), "wikidata_items": len(wd_p["data"]["items"])},
        "garrisons": garrisons(inst, rngs, load_web("cities.json")),
    }
    write_web("military.json", doc)
    tiers = Counter(i["tier"] for i in inst)
    print(f"    {len(inst)} installations ({', '.join(f'{v} {k}' for k, v in tiers.items())}); left out: {dict(dropped)}")
    print(f"    branches {dict(Counter(i['component'] for i in inst))}; from {dict(Counter(i['branch_from'] for i in inst))}")
    print(f"    {len(rngs)} ranges; {len(doc['garrisons'])} garrison cities; {doc['national']['linked']} linked to Wikidata")


def check(web_dir) -> list[tuple[str, str]]:
    """Spain-only checks on top of military.check (which validates the shared contract)."""
    path = Path(web_dir) / "military.json"
    if active().id != "es" or not path.exists():
        return []
    d = json.loads(path.read_text())
    bad = []
    comps = {c["id"] for c in d.get("components") or []}
    if comps != set(COMPONENT_IDS):
        bad.append(f"components {sorted(comps)} are not {COMPONENT_IDS}")
    names = {i["name"] for i in d.get("installations") or []}
    for n in JOINT:
        if n not in names:
            bad.append(f"joint base {n!r} missing")
    if any(i.get("joint") and i["name"] not in JOINT for i in d.get("installations") or []):
        bad.append("a joint installation is not Rota or Morón")
    for cid, g in (d.get("garrisons") or {}).items():
        if not g.get("installations"):
            bad.append(f"garrison {cid}: no installations")
    out = [("FAIL", f"military.json (es): {m}") for m in bad]
    if not bad:
        other = sum(i["component"] == "other" for i in d["installations"])
        out.append(("PASS", f"military.json (es): {len(d['installations'])} installations, {other} without a branch, "
                            f"{d['national']['linked']} linked to Wikidata, {len(d.get('garrisons') or {})} garrison cities"))
    return out
