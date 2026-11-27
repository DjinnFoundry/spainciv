"""Spain's longevity lenses (group "longevity", DECISIONS E107–E108).

* **Life expectancy** at birth and **at 65** (INE Indicadores Demográficos Básicos, `life_lens`): the 155 municipalities
  INE computes it for carry their own figure, every other municipality its province's (a life expectancy cannot be
  subtracted, so there is no rest of the province); a hex takes the population-weighted mean of its municipalities.
  The lens at 65 lists, per hex, the units it takes them from, with both sexes, men and women.
* **Oldest old** (índice de sobreenvejecimiento): residents aged 85 and over ÷ those aged 65 and over (INE Annual
  Population Census by age), drawn towards Spain's index as if the hex had OLDEST_PRIOR more residents aged 65 and over
  at that index. **Centenarians**: residents aged 100 and over per 10,000, drawn towards Spain's rate the same way
  with CENTENARIAN_PRIOR residents. Both pool a hex's municipalities before dividing: each municipality adds its count
  × the share of its census residents the hex holds (`spain_fiesta.hex_totals`).
* **Longevity zones**: how many of those three a hex has at or above the population-weighted ZONE_PERCENTILE of land
  hexes (the value that three in four residents live at or below); hexes with all three that touch make a zone, named
  after the municipality with most of its residents. The three lenses store their values at the precision the map
  shows them (DIGITS), and the cuts are taken from those values, so a tooltip and the zones never disagree.

The builder is spain.py, which calls `lenses()`; SOURCES go into its REQUIRES.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ..core.hexgrid import HexGrid, components
from ..core.lang import Num, Text, and_list, tr
from ..core.store import load_interim, load_interim_payload
from ..sources.es.ine_people import ages_from
from ..sources.es.provinces import PROVINCES, display_name
from .lenses import AMENITIES_RAMP, _spread
from .spain_daily import SPREAD, by_municipality, share_text
from .spain_fiesta import hex_totals, shrunk_rate

SOURCES = ["ine_censo_edad", "ine_esperanza_vida"]
PER = 10_000  # centenarians per 10,000 residents
CENTENARIAN_PRIOR = 10_000  # residents at Spain's rate added to every hex: at that rate, about 3.7 centenarians
OLDEST_PRIOR = 200  # residents aged 65+ at Spain's oldest-old index added to every hex: about 31 aged 85+
RATE_MIN = CENTENARIAN_PRIOR  # a municipality's own centenarian rate is listed only from this many residents up
ZONE_PERCENTILE = 0.75  # a zone's hexes are at or above this population-weighted percentile in all three measures
SPARSE = 12.5  # inhabitants per km²: a sparsely populated NUTS 3 region in the EU's Guidelines on regional State aid
ZONES_LISTED = 6  # the largest zones the description names, by hexes and by residents; the legend lists as many
OLD_FROM, OLDEST_FROM, CENTENARIAN_FROM = 65, 85, 100
ZONE_MEASURES = ("oldest_old", "centenarians", "life_expectancy_65")
# The digits each zone measure is stored with: the one decimal the map shows ("17,3 %" is 0.173, "4,4", "22,2 años").
DIGITS = {"oldest_old": 3, "centenarians": 1, "life_expectancy_65": 1}
ZONE_CATEGORIES = [("none", tr("Ninguna", "None"), "#2b2433"), ("one", tr("Una", "One"), "#5b5a6e"),
                   ("two", tr("Dos", "Two"), "#8fae7a"),
                   ("three", tr("Las tres: zona de longevidad", "All three: a longevity zone"), "#e8d56a")]
POINT = tr("Toca o pasa el ratón por un hexágono", "Tap or hover over a hex")


def unit_of(own: dict, code: str) -> str:
    """The unit a municipality takes its life expectancy from: itself if INE lists it, else its province."""
    return code if code in own else code[:2]


def unit_name(code: str, munis: dict[str, str]) -> Text | str:
    """A municipality by its name; a province: 'Provincia de Zamora'."""
    if len(code) == 5:
        return munis.get(code, code)
    return tr("Provincia de {name}", "Province of {name}").format(name=display_name(PROVINCES[code][1]))


def held_units(geoids: list[str], weights: list, unit: dict[str, int]) -> list:
    """Per hex, the indices of the units (`unit`, municipality code → index; one missing has none) its municipalities
    are in, the one with most of its residents first; null where it has none."""
    out = []
    for parts in weights:
        held: Counter = Counter()
        for k, w in parts:
            u = unit.get(geoids[k])
            if u is not None and w > 0:
                held[u] += w
        out.append(sorted(held, key=lambda u: (-held[u], u)) or None)
    return out


LIFE = {
    "birth": {
        "id": "life_expectancy", "name": tr("Esperanza de vida", "Life expectancy"), "icon": "l-amenities",
        "emoji": "❤️", "unit": tr("años al nacer", "years at birth"), "digits": 2,
        "description": tr(
            "Esperanza de vida al nacer, ambos sexos, en {year} (Indicadores Demográficos Básicos del INE). Los {n} "
            "municipios para los que el INE la calcula tienen la suya; los demás, la de su provincia, que incluye a "
            "esos municipios (una esperanza de vida no se puede restar). Ocupa el lugar del índice de bienestar del "
            "mapa de EE. UU. (estimaciones de salud de los CDC). {spread}",
            "Life expectancy at birth, both sexes, in {year} (INE Basic Demographic Indicators). The {n} "
            "municipalities INE calculates it for have their own; the others take their province's, which includes "
            "those municipalities (a life expectancy cannot be subtracted). It takes the place of the US map's "
            "wellbeing index (CDC health estimates). {spread}"),
    },
    "65": {
        "id": "life_expectancy_65", "name": tr("Vida a los 65", "Life at 65"),
        "heading": tr("Esperanza de vida a los 65", "Life expectancy at 65"),
        "icon": "l-life-65", "emoji": "⌛", "unit": tr("años más a los 65", "more years at 65"),
        "digits": DIGITS["life_expectancy_65"],
        "description": tr(
            "Años que le quedan de media a quien cumple 65, ambos sexos, en {year} (Indicadores Demográficos Básicos "
            "del INE; en España, {spain}: {men} los hombres y {women} las mujeres). Los {n} municipios para los que el "
            "INE la calcula tienen la suya; los demás, la de su provincia, que incluye a esos municipios, así que fuera "
            "de ellos la lente sigue las fronteras provinciales. {point} para ver de qué municipios o provincias sale, "
            "con hombres y mujeres. {spread}",
            "The years someone turning 65 has left on average, both sexes, in {year} (INE Basic Demographic "
            "Indicators; Spain: {spain}, {men} for men and {women} for women). The {n} municipalities INE calculates "
            "it for have their own; the others take their province's, which includes those municipalities, so outside "
            "them the lens follows province borders. {point} to see the municipalities or provinces it comes from, "
            "with men and women. {spread}"),
    },
}


def life_lens(measure: str, data: dict, geoids: list[str], weights: list, munis: dict[str, str]) -> dict:
    """The life expectancy lens at birth (`measure` "birth", from data's top level) or at 65 ("65", from data["at65"],
    which also lists each hex's units)."""
    meta = LIFE[measure]
    src = data if measure == "birth" else data["at65"]
    both = (lambda v: v) if measure == "birth" else (lambda v: v["both"])
    own, prov = src["municipalities"], src["provinces"]
    value = {**{p: both(v) for p, v in prov.items()}, **{m: both(v) for m, v in own.items()}}
    fields = {"year": str(src["year"]), "n": len(own), "spread": SPREAD}
    lens = {
        "id": meta["id"], "group": "longevity", "name": meta["name"], "icon": meta["icon"], "emoji": meta["emoji"],
        "unit": meta["unit"], "format": "years", "scale": "linear", "higher_is": "good", "ramp": AMENITIES_RAMP,
        "source": "ine_esperanza_vida",
        "values": _spread(weights, by_municipality(geoids, lambda g: value.get(unit_of(own, g))), meta["digits"]),
    }
    if measure == "birth":
        return {**lens, "description": meta["description"].format(**fields)}
    spain = src["nation"]
    keys = [*sorted(own), *sorted(prov)]
    index = {k: i for i, k in enumerate(keys)}
    lens |= {"heading": meta["heading"], "decimals": meta["digits"], "touch_details": True}
    lens["description"] = meta["description"].format(
        **fields, point=POINT, spain=Num(spain["both"], 2), men=Num(spain["men"], 2), women=Num(spain["women"], 2))
    lens["names"] = [tr("{name}: {both} (hombres {men}, mujeres {women})", "{name}: {both} (men {men}, women {women})")
                     .format(name=unit_name(k, munis), **{s: Num(v, 2) for s, v in (own.get(k) or prov[k]).items()})
                     for k in keys]
    units = {g: index[unit_of(own, g)] for g in geoids if unit_of(own, g) in index}
    lens["labels"] = held_units(geoids, weights, units)
    return lens


def oldest_old_index(counts: dict) -> float:
    """Residents aged 85 and over ÷ those aged 65 and over, of a place's census counts by age."""
    return ages_from(counts, OLDEST_FROM) / ages_from(counts, OLD_FROM)


def census_is_provisional(payload: dict) -> bool:
    """Whether INE still calls the census by age provisional (IneCensoEdad's vintage says so)."""
    return "(provisional)" in payload["vintage"]


def census_totals(ages: dict, geoids: list[str], start: int, weights: list) -> list:
    """(residents aged `start` and over, residents) on each hex, pooling its municipalities by their census
    residents."""
    munis = ages["municipalities"]
    totals = [munis.get(g, {}).get("total") for g in geoids]
    return hex_totals({g: ages_from(m, start) for g, m in munis.items()}, geoids, totals, weights)


def oldest_old_values(oldest: list, old: list, prior: float, spain: float) -> list:
    """Each hex's 85+ ÷ 65+ drawn towards Spain's index: (85+ + prior × Spain) ÷ (65+ + prior), at the precision the
    map shows; null where the hex has no residents aged 65 and over. `oldest` and `old` are census_totals of 85 and
    65 over the same residents, so their first terms are the counts."""
    return [None if o is None or not w or not w[0] else round((o[0] + prior * spain) / (w[0] + prior),
                                                                  DIGITS["oldest_old"])
            for o, w in zip(oldest, old)]


def weighted_percentile(pairs: list[tuple[float, float]], p: float) -> float:
    """The smallest value at or below which a share `p` of the total weight lies."""
    if not pairs:
        raise ValueError("a weighted percentile of no values")
    pairs = sorted(pairs)
    total, acc = sum(w for _, w in pairs), 0.0
    for v, w in pairs:
        acc += w
        if acc >= p * total:
            return v
    return pairs[-1][0]


def zone_counts(measures: list[list], residents: list[float]) -> tuple[list[float], list]:
    """(thresholds, per hex how many measures are at or above theirs, null where any is null): each threshold is the
    population-weighted ZONE_PERCENTILE of the hexes with every measure, taken from the values as they are stored."""
    known = [i for i, vs in enumerate(zip(*measures)) if all(v is not None for v in vs)]
    if not known:
        raise RuntimeError("longevity zones: no hex has all three measures")
    cuts = [weighted_percentile([(m[i], residents[i]) for i in known], ZONE_PERCENTILE) for m in measures]
    counts = [None] * len(residents)
    for i in known:
        counts[i] = sum(m[i] >= c for m, c in zip(measures, cuts))
    return cuts, counts


def zones(counts: list, grid: HexGrid, weights: list, geoids: list[str], munis: dict[str, str],
          residents: list[float]) -> list[dict]:
    """The longevity zones: the touching hexes with all three measures, each {name (the municipality with most of
    its residents), cells, residents}, the largest first."""
    out = []
    for cells in components([i for i, n in enumerate(counts) if n == len(ZONE_MEASURES)], grid.neighbours):
        held: Counter = Counter()
        for c in cells:
            for k, w in weights[c]:
                held[geoids[k]] += w
        top = max(held, key=lambda g: (held[g], g))
        out.append({"name": munis.get(top, top), "cells": cells, "residents": round(sum(residents[c] for c in cells))})
    return sorted(out, key=lambda z: (-len(z["cells"]), -z["residents"], z["name"]))


def hexes(n: int) -> Text:
    """'1 hexágono', '12 hexágonos' / '1 hex', '12 hexes'."""
    return tr("1 hexágono", "1 hex") if n == 1 else tr("{n} hexágonos", "{n} hexes").format(n=n)


def zone_label(z: dict) -> Text:
    return tr("Zona de {name}: {hexes}, {pop} residentes", "{name} zone: {hexes}, {pop} residents").format(
        name=z["name"], hexes=hexes(len(z["cells"])), pop=z["residents"])


def by_residents(found: list[dict]) -> list[int]:
    """The zones' indices, the most residents first."""
    return sorted(range(len(found)), key=lambda k: (-found[k]["residents"], k))


def zones_lens(measures: dict[str, list], residents: list, density: list, old_share: list, owner: list[int],
               grid: HexGrid, weights: list, geoids: list[str], munis: dict[str, str], at65_year: int,
               census_year: int, n_listed: int) -> dict:
    cuts, counts = zone_counts([measures[k] for k in ZONE_MEASURES], residents)
    found = zones(counts, grid, weights, geoids, munis, residents)
    if not found:
        raise RuntimeError(f"longevity zones: no hex meets all three thresholds {cuts}")
    land = [i for i, o in enumerate(owner) if o >= 0 and counts[i] is not None]
    in_zone = [c for z in found for c in z["cells"]]
    sparse = lambda cells: sum(density[c] is not None and density[c] < SPARSE for c in cells) / len(cells)
    olds = sorted(old_share[i] for i in land if old_share[i] is not None)
    if not olds:
        raise RuntimeError("longevity zones: no land hex has a share of residents over 65")
    old_cut = olds[int(0.75 * (len(olds) - 1))]
    old_top = sum(old_share[c] is not None and old_share[c] >= old_cut for c in in_zone) / len(in_zone)
    labels: list = [None] * len(owner)
    for i, z in enumerate(found):
        for c in z["cells"]:
            labels[c] = [i]
    pop = sum(z["residents"] for z in found)
    most = by_residents(found)
    top2 = [found[k] for k in most[:2]]
    named = lambda zs, n: and_list([tr("{name} ({n})", "{name} ({n})").format(name=z["name"], n=n(z)) for z in zs])
    return {
        "id": "longevity_zones", "group": "longevity", "name": tr("Zonas de longevidad", "Longevity zones"),
        "icon": "l-longevity", "emoji": "🌿",
        "unit": tr("medidas de longevidad altas", "high longevity measures"), "format": "category", "scale": "linear",
        "higher_is": "neutral", "source": "ine_censo_edad", "also_sources": ["ine_esperanza_vida"],
        "categories": [{"id": k, "name": n, "color": c} for k, n, c in ZONE_CATEGORIES],
        "ramp": [c for _, _, c in ZONE_CATEGORIES], "domain": [0, len(ZONE_CATEGORIES) - 1],
        "note": tr("Índice propio de este mapa, no una estadística oficial. Por hexágonos es sobre todo la España rural "
                   "y envejecida; por residentes, {a} y {b}.",
                   "This map's own index, not an official statistic. By hexes it is mostly rural, ageing Spain; by "
                   "residents, {a} and {b}.").format(a=top2[0]["name"], b=top2[-1]["name"]),
        "description": tr(
            "Cuántas de tres medidas tiene un hexágono en lo alto: sobreenvejecimiento (85+ ÷ 65+) de {o} o más, "
            "centenarios de {c} por 10.000 o más y esperanza de vida a los 65 de {e} años o más, cada una con el "
            "decimal que muestra su lente. Cada umbral es el percentil 75 ponderado por población de los hexágonos de "
            "tierra: el valor por debajo del cual vive el 75 % de los residentes. Los hexágonos con las tres que se "
            "tocan forman una zona, con el nombre del municipio que más residentes tiene en ella: {zones} zonas, "
            "{cells} hexágonos y {pop} residentes. Las de más hexágonos son {largest}; las de más residentes, "
            "{populous}, y las dos primeras reúnen el {top2} de los residentes de las zonas. En hexágonos es sobre "
            "todo la España despoblada: el {sparse_z} de los de las zonas tiene menos de 12,5 habitantes por km² (el "
            "umbral de zona escasamente poblada de las Directrices de ayudas regionales de la UE, 2021/C 153/01), "
            "frente al {sparse_all} de los de tierra, y el {old_top} está en el cuarto de hexágonos con más "
            "proporción de mayores de 65. Fuera de los {n} municipios con esperanza de vida propia, la de los 65 es la "
            "de la provincia, así que donde decide ella el borde de una zona sigue la frontera provincial. {point} "
            "para ver el nombre de su zona. Censo anual de población de {census} y esperanza de vida de {year}.",
            "How many of three measures a hex has at the top: oldest old (85+ ÷ 65+) of {o} or more, centenarians of "
            "{c} per 10,000 or more and life expectancy at 65 of {e} years or more, each to the decimal its lens "
            "shows. Each threshold is the population-weighted 75th percentile of land hexes: the value three in four "
            "residents live at or below. Touching hexes with all three make a zone, named after the municipality "
            "with most of its residents: {zones} zones, {cells} hexes and {pop} residents. The zones with most hexes "
            "are {largest}; those with most residents, {populous}, and the first two hold {top2} of the zones' "
            "residents. By hexes it is mostly depopulated Spain: {sparse_z} of the zones' hexes have fewer than 12.5 "
            "inhabitants per km² (the sparsely populated cut-off of the EU Guidelines on regional State aid, 2021/C "
            "153/01), against {sparse_all} of land hexes, and {old_top} are in the quarter of hexes with the largest "
            "share of people over 65. Outside the {n} municipalities with a life expectancy of their own, the one at "
            "65 is the province's, so where it decides, a zone's edge follows the province border. {point} to see "
            "its zone's name. Annual Population Census of {census} and life expectancy of {year}.",
        ).format(o=share_text(cuts[0], 1), c=Num(cuts[1], 1), e=Num(cuts[2], 1),
                 zones=len(found), cells=len(in_zone), pop=pop,
                 largest=named(found[:ZONES_LISTED], lambda z: hexes(len(z["cells"]))),
                 populous=named([found[k] for k in most[:ZONES_LISTED]], lambda z: z["residents"]),
                 top2=share_text(sum(z["residents"] for z in top2) / pop, 0),
                 sparse_z=share_text(sparse(in_zone), 0), sparse_all=share_text(sparse(land), 0),
                 old_top=share_text(old_top, 0), n=n_listed, point=POINT, census=str(census_year),
                 year=str(at65_year)),
        "values": counts, "names": [zone_label(z) for z in found], "labels": labels, "touch_details": True,
        "fly_to": most[:ZONES_LISTED],
        "thresholds": dict(zip(ZONE_MEASURES, cuts)),
    }


def centenarian_line(name: str, counts: dict) -> Text | str:
    """A municipality with centenarians in the tooltip: its count, and its own rate from RATE_MIN residents up (in a
    village of 20 one centenarian is 500 per 10,000, which says nothing)."""
    if counts["total"] < RATE_MIN:
        return f"{name}: {counts['100']}"
    return tr("{name}: {n} ({rate} por 10.000)", "{name}: {n} ({rate} per 10,000)").format(
        name=name, n=counts["100"], rate=Num(counts["100"] * PER / counts["total"], 1))


def lenses(world: dict, weights: list, grid: HexGrid, density: list, munis: dict[str, str]) -> list[dict]:
    """The five lenses of the group, in the order the lens list shows them. `munis` names municipalities by code."""
    geoids, owner = world["counties"], world["owner"]
    ages_payload = load_interim_payload("ine_censo_edad")
    ages = ages_payload["data"]
    life = load_interim("ine_esperanza_vida")
    year = ages["year"]
    when = tr("1 de enero de {year}", "1 January {year}").format(year=str(year)) + (
        tr(", provisional", ", provisional") if census_is_provisional(ages_payload) else "")
    nation = ages["nation"]
    old, oldest, cent = (census_totals(ages, geoids, a, weights) for a in (OLD_FROM, OLDEST_FROM, CENTENARIAN_FROM))
    residents = [sum(w for _, w in parts) for parts in weights]
    spain_rate = nation["100"] / nation["total"]
    spain_index = oldest_old_index(nation)
    oldest_old = oldest_old_values(oldest, old, OLDEST_PRIOR, spain_index)
    centenarians = [None if r is None else round(r * PER, DIGITS["centenarians"])
                    for r in shrunk_rate(cent, CENTENARIAN_PRIOR, spain_rate)]
    old_share = [None if t is None or not t[1] else t[0] / t[1] for t in old]

    counts = ages["municipalities"]
    with_cent = sorted(g for g, m in counts.items() if m.get("100"))
    index = {g: i for i, g in enumerate(with_cent)}
    at65 = life_lens("65", life, geoids, weights, munis)
    measures = {"oldest_old": oldest_old, "centenarians": centenarians, "life_expectancy_65": at65["values"]}
    return [
        life_lens("birth", life, geoids, weights, munis),
        {"id": "oldest_old", "group": "longevity", "name": tr("Sobreenvejecimiento", "Oldest old"),
         "icon": "l-oldest-old", "emoji": "👵", "unit": tr("de 85 años o más entre los de 65 o más",
                                                           "aged 85 and over among those 65 and over"),
         "format": "pct", "decimals": 1, "scale": "linear", "higher_is": "neutral",
         "ramp": ["#1c1a2e", "#3a3266", "#6a4c93", "#a5668b", "#dd8d6c", "#f7d08a"], "source": "ine_censo_edad",
         "note": tr("Cuenta dónde vive la gente: una residencia de mayores sube la de su municipio. La despoblación la "
                    "mueve menos que la proporción de mayores de 65.",
                    "It counts where people live: a care home raises its municipality's. Depopulation moves it less "
                    "than the share of people over 65."),
         "description": tr(
             "Índice de sobreenvejecimiento: residentes de 85 años o más por cada 100 de 65 o más (Censo anual de "
             "población del INE, {when}; en España, {spain}, {o85} de {o65}). Algunas fuentes lo calculan con los de 80 "
             "o más. Mide cuánto viven los que llegan a mayores, no cuántos mayores hay: un pueblo que pierde jóvenes "
             "sube en proporción de mayores, no en este índice. Un hexágono suma los mayores de sus municipios, cada "
             "uno por la parte de sus residentes que cae en él, y luego se acerca al índice de España como si tuviera "
             "{prior} residentes más de 65 o más con ese índice: (85+ + {prior} × España) ÷ (65+ + {prior}). Así un "
             "pueblo de 50 vecinos no sale el primero por diez mayores de 85. El INE publica todos los municipios, sin "
             "casillas ocultas.",
             "Oldest-old index: residents aged 85 and over per 100 aged 65 and over (INE Annual Population Census, "
             "{when}; Spain: {spain}, {o85} of {o65}). Some sources use 80 and over. It measures how long those who "
             "reach old age live, not how many old people there are: a village that loses its young rises in the "
             "share over 65, not in this index. A hex adds up the old residents of its municipalities, each by the "
             "share of its residents in the hex, then moves towards Spain's index as if it had {prior} more residents "
             "aged 65 and over at that index: (85+ + {prior} × Spain) ÷ (65+ + {prior}). That way a village of 50 "
             "does not come first for ten people over 85. INE publishes every municipality, with no cell hidden.",
         ).format(when=when, spain=share_text(spain_index, 1), o85=ages_from(nation, OLDEST_FROM),
                  o65=ages_from(nation, OLD_FROM), prior=OLDEST_PRIOR),
         "values": oldest_old},
        {"id": "centenarians", "group": "longevity", "name": tr("Centenarios", "Centenarians"),
         "icon": "l-centenarians", "emoji": "💯", "unit": tr("por 10.000 habitantes", "per 10,000 inhabitants"),
         "format": "float", "decimals": DIGITS["centenarians"], "scale": "linear", "higher_is": "neutral",
         "national": round(spain_rate * PER, 2), "touch_details": True,
         "ramp": ["#14202a", "#1f4157", "#2f6f7d", "#58a08a", "#a8cf8e", "#f4f1a8"], "source": "ine_censo_edad",
         "note": tr("Son pocos: cada hexágono cuenta con {prior} residentes más a la tasa de España para que una aldea "
                    "con un centenario no pase por la primera.",
                    "They are few: each hex counts {prior} more residents at Spain's rate so a hamlet with one "
                    "centenarian does not come first.").format(prior=CENTENARIAN_PRIOR),
         "description": tr(
             "Residentes de 100 años o más por cada 10.000 (Censo anual de población del INE, {when}; en España, "
             "{spain}, {n} centenarios de {total} residentes). Un hexágono suma los centenarios y los residentes de sus "
             "municipios, cada uno por la parte de sus residentes que cae en él, y luego se acerca a la tasa de España "
             "como si tuviera {prior} residentes más a esa tasa: (centenarios + {prior} × España) ÷ (residentes + "
             "{prior}) × 10.000, con España = {n} ÷ {total}. {point} para ver cada municipio con centenarios y su "
             "cuenta entera, y la tasa sin suavizar de los de {min} residentes o más: un municipio grande repite su "
             "cuenta en cada uno de sus hexágonos.",
             "Residents aged 100 and over per 10,000 (INE Annual Population Census, {when}; Spain: {spain}, {n} "
             "centenarians of {total} residents). A hex adds up the centenarians and residents of its "
             "municipalities, each by the share of its residents in the hex, then moves towards Spain's rate as if it "
             "had {prior} more residents at that rate: (centenarians + {prior} × Spain) ÷ (residents + {prior}) × "
             "10,000, with Spain = {n} ÷ {total}. {point} to see each municipality with centenarians and its whole "
             "count, and the unsmoothed rate of those with {min} residents or more: a large municipality repeats its "
             "count in each of its hexes.",
         ).format(when=when, spain=Num(spain_rate * PER, 2), n=nation["100"], total=nation["total"],
                  prior=CENTENARIAN_PRIOR, point=POINT, min=RATE_MIN),
         "values": centenarians, "names": [centenarian_line(munis.get(g, g), counts[g]) for g in with_cent],
         "labels": held_units(geoids, weights, index)},
        at65,
        zones_lens(measures, residents, density, old_share, owner, grid, weights, geoids, munis, life["at65"]["year"],
                   year, len(life["at65"]["municipalities"])),
    ]


def check(web_dir) -> list[tuple[str, str]]:
    """The longevity zones agree with the three lenses they come from: every hex's count is how many of its values
    are at or above the thresholds the lens states, a hex is in a zone exactly when it has all three, and there is a
    zone. Nothing to check on a map without the lens."""
    doc = json.loads((Path(web_dir) / "lenses.json").read_text())["lenses"]
    by_id = {l["id"]: l for l in doc}
    lens = by_id.get("longevity_zones")
    if lens is None:
        return []
    cuts = lens["thresholds"]
    bad = []
    for c, n in enumerate(lens["values"]):
        vals = [by_id[k]["values"][c] for k in ZONE_MEASURES]
        expected = None if any(v is None for v in vals) else sum(v >= cuts[k] for v, k in zip(vals, ZONE_MEASURES))
        if n != expected or bool(lens["labels"][c]) != (n == len(ZONE_MEASURES)):
            bad.append(c)
    if not lens["names"] or bad:
        return [("FAIL", f"longevity_zones: {len(lens['names'])} zones, {len(bad)} hexes whose count or zone does not "
                         f"match the thresholds {cuts} ({bad[:5]})")]
    cells = sum(bool(x) for x in lens["labels"])
    return [("PASS", f"longevity_zones: {len(lens['names'])} zones, {cells} hexes, every count matches {cuts}")]
