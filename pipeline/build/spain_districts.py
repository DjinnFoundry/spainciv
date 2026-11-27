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

from ..core.lang import pick_all
from ..core.store import load_interim, load_interim_payload, load_web, write_web
from .districts import (
    BADGE_LQ, BADGE_SHARE, CATALOG as US_CATALOG, MAX_PER_CITY, MIN_JOBS, MIN_LQ, MIN_SHARE, SPECIALTY_JOBS,
    SPECIALTY_LQ, SPECIALTY_SHARE, TOP_INDUSTRIES, _d, _r, badge_district, badge_for, evaluate, lq, wet_cities,
)
from .texts_es import BADGE_TEXT, Text, pct, tr, vintage

REQUIRES = ["ine_censo_divisiones", "_world", "cities.json", "world.json"]
PRODUCES = ["districts.json"]
COUNTRIES = ("es",)

ALL = [0]  # the census has no ownership split: one "ownership" that sums everything
MANUFACTURING = [f"{d:02d}" for d in range(10, 34)]
MINING = ["05", "06", "07", "08", "09"]

# Names, specialities, city types and descriptions in Spanish and English; the English district names, and the city
# types that mean the same, are the US catalog's (districts.CATALOG).
CATALOG = [
    _d("campus", "Campus", "#4a7bd0", ["72", "62", "63"], ALL,
       {"72": tr("Investigación y desarrollo", "Research and development"),
        "62": tr("Programación y servicios informáticos", "Programming and computer services"),
        "63": tr("Servicios de información", "Information services")},
       ("scientific", tr("Ciudad del conocimiento", "Knowledge city")),
       {"72": tr("Ciudad de la investigación", "Research city"), "62": tr("Ciudad tecnológica", "Tech city"),
        "63": tr("Ciudad tecnológica", "Tech city")},
       tr("Ciencia y tecnología: investigación y desarrollo, programación y servicios informáticos, servicios de "
          "información.",
          "Science and technology: research and development, programming and computer services, information services.")),
    _d("commercial_hub", tr("Centro comercial", "Commercial hub"), "#d0a23a", ["64", "65", "66"], ALL,
       {"64": tr("Banca", "Banking"), "65": tr("Seguros", "Insurance")},
       ("commercial", tr("Ciudad financiera", "Finance city")),
       {"64": tr("Capital financiera", "Finance capital"), "65": tr("Ciudad de los seguros", "Insurance city")},
       tr("Finanzas y seguros: bancos, aseguradoras y los servicios que los rodean.",
          "Finance and insurance: banks, insurers and the services around them.")),
    _d("industrial_zone", tr("Zona industrial", "Industrial zone"), "#c2643a", MANUFACTURING + MINING, ALL,
       {"29": tr("Vehículos de motor", "Motor vehicles"), "23": tr("Cerámica, vidrio y cemento", "Ceramics, glass and cement"),
        "26": tr("Electrónica", "Electronics"), "21": tr("Industria farmacéutica", "Pharmaceuticals"),
        "19": tr("Refino de petróleo", "Oil refining"), "24": tr("Metalurgia", "Basic metals"),
        "20": tr("Industria química", "Chemicals"), "15": tr("Cuero y calzado", "Leather and footwear"),
        "13": tr("Textil", "Textiles"), "14": tr("Confección", "Clothing"), "11": tr("Bebidas", "Beverages"),
        "10": tr("Alimentación", "Food products")},
       ("industrial", tr("Ciudad fabril", "Factory town")),
       {"29": tr("Ciudad del motor", "Motor city"), "23": tr("Ciudad de la cerámica", "Ceramics town"),
        "26": tr("Ciudad del silicio", "Silicon city"), "21": tr("Ciudad farmacéutica", "Pharma city"),
        "19": tr("Ciudad refinera", "Refinery town"), "24": tr("Ciudad del acero", "Steel town"),
        "20": tr("Ciudad química", "Chemical town"), "15": tr("Ciudad del calzado", "Shoe town"),
        "13": tr("Ciudad textil", "Textile town"), "14": tr("Ciudad de la moda", "Fashion city"),
        "11": tr("Ciudad de las bebidas", "Drinks town"), "10": tr("Ciudad de la alimentación", "Food town")},
       tr("Industria manufacturera, más minas y canteras.", "Manufacturing, plus mines and quarries.")),
    _d("harbor", tr("Puerto", "Harbor"), "#2f8fb0", ["50"], ALL,
       {"50": tr("Transporte marítimo", "Water transport")}, ("maritime", tr("Ciudad portuaria", "Port city")),
       {"50": tr("Ciudad portuaria", "Port city")},
       tr("Transporte marítimo y por vías navegables interiores (los servicios portuarios están dentro de la división de "
          "almacenamiento, más amplia, y no se pueden separar).",
          "Sea and inland water transport (port services are part of the broader warehousing division and cannot be "
          "split off)."),
       tr("Solo para ciudades con un hexágono sobre el agua, junto a ella o en un río del mapa.",
          "Only for cities with a hex on or next to water or on a mapped river.")),
    _d("theater_square", tr("Plaza del teatro", "Theater square"), "#a15bc4", ["90", "59", "60"], ALL,
       {"90": tr("Artes escénicas", "Performing arts"), "59": tr("Cine y música", "Film and music"),
        "60": tr("Radio y televisión", "Radio and television")},
       ("cultural", tr("Ciudad de las artes", "Arts city")),
       {"90": tr("Ciudad de las artes", "Arts city"), "59": tr("Capital del cine", "Film capital"),
        "60": tr("Ciudad de los medios", "Media city")},
       tr("Cultura y medios: artes escénicas y creación, cine, vídeo y música, radio y televisión.",
          "Culture and media: performing and creative arts, film, video and music, radio and television.")),
    _d("entertainment_complex", tr("Complejo de ocio", "Entertainment complex"), "#d0508a", ["93", "92", "55"], ALL,
       {"92": tr("Juego y apuestas", "Gambling and betting"), "93": tr("Deporte y ocio", "Sport and recreation"),
        "55": tr("Hoteles y alojamiento", "Hotels and accommodation")},
       ("entertainment", tr("Ciudad turística", "Resort city")),
       {"92": tr("Ciudad del juego", "Casino city"), "93": tr("Ciudad turística", "Resort city"),
        "55": tr("Ciudad turística", "Resort city")},
       tr("Ocio: deporte, actividades recreativas y juegos de azar, más hoteles y otros alojamientos.",
          "Leisure: sport, recreation and gambling, plus hotels and other accommodation.")),
    _d("aerodrome", tr("Aeródromo", "Aerodrome"), "#6a8fb8", ["51"], ALL,
       {"51": tr("Transporte aéreo", "Air transport")}, ("aviation", tr("Nudo aéreo", "Air hub")),
       {"51": tr("Nudo aéreo", "Air hub")},
       tr("Transporte aéreo (la construcción aeronáutica comparte división con la naval y la ferroviaria y no se puede "
          "separar).",
          "Air transport (aircraft building shares a division with ships and railway stock and cannot be split off).")),
    _d("government_plaza", tr("Plaza del gobierno", "Government plaza"), "#8a9a5b", ["84"], ALL,
       {}, ("governmental", tr("Ciudad administrativa", "Government town")), {},
       tr("Administración pública, defensa y Seguridad Social obligatoria (una sola división: la defensa no se puede "
          "separar).",
          "Public administration, defence and compulsory social security (a single division: defence cannot be split "
          "off).")),
    _d("aqueduct", tr("Acueducto y presa", "Aqueduct & dam"), "#3aa0a0", ["35", "36"], ALL,
       {"35": tr("Electricidad y gas", "Electricity and gas"),
        "36": tr("Captación y distribución de agua", "Water collection and supply")},
       ("utility", tr("Ciudad de los suministros", "Utility town")),
       {"35": tr("Ciudad de la energía", "Power town"), "36": tr("Ciudad del agua", "Waterworks town")},
       tr("Suministros: electricidad y gas, y captación y distribución de agua.",
          "Utilities: electricity and gas, and water collection and supply.")),
]
BY_ID = {d["id"]: d for d in CATALOG}
# City types named by hand where the CNAE division is broader than what the city is known for (DECISIONS E20).
BADGE_LABELS = {"26089": tr("Ciudad del vino tinto", "Red wine town")}  # Logroño: its beverages division is Rioja wine
assert [d["id"] for d in CATALOG] == [d["id"] for d in US_CATALOG if d["id"] != "encampment"]

