"""Spain's crime lenses, from the Ministerio del Interior's Balance de Criminalidad (sources/es/criminalidad.py).

* **Crime**: known criminal offences per 1,000 inhabitants (Padrón of the balance's year). The balance lists every
  municipality over 20,000 inhabitants: those carry their own rate. Every other municipality takes the rest of its
  province, or of its island in the Balearic and Canary Islands (the unit's offences and residents minus those of its
  listed municipalities), as spain_daily's `listed_or_rest` does for INE's main cities.
* **Crime above Spain's rate**: the offence type whose rate is the most times Spain's, among the types common enough
  to compare (`COMPARED`); null where no type is above Spain's rate.

A hex takes the population-weighted mean of its municipalities' rates, type by type. Both lenses list in the tooltip,
for each listed municipality or rest of province the hex holds, its three highest rates by type.
"""

from __future__ import annotations

from ..core.lang import Num, Text, join_texts, num, pick, tr
from ..sources.es.criminalidad import TOTAL
from ..sources.es.food import ISLANDS
from ..sources.es.ine_daily import province_of, rest_of_provinces
from ..sources.es.provinces import PROVINCES, display_name
from .lenses import DISASTERS_RAMP, _spread
from .spain_daily import SPREAD, by_municipality, listed_or_rest
from .spain_food import island

SOURCES = ["balance_criminalidad"]
PER = 1000  # per 1,000 inhabitants
POP = "pop"  # the residents, carried with the counts so the rest of a unit subtracts them too
# The balance's types, as the tooltip and the legend name them. Its catch-all ("resto de criminalidad convencional")
# counts in the total but is no type to name.
TYPE_NAMES = {
    "homicide": tr("homicidios", "homicides"),
    "attempted_homicide": tr("intentos de homicidio", "attempted homicides"),
    "assault": tr("lesiones", "assault"), "kidnapping": tr("secuestros", "kidnapping"),
    "sexual": tr("delitos sexuales", "sexual offences"),
    "violent_robbery": tr("robos con violencia", "violent robbery"),
    "burglary": tr("robos con fuerza", "burglary"), "theft": tr("hurtos", "theft"),
    "vehicle_theft": tr("robos de vehículos", "vehicle theft"),
    "drug_trafficking": tr("tráfico de drogas", "drug trafficking"),
    "online_fraud": tr("estafas informáticas", "online fraud"),
    "other_cyber": tr("otros ciberdelitos", "other cybercrime"),
}
# The types the second lens compares: those with at least about 20,000 known offences a year in Spain, so a listed
# municipality of 20,000 inhabitants expects ten or more of each. Homicides (a few hundred), attempted homicides and
# kidnappings would let one case decide a town.
COMPARED = {
    "theft": "#e0a83a", "online_fraud": "#3d8fbf", "burglary": "#c8553d", "violent_robbery": "#9b2442",
    "assault": "#e86a92", "vehicle_theft": "#7fb069", "drug_trafficking": "#9b5de5", "sexual": "#d9d9d9",
    "other_cyber": "#43aa8b",
}
TOOLTIP_TYPES = 3


def island_of(municipalities: list[dict]) -> dict[str, str]:
    """INE code → island (food.ISLANDS) of every municipality of the Balearic and Canary Islands."""
    return {code: name for name, seed in ISLANDS.items() for code in island(municipalities, seed)}


def crime_units(crime: dict, pops: dict[str, int], islands: dict[str, str]) -> dict:
    """The counts and residents of every listed municipality ("municipalities") and of the rest of every province or
    island ("rest_of_province", keyed by province code or island name), and `unit_of`, the unit a municipality is in.
    A unit's residents are the Padrón's of its municipalities."""
    def unit_of(code: str) -> str:
        return islands.get(code) or province_of(code)

    def with_pop(counts: dict, residents: int) -> dict:
        return {**counts, POP: residents}

    unit_pop: dict[str, int] = {}
    for code, n in pops.items():
        unit_pop[unit_of(code)] = unit_pop.get(unit_of(code), 0) + n
    on_islands = {code[:2] for code in islands}
    units = {**{p: with_pop(c, unit_pop[p]) for p, c in crime["provinces"].items() if p not in on_islands},
             **{name: with_pop(c, unit_pop[name]) for name, c in crime["islands"].items()}}
    listed = {code: with_pop(c, pops[code]) for code, c in crime["municipalities"].items()}
    return {"municipalities": listed, "rest_of_province": rest_of_provinces(units, listed, unit_of),
            "unit_of": unit_of}


