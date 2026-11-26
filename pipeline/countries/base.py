"""The Country model (see pipeline/countries/__init__.py)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..core.geo import MapProjection
from ..core.paths import DATA, INTERIM, WEB, WEB_DATA


@dataclass(frozen=True)
class Level:
    """An administrative level as the UI names it: one and many."""

    one: str
    many: str


@dataclass(frozen=True)
class Page:
    """How the published page presents a country: web/index.html is written for the United States, so every other
    country gets its own title, social cards and map credits when the page is served or packaged (pipeline/site.py)."""

    title: str  # <title>
    card_title: str  # og:title, twitter:title
    description: str  # meta description, og:description, twitter:description
    image_alt: str  # og:image:alt, twitter:image:alt (the image is <site_url>/og-image.png)
    data_credit: str  # the data sources, on the map and on share images
    notices: tuple[str, ...] = ()  # licence notices that must stay visible on the map


@dataclass(frozen=True)
class Country:
    id: str
    name: str  # as shown on the map's banner
    product: str  # package and source-zip name
    site_url: str  # public address without scheme: printed on share images, absolute URLs of the social cards
    base_projection: Callable[[], object]  # km, y up, with to_web(); see core.geo
    hex_radius_km: float
    margin_km: float
    region: Level  # state / provincia
    unit: Level  # county / municipio
    metro: Level  # metro area / área urbana
    currency: str  # ISO 4217
    locale: str  # BCP 47, for number formatting
    lang: str
    off_map: frozenset[str] = frozenset()  # region codes not drawn (e.g. Alaska, Hawaii)
    capital_city: str | None = None  # city id of the national capital
    relief_std_m: tuple[float, float] = (85.0, 260.0)  # elevation std. dev. for hills, mountains (see world.py)
    claim_tiny_regions: bool = False  # a region with no hex by majority claims the hex at its centroid (see world.py)
    page: Page | None = None  # None: web/index.html as written (the United States)
    interim_dir: Path = INTERIM
    web_data_dir: Path = WEB_DATA
    extra: dict = field(default_factory=dict)

    def map_projection(self, min_x: float, max_y: float, margin: float) -> MapProjection:
        return MapProjection(min_x, max_y, margin, self.base_projection())

    def world_projection(self, world: dict) -> MapProjection:
        """The map projection stored in the `_world` interim."""
        return self.map_projection(**world["projection"])

    def web_block(self, projection: MapProjection) -> dict:
        """world.json `country`: what the browser needs to know about the country."""
        return {
            "id": self.id,
            "name": self.name,
            "product": self.product,
            "site_url": self.site_url,
            "lang": self.lang,
            "locale": self.locale,
            "currency": self.currency,
            "levels": {k: {"one": v.one, "many": v.many} for k, v in (("region", self.region), ("unit", self.unit), ("metro", self.metro))},
            "capital_city": self.capital_city,
            "projection": {**projection.base.to_web(), **projection.to_dict()},
        }


def country_dirs(country_id: str) -> tuple[Path, Path]:
    """(interim, web data) folders of a country other than the US: data/interim/<id>/ and sites/<id>/data/."""
    return DATA / "interim" / country_id, WEB.parent / "sites" / country_id / "data"
