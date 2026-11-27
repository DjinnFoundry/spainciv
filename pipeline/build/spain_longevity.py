"""Spain's longevity lenses (group "longevity", DECISIONS E107–E108).

* **Life expectancy** at birth and **at 65** (INE Indicadores Demográficos Básicos, `life_lens`): the 155 municipalities
  INE computes it for carry their own figure, every other municipality its province's (a life expectancy cannot be
  subtracted, so there is no rest of the province); a hex takes the population-weighted mean of its municipalities.
  The lens at 65 lists, per hex, the units it takes them from, with both sexes, men and women.
* **Oldest old** (índice de sobreenvejecimiento): residents aged 85 and over ÷ those aged 65 and over (INE Annual
  Population Census by age). **Centenarians**: residents aged 100 and over per 10,000, drawn towards Spain's rate as if
  the hex had CENTENARIAN_PRIOR more residents at that rate. Both pool a hex's municipalities before dividing: each
  municipality adds its count × the share of its census residents the hex holds (`spain_fiesta.hex_totals`).
* **Longevity zones**: how many of those three a hex has at or above the population-weighted ZONE_PERCENTILE of land
  hexes (the value that three in four residents live at or below); hexes with all three that touch make a zone, named
  after its most populous municipality.

The builder is spain.py, which calls `lenses()`; SOURCES go into its REQUIRES.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from ..core.hexgrid import HexGrid
from ..core.lang import Num, Text, join_texts, tr
from ..core.store import load_interim, load_interim_payload
from ..sources.es.provinces import PROVINCES, display_name
from .lenses import AMENITIES_RAMP, _spread
from .spain_daily import SPREAD, by_municipality, share_text
from .spain_fiesta import hex_totals, shrunk_rate
from .unciv import components

SOURCES = ["ine_censo_edad", "ine_esperanza_vida"]
PER = 10_000  # centenarians per 10,000 residents
CENTENARIAN_PRIOR = 10_000  # residents at Spain's rate added to every hex: at that rate, about 3.7 centenarians
ZONE_PERCENTILE = 0.75  # a zone's hexes are at or above this population-weighted percentile in all three measures
SPARSE = 12.5  # inhabitants per km²: a sparsely populated NUTS 3 region in the EU's Guidelines on regional State aid
ZONES_LISTED = 8  # the largest zones the description names
OLD, OLDEST, CENTENARIAN = ("65", "70", "75", "80", "85", "90", "95", "100"), ("85", "90", "95", "100"), ("100",)
ZONE_MEASURES = ("oldest_old", "centenarians", "life_expectancy_65")
ZONE_CATEGORIES = [("none", tr("Ninguna", "None"), "#2b2433"), ("one", tr("Una", "One"), "#5b5a6e"),
                   ("two", tr("Dos", "Two"), "#8fae7a"), ("three", tr("Las tres: zona de longevidad", "All three: a "
                                                                   "longevity zone"), "#e8d56a")]


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
        "emoji": "❤️", "unit": tr("años al nacer", "years at birth"),
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
        "id": "life_expectancy_65", "name": tr("Esperanza de vida a los 65", "Life expectancy at 65"),
        "icon": "l-life-65", "emoji": "⌛", "unit": tr("años más a los 65", "more years at 65"),
        "description": tr(
            "Años que le quedan de media a quien cumple 65, ambos sexos, en {year} (Indicadores Demográficos Básicos "
            "del INE; en España, {spain}: {men} los hombres y {women} las mujeres). Los {n} municipios para los que el "
            "INE la calcula tienen la suya; los demás, la de su provincia, que incluye a esos municipios, así que fuera "
            "de ellos la lente sigue las fronteras provinciales. Pasa el ratón por un hexágono para ver de qué "
            "municipios o provincias sale, con hombres y mujeres. {spread}",
            "The years someone turning 65 has left on average, both sexes, in {year} (INE Basic Demographic "
            "Indicators; Spain: {spain}, {men} for men and {women} for women). The {n} municipalities INE calculates "
            "it for have their own; the others take their province's, which includes those municipalities, so outside "
            "them the lens follows province borders. Hover a hex to see the municipalities or provinces it comes "
            "from, with men and women. {spread}"),
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
        "values": _spread(weights, by_municipality(geoids, lambda g: value.get(unit_of(own, g))), 2),
    }
    if measure == "birth":
        return {**lens, "description": meta["description"].format(**fields)}
    spain = src["nation"]
    keys = [*sorted(own), *sorted(prov)]
    index = {k: i for i, k in enumerate(keys)}
    lens["description"] = meta["description"].format(
        **fields, spain=Num(spain["both"], 2), men=Num(spain["men"], 2), women=Num(spain["women"], 2))
    lens["names"] = [tr("{name}: {both} (hombres {men}, mujeres {women})", "{name}: {both} (men {men}, women {women})")
                     .format(name=unit_name(k, munis), **{s: Num(v, 2) for s, v in (own.get(k) or prov[k]).items()})
                     for k in keys]
    lens["labels"] = held_units(geoids, weights, {g: index[unit_of(own, g)] for g in geoids if unit_of(own, g) in index})
    return lens


def group_sum(counts: dict, groups: tuple[str, ...]) -> int:
    return sum(counts.get(g, 0) for g in groups)


def oldest_old_index(counts: dict) -> float:
    """Residents aged 85 and over ÷ those aged 65 and over, of a place's census counts by age."""
    return group_sum(counts, OLDEST) / group_sum(counts, OLD)


