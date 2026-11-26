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

from ..core.hexgrid import HexGrid
from ..core.store import load_interim, load_interim_payload, write_web
from ..countries import active
from .cities import add_ranks, footprints, free_cell, nearest_land
from .growth import BASELINE_YEAR, rate
from .lenses import COUNTY_LENSES, DOMAIN_NOTE, GROUPS, land_lenses, percentile_domain, spread_population
from .states import label_anchor, land_shares
from .yields import YIELDS

REQUIRES = ["_world", "siane", "audes", "ine_padron", "ine_pib", "ine_adrh", "ine_censo_ocupados"]
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
    }, income_lens(load_interim_payload("ine_adrh"), world["counties"], weights)] + land_lenses(world, "corine")
    for lens in lenses:
        lens["domain"] = percentile_domain(lens["values"], lens["scale"] == "log")
        lens["description"] += DOMAIN_NOTE
    groups = [g for g in GROUPS if any(l["group"] == g["id"] for l in lenses)]

    write_web("cities.json", cities)
    write_web("nation.json", nation)
    write_web("states.json", states)
    write_web("lenses.json", {"vintage": padron_p["vintage"], "groups": groups, "lenses": lenses})
    print(f"    {len(cities)} cities (AUDES large urban areas), {len(states)} provinces; GDP {gdp_year}, Padrón {year}")
