"""Spain's cities, provinces, nation and lenses, on the shared helpers of the US builders.

First cut (see docs/SPAIN.md):

* **Cities** are the large urban areas (AUDES: over 50,000 residents), named after and placed at their core
  municipality's capital (SIANE), on the nearest free land hex of its province. Population, Padrón series, jobs and
  footprint add up the member municipalities (the US metro rule, cities.footprints). Employment leaves out the members
  of under 500 residents, which INE does not publish by section (three areas, a few thousand residents).
* **Gold** is GDP at market prices (INE Contabilidad Regional), which INE publishes down to provinces: provinces and
  the nation have it; cities don't (there is no official municipal GDP, and none is made up here).
* **Food, Production, Science, Culture** count employed residents by CNAE section (INE Annual Population Census: cities,
  provinces, Spain), mapped to the US industry keys so the US yield definitions apply unchanged. Median household
  income, rent, home value and unemployment stay null.
* **Growth** is Padrón population change from BASELINE_YEAR to the Padrón year, like the US rule (cap ±25%).
* **Lenses**: population density (each municipality's Padrón population spread over its hexes, lenses.spread_population),
  income (INE ADRH mean net income per person, population-weighted over each hex's municipalities) and the land-cover
  shares (CORINE, lenses.land_lenses). ADRH is a mean per person, not the US median per household, so it is a lens of
  its own and the cities' `median_income` stays null.
"""

from __future__ import annotations

import math
import re
import unicodedata

from ..core.geo import Shape, geojson_rings, ring_area, ring_centroid
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_interim_payload, write_web
from ..countries import active
from .cities import add_ranks, footprints, free_cell, nearest_land
from .growth import BASELINE_YEAR, rate
from .lenses import COUNTY_LENSES, GROUPS, land_lenses, set_domains, spread_population
from .states import label_anchor, land_shares
from .spain_wonders import place_key
from .yields import YIELDS

REQUIRES = ["_world", "siane", "audes", "ine_padron", "ine_pib", "ine_adrh", "ine_censo_ocupados", "wikidata_es",
            "calidad_diferenciada", "pleiades_iberia", "lenguas_es", "bandera_azul"]
PRODUCES = ["cities.json", "nation.json", "states.json", "lenses.json"]
COUNTRIES = ("es",)

SERIES_FROM = 2020  # pop_series spans the same years as the US map's (the full Padrón series is in the interim)

WORKERS = "Employed residents, counted where they live (INE Annual Population Census, 1 January {year})"
YIELD_TEXT = {
    "food": WORKERS + ": agriculture, livestock, forestry and fishing (CNAE section A).",
    "production": WORKERS + ": mining (B), manufacturing (C) and construction (F), the US map's three industries.",
    "gold": "Gross domestic product at market prices, current euros (INE Contabilidad Regional de España). INE publishes "
    "it down to provinces, so cities have no Gold of their own.",
    "science": WORKERS + ": information & communication (J) and professional, scientific & technical services (M).",
    "culture": WORKERS + ": arts, entertainment & recreation (R).",
}
# CNAE-2009 section → the industry key the map uses (yields.INDUSTRY_LINES), with the Spanish section's own label.
CNAE = {
    "A": ("agriculture", "Agriculture, livestock, forestry & fishing"), "B": ("mining", "Mining & quarrying"),
    "C": ("manufacturing", "Manufacturing"), "D": ("utilities", "Energy, water & waste"), "E": ("utilities", None),
    "F": ("construction", "Construction"), "G": ("retail", "Wholesale & retail trade, motor-vehicle repair"),
    "H": ("transportation", "Transportation & storage"), "I": ("accommodation", "Accommodation & food services"),
    "J": ("information", "Information & communication"), "K": ("finance", "Finance & insurance"),
    "L": ("real_estate", "Real estate"), "M": ("professional", "Professional, scientific & technical"),
    "N": ("admin", "Administrative & support services"), "O": ("public_admin", "Public administration & defence"),
    "P": ("education", "Education"), "Q": ("health", "Health & social work"), "R": ("arts", "Arts, entertainment & recreation"),
    "S": ("other", "Other services, households as employers, extraterritorial bodies"), "T": ("other", None), "U": ("other", None),
}
INDUSTRIES = {key: label for key, label in CNAE.values() if label}
ECON_NULL = {"median_income": None, "median_rent": None, "home_value": None, "unemployment": None, "rent_burden": None}