def census_totals(ages: dict, geoids: list[str], groups: tuple[str, ...], weights: list) -> list:
    """(residents of `groups`, residents) on each hex, pooling its municipalities by their census residents."""
    munis = ages["municipalities"]
    totals = [munis.get(g, {}).get("total") for g in geoids]
    return hex_totals({g: group_sum(m, groups) for g, m in munis.items()}, geoids, totals, weights)


def share(part: list, whole: list, digits: int = 4) -> list:
    """part ÷ whole per hex (two hex_totals over the same residents); null where the whole is null or zero."""
    return [None if w is None or not w[0] else round(p[0] / w[0], digits) for p, w in zip(part, whole)]


def weighted_percentile(pairs: list[tuple[float, float]], p: float) -> float:
    """The smallest value at or below which a share `p` of the total weight lies."""
    pairs = sorted(pairs)
    total, acc = sum(w for _, w in pairs), 0.0
    for v, w in pairs:
        acc += w
        if acc >= p * total:
            return v
    return pairs[-1][0]


def zone_counts(measures: list[list], residents: list[float]) -> tuple[list[float], list]:
    """(thresholds, per hex how many measures are at or above theirs, null where any is null): each threshold is the
    population-weighted ZONE_PERCENTILE of the hexes with every measure."""
    known = [i for i, vs in enumerate(zip(*measures)) if all(v is not None for v in vs)]
    cuts = [weighted_percentile([(m[i], residents[i]) for i in known], ZONE_PERCENTILE) for m in measures]
    counts = [None] * len(residents)
    for i in known:
        counts[i] = sum(m[i] >= c for m, c in zip(measures, cuts))
    return cuts, counts


def zones(counts: list, grid: HexGrid, weights: list, geoids: list[str], munis: dict[str, str],
          residents: list[float]) -> list[dict]:
    """The longevity zones: the touching hexes with all three measures, each {name (its most populous municipality),
    cells, residents}, the largest first."""
    out = []
    for cells in components([i for i, n in enumerate(counts) if n == len(ZONE_MEASURES)], grid.neighbours):
        held: Counter = Counter()
        for c in cells:
            for k, w in weights[c]:
                held[geoids[k]] += w
        top = max(held, key=lambda g: (held[g], g))
        out.append({"name": munis.get(top, top), "cells": cells, "residents": round(sum(residents[c] for c in cells))})
    return sorted(out, key=lambda z: (-len(z["cells"]), -z["residents"], z["name"]))


def zone_label(z: dict) -> Text:
    return tr("Zona de {name}: {n} hexágonos, {pop} residentes", "{name} zone: {n} hexes, {pop} residents").format(
        name=z["name"], n=len(z["cells"]), pop=z["residents"])


