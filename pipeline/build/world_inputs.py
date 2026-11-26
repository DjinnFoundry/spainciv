"""What the world builder needs from each country, in one neutral shape.

world.py draws the map from: region outlines (states, provinces), unit outlines (counties, municipalities),
neighbouring countries/lakes/rivers (Natural Earth), elevation samples (ETOPO) and a land-cover raster. Each country
loads those from its own sources here. Land cover is handed over in NLCD class codes: Spain's CORINE classes are
cross-walked to them (see pipeline/sources/es/corine.py), so the cover rules and the world.json tables stay one
definition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..core.geo import AlbersEllipsoid, LambertAzimuthalEllipsoid
from ..core.store import load_interim
from . import texts_es

REQUIRES = {
    "us": ["census_boundaries", "natural_earth", "etopo", "nlcd"],
    "es": ["siane", "natural_earth_es", "etopo_es", "corine"],
}


@dataclass
class WorldInputs:
    regions: list[dict]  # {"fips": code, "abbr", "name", "rings"}: states / provinces
    units: list[dict]  # {"geoid": code, "name", "state_fips", "rings"}: counties / municipalities
    ne: dict  # Natural Earth: countries, lakes, rivers (see sources/natural_earth.py)
    etopo: dict  # {"lat": [], "lon": [], "alt": []}
    cover_at: Callable[[float, float], int | None]  # lon/lat → NLCD class code (0 no data), None off the raster
    cover_step_km: float  # spacing of the land-cover sampling lattice inside a hex
    texts: dict = field(default_factory=dict)  # world.json table names, rules and notes in the country's words (world.localized)


def raster_lookup(raster: dict, project) -> Callable[[float, float], int | None]:
    """A nearest-pixel lookup into an interim raster {x0, dx, y0, dy, cols, rows: [str], legend: {char: code}}, or into
    several tiles of one ({legend, rasters: [{x0, dx, y0, dy, cols, rows}]}): the first tile holding the point wins."""
    legend = raster["legend"]
    tiles = [(t["x0"], t["dx"], t["y0"], t["dy"], t["cols"], len(t["rows"]), t["rows"]) for t in raster.get("rasters", [raster])]

    def at(lon: float, lat: float) -> int | None:
        ex, ey = project(lon, lat)
        for x0, dx, y0, dy, ncols, nrows, rows in tiles:
            c, r = round((ex - x0) / dx), round((ey - y0) / dy)
            if 0 <= c < ncols and 0 <= r < nrows:
                return legend[rows[r][c]]
        return None

    return at


def _us() -> WorldInputs:
    bounds = load_interim("census_boundaries")
    return WorldInputs(
        regions=bounds["states"],
        units=bounds["counties"],
        ne=load_interim("natural_earth"),
        etopo=load_interim("etopo"),
        cover_at=raster_lookup(load_interim("nlcd"), AlbersEllipsoid()),  # NLCD is in EPSG:5070
        cover_step_km=2.0,
    )


def _es() -> WorldInputs:
    lau = load_interim("siane")
    corine = load_interim("corine")
    return WorldInputs(
        regions=lau["provinces"],
        units=lau["municipalities"],
        ne=load_interim("natural_earth_es"),
        etopo=load_interim("etopo_es"),
        cover_at=raster_lookup(corine, LambertAzimuthalEllipsoid()),  # CORINE is in EPSG:3035
        cover_step_km=corine["step_km"],
        texts=texts_es.WORLD,
    )


def load(country_id: str) -> WorldInputs:
    return {"us": _us, "es": _es}[country_id]()
