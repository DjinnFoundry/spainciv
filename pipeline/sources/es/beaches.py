"""Spain's Blue Flag beaches (ADEAC), from the list ADEAC publishes only as a PDF, read into a CSV in this
repository by tools/bandera_azul_pdf.py."""

from __future__ import annotations

import csv
from pathlib import Path

from ...core.source import Source, SourceInfo

FILE = Path(__file__).parent / "data" / "bandera_azul_2026.csv"
SEASON = "2026-2027"
PDF = ("https://www.banderaazul.org/sites/default/files/2026/Rueda-de-prensa-2026/"
       "Relaci%C3%B3n%20Playas%20Galardonadas%202026.pdf")
PDF_FILE = "relacion_playas_galardonadas_2026.pdf"
# ADEAC's province headers (islands for the archipelagos, a Catalan coast for Tarragona's south) → INE province code.
PROVINCE = {"ALMERÍA": "04", "CÁDIZ": "11", "CÓRDOBA": "14", "GRANADA": "18", "HUELVA": "21", "JAÉN": "23",
            "MÁLAGA": "29", "EL HIERRO": "38", "LA GOMERA": "38", "LA PALMA": "38", "TENERIFE": "38",
            "FUERTEVENTURA": "35", "GRAN CANARIA": "35", "LANZAROTE": "35", "BARCELONA": "08", "GIRONA": "17",
            "TARRAGONA": "43", "TERRES DE L’EBRE": "43", "ALICANTE": "03", "CASTELLÓN": "12", "VALENCIA": "46",
            "BADAJOZ": "06", "CÁCERES": "10", "A CORUÑA": "15", "LUGO": "27", "OURENSE": "32", "PONTEVEDRA": "36",
            "IBIZA": "07", "MALLORCA": "07", "MENORCA": "07", "VIZCAYA": "48", "ÁLAVA": "01"}
# Single-province communities, which the list gives no province header.
COMMUNITY = {"CANTABRIA": "39", "CIUDAD AUTÓNOMA DE CEUTA": "51", "CIUDAD AUTÓNOMA DE MELILLA": "52",
             "COMUNIDAD DE MADRID": "28", "PRINCIPADO DE ASTURIAS": "33", "REGIÓN DE MURCIA": "30"}


class BanderaAzul(Source):
    info = SourceInfo(
        id="bandera_azul",
        title=f"Blue Flag beaches {SEASON} (Bandera Azul, ADEAC)",
        publisher="ADEAC (Asociación de Educación Ambiental y del Consumidor), Blue Flag programme",
        homepage="https://www.banderaazul.org/",
        license="© ADEAC; the list of awarded beaches is cited as published",
        description=f"Every Spanish beach awarded the Blue Flag for {SEASON}, by municipality, as ADEAC lists them in "
        "its PDF (read into pipeline/sources/es/data/bandera_azul_2026.csv; the count per community matches ADEAC's).",
        used_for=["Blue Flag beaches lens"],
    )

    def fetch(self, force=False):
        # The PDF the CSV was read from, cached for provenance (reading it needs poppler: tools/bandera_azul_pdf.py).
        self.download(PDF, PDF_FILE, force=force, expect_binary=True)

    def process(self):
        with open(FILE, encoding="utf-8") as f:
            rows = list(csv.DictReader(line for line in f if not line.startswith("#")))
        beaches = [{"beach": r["beach"], "municipality": r["municipality"],
                    "province": PROVINCE.get(r["province"]) or COMMUNITY[r["community"]]} for r in rows]
        return {"vintage": f"Bandera Azul {SEASON}", "_files": [PDF_FILE], "season": SEASON, "beaches": beaches}
