"""Where Spain's regional languages are official, by municipality, from the laws that say so.

* Catalonia, the Balearic Islands, Galicia and the Basque Country: the language is co-official in every municipality
  (their Statutes of Autonomy); in Catalonia, Aranese (Occitan) is also official in Val d'Aran (Llei 35/2010).
* Navarre: the Ley Foral del Vascuence (18/1986) splits the region into a Basque-speaking, a mixed and a
  non-Basque-speaking zone; the zones' polygons come from the Government of Navarre's map server (IDENA).
* Valencian Community: the Llei d'Ús i Ensenyament del Valencià (4/1983), arts. 35 and 36, lists the municipalities
  where Castilian predominates; every other one is Valencian-speaking. The list is read from the BOE's consolidated
  text, in the 1983 spellings, and matched to today's municipalities.
* Asturias: Asturian is protected (Ley 1/1998), not co-official.
"""

from __future__ import annotations

import json
import re

from ...core.source import Source, SourceInfo
from .tls import SECTIGO_R46_DV_R36

NAVARRA = ("https://idena.navarra.es/ogc/wfs?service=WFS&version=2.0.0&request=GetFeature"
           "&typeNames=IDENA:PATRIM_Pol_Zonifling&outputFormat=application/json&srsName=EPSG:4326")
NAVARRA_FILE = "navarra_zonificacion_linguistica.geojson"
BOE = "https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/BOE-A-1984-1851/texto/bloque/a36"
BOE_FILE = "llei_4_1983_art36.xml"
NAVARRA_ZONES = {1: "basque", 2: "basque_mixed", 3: "spanish"}  # 4: common lands (Bardenas…), no municipality
PROVINCE = {"Alicante": "03", "Castellón": "12", "Valencia": "46"}


def castilian_valencia(xml: str) -> dict[str, list[str]]:
    """Art. 36 of Llei 4/1983 → {province code: [municipality names as the law spells them]}."""
    text = re.sub(r"<[^>]+>", " ", xml)
    out = {}
    for m in re.finditer(r"Provincia de (Alicante|Castellón|Valencia):\s*([^.]+)\.", text):
        out[PROVINCE[m.group(1)]] = [n.strip() for n in m.group(2).split(",") if n.strip()]
    if set(out) != set(PROVINCE.values()):
        raise RuntimeError(f"{BOE_FILE}: expected the three provinces' lists, got {sorted(out)}")
    return out


class LenguasEs(Source):
    info = SourceInfo(
        id="lenguas_es",
        title="Official regional languages by municipality (Navarre's language zones, Valencian-speaking area)",
        publisher="Gobierno de Navarra (IDENA); Agencia Estatal Boletín Oficial del Estado",
        homepage="https://idena.navarra.es/",
        license="IDENA: CC BY 4.0; BOE: legal texts, free reuse",
        description="The language zones of Navarre (Ley Foral 18/1986, as amended in 2017) and the municipalities where "
        "Castilian predominates in the Valencian Community (Llei 4/1983, art. 36); with the regions where a language "
        "is co-official everywhere, they give each municipality its official languages.",
        used_for=["Languages lens"],
    )

    def fetch(self, force=False):
        self.download(NAVARRA, NAVARRA_FILE, force=force, cafile=SECTIGO_R46_DV_R36)
        self.download(BOE, BOE_FILE, force=force, headers={"Accept": "application/xml"})

    def process(self):
        zones = []
        for f in json.loads((self.raw_dir / NAVARRA_FILE).read_text())["features"]:
            zone = NAVARRA_ZONES.get(f["properties"]["CZONALING"])
            if zone:
                zones.append({"zone": zone, "geometry": f["geometry"]})
        return {"vintage": "Ley Foral 18/1986 (IDENA, 2018); Llei 4/1983 (BOE)", "_files": [NAVARRA_FILE, BOE_FILE],
                "navarra_zones": zones,
                "valencia_castilian": castilian_valencia((self.raw_dir / BOE_FILE).read_text(encoding="utf-8"))}
