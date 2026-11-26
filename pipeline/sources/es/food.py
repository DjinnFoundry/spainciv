"""Spain's protected food and drink names: every name Spain has in the EU register (eAmbrosia), each with its area.

The area comes from the Ministry of Agriculture's map of designations (MAPA, revised in 2017) when the name is on it.
For the names the Ministry has not mapped (wine PGIs, vinos de pago, names registered since 2017), the area that the
official specification or EU single document delimits was read into data/calidad_diferenciada_zonas.csv as
administrative units (communities, provinces, islands, municipalities); the map builds them from the IGN's SIANE
boundaries. A vino de pago is a single estate: the CSV gives its municipality.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

from ...core.geo import geojson_rings
from ...core.source import Source, SourceInfo
from .provinces import COMMUNITIES, PROVINCES
from .tls import GLOBALSIGN_R46

ZONES = ("https://wmts.mapama.gob.es/sig-api/ogc/features/v1/collections/alimentacion:CDZ_CalidadDiferenciada/items"
         "?f=json&limit={limit}&startIndex={start}")
PAGE = 25  # features per request: the whole collection is over 50 MB and one request times out
TOTAL = 301
EAMBROSIA = "https://webgate.ec.europa.eu/eambrosia-api/api/geographical-indications?size=2000&page={page}"
EAMBROSIA_PAGES = 2  # 2,000 names a page (the API's maximum); the register holds about 3,900
AREAS = Path(__file__).parent / "data" / "calidad_diferenciada_zonas.csv"
# The Ministry's designation types ('Denominación de Origen Protegida', 'Indicación Geográfica Protegida Bebida
# Espirituosa', 'Vino de Pago'…) by the words that set them apart, in order: the first match names the kind.
KIND = [("Pago", "Vino de pago"), ("Calidad", "Vino de calidad"), ("Origen", "DOP"), ("Protegida", "IGP"),
        ("Geográfica", "IG")]
# Names the Ministry mapped under an earlier name: its code → the EU file number of the name registered since.
RENAMED = {"DO83": "PDO-ES-A0882",  # D.O. Tierra de León, now León
           "DO113": "PDO-ES-0308",  # Gamonedo, registered as Gamonéu
           "DO126": "PGI-ES-0313"}  # Lenteja Pardina de Tierra de Campos, registered as Lenteja de Tierra de Campos
# Not a rename: IGP Carne Morucha de Salamanca (DO194) was cancelled in 2018 (Reg. 2018/69) and Carne de Salamanca
# registered as a new name (Reg. 2018/68), so the Ministry's 2017 area is the cancelled one's and the CSV has the new.
# Words left out when comparing names: articles and prepositions (Spanish, Galician, Catalan).
STOPWORDS = {"de", "del", "la", "las", "los", "el", "d", "do", "da", "dos", "das", "y", "e", "i"}
# A product word the Ministry puts before some registered names ('Queso Idiazábal' is 'Idiazabal').
GENERIC = {"Food": ("queso",), "Wine": ("vino pago", "pago")}
# The Ministry's product families that are not food → eAmbrosia's product type.
PRODUCTS = {"Vinos": "Wine", "Bebidas Espirituosas": "Spirit drink"}
# Islands by one of their municipalities (INE code): an island is every municipality whose outline joins it.
ISLANDS = {"Mallorca": "07040", "Menorca": "07032", "Eivissa": "07026", "Formentera": "07024", "Tenerife": "38038",
           "Gran Canaria": "35016", "Lanzarote": "35004", "Fuerteventura": "35017", "La Palma": "38037",
           "La Gomera": "38036", "El Hierro": "38048"}
# How an area of units was obtained, as the name says it after its kind: 'Torrezno de Soria (IGP · provincia)'.
HOW = {"comunidad": "comunidad", "provincia": "provincia", "isla": "isla", "municipio": "municipios"}


def label(name: str, kind: str) -> str:
    return f"{name} ({next((short for word, short in KIND if word in kind), kind)})"


def ministry_label(p: dict) -> str:
    """A Ministry designation's label: its zone name and kind."""
    return label(p["zon_ds_nombre"], p["tpr_ds_descripcion"])


def area_kind(kind: str, units: list[str]) -> str:
    """How an areas CSV row is placed: 'ninguna' (no area), 'finca' (a vino de pago's estate) or 'unidades'."""
    if not units:
        return "ninguna"
    return "finca" if kind == "Vino de pago" else "unidades"


def area_label(name: str, kind: str, units: list[str]) -> str:
    """'Torrezno de Soria', 'IGP', ['provincia:42'] → 'Torrezno de Soria (IGP · provincia)'; a vino de pago says
    'finca'; a name with no area says 'sin zona'."""
    area = area_kind(kind, units)
    if area == "ninguna":
        how = "sin zona"
    elif area == "finca":
        how = "finca"
    else:
        kinds = {u.partition(":")[0] for u in units}
        how = ", ".join(HOW[k] for k in HOW if k in kinds)
    return f"{name} ({kind} · {how})"


