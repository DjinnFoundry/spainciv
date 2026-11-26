"""Natural Earth 1:10m around Spain: neighbouring countries, lakes and reservoirs, rivers."""

from ...core.source import SourceInfo
from ..natural_earth import TAG, NaturalEarth, NaturalEarthRoads


class NaturalEarthEs(NaturalEarth):
    info = SourceInfo(
        id="natural_earth_es",
        title="Natural Earth 1:10m (countries, lakes, rivers) around Spain",
        publisher="Natural Earth",
        homepage="https://www.naturalearthdata.com/",
        license="Public domain",
        description="Neighbouring countries (Portugal, France, Andorra, Gibraltar, Morocco; shown fogged), lakes and "
        "reservoirs, and rivers. At 1:10m, so the 10 km hexes get the Ebro's, Tajo's and Guadalquivir's tributaries too. "
        f"Files are pinned to the natural-earth-vector release {TAG}.",
        used_for=["Foreign land (Portugal, France, Morocco)", "Lakes and reservoirs", "Rivers"],
    )

    FILES = ["ne_10m_admin_0_countries", "ne_10m_lakes", "ne_10m_rivers_lake_centerlines"]
    BBOX = (-19.5, 26.5, 5.5, 45.0)  # the peninsula, the Balearics, Ceuta, Melilla and the Canary Islands
    HOME = "ESP"
    SCALE = "1:10m"


class NaturalEarthRoadsEs(NaturalEarthRoads):
    info = SourceInfo(
        id="natural_earth_roads_es",
        title="Natural Earth 1:10m roads and railroads around Spain",
        publisher="Natural Earth",
        homepage="https://www.naturalearthdata.com/",
        license="Public domain",
        description="Motorways (autovías and autopistas), main roads and railroads as 1:10m line work. Shown as map art "
        "(roads and rail between hex centres), not as statistics: Natural Earth carries no traffic or owner data and "
        f"holds only the main lines. Files are pinned to the natural-earth-vector release {TAG}.",
        used_for=["Motorways and main roads on the map", "Railroads on the map"],
    )
    BBOX = NaturalEarthEs.BBOX
    LABEL = "Spain-window"

    def keep_road(self, p: dict) -> bool:
        return p.get("sov_a3") is None  # outside North America the field is empty; the builder clips foreign land

