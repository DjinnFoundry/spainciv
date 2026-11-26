"""Spain's National Parks (Red de Parques Nacionales): official boundaries from the OAPN's GeoServer (WFS, GeoJSON)."""

from __future__ import annotations

import csv
import re
from pathlib import Path

from ...core.geo import geojson_rings, load_geojson
from ...core.source import Source, SourceInfo

LAYER = "LimitesParquesNacionalesZPP:view_red_oapn_limite_pn"
URL = ("https://sigred.oapn.es/geoserverOAPN/LimitesParquesNacionalesZPP/wfs?service=WFS&version=2.0.0&request=GetFeature"
       f"&typeNames={LAYER}&outputFormat=application/json&srsName=EPSG:4326")
FILE = "limites_parques_nacionales.geojson"
# sigred.oapn.es sends no intermediate certificate, and its root is newer than older system bundles: the intermediate
# (from the certificate's own AIA URL) and Sectigo's R46 root (from the macOS system root store), checked with
# `openssl verify`. SHA-256: intermediate 8C:54:C3:34:…:A4:EF:22:E0, root 7B:B6:47:A6:…:EC:38:F2:5A:06.
OAPN_CHAIN = Path(__file__).parent / "certs" / "sectigo-r46-dv-r36.pem"


VISITORS = Path(__file__).parent / "data" / "visitantes_parques_nacionales_2025.csv"
VISITORS_YEAR = 2025
PREFIX = re.compile(r"^Parque Nacional (Marítimo-Terrestre )?(de las |de los |de la |del |de )?", re.IGNORECASE)


def short_name(name: str) -> str:
    """'Parque Nacional de la Sierra de Guadarrama' → 'Sierra de Guadarrama'."""
    return PREFIX.sub("", name).strip() or name


def visitors() -> dict[str, int]:
    """Visitors per park (short name), transcribed from the OAPN's 2025 report, which is only published as a PDF."""
    with open(VISITORS, encoding="utf-8") as f:
        return {r["park"]: int(r["visitors"]) for r in csv.DictReader(line for line in f if not line.startswith("#"))}


def number(text: str | None) -> float | None:
    """'18.396,00' → 18396.0."""
    if not text:
        return None
    return float(text.replace(".", "").replace(",", "."))


class Oapn(Source):
    info = SourceInfo(
        id="oapn_parques",
        title="National Park boundaries (Red de Parques Nacionales)",
        publisher="Organismo Autónomo Parques Nacionales (OAPN), Ministerio para la Transición Ecológica",
        homepage="https://www.miteco.gob.es/es/parques-nacionales-oapn/red-parques-nacionales/sig/sig-descargas.html",
        license="Public-sector information, reuse permitted citing the source (Ley 37/2007); the service declares no "
        "access constraints or fees",
        description="The boundaries of Spain's 16 National Parks as declared by law, with their declaration date and "
        "official area, from the OAPN's map server, and their 2025 visitors from the OAPN's yearly report (a PDF, "
        "transcribed in pipeline/sources/es/data). The special protection area around the Sierra de Guadarrama is "
        "not a National Park and is left out.",
        used_for=["National Park wonders", "Protected land"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, cafile=OAPN_CHAIN)

    def process(self):
        parks = []
        for f in load_geojson(self.raw_dir / FILE):
            p = f["properties"]
            if p.get("Tipo Centro") != "Parque Nacional" or not p.get("Nombre", "").startswith("Parque Nacional"):
                continue
            parks.append({
                "name": p["Nombre"].strip(), "declared": p.get("Fecha Declaración"), "law": p.get("Declaración"),
                "area_ha": number(p.get("Superficie oficial (ha)")), "web": p.get("Web"),
                "rings": geojson_rings(f["geometry"]),
            })
        if len(parks) < 15:
            raise RuntimeError(f"{FILE}: only {len(parks)} National Parks")
        visits = visitors()
        for p in parks:
            p["visitors"] = visits.get(short_name(p["name"]))
        missing = [p["name"] for p in parks if p["visitors"] is None]
        if missing:
            raise RuntimeError(f"no visitor figure for {missing}")
        return {"vintage": f"OAPN, Red de Parques Nacionales; visitors {VISITORS_YEAR}", "_files": [FILE],
                "visitors_year": VISITORS_YEAR,
                "parks": sorted(parks, key=lambda p: p["name"])}
