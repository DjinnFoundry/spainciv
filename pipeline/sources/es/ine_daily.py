"""INE tables behind the daily-life and longevity lenses: where the employed work (Annual Population Census), life
expectancy at birth and at 65 (Indicadores Demográficos Básicos) and how marriages are celebrated (Movimiento
Natural de la Población).

INE publishes each of them for Spain and every province, and for municipalities only for a list of large ones (the
provincial capitals and main cities). Counts (workers, marriages) also give the rest of each province, the province
minus its listed municipalities; a rate (life expectancy) can't be split that way.
"""

from __future__ import annotations

from collections.abc import Callable

from ...core.source import Source, SourceInfo
from .ine import CSV, LICENSE, PROVINCES, number, read_rows, split_geo
from .provinces import COMMUNITIES


class IneTables(Source):
    TABLES: dict[str, int]

    def _file(self, table: int) -> str:
        return f"{table}.csv"

    def fetch(self, force=False):
        for table in self.TABLES.values():
            self.download(CSV.format(table=table), self._file(table), force=force)

    def rows(self, key: str) -> list[list[str]]:
        return read_rows(self.raw_dir / self._file(self.TABLES[key]))

    def files(self) -> list[str]:
        return [self._file(t) for t in self.TABLES.values()]


Counts = dict[str, dict[str, int]]


def province_of(code: str) -> str:
    return code[:2]


def rest_of_provinces(provinces: Counts, municipalities: Counts, unit_of: Callable[[str], str] = province_of) -> Counts:
    """Each province's counts minus those of its listed municipalities (a negative remainder fails: the tables don't add
    up). `unit_of` names the unit a municipality is in, when the units are not provinces (the islands)."""
    rest = {p: dict(v) for p, v in provinces.items()}
    for code, counts in municipalities.items():
        unit = unit_of(code)
        r = rest.get(unit)
        if r is None:
            raise RuntimeError(f"municipality {code}: no counts for its unit {unit}")
        for k, v in counts.items():
            r[k] = r.get(k, 0) - v
            if r[k] < 0:
                raise RuntimeError(f"{unit}: its listed municipalities have more {k} than it has")
    return rest


def by_level(geos: Counts) -> tuple[Counts, Counts]:
    """(provinces, municipalities) of a year's counts, each sorted by code."""
    ordered = sorted(geos.items())
    return {c: v for c, v in ordered if len(c) == 2}, {c: v for c, v in ordered if len(c) == 5}


class IneLugarTrabajo(IneTables):
    info = SourceInfo(
        id="ine_censo_lugar_trabajo",
        title="Annual Population Census: employed residents by place of work (tables 69968 and 69987)",
        publisher="Instituto Nacional de Estadística (INE)",
        homepage="https://www.ine.es/jaxiT3/Tabla.htm?t=69968",
        license=LICENSE,
        description="Employed people aged 16 and over by where they work against where they live (same municipality, "
        "another municipality of the province, another province of the community, another community, or not known), "
        "from the Annual Population Census, which INE builds from administrative registers: Spain and every province "
        "(table 69968) and the provincial capitals and main cities (151 municipalities, table 69987). It is where people "
        "work, not how long it takes them: INE publishes no travel time for municipalities.",
        used_for=["Commuting lens (employed who work outside their municipality)"],
    )
    TABLES = {"regions": 69968, "cities": 69987}
    PLACES = {
        "Mismo municipio al de residencia": "same", "Distinto municipio de la misma provincia": "province",
        "Distinta provincia de la misma comunidad autónoma": "community", "Otra comunidad autónoma": "other_community",
        "Trabaja pero no hay información sobre el lugar de trabajo": "unknown",
    }

    def process(self):
        by_year: dict[str, Counts] = {}

        def add(year, geo, place, value):
            key, v = self.PLACES.get(place.strip()), number(value)
            if key and v is not None:
                by_year.setdefault(year.strip(), {}).setdefault(geo, {})[key] = int(v)

        for r in self.rows("regions"):
            if (len(r) < 8 or r[3].strip() != "Total CNAE" or r[5].strip() != "Total"
                    or (r[1].strip() and not r[2].strip())):
                continue  # one activity, one sex, or an autonomous community
            add(r[6], split_geo(r[2])[0] if r[2].strip() else "nation", r[4], r[7])
        for r in self.rows("cities"):
            if len(r) < 7 or r[2].strip() != "Total" or r[3].strip() != "Total CNAE" or r[4].strip() != "Total":
                continue
            add(r[5], split_geo(r[0])[0], r[1], r[6])
        year = max(by_year)
        geos = by_year[year]
        provinces, cities = by_level(geos)
        missing = sorted(set(PROVINCES) - set(provinces))
        if "nation" not in geos or missing or not cities:
            raise RuntimeError(f"{self.id} {year}: no national row, no cities or no provinces {missing}")
        return {
            "vintage": f"INE Censo anual de población (Ocupación y actividad), 1 January {year}",
            "_files": self.files(),
            "year": int(year),
            "nation": geos["nation"],
            "provinces": provinces,
            "municipalities": cities,
            "rest_of_province": rest_of_provinces(provinces, cities),
        }


