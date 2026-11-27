"""Spanish texts for the tables Spain shares with the US builders.

The US builders' constants (yield labels, lens groups, the land lenses, the world.json tables, badge texts, rail
tiers) stay in English, since the US output must not change. Spain's builders take these Spanish versions instead;
Spain-only catalogs (spain.py, spain_districts.py, spain_wonders.py, spain_infrastructure.py) are written in Spanish
where they are defined. The Almanac's source entries come from pipeline/sources/es in English and are given in
Spanish here (`source`), with their vintages (`vintage`).
"""

from __future__ import annotations

import re

from ..core.lang import Text, num, pct, tr  # noqa: F401  (num and pct re-exported for the builders: Spanish by default)

# Spain's site is in Spanish and English (core/lang.py): every text here is a Text, the English written for Spain.
YIELD_LABELS = {"food": tr("Comida", "Food"), "production": tr("Producción", "Production"), "gold": tr("Oro", "Gold"),
                "science": tr("Ciencia", "Science"), "culture": tr("Cultura", "Culture")}

LENS_GROUPS = {
    "people": tr("Población", "People"), "prosperity": tr("Prosperidad", "Prosperity"),
    "knowledge": tr("Conocimiento", "Knowledge"), "life": tr("Vida diaria", "Daily life"), "faith": tr("Fe", "Faith"),
    "hazards": tr("Riesgos", "Hazards"), "land": tr("Territorio", "Land"),
}
LAND_UNIT = tr("proporción del suelo", "share of land")
LAND_LENSES = {
    "forest": {"name": tr("Bosque", "Forest"), "description": tr(
        "Proporción de la tierra del hexágono cubierta de bosque caducifolio, de coníferas o mixto (CORINE 311–313).",
        "Share of the hex's land covered by broadleaved, coniferous or mixed forest (CORINE 311–313).")},
    "farmland": {"name": tr("Tierra agraria", "Farmland"), "description": tr(
        "Proporción de la tierra del hexágono con cultivos, prados o dehesas (CORINE 2xx, cruzadas con las clases 81 y "
        "82 de NLCD).",
        "Share of the hex's land in crops, meadows or dehesas (CORINE 2xx, matched to NLCD classes 81 and 82).")},
    "developed": {"name": tr("Urbanizado", "Built-up"), "description": tr(
        "Proporción de la tierra del hexágono urbanizada: tejido urbano, zonas industriales y comerciales, redes de "
        "transporte, puertos, aeropuertos y obras (CORINE 111, 112, 121–124 y 133; las zonas verdes y deportivas urbanas "
        "no cuentan).",
        "Share of the hex's land that is built up: urban fabric, industrial and commercial areas, transport networks, "
        "ports, airports and construction sites (CORINE 111, 112, 121–124 and 133; urban green and sports areas are not "
        "counted).")},
}
DOMAIN_NOTE = tr(" Los colores abarcan del percentil 2 al 98 de los hexágonos; los valores de fuera se pintan con el "
                 "color del extremo.",
                 " Colours span the 2nd–98th percentile of hexes; values beyond are drawn at the end colours.")