def rate(key: str):
    """Offences of `key` per 1,000 residents of a set of counts."""
    return lambda counts: counts.get(key, 0) * PER / counts[POP] if counts.get(POP) else None


def unit_name(unit: str, listed_in_it: bool) -> Text | str:
    """'Toledo' → 'Resto de la provincia de Toledo'; an island: 'Resto de Mallorca'; a unit with no listed
    municipality, its own name ('Ceuta', 'El Hierro')."""
    name = unit if unit in ISLANDS else display_name(PROVINCES[unit][1])
    if not listed_in_it:
        return name
    if unit in ISLANDS:
        return tr("Resto de {name}", "Rest of {name}").format(name=name)
    return tr("Resto de la provincia de {name}", "Rest of the province of {name}").format(name=name)


def breakdown(name, counts: dict) -> Text:
    """'Benidorm: hurtos 40,1, estafas informáticas 9,9, robos con fuerza 4,0': the three highest rates by type per
    1,000 inhabitants."""
    top = sorted(TYPE_NAMES, key=lambda k: -counts.get(k, 0))[:TOOLTIP_TYPES]
    rates = join_texts([TYPE_NAMES[k].map(lambda s, lang, k=k: f"{s} {num(rate(k)(counts), 1, lang)}") for k in top])
    return rates.map(lambda s, lang: f"{pick(name, lang)}: {s}")


def unit_labels(units: dict, municipalities: dict[str, str], geoids: list[str], weights: list) -> dict:
    """`names` (one per listed municipality and rest of a unit, with its breakdown) and per hex the indices of those its
    municipalities are in (`labels`), the most populous first."""
    unit_of, listed = units["unit_of"], units["municipalities"]
    with_listed = {unit_of(code) for code in listed}
    keys = [*sorted(listed), *sorted(units["rest_of_province"])]
    index = {k: i for i, k in enumerate(keys)}
    names = [breakdown(municipalities.get(k, k), listed[k]) if k in listed else
             breakdown(unit_name(k, k in with_listed), units["rest_of_province"][k]) for k in keys]
    labels = []
    for parts in weights:
        held: dict[int, float] = {}
        for m, w in parts:
            code = geoids[m]
            k = index.get(code if code in listed else unit_of(code))
            if k is not None and w > 0:
                held[k] = held.get(k, 0) + w
        labels.append(sorted(held, key=lambda k: -held[k]) or None)
    return {"names": names, "labels": labels}


def above_spain(rates: dict[str, list], spain: dict[str, float]) -> list:
    """Per hex, the index in COMPARED of the type whose rate is the most times Spain's, or None where none is above
    Spain's (or the hex has no rate)."""
    keys = list(COMPARED)
    out = []
    for hex_rates in zip(*(rates[k] for k in keys)):
        ratios = [(r / spain[k], i) for i, (k, r) in enumerate(zip(keys, hex_rates)) if r is not None]
        best = max(ratios, default=None)
        out.append(best[1] if best and best[0] > 1 else None)
    return out


