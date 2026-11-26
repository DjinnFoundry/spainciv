"""Spain's Knowledge, Daily life, Faith and Hazards lenses: the Spanish counterparts of the US map's Broadband,
Commute, Wellbeing, Faith and Disasters lenses, each from the official open figure that exists in Spain (DECISIONS).

* **Broadband** (id and look of the US lens): households a network can serve at 100 Mbps or more, by municipality
  (Ministerio para la Transformación Digital). Coverage, where the US lens counts subscriptions.
* **Commuting**: employed residents who work in another municipality (INE Annual Population Census). INE publishes
  where people work, not how long it takes them, so it is a share and not the US minutes: a lens of its own.
* **Life expectancy** at birth (INE), standing in for the US Wellbeing index (CDC health estimates).
* **Religious weddings**: share of marriages celebrated religiously (INE). Spain has no census of religion.
* **Wildfires**: burnt area of the last ten seasons (EFFIS), standing in for the FEMA disaster declarations.

INE publishes commuting, life expectancy and weddings for every province and for about 150 large municipalities.
Those municipalities carry their own figure; every other municipality takes the rest of its province (the province's
count minus its listed municipalities) where the figure is a count, and the province's own value where it is a rate
(life expectancy). Each lens is spread to hexes like the income lens: the population-weighted mean of the hex's
municipalities. Uninsured has no counterpart: public health care covers every resident (Real Decreto-ley 7/2018).

The builder is spain.py, which calls `lenses()`; SOURCES go into its REQUIRES.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from ..core.geo import ring_area, ring_centroid
from ..core.hexgrid import HexGrid
from ..core.store import load_interim
from .lenses import AMENITIES_RAMP, COUNTY_LENSES, DISASTERS_RAMP, FAITH_RAMP, _spread
from .texts_es import num, pct

SOURCES = [
    "cobertura_banda_ancha", "ine_censo_lugar_trabajo", "ine_esperanza_vida", "ine_matrimonios", "effis_incendios",
]
SPREAD = "Un hexágono muestra la media de sus municipios ponderada por población."


def listed(n: int) -> str:
    return (f"Los {n} municipios que el INE publica (capitales de provincia y ciudades principales) tienen su propio "
            "dato; los demás, el del resto de su provincia (la provincia menos esos municipios).")


def by_municipality(geoids: list[str], value) -> list:
    """value(code) of every municipality of the map, aligned with world["counties"]."""
    return [value(g) for g in geoids]


def listed_or_rest(data: dict, rate: Callable[[dict], float | None]) -> Callable[[str], float | None]:
    """A municipality's rate: its own counts if INE lists it, else the rest of its province's."""
    def value(code: str):
        counts = data["municipalities"].get(code) or data["rest_of_province"].get(code[:2])
        return rate(counts) if counts else None
    return value


def broadband_lens(data: dict, geoids: list[str], weights: list) -> dict:
    meta = COUNTY_LENSES["broadband"][1]
    return {
        "id": "broadband", **{k: meta[k] for k in ("group", "icon", "emoji", "format", "scale", "higher_is", "ramp")},
        "name": "Banda ancha", "unit": "hogares con cobertura de 100 Mbps o más", "source": "cobertura_banda_ancha",
        "description": "Proporción de los hogares de cada municipio a los que llega una red fija o inalámbrica fija de "
        "100 Mbps o más en condiciones de máxima demanda (informe de cobertura del Ministerio para la Transformación "
        f"Digital, junio de {data['year']}, con los datos de los operadores por parcela catastral; en España, "
        f"{pct(data['nation'], 1) if data.get('nation') is not None else 'sin dato'}). Es cobertura, no contratos: el "
        f"mapa de EE. UU. cuenta hogares abonados. {SPREAD}",
        "values": _spread(weights, by_municipality(geoids, data["municipalities"].get), 4),
    }


def works_elsewhere(counts: dict) -> float | None:
    """Employed who work in another municipality ÷ employed whose place of work is known."""
    away = sum(counts.get(k, 0) for k in ("province", "community", "other_community"))
    known = away + counts.get("same", 0)
    return away / known if known else None


def commuters_lens(data: dict, geoids: list[str], weights: list) -> dict:
    meta = COUNTY_LENSES["commute"][1]
    return {
        "id": "commuters", **{k: meta[k] for k in ("group", "icon", "emoji", "ramp")},
        "name": "Trabajan fuera", "unit": "ocupados que trabajan en otro municipio", "format": "pct", "scale": "linear",
        "higher_is": "neutral", "source": "ine_censo_lugar_trabajo",
        "description": "Proporción de los residentes ocupados que trabajan en un municipio distinto del suyo (de su "
        "provincia, de otra provincia de su comunidad o de otra comunidad), entre los que tienen lugar de trabajo "
        f"conocido (Censo anual de población del INE, 1 de enero de {data['year']}; en España, "
        f"{pct(works_elsewhere(data['nation']), 1)}). {listed(len(data['municipalities']))} El INE no publica el tiempo "
        f"de desplazamiento por municipio: es dónde se trabaja, no los minutos al trabajo del mapa de EE. UU. {SPREAD}",
        "values": _spread(weights, by_municipality(geoids, listed_or_rest(data, works_elsewhere)), 4),
    }


def life_expectancy_lens(data: dict, geoids: list[str], weights: list) -> dict:
    own, prov = data["municipalities"], data["provinces"]
    return {
        "id": "life_expectancy", "group": "life", "name": "Esperanza de vida", "icon": "l-amenities", "emoji": "❤️",
        "unit": "años al nacer", "format": "years", "scale": "linear", "higher_is": "good",
        "ramp": AMENITIES_RAMP, "source": "ine_esperanza_vida",
        "description": f"Esperanza de vida al nacer, ambos sexos, en {data['year']} (Indicadores Demográficos Básicos del "
        f"INE). Los {len(own)} municipios para los que el INE la calcula tienen la suya; los demás, la de su provincia, "
        "que incluye a esos municipios (una esperanza de vida no se puede restar). Ocupa el lugar del índice de "
        f"bienestar del mapa de EE. UU. (estimaciones de salud de los CDC). {SPREAD}",
        "values": _spread(weights, by_municipality(geoids, lambda g: own.get(g, prov.get(g[:2]))), 2),
    }


def religious_share(counts: dict) -> float | None:
    return counts.get("religious", 0) / counts["total"] if counts.get("total") else None


def weddings_lens(data: dict, geoids: list[str], weights: list) -> dict:
    return {
        "id": "religious_weddings", "group": "faith", "name": "Bodas religiosas", "icon": "l-faith", "emoji": "💒",
        "unit": "matrimonios religiosos, proporción del total", "format": "pct", "scale": "linear", "higher_is": "neutral",
        "ramp": FAITH_RAMP, "source": "ine_matrimonios",
        "note": "España no tiene censo de religión: esto mide cómo se casan, no lo que creen sus vecinos.",
        "description": f"Proporción de los matrimonios de {data['year']} celebrados por una confesión religiosa (el INE "
        "no separa la católica de las demás en estas tablas), por lugar de residencia de la pareja (Estadística de "
        f"Matrimonios del INE; en España, {pct(religious_share(data['nation']), 1)}). "
        f"{listed(len(data['municipalities']))} {SPREAD}",
        "values": _spread(weights, by_municipality(geoids, listed_or_rest(data, religious_share)), 4),
    }


def burnt_cells(fires: list[dict], proj, grid: HexGrid, step_km: float = 0.2) -> dict[int, float]:
    """Hectares burnt per grid cell: each fire's EFFIS area shared among the cells its perimeter covers (scanline
    samples every `step_km`, holes excluded by the even-odd rule), or put whole in the cell of its centroid when it is
    smaller than a sample. Cells may be off land; the caller keeps the land ones."""
    out: dict[int, float] = {}
    for fire in fires:
        rings = [[proj(lon, lat) for lon, lat in r] for r in fire["rings"]]
        rows: dict[int, list[float]] = {}
        for ring in rings:
            for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
                if y1 == y2:
                    continue
                lo, hi = sorted((y1, y2))
                for k in range(math.ceil(lo / step_km - 0.5), math.ceil(hi / step_km - 0.5)):
                    y = (k + 0.5) * step_km
                    rows.setdefault(k, []).append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
        hits: dict[int, int] = {}
        for k, xs in rows.items():
            y = (k + 0.5) * step_km
            xs.sort()
            for a, b in zip(xs[::2], xs[1::2]):
                for j in range(math.ceil(a / step_km - 0.5), math.ceil(b / step_km - 0.5)):
                    c = grid.cell_at((j + 0.5) * step_km, y)
                    if c >= 0:
                        hits[c] = hits.get(c, 0) + 1
        if not hits:
            c = grid.cell_at(*ring_centroid(max(rings, key=lambda r: abs(ring_area(r)))))
            hits = {c: 1} if c >= 0 else {}
        n = sum(hits.values())
        for c, h in hits.items():
            out[c] = out.get(c, 0.0) + fire["area_ha"] * h / n
    return out


def wildfires_lens(data: dict, proj, grid: HexGrid, owner: list[int]) -> dict:
    burnt = burnt_cells(data["fires"], proj, grid)
    first, last = data["years"]
    total = sum(f["area_ha"] for f in data["fires"])
    return {
        "id": "wildfires", "group": "hazards", "icon": "l-disasters", "emoji": "🔥", "ramp": DISASTERS_RAMP,
        "name": "Incendios", "unit": "hectáreas quemadas", "format": "int", "scale": "log", "higher_is": "bad",
        "source": "effis_incendios",
        "note": "Superficie que ardió, no daños: un monte que arde dos veces cuenta dos.",
        "description": f"Hectáreas quemadas en cada hexágono en los incendios de {first} a {last} que cartografió el "
        "Sistema Europeo de Información sobre Incendios Forestales (EFFIS, Copernicus) con imágenes de satélite: su "
        "perímetro, sea monte o cultivo, sumado año a año (en España, "
        f"{num(round(total))} ha en {len(data['fires'])} incendios). Recoge los de unas 30 ha o más (desde 2021, con "
        "Sentinel-2, también muchos menores); los más pequeños, que la estadística del ministerio (EGIF) sí cuenta, "
        "no salen. Ocupa el lugar de las declaraciones de catástrofe de la FEMA del mapa de EE. UU.",
        "values": [round(burnt.get(c, 0.0)) if o >= 0 else None for c, o in enumerate(owner)],
    }


def lenses(world: dict, weights: list, proj, grid: HexGrid) -> list[dict]:
    """The five lenses, in the order of the US groups (Knowledge, Daily life, Faith, Hazards)."""
    geoids = world["counties"]
    return [
        broadband_lens(load_interim("cobertura_banda_ancha"), geoids, weights),
        commuters_lens(load_interim("ine_censo_lugar_trabajo"), geoids, weights),
        life_expectancy_lens(load_interim("ine_esperanza_vida"), geoids, weights),
        weddings_lens(load_interim("ine_matrimonios"), geoids, weights),
        wildfires_lens(load_interim("effis_incendios"), proj, grid, world["owner"]),
    ]
