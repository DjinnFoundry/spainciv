"""ETOPO1 relief around Spain at full 1 arc-minute resolution (~1.85 km), via NOAA ERDDAP."""

from ...core.source import SourceInfo
from ..etopo import Etopo


class EtopoEs(Etopo):
    info = SourceInfo(
        id="etopo_es",
        title="ETOPO1 global relief model (Spain, full resolution)",
        publisher="NOAA National Centers for Environmental Information (via ERDDAP)",
        homepage="https://www.ncei.noaa.gov/products/etopo-global-relief-model",
        license="Public domain (U.S. Government work)",
        description="Land elevation and sea depth every 1 arc-minute (~1.85 km), about 25 samples per 10 km hex. Each "
        "hex's relief (flat, hills, mountains, peaks) comes from the mean and roughness of the land samples inside it.",
        used_for=["Relief (hills, mountains)", "Hill-shading", "Sea depth"],
    )
    STRIDE = 1
    # The map rectangle (peninsula, Balearics, Ceuta and Melilla plus the margin, reaching south-west to the Canary
    # inset box) in 2° latitude bands that don't share a row (ERDDAP drops very large requests), and the Canary
    # Islands themselves, which the projection shifts into that box.
    WINDOWS = [((lat, round(lat + 2 - 1 / 60, 4) if lat + 2 < 44.6 else 44.6), (-16.0, 6.0))
               for lat in (32.5, 34.5, 36.5, 38.5, 40.5, 42.5, 44.5)] + [((27.4, 29.6), (-18.4, -13.2))]
    VINTAGE = "ETOPO1, 1 arc-minute"