SEXES = {"Ambos sexos": "both", "Hombres": "men", "Mujeres": "women"}


class IneEsperanzaVida(IneTables):
    info = SourceInfo(
        id="ine_esperanza_vida",
        title="Life expectancy at birth and at 65 by province, municipality and autonomous community (Indicadores "
        "Demográficos Básicos, tables 1485, 30687, 1486, 30688, 1415 and 1449)",
        publisher="Instituto Nacional de Estadística (INE)",
        homepage="https://www.ine.es/jaxiT3/Tabla.htm?t=30688",
        license=LICENSE,
        description="Life expectancy at birth, both sexes, for every province (table 1485) and for the municipalities "
        "INE computes it for (about 150 large ones, table 30687); life expectancy at 65, both sexes, men and women, for "
        "every province (table 1486), the same municipalities (table 30688), Spain (table 1415) and the autonomous "
        "communities (table 1449). INE works them out from deaths (Movimiento Natural de la Población) and "
        "population. The map takes the latest year the provincial and municipal tables share; the communities, their "
        "latest year.",
        used_for=["Life expectancy lens", "Life expectancy at 65 lens", "Longevity zones", "Unciv: the longevity trait"],
    )
    TABLES = {"provinces": 1485, "municipalities": 30687, "provinces_65": 1486, "municipalities_65": 30688,
              "nation_65": 1415, "communities_65": 1449}

    def by_year(self, key: str, size: int | None, geo_col: int = 0, sex_col: int = 1) -> dict[str, dict[str, dict]]:
        """year → code → {"both", "men", "women"} of a table: places whose INE code has `size` digits (None: the
        national row, keyed "nation")."""
        out: dict[str, dict[str, dict]] = {}
        for r in (r for r in self.rows(key) if len(r) >= 4):
            sex, year, v = SEXES.get(r[sex_col].strip()), r[2].strip(), number(r[3])
            code = split_geo(r[geo_col])[0] if size else ("nation" if r[geo_col].strip() == "Total Nacional" else None)
            if sex and v is not None and code and (size is None or len(code) == size):
                out.setdefault(year, {}).setdefault(code, {})[sex] = v
        return out

    def at65(self) -> dict:
        prov, muni = self.by_year("provinces_65", 2), self.by_year("municipalities_65", 5)
        nation, comms = self.by_year("nation_65", None), self.by_year("communities_65", 2, geo_col=1, sex_col=0)
        years = [y for y in sorted(set(prov) & set(muni) & set(nation)) if set(PROVINCES) <= set(prov[y])]
        comm_years = [y for y in sorted(comms) if set(COMMUNITIES) <= set(comms[y])]
        if not years or not comm_years:
            raise RuntimeError(f"{self.id}: no year with every province in table 1486, municipalities in table 30688 "
                               "and Spain in table 1415, or none with every community in table 1449")
        year, comm_year = years[-1], comm_years[-1]
        return {"year": int(year), "nation": nation[year]["nation"], "provinces": dict(sorted(prov[year].items())),
                "municipalities": dict(sorted(muni[year].items())), "communities_year": int(comm_year),
                "communities": dict(sorted(comms[comm_year].items()))}

    def process(self):
        levels: dict[str, dict[str, dict[str, float]]] = {"provinces": {}, "municipalities": {}}
        for level, size in (("provinces", 2), ("municipalities", 5)):
            for year, geos in self.by_year(level, size).items():
                levels[level][year] = {code: v["both"] for code, v in geos.items() if "both" in v}
        prov, muni = levels["provinces"], levels["municipalities"]
        years = [y for y in sorted(set(prov) & set(muni)) if set(PROVINCES) <= set(prov[y])]
        if not years:
            raise RuntimeError(f"{self.id}: no year with every province in table 1485 and municipalities in table 30687")
        year = years[-1]
        at65 = self.at65()
        if at65["year"] != int(year):
            raise RuntimeError(f"{self.id}: life expectancy at birth is of {year} and at 65 of {at65['year']}; the "
                               "vintage names one year")
        return {
            "vintage": f"INE Indicadores Demográficos Básicos, {year}",
            "_files": self.files(),
            "year": int(year),
            "provinces": dict(sorted(prov[year].items())),
            "municipalities": dict(sorted(muni[year].items())),
            "at65": at65,
        }


