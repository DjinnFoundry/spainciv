"""AEMET's ROCIO daily gridded temperature and precipitation, averaged by this map over 1991-2020 for each point and
month.

ROCIO_IBEB covers the peninsula and the Balearic Islands at 0.05° (about 5 km): temperature v1 (Amblar et al. 2020)
and precipitation v2 (Peral, Navascués and Ramos 2017, AEMET Nota técnica 24). ROCIO+_CAN covers the Canary Islands at
0.025°. Neither covers Ceuta or Melilla. The archives hold netCDF classic files (core/netcdf.py): the peninsula one
file a year with a fixed variable, the Canaries several years in a gzipped file with record variables, in kelvin.

For each grid point and month, over every day of that month from 1991 to 2020:

* tmax, tmin: the mean of the daily maximum and minimum (°C);
* prec: the mean of the 30 monthly totals (mm). A day's precipitation is the 07-07 h total dated by the day it starts
  (the archives' README), and each month sums the days its file dates in it;
* frost: the mean number of days a month with a minimum at or below 0 °C.

A point-month with a missing day in any year is null, and a point null in every month is left out. These are this
map's own means of AEMET's daily grids, not AEMET's published normals (the 1 km 1991-2020 normal grids are not
downloadable).
"""

from __future__ import annotations

import gzip
import tarfile
from array import array
from bisect import bisect_right
from datetime import date, datetime, timedelta

from ...core.netcdf import open_nc
from ...core.source import Source, SourceInfo

BASE = ("https://www.aemet.es/documentos/es/serviciosclimaticos/cambio_climat/datos_diarios/dato_observacional/"
        "rejilla_5km/")
FIRST, LAST = 1991, 2020
DECADES = ["1990a1999", "2000a2009", "2010a2019"]
# region → variable → archive paths under BASE
ARCHIVES = {
    "ibeb": {
        "tmax": [f"temperatura/v1/tmax/Serie_AEMET_v1_tmax_{p}_netcdf.tar.gz" for p in DECADES + ["2020"]],
        "tmin": [f"temperatura/v1/tmin/Serie_AEMET_v1_tmin_{p}_netcdf.tar.gz" for p in DECADES + ["2020"]],
        "prec": [f"v2/Serie_AEMET_v2_pcp_{p}_netcdf.tar.gz" for p in DECADES + ["2020"]],
    },
    "can": {
        "tmax": [f"rocio_can/tmax/Rejilla_AEMET_ROCIOplus_CAN_v1_tmax_{p}_netcdf.tar.gz" for p in DECADES + ["2020a2022"]],
        "tmin": [f"rocio_can/tmin/Rejilla_AEMET_ROCIOplus_CAN_v1_tmin_{p}_netcdf.tar.gz" for p in DECADES + ["2020a2022"]],
        "prec": [f"rocio_can/pcp/Rejilla_AEMET_ROCIOplus_CAN_v1_pcp_{p}_netcdf.tar.gz"
                 for p in ["1990a1994", "1995a1999", "2000a2004", "2005a2009", "2010a2014", "2015a2019", "2020a2022"]],
    },
}
SPACING_KM = {"ibeb": 5.5, "can": 2.8}  # 0.05° and 0.025° of latitude, rounded
FROST_C = 0.0  # a frost day: minimum at or below this
KELVIN = 273.15


def local(path: str) -> str:
    """The archive's file in data/raw/aemet_rocio: the path under BASE, flattened."""
    return path.replace("/", "_")


def days_since(units: str) -> date:
    """'days since 1990-1-1 06:00:00' → date(1990, 1, 1)."""
    head = units.split("since", 1)[1].strip().split()[0]
    return datetime.strptime(head, "%Y-%m-%d").date()


def month_spans(dates: list[date]) -> dict[tuple[int, int], tuple[int, int]]:
    """(year, month) → (first, end) step indices of a run of consecutive dates, for the years FIRST-LAST."""
    spans: dict[tuple[int, int], list[int]] = {}
    for k, d in enumerate(dates):
        if not FIRST <= d.year <= LAST:
            continue
        s = spans.get((d.year, d.month))
        if s is None:
            spans[(d.year, d.month)] = [k, k + 1]
        elif k == s[1]:
            s[1] = k + 1
        else:
            raise ValueError(f"{d}: the steps of a month are not consecutive")
    return {key: (a, z) for key, (a, z) in spans.items()}


