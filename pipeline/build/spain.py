"""Spain's cities, provinces, nation and lenses, on the shared helpers of the US builders.

First cut (see docs/SPAIN.md):

* **Cities** are the large urban areas (AUDES: over 50,000 residents), named after and placed at their core
  municipality's capital (SIANE), on the nearest free land hex of its province. Population, Padrón series, jobs and
  footprint add up the member municipalities (the US metro rule, cities.footprints). Employment leaves out the members
  of under 500 residents, which INE does not publish by section (three areas, a few thousand residents).
* **Gold** is GDP at market prices (INE Contabilidad Regional), which INE publishes down to provinces: provinces and
  the nation have it; cities don't (there is no official municipal GDP, and none is made up here: household income or
  IRPF bases measure what residents earn, not what is produced there, so they are not used as a stand-in).
* **Food, Production, Culture** count employed residents by CNAE section (INE Annual Population Census: cities,
  provinces, Spain), mapped to the US industry keys so the US yield definitions apply unchanged.
* **Science** is R&D personnel in full-time equivalents (INE R&D statistic, all sectors), counted where the R&D is
  done, where the US map counts Science workers (professional + information, ACS). INE publishes it by autonomous
  community only, so below that a community's R&D personnel is shared among its provinces and municipalities in
  proportion to their residents employed in the US Science industries (CNAE J + M, the same census): every place
  gets its Science workers times its community's R&D personnel per Science worker. Provinces add up to their
  community; cities add up their members, each at its own community's rate (an area can straddle two); Spain is
  INE's national total. A community without a published figure (Ceuta and Melilla, statistical secrecy) leaves its
  provinces and cities null. Science keeps no industry list, so the yield report shows no census breakdown that
  would not add up to it.
* **Living standards** (the US contract's fields, see living()): `unemployment` = unemployed ÷ (employed + unemployed)
  of the Annual Population Census; `median_income` = ADRH *mean* net income per household (INE publishes no median);
  `median_rent` = SERPAVI median monthly rent; `rent_burden` = rent × 12 ÷ income, the US formula. `home_value` stays
  null: no official source gives a value per dwelling by municipality (the ministry's appraisals are in €/m²).
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

from ..core.geo import Shape, geojson_rings
from ..core.hexgrid import HexGrid
from ..core.lang import Text, tr
from ..core.store import load_interim, load_interim_payload, write_web
from ..countries import active
from ..sources.es.names import title_es
from ..sources.es.provinces import COMMUNITIES, COMMUNITY_OF, community_name
from .cities import add_ranks, footprints, free_cell, nearest_land
from .growth import BASELINE_YEAR, rate
from .lenses import COUNTY_LENSES, GROUPS, land_lenses, set_domains, spread_population
from . import spain_crime, spain_daily
from .spain_people import REQUIRES as PEOPLE_REQUIRES, people_lenses
from .spain_fiesta import FIESTA_FILE, FIESTA_REQUIRES, fiesta_lenses
from . import spain_beaches, spain_fauna, spain_personajes
from .spain_food import food_lens
from .spain_named import named_counts, shore_cell
from .spain_wonders import place_key
from .states import label_anchor, land_shares
from .texts_es import DOMAIN_NOTE, LAND_LENSES, LAND_UNIT, LENS_GROUPS, YIELD_LABELS, vintage
from .world import localized
from .yields import YIELDS

REQUIRES = ["_world", "siane", "audes", "ine_padron", "ine_pib", "ine_adrh", "ine_censo_ocupados", "ine_censo_actividad",
            "ine_imasd", "serpavi", "wikidata_es", "calidad_diferenciada", "pleiades_iberia", "lenguas_es",
            "gastronomia_es"] + spain_beaches.REQUIRES + spain_daily.SOURCES + spain_crime.SOURCES + spain_fauna.SOURCES + PEOPLE_REQUIRES + FIESTA_REQUIRES + spain_personajes.REQUIRES
PRODUCES = ["cities.json", "nation.json", "states.json", "lenses.json", f"{spain_personajes.FILE}.json",
            f"{FIESTA_FILE}.json"]
COUNTRIES = ("es",)

SERIES_FROM = 2020  # pop_series spans the same years as the US map's (the full Padrón series is in the interim)

WORKERS = tr("Residentes ocupados, contados donde viven (Censo anual de población del INE, 1 de enero de {year})",
             "Employed residents, counted where they live (INE Annual Population Census, 1 January {year})")
YIELD_TEXT = {
    "food": WORKERS + tr(": agricultura, ganadería, silvicultura y pesca (sección A de la CNAE).",
                         ": agriculture, livestock, forestry and fishing (CNAE section A)."),
    "production": WORKERS + tr(
        ": industrias extractivas (B), industria manufacturera (C) y construcción (F), los tres sectores del mapa de "
        "EE. UU.",
        ": mining and quarrying (B), manufacturing (C) and construction (F), the three sectors of the US map."),
    "gold": tr(
        "Producto interior bruto a precios de mercado, en euros corrientes (Contabilidad Regional de España del INE). "
        "El INE lo publica hasta el nivel provincial, así que las ciudades no tienen oro propio.",
        "Gross domestic product at market prices, in current euros (INE Regional Accounts of Spain). INE publishes it "
        "down to provinces, so cities have no gold of their own."),
    "science": tr(
        "Personal en I+D en equivalencia a jornada completa, contado donde se hace la I+D (Estadística sobre "
        "actividades de I+D del INE, {rd_year}: empresas, administración pública, enseñanza superior e instituciones "
        "sin fines de lucro). El INE lo publica por comunidad autónoma; cada provincia y cada ciudad recibe la parte de "
        "su comunidad que le corresponde por sus residentes ocupados en información y comunicaciones (J) y actividades "
        "profesionales, científicas y técnicas (M) según el Censo anual de población ({year}). España es el total "
        "nacional del INE; Ceuta y Melilla no tienen dato (secreto estadístico).",
        "R&D personnel in full-time equivalents, counted where the R&D is done (INE R&D statistic, {rd_year}: "
        "businesses, government, higher education and non-profit institutions). INE publishes it by autonomous "
        "community; each province and each city gets the part of its community's that its residents employed in "
        "information and communication (J) and professional, scientific and technical activities (M) earn it, by the "
        "Annual Population Census ({year}). Spain is INE's national total; Ceuta and Melilla have no figure "
        "(statistical confidentiality)."),
    "culture": WORKERS + tr(": actividades artísticas, recreativas y de entretenimiento (R).",
                            ": arts, entertainment and recreation (R)."),
}
# CNAE-2009 section → the industry key the map uses (yields.INDUSTRY_LINES), with the section's own label (in English,
# the NACE Rev. 2 section titles CNAE-2009 translates).
CNAE = {
    "A": ("agriculture", tr("Agricultura, ganadería, silvicultura y pesca", "Agriculture, forestry and fishing")),
    "B": ("mining", tr("Industrias extractivas", "Mining and quarrying")),
    "C": ("manufacturing", tr("Industria manufacturera", "Manufacturing")),
    "D": ("utilities", tr("Energía, agua y residuos", "Energy, water and waste")), "E": ("utilities", None),
    "F": ("construction", tr("Construcción", "Construction")),
    "G": ("retail", tr("Comercio y reparación de vehículos", "Wholesale and retail trade; repair of motor vehicles")),
    "H": ("transportation", tr("Transporte y almacenamiento", "Transportation and storage")),
    "I": ("accommodation", tr("Hostelería", "Accommodation and food service")),
    "J": ("information", tr("Información y comunicaciones", "Information and communication")),
    "K": ("finance", tr("Actividades financieras y de seguros", "Financial and insurance activities")),
    "L": ("real_estate", tr("Actividades inmobiliarias", "Real estate activities")),
    "M": ("professional", tr("Actividades profesionales, científicas y técnicas",
                             "Professional, scientific and technical activities")),
    "N": ("admin", tr("Actividades administrativas y servicios auxiliares",
                      "Administrative and support service activities")),
    "O": ("public_admin", tr("Administración pública y defensa", "Public administration and defence")),
    "P": ("education", tr("Educación", "Education")),
    "Q": ("health", tr("Sanidad y servicios sociales", "Human health and social work")),
    "R": ("arts", tr("Actividades artísticas, recreativas y de entretenimiento", "Arts, entertainment and recreation")),
    "S": ("other", tr("Otros servicios, hogares como empleadores y organismos extraterritoriales",
                      "Other services, households as employers and extraterritorial bodies")),
    "T": ("other", None), "U": ("other", None),
}
INDUSTRIES = {key: label for key, label in CNAE.values() if label}
ECON_NULL = {"median_income": None, "median_rent": None, "home_value": None, "unemployment": None, "rent_burden": None}


SCIENCE_INDUSTRIES = next(y["industries"] for y in YIELDS if y["key"] == "science")  # the apportioning key (J + M)


def yields_es(year: int | None = None, rd: dict | None = None) -> list[dict]:
    """The US yield definitions (keys, icons, colours, industries) with Spain's names and sources; Gold is in euros.
    Science is R&D personnel (`rd` = the ine_imasd payload): no industry list, and its own vintage."""
    rd = rd or {}
    out = []
    for y in YIELDS:
        e = {**y, "label": YIELD_LABELS[y["key"]], "unit": "eur" if y["key"] == "gold" else y["unit"],
             "description": YIELD_TEXT[y["key"]].format(year=str(year), rd_year=str((rd.get("data") or {}).get("year")))}
        if y["key"] == "science":
            e |= {"industries": [], "vintage": vintage(rd.get("vintage"))}
        out.append(e)
    return out


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


def rd_rates(rd: dict, provinces: dict[str, dict | None]) -> dict[str, float | None]:
    """Community → its R&D personnel (FTE) per resident employed in the Science industries (census, all its provinces);
    None where INE gives no R&D figure or a province's Science workers are unknown."""
    out = {}
    for comm, (_, provs) in COMMUNITIES.items():
        fte = (rd["communities"].get(comm) or {}).get("personnel_fte")
        workers = [total(jobs_of(provinces.get(p)), SCIENCE_INDUSTRIES) for p in provs]
        out[comm] = None if fte is None or None in workers or not sum(workers) else fte / sum(workers)
    return out


