"""Spain's festive lenses: tourist dwellings, Fiestas de Interés Turístico, bars per inhabitant, this map's party
index, castles and bullrings.

* **Per inhabitant** (tourist dwellings, bars): a municipality's count ÷ its Padrón residents, × 1,000; a hex takes
  the population-weighted mean of its municipalities (the weights that spread the density lens), which is the hex's
  share of their counts ÷ its residents.
* **Fiestas** go to the hex of the capital of each municipality the official list places them in (data table in
  pipeline/sources/es/data/fiestas_interes_turistico.csv), named in the tooltip.
* **Bars** (OpenStreetMap amenity=bar and pub) are counted in the municipality whose SIANE outline holds them; one
  outside every outline (the 1:3M coast is simplified) goes to the municipality with the nearest capital.
* **Party index** (`PARTY_PARTS`): for each component, a hex's percentile = the share of land hexes with a value that
  have a strictly lower one (0 = the lowest, so the many hexes without a fiesta score 0 on it); the index is the mean
  of the three percentiles × 100. It is this map's own index, not an official statistic.
"""

from __future__ import annotations

import bisect
import math

from ..core.geo import Shape, ShapeIndex
from ..core.hexgrid import HexGrid
from ..core.store import load_interim
from .cities import nearest_land
from .spain_named import named_counts, shore_cell
from .texts_es import num

FIESTA_REQUIRES = ["fiestas_interes_turistico", "ine_viviendas_turisticas", "osm_bares"]
PER = 1000  # per 1,000 inhabitants
CATEGORY = {"internacional": "Internacional", "nacional": "Nacional"}
FIESTA_WEIGHT = {"internacional": 2, "nacional": 1}  # in the party index


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


def per_inhabitant(counts: dict[str, float | None], geoids: list[str], pops: list, weights: list) -> list:
    """Per 1,000 inhabitants on each hex: the population-weighted mean of its municipalities' rates (null where none
    of them has both a count and residents)."""
    rate = [counts.get(g) * PER / p if counts.get(g) is not None and p else None for g, p in zip(geoids, pops)]
    values = []
    for parts in weights:
        vals = [(rate[k], w) for k, w in parts if rate[k] is not None and w > 0]
        wsum = sum(w for _, w in vals)
        values.append(round(sum(v * w for v, w in vals) / wsum, 1) if wsum else None)
    return values


def percentiles(values: list) -> list:
    """Each value's share of the non-null values strictly below it (0 for the lowest); null stays null."""
    known = sorted(v for v in values if v is not None)
    n = len(known)
    return [None if v is None else bisect.bisect_left(known, v) / max(n - 1, 1) for v in values]


def party_index(parts: list[list]) -> list:
    """Mean percentile of the parts × 100, per hex; null where any part is null."""
    ranks = [percentiles(p) for p in parts]
    return [None if any(r is None for r in rs) else round(100 * sum(rs) / len(rs)) for rs in zip(*ranks)]


def fiesta_cells(fiestas: list[dict], cell_of: dict[str, int]) -> list[list[int]]:
    """The hexes of each fiesta: its municipalities' capitals, each hex once (a valley's towns can share one)."""
    return [sorted({cell_of[m] for m in f["municipalities"]}) for f in fiestas]


def fiestas_lens(fiestas: list[dict], cells: list[list[int]], owner: list[int]) -> dict:
    n = {c: sum(f["category"] == c for f in fiestas) for c in CATEGORY}
    return {
        "id": "fiestas", "group": "food", "name": "Fiestas de interés turístico", "icon": "l-fiestas", "emoji": "🎉",
        "unit": "fiestas de interés turístico", "format": "int", "scale": "linear", "higher_is": "neutral",
        "domain": [0, 3], "ramp": ["#2a0f24", "#5e1838", "#9b2442", "#d34a3a", "#f39a3c", "#ffe08a"],
        "source": "fiestas_interes_turistico",
        "description": f"Las {n['internacional']} Fiestas de Interés Turístico Internacional y las {n['nacional']} de "
        "Interés Turístico Nacional que declara la Secretaría de Estado de Turismo (Sanfermines, Fallas, la Tomatina, "
        "el Rocío, la Semana Santa de Sevilla…), cada una en el hexágono de la capital de su municipio; una ruta o un "
        "valle, en los de todos sus municipios, una vez por hexágono. Una fiesta ascendida a Internacional cuenta una "
        "vez. Pasa el ratón por un hexágono para ver sus nombres.",
        **named_counts([f"{f['name']} ({CATEGORY[f['category']]})" for f in fiestas], cells, owner),
    }


def points_lens(items: list[dict], proj, grid: HexGrid, owner: list[int], **meta) -> dict:
    """A named count of Wikidata items at their positions."""
    return {**meta, "format": "int", "higher_is": "neutral", "source": "wikidata_es",
            **named_counts([i["label"] for i in items], [[shore_cell(grid, owner, *proj(*i["coord"]))] for i in items],
                           owner)}


