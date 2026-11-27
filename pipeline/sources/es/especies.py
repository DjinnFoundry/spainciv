"""Where five of Spain's best-known wild animals were reported: the 10 km squares where Spain reported them to the European Union
for 2013-2018 (Ministerio para la Transición Ecológica y el Reto Demográfico, Banco de Datos de la Naturaleza).

Every six years each member state reports the distribution of the species of the Habitats Directive (art. 17: lynx,
brown bear, wolf) and of the breeding birds of the Birds Directive (art. 12: Spanish imperial eagle, bearded vulture)
on the EEA 10 km reference grid in ETRS89-LAEA (EPSG:3035). MITECO publishes each report as one shapefile whose
records carry the code of their square (`CellCode10`, e.g. "10kmE316N182"), so only the table (.dbf) is read,
streamed from the zip: no polygon is needed to know which square a record is. Process keeps SPECIES and fails if any
of their records is marked sensitive, is not a distribution record or names a square in another form. Rules:
DECISIONS.md E90 and F37.
"""

from __future__ import annotations

import io
import re
import zipfile

from ...core.dbf import records
from ...core.source import Source, SourceInfo

DAM = "https://www.miteco.gob.es/content/dam/miteco/es/biodiversidad/temas/"
# Directive article → (zip, the field that names the species)
REPORTS = {
    "art17": (DAM + "espacios-protegidos/es_art17_speciesdistrib_laea_tcm30-508255.zip", "Especie"),
    "art12": (DAM + "conservacion-de-especies/es_art12_birdsdistrib_laea_tcm30-508242.zip", "Nombre"),
}
# The pages that link each zip: the art. 17 report (HOMEPAGE, cited as the source's page) and the art. 12 report.
HOMEPAGE = ("https://www.miteco.gob.es/es/biodiversidad/temas/espacios-protegidos/red-natura-2000/"
            "rn_cons_seguimiento_art17_inf_2013_2018.html")
ART12_PAGE = ("https://www.miteco.gob.es/es/biodiversidad/temas/conservacion-de-especies/especies-proteccion-especial/"
              "2-3-ce-informes-sexenales-19.html")
PERIOD = [2013, 2018]
# The species the map shows, by scientific name as the reports write it, and the report each one is in.
SPECIES = {"Lynx pardinus": "art17", "Ursus arctos": "art17", "Canis lupus": "art17", "Aquila adalberti": "art12",
           "Gypaetus barbatus": "art12"}
CELL = re.compile(r"^10kmE\d+N\d+$")
FIELDS = ["CellCode10", "code", "maptype", "refgrid", "sensitive"]


def file(article: str) -> str:
    return REPORTS[article][0].rsplit("/", 1)[1]


def member(zf: zipfile.ZipFile, suffix: str) -> str:
    names = [n for n in zf.namelist() if n.lower().endswith(suffix)]
    if len(names) != 1:
        raise RuntimeError(f"{zf.filename}: expected one {suffix} file, found {names}")
    return names[0]


def species_cells(zf: zipfile.ZipFile, name_field: str, wanted: set[str]) -> dict[str, dict]:
    """{scientific name: {"code", "refgrid", "cells": sorted square codes}} of the `wanted` species of one report."""
    encoding = zf.read(member(zf, ".cpg")).decode("ascii").strip() if any(
        n.lower().endswith(".cpg") for n in zf.namelist()) else "utf-8"
    out: dict[str, dict] = {}
    with zf.open(member(zf, ".dbf")) as fh:
        for r in records(io.BufferedReader(fh), FIELDS + [name_field], encoding):
            name = r[name_field]
            if name not in wanted:
                continue
            where = f"{zf.filename}: {name} in {r['CellCode10']!r}"
            if r["sensitive"] != "Non sensitive":
                raise RuntimeError(f"{where} is marked {r['sensitive']!r}: sensitive records are not shown")
            if r["maptype"] != "Distribution":
                raise RuntimeError(f"{where} is a {r['maptype']!r} record, not a distribution")
            if not CELL.match(r["CellCode10"]):
                raise RuntimeError(f"{where}: not an EEA 10 km cell code")
            sp = out.setdefault(name, {"code": r["code"], "refgrid": r["refgrid"], "cells": set()})
            if (r["code"], r["refgrid"]) != (sp["code"], sp["refgrid"]):
                raise RuntimeError(f"{where}: code {r['code']} / grid {r['refgrid']}, other records say "
                                   f"{sp['code']} / {sp['refgrid']}")
            sp["cells"].add(r["CellCode10"])
    missing = wanted - set(out)
    if missing:
        raise RuntimeError(f"{zf.filename}: no records of {sorted(missing)}")
    return {k: {**v, "cells": sorted(v["cells"])} for k, v in out.items()}


class Especies(Source):
    info = SourceInfo(
        id="bdn_especies",
        title=f"Distribution of species and breeding birds in Spain, {PERIOD[0]}-{PERIOD[1]} (Habitats Directive art. "
        "17 and Birds Directive art. 12 reports, 10 km grid)",
        publisher="Ministerio para la Transición Ecológica y el Reto Demográfico (MITECO): Banco de Datos de la "
        "Naturaleza, Inventario Español del Patrimonio Natural y de la Biodiversidad",
        homepage=HOMEPAGE,
        # Neither page states a licence; MITECO's legal notice puts its content under Ley 37/2007.
        license="Public-sector information, reusable citing the source (Ley 37/2007)",
        description="The 10 km squares of the EEA reference grid (ETRS89-LAEA) where Spain reported each species of the "
        "Habitats Directive and each breeding bird of the Birds Directive in its six-year reports to the EU. The map "
        "reads the squares of the Iberian lynx, brown bear, wolf, Spanish imperial eagle and bearded vulture. The art. "
        "17 zip is linked from the page above, the art. 12 zip from MITECO's page for the 2013-2018 Birds Directive "
        "report.",
        used_for=["Wildlife lenses"],
    )

    def fetch(self, force=False):
        for url, _ in REPORTS.values():
            self.download(url, url.rsplit("/", 1)[1], force=force, expect_binary=True)

    def process(self):
        species: dict[str, dict] = {}
        for article, (_, name_field) in REPORTS.items():
            wanted = {k for k, a in SPECIES.items() if a == article}
            with zipfile.ZipFile(self.raw_dir / file(article)) as zf:
                for name, sp in species_cells(zf, name_field, wanted).items():
                    species[name] = {"directive": article, **sp}
        return {
            "vintage": f"MITECO (BDN), {PERIOD[0]}-{PERIOD[1]}",  # each lens's note names its article
            "_files": [file(a) for a in REPORTS],
            "period": PERIOD,
            "grid": "EEA 10 km, ETRS89-LAEA (EPSG:3035)",
            "species": {k: species[k] for k in SPECIES},
        }