def rd_science(rows: dict[str, dict | None], rates: dict[str, float | None]) -> int | None:
    """Science (R&D personnel) of a place made of `rows` {INE code (province or municipality): census sections}: each
    row's Science workers at its community's rate, summed. Rows INE does not publish (None) are left out, like the
    rest of the area's employment; a row in a community without a rate, or with its Science workers unknown, makes the
    whole place unknown."""
    parts = []
    for code, sections in rows.items():
        if not sections:
            continue
        workers, rate_ = total(jobs_of(sections), SCIENCE_INDUSTRIES), rates.get(COMMUNITY_OF[code[:2]])
        if workers is None or rate_ is None:
            return None
        parts.append(workers * rate_)
    return round(sum(parts)) if parts else None


def unemployment_rate(rows: list[dict | None]) -> float | None:
    """Unemployed ÷ (employed + unemployed) over the places with Census figures (INE leaves out municipalities of
    under ~75 residents): the area's own rate, each member weighted by its labour force."""
    known = [r for r in rows if r]
    labour = sum(r["employed"] + r["unemployed"] for r in known)
    return round(sum(r["unemployed"] for r in known) / labour, 4) if labour else None


def household_income(rows: list[tuple[int | None, float | None, float | None]]) -> int | None:
    """Mean net income per household of a group of municipalities from ADRH's per-person and per-household means:
    rows of (population, per person, per household). A municipality's households are population × per person ÷ per
    household, so the result is total income ÷ total households, the members' means weighted by their households.
    Municipalities INE leaves out (confidentiality) are skipped."""
    known = [(p, pp, ph) for p, pp, ph in rows if p and pp and ph]
    households = sum(p * pp / ph for p, pp, ph in known)
    return round(sum(p * pp for p, pp, _ in known) / households) if households else None


