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
from ..sources.es.names import title_es
from ..sources.es.provinces import PROVINCES, display_name
from .resources import Placer, _cluster_name, _settle, _t, _tidy, summarize
from .spain_wonders import municipality_finder
from .states import energy_by_state
from .texts_es import Text, tr
from ..core.lang import Num

REQUIRES = ["states.json", "_world", "power_plants_es", "igme_minas", "siane", "cities.json", "world.json"]
PRODUCES = ["resources.json"]
COUNTRIES = ("es",)

PLANT_MIN = {"hydro": 200, "pumped_storage": 400, "coal": 500, "gas": 750, "oil": 150}
CLUSTER_MIN = {"wind": 150, "solar": 150, "battery": 50}
OFFSHORE_RINGS = 3
SRC = "power_plants_es"
PER_HEX = tr("Las centrales de este tipo en un mismo hexágono se suman y se muestran como un solo sitio.",
             "Plants of this type in one hex are added up and shown as one site.")
SUMMARY_NOTE = tr("Totales de los sitios del mapa: cada tipo de central tiene un umbral de tamaño (ver su descripción), así "
                  "que no son la potencia total de una provincia ni de España. Las minas se cuentan, sin valor.",
                  "Totals of the sites on the map: each plant type has a size threshold (see its description), so these are "
                  "not the total capacity of a province or of Spain. Mines are counted, without a value.")
ENERGY_NOTE = tr("Solo cuentan las centrales y las agrupaciones eólicas, solares y de baterías del mapa, cada una por encima "
                 "del umbral de su tipo: no es la potencia total instalada en la provincia.",
                 "Only the plants and the wind, solar and battery clusters on the map count, each above its type's "
                 "threshold: this is not the province's total installed capacity.")
UNIT = re.compile(r"\s+(\d+|[IVX]+|Phase)$")  # 'Almaraz 1' and 'Almaraz 2' are units of 'Almaraz'
# powerplantmatching files many plants under English names ('Las Majas Wind Farm', 'Castile La Mancha Solar'): the map
# writes the kind first, in Spanish ('Parque eólico Las Majas'), and the regions by their Spanish names.
PLANT_KINDS = [(re.compile(r"^(.+?) Wind(?: Farm)?\b(?: Spain)?"), "Parque eólico {}"),
               (re.compile(r"^(.+?) (?:Thermosolar|Csp Solar) Farm\b(?: Spain)?"), "Central termosolar {}"),
               (re.compile(r"^(.+?)(?: Solar)? Solar (?:Farm|Park|Photovoltaic)\b(?: Spain)?"), "Planta solar {}")]
EXONYMS = {"Castile La Mancha": "Castilla-La Mancha", "Castile Leon": "Castilla y León", "Andalusia": "Andalucía",
           "Aragon": "Aragón", "Seville": "Sevilla"}
TYPE_OF = {"coal": "coal_plant", "gas": "gas_plant", "oil": "oil_plant"}
MINE_SRC = "igme_minas"
MINE_RULE = tr(
    "Todas las explotaciones de {what} activas en 2019 según la Estadística Minera de España (IGME, Panorama Minero 2022), "
    "la lista más reciente con el nombre de cada mina. Sin umbral de tamaño ni valor: la estadística no publica la "
    "producción de cada mina. Cada una está en el yacimiento del BDMIN del IGME de su mineral y su municipio que comparte "
    "nombre con ella (o en el único grande o mediano); si no hay ninguno, en el centro de su municipio, y su detalle lo "
    "dice.",
    "Every {what} working active in 2019 according to the Estadística Minera de España (IGME, Panorama Minero 2022), the "
    "latest list that names each mine. No size threshold and no value: the statistic publishes no output per mine. Each "
    "one sits at the IGME BDMIN deposit of its mineral and municipality that shares its name (or at the only large or "
    "medium one); if there is none, at the centre of its municipality, and its detail says so.")


def _mine(id, name, emoji, color, what, icon=None):
    t = _t(id, name, "mineral", emoji, color, None, MINE_RULE.format(what=what), MINE_SRC)
    return {**t, "icon": icon} if icon else t


