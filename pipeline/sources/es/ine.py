"""INE tables (Instituto Nacional de Estadística), from their keyless "csv_bdsc" exports.

The exports are semicolon-separated with a header row; numbers use Spanish thousands separators ("1.690.012.000")
and an empty value is "" or ".." (not available). The geography column starts with the INE code: "28079 Madrid",
"08 Barcelona", "13 MADRID, COMUNIDAD DE" (autonomous communities are in capitals), or "Total Nacional".
"""

from __future__ import annotations

import csv
import io
import re

from ...core.source import Source, SourceInfo
from .provinces import PROVINCES, display_name

CSV = "https://www.ine.es/jaxiT3/files/t/csv_bdsc/{table}.csv"
LICENSE = ("CC BY 4.0 (INE legal notice): commercial and non-commercial reuse, citing the source as \"Elaboración "
           "propia con datos del INE\"; INE does not endorse this map")

# Autonomous communities with one province: INE publishes their provincial figures only as the community.
UNIPROVINCIAL = {"03": "33", "04": "07", "06": "39", "13": "28", "14": "30", "15": "31", "17": "26", "18": "51", "19": "52"}


def number(text: str) -> float | None:
    t = text.strip().strip('"')
    if t in ("", "..", "."):
        return None
    return float(t.replace(".", "").replace(",", "."))


def read_rows(path) -> list[list[str]]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("iso-8859-15")
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    return rows[1:]


def split_geo(label: str) -> tuple[str | None, str]:
    """'28079 Madrid' → ('28079', 'Madrid'); 'Total Nacional' → (None, 'Total Nacional')."""
    m = re.match(r"(\d+)\s+(.*)", label.strip())
    return (m.group(1), m.group(2)) if m else (None, label.strip())


class IneTable(Source):
    TABLE: int

    def _file(self) -> str:
        return f"{self.TABLE}.csv"

    def fetch(self, force=False):
        self.download(CSV.format(table=self.TABLE), self._file(), force=force)


class InePadron(IneTable):
    info = SourceInfo(
        id="ine_padron",
        title="Official population figures by municipality (Padrón municipal revision), table 29005",
        publisher="Instituto Nacional de Estadística (INE)",
        homepage="https://www.ine.es/jaxiT3/Tabla.htm?t=29005",
        license=LICENSE,
        description="Residents of every municipality on 1 January of each year since 1996, from the yearly revision of "
        "the municipal registers (Padrón). Provinces and Spain are the sums of their municipalities.",
        used_for=["Population", "City size", "Population growth", "Density lens"],
    )
    TABLE = 29005

    def process(self):
        munis: dict[str, dict] = {}
        for geo, sex, year, value in (r[:4] for r in read_rows(self.raw_dir / self._file()) if len(r) >= 4):
            code, name = split_geo(geo)
            if sex.strip() != "Total" or not code or len(code) != 5:
                continue
            m = munis.setdefault(code, {"name": name, "display": display_name(name), "pop": {}})
            v = number(value)
            m["pop"][year.strip()] = int(v) if v is not None else None
        years = sorted({y for m in munis.values() for y in m["pop"]})
        year = max(y for y in years if sum(1 for m in munis.values() if m["pop"].get(y)) > 8000)
        provinces: dict[str, dict] = {}
        nation: dict[str, int] = {}
        for code, m in munis.items():
            prov = provinces.setdefault(code[:2], {"pop": {}})["pop"]
            for y, v in m["pop"].items():
                if v is not None:
                    prov[y] = prov.get(y, 0) + v
                    nation[y] = nation.get(y, 0) + v
        unknown = sorted(set(provinces) - set(PROVINCES))
        if unknown:
            raise RuntimeError(f"table {self.TABLE}: municipality codes in unknown provinces {unknown}")
        return {
            "vintage": f"INE Padrón, 1 January {year}",
            "_files": [self._file()],
            "year": int(year),
            "years": [int(y) for y in years],
            "municipalities": munis,
            "provinces": provinces,
            "nation": nation,
        }


