"""Spain's Knowledge, Daily life, Faith and Hazards lenses: the Spanish counterparts of the US map's Broadband,
Commute, Faith and Disasters lenses, each from the official open figure that exists in Spain (DECISIONS).

* **Broadband** (id and look of the US lens): households a network can serve at 100 Mbps or more, by municipality
  (Ministerio para la Transformación Digital). Coverage, where the US lens counts subscriptions.
* **Commuting**: employed residents who work in another municipality (INE Annual Population Census). INE publishes
  where people work, not how long it takes them, so it is a share and not the US minutes: a lens of its own.
* **Religious weddings**: share of marriages celebrated religiously (INE). Spain has no census of religion.
* **Wildfires**: burnt area of the last ten seasons (EFFIS), standing in for the FEMA disaster declarations.

INE publishes commuting and weddings for every province and for about 150 large municipalities. Those municipalities
carry their own figure; every other municipality takes the rest of its province (the province's count minus its
listed municipalities). Life expectancy, which stands in for the US Wellbeing index, is in spain_longevity.py. Each lens is spread to hexes like the income lens: the population-weighted mean of the hex's
municipalities. Uninsured has no counterpart: public health care covers every resident (Real Decreto-ley 7/2018).

The builder is spain.py, which calls `lenses()`; SOURCES go into its REQUIRES.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from ..core.geo import ring_area, ring_centroid
from ..core.hexgrid import HexGrid
from ..core.lang import Text, pct, tr
from ..core.store import load_interim
from ..sources.es.ine_daily import province_of
from .lenses import COUNTY_LENSES, DISASTERS_RAMP, FAITH_RAMP, _spread

SOURCES = [
    "cobertura_banda_ancha", "ine_censo_lugar_trabajo", "ine_matrimonios", "effis_incendios",
]
SPREAD = tr("Un hexágono muestra la media de sus municipios ponderada por población.",
            "A hex shows the population-weighted mean of its municipalities.")


def share_text(x: float | None, decimals: int = 1) -> Text:
    """A share as a percentage in each language ("12,5 %", "12.5%"), or "no figure"."""
    if x is None:
        return tr("sin dato", "no figure")
    return tr(pct(x, decimals, "es"), pct(x, decimals, "en"))


def listed(n: int) -> Text:
    return tr("Los {n} municipios que el INE publica (capitales de provincia y ciudades principales) tienen su propio "
              "dato; los demás, el del resto de su provincia (la provincia menos esos municipios).",
              "The {n} municipalities INE publishes (provincial capitals and main cities) have their own figure; the "
              "others take the rest of their province's (the province minus those municipalities).").format(n=n)


def by_municipality(geoids: list[str], value) -> list:
    """value(code) of every municipality of the map, aligned with world["counties"]."""
    return [value(g) for g in geoids]


def listed_or_rest(data: dict, rate: Callable[[dict], float | None],
                   unit_of: Callable[[str], str] = province_of) -> Callable[[str], float | None]:
    """A municipality's rate: its own counts if its source lists it, else the rest of its province's (of its unit's,
    with `unit_of`, keyed so in data["rest_of_province"])."""
    def value(code: str):
        counts = data["municipalities"].get(code) or data["rest_of_province"].get(unit_of(code))
        return rate(counts) if counts else None
    return value


def broadband_lens(data: dict, geoids: list[str], weights: list) -> dict:
    meta = COUNTY_LENSES["broadband"][1]
    return {
        "id": "broadband", **{k: meta[k] for k in ("group", "icon", "emoji", "format", "scale", "higher_is", "ramp")},
        "name": tr("Banda ancha", "Broadband"),
        "unit": tr("hogares con cobertura de 100 Mbps o más", "households covered at 100 Mbps or more"),
        "source": "cobertura_banda_ancha",
        "description": tr(
            "Proporción de los hogares de cada municipio a los que llega una red fija o inalámbrica fija de 100 Mbps o "
            "más en condiciones de máxima demanda (informe de cobertura del Ministerio para la Transformación Digital, "
            "junio de {year}, con los datos de los operadores por parcela catastral; en España, {spain}). Es cobertura, "
            "no contratos: el mapa de EE. UU. cuenta hogares abonados. {spread}",
            "Share of each municipality's households that a fixed or fixed-wireless network of 100 Mbps or more reaches "
            "under peak demand (coverage report of the Ministerio para la Transformación Digital, June {year}, from the "
            "operators' data by cadastral parcel; Spain: {spain}). It is coverage, not subscriptions: the US map counts "
            "subscribing households. {spread}",
        ).format(year=str(data["year"]), spain=share_text(data.get("nation")), spread=SPREAD),
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
        "name": tr("Trabajan fuera", "Work elsewhere"),
        "unit": tr("ocupados que trabajan en otro municipio", "employed who work in another municipality"),
        "format": "pct", "scale": "linear", "higher_is": "neutral", "source": "ine_censo_lugar_trabajo",
        "description": tr(
            "Proporción de los residentes ocupados que trabajan en un municipio distinto del suyo (de su provincia, de "
            "otra provincia de su comunidad o de otra comunidad), entre los que tienen lugar de trabajo conocido (Censo "
            "anual de población del INE, 1 de enero de {year}; en España, {spain}). {listed} El INE no publica el tiempo "
            "de desplazamiento por municipio: es dónde se trabaja, no los minutos al trabajo del mapa de EE. UU. "
            "{spread}",
            "Share of employed residents who work in a municipality other than their own (in their province, in "
            "another province of their autonomous community or in another community), among those whose place of work "
            "is known (INE Annual Population Census, 1 January {year}; Spain: {spain}). {listed} INE does not publish "
            "commuting time by municipality: this is where people work, not the US map's minutes to work. {spread}",
        ).format(year=str(data["year"]), spain=share_text(works_elsewhere(data["nation"])),
                 listed=listed(len(data["municipalities"])), spread=SPREAD),
        "values": _spread(weights, by_municipality(geoids, listed_or_rest(data, works_elsewhere)), 4),
    }


def religious_share(counts: dict) -> float | None:
    return counts.get("religious", 0) / counts["total"] if counts.get("total") else None


def weddings_lens(data: dict, geoids: list[str], weights: list) -> dict:
    return {
        "id": "religious_weddings", "group": "faith", "name": tr("Bodas religiosas", "Religious weddings"),
        "icon": "l-faith", "emoji": "💒",
        "unit": tr("matrimonios religiosos, proporción del total", "religious marriages, share of all"), "format": "pct",
        "scale": "linear", "higher_is": "neutral", "ramp": FAITH_RAMP, "source": "ine_matrimonios",
        "note": tr("España no tiene censo de religión: esto mide cómo se casan, no lo que creen sus vecinos.",
                   "Spain has no census of religion: this measures how people marry, not what they believe."),
        "description": tr(
            "Proporción de los matrimonios de {year} celebrados por una confesión religiosa (el INE no separa la "
            "católica de las demás en estas tablas), por lugar de residencia de la pareja (Estadística de Matrimonios "
            "del INE; en España, {spain}). {listed} {spread}",
            "Share of the marriages of {year} celebrated by a religious denomination (INE does not separate Catholic "
            "from other weddings in these tables), by the couple's place of residence (INE Marriage Statistics; Spain: "
            "{spain}). {listed} {spread}",
        ).format(year=str(data["year"]), spain=share_text(religious_share(data["nation"])),
                 listed=listed(len(data["municipalities"])), spread=SPREAD),
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
        "name": tr("Incendios", "Wildfires"), "unit": tr("hectáreas quemadas", "hectares burnt"), "format": "int",
        "scale": "log", "higher_is": "bad", "source": "effis_incendios",
        "note": tr("Superficie que ardió, no daños: un monte que arde dos veces cuenta dos.",
                   "Area burnt, not damage: land that burns twice counts twice."),
        "description": tr(
            "Hectáreas quemadas en cada hexágono en los incendios de {first} a {last} que cartografió el Sistema Europeo "
            "de Información sobre Incendios Forestales (EFFIS, Copernicus) con imágenes de satélite: su perímetro, sea "
            "monte o cultivo, sumado año a año (en España, {ha} ha en {fires} incendios). Recoge los de unas 30 ha o más "
            "(desde 2021, con Sentinel-2, también muchos menores); los más pequeños, que la estadística del ministerio "
            "(EGIF) sí cuenta, no salen. Ocupa el lugar de las declaraciones de catástrofe de la FEMA del mapa de "
            "EE. UU.",
            "Hectares burnt in each hex in the fires of {first} to {last} that the European Forest Fire Information "
            "System (EFFIS, Copernicus) mapped from satellite images: their perimeter, woodland or farmland, added up "
            "year by year (Spain: {ha} ha in {fires} fires). It records fires of about 30 ha or more (since 2021, with "
            "Sentinel-2, many smaller ones too); the smallest, which the ministry's statistic (EGIF) does count, are "
            "missing. It takes the place of the US map's FEMA disaster declarations.",
        ).format(first=str(first), last=str(last), ha=round(total), fires=len(data["fires"])),
        "values": [round(burnt.get(c, 0.0)) if o >= 0 else None for c, o in enumerate(owner)],
    }


def lenses(world: dict, weights: list, proj, grid: HexGrid) -> list[dict]:
    """The four lenses, in the order of the US groups (Knowledge, Daily life, Faith, Hazards)."""
    geoids = world["counties"]
    return [
        broadband_lens(load_interim("cobertura_banda_ancha"), geoids, weights),
        commuters_lens(load_interim("ine_censo_lugar_trabajo"), geoids, weights),
        weddings_lens(load_interim("ine_matrimonios"), geoids, weights),
        wildfires_lens(load_interim("effis_incendios"), proj, grid, world["owner"]),
    ]
