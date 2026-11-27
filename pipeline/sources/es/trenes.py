"""Passenger trains in Spain: the timetables of one day (GTFS) and the railway lines of OpenStreetMap.

`horarios_tren` reads four GTFS feeds straight from their zips (pipeline/core/gtfs.py): Renfe high speed, long and
medium distance; Renfe Cercanías and Rodalies; Ouigo; and Iryo, plus Renfe Feve when a NAP key is set and its file
covers the chosen day. Stops are Adif station codes in every feed once Ouigo's UIC prefix (0071) is stripped, so the
same station has the same id across feeds. The Renfe CSVs pad their fields with spaces and write `8:30:00`; Ouigo gives
its times in Europe/Paris and Europe/Amsterdam, which keep Madrid's offset all year.

The day (DECISIONS E85): the first Tuesday, Wednesday or Thursday inside every feed's window, after the day the newest
file was written, on which every feed, and every Cercanías network (the first two characters of its route_id), runs at
least 90 % of the trains of its busiest day of the same weekday in that window. A train is counted once however many
trips the feed writes for it (Renfe writes one per set of stops where it may be boarded). Only the cached files decide it, so the same raw data always gives the same
day. Buses in the feeds (route_type 3, or a route called "BUS") are not trains and are left out everywhere.

The NAP (nap.transportes.gob.es) wants an `ApiKey` header, read from the NAP_API_KEY environment variable at fetch time
only (it is never written to the repo or the manifest). Without it Ouigo comes from the Mobility Database copy of the
same NAP file, and Renfe Feve's own file is left out (the Feve trains that Renfe's AV/LD file carries are still in).

`osm_ferrocarril` is one cached Overpass query: every OpenStreetMap railway=rail or narrow_gauge way in Spain that is
not a siding, yard or spur (no `service` tag), with its geometry simplified to about 50 m and six tags.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

from ...core import gtfs
from ...core.fetch import read_manifest
from ...core.source import Source, SourceInfo
from ..mirta import simplify_line
from .osm_bares import OVERPASS

NAP = "https://nap.transportes.gob.es/api/Fichero/download/"
NAP_KEY = "NAP_API_KEY"
SHARE = 0.9  # a candidate day needs this share of the trips of its busiest same weekday, in every group
CANDIDATE_WEEKDAYS = (1, 2, 3)  # Tuesday, Wednesday, Thursday
BUS_TYPES = {"3"}  # GTFS route_type of a bus
# Renfe's route_short_name → the kind of train the map counts (long distance, medium distance, Cercanías).
RENFE_KINDS = {"AVE": "ld", "AVLO": "ld", "AVE Euromed": "ld", "Euromed": "ld", "Intercity": "ld", "Alvia": "ld",
               "Regional": "md", "Regional Exprés": "md", "AVANT": "md", "AVANT EXP": "md", "MD": "md"}


def uic_to_adif(stop: str) -> str:
    """Ouigo's stop ids are UIC codes: 0071 (Spain) + the Adif code. '007160000' → '60000'."""
    return stop[4:] if stop.startswith("0071") and len(stop) > 4 else stop


@dataclass(frozen=True)
class Feed:
    id: str
    label: str  # how the vintage names it
    file: str
    url: str
    publisher: str
    license: str
    kind: str | None = None  # every trip's kind; None: by Renfe's route_short_name (RENFE_KINDS)
    group: Callable[[str], str] | None = None  # route_id → the network compared on its own for the day rule
    stop: Callable[[str], str] = lambda s: s
    nap_file: int | None = None  # the NAP file id (then the key is used when set)
    mirror: str | None = None  # where the same file comes from without a NAP key; None: the feed needs the key
    optional: bool = False  # left out of the day rule; in the build only if its calendar covers the chosen day
    unofficial: bool = False


RENFE_LICENCE = ("CC BY 4.0 (data.renfe.com), with the conditions of Ley 37/2007: cite «Origen de los datos: Renfe "
                 "Operadora» and the date of the last update")
