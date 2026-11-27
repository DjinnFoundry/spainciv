"""Road freight between Spain's autonomous communities: the Encuesta Permanente de Transporte de Mercancías por
Carretera (EPTMC), annual tables, Ministerio de Transportes y Movilidad Sostenible.

The survey samples Spanish-registered heavy goods vehicles (tractors able to pull more than 3.5 t; rigid trucks with
more than 3.5 t payload and more than 6 t maximum mass) one week at a time. Its smallest geography is the autonomous
community, and Ceuta and Melilla are published together. Read from the workbook's sheets:

* 6.7 / 6.7s: thousand tonnes by community of loading (rows) and of unloading (columns), split over two sheets; the
  diagonal is the traffic inside a community, intramunicipal included.
* 6.8 / 6.8s: million tonne-kilometres, same layout.
* 6.3: thousand tonnes by community and kind of trip (intramunicipal, intermunicipal, received from and sent to other
  communities, international received and sent; Spanish trucks only).
* 7.5p1…7.5p8: thousand tonnes by NST/R chapter (10 classes) sent to and received from other communities.

Cells marked `..` (not significant: every interregional flow of the Balearic and Canary Islands, Ceuta and Melilla,
as the sheets' footnote says), `.` and `-` are kept as null, never as zero. The workbook does not say what `.` and `-`
mean (it has no legend for them; 6.3 writes `.` for Canarias' tonnes sent to other communities and `-` for the
intermunicipal traffic of Ceuta and Melilla), so they are not read as zero either. Labels are matched by their text through LABELS, never by position: the
survey sorts Castilla-La Mancha before Castilla y León, the reverse of the INE codes. The matrix is checked against
the table's own totals and against table 6.3 (see `check_consistency`).

The ministry's web firewall refuses scripted User-Agent strings (403), so the download sends a desktop browser's.

The ministry's reuse conditions (https://www.transportes.gob.es/aviso-legal) ask to cite the source, suggesting
ATTRIBUTION's wording, and to give the date the documents were last updated: the server's Last-Modified for the
workbook, kept in the manifest by the download and passed on as `updated`.
"""

from __future__ import annotations

import re
import unicodedata
from email.utils import parsedate_to_datetime

from ...core.fetch import read_manifest
from ...core.lang import tr
from ...core.source import Source, SourceInfo
from ...core.xls import sheets

EPTMC_YEAR = 2025
PAGE = ("https://www.transportes.gob.es/el-ministerio/informacion-estadistica/transporte/"
        "transporte-de-mercancias-por-carretera/publicaciones-encuesta-permanente-transporte-mercancias-por-carretera/"
        f"EPTMC{EPTMC_YEAR}")
FILE = f"eptmc{EPTMC_YEAR}.tablas.xls"
URL = f"https://www.transportes.gob.es/recursos_mfom/comodin/recursos/{FILE}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/131.0.0.0 Safari/537.36"}
ATTRIBUTION = "Origen de los datos: Ministerio de Transportes y Movilidad Sostenible"  # the aviso legal's own example

CEUTA_MELILLA = "18+19"  # the survey publishes the two autonomous cities together
NOT_SIGNIFICANT = {"04", "05", CEUTA_MELILLA}  # every interregional cell of theirs is `..`
CODES = [f"{i:02d}" for i in range(1, 18)] + [CEUTA_MELILLA]
MISSING = {"..", ".", "-"}  # not significant (`..`) and two marks the workbook does not define: all kept as null


def norm(text: str | None) -> str:
    """A label as LABELS keys it: a word hyphenated across a line break joined, lowercase, accents and punctuation
    gone, spaces collapsed. 'Extre-\\nmadura' → 'extremadura', 'Asturias, \\nP. de' → 'asturias p de'."""
    t = re.sub(r"-\s*\n\s*(?=[a-záéíóúñ])", "", text or "")
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    return " ".join(re.split(r"[^a-z0-9]+", t)).strip()


