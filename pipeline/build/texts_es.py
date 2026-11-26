"""Spanish texts for the tables Spain shares with the US builders.

The US builders' constants (yield labels, lens groups, the land lenses, the world.json tables, badge texts, rail
tiers) stay in English, since the US output must not change. Spain's builders take these Spanish versions instead;
Spain-only catalogs (spain.py, spain_districts.py, spain_wonders.py, spain_infrastructure.py) are written in Spanish
where they are defined. The Almanac's source entries come from pipeline/sources/es in English and are given in
Spanish here (`source`), with their vintages (`vintage`).
"""

from __future__ import annotations

import re


def num(x: float, decimals: int | None = None) -> str:
    """A number as Spanish writes it: decimal comma, and a thousands point from five digits on ("1000", "12.000", "2,5")."""
    if decimals is None and float(x).is_integer():
        x = int(x)
    whole, _, frac = (f"{x:,.{decimals}f}" if decimals is not None else f"{x:,}").partition(".")
    if len(whole.lstrip("-").replace(",", "")) <= 4:
        whole = whole.replace(",", "")
    return whole.replace(",", ".") + ("," + frac if frac else "")


def pct(x: float, decimals: int = 0) -> str:
    return f"{num(x * 100, decimals)} %"


YIELD_LABELS = {"food": "Comida", "production": "Producción", "gold": "Oro", "science": "Ciencia", "culture": "Cultura"}

LENS_GROUPS = {
    "people": "Población", "prosperity": "Prosperidad", "knowledge": "Conocimiento", "life": "Vida diaria", "faith": "Fe",
    "hazards": "Riesgos", "land": "Territorio",
}
LAND_UNIT = "proporción del suelo"
LAND_LENSES = {
    "forest": {"name": "Bosque", "description": "Proporción de la tierra del hexágono cubierta de bosque caducifolio, de "
               "coníferas o mixto (CORINE 311–313)."},
    "farmland": {"name": "Tierra agraria", "description": "Proporción de la tierra del hexágono con cultivos, prados o "
                 "dehesas (CORINE 2xx, cruzadas con las clases 81 y 82 de NLCD)."},
    "developed": {"name": "Urbanizado", "description": "Proporción de la tierra del hexágono urbanizada: tejido urbano, "
                  "zonas industriales y comerciales, redes de transporte, puertos, aeropuertos y obras (CORINE 111, 112, "
                  "121–124 y 133; las zonas verdes y deportivas urbanas no cuentan)."},
}
DOMAIN_NOTE = " Los colores abarcan del percentil 2 al 98 de los hexágonos; los valores de fuera se pintan con el color del extremo."

