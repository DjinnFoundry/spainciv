"""Known criminal offences by type: the Ministerio del Interior's Balance de Criminalidad, from its Portal Estadístico
de Criminalidad (estadisticasdecriminalidad.ses.mir.es), which publishes each quarter's balance as PC-Axis tables
with keyless CSV exports.

The fourth quarter's balance is the whole year (January to December). Two of its tables are read: provinces (with Spain
and the offences committed abroad) and "municipalities over 20,000 inhabitants and islands", which also repeats the
communities and provinces. Each quarter has its own table numbers: the latest full year's are those of the
"Cuarto trimestre" link of the balances page (`INDEX`), listed by the page its iframe opens.
"""

from __future__ import annotations

import re

from ...core.source import Source, SourceInfo
from .food import ISLANDS
from .ine import number, read_rows, split_geo
from .provinces import PROVINCES

INDEX = "https://estadisticasdecriminalidad.ses.mir.es/publico/portalestadistico/balances.html"
CSV = "https://estadisticasdecriminalidad.ses.mir.es/sec/jaxiPx/files/_px/es/csv_bdsc/DatosBalanceAnt/l0/{table}.csv_bdsc?nocab=1"
# Balance trimestral de criminalidad 2025, 4º trimestre (enero-diciembre 2025), published 21 April 2026.
TABLES = {"provinces": 1509011, "municipalities": 1509012}
TOTAL = "total"
# Offence types of the balance (its own numbering) → key. Its subtotals (conventional crime, cybercrime) and
# sub-types (5.1, 5.2, 7.1) are left out: the numbered types add up to the total.
TYPES = {
    "1": "homicide", "2": "attempted_homicide", "3": "assault", "4": "kidnapping", "5": "sexual",
    "6": "violent_robbery", "7": "burglary", "8": "theft", "9": "vehicle_theft", "10": "drug_trafficking",
    "11": "other", "12": "online_fraud", "13": "other_cyber",
}
ABROAD = "En el extranjero"


def offence_key(label: str) -> str | None:
    """'8. Hurtos' → 'theft', '12.-Estafas informáticas' → 'online_fraud', 'III. TOTAL INFRACCIONES PENALES' → 'total';
    None for a subtotal or a sub-type."""
    if label.strip().startswith("III. TOTAL"):
        return TOTAL
    m = re.match(r"(\d+)\.(?!\d)", label.strip())
    return TYPES.get(m.group(1)) if m else None


def province_name(name: str) -> str:
    """INE's 'Coruña, A' as the balance writes it: 'Coruña (A)'."""
    rest, sep, article = name.rpartition(", ")
    return f"{rest} ({article})" if sep else name


PROVINCE_CODE = {province_name(name): code for code, (_, name) in PROVINCES.items()}


def island_name(label: str) -> str | None:
    """'Isla de Gomera (La)' → 'La Gomera', 'Isla  de Eivissa' → 'Eivissa' (the names of food.ISLANDS); None for a row
    that is no island."""
    m = re.match(r"Isla\s+de\s+(.+?)(?:\s+\((\w+)\))?$", label.strip())
    if not m:
        return None
    name = f"{m.group(2)} {m.group(1)}" if m.group(2) else m.group(1)
    if name not in ISLANDS:
        raise RuntimeError(f"balance de criminalidad: unknown island {label!r}")
    return name


