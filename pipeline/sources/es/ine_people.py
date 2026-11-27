"""INE municipal indicators of people and prosperity: age, birthplace, education, poverty, home ownership.

* ADRH indicator tables (Atlas de Distribución de Renta de los Hogares, like table 30824 in ine.py): one row per
  municipality, district or census section; the municipal rows have the district and section columns empty.
* Annual Population Census tables by census section (ine.CensoSecciones, like table 66594): Spain, provinces, municipalities
  and sections in one export, read in a stream.
* The 2021 Population and Housing Census's indicators by census section (one CSV), summed up to municipalities.
"""

from __future__ import annotations

import csv

from ...core.source import Source, SourceInfo
from .ine import CSV, LICENSE, CensoSecciones, number, read_rows, split_geo, stream_rows
from .provinces import PROVINCES

COMPLETE = 0.9  # a year counts as published when it has at least this share of the best year's municipalities


def latest_complete(by_year: dict[str, dict]) -> str:
    """The latest year with (nearly) as many municipalities as the most complete one: a year INE is still filling in
    (or that lacks a series) is not taken."""
    best = max(len(v) for v in by_year.values())
    return max(y for y, v in by_year.items() if len(v) >= COMPLETE * best)


class IneAdrhIndicadores(Source):
    """Two ADRH tables, one indicator taken from each: the mean age (demographic indicators, from the Annual Population
    Census) and the share of people below 60 % of the national median income per consumption unit."""

    info = SourceInfo(
        id="ine_adrh_indicadores",
        title="Household income distribution atlas (ADRH): demographic indicators (table 30832) and relative income "
        "thresholds (table 30829)",
        publisher="Instituto Nacional de Estadística (INE)",
        homepage="https://www.ine.es/dyngs/INEbase/es/operacion.htm?c=Estadistica_C&cid=1254736177088&menu=ultiDatos&idp=1254735976608",
        license=LICENSE,
        description="For every municipality: the mean age of its residents (table 30832, which ADRH takes from the Annual "
        "Population Census, published for all municipalities) and the share of residents whose income per consumption "
        "unit (modified OECD scale) is below 60% of the national median (table 30829, both sexes; the median is "
        "Spain's, all tax territories included, since ADRH 2023). Small municipalities can lack the income indicator "
        "(statistical confidentiality); they stay without data.",
        used_for=["Mean age lens", "Relative poverty lens"],
    )
    TABLES = {"mean_age": (30832, "Edad media de la población", 1),
              "poverty": (30829, "Población con ingresos por unidad de consumo por debajo 60% de la mediana", 0.01)}

    def _file(self, table: int) -> str:
        return f"{table}.csv"

    def fetch(self, force=False):
        for table, _, _ in self.TABLES.values():
            self.download(CSV.format(table=table), self._file(table), force=force)

    def read(self, table: int, indicator: str, scale: float) -> tuple[str, dict[str, float]]:
        """(year, {municipality: value}) of one indicator: municipal rows only, both sexes where the table splits them."""
        by_year: dict[str, dict[str, float]] = {}
        for row in stream_rows(self.raw_dir / self._file(table)):  # with every census section: about 1 GB
            if len(row) < 6 or row[1].strip() or row[2].strip():
                continue  # census districts and sections
            *filters, label, year, value = row[3:]
            if label.strip() != indicator or any(f.strip() != "Total" for f in filters):
                continue
            code, v = split_geo(row[0])[0], number(value)
            if code and len(code) == 5 and v is not None:
                by_year.setdefault(year.strip(), {})[code] = round(v * scale, 6)
        if not by_year:
            raise RuntimeError(f"{self.id}: no {indicator!r} rows in table {table}")
        year = latest_complete(by_year)
        return year, by_year[year]

    def process(self):
        years, values = {}, {}
        for key, args in self.TABLES.items():
            years[key], values[key] = self.read(*args)
        return {
            "vintage": "INE Atlas de Distribución de Renta de los Hogares, " + ", ".join(sorted(set(years.values()))),
            "_files": [self._file(t) for t, _, _ in self.TABLES.values()],
            "years": {k: int(y) for k, y in years.items()},
            **values,
        }