def fiesta_lenses(world: dict, proj, grid: HexGrid, municipalities: list[dict], pops: list, weights: list,
                  padron_year: int) -> list[dict]:
    """The lenses of this module, in the order the lens list shows them."""
    owner, geoids = world["owner"], world["counties"]
    fiestas = load_interim("fiestas_interes_turistico")["fiestas"]
    homes = load_interim("ine_viviendas_turisticas")
    bars = load_interim("osm_bares")
    wikidata = load_interim("wikidata_es")

    homes_rate = per_inhabitant({g: m.get("dwellings") for g, m in homes["municipalities"].items()}, geoids, pops,
                                weights)
    codes, outside = locate(bars["bars"], municipalities, proj)
    bar_count: dict[str, float] = {m["geoid"]: 0 for m in municipalities}
    for code in codes:
        bar_count[code] += 1
    bars_rate = per_inhabitant(bar_count, geoids, pops, weights)
    cells = fiesta_cells(fiestas, municipality_cells(grid, owner, proj, municipalities))
    points = [None if o < 0 else 0 for o in owner]
    for f, fc in zip(fiestas, cells):
        for c in fc:
            points[c] += FIESTA_WEIGHT[f["category"]]
    print(f"    {len(fiestas)} fiestas; {len(codes)} bars ({outside} outside every municipal outline); tourist "
          f"dwellings {homes['period']}")

    return [
        {"id": "tourist_homes", "group": "life", "name": "Viviendas turísticas", "icon": "l-tourist-homes",
         "emoji": "🧳", "unit": "viviendas turísticas por 1.000 habitantes", "format": "float", "scale": "log",
         "higher_is": "neutral", "ramp": ["#10223a", "#1d4a6b", "#2f7a8f", "#5fae9a", "#b5d98a", "#fff6b0"],
         "source": "ine_viviendas_turisticas",
         "description": "Viviendas que se alquilan a turistas por cada 1.000 habitantes: las "
         f"{num(homes['nation']['dwellings'])} que el INE encuentra anunciadas en las grandes plataformas y casa con el "
         f"Catastro (estadística experimental, {homes['period'][5:]}/{homes['period'][:4]}), entre los residentes del "
         f"Padrón ({padron_year}). En un hexágono, la media de sus municipios ponderada por población.",
         "values": homes_rate},
        fiestas_lens(fiestas, cells, owner),
        {"id": "bars", "group": "food", "name": "Bares", "icon": "l-bars", "emoji": "🍺",
         "unit": "bares y pubs por 1.000 habitantes", "format": "float", "scale": "linear", "higher_is": "neutral",
         "ramp": ["#1f1406", "#4a2d0b", "#7c4a10", "#b37318", "#e0a83a", "#fff0b8"], "source": "osm_bares",
         "description": f"Bares y pubs de OpenStreetMap (amenity=bar y amenity=pub, {num(len(codes))} en España; sin "
         "cafeterías ni restaurantes) por cada 1.000 habitantes del Padrón, contados en su municipio. En un hexágono, la "
         "media de sus municipios ponderada por población. Lo mapean voluntarios y la cobertura es muy desigual: "
         "ciudades y costas turísticas están mucho mejor mapeadas que los pueblos, donde un cero puede ser un bar sin "
         "mapear.",
         "values": bars_rate},
        {"id": "party", "group": "food", "name": "Índice de fiesta", "icon": "l-party", "emoji": "💃",
         "unit": "índice de este mapa (0–100)", "format": "int", "scale": "linear", "higher_is": "neutral",
         "domain": [0, 100], "ramp": ["#1a1030", "#47206a", "#8a2c8c", "#d0477a", "#f6894f", "#ffd86b"],
         "source": "fiestas_interes_turistico",
         "description": "Índice propio de este mapa, no una estadística oficial: la media de tres percentiles del "
         "hexágono × 100. Para cada parte, el percentil es la proporción de hexágonos con dato que tienen un valor "
         "estrictamente menor (0 el más bajo): fiestas de interés turístico (Internacional = 2 puntos, Nacional = 1), "
         "bares por 1.000 habitantes y viviendas turísticas por 1.000 habitantes. Índice = 100 × (P_fiestas + P_bares + "
         "P_viviendas) ÷ 3. Sin fiesta declarada, esa parte vale 0.",
         "values": party_index([points, bars_rate, homes_rate])},
        points_lens(wikidata["castles"], proj, grid, owner, id="castles", group="heritage", name="Castillos",
                    icon="l-castles", emoji="🏰", unit="castillos", scale="log",
                    ramp=["#1b1a17", "#3d3a31", "#6b6250", "#a08f6c", "#d2c08f", "#f7efd0"],
                    description=f"Los {num(len(wikidata['castles']))} castillos de España que Wikidata sitúa (con "
                    "alcazabas, alcázares, casas torre y castillos en ruinas; sin los derribados). Pasa el ratón por un "
                    "hexágono para ver sus nombres. Lo editan voluntarios: la cobertura no es la de un inventario "
                    "oficial."),
        points_lens(wikidata["bullrings"], proj, grid, owner, id="bullrings", group="heritage", name="Plazas de toros",
                    icon="l-bullrings", emoji="🐂", unit="plazas de toros", scale="linear", domain=[0, 3],
                    ramp=["#1e0d0d", "#4a1414", "#7d1d1a", "#b3321f", "#dc6b2e", "#f6c35a"],
                    description=f"Las {num(len(wikidata['bullrings']))} plazas de toros de España que Wikidata sitúa "
                    "(de cualquier categoría; sin las derribadas). Pasa el ratón por un hexágono para ver sus "
                    "nombres. Lo editan voluntarios: la cobertura no es la del registro oficial."),
    ]
