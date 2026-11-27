"""Hours to Madrid by train (`transit.json`): the shortest timetabled journey to Madrid on one weekday, from every land
hex, with the stations and the passenger track of that day (DECISIONS E84–E87).

* **Madrid** is every stop inside the SIANE outline of municipality 28079.
* **Router**: a profile Connection Scan over the day's trains (pipeline/core/csa.py), CHANGE_MIN minutes to change
  trains, walks of up to WALK_KM in a straight line at WALK_KMH between stops. A stop's time is its shortest journey of
  the day.
* **Stations**: stops with the same id, or within CLUSTER_M of each other, are one station, named after its stop of
  the first feed (Renfe AV/LD, then Cercanías, then the others) with the most trains. A station's trains are the distinct trains that can be
  boarded there, by kind. A station off Spain (France, Portugal) is routed through but not shown.
* **Hex value**: the smallest stop time + straight-line distance ÷ ACCESS_KMH over the shown stations' stops within
  ACCESS_KM of the hex centre; null beyond (the islands have no trains in these feeds).
* **Track**: OpenStreetMap railways on hex links (`line_links`, the rule of the map's rail layer). Each consecutive stop
  pair of the day takes the shortest path on that graph (A*, straight-line heuristic), accepted when it is at most
  DETOUR × the straight line + DETOUR_KM; each link of an accepted path adds the pair's trains. A ghost link is one built
  from an Adif way that no train uses; Adif's metre gauge is judged only when the Renfe Feve feed is in the build.
"""

from __future__ import annotations

import heapq
import json
import math
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from ..core.csa import footpaths, km, profile, trip_connections
from ..core.geo import Shape, ShapeIndex
from ..core.gtfs import clock
from ..core.hexgrid import HexGrid
from ..core.lang import Num, Text, tr
from ..core.store import load_interim, load_interim_payload, write_web
from ..countries import active
from .cities import nearest_land, ring_search
from .infrastructure import line_links
from .lenses import percentile_domain
from .texts_es import MONTHS

REQUIRES = ["_world", "siane", "horarios_tren", "osm_ferrocarril", "world.json"]
PRODUCES = ["transit.json"]
COUNTRIES = ("es",)

MADRID = "28079"  # INE code of the municipality of Madrid
CHANGE_MIN = 10  # minutes to change trains (convention)
WALK_KM, WALK_KMH = 1.5, 4.5  # walks between stops (convention)
ACCESS_KM, ACCESS_KMH = 30, 40  # from a hex centre to a station, in a straight line (map convention)
CLUSTER_M = 300  # stops this close are one station
DETOUR, DETOUR_KM = 1.5, 15  # a stop pair's path may be this much longer than the straight line: track bends (~1.3) times hex steps (up to 2/√3)
SNAP_KM = 15  # a stop takes the nearest hex of the track graph this close
FASTEST_KMH = 350  # check: no journey beats the straight line at this speed
KINDS = ("ld", "md", "cer")
KIND_NAMES = {"ld": tr("Alta velocidad y larga distancia", "High speed and long distance"),
              "md": tr("Media distancia", "Medium distance"),
              "cer": tr("Cercanías y Rodalies", "Commuter trains (Cercanías and Rodalies)")}
FEED_NAMES = {"renfe_av_ld": tr("Renfe: alta velocidad, larga y media distancia",
                                "Renfe: high speed, long and medium distance"),
              "renfe_cercanias": tr("Renfe: Cercanías y Rodalies", "Renfe: Cercanías and Rodalies"),
              "ouigo": "Ouigo",
              "iryo": tr("Iryo (recopilación no oficial)", "Iryo (unofficial compilation)"),
              "renfe_feve": "Renfe Feve"}
FEED_ORDER = list(FEED_NAMES)
RAMP = ["#f6f9cf", "#c2e39f", "#74c49f", "#2f979c", "#1f5f86", "#1b2f57"]  # short (light) to long (dark)
_WEEKDAYS = {"es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
             "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]}
_EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
              "November", "December"]


# ------------------------------------------------------------------ dates