def zones_lens(measures: dict[str, list], residents: list, density: list, old_share: list, owner: list[int],
               grid: HexGrid, weights: list, geoids: list[str], munis: dict[str, str], at65_year: int,
               census_year: int, n_listed: int) -> dict:
    cuts, counts = zone_counts([measures[k] for k in ZONE_MEASURES], residents)
    found = zones(counts, grid, weights, geoids, munis, residents)
    land = [i for i, o in enumerate(owner) if o >= 0 and counts[i] is not None]
    in_zone = [c for z in found for c in z["cells"]]
    sparse = lambda cells: sum(density[c] is not None and density[c] < SPARSE for c in cells) / len(cells)
    old_cut = sorted(old_share[i] for i in land if old_share[i] is not None)[int(0.75 * (len(land) - 1))]
    old_top = sum(old_share[c] is not None and old_share[c] >= old_cut for c in in_zone) / len(in_zone)
    labels: list = [None] * len(owner)
    for i, z in enumerate(found):
        for c in z["cells"]:
            labels[c] = [i]
    largest = join_texts([tr("{name} ({n})", "{name} ({n})").format(name=z["name"], n=len(z["cells"]))
                          for z in found[:ZONES_LISTED]])
    return {
        "id": "longevity_zones", "group": "longevity", "name": tr("Zonas de longevidad", "Longevity zones"),
        "icon": "l-longevity", "emoji": "🌿",
        "unit": tr("medidas de longevidad altas", "high longevity measures"), "format": "category", "scale": "linear",
        "higher_is": "neutral", "source": "ine_censo_edad",
        "categories": [{"id": k, "name": n, "color": c} for k, n, c in ZONE_CATEGORIES],
        "ramp": [c for _, _, c in ZONE_CATEGORIES], "domain": [0, len(ZONE_CATEGORIES) - 1],
        "note": tr("Índice propio de este mapa, no una estadística oficial. Se apoya en la España rural y envejecida.",
                   "This map's own index, not an official statistic. It leans on rural, ageing Spain."),
        "description": tr(
            "Cuántas de tres medidas tiene un hexágono en lo alto: sobreenvejecimiento (85+ ÷ 65+) de {o}, "
            "centenarios de {c} por 10.000 y esperanza de vida a los 65 de {e} años o más. Cada umbral es el percentil "
            "75 ponderado por población de los hexágonos de tierra: el valor por debajo del cual vive el 75 % de los "
            "residentes. Los hexágonos con las tres que se tocan forman una zona, con el nombre de su municipio más "
            "poblado: {zones} zonas, {cells} hexágonos y {pop} residentes; las mayores, {largest}. Es sobre todo la "
            "meseta del Duero y Ourense, más la ciudad de Madrid. En parte es la España despoblada: el {sparse_z} de los "
            "hexágonos de las zonas tiene menos de 12,5 habitantes por km² (el umbral de zona escasamente poblada de "
            "las Directrices de ayudas regionales de la UE, 2021/C 153/01), frente al {sparse_all} de los de tierra, y "
            "el {old_top} está en el cuarto de hexágonos con más proporción de mayores de 65. Fuera de los {n} "
            "municipios con esperanza de vida propia, la de los 65 es la de la provincia, así que donde decide ella el "
            "borde de una zona sigue la frontera provincial. Censo anual de población de {census} y esperanza de vida "
            "de {year}.",
            "How many of three measures a hex has at the top: oldest old (85+ ÷ 65+) of {o}, centenarians of {c} per "
            "10,000 and life expectancy at 65 of {e} years or more. Each threshold is the population-weighted 75th "
            "percentile of land hexes: the value three in four residents live at or below. Touching hexes with all "
            "three make a zone, named after its most populous municipality: {zones} zones, {cells} hexes and {pop} "
            "residents; the largest, {largest}. They are mostly the Duero plateau and Ourense, plus the city of "
            "Madrid. In part this is depopulated Spain: {sparse_z} of the zones' hexes have fewer than 12.5 "
            "inhabitants per km² (the sparsely populated cut-off of the EU Guidelines on regional State aid, 2021/C "
            "153/01), against {sparse_all} of land hexes, and {old_top} are in the quarter of hexes with the largest "
            "share of people over 65. Outside the {n} municipalities with a life expectancy of their own, the one at "
            "65 is the province's, so where it decides, a zone's edge follows the province border. Annual Population "
            "Census of {census} and life expectancy of {year}.",
        ).format(o=share_text(cuts[0], 1), c=Num(cuts[1], 1), e=Num(cuts[2], 2),
                 zones=len(found), cells=len(in_zone), pop=sum(z["residents"] for z in found), largest=largest,
                 sparse_z=share_text(sparse(in_zone), 0),
                 sparse_all=share_text(sparse(land), 0),
                 old_top=share_text(old_top, 0), n=n_listed, census=str(census_year),
                 year=str(at65_year)),
        "values": counts, "names": [zone_label(z) for z in found], "labels": labels,
        "thresholds": dict(zip(ZONE_MEASURES, [round(c, 4) for c in cuts])),
    }