def monthly_rent(groups: list[list[list[float]] | None]) -> int | None:
    """SERPAVI median monthly rents (flats and houses of each place, [[rented dwellings, median], …]) combined into one
    figure: their mean weighted by rented dwellings. A median of each part, so for a group it approximates the median."""
    pairs = [pair for g in groups if g for pair in g]
    leases = sum(n for n, _ in pairs)
    return round(sum(n * m for n, m in pairs) / leases) if leases else None


def living(unemployment: list[dict | None], income: list[tuple], rents: list[list[list[float]] | None]) -> dict:
    """The US contract's living-standard fields (yields.economy) from Spain's sources; home_value has none."""
    inc, rent = household_income(income), monthly_rent(rents)
    return {"median_income": inc, "median_rent": rent, "home_value": None, "unemployment": unemployment_rate(unemployment),
            "rent_burden": round(rent * 12 / inc, 4) if rent and inc else None}


def econ(population: int | None, gdp: float | None, gdp_year: int | None, workers: dict[str, int] | None = None,
         science: float | None = None, living_fields: dict | None = None) -> dict:
    """The economy block of a place; `science` is its R&D personnel (rd_science), not a census count, and
    `living_fields` its living standards (living())."""
    jobs = jobs_of(workers)
    special = {"gold": gdp, "science": science}
    return {
        "population": population, "employed": workers.get("total") if workers else None, "jobs": jobs or {},
        **(living_fields or ECON_NULL),
        "yields": {y["key"]: special[y["key"]] if y["key"] in special else total(jobs, y["industries"]) for y in YIELDS},
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


# AUDES labels it misprints: AUDES 2025 → the label its own member municipalities give (Santa Cruz de Tenerife and San
# Cristóbal de La Laguna).
AUDES_MISPRINTS = {"SALTA CRUZ DE TENERIFE - LA LAGUNA": "SANTA CRUZ DE TENERIFE - LA LAGUNA"}


def area_name(label: str) -> Text:
    """An AUDES label ('ÁREA URBANA DE TARRAGONA-REUS') as the map names the area: the place written as names are
    (names.title_es: 'Tarragona-Reus', 'Alcoy/Alcoi', 'Santander - Torrelavega'), after 'Área urbana de' in Spanish and
    before 'urban area' in English ('Área urbana de la Bahía de Cádiz', 'La Bahía de Cádiz urban area')."""
    m = re.match(r"ÁREA URBANA\s*(?:(DEL?)\s+)?(.+)$", label, flags=re.I)  # AUDES writes "ÁREA URBANADE SEGOVIA"
    prep, place = m.group(1), title_es(AUDES_MISPRINTS.get(m.group(2), m.group(2)))
    es = re.sub(r"^(La|Las|Los|El) ", lambda x: x.group(1).lower() + " ", place) if prep else place
    return tr(f"Área urbana {prep.lower() + ' ' if prep else ''}{es}", f"{place} urban area")


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
        out.append({"id": members[0], "full": area_name(a["label"]), "members": members})
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
        "id": "income", **{k: meta[k] for k in ("group", "icon", "emoji", "scale", "higher_is", "ramp")},
        "name": tr("Renta", "Income"), "unit": tr("renta neta por persona, €", "net income per person, €"),
        "format": "eur", "source": "ine_adrh",
        "description": tr(
            "Renta neta media por persona de los municipios de cada hexágono, ponderada por población (Atlas de "
            "Distribución de Renta de los Hogares del INE, {year}: registros tributarios cruzados con el Padrón). Es una "
            "media por persona, no la mediana por hogar del mapa de EE. UU.",
            "Mean net income per person of each hex's municipalities, weighted by population (INE Household Income "
            "Distribution Atlas, {year}: tax records matched to the Padrón). It is a mean per person, not the US map's "
            "median per household.").format(year=str(adrh["year"])),
        "values": values,
    }


