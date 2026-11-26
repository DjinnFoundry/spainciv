"""Spain's large urban areas (Grandes Áreas Urbanas) from the Atlas Digital de las Áreas Urbanas (AUDES).

The ministry for housing and urban agenda publishes each year the list of the large urban areas (over 50,000
residents) and their member municipalities, by name only (no INE codes), with the area's population. The builder
matches the names to INE codes (pipeline/build/spain.py) and checks each area against its member count and population.
"""

from __future__ import annotations

import re

from ...core.source import Source, SourceInfo
from ...core.xlsx import sheets

YEAR = 2025
URL = f"https://atlasau.mitma.gob.es/documentos/listado_{YEAR}.xlsx"
FILE = f"listado_{YEAR}.xlsx"
SHEET = "LISTADO"
AREA = re.compile(r"ÁREA URBANA\s*(?:(?:DE|DEL)\s+)?(.+)", re.IGNORECASE)  # "DE MADRID", "DEL VALLE…", "ZARAGOZA"


class Audes(Source):
    info = SourceInfo(
        id="audes",
        title=f"Atlas Digital de las Áreas Urbanas: large urban areas and their municipalities ({YEAR})",
        publisher="Ministerio de Vivienda y Agenda Urbana (Atlas Digital de las Áreas Urbanas de España)",
        homepage="https://atlasau.mitma.gob.es/",
        license="Public-sector information, reuse permitted citing the source (Ley 37/2007)",
        description="The 86 large urban areas (Grandes Áreas Urbanas: over 50,000 residents) and the municipalities each "
        "one is made of, as defined by the ministry. They are the map's cities, like the US metro areas: a city's "
        "population, jobs and footprint add up its member municipalities.",
        used_for=["Cities (urban areas) and their member municipalities"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=True)

    def process(self):
        rows = sheets(self.raw_dir / FILE)[SHEET]
        areas = []
        for r in rows[1:]:
            if not r or not r[0]:
                continue
            m = AREA.match(r[0].strip())
            if m:
                areas.append({"name": m.group(1).strip(), "label": r[0].strip(), "municipalities": int(float(r[1])),
                              "population": int(float(r[3])), "members": []})
            elif areas:
                areas[-1]["members"].append(r[0].strip())
        bad = [a["name"] for a in areas if len(a["members"]) != a["municipalities"]]
        if bad or not areas:
            raise RuntimeError(f"{FILE}: member lists don't match their counts for {bad or 'every area'}")
        return {"vintage": f"AUDES {YEAR} (population {YEAR - 1})", "_files": [FILE], "year": YEAR, "areas": areas}
