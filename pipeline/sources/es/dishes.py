"""Regional dishes and foods of each Spanish province: the articles of the Spanish Wikipedia's "Gastronomía de
<province>" categories that Wikidata says are a food or a drink.

The category lists which articles belong to a province's cuisine (dishes, sausages, cheeses, sweets, wines, but also
restaurants, cooks and towns); Wikidata's class tree keeps only the foods and drinks. Each answer is cached like any
download, so a build is reproducible from the cache.
"""

from __future__ import annotations

import json
import re
import urllib.parse

from ...core.source import Source, SourceInfo

API = "https://es.wikipedia.org/w/api.php?format=json&formatversion=2&"
SPARQL = "https://query.wikidata.org/sparql?format=json&query="
HEADERS = {"User-Agent": "spainciv/0.1 (https://github.com/DjinnFoundry/spainciv)"}
# Category (after "Categoría:Gastronomía de ") → INE province codes. The Wikipedia names provinces in Spanish
# (Gerona, Orense…); the archipelagos and single-province communities have one category for the whole community.
CATEGORIES = {
    "Álava": ["01"], "la provincia de Albacete": ["02"], "la provincia de Alicante": ["03"],
    "la provincia de Almería": ["04"], "la provincia de Ávila": ["05"], "la provincia de Badajoz": ["06"],
    "las Islas Baleares": ["07"], "la provincia de Barcelona": ["08"], "la provincia de Burgos": ["09"],
    "la provincia de Cáceres": ["10"], "la provincia de Cádiz": ["11"], "la provincia de Castellón": ["12"],
    "la provincia de Ciudad Real": ["13"], "la provincia de Córdoba (España)": ["14"],
    "la provincia de La Coruña": ["15"], "la provincia de Cuenca": ["16"], "la provincia de Gerona": ["17"],
    "la provincia de Granada": ["18"], "la provincia de Guadalajara": ["19"], "Guipúzcoa": ["20"],
    "la provincia de Huelva": ["21"], "la provincia de Huesca": ["22"], "la provincia de Jaén": ["23"],
    "la provincia de León": ["24"], "la provincia de Lérida": ["25"], "La Rioja (España)": ["26"],
    "la provincia de Lugo": ["27"], "la Comunidad de Madrid": ["28"], "la provincia de Málaga": ["29"],
    "la Región de Murcia": ["30"], "Navarra": ["31"], "la provincia de Orense": ["32"], "Asturias": ["33"],
    "la provincia de Palencia": ["34"], "Canarias": ["35", "38"], "la provincia de Pontevedra": ["36"],
    "la provincia de Salamanca": ["37"], "Cantabria": ["39"], "la provincia de Segovia": ["40"],
    "la provincia de Sevilla": ["41"], "la provincia de Soria": ["42"], "la provincia de Tarragona": ["43"],
    "la provincia de Teruel": ["44"], "la provincia de Toledo": ["45"], "la provincia de Valencia": ["46"],
    "la provincia de Valladolid": ["47"], "Vizcaya": ["48"], "la provincia de Zamora": ["49"],
    "la provincia de Zaragoza": ["50"], "Ceuta": ["51"], "Melilla": ["52"],
}
CHUNK = 200  # QIDs per Wikidata query
FOOD_QUERY = """SELECT DISTINCT ?item WHERE {
  VALUES ?item { %s }
  VALUES ?root { wd:Q2095 wd:Q40050 }
  ?item (wdt:P31|wdt:P279)/wdt:P279* ?root.
}"""  # food, drink


def slug(category: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", category.lower().encode("ascii", "ignore").decode()).strip("_")


class GastronomiaEs(Source):
    info = SourceInfo(
        id="gastronomia_es",
        title="Regional dishes and foods by province (Spanish Wikipedia categories, filtered with Wikidata)",
        publisher="Wikipedia en español and Wikidata (Wikimedia Foundation and volunteer editors)",
        homepage="https://es.wikipedia.org/wiki/Categor%C3%ADa:Gastronom%C3%ADa_de_Espa%C3%B1a_por_provincia",
        license="Wikipedia: CC BY-SA 4.0 (titles only are used); Wikidata: CC0",
        description="The articles in each province's 'Gastronomía de …' category of the Spanish Wikipedia that "
        "Wikidata classes as a food or a drink: dishes, sausages, cheeses, sweets, breads, wines. Volunteer-edited: "
        "some provinces are far better covered than others (Madrid dozens, Álava a handful), and the Canary Islands "
        "share one category.",
        used_for=["Regional dishes lens"],
    )

    def fetch(self, force=False):
        for category in CATEGORIES:
            title = f"Categoría:Gastronomía de {category}"
            query = urllib.parse.urlencode({"action": "query", "generator": "categorymembers", "gcmtitle": title,
                                            "gcmnamespace": 0, "gcmlimit": "max", "prop": "pageprops",
                                            "ppprop": "wikibase_item"})
            self.download(API + query, f"cat_{slug(category)}.json", force=force, headers=HEADERS)
        qids = sorted({q for _, q in self._members()})
        for k in range(0, len(qids), CHUNK):
            sparql = FOOD_QUERY % " ".join(f"wd:{q}" for q in qids[k:k + CHUNK])
            self.download(SPARQL + urllib.parse.quote(" ".join(sparql.split())), f"food_{k // CHUNK:02d}.json",
                          force=force, headers={**HEADERS, "Accept": "application/sparql-results+json"})

    def _members(self) -> list[tuple[str, str]]:
        """(category, QID) for every article of every category."""
        out = []
        for category in CATEGORIES:
            path = self.raw_dir / f"cat_{slug(category)}.json"
            if not path.exists():
                continue
            data = json.loads(path.read_text())
            if "continue" in data:
                raise RuntimeError(f"{path.name}: more members than one page; paginate")
            for page in data.get("query", {}).get("pages", []):
                qid = page.get("pageprops", {}).get("wikibase_item")
                if qid and not page["title"].startswith("Gastronomía"):
                    out.append((category, qid))
        return out

    def process(self):
        titles: dict[str, str] = {}
        files = []
        for category in CATEGORIES:
            name = f"cat_{slug(category)}.json"
            if (self.raw_dir / name).exists():
                files.append(name)
                for page in json.loads((self.raw_dir / name).read_text()).get("query", {}).get("pages", []):
                    if q := page.get("pageprops", {}).get("wikibase_item"):
                        titles[q] = page["title"]
        food = set()
        for path in sorted(self.raw_dir.glob("food_*.json")):
            files.append(path.name)
            food |= {b["item"]["value"].rsplit("/", 1)[-1] for b in json.loads(path.read_text())["results"]["bindings"]}
        dishes: dict[str, dict] = {}
        for category, qid in self._members():
            if qid in food:
                d = dishes.setdefault(qid, {"qid": qid, "name": re.sub(r"\s*\(.*\)$", "", titles[qid]),
                                            "provinces": []})
                for code in CATEGORIES[category]:
                    if code not in d["provinces"]:
                        d["provinces"].append(code)
        return {"vintage": "Wikipedia, Wikidata", "_files": files,
                "dishes": sorted(dishes.values(), key=lambda d: d["name"])}
