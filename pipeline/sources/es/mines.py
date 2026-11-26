"""Spain's active metal mines and key industrial-mineral mines: the Estadística Minera de España's list of active
workings (IGME, the 2019 list published with Panorama Minero 2022), placed at the matching deposit of IGME's BDMIN.

The list gives each working's name, company, municipality and substance, not its position, and no production (the
statistic does not publish output per mine). Its counts per substance must equal Panorama Minero 2022's tables
(PANORAMA_2019). A working takes the position of a BDMIN deposit of its mineral in its municipality (see locate);
one without such a deposit is left without coordinates, for the builder to put at the municipality's centre.
"""

from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
from collections import Counter

from ...core.source import Source, SourceInfo
from ...core.xlsx import sheets
from .provinces import PROVINCES

YEAR = 2019
LIST_URL = "https://www.igme.es/wp-content/uploads/2023/11/EXPLOTACIONES_2019.xlsx"
LIST_FILE = "explotaciones_2019.xlsx"
PANORAMA_URL = "https://info.igme.es/media/Pdfs/PANORAMA%20MINERO%202022.pdf"
PANORAMA_FILE = "panorama_minero_2022.pdf"
BDMIN = "https://mapas.igme.es/gis/rest/services/BasesDatos/IGME_BDMIN_Indicios/MapServer/0/query"
PAGE = 1000  # the layer's maxRecordCount

# EME substance → (our type, the BDMIN substance names that count as the same mineral). Coal is not in the 2019 list
# (Spain's last coal mines closed in 2018); iron oxides (pigments), rock salt and feldspar are left out.
SODIUM_SULFATE = ("sodium_sulfate", ["Glauberita", "Thenardita", "Sulfato"])
KIND = {
    "COBRE": ("copper", ["Cobre"]),
    "ORO-PLATA (MIN.)": ("gold", ["Oro"]),
    "WOLFRAMIO": ("tungsten", ["Wolframio"]),
    "ESTAÑO-TÁNTALO": ("tin_tantalum", ["Estaño", "Tantalio"]),
    "SALES POTAS.(MIN.)": ("potash", ["Potasio"]),
    "ESPATO FLÚOR": ("fluorite", ["Fluorita"]),
    "ESTRONCIO": ("celestine", ["Estroncio", "Celestina"]),
    "MAGNESITA CRUDA": ("magnesite", ["Magnesita"]),
    "GLAUBERITA": SODIUM_SULFATE,
    "THENARDITA": SODIUM_SULFATE,
}
# Active workings in 2019 per EME substance, as Panorama Minero 2022 counts them (PDF pages): «Minería metálica.
# Explotaciones activas por mineral, provincia y empresa» (43-44) and «Número de explotaciones de … por CCAA,
# provincia y empresa» for strontium (611), fluorspar (640), magnesite (671), potash (726) and sodium sulphate (793).
PANORAMA_2019 = {"COBRE": 5, "ORO-PLATA (MIN.)": 1, "WOLFRAMIO": 1, "ESTAÑO-TÁNTALO": 1, "SALES POTAS.(MIN.)": 2,
                 "ESPATO FLÚOR": 6, "ESTRONCIO": 2, "MAGNESITA CRUDA": 3, "GLAUBERITA": 3, "THENARDITA": 1}
BDMIN_WHERE = " OR ".join(f"Sustancia LIKE '%{s}%'" for s in sorted({s for _, subs in KIND.values() for s in subs}))
SIZE_RANK = {"grande": 0, "mediano": 1}  # BDMIN's 'Tamaño_indicio'; 'pequeño' and 'desconocido' never stand alone
# Older province names IGME uses → INE code (the others match INE's names).
PROVINCE_ALIASES = {"orense": "32", "gerona": "17", "lerida": "25", "vizcaya": "48", "guipuzcoa": "20",
                    "baleares": "07", "coruna": "15", "la coruna": "15"}
STOP = {"mina", "minas", "grupo", "minero", "otras", "otros", "fraccion", "concesion", "explotacion", "derivada",
        "del", "las", "los", "indicio", "indicios"}


def norm(text: str | None) -> str:
    """Lower case without accents or punctuation; INE's inverted articles put back ('Santos (Los)' → 'los santos')."""
    t = unicodedata.normalize("NFD", (text or "").lower().strip())
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    t = re.sub(r"\s*\((.+?)\)$", r", \1", t)
    if m := re.match(r"(.+?), (\S+)$", t):
        t = f"{m.group(2)} {m.group(1)}"
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


PROVINCE_CODES = {norm(part): code for code, (_, n) in PROVINCES.items() for part in n.split("/")} | PROVINCE_ALIASES


def province_code(name: str) -> str:
    code = PROVINCE_CODES.get(norm(name))
    if not code:
        raise RuntimeError(f"IGME: unknown province {name!r}")
    return code


def words(name: str) -> list[str]:
    """A name's significant words, in order."""
    return [w for w in norm(name).split() if len(w) >= 3 and w not in STOP]