def yields_es(year: int | None = None) -> list[dict]:
    """The US yield definitions (keys, icons, colours, industries) with Spain's sources; Gold is in euros."""
    return [{**y, "unit": "eur" if y["key"] == "gold" else y["unit"], "description": YIELD_TEXT[y["key"]].format(year=year)}
            for y in YIELDS]


def jobs_of(sections: dict[str, int] | None) -> dict[str, int | None] | None:
    """Workers by CNAE section → by the map's industry keys (D+E, S+T+U add up); an industry with a section missing
    from the source is null, never a partial sum."""
    if not sections:
        return None
    out: dict[str, int | None] = {}
    for sec, (key, _) in CNAE.items():
        v = sections.get(sec)
        out[key] = None if v is None or (key in out and out[key] is None) else out.get(key, 0) + v
    return out


def total(jobs: dict | None, keys: list[str]) -> int | None:
    """Sum of the industries, or None if any of them is unknown."""
    if not jobs or any(jobs.get(k) is None for k in keys):
        return None
    return sum(jobs[k] for k in keys)


def econ(population: int | None, gdp: float | None, gdp_year: int | None, workers: dict[str, int] | None = None) -> dict:
    jobs = jobs_of(workers)
    return {
        "population": population, "employed": workers.get("total") if workers else None, "jobs": jobs or {}, **ECON_NULL,
        "yields": {y["key"]: (gdp if y["key"] == "gold" else total(jobs, y["industries"])) for y in YIELDS},
        "gdp": gdp, "gdp_year": gdp_year if gdp is not None else None,
    }


# AUDES names of municipalities INE has since renamed: AUDES name → today's INE name (matched like any other name).
ALIASES = {
    "Bigues i Riells": "Bigues i Riells del Fai",
    "Arrankudiaga": "Arrankudiaga-Zollo",
    "Castell-Platja d'Aro": "Castell d'Aro, Platja d'Aro i s'Agaró",
}
AREA_TOLERANCE = 0.03  # an area's matched population must be within 3% of the AUDES figure (a different count date)
AUDES_POP_YEAR = "2024"  # the population year the AUDES list gives, used to check the matched members


def name_keys(name: str) -> set[str]:
    """Comparable forms of a municipality name: accents and punctuation dropped, each co-official form, and INE's
    inverted articles both ways ('Palmas de Gran Canaria, Las' = 'Las Palmas de Gran Canaria')."""
    def norm(t: str) -> str:
        t = unicodedata.normalize("NFD", t.lower())
        return re.sub(r"[^a-z0-9]+", " ", "".join(ch for ch in t if unicodedata.category(ch) != "Mn")).strip()

    out = set()
    for part in name.split("/"):
        p = part.strip()
        out.add(norm(p))
        for pat in (r"(.*),\s*(\S+)$", r"(.*)\(([^)]+)\)$"):
            m = re.match(pat, p)
            if m:
                out |= {norm(f"{m.group(2)} {m.group(1)}"), norm(m.group(1))}
    return out


def urban_areas(areas: list[dict], muni: dict, centre: dict) -> list[dict]:
    """AUDES areas with their members as INE codes: [{id (the core, first-listed member), full, members}].

    Names are matched to the Padrón's; a name several municipalities share goes to the one nearest the area's core.
    An area whose members are not all found, or whose population is off by more than AREA_TOLERANCE, is an error: a
    wrong match must not slip into the map.
    """
    index: dict[str, set[str]] = {}
    for code, m in muni.items():
        if code in centre:
            for k in name_keys(m["name"]):
                index.setdefault(k, set()).add(code)

    def near(a: str, b: str) -> float:
        (x0, y0), (x1, y1) = centre[a], centre[b]
        return math.hypot((x1 - x0) * math.cos(math.radians(y0)), y1 - y0)

    def pop(c: str) -> int:
        return muni[c]["pop"].get(AUDES_POP_YEAR) or 0

    out, problems = [], []
    for a in areas:
        members: list[str] = []
        for name in a["members"]:
            cands = set().union(*(index.get(k, set()) for k in name_keys(ALIASES.get(name, name))))
            if not cands:
                problems.append(f"{a['name']}: no INE municipality named {name!r}")
                continue
            members.append(max(cands, key=pop) if not members else min(cands, key=lambda c: near(c, members[0])))
        total = sum(pop(c) for c in members)
        if len(set(members)) != a["municipalities"] or abs(total - a["population"]) > AREA_TOLERANCE * a["population"]:
            problems.append(f"{a['name']}: {len(set(members))} of {a['municipalities']} municipalities, population "
                            f"{total:,} vs {a['population']:,}")
            continue
        rest = re.sub(r"^ÁREA URBANA\s*", "", a["label"], flags=re.I)
        words = [w.lower() if w.lower() in ("de", "del", "la", "las", "los", "el", "y") else w.capitalize() for w in rest.split()]
        out.append({"id": members[0], "full": "Área urbana " + " ".join(words), "members": members})
    if problems:
        raise RuntimeError("AUDES areas that don't match the Padrón:\n  " + "\n  ".join(problems))
    return out


