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
from .texts_es import BADGE_TEXT, num, pct, vintage

REQUIRES = ["ine_censo_divisiones", "_world", "cities.json", "world.json"]
PRODUCES = ["districts.json"]
COUNTRIES = ("es",)

ALL = [0]  # the census has no ownership split: one "ownership" that sums everything
MANUFACTURING = [f"{d:02d}" for d in range(10, 34)]
MINING = ["05", "06", "07", "08", "09"]

CATALOG = [
    _d("campus", "Campus", "#4a7bd0", ["72", "62", "63"], ALL,
       {"72": "Investigación y desarrollo", "62": "Programación y servicios informáticos", "63": "Servicios de información"},
       ("scientific", "Ciudad del conocimiento"),
       {"72": "Ciudad de la investigación", "62": "Ciudad tecnológica", "63": "Ciudad tecnológica"},
       "Ciencia y tecnología: investigación y desarrollo, programación y servicios informáticos, servicios de información."),
    _d("commercial_hub", "Centro comercial", "#d0a23a", ["64", "65", "66"], ALL,
       {"64": "Banca", "65": "Seguros"},
       ("commercial", "Ciudad financiera"), {"64": "Capital financiera", "65": "Ciudad de los seguros"},
       "Finanzas y seguros: bancos, aseguradoras y los servicios que los rodean."),
    _d("industrial_zone", "Zona industrial", "#c2643a", MANUFACTURING + MINING, ALL,
       {"29": "Vehículos de motor", "23": "Cerámica, vidrio y cemento", "26": "Electrónica", "21": "Industria farmacéutica",
        "19": "Refino de petróleo", "24": "Metalurgia", "20": "Industria química", "15": "Cuero y calzado", "13": "Textil",
        "14": "Confección", "11": "Bebidas", "10": "Alimentación"},
       ("industrial", "Ciudad fabril"),
       {"29": "Ciudad del motor", "23": "Ciudad de la cerámica", "26": "Ciudad del silicio", "21": "Ciudad farmacéutica",
        "19": "Ciudad refinera", "24": "Ciudad del acero", "20": "Ciudad química", "15": "Ciudad del calzado",
        "13": "Ciudad textil", "14": "Ciudad de la moda", "11": "Ciudad de las bebidas", "10": "Ciudad de la alimentación"},
       "Industria manufacturera, más minas y canteras."),
    _d("harbor", "Puerto", "#2f8fb0", ["50"], ALL,
       {"50": "Transporte marítimo"}, ("maritime", "Ciudad portuaria"), {"50": "Ciudad portuaria"},
       "Transporte marítimo y por vías navegables interiores (los servicios portuarios están dentro de la división de "
       "almacenamiento, más amplia, y no se pueden separar).",
       "Solo para ciudades con un hexágono sobre el agua, junto a ella o en un río del mapa."),
    _d("theater_square", "Plaza del teatro", "#a15bc4", ["90", "59", "60"], ALL,
       {"90": "Artes escénicas", "59": "Cine y música", "60": "Radio y televisión"},
       ("cultural", "Ciudad de las artes"), {"90": "Ciudad de las artes", "59": "Capital del cine", "60": "Ciudad de los medios"},
       "Cultura y medios: artes escénicas y creación, cine, vídeo y música, radio y televisión."),
    _d("entertainment_complex", "Complejo de ocio", "#d0508a", ["93", "92", "55"], ALL,
       {"92": "Juego y apuestas", "93": "Deporte y ocio", "55": "Hoteles y alojamiento"},
       ("entertainment", "Ciudad turística"), {"92": "Ciudad del juego", "93": "Ciudad turística", "55": "Ciudad turística"},
       "Ocio: deporte, actividades recreativas y juegos de azar, más hoteles y otros alojamientos."),
    _d("aerodrome", "Aeródromo", "#6a8fb8", ["51"], ALL,
       {"51": "Transporte aéreo"}, ("aviation", "Nudo aéreo"), {"51": "Nudo aéreo"},
       "Transporte aéreo (la construcción aeronáutica comparte división con la naval y la ferroviaria y no se puede separar)."),
    _d("government_plaza", "Plaza del gobierno", "#8a9a5b", ["84"], ALL,
       {}, ("governmental", "Ciudad administrativa"), {},
       "Administración pública, defensa y Seguridad Social obligatoria (una sola división: la defensa no se puede separar)."),
    _d("aqueduct", "Acueducto y presa", "#3aa0a0", ["35", "36"], ALL,
       {"35": "Electricidad y gas", "36": "Captación y distribución de agua"},
       ("utility", "Ciudad de los suministros"), {"35": "Ciudad de la energía", "36": "Ciudad del agua"},
       "Suministros: electricidad y gas, y captación y distribución de agua."),
]
BY_ID = {d["id"]: d for d in CATALOG}
# City types named by hand where the CNAE division is broader than what the city is known for (DECISIONS E20).
BADGE_LABELS = {"26089": "Ciudad del vino tinto"}  # Logroño: its beverages division is Rioja wine
assert [d["id"] for d in CATALOG] == [d["id"] for d in US_CATALOG if d["id"] != "encampment"]

