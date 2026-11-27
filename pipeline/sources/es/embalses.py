"""Spain's reservoirs week by week since 1988: the Boletín Hidrológico's historical database (BD-Embalses, MITECO),
with the positions and basins of the Boletín's own map.

* **BD-Embalses** (a zip holding one Access file, updated every week): one row per reservoir and Tuesday, with its
  basin (ámbito), name, date, capacity and water stored (hm³, as text: "91,00") and whether it is hydroelectric.
  The table's name carries the last year ("T_Datos Embalses 1988-2026"), so it is found by its prefix; exactly one
  table must match. Read with core.mdb from the member extracted once next to the zip.
* **Embalses_Mapa** (the Boletín's ArcGIS point layer): the reservoirs of the latest week, at their position, keyed by
  basin and name exactly as the database writes them.
* **DDHH** (the Boletín's basin layer): the 16 basins as polygons, named exactly as the database's ámbitos, with the
  latest week's water stored and percentage, which must equal the database's sums for that week.

Cleaning (DECISIONS E86): a number must read `^\\d+(,\\d+)?$` (else the process fails); an empty one is null. Rows
before the series' first week (START) are dropped and counted. A reservoir reports in a week when that week has its
row with both numbers; otherwise it counts in neither sum. Each week keeps its own capacity, and values above
capacity are kept as written. The use (hydroelectric or not) is the flag of the reservoir's latest row.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from ...core.fetch import read_manifest
from ...core.mdb import Jet4
from ...core.source import Source, SourceInfo

BOLETIN = "https://www.miteco.gob.es/es/agua/temas/evaluacion-de-los-recursos-hidricos/boletin-hidrologico.html"
_DAM = "https://www.miteco.gob.es/content/dam/miteco/es/agua/temas/evaluacion-de-los-recursos-hidricos/"
ZIP_URL = _DAM + "boletin-hidrologico/Historico-de-embalses/BD-Embalses.zip"
ZIP_FILE = "BD-Embalses.zip"
MDB_FILE = "BD-Embalses.mdb"  # extracted from the zip; never cited, the zip is
MODEL_URL = _DAM + "modelo-de-datos-bd-embalses-1988-2022_tcm30-538818.pdf"
MODEL_FILE = "modelo_de_datos_bd_embalses.pdf"
TABLE_PREFIX = "T_Datos Embalses"
ARCGIS = "https://services-eu1.arcgis.com/RvnYk1PBUJ9rrAuT/arcgis/rest/services/"
POINTS_LAYER = ARCGIS + "Embalses_Mapa/FeatureServer/0/query"
POINTS_FIELDS = "embalse_nombre,ambito_nombre,ambito_id,agua_total,agua_actual,Fecha_str"
POINTS_FILE = "embalses_mapa.json"
BASINS_LAYER = ARCGIS + "DDHH/FeatureServer/0/query"
BASINS_FIELDS = "NOM_DEMAR,Agua,Porc_Agua_Cuenca,Fecha"
BASINS_FILE = "ddhh.json"
START = date(1988, 1, 5)  # the first Tuesday of the series (the data model covers 1988 onwards)
HM3 = re.compile(r"^\d+(,\d+)?$")
HYDRO, CONSUMPTIVE = "hidroelectrico", "consuntivo"


def parse_hm3(text: str | None) -> int | float | None:
    """'91,00' → 91; '' or None → None. Any other format raises (the build must not guess)."""
    if text is None or text.strip() == "":
        return None
    if not HM3.match(text):
        raise ValueError(f"BD-Embalses: {text!r} is not a number of hm³")
    v = Decimal(text.replace(",", "."))
    return int(v) if v == v.to_integral_value() else float(v)


def series(rows, start: date = START) -> dict:
    """The weekly series from the table's rows: {(basin, name, date, capacity text, stored text, flag)}.

    Returns {dates, dropped, reservoirs}: `dates` every Tuesday from the first week on or after `start` to the last
    (they must follow one another a week apart); `dropped` the rows before `start`; per reservoir (by basin and name,
    in the order of their first row) its `use`, `actual` (hm³ per date, null when it does not report), `capacity`
    (runs [date index, hm³], a new run whenever the capacity changes between reporting weeks), `first` and `last`
    (indices of its first and last reporting week; null if it never reports)."""
    kept, dropped = [], 0
    for r in rows:
        if r[2] < start:
            dropped += 1
        else:
            kept.append(r)
    dates = sorted({r[2] for r in kept})
    if not dates:
        raise ValueError("BD-Embalses: no rows on or after the first week")
    bad = [d for d in dates if d.weekday() != 1]
    gaps = [b for a, b in zip(dates, dates[1:]) if b - a != timedelta(days=7)]
    if bad or gaps:
        raise ValueError(f"BD-Embalses: {len(bad)} dates not a Tuesday ({bad[:3]}), {len(gaps)} gaps ({gaps[:3]})")
    at = {d: k for k, d in enumerate(dates)}
    found: dict[tuple, dict] = {}
    for basin, name, day, total, actual, flag in kept:
        res = found.setdefault((basin, name), {"rows": {}, "flag": (day, flag)})
        if day in res["rows"]:
            raise ValueError(f"BD-Embalses: two rows for {name} ({basin}) on {day}")
        res["rows"][day] = (parse_hm3(total), parse_hm3(actual))
        if day >= res["flag"][0]:
            res["flag"] = (day, flag)
    out = []
    for (basin, name), res in found.items():
        actual: list = [None] * len(dates)
        runs: list[list] = []
        for day in sorted(res["rows"]):
            cap, act = res["rows"][day]
            if cap is None or act is None:
                continue
            k = at[day]
            actual[k] = act
            if not runs or runs[-1][1] != cap:
                runs.append([k, cap])
        reported = [k for k, v in enumerate(actual) if v is not None]
        out.append({"basin": basin, "name": name, "use": HYDRO if int(res["flag"][1] or 0) else CONSUMPTIVE,
                    "actual": actual, "capacity": runs, "first": reported[0] if reported else None,
                    "last": reported[-1] if reported else None})
    return {"dates": [d.isoformat() for d in dates], "dropped": dropped, "reservoirs": out}


def capacity_at(runs: list[list], k: int):
    """The capacity in force in week k from a reservoir's runs (None before the first)."""
    cap = None
    for start, v in runs:
        if start > k:
            break
        cap = v
    return cap