class Accumulator:
    """Per point and month, over the years: sums and day counts of one variable, nulling a point-month with a
    missing day (or a short month)."""

    def __init__(self, n: int, kind: str):
        self.n, self.kind = n, kind
        self.total = [[0.0] * n for _ in range(12)]
        self.frost = [[0] * n for _ in range(12)] if kind == "tmin" else None
        self.days = [0] * 12  # days added per month
        self.years = [set() for _ in range(12)]
        self.bad = [set() for _ in range(12)]  # points with a missing day
        self._alive, self._dead = None, []

    def add_month(self, data, a: int, z: int, year: int, month: int, missing: float, alive: list[int] | None = None,
                  offset: float = 0.0) -> None:
        """Steps a..z (one month of one year) of `data`, n values a step. Only the `alive` points are read (the
        others are missing throughout the file: the sea around a masked grid)."""
        n, m = self.n, month - 1
        days = z - a
        if days != (date(year + month // 12, month % 12 + 1, 1) - date(year, month, 1)).days:
            raise ValueError(f"{year}-{month:02d}: {days} days in the file")
        if year in self.years[m]:
            raise ValueError(f"{year}-{month:02d} read twice")
        self.years[m].add(year)
        self.days[m] += days
        total, bad = self.total[m], self.bad[m]
        frost = self.frost[m] if self.frost is not None else None
        limit = FROST_C - offset
        if alive is None:
            alive = range(n)
        elif alive is not self._alive:  # a new block: the points missing throughout it
            live = set(alive)
            self._alive, self._dead = alive, [i for i in range(n) if i not in live]
        if alive is self._alive:
            bad.update(self._dead)
        for i in alive:
            s = data[a * n + i:z * n:n]
            if missing in s:
                bad.add(i)
                continue
            total[i] += sum(s) + offset * days
            if frost is not None:
                frost[i] += bisect_right(sorted(s), limit)

    def result(self) -> dict[str, list[list[float | None]]]:
        """{name: [12][n]}: tmax/tmin → mean °C; prec → mean monthly total; tmin also frost → mean days a month."""
        years = FIRST, LAST
        for m in range(12):
            if self.years[m] != set(range(years[0], years[1] + 1)):
                raise ValueError(f"month {m + 1}: years {sorted(set(range(years[0], years[1] + 1)) - self.years[m])} "
                                 "missing")
        nyears = LAST - FIRST + 1
        out = {"prec" if self.kind == "prec" else self.kind: [
            [None if i in self.bad[m] else round((t / nyears if self.kind == "prec" else t / self.days[m]), 1)
             for i, t in enumerate(self.total[m])] for m in range(12)]}
        if self.frost is not None:
            out["frost"] = [[None if i in self.bad[m] else round(f / nyears, 1) for i, f in enumerate(self.frost[m])]
                            for m in range(12)]
        return out


def grid_var(nc) -> str:
    """The data variable: the one 4-D variable (time, height, y, x)."""
    found = [v.name for v in nc.vars.values() if len(v.dims) == 4]
    if len(found) != 1:
        raise ValueError(f"expected one 4-D variable, found {found}")
    return found[0]


def lon_lat(nc) -> tuple[list[float], list[float]]:
    """Longitude and latitude of each point, in the variable's (y, x) order: 2-D arrays on the rotated grid, or the
    regular grid's 1-D axes crossed."""
    lon, lat = nc.read("lon"), nc.read("lat")
    if len(nc.vars["lon"].dims) == 2:
        return list(lon), list(lat)
    return [x for _ in lat for x in lon], [y for y in lat for _ in lon]


def step_dates(times, units: str) -> list[date]:
    start = days_since(units)
    return [start + timedelta(days=int(t // 1)) for t in times]


def alive(data, n: int, missing: float) -> list[int]:
    """The points with at least one value in a block of steps."""
    steps = len(data) // n
    return [i for i in range(n) if data[i::n].count(missing) < steps]


def read_member(acc: Accumulator, nc, var: str, kind: str, kelvin: bool) -> None:
    """One netCDF file's months of FIRST-LAST into `acc`."""
    v = nc.vars[var]
    missing = float(v.attrs.get("missing_value", v.attrs.get("_FillValue", -9999.0)))
    offset = -KELVIN if kelvin else 0.0
    if not v.record:
        dates = step_dates(nc.read("time"), nc.vars["time"].attrs["units"])
        data = nc.read(var)
        flush(acc, data, dates, missing, offset)
        return
    # Record variables (the Canaries): a year's steps at a time, so a decade is never held whole.
    units = nc.vars["time"].attrs["units"]
    start = days_since(units)
    year, buf, dates = None, array("f"), []
    for t, values in nc.iter_records("time", var):
        d = start + timedelta(days=int(t[0] // 1))
        if d.year != year:
            flush(acc, buf, dates, missing, offset)
            year, buf, dates = d.year, array("f"), []
        if FIRST <= d.year <= LAST:
            buf.extend(values)
            dates.append(d)
    flush(acc, buf, dates, missing, offset)


def flush(acc: Accumulator, data, dates: list[date], missing: float, offset: float) -> None:
    """The months of FIRST-LAST in a block of consecutive steps (a file, or a year of one)."""
    spans = month_spans(dates)
    if not spans:
        return
    live = alive(data, acc.n, missing)
    for (y, m), (a, z) in sorted(spans.items()):
        acc.add_month(data, a, z, y, m, missing, live, offset)


def members(path):
    """The netCDF files of an archive, in name order: (name, file object). A gzipped member is streamed."""
    with tarfile.open(path, "r:gz") as tar:
        for info in sorted((i for i in tar.getmembers() if i.isfile() and ".nc" in i.name), key=lambda i: i.name):
            f = tar.extractfile(info)
            yield info.name, (gzip.GzipFile(fileobj=f) if info.name.endswith(".gz") else f)


class AemetRocio(Source):
    info = SourceInfo(
        id="aemet_rocio",
        title="ROCIO daily gridded temperature and precipitation (AEMET), 1991-2020 means",
        publisher="Agencia Estatal de Meteorología (AEMET)",
        homepage="https://www.aemet.es/es/serviciosclimaticos/cambio_climat/datos_diarios?w=1&w2=0",
        license="AEMET Nota legal: reuse allowed citing AEMET as the author (Ley 37/2007 as amended by Ley 18/2015)",
        description="AEMET's daily grids of maximum and minimum temperature (ROCIO_IBEB v1) and precipitation (v2), "
        "0.05° over the peninsula and the Balearics, and ROCIO+_CAN at 0.025° over the Canary Islands, averaged by "
        "spainciv for each point and month over 1991-2020: mean maximum and minimum, mean monthly rainfall and mean "
        "days with a minimum at or below 0 °C. Method: AEMET Nota técnica 24 (Peral, Navascués and Ramos 2017) and "
        "Amblar et al. (2020).",
        used_for=["Climate this month (temperature, rainfall, frost days)"],
    )

    def fetch(self, force=False):
        for by_var in ARCHIVES.values():
            for paths in by_var.values():
                for p in paths:
                    self.download(BASE + p, local(p), force=force, expect_binary=True)

    def process(self):
        regions, files = {}, []
        for region, by_var in ARCHIVES.items():
            out, coords = {}, None
            for kind, paths in by_var.items():
                acc = None
                for p in paths:
                    files.append(local(p))
                    for name, f in members(self.raw_dir / local(p)):
                        nc = open_nc(f)
                        var = grid_var(nc)
                        if acc is None:
                            coords = coords or lon_lat(nc)
                            acc = Accumulator(len(coords[0]), kind)
                        read_member(acc, nc, var, kind, nc.vars[var].attrs.get("units") == "K")
                out |= acc.result()
            keep = [i for i in range(len(coords[0])) if any(out[k][m][i] is not None for k in out for m in range(12))]
            regions[region] = {"lon": [round(coords[0][i], 4) for i in keep], "lat": [round(coords[1][i], 4) for i in keep],
                               **{k: [[v[m][i] for m in range(12)] for i in keep] for k, v in out.items()},
                               "spacing_km": SPACING_KM[region]}
            nulls = sum(v[m][i] is None for v in out.values() for m in range(12) for i in keep)
            print(f"    {region}: {len(keep)} grid points, {nulls} point-month values null (a missing day)")
        return {"vintage": f"{FIRST}-{LAST}", "regions": regions, "_files": files}
