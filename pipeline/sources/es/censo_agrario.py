"""Horses, mules and donkeys on Spain's farms: the INE's Censo Agrario 2020 by agricultural comarca.

The equine census of the Ministry of Agriculture (REGA, now RIIA-SITRAN) is published only by autonomous community.
The Censo Agrario 2020 counts the equines of every agricultural holding by comarca (table 51175, «8 Equinos», heads);
holdings that keep only equines are not in the census (equines have no livestock-unit coefficient), so it counts
239,990 head against REGA's 639,000: the horses of the countryside, without riding centres and leisure horses. Which
municipalities make up each comarca comes from table 75479 (any Censo Agrario table published down to municipalities).
"""

from __future__ import annotations

from ...core.source import Source, SourceInfo
from .ine import LICENSE, TPX_CSV, number, read_rows, split_geo

TABLES = {"equines": 51175, "municipalities": 75479}
# The row of table 51175 with a comarca's equine heads: kind, holder, measure and datum.
EQUINE_HEADS = ("8 Equinos", "Todas las personalidades jurídicas", "Cabezas", "Valor")


class IneCensoAgrario(Source):
    info = SourceInfo(
        id="ine_censo_agrario",
        title="Censo Agrario 2020: equine heads by agricultural comarca (table 51175) and the comarca of every "
        "municipality (table 75479)",
        publisher="Instituto Nacional de Estadística (INE)",
        homepage="https://www.ine.es/jaxi/Tabla.htm?tpx=51175&L=0",
        license=LICENSE,
        description="Equine heads (horses, mules and donkeys) on agricultural holdings in 2020, by the INE's agricultural "
        "comarcas, and the municipalities of each comarca. Holdings with only equines are not in the census.",
        used_for=["Horses of the Unciv map"],
    )

    def fetch(self, force=False):
        for table in TABLES.values():
            self.download(TPX_CSV.format(table=table), f"{table}.csv", force=force)

    def process(self):
        equines = {}
        for row in read_rows(self.raw_dir / f"{TABLES['equines']}.csv"):
            if len(row) < 6 or tuple(row[1:5]) != EQUINE_HEADS:
                continue
            code, name = split_geo(row[0])
            if code and len(code) == 4:
                equines[code] = {"name": name, "heads": number(row[5])}
        comarca_of = {}
        for row in read_rows(self.raw_dir / f"{TABLES['municipalities']}.csv"):
            if len(row) >= 5 and row[3] and row[4]:
                comarca_of[split_geo(row[4])[0]] = split_geo(row[3])[0]
        missing = set(comarca_of.values()) - set(equines)
        if missing or len(equines) < 300:
            raise RuntimeError(f"Censo Agrario: {len(equines)} comarcas with equines; no row for {sorted(missing)}")
        return {"vintage": "Censo Agrario 2020 (INE)", "_files": [f"{t}.csv" for t in TABLES.values()],
                "comarcas": equines, "comarca_of": comarca_of}