# Every form of a community's name in the tables (the short one of 6.7/6.8 and the long one of 6.3/7.5) → INE code.
LABELS = {norm(k): code for code, names in {
    "01": ["Andalucía"], "02": ["Aragón"], "03": ["Asturias, P. de", "Asturias, Principado de"],
    "04": ["Balears, Illes"], "05": ["Canarias"], "06": ["Cantabria"], "07": ["Castilla y León"],
    "08": ["Castilla-La Mancha"], "09": ["Cataluña"],
    "10": ["Com. Valenciana", "C. Valenciana", "Comunidad Valenciana"], "11": ["Extremadura"], "12": ["Galicia"],
    "13": ["Madrid, C. de", "Madrid, Comunidad de"], "14": ["Murcia, R. de", "Murcia, Región de"],
    "15": ["Navarra, C. F. de", "Navarra, C. Foral de", "Navarra, Comunidad Foral de"], "16": ["País Vasco"], "17": ["Rioja, La"],
    CEUTA_MELILLA: ["Ceuta y Melilla"],
}.items() for k in names}

# The ten NST/R chapters of table 7.5: its column header (normalised) and the chapter's name (the survey's
# methodology, section 3.6, and Eurostat's English).
CLASSES = [
    ("productos agricolas y animales vivos", tr("Productos agrícolas y animales vivos", "Agricultural products and live animals")),
    ("productos alimenticios y forrajes", tr("Productos alimenticios y forrajes", "Foodstuffs and animal fodder")),
    ("combustibles minerales solidos", tr("Combustibles minerales sólidos", "Solid mineral fuels")),
    ("productos petroliferos", tr("Productos petrolíferos", "Petroleum products")),
    ("minerales y residuos para refundicion", tr("Minerales y residuos para refundición", "Ores and metal waste")),
    ("productos metalurgicos", tr("Productos metalúrgicos", "Metal products")),
    ("minerales y materiales para construccion",
     tr("Minerales en bruto o manufacturados y materiales de construcción", "Crude and manufactured minerals, building materials")),
    ("abonos", tr("Abonos", "Fertilisers")),
    ("productos quimicos", tr("Productos químicos", "Chemicals")),
    ("maquinas vehiculos objetos manufacturados",
     tr("Máquinas, vehículos, objetos manufacturados y transacciones especiales",
        "Machinery, transport equipment, manufactured and miscellaneous articles")),
]

# Table 6.3's columns.
TRIP_COLUMNS = {"total": "within", "intra municipal": "intramunicipal", "inter municipal": "intermunicipal",
                "recibido de otras cc aa": "received", "expedido a otras cc aa": "sent",
                "recibido": "intl_received", "expedido": "intl_sent"}
# Table 7.5's row kinds: the community's interregional tonnes sent and received are the two kept.
GOODS_ROWS = {"expedido c": "sent", "recibido d": "received"}
GOODS_OTHER_ROWS = {"total", "intramunicipal", "intermunicipal intrarregional", "interregional",
                    "total transportado a b c d", "total de origen a b c", "total de destino a b d", "intramunicipal a",
                    "intermunicipal intrarregional b", "interregional c d"}


class EptmcError(ValueError):
    """The workbook does not read as expected: a label, a header or a total has changed."""


def cell(x: str | None, where: str) -> float | None:
    """A number of the tables, or None for `..`, `.` and `-`. An empty cell where a number belongs is an error."""
    s = (x or "").strip()
    if s in MISSING:
        return None
    try:
        return float(s)
    except ValueError:
        raise EptmcError(f"{where}: {x!r} is not a number") from None


def _get(row: list, i: int):
    return row[i] if i < len(row) else None


