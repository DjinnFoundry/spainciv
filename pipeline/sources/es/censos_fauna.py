"""The latest national censuses of the Iberian lynx (2025) and the wolf (2021-2024), from the Ministerio para la
Transición Ecológica y el Reto Demográfico: how many there are and in which autonomous communities, as text beside
the 2013-2018 distribution squares of the wildlife lenses (especies.py), which are older.

The figures are transcribed from the PDFs into CENSUSES, with their page: the standard library cannot read PDF text
reliably (the precedent is the hand-transcribed fiestas_autonomicas.csv). `fetch` caches both PDFs so the Almanac
cites them with their checksums, and `process` fails if either file is no longer the one transcribed (SHA256), so a
replaced PDF is re-read before the map repeats its old figures. The censuses' maps are pictures and are not used as
geometry (DECISIONS.md F39).
"""

from __future__ import annotations

import hashlib

from ...core.source import Source, SourceInfo

DAM = "https://www.miteco.gob.es/content/dam/miteco/es/biodiversidad/temas/inventarios-nacionales/"
LYNX_URL = DAM + "lince/censolinceiberico2025.pdf"
# The Inventario Español de Especies Terrestres page for mammals links every lynx census and both wolf censuses;
# WOLF_PAGE has the 2021-2024 wolf results.
HOMEPAGE = ("https://www.miteco.gob.es/es/biodiversidad/temas/inventarios-nacionales/inventario-especies-terrestres/"
            "ieet_mamiferos.html")
WOLF_PAGE = ("https://www.miteco.gob.es/es/biodiversidad/temas/inventarios-nacionales/inventario-especies-terrestres/"
             "ieet-mamiferos-censo-lobo-2024.html")
WOLF_URL = DAM + "ieet/mamiferos/lobo/Censo_nacional_Lobo_2021_2024.pdf"

# Scientific name (as especies.SPECIES) → the census, transcribed. `communities` are INE community codes
# (provinces.COMMUNITIES), in the order of the census table; `unit` is what `figure` counts (the builder words it).
CENSUSES = {
    "Lynx pardinus": {
        "url": LYNX_URL, "sha256": "c8523abd6103b235f3e5b699070af9ce5f571423574bf66bcd7aea816b749d3c",
        "period": "2025",
        # p. 2, text and table: Spain 2,269 lynx in total = 1,446 adults and subadults (468 territorial females) + 823
        # cubs; Andalucía 885, Castilla-La Mancha 1,051, Extremadura 302, Murcia 19, Castilla y León 11, Madrid 1.
        "figure": 2269, "unit": "individuals", "page": "2",
        "communities": ["01", "08", "11", "14", "07", "13"],
    },
    "Canis lupus": {
        "url": WOLF_URL, "sha256": "0548d8da636d5cdc19643aeb269d8f72c350ff8238a5233b944e9cf1a884f5ed",
        "period": "2021-2024",
        # p. 5: 333 packs; p. 6, Tabla 1, packs by community (shared packs count in each): Galicia 93, Castilla y León
        # 193, Cantabria 23, Asturias 45, Euskadi 2, La Rioja 5, Madrid 5, Castilla-La Mancha 4, Extremadura 1.
        "figure": 333, "unit": "packs", "page": "4-6",
        "communities": ["12", "07", "06", "03", "16", "17", "13", "08", "11"],
        # p. 4: distribution 2019-2024 (a longer period than the packs'), 10 km squares (ETRS89-LAEA) of stable and of
        # sporadic presence (Aragón, Cataluña). The census map (Figura 1, p. 5) is published only as a picture.
        "cells_period": "2019-2024", "stable_cells": 1357, "sporadic_cells": 37,
    },
}


def file(url: str) -> str:
    return url.rsplit("/", 1)[1]


class CensosFauna(Source):
    info = SourceInfo(
        id="miteco_censos_fauna",
        title="National censuses of the Iberian lynx (2025) and the wolf (2021-2024)",
        publisher="Ministerio para la Transición Ecológica y el Reto Demográfico (MITECO), with the autonomous "
        "communities",
        homepage=HOMEPAGE,
        license="Public-sector information, reusable citing the source (Ley 37/2007)",
        description="The Iberian lynx census of 2025 (Spain and Portugal) and the wolf census of 2021-2024 (packs, and "
        "10 km squares of presence for 2019-2024), as PDF reports linked from the mammals page of the Inventario "
        f"Español de Especies Terrestres; the wolf results also have their own page ({WOLF_PAGE}). The map quotes "
        "their totals and the autonomous communities they name beside the older distribution squares of the wildlife "
        "lenses.",
        used_for=["Wildlife lenses (lynx and wolf)"],
    )

    def fetch(self, force=False):
        for c in CENSUSES.values():
            self.download(c["url"], file(c["url"]), force=force, expect_binary=True)

    def process(self):
        for name, c in CENSUSES.items():
            path = self.raw_dir / file(c["url"])
            got = hashlib.sha256(path.read_bytes()).hexdigest()
            if got != c["sha256"]:
                raise RuntimeError(f"{file(c['url'])} ({name}) has changed (SHA256 {got}, transcribed from "
                                   f"{c['sha256']}): re-read the PDF and update the figures in CENSUSES")
        return {
            "vintage": "MITECO, Lynx pardinus 2025, Canis lupus 2021-2024",
            "_files": [file(c["url"]) for c in CENSUSES.values()],
            "censuses": {name: {k: v for k, v in c.items() if k != "sha256"} for name, c in CENSUSES.items()},
        }