RULE_TEXT = tr(
    "Un distrito aparece cuando los residentes ocupados de la ciudad en sus divisiones de la CNAE son al menos {min_lq} "
    "veces la cuota nacional y suman al menos {min_jobs} personas o el {min_share} de los ocupados de la ciudad, o cuando "
    "una de sus especialidades llega a {sp_lq} veces la cuota nacional con al menos {sp_jobs} personas o el {sp_share} "
    "de los ocupados. Los distritos se ordenan por cuántas personas emplean por encima de la norma nacional, hasta "
    "{max} por ciudad. Un Puerto necesita además un hexágono de la ciudad sobre el agua, junto a ella o en un río del "
    "mapa. El tipo de ciudad toma el nombre del distrito más fuerte, o de una especialidad con un cociente de al menos "
    "{badge_lq} y al menos el {badge_share} de los ocupados de la ciudad cuando la hay; «{capital}» corresponde a la "
    "Plaza del gobierno de Madrid. El empleo es el del Censo anual de población del INE (residentes ocupados, contados "
    "donde viven, por división de dos dígitos de la CNAE-2009) para las 151 ciudades que el INE publica con ese detalle.",
    "A district appears when the city's employed residents in its CNAE divisions are at least {min_lq} times the "
    "national share and number at least {min_jobs} people or {min_share} of the city's employed, or when one of its "
    "specialities reaches {sp_lq} times the national share with at least {sp_jobs} people or {sp_share} of the "
    "employed. Districts are ranked by how many people they employ above the national norm, up to {max} per city. A "
    "Harbor also needs a city hex on or next to water or on a mapped river. The city type is named after the strongest "
    "district, or after a speciality with a quotient of at least {badge_lq} and at least {badge_share} of the city's "
    "employed when there is one; “{capital}” is Madrid's Government plaza. Employment is from INE's Annual Population "
    "Census (employed residents, counted where they live, by two-digit CNAE-2009 division) for the 151 cities INE "
    "publishes at that detail.",
).format(min_lq=MIN_LQ, min_jobs=MIN_JOBS, min_share=tr(pct(MIN_SHARE), pct(MIN_SHARE, 0, "en")), sp_lq=SPECIALTY_LQ,
         sp_jobs=SPECIALTY_JOBS, sp_share=tr(pct(SPECIALTY_SHARE, 1), pct(SPECIALTY_SHARE, 1, "en")), max=MAX_PER_CITY,
         badge_lq=BADGE_LQ, badge_share=tr(pct(BADGE_SHARE), pct(BADGE_SHARE, 0, "en")),
         capital=tr(BADGE_TEXT["es"]["capital"], BADGE_TEXT["en"]["capital"]))
