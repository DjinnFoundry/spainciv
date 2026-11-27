"""WMO Climatological Standard Normals 1991-2020 of AEMET's 83 stations (AEMET's submission, archived by NCEI).

NCEI accession 0253808, version 6.6, keeps one CSV per station: a header with its name, WMO number, position and
height, then one block per parameter with a row per calculation and the 12 months. The parameters used here:

    1 precipitation (Sum, mm)          3 mean maximum (Mean, °C)      4 mean minimum (Mean, °C)
    5 mean temperature (Mean, °C)      8 sunshine (Sum, hours)        15 days with a minimum below 0 °C (Count)

Seven stations have no sunshine. The WMO header's position is wrong for some stations (Murcia's longitude is that of
another place), so a station takes its name and position from its own AEMET page when the committed table
data/aemet_estaciones_omm.csv gives it an indicativo; Rota, which has no AEMET page, keeps the header's position and
takes the table's `nombre` ("Rota, Base Naval") for its abbreviated header name. AEMET calls one station "Estación de
Tortosa (Roquetes)": the leading "Estación de" is dropped, as the tooltip already says "Estación".
"""

from __future__ import annotations

import csv
import html
import io
import json
import re
from pathlib import Path

from ...core.source import Source, SourceInfo

INDEX = ("https://www.ncei.noaa.gov/data/oceans/archive/arc0216/0253808/6.6/data/0-data/Region-6-WMO-Normals-9120/"
         "Spain/CSV/")
STATION_PAGE = "https://www.aemet.es/es/serviciosclimaticos/datosclimatologicos/valoresclimatologicos?l={}"
TABLE = Path(__file__).parent / "data" / "aemet_estaciones_omm.csv"
LISTING = "csv_files.json"  # the CSV names found in the index, so --offline needs no request
# key → (parameter code, calculation name)
PARAMS = {"prec": ("1", "Sum"), "tmax": ("3", "Mean"), "tmin": ("4", "Mean"), "tmean": ("5", "Mean"),
          "sun": ("8", "Sum"), "frost_lt0": ("15", "Count")}
REQUIRED = ["prec", "tmax", "tmin", "tmean", "frost_lt0"]
MISSING = {"", "-9999", "-9999.0", "-9999.000000"}
PAGE_COORDS = re.compile(r"Altitud \(m\) : (\d+) .*?Latitud : (\d+)° (\d+)' (\d+)'' (N|S) - "
                         r"Longitud : (\d+)° (\d+)' (\d+)'' (E|O)")
PAGE_NAME = re.compile(r"Estación : (.+?) - ")
NAME_PREFIX = re.compile(r"^Estación(?: de)?\s+", re.IGNORECASE)  # "Estación de Tortosa (Roquetes)"


def dms(d, m, s, hemi: str) -> float:
    v = int(d) + int(m) / 60 + int(s) / 3600
    return round(-v if hemi in "WOS" else v, 5)


def wmo_number(s: str) -> str:
    return s.strip().zfill(5)


def parse_station(text: str) -> dict:
    """One NCEI CSV → {wmo, name, lon, lat, alt, prec, tmax, …: [12] | None}. A parameter is None unless all 12 months
    are given."""
    lines = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    name = next(l[1] for l in lines if l and l[0] == "Station_Name").strip()
    k = next(i for i, l in enumerate(lines) if l and l[0] == "WMO_Number")
    num, lat, lon, alt = lines[k + 1][:4]
    out = {"wmo": wmo_number(num), "name": name, "lon": dms(*lon.split("|")), "lat": dms(*lat.split("|")),
           "alt": round(float(alt))}
    want = {v: key for key, v in PARAMS.items()}
    for l in lines:
        if len(l) >= 16 and l[0].strip().isdigit() and (l[1], l[2]) in want:
            vals = [v.strip() for v in l[4:16]]
            out[want[(l[1], l[2])]] = None if any(v in MISSING for v in vals) else [float(v) for v in vals]
    for key in PARAMS:
        out.setdefault(key, None)
    return out


def parse_page(text: str) -> dict:
    """An AEMET station page → {name, lon, lat, alt}."""
    flat = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text)))
    m, n = PAGE_COORDS.search(flat), PAGE_NAME.search(flat)
    if not m or not n:
        raise ValueError("no station name or coordinates on the AEMET page")
    return {"name": NAME_PREFIX.sub("", n.group(1).strip()), "alt": int(m.group(1)), "lat": dms(*m.group(2, 3, 4, 5)),
            "lon": dms(*m.group(6, 7, 8, 9))}


