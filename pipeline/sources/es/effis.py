"""Burnt areas in Spain from the European Forest Fire Information System (EFFIS, Copernicus Emergency Management
Service, European Commission Joint Research Centre), one WFS layer per fire season.

EFFIS maps the perimeter of every fire it detects from MODIS and Sentinel-2 imagery, about 30 ha and larger (smaller
ones appear when they are seen), wherever they burn: forest, scrub or farmland. Each polygon carries its area, start
date and the province and commune EFFIS places it in. Spain's own statistic (MITECO's EGIF) counts every fire from
the regional fire reports, but its public search tool gives fires one by one, by municipality name, with definitive
data only up to 2016 (DECISIONS); EFFIS is the official open series of where the land burnt, year by year.
"""

from __future__ import annotations

import urllib.parse

from ...core.geo import geojson_rings, load_geojson
from ...core.source import Source, SourceInfo

WFS = "https://maps.effis.emergency.copernicus.eu/effis"
YEARS = range(2016, 2026)  # the last ten complete fire seasons with their own layer
FILTER = ("<Filter><PropertyIsEqualTo><PropertyName>COUNTRY</PropertyName><Literal>ES</Literal></PropertyIsEqualTo>"
          "</Filter>")


def url(year: int) -> str:
    return WFS + "?" + urllib.parse.urlencode({
        "service": "WFS", "version": "1.1.0", "request": "GetFeature", "typename": f"ms:modis.ba.poly.{year}",
        "outputformat": "application/json; subtype=geojson", "FILTER": FILTER,
    })


def file(year: int) -> str:
    return f"modis.ba.poly.{year}.es.geojson"


def rings_of(geom: dict) -> list[list[tuple[float, float]]]:
    """The rings of a Polygon, MultiPolygon or GeometryCollection of them (EFFIS uses all three)."""
    if geom.get("type") == "GeometryCollection":
        return [r for g in geom.get("geometries", []) for r in rings_of(g)]
    return [r for r in geojson_rings(geom) if len(r) >= 4]


def fires(features: list[dict], year: int) -> list[dict]:
    """Spain's burnt-area polygons of one season: year, area (ha), province and rings (lon, lat). Polygons with no
    area or no geometry are left out."""
    out = []
    for f in features:
        p, geom = f.get("properties") or {}, f.get("geometry")
        area = float(p.get("AREA_HA") or 0)
        if p.get("COUNTRY") != "ES" or not geom or area <= 0:
            continue
        rings = rings_of(geom)
        if rings:
            out.append({"year": year, "area_ha": area, "province": p.get("PROVINCE"), "rings": rings})
    return out


class EffisBurntAreas(Source):
    info = SourceInfo(
        id="effis_incendios",
        title=f"EFFIS burnt areas in Spain, {YEARS[0]}-{YEARS[-1]} (Copernicus Emergency Management Service)",
        publisher="European Commission, Joint Research Centre: European Forest Fire Information System (EFFIS), "
        "Copernicus Emergency Management Service",
        homepage="https://forest-fire.emergency.copernicus.eu/applications/data-and-services",
        license="CC BY 4.0 (European Commission reuse policy), crediting EFFIS / Copernicus EMS",
        description="The perimeters of the fires EFFIS mapped in Spain each season from satellite imagery (MODIS and "
        "Sentinel-2), roughly 30 ha and larger, with their area. The map adds up the burnt area of the last ten "
        "complete seasons on each hex.",
        used_for=["Wildfires lens"],
    )

    def fetch(self, force=False):
        for year in YEARS:
            self.download(url(year), file(year), force=force)

    def process(self):
        out = []
        for year in YEARS:
            season = fires(load_geojson(self.raw_dir / file(year)), year)
            if not season:
                raise RuntimeError(f"{file(year)}: no burnt areas in Spain")
            out += season
        return {
            "vintage": f"EFFIS (Copernicus), {YEARS[0]}-{YEARS[-1]}",
            "_files": [file(y) for y in YEARS],
            "years": [YEARS[0], YEARS[-1]],
            "fires": out,
        }
