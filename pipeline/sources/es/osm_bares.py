"""Bars and pubs in Spain from OpenStreetMap (ODbL), in one cached Overpass query.

OSM tags a Spanish bar as amenity=bar (or amenity=pub for the beer and cocktail kind); cafés (amenity=cafe) and
restaurants are left out. Mappers are volunteers: cities and tourist coasts are mapped far more completely than the
countryside, so a count is a lower bound, uneven from place to place.
"""

from __future__ import annotations

import csv
import io
import urllib.parse

from ...core.fetch import read_manifest
from ...core.source import Source, SourceInfo

OVERPASS = "https://overpass-api.de/api/interpreter?data="
AMENITIES = ("bar", "pub")
QUERY = ('[out:csv(::type,::lat,::lon,amenity;false;",")][timeout:300];area["ISO3166-1"="ES"][admin_level=2]->.es;'
         f'nwr["amenity"~"^({"|".join(AMENITIES)})$"](area.es);out center;')
FILE = "bars_pubs.csv"


class OsmBares(Source):
    info = SourceInfo(
        id="osm_bares",
        title="Bars and pubs in Spain (OpenStreetMap, amenity=bar and amenity=pub)",
        publisher="OpenStreetMap contributors, via the Overpass API",
        homepage="https://www.openstreetmap.org/",
        license="ODbL 1.0 (© OpenStreetMap contributors)",
        description="Every OpenStreetMap node, way or relation in Spain tagged amenity=bar or amenity=pub, at its "
        "position (the centre of a way). Cafés are not counted. Volunteer-mapped: coverage is much better in cities "
        "and on the tourist coasts than in the countryside.",
        used_for=["Bars per inhabitant lens", "Party index lens"],
    )

    def fetch(self, force=False):
        self.download(OVERPASS + urllib.parse.quote(QUERY), FILE, force=force)

    def process(self):
        bars = [[round(float(lon), 5), round(float(lat), 5)]
                for kind, lat, lon, amenity in csv.reader(io.StringIO((self.raw_dir / FILE).read_text(encoding="utf-8")))
                if lat and amenity in AMENITIES]
        retrieved = read_manifest(self.id)[FILE]["retrieved"][:10]
        return {"vintage": f"OpenStreetMap, {retrieved}", "_files": [FILE], "amenities": list(AMENITIES), "bars": bars}