class IneCensoNacimiento(CensoSecciones):
    info = SourceInfo(
        id="ine_censo_nacimiento",
        title="Annual Population Census: population by sex and place of birth (Spain/abroad), table 65031",
        publisher="Instituto Nacional de Estadística (INE)",
        homepage="https://www.ine.es/jaxiT3/Tabla.htm?t=65031",
        license=LICENSE,
        description="Residents born in Spain and abroad, for Spain, every province and every municipality (and census "
        "sections, not used here), from the Annual Population Census, which INE builds from the Padrón and other "
        "registers. Born abroad is a place of birth, not a nationality: Spaniards born abroad count, foreigners born in "
        "Spain do not.",
        used_for=["Born abroad lens"],
    )
    TABLE = 65031
    CATEGORIES = {"Extranjero": "abroad"}


def ages_from(counts: dict, start: int) -> int:
    """Residents aged `start` and over, of a place's census counts by age (IneCensoEdad: each age group keyed by the
    age it starts at, beside "total")."""
    return sum(n for k, n in counts.items() if k != "total" and int(k) >= start)


class IneCensoEdad(CensoSecciones):
    """Residents aged 65 and over by five-year group, and every resident, from the census by section (table 65034).
    Table 1488 (share of the population over each age, by province) checks it: the provinces' shares of 85+ and 100+
    worked out here must be INE's, to its two decimals."""

    info = SourceInfo(
        id="ine_censo_edad",
        title="Annual Population Census: population by sex and age (five-year groups), table 65034, checked against "
        "table 1488",
        publisher="Instituto Nacional de Estadística (INE)",
        homepage="https://www.ine.es/jaxiT3/Tabla.htm?t=65034",
        license=LICENSE,
        description="Residents of every age group from 65 (65–69, 70–74 … 95–99, 100 and over) and all residents, for "
        "Spain, every province and every municipality (and census sections, not used here), from the Annual "
        "Population Census, which INE builds from the Padrón and other registers. Where people live, not where they "
        "were born: someone in a care home counts in the municipality of the home. INE publishes every municipality, "
        "with no cell hidden. The provinces' shares of residents aged 85 and over and 100 and over are checked against "
        "INE's own (Indicadores Demográficos Básicos, table 1488).",
        used_for=["Oldest old lens", "Centenarians lens", "Longevity zones", "Unciv: the longevity trait"],
    )
    TABLE = 65034
    CHECK_TABLE = 1488  # share of the population over a given age, by province (Indicadores Demográficos Básicos)
    TOTAL_LABEL = "Todas las edades"
    CATEGORIES = {**{f"De {a} a {a + 4} años": str(a) for a in range(65, 100, 5)}, "100 y más años": "100"}
    TOPIC = "Sexo y edad"
    CHECKED = {85: "85 y más años", 100: "100 y más años"}  # the groups from this age up → table 1488's label
    TOLERANCE = 0.01  # percentage points: table 1488 rounds to two decimals

    def fetch(self, force=False):
        super().fetch(force)
        self.download(CSV.format(table=self.CHECK_TABLE), f"{self.CHECK_TABLE}.csv", force=force)

    def process(self):
        out = super().process()
        year = str(out["year"])
        published = {}
        for geo, age, period, value in (r[:4] for r in read_rows(self.raw_dir / f"{self.CHECK_TABLE}.csv") if len(r) >= 4):
            code, v = split_geo(geo)[0], number(value)
            if period.strip() == year and code in PROVINCES and v is not None:
                published[(code, age.strip())] = v
        for code in PROVINCES:
            counts = out["provinces"][code]
            for start, label in self.CHECKED.items():
                ours = 100 * ages_from(counts, start) / counts["total"]
                theirs = published.get((code, label))
                if theirs is None or abs(ours - theirs) > self.TOLERANCE:
                    raise RuntimeError(f"{self.id} {year}: province {code} has {ours:.3f} % aged {label!r} in table "
                                       f"{self.TABLE}, {theirs} % in table {self.CHECK_TABLE}")
        out["_files"].append(f"{self.CHECK_TABLE}.csv")
        return out