def basin_totals(reservoirs: list[dict], basins: list[str], n: int) -> dict[str, dict]:
    """Per basin name, the weekly sums {actual, capacity} (hm³, null in a week with no reporting reservoir) of the
    reservoirs that report that week."""
    out = {b: {"actual": [None] * n, "capacity": [None] * n} for b in basins}
    for r in reservoirs:
        s = out[r["basin"]]
        for k, v in enumerate(r["actual"]):
            if v is None:
                continue
            s["actual"][k] = (s["actual"][k] or 0) + v
            s["capacity"][k] = (s["capacity"][k] or 0) + capacity_at(r["capacity"], k)
    return out


def check_layer(doc: dict, count: dict, what: str) -> list[dict]:
    """The features of an ArcGIS query answer, after checking it is complete: no error, no `exceededTransferLimit`,
    and as many features as the layer's returnCountOnly answer says."""
    if "error" in doc or "error" in count:
        raise ValueError(f"{what}: the service answered an error ({doc.get('error') or count.get('error')})")
    feats = doc.get("features") or []
    if doc.get("exceededTransferLimit") or len(feats) != count.get("count"):
        raise ValueError(f"{what}: {len(feats)} features for a count of {count.get('count')}"
                         f"{' (exceededTransferLimit)' if doc.get('exceededTransferLimit') else ''}")
    return feats


def round_ring(ring: list) -> list[list[float]]:
    return [[round(x, 5), round(y, 5)] for x, y in ring]


def weekday_of(text: str) -> str:
    """Embalses_Mapa's Fecha_str ('24112026') as an ISO date."""
    return f"{text[4:]}-{text[2:4]}-{text[:2]}"