TYPES = [
    _t("nuclear", tr("Central nuclear", "Nuclear plant"), "energy", "☢️", "#e8d44d", "MW", tr(
        "Todas las centrales nucleares en servicio (powerplantmatching): Almaraz, Ascó, Cofrentes, Vandellós y Trillo. El "
        "valor es la potencia de la central; las cerradas (Garoña, Zorita, Vandellós I) no salen.",
        "Every nuclear plant in service (powerplantmatching): Almaraz, Ascó, Cofrentes, Vandellós and Trillo. The value is "
        "the plant's capacity; closed ones (Garoña, Zorita, Vandellós I) are not shown."), SRC),
    _t("hydro", tr("Central hidroeléctrica", "Hydroelectric plant"), "energy", "💧", "#3fa7d6", "MW", tr(
        "Centrales hidráulicas (de embalse o fluyentes) de {mw} MW o más. ",
        "Hydro plants (reservoir or run-of-river) of {mw} MW or more. ").format(mw=PLANT_MIN["hydro"]) + PER_HEX, SRC),
    _t("coal_plant", tr("Central de carbón", "Coal plant"), "energy", "🏭", "#5a5a5a", "MW", tr(
        "Centrales de carbón de {mw} MW o más que powerplantmatching aún no da por cerradas. ",
        "Coal plants of {mw} MW or more that powerplantmatching does not yet list as closed. ").format(mw=PLANT_MIN["coal"])
       + PER_HEX, SRC),
    _t("gas_plant", tr("Central de gas", "Gas plant"), "energy", "⚡", "#f08a24", "MW", tr(
        "Centrales de gas (sobre todo ciclos combinados) de {mw} MW o más. ",
        "Gas plants (mostly combined cycle) of {mw} MW or more. ").format(mw=PLANT_MIN["gas"]) + PER_HEX, SRC),
    {**_t("oil_plant", tr("Central de fuel", "Oil plant"), "energy", "🛢️", "#3a2f2a", "MW", tr(
        "Centrales de fuel y diésel de {mw} MW o más: los sistemas eléctricos insulares (Canarias, según OpenStreetMap; "
        "Baleares, Ceuta y Melilla). ",
        "Fuel oil and diesel plants of {mw} MW or more: the island power systems (the Canary Islands, from OpenStreetMap; "
        "the Balearic Islands, Ceuta and Melilla). ").format(mw=PLANT_MIN["oil"]) + PER_HEX, SRC), "icon": "r-oil"},
    _t("pumped_storage", tr("Central de bombeo", "Pumped storage"), "energy", "🔄", "#2f7fb8", "MW", tr(
        "Centrales de bombeo de {mw} MW o más: baterías de la red hechas con dos embalses. ",
        "Pumped-storage plants of {mw} MW or more: grid batteries made of two reservoirs. ").format(
        mw=PLANT_MIN["pumped_storage"]) + PER_HEX, SRC),
    _t("wind", tr("Parques eólicos", "Wind farms"), "energy", "🌬️", "#9fd8cb", "MW", tr(
        "Potencia eólica, donde un hexágono suma {mw} MW o más. ",
        "Wind capacity, where a hex adds up to {mw} MW or more. ").format(mw=CLUSTER_MIN["wind"]) + PER_HEX, SRC),
    _t("solar", tr("Plantas solares", "Solar plants"), "energy", "☀️", "#ffc93c", "MW", tr(
        "Potencia solar (fotovoltaica y termosolar), donde un hexágono suma {mw} MW o más (sin el autoconsumo en tejados). ",
        "Solar capacity (photovoltaic and solar thermal), where a hex adds up to {mw} MW or more (rooftop self-consumption "
        "not included). ").format(mw=CLUSTER_MIN["solar"]) + PER_HEX, SRC),
    _t("battery", tr("Baterías", "Batteries"), "energy", "🔋", "#7bc96f", "MW", tr(
        "Almacenamiento en baterías, donde un hexágono suma {mw} MW o más. ",
        "Battery storage, where a hex adds up to {mw} MW or more. ").format(mw=CLUSTER_MIN["battery"]) + PER_HEX, SRC),
    _mine("copper", tr("Mina de cobre", "Copper mine"), "🥉", "#b87333", tr("cobre", "copper")),
    _mine("gold", tr("Mina de oro", "Gold mine"), "🥇", "#d4af37", tr("oro y plata", "gold and silver")),
    _mine("tungsten", tr("Mina de wolframio", "Tungsten mine"), "🔩", "#6f7f8f", tr("wolframio", "tungsten"), "r-iron"),
    _mine("tin_tantalum", tr("Mina de estaño y tántalo", "Tin and tantalum mine"), "🪙", "#9aa7b4",
          tr("estaño y tántalo", "tin and tantalum"), "r-silver"),
    _mine("potash", tr("Mina de potasa", "Potash mine"), "🧂", "#e07a5f", tr("sales potásicas", "potash"), "r-molybdenum"),
    _mine("fluorite", tr("Mina de fluorita", "Fluorite mine"), "💎", "#8e6cc9", tr("fluorita (espato flúor)", "fluorite (fluorspar)"),
          "r-molybdenum"),
    _mine("celestine", tr("Mina de celestina", "Celestine mine"), "🔷", "#6fa8dc",
          tr("estroncio (celestina)", "strontium (celestine)"), "r-molybdenum"),
    _mine("magnesite", tr("Mina de magnesita", "Magnesite mine"), "🧱", "#c9a27e", tr("magnesita", "magnesite"), "r-molybdenum"),
    _mine("sodium_sulfate", tr("Mina de sulfato sódico", "Sodium sulphate mine"), "🧪", "#9fc5c0",
          tr("sulfato sódico (glauberita y thenardita)", "sodium sulphate (glauberite and thenardite)"), "r-molybdenum"),
]
RANK = {t["id"]: i for i, t in enumerate(TYPES)}


def type_of(fuel: str) -> str:
    return TYPE_OF.get(fuel, fuel)