METHOD = {
    "code_system": "CNAE", "source_label": tr("INE Censo anual", "INE Annual Population Census"),
    "note": tr("El censo cuenta a los residentes ocupados donde viven, por la división de la CNAE-2009 de su empleo; no "
               "recoge salarios, así que no hay salario medio. Las divisiones de dos dígitos son más gruesas que los "
               "códigos NAICS de EE. UU.",
               "The census counts employed residents where they live, by the CNAE-2009 division of their job; it records "
               "no wages, so there is no average pay. Two-digit divisions are coarser than the US NAICS codes."),
}
COUNTY_NOTE = tr("Los municipios no tienen distritos propios: el censo solo publica las divisiones de dos dígitos de las "
                 "ciudades principales.",
                 "Municipalities have no districts of their own: the census publishes two-digit divisions for the main "
                 "cities only.")


BY_LANG = {lang: pick_all(BY_ID, lang) for lang in BADGE_TEXT}


def badge(best: dict | None, capital: bool, label: Text | None = None) -> dict | None:
    """districts.badge_for in each language, its label and sentence as Texts (the label given by hand if `label`)."""
    per = {lang: badge_for(best, capital, False, BY_LANG[lang], "census", texts) for lang, texts in BADGE_TEXT.items()}
    if per["es"] is None:
        return None
    out = {**per["es"], "label": Text(**{lang: b["label"] for lang, b in per.items()}),
           "text": Text(**{lang: b["text"] for lang, b in per.items()})}
    return out | {"label": label} if label else out


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
            "badge": badge(badge_district(dists), bool(c.get("capital")), BADGE_LABELS.get(c["id"])),
        }

    catalog = [dict(d, naics=list(d["naics"])) for d in CATALOG]
    write_web("districts.json", {
        "version": 1,
        "vintage": vintage(payload["vintage"]),
        "year": data["year"],
        "sources": ["ine_censo_divisiones"],
        "rule": {"min_lq": MIN_LQ, "min_jobs": MIN_JOBS, "min_share": MIN_SHARE, "specialty_lq": SPECIALTY_LQ,
                 "specialty_jobs": SPECIALTY_JOBS, "specialty_share": SPECIALTY_SHARE, "max_per_city": MAX_PER_CITY,
                 "harbor_needs_water": True, "badge_lq": BADGE_LQ, "badge_share": BADGE_SHARE, "text": RULE_TEXT,
                 "county_note": COUNTY_NOTE},
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
