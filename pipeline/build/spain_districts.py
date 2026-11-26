"""Spain's districts: the US district rule (pipeline/build/districts.py) on INE census employment by CNAE division.

Same rule, thresholds, ranking and badges as the US map; what changes is the data and the dictionary:

* Jobs are employed residents by two-digit CNAE-2009 division (INE Annual Population Census, table 69980), for the
  151 provincial capitals and main cities INE publishes at that detail; the national shares come from table 69960.
  A city (an urban area) gets the districts of its core municipality; a city whose core has no divisions has none
  (null), never a guess.
* The catalog maps each district to CNAE divisions. Two-digit divisions are coarser than the US's NAICS codes, so some
  districts lose specialities (no casinos inside 'gambling', no defence inside public administration: the Encampment
  has no Spanish counterpart and is left out).
* The census counts no wages and suppresses nothing, so `avg_pay` is null and no value is a lower bound.
"""

from __future__ import annotations

from ..core.store import load_interim, load_interim_payload, load_web, write_web
from .districts import (
    BADGE_LQ, BADGE_SHARE, CATALOG as US_CATALOG, MAX_PER_CITY, MIN_JOBS, MIN_LQ, MIN_SHARE, SPECIALTY_JOBS,
    SPECIALTY_LQ, SPECIALTY_SHARE, TOP_INDUSTRIES, _d, _r, badge_district, badge_for, evaluate, lq, wet_cities,
)

REQUIRES = ["ine_censo_divisiones", "_world", "cities.json", "world.json"]
PRODUCES = ["districts.json"]
COUNTRIES = ("es",)

ALL = [0]  # the census has no ownership split: one "ownership" that sums everything
MANUFACTURING = [f"{d:02d}" for d in range(10, 34)]
MINING = ["05", "06", "07", "08", "09"]

CATALOG = [
    _d("campus", "Campus", "#4a7bd0", ["72", "62", "63"], ALL,
       {"72": "Research & development", "62": "Software & IT services", "63": "Information services"},
       ("scientific", "Knowledge city"), {"72": "Research city", "62": "Tech city", "63": "Tech city"},
       "Science and technology: research and development, software and IT services, information services."),
    _d("commercial_hub", "Commercial hub", "#d0a23a", ["64", "65", "66"], ALL,
       {"64": "Banking", "65": "Insurance"},
       ("commercial", "Finance city"), {"64": "Finance capital", "65": "Insurance city"},
       "Finance and insurance: banks, insurers and the services around them."),
    _d("industrial_zone", "Industrial zone", "#c2643a", MANUFACTURING + MINING, ALL,
       {"29": "Motor vehicles", "23": "Ceramics, glass & cement", "26": "Electronics", "21": "Pharmaceuticals",
        "19": "Oil refining", "24": "Metals", "20": "Chemicals"},
       ("industrial", "Factory town"),
       {"29": "Motor city", "23": "Ceramics city", "26": "Silicon city", "21": "Pharma city", "19": "Refinery town",
        "24": "Steel town", "20": "Chemical town"},
       "Manufacturing plus mining and quarrying."),
    _d("harbor", "Harbor", "#2f8fb0", ["50"], ALL,
       {"50": "Shipping"}, ("maritime", "Port city"), {"50": "Port city"},
       "Water transport: sea and inland shipping (port services are inside the broader 'warehousing' division and "
       "cannot be split out).", "Only for cities with a hex on or next to water or a mapped river."),
    _d("theater_square", "Theater square", "#a15bc4", ["90", "59", "60"], ALL,
       {"90": "Performing arts", "59": "Film & music", "60": "Broadcasting"},
       ("cultural", "Arts city"), {"90": "Arts city", "59": "Film capital", "60": "Media city"},
       "Culture and media: performing arts and creation, film, video and music, radio and television."),
    _d("entertainment_complex", "Entertainment complex", "#d0508a", ["93", "92", "55"], ALL,
       {"92": "Gambling", "93": "Sport & recreation", "55": "Hotels & lodging"},
       ("entertainment", "Resort city"), {"92": "Casino city", "93": "Resort city", "55": "Resort city"},
       "Leisure: sport, recreation and gambling, plus hotels and other lodging."),
    _d("aerodrome", "Aerodrome", "#6a8fb8", ["51"], ALL,
       {"51": "Airlines"}, ("aviation", "Air hub"), {"51": "Air hub"},
       "Air transport (aircraft manufacturing shares a division with ships and trains and cannot be split out)."),
    _d("government_plaza", "Government plaza", "#8a9a5b", ["84"], ALL,
       {}, ("governmental", "Government town"), {},
       "Public administration, defence and compulsory social security (one division: defence cannot be split out)."),
    _d("aqueduct", "Aqueduct & dam", "#3aa0a0", ["35", "36"], ALL,
       {"35": "Power & gas", "36": "Water supply"},
       ("utility", "Utility town"), {"35": "Power town", "36": "Waterworks town"},
       "Utilities: electricity and gas, and water collection and supply."),
]
BY_ID = {d["id"]: d for d in CATALOG}
assert [d["id"] for d in CATALOG] == [d["id"] for d in US_CATALOG if d["id"] != "encampment"]

