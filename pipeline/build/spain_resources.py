"""Spain's tile resources: the power plants and the mines (resources.json, same contract as the US build).

Thresholds are lower than the US ones (Spain's grid is about a tenth of the US's, and its hexes are 10 km wide):
single plants count from PLANT_MIN MW of their fuel; wind, solar and battery plants are summed per hex and shown from
CLUSTER_MIN MW. Plants of the same type in one hex are one site (two OSM objects for Jinámar, Ascó I and II). Every
nuclear plant in service is shown. Every active metal mine and key industrial-mineral mine of the Estadística Minera
is shown, one site each and without a value (the statistic publishes no output per mine). Oil and gas fields are not
mapped.
"""

from __future__ import annotations

import re
from collections import defaultdict

from ..core.store import load_interim, load_interim_payload, load_web, write_web
from ..sources.es.provinces import PROVINCES, display_name
from .resources import Placer, _cluster_name, _settle, _t, _tidy, summarize
from .spain_wonders import municipality_finder
from .texts_es import num

REQUIRES = ["_world", "power_plants_es", "igme_minas", "siane", "cities.json", "world.json"]
PRODUCES = ["resources.json"]
COUNTRIES = ("es",)

PLANT_MIN = {"hydro": 200, "pumped_storage": 400, "coal": 500, "gas": 750, "oil": 150}
CLUSTER_MIN = {"wind": 150, "solar": 150, "battery": 50}
OFFSHORE_RINGS = 3
SRC = "power_plants_es"
PER_HEX = "Las centrales de este tipo en un mismo hexágono se suman y se muestran como un solo sitio."
SUMMARY_NOTE = ("Totales de los sitios del mapa: cada tipo de central tiene un umbral de tamaño (ver su descripción), así "
                "que no son la potencia total de una provincia ni de España. Las minas se cuentan, sin valor.")
UNIT = re.compile(r"\s+(\d+|[IVX]+|Phase)$")  # 'Almaraz 1' and 'Almaraz 2' are units of 'Almaraz'
TYPE_OF = {"coal": "coal_plant", "gas": "gas_plant", "oil": "oil_plant"}
MINE_SRC = "igme_minas"
MINE_RULE = ("Todas las explotaciones de {what} activas en 2019 según la Estadística Minera de España (IGME, Panorama "
             "Minero 2022), la lista más reciente con el nombre de cada mina. Sin umbral de tamaño ni valor: la "
             "estadística no publica la producción de cada mina. Cada una está en el yacimiento del BDMIN del IGME de su "
             "mineral y su municipio que comparte nombre con ella (o en el único grande o mediano); si no hay ninguno, "
             "en el centro de su municipio, y su detalle lo dice.")
SMALL_WORDS = {"de", "del", "la", "las", "los", "el", "y", "e", "o", "a", "en"}
ROMAN = {"I", "II", "III", "IV", "V", "VI"}


def _mine(id, name, emoji, color, what, icon=None):
    t = _t(id, name, "mineral", emoji, color, None, MINE_RULE.format(what=what), MINE_SRC)
    return {**t, "icon": icon} if icon else t