def day_text(d: date) -> Text:
    """'miércoles 9 de diciembre de 2026' / 'Wednesday 9 December 2026'."""
    return tr(f"{_WEEKDAYS['es'][d.weekday()]} {d.day} de {MONTHS[d.month - 1]} de {d.year}",
              f"{_WEEKDAYS['en'][d.weekday()]} {d.day} {_EN_MONTHS[d.month - 1]} {d.year}")


def week_text(a: date, b: date) -> Text:
    """'del 7 al 13' / '7 to 13 December' (the month on both ends when the week spans two)."""
    if a.month == b.month:
        return tr(f"del {a.day} al {b.day}", f"{a.day} to {b.day} {_EN_MONTHS[b.month - 1]}")
    return tr(f"del {a.day} de {MONTHS[a.month - 1]} al {b.day} de {MONTHS[b.month - 1]}",
              f"{a.day} {_EN_MONTHS[a.month - 1]} to {b.day} {_EN_MONTHS[b.month - 1]}")


# ------------------------------------------------------------------ stations


class UnionFind:
    def __init__(self, items):
        self.up = {x: x for x in items}

    def find(self, x):
        while self.up[x] != x:
            self.up[x] = self.up[self.up[x]]
            x = self.up[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.up[max(ra, rb)] = min(ra, rb)


def cluster(stops: dict[str, list]) -> list[list[str]]:
    """Stops within CLUSTER_M of each other, as groups of ids (stops = {id: [name, lon, lat, feed]})."""
    uf = UnionFind(stops)
    coords = {s: (v[1], v[2]) for s, v in stops.items()}
    for s, near in footpaths(coords, CLUSTER_M / 1000, 1).items():
        for j, _ in near:
            uf.union(s, j)
    groups = defaultdict(list)
    for s in stops:
        groups[uf.find(s)].append(s)
    return [sorted(g) for g in groups.values()]


def named_stop(group: list[str], stops: dict[str, list], trains: dict[str, int] | None = None) -> str:
    """The stop that names a station: the first feed's, then the one with the most trains to board, then the lowest
    id (Madrid-Puerta de Atocha, not the Cercanías platforms beside it that the AV/LD feed also lists)."""
    trains = trains or {}
    return min(group, key=lambda s: (FEED_ORDER.index(stops[s][3]) if stops[s][3] in FEED_ORDER else 99,
                                     -trains.get(s, 0), s))


def boardings(trips: list) -> dict[str, dict[str, set]]:
    """{stop: {kind: {(feed, train)}}}: the distinct trains one can board at each stop (not at its last call)."""
    out: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for feed, kind, _route, _number, train, calls in trips:
        for stop, _a, _d, board, _alight in calls[:-1]:
            if board:
                out[stop][kind].add((feed, train))
    return out


# ------------------------------------------------------------------ router


def connections(trips: list) -> list:
    conns = []
    for k, (_feed, _kind, _route, _number, _train, calls) in enumerate(trips):
        conns += trip_connections(str(k), [(s, a, d, bool(b), bool(al)) for s, a, d, b, al in calls])
    return conns


def route(trips: list, stops: dict[str, list], targets: set[str]):
    walks = footpaths({s: (v[1], v[2]) for s, v in stops.items()}, WALK_KM, WALK_KMH)
    return profile(connections(trips), targets, CHANGE_MIN * 60, walks)


def access_value(best_s: float, dist_km: float) -> float:
    """Seconds from a hex centre `dist_km` from a stop whose journey takes `best_s`."""
    return best_s + dist_km / ACCESS_KMH * 3600


def hex_values(grid: HexGrid, owner: list[int], points: list[tuple[float, float, float, int]]) -> tuple[list, list]:
    """(minutes, station) per cell: the best of best_s + access over the points (x, y, best_s, station) within
    ACCESS_KM of each land cell's centre; null elsewhere."""
    buckets = defaultdict(list)
    for p in points:
        buckets[(math.floor(p[0] / ACCESS_KM), math.floor(p[1] / ACCESS_KM))].append(p)
    values, station = [None] * grid.size, [None] * grid.size
    for i in range(grid.size):
        if owner[i] < 0:
            continue
        cx, cy = grid.center(*grid.col_row(i))
        bx, by = math.floor(cx / ACCESS_KM), math.floor(cy / ACCESS_KM)
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for x, y, t, st in buckets.get((bx + dx, by + dy), ()):
                    d = math.hypot(x - cx, y - cy)
                    if d <= ACCESS_KM and (best is None or access_value(t, d) < best[0]):
                        best = (access_value(t, d), st)
        if best is not None:
            values[i], station[i] = round(best[0] / 60), best[1]
    return values, station


# ------------------------------------------------------------------ track


def track_links(grid: HexGrid, proj, owner: list[int], ways: list[dict]) -> dict[tuple[int, int], set[str]]:
    """{(a, b): set of 'adif', 'adif_metre', 'other'}: the hex links of the OSM railways and who operates them."""
    out: dict[tuple[int, int], set[str]] = defaultdict(set)
    for w in ways:
        tags = w["tags"]
        adif = bool(re.search(r"\badif\b", tags.get("operator", ""), re.I))
        metre = tags.get("railway") == "narrow_gauge" or str(tags.get("gauge", "")).split(";")[0].strip() == "1000"
        what = ("adif_metre" if metre else "adif") if adif else "other"
        for link in line_links(grid, proj, owner, [w["line"]]):
            out[link].add(what)
    return dict(out)


def shortest_path(grid: HexGrid, adj: dict[int, list[int]], a: int, b: int, limit_km: float) -> list[int] | None:
    """Cells of the shortest path from a to b on the link graph (A*, straight-line heuristic), or None when there is
    none of at most `limit_km`."""
    centre = lambda c: grid.center(*grid.col_row(c))
    tb = centre(b)
    h = lambda c: math.dist(centre(c), tb)
    dist, prev = {a: 0.0}, {}
    heap = [(h(a), 0.0, a)]
    while heap:
        f, g, c = heapq.heappop(heap)
        if c == b:
            path = [b]
            while path[-1] != a:
                path.append(prev[path[-1]])
            return path[::-1]
        if g > dist.get(c, math.inf) or f > limit_km:
            continue
        pc = centre(c)
        for n in adj.get(c, ()):
            ng = g + math.dist(pc, centre(n))
            if ng < dist.get(n, math.inf):
                dist[n], prev[n] = ng, c
                heapq.heappush(heap, (ng + h(n), ng, n))
    return None


def snap(grid: HexGrid, adj: dict, x: float, y: float) -> int:
    """The nearest hex of the track graph within SNAP_KM of (x, y), or -1."""
    c = grid.cell_at(x, y)
    if c in adj:
        return c
    best = (SNAP_KM, -1)
    rings = math.ceil(SNAP_KM / (math.sqrt(3) * grid.radius)) + 1
    for _, n in ring_search(grid, max(c, 0), rings):
        if n in adj:
            d = math.dist(grid.center(*grid.col_row(n)), (x, y))
            if d <= best[0]:
                best = (d, n)
    return best[1]


def match_pairs(grid, links: dict, pairs: dict[tuple[str, str], int], where: dict[str, tuple[float, float]],
                abroad: set[str]) -> tuple[Counter, dict]:
    """Trains per link from the stop pairs ({(a, b): trains}) whose track path is accepted, and the tally."""
    adj = defaultdict(list)
    for a, b in links:
        adj[a].append(b)
        adj[b].append(a)
    trains, unmatched, skipped = Counter(), [], 0
    node = {s: snap(grid, adj, *where[s]) for s in where}
    for (u, v), n in sorted(pairs.items()):
        if u in abroad or v in abroad:
            skipped += 1
            continue
        a, b = node[u], node[v]
        straight = math.dist(where[u], where[v])
        limit = DETOUR * straight + DETOUR_KM
        path = shortest_path(grid, adj, a, b, limit) if a >= 0 and b >= 0 else None
        if path is None:
            unmatched.append((u, v))
            continue
        for p, q in zip(path, path[1:]):
            trains[(p, q) if p < q else (q, p)] += n
    return trains, {"pairs": len(pairs), "abroad": skipped, "unmatched": len(unmatched), "unmatched_pairs": unmatched}


def stop_pairs(trips: list) -> dict[tuple[str, str], int]:
    """{(a, b) with a < b: distinct trains that run between the two consecutive calls, either way}."""
    seen = defaultdict(set)
    for feed, _kind, _route, _number, train, calls in trips:
        for p, q in zip(calls, calls[1:]):
            if p[0] != q[0]:
                seen[tuple(sorted((p[0], q[0])))].add((feed, train))
    return {k: len(v) for k, v in seen.items()}


def ghosts(links: dict, served: Counter, feve: bool) -> list[tuple[int, int]]:
    """Adif links no train used (metre gauge only with the Feve feed in the build)."""
    judged = {"adif", "adif_metre"} if feve else {"adif"}
    return sorted(l for l, what in links.items() if what & judged and not served.get(l))


# ------------------------------------------------------------------ texts


def texts(day: date, week: tuple[date, date], feeds: list[dict]) -> dict:
    when, span = day_text(day), week_text(*week)
    feve = any(f["id"] == "renfe_feve" for f in feeds)
    left_out = tr("FGC, Euskotren, FGV, SFM, metros, tranvías y autobuses", "FGC, Euskotren, FGV, SFM, metros, trams and buses")
    metre = (lambda text: text) if feve else (lambda text: text + tr(
        " La vía métrica de Adif sin trenes no se dibuja: el horario de Renfe Feve no entra en el mapa.",
        " Adif's metre-gauge track without trains is not drawn: the Renfe Feve timetable is not in the map."))
    params = dict(change=CHANGE_MIN, walk=Num(WALK_KM, 1), walkkmh=Num(WALK_KMH, 1), access=ACCESS_KM, accesskmh=ACCESS_KMH)
    rules = {
        "day": tr(
            "El horario es el del {when}: el primer martes, miércoles o jueves dentro de todos los ficheros, después del "
            "día en que se escribió el más nuevo, en que cada operador y cada núcleo de Cercanías lleva al menos el 90 % "
            "de los trenes de su día de la misma semana más cargado. Los trenes que vienen del día anterior no cuentan.",
            "The timetable is that of {when}: the first Tuesday, Wednesday or Thursday inside every file, after the day "
            "the newest one was written, on which every operator and every Cercanías network runs at least 90% of the "
            "trains of its busiest day of the same weekday. Trains running on from the day before are not counted.",
        ).format(when=when),
        "router": tr(
            "El viaje más corto a cualquier estación del término municipal de Madrid entre todas las salidas del día "
            "(Connection Scan de perfiles), con {change} minutos como mínimo para cambiar de tren y paseos de hasta "
            "{walk} km en línea recta entre estaciones a {walkkmh} km/h. Se sube y se baja solo donde el horario lo "
            "permite.",
            "The shortest journey to any station in the municipality of Madrid over all of the day's departures "
            "(profile Connection Scan), with at least {change} minutes to change trains and walks of up to {walk} km in "
            "a straight line between stations at {walkkmh} km/h. Trains are boarded and left only where the timetable "
            "allows it.").format(**params),
        "access": tr(
            "Cada hexágono suma al viaje de la mejor estación a {access} km o menos de su centro la distancia en línea "
            "recta a {accesskmh} km/h, una convención del mapa y no un tiempo en coche. Más lejos, sin dato.",
            "Each hex adds to the journey of the best station within {access} km of its centre the straight-line distance "
            "at {accesskmh} km/h, a map convention rather than a driving time. Further away, no value.").format(**params),
        "trains": tr(
            "Los trenes de una estación son los trenes distintos que se pueden tomar allí ese día; un tren que el horario "
            "escribe varias veces (una por cada tramo en que se puede subir) cuenta una vez.",
            "A station's trains are the distinct trains that can be boarded there that day; a train the timetable writes "
            "several times (once for each stretch where it may be boarded) counts once."),
        "ghost": metre(tr(
            "Las vías de OpenStreetMap se pasan a enlaces entre hexágonos. Cada par de paradas seguidas toma el camino "
            "más corto por esas vías, si mide como mucho {detour} veces la línea recta más {detourkm} km, y suma sus "
            "trenes a cada enlace. Una vía fantasma es una vía de Adif por la que no pasa ningún tren de viajeros ese "
            "día; puede tener mercancías. Las vías de otros operadores sin tren no se dibujan.",
            "OpenStreetMap railways are snapped to links between hexes. Each pair of consecutive stops takes the shortest "
            "path along them, if it is at most {detour} times the straight line plus {detourkm} km, and adds its trains "
            "to each link. A ghost line is Adif track with no passenger train that day; it may carry freight. Other "
            "operators' track without trains is not drawn.").format(detour=Num(DETOUR, 1), detourkm=DETOUR_KM)),
    }
    lens = {
        "unit": tr("horas y minutos de viaje programado", "hours and minutes of timetabled travel"),
        "description": tr(
            "El viaje en tren más corto a Madrid el {when}, desde la mejor estación a {access} km o menos, más el "
            "camino hasta ella en línea recta a {accesskmh} km/h. Cuenta todas las salidas del día, con {change} minutos "
            "para cambiar de tren y paseos de hasta {walk} km entre estaciones. La velocidad de acceso, el radio y el "
            "tiempo de transbordo son convenciones del mapa, no tiempos medidos.",
            "The shortest train journey to Madrid on {when}, from the best station within {access} km, plus the way "
            "there in a straight line at {accesskmh} km/h. It counts every departure of the day, with {change} minutes "
            "to change trains and walks of up to {walk} km between stations. The access speed, the radius and the "
            "change time are map conventions, not measured times.").format(when=when, **params),
        "note": metre(tr(
            "Horario del {when} (semana {span}). Trenes de Renfe, Ouigo e Iryo (el de Iryo, de una recopilación no "
            "oficial). Fuera: {out}. Es el horario publicado: no cuenta retrasos, trenes llenos ni obras posteriores. "
            "Con la lente, las vías con tren van en líneas más gruesas cuantos más trenes, y las de Adif sin trenes de "
            "viajeros, en gris a trazos.",
            "Timetable of {when} (week of {span}). Trains of Renfe, Ouigo and Iryo (Iryo's from an unofficial "
            "compilation). Left out: {out}. It is the published timetable: delays, sold-out trains and later works are "
            "not counted. With the lens on, track with trains is drawn thicker the more trains it carries, and Adif "
            "track without passenger trains in dashed grey.").format(when=when, span=span, out=left_out)),
        "null_label": tr("A más de {access} km de una estación con tren a Madrid ese día",
                         "More than {access} km from a station with a train to Madrid that day").format(**params),
    }
    return {"rules": rules, "lens": lens,
            "vintage": tr("Horarios de Renfe, Ouigo e Iryo del {when}", "Timetables of Renfe, Ouigo and Iryo for {when}")
            .format(when=when)}


# ------------------------------------------------------------------ build


def build() -> None:
    world = load_interim("_world")
    grid, owner = HexGrid(**world["grid"]), world["owner"]
    proj = active().world_projection(world)
    tt = load_interim("horarios_tren")
    osm = load_interim("osm_ferrocarril")
    madrid = next(m for m in load_interim("siane")["municipalities"] if m["geoid"] == MADRID)
    madrid_shape = Shape([[proj(lon, lat) for lon, lat in r] for r in madrid["rings"]])
    stops, trips = tt["stops"], tt["trips"]
    xy = {s: proj(v[1], v[2]) for s, v in stops.items()}
    targets = {s for s in stops if madrid_shape.contains(*xy[s])}
    prof = route(trips, stops, targets)
    best = {s: prof.best(s) for s in prof.stops()}

    # stations
    board = boardings(trips)
    groups = cluster(stops)
    station_of, rows = {}, []
    per_stop = {s: sum(len(v) for v in kinds.values()) for s, kinds in board.items()}
    for g in groups:
        named = named_stop(g, stops, per_stop)
        x, y = xy[named]
        cell = grid.cell_at(x, y)
        in_spain = cell >= 0 and (owner[cell] >= 0 or (owner[cell] == -1 and any(owner[n] >= 0 for n in grid.neighbours(cell))))
        rows.append({"g": g, "name": stops[named][0], "x": x, "y": y, "spain": in_spain,
                     "cell": nearest_land(grid, owner, max(cell, 0), x, y, -1) if in_spain else -1})
    name_of = {}
    for r in rows:
        for s in r["g"]:
            name_of[s] = r["name"]
    shown = [r for r in rows if r["spain"]]
    abroad = {s for r in rows if not r["spain"] for s in r["g"]}

    def journey(r):
        js = [best[s] for s in r["g"] if best.get(s)]
        return min(js, key=lambda j: (j.duration, j.dep)) if js else None

    stations = []
    for r in shown:
        trains = [len(set().union(*(board.get(s, {}).get(k, set()) for s in r["g"]))) for k in KINDS]
        j = journey(r)
        rec = {"name": r["name"], "x": round(r["x"], 1), "y": round(r["y"], 1), "cell": r["cell"], "stops": r["g"],
               "trains": trains, "best": None}
        if all(s in targets for s in r["g"]):
            rec["madrid"] = True
        elif j is not None:
            legs = [[trips[int(l.trip)][2], trips[int(l.trip)][3], stops[l.frm][0], stops[l.to][0]] for l in j.legs]
            rec["best"] = {"min": round(j.duration / 60), "dep": clock(j.dep), "arr": clock(j.arr), "to": stops[j.to][0],
                           "changes": j.changes, "legs": legs}
        stations.append(rec)
    stations.sort(key=lambda s: (-sum(s["trains"]), s["name"]))
    index = {id(s): k for k, s in enumerate(stations)}
    for s in stations:
        for stop in s["stops"]:
            station_of[stop] = index[id(s)]

    # hexes
    points = [(*xy[s], 0 if s in targets else best[s].duration, station_of[s]) for s in station_of
              if s in targets or best.get(s)]
    values, station = hex_values(grid, owner, points)

    # track
    links = track_links(grid, proj, owner, osm["ways"])
    pairs = stop_pairs(trips)
    served, matching = match_pairs(grid, links, pairs, {s: xy[s] for s in stops}, abroad)
    feve = any(f["id"] == "renfe_feve" for f in tt["feeds"])
    ghost = ghosts(links, served, feve)
    matching["unmatched_pairs"] = [[name_of[u], name_of[v]] for u, v in matching["unmatched_pairs"]]

    day = date.fromisoformat(tt["date"])
    week = tuple(date.fromisoformat(d) for d in tt["week"])
    tx = texts(day, week, tt["feeds"])
    doc = {
        "version": 1,
        "vintage": tx["vintage"],
        "sources": ["horarios_tren", "osm_ferrocarril", "siane"],
        "date": tt["date"], "week": tt["week"],
        "feeds": [{"id": f["id"], "name": FEED_NAMES.get(f["id"], f["id"]), "trains": f["trains"], "window": f["window"],
                   "file_date": f["file_date"], "unofficial": f["unofficial"]} for f in tt["feeds"]],
        "params": {"change_min": CHANGE_MIN, "walk_km": WALK_KM, "walk_kmh": WALK_KMH, "access_km": ACCESS_KM,
                   "access_kmh": ACCESS_KMH},
        "rules": tx["rules"],
        "kinds": [{"id": k, "name": KIND_NAMES[k]} for k in KINDS],
        "lens": {"format": "duration", "scale": "linear", "domain": percentile_domain(values, False), "ramp": RAMP,
                 "higher_is": "bad", **tx["lens"], "values": values, "station": station},
        "stations": stations,
        "links": [[a, b, n] for (a, b), n in sorted(served.items())],
        "ghost": [[a, b] for a, b in ghost],
        "matching": matching,
    }
    write_web("transit.json", doc)
    land = sum(1 for o in owner if o >= 0)
    covered = sum(1 for i, v in enumerate(values) if v is not None and owner[i] >= 0)
    print(f"    {tt['date']}: {len(trips)} trips, {len(stations)} stations, {covered}/{land} land hexes "
          f"({covered / land:.0%}); {len(served)} served links, {len(ghost)} ghost; pairs {matching['pairs']}, "
          f"unmatched {matching['unmatched']}, abroad {matching['abroad']}")


# ------------------------------------------------------------------ check


def check(web_dir: Path) -> list[tuple[str, str]]:
    path = Path(web_dir) / "transit.json"
    if not path.exists():
        return [("NOTE", "transit.json not built (optional; run: build spain_transit --country es)")]
    doc = json.loads(path.read_text(encoding="utf-8"))
    out = []
    missing = [k for k in ("version", "date", "lens", "stations", "links", "ghost", "matching") if k not in doc]
    if missing:
        return [("FAIL", f"transit.json lacks {missing}")]
    wpath = Path(web_dir) / "world.json"
    if not wpath.exists():
        return [("NOTE", "transit.json: world.json unavailable, cell checks skipped")]
    world = json.loads(wpath.read_text(encoding="utf-8"))
    g = world["grid"]
    grid, owner = HexGrid(g["radius"], g["cols"], g["rows"]), world["owner"]
    n = grid.size
    lens = doc["lens"]
    for key in ("values", "station"):
        if len(lens.get(key) or []) != n:
            out.append(("FAIL", f"transit.json lens.{key} has {len(lens.get(key) or [])} cells, the grid {n}"))
    if any(lv == "FAIL" for lv, _ in out):
        return out
    neg = [i for i, v in enumerate(lens["values"]) if v is not None and v < 0]
    if neg:
        out.append(("FAIL", f"transit.json: {len(neg)} negative minutes (e.g. cell {neg[0]})"))
    sea = [i for i, v in enumerate(lens["values"]) if v is not None and owner[i] < 0]
    if sea:
        out.append(("FAIL", f"transit.json: {len(sea)} values off land"))
    ns = len(doc["stations"])
    bad_st = [i for i, v in enumerate(lens["station"]) if (v is None) != (lens["values"][i] is None) or
              (v is not None and not 0 <= v < ns)]
    if bad_st:
        out.append(("FAIL", f"transit.json: {len(bad_st)} cells whose station does not match their value"))
    off = [s["name"] for s in doc["stations"] if not (isinstance(s.get("cell"), int) and 0 <= s["cell"] < n and owner[s["cell"]] >= 0)]
    if off:
        out.append(("FAIL", f"transit.json: {len(off)} stations off land, e.g. {off[:3]}"))
    madrid = [(s["x"], s["y"]) for s in doc["stations"] if s.get("madrid")]
    fast = []
    for s in doc["stations"]:
        b = s.get("best")
        if b is None or not madrid:
            continue
        if b["min"] < 0:
            fast.append(f"{s['name']} {b['min']} min")
            continue
        d = min(math.dist((s["x"], s["y"]), m) for m in madrid)
        if b["min"] * 60 < d / FASTEST_KMH * 3600 - 60:
            fast.append(f"{s['name']} {b['min']} min for {d:.0f} km")
    if fast:
        out.append(("FAIL", f"transit.json: {len(fast)} journeys faster than {FASTEST_KMH} km/h in a straight line, "
                            f"e.g. {fast[:3]}"))

    def bad(link):
        a, b = link[:2]
        if not (isinstance(a, int) and isinstance(b, int) and 0 <= a < b < n):
            return "order/range"
        if b not in grid.neighbours(a):
            return "not neighbours"
        if owner[a] == -2 or owner[b] == -2 or (owner[a] < 0 and owner[b] < 0):
            return "no Spanish land end or a foreign end"
        return None

    for key in ("links", "ghost"):
        probs = [(l, why) for l in doc[key] if (why := bad(l))]
        if probs:
            out.append(("FAIL", f"transit.json {key}: {len(probs)} bad links, e.g. {probs[:2]}"))
    both = {tuple(l[:2]) for l in doc["links"]} & {tuple(l) for l in doc["ghost"]}
    if both:
        out.append(("FAIL", f"transit.json: {len(both)} links both served and ghost"))
    if any(not isinstance(l[2], int) or l[2] < 1 for l in doc["links"]):
        out.append(("FAIL", "transit.json links: trains must be a positive integer"))
    if not any(lv == "FAIL" for lv, _ in out):
        out.append(("PASS", f"transit.json: {ns} stations, {len(doc['links'])} served and {len(doc['ghost'])} ghost "
                            f"links, timetable of {doc['date']}"))
    land = sum(1 for o in owner if o >= 0)
    covered = sum(1 for i, v in enumerate(lens["values"]) if v is not None)
    out.append(("NOTE", f"transit.json: {covered} of {land} land hexes ({covered / land:.0%}) within "
                        f"{doc['params']['access_km']} km of a station with a train to Madrid"))
    m = doc["matching"]
    out.append(("NOTE", f"transit.json: {m['unmatched']} of {m['pairs']} stop pairs without a track path "
                        f"({m['abroad']} abroad), e.g. {m['unmatched_pairs'][:4]}"))
    size = path.stat().st_size
    out.append(("NOTE", f"transit.json is {size / 1e3:.0f} kB (loaded when the lens opens)"))
    return out