# world.json tables (world.py: names and rules by row id; {hills}, {mountains} and {urban} are the country's thresholds).
WORLD = {
    "water": {
        0: {"name": tr("Tierra", "Land"), "rule": tr(
            "Al menos 4 de los 7 puntos de muestra del hexágono (el centro y 6 más) caen en un municipio del SIANE o en un "
            "país de Natural Earth, salvo que el centro sea mar y la media de ETOPO1 esté al nivel del mar o por debajo, o "
            "lo esté al menos la mitad de sus muestras de ETOPO1 (las rías y los estuarios siguen siendo agua).",
            "At least 4 of the hex's 7 sample points (the centre and 6 more) fall in a SIANE municipality or a Natural "
            "Earth country, unless the centre is sea and the ETOPO1 mean is at or below sea level, or at least half its "
            "ETOPO1 samples are (rías and estuaries stay water).")},
        1: {"name": tr("Océano", "Ocean"), "rule": tr("Mar de más de 200 m de profundidad y sin tierra al lado.",
                                                       "Sea deeper than 200 m and not next to land.")},
        2: {"name": tr("Costa", "Coast"), "rule": tr(
            "Mar junto a un hexágono de tierra, o de menos de 200 m de profundidad (media de ETOPO1).",
            "Sea next to a land hex, or shallower than 200 m (ETOPO1 mean).")},
        3: {"name": tr("Lago", "Lake"), "rule": tr(
            "Hexágono de agua (la mayoría de sus 7 puntos fuera de tierra) con más puntos de lago de Natural Earth 1:10m "
            "que de mar, o por encima del nivel del mar.",
            "Water hex (most of its 7 sample points off land) with more Natural Earth 1:10m lake points than sea points, "
            "or above sea level.")},
    },
    "relief": {
        0: {"name": tr("Llano", "Flat"), "rule": tr("Desviación típica de la altitud dentro del hexágono menor de {hills} m.",
                                                     "Elevation standard deviation inside the hex under {hills} m.")},
        1: {"name": tr("Colinas", "Hills"), "rule": tr("Desviación típica de la altitud de {hills} m o más.",
                                                        "Elevation standard deviation of {hills} m or more.")},
        2: {"name": tr("Montañas", "Mountains"), "rule": tr(
            "Desviación típica de la altitud de {mountains} m o más, o altitud media de 2300 m o más.",
            "Elevation standard deviation of {mountains} m or more, or mean elevation of 2,300 m or more.")},
        3: {"name": tr("Cumbres", "Peaks"), "rule": tr("Altitud media de 2700 m o más (alta montaña).",
                                                        "Mean elevation of 2,700 m or more (high mountains).")},
    },
    "cover": {
        0: {"name": tr("Ninguna", "None"), "rule": tr("Agua, tierra extranjera o ningún píxel de tierra de CORINE.",
                                                       "Water, foreign land, or no CORINE land pixels.")},
        1: {"name": tr("Bosque caducifolio", "Broadleaved forest"), "rule": tr(
            "El bosque (NLCD 41+42+43) es el grupo mayor y el caducifolio (41), su tipo principal.",
            "Forest (NLCD 41+42+43) is the largest group and broadleaved (41) its largest type.")},
        2: {"name": tr("Bosque de coníferas", "Conifer forest"), "rule": tr(
            "El bosque es el grupo mayor y el perennifolio (42), su tipo principal.",
            "Forest is the largest group and evergreen (42) its largest type.")},
        3: {"name": tr("Bosque mixto", "Mixed forest"), "rule": tr(
            "El bosque es el grupo mayor y el mixto (43), su tipo principal.",
            "Forest is the largest group and mixed (43) its largest type.")},
        4: {"name": tr("Matorral y desierto", "Scrub & desert"), "rule": tr(
            "El matorral (52) es el grupo mayor: maquia, garriga, landas y zonas semiáridas.",
            "Scrub (52) is the largest group: maquis, garrigue, heathland and semi-arid land.")},
        5: {"name": tr("Pastizal", "Grassland"), "rule": tr(
            "El pastizal (71) más los espacios abiertos urbanos (21: parques, zonas deportivas) es el grupo mayor.",
            "Grassland (71) plus urban open space (21: parks, sports grounds) is the largest group.")},
        6: {"name": tr("Pastos", "Pasture"), "rule": tr("Los prados y pastos (81) son el grupo mayor.",
                                                         "Meadows and pasture (81) are the largest group.")},
        7: {"name": tr("Cultivos", "Cropland"), "rule": tr("Los cultivos (82) son el grupo mayor.",
                                                            "Crops (82) are the largest group.")},
        8: {"name": tr("Humedal", "Wetland"), "rule": tr(
            "Los humedales leñosos (90) y herbáceos (95) juntos son el grupo mayor.",
            "Woody (90) and herbaceous (95) wetlands together are the largest group.")},
        9: {"name": tr("Urbano", "Urban"), "rule": tr(
            "Lo urbanizado de intensidad baja, media o alta (22+23+24) ocupa el {urban} % o más de la tierra del hexágono, "
            "haya lo que haya además.",
            "Built-up land of low, medium or high intensity (22+23+24) covers {urban}% or more of the hex's land, whatever "
            "else is there.")},
        10: {"name": tr("Suelo desnudo", "Barren"), "rule": tr(
            "El suelo desnudo (31: roca, arena, salinas) es el grupo mayor.",
            "Bare ground (31: rock, sand, salt pans) is the largest group.")},
        11: {"name": tr("Hielo y nieve", "Ice & snow"), "rule": tr(
            "El hielo y la nieve perpetuos (12) son el grupo mayor.", "Perennial ice and snow (12) are the largest group.")},
    },
    "notes": {
        "water": tr(
            "Los límites municipales del SIANE 1:3M y los de países y lagos de Natural Earth 1:10m no encajan del todo. Un "
            "hexágono de mar cuya media de ETOPO1 está sobre el nivel del mar (y con menos de la mitad de sus muestras por "
            "debajo) pasa a tierra si al menos 4 de sus 6 vecinos son tierra, o si toca a la vez tierra española y "
            "extranjera; toma el dueño mayoritario de sus vecinos. La altitud de un hexágono de mar es la media de sus "
            "muestras de ETOPO1 bajo el nivel del mar (su profundidad). Canarias va en un recuadro al suroeste de la "
            "península; sus hexágonos conservan su altitud y su cubierta del suelo reales.",
            "The SIANE 1:3M municipal boundaries and the Natural Earth 1:10m country and lake outlines do not fit exactly. "
            "A sea hex whose ETOPO1 mean is above sea level (with fewer than half its samples below it) becomes land if at "
            "least 4 of its 6 neighbours are land, or if it touches both Spanish and foreign land; it takes the owner most "
            "of its neighbours have. A sea hex's elevation is the mean of its ETOPO1 samples below sea level (its depth). "
            "The Canary Islands are drawn in a box south-west of the peninsula; their hexes keep their real elevation and "
            "land cover."),
        "relief": tr(
            "Sale de las muestras de ETOPO1 (1 minuto de arco, unos 1,85 km de separación, unas 25 por hexágono de 10 km) "
            "con altitud de -100 m o más, para que bahías y fondo marino no cuenten; si ninguna llega, se usan todas. Los "
            "hexágonos de agua son siempre llanos. Los umbrales de rugosidad son más bajos que los del mapa de EE. UU. "
            "(85 m y 260 m en hexágonos de 25 km) porque un hexágono más pequeño abarca menos relieve: se fijaron para que "
            "España tenga la misma proporción de tierra llana, de colinas y de montaña que con la regla de EE. UU. en "
            "hexágonos de 25 km.",
            "From the ETOPO1 samples (1 arc-minute, about 1.85 km apart, some 25 per 10 km hex) at -100 m or higher, so "
            "that bays and sea floor do not count; if none is, all are used. Water hexes are always flat. The roughness "
            "thresholds are lower than the US map's (85 m and 260 m on 25 km hexes) because a smaller hex spans less "
            "relief: they were set so that Spain has the same shares of flat land, hills and mountains as the US rule "
            "gives it on 25 km hexes."),
        "cover": tr(
            "Sale de CORINE Land Cover 2018 (Copernicus), muestreado en una retícula dentro de cada hexágono español. Las "
            "clases de CORINE se cruzan con los grupos de estilo NLCD de abajo (la tabla de cruce está en la entrada de "
            "CORINE del Almanaque); el agua (5xx) y los píxeles sin datos se descartan, las proporciones son de los puntos "
            "de tierra restantes y el umbral urbano se aplica a la proporción urbanizada redondeada (CORINE 111, 112, "
            "121–124 y 133). Los hexágonos extranjeros (Portugal, Francia, Andorra, Marruecos) tienen cubierta 0 (ninguna).",
            "From CORINE Land Cover 2018 (Copernicus), sampled on a grid inside each Spanish hex. The CORINE classes are "
            "matched to the NLCD-style groups below (the matching table is in CORINE's Almanac entry); water (5xx) and "
            "no-data pixels are dropped, the shares are of the remaining land points, and the urban threshold applies to "
            "the rounded built-up share (CORINE 111, 112, 121–124 and 133). Foreign hexes (Portugal, France, Andorra, "
            "Morocco) have cover 0 (none)."),
    },
}

RAIL_TIERS = {"main": tr("Línea principal", "Main line"), "secondary": tr("Línea secundaria", "Secondary line")}
HUBS = {"L": tr("Hub grande", "Large hub"), "M": tr("Hub mediano", "Medium hub"), "S": tr("Hub pequeño", "Small hub"),
        "N": tr("Sin categoría de hub", "No hub class")}

# districts.badge_for: the city-type label of a capital and the badge's sentence, by language ({lq} is already a number
# in that language). The English is the US builder's (districts.BADGE_TEXT).
BADGE_TEXT = {"es": {"capital": "Capital", "seat": "Sede de gobierno",
                     "share": "{name}: {ge}{lq} veces la cuota nacional de empleo", "decimal": ","},
              "en": {"capital": "Capital city", "seat": "Seat of government",
                     "share": "{name}: {ge}{lq}× the national share of jobs", "decimal": "."}}

MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
          "diciembre"]
_EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
              "November", "December"]
_DATE = re.compile(r"\b(\d{1,2}) (" + "|".join(_EN_MONTHS) + r") (\d{4})\b")
_VINTAGE_WORDS = [("(population ", "(población "), ("1 arc-minute", "1 minuto de arco"), (", edition ", ", edición "),
                  (" (final)", " (datos definitivos)"), ("(2017 areas)", "(zonas de 2017)"), ("; visitors ", "; visitantes "),
                  (", students ", ", matriculados "), ("(Canary Islands)", "(Canarias)")]


# The few vintages a Spanish source writes in Spanish, and their English.
_ES_DATE = re.compile(r"\b(?:(\d{1,2}) de )?(" + "|".join(MONTHS) + r") de (\d{4})\b")
_ES_QUARTER = re.compile(r"\b(\d)\.º trimestre de (\d{4})\b")
_VINTAGE_WORDS_ES = [("(zonas de 2017)", "(2017 areas)"), ("pliegos de condiciones", "product specifications"),
                     ("Cobertura de banda ancha", "Broadband coverage"), ("viviendas turísticas", "tourist dwellings"),
                     ("valor tasado", "appraised value")]