ES_GROUPS = [{"id": "fauna", "name": tr("Fauna", "Wildlife")},
             {"id": "heritage", "name": tr("Patrimonio", "Heritage")},
             {"id": "great_people", "name": tr("Grandes personajes", "Great people")},
             {"id": "food", "name": tr("Comida, bebida y fiestas", "Food, drink and fiestas")}]


def heritage_lens(points: list, proj, grid: HexGrid, owner: list[int]) -> dict:
    """Bienes de Interés Cultural per land hex (a count, 0 included: the lens shows where heritage is dense)."""
    values = [0 if o >= 0 else None for o in owner]
    for lon, lat in points:
        c = grid.cell_at(*proj(lon, lat))
        if c >= 0 and values[c] is not None:
            values[c] += 1
    return {
        "id": "heritage", "group": "heritage", "name": tr("Patrimonio", "Heritage"), "icon": "l-heritage",
        "emoji": "🏛️", "unit": tr("monumentos protegidos (BIC)", "protected monuments (BIC)"), "format": "int",
        "scale": "log", "higher_is": "neutral",
        "ramp": ["#2a1a0e", "#5a3418", "#8f5a25", "#c48a3a", "#e8c070", "#fff1c4"], "source": "wikidata_es",
        "description": tr(
            "Bienes de Interés Cultural (la máxima protección del patrimonio en España: monumentos, sitios, conjuntos "
            "históricos) de cada hexágono, según los sitúa Wikidata.",
            "Bienes de Interés Cultural (Spain's highest heritage protection: monuments, sites, historic ensembles) in "
            "each hex, as Wikidata places them."),
        "values": values,
    }


