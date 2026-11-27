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

* `home`: appraised value of a free-market dwelling per m² (Ministerio de Vivienda), by province: every municipality
  takes its province's value. The US lens is the median value of a whole dwelling, which no Spanish source gives by
  municipality (DECISIONS E30, E49).
"""

from __future__ import annotations

from ..core.lang import tr
from ..core.store import load_interim_payload
from .lenses import COUNTY_LENSES, _spread

REQUIRES = ["ine_adrh_indicadores", "ine_censo_nacimiento", "ine_censo_formacion", "ine_censo2021_indicadores",
            "mivau_valor_tasado"]
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
    """Relative poverty, mean age, born abroad, higher education, homeowners and home value, in the US lens order."""
    adrh = load_interim_payload("ine_adrh_indicadores")["data"]
    birth = load_interim_payload("ine_censo_nacimiento")["data"]
    school = load_interim_payload("ine_censo_formacion")["data"]
    census = load_interim_payload("ine_censo2021_indicadores")["data"]
    value = load_interim_payload("mivau_valor_tasado")["data"]
    tenure = census["municipalities"]
    adrh_year = adrh["years"]
    small = tr("Los municipios pequeños pueden no tener dato (secreto estadístico) y no cuentan en su hexágono.",
               "Small municipalities may have no figure (statistical confidentiality) and do not count in their hex.")
    return [
        municipal_lens(
            "poverty", adrh["poverty"], geoids, weights, 4, name=tr("Pobreza", "Poverty"), source="ine_adrh_indicadores",
            unit=tr("población bajo el 60 % de la mediana de renta", "population below 60% of the median income"),
            description=tr(
                "Proporción de residentes con ingresos por unidad de consumo por debajo del 60 % de la mediana "
                "nacional, el umbral de riesgo de pobreza de la UE (Atlas de Distribución de Renta de los Hogares del "
                "INE, {year}: renta de los registros tributarios, escala de la OCDE modificada). Es un umbral relativo a "
                "la renta de España, no la línea de pobreza fija del mapa de EE. UU. Ponderada por población en los "
                "hexágonos con varios municipios. {small}",
                "Share of residents whose income per consumption unit is below 60% of the national median, the EU "
                "at-risk-of-poverty threshold (INE Household Income Distribution Atlas, {year}: income from tax records, "
                "modified OECD scale). It is a threshold relative to Spain's income, not the US map's fixed poverty "
                "line. Population-weighted in hexes with several municipalities. {small}",
            ).format(year=str(adrh_year["poverty"]), small=small)),
        municipal_lens(
            "age", adrh["mean_age"], geoids, weights, 1, name=tr("Edad media", "Mean age"), source="ine_adrh_indicadores",
            unit=tr("años", "years"),
            description=tr(
                "Edad media de los residentes de los municipios de cada hexágono, ponderada por población (indicadores "
                "demográficos del Atlas de Distribución de Renta de los Hogares del INE, {year}, que salen del Censo "
                "anual de población). Es la media: el INE no publica la mediana de edad por municipio, que es lo que "
                "muestra el mapa de EE. UU.",
                "Mean age of the residents of each hex's municipalities, weighted by population (demographic indicators "
                "of the INE Household Income Distribution Atlas, {year}, drawn from the Annual Population Census). It "
                "is the mean: INE publishes no median age by municipality, which is what the US map shows.",
            ).format(year=str(adrh_year["mean_age"]))),
        municipal_lens(
            "foreign_born", {c: share(r, "abroad") for c, r in birth["municipalities"].items()}, geoids, weights, 4,
            name=tr("Nacidos en el extranjero", "Born abroad"), source="ine_censo_nacimiento",
            unit=tr("residentes nacidos fuera de España", "residents born outside Spain"),
            description=tr(
                "Proporción de residentes nacidos fuera de España (Censo anual de población del INE, tabla 65031, 1 de "
                "enero de {year}), ponderada por población en los hexágonos con varios municipios. Cuenta el lugar de "
                "nacimiento, no la nacionalidad: un español nacido en el extranjero cuenta; un extranjero nacido en "
                "España, no.",
                "Share of residents born outside Spain (INE Annual Population Census, table 65031, 1 January {year}), "
                "population-weighted in hexes with several municipalities. It counts the place of birth, not "
                "nationality: a Spaniard born abroad counts; a foreigner born in Spain does not.",
            ).format(year=str(birth["year"]))),
        municipal_lens(
            "bachelors", {c: share(r, "higher") for c, r in school["municipalities"].items()}, geoids, weights, 4,
            name=tr("Estudios superiores", "Higher education"), source="ine_censo_formacion",
            unit=tr("población de 15 años o más con estudios superiores", "population aged 15+ with higher education"),
            description=tr(
                "Proporción de residentes de 15 años o más cuyo nivel de estudios terminado más alto es la educación "
                "superior: estudios universitarios y ciclos formativos de grado superior (Censo anual de población del "
                "INE, tabla 66592, 1 de enero de {year}), ponderada por población. El mapa de EE. UU. cuenta a los "
                "adultos de 25 años o más con un título universitario; el INE da la edad solo en los municipios de 500 "
                "habitantes o más, así que aquí se cuenta desde los 15 años y la proporción sale más baja.",
                "Share of residents aged 15 or over whose highest completed level of education is higher education: "
                "university degrees and higher vocational training (INE Annual Population Census, table 66592, 1 "
                "January {year}), weighted by population. The US map counts adults aged 25 or over with a bachelor's "
                "degree; INE gives age only for municipalities of 500 residents or more, so here everyone from 15 is "
                "counted and the share comes out lower.",
            ).format(year=str(school["year"]))),
        municipal_lens(
            "homeownership", {c: tenure_share(r) for c, r in tenure.items()}, geoids, weights, 4,
            name=tr("Vivienda en propiedad", "Homeowners"), source="ine_censo2021_indicadores",
            unit=tr("viviendas principales en propiedad", "main dwellings owned"),
            description=tr(
                "Proporción de las viviendas principales (residencia habitual de un hogar) que están en propiedad, "
                "frente al alquiler y a otras formas de tenencia como la cesión gratuita (Censo de Población y "
                "Viviendas del INE, 1 de enero de {year}: indicadores por sección censal sumados por municipio), "
                "ponderada por población. Los municipios más pequeños no tienen dato: el INE no publica sus secciones "
                "(secreto estadístico).",
                "Share of main dwellings (a household's usual residence) that are owned, against renting and other "
                "forms of tenure such as rent-free use (INE Population and Housing Census, 1 January {year}: "
                "indicators by census section added up by municipality), weighted by population. The smallest "
                "municipalities have no figure: INE does not publish their sections (statistical confidentiality).",
            ).format(year=str(census["year"]))),
        {**municipal_lens(
            "home", {g: value["provinces"].get(g[:2]) for g in geoids}, geoids, weights, 0,
            name=tr("Valor de la vivienda", "Home value"), source="mivau_valor_tasado",
            unit=tr("valor tasado de la vivienda libre, €/m²", "appraised value of free-market housing, €/m²"),
            description=tr(
                "Valor medio por m² construido de la vivienda libre según las tasaciones del {quarter}.º trimestre de "
                "{year} (estadística de valor tasado del Ministerio de Vivienda; en España, {spain} €/m²). El dato es "
                "de la provincia, porque la serie por municipio no se puede descargar: un hexágono lleva el de su "
                "provincia, o la media ponderada por población si toca dos. Es precio por m², no el valor mediano de "
                "una vivienda entera del mapa de EE. UU.",
                "Mean value per built m² of free-market housing from the appraisals of Q{quarter} {year} (appraised "
                "value statistic of the Ministerio de Vivienda; Spain: {spain} €/m²). The figure is the province's, "
                "because the series by municipality cannot be downloaded: a hex carries its province's, or the "
                "population-weighted mean if it touches two. It is a price per m², not the US map's median value of a "
                "whole home.",
            ).format(quarter=str(value["quarter"]), year=str(value["year"]), spain=round(value["spain"]))),
         "format": "eur"},
    ]
