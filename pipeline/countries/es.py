"""Spain (spainciv): provinces, municipalities and urban areas on 10 km hexes.

Map projection: Lambert azimuthal equal-area centred on the peninsula (40°N 3.7°W), so north stays up and areas
are true. Rasters published in ETRS89-LAEA Europe (EPSG:3035, such as CORINE) are looked up with the exact
ellipsoidal projection (core.geo.LambertAzimuthalEllipsoid). The Canary Islands are drawn in an inset box in
the Atlantic south-west of the peninsula, as on most maps of Spain; their hexes keep their real lon/lat.
"""

import math

from ..core.geo import Inset, InsetProjection, LambertAzimuthal
from ..core.lang import tr
from ..sources.es.provinces import COMMUNITIES, COMMUNITY_NAMES
from .base import Country, Level, Page, country_dirs

CENTRE = (40.0, -3.7)  # lat, lon
CANARIAS = {"lon": (-18.4, -13.2), "lat": (27.5, 29.6)}
CANARIAS_BOX_CENTRE_KM = (-640.0, -600.0)  # where the islands' window centre lands (km from CENTRE, y up)


def projection() -> InsetProjection:
    base = LambertAzimuthal(*CENTRE)
    lon, lat = CANARIAS["lon"], CANARIAS["lat"]
    cx, cy = base((lon[0] + lon[1]) / 2, (lat[0] + lat[1]) / 2)
    dx, dy = CANARIAS_BOX_CENTRE_KM[0] - cx, CANARIAS_BOX_CENTRE_KM[1] - cy
    return InsetProjection(base, [Inset.make(base, "Canarias", lon, lat, round(dx, 3), round(dy, 3))])


_interim, _web = country_dirs("es")

COUNTRY = Country(
    id="es",
    name=tr("España", "Spain"),
    product="spainciv",
    site_url="spainciv.djinnfoundry.com",
    base_projection=projection,
    hex_radius_km=10 / math.sqrt(3),  # 10 km across the flats (pointy-top hexes: width = √3·radius)
    margin_km=80.0,
    region=Level(tr("Provincia", "Province"), tr("Provincias", "Provinces")),
    unit=Level(tr("Municipio", "Municipality"), tr("Municipios", "Municipalities")),
    metro=Level(tr("Área urbana", "Urban area"), tr("Áreas urbanas", "Urban areas")),
    currency="EUR",
    locale="es-ES",
    lang="es",
    # Published in Spanish and English (docs/SPAIN.md, Language): the data files are in Spanish, with an English
    # overlay next to each (core/lang.py); English numbers in en-IE, the English of a euro country ("€1.6T", "12.5%").
    locales={"es": "es-ES", "en": "en-IE"},
    capital_city="28079",  # Madrid (city ids are INE municipality codes)
    claim_tiny_regions=True,  # Ceuta and Melilla are smaller than a hex
    # Roughness inside a 87 km² hex is far lower than inside the US's 1,600 km² ones. These thresholds give Spain the
    # same land shares of flat / hills / mountains (26 / 56 / 18%) that the original 85 m / 260 m rule gives it on 25 km
    # hexes (calibrated on ETOPO1, see docs/SPAIN.md).
    relief_std_m=(32.0, 138.0),
    # The page, its social cards, its credits and the interface are in Spanish, and in English when the visitor picks it
    # (web/js/i18n/es, web/js/i18n/en-ES). Link previews only ever see the Spanish head and card.
    page=Page(
        title=tr("spainciv — España como mapa de un juego de estrategia", "spainciv — Spain as a strategy game map"),
        card_title=tr("España como mapa de un juego de estrategia", "Spain as a strategy game map"),
        description=tr(
            "La España real dibujada como un mapa de estrategia 4X: terreno en hexágonos, ciudades, provincias y lentes"
            " de población y renta, con datos públicos del INE, el IGN, Copernicus, la NOAA y Natural Earth.",
            "The real Spain drawn as a 4X strategy map: hex terrain, cities, provinces and lenses of population and"
            " income, from public data by INE, IGN, Copernicus, NOAA and Natural Earth.",
        ),
        image_alt=tr("Mapa de hexágonos de España con los rótulos de sus ciudades, al estilo de un juego de estrategia",
                     "Hex map of Spain with its cities labelled, in the style of a strategy game"),
        data_credit=tr("Datos: INE, IGN, MITECO, MAPA, Vivienda, Transportes, AENA, Puertos del Estado, IGME, AEMET, "
                       "Wikidata, OpenStreetMap",
                       "Data: INE, IGN, MITECO, MAPA, Vivienda, Transportes, AENA, Puertos del Estado, IGME, AEMET, "
                       "Wikidata, OpenStreetMap"),
        # SIANE boundaries are CC BY 4.0: the attribution the IGN asks for stays visible on the map (docs/SPAIN.md).
        notices=(tr("Límites: Atlas Nacional de España (ANE), CC BY 4.0, ign.es",
                    "Boundaries: Atlas Nacional de España (ANE), CC BY 4.0, ign.es"),),
        based_on=tr("Basado en {usaciv}, de Andrej Karpathy (MIT)", "Based on {usaciv} by Andrej Karpathy (MIT)"),
        game=True,
        sunset=True,
        # The fog of war counts what is explored by autonomous community (their provinces are the map's regions).
        explore=tuple((COMMUNITY_NAMES[code], tuple(provs)) for code, (_, provs) in COMMUNITIES.items()),
    ),
    interim_dir=_interim,
    web_data_dir=_web,
)