def add_series(series: list[dict[str, int | None]]) -> dict[str, int | None]:
    """Year-by-year sum of the members' Padrón series; a year with a member missing is None."""
    years = sorted(set().union(*series))
    return {y: (sum(s[y] for s in series) if all(s.get(y) is not None for s in series) else None) for y in years}


def add_sections(rows: list[dict | None]) -> dict[str, int] | None:
    """Census employment of an area: the sum of its members INE publishes (municipalities of 500 residents or more)."""
    known = [r for r in rows if r]
    if not known:
        return None
    out: dict[str, int] = {}
    for r in known:
        for k, v in r.items():
            out[k] = out.get(k, 0) + v
    return out


def growth_of(series: dict[str, int | None], years: list[int]) -> float | None:
    return rate(series.get(str(years[1])), series.get(str(years[0]))) if years else None


def income_lens(adrh_p: dict, geoids: list[str], weights: list) -> dict:
    """Mean net income per person (INE ADRH), population-weighted over each hex's municipalities; null where none of
    the hex's municipalities has a figure (INE leaves out the smallest for confidentiality)."""
    adrh = adrh_p["data"]
    per_person = [(adrh["municipalities"].get(g) or {}).get("net_per_person") for g in geoids]
    values = []
    for parts in weights:
        vals = [(per_person[k], p) for k, p in parts if per_person[k] is not None]
        wsum = sum(p for _, p in vals)
        values.append(round(sum(v * p for v, p in vals) / wsum) if wsum else None)
    meta = COUNTY_LENSES["income"][1]
    return {
        "id": "income", **{k: meta[k] for k in ("group", "name", "icon", "emoji", "scale", "higher_is", "ramp")},
        "unit": "net income per person, €", "format": "eur", "source": "ine_adrh",
        "description": f"Mean net income per person of the municipalities in each hex, weighted by population (INE Atlas "
        f"de Distribución de Renta de los Hogares, {adrh['year']}: tax records matched to the Padrón). A mean per person, "
        "not the US map's median per household.",
        "values": values,
    }


ES_GROUPS = [{"id": "heritage", "name": "Heritage"}, {"id": "food", "name": "Food & drink"}]


def heritage_lens(points: list, proj, grid: HexGrid, owner: list[int]) -> dict:
    """Bienes de Interés Cultural per land hex (a count, 0 included: the lens shows where heritage is dense)."""
    values = [0 if o >= 0 else None for o in owner]
    for lon, lat in points:
        c = grid.cell_at(*proj(lon, lat))
        if c >= 0 and values[c] is not None:
            values[c] += 1
    return {
        "id": "heritage", "group": "heritage", "name": "Heritage", "icon": "l-heritage", "emoji": "🏛️",
        "unit": "protected monuments (BIC)", "format": "int", "scale": "log", "higher_is": "neutral",
        "ramp": ["#2a1a0e", "#5a3418", "#8f5a25", "#c48a3a", "#e8c070", "#fff1c4"], "source": "wikidata_es",
        "description": "Bienes de Interés Cultural (Spain's highest heritage protection: monuments, sites, historic "
        "quarters) in each hex, as Wikidata locates them.",
        "values": values,
    }


