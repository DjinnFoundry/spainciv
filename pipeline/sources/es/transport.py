"""Spain's airports (AENA traffic, OurAirports positions) and ports (Puertos del Estado traffic and service areas)."""

from __future__ import annotations

import csv
import io
import re
import unicodedata

from ...core.geo import geojson_rings, load_geojson, ring_area, ring_centroid
from ...core.source import Source, SourceInfo
from ...core.xlsx import sheets

AENA_YEAR = 2025
AENA_URL = ("https://www.aena.es/sites/Satellite?blobcol=urldata&blobkey=id&blobtable=MungoBlobs"
            "&blobwhere=1576875166499&ssbinary=true")
AENA_FILE = f"aena_trafico_{AENA_YEAR}.xlsx"
OA_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"  # the project's own GitHub mirror
OA_FILE = "ourairports_airports.csv"
OA_TYPES = {"large_airport", "medium_airport", "small_airport", "heliport"}
STOP = {"aeropuerto", "airport", "int", "intl", "internacional", "helipuerto", "heliport", "base", "aerea", "del", "los",
        "las", "san"}
# AENA names that the word match would pair with the wrong OurAirports entry: AENA name → OurAirports name.
AIRPORT_ALIASES = {"LA PALMA": "La Palma Airport", "SABADELL": "Sabadell Airfield"}


def words(text: str) -> set[str]:
    t = unicodedata.normalize("NFD", (text or "").lower())
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    return {w for w in re.split(r"[^a-z0-9]+", t) if len(w) > 2 and w not in STOP}


class AenaAirports(Source):
    info = SourceInfo(
        id="aena_airports",
        title=f"Passengers, operations and cargo by airport, AENA network ({AENA_YEAR}, final)",
        publisher="Aena; airport positions from OurAirports",
        homepage="https://www.aena.es/es/estadisticas/inicio.html",
        license="AENA statistics: reproduction subject to Aena's legal notice; OurAirports: public domain",
        description=f"Passengers (arrivals plus departures), aircraft operations and cargo of the 47 airports and heliports "
        f"of the AENA network in {AENA_YEAR}. Each is placed with OurAirports, matched by the words of its name.",
        used_for=["Airports on the map"],
    )

    def fetch(self, force=False):
        self.download(AENA_URL, AENA_FILE, force=force, expect_binary=True)
        self.download(OA_URL, OA_FILE, force=force)

    def process(self):
        rows = sheets(self.raw_dir / AENA_FILE)[str(AENA_YEAR)]
        blocks = {"passengers": 1, "operations": 5, "cargo_kg": 9}
        traffic: dict[str, dict] = {}
        for key, col in blocks.items():
            for r in rows[7:]:
                name = (r[col] if len(r) > col else None) or ""
                if name.startswith("Total"):
                    break  # the Spanish network ends here; Aena's Brazilian airports follow
                if name and len(r) > col + 1 and r[col + 1]:
                    traffic.setdefault(name.strip(), {})[key] = round(float(r[col + 1]))
        oa = [r for r in csv.DictReader(io.StringIO((self.raw_dir / OA_FILE).read_text(encoding="utf-8")))
              if r["iso_country"] == "ES" and r["type"] in OA_TYPES and (r["icao_code"] or r["gps_code"])]
        by_name = {r["name"]: r for r in oa}

        def match(name: str) -> dict:
            if name in AIRPORT_ALIASES:
                return by_name[AIRPORT_ALIASES[name]]
            k = words(name.replace("-", " "))
            score = lambda r: len(k & (words(r["name"]) | words(r["municipality"]) | words(r["keywords"]) | words(r["home_link"])))
            best = max(oa, key=lambda r: (score(r), r["type"] == "large_airport", r["type"] == "medium_airport", bool(r["iata_code"])))
            if score(best) == 0:
                raise RuntimeError(f"no OurAirports match for AENA airport {name!r}")
            return best

        airports = []
        for name, t in traffic.items():
            r = match(name)
            airports.append({"id": r["icao_code"] or r["gps_code"], "iata": r["iata_code"] or None, "name": name.title(),
                             "matched": r["name"], "lon": float(r["longitude_deg"]), "lat": float(r["latitude_deg"]), **t})
        dup = {a["id"] for a in airports if sum(b["id"] == a["id"] for b in airports) > 1}
        if dup:
            raise RuntimeError(f"two AENA airports matched the same OurAirports entry: {dup}")
        return {"vintage": f"AENA {AENA_YEAR} (final)", "_files": [AENA_FILE, OA_FILE], "year": AENA_YEAR,
                "airports": sorted(airports, key=lambda a: -(a.get("passengers") or 0))}


PORTS_YEAR = 2025
PORTS_URL = "https://www.puertos.es/file-download/download/private/5465"
PORTS_FILE = f"puertos_trafico_{PORTS_YEAR}.xlsx"
WFS = ("https://geoserver.puertos.es/geoserver/puertos/wfs?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature"
       "&TYPENAMES=Puertos:TN.WaterTransportNetwork.PortArea&outputFormat=application/json&srsName=EPSG:4326")
WFS_FILE = "zonas_servicio_puertos.geojson"


class PuertosEstado(Source):
    info = SourceInfo(
        id="puertos_estado",
        title=f"Freight traffic by Port Authority ({PORTS_YEAR}) and port service areas",
        publisher="Puertos del Estado",
        homepage="https://www.puertos.es/datos/estadisticas/mensuales",
        license="Service areas: CC BY 4.0 (datos.gob.es); traffic statistics: Puertos del Estado's legal notice",
        description=f"Total freight traffic in tonnes of each of the 28 Port Authorities in {PORTS_YEAR} (December "
        "cumulative), placed at the land service area of their largest port.",
        used_for=["Ports on the map"],
    )

    def fetch(self, force=False):
        self.download(PORTS_URL, PORTS_FILE, force=force, expect_binary=True)
        self.download(WFS, WFS_FILE, force=force)

    def process(self):
        sheet = sheets(self.raw_dir / PORTS_FILE)["Total tráfico"]
        traffic = {}
        for r in sheet:
            if len(r) > 4 and r[0] and r[4] and re.fullmatch(r"[\d.Ee+-]+", str(r[4]).strip()):
                name = r[0].strip()
                if name.upper() != "TOTAL":
                    traffic[name] = round(float(r[4]))
        areas: dict[str, list] = {}
        for f in load_geojson(self.raw_dir / WFS_FILE):
            p = f["properties"]
            if (p.get("zona_servi") or "").lower().startswith("terrestre") and f.get("geometry"):
                for ring in geojson_rings(f["geometry"]):
                    areas.setdefault(p["ap"].strip(), []).append((abs(ring_area(ring)), ring, (p.get("pig") or "").replace("\xad", "")))
        ports = []
        for ap, tonnes in sorted(traffic.items(), key=lambda kv: -kv[1]):
            if ap not in areas:
                raise RuntimeError(f"no service area for Port Authority {ap!r}")
            _, ring, pig = max(areas[ap], key=lambda t: t[0])
            lon, lat = ring_centroid(ring)
            ports.append({"id": re.sub(r"[^a-z0-9]+", "-", ap.lower()), "name": ap, "main_port": pig, "tonnes": tonnes,
                          "lon": round(lon, 5), "lat": round(lat, 5)})
        return {"vintage": f"Puertos del Estado {PORTS_YEAR}", "_files": [PORTS_FILE, WFS_FILE], "year": PORTS_YEAR,
                "ports": ports}