TYPES = [
    _t("nuclear", "Central nuclear", "energy", "☢️", "#e8d44d", "MW",
       "Todas las centrales nucleares en servicio (powerplantmatching): Almaraz, Ascó, Cofrentes, Vandellós y Trillo. "
       "El valor es la potencia de la central; las cerradas (Garoña, Zorita, Vandellós I) no salen.", SRC),
    _t("hydro", "Central hidroeléctrica", "energy", "💧", "#3fa7d6", "MW",
       f"Centrales hidráulicas (de embalse o fluyentes) de {PLANT_MIN['hydro']} MW o más. {PER_HEX}", SRC),
    _t("coal_plant", "Central de carbón", "energy", "🏭", "#5a5a5a", "MW",
       f"Centrales de carbón de {PLANT_MIN['coal']} MW o más que powerplantmatching aún no da por cerradas. {PER_HEX}",
       SRC),
    _t("gas_plant", "Central de gas", "energy", "⚡", "#f08a24", "MW",
       f"Centrales de gas (sobre todo ciclos combinados) de {PLANT_MIN['gas']} MW o más. {PER_HEX}", SRC),
    {**_t("oil_plant", "Central de fuel", "energy", "🛢️", "#3a2f2a", "MW",
          f"Centrales de fuel y diésel de {PLANT_MIN['oil']} MW o más: los sistemas eléctricos insulares (Canarias, "
          f"según OpenStreetMap; Baleares, Ceuta y Melilla). {PER_HEX}", SRC), "icon": "r-oil"},
    _t("pumped_storage", "Central de bombeo", "energy", "🔄", "#2f7fb8", "MW",
       f"Centrales de bombeo de {PLANT_MIN['pumped_storage']} MW o más: baterías de la red hechas con dos embalses. "
       f"{PER_HEX}", SRC),
    _t("wind", "Parques eólicos", "energy", "🌬️", "#9fd8cb", "MW",
       f"Potencia eólica, donde un hexágono suma {CLUSTER_MIN['wind']} MW o más. {PER_HEX}", SRC),
    _t("solar", "Plantas solares", "energy", "☀️", "#ffc93c", "MW",
       f"Potencia solar (fotovoltaica y termosolar), donde un hexágono suma {CLUSTER_MIN['solar']} MW o más (sin el "
       f"autoconsumo en tejados). {PER_HEX}", SRC),
    _t("battery", "Baterías", "energy", "🔋", "#7bc96f", "MW",
       f"Almacenamiento en baterías, donde un hexágono suma {CLUSTER_MIN['battery']} MW o más. {PER_HEX}", SRC),
    _mine("copper", "Mina de cobre", "🥉", "#b87333", "cobre"),
    _mine("gold", "Mina de oro", "🥇", "#d4af37", "oro y plata"),
    _mine("tungsten", "Mina de wolframio", "🔩", "#6f7f8f", "wolframio", "r-iron"),
    _mine("tin_tantalum", "Mina de estaño y tántalo", "🪙", "#9aa7b4", "estaño y tántalo", "r-silver"),
    _mine("potash", "Mina de potasa", "🧂", "#e07a5f", "sales potásicas", "r-molybdenum"),
    _mine("fluorite", "Mina de fluorita", "💎", "#8e6cc9", "fluorita (espato flúor)", "r-molybdenum"),
    _mine("celestine", "Mina de celestina", "🔷", "#6fa8dc", "estroncio (celestina)", "r-molybdenum"),
    _mine("magnesite", "Mina de magnesita", "🧱", "#c9a27e", "magnesita", "r-molybdenum"),
    _mine("sodium_sulfate", "Mina de sulfato sódico", "🧪", "#9fc5c0", "sulfato sódico (glauberita y thenardita)",
          "r-molybdenum"),
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
    online = "" if not years else f", en servicio desde {years[0]}" + (f"–{years[-1]}" if years[-1] != years[0] else "")
    if len(group) == 1:
        name, detail = lead["name"], f"{num(mw)} MW{online}"
    else:
        bases = {UNIT.sub("", p["name"]) for p, _, _ in group}
        name = (bases.pop() if len(bases) == 1 else None) \
            or _cluster_name([(p["name"], p["mw"]) for p, _, _ in group]) or f"{_tidy(lead['name'])} (+{len(group) - 1})"
        detail = f"{len(group)} centrales, entre ellas {lead['name']} ({num(lead['mw'])} MW){online}"
    if any(p["offshore"] for p, _, _ in group):
        detail += "; marina, en el hexágono de costa más cercano"
    if any(p["source"] == "osm" for p, _, _ in group):
        detail += "; OpenStreetMap"
    return {"type": type_id, "name": _tidy(name), "x": x, "y": y, "cell": cell, "value": round(mw), "detail": detail}


def title_es(name: str) -> str:
    """A name the list writes in capitals, as Spanish writes it: 'MINAS DE RIO TINTO' → 'Minas de Rio Tinto' (articles
    and prepositions in lower case, Roman numerals kept); a name already in mixed case is left alone."""
    if not name.isupper():
        return name
    def word(m):
        w = m.group(0)
        if w in ROMAN:
            return w
        return w.lower() if w.lower() in SMALL_WORDS and m.start() else w.capitalize()
    return re.sub(r"[^\W\d_]+", word, name)


def mine_site(m: dict, place: Placer, find) -> dict:
    """One map site for a working of the IGME list: at its BDMIN deposit, or at its municipality's centre."""
    muni = find(m["municipality"], m["province"])
    if m["lon"] is not None:
        lon, lat = m["lon"], m["lat"]
        deposit = title_es(m["deposit"] or "").rstrip(" .,")
        where = f"en el yacimiento «{deposit}» del BDMIN" if deposit else "en un yacimiento sin nombre del BDMIN"
    else:
        lon, lat = muni["centre"]
        where = "en el centro del municipio (ningún yacimiento del BDMIN casa con la mina)"
    x, y, cell = place(lon, lat)
    if cell < 0:
        raise RuntimeError(f"IGME mine {m['name']!r} falls off the map")
    province = display_name(PROVINCES[m["province"]][1])
    detail = f"{m['company']}; {display_name(muni['name'])} ({province}); activa en 2019; {where}"
    return {"type": m["type"], "name": _tidy(title_es(m["name"])), "x": x, "y": y, "cell": cell, "value": None,
            "detail": detail}


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
    find = municipality_finder(load_interim("siane")["municipalities"])
    items += [mine_site(m, place, find) for m in load_interim("igme_minas")["mines"]]
    items.sort(key=lambda it: (RANK[it["type"]], -(it["value"] or 0)))
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