def named_counts(names: list[str], cells_of: list[list[int]], owner: list[int]) -> dict:
    """A count lens that also names what it counts: `values` (how many per land hex), `names`, and per hex the indices
    of the names in it (`labels`), which the tooltip lists."""
    labels: list[list[int] | None] = [[] if o >= 0 else None for o in owner]
    for k, cells in enumerate(cells_of):
        for c in cells:
            if c >= 0 and labels[c] is not None:
                labels[c].append(k)
    return {"values": [len(v) if v is not None else None for v in labels], "names": names, "labels": labels}


def shore_cell(grid: HexGrid, owner: list[int], x: float, y: float) -> int:
    """The land hex at x/y, or the nearest one next to it (a harbour museum sits in a sea hex); -1 if none."""
    cell = grid.cell_at(x, y)
    return -1 if cell < 0 else cell if owner[cell] >= 0 else nearest_land(grid, owner, cell, x, y, -1, max_rings=1)


def museums_lens(museums: list[dict], proj, grid: HexGrid, owner: list[int]) -> dict:
    """Museums per land hex, named in the tooltip (the most visited first, where Wikidata records visitors)."""
    return {
        "id": "museums", "group": "heritage", "name": "Museums", "icon": "l-museums", "emoji": "🖼️",
        "unit": "museums", "format": "int", "scale": "log", "higher_is": "neutral",
        "ramp": ["#141a2e", "#23365e", "#36598f", "#5b86b8", "#9cc0dc", "#e8f3fb"], "source": "wikidata_es",
        "description": f"Museums in each hex: the {len(museums):,} museums, galleries, science centres and visitor "
        "centres in Spain that Wikidata locates. Hover a hex for their names.",
        **named_counts([m["label"] for m in museums], [[shore_cell(grid, owner, *proj(*m["coord"]))] for m in museums],
                       owner),
    }


LANGUAGES = [
    {"id": "spanish", "name": "Spanish only", "color": "#c9b99a"},
    {"id": "catalan", "name": "Catalan (co-official)", "color": "#d9534f"},
    {"id": "aranese", "name": "Aranese/Occitan and Catalan (co-official)", "color": "#9b5de5"},
    {"id": "valencian", "name": "Valencian (co-official): Valencian-speaking area", "color": "#f0883e"},
    {"id": "valencia_castilian", "name": "Valencian (co-official): Spanish-speaking area", "color": "#f3c98b"},
    {"id": "galician", "name": "Galician (co-official)", "color": "#4f9fd9"},
    {"id": "basque", "name": "Basque (co-official)", "color": "#2e8b57"},
    {"id": "basque_mixed", "name": "Basque: Navarre's mixed zone", "color": "#9ad0a6"},
    {"id": "asturian", "name": "Asturian (protected, not co-official)", "color": "#e8d44d"},
]
# Province code → the language co-official (or protected) in all of it.
LANGUAGE_OF_PROVINCE = {**dict.fromkeys(("08", "17", "25", "43", "07"), "catalan"),
                        **dict.fromkeys(("15", "27", "32", "36"), "galician"),
                        **dict.fromkeys(("01", "20", "48"), "basque"), "33": "asturian",
                        **dict.fromkeys(("03", "12", "46"), "valencian")}
ARAN = {"25025", "25031", "25045", "25057", "25059", "25063", "25121", "25243", "25247"}  # Val d'Aran (Llei 35/2010)
# Names in Llei 4/1983 art. 36 that are not today's: misprints in the BOE text, a rename (Aras de Alpuente → Aras de
# los Olmos) and Gátova, which moved from Castellón to Valencia in 1995. (province, 1983 name) → today's INE code.
CASTILIAN_ALIASES = {("12", "Bejfs"): "12022", ("12", "Mentanejos"): "12079", ("12", "Gátova"): "46902",
                     ("46", "Aras de Alpuente"): "46041", ("46", "Higeruelas"): "46141", ("46", "Tuéiar"): "46247"}
# Municipalities split off after 1983 from a Spanish-speaking one, which the law therefore does not list.
CASTILIAN_SINCE_1983 = {"03902": "Orihuela", "03903": "Almoradí", "03904": "Albatera"}