class BalanceCriminalidad(Source):
    info = SourceInfo(
        id="balance_criminalidad",
        title="Balance de Criminalidad, fourth quarter (January to December): known criminal offences by type, for "
        "provinces, islands and municipalities over 20,000 inhabitants",
        publisher="Ministerio del Interior, Secretaría de Estado de Seguridad (Portal Estadístico de Criminalidad)",
        homepage=INDEX,
        license="Public-sector information, reuse citing the source (Ley 37/2007)",
        description="Criminal offences known to the police (Policía Nacional, Guardia Civil, Mossos d'Esquadra, "
        "Ertzaintza, Policía Foral de Navarra and the local police forces that report to the Sistema Estadístico de "
        "Criminalidad), by complaint or by the police's own action, in thirteen types (homicide, assault, sexual "
        "offences, robbery, burglary, theft, vehicle theft, drug trafficking, online fraud, other cybercrime, the rest) "
        "and in total. Spain, every province and the offences committed abroad (one table), every island and every "
        "municipality over 20,000 inhabitants (the other). The rest of each province or island is the province or "
        "island minus its listed municipalities.",
        used_for=["Crime lens (known offences per 1,000 inhabitants)", "Crime type above Spain's rate lens"],
    )

    def _file(self, key: str) -> str:
        return f"{TABLES[key]}.csv"

    def files(self) -> list[str]:
        return [self._file(k) for k in TABLES]

    def fetch(self, force=False):
        for key, table in TABLES.items():
            self.download(CSV.format(table=table), self._file(key), force=force)

    def counts(self, key: str) -> tuple[int, dict[str, dict[str, int]]]:
        """(year, {place label: {offence key: count}}) of a table's latest January-to-December period."""
        by_year: dict[int, dict[str, dict[str, int]]] = {}
        for r in read_rows(self.raw_dir / self._file(key)):
            if len(r) < 4:
                continue
            period, offence, value = re.fullmatch(r"enero-diciembre (\d{4})", r[2].strip()), offence_key(r[1]), number(r[3])
            if period and offence and value is not None:
                by_year.setdefault(int(period.group(1)), {}).setdefault(r[0].strip(), {})[offence] = int(value)
        if not by_year:
            raise RuntimeError(f"{self.id}: table {TABLES[key]} has no January-to-December period")
        year = max(by_year)
        return year, by_year[year]

    def process(self):
        year, places = self.counts("provinces")
        muni_year, rows = self.counts("municipalities")
        if muni_year != year:
            raise RuntimeError(f"{self.id}: provinces for {year}, municipalities for {muni_year}")
        provinces = {PROVINCE_CODE[name]: c for name, c in places.items() if name in PROVINCE_CODE}
        missing = sorted(set(PROVINCES) - set(provinces))
        unknown = sorted(set(places) - set(PROVINCE_CODE) - {"Total Nacional", ABROAD})
        if missing or unknown:
            raise RuntimeError(f"{self.id} {year}: provinces missing {missing}, rows not understood {unknown}")
        municipalities: dict[str, dict[str, int]] = {}
        islands: dict[str, dict[str, int]] = {}
        for label, c in rows.items():
            code, _ = split_geo(label)
            if code and len(code) == 5:
                municipalities[code] = c
            elif (island := island_name(label)) is not None:
                islands[island] = c
        if set(islands) != set(ISLANDS) or not municipalities:
            raise RuntimeError(f"{self.id} {year}: islands {sorted(islands)}, {len(municipalities)} municipalities")
        for prov in sorted({seed[:2] for seed in ISLANDS.values()}):
            on_islands = sum(c[TOTAL] for name, c in islands.items() if ISLANDS[name][:2] == prov)
            if on_islands != provinces[prov][TOTAL]:
                raise RuntimeError(f"{self.id} {year}: the islands of {prov} add up to {on_islands}, not "
                                   f"{provinces[prov][TOTAL]}")
        for place, c in [*provinces.items(), *islands.items(), *municipalities.items()]:
            if sum(c.get(k, 0) for k in TYPES.values()) != c.get(TOTAL):
                raise RuntimeError(f"{self.id} {year}: the offence types of {place} do not add up to its total")
        return {
            "vintage": f"Ministerio del Interior, Balance de Criminalidad, 4.º trimestre de {year}",
            "_files": self.files(),
            "year": year,
            "nation": places["Total Nacional"],
            "abroad": places[ABROAD],
            "provinces": dict(sorted(provinces.items())),
            "islands": dict(sorted(islands.items())),
            "municipalities": dict(sorted(municipalities.items())),
        }