class IneCensoFormacion(CensoSecciones):
    info = SourceInfo(
        id="ine_censo_formacion",
        title="Annual Population Census: population aged 15 and over by sex and educational attainment (grouped), "
        "table 66592",
        publisher="Instituto Nacional de Estadística (INE)",
        homepage="https://www.ine.es/jaxiT3/Tabla.htm?t=66592",
        license=LICENSE,
        description="Residents aged 15 and over by the highest level of education completed (primary or less, lower "
        "secondary, upper secondary and post-secondary non-tertiary, higher education), for Spain, every province and "
        "every municipality (and census sections, not used here), from the Annual Population Census. Higher education "
        "covers higher vocational training (técnico superior) as well as university degrees. INE publishes the age "
        "breakdown only for municipalities of 500 residents or more, so the map uses everyone aged 15 and over.",
        used_for=["Higher education lens"],
    )
    TABLE = 66592
    CATEGORIES = {"Educación superior": "higher"}


class IneCenso2021Indicadores(Source):
    """The 2021 census's indicator file by census section: counts of main dwellings by tenure (t20_1 owned, t20_2
    rented, t20_3 other), summed over each municipality's sections. Sections INE leaves blank (statistical
    confidentiality: the smallest municipalities, usually a single section) do not count; a municipality with no
    section published has no figure."""

    info = SourceInfo(
        id="ine_censo2021_indicadores",
        title="2021 Population and Housing Census: indicators by census section (main dwellings by tenure)",
        publisher="Instituto Nacional de Estadística (INE)",
        homepage="https://www.ine.es/censos2021/",
        license=LICENSE,
        description="Main (primary-residence) dwellings by tenure (owned, rented, other) of every census section on 1 "
        "January 2021, from the indicator file of the 2021 Population and Housing Census, added up to municipalities. "
        "INE leaves out the sections of the smallest municipalities (statistical confidentiality) and calls the file "
        "provisional because some dwellings are being moved to their right section, which does not change a "
        "municipality's total.",
        used_for=["Homeowners lens"],
    )
    URL = "https://www.ine.es/censos2021/C2021_Indicadores.csv"
    FILE = "C2021_Indicadores.csv"
    TENURE = {"t20_1": "owned", "t20_2": "rented", "t20_3": "other"}

    def fetch(self, force=False):
        self.download(self.URL, self.FILE, force=force)

    def process(self):
        munis: dict[str, dict[str, int]] = {}
        with open(self.raw_dir / self.FILE, encoding="utf-8-sig", newline="") as f:
            rows = csv.DictReader(f)
            if not set(self.TENURE) <= set(rows.fieldnames or []):
                raise RuntimeError(f"{self.FILE}: no tenure columns {sorted(self.TENURE)}")
            for r in rows:
                if any(not (r[k] or "").strip() for k in self.TENURE):
                    continue  # a confidential section
                m = munis.setdefault(r["cpro"] + r["cmun"], dict.fromkeys(self.TENURE.values(), 0))
                for col, key in self.TENURE.items():
                    m[key] += int(float(r[col]))
        unknown = sorted({c[:2] for c in munis} - set(PROVINCES))
        if unknown or len(munis) < 5000:
            raise RuntimeError(f"{self.FILE}: {len(munis)} municipalities, unknown provinces {unknown}")
        return {"vintage": "INE Censos de Población y Viviendas 2021, 1 January 2021", "_files": [self.FILE],
                "year": 2021, "municipalities": dict(sorted(munis.items()))}
