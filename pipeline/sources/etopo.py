import csv

from ..core.source import Source, SourceInfo

ERDDAP = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180.csv"


def erddap_url(lat: tuple, lon: tuple, stride: int) -> str:
    return f"{ERDDAP}?altitude%5B({lat[0]}):{stride}:({lat[1]})%5D%5B({lon[0]}):{stride}:({lon[1]})%5D"


def window_file(lat: tuple, lon: tuple, stride: int) -> str:
    return f"etopo_lat{lat[0]}_{lat[1]}_lon{lon[0]}_{lon[1]}_stride{stride}.csv"


class Etopo(Source):
    info = SourceInfo(
        id="etopo",
        title="ETOPO1 global relief model",
        publisher="NOAA National Centers for Environmental Information (via ERDDAP)",
        homepage="https://www.ncei.noaa.gov/products/etopo-global-relief-model",
        license="Public domain (U.S. Government work)",
        description="Land elevation and ocean depth, sampled every ~9 km. Each hex's relief (flat, hills, mountains, "
        "peaks) comes from the mean and roughness (standard deviation) of the land samples inside it.",
        used_for=["Relief (hills, mountains)", "Hill-shading", "Ocean depth"],
    )
    # ETOPO1 (1 arc-minute) via NOAA ERDDAP, sampled every 5th point (~9 km). The window covers the
    # whole map rectangle (lower 48 plus the margin into Canada, Mexico and the oceans).
    STRIDE = 5
    WINDOWS = [((22, 56), (-131, -60))]  # ((lat0, lat1), (lon0, lon1)), one file each
    VINTAGE = "ETOPO1, 1 arc-minute, sampled every ~9 km"

    def _files(self) -> list[tuple[str, str]]:
        return [(erddap_url(lat, lon, self.STRIDE), window_file(lat, lon, self.STRIDE)) for lat, lon in self.WINDOWS]

    def fetch(self, force=False):
        for url, file in self._files():
            self.download(url, file, force=force)

    def process(self):
        lat, lon, alt = [], [], []
        for _, file in self._files():
            with open(self.raw_dir / file, newline="") as f:
                rows = csv.reader(f)
                next(rows), next(rows)  # header + units
                for la, lo, al in rows:
                    if al == "NaN":
                        continue
                    lat.append(round(float(la), 4))
                    lon.append(round(float(lo), 4))
                    alt.append(int(float(al)))
        return {
            "vintage": self.VINTAGE,
            "_files": [file for _, file in self._files()],
            "lat": lat,
            "lon": lon,
            "alt": alt,
        }
