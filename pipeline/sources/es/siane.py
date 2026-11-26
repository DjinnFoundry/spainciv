"""Municipal boundaries and municipal capitals of the IGN's SIANE (Atlas Nacional de España), as GeoPackages.

The rOpenSpain/mapSpain project republishes the SIANE base cartography (IGN, CC BY 4.0) as one GeoPackage per layer and
scale, pinned here to a commit so the content cannot change under the same URL. The 1:3M municipal layer has every
municipality with its INE code, its validity dates and the coordinates of its capital (the town centre), in ETRS89
lon/lat. `_x` is the peninsula and the Balearics, `_y` the Canary Islands.
"""

from __future__ import annotations

from ...core.geo import ring_area
from ...core.gpkg import features
from ...core.source import Source, SourceInfo
from .provinces import PROVINCES, display_name

COMMIT = "365286363cab2266d81f981093525edd50e2ce15"  # rOpenSpain/mapSpain, branch sianedata (SIANE edition 2026)
BASE = f"https://raw.githubusercontent.com/rOpenSpain/mapSpain/{COMMIT}/dist"
LAYERS = ["se89_3_admin_muni_a_x", "se89_3_admin_muni_a_y"]
MUNICIPALITY, SHARED = 99, 4  # t_ua: a municipality; a territory shared by several (condominio, INE code 53xxx)


class Siane(Source):
    info = SourceInfo(
        id="siane",
        title="SIANE municipal boundaries and capitals, 1:3 million (Atlas Nacional de España)",
        publisher="Instituto Geográfico Nacional (IGN), republished by rOpenSpain/mapSpain",
        homepage="https://www.ign.es/web/ane-area-ane",
        license="CC BY 4.0: Atlas Nacional de España (ANE), ign.es",
        description="Outlines of Spain's municipalities in force (INE code) and the position of each municipality's "
        "capital. Each hex belongs to the municipality and province most of its seven sample points fall in; provinces are "
        "the union of their municipalities and of the territories several municipalities share (condominios). Cities sit "
        "at their municipal capital.",
        used_for=["Map: land vs. water", "Province borders", "Municipality lookup", "City positions"],
    )

    def fetch(self, force=False):
        for layer in LAYERS:
            self.download(f"{BASE}/{layer}.gpkg", f"{COMMIT[:12]}/{layer}.gpkg", force=force, expect_binary=True)

    def process(self):
        municipalities, rings_by_prov = [], {}
        for layer in LAYERS:
            for p, kind, rings in features(self.raw_dir / COMMIT[:12] / f"{layer}.gpkg"):
                if p["fecha_baja"] is not None or kind != "polygon":
                    continue  # municipalities that no longer exist
                prov = p["id_prov"]
                rings = [[(round(x, 5), round(y, 5)) for x, y in r] for r in rings]
                rings_by_prov.setdefault(prov, []).extend(rings)
                if p["t_ua"] == MUNICIPALITY:
                    municipalities.append({
                        "geoid": p["id_ine"], "name": p["rotulo"], "state_fips": prov,
                        "centre": (round(p["x_cap"], 5), round(p["y_cap"], 5)), "rings": rings,
                    })
                elif p["t_ua"] != SHARED:
                    raise RuntimeError(f"{layer}: unknown unit type {p['t_ua']} for {p['id_ine']}")
        missing = sorted(set(PROVINCES) - set(rings_by_prov))
        if missing:
            raise RuntimeError(f"SIANE: no municipalities for provinces {missing}")
        provinces = [
            {"fips": code, "abbr": PROVINCES[code][0], "name": display_name(PROVINCES[code][1]),
             "rings": [r for r in rings_by_prov[code] if ring_area(r)]}
            for code in sorted(rings_by_prov)
        ]
        return {
            "vintage": "SIANE (IGN), edition 2026, 1:3M",
            "_files": [f"{COMMIT[:12]}/{layer}.gpkg" for layer in LAYERS],
            "provinces": provinces,
            "municipalities": sorted(municipalities, key=lambda m: m["geoid"]),
        }
