"""Fiestas each autonomous community declares of tourist interest at its own level (Fiesta de Interés Turístico de
Andalucía, Festa de Interese Turístico de Galicia, Fiesta de Interés Turístico Regional…), from each community's
official list, transcribed and placed in data/fiestas_autonomicas.csv.

The lists come as an open-data CSV, an HTML page, a PDF register or a run of bulletin orders, so the table in the
repository is the transcription (names, places and dates as each source writes them, and the source's URL on every
row) and the placement (INE codes). `fetch` caches every document the table cites and each community's `documents`,
for provenance. Where a list can be read with the standard library (`LISTS`), the build reads it and fails unless the
table has exactly its fiestas, so a new declaration is not missed. A fiesta the State has since declared Nacional or
Internacional names that entry of fiestas_interes_turistico.csv in `state_same`, and the map counts it once, at the
State's category. Rules: DECISIONS.md E77–E79 and F34.
"""

from __future__ import annotations

import csv
import hashlib
import html
import re
from pathlib import Path
from urllib.parse import urlsplit

from ...core.fetch import read_manifest
from ...core.source import Source, SourceInfo
from .fiestas import TABLE as STATE_TABLE
from .names import title_es
from .tls import FNMT_SERVIDORES_SEGUROS, GLOBALSIGN_R46, SECTIGO_R46_DV_R36

TABLE = Path(__file__).parent / "data" / "fiestas_autonomicas.csv"

# Community → its name, its declaration as its rules name it, those rules, and documents cached beside the cited ones
# (where the dates come from when that is not the list itself). A community absent here declares none (NONE). The name
# is the one its list uses, as the rest of the transcription; the interface's own short names are
# provinces.COMMUNITY_NAMES.
COMMUNITIES = {
    "andalucia": {"name": "Andalucía", "declaration": "Fiesta de Interés Turístico de Andalucía",
                  "rules": "Ley 13/2011 del Turismo de Andalucía, art. 58; Decreto 116/2016"},
    "aragon": {"name": "Aragón", "declaration": "Fiesta de Interés Turístico de Aragón", "rules": "Decreto 295/2005"},
    "asturias": {"name": "Principado de Asturias",
                 "declaration": "Fiesta o Actividad de Interés Turístico del Principado de Asturias",
                 "rules": "Ley 7/2001 de Turismo, art. 59; Decreto 64/2022"},
    "canarias": {"name": "Canarias", "declaration": "Fiesta de Interés Turístico de Canarias",
                 "rules": "Decreto 18/2008"},
    "cantabria": {"name": "Cantabria", "declaration": "Fiesta de Interés Turístico Regional",
                  "rules": "Decreto 12/1993; Ley 5/1999, art. 43"},
    "castilla-leon": {"name": "Castilla y León", "declaration": "Fiesta de Interés Turístico de Castilla y León",
                      "rules": "Ley 14/2010 de Turismo de Castilla y León, art. 67; Orden de 14 de marzo de 1995",
                      "documents": [f"https://www.turismocastillayleon.com/es/{p}.relaciones" for p in (
                          "avila", "burgos", "leon", "palencia", "salamanca", "segovia", "soria", "valladolid",
                          "zamora")]},
    "castilla-la-mancha": {"name": "Castilla-La Mancha",
                           "declaration": "Fiesta de Interés Turístico Regional de Castilla-La Mancha",
                           "rules": "Decreto 32/2006"},
    "catalunya": {"name": "Catalunya", "declaration": "Festa local d'interès turístic",
                  "rules": "declarades per la Direcció General de Turisme de la Generalitat (1986-2010)"},
    "extremadura": {"name": "Extremadura", "declaration": "Fiesta de Interés Turístico de Extremadura",
                    "rules": "Decreto 152/1997"},
    "galicia": {"name": "Galicia", "declaration": "Festa de Interese Turístico de Galicia",
                "rules": "Lei 7/2011 do turismo de Galicia, art. 93; Decreto 4/2015"},
    "madrid": {"name": "Comunidad de Madrid", "declaration": "Fiesta de Interés Turístico Regional",
               "rules": "Ley 1/1999 de Ordenación del Turismo, art. 44"},
    "murcia": {"name": "Región de Murcia", "declaration": "Fiesta de Interés Turístico Regional",
               "rules": "Ley 12/2013 de Turismo, art. 13; Decreto 200/2017"},
    "navarra": {"name": "Navarra", "declaration": "Fiesta de Interés Turístico de Navarra",
                "rules": "Decreto Foral 45/2010"},
    "rioja": {"name": "La Rioja", "declaration": "Fiesta de Interés Turístico de La Rioja", "rules": "Decreto 10/2017"},
    "valenciana": {"name": "Comunitat Valenciana", "declaration": "Fiesta de Interés Turístico Autonómico",
                   "rules": "Decreto 119/2006"},
}