def lenses(world: dict, weights: list, grid: HexGrid, density: list, munis: dict[str, str]) -> list[dict]:
    """The five lenses of the group, in the order the lens list shows them. `munis` names municipalities by code."""
    geoids, owner = world["counties"], world["owner"]
    ages_payload = load_interim_payload("ine_censo_edad")
    ages = ages_payload["data"]
    life = load_interim("ine_esperanza_vida")
    year = ages["year"]
    when = tr("1 de enero de {year}", "1 January {year}").format(year=str(year)) + (
        tr(", provisional", ", provisional") if "(provisional)" in ages_payload["vintage"] else "")
    nation = ages["nation"]
    old, oldest, cent = (census_totals(ages, geoids, g, weights) for g in (OLD, OLDEST, CENTENARIAN))
    residents = [sum(w for _, w in parts) for parts in weights]
    spain_rate = nation["100"] / nation["total"]
    oldest_old = share(oldest, old)
    centenarians = [None if r is None else round(r * PER, 2) for r in shrunk_rate(cent, CENTENARIAN_PRIOR, spain_rate)]
    old_share = [None if t is None or not t[1] else t[0] / t[1] for t in old]

    counts = ages["municipalities"]
    with_cent = sorted(g for g, m in counts.items() if m.get("100"))
    index = {g: i for i, g in enumerate(with_cent)}
    cent_names = [tr("{name}: {n} ({rate} por 10.000)", "{name}: {n} ({rate} per 10,000)").format(
        name=munis.get(g, g), n=counts[g]["100"], rate=Num(counts[g]["100"] * PER / counts[g]["total"], 1))
        for g in with_cent]
    at65 = life_lens("65", life, geoids, weights, munis)
    measures = {"oldest_old": oldest_old, "centenarians": centenarians, "life_expectancy_65": at65["values"]}
    return [
        life_lens("birth", life, geoids, weights, munis),
        {"id": "oldest_old", "group": "longevity", "name": tr("Sobreenvejecimiento", "Oldest old"),
         "icon": "l-oldest-old", "emoji": "👵", "unit": tr("de 85 años o más entre los de 65 o más",
                                                           "aged 85 and over among those 65 and over"),
         "format": "pct", "scale": "linear", "higher_is": "neutral",
         "ramp": ["#1c1a2e", "#3a3266", "#6a4c93", "#a5668b", "#dd8d6c", "#f7d08a"], "source": "ine_censo_edad",
         "note": tr("Cuenta dónde vive la gente: una residencia de mayores sube la de su municipio. La despoblación la "
                    "mueve menos que la proporción de mayores de 65.",
                    "It counts where people live: a care home raises its municipality's. Depopulation moves it less "
                    "than the share of people over 65."),
         "description": tr(
             "Índice de sobreenvejecimiento: residentes de 85 años o más por cada 100 de 65 o más (Censo anual de "
             "población del INE, {when}; en España, {spain}, {o85} de {o65}). Algunas fuentes lo calculan con los de 80 "
             "o más. Mide cuánto viven los que llegan a mayores, no cuántos mayores hay: un pueblo que pierde jóvenes sube en proporción de mayores, no en este índice. Un hexágono suma "
             "los mayores de sus municipios, cada uno por la parte de sus residentes que cae en él, antes de dividir, "
             "así que un pueblo pequeño nunca cuenta solo. El INE publica todos los municipios, sin casillas ocultas.",
             "Oldest-old index: residents aged 85 and over per 100 aged 65 and over (INE Annual Population Census, "
             "{when}; Spain: {spain}, {o85} of {o65}). Some sources use 80 and over. It measures how long those who "
             "reach old age live, not how many old people there are: a village that loses its "
             "young rises in the share over 65, not in this index. A hex adds up the old residents of its "
             "municipalities, each by the share of its residents in the hex, before dividing, so a small village "
             "never counts alone. INE publishes every municipality, with no cell hidden.",
         ).format(when=when, spain=share_text(oldest_old_index(nation), 1),
                  o85=group_sum(nation, OLDEST), o65=group_sum(nation, OLD)),
         "values": oldest_old},
        {"id": "centenarians", "group": "longevity", "name": tr("Centenarios", "Centenarians"),
         "icon": "l-centenarians", "emoji": "💯", "unit": tr("por 10.000 habitantes", "per 10,000 inhabitants"),
         "format": "float", "scale": "linear", "higher_is": "neutral", "national": round(spain_rate * PER, 2),
         "ramp": ["#14202a", "#1f4157", "#2f6f7d", "#58a08a", "#a8cf8e", "#f4f1a8"], "source": "ine_censo_edad",
         "note": tr("Son pocos: cada hexágono cuenta con {prior} residentes más a la tasa de España para que una aldea "
                    "con un centenario no pase por la primera.",
                    "They are few: each hex counts {prior} more residents at Spain's rate so a hamlet with one "
                    "centenarian does not come first.").format(prior=CENTENARIAN_PRIOR),
         "description": tr(
             "Residentes de 100 años o más por cada 10.000 (Censo anual de población del INE, {when}; en España, "
             "{spain}, {n} centenarios). Un hexágono suma los centenarios y los residentes de sus municipios, cada uno por la parte de sus residentes que cae en él, y luego se acerca a la tasa de "
             "España como si tuviera {prior} residentes más a esa tasa: (centenarios + {prior} × España) ÷ "
             "(residentes + {prior}). Pasa el ratón por un hexágono para ver cada municipio con centenarios, con su "
             "cuenta entera y su tasa sin suavizar: un municipio grande repite su cuenta en cada uno de sus hexágonos.",
             "Residents aged 100 and over per 10,000 (INE Annual Population Census, {when}; Spain: {spain}, {n} "
             "centenarians). A hex adds up the centenarians and residents of its municipalities, each by the share of its residents in the hex, then moves towards Spain's rate as if it had {prior} "
             "more residents at that rate: (centenarians + {prior} × Spain) ÷ (residents + {prior}). Hover a hex to "
             "see each municipality with centenarians, with its whole count and its unsmoothed rate: a large "
             "municipality repeats its count in each of its hexes.",
         ).format(when=when, spain=Num(spain_rate * PER, 2), n=nation["100"], prior=CENTENARIAN_PRIOR),
         "values": centenarians, "names": cent_names,
         "labels": held_units(geoids, weights, index)},
        at65,
        zones_lens(measures, residents, density, old_share, owner, grid, weights, geoids, munis, life["at65"]["year"],
                   year, len(life["at65"]["municipalities"])),
    ]


def check(web_dir) -> list[tuple[str, str]]:
    """Every hex of a longevity zone meets the three thresholds the lens states, and there is a zone. Nothing to check
    on a map without the lens."""
    doc = json.loads((Path(web_dir) / "lenses.json").read_text())["lenses"]
    by_id = {l["id"]: l for l in doc}
    lens = by_id.get("longevity_zones")
    if lens is None:
        return []
    cuts = lens["thresholds"]
    cells = [c for c, labels in enumerate(lens["labels"]) if labels]
    bad = [c for c in cells if lens["values"][c] != len(ZONE_MEASURES)
           or any(by_id[k]["values"][c] is None or by_id[k]["values"][c] < cuts[k] - 1e-9 for k in ZONE_MEASURES)]
    if not lens["names"] or bad:
        return [("FAIL", f"longevity_zones: {len(lens['names'])} zones, {len(bad)} zone hexes under a threshold "
                         f"({bad[:5]})")]
    return [("PASS", f"longevity_zones: {len(lens['names'])} zones, {len(cells)} hexes, all over {cuts}")]