def matrix_sheet(rows: list[list], name: str) -> dict[str, dict[str, float | None]]:
    """One sheet of an origin-destination table (6.7, 6.7s, 6.8, 6.8s): {origin: {destination: value}}. The header
    row holds the "DESTINO" label; that column holds the origins. Columns: community codes, "_total" (TOTAL DE
    ORIGEN) and "_sent" (expedido a otras CC.AA.); rows: community codes, "_total" (TOTAL DE DESTINO) and "_received"
    (recibido de otras CC.AA.)."""
    head = next(((i, j) for i, r in enumerate(rows) for j, x in enumerate(r) if norm(x) == "destino"), None)
    if head is None:
        raise EptmcError(f"{name}: no DESTINO header row")
    h, lab = head
    cols = {}
    for j, x in enumerate(rows[h]):
        n = norm(x)
        if j == lab or not n:
            continue
        if n in LABELS:
            cols[j] = LABELS[n]
        elif n == "total de origen":
            cols[j] = "_total"
        elif n.startswith("del cual expedido"):
            cols[j] = "_sent"
        else:
            raise EptmcError(f"{name}: unknown column {x!r}")
    out: dict[str, dict] = {}
    for i, r in enumerate(rows[h + 1:], h + 1):
        n = norm(_get(r, lab))
        if not n or n == "origen":
            continue
        if n in LABELS:
            key = LABELS[n]
        elif n == "total de destino":
            key = "_total"
        elif n.startswith("del cual recibido"):
            key = "_received"
        else:
            raise EptmcError(f"{name} row {i}: unknown origin {_get(r, lab)!r}")
        if key in out:
            raise EptmcError(f"{name}: two rows for {key}")
        # A total row leaves some corners blank (the national "recibido" of the TOTAL DE ORIGEN column).
        blank_ok = key.startswith("_")
        out[key] = {c: None if blank_ok and _get(r, j) in (None, "") else cell(_get(r, j), f"{name} row {i} col {j}")
                    for j, c in cols.items()}
        if key == "_received":
            return out
    raise EptmcError(f"{name}: no 'Del cual, recibido de otras CC.AA.' row")


def matrix(left: list[list], right: list[list], name: str) -> dict[str, dict[str, float | None]]:
    """The two sheets of an origin-destination table joined: every origin row with all 18 destinations."""
    a, b = matrix_sheet(left, name), matrix_sheet(right, f"{name}s")
    if set(a) != set(b):
        raise EptmcError(f"{name}: the two sheets have different rows")
    out = {}
    for k in a:
        if set(a[k]) & set(b[k]):
            raise EptmcError(f"{name}: a column in both sheets")
        out[k] = {**a[k], **b[k]}
    want_rows, want_cols = set(CODES) | {"_total", "_received"}, set(CODES) | {"_total", "_sent"}
    if set(out) != want_rows or any(set(v) != want_cols for v in out.values()):
        raise EptmcError(f"{name}: rows or columns missing")
    return out


def trips(rows: list[list]) -> dict[str, dict[str, float | None]]:
    """Table 6.3: {community code or "national": {within, intramunicipal, intermunicipal, received, sent,
    intl_received, intl_sent}}."""
    h = next((i for i, r in enumerate(rows) if norm(_get(r, 0)) == "comunidad autonoma"), None)
    if h is None:
        raise EptmcError("6.3: no 'Comunidad Autónoma' header row")
    cols = {}
    for j, x in enumerate(rows[h][1:], 1):
        n = norm(x)
        if not n:
            continue
        if n not in TRIP_COLUMNS or TRIP_COLUMNS[n] in cols.values():
            raise EptmcError(f"6.3: unknown or repeated column {x!r}")
        cols[j] = TRIP_COLUMNS[n]
    if set(cols.values()) != set(TRIP_COLUMNS.values()):
        raise EptmcError("6.3: columns missing")
    out = {}
    for i, r in enumerate(rows[h + 1:], h + 1):
        n = norm(_get(r, 0))
        if not n:
            continue
        if n.startswith("fuente"):
            break
        key = "national" if n == "total" else LABELS.get(n)
        if key is None:
            raise EptmcError(f"6.3 row {i}: unknown community {_get(r, 0)!r}")
        out[key] = {k: cell(_get(r, j), f"6.3 row {i} col {j}") for j, k in cols.items()}
    if set(out) != set(CODES) | {"national"}:
        raise EptmcError("6.3: communities missing")
    return out