def vintage(text: str | None) -> Text | str | None:
    """A source vintage in both languages. Most sources write it in English: the Spanish translates its dates ('1
    January 2025' → '1 de enero de 2025') and its few English words. A vintage written in Spanish gets its English the
    other way ('junio de 2025' → 'June 2025'). Names of statistics stay as their publisher writes them. An empty
    vintage stays as it is."""
    if not text:
        return text
    es = _DATE.sub(lambda m: f"{m.group(1)} de {MONTHS[_EN_MONTHS.index(m.group(2))]} de {m.group(3)}", text)
    for en_word, es_word in _VINTAGE_WORDS:
        es = es.replace(en_word, es_word)
    en = _ES_DATE.sub(lambda m: " ".join(filter(None, [m.group(1), _EN_MONTHS[MONTHS.index(m.group(2))], m.group(3)])), text)
    en = _ES_QUARTER.sub(lambda m: f"Q{m.group(1)} {m.group(2)}", en)
    for es_word, en_word in _VINTAGE_WORDS_ES:
        en = en.replace(es_word, en_word)
    return tr(es, en)


_INE_LICENCE = ("CC BY 4.0 (aviso legal del INE): reutilización comercial y no comercial citando la fuente como "
                "«Elaboración propia con datos del INE»; el INE no avala este mapa")
_REUSE = "Información del sector público, reutilizable citando la fuente (Ley 37/2007)"
_AEMET = ("Nota legal de AEMET: reutilización permitida citando a AEMET como autora (Ley 37/2007, modificada por la "
          "Ley 18/2015); AEMET no avala este mapa")