def castilian_codes(lists: dict[str, list[str]], municipalities: list[dict]) -> set[str]:
    """INE codes of the Valencian Community's Spanish-speaking municipalities (Llei 4/1983, art. 36)."""
    by_key = {(m["state_fips"], place_key(part)): m["geoid"] for m in municipalities for part in m["name"].split("/")}
    codes = set(CASTILIAN_SINCE_1983)
    for province, names in lists.items():
        for name in names:
            code = CASTILIAN_ALIASES.get((province, name)) or by_key.get((province, place_key(name)))
            if not code:
                raise RuntimeError(f"Llei 4/1983 art. 36: no municipality {name!r} in province {province}")
            codes.add(code)
    return codes


def language_of(lenguas: dict, municipalities: list[dict]) -> dict[str, str]:
    """INE municipality code → LANGUAGES id."""
    castilian = castilian_codes(lenguas["valencia_castilian"], municipalities)
    zones = [(z["zone"], Shape(geojson_rings(z["geometry"]))) for z in lenguas["navarra_zones"]]
    out = {}
    for m in municipalities:
        g = m["geoid"]
        if g[:2] == "31":
            out[g] = next((zone for zone, shape in zones if shape.contains(*m["centre"])), "spanish")
        elif g in ARAN:
            out[g] = "aranese"
        elif g in castilian:
            out[g] = "valencia_castilian"
        else:
            out[g] = LANGUAGE_OF_PROVINCE.get(g[:2], "spanish")
    return out


def languages_lens(lenguas: dict, municipalities: list[dict], world: dict) -> dict:
    language = language_of(lenguas, municipalities)
    index = {c["id"]: k for k, c in enumerate(LANGUAGES)}
    values = [index[language[world["counties"][ci]]] if o >= 0 and ci >= 0 and world["counties"][ci] in language else None
              for o, ci in zip(world["owner"], world["county"])]
    return {
        "id": "languages", "group": "heritage", "name": "Languages", "icon": "l-languages", "emoji": "🗣️",
        "unit": "official languages", "format": "category", "scale": "linear", "higher_is": "neutral",
        "categories": LANGUAGES, "ramp": [c["color"] for c in LANGUAGES], "domain": [0, len(LANGUAGES) - 1],
        "source": "lenguas_es",
        "description": "Where each regional language is official, municipality by municipality, as the laws set it: "
        "co-official in all of Catalonia, the Balearic Islands, Galicia and the Basque Country; Aranese in Val d'Aran; "
        "Navarre's Basque-speaking and mixed zones (Ley Foral 18/1986); in the Valencian Community, the "
        "Spanish-speaking municipalities of Llei 4/1983 (Valencian is co-official there too); Asturian, protected "
        "but not co-official. Aragonese and Catalan in Aragon have no published list of municipalities yet, so "
        "Aragon shows Spanish only. Dialects (Andalusian, Canarian…) are not legal categories and are not mapped.",
        "values": values,
    }


# ADEAC's municipality names that are not INE's: (province, ADEAC name) → INE codes (the first holds a shared beach).
BEACH_TOWNS = {("03", "Vila Joiosa"): ["03139"], ("07", "Palma de Mallorca"): ["07040"],
               ("08", "Pineda del Mar"): ["08163"], ("15", "Riveira"): ["15073"],
               ("33", "Castropol- Tapia de Casariego"): ["33017", "33070"], ("35", "Villa de Agüimes"): ["35002"],
               ("38", "Pinar del Hierro"): ["38901"], ("51", "Ciudad Autónoma de Ceuta"): ["51001"],
               ("52", "Ciudad Autónoma de Melilla"): ["52001"]}


BEACH_REACH_KM = 15


def beach_town(beach: dict, by_key: dict) -> str:
    """The INE code of the municipality a Blue Flag beach belongs to (the first, for one shared by two)."""
    key = (beach["province"], beach["municipality"])
    if key in BEACH_TOWNS:
        return BEACH_TOWNS[key][0]
    first = beach["municipality"].split("/")[0]
    code = by_key.get((beach["province"], place_key(first)))
    if not code:
        raise RuntimeError(f"Blue Flag: no municipality {beach['municipality']!r} in province {beach['province']}")
    return code


