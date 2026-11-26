"""Tourist dwellings by municipality: INE's experimental statistic "Medición del número de viviendas turísticas en
España y su capacidad" (table 39363), which counts the dwellings listed on the big holiday-rental platforms (Airbnb,
Booking, Vrbo), matched to the cadastre, twice a year (February/May and August/November)."""

from __future__ import annotations

from ...core.source import SourceInfo
from .ine import LICENSE, IneTable, number, read_rows, split_geo

MEASURES = {"Viviendas turísticas": "dwellings", "Plazas": "places"}


class IneViviendasTuristicas(IneTable):
    info = SourceInfo(
        id="ine_viviendas_turisticas",
        title="Tourist dwellings and their places by municipality (INE experimental statistic), table 39363",
        publisher="Instituto Nacional de Estadística (INE)",
        homepage="https://www.ine.es/jaxiT3/Tabla.htm?t=39363",
        license=LICENSE,
        description="Dwellings offered as tourist rentals on the main online platforms and their places (beds), by "
        "municipality, from INE's experimental statistic on tourist dwellings (web scraping matched to the cadastre). "
        "The latest period is used; Spain's figure is INE's national total.",
        used_for=["Tourist dwellings lens", "Party index lens"],
    )
    TABLE = 39363

    def process(self):
        rows = read_rows(self.raw_dir / self._file())
        periods = sorted({r[5] for r in rows if len(r) >= 7})
        period = periods[-1]
        munis: dict[str, dict] = {}
        nation: dict[str, float | None] = {}
        for nat, comm, prov, muni, measure, per, value in (r[:7] for r in rows if len(r) >= 7):
            key = MEASURES.get(measure.strip())
            if per != period or key is None:
                continue
            code, _ = split_geo(muni) if muni else (None, "")
            if code and len(code) == 5:
                munis.setdefault(code, {})[key] = number(value)
            elif not comm and not prov and not muni and nat.strip() == "Total Nacional":
                nation[key] = number(value)
        total = sum(m.get("dwellings") or 0 for m in munis.values())
        if not nation.get("dwellings") or abs(total - nation["dwellings"]) > 0.01 * nation["dwellings"]:
            raise RuntimeError(f"table {self.TABLE} {period}: municipalities add up to {total}, Spain {nation}")
        year, month = period.split("M")
        return {"vintage": f"INE viviendas turísticas, {year}-{month}", "_files": [self._file()],
                "period": f"{year}-{month}", "municipalities": munis, "nation": nation}
