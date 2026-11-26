"""Spain's people and prosperity lenses under the US lens ids, so the map gives them the US icon, group, ramp and format.

Each lens is a municipal figure spread over the hexes like the income lens: the population-weighted mean of the
municipalities in each hex (lenses.spread_population weights), null where none of them has a figure.

* `age`: mean age (ADRH demographic indicators, from the Annual Population Census). INE publishes no median age by
  municipality, so it is the mean, named as such.
* `foreign_born`: residents born abroad ÷ residents (Annual Population Census, table 65031).
* `bachelors`: residents aged 15+ with higher education ÷ residents aged 15+ (Annual Population Census, table 66592);
  INE gives the age breakdown only for municipalities of 500 residents or more, so the US 25+ universe is not used.
* `homeownership`: owned ÷ all main dwellings (2021 Population and Housing Census, indicators by census section).
* `poverty`: share of residents below 60 % of the national median income per consumption unit (ADRH, table 30829),
  the EU at-risk-of-poverty threshold; not the US fixed poverty line.

The US `home` lens (median value of a dwelling) has no Spanish counterpart: see DECISIONS E30.
"""

from __future__ import annotations

from ..core.store import load_interim_payload
from .lenses import COUNTY_LENSES, _spread

REQUIRES = ["ine_adrh_indicadores", "ine_censo_nacimiento", "ine_censo_formacion", "ine_censo2021_indicadores"]
SHARED = ("group", "icon", "emoji", "format", "scale", "higher_is", "ramp")  # what each lens takes from the US one


def share(rec: dict | None, part: str, whole: str = "total") -> float | None:
    """rec[part] ÷ rec[whole], or None when either is unknown or the whole is 0."""
    if not rec or rec.get(part) is None or not rec.get(whole):
        return None
    return rec[part] / rec[whole]


def tenure_share(rec: dict | None) -> float | None:
    """Owned ÷ all main dwellings (owned, rented, other)."""
    return share(rec and {**rec, "total": sum(rec.values())}, "owned")


def municipal_lens(lens_id: str, by_code: dict[str, float | None], geoids: list[str], weights: list, digits: int,
                   **texts) -> dict:
    """A lens with the US lens `lens_id`'s look and Spain's `texts` (name, unit, source, description): the municipal
    values `by_code` (INE code → value) averaged over each hex's municipalities, weighted by population."""
    meta = COUNTY_LENSES[lens_id][1]
    return {"id": lens_id, **{k: meta[k] for k in SHARED}, **texts,
            "values": _spread(weights, [by_code.get(g) for g in geoids], digits)}


def people_lenses(geoids: list[str], weights: list) -> list[dict]:
    """Mean age, born abroad, higher education, homeowners and relative poverty, in the US lens order."""
    adrh = load_interim_payload("ine_adrh_indicadores")["data"]
    birth = load_interim_payload("ine_censo_nacimiento")["data"]
    school = load_interim_payload("ine_censo_formacion")["data"]
    census = load_interim_payload("ine_censo2021_indicadores")["data"]
    tenure = census["municipalities"]
    adrh_year = adrh["years"]
    small = "Los municipios pequeños pueden no tener dato (secreto estadístico) y no cuentan en su hexágono."
    return [
        municipal_lens(
            "poverty", adrh["poverty"], geoids, weights, 4, name="Pobreza", source="ine_adrh_indicadores",
            unit="población bajo el 60 % de la mediana de renta",
            description="Proporción de residentes con ingresos por unidad de consumo por debajo del 60 % de la mediana "
            "nacional, el umbral de riesgo de pobreza de la UE (Atlas de Distribución de Renta de los Hogares del INE, "
            f"{adrh_year['poverty']}: renta de los registros tributarios, escala de la OCDE modificada). Es un umbral "
            "relativo a la renta de España, no la línea de pobreza fija del mapa de EE. UU. Ponderada por población en "
            f"los hexágonos con varios municipios. {small}"),
        municipal_lens(
            "age", adrh["mean_age"], geoids, weights, 1, name="Edad media", source="ine_adrh_indicadores", unit="años",
            description="Edad media de los residentes de los municipios de cada hexágono, ponderada por población "
            f"(indicadores demográficos del Atlas de Distribución de Renta de los Hogares del INE, {adrh_year['mean_age']}, "
            "que salen del Censo anual de población). Es la media: el INE no publica la mediana de edad por municipio, "
            "que es lo que muestra el mapa de EE. UU."),
        municipal_lens(
            "foreign_born", {c: share(r, "abroad") for c, r in birth["municipalities"].items()}, geoids, weights, 4,
            name="Nacidos en el extranjero", source="ine_censo_nacimiento", unit="residentes nacidos fuera de España",
            description="Proporción de residentes nacidos fuera de España (Censo anual de población del INE, tabla "
            f"65031, 1 de enero de {birth['year']}), ponderada por población en los hexágonos con varios municipios. "
            "Cuenta el lugar de nacimiento, no la nacionalidad: un español nacido en el extranjero cuenta; un "
            "extranjero nacido en España, no."),
        municipal_lens(
            "bachelors", {c: share(r, "higher") for c, r in school["municipalities"].items()}, geoids, weights, 4,
            name="Estudios superiores", source="ine_censo_formacion",
            unit="población de 15 años o más con estudios superiores",
            description="Proporción de residentes de 15 años o más cuyo nivel de estudios terminado más alto es la "
            "educación superior: estudios universitarios y ciclos formativos de grado superior (Censo anual de "
            f"población del INE, tabla 66592, 1 de enero de {school['year']}), ponderada por población. El mapa de "
            "EE. UU. cuenta a los adultos de 25 años o más con un título universitario; el INE da la edad solo en los "
            "municipios de 500 habitantes o más, así que aquí se cuenta desde los 15 años y la proporción sale más baja."),
        municipal_lens(
            "homeownership", {c: tenure_share(r) for c, r in tenure.items()}, geoids, weights, 4,
            name="Vivienda en propiedad", source="ine_censo2021_indicadores", unit="viviendas principales en propiedad",
            description="Proporción de las viviendas principales (residencia habitual de un hogar) que están en "
            "propiedad, frente al alquiler y a otras formas de tenencia como la cesión gratuita (Censo de Población y "
            f"Viviendas del INE, 1 de enero de {census['year']}: indicadores por sección censal sumados "
            "por municipio), ponderada por población. Los municipios más pequeños no tienen dato: el INE no publica sus "
            "secciones (secreto estadístico)."),
    ]