def museums_lens(museums: list[dict], proj, grid: HexGrid, owner: list[int]) -> dict:
    """Museums per land hex, named in the tooltip (the most visited first, where Wikidata records visitors)."""
    return {
        "id": "museums", "group": "heritage", "name": tr("Museos", "Museums"), "icon": "l-museums", "emoji": "🖼️",
        "unit": tr("museos", "museums"), "format": "int", "scale": "log", "higher_is": "neutral",
        "ramp": ["#141a2e", "#23365e", "#36598f", "#5b86b8", "#9cc0dc", "#e8f3fb"], "source": "wikidata_es",
        "description": tr(
            "Museos de cada hexágono: los {n} museos, galerías, museos de ciencia y centros de interpretación de España "
            "que Wikidata sitúa. Pasa el ratón por un hexágono para ver sus nombres.",
            "Museums in each hex: the {n} museums, galleries, science museums and interpretation centres of Spain that "
            "Wikidata places. Hover a hex to see their names.").format(n=len(museums)),
        **named_counts([m["label"] for m in museums], [[shore_cell(grid, owner, *proj(*m["coord"]))] for m in museums],
                       owner),
    }


LANGUAGES = [
    {"id": "spanish", "name": tr("Solo castellano", "Spanish only"), "color": "#c9b99a"},
    {"id": "catalan", "name": tr("Catalán (cooficial)", "Catalan (co-official)"), "color": "#d9534f"},
    {"id": "aranese", "name": tr("Aranés/occitano y catalán (cooficiales)", "Aranese/Occitan and Catalan (co-official)"),
     "color": "#9b5de5"},
    {"id": "valencian", "name": tr("Valenciano (cooficial): zona valencianohablante",
                                   "Valencian (co-official): Valencian-speaking area"), "color": "#f0883e"},
    {"id": "valencia_castilian", "name": tr("Valenciano (cooficial): zona castellanohablante",
                                            "Valencian (co-official): Spanish-speaking area"), "color": "#f3c98b"},
    {"id": "galician", "name": tr("Gallego (cooficial)", "Galician (co-official)"), "color": "#4f9fd9"},
    {"id": "basque", "name": tr("Euskera (cooficial)", "Basque (co-official)"), "color": "#2e8b57"},
    {"id": "basque_mixed", "name": tr("Euskera: zona mixta de Navarra", "Basque: mixed area of Navarre"),
     "color": "#9ad0a6"},
    {"id": "asturian", "name": tr("Asturiano (protegido, no cooficial)", "Asturian (protected, not co-official)"),
     "color": "#e8d44d"},
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
        "id": "languages", "group": "heritage", "name": tr("Lenguas", "Languages"), "icon": "l-languages",
        "emoji": "🗣️", "unit": tr("lenguas oficiales", "official languages"), "format": "category", "scale": "linear", "higher_is": "neutral",
        "categories": LANGUAGES, "ramp": [c["color"] for c in LANGUAGES], "domain": [0, len(LANGUAGES) - 1],
        "source": "lenguas_es",
        "description": tr(
            "Dónde es oficial cada lengua, municipio a municipio, según las leyes: cooficial en toda Cataluña, Baleares, "
            "Galicia y el País Vasco; el aranés en el Valle de Arán; las zonas vascófona y mixta de Navarra (Ley Foral "
            "18/1986); en la Comunitat Valenciana, los municipios castellanohablantes de la Llei 4/1983 (donde el "
            "valenciano también es cooficial); el asturiano, protegido pero no cooficial. El aragonés y el catalán de "
            "Aragón aún no tienen una lista publicada de municipios, así que Aragón sale solo en castellano. Los "
            "dialectos (andaluz, canario…) no son categorías legales y no se cartografían.",
            "Where each language is official, municipality by municipality, according to the law: co-official in all "
            "of Catalonia, the Balearic Islands, Galicia and the Basque Country; Aranese in the Val d'Aran; the "
            "Basque-speaking and mixed areas of Navarre (Ley Foral 18/1986); in the Valencian Community, the "
            "Spanish-speaking municipalities of Llei 4/1983 (where Valencian is co-official too); Asturian, protected "
            "but not co-official. Aragonese and the Catalan of Aragon have no published list of municipalities yet, "
            "so Aragon shows Spanish only. Dialects (Andalusian, Canarian…) are not legal categories and are not "
            "mapped."),
        "values": values,
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
        "id": "peoples", "group": "heritage", "name": tr("Pueblos prerromanos", "Pre-Roman peoples"),
        "icon": "l-peoples", "emoji": "🛡️", "unit": tr("pueblo de la Iberia antigua", "people of ancient Iberia"),
        "format": "category", "scale": "linear", "higher_is": "neutral",
        "categories": categories, "ramp": [c["color"] for c in categories], "domain": [0, max(len(categories) - 1, 1)],
        "source": "pleiades_iberia",
        "description": tr(
            "El pueblo antiguo cuya ubicación en Pleiades está más cerca de cada hexágono (hasta {km} km): vacceos, "
            "vascones, cántabros, ilergetes… y, en el sur y el este, las regiones que llevan el nombre de sus pueblos "
            "(Turdetania, Bastetania, Contestania). Las fronteras son territorios del punto más cercano que dibuja este "
            "mapa: Pleiades da a cada pueblo un punto, no un límite. Los nombres van en latín o griego, como en "
            "Pleiades.",
            "The ancient people whose location in Pleiades is nearest each hex (up to {km} km): Vaccaei, Vascones, "
            "Cantabri, Ilergetes… and, in the south and east, the regions named after their peoples (Turdetania, "
            "Bastetania, Contestania). The borders are nearest-point territories drawn by this map: Pleiades gives each "
            "people a point, not a boundary. The names are in Latin or Greek, as in Pleiades.").format(km=PEOPLE_REACH_KM),
        "values": [index[k] if k is not None else None for k in nearest],
    }


