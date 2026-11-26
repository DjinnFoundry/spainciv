"""CORINE Land Cover 2018 for Spain, read back from the IDEE land-cover WMS by its exact legend colours.

The Spanish INSPIRE land-cover service (IGN, servicios.idee.es) draws CORINE Land Cover 2018 at scales smaller than
1:50,000 with the standard CLC legend and no antialiasing, so every pixel's colour is exactly one CLC class. The map is
requested in EPSG:3035 at 500 m per pixel (CORINE's minimum mapping unit is 25 ha, a 500 m square) in a few tiles, and
each class is cross-walked to the NLCD code whose cover rules (world.py) describe it best.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from ...core.png import decode
from ...core.source import Source, SourceInfo

WMS = "https://servicios.idee.es/wms-inspire/ocupacion-suelo"
# servicios.idee.es chains to HARICA TLS RSA Root CA 2021, which older system CA bundles (macOS /etc/ssl/cert.pem) lack.
# Copied from the macOS system root store; SHA-256 D9:5D:0E:8E:DA:79:52:5B:F9:BE:B1:1B:14:D2:10:0D:32:94:98:5F:0C:62:D9:FA:BD:9C:D9:99:EC:CB:7B:1D.
IDEE_ROOT = Path(__file__).parent / "certs" / "harica-tls-rsa-root-ca-2021.pem"
LAYER = "LC.LandCoverSurfaces"
PIXEL_M = 500
TILE_PX = 1500
# EPSG:3035 windows (x0, y0, x1, y1), in metres: the peninsula, the Balearics, Ceuta and Melilla; the Canary Islands.
WINDOWS = {"peninsula": (2600000, 1400000, 4100000, 2600000), "canarias": (1500000, 950000, 2100000, 1150000)}

# CLC code → (RGB of the standard legend, name, NLCD code the cover rules use).
CLC = {
    111: ((230, 0, 77), "Continuous urban fabric", 24),
    112: ((255, 0, 0), "Discontinuous urban fabric", 22),
    121: ((204, 77, 242), "Industrial or commercial units", 23),
    122: ((204, 0, 0), "Road and rail networks", 23),
    123: ((230, 204, 204), "Port areas", 23),
    124: ((230, 204, 230), "Airports", 23),
    131: ((166, 0, 204), "Mineral extraction sites", 31),
    132: ((166, 77, 0), "Dump sites", 31),
    133: ((255, 77, 255), "Construction sites", 22),
    141: ((255, 166, 255), "Green urban areas", 21),
    142: ((255, 230, 255), "Sport and leisure facilities", 21),
    211: ((255, 255, 168), "Non-irrigated arable land", 82),
    212: ((255, 255, 0), "Permanently irrigated land", 82),
    213: ((230, 230, 0), "Rice fields", 82),
    221: ((230, 128, 0), "Vineyards", 82),
    222: ((242, 166, 77), "Fruit trees and berry plantations", 82),
    223: ((230, 166, 0), "Olive groves", 82),
    231: ((230, 230, 77), "Pastures", 81),
    241: ((255, 230, 166), "Annual crops associated with permanent crops", 82),
    242: ((255, 230, 77), "Complex cultivation patterns", 82),
    243: ((230, 204, 77), "Agriculture with significant natural vegetation", 82),
    244: ((242, 204, 166), "Agro-forestry areas (dehesas)", 81),
    311: ((128, 255, 0), "Broad-leaved forest", 41),
    312: ((0, 166, 0), "Coniferous forest", 42),
    313: ((77, 255, 0), "Mixed forest", 43),
    321: ((204, 242, 77), "Natural grasslands", 71),
    322: ((166, 255, 128), "Moors and heathland", 52),
    323: ((166, 230, 77), "Sclerophyllous vegetation", 52),
    324: ((166, 242, 0), "Transitional woodland-shrub", 52),
    331: ((230, 230, 230), "Beaches, dunes, sands", 31),
    332: ((204, 204, 204), "Bare rocks", 31),
    333: ((204, 255, 204), "Sparsely vegetated areas", 52),
    334: ((0, 0, 0), "Burnt areas", 52),
    335: ((166, 230, 204), "Glaciers and perpetual snow", 12),
    411: ((166, 166, 255), "Inland marshes", 95),
    412: ((77, 77, 255), "Peat bogs", 95),
    421: ((204, 204, 255), "Salt marshes", 95),
    422: ((230, 230, 255), "Salines", 31),
    423: ((166, 166, 230), "Intertidal flats", 11),
    511: ((0, 204, 242), "Water courses", 11),
    512: ((128, 242, 230), "Water bodies", 11),
    521: ((0, 255, 166), "Coastal lagoons", 11),
    522: ((166, 255, 230), "Estuaries", 11),
    523: ((230, 242, 255), "Sea and ocean", 11),
}
BY_RGB = {rgb: code for code, (rgb, _, _) in CLC.items()}
NO_DATA = "."
# One character per CLC class, so each raster row is a short string in the interim (as for NLCD).
CHAR = {code: chr(0x41 + k) for k, code in enumerate(sorted(CLC))}


def tiles(window: tuple[int, int, int, int]):
    """(name, bbox) of the TILE_PX-square tiles covering an EPSG:3035 window, west to east, north to south."""
    x0, y0, x1, y1 = window
    span = TILE_PX * PIXEL_M
    for ty, top in enumerate(range(y1, y0, -span)):
        for tx, left in enumerate(range(x0, x1, span)):
            yield f"{ty}_{tx}", (left, top - span, left + span, top)


def wms_url(bbox) -> str:
    return (f"{WMS}?service=WMS&version=1.1.1&request=GetMap&layers={LAYER}&styles=&srs=EPSG:3035"
            f"&bbox={','.join(map(str, bbox))}&width={TILE_PX}&height={TILE_PX}&format=image/png")


def classify(rows) -> tuple[list[str], Counter]:
    """Rows of (r, g, b) → rows of class characters; colours outside the legend (white = no data) become NO_DATA."""
    unknown: Counter = Counter()
    out = []
    for row in rows:
        chars = []
        for px in row:
            code = BY_RGB.get(px)
            if code is None:
                if px != (255, 255, 255) and px is not None:
                    unknown[px] += 1
                chars.append(NO_DATA)
            else:
                chars.append(CHAR[code])
        out.append("".join(chars))
    return out, unknown


class Corine(Source):
    info = SourceInfo(
        id="corine",
        title="CORINE Land Cover 2018 (via the IDEE land-cover WMS)",
        publisher="Copernicus Land Monitoring Service (EEA); served by the Instituto Geográfico Nacional (IDEE)",
        homepage="https://land.copernicus.eu/en/products/corine-land-cover/clc2018",
        license="CC BY 4.0 (scne.es) for the IDEE service; CORINE Land Cover is Copernicus data under its free, full "
        "and open data policy",
        description="Land cover in 44 CORINE classes for Spain, read from the IDEE INSPIRE land-cover map (EPSG:3035, "
        f"{PIXEL_M} m pixels, the size of CORINE's 25 ha minimum mapping unit) by the exact colours of the standard CLC "
        "legend. Each class is cross-walked to an NLCD class (built-up 111/112/12x → developed, arable and permanent "
        "crops → cultivated, 231 pastures and 244 dehesas → pasture, 31x forests, 321 grassland, 32x and 333 scrub, "
        "33x bare → barren, 4xx wetlands, 5xx water) so the map uses one set of cover rules for every country.",
        used_for=["Hex land cover (biomes)", "Forest / cropland / developed shares"],
    )

    def _tiles(self):
        return [(f"{name}_{tile}", bbox) for name, window in WINDOWS.items() for tile, bbox in tiles(window)]

    def fetch(self, force=False):
        for name, bbox in self._tiles():
            self.download(wms_url(bbox), f"clc2018_{name}_{PIXEL_M}m.png", force=force, expect_binary=True, cafile=IDEE_ROOT)

    def process(self):
        rasters, counts, unknown = [], Counter(), Counter()
        for name, (x0, y0, x1, y1) in self._tiles():
            w, h, rows = decode((self.raw_dir / f"clc2018_{name}_{PIXEL_M}m.png").read_bytes())
            if (w, h) != (TILE_PX, TILE_PX):
                raise ValueError(f"{name}: expected {TILE_PX}×{TILE_PX} px, got {w}×{h}")
            chars, bad = classify(rows)
            unknown.update(bad)
            if all(set(r) == {NO_DATA} for r in chars):
                continue  # open sea or foreign land only
            counts.update(c for r in chars for c in r)
            # Pixel centres: column 0 / row 0 is the top-left pixel; rows go south (dy < 0), as in the NLCD interim.
            rasters.append({"x0": x0 + PIXEL_M / 2, "dx": PIXEL_M, "y0": y1 - PIXEL_M / 2, "dy": -PIXEL_M,
                            "cols": w, "rows": chars})
        if unknown:
            share = sum(unknown.values()) / (sum(counts.values()) or 1)
            print(f"    warning: {sum(unknown.values())} pixels ({share:.3%}) in colours outside the CLC legend, kept as no data: "
                  f"{unknown.most_common(5)}")
        legend = {CHAR[code]: nlcd for code, (_, _, nlcd) in CLC.items()} | {NO_DATA: 0}
        by_class = {code: counts[CHAR[code]] for code in sorted(CLC) if counts[CHAR[code]]}
        return {
            "vintage": "CORINE Land Cover 2018",
            "_files": [f"clc2018_{name}_{PIXEL_M}m.png" for name, _ in self._tiles()],
            "crs": "EPSG:3035",
            "step_km": 1.0,
            "legend": legend,  # class character → NLCD code (the crosswalk); "." = no data
            "classes": {str(code): {"name": name, "rgb": list(rgb), "nlcd": nlcd} for code, (rgb, name, nlcd) in CLC.items()},
            "pixels_by_class": {str(k): v for k, v in by_class.items()},
            "rasters": rasters,
        }
