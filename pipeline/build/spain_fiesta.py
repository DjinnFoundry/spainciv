"""Spain's festive lenses: tourist dwellings, Fiestas de Interés Turístico, bars per inhabitant, this map's party
index, castles and bullrings.

* **Per inhabitant** (tourist dwellings, bars): a municipality's count ÷ its Padrón residents, × 1,000; a hex takes
  the population-weighted mean of its municipalities (the weights that spread the density lens), which is the hex's
  share of their counts ÷ its residents.
* **Fiestas**: the State's Internacional and Nacional and each community's own (autonómica) go to the hex of the
  capital of each municipality the official list places them in (data tables in pipeline/sources/es/data:
  fiestas_interes_turistico.csv and fiestas_autonomicas.csv), named in the tooltip. A community's fiesta the State has
  since declared counts once, at the State's category; one with no municipality in its source (declared for a whole
  community, or held in a different village each year) is in the calendar but on no hex. `fiestas.json` lists them
  all with their dates, where the source gives them; the State gives none, so a State's fiesta has those of its
  community's entry for it, when there is one.
* **Bars** (OpenStreetMap amenity=bar and pub) are counted in the municipality whose SIANE outline holds them; one
  outside every outline (the 1:3M coast is simplified) goes to the municipality with the nearest capital.
* **Party index**: how many times Spain's usual a hex is, as the geometric mean of three factors: its bars and its
  tourist dwellings per inhabitant, each ÷ Spain's rate, and 1 + its fiesta points (Internacional 2, Nacional 1,
  autonómica 0.5). The two rates are first drawn towards Spain's as if the hex had `PARTY_PRIOR` more residents at
  that rate, so a hamlet with one bar does not outshine Benidorm. 1 is Spain's usual; the lens leaves everything up to
  it dark. It is this map's own index, not an official statistic.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from ..core.geo import Shape, ShapeIndex
from ..core.hexgrid import HexGrid
from ..core.lang import tr
from ..core.store import load_interim, load_interim_payload
from ..sources.es.fiestas import split_year
from .cities import nearest_land
from .spain_named import named_counts, shore_cell

FIESTA_REQUIRES = ["fiestas_interes_turistico", "fiestas_autonomicas", "ine_viviendas_turisticas", "osm_bares"]
FIESTA_FILE = "fiestas"  # the calendar: every fiesta with its dates (fiestas.json)
PER = 1000  # per 1,000 inhabitants
CATEGORY = {"internacional": tr("Internacional", "International"), "nacional": tr("Nacional", "National"),
            "autonomica": tr("Autonómica", "Regional")}
# Points in the party index: each step down the ladder halves, so a community's fiesta adds half a Nacional (E78).
FIESTA_WEIGHT = {"internacional": 2, "nacional": 1, "autonomica": 0.5}
PARTY_PRIOR = 1000  # residents: the weight of Spain's rate in a hex's bars and tourist dwellings for the party index


def municipality_cells(grid: HexGrid, owner: list[int], proj, municipalities: list[dict]) -> dict[str, int]:
    """INE code → the land hex of the municipality's capital (SIANE), or the nearest land hex to a capital on a sea
    hex (a small coastal town)."""
    out = {}
    for m in municipalities:
        x, y = proj(*m["centre"])
        cell = grid.cell_at(x, y)
        out[m["geoid"]] = cell if cell >= 0 and owner[cell] >= 0 else nearest_land(grid, owner, max(cell, 0), x, y, -1)
    return out


def locate(points: list[list[float]], municipalities: list[dict], proj) -> tuple[list[str], int]:
    """The INE code of the municipality holding each lon/lat point, and how many fell outside every outline (those go
    to the municipality whose capital is nearest)."""
    shapes = [Shape([[proj(lon, lat) for lon, lat in ring] for ring in m["rings"]]) for m in municipalities]
    index = ShapeIndex(shapes, cell_km=20)
    centres = [proj(*m["centre"]) for m in municipalities]
    codes, outside = [], 0
    for lon, lat in points:
        x, y = proj(lon, lat)
        k = index.locate(x, y)
        if k < 0:
            outside += 1
            k = min(range(len(centres)), key=lambda j: math.dist(centres[j], (x, y)))
        codes.append(municipalities[k]["geoid"])
    return codes, outside


def hex_totals(counts: dict[str, float | None], geoids: list[str], pops: list, weights: list) -> list:
    """(count, residents) on each hex: its share of each municipality's count, by the residents it holds of it; null
    where none of its municipalities has both a count and residents."""
    share = [counts.get(g) / p if counts.get(g) is not None and p else None for g, p in zip(geoids, pops)]
    out = []
    for parts in weights:
        held = [(share[k], w) for k, w in parts if share[k] is not None and w > 0]
        out.append((sum(s * w for s, w in held), sum(w for _, w in held)) if held else None)
    return out


def per_inhabitant(totals: list) -> list:
    """Per 1,000 inhabitants on each hex (the population-weighted mean of its municipalities' rates)."""
    return [None if t is None else round(t[0] * PER / t[1], 1) for t in totals]


def times_spain(totals: list, prior: float) -> list:
    """Each hex's rate ÷ Spain's, the hex's count and residents first topped up with `prior` residents at Spain's
    rate: (count + prior × Spain) ÷ (residents + prior) ÷ Spain."""
    known = [t for t in totals if t is not None]
    spain = sum(c for c, _ in known) / sum(r for _, r in known)
    return [None if t is None else (t[0] + prior * spain) / (t[1] + prior) / spain for t in totals]


def party_index(factors: list[list]) -> list:
    """The geometric mean of the factors, per hex, to two decimals; null where any factor is null."""
    return [None if any(f is None for f in fs) else round(math.prod(fs) ** (1 / len(fs)), 2) for fs in zip(*factors)]


def twin_dates(twins: list[dict]) -> dict:
    """The dates of a State's fiesta: the State publishes none, so they are those of its community's entries for the
    same fiesta (`state_same`), each text as its source writes it (distinct texts joined by "; ") and the months they
    name; none without such an entry."""
    texts = list(dict.fromkeys(t["when"] for t in twins if t["when"]))
    return {"when": "; ".join(texts) or None, "months": sorted({m for t in twins for m in t["months"]})}


def all_fiestas(state: list[dict], regional: dict) -> list[dict]:
    """The State's fiestas and the communities' own, each once: a community's fiesta the State has since declared
    (`state_same`) is left to the State's entry, which takes its dates. A regional one carries its community's name
    for the declaration."""
    communities = regional["communities"]
    twins: dict[tuple, list[dict]] = {}
    for f in regional["fiestas"]:
        if f["state_same"]:
            twins.setdefault(split_year(f["state_same"]), []).append(f)
    keys = [(f["name"], f["year"]) for f in state]
    if unknown := sorted(set(twins) - set(keys), key=str):
        raise RuntimeError(f"state_same names no State fiesta: {unknown}")
    if len(set(keys)) != len(keys):
        raise RuntimeError("two State fiestas with the same name and year: their twins' dates would be ambiguous")
    return [{**f, "declaration": None, "place": None, **twin_dates(twins.get(k, []))}
            for f, k in zip(state, keys)] + [
        {**f, "category": "autonomica", "community": communities[f["community"]]["name"],
         "declaration": communities[f["community"]]["declaration"]}
        for f in regional["fiestas"] if not f["state_same"]]


def fiesta_label(f: dict):
    """'Semana Santa de Zamora (Internacional)'; a community's: 'Semana Santa (Autonómica · Fiesta de Interés
    Turístico de Castilla y León)', its declaration as the community names it."""
    declaration = f" · {f['declaration']}" if f["declaration"] else ""
    return CATEGORY[f["category"]].map(lambda c, _l: f"{f['name']} ({c}{declaration})")


def fiesta_cells(fiestas: list[dict], cell_of: dict[str, int]) -> list[list[int]]:
    """The hexes of each fiesta: its municipalities' capitals, each hex once (a valley's towns can share one); none for
    one with no municipality in its source."""
    return [sorted({cell_of[m] for m in f["municipalities"]}) for f in fiestas]


def fiestas_lens(fiestas: list[dict], cells: list[list[int]], owner: list[int]) -> dict:
    n = {c: sum(f["category"] == c for f in fiestas) for c in CATEGORY}
    unplaced = [f["name"] for f, c in zip(fiestas, cells) if not c]
    communities = len({f["community"] for f in fiestas if f["category"] == "autonomica"})
    unplaced_note = tr(" Sin municipio en su fuente (declaradas para toda una comunidad o celebradas cada año en un "
                       "lugar distinto), no van en ningún hexágono: {names}.",
                       " With no municipality in their source (declared for a whole community or held in a different "
                       "place each year), these are on no hex: {names}.").format(
        names=", ".join(f"«{name}»" for name in unplaced)) if unplaced else ""
    return {
        "id": "fiestas", "group": "food", "name": tr("Fiestas de interés turístico", "Fiestas of tourist interest"),
        "icon": "l-fiestas", "emoji": "🎉", "unit": tr("fiestas de interés turístico", "fiestas of tourist interest"),
        "format": "int", "scale": "linear", "higher_is": "neutral",
        "domain": [0, 4], "ramp": ["#2a0f24", "#5e1838", "#9b2442", "#d34a3a", "#f39a3c", "#ffe08a"],
        "source": "fiestas_interes_turistico",
        "description": tr(
            "Las {intl} Fiestas de Interés Turístico Internacional y las {nat} de Interés Turístico Nacional que declara "
            "la Secretaría de Estado de Turismo (Sanfermines, Fallas, la Tomatina, el Rocío, la Semana Santa de "
            "Sevilla…) y las {reg} que declaran de interés turístico {comm} comunidades autónomas, cada una con su "
            "nombre (Fiesta de Interés Turístico de Andalucía, Festa de Interese Turístico de Galicia…), cada fiesta "
            "en el hexágono de la capital de su municipio; una ruta o un valle, en los de todos sus municipios, una vez "
            "por hexágono. Una fiesta ascendida cuenta una vez, en su categoría más alta.{unplaced} Pasa el ratón por "
            "un hexágono para ver sus nombres.",
            "The {intl} Fiestas of International Tourist Interest and the {nat} of National Tourist Interest declared "
            "by the Secretaría de Estado de Turismo (Sanfermines, Fallas, the Tomatina, El Rocío, Holy Week in "
            "Seville…) and the {reg} that {comm} autonomous communities declare of regional tourist interest, each "
            "under its own name (Fiesta de Interés Turístico de Andalucía, Festa de Interese Turístico de Galicia…), "
            "each fiesta on the hex of its municipality's capital; a route or a valley, on those of all its "
            "municipalities, once per hex. A promoted fiesta counts once, at its highest category.{unplaced} Hover a "
            "hex to see their names.",
        ).format(intl=n["internacional"], nat=n["nacional"], reg=n["autonomica"], comm=communities,
                 unplaced=unplaced_note),
        **named_counts([fiesta_label(f) for f in fiestas], cells, owner),
    }


def fiesta_calendar(fiestas: list[dict], cells: list[list[int]], vintage: str) -> dict:
    """fiestas.json: every fiesta with its category, community, place, hexes and the dates its source gives (`when`,
    verbatim, and the months it names), so a calendar can find the fiestas of a week."""
    return {"vintage": vintage, "fiestas": [
        {"name": f["name"], "category": f["category"], "declaration": f["declaration"], "community": f["community"],
         "place": f["place"], "municipalities": f["municipalities"], "cells": c, "when": f["when"],
         "months": f["months"]} for f, c in zip(fiestas, cells)]}


def check(web_dir) -> list[tuple[str, str]]:
    """fiestas.json against the fiestas lens: one entry per name, in its order, each on the hexes that list it, every
    month 1–12. Nothing to check on a map without the lens."""
    web_dir = Path(web_dir)
    lens = next((l for l in json.loads((web_dir / "lenses.json").read_text())["lenses"] if l["id"] == "fiestas"), None)
    if lens is None:
        return []
    path = web_dir / f"{FIESTA_FILE}.json"
    if not path.exists():
        return [("FAIL", f"{FIESTA_FILE}.json: missing, and the fiestas lens names its fiestas")]
    items = json.loads(path.read_text())["fiestas"]
    held: dict[int, set[int]] = {}
    for c, labels in enumerate(lens["labels"]):
        for k in labels or []:
            held.setdefault(k, set()).add(c)
    bad = [f["name"] for k, f in enumerate(items) if set(f["cells"]) != held.get(k, set())
           or not all(1 <= m <= 12 for m in f["months"])]
    if len(items) != len(lens["names"]) or bad:
        return [("FAIL", f"{FIESTA_FILE}.json: {len(items)} fiestas for {len(lens['names'])} names in the lens; "
                         f"{len(bad)} off their hexes or months ({', '.join(bad[:5])})")]
    dated = sum(bool(f["when"]) for f in items)
    return [("PASS", f"{FIESTA_FILE}.json: {len(items)} fiestas matching the fiestas lens, {dated} with dates")]


def points_lens(items: list[dict], proj, grid: HexGrid, owner: list[int], **meta) -> dict:
    """A named count of Wikidata items at their positions."""
    return {**meta, "format": "int", "higher_is": "neutral", "source": "wikidata_es",
            **named_counts([i["label"] for i in items], [[shore_cell(grid, owner, *proj(*i["coord"]))] for i in items],
                           owner)}


def fiesta_lenses(world: dict, proj, grid: HexGrid, municipalities: list[dict], pops: list, weights: list,
                  padron_year: int) -> tuple[list[dict], dict]:
    """The lenses of this module, in the order the lens list shows them, and the fiesta calendar (fiestas.json)."""
    owner, geoids = world["owner"], world["counties"]
    state = load_interim_payload("fiestas_interes_turistico")
    regional = load_interim_payload("fiestas_autonomicas")
    fiestas = all_fiestas(state["data"]["fiestas"], regional["data"])
    homes = load_interim("ine_viviendas_turisticas")
    bars = load_interim("osm_bares")
    wikidata = load_interim("wikidata_es")

    home_totals = hex_totals({g: m.get("dwellings") for g, m in homes["municipalities"].items()}, geoids, pops,
                             weights)
    codes, outside = locate(bars["bars"], municipalities, proj)
    bar_count: dict[str, float] = {m["geoid"]: 0 for m in municipalities}
    for code in codes:
        bar_count[code] += 1
    bar_totals = hex_totals(bar_count, geoids, pops, weights)
    cells = fiesta_cells(fiestas, municipality_cells(grid, owner, proj, municipalities))
    points = [None if o < 0 else 0 for o in owner]  # fiesta points per hex
    for f, fc in zip(fiestas, cells):
        for c in fc:
            points[c] += FIESTA_WEIGHT[f["category"]]
    print(f"    {len(fiestas)} fiestas ({sum(f['category'] == 'autonomica' for f in fiestas)} autonómicas); "
          f"{len(codes)} bars ({outside} outside every municipal outline); tourist dwellings {homes['period']}")

    period = f"{homes['period'][5:]}/{homes['period'][:4]}"
    calendar = fiesta_calendar(fiestas, cells, f"{state['vintage']}; {regional['vintage']}")
    return [
        {"id": "tourist_homes", "group": "life", "name": tr("Viviendas turísticas", "Tourist dwellings"),
         "icon": "l-tourist-homes", "emoji": "🧳",
         "unit": tr("viviendas turísticas por 1.000 habitantes", "tourist dwellings per 1,000 inhabitants"),
         "format": "float", "scale": "log", "higher_is": "neutral",
         "ramp": ["#10223a", "#1d4a6b", "#2f7a8f", "#5fae9a", "#b5d98a", "#fff6b0"],
         "source": "ine_viviendas_turisticas",
         "description": tr(
             "Viviendas que se alquilan a turistas por cada 1.000 habitantes: las {n} que el INE encuentra anunciadas "
             "en las grandes plataformas y casa con el Catastro (estadística experimental, {period}), entre los "
             "residentes del Padrón ({year}). En un hexágono, la media de sus municipios ponderada por población.",
             "Dwellings let to tourists per 1,000 inhabitants: the {n} that INE finds advertised on the large "
             "platforms and matches to the Cadastre (experimental statistic, {period}), over the Padrón residents "
             "({year}). In a hex, the population-weighted mean of its municipalities.",
         ).format(n=homes["nation"]["dwellings"], period=period, year=str(padron_year)),
         "values": per_inhabitant(home_totals)},
        fiestas_lens(fiestas, cells, owner),
        {"id": "bars", "group": "food", "name": tr("Bares", "Bars"), "icon": "l-bars", "emoji": "🍺",
         "unit": tr("bares y pubs por 1.000 habitantes", "bars and pubs per 1,000 inhabitants"), "format": "float",
         "scale": "linear", "higher_is": "neutral",
         "ramp": ["#1f1406", "#4a2d0b", "#7c4a10", "#b37318", "#e0a83a", "#fff0b8"], "source": "osm_bares",
         "description": tr(
             "Bares y pubs de OpenStreetMap (amenity=bar y amenity=pub, {n} en España; sin cafeterías ni restaurantes) "
             "por cada 1.000 habitantes del Padrón, contados en su municipio. En un hexágono, la media de sus municipios "
             "ponderada por población. Lo mapean voluntarios y la cobertura es muy desigual: ciudades y costas "
             "turísticas están mucho mejor mapeadas que los pueblos, donde un cero puede ser un bar sin mapear.",
             "Bars and pubs in OpenStreetMap (amenity=bar and amenity=pub, {n} in Spain; no cafés or restaurants) per "
             "1,000 Padrón inhabitants, counted in their municipality. In a hex, the population-weighted mean of its "
             "municipalities. Volunteers map them and coverage is very uneven: cities and tourist coasts are far "
             "better mapped than villages, where a zero can be an unmapped bar.",
         ).format(n=len(codes)),
         "values": per_inhabitant(bar_totals)},
        {"id": "party", "group": "food", "name": tr("Índice de fiesta", "Party index"), "icon": "l-party", "emoji": "💃",
         "unit": tr("veces lo habitual en España", "times Spain's usual"), "format": "float", "scale": "log",
         "higher_is": "neutral", "domain": [1, 4], "ramp": ["#1a1030", "#47206a", "#8a2c8c", "#d0477a", "#f6894f", "#ffd86b"],
         "source": "fiestas_interes_turistico",
         "description": tr(
             "Índice propio de este mapa, no una estadística oficial: cuántas veces lo habitual en España tiene un "
             "hexágono de bares, de viviendas turísticas y de fiestas de interés turístico, como media geométrica de "
             "tres factores. Bares y viviendas turísticas: su número por habitante ÷ el de España, contando cada "
             "hexágono con {prior} residentes más a la tasa de España, para que una aldea con un bar no pase por "
             "Benidorm. Fiestas: 1 + sus puntos (Internacional 2, Nacional 1, autonómica 0,5). 1 es lo habitual; todo "
             "lo que no llega queda oscuro.",
             "This map's own index, not an official statistic: how many times Spain's usual a hex has in bars, tourist "
             "dwellings and fiestas of tourist interest, as the geometric mean of three factors. Bars and tourist "
             "dwellings: their number per inhabitant ÷ Spain's, counting each hex with {prior} more residents at "
             "Spain's rate, so a hamlet with one bar does not pass for Benidorm. Fiestas: 1 + their points "
             "(International 2, National 1, regional 0.5). 1 is the usual; everything up to it stays dark.",
         ).format(prior=PARTY_PRIOR),
         "values": party_index([times_spain(bar_totals, PARTY_PRIOR), times_spain(home_totals, PARTY_PRIOR),
                                [None if p is None else 1 + p for p in points]])},
        points_lens(wikidata["castles"], proj, grid, owner, id="castles", group="heritage",
                    name=tr("Castillos", "Castles"), icon="l-castles", emoji="🏰", unit=tr("castillos", "castles"),
                    scale="log", ramp=["#1b1a17", "#3d3a31", "#6b6250", "#a08f6c", "#d2c08f", "#f7efd0"],
                    description=tr(
                        "Los {n} castillos de España que Wikidata sitúa (con alcazabas, alcázares, casas torre y "
                        "castillos en ruinas; sin los derribados). Pasa el ratón por un hexágono para ver sus nombres. "
                        "Lo editan voluntarios: la cobertura no es la de un inventario oficial.",
                        "The {n} castles of Spain that Wikidata places (alcazabas, alcázares, tower houses and ruined "
                        "castles included; demolished ones left out). Hover a hex to see their names. Volunteer-edited: "
                        "the coverage is not that of an official inventory.",
                    ).format(n=len(wikidata["castles"]))),
        points_lens(wikidata["bullrings"], proj, grid, owner, id="bullrings", group="heritage",
                    name=tr("Plazas de toros", "Bullrings"), icon="l-bullrings", emoji="🐂",
                    unit=tr("plazas de toros", "bullrings"), scale="linear", domain=[0, 3],
                    ramp=["#1e0d0d", "#4a1414", "#7d1d1a", "#b3321f", "#dc6b2e", "#f6c35a"],
                    description=tr(
                        "Las {n} plazas de toros de España que Wikidata sitúa (de cualquier categoría; sin las "
                        "derribadas). Pasa el ratón por un hexágono para ver sus nombres. Lo editan voluntarios: la "
                        "cobertura no es la del registro oficial.",
                        "The {n} bullrings of Spain that Wikidata places (of any category; demolished ones left out). "
                        "Hover a hex to see their names. Volunteer-edited: the coverage is not that of the official "
                        "register.",
                    ).format(n=len(wikidata["bullrings"]))),
    ], calendar