def goods_sheet(rows: list[list], name: str, into: dict) -> None:
    """One sheet of table 7.5: its classes' tonnes sent and received by each community, added to
    into[code][kind][class index] (and into[code][kind + "_total"] from the TOTAL column)."""
    units = next((i for i, r in enumerate(rows) if any(norm(x) == "miles de tn" for x in r)), None)
    lab = next((j for r in rows for j, x in enumerate(r) if norm(x) == "comunidad autonoma"), None)
    if units is None or lab is None:
        raise EptmcError(f"{name}: no units row or no 'Comunidad Autónoma' column")
    first = next((i for i, r in enumerate(rows) if i > units and (norm(_get(r, lab)) == "total" or norm(_get(r, lab)) in LABELS)), None)
    if first is None:
        raise EptmcError(f"{name}: no data rows")
    class_of = {n: k for k, (n, _) in enumerate(CLASSES)}
    cols = {}
    for j in range(max(len(r) for r in rows[units + 1: first])):
        if j == lab:
            continue
        n = norm(" ".join(_get(r, j) or "" for r in rows[units + 1: first]))
        if not n:
            continue
        if n == "total":
            cols[j] = "total"
        elif n in class_of:
            cols[j] = class_of[n]
        else:
            raise EptmcError(f"{name}: unknown goods class {n!r}")
    current = None
    for i, r in enumerate(rows[first:], first):
        n = norm(_get(r, lab))
        if any(norm(x).startswith("fuente") for x in r):  # the footnotes (in the first column of every sheet)
            break
        if n in LABELS:
            current = LABELS[n]
            continue
        has_data = any(_get(r, j) not in (None, "") for j in cols)
        if n in GOODS_ROWS:
            if current is None:
                raise EptmcError(f"{name} row {i}: {n!r} before any community")
            kind = GOODS_ROWS[n]
            for j, k in cols.items():
                v = cell(_get(r, j), f"{name} row {i} col {j}")
                slot = into.setdefault(current, {}).setdefault(kind, [False] * len(CLASSES))
                if k == "total":
                    into[current][f"{kind}_total"] = v
                    continue
                if slot[k] is not False:
                    raise EptmcError(f"{name}: class {k} of {current} {kind} read twice")
                slot[k] = v
        elif n not in GOODS_OTHER_ROWS and (n or has_data):
            raise EptmcError(f"{name} row {i}: unknown row {_get(r, lab)!r}")


def goods(book: dict) -> dict[str, dict]:
    """Table 7.5 over its eight sheets: {code: {sent: [10], received: [10], sent_total, received_total}}."""
    names = [f"7.5p{k}" for k in range(1, 9)]
    if any(n not in book for n in names):
        raise EptmcError("table 7.5 sheets missing")
    out: dict[str, dict] = {}
    for n in names:
        goods_sheet(book[n], n, out)
    for code in CODES:
        for kind in ("sent", "received"):
            got = out.get(code, {}).get(kind)
            if got is None or any(v is False for v in got) or f"{kind}_total" not in out[code]:
                raise EptmcError(f"7.5: {code} {kind} lacks classes")
    if set(out) != set(CODES):
        raise EptmcError("7.5: unexpected communities")
    return out


