"""Spain's crime lenses, from the Ministerio del Interior's Balance de Criminalidad (sources/es/criminalidad.py).

* **Crime**: known criminal offences per 1,000 inhabitants (Padrón of the balance's year). The balance lists the
  municipalities over 20,000 inhabitants by its own reference padrón: those carry their own rate. Every other
  municipality takes the rest of its province, or of its island in the Balearic and Canary Islands (the unit's
  offences and residents minus those of its listed municipalities), as spain_daily's `listed_or_rest` does for INE's
  main cities. A hex takes the population-weighted mean of its municipalities' rates; the tooltip gives, for each
  listed municipality or rest the hex holds, its total, its three highest types and the rest.
* **Standout offence**: per listed municipality or rest, the offence type whose rate is the most times Spain's, among
  the types common enough to compare (`COMPARED`), where it is MIN_RATIO times Spain's or more and the unit has
  MIN_RESIDENTS residents or more. A hex takes the colour of the unit with most of its residents; its tooltip lists
  the crime lens's units (`labels_from`), each with its standout type, rate and ratio.
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
# counts in the total but is not a type to name.
TYPE_NAMES = {
    "homicide": tr("homicidios", "homicides"),
    "attempted_homicide": tr("intentos de homicidio", "attempted homicides"),
    "assault": tr("lesiones", "assault"), "kidnapping": tr("secuestros", "kidnapping"),
    "sexual": tr("delitos sexuales", "sexual offences"),
    "violent_robbery": tr("robos con violencia", "violent robbery"),
    "burglary": tr("robos con fuerza", "burglary"), "theft": tr("hurtos", "theft"),
    "vehicle_theft": tr("sustracciones de vehículos", "vehicle theft"),
    "drug_trafficking": tr("tráfico de drogas", "drug trafficking"),
    "online_fraud": tr("estafas informáticas", "online fraud"),
    "other_cyber": tr("otros ciberdelitos", "other cybercrime"),
}
# The types the second lens compares: those with about 20,000 known offences a year in Spain or more (0.44 per 1,000
# for sexual offences, the rarest), so a unit of MIN_RESIDENTS expects about nine or more of each. Homicides (376 in
# 2025), attempted homicides (1,413) and kidnappings (109) would let one or two cases decide a town.
COMPARED = {
    "theft": "#e0a83a", "online_fraud": "#3d8fbf", "burglary": "#c8553d", "violent_robbery": "#9b2442",
    "assault": "#e86a92", "vehicle_theft": "#7fb069", "drug_trafficking": "#9b5de5", "sexual": "#4a5bd4",
    "other_cyber": "#43aa8b",
}
# A unit takes a colour only with this many residents (the balance's own cut-off for listing a municipality) and a
# type this many times Spain's rate: below that, a colour would mean a few cases or a few percent. Our cut-offs.
MIN_RESIDENTS = 20000
MIN_RATIO = 1.25
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
    """'Benidorm: 92,3 por 1.000 hab.; hurtos 40,1, estafas informáticas 9,9, robos con fuerza 4,0, el resto 38,3': the
    total rate per 1,000 inhabitants, its three highest types and what the other types add up to."""
    top = sorted(TYPE_NAMES, key=lambda k: -counts.get(k, 0))[:TOOLTIP_TYPES]
    total = rate(TOTAL)(counts)
    rates = join_texts([TYPE_NAMES[k].map(lambda s, lang, k=k: f"{s} {num(rate(k)(counts), 1, lang)}") for k in top])
    rest = total - sum(rate(k)(counts) for k in top)
    return tr("{name}: {total} por 1.000 hab.; {rates}, el resto {rest}",
              "{name}: {total} per 1,000; {rates}, the rest {rest}").format(
        name=name, total=Num(total, 1), rates=rates, rest=Num(rest, 1))


def hex_units(units: dict, geoids: list[str], weights: list) -> dict:
    """`keys` (every listed municipality, then every rest of a unit) and per hex the indices in `keys` of those its
    municipalities are in (`labels`), the most populous first."""
    unit_of, listed = units["unit_of"], units["municipalities"]
    keys = [*sorted(listed), *sorted(units["rest_of_province"])]
    index = {k: i for i, k in enumerate(keys)}
    labels = []
    for parts in weights:
        held: dict[int, float] = {}
        for m, w in parts:
            code = geoids[m]
            k = index.get(code if code in listed else unit_of(code))
            if k is not None and w > 0:
                held[k] = held.get(k, 0) + w
        labels.append(sorted(held, key=lambda k: -held[k]) or None)
    return {"keys": keys, "labels": labels}


def named_counts(units: dict, municipalities: dict[str, str], keys: list[str]) -> list[tuple]:
    """(name, counts) of every key of hex_units: a listed municipality by its name, a rest by unit_name."""
    listed, rest = units["municipalities"], units["rest_of_province"]
    with_listed = {units["unit_of"](code) for code in listed}
    return [(municipalities.get(k, k), listed[k]) if k in listed else (unit_name(k, k in with_listed), rest[k])
            for k in keys]


def standout(counts: dict, spain: dict[str, float]) -> tuple[str, float] | None:
    """(type, times Spain's rate) of the COMPARED type whose rate is the most times Spain's; None without residents."""
    if not counts.get(POP):
        return None
    return max(((k, rate(k)(counts) / spain[k]) for k in COMPARED if spain.get(k)), key=lambda kr: kr[1], default=None)


def standout_index(counts: dict, spain: dict[str, float]) -> int | None:
    """The index in COMPARED of a unit's standout type, or None where the unit has fewer than MIN_RESIDENTS residents
    or no type reaches MIN_RATIO times Spain's rate."""
    best = standout(counts, spain)
    if counts.get(POP, 0) < MIN_RESIDENTS or not best or best[1] < MIN_RATIO:
        return None
    return list(COMPARED).index(best[0])


def standout_name(name, counts: dict, spain: dict[str, float]) -> Text:
    """'Vilagarcía de Arousa: tráfico de drogas 1,0 por 1.000, 2,17 veces España'; below MIN_RATIO, the type that comes
    closest; under MIN_RESIDENTS, the residents and why it is left uncoloured."""
    best = standout(counts, spain)
    if counts.get(POP, 0) < MIN_RESIDENTS or not best:
        line = tr("{pop} habitantes, pocos casos para comparar", "{pop} inhabitants, too few cases to compare").format(
            pop=counts.get(POP, 0))
    else:
        k, ratio = best
        line = tr("{type} {rate} por 1.000, {ratio} veces España", "{type} {rate} per 1,000, {ratio} times Spain's")
        if ratio < MIN_RATIO:
            line = tr("ninguno llega a {min} veces España; el que más, ", "none reaches {min} times Spain's; the "
                      "closest, ").format(min=Num(MIN_RATIO, 2)) + line
        line = line.format(type=TYPE_NAMES[k], rate=Num(rate(k)(counts), 1), ratio=Num(ratio, 2))
    return line.map(lambda s, lang: f"{pick(name, lang)}: {s}")


def above_spain(counts: list[dict], spain: dict[str, float], labels: list) -> list:
    """The standout lens's values from the units of hex_units (their `counts`) and its `labels`: per hex, the
    standout_index of the unit with most of its residents, the first one its tooltip lists."""
    index = [standout_index(c, spain) for c in counts]
    return [index[held[0]] if held else None for held in labels]


def lenses(crime: dict, padron: dict, municipalities: list[dict], geoids: list[str], weights: list) -> list[dict]:
    """The crime lens and the standout offence lens."""
    year = crime["year"]
    pops = {code: m["pop"][str(year)] for code, m in padron["municipalities"].items() if m["pop"].get(str(year))}
    units = crime_units(crime, pops, island_of(municipalities))
    hexes = hex_units(units, geoids, weights)
    named = named_counts(units, {code: m["display"] for code, m in padron["municipalities"].items()}, hexes["keys"])
    in_spain = {k: sum(c.get(k, 0) for c in crime["provinces"].values()) for k in [TOTAL, *TYPE_NAMES]}
    residents = sum(pops.values())
    spain = {k: v * PER / residents for k, v in in_spain.items()}

    def spread(key: str, digits: int) -> list:
        return _spread(weights, by_municipality(geoids, listed_or_rest(units, rate(key), units["unit_of"])), digits)

    how = tr(
        "Los {n} municipios que lista el balance (los de más de 20.000 habitantes según su padrón de referencia) "
        "tienen su propia tasa; Ceuta y Melilla salen como ciudades, con la de toda la ciudad. Cada uno de los demás "
        "municipios lleva la del resto de su provincia (en Baleares y Canarias, de su isla): sus infracciones y sus "
        "residentes menos los de los municipios de la lista.",
        "The {n} municipalities the balance lists (those over 20,000 inhabitants by its reference padrón) have their "
        "own rate; Ceuta and Melilla appear as cities, with the rate of the whole city. Every other municipality takes "
        "the rate of the rest of its province (in the Balearic and Canary Islands, of its island): its offences and "
        "residents minus those of the listed municipalities.").format(n=len(units["municipalities"]))
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
    # mid-sentence, a rest (the only Text among the names) starts in lower case: 'y el resto de Eivissa'
    small = sorted((name.map(lambda s, _l: s[:1].lower() + s[1:]) if isinstance(name, Text) else name
                    for name, counts in named if counts.get(POP, 0) < MIN_RESIDENTS), key=lambda n: pick(n, "es"))
    small = tr(" Por eso quedan sin color: {units}.", " Left uncoloured for that reason: {units}.").format(
        units=join(small)) if small else ""
    left_out = join(TYPE_NAMES[k].map(lambda s, lang, k=k: f"{s} ({num(in_spain[k], None, lang)})")
                    for k in ("homicide", "attempted_homicide", "kidnapping"))
    return [
        {"id": "crime", "group": "hazards", "name": tr("Criminalidad", "Crime"), "icon": "l-crime", "emoji": "🚨",
         "unit": tr("infracciones penales conocidas por 1.000 habitantes",
                    "known criminal offences per 1,000 inhabitants"),
         "format": "float", "scale": "linear", "higher_is": "bad", "ramp": DISASTERS_RAMP,
         "source": "balance_criminalidad", "note": note,
         "description": tr(
             "{source}, por cada 1.000 habitantes del Padrón de {year}; en España, {spain} ({abroad} más se "
             "cometieron en el extranjero y no cuentan). {how} Pasa el ratón por un hexágono para ver, de cada "
             "municipio de la lista o resto de provincia que toca, su tasa, sus tres tipos más frecuentes y lo que "
             "suma el resto, sobre todo el resto de la criminalidad convencional, que no es un tipo. {spread}",
             "{source}, per 1,000 Padrón inhabitants of {year}; Spain: {spain} ({abroad} more were committed abroad "
             "and are left out). {how} Hover a hex to see, for each listed municipality or rest of a province it "
             "touches, its rate, its three most frequent types and what the rest adds up to, mostly the rest of "
             "conventional crime, which is not a type. {spread}",
         ).format(source=source, year=str(year), spain=Num(spain[TOTAL], 1), abroad=crime["abroad"][TOTAL], how=how,
                  spread=SPREAD),
         "values": spread(TOTAL, 1), "names": [breakdown(n, c) for n, c in named], "labels": hexes["labels"]},
        {"id": "crime_type", "group": "hazards", "name": tr("Delito que más destaca", "Standout offence"),
         "icon": "l-crime-type", "emoji": "🔎",
         "unit": tr("tipo de delito más por encima de la tasa de España", "offence type furthest above Spain's rate"),
         "format": "category", "scale": "linear", "higher_is": "neutral", "categories": categories,
         "ramp": [c["color"] for c in categories], "domain": [0, len(categories) - 1],
         "null_label": tr("Ninguno destaca", "None stands out"),
         "source": "balance_criminalidad", "note": note,
         "description": tr(
             "De cada municipio de la lista o resto de provincia, el tipo de delito cuya tasa por habitante es más "
             "veces la de España, entre los que pasan de unos 20.000 al año: {types}. Solo se pinta si llega a "
             "{ratio} veces la tasa de España y la unidad tiene {min} habitantes o más (umbrales nuestros): con "
             "menos, el color lo decidirían unos pocos casos o unas décimas.{small} Fuera, porque uno o dos casos "
             "decidirían un pueblo: {left_out} en {year}; el resto de la criminalidad convencional no es un tipo. Un "
             "hexágono toma el color de la unidad con más residentes en él, la primera que lista el tooltip, que da "
             "de cada una su tipo, su tasa y cuántas veces es la de España. Mide qué delito destaca, no cuánto hay: "
             "un sitio tranquilo puede destacar en ciberdelitos o en robos con fuerza con una tasa total baja. "
             "{source}. {how}",
             "For each listed municipality or rest of a province, the offence type whose rate per inhabitant is the "
             "most times Spain's, among those with more than about 20,000 a year: {types}. It is painted only at "
             "{ratio} times Spain's rate or more and in units of {min} inhabitants or more (our cut-offs): below "
             "that, a few cases or a few percent would decide the colour.{small} Left out, as one or two cases would "
             "decide a town: {left_out} in {year}; the rest of conventional crime is not a type. A hex takes the "
             "colour of the unit with most of its residents, the first in the tooltip, which gives each unit's "
             "type, its rate and how many times Spain's it is. It measures which offence stands out, not how much "
             "there is: a quiet place can stand out in cybercrime or burglary with a low total rate. {source}. {how}",
         ).format(types=join(TYPE_NAMES[k] for k in COMPARED), ratio=Num(MIN_RATIO, 2), min=MIN_RESIDENTS,
                  small=small, left_out=left_out, year=str(year), source=source, how=how),
         "values": above_spain([c for _, c in named], spain, hexes["labels"]),
         "names": [standout_name(n, c, spain) for n, c in named], "labels_from": "crime"},
    ]


def join(texts) -> Text:
    """Texts (or strings) joined with commas and a final 'y' / 'and'; a single one as it is."""
    *head, last = list(texts)

    def one(lang: str, word: str) -> str:
        return ", ".join(pick(t, lang) for t in head) + f" {word} " + pick(last, lang) if head else pick(last, lang)
    return tr(one("es", "y"), one("en", "and"))