NAP_LICENCE = "MITRAMS open-data licence (nap.transportes.gob.es/licencia-datos): credit «Powered by MITRAMS»"
FEEDS = (
    Feed("renfe_av_ld", "Renfe AV/LD", "renfe_av_ld.zip", "https://ssl.renfe.com/gtransit/Fichero_AV_LD/google_transit.zip",
         "Renfe Operadora", RENFE_LICENCE),
    Feed("renfe_cercanias", "Renfe Cercanías", "renfe_cercanias.zip", "https://ssl.renfe.com/ftransit/Fichero_CER_FOMENTO/fomento_transit.zip",
         "Renfe Operadora", RENFE_LICENCE, kind="cer", group=lambda route: route[:2]),
    Feed("ouigo", "Ouigo", "ouigo.zip", NAP + "1766", "Ouigo España, via the NAP of the Ministerio de Transportes", NAP_LICENCE,
         kind="ld", stop=uic_to_adif, nap_file=1766, mirror="https://files.mobilitydatabase.org/mdb-2785/latest.zip"),
    Feed("iryo", "Iryo", "iryo.zip", "https://deryclem.github.io/iryo-gtfs/gtfs-iryo.zip",
         "Clément Desouche (clementdesouche.fr/gtfs), from the timetables on iryo.eu", "CC BY 4.0 (the compilation)",
         kind="ld", unofficial=True),
    Feed("renfe_feve", "Renfe Feve", "renfe_feve.zip", NAP + "1131", "Renfe Operadora (Feve), via the NAP of the Ministerio de Transportes",
         NAP_LICENCE, kind="cer", group=lambda route: route[:2], nap_file=1131, optional=True),
)


class Timetable:
    """One feed's zip: its calendar, routes and trips, and the calls of the trips of a day."""

    def __init__(self, feed: Feed, path):
        self.feed, self.zip = feed, zipfile.ZipFile(path)
        self.calendar = gtfs.Calendar(self.zip)
        self.routes = {rid: (name, rtype) for rid, name, rtype in
                       gtfs.columns(self.zip, "routes.txt", ("route_id", "route_short_name", "route_type"))}
        self.trips = {tid: (rid, sid, short) for rid, sid, tid, short in
                      gtfs.columns(self.zip, "trips.txt", ("route_id", "service_id", "trip_id", "trip_short_name"))
                      if not self.is_bus(rid)}

    def is_bus(self, route: str) -> bool:
        name, rtype = self.routes.get(route, ("", ""))
        return rtype in BUS_TYPES or name.upper() == "BUS"

    def kind(self, route: str) -> str:
        if self.feed.kind:
            return self.feed.kind
        name = self.routes[route][0]
        if name not in RENFE_KINDS:
            raise ValueError(f"{self.feed.id}: route_short_name {name!r} of route {route} is not in RENFE_KINDS")
        return RENFE_KINDS[name]

    def group(self, route: str) -> str:
        return f"{self.feed.id}:{self.feed.group(route)}" if self.feed.group else self.feed.id

    @staticmethod
    def train(trip_id: str, number: str) -> str:
        """The physical train of a trip: its number, or the trip itself where the feed numbers none (Cercanías)."""
        return number or trip_id

    def counts(self, days: list[date]) -> dict[str, dict[date, int]]:
        trips = ((sid, self.group(rid), self.train(tid, short)) for tid, (rid, sid, short) in self.trips.items())
        return gtfs.trains_by_day(trips, self.calendar, days)

    def file_date(self) -> date:
        """The newest file inside the zip: the date of the timetable's last update."""
        return max(date(*i.date_time[:3]) for i in self.zip.infolist())

    def day(self, day: date) -> tuple[list[list], dict[str, list]]:
        """[[feed, kind, route name, train number, train, [[stop, arr s, dep s, board, alight], …]], …] of the trips of
        `day` (`train` is the same for the trips the feed writes for one physical train), and {stop: [name, lon, lat]}
        of the stops they call at."""
        running = self.calendar.on(day)
        todays = {tid: t for tid, t in self.trips.items() if t[1] in running}
        calls = defaultdict(list)
        cols = ("trip_id", "stop_sequence", "stop_id", "arrival_time", "departure_time", "pickup_type", "drop_off_type")
        for tid, seq, stop, arr, dep, pickup, drop in gtfs.columns(self.zip, "stop_times.txt", cols):
            if tid in todays:
                arr, dep = arr or dep, dep or arr
                calls[tid].append((int(seq), self.feed.stop(stop), gtfs.seconds(arr), gtfs.seconds(dep),
                                   pickup != "1", drop != "1"))
        trips = []
        for tid in sorted(calls):
            rid, _, short = todays[tid]
            seq = [[s, a, d, int(b), int(al)] for _, s, a, d, b, al in sorted(calls[tid])]
            trips.append([self.feed.id, self.kind(rid), self.routes[rid][0], short, self.train(tid, short), seq])
        used = {c[0] for t in trips for c in t[-1]}
        stops = {}
        for sid, name, lat, lon in gtfs.columns(self.zip, "stops.txt", ("stop_id", "stop_name", "stop_lat", "stop_lon")):
            s = self.feed.stop(sid)
            if s in used and s not in stops:
                stops[s] = [name, round(float(lon), 6), round(float(lat), 6)]
        missing = used - set(stops)
        if missing:
            raise ValueError(f"{self.feed.id}: stops without coordinates: {sorted(missing)[:5]}")
        return trips, stops