# world.json tables (world.py: names and rules by row id; {hills}, {mountains} and {urban} are the country's thresholds).
WORLD = {
    "water": {
        0: {"name": "Tierra", "rule": "Al menos 4 de los 7 puntos de muestra del hexágono (el centro y 6 más) caen en un "
            "municipio del SIANE o en un país de Natural Earth, salvo que el centro sea mar y la media de ETOPO1 esté al "
            "nivel del mar o por debajo, o lo esté al menos la mitad de sus muestras de ETOPO1 (las rías y los estuarios "
            "siguen siendo agua)."},
        1: {"name": "Océano", "rule": "Mar de más de 200 m de profundidad y sin tierra al lado."},
        2: {"name": "Costa", "rule": "Mar junto a un hexágono de tierra, o de menos de 200 m de profundidad (media de ETOPO1)."},
        3: {"name": "Lago", "rule": "Hexágono de agua (la mayoría de sus 7 puntos fuera de tierra) con más puntos de lago de "
            "Natural Earth 1:10m que de mar, o por encima del nivel del mar."},
    },
    "relief": {
        0: {"name": "Llano", "rule": "Desviación típica de la altitud dentro del hexágono menor de {hills} m."},
        1: {"name": "Colinas", "rule": "Desviación típica de la altitud de {hills} m o más."},
        2: {"name": "Montañas", "rule": "Desviación típica de la altitud de {mountains} m o más, o altitud media de 2300 m o más."},
        3: {"name": "Cumbres", "rule": "Altitud media de 2700 m o más (alta montaña)."},
    },
    "cover": {
        0: {"name": "Ninguna", "rule": "Agua, tierra extranjera o ningún píxel de tierra de CORINE."},
        1: {"name": "Bosque caducifolio", "rule": "El bosque (NLCD 41+42+43) es el grupo mayor y el caducifolio (41), su "
            "tipo principal."},
        2: {"name": "Bosque de coníferas", "rule": "El bosque es el grupo mayor y el perennifolio (42), su tipo principal."},
        3: {"name": "Bosque mixto", "rule": "El bosque es el grupo mayor y el mixto (43), su tipo principal."},
        4: {"name": "Matorral y desierto", "rule": "El matorral (52) es el grupo mayor: maquia, garriga, landas y zonas "
            "semiáridas."},
        5: {"name": "Pastizal", "rule": "El pastizal (71) más los espacios abiertos urbanos (21: parques, zonas deportivas) "
            "es el grupo mayor."},
        6: {"name": "Pastos", "rule": "Los prados y pastos (81) son el grupo mayor."},
        7: {"name": "Cultivos", "rule": "Los cultivos (82) son el grupo mayor."},
        8: {"name": "Humedal", "rule": "Los humedales leñosos (90) y herbáceos (95) juntos son el grupo mayor."},
        9: {"name": "Urbano", "rule": "Lo urbanizado de intensidad baja, media o alta (22+23+24) ocupa el {urban} % o más de "
            "la tierra del hexágono, haya lo que haya además."},
        10: {"name": "Suelo desnudo", "rule": "El suelo desnudo (31: roca, arena, salinas) es el grupo mayor."},
        11: {"name": "Hielo y nieve", "rule": "El hielo y la nieve perpetuos (12) son el grupo mayor."},
    },
    "notes": {
        "water": "Los límites municipales del SIANE 1:3M y los de países y lagos de Natural Earth 1:10m no encajan del "
        "todo. Un hexágono de mar cuya media de ETOPO1 está sobre el nivel del mar (y con menos de la mitad de sus muestras "
        "por debajo) pasa a tierra si al menos 4 de sus 6 vecinos son tierra, o si toca a la vez tierra española y "
        "extranjera; toma el dueño mayoritario de sus vecinos. La altitud de un hexágono de mar es la media de sus muestras "
        "de ETOPO1 bajo el nivel del mar (su profundidad). Canarias va en un recuadro al suroeste de la península; sus "
        "hexágonos conservan su altitud y su cubierta del suelo reales.",
        "relief": "Sale de las muestras de ETOPO1 (1 minuto de arco, unos 1,85 km de separación, unas 25 por hexágono de "
        "10 km) con altitud de -100 m o más, para que bahías y fondo marino no cuenten; si ninguna llega, se usan todas. "
        "Los hexágonos de agua son siempre llanos. Los umbrales de rugosidad son más bajos que los del mapa de EE. UU. "
        "(85 m y 260 m en hexágonos de 25 km) porque un hexágono más pequeño abarca menos relieve: se fijaron para que "
        "España tenga la misma proporción de tierra llana, de colinas y de montaña que con la regla de EE. UU. en "
        "hexágonos de 25 km.",
        "cover": "Sale de CORINE Land Cover 2018 (Copernicus), muestreado en una retícula dentro de cada hexágono español. "
        "Las clases de CORINE se cruzan con los grupos de estilo NLCD de abajo (la tabla de cruce está en la entrada de "
        "CORINE del Almanaque); el agua (5xx) y los píxeles sin datos se descartan, las proporciones son de los puntos de "
        "tierra restantes y el umbral urbano se aplica a la proporción urbanizada redondeada (CORINE 111, 112, 121–124 y "
        "133). Los hexágonos extranjeros (Portugal, Francia, Andorra, Marruecos) tienen cubierta 0 (ninguna).",
    },
}