RULE_TEXT = (
    f"Un distrito aparece cuando los residentes ocupados de la ciudad en sus divisiones de la CNAE son al menos "
    f"{num(MIN_LQ)} veces la cuota nacional y suman al menos {num(MIN_JOBS)} personas o el {pct(MIN_SHARE)} de los "
    f"ocupados de la ciudad, o cuando una de sus especialidades llega a {num(SPECIALTY_LQ)} veces la cuota nacional con "
    f"al menos {num(SPECIALTY_JOBS)} personas o el {pct(SPECIALTY_SHARE, 1)} de los ocupados. Los distritos se ordenan "
    f"por cuántas personas emplean por encima de la norma nacional, hasta {MAX_PER_CITY} por ciudad. Un Puerto necesita "
    f"además un hexágono de la ciudad sobre el agua, junto a ella o en un río del mapa. El tipo de ciudad toma el nombre "
    f"del distrito más fuerte, o de una especialidad con un cociente de al menos {num(BADGE_LQ)} y al menos el "
    f"{pct(BADGE_SHARE)} de los ocupados de la ciudad cuando la hay; «{BADGE_TEXT['capital']}» corresponde a la Plaza del "
    f"gobierno de Madrid. El empleo es el del Censo anual de población del INE (residentes ocupados, contados donde "
    f"viven, por división de dos dígitos de la CNAE-2009) para las 151 ciudades que el INE publica con ese detalle."
)
METHOD = {
    "code_system": "CNAE", "source_label": "INE Censo anual",
    "note": "El censo cuenta a los residentes ocupados donde viven, por la división de la CNAE-2009 de su empleo; no "
    "recoge salarios, así que no hay salario medio. Las divisiones de dos dígitos son más gruesas que los códigos NAICS "
    "de EE. UU.",
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
            "badge": badge_for(badge_district(dists), bool(c.get("capital")), False, BY_ID, "census", BADGE_TEXT),
        }
        if out_cities[c["id"]]["badge"] and c["id"] in BADGE_LABELS:
            out_cities[c["id"]]["badge"]["label"] = BADGE_LABELS[c["id"]]

    catalog = [dict(d, naics=list(d["naics"])) for d in CATALOG]
    write_web("districts.json", {
        "version": 1,
        "vintage": vintage(payload["vintage"]),
        "year": data["year"],
        "sources": ["ine_censo_divisiones"],
        "rule": {"min_lq": MIN_LQ, "min_jobs": MIN_JOBS, "min_share": MIN_SHARE, "specialty_lq": SPECIALTY_LQ,
                 "specialty_jobs": SPECIALTY_JOBS, "specialty_share": SPECIALTY_SHARE, "max_per_city": MAX_PER_CITY,
                 "harbor_needs_water": True, "badge_lq": BADGE_LQ, "badge_share": BADGE_SHARE, "text": RULE_TEXT,
                 "county_note": "Los municipios no tienen distritos propios: el censo solo publica las divisiones de dos "
                 "dígitos de las ciudades principales."},
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