class InePib(IneTable):
    info = SourceInfo(
        id="ine_pib",
        title="GDP at market prices by province, current prices (Contabilidad Regional de España), table 80109",
        publisher="Instituto Nacional de Estadística (INE)",
        homepage="https://www.ine.es/jaxiT3/Tabla.htm?t=80109",
        license=LICENSE,
        description="Gross domestic product at market prices in current euros for Spain, its autonomous communities and "
        "provinces (thousands of euros in the table). The single-province communities (Madrid, Asturias, Cantabria, "
        "Murcia, Navarra, La Rioja, the Balearic Islands, Ceuta and Melilla) appear only as communities and are used as "
        "their province. Spain's total also counts the extra-regional territory (embassies, bases abroad), which no "
        "province has.",
        used_for=["Gold yield (GDP) of provinces and Spain"],
    )
    TABLE = 80109

    def process(self):
        provinces: dict[str, dict[str, float | None]] = {}
        nation: dict[str, float | None] = {}
        for geo, measure, year, value in (r[:4] for r in read_rows(self.raw_dir / self._file()) if len(r) >= 4):
            if measure.strip() != "Valor":
                continue
            v = number(value)
            eur = v * 1000 if v is not None else None
            code, name = split_geo(geo)
            if code is None:
                if name == "Total Nacional":
                    nation[year.strip()] = eur
                continue
            letters = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", name)
            if letters.isupper():  # an autonomous community
                if code in UNIPROVINCIAL:
                    provinces.setdefault(UNIPROVINCIAL[code], {})[year.strip()] = eur
            elif code in PROVINCES:
                provinces.setdefault(code, {})[year.strip()] = eur
        missing = sorted(set(PROVINCES) - set(provinces))
        if missing:
            raise RuntimeError(f"table {self.TABLE}: no GDP for provinces {missing}")
        years = sorted({y for p in provinces.values() for y, v in p.items() if v is not None})
        year = max(y for y in years if all(p.get(y) is not None for p in provinces.values()))
        return {
            "vintage": f"INE Contabilidad Regional de España, {year}",
            "_files": [self._file()],
            "year": int(year),
            "unit": "eur",
            "provinces": {code: p[year] for code, p in sorted(provinces.items())},
            "nation": nation.get(year),
            "series": {code: p for code, p in sorted(provinces.items())},
        }


class IneAdrh(IneTable):
    info = SourceInfo(
        id="ine_adrh",
        title="Household income distribution atlas (ADRH): mean and median income indicators, table 30824",
        publisher="Instituto Nacional de Estadística (INE)",
        homepage="https://www.ine.es/jaxiT3/Tabla.htm?t=30824",
        license=LICENSE,
        description="Net income from the tax records of the Agencia Tributaria and the regional treasuries, matched to the "
        "Padrón, for every municipality (and its census districts and sections, which are not used here). The map uses "
        "the mean net income per person of each municipality, the latest year INE publishes. Small municipalities can be "
        "missing (statistical confidentiality); they stay without data.",
        used_for=["Income lens"],
    )
    TABLE = 30824
    INDICATORS = {"Renta neta media por persona": "net_per_person", "Renta neta media por hogar": "net_per_household"}

    def process(self):
        munis: dict[str, dict[str, dict[str, float]]] = {}
        for row in read_rows(self.raw_dir / self._file()):
            if len(row) < 6 or row[1].strip() or row[2].strip():
                continue  # census districts and sections
            key = self.INDICATORS.get(row[3].strip())
            code, _ = split_geo(row[0])
            v = number(row[5])
            if key and code and len(code) == 5 and v is not None:
                munis.setdefault(code, {}).setdefault(key, {})[row[4].strip()] = v
        years = sorted({y for m in munis.values() for s in m.values() for y in s})
        year = max(y for y in years if sum(1 for m in munis.values() if y in m.get("net_per_person", {})) > 7000)
        return {
            "vintage": f"INE Atlas de Distribución de Renta de los Hogares, {year}",
            "_files": [self._file()],
            "year": int(year),
            "unit": "eur",
            "municipalities": {
                code: {k: s.get(year) for k, s in m.items()} for code, m in sorted(munis.items()) if any(year in s for s in m.values())
            },
        }