def dishes_lens(dishes: list[dict], world: dict) -> dict:
    """Regional dishes and foods per province (Spanish Wikipedia's provincial cuisine categories, filtered to foods
    with Wikidata): every land hex lists its province's."""
    by_province: dict[str, list[int]] = {}
    for c, o in enumerate(world["owner"]):
        if o >= 0:
            by_province.setdefault(world["states"][o], []).append(c)
    return {
        "id": "dishes", "group": "food", "name": tr("Platos regionales", "Regional dishes"), "icon": "l-dishes",
        "emoji": "🥘", "unit": tr("platos y productos de la provincia", "dishes and products of the province"),
        "format": "int", "scale": "linear", "higher_is": "neutral",
        "ramp": ["#2a1708", "#5b3112", "#8f5119", "#c47c2a", "#e6ad55", "#fde3a7"], "source": "gastronomia_es",
        "description": tr(
            "Los {n} platos, embutidos, quesos, dulces, panes y vinos que la Wikipedia en español pone en la "
            "gastronomía de cada provincia (y que Wikidata clasifica como comida o bebida). Pasa el ratón por un "
            "hexágono para ver los de su provincia. Lo editan voluntarios: unas provincias están mucho mejor cubiertas "
            "que otras.",
            "The {n} dishes, cured meats, cheeses, sweets, breads and wines that the Spanish Wikipedia lists under each "
            "province's cuisine (and that Wikidata classes as food or drink). Hover a hex to see its province's. "
            "Volunteer-edited: some provinces are far better covered than others.").format(n=len(dishes)),
        **named_counts([d["name"] for d in dishes],
                       [[c for p in d["provinces"] for c in by_province.get(p, [])] for d in dishes], world["owner"]),
    }