class IneMatrimonios(IneTables):
    info = SourceInfo(
        id="ine_matrimonios",
        title="Marriages by province and main municipalities of residence and form of celebration (MNP, tables 77172 "
        "and 37645)",
        publisher="Instituto Nacional de Estadística (INE)",
        homepage="https://www.ine.es/jaxiT3/Tabla.htm?t=37645",
        license=LICENSE,
        description="Marriages of each year by where the couple lives, civil or religious (INE's tables don't separate "
        "Catholic from other religious marriages), for every province (table 77172) and the main municipalities of "
        "residence (about 150, table 37645), from the Movimiento Natural de la Población.",
        used_for=["Religious weddings lens"],
    )
    TABLES = {"provinces": 77172, "municipalities": 37645}
    FORMS = {"Total": "total", "Matrimonios religiosos": "religious", "Matrimonios civiles": "civil"}

    def process(self):
        by_year: dict[str, Counts] = {}

        def add(geo, month, form, year, value):
            key, v = self.FORMS.get(form.strip()), number(value)
            code = "nation" if geo.strip() == "Total Nacional" else split_geo(geo)[0]
            if month.strip() == "Total" and key and v is not None and code:
                by_year.setdefault(year.strip(), {}).setdefault(code, {})[key] = int(v)

        for geo, *rest in (r[:5] for r in self.rows("provinces") if len(r) >= 5):
            if geo.strip() == "Total Nacional" or len(split_geo(geo)[0] or "") == 2:
                add(geo, *rest)
        for _, mun, *rest in (r[:6] for r in self.rows("municipalities") if len(r) >= 6):
            if mun.strip():
                add(mun, *rest)
        year = max(by_year)
        geos = by_year[year]
        provinces, munis = by_level(geos)
        missing = sorted(set(PROVINCES) - set(provinces))
        if missing or not munis or "nation" not in geos:
            raise RuntimeError(f"{self.id} {year}: no national row, no municipalities or no provinces {missing}")
        return {
            "vintage": f"INE Estadística de Matrimonios (MNP), {year}",
            "_files": self.files(),
            "year": int(year),
            "nation": geos["nation"],
            "provinces": provinces,
            "municipalities": munis,
            "rest_of_province": rest_of_provinces(provinces, munis),
        }