def candidates(first: date, last: date) -> list[date]:
    return [d for d in gtfs.days_between(first, last) if d.weekday() in CANDIDATE_WEEKDAYS]


class HorariosTren(Source):
    info = SourceInfo(
        id="horarios_tren",
        title="Train timetables of one day in Spain: Renfe, Ouigo and Iryo (GTFS)",
        publisher="Renfe Operadora (data.renfe.com); Ouigo España via the NAP of the Ministerio de Transportes; "
                  "Clément Desouche (Iryo, unofficial)",
        homepage="https://data.renfe.com/",
        license="Renfe: CC BY 4.0, «Origen de los datos: Renfe Operadora» (Ley 37/2007); Ouigo: MITRAMS open-data "
                "licence, «Powered by MITRAMS»; Iryo: CC BY 4.0 (unofficial compilation of iryo.eu)",
        description="Every passenger train timetabled on one weekday in the GTFS feeds of Renfe (high speed, long and "
        "medium distance; Cercanías and Rodalies), Ouigo and Iryo, with each call's times and whether one may board or "
        "get off there. The day is the first Tuesday, Wednesday or Thursday on which every operator and every "
        "Cercanías network runs at least 90% of its usual trips for that weekday. Iryo publishes no open timetable of "
        "its own: its feed is an unofficial compilation of the timetables on iryo.eu. Buses are left out. «Origen de "
        "los datos: Renfe Operadora». «Powered by MITRAMS».",
        used_for=["Hours to Madrid by train lens", "Stations and passenger track while that lens is open"],
    )

    def fetch(self, force=False):
        key = os.environ.get(NAP_KEY, "").strip()
        for f in FEEDS:
            if f.nap_file and key:
                self.download(f.url, f.file, force=force, headers={"ApiKey": key}, expect_binary=True)
            elif f.nap_file and f.mirror:
                print(f"    {f.id}: no {NAP_KEY}, from the Mobility Database copy")
                self.download(f.mirror, f.file, force=force, expect_binary=True)
            elif f.nap_file:
                print(f"    {f.id}: skipped (needs {NAP_KEY})")
            else:
                self.download(f.url, f.file, force=force, expect_binary=True)

    def timetables(self) -> list[Timetable]:
        return [Timetable(f, self.raw_dir / f.file) for f in FEEDS if (self.raw_dir / f.file).exists()]

    def process(self):
        tables = self.timetables()
        core = [t for t in tables if not t.feed.optional]
        if {t.feed.id for t in core} != {f.id for f in FEEDS if not f.optional}:
            raise FileNotFoundError(f"horarios_tren: missing feeds, run fetch ({[t.feed.id for t in core]})")
        windows = {t.feed.id: t.calendar.window() for t in tables}
        # Days from the one after the newest file: a feed's first days can be a day already gone when it was written.
        first = max([windows[t.feed.id][0] for t in core] + [max(t.file_date() for t in core) + timedelta(days=1)])
        last = min(windows[t.feed.id][1] for t in core)
        days = gtfs.days_between(first, last)
        counts = {g: c for t in core for g, c in t.counts(days).items()}
        cands = candidates(first, last)
        day = gtfs.pick_day(counts, cands, SHARE)
        skipped = [{"date": d.isoformat(), "short": gtfs.failing(counts, d, SHARE)} for d in cands if d < day]
        used = [t for t in tables if not t.feed.optional or windows[t.feed.id][0] <= day <= windows[t.feed.id][1]]
        trips, stops, feeds = [], {}, []
        for t in used:
            ft, fs = t.day(day)
            trips += ft
            for s, v in fs.items():
                stops.setdefault(s, [*v, t.feed.id])  # the first feed's name and position (FEEDS order)
            m = read_manifest(self.id).get(t.feed.file, {})
            trains = len({(x[0], x[4]) for x in ft})
            feeds.append({"id": t.feed.id, "window": [d.isoformat() for d in windows[t.feed.id]], "trains": trains,
                          "file_date": t.file_date().isoformat(), "url": m.get("url", t.feed.url),
                          "publisher": t.feed.publisher, "license": t.feed.license, "unofficial": t.feed.unofficial})
        monday = day - timedelta(days=day.weekday())
        dated = ", ".join(f"{_long(t.file_date())} ({t.feed.label})" for t in used)
        return {
            "vintage": f"Timetable of {_long(day)}; files of {dated}",
            "_files": [t.feed.file for t in used],
            "date": day.isoformat(), "week": [monday.isoformat(), (monday + timedelta(days=6)).isoformat()],
            "share": SHARE, "window": [first.isoformat(), last.isoformat()], "skipped": skipped,
            "feeds": feeds, "stops": dict(sorted(stops.items())), "trips": trips,
        }


MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November",
          "December")


def _long(d: date) -> str:
    """date(2026, 12, 9) → '9 December 2026' (the form texts_es.vintage translates)."""
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


# --------------------------------------------------------------------------------------------------- OpenStreetMap

RAIL_QUERY = ('[out:json][timeout:900];area["ISO3166-1"="ES"][admin_level=2]->.es;'
              'way["railway"~"^(rail|narrow_gauge)$"][!"service"](area.es);out geom;')
RAIL_FILE = "railways.json"
RAIL_TAGS = ("railway", "gauge", "usage", "operator", "highspeed", "ref")
SIMPLIFY_DEG = 0.0005  # ~50 m, far finer than a 10 km hex


class OsmFerrocarril(Source):
    info = SourceInfo(
        id="osm_ferrocarril",
        title="Railway lines in Spain (OpenStreetMap, railway=rail and narrow_gauge)",
        publisher="OpenStreetMap contributors, via the Overpass API",
        homepage="https://wiki.openstreetmap.org/wiki/Key:railway",
        license="ODbL 1.0 (© OpenStreetMap contributors)",
        description="Every OpenStreetMap way in Spain tagged railway=rail or railway=narrow_gauge that is not a siding, "
        "yard or spur (no service tag), with its line simplified to about 50 m and its gauge, usage, operator, highspeed and ref tags. "
        "Volunteer-mapped: operator tags are the mappers'.",
        used_for=["Hours to Madrid by train lens: passenger and unused track"],
    )

    def fetch(self, force=False):
        self.download(OVERPASS + urllib.parse.quote(RAIL_QUERY), RAIL_FILE, force=force)

    def process(self):
        raw = json.loads((self.raw_dir / RAIL_FILE).read_text(encoding="utf-8"))
        ways = []
        for e in raw["elements"]:
            geom = e.get("geometry") or []
            if e.get("type") != "way" or len(geom) < 2:
                continue
            line = simplify_line([(p["lon"], p["lat"]) for p in geom], SIMPLIFY_DEG)
            tags = {k: e["tags"][k] for k in RAIL_TAGS if k in e.get("tags", {})}
            ways.append({"osm": e["id"], "tags": tags, "line": [[round(x, 5), round(y, 5)] for x, y in line]})
        ways.sort(key=lambda w: w["osm"])
        return {"vintage": f"OpenStreetMap, {read_manifest(self.id)[RAIL_FILE]['retrieved'][:10]}", "_files": [RAIL_FILE],
                "tags": list(RAIL_TAGS), "ways": ways}
