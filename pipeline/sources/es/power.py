"""Spain's power plants: powerplantmatching (peninsula, Balearics, Ceuta, Melilla) and OpenStreetMap (Canary Islands)."""

from __future__ import annotations

import csv
import io
import json
import re
import urllib.parse

from ...core.source import Source, SourceInfo

PPM_COMMIT = "2889ad9d1754a7ee4368b9282d7af835bf572ca2"
PPM_URL = f"https://raw.githubusercontent.com/PyPSA/powerplantmatching/{PPM_COMMIT}/powerplants.csv"
PPM_FILE = "powerplants.csv"
YEAR = 2026  # a unit with DateOut in or before this year is retired; one with DateIn after it is not built yet
# powerplantmatching (Fueltype, Technology) → our fuel. Anything else (biomass, waste, heat or hydrogen storage) is left out.
PPM_FUEL = {"Nuclear": "nuclear", "Hard Coal": "coal", "Lignite": "coal", "Natural Gas": "gas", "Oil": "oil",
            "Wind": "wind", "Solar": "solar", "Battery": "battery"}
OVERPASS = "https://overpass-api.de/api/interpreter?data="
CANARIES_BBOX = (27.5, -18.3, 29.5, -13.3)  # south, west, north, east
OSM_QUERY = (f'[out:json][timeout:90];nwr["power"="plant"]({",".join(map(str, CANARIES_BBOX))});out center tags;')
OSM_FILE = "osm_canarias_power_plants.json"
OSM_FUEL = {"diesel": "oil", "oil": "oil", "gas": "gas", "hydro": "hydro", "wind": "wind", "solar": "solar",
            "battery": "battery"}
MW = re.compile(r"^\s*([\d.,]+)\s*(GW|MW|kW)\s*$", re.IGNORECASE)


def mw_of(text: str | None) -> float | None:
    """OSM's plant:output:electricity ('697 MW', '800 kW', '1,2 GW') in MW; None for 'yes' or blanks."""
    m = MW.match(text or "")
    if not m:
        return None
    value = float(m.group(1).replace(",", "."))
    return value * {"gw": 1000, "mw": 1, "kw": 0.001}[m.group(2).lower()]


def ppm_fuel(row: dict) -> str | None:
    if row["Fueltype"] == "Hydro":
        return "pumped_storage" if row["Technology"] == "Pumped Storage" else "hydro"
    return PPM_FUEL.get(row["Fueltype"])


def year(text: str) -> int | None:
    return int(float(text)) if text else None


class PowerPlantsEs(Source):
    info = SourceInfo(
        id="power_plants_es",
        title="Power plants in Spain (powerplantmatching; OpenStreetMap for the Canary Islands)",
        publisher="PyPSA powerplantmatching (KIT and contributors); OpenStreetMap contributors",
        homepage="https://github.com/PyPSA/powerplantmatching",
        license="powerplantmatching data: CC BY 4.0; OpenStreetMap: ODbL 1.0",
        description="Every power plant powerplantmatching lists in Spain (a merge of ENTSO-E, GEM, OPSD, JRC and other "
        "registers), with its fuel, capacity, location and commissioning and retirement years, pinned to commit "
        f"{PPM_COMMIT[:9]}. It has no plant on the Canary Islands, so those come from OpenStreetMap's power=plant "
        "objects that state their capacity.",
        used_for=["Power plants on the map (resources)"],
    )

    def fetch(self, force=False):
        self.download(PPM_URL, PPM_FILE, force=force)
        self.download(OVERPASS + urllib.parse.quote(OSM_QUERY), OSM_FILE, force=force)

    def process(self):
        plants = []
        text = (self.raw_dir / PPM_FILE).read_text(encoding="utf-8")
        for r in csv.DictReader(io.StringIO(text)):
            fuel = ppm_fuel(r) if r["Country"] == "Spain" else None
            if not fuel or not r["lat"] or not r["Capacity"]:
                continue
            start, end = year(r["DateIn"]), year(r["DateOut"])
            if (end and end <= YEAR) or (start and start > YEAR):
                continue
            plants.append({"name": r["Name"], "fuel": fuel, "mw": float(r["Capacity"]), "lon": float(r["lon"]),
                           "lat": float(r["lat"]), "year": start, "offshore": r["Technology"] == "Offshore",
                           "source": "ppm"})
        for e in json.loads((self.raw_dir / OSM_FILE).read_text())["elements"]:
            t = e.get("tags", {})
            fuel = OSM_FUEL.get((t.get("plant:source") or "").split(";")[0])
            mw = mw_of(t.get("plant:output:electricity"))
            pos = e.get("center") or e
            if not fuel or not mw or "lat" not in pos:
                continue
            plants.append({"name": t.get("name") or t.get("operator") or f"OSM {e['type']} {e['id']}", "fuel": fuel,
                           "mw": mw, "lon": pos["lon"], "lat": pos["lat"], "year": None, "offshore": False,
                           "source": "osm"})
        return {"vintage": f"powerplantmatching {PPM_COMMIT[:9]}; OpenStreetMap (Canary Islands)",
                "_files": [PPM_FILE, OSM_FILE], "year": YEAR, "plants": plants}
