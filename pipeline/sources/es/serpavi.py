"""Rents from the Sistema Estatal de Referencia del Precio del Alquiler de Vivienda (SERPAVI), Ministerio de Vivienda.

SERPAVI is an exploitation of income-tax returns (Modelo 100: rents declared for a primary residence, leases between
relatives excluded) crossed with the Cadastre. Its workbook gives, for every year, Spain's autonomous communities,
provinces, municipalities, districts and census sections, the number of rented dwellings and the median monthly rent
of the whole dwelling, separately for flats (vivienda colectiva) and houses (vivienda unifamiliar). Municipalities
with too few leases are left blank by the ministry. The census-section sheet (most of the file) is not read.
"""

from __future__ import annotations

import re

from ...core.source import Source, SourceInfo
from ...core.xlsx import sheets

URL = ("https://cdn.mivau.gob.es/portal-web-mivau/vivienda/serpavi/"
       "2026-03_09_bd_SERPAVI_2011-2024%20-%20DEFINITIVO%20WEB_v2.xlsx")
FILE = "bd_SERPAVI_2011-2024.xlsx"
TYPES = ("VC", "VU")  # vivienda colectiva (flats), vivienda unifamiliar o rural (houses)
SHEETS = {"municipalities": ("Municipios", "CUMUN"), "provinces": ("Provincias", "CPRO")}


def as_float(text: str | None) -> float | None:
    return float(text) if text not in (None, "") else None


def latest_year(header: list[str | None]) -> str:
    """The last two-digit year with a median-rent column: 'ALQTBID12_M_VC_24' → '24'."""
    years = [m.group(1) for h in header if h and (m := re.fullmatch(r"ALQTBID12_M_VC_(\d\d)", h))]
    if not years:
        raise RuntimeError(f"{FILE}: no ALQTBID12_M_VC_<year> column")
    return max(years)


def rents(rows: list[list[str | None]], code_col: str, yy: str) -> dict[str, list[list[float]]]:
    """{code: [[rented dwellings, median monthly rent], …]} for the dwelling types with both figures in year yy."""
    header = rows[0]
    at = {h: k for k, h in enumerate(header) if h}
    cols = [(at[f"BI_ALVHEPCO_T{t}_{yy}"], at[f"ALQTBID12_M_{t}_{yy}"]) for t in TYPES]
    out = {}
    for r in rows[1:]:
        if not r or len(r) <= at[code_col] or not r[at[code_col]]:
            continue
        pairs = []
        for n_col, m_col in cols:
            n = as_float(r[n_col]) if n_col < len(r) else None
            m = as_float(r[m_col]) if m_col < len(r) else None
            if n and m is not None:
                pairs.append([int(n), round(m, 2)])
        if pairs:
            out[r[at[code_col]].strip()] = pairs
    return out


class Serpavi(Source):
    info = SourceInfo(
        id="serpavi",
        title="Sistema Estatal de Referencia del Precio del Alquiler de Vivienda (SERPAVI), 2011-2024",
        publisher="Ministerio de Vivienda y Agenda Urbana (with the Agencia Tributaria and the Dirección General del Catastro)",
        homepage="https://www.mivau.gob.es/vivienda/alquila-bien-es-tu-derecho/serpavi",
        license="Public-sector information, reuse permitted citing the source (Ley 37/2007)",
        description="Rents declared in personal income-tax returns for primary residences, crossed with the Cadastre: the "
        "number of rented dwellings and the median monthly rent of the whole dwelling, for flats and houses separately, "
        "by province and municipality. Municipalities with too few leases have no figure. The Basque Country and "
        "Navarre (own tax regimes) have fewer years.",
        used_for=["Monthly rent of cities, provinces and Spain", "Rent ÷ income"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=True)

    def process(self):
        book = sheets(self.raw_dir / FILE, only={name for name, _ in SHEETS.values()})
        yy = latest_year(book[SHEETS["municipalities"][0]][0])
        out = {level: rents(book[name], col, yy) for level, (name, col) in SHEETS.items()}
        if len(out["provinces"]) < 52:
            raise RuntimeError(f"{FILE} 20{yy}: rents for only {len(out['provinces'])} provinces")
        return {"vintage": f"SERPAVI (Ministerio de Vivienda), 20{yy}", "_files": [FILE], "year": 2000 + int(yy), **out}