def check_consistency(tons: dict, trip: dict, goods_: dict | None = None) -> None:
    """Raise unless the matrix agrees with itself and with table 6.3, for every community whose flows are published:
    the flows shown add up to no more than what it sent to other communities, the gap (cells with the islands, Ceuta
    and Melilla, published as `..`) is under 6 %, the diagonal is its intramunicipal plus intermunicipal traffic, and
    table 7.5's goods classes add up to what table 6.3 says it sent and received."""
    for o in CODES:
        if o in NOT_SIGNIFICANT:
            continue
        row = tons[o]
        shown = sum(v for d, v in row.items() if d in CODES and d != o and v is not None)
        sent = row["_sent"]
        if sent is None or shown > sent + 0.5:
            raise EptmcError(f"6.7 {o}: the flows shown ({shown:.1f}) exceed what it sent ({sent})")
        if sent - shown > 0.06 * sent:
            raise EptmcError(f"6.7 {o}: {sent - shown:.1f} thousand t sent to other communities are not in the matrix")
        t = trip[o]
        if abs(row[o] - (t["intramunicipal"] + t["intermunicipal"])) > 0.5:
            raise EptmcError(f"6.7 {o}: the diagonal {row[o]:.1f} is not table 6.3's intra- plus intermunicipal")
        if abs(sent - t["sent"]) > 0.5:
            raise EptmcError(f"6.7 {o}: sent {sent:.1f}, table 6.3 says {t['sent']:.1f}")
        for kind in ("sent", "received") if goods_ is not None else ():
            g, total = goods_[o][kind], goods_[o][f"{kind}_total"]
            if total is None or abs(total - t[kind]) > 0.5 or abs(sum(v for v in g if v is not None) - total) > 0.5:
                raise EptmcError(f"7.5 {o}: the goods {kind} do not add up to table 6.3's {t[kind]:.1f}")
    if abs(tons["_received"]["_sent"] - trip["national"]["sent"]) > 0.5:
        raise EptmcError("6.7: the national interregional total is not table 6.3's")


def parse(book: dict) -> dict:
    """The interim data from the workbook's sheets (a dict like core.xls.sheets returns)."""
    for n in ("6.3", "6.7", "6.7s", "6.8", "6.8s"):
        if n not in book:
            raise EptmcError(f"sheet {n} missing")
    tons, tkm = matrix(book["6.7"], book["6.7s"], "6.7"), matrix(book["6.8"], book["6.8s"], "6.8")
    trip = trips(book["6.3"])
    g = goods(book)
    check_consistency(tons, trip, g)
    strip = lambda m: {o: {d: m[o][d] for d in CODES} for o in CODES}
    return {
        "year": EPTMC_YEAR, "codes": CODES, "not_significant": sorted(NOT_SIGNIFICANT),
        "tons_k": strip(tons), "tkm_m": strip(tkm),
        "sent_k": {o: tons[o]["_sent"] for o in CODES}, "received_k": {d: tons["_received"][d] for d in CODES},
        "trips_k": trip,
        "goods_k": {c: {"sent": g[c]["sent"], "received": g[c]["received"]} for c in CODES},
    }


class Eptmc(Source):
    info = SourceInfo(
        id="eptmc",
        title=f"Permanent Survey of Road Freight Transport (EPTMC {EPTMC_YEAR}): tonnes by autonomous community of "
        "loading and unloading",
        publisher="Ministerio de Transportes y Movilidad Sostenible",
        homepage=PAGE,
        license="Reuse allowed, commercial or not, under the ministry's conditions (Ley 37/2007, "
        f"transportes.gob.es/aviso-legal): cite the source («{ATTRIBUTION}») and give the date the data was last "
        "updated",
        description=f"The annual tables of the EPTMC {EPTMC_YEAR}, a weekly sample survey of Spanish-registered heavy "
        "goods vehicles (over 3.5 t): tonnes and tonne-kilometres by community of loading and of unloading (tables "
        "6.7 and 6.8), tonnes by kind of trip (6.3) and by NST/R goods chapter (7.5). Flows with the Balearic and "
        "Canary Islands, Ceuta and Melilla are not significant and are not published.",
        used_for=["Trade routes", "Commerce advisor"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, headers=HEADERS, expect_binary=True)

    def process(self):
        book = sheets(self.raw_dir / FILE, only={"6.3", "6.7", "6.7s", "6.8", "6.8s"} | {f"7.5p{k}" for k in range(1, 9)})
        return {**parse(book), "updated": updated(read_manifest(self.id).get(FILE, {})), "vintage": f"EPTMC {EPTMC_YEAR}",
                "_files": [FILE]}


def updated(entry: dict) -> str:
    """The workbook's last update, from its manifest entry's Last-Modified, as an ISO date ("2026-11-16")."""
    try:
        return parsedate_to_datetime(entry["last_modified"]).date().isoformat()
    except (KeyError, TypeError, ValueError):
        raise EptmcError(f"{FILE}: no Last-Modified in the manifest (fetch eptmc --force); the licence needs the "
                         "update date") from None
