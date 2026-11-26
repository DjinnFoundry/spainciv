"""The contiguous United States: Karpathy's original usaciv map."""

from ..core.geo import Albers
from .base import Country, Level

COUNTRY = Country(
    id="us",
    name="United States",
    product="usaciv",
    site_url="karpathy.ai/usaciv",
    base_projection=Albers,  # USGS lower-48 parameters (standard parallels 29.5° and 45.5°, lon0 96°W)
    hex_radius_km=25.0,
    margin_km=200.0,
    region=Level("State", "States"),
    unit=Level("County", "Counties"),
    metro=Level("Metro", "Metros"),
    currency="USD",
    locale="en-US",
    lang="en",
    off_map=frozenset({"02", "15", "60", "66", "69", "72", "78"}),  # AK, HI and the territories (state FIPS)
    capital_city="47900",  # Washington-Arlington-Alexandria CBSA
)