def build() -> None:
    world = load_interim("_world")
    lau = load_interim("siane")
    padron_p = load_interim_payload("ine_padron")
    padron = padron_p["data"]
    pib_p = load_interim_payload("ine_pib")
    pib = pib_p["data"]
    ss = load_interim("ine_censo_ocupados")
    rd_p = load_interim_payload("ine_imasd")
    rates = rd_rates(rd_p["data"], ss["provinces"])
    activity_p, rent_p = load_interim_payload("ine_censo_actividad"), load_interim_payload("serpavi")
    activity, rent = activity_p["data"], rent_p["data"]
    adrh_p = load_interim_payload("ine_adrh")
    adrh = adrh_p["data"]
    proj = active().world_projection(world)
    grid = HexGrid(**world["grid"])
    owner = world["owner"]
    year, gdp_year = padron["year"], pib["year"]
    years = [BASELINE_YEAR, year] if str(BASELINE_YEAR) in padron["nation"] else []

    state_index = {fips: i for i, fips in enumerate(world["states"])}
    centre = {m["geoid"]: m["centre"] for m in lau["municipalities"]}
    regions = {p["fips"]: p for p in lau["provinces"]}
    muni = padron["municipalities"]

    def income_rows(codes) -> list[tuple]:
        """(Padrón population of the ADRH year, ADRH per person, per household) of each municipality."""
        rows = []
        for c in codes:
            a = adrh["municipalities"].get(c) or {}
            rows.append((muni.get(c, {}).get("pop", {}).get(str(adrh["year"])), a.get("net_per_person"),
                         a.get("net_per_household")))
        return rows

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
            **econ(series.get(str(year)), None, None, add_sections([ss["municipalities"].get(c) for c in members]),
                   rd_science({c: ss["municipalities"].get(c) for c in members}, rates),
                   living([activity["municipalities"].get(c) for c in members], income_rows(members),
                          [rent["municipalities"].get(c) for c in members])),
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
            "community": {"code": COMMUNITY_OF[fips], "name": community_name(COMMUNITY_OF[fips])},
            **econ(series.get(str(year)), pib["provinces"].get(fips), gdp_year, ss["provinces"].get(fips),
                   rd_science({fips: ss["provinces"].get(fips)}, rates),
                   living([activity["provinces"].get(fips)], income_rows(c for c in muni if c[:2] == fips),
                          [rent["provinces"].get(fips)])),
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
        "vintage": vintage(padron_p["vintage"]), "year": year, "gdp_vintage": vintage(pib_p["vintage"]),
        "nation": {**econ(nat_series.get(str(year)), pib["nation"], gdp_year, ss["nation"],
                          round(rd_p["data"]["nation"]["personnel_fte"]),
                          living([activity["nation"]], income_rows(muni), list(rent["provinces"].values()))),
                   "growth": growth_of(nat_series, years),
                   "growth_years": years or None},
        "yields": yields_es(ss["year"], rd_p),
        "industries": INDUSTRIES,
        # The living-standard fields and the employed come from other sources than the Padrón, and no source gives
        # home values (docs/DATA_CONTRACTS.md, nation.json).
        "field_vintages": {"unemployment": vintage(activity_p["vintage"]), "median_income": vintage(adrh_p["vintage"]),
                           "median_rent": vintage(rent_p["vintage"]),
                           "employed": vintage(load_interim_payload("ine_censo_ocupados")["vintage"]),
                           "home_value": tr("sin datos: el INE no lo publica", "no data: INE does not publish it")},
    }

    # --- lenses ------------------------------------------------------------------------------------------------
    wikidata = load_interim("wikidata_es")
    food = load_interim("calidad_diferenciada")
    pops = [muni.get(g, {}).get("pop", {}).get(str(year)) for g in world["counties"]]
    _, weights, density = spread_population(
        world, proj, pops, lambda k: (*centre[world["counties"][k]], muni.get(world["counties"][k], {}).get("display", ""))
        if world["counties"][k] in centre else None
    )
    fiesta_lens_list, fiesta_doc = fiesta_lenses(world, proj, grid, lau["municipalities"], pops, weights, year)
    lenses = [{
        "id": "density", "group": "people", "name": tr("Población", "Population"), "icon": "l-people", "emoji": "👥",
        "unit": tr("habitantes / km²", "inhabitants / km²"), "format": "int", "scale": "log",
        "ramp": ["#1b1035", "#4b2377", "#9a3b8a", "#e0645e", "#f9b24a", "#fff3a8"], "higher_is": "neutral",
        "source": "ine_padron",
        "description": tr(
            "Residentes por km² de tierra. La población de cada municipio (Padrón del INE, {year}) se reparte entre sus "
            "hexágonos en proporción a la parte del municipio que cubre cada uno.",
            "Residents per km² of land. Each municipality's population (INE Padrón, {year}) is shared among its hexes in "
            "proportion to the part of the municipality each one covers.").format(year=str(year)),
        "values": density,
    }, income_lens(adrh_p, world["counties"], weights), *people_lenses(world["counties"], weights),
        heritage_lens(wikidata["bic"], proj, grid, owner), museums_lens(wikidata["museums"], proj, grid, owner),
        food_lens(food["names"], proj, grid, world, lau["municipalities"], food["not_registered"]),
        dishes_lens(load_interim("gastronomia_es")["dishes"], world),
        peoples_lens(load_interim("pleiades_iberia")["peoples"], proj, grid, owner),
        languages_lens(load_interim("lenguas_es"), lau["municipalities"], world),
        spain_beaches.beaches_lens(spain_beaches.place(
            load_interim("bandera_azul")["beaches"], lau["municipalities"], load_interim("wikidata_playas")["beaches"],
            load_interim("osm_playas")["beaches"]), lau["municipalities"], world, grid, proj),
        *fiesta_lens_list] + [
        {**lens, **LAND_LENSES[lens["id"]], "unit": LAND_UNIT} for lens in land_lenses(world, "corine")]
    lenses += spain_daily.lenses(world, weights, proj, grid)
    lenses += spain_crime.lenses(load_interim("balance_criminalidad"), padron, lau["municipalities"], world["counties"],
                                 weights)
    lenses += spain_fauna.lenses(world, proj, grid, lau["municipalities"])
    great, people_doc = spain_personajes.great_people(world, proj, grid, lau["municipalities"])
    lenses += great
    set_domains(lenses, DOMAIN_NOTE)
    groups = [g for g in localized(GROUPS, {k: {"name": v} for k, v in LENS_GROUPS.items()}) + ES_GROUPS
              if any(l["group"] == g["id"] for l in lenses)]

    write_web("cities.json", cities)
    write_web("nation.json", nation)
    write_web("states.json", states)
    write_web("lenses.json", {"vintage": vintage(padron_p["vintage"]), "groups": groups, "lenses": lenses})
    write_web(f"{spain_personajes.FILE}.json", people_doc)
    write_web(f"{FIESTA_FILE}.json", fiesta_doc)
    print(f"    {len(cities)} cities (AUDES large urban areas), {len(states)} provinces; GDP {gdp_year}, Padrón {year}")