def lenses(crime: dict, padron: dict, municipalities: list[dict], geoids: list[str], weights: list) -> list[dict]:
    """The crime lens and the crime-above-Spain's-rate lens."""
    year = crime["year"]
    pops = {code: m["pop"][str(year)] for code, m in padron["municipalities"].items() if m["pop"].get(str(year))}
    units = crime_units(crime, pops, island_of(municipalities))
    names = {code: m["display"] for code, m in padron["municipalities"].items()}
    tooltip = unit_labels(units, names, geoids, weights)
    in_spain = {k: sum(c.get(k, 0) for c in crime["provinces"].values()) for k in [TOTAL, *TYPE_NAMES]}
    residents = sum(pops.values())
    spain = {k: v * PER / residents for k, v in in_spain.items()}

    def spread(key: str, digits: int) -> list:
        return _spread(weights, by_municipality(geoids, listed_or_rest(units, rate(key), units["unit_of"])), digits)

    n = len(units["municipalities"])
    how = tr(
        "Los {n} municipios de más de 20.000 habitantes que lista el balance tienen su propia tasa; cada uno de los "
        "demás, la del resto de su provincia (en Baleares y Canarias, de su isla): sus infracciones y sus residentes "
        "menos los de esos municipios.",
        "The {n} municipalities of more than 20,000 inhabitants the balance lists have their own rate; every other "
        "takes the rest of its province's (in the Balearic and Canary Islands, of its island's): its offences and "
        "residents minus those of the listed municipalities.").format(n=n)
    note = tr("Por residente: en los sitios turísticos (Benidorm, Marbella, Eivissa, Lloret de Mar…) los "
              "visitantes suman delitos pero no habitantes del Padrón. Son delitos conocidos por la policía, no "
              "todos los que hay.",
              "Per resident: in tourist places (Benidorm, Marbella, Ibiza, Lloret de Mar…) visitors add offences but "
              "no Padrón residents. These are offences known to the police, not all that happen.")
    source = tr(
        "Infracciones penales conocidas por la Policía Nacional, la Guardia Civil, las policías autonómicas y las "
        "locales que informan al Sistema Estadístico de Criminalidad, por denuncia o por actuación policial "
        "(Balance de Criminalidad del Ministerio del Interior, enero a diciembre de {year})",
        "Criminal offences known to the Policía Nacional, the Guardia Civil, the regional police forces and the "
        "local ones that report to the Sistema Estadístico de Criminalidad, by complaint or by the police's own "
        "action (Ministerio del Interior, Balance de Criminalidad, January to December {year})").format(year=str(year))
    categories = [{"id": k, "name": TYPE_NAMES[k].map(lambda s, _l: s[:1].upper() + s[1:]), "color": c}
                  for k, c in COMPARED.items()]
    return [
        {"id": "crime", "group": "hazards", "name": tr("Criminalidad", "Crime"), "icon": "l-crime", "emoji": "🚨",
         "unit": tr("infracciones penales conocidas por 1.000 habitantes",
                    "known criminal offences per 1,000 inhabitants"),
         "format": "float", "scale": "linear", "higher_is": "bad", "ramp": DISASTERS_RAMP,
         "source": "balance_criminalidad", "note": note,
         "description": tr(
             "{source}, por cada 1.000 habitantes del Padrón de {year}; en España, {spain} ({abroad} más se "
             "cometieron en el extranjero y no cuentan). {how} Pasa el ratón por un hexágono para ver sus tres tipos "
             "más frecuentes por 1.000 habitantes, sin el resto de la criminalidad convencional, que no es un tipo. "
             "{spread}",
             "{source}, per 1,000 Padrón inhabitants of {year}; Spain: {spain} ({abroad} more were committed abroad "
             "and are left out). {how} Hover a hex to see its three most frequent types per 1,000 inhabitants, "
             "without the rest of conventional crime, which is no type. {spread}",
         ).format(source=source, year=str(year), spain=Num(spain[TOTAL], 1), abroad=crime["abroad"][TOTAL], how=how,
                  spread=SPREAD),
         "values": spread(TOTAL, 1), **tooltip},
        {"id": "crime_type", "group": "hazards", "name": tr("Delito que más destaca", "Standout offence"),
         "icon": "l-crime-type", "emoji": "🔎",
         "unit": tr("tipo de delito más por encima de la tasa de España", "offence type furthest above Spain's rate"),
         "format": "category", "scale": "linear", "higher_is": "neutral", "categories": categories,
         "ramp": [c["color"] for c in categories], "domain": [0, len(categories) - 1],
         "null_label": tr("Ninguno por encima de España", "None above Spain's rate"),
         "source": "balance_criminalidad", "note": note,
         "description": tr(
             "El tipo de delito cuya tasa por habitante es más veces la de España, entre los que pasan de unos "
             "20.000 al año: {types}. Los homicidios, sus intentos y los secuestros, unos cientos, se dejan fuera "
             "para que un solo caso no decida un pueblo, y el resto de la criminalidad convencional no es un tipo. "
             "Un hexágono sin ningún tipo por encima de España queda sin color. Mide qué delito destaca, no "
             "cuánto hay: un sitio tranquilo puede destacar en ciberdelitos o en robos con fuerza con una tasa "
             "total baja. {source}. {how} {spread}",
             "The offence type whose rate per inhabitant is the most times Spain's, among those with more than about "
             "20,000 a year: {types}. Homicides, their attempts and kidnappings, a few hundred, are left out so that "
             "one case does not decide a town, and the rest of conventional crime is no type. A hex with no type "
             "above Spain's is left uncoloured. It measures which offence stands out, not how much there is: a "
             "quiet place can stand out in cybercrime or burglary with a low total rate. {source}. {how} {spread}",
         ).format(types=join(TYPE_NAMES[k] for k in COMPARED), source=source, how=how, spread=SPREAD),
         "values": above_spain({k: spread(k, 3) for k in COMPARED}, spain), **tooltip},
    ]


def join(texts) -> Text:
    """Texts joined with commas and a final 'y' / 'and'."""
    *head, last = list(texts)
    es = ", ".join(t["es"] for t in head) + " y " + last["es"]
    en = ", ".join(t["en"] for t in head) + " and " + last["en"]
    return tr(es, en)