def beaches_lens(beaches: list[dict], municipalities: list[dict], world: dict, grid: HexGrid, proj) -> dict:
    """Blue Flag beaches per hex. ADEAC gives each beach's municipality, not its position: a municipality's beaches
    take its coastal hexes in turn, nearest its centre first. A municipality too small to own a hex uses the coastal
    hexes within BEACH_REACH_KM of its centre; a lake or river beach (no coast near) its nearest land hex."""
    owner, county, geoids = world["owner"], world["county"], world["counties"]
    by_key = {(m["state_fips"], place_key(part)): m["geoid"] for m in municipalities for part in m["name"].split("/")}
    centre = {m["geoid"]: m["centre"] for m in municipalities}
    hexes: dict[str, list[int]] = {}
    for c, (o, ci) in enumerate(zip(owner, county)):
        if o >= 0 and ci >= 0:
            hexes.setdefault(geoids[ci], []).append(c)
    coastal = {c for c, o in enumerate(owner) if o >= 0 and any(owner[n] == -1 for n in grid.neighbours(c))}
    used: dict[str, int] = {}
    cells_of = []
    for b in beaches:
        town = beach_town(b, by_key)
        x, y = proj(*centre[town])
        dist = lambda c: math.dist(grid.center(*grid.col_row(c)), (x, y))
        own = hexes.get(town, [])
        options = ([c for c in own if c in coastal] or [c for c in coastal if dist(c) <= BEACH_REACH_KM] or own
                   or [nearest_land(grid, owner, max(grid.cell_at(x, y), 0), x, y, -1)])
        options.sort(key=dist)
        cells_of.append([options[used.get(town, 0) % len(options)]])
        used[town] = used.get(town, 0) + 1
    return {
        "id": "beaches", "group": "heritage", "name": "Blue Flag beaches", "icon": "l-beaches", "emoji": "🏖️",
        "unit": "Blue Flag beaches", "format": "int", "scale": "linear", "higher_is": "good", "domain": [0, 6],
        "ramp": ["#0d2b45", "#134f74", "#1a77a3", "#2ea3c9", "#7fd1e3", "#e6f8fb"], "source": "bandera_azul",
        "description": f"The {len(beaches)} beaches flying the Blue Flag in 2026-27, named in the tooltip. ADEAC lists "
        "each beach's municipality, not its position, so a municipality's beaches are spread over its coastal hexes.",
        **named_counts([f"{b['beach']} ({b['municipality']})" for b in beaches], cells_of, owner),
    }


PEOPLE_REACH_KM = 175  # further than this from every people's point a hex is left blank: the Balearic and Canary Islands
# Eight colours, assigned so that neighbouring territories never share one.
PEOPLE_COLOURS = ["#c8553d", "#f2a541", "#7fb069", "#3d8fbf", "#9b5de5", "#e86a92", "#43aa8b", "#d4c26a"]


def peoples_lens(peoples: list[dict], proj, grid: HexGrid, owner: list[int]) -> dict:
    """Each land hex in the territory of the nearest ancient people (Pleiades points), up to PEOPLE_REACH_KM away.
    The territories are nearest-point regions drawn by this map, not the historical boundaries, which no source maps."""
    points = [proj(p["lon"], p["lat"]) for p in peoples]
    nearest: list[int | None] = []
    for c, o in enumerate(owner):
        k = None
        if o >= 0:
            x, y = grid.center(*grid.col_row(c))
            d, k = min((math.hypot(px - x, py - y), j) for j, (px, py) in enumerate(points))
            k = k if d <= PEOPLE_REACH_KM else None
        nearest.append(k)
    used = sorted({k for k in nearest if k is not None}, key=lambda k: peoples[k]["name"])
    index = {k: i for i, k in enumerate(used)}
    touching: dict[int, set[int]] = {i: set() for i in range(len(used))}
    for c, k in enumerate(nearest):
        if k is not None:
            for n in grid.neighbours(c):
                if nearest[n] is not None and nearest[n] != k:
                    touching[index[k]].add(index[nearest[n]])
    colour: dict[int, int] = {}
    for i in sorted(touching, key=lambda i: -len(touching[i])):  # greedy, most-connected first
        taken = {colour[j] for j in touching[i] if j in colour}
        colour[i] = next(c for c in range(len(PEOPLE_COLOURS)) if c not in taken)
    categories = [{"id": peoples[k]["id"], "name": peoples[k]["name"], "color": PEOPLE_COLOURS[colour[i]]}
                  for i, k in enumerate(used)]
    return {
        "id": "peoples", "group": "heritage", "name": "Ancient peoples", "icon": "l-peoples", "emoji": "🛡️",
        "unit": "people of ancient Iberia", "format": "category", "scale": "linear", "higher_is": "neutral",
        "categories": categories, "ramp": [c["color"] for c in categories], "domain": [0, max(len(categories) - 1, 1)],
        "source": "pleiades_iberia",
        "description": f"The ancient people whose Pleiades location is nearest to each hex (within {PEOPLE_REACH_KM} km): "
        "Vaccaei, Vascones, Cantabri, Ilergetes… and, in the south and east, the regions named after their peoples "
        "(Turdetania, Bastetania, Contestania). The borders are nearest-point territories drawn by this map: Pleiades "
        "gives each people a point, not a boundary.",
        "values": [index[k] if k is not None else None for k in nearest],
    }


