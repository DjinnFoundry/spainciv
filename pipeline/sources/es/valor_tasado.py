"""Appraised value of free-market housing per m², by province and quarter (Ministerio de Vivienda, VDP006).

The Ministry's statistic of appraisals (tasaciones) made for mortgages and other purposes, in € per m² of built area,
for free-market dwellings (vivienda libre; protected dwellings have a capped price and their own series). The open CSV
gives Spain, the communities and the provinces; a single-province community (Madrid, Asturias, Navarra, Murcia,
Cantabria, La Rioja, the Balearic Islands) appears only as a community row, and Murcia's row comes without its code.
The municipal series (towns over 25,000) is published only as a binary XLS on a server that answers 503 (DECISIONS E44).
"""

from __future__ import annotations

import csv
import io
import unicodedata

from ...core.source import Source, SourceInfo
from .provinces import COMMUNITIES, PROVINCES

URL = "https://cdn.mivau.gob.es/portal-web-mivau/Datos_MIVAU/CSV/VDP006_01.csv"
FILE = "VDP006_01.csv"


def fold(text: str) -> str:
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower()


COMMUNITY_BY_NAME = {fold(name): code for code, (name, _) in COMMUNITIES.items()}


def province_of(row: dict) -> str | None:
    """The INE province code a row stands for: a province row's own, or a single-province community's province."""
    if row["Provincia"] != "Total CCAA":
        return row["CPRO"].zfill(2) if row["CPRO"].isdigit() else None
    code = row["CODAUTO"].zfill(2) if row["CODAUTO"] else COMMUNITY_BY_NAME.get(fold(row["Comunidad_Autónoma"]))
    provinces = COMMUNITIES[code][1] if code in COMMUNITIES else []
    return provinces[0] if len(provinces) == 1 else None


def latest(rows: list[dict]) -> dict:
    """The last quarter with a free-market value for every province: {"year", "quarter", "provinces", "spain"}."""
    free = [r for r in rows if r["Régimen"] == "Libre" and r["Valor"]]
    for year, quarter in sorted({(int(r["Año"]), int(r["Trimestre"])) for r in free}, reverse=True):
        now = [r for r in free if (int(r["Año"]), int(r["Trimestre"])) == (year, quarter)]
        provinces = {p: float(r["Valor"]) for r in now if (p := province_of(r))}
        if set(provinces) == set(PROVINCES):
            spain = next(float(r["Valor"]) for r in now if r["Comunidad_Autónoma"] == "Total nacional")
            return {"year": year, "quarter": quarter, "provinces": dict(sorted(provinces.items())), "spain": spain}
    raise RuntimeError(f"{FILE}: no quarter has a value for all {len(PROVINCES)} provinces")


class ValorTasado(Source):
    info = SourceInfo(
        id="mivau_valor_tasado",
        title="Appraised value of free-market housing per m², by province (Ministerio de Vivienda, VDP006)",
        publisher="Ministerio de Vivienda y Agenda Urbana",
        homepage="https://cdn.mivau.gob.es/portal-web-mivau/Datos_MIVAU/Info/Readme_VDP006_01.pdf",
        license="Public-sector information, reuse permitted citing the source (Ley 37/2007)",
        description="Mean appraised value of free-market dwellings, € per m² of built area, from the appraisals that "
        "appraisal companies report each quarter, by province. A province's value covers all of it; no municipal "
        "figure is read.",
        used_for=["Home value lens (€/m², by province)"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force)

    def process(self):
        text = (self.raw_dir / FILE).read_text(encoding="utf-8-sig")
        data = latest(list(csv.DictReader(io.StringIO(text), delimiter=";")))
        return {"vintage": f"Ministerio de Vivienda, valor tasado, {data['quarter']}.º trimestre de {data['year']}",
                "_files": [FILE], **data}