RAIL_TIERS = {"main": "Línea principal", "secondary": "Línea secundaria"}
HUBS = {"L": "Hub grande", "M": "Hub mediano", "S": "Hub pequeño", "N": "Sin categoría de hub"}

# districts.badge_for: the city-type label of a capital and the badge's sentence ({lq} is already a Spanish number).
BADGE_TEXT = {"capital": "Capital", "seat": "Sede de gobierno", "share": "{name}: {ge}{lq} veces la cuota nacional de empleo",
              "decimal": ","}

MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre",
          "diciembre"]
_EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
              "November", "December"]
_DATE = re.compile(r"\b(\d{1,2}) (" + "|".join(_EN_MONTHS) + r") (\d{4})\b")
_VINTAGE_WORDS = [("(population ", "(población "), ("1 arc-minute", "1 minuto de arco"), (", edition ", ", edición ")]


def vintage(text: str | None) -> str | None:
    """A source vintage in Spanish: '1 January 2025' → '1 de enero de 2025' and the few English words the Spanish
    sources use."""
    if not text:
        return text
    out = _DATE.sub(lambda m: f"{m.group(1)} de {MONTHS[_EN_MONTHS.index(m.group(2))]} de {m.group(3)}", text)
    for en, es in _VINTAGE_WORDS:
        out = out.replace(en, es)
    return out


_INE_LICENCE = ("CC BY 4.0 (aviso legal del INE): reutilización comercial y no comercial citando la fuente como "
                "«Elaboración propia con datos del INE»; el INE no avala este mapa")
_REUSE = "Información del sector público, reutilizable citando la fuente (Ley 37/2007)"
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
    "ine_adrh": {
        "title": "Atlas de Distribución de Renta de los Hogares (ADRH): indicadores de renta media y mediana, tabla 30824",
        "license": _INE_LICENCE,
        "description": "Renta neta de los registros tributarios de la Agencia Tributaria y de las haciendas forales, "
        "cruzados con el Padrón, para cada municipio (y sus distritos y secciones censales, que aquí no se usan). El "
        "mapa toma la renta neta media por persona de cada municipio, del último año que publica el INE. Pueden faltar "
        "municipios pequeños (secreto estadístico): se quedan sin datos.",
        "used_for": ["Lente de renta"],
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
        "title": "Wikidata: Patrimonio Mundial, catedrales, museos y Bienes de Interés Cultural de España",
        "publisher": "Wikidata (Fundación Wikimedia y editores voluntarios)",
        "license": "CC0 1.0 (cesión al dominio público)",
        "description": "Los elementos de España declarados Patrimonio Mundial (agrupados por su número de sitio de la "
        "UNESCO), las catedrales y concatedrales, los museos y los Bienes de Interés Cultural, con sus coordenadas, del servicio "
        "SPARQL de Wikidata. Lo editan voluntarios: la cobertura se acerca a los registros oficiales, pero no es exacta.",
        "used_for": ["Maravillas de Patrimonio Mundial y catedrales", "Lente de patrimonio (Bienes de Interés Cultural)",
                     "Lente de museos"],
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
    "calidad_diferenciada": {
        "title": "Denominaciones de calidad: sus zonas (MAPA) y el registro de la UE (eAmbrosia)",
        "publisher": "Ministerio de Agricultura, Pesca y Alimentación; Comisión Europea (eAmbrosia)",
        "license": "MAPA: CC BY 4.0; eAmbrosia: aviso de reutilización de la Comisión Europea (CC BY 4.0)",
        "description": "La zona geográfica de cada denominación de origen protegida (DOP), indicación geográfica "
        "protegida (IGP), vino de calidad y vino de pago de España, tal como las cartografía el Ministerio (revisión de "
        "2017: las registradas después aún no tienen zona), y los nombres que España tiene en el registro de la UE.",
        "used_for": ["Lente de denominaciones de origen"],
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
}


def source(entry: dict) -> dict:
    """A sources.json entry with its Spanish texts (fields without a translation stay as the source gives them)."""
    return {**entry, **SOURCES.get(entry["id"], {}), "vintage": vintage(entry.get("vintage"))}