# Communities whose government declares no fiesta of tourist interest of its own, and the rule that shows it.
NONE = {
    "balears": "Illes Balears: la Llei 8/2012 del turisme (art. 6.1.e) y el Decret 20/2015 permitían al Govern declarar "
    "fiestas de interés turístico autonómico; no declaró ninguna (BOIB), y la Llei 4/2026 deroga esa potestad",
    "euskadi": "Euskadi: la Ley 13/2016 de Turismo no prevé declarar fiestas de interés turístico",
    "ceuta": "Ceuta: el Reglamento de Turismo de 30 de noviembre de 2010 no prevé declarar fiestas de interés turístico",
    "melilla": "Melilla: el Reglamento de Turismo (Decreto 351/2010, art. 45) crea las Fiestas de interés turístico "
    "local y de excelencia turística, pero no consta ninguna concedida (BOME)",
}

# Hosts whose TLS chain ends in a root the system bundle may lack (pipeline/sources/es/tls.py).
CAFILE = {"www.boa.aragon.es": GLOBALSIGN_R46, "datosabiertos.castillalamancha.es": GLOBALSIGN_R46,
          "docm.jccm.es": GLOBALSIGN_R46, "lariojaturismo.com": SECTIGO_R46_DV_R36,
          "www.turismoextremadura.com": FNMT_SERVIDORES_SEGUROS}

MONTHS = {  # Spanish, Galician and Catalan month names → month number
    1: "enero xaneiro gener", 2: "febrero febreiro febrer", 3: "marzo març", 4: "abril", 5: "mayo maio maig",
    6: "junio xuño juny", 7: "julio xullo juliol", 8: "agosto agost", 9: "septiembre setiembre setembro setembre",
    10: "octubre outubro", 11: "noviembre novembro novembre", 12: "diciembre decembro desembre",
}
MONTH = {w: m for m, words in MONTHS.items() for w in words.split()}


def months(when: str) -> list[int]:
    """The months a date text names, in calendar order ("del 30 de abril al 3 de mayo" → [4, 5]); none for a movable
    feast the text does not tie to a month ("Semana Santa", "Carnaval")."""
    return sorted({MONTH[w] for w in re.findall(r"[^\W\d_]+", when.lower()) if w in MONTH})


def cache_name(url: str) -> str:
    """The cached file of a URL: its host, a short hash of the URL and the extension its path ends in."""
    parts = urlsplit(url)
    ext = re.search(r"\.(pdf|csv|xlsx|json|html?)$", parts.path.lower())
    return f"{parts.hostname}/{hashlib.sha1(url.encode()).hexdigest()[:12]}.{ext.group(1) if ext else 'html'}"


def documents(rows: list[dict]) -> list[str]:
    """Every URL the table cites, every community document and every page of the machine-readable lists, once."""
    return list(dict.fromkeys([u for r in rows for u in r["source"].split()] +
                              [u for c in COMMUNITIES.values() for u in c.get("documents", [])] +
                              [u for urls, _ in LISTS.values() for u in urls]))


def read_table(path: Path = TABLE) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(line for line in f if not line.startswith("#")))


def row_problem(r: dict, seen: bool, state_names: set[str]) -> str:
    """What is wrong with a table row, the first thing found, or "" when nothing is."""
    if r["community"] not in COMMUNITIES:
        return "unknown community"
    if seen:
        return "listed twice"
    if not all(len(m) == 5 and m.isdigit() for m in r["municipalities"].split()):
        return "bad INE codes"
    if r["state_same"] and r["state_same"] not in state_names:
        return f"state_same {r['state_same']!r} is not in the State's table"
    if not r["source"]:
        return "no source"
    return ""


def fiestas(rows: list[dict], state_names: set[str]) -> list[dict]:
    """The table's fiestas, checked, with names in capitals written as Spanish writes them (title_es): a known community, one row per (community, name, place), INE codes, a
    `state_same` that is an entry of the State's table, a source."""
    seen, out = set(), []
    for r in rows:
        key = (r["community"], r["name"], r["place"])
        if problem := row_problem(r, key in seen, state_names):
            raise RuntimeError(f"fiestas_autonomicas.csv, {key}: {problem}")
        seen.add(key)
        out.append({"name": title_es(r["name"]), "community": r["community"], "place": r["place"],
                    "municipalities": r["municipalities"].split(), "when": r["when"] or None, "months": months(r["when"]),
                    "state_same": r["state_same"] or None})
    return out


def listed(raw_dir: Path, community: str) -> list[str]:
    """The fiesta names on a community's machine-readable list, read from its cached pages."""
    urls, read = LISTS[community]
    return [n for u in urls for n in read((raw_dir / cache_name(u)).read_text(encoding="utf-8"))]


def check_lists(rows: list[dict], lists: dict[str, list[str]]) -> None:
    """Fail unless the table holds, for each community with a machine-readable list, exactly the names on it."""
    for community, names in lists.items():
        have = sorted(r["name"] for r in rows if r["community"] == community)
        if have != sorted(names):
            raise RuntimeError(f"fiestas_autonomicas.csv out of date for {community}: not in the table "
                               f"{sorted(set(names) - set(have))}, no longer listed {sorted(set(have) - set(names))}"
                               f" ({len(have)} rows, {len(names)} listed)")