def name_key(name: str) -> str:
    """A name compared without case, accents, punctuation, articles or a plural s: 'Pimientos del Piquillo de
    Lodosa' and 'Pimiento del Piquillo de Lodosa' give the same key."""
    t = unicodedata.normalize("NFKD", name.lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    words = [w for w in re.split(r"[^a-z0-9]+", t) if w and w not in STOPWORDS]
    return " ".join(w[:-1] if w.endswith("s") and len(w) > 3 else w for w in words)


def name_keys(name: str, product: str) -> set[str]:
    key = name_key(name)
    return {key} | {key[len(g) + 1:] for g in GENERIC.get(product, ()) if key.startswith(g + " ")}


def product_of(family: str) -> str:
    """The Ministry's product family → eAmbrosia's product type."""
    return PRODUCTS.get(family, "Food")


def ministry_names(p: dict) -> list[str]:
    """The ways the Ministry writes a designation: its zone name and its designation name without the abbreviation
    ('D.O.P.', 'I.G.P.', 'V.P.', 'D.O.Ca.')."""
    return [p["zon_ds_nombre"], re.sub(r"^(?:[A-Z][a-z]?\.)+\s*", "", p["cal_ds_nombre"])]


def matches(ministry: list[str], protected: list[str], product: str) -> bool:
    """Whether a Ministry designation is a registered name: one of its spellings is one of the protected names; or,
    split at ' o ' or '/', a part is ('Jijona / Xixona' is 'Jijona'); or, split at '-', every part is
    ('Arabako Txakolina-Chacolí de Álava' is the name with both)."""
    keys = set().union(*(name_keys(n, product) for n in protected))
    for name in ministry:
        alternatives = re.split(r" o |/", name)
        joined = name.split("-")
        if any(name_keys(a, product) & keys for a in alternatives) or (
                len(joined) > 1 and all(name_keys(j, product) & keys for j in joined)):
            return True
    return False


def match_register(ministry: dict[str, dict], register: list[dict]) -> dict[str, dict]:
    """Ministry code → the registered name it maps. Names are compared only within their product type (a cheese is
    never a wine); a code that matches no name or several is left out, and a name two codes match is an error."""
    out, taken = {}, {}
    for code, p in ministry.items():
        product = product_of(p["fam_ds_nombre"])
        found = [g for g in register if g["registration"]["fileNumber"] == RENAMED.get(code)] or [
            g for g in register if g["productType"] == product and matches(ministry_names(p), g["protectedNames"], product)]
        if len(found) != 1:
            continue
        gi = found[0]["giIdentifier"]
        if gi in taken:
            raise RuntimeError(f"eAmbrosia {gi} matches Ministry codes {taken[gi]} and {code}")
        out[code], taken[gi] = found[0], code
    return out


def valid_unit(kind: str, value: str) -> bool:
    if kind == "comunidad":
        return value in COMMUNITIES
    if kind == "provincia":
        return value in PROVINCES
    if kind == "isla":
        return value.replace("_", " ") in ISLANDS
    if kind == "municipio":
        return bool(re.fullmatch(r"\d{5}\*?", value)) and value[:2] in PROVINCES
    return False


def parse_units(text: str) -> list[str]:
    """'provincia:42 municipio:05057*' → ['provincia:42', 'municipio:05057*'], each checked: communities and
    provinces by INE code, islands by name (underscores for spaces: 'isla:Gran_Canaria'), municipalities by a
    five-digit INE code (a trailing * marks one only partly in the area)."""
    units = text.split()
    for unit in units:
        kind, _, value = unit.partition(":")
        if not valid_unit(kind, value):
            raise ValueError(f"bad area unit {unit!r}")
    return units


def read_areas(path: Path = AREAS) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(line for line in f if not line.startswith("#")))
    for r in rows:
        r["units"] = parse_units(r["unidades"])
        if r["figura"] == "Vino de pago" and not all(u.startswith("municipio:") for u in r["units"]):
            raise ValueError(f"{r['nombre']}: a vino de pago is placed at its municipality")
    return rows