class BoletinHidrologico(Source):
    info = SourceInfo(
        id="boletin_hidrologico",
        title="Boletín Hidrológico: reservoir storage week by week since 1988 (BD-Embalses), with the Boletín's "
        "reservoir points and basins",
        publisher="Ministerio para la Transición Ecológica y el Reto Demográfico (MITECO), Boletín Hidrológico",
        homepage=BOLETIN,
        license="Public-sector information, reusable citing the source and keeping its update date (Ley 37/2007, "
        "RD 1495/2011 art. 7; MITECO legal notice); MITECO does not endorse this map",
        description="The historical database of the weekly Boletín Hidrológico (BD-Embalses, 'without validation'): "
        "for every reservoir it follows, each Tuesday since 1988, its basin, its capacity and the water it holds in "
        "hm³, and whether it is hydroelectric. Its data model (a MITECO PDF for BD-Embalses 1988-2022) describes one "
        "table with the basin (AMBITO_NOMBRE), the reservoir (EMBALSE_NOMBRE), the date (FECHA), the capacity "
        "(AGUA_TOTAL), the water stored (AGUA_ACTUAL) and the hydroelectric flag (ELECTRICO_FLAG); validated figures "
        "are only in the yearly 'Anuario de Aforos'. The positions of the reservoirs of the latest week and the outlines of the "
        "16 basins come from the two layers of the Boletín's own map (ArcGIS Online, account BolHidro_miteco), whose "
        "names are those of the database.",
        used_for=["Reservoirs lens: water stored by basin and reservoir, week by week since 1988"],
    )

    def _arcgis(self, layer: str, params: dict, file: str, force: bool) -> None:
        base = {"where": "1=1", "f": "json"}
        q = urllib.parse.urlencode({**base, **params})
        path = self.download(f"{layer}?{q}", file, force=force)
        count = self.download(f"{layer}?{urllib.parse.urlencode({**base, 'returnCountOnly': 'true'})}",
                              file.replace(".json", "_count.json"), force=force)
        try:
            check_layer(json.loads(path.read_text()), json.loads(count.read_text()), file)
        except ValueError:
            self.discard(file)
            raise

    def fetch(self, force=False):
        self.download(ZIP_URL, ZIP_FILE, force=force, expect_binary=True)
        self.download(MODEL_URL, MODEL_FILE, force=force, expect_binary=True)
        self._arcgis(POINTS_LAYER, {"outFields": POINTS_FIELDS, "outSR": 4326, "resultRecordCount": 2000}, POINTS_FILE,
                     force)
        self._arcgis(BASINS_LAYER, {"outFields": BASINS_FIELDS, "outSR": 4326, "geometryPrecision": 5}, BASINS_FILE,
                     force)

    def mdb(self):
        """The database, extracted from the cached zip the first time (and again whenever the zip changes)."""
        sha = read_manifest(self.id)[ZIP_FILE]["sha256"]
        mdb, stamp = self.raw_dir / MDB_FILE, self.raw_dir / f"{MDB_FILE}.sha256"
        if not mdb.exists() or not stamp.exists() or stamp.read_text().strip() != sha:
            with zipfile.ZipFile(self.raw_dir / ZIP_FILE) as z:
                names = [n for n in z.namelist() if n.lower().endswith(".mdb")]
                if len(names) != 1:
                    raise ValueError(f"{ZIP_FILE}: {len(names)} .mdb members, expected one")
                tmp = mdb.with_name(mdb.name + ".part")
                with z.open(names[0]) as src, open(tmp, "wb") as dst:
                    while chunk := src.read(1 << 20):
                        dst.write(chunk)
                tmp.replace(mdb)
            stamp.write_text(sha)
        return Jet4(mdb)

    def process(self):
        with self.mdb() as db:
            tables = [t for t in db.tables() if t.startswith(TABLE_PREFIX)]
            if len(tables) != 1:
                raise ValueError(f"BD-Embalses: {len(tables)} tables named {TABLE_PREFIX}…, expected one ({tables})")
            cols = ["AMBITO_NOMBRE", "EMBALSE_NOMBRE", "FECHA", "AGUA_TOTAL", "AGUA_ACTUAL", "ELECTRICO_FLAG"]
            rows = [(r["AMBITO_NOMBRE"], r["EMBALSE_NOMBRE"], r["FECHA"].date(), r["AGUA_TOTAL"], r["AGUA_ACTUAL"],
                     r["ELECTRICO_FLAG"]) for r in db.rows(tables[0], cols)]
            if len(rows) != db.row_count(tables[0]):
                raise ValueError(f"BD-Embalses: read {len(rows)} rows of the {db.row_count(tables[0])} the table holds")
        out = series(rows)
        dates, reservoirs = out["dates"], out["reservoirs"]
        print(f"    BD-Embalses ({tables[0]}): {len(rows)} rows, {len(reservoirs)} reservoirs, {len(dates)} weeks "
              f"{dates[0]}…{dates[-1]}; {out['dropped']} rows before {START} dropped")

        point_feats = check_layer(json.loads((self.raw_dir / POINTS_FILE).read_text()),
                                  json.loads((self.raw_dir / POINTS_FILE.replace(".json", "_count.json")).read_text()),
                                  POINTS_FILE)
        points = [{"basin": a["ambito_nombre"], "name": a["embalse_nombre"], "basin_id": a["ambito_id"],
                   "lon": round(f["geometry"]["x"], 5), "lat": round(f["geometry"]["y"], 5),
                   "capacity": a["agua_total"], "actual": a["agua_actual"], "date": weekday_of(a["Fecha_str"])}
                  for f in point_feats for a in [f["attributes"]]]
        basin_feats = check_layer(json.loads((self.raw_dir / BASINS_FILE).read_text()),
                                  json.loads((self.raw_dir / BASINS_FILE.replace(".json", "_count.json")).read_text()),
                                  BASINS_FILE)
        order = {}
        for p in points:
            order.setdefault(p["basin"], p["basin_id"])
        basins = sorted(({"name": a["NOM_DEMAR"], "rings": [round_ring(r) for r in f["geometry"]["rings"]],
                          "stored": a["Agua"], "pct": a["Porc_Agua_Cuenca"],
                          "date": datetime.fromtimestamp(a["Fecha"] / 1000, timezone.utc).date().isoformat()}
                         for f in basin_feats for a in [f["attributes"]]), key=lambda b: order.get(b["name"], 99))
        names = {b["name"] for b in basins}
        if names != {r["basin"] for r in reservoirs} or len(names) != len(basins):
            raise ValueError(f"DDHH basins {sorted(names)} are not the database's ámbitos "
                             f"{sorted({r['basin'] for r in reservoirs})}")
        totals = basin_totals(reservoirs, [b["name"] for b in basins], len(dates))
        for b in basins:  # the Boletín's own basin figures for its week (they are the database's sums)
            if b["date"] in dates:
                k = dates.index(b["date"])
                got = totals[b["name"]]
                if got["actual"][k] != b["stored"] or abs(100 * got["actual"][k] / got["capacity"][k] - b["pct"]) > 0.01:
                    raise ValueError(f"DDHH {b['name']} {b['date']}: {b['stored']} hm³ ({b['pct']:.2f} %) but the "
                                     f"database sums {got['actual'][k]} of {got['capacity'][k]} hm³")
        retrieved = read_manifest(self.id)[ZIP_FILE]["retrieved"][:10]
        return {"vintage": f"BD-Embalses (Boletín Hidrológico), {dates[0]} to {dates[-1]}, provisional; retrieved "
                           f"{retrieved}",
                "_files": [ZIP_FILE, MODEL_FILE, POINTS_FILE, BASINS_FILE], "table": tables[0], "dates": dates,
                "dropped": out["dropped"], "reservoirs": reservoirs, "points": points,
                "basins": [{k: b[k] for k in ("name", "rings", "stored", "pct", "date")} for b in basins]}