def same_name(a: str, b: str) -> bool:
    """Two names share a significant word, or read the same run together ('Rio Tinto' and 'Riotinto')."""
    wa, wb = words(a), words(b)
    return bool(set(wa) & set(wb)) or bool(wa and "".join(wa) == "".join(wb))


def locate(mine: dict, deposits: list[dict]) -> dict | None:
    """The BDMIN deposit a working is placed at, among those of its mineral in its municipality: the one whose name
    shares a word with the working's (the largest such, then the first by IGME code), else the municipality's only
    deposit rated large or medium; None when neither exists."""
    subs = KIND[mine["substance"]][1]
    here = [d for d in deposits if d["province"] == mine["province"] and norm(d["municipality"]) == norm(mine["municipality"])
            and any(s in d["substance"] for s in subs)]
    rank = lambda d: (SIZE_RANK.get(d["size"], 9), d["code"])
    named = sorted((d for d in here if same_name(mine["name"], d["name"])), key=rank)
    if named:
        return named[0]
    sized = [d for d in here if d["size"] in SIZE_RANK]
    return sized[0] if len(sized) == 1 else None


class IgmeMinas(Source):
    info = SourceInfo(
        id="igme_minas",
        title=f"Active mines {YEAR} (Estadística Minera de España, IGME) placed with IGME's BDMIN deposits",
        publisher="IGME-CSIC (Instituto Geológico y Minero de España); Ministerio para la Transición Ecológica "
        "(Estadística Minera de España)",
        homepage="https://www.igme.es/es/panorama-minero",
        license="IGME licence of use: free reuse, commercial or not, citing the source (Ley 37/2007, RD 1495/2011)",
        description=f"The workings active in {YEAR} that the Estadística Minera de España lists, as IGME publishes "
        "them with Panorama Minero 2022 (EXPLOTACIONES_2019.xlsx); the metal mines and the potash, fluorspar, "
        "celestine, magnesite and sodium-sulphate mines are kept, and their count per substance matches the "
        "Panorama's tables. Positions are those of the matching deposit in IGME's BDMIN mineral-occurrence database.",
        used_for=["Mines on the map (resources)"],
    )

    def fetch(self, force=False):
        self.download(LIST_URL, LIST_FILE, force=force, expect_binary=True)
        # The Panorama whose tables the counts are checked against, cached for provenance.
        self.download(PANORAMA_URL, PANORAMA_FILE, force=force, expect_binary=True)
        page = 0
        while True:
            query = urllib.parse.urlencode({"where": BDMIN_WHERE, "outFields": "*", "returnGeometry": "false",
                                            "orderByFields": "Codigo_indicio", "resultOffset": page * PAGE,
                                            "resultRecordCount": PAGE, "f": "json"})
            path = self.download(f"{BDMIN}?{query}", f"bdmin_indicios_{page}.json", force=force)
            if not json.loads(path.read_text()).get("exceededTransferLimit"):
                break
            page += 1

    def deposits(self) -> tuple[list[dict], list[str]]:
        out, files, page = [], [], 0
        while (path := self.raw_dir / f"bdmin_indicios_{page}.json").exists():
            doc = json.loads(path.read_text())
            files.append(path.name)
            for f in doc["features"]:
                a = f["attributes"]
                province = PROVINCE_CODES.get(norm(a["Provincia"]))
                if not province:
                    continue
                out.append({"code": a["Codigo_indicio"], "name": (a["Nombre_mina"] or "").strip(),
                            "municipality": a["Municipio"] or "", "province": province,
                            "substance": a["Sustancia"] or "", "size": a["Tamaño_indicio"],
                            "lon": a["X"], "lat": a["Y"]})
            if not doc.get("exceededTransferLimit"):
                break
            page += 1
        return out, files

    def process(self):
        rows = next(iter(sheets(self.raw_dir / LIST_FILE).values()))
        head = rows[0]
        mines = [dict(zip(head, r)) for r in rows[1:] if r and r[head.index("Sustancia")] in KIND]
        got = Counter(m["Sustancia"] for m in mines)
        if got != Counter(PANORAMA_2019):
            raise RuntimeError(f"IGME {YEAR}: workings per substance {dict(got)} != Panorama Minero 2022 {PANORAMA_2019}")
        deposits, files = self.deposits()
        out = []
        for m in mines:
            mine = {"name": " ".join(m["Explotacion"].split()), "company": " ".join(m["Empresa"].split()),
                    "municipality": m["Municipio_Explotacion"], "province": province_code(m["Provincia_Explotacion"]),
                    "substance": m["Sustancia"], "type": KIND[m["Sustancia"]][0]}
            d = locate(mine, deposits) or {}
            out.append(mine | {"lon": d.get("lon"), "lat": d.get("lat"), "deposit": d.get("name") or None,
                               "deposit_size": d.get("size")})
        return {"vintage": f"Estadística Minera de España {YEAR} (IGME, Panorama Minero 2022); BDMIN",
                "_files": [LIST_FILE, PANORAMA_FILE, *files], "year": YEAR, "mines": out}