RULE_TEXT = (
    f"A district appears when the city's employed residents in its CNAE divisions are at least {MIN_LQ:g} times the "
    f"national share and number at least {MIN_JOBS:,} or {MIN_SHARE:.0%} of the city's employed residents, or when one "
    f"of its listed specialities is at least {SPECIALTY_LQ:g} times the national share with at least {SPECIALTY_JOBS:,} "
    f"people or {SPECIALTY_SHARE:.1%} of the city's employed. Districts are ranked by how many people they employ above "
    f"the national norm; up to {MAX_PER_CITY} per city. A Harbor also needs a city hex on or next to water or a mapped "
    f"river. The city type is named after the strongest district, or after a listed district with a quotient of at "
    f"least {BADGE_LQ:g} and at least {BADGE_SHARE:.0%} of the city's employed when there is one; 'Capital city' goes "
    f"to Madrid's Government plaza. Employment is the INE Annual Population Census (employed residents, counted where "
    f"they live, by two-digit CNAE-2009 division) for the 151 cities INE publishes at that detail."
)
METHOD = {
    "code_system": "CNAE", "source_label": "INE Censo anual",
    "note": "The census counts employed residents where they live, by the CNAE-2009 division of their job; it has no "
    "wages, so there is no average pay. Two-digit divisions are coarser than US NAICS codes.",
}


class CensusMetrics:
    """districts.evaluate's metrics over INE census divisions: one city = one municipality, nothing suppressed."""

    def __init__(self, data: dict):
        self.local, self.national = data["municipalities"], data["nation"]
        self.us_emp = self.national["total"]

    def industry(self, codes: list[str], own: list[int], members: list[str]) -> dict:
        rows = [self.local.get(m) for m in members]
        if not any(rows):
            return {"emp": None, "wages": None, "chg": None, "suppressed": 0}
        emp = sum(r.get(c, 0) for r in rows if r for c in codes)
        return {"emp": emp, "wages": None, "chg": None, "suppressed": 0}

    def us(self, codes: list[str], own: list[int]) -> int:
        return sum(self.national.get(c, 0) for c in codes)


def build() -> None:
    payload = load_interim_payload("ine_censo_divisiones")
    data = payload["data"]
    m = CensusMetrics(data)
    world_i = load_interim("_world")
    cities = load_web("cities.json")
    wet = wet_cities(cities, world_i, load_web("world.json"))
    titles = data["titles"]
    industries = {c: {"title": t, "us_emp": m.us([c], ALL)} for c, t in titles.items()}

    out_cities: dict[str, dict | None] = {}
    for c in cities:
        # A city is an urban area, but INE publishes divisions only for main cities: the districts describe the area's
        # core municipality (its id), with that municipality's own total, so the quotients are not mixed.
        members = [c["id"]]
        row = data["municipalities"].get(c["id"])
        if not row:
            out_cities[c["id"]] = None
            continue
        total = row["total"]
        top = []
        for code in titles:
            emp = row.get(code)
            if emp is None or emp < MIN_JOBS:
                continue
            ilq = lq(emp, total, industries[code]["us_emp"], m.us_emp)
            if ilq is not None:
                top.append({"naics": code, "emp": emp, "lq": _r(ilq, 2), "avg_pay": None, "oty_pct": None,
                            "suppressed": 0, "lower_bound": False})
        top.sort(key=lambda r: -r["lq"])
        dists = evaluate(m, members, total, c["id"] in wet, CATALOG)
        out_cities[c["id"]] = {
            "emp": total, "avg_pay": None, "counties": [1, len(c.get("counties") or [])], "top": top[:TOP_INDUSTRIES],
            "districts": dists,
            "badge": badge_for(badge_district(dists), bool(c.get("capital")), False, BY_ID, "census"),
        }

    catalog = [dict(d, naics=list(d["naics"])) for d in CATALOG]
    write_web("districts.json", {
        "version": 1,
        "vintage": payload["vintage"],
        "year": data["year"],
        "sources": ["ine_censo_divisiones"],
        "rule": {"min_lq": MIN_LQ, "min_jobs": MIN_JOBS, "min_share": MIN_SHARE, "specialty_lq": SPECIALTY_LQ,
                 "specialty_jobs": SPECIALTY_JOBS, "specialty_share": SPECIALTY_SHARE, "max_per_city": MAX_PER_CITY,
                 "harbor_needs_water": True, "badge_lq": BADGE_LQ, "badge_share": BADGE_SHARE, "text": RULE_TEXT,
                 "county_note": "Municipalities have no districts of their own: the census publishes two-digit divisions "
                 "only for the main cities."},
        "method": METHOD,
        "catalog": catalog,
        "industries": industries,
        "national": {"emp": m.us_emp, "avg_pay": None},
        "cities": out_cities,
        "counties": {},
    })
    with_d = [k for k, v in out_cities.items() if v]
    print(f"    {len(with_d)} of {len(cities)} cities with census divisions; "
          f"{sum(1 for k in with_d if out_cities[k]['badge'])} with a city type")