def minimum(fuel: str) -> float:
    return 0 if fuel == "nuclear" else PLANT_MIN.get(fuel, CLUSTER_MIN.get(fuel, float("inf")))


def plant_name(name: str) -> Text:
    """A plant's name as the map shows it. Spanish: 'Las Majas Wind Farm (+1)' → 'Parque eólico Las Majas (+1)',
    'Andalusia Solar' → 'Andalucía Solar'; English: the source's own name, as powerplantmatching writes it. Both drop
    the source's noise: 'Alcudia Phase' → 'Alcudia', 'X Wind Farm Spain' → 'X Wind Farm'."""
    def tidy(n: str) -> str:
        return re.sub(r"\s+Phase$", "", re.sub(r" Spain\b", "", n))

    es = name
    for pattern, form in PLANT_KINDS:
        es, n = pattern.subn(lambda m: form.format(m.group(1)), es, count=1)
        if n:
            break
    es = tidy(es)
    for en, local in EXONYMS.items():
        es = re.sub(rf"\b{en}\b", local, es)
    return tr(title_es(es), title_es(tidy(name)))


def site(type_id: str, group: list[tuple[dict, float, float]], cell: int) -> dict:
    """One map site from the (plant, x, y) of a type in a hex: the capacity-weighted position, the largest plant's
    name (or the plants' shared name), and the plants and online years in the detail."""
    group.sort(key=lambda g: -g[0]["mw"])
    lead = group[0][0]
    mw = sum(p["mw"] for p, _, _ in group)
    x = sum(gx * p["mw"] for p, gx, _ in group) / mw
    y = sum(gy * p["mw"] for p, _, gy in group) / mw
    years = sorted(p["year"] for p, _, _ in group if p["year"])
    span = "" if not years else str(years[0]) + (f"–{years[-1]}" if years[-1] != years[0] else "")
    online = tr(", en servicio desde {span}", ", in service since {span}").format(span=span) if years else ""
    if len(group) == 1:
        name, detail = lead["name"], tr("{mw} MW", "{mw} MW").format(mw=Num(round(mw, 2))) + online
    else:
        bases = {UNIT.sub("", p["name"]) for p, _, _ in group}
        name = (bases.pop() if len(bases) == 1 else None) \
            or _cluster_name([(p["name"], p["mw"]) for p, _, _ in group]) or f"{_tidy(lead['name'])} (+{len(group) - 1})"
        detail = tr("{n} centrales, entre ellas {lead} ({mw} MW)", "{n} plants, including {lead} ({mw} MW)").format(
            n=len(group), lead=plant_name(lead["name"]), mw=Num(round(lead["mw"], 2))) + online
    if any(p["offshore"] for p, _, _ in group):
        detail += tr("; marina, en el hexágono de costa más cercano", "; offshore, on the nearest coastal hex")
    if any(p["source"] == "osm" for p, _, _ in group):
        detail += "; OpenStreetMap"
    return {"type": type_id, "name": plant_name(_tidy(name)), "x": x, "y": y, "cell": cell, "value": round(mw), "detail": detail}


def mine_site(m: dict, place: Placer, find) -> dict:
    """One map site for a working of the IGME list: at its BDMIN deposit, or at its municipality's centre."""
    muni = find(m["municipality"], m["province"])
    if m["lon"] is not None:
        lon, lat = m["lon"], m["lat"]
        deposit = title_es(m["deposit"] or "").rstrip(" .,")
        where = (tr("en el yacimiento «{d}» del BDMIN", "at the BDMIN deposit “{d}”").format(d=deposit) if deposit
                 else tr("en un yacimiento sin nombre del BDMIN", "at an unnamed BDMIN deposit"))
    else:
        lon, lat = muni["centre"]
        where = tr("en el centro del municipio (ningún yacimiento del BDMIN casa con la mina)",
                   "at the centre of the municipality (no BDMIN deposit matches the mine)")
    x, y, cell = place(lon, lat)
    if cell < 0:
        raise RuntimeError(f"IGME mine {m['name']!r} falls off the map")
    province = display_name(PROVINCES[m["province"]][1])
    detail = tr("{company}; {muni} ({province}); activa en 2019; {where}",
                "{company}; {muni} ({province}); active in 2019; {where}").format(
        company=title_es(m["company"]), muni=display_name(muni["name"]), province=province, where=where)
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
    # Provinces' mapped power (states.json `energy`, as the US states have it). spain.py writes states.json before
    # this builder can run (resources need its cities), so the field is filled in here.
    energy = energy_by_state(ENERGY_NOTE)
    provinces = load_web("states.json", texts=True)  # its texts in every language, written back as they are
    for p in provinces:
        p["energy"] = dict(energy.get(p["abbr"]) or energy[""])
    write_web("states.json", provinces)
    counts = defaultdict(int)
    for it in items:
        counts[it["type"]] += 1
    print("    " + ", ".join(f"{t['id']} {counts[t['id']]}" for t in TYPES) + f"; {moved} moved to their hex centre")