def read_table(path: Path = TABLE) -> dict[str, dict]:
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(line for line in f if not line.startswith("#")))
    out = {wmo_number(r["wmo"]): {"aemet": r["indicativo"] or None, "province": r["provincia_ine"],
                                  "name": r["nombre"] or None} for r in rows}
    if len(out) != len(rows):
        raise ValueError(f"{path.name}: a WMO number twice")
    return out


def station(wmo: dict, page: dict | None, row: dict) -> dict:
    """A station's normals with the name and position of its AEMET page when it has one; without one, the table's
    name, else the WMO header's without quotes and in title case."""
    if missing := [k for k in REQUIRED if wmo[k] is None]:
        raise ValueError(f"{wmo['wmo']} {wmo['name']}: no 12 months of {missing}")
    place = page or wmo
    name = page["name"] if page else row.get("name") or wmo["name"].strip(" '\"").title()
    return {"wmo": wmo["wmo"], "aemet": row["aemet"], "province": row["province"], "name": name,
            "lon": place["lon"], "lat": place["lat"], "alt": place["alt"], "coords": "aemet" if page else "wmo",
            **{k: wmo[k] for k in ["tmean", "tmax", "tmin", "prec", "frost_lt0", "sun"]}}


class OmmNormalesEs(Source):
    info = SourceInfo(
        id="omm_normales_es",
        title="WMO Climatological Standard Normals 1991-2020, Spain (AEMET, via NCEI accession 0253808 v6.6)",
        publisher="Agencia Estatal de Meteorología (AEMET); archived by NOAA NCEI for the WMO",
        homepage="https://www.ncei.noaa.gov/archive/accession/0253808",
        license="AEMET Nota legal: reuse allowed citing AEMET as the author (NCEI states no licence on the files)",
        description="The 1991-2020 monthly normals AEMET submitted to the WMO for 83 stations: mean, maximum and minimum "
        "temperature, precipitation, days with a minimum below 0 °C and sunshine hours (76 stations). Station names and "
        "positions from AEMET's own station pages.",
        used_for=["Climate this month (stations, sunshine)"],
    )

    def fetch(self, force=False):
        listing = self.raw_dir / LISTING
        if self.offline and listing.exists():
            names = json.loads(listing.read_text())
        else:
            index = self.download(INDEX, "index.html", force=force or not listing.exists()).read_text(encoding="utf-8")
            names = sorted(set(re.findall(r'href="([A-Z0-9]+_\d+\.csv)"', index)))
            if not names:
                raise RuntimeError("no station CSVs in the NCEI index")
            listing.write_text(json.dumps(names))
        for name in names:
            self.download(INDEX + name, f"csv/{name}", force=force)
        for row in read_table().values():
            if row["aemet"]:
                self.download(STATION_PAGE.format(row["aemet"]), f"aemet/{row['aemet']}.html", force=force)

    def process(self):
        table = read_table()
        names = json.loads((self.raw_dir / LISTING).read_text())
        stations, files = [], ["index.html"]  # the listing the CSV names came from
        for name in names:
            files.append(f"csv/{name}")
            wmo = parse_station((self.raw_dir / "csv" / name).read_text(encoding="utf-8"))
            if wmo["wmo"] not in table:
                raise RuntimeError(f"{wmo['wmo']} {wmo['name']}: not in {TABLE.name}")
            row = table[wmo["wmo"]]
            page = None
            if row["aemet"]:
                files.append(f"aemet/{row['aemet']}.html")
                page = parse_page((self.raw_dir / "aemet" / f"{row['aemet']}.html").read_text(encoding="latin-1"))
            stations.append(station(wmo, page, row))
        if stale := sorted(set(table) - {s["wmo"] for s in stations}):
            raise RuntimeError(f"{TABLE.name} lists stations NCEI no longer has: {stale}")
        print(f"    {len(stations)} stations, {sum(s['sun'] is not None for s in stations)} with sunshine, "
              f"{sum(s['coords'] == 'aemet' for s in stations)} placed by their AEMET page")
        return {"vintage": "1991-2020 (NCEI accession 0253808 v6.6)", "_files": files, "stations": stations}
