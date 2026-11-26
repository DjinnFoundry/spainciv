"""Fixed broadband coverage by municipality, from the yearly coverage report of the Ministerio para la Transformación
Digital y de la Función Pública (Secretaría de Estado de Telecomunicaciones e Infraestructuras Digitales).

The ministry publishes, as a reusable workbook, the coverage of every municipality, province, autonomous community and
Spain in June of each year: the share of households (and of Cadastre dwellings) that the operators' networks reach,
by technology (FTTH, HFC, fixed wireless, 4G, 5G) and by speed under peak-demand conditions (30 Mbps, 100 Mbps,
1 Gbps). It is coverage (a network can serve the home), not subscriptions.
"""

from __future__ import annotations

import re

from ...core.source import Source, SourceInfo
from ...core.xlsx import sheets

URL = ("https://digital.gob.es/content/dam/portal-mtdfp/avance-digital/telecomunicacion-e-infraestructuras-digitales/"
       "areas_interes/banda-ancha/cobertura/documents/Cobertura_BA_Espa%C3%B1a_2021-2025_MUN_PROV_CCAA_Nacional_datosgob_DEF.xlsx")
FILE = "Cobertura_BA_Espana_2021-2025.xlsx"
SHEETS = {"municipalities": "Municipio_%hogar", "nation": "Nacional_%hogar"}
SPEED = "100Mbps"  # the map's threshold: "banda ancha ultrarrápida", 100 Mbps or more under peak demand
COLUMN = re.compile(r"Cob\. (\d+[MG]bps).*\(junio (\d{4})\)", re.S)


def latest_column(header: list[str | None], speed: str = SPEED) -> tuple[int, int]:
    """(column index, year) of the newest June column of the coverage at `speed`."""
    found = [(int(m.group(2)), k) for k, h in enumerate(header) if h and (m := COLUMN.match(h)) and m.group(1) == speed]
    if not found:
        raise RuntimeError(f"{FILE}: no 'Cob. {speed} … (junio <year>)' column")
    year, col = max(found)
    return col, year


def coverage(rows: list[list[str | None]], key_col: int, col: int) -> dict[str, float]:
    """{key: share of households covered, rounded to 4 decimals} for the rows that have both."""
    out = {}
    for r in rows[1:]:
        if len(r) <= max(key_col, col) or not r[key_col] or r[col] in (None, ""):
            continue
        out[r[key_col].strip()] = round(min(max(float(r[col]), 0.0), 1.0), 4)
    return out


class CoberturaBandaAncha(Source):
    info = SourceInfo(
        id="cobertura_banda_ancha",
        title="Broadband coverage in Spain 2021-2025 by municipality, province, autonomous community and Spain",
        publisher="Ministerio para la Transformación Digital y de la Función Pública (Secretaría de Estado de "
        "Telecomunicaciones e Infraestructuras Digitales)",
        homepage="https://digital.gob.es/telecomunicaciones-infraestructuras-digitales/areas-interes/banda-ancha/"
        "informacion-cobertura.html",
        license="Public-sector information, reuse permitted citing the source (Ley 37/2007)",
        description="Share of households that fixed and mobile networks can serve, by technology and by speed under "
        "peak-demand conditions, in June of each year, from the coverage the operators report to the ministry, "
        "georeferenced to Cadastre parcels (households: INE 2021 census). The map uses coverage at 100 Mbps or more "
        "for every municipality. It measures where a network reaches, not who subscribes.",
        used_for=["Broadband lens"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=True)

    def process(self):
        book = sheets(self.raw_dir / FILE, only=set(SHEETS.values()))
        munis = book[SHEETS["municipalities"]]
        col, year = latest_column(munis[0])
        out = coverage(munis, munis[0].index("CMUN"), col)
        if len(out) < 8000:
            raise RuntimeError(f"{FILE}: coverage for only {len(out)} municipalities")
        nation = book[SHEETS["nation"]]
        ncol, nyear = latest_column(nation[0])
        return {
            "vintage": f"Cobertura de banda ancha (Ministerio para la Transformación Digital), junio de {year}",
            "_files": [FILE],
            "year": year,
            "speed": SPEED,
            "municipalities": dict(sorted(out.items())),
            "nation": coverage(nation, 0, ncol).get("España") if nyear == year else None,
        }