def food_lens(names: list[dict], proj, grid: HexGrid, owner: list[int]) -> dict:
    """Protected food and drink names (DOP, IGP, wine denominations) whose area holds each land hex's centre. A name
    whose area holds no hex centre (a small vino de pago) goes to the land hex nearest its area's centre."""
    centres = {c: grid.center(*grid.col_row(c)) for c in range(grid.size) if owner[c] >= 0}
    cells_of = []
    for n in names:
        shape = Shape([[proj(lon, lat) for lon, lat in ring] for ring in n["rings"] if len(ring) >= 3])
        x0, y0, x1, y1 = shape.bbox
        cells = [c for c, (x, y) in centres.items() if x0 <= x <= x1 and y0 <= y <= y1 and shape.contains(x, y)]
        if not cells:
            x, y = proj(*ring_centroid(max(n["rings"], key=lambda r: abs(ring_area(r)))))
            cells = [nearest_land(grid, owner, max(grid.cell_at(x, y), 0), x, y, -1)]
        cells_of.append(cells)
    return {
        "id": "food", "group": "food", "name": "Food & drink", "icon": "l-food", "emoji": "🍷",
        "unit": "protected names (DOP, IGP, wine)", "format": "int", "scale": "linear", "higher_is": "neutral",
        "ramp": ["#2b1320", "#5c1f3a", "#8e3049", "#c25a4a", "#e89a5a", "#ffe0a0"], "source": "calidad_diferenciada",
        "description": f"How many of Spain's {len(names)} mapped protected food and drink names (DOP, IGP, vinos de "
        "pago and quality wines: Rioja, Jamón de Teruel, Queso Manchego…) include each hex in their area, as the "
        "Ministry of Agriculture maps them. Hover a hex for the names.",
        **named_counts([n["name"] for n in names], cells_of, owner),
    }