class CensoEmpleo(Source):
    """Employed residents by economic activity from INE's Annual Population Census (Ocupación y actividad): a table for
    Spain and its provinces and one for municipalities, read the same way. Subclasses say which tables and which level of
    the CNAE-2009 code (section letter or two-digit division)."""

    TABLES: dict[str, int]  # {"regions": table, "local": table}
    CODE = re.compile(r"")  # the activity code at the start of the label

    def _file(self, table: int) -> str:
        return f"{table}.csv"

    def fetch(self, force=False):
        for table in self.TABLES.values():
            self.download(CSV.format(table=table), self._file(table), force=force)

    def code(self, label: str) -> str | None:
        """The activity code of a label ('Total CNAE' → 'total'; 'No consta' → None)."""
        if label == "Total CNAE":
            return "total"
        m = self.CODE.match(label)
        return m.group(1) if m else None

    def process(self):
        by_year: dict[str, dict[str, dict[str, int]]] = {}  # year → geo → code → people
        titles: dict[str, str] = {}

        def add(year, geo, label, value):
            label = label.strip()
            code, v = self.code(label), number(value)
            if code and v is not None:
                by_year.setdefault(year.strip(), {}).setdefault(geo, {})[code] = int(v)
                if code != "total":
                    titles.setdefault(code, label[len(code):].strip())

        for r in read_rows(self.raw_dir / self._file(self.TABLES["regions"])):
            cols = dict(zip(("nation", "community", "province"), r[:3]))
            label, year, value = r[3], r[-2], r[-1]
            filters = r[4:-2]  # age and/or sex
            if any(f not in ("16 y más años", "Total") for f in filters) or (cols["community"] and not cols["province"]):
                continue  # age bands, one sex, or an autonomous-community row
            code, _ = split_geo(cols["province"]) if cols["province"] else (None, None)
            add(year, code if code else "nation", label, value)
        for r in read_rows(self.raw_dir / self._file(self.TABLES["local"])):
            geo, sex, label, year, value = r[:5]
            code, _ = split_geo(geo)
            if sex == "Total" and code and len(code) == 5:
                add(year, code, label, value)
        year = max(by_year)
        geos = by_year[year]
        if "nation" not in geos:
            raise RuntimeError(f"{self.id} {year}: no national row")
        return {
            "vintage": f"INE Censo anual de población (Ocupación y actividad), 1 January {year}",
            "_files": [self._file(t) for t in self.TABLES.values()],
            "year": int(year),
            "titles": dict(sorted(titles.items())),
            "nation": geos["nation"],
            "provinces": {c: v for c, v in sorted(geos.items()) if len(c) == 2},
            "municipalities": {c: v for c, v in sorted(geos.items()) if len(c) == 5},
        }


class IneCensoOcupados(CensoEmpleo):
    info = SourceInfo(
        id="ine_censo_ocupados",
        title="Annual Population Census: employed residents by CNAE section (tables 69962 and 69992)",
        publisher="Instituto Nacional de Estadística (INE)",
        homepage="https://www.ine.es/jaxiT3/Tabla.htm?t=69992",
        license=LICENSE,
        description="Employed people aged 16 and over by the CNAE-2009 section (A…U) of their job, counted where they live "
        "(like the US map's ACS), from the Annual Population Census (Ocupación y actividad): Spain and the provinces "
        "(table 69962) and every municipality of 500 residents or more (table 69992). The sections are mapped to the map's "
        "industries; 'No consta' (not stated) counts in the total only.",
        used_for=["Food, Production, Science and Culture yields", "Jobs by industry", "Employed residents"],
    )
    TABLES = {"regions": 69962, "local": 69992}
    CODE = re.compile(r"([A-U]) ")

    def process(self):
        out = super().process()
        missing = sorted(set(PROVINCES) - set(out["provinces"]))
        if missing:
            raise RuntimeError(f"{self.id}: no employed residents for provinces {missing}")
        return out


class IneCensoDivisiones(CensoEmpleo):
    info = SourceInfo(
        id="ine_censo_divisiones",
        title="Annual Population Census: employed residents by CNAE division, Spain and main cities (tables 69960 and 69980)",
        publisher="Instituto Nacional de Estadística (INE)",
        homepage="https://www.ine.es/jaxiT3/Tabla.htm?t=69980",
        license=LICENSE,
        description="Employed people aged 16 and over by the two-digit CNAE-2009 division of their job (88 divisions), for "
        "Spain and its provinces (table 69960) and for the provincial capitals and main cities (151 municipalities, table "
        "69980), counted where they live. Used for districts: each city's industry specialisation against the national "
        "share.",
        used_for=["Districts and city types"],
    )
    TABLES = {"regions": 69960, "local": 69980}
    CODE = re.compile(r"(\d\d) ")
