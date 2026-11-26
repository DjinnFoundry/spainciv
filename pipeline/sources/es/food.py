"""Spain's protected food and drink names: the areas of every DOP, IGP and wine denomination (MAPA) and the EU register
(eAmbrosia) they belong to."""

from __future__ import annotations

import json

from ...core.geo import geojson_rings
from ...core.source import Source, SourceInfo
from .tls import GLOBALSIGN_R46

ZONES = ("https://wmts.mapama.gob.es/sig-api/ogc/features/v1/collections/alimentacion:CDZ_CalidadDiferenciada/items"
         "?f=json&limit={limit}&startIndex={start}")
PAGE = 25  # features per request: the whole collection is over 50 MB and one request times out
TOTAL = 301
EAMBROSIA = "https://webgate.ec.europa.eu/eambrosia-api/api/geographical-indications?size=2000&page={page}"
EAMBROSIA_PAGES = 2  # 2,000 names a page (the API's maximum); the register holds about 3,900
# The Ministry's designation types ('Denominación de Origen Protegida', 'Indicación Geográfica Protegida Bebida
# Espirituosa', 'Vino de Pago'…) by the words that set them apart, in order: the first match names the kind.
KIND = [("Pago", "Vino de pago"), ("Calidad", "Vino de calidad"), ("Origen", "DOP"), ("Protegida", "IGP"),
        ("Geográfica", "IG")]


def label(name: str, kind: str) -> str:
    return f"{name} ({next((short for word, short in KIND if word in kind), kind)})"


class CalidadDiferenciada(Source):
    info = SourceInfo(
        id="calidad_diferenciada",
        title="Protected food and drink names: their areas (MAPA) and the EU register (eAmbrosia)",
        publisher="Ministerio de Agricultura, Pesca y Alimentación; European Commission (eAmbrosia)",
        homepage="https://www.mapa.gob.es/es/cartografia-y-sig/ide/descargas/alimentacion/calidad-diferenciada.aspx",
        license="MAPA: CC BY 4.0; eAmbrosia: European Commission reuse notice (CC BY 4.0)",
        description="The geographical area of each Spanish protected designation of origin (DOP), protected "
        "geographical indication (IGP), quality wine and vino de pago, as the Ministry maps them (last revised in "
        "2017, so names registered since then have no area yet), and the count of names Spain has in the EU register.",
        used_for=["Food and drink lens"],
    )

    def fetch(self, force=False):
        for start in range(0, TOTAL, PAGE):
            self.download(ZONES.format(limit=PAGE, start=start), f"zonas_{start:03d}.json", force=force)
        self.discard("eambrosia.json")  # the first fetch took only the API's default page of 50
        for page in range(EAMBROSIA_PAGES):
            self.download(EAMBROSIA.format(page=page), f"eambrosia_{page}.json", force=force, cafile=GLOBALSIGN_R46)

    def process(self):
        names: dict[str, dict] = {}
        files = [f"zonas_{start:03d}.json" for start in range(0, TOTAL, PAGE)]
        for file in files:
            for f in json.loads((self.raw_dir / file).read_text())["features"]:
                p = f["properties"]
                if not f.get("geometry"):
                    continue
                n = names.setdefault(p["cal_ds_codigo"], {
                    "code": p["cal_ds_codigo"], "name": label(p["zon_ds_nombre"], p["tpr_ds_descripcion"]),
                    "family": p["fam_ds_nombre"], "rings": []})
                n["rings"] += [[(round(x, 4), round(y, 4)) for x, y in r] for r in geojson_rings(f["geometry"])]
        eambrosia = [f"eambrosia_{page}.json" for page in range(EAMBROSIA_PAGES)]
        pages = [json.loads((self.raw_dir / f).read_text()) for f in eambrosia]
        if sum(len(p["content"]) for p in pages) < pages[0]["totalElements"]:
            raise RuntimeError("eAmbrosia has more names than the pages fetched: raise EAMBROSIA_PAGES")
        register = [g for p in pages for g in p["content"] if "es" in (g.get("countries") or []) and not g["removedFlag"]
                    and g["registration"]["status"] == "REGISTERED"]
        by_type: dict[str, int] = {}
        for g in register:
            key = f"{g['giType']} {g['productType']}"
            by_type[key] = by_type.get(key, 0) + 1
        return {"vintage": "MAPA, Calidad diferenciada (2017 areas); eAmbrosia", "_files": files + eambrosia,
                "names": sorted(names.values(), key=lambda n: n["name"]), "eu_register": by_type,
                "eu_registered": len(register)}
