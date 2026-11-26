"""Peoples of pre-Roman and Roman Iberia from Pleiades, the gazetteer of ancient places."""

from __future__ import annotations

import csv
import gzip
import io
import re

from ...core.source import Source, SourceInfo

URL = "https://atlantides.org/downloads/pleiades/dumps/pleiades-places-latest.csv.gz"
FILE = "pleiades-places.csv.gz"
# Iberia and the lands around it (Aquitania, Narbonensis), whose peoples bound the Iberian ones; Africa is left out.
BBOX = (-10.0, 35.9, 4.5, 44.6)
AFRICA = (-1.9, 35.9, 4.5, 37.2)  # the Algerian coast inside BBOX (Spain's coast there runs north of 37.2°)
# Regions Pleiades names after a people where it has no point for the people itself (the south and the east).
REGIONS = {"265877", "265888", "266075", "265822", "265847", "246322", "246331", "246460"}
TAG = re.compile(r"\s*\((region|people)\)$")


def inside(box: tuple, lon: float, lat: float) -> bool:
    w, s, e, n = box
    return w <= lon <= e and s <= lat <= n


class PleiadesIberia(Source):
    info = SourceInfo(
        id="pleiades_iberia",
        title="Peoples of ancient Iberia (Pleiades)",
        publisher="Pleiades (Institute for the Study of the Ancient World, NYU, and contributors)",
        homepage="https://pleiades.stoa.org/",
        license="CC BY 3.0",
        description="Every place Pleiades types as a people with a located point in and around the Iberian Peninsula "
        "(Vaccaei, Vascones, Cantabri, Ilergetes, the many peoples of Gallaecia…), plus the regions it names after "
        "peoples it has no point for (Turdetania, Bastetania, Contestania, Edetania, Carpetania, Celtiberia, "
        "Cessetania, Laeetania). A '?' marks an uncertain location, as in Pleiades.",
        used_for=["Ancient peoples lens"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=True)

    def process(self):
        peoples = []
        with gzip.open(self.raw_dir / FILE, "rt", encoding="utf-8") as f:
            for r in csv.DictReader(io.StringIO(f.read())):
                if not r["reprLat"] or not ("people" in r["featureTypes"] or r["id"] in REGIONS):
                    continue
                lat, lon = float(r["reprLat"]), float(r["reprLong"])
                if inside(BBOX, lon, lat) and not inside(AFRICA, lon, lat) and r["locationPrecision"] != "rough":
                    peoples.append({"id": r["id"], "name": TAG.sub("", r["title"]), "lon": round(lon, 4),
                                    "lat": round(lat, 4)})
        return {"vintage": "Pleiades", "_files": [FILE], "peoples": sorted(peoples, key=lambda p: p["name"])}