class CalidadDiferenciada(Source):
    info = SourceInfo(
        id="calidad_diferenciada",
        title="Protected food and drink names: the EU register (eAmbrosia) and their areas (MAPA and specifications)",
        publisher="European Commission (eAmbrosia, Official Journal); Ministerio de Agricultura, Pesca y Alimentación; "
        "regional governments (specifications)",
        homepage="https://www.mapa.gob.es/es/cartografia-y-sig/ide/descargas/alimentacion/calidad-diferenciada.aspx",
        license="eAmbrosia and EUR-Lex: European Commission reuse notice (CC BY 4.0); MAPA: CC BY 4.0; specifications: "
        "official texts",
        description="Every name Spain has registered in the EU register (protected designations of origin, protected "
        "geographical indications, wines and spirits) with its geographical area: the Ministry's map where the name is "
        "on it (revised in 2017), otherwise the area the specification or EU single document delimits, read into "
        "pipeline/sources/es/data/calidad_diferenciada_zonas.csv as communities, provinces, islands or municipalities. "
        "A vino de pago is an estate, placed in its municipality.",
        used_for=["Food and drink lens", "Unciv map resources (wine, citrus, spices, cattle, sheep, fish, bananas)"],
    )

    def fetch(self, force=False):
        for start in range(0, TOTAL, PAGE):
            self.download(ZONES.format(limit=PAGE, start=start), f"zonas_{start:03d}.json", force=force)
        self.discard("eambrosia.json")  # the first fetch took only the API's default page of 50
        for page in range(EAMBROSIA_PAGES):
            self.download(EAMBROSIA.format(page=page), f"eambrosia_{page}.json", force=force, cafile=GLOBALSIGN_R46)

    def process(self):
        files = [f"zonas_{start:03d}.json" for start in range(0, TOTAL, PAGE)]
        ministry: dict[str, dict] = {}
        rings: dict[str, list] = {}
        for file in files:
            for f in json.loads((self.raw_dir / file).read_text())["features"]:
                if f.get("geometry"):
                    code = f["properties"]["cal_ds_codigo"]
                    ministry.setdefault(code, f["properties"])
                    rings.setdefault(code, []).extend(
                        [(round(x, 4), round(y, 4)) for x, y in r] for r in geojson_rings(f["geometry"]))
        eambrosia = [f"eambrosia_{page}.json" for page in range(EAMBROSIA_PAGES)]
        pages = [json.loads((self.raw_dir / f).read_text()) for f in eambrosia]
        if sum(len(p["content"]) for p in pages) < pages[0]["totalElements"]:
            raise RuntimeError("eAmbrosia has more names than the pages fetched: raise EAMBROSIA_PAGES")
        register = [g for p in pages for g in p["content"] if "es" in (g.get("countries") or []) and not g["removedFlag"]
                    and g["registration"]["status"] == "REGISTERED"]
        return {"vintage": "eAmbrosia; MAPA, Calidad diferenciada (zonas de 2017); pliegos de condiciones",
                "_files": files + eambrosia, **register_areas(register, ministry, rings, read_areas())}


def register_areas(register: list[dict], ministry: dict[str, dict], rings: dict[str, list], areas: list[dict]) -> dict:
    """Every registered name with its area: the Ministry's rings, else the units of the areas CSV (none: the CSV's
    note says why). A registered name with no row, or a row for a name not registered or already mapped, is an
    error."""
    mapped = match_register(ministry, register)
    by_gi = {g["giIdentifier"]: g for g in register}
    mapped_gi = {g["giIdentifier"] for g in mapped.values()}
    rows = {r["eambrosia"]: r for r in areas}
    if stray := sorted(set(rows) - set(by_gi)):
        raise RuntimeError(f"areas CSV: names not in the register: {stray}")
    if twice := sorted(set(rows) & mapped_gi):
        raise RuntimeError(f"areas CSV: names the Ministry already maps: {twice}")
    if unknown := sorted(gi for gi in by_gi if gi not in mapped_gi and gi not in rows):
        raise RuntimeError(f"registered names with no area and no row in the areas CSV: "
                           f"{[by_gi[gi]['protectedNames'][0] for gi in unknown]}")
    names = []
    for code, g in mapped.items():
        p = ministry[code]
        names.append({"id": g["giIdentifier"], "type": gi_type(g), "name": ministry_label(p),
                      "family": p["fam_ds_nombre"], "area": "mapa", "rings": rings[code]})
    for gi, r in rows.items():
        names.append({"id": gi, "type": gi_type(by_gi[gi]), "name": area_label(r["nombre"], r["figura"], r["units"]),
                      "family": r["familia"], "area": area_kind(r["figura"], r["units"]),
                      "units": r["units"], "source": r["fuente"], "note": r["nota"]})
    return {"names": sorted(names, key=lambda n: n["name"]), "eu_register": dict(Counter(map(gi_type, register))),
            "eu_registered": len(register),
            "not_registered": sorted(ministry_label(p) for code, p in ministry.items() if code not in mapped)}


def gi_type(g: dict) -> str:
    """A registered name's type and product: 'PDO Wine', 'PGI Food'…"""
    return f"{g['giType']} {g['productType']}"