def build() -> None:
    world = load_interim("_world")
    lau = load_interim("siane")
    padron_p = load_interim_payload("ine_padron")
    padron = padron_p["data"]
    pib_p = load_interim_payload("ine_pib")
    pib = pib_p["data"]
    ss = load_interim("ine_censo_ocupados")
    proj = active().world_projection(world)
    grid = HexGrid(**world["grid"])
    owner = world["owner"]
    year, gdp_year = padron["year"], pib["year"]
    years = [BASELINE_YEAR, year] if str(BASELINE_YEAR) in padron["nation"] else []

    state_index = {fips: i for i, fips in enumerate(world["states"])}
    centre = {m["geoid"]: m["centre"] for m in lau["municipalities"]}
    regions = {p["fips"]: p for p in lau["provinces"]}
    muni = padron["municipalities"]

    # --- cities: the large urban areas (AUDES), like the US metro areas ------------------------------------------
    areas = urban_areas(load_interim("audes")["areas"], muni, centre)
    feet = footprints(world, {a["id"]: a["members"] for a in areas})
    taken: set[int] = set()
    cities = []
    for a in sorted(areas, key=lambda a: -sum(muni[c]["pop"].get(str(year)) or 0 for c in a["members"])):
        code, members = a["id"], a["members"]
        prov = code[:2]
        lon, lat = centre[code]
        x, y = proj(lon, lat)
        s = state_index.get(prov, -1)
        cell = nearest_land(grid, owner, max(grid.cell_at(x, y), 0), x, y, s)
        free = free_cell(grid, owner, taken, cell, x, y, s) if cell >= 0 else None
        cell = free if free is not None else cell
        taken.add(cell)
        series = add_series([muni[c]["pop"] for c in members])
        provs = sorted({c[:2] for c in members}, key=lambda p: (p != prov, p))
        cities.append({
            "id": code, "name": muni[code]["display"], "full": a["full"],
            "states": [regions[p]["abbr"] for p in provs], "metro": True, "capital": code == active().capital_city,
            "x": round(x, 1), "y": round(y, 1), "cell": cell,
            **econ(series.get(str(year)), None, None, add_sections([ss["municipalities"].get(c) for c in members])),
            "growth": growth_of(series, years), "growth_years": years or None,
            "counties": sorted(members),
            "footprint": sorted(feet.get(code, set()) | {cell}),
            "pop_series": {k: v for k, v in series.items() if int(k) >= SERIES_FROM},
        })
    add_ranks(cities)

    # --- provinces ---------------------------------------------------------------------------------------------
    states = []
    for i, fips in enumerate(world["states"]):
        p, pp = regions[fips], padron["provinces"].get(fips, {})
        series = pp.get("pop", {})
        states.append({
            "fips": fips, "abbr": p["abbr"], "name": p["name"],
            **econ(series.get(str(year)), pib["provinces"].get(fips), gdp_year, ss["provinces"].get(fips)),
            "growth": growth_of(series, years), "growth_years": years or None,
            "ranks": {}, "label": label_anchor(grid, owner, i, p["name"]), "land": land_shares(world, i), "energy": None,
        })
    for y in YIELDS:
        key = y["key"]
        ranked = sorted((s for s in states if s["yields"][key] is not None), key=lambda s: -s["yields"][key])
        for r, s in enumerate(ranked, 1):
            s["ranks"][key] = r
        for s in states:
            s["ranks"].setdefault(key, None)

    # --- nation ------------------------------------------------------------------------------------------------
    nat_series = padron["nation"]
    nation = {
        "vintage": padron_p["vintage"], "year": year, "gdp_vintage": pib_p["vintage"],
        "nation": {**econ(nat_series.get(str(year)), pib["nation"], gdp_year, ss["nation"]), "growth": growth_of(nat_series, years),
                   "growth_years": years or None},
        "yields": yields_es(ss["year"]),
        "industries": INDUSTRIES,
    }

    # --- lenses ------------------------------------------------------------------------------------------------
    wikidata = load_interim("wikidata_es")
    pops = [muni.get(g, {}).get("pop", {}).get(str(year)) for g in world["counties"]]
    _, weights, density = spread_population(
        world, proj, pops, lambda k: (*centre[world["counties"][k]], muni.get(world["counties"][k], {}).get("display", ""))
        if world["counties"][k] in centre else None
    )
    lenses = [{
        "id": "density", "group": "people", "name": "Population", "icon": "l-people", "emoji": "👥",
        "unit": "people / km²", "format": "int", "scale": "log",
        "ramp": ["#1b1035", "#4b2377", "#9a3b8a", "#e0645e", "#f9b24a", "#fff3a8"], "higher_is": "neutral",
        "source": "ine_padron",
        "description": f"Residents per km² of land. Each municipality's population (INE Padrón, {year}) is spread over "
        "its hexes in proportion to how much of the municipality each hex covers.",
        "values": density,
    }, income_lens(load_interim_payload("ine_adrh"), world["counties"], weights),
        heritage_lens(wikidata["bic"], proj, grid, owner), museums_lens(wikidata["museums"], proj, grid, owner),
        food_lens(load_interim("calidad_diferenciada")["names"], proj, grid, owner),
        peoples_lens(load_interim("pleiades_iberia")["peoples"], proj, grid, owner),
        languages_lens(load_interim("lenguas_es"), lau["municipalities"], world),
        beaches_lens(load_interim("bandera_azul")["beaches"], lau["municipalities"], world, grid, proj)] + land_lenses(world, "corine")
    set_domains(lenses)
    groups = [g for g in GROUPS + ES_GROUPS if any(l["group"] == g["id"] for l in lenses)]

    write_web("cities.json", cities)
    write_web("nation.json", nation)
    write_web("states.json", states)
    write_web("lenses.json", {"vintage": padron_p["vintage"], "groups": groups, "lenses": lenses})
    print(f"    {len(cities)} cities (AUDES large urban areas), {len(states)} provinces; GDP {gdp_year}, Padrón {year}")