def clean(text: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", text)).split())


def andalucia_names(text: str) -> list[str]:
    """The Junta's open-data CSV ('=' between fields): the rows of ámbito Autonómico and tipo Fiesta."""
    rows = list(csv.reader(text.splitlines(True), delimiter="="))
    col = {h.strip(): k for k, h in enumerate(rows[0])}
    return [" ".join(r[0].split()) for r in rows[1:]
            if r and r[col["ÁMBITO"]].strip() == "Autonómico" and r[col["TIPO"]].strip() == "Fiesta"]


def galicia_names(text: str) -> list[str]:
    """Turismo de Galicia's resource locator filtered to the Festas de Interese Turístico de Galicia (subtype 261)."""
    return [clean(m) for m in re.findall(r'class="title mod-href">(.*?)</a>', text, re.S)]


def cantabria_names(text: str) -> list[str]:
    """turismodecantabria.com's tables: the first cell of the rows with data-tipo="regional"."""
    rows = re.findall(r'<tr\s[^>]*data-tipo="([^"]*)"[^>]*>(.*?)</tr>', text, re.S)
    return [clean(re.search(r"<td>(.*?)</td>", body, re.S).group(1)) for kind, body in rows if kind == "regional"]


def canarias_names(text: str) -> list[str]:
    """The Consejería's register page: the first cell of each row of the table after "(Registro)"."""
    body = re.search(r"<tbody>(.*?)</tbody>", text[text.index("(Registro)"):], re.S).group(1)
    return [clean(re.search(r"<td[^>]*>(.*?)</td>", row, re.S).group(1))
            for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S)]


def extremadura_names(text: str) -> list[str]:
    """One page of turismoextremadura.com's list of fiestas: the link of each item's h2.titu2."""
    return [clean(m) for m in re.findall(r'<h2 class="titu2"[^>]*>\s*<a[^>]*>(.*?)</a>', text, re.S)]


GALICIA_LIST = ("https://www.turismo.gal/localizador-de-recursos?p_p_id=buscador_de_recursos_ritga_portlet_WAR_ritgaportlet"
                "&p_p_lifecycle=1&p_p_state=normal&p_p_mode=view&p_p_col_id=column-1&p_p_col_count=1"
                "&pBsq%23%2326%23%2397%23%23subtipo%23%23261=on&orden=0&reverse=0&items=200&indexPage=1&langId=gl_ES")
# Community → (URLs of the pages of its machine-readable list, the function that reads the fiesta names on a page).
LISTS = {
    "andalucia": (["https://www.juntadeandalucia.es/datosabiertos/portal/dataset/9c1437e9-98bd-41e5-84cf-6bf678037b1b/"
                   "resource/827cb3e2-fe05-4c37-92d3-ed31f2935f35/download/dataset_interes_turistico_07072026.csv"],
                  andalucia_names),
    "canarias": (["https://www.gobiernodecanarias.org/turismo/fiestas/index.html"], canarias_names),
    "cantabria": (["https://turismodecantabria.com/disfrutala/fiestas-de-interes/"], cantabria_names),
    "extremadura": ([f"https://www.turismoextremadura.com/es/recursos-turisticos/fiestas-extremadura/index.html"
                     f"?paginaBusqueda={n}" for n in range(1, 9)], extremadura_names),
    "galicia": ([GALICIA_LIST], galicia_names),
}


class FiestasAutonomicas(Source):
    info = SourceInfo(
        id="fiestas_autonomicas",
        title="Fiestas declared of tourist interest by the autonomous communities",
        publisher="The tourism departments of the autonomous communities, in their bulletins, registers, tourism "
        "portals and open data",
        homepage="https://www.juntadeandalucia.es/datosabiertos/portal/dataset/declaraciones-de-interes-turistico-en-andalucia",
        license="Public-sector information, reuse citing the source (Ley 37/2007)",
        description="The fiestas each autonomous community has declared of tourist interest at its own level, from "
        "its official list, register or bulletin orders, with the dates the source gives, placed in their "
        "municipalities by a table kept in this repository (pipeline/sources/es/data/fiestas_autonomicas.csv) that "
        "cites the source of each row. A fiesta the State has since declared of National or International tourist "
        "interest counts once, at the State's category.",
        used_for=["Fiestas lens", "Party index lens", "Fiesta calendar (fiestas.json)"],
    )

    def fetch(self, force=False):
        for url in documents(read_table()):
            self.download(url, cache_name(url), force=force, cafile=CAFILE.get(urlsplit(url).hostname))

    def process(self):
        rows = read_table()
        found = fiestas(rows, {r["name"] for r in read_table(STATE_TABLE)})
        check_lists(rows, {c: listed(self.raw_dir, c) for c in LISTS})
        retrieved = min(v["retrieved"] for v in read_manifest(self.id).values())[:10]
        return {"vintage": retrieved,
                "_files": [cache_name(u) for u in documents(rows)],
                "communities": COMMUNITIES, "none": NONE, "fiestas": found}