_PINNED = "Los ficheros están fijados en la versión v5.1.2 de natural-earth-vector."
# The Almanac entry of each Spanish source (sources.json): the fields in Spanish, by source id.
SOURCES = {
    "audes": {
        "title": "Atlas Digital de las Áreas Urbanas: grandes áreas urbanas y sus municipios (2025)",
        "license": _REUSE,
        "description": "Las 86 grandes áreas urbanas (más de 50.000 habitantes) y los municipios que forman cada una, tal "
        "como las define el ministerio. Son las ciudades del mapa, como las áreas metropolitanas del mapa de EE. UU.: la "
        "población, el empleo y la huella de una ciudad suman los de sus municipios.",
        "used_for": ["Ciudades (áreas urbanas) y sus municipios"],
    },
    "corine": {
        "title": "CORINE Land Cover 2018 (a través del WMS de ocupación del suelo de la IDEE)",
        "publisher": "Servicio de Vigilancia Terrestre de Copernicus (AEMA); servido por el Instituto Geográfico Nacional (IDEE)",
        "license": "CC BY 4.0 (scne.es) para el servicio de la IDEE; CORINE Land Cover son datos de Copernicus con su "
        "política de datos libres, completos y abiertos",
        "description": "La cubierta del suelo en las 44 clases de CORINE para España, leída del mapa INSPIRE de ocupación "
        "del suelo de la IDEE (EPSG:3035, píxeles de 500 m, el tamaño de la unidad mínima de 25 ha de CORINE) por los "
        "colores exactos de la leyenda estándar. Cada clase se cruza con una clase NLCD (urbano 111/112/12x → "
        "urbanizado, tierras de labor y cultivos permanentes → cultivos, 231 prados y 244 dehesas → pastos, 31x bosques, "
        "321 pastizal, 32x y 333 matorral, 33x desnudo → suelo desnudo, 4xx humedales, 5xx agua), para que el mapa use "
        "las mismas reglas de cubierta en todos los países.",
        "used_for": ["Cubierta del suelo de los hexágonos (biomas)", "Proporciones de bosque, cultivos y suelo urbanizado"],
    },
    "etopo_es": {
        "title": "Modelo global de relieve ETOPO1 (España, resolución completa)",
        "publisher": "NOAA National Centers for Environmental Information (a través de ERDDAP)",
        "license": "Dominio público (obra del Gobierno de EE. UU.)",
        "description": "Altitud del terreno y profundidad del mar cada minuto de arco (unos 1,85 km), unas 25 muestras por "
        "hexágono de 10 km. El relieve de cada hexágono (llano, colinas, montañas, cumbres) sale de la media y de la "
        "rugosidad de sus muestras de tierra.",
        "used_for": ["Relieve (colinas, montañas)", "Sombreado del relieve", "Profundidad del mar"],
    },
    "noaa_solar": {
        "title": "Calculadora solar de la NOAA: ecuaciones de posición del Sol (Solar Calculation Details)",
        "publisher": "NOAA Global Monitoring Laboratory",
        "license": "Dominio público (obra del Gobierno de EE. UU.)",
        "description": "Las ecuaciones con que la calculadora solar de la NOAA halla la declinación del Sol y la ecuación "
        "del tiempo, de Jean Meeus, Astronomical Algorithms; la salida y la puesta, con el centro del Sol 0,833° bajo un "
        "horizonte a nivel del mar. La NOAA las da como exactas, en teoría, a un minuto entre ±72° de latitud; las horas "
        "observadas varían con la atmósfera. El mapa las calcula en el navegador para el centro de cada hexágono.",
        "used_for": ["Lente Sol y reloj (salida, puesta, mediodía solar, horas de luz)"],
    },
    "ine_adrh": {
        "title": "Atlas de Distribución de Renta de los Hogares (ADRH): indicadores de renta media y mediana, tabla 30824",
        "license": _INE_LICENCE,
        "description": "Renta neta de los registros tributarios de la Agencia Tributaria y de las haciendas forales, "
        "cruzados con el Padrón, para cada municipio (y sus distritos y secciones censales, que aquí no se usan). El "
        "mapa toma, del último año que publica el INE, la renta neta media por persona de cada municipio para la lente "
        "de renta y la renta neta media por hogar para la renta de los hogares de áreas urbanas, provincias y España (el "
        "INE no publica la mediana por hogar de los municipios). En un grupo de municipios, la renta por hogar es la "
        "renta total entre el total de hogares: cada municipio pesa por sus hogares, que son su población (Padrón del "
        "mismo año) por la renta por persona entre la renta por hogar. Pueden faltar municipios pequeños (secreto "
        "estadístico): se quedan sin datos y no cuentan en los grupos.",
        "used_for": ["Lente de renta", "Renta de los hogares de áreas urbanas, provincias y España", "Alquiler ÷ renta"],
    },
    "ine_censo_actividad": {
        "title": "Censo anual de población: población de 16 años o más por relación con la actividad, tabla 66594",
        "license": _INE_LICENCE,
        "description": "Ocupados, parados e inactivos de 16 años o más de España, cada provincia y cada municipio (y sus "
        "secciones censales, que aquí no se usan), del Censo anual de población, que el INE elabora con registros "
        "administrativos (Padrón y fuentes laborales, tributarias y educativas). La tasa de paro del mapa es parados ÷ "
        "(ocupados + parados), contados donde viven, como la de la ACS del mapa de EE. UU.; en un área urbana es la "
        "suma de sus parados entre la suma de su población activa. No es la tasa de la EPA (una encuesta) ni el paro "
        "registrado del SEPE, que cuenta demandantes de empleo y no tiene denominador. El INE no publica los municipios "
        "de menos de unos 75 habitantes, que no cuentan en su área.",
        "used_for": ["Tasa de paro de áreas urbanas, provincias y España"],
    },
    "ine_adrh_indicadores": {
        "title": "Atlas de Distribución de Renta de los Hogares (ADRH): indicadores demográficos (tabla 30832) y umbrales "
        "relativos de renta (tabla 30829)",
        "license": _INE_LICENCE,
        "description": "De cada municipio, la edad media de sus residentes (tabla 30832, que el ADRH toma del Censo anual "
        "de población y publica para todos los municipios) y la proporción de residentes con ingresos por unidad de "
        "consumo (escala de la OCDE modificada) por debajo del 60 % de la mediana nacional (tabla 30829, ambos sexos; "
        "desde el ADRH 2023 la mediana es la de toda España, territorios forales incluidos). A los municipios pequeños "
        "les puede faltar el indicador de renta (secreto estadístico): se quedan sin datos.",
        "used_for": ["Lente de edad media", "Lente de pobreza"],
    },
    "ine_censo_nacimiento": {
        "title": "Censo anual de población: población por sexo y lugar de nacimiento (España/extranjero), tabla 65031",
        "license": _INE_LICENCE,
        "description": "Residentes nacidos en España y en el extranjero de España, cada provincia y cada municipio (y sus "
        "secciones censales, que aquí no se usan), del Censo anual de población, que el INE elabora con el Padrón y "
        "otros registros. Es el lugar de nacimiento, no la nacionalidad: cuentan los españoles nacidos fuera y no los "
        "extranjeros nacidos en España.",
        "used_for": ["Lente de nacidos en el extranjero"],
    },
    "ine_censo_formacion": {
        "title": "Censo anual de población: población de 15 años o más por sexo y nivel de estudios (agrupado), tabla 66592",
        "license": _INE_LICENCE,
        "description": "Residentes de 15 años o más por el nivel de estudios más alto terminado (primaria o inferior, "
        "primera etapa de secundaria, segunda etapa de secundaria y postsecundaria no superior, educación superior) de "
        "España, cada provincia y cada municipio (y sus secciones censales, que aquí no se usan), del Censo anual de "
        "población. La educación superior incluye los ciclos formativos de grado superior además de los estudios "
        "universitarios. El INE solo cruza la edad en los municipios de 500 habitantes o más, así que el mapa cuenta a "
        "todos los de 15 años o más.",
        "used_for": ["Lente de estudios superiores"],
    },
    "ine_censo2021_indicadores": {
        "title": "Censos de Población y Viviendas 2021: indicadores por sección censal (viviendas principales por régimen "
        "de tenencia)",
        "license": _INE_LICENCE,
        "description": "Viviendas principales (residencia habitual de un hogar) en propiedad, en alquiler y en otro régimen "
        "de tenencia de cada sección censal el 1 de enero de 2021, del fichero de indicadores del Censo de 2021, sumadas "
        "por municipio. El INE no publica las secciones de los municipios más pequeños (secreto estadístico), que se "
        "quedan sin dato, y llama provisional al fichero porque está pasando algunas viviendas a su sección correcta, "
        "lo que no cambia el total de un municipio.",
        "used_for": ["Lente de vivienda en propiedad"],
    },
    "ine_censo_divisiones": {
        "title": "Censo anual de población: ocupados por división de la CNAE, España y ciudades principales (tablas 69960 y 69980)",
        "license": _INE_LICENCE,
        "description": "Ocupados de 16 años o más por la división de dos dígitos de la CNAE-2009 de su empleo (88 "
        "divisiones), para España y sus provincias (tabla 69960) y para las capitales de provincia y ciudades "
        "principales (151 municipios, tabla 69980), contados donde viven. Sirve para los distritos: la especialización "
        "de cada ciudad frente a la cuota nacional.",
        "used_for": ["Distritos y tipos de ciudad"],
    },
    "ine_censo_ocupados": {
        "title": "Censo anual de población: ocupados por sección de la CNAE (tablas 69962 y 69992)",
        "license": _INE_LICENCE,
        "description": "Ocupados de 16 años o más por la sección de la CNAE-2009 (A…U) de su empleo, contados donde viven "
        "(como la ACS del mapa de EE. UU.), del Censo anual de población (Ocupación y actividad): España y las provincias "
        "(tabla 69962) y todos los municipios de 500 habitantes o más (tabla 69992). Las secciones se asignan a los "
        "sectores del mapa; «No consta» solo cuenta en el total.",
        "used_for": ["Rendimientos de comida, producción y cultura", "Reparto de la ciencia (I+D) entre provincias y ciudades",
                     "Empleo por sector", "Residentes ocupados"],
    },
    "ine_imasd": {
        "title": "Estadística sobre actividades de I+D (todos los sectores): gasto en I+D interna y personal en I+D por "
        "comunidad autónoma, tablas 82978 y 82944",
        "license": _INE_LICENCE,
        "description": "Gasto en I+D interna (euros) y personal en I+D en equivalencia a jornada completa (EJC), contados "
        "donde se hace la I+D, de España, sus 17 comunidades autónomas, Ceuta y Melilla (tabla 82978; empresas, "
        "administración pública, enseñanza superior e instituciones privadas sin fines de lucro, según el Manual de "
        "Frascati). El año sale de la serie nacional de personal en EJC (tabla 82944). Los datos de Ceuta y Melilla están "
        "protegidos por secreto estadístico y quedan vacíos.",
        "used_for": ["Rendimiento de ciencia (personal en I+D) de las provincias, las ciudades y España"],
    },
    "ine_padron": {
        "title": "Cifras oficiales de población de los municipios (revisión del Padrón municipal), tabla 29005",
        "license": _INE_LICENCE,
        "description": "Residentes de cada municipio a 1 de enero de cada año desde 1996, de la revisión anual del Padrón "
        "municipal. Las provincias y España son la suma de sus municipios.",
        "used_for": ["Población", "Tamaño de las ciudades", "Crecimiento de la población", "Lente de densidad"],
    },
    "ine_pib": {
        "title": "PIB a precios de mercado por provincia, precios corrientes (Contabilidad Regional de España), tabla 80109",
        "license": _INE_LICENCE,
        "description": "Producto interior bruto a precios de mercado en euros corrientes de España, sus comunidades "
        "autónomas y sus provincias (miles de euros en la tabla). Las comunidades uniprovinciales (Madrid, Asturias, "
        "Cantabria, Murcia, Navarra, La Rioja, Illes Balears, Ceuta y Melilla) solo aparecen como comunidad y se usan "
        "como su provincia. El total de España cuenta además la extrarregio (embajadas, bases en el extranjero), que no "
        "tiene ninguna provincia.",
        "used_for": ["Oro (PIB) de las provincias y de España"],
    },
    "natural_earth_es": {
        "title": "Natural Earth 1:10m (países, lagos, ríos) alrededor de España",
        "license": "Dominio público",
        "description": "Los países vecinos (Portugal, Francia, Andorra, Gibraltar, Marruecos; bajo niebla), lagos y "
        "embalses, y ríos. A 1:10m, así que los hexágonos de 10 km reciben también los afluentes del Ebro, el Tajo y el "
        "Guadalquivir. " + _PINNED,
        "used_for": ["Tierra extranjera (Portugal, Francia, Marruecos)", "Lagos y embalses", "Ríos"],
    },
    "natural_earth_roads_es": {
        "title": "Natural Earth 1:10m: carreteras y ferrocarriles alrededor de España",
        "license": "Dominio público",
        "description": "Autovías y autopistas, carreteras principales y ferrocarriles como trazado a 1:10m. Se muestran "
        "como dibujo del mapa (carreteras y vías entre centros de hexágono), no como estadística: Natural Earth no trae "
        "datos de tráfico ni de titularidad y solo recoge las líneas principales. " + _PINNED,
        "used_for": ["Autovías y carreteras principales del mapa", "Ferrocarriles del mapa"],
    },
    "oapn_parques": {
        "title": "Límites y visitantes de los Parques Nacionales (Red de Parques Nacionales)",
        "license": _REUSE + "; el servicio no declara restricciones de acceso ni tasas",
        "description": "Los límites de los 16 Parques Nacionales de España tal como los declara la ley, con su fecha de "
        "declaración y su superficie oficial, del servidor de mapas del OAPN, y sus visitantes de 2025 según el informe "
        "anual del OAPN (solo en PDF, transcrito en pipeline/sources/es/data). La zona periférica de protección de la "
        "Sierra de Guadarrama no es Parque Nacional y se deja fuera.",
        "used_for": ["Maravillas de los Parques Nacionales", "Espacios protegidos"],
    },
    "siane": {
        "title": "Límites y capitales municipales del SIANE, 1:3 millones (Atlas Nacional de España)",
        "publisher": "Instituto Geográfico Nacional (IGN), republicado por rOpenSpain/mapSpain",
        "description": "Los contornos de los municipios vigentes (código INE) y la posición de la capital de cada "
        "municipio. Cada hexágono pertenece al municipio y a la provincia donde caen la mayoría de sus siete puntos de "
        "muestra; las provincias son la unión de sus municipios y de los territorios que comparten varios municipios "
        "(condominios). Las ciudades se sitúan en su capital municipal.",
        "used_for": ["Mapa: tierra y agua", "Límites provinciales", "Municipio de cada hexágono", "Posición de las ciudades"],
    },
    "wikidata_es": {
        "title": "Wikidata: Patrimonio Mundial, catedrales, museos, Bienes de Interés Cultural, castillos y plazas de toros "
        "de España",
        "publisher": "Wikidata (Fundación Wikimedia y editores voluntarios)",
        "license": "CC0 1.0 (cesión al dominio público)",
        "description": "Los elementos de España declarados Patrimonio Mundial (agrupados por su número de sitio de la "
        "UNESCO), las catedrales y concatedrales, los museos, los Bienes de Interés Cultural, los castillos (con sus "
        "subclases: casas torre, alcazabas, alcázares, ruinas) y las plazas de toros, sin los derribados, con sus "
        "coordenadas, del servicio SPARQL de Wikidata. Lo editan voluntarios: la cobertura se acerca a los registros "
        "oficiales, pero no es exacta.",
        "used_for": ["Maravillas de Patrimonio Mundial y catedrales", "Lente de patrimonio (Bienes de Interés Cultural)",
                     "Lente de museos", "Lente de castillos", "Lente de plazas de toros"],
    },
    "wikidata_personajes": {
        "title": "Wikidata: personajes famosos nacidos en España (oficios, cargos, premios, lugares y fechas)",
        "publisher": "Wikidata (Fundación Wikimedia y editores voluntarios)",
        "license": "CC0 1.0 (cesión al dominio público)",
        "description": "Las personas cuyo lugar de nacimiento sitúa Wikidata en España (o, en lugares históricos, en un "
        "reino o un estado de la península: Calagurris en la Antigua Roma, una villa de la Corona de Castilla), con "
        "sus ocupaciones, cargos (monarcas, papas, cardenales), premios Nobel, estado de canonización, número de "
        "enlaces a proyectos de Wikimedia, fechas de nacimiento y muerte y coordenadas del lugar de nacimiento, del "
        "servicio SPARQL de Wikidata. Lo editan voluntarios: quién tiene ficha y qué oficios lista sigue la "
        "cobertura de Wikipedia, no un registro.",
        "used_for": ["Lentes de grandes personajes", "Búsqueda de personajes"],
    },
    "aena_airports": {
        "title": "Pasajeros, operaciones y mercancías por aeropuerto de la red de AENA (2025, definitivos)",
        "publisher": "Aena; posiciones de los aeropuertos de OurAirports",
        "license": "Estadísticas de AENA: reproducción sujeta al aviso legal de Aena; OurAirports: dominio público",
        "description": "Pasajeros (llegadas más salidas), operaciones y mercancías de los aeropuertos y helipuertos de la "
        "red de AENA en 2025. Cada uno se sitúa con OurAirports, emparejado por las palabras de su nombre.",
        "used_for": ["Aeropuertos del mapa"],
    },
    "puertos_estado": {
        "title": "Tráfico de mercancías por Autoridad Portuaria (2025) y zonas de servicio de los puertos",
        "publisher": "Puertos del Estado",
        "license": "Zonas de servicio: CC BY 4.0 (datos.gob.es); estadísticas de tráfico: aviso legal de Puertos del Estado",
        "description": "Tráfico total de mercancías en toneladas de cada una de las 28 Autoridades Portuarias en 2025 "
        "(acumulado a diciembre), situado en la zona de servicio terrestre de su puerto más grande.",
        "used_for": ["Puertos del mapa"],
    },
    "siiu_universidades": {
        "title": "Estudiantes universitarios por centro y municipio de cada centro (SIIU, curso 2024-2025)",
        "publisher": "Sistema Integrado de Información Universitaria, Ministerio de Ciencia, Innovación y Universidades",
        "license": "Reutilización comercial o no, citando al Ministerio de Ciencia, Innovación y Universidades",
        "description": "Estudiantes matriculados en grado, máster y doctorado en el curso 2024-25 en cada centro de cada "
        "universidad española, con el municipio del centro y si la universidad es presencial.",
        "used_for": ["Maravillas de las grandes universidades"],
    },
    "power_plants_es": {
        "title": "Centrales eléctricas de España (powerplantmatching; OpenStreetMap en Canarias)",
        "publisher": "powerplantmatching de PyPSA (KIT y colaboradores); colaboradores de OpenStreetMap",
        "license": "Datos de powerplantmatching: CC BY 4.0; OpenStreetMap: ODbL 1.0",
        "description": "Todas las centrales que powerplantmatching recoge en España (una fusión de ENTSO-E, GEM, OPSD, "
        "JRC y otros registros), con su combustible, potencia, ubicación y años de entrada y de cierre, fijado a un "
        "commit. No tiene ninguna central en Canarias, así que esas salen de los objetos power=plant de OpenStreetMap "
        "que declaran su potencia.",
        "used_for": ["Centrales del mapa (recursos)"],
    },
    "igme_minas": {
        "title": "Minas activas en 2019 (Estadística Minera de España, IGME), situadas con los yacimientos del BDMIN",
        "publisher": "IGME-CSIC (Instituto Geológico y Minero de España); Ministerio para la Transición Ecológica "
        "(Estadística Minera de España)",
        "license": "Licencia de uso del IGME: reutilización libre y gratuita, comercial o no, citando la fuente "
        "(Ley 37/2007 y RD 1495/2011)",
        "description": "Las explotaciones activas en 2019 de la Estadística Minera de España, tal como el IGME las "
        "publica con el Panorama Minero 2022 (EXPLOTACIONES_2019.xlsx), la lista más reciente con el nombre de cada "
        "mina. Se quedan las minas metálicas y las de potasa, fluorita, celestina, magnesita y sulfato sódico, y su "
        "número por sustancia coincide con las tablas del Panorama. La estadística no da la posición ni la producción de "
        "cada mina: la posición es la del yacimiento de su mineral y su municipio en el BDMIN del IGME (base de datos de "
        "indicios minerales) y, si no hay ninguno, el centro del municipio. Del resto de la lista se guardan la "
        "sustancia y el municipio de cada explotación, y del BDMIN los yacimientos grandes y medianos de carbón, uranio, "
        "bauxita, hierro, oro, cobre y plata, se exploten o no, para el mapa de Unciv.",
        "used_for": ["Minas del mapa (recursos)", "Recursos del mapa de Unciv (carbón, uranio, aluminio, hierro, oro, cobre, "
                     "plata, petróleo, mármol, sal, piedra)"],
    },
    "ine_censo_agrario": {
        "title": "Censo Agrario 2020: cabezas de équidos por comarca agraria (tabla 51175) y la comarca de cada municipio "
        "(tabla 75479)",
        "license": _INE_LICENCE,
        "description": "Las cabezas de ganado equino (caballos, mulos y asnos) de las explotaciones agrarias en 2020, por "
        "comarca agraria del INE, y los municipios de cada comarca. Las explotaciones que solo tienen équidos no están en "
        "el censo. El censo equino del Ministerio de Agricultura (REGA) solo se publica por comunidad autónoma.",
        "used_for": ["Caballos del mapa de Unciv"],
    },
    "calidad_diferenciada": {
        "title": "Denominaciones de calidad: el registro de la UE (eAmbrosia) y sus zonas (MAPA y pliegos)",
        "publisher": "Comisión Europea (eAmbrosia, Diario Oficial); Ministerio de Agricultura, Pesca y Alimentación; "
        "gobiernos autonómicos (pliegos de condiciones)",
        "license": "eAmbrosia y EUR-Lex: aviso de reutilización de la Comisión Europea (CC BY 4.0); MAPA: CC BY 4.0; "
        "pliegos: textos oficiales",
        "description": "Todos los nombres que España tiene en el registro de la UE (denominaciones de origen protegidas, "
        "indicaciones geográficas protegidas, vinos y bebidas espirituosas) con su zona geográfica: la del mapa del "
        "Ministerio cuando la tiene (revisión de 2017) y, si no, la que delimita su pliego o el documento único de la "
        "UE, pasada a pipeline/sources/es/data/calidad_diferenciada_zonas.csv como comunidades, provincias, islas o "
        "municipios. Un vino de pago es una finca y va en su municipio.",
        "used_for": ["Lente de denominaciones de origen",
                     "Recursos del mapa de Unciv (vino, cítricos, especias, ganado, ovejas, pescado, plátanos)"],
    },
    "pleiades_iberia": {
        "title": "Pueblos de la Iberia antigua (Pleiades)",
        "publisher": "Pleiades (Institute for the Study of the Ancient World, NYU, y colaboradores)",
        "license": "CC BY 3.0",
        "description": "Todos los lugares que Pleiades clasifica como pueblo, con punto, en la península y su entorno "
        "(vacceos, vascones, cántabros, ilergetes, los muchos pueblos de Gallaecia…), más las regiones que llevan el "
        "nombre de pueblos sin punto propio (Turdetania, Bastetania, Contestania, Edetania, Carpetania, Celtiberia, "
        "Cessetania, Laeetania). Un «?» marca una ubicación dudosa, como en Pleiades.",
        "used_for": ["Lente de pueblos prerromanos"],
    },
    "lenguas_es": {
        "title": "Lenguas oficiales por municipio (zonas lingüísticas de Navarra, zona valencianohablante)",
        "publisher": "Gobierno de Navarra (IDENA); Agencia Estatal Boletín Oficial del Estado",
        "license": "IDENA: CC BY 4.0; BOE: textos legales, de libre reutilización",
        "description": "Las zonas lingüísticas de Navarra (Ley Foral 18/1986, reformada en 2017) y los municipios de "
        "predominio castellano de la Comunitat Valenciana (Llei 4/1983, art. 36); con las comunidades donde una lengua "
        "es cooficial en todo el territorio, dan las lenguas oficiales de cada municipio.",
        "used_for": ["Lente de lenguas"],
    },
    "gastronomia_es": {
        "title": "Platos y productos regionales por provincia (categorías de la Wikipedia en español, filtradas con "
        "Wikidata)",
        "publisher": "Wikipedia en español y Wikidata (Fundación Wikimedia y editores voluntarios)",
        "license": "Wikipedia: CC BY-SA 4.0 (solo se usan los títulos); Wikidata: CC0",
        "description": "Los artículos de la categoría «Gastronomía de …» de cada provincia en la Wikipedia en español que "
        "Wikidata clasifica como comida o bebida: platos, embutidos, quesos, dulces, panes, vinos. Lo editan "
        "voluntarios: unas provincias están mucho mejor cubiertas que otras, y Canarias comparte una sola categoría.",
        "used_for": ["Lente de platos regionales"],
    },
    "bandera_azul": {
        "title": "Playas con Bandera Azul 2026-2027 (ADEAC)",
        "publisher": "ADEAC (Asociación de Educación Ambiental y del Consumidor), programa Bandera Azul",
        "license": "© ADEAC; la lista de playas galardonadas se cita tal como se publica",
        "description": "Todas las playas españolas con Bandera Azul para 2026-2027, por municipio, según la lista en "
        "PDF de ADEAC (leída a pipeline/sources/es/data/bandera_azul_2026.csv; el número por comunidad coincide con el "
        "de ADEAC).",
        "used_for": ["Lente de Bandera Azul"],
    },
    "serpavi": {
        "title": "Sistema Estatal de Referencia del Precio del Alquiler de Vivienda (SERPAVI), 2011-2024",
        "publisher": "Ministerio de Vivienda y Agenda Urbana (con la Agencia Tributaria y la Dirección General del Catastro)",
        "license": _REUSE,
        "description": "Alquileres declarados en el IRPF por viviendas habituales (sin los arrendamientos entre "
        "parientes), cruzados con el Catastro: número de viviendas alquiladas y alquiler mensual mediano de la vivienda "
        "entera, por separado para pisos (vivienda colectiva) y casas (unifamiliar), por provincia y municipio. Los "
        "municipios con pocos contratos no tienen cifra. Un lugar junta sus pisos y sus casas, y un área urbana sus "
        "municipios con cifra, en la media de esas medianas ponderada por viviendas alquiladas: se aproxima a la "
        "mediana del conjunto, no es la mediana exacta. España junta así sus provincias. Es la renta que declara el "
        "arrendador; la del mapa de EE. UU. es el alquiler bruto, con suministros, que declara el inquilino.",
        "used_for": ["Alquiler mensual de áreas urbanas, provincias y España", "Alquiler ÷ renta"],
    },
    "mivau_valor_tasado": {
        "title": "Valor tasado de la vivienda libre por m², por provincia (Ministerio de Vivienda, VDP006)",
        "publisher": "Ministerio de Vivienda y Agenda Urbana",
        "license": _REUSE,
        "description": "Valor medio por m² construido de las viviendas libres según las tasaciones que las sociedades "
        "tasadoras hacen cada trimestre, por provincia. Las comunidades de una sola provincia (Madrid, Asturias, Navarra, "
        "Murcia, Cantabria, La Rioja, Baleares) vienen como fila de comunidad. La serie municipal solo se publica en un "
        "XLS que hoy no se puede descargar, así que todo hexágono lleva el valor de su provincia.",
        "used_for": ["Lente de valor de la vivienda (€/m², por provincia)"],
    },
    "cobertura_banda_ancha": {
        "title": "Cobertura de banda ancha en España 2021-2025 por municipio, provincia, comunidad autónoma y España",
        "license": _REUSE,
        "description": "Proporción de los hogares a los que pueden dar servicio las redes fijas y móviles, por tecnología "
        "y por velocidad en condiciones de máxima demanda, en junio de cada año, a partir de la cobertura que los "
        "operadores declaran al ministerio, situada por parcela catastral (hogares del Censo 2021 del INE). El mapa toma "
        "la cobertura de 100 Mbps o más de cada municipio. Mide hasta dónde llega una red, no quién la contrata.",
        "used_for": ["Lente de banda ancha"],
    },
    "ine_censo_lugar_trabajo": {
        "title": "Censo anual de población: ocupados por lugar de trabajo (tablas 69968 y 69987)",
        "license": _INE_LICENCE,
        "description": "Ocupados de 16 años o más según dónde trabajan respecto a dónde viven (el mismo municipio, otro "
        "de la provincia, otra provincia de la comunidad, otra comunidad, o sin información), del Censo anual de "
        "población que el INE elabora con registros administrativos: España y cada provincia (tabla 69968) y las "
        "capitales de provincia y ciudades principales (151 municipios, tabla 69987). El resto de cada provincia es la "
        "provincia menos esas ciudades. Es dónde se trabaja, no cuánto se tarda: el INE no publica el tiempo de "
        "desplazamiento por municipio.",
        "used_for": ["Lente de los que trabajan fuera de su municipio"],
    },
    "ine_esperanza_vida": {
        "title": "Esperanza de vida al nacer por provincia y por municipio (Indicadores Demográficos Básicos, tablas 1485 "
        "y 30687)",
        "license": _INE_LICENCE,
        "description": "Esperanza de vida al nacer, ambos sexos, de cada provincia (tabla 1485) y de los municipios para "
        "los que el INE la calcula (unos 150 grandes, tabla 30687), a partir de las defunciones (Movimiento Natural de "
        "la Población) y la población. El mapa toma el último año que tienen las dos tablas.",
        "used_for": ["Lente de esperanza de vida"],
    },
    "ine_matrimonios": {
        "title": "Matrimonios por provincia y principales municipios de residencia y forma de celebración (MNP, tablas "
        "77172 y 37645)",
        "license": _INE_LICENCE,
        "description": "Matrimonios de cada año según dónde vive la pareja, civiles o religiosos (las tablas del INE no "
        "separan los católicos de los de otras confesiones), de España y cada provincia (tabla 77172) y de los "
        "principales municipios de residencia (unos 150, tabla 37645), del Movimiento Natural de la Población. El resto "
        "de cada provincia es la provincia menos esos municipios.",
        "used_for": ["Lente de bodas religiosas"],
    },
    "effis_incendios": {
        "title": "Superficies quemadas en España, 2016-2025, del EFFIS (Servicio de Gestión de Emergencias de Copernicus)",
        "publisher": "Comisión Europea, Centro Común de Investigación: Sistema Europeo de Información sobre Incendios "
        "Forestales (EFFIS), Servicio de Gestión de Emergencias de Copernicus",
        "license": "CC BY 4.0 (política de reutilización de la Comisión Europea), citando EFFIS / Copernicus EMS",
        "description": "Los perímetros de los incendios que el EFFIS cartografió en España cada temporada con imágenes de "
        "satélite (MODIS y Sentinel-2), de unas 30 ha o más, con su superficie. El mapa suma lo quemado en las diez "
        "últimas temporadas completas en cada hexágono: la superficie de cada incendio se reparte entre los hexágonos "
        "que cubre su perímetro. La estadística oficial española (EGIF, del Ministerio para la Transición Ecológica) "
        "cuenta todos los incendios, también los pequeños, pero no tiene descarga por municipio.",
        "used_for": ["Lente de incendios"],
    },
    "balance_criminalidad": {
        "title": "Balance de Criminalidad, cuarto trimestre (enero a diciembre): infracciones penales conocidas por "
        "tipo, de provincias, islas y municipios de más de 20.000 habitantes",
        "license": _REUSE,
        "description": "Infracciones penales que conocen la Policía Nacional, la Guardia Civil, los Mossos d'Esquadra, la "
        "Ertzaintza, la Policía Foral de Navarra y las policías locales que informan al Sistema Estadístico de "
        "Criminalidad, por denuncia o por actuación policial, en trece tipos (homicidios, intentos de homicidio, "
        "lesiones, secuestros, delitos sexuales, robos con violencia, robos con fuerza, hurtos, sustracciones de "
        "vehículos, tráfico de drogas, estafas informáticas, otros ciberdelitos, el resto) y en total. España, cada provincia y las cometidas en el "
        "extranjero (una tabla), cada isla y cada municipio de más de 20.000 habitantes (la otra). El resto de cada "
        "provincia o isla es la provincia o la isla menos sus municipios de la lista.",
        "used_for": ["Lente de criminalidad (infracciones penales conocidas por 1.000 habitantes)",
                     "Lente del delito que más destaca sobre la tasa de España"],
    },
    "aemet_normales_provincias": {
        "title": "Valores normales 1991-2020 por provincia (AEMET, Estadística de Vigilancia del Clima)",
        "license": _AEMET,
        "description": "Las normales mensuales 1991-2020 de AEMET de temperatura media, media de las máximas, media de "
        "las mínimas y precipitación de cada provincia, Ceuta, Melilla y la España peninsular: AEMET interpola los datos "
        "de sus estaciones a una rejilla y la promedia en cada región.",
        "used_for": ["Clima del mes (diagrama de la provincia, barras de los meses, Ceuta y Melilla)"],
    },
    "omm_normales_es": {
        "title": "Normales climatológicas estándar de la OMM 1991-2020, España (AEMET, vía la NCEI, accession 0253808 "
        "v6.6)",
        "license": _AEMET + " (la NCEI no indica licencia en los ficheros)",
        "description": "Las normales mensuales 1991-2020 que AEMET envió a la OMM para 83 estaciones: temperatura media, "
        "máxima y mínima, precipitación, días con la mínima por debajo de 0 °C y horas de sol (76 estaciones). El nombre "
        "y la posición de cada estación salen de su página de AEMET.",
        "used_for": ["Clima del mes (estaciones, horas de sol)"],
    },
    "fiestas_interes_turistico": {
        "title": "Fiestas de Interés Turístico Internacional y Nacional (Secretaría de Estado de Turismo)",
        "publisher": "Ministerio de Industria y Turismo, Secretaría de Estado de Turismo",
        "license": _REUSE,
        "description": "Las dos listas oficiales de fiestas declaradas de Interés Turístico Internacional y Nacional "
        "(Orden ICT/851/2019), por comunidad autónoma y con el año de cada declaración, tal como las publica "
        "turismo.gob.es. Cada fiesta se sitúa en los municipios que nombra su título (una ruta o un valle, en los suyos) "
        "con una tabla del repositorio (pipeline/sources/es/data/fiestas_interes_turistico.csv). Una fiesta que está en "
        "las dos listas cuenta una vez, como Internacional.",
        "used_for": ["Lente de fiestas de interés turístico", "Índice de fiesta"],
    },
    "fiestas_autonomicas": {
        "title": "Fiestas de interés turístico que declaran las comunidades autónomas",
        "publisher": "Las consejerías de turismo de las comunidades autónomas, en sus boletines, registros, portales de "
        "turismo y datos abiertos",
        "license": _REUSE,
        "description": "Las fiestas que cada comunidad autónoma declara de interés turístico en su propio ámbito (Fiesta "
        "de Interés Turístico de Andalucía, Festa de Interese Turístico de Galicia, Fiesta de Interés Turístico "
        "Regional…), de su lista oficial, su registro o las órdenes de su boletín, con las fechas que da la fuente. Una "
        "tabla del repositorio (pipeline/sources/es/data/fiestas_autonomicas.csv) las transcribe, cita la fuente de "
        "cada fila y sitúa cada fiesta en su municipio. Una fiesta que el Estado ha declarado después Nacional o "
        "Internacional cuenta una vez, en la categoría del Estado. Euskadi, Illes Balears, Ceuta y Melilla no han "
        "declarado ninguna.",
        "used_for": ["Lente de fiestas de interés turístico", "Índice de fiesta", "Calendario de fiestas (fiestas.json)"],
    },
    "ine_viviendas_turisticas": {
        "title": "Viviendas turísticas, plazas y plazas por vivienda turística por municipio (INE, estadística "
        "experimental, tabla 39363)",
        "publisher": "Instituto Nacional de Estadística (INE)",
        "license": _INE_LICENCE,
        "description": "Viviendas que se anuncian como alquiler turístico en las grandes plataformas en línea, casadas "
        "con el Catastro, y sus plazas, por municipio, de la estadística experimental del INE sobre viviendas "
        "turísticas. Se usa el último periodo publicado; las de los municipios suman el total nacional.",
        "used_for": ["Lente de viviendas turísticas", "Índice de fiesta"],
    },
    "osm_bares": {
        "title": "Bares y pubs de España (OpenStreetMap, amenity=bar y amenity=pub)",
        "publisher": "Colaboradores de OpenStreetMap, a través de la API Overpass",
        "license": "ODbL 1.0 (© colaboradores de OpenStreetMap)",
        "description": "Todos los nodos, vías y relaciones de OpenStreetMap en España con amenity=bar o amenity=pub, en "
        "su posición (el centro de una vía), de una sola consulta guardada. Las cafeterías y los restaurantes no "
        "cuentan. Lo mapean voluntarios: las ciudades y las costas turísticas están mucho mejor cubiertas que los "
        "pueblos.",
        "used_for": ["Lente de bares por 1.000 habitantes", "Índice de fiesta"],
    },
    "osm_playas": {
        "title": "Playas con nombre de España (OpenStreetMap, natural=beach)",
        "publisher": "Colaboradores de OpenStreetMap, a través de la API Overpass",
        "license": "ODbL 1.0 (© colaboradores de OpenStreetMap)",
        "description": "Todos los nodos, vías y relaciones de OpenStreetMap en España con natural=beach y nombre, en su "
        "posición (el centro de una vía), con sus nombres (name, name:es, name:ca, name:gl, name:eu, name:ast, "
        "alt_name, official_name, loc_name, old_name), de una sola consulta guardada. Lo mapean voluntarios.",
        "used_for": ["Lente de Bandera Azul: la posición de cada playa que Wikidata no tiene"],
    },
    "osm_militar": {
        "title": "Terreno e instalaciones militares de España (OpenStreetMap, landuse=military y military=*)",
        "publisher": "Colaboradores de OpenStreetMap, a través de la API Overpass",
        "license": "ODbL 1.0 (© colaboradores de OpenStreetMap)",
        "description": "Todas las zonas de OpenStreetMap en España con landuse=military o military=base, barracks, "
        "airfield, naval_base, training_area, range, danger_area u office, con su límite, nombre y operador, y los "
        "puntos con nombre que llevan esas etiquetas, de una sola consulta guardada. Lo mapean voluntarios: los nombres "
        "y operadores son suyos, y algunos límites cubren solo parte de un recinto. El Ministerio de Defensa no publica "
        "una lista abierta de sus instalaciones.",
        "used_for": ["Consejero militar: instalaciones, campos de maniobras y guarniciones",
                     "Capa militar del mapa (fuertes y terreno restringido)"],
    },
    "wikidata_militar": {
        "title": "Wikidata: bases, cuarteles, academias y arsenales militares de España",
        "publisher": "Wikidata (Fundación Wikimedia y editores voluntarios)",
        "license": "CC0 1.0 (dominio público)",
        "description": "Elementos en España cuya clase es cuartel, academia o escuela militar, base aérea, naval o "
        "militar, estación naval, arsenal, maestranza aérea, hospital militar, centro o campo de entrenamiento, con "
        "coordenadas, operador (P137) y rama (P241), sin los que Wikidata da por disueltos o como instalación militar "
        "histórica. Sirve para enlazar las instalaciones de OpenStreetMap con su elemento y para dar la rama que OSM "
        "no trae.",
        "used_for": ["Consejero militar: enlaces a Wikidata y rama de las instalaciones"],
    },
    "wikidata_playas": {
        "title": "Wikidata: playas de España con coordenadas, nombres y municipio",
        "publisher": "Wikidata (Fundación Wikimedia y editores voluntarios)",
        "license": "CC0 1.0 (dominio público)",
        "description": "Todos los elementos de Wikidata en España que son una playa (Q40080 o una subclase) con "
        "coordenadas, con sus etiquetas y alias en castellano, gallego, catalán, euskera, asturiano, aragonés, occitano "
        "y «mul», y el código INE del municipio en que están. Lo editan voluntarios: unas costas están mucho mejor "
        "cubiertas que otras.",
        "used_for": ["Lente de Bandera Azul: la posición de cada playa"],
    },
}


def source(entry: dict) -> dict:
    """A sources.json entry in Spanish and English: each field SOURCES translates is a Text of the Spanish and the
    source's own English (pipeline/sources/es), item by item for `used_for`; the others stay as the source gives them."""
    out = {**entry, "vintage": vintage(entry.get("vintage"))}
    for key, es in SOURCES.get(entry["id"], {}).items():
        en = entry.get(key)
        if key == "used_for":
            if len(es) != len(en or []):
                raise ValueError(f"{entry['id']}: used_for has {len(es)} items in Spanish and {len(en or [])} in English")
            out[key] = [tr(a, b) for a, b in zip(es, en)]
        elif not en:
            raise ValueError(f"{entry['id']}: no English {key} for the Spanish one")
        else:
            out[key] = tr(es, en)
    return out

