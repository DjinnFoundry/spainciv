"""Hours to Madrid by train (`transit.json`): the shortest timetabled journey to Madrid on one weekday, from every land
hex, with the stations and the passenger track of that day (DECISIONS E101–E104).

* **Madrid** is every stop inside the SIANE outline of municipality 28079.
* **Router**: a profile Connection Scan over the day's trains (pipeline/core/csa.py), CHANGE_MIN minutes to change
  trains, walks of up to WALK_KM in a straight line at WALK_KMH between stops, also at the start of a journey. A stop's
  time is its shortest journey of the day.
* **Stations**: stops with the same id, or within CLUSTER_M of each other, are one station, named after its stop of
  the first feed (Renfe AV/LD, then Cercanías, then the others) with the most long-distance trains. A station's trains
  are the distinct trains that can be boarded there, by kind; one with none is left out (but in Madrid). A station
  more than ABROAD_KM outside every SIANE municipality (France, Portugal) is routed through but not shown.
* **Hex value**: the smallest stop time + straight-line distance ÷ ACCESS_KMH over the shown stations' stops within
  ACCESS_KM of the hex centre; null beyond (the islands have no trains in these feeds).
* **Track**: OpenStreetMap railways on hex links (`line_links`, the rule of the map's rail layer). Each consecutive stop
  pair of the day takes the cheapest path on that graph for its class of train (high-speed track for long distance and
  AVANT, conventional for the rest: link_cost), accepted when it is at most DETOUR × the straight line + DETOUR_KM
  long; each link of an accepted path adds the pair's distinct trains. A ghost link is one built from an Adif way that
  no train uses, unless an unmatched pair runs near it or it is a short run beside served track of its line (ghosts);
  Adif's metre gauge is judged only when the Renfe Feve feed is in the build.
"""

from __future__ import annotations

import heapq
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from ..core.csa import footpaths, km, profile, trip_connections
from ..core.geo import Shape, ShapeIndex
from ..core.gtfs import clock
from ..core.hexgrid import HexGrid
from ..core.lang import Num, Text, tr
from ..core.store import load_interim, write_web
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
HS_PENALTY = 2  # a link of the other kind of track costs this many times its length (track_class)
HS_ROUTES = {"AVANT", "AVANT EXP"}  # medium-distance trains on high-speed track
ABROAD_KM = 0.5  # a stop further than this outside every SIANE municipality is abroad (in_spain)
NEAR_KM = 10  # an unused link this close to an unmatched stop pair is not called ghost
SHORT_RUN = 3  # a ghost run this short beside served track of the same line is not called ghost
FEED_MARGIN_DAYS = 7  # check notes a feed whose window ends sooner than this after the day
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
OPERATOR_FEEDS = {"ouigo": "Ouigo", "iryo": "Iryo"}  # feeds whose legs are named after the operator
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


def named_stop(group: list[str], stops: dict[str, list], board: dict | None = None) -> str:
    """The stop that names a station: the first feed's, then the one with the most long-distance trains to board, then
    the most trains of any kind, then the lowest id (Madrid-Puerta de Atocha, not the Cercanías platforms beside it
    that the AV/LD feed also lists and that board far more Cercanías trains)."""
    board = board or {}
    count = lambda s, kinds: sum(len(v) for k, v in board.get(s, {}).items() if k in kinds)
    return min(group, key=lambda s: (FEED_ORDER.index(stops[s][3]) if stops[s][3] in FEED_ORDER else 99,
                                     -count(s, {"ld"}), -count(s, KINDS), s))


def leg_label(trip: list) -> str:
    """How a leg names its train: 'AVE 02061', 'C6', 'Ouigo 6540' (the feed writes 'TGV' and 'TGV 6540'), 'Iryo 06083'
    (the compilation names no route)."""
    feed, _kind, route, number = trip[:4]
    if feed in OPERATOR_FEEDS:
        return f"{OPERATOR_FEEDS[feed]} {number.removeprefix(route).strip()}".strip()
    return f"{route} {number}".strip()


def in_spain(spain: ShapeIndex, x: float, y: float) -> bool:
    """Inside a SIANE municipality, or at most ABROAD_KM outside one. The outline is generalised and leaves a few
    Spanish stations on the coast and on the Miño a few metres outside (Santa Susanna 20 m, Pousa-Crecente 10 m); the
    nearest stations abroad lie 0.8 km or more beyond it (Cerbère 0.8, La Tor de Querol 1.2, Valença 1.5)."""
    if spain.locate(x, y) >= 0:
        return True
    gx, gy = int(x // spain.cell), int(y // spain.cell)
    near = {k for dx in (-1, 0, 1) for dy in (-1, 0, 1) for k in spain.buckets.get((gx + dx, gy + dy), ())}
    for k in near:
        sh = spain.shapes[k]
        x0, y0, x1, y1 = sh.bbox
        if not (x0 - ABROAD_KM <= x <= x1 + ABROAD_KM and y0 - ABROAD_KM <= y <= y1 + ABROAD_KM):
            continue
        for r in sh.rings:
            if any(_seg_dist((x, y), a, b) <= ABROAD_KM for a, b in zip(r, r[1:] + r[:1])):
                return True
    return False


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


@dataclass
class Track:
    """What runs on one hex link: who operates its ways ('adif', 'adif_metre', 'other'), whether any is high-speed
    track (OSM highspeed=yes) or conventional, and their line numbers (OSM `ref`)."""
    what: set = field(default_factory=set)
    hs: bool = False
    conv: bool = False
    refs: set = field(default_factory=set)


def track_links(grid: HexGrid, proj, owner: list[int], ways: list[dict]) -> dict[tuple[int, int], Track]:
    """{(a, b): Track}: the hex links of the OSM railways."""
    out: dict[tuple[int, int], Track] = defaultdict(Track)
    for w in ways:
        tags = w["tags"]
        adif = bool(re.search(r"\badif\b", tags.get("operator", ""), re.I))
        metre = tags.get("railway") == "narrow_gauge" or str(tags.get("gauge", "")).split(";")[0].strip() == "1000"
        what = ("adif_metre" if metre else "adif") if adif else "other"
        hs = tags.get("highspeed") == "yes"
        refs = {r.strip() for r in str(tags.get("ref", "")).split(";") if r.strip()}
        for link in line_links(grid, proj, owner, [w["line"]]):
            t = out[link]
            t.what.add(what)
            t.refs |= refs
            if hs:
                t.hs = True
            else:
                t.conv = True
    return dict(out)


def track_class(kind: str, route: str) -> str:
    """'hs' for the trains that keep to high-speed track where there is some (long distance, AVANT), else 'conv'."""
    return "hs" if kind == "ld" or route in HS_ROUTES else "conv"


def link_cost(track: Track, cls: str, km_: float) -> float:
    """A link's length, HS_PENALTY times longer on track of the other class: of two parallel lines, a train takes its
    own."""
    own = track.hs if cls == "hs" else track.conv
    return km_ if own else km_ * HS_PENALTY


def shortest_path(grid: HexGrid, adj: dict[int, list[int]], a: int, b: int, limit_km: float,
                  cost=None) -> list[int] | None:
    """Cells of the cheapest path from a to b on the link graph (A*, straight-line heuristic; `cost(p, q, km)` the
    price of a link, its length by default), or None when there is none of at most `limit_km` long."""
    centre = lambda c: grid.center(*grid.col_row(c))
    cost = cost or (lambda p, q, d: d)
    tb = centre(b)
    h = lambda c: math.dist(centre(c), tb)
    dist, prev, length = {a: 0.0}, {}, {a: 0.0}
    heap = [(h(a), 0.0, a)]
    while heap:
        _f, g, c = heapq.heappop(heap)
        if c == b:
            path = [b]
            while path[-1] != a:
                path.append(prev[path[-1]])
            return path[::-1]
        if g > dist.get(c, math.inf) or length[c] + h(c) > limit_km:
            continue
        pc = centre(c)
        for n in adj.get(c, ()):
            d = math.dist(pc, centre(n))
            ng = g + cost(c, n, d)
            if ng < dist.get(n, math.inf):
                dist[n], prev[n], length[n] = ng, c, length[c] + d
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


def path_km(grid: HexGrid, path: list[int]) -> float:
    return sum(math.dist(grid.center(*grid.col_row(p)), grid.center(*grid.col_row(q))) for p, q in zip(path, path[1:]))


def match_pairs(grid, links: dict, pairs: dict[tuple[str, str, str], set], where: dict[str, tuple[float, float]],
                abroad: set[str]) -> tuple[dict, dict]:
    """The trains of each link ({(a, b): {(feed, train)}}) from the stop pairs ({(stop, stop, class): trains}) whose
    track path is accepted, and the tally. A pair takes the cheapest path for its class (link_cost) when that is short
    enough, else the shortest one; either must be at most DETOUR × the straight line + DETOUR_KM long."""
    adj = defaultdict(list)
    for a, b in links:
        adj[a].append(b)
        adj[b].append(a)
    trains: dict[tuple[int, int], set] = defaultdict(set)
    unmatched, skipped = [], 0
    node = {s: snap(grid, adj, *where[s]) for s in where}
    key = lambda p, q: (p, q) if p < q else (q, p)
    for (u, v, cls), who in sorted(pairs.items()):
        if u in abroad or v in abroad:
            skipped += 1
            continue
        a, b = node[u], node[v]
        limit = DETOUR * math.dist(where[u], where[v]) + DETOUR_KM
        path = None
        if a >= 0 and b >= 0:
            path = shortest_path(grid, adj, a, b, limit, lambda p, q, d: link_cost(links[key(p, q)], cls, d))
            if path is None or path_km(grid, path) > limit:
                path = shortest_path(grid, adj, a, b, limit)
        if path is None:
            unmatched.append((u, v))
            continue
        for p, q in zip(path, path[1:]):
            trains[key(p, q)] |= who
    unmatched = sorted(set(unmatched))
    return dict(trains), {"pairs": len({(u, v) for u, v, _ in pairs}), "abroad": skipped, "unmatched": len(unmatched),
                          "unmatched_pairs": unmatched}


def stop_pairs(trips: list) -> dict[tuple[str, str, str], set]:
    """{(a, b, class) with a < b: the distinct trains ((feed, train)) that run between the two consecutive calls,
    either way}; class is track_class of the trip. A train the feed writes as several trips with different calls
    is one train on every link the pairs share (match_pairs unites the sets)."""
    seen = defaultdict(set)
    for feed, kind, route, _number, train, calls in trips:
        cls = track_class(kind, route)
        for p, q in zip(calls, calls[1:]):
            if p[0] != q[0]:
                seen[(*sorted((p[0], q[0])), cls)].add((feed, train))
    return dict(seen)


def _seg_dist(p, a, b) -> float:
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    u = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2)) if l2 else 0.0
    return math.hypot(px - (ax + u * dx), py - (ay + u * dy))


def runs(links: list[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    """The links grouped into connected runs (links sharing a cell)."""
    uf = UnionFind({c for l in links for c in l})
    for a, b in links:
        uf.union(a, b)
    out = defaultdict(list)
    for l in links:
        out[uf.find(l[0])].append(l)
    return list(out.values())


def ghosts(grid: HexGrid, links: dict, served: dict, feve: bool,
           unmatched: list[tuple[tuple[float, float], tuple[float, float]]]) -> tuple[list[tuple[int, int]], dict]:
    """Adif links no train used (metre gauge only with the Feve feed in the build), and the tally. Left out, as not
    known: a link within NEAR_KM of the straight line of a stop pair with no track path (its trains may run there),
    and the links of a line (OSM ref) whose unused run is SHORT_RUN links or fewer and touches served track of the same
    line, which is how a path that took the parallel track looks."""
    judged = {"adif", "adif_metre"} if feve else {"adif"}
    centre = lambda c: grid.center(*grid.col_row(c))
    mid = lambda l: tuple((u + v) / 2 for u, v in zip(centre(l[0]), centre(l[1])))
    cand = [l for l, t in links.items() if t.what & judged and not served.get(l)]
    near = {l for l in cand if any(_seg_dist(mid(l), a, b) <= NEAR_KM for a, b in unmatched)}
    cand = [l for l in cand if l not in near]
    served_refs = defaultdict(set)
    for l in served:
        for c in l:
            served_refs[c] |= links[l].refs
    short, n_short = set(), 0
    for ref in sorted(set().union(set(), *(links[l].refs for l in cand))):
        for run in runs([l for l in cand if ref in links[l].refs]):
            if len(run) <= SHORT_RUN and any(ref in served_refs[c] for l in run for c in l):
                short |= set(run)
                n_short += 1
    kept = sorted(l for l in cand if l not in short)
    return kept, {"ghost_runs": len(runs(kept)), "near_unmatched": len(near), "short_runs": n_short}


def hs_ghosts(links: dict, served: dict, ghost: list[tuple[int, int]]) -> int:
    """High-speed ghost links that share a cell and a line (OSM ref) with served high-speed track: the trains of that
    line are matched next to them, so the link is more likely a matching artefact than track with no trains (check
    fails on any)."""
    by_cell = defaultdict(set)
    for l in served:
        if links[l].hs:
            for c in l:
                by_cell[c] |= links[l].refs
    return sum(1 for l in ghost if links[l].hs and links[l].refs & (by_cell[l[0]] | by_cell[l[1]]))


# ------------------------------------------------------------------ texts


def date_text(d: date) -> Text:
    """'2 de julio de 2026' / '2 July 2026'."""
    return tr(f"{d.day} de {MONTHS[d.month - 1]} de {d.year}", f"{d.day} {_EN_MONTHS[d.month - 1]} {d.year}")


FEED_LABELS = {"renfe_av_ld": "Renfe AV/LD", "renfe_cercanias": "Renfe Cercanías", "ouigo": "Ouigo", "iryo": "Iryo",
               "renfe_feve": "Renfe Feve"}  # how the day rule names each file (the same in both languages)


def _join(parts: list[Text]) -> Text:
    """A list of bilingual phrases joined with commas and a last 'y' / 'and'."""
    out = {}
    for lang, last in (("es", " y "), ("en", " and ")):
        items = [p[lang] for p in parts]
        out[lang] = items[0] if len(items) == 1 else ", ".join(items[:-1]) + last + items[-1]
    return tr(out["es"], out["en"])


def texts(day: date, week: tuple[date, date], feeds: list[dict], window: tuple[date, date] | None = None,
          unmatched: int = 0, stranded: int = 0, cuts: list[dict] | None = None) -> dict:
    """The rules, the lens description and note and the vintage. `window`: the days every feed covers (the day rule
    compares within it); `unmatched`: stop pairs with no track path; `stranded`: stations with trains and no journey
    to Madrid; `cuts`: cut_lines."""
    when, span = day_text(day), week_text(*week)
    window = window or week
    feve = any(f["id"] == "renfe_feve" for f in feeds)
    left_out = tr("FGC, Euskotren, FGV, SFM, metros, tranvías y autobuses", "FGC, Euskotren, FGV, SFM, metros, trams and buses")
    params = dict(change=CHANGE_MIN, walk=Num(WALK_KM, 1), walkkmh=Num(WALK_KMH, 1), access=ACCESS_KM, accesskmh=ACCESS_KMH)
    others = sum(1 for d in range((window[1] - window[0]).days + 1)
                 if (window[0].toordinal() + d) % 7 == day.toordinal() % 7) - 1
    wd = _WEEKDAYS["en"][day.weekday()]
    dated = [(FEED_LABELS.get(f["id"], f["id"]), date_text(date.fromisoformat(f["file_date"])))
             for f in feeds if f.get("file_date")]
    files = tr(" Ficheros: " + "; ".join(f"{n}, del {d['es']}" for n, d in dated) + ".",
               " Files: " + "; ".join(f"{n}, of {d['en']}" for n, d in dated) + ".") if dated else ""
    rules = {
        "day": tr(
            "El horario es el del {when}: el primer martes, miércoles o jueves dentro de todos los ficheros, después del "
            "día en que se escribió el más nuevo, en que cada operador y cada núcleo de Cercanías lleva al menos el 90 % "
            "de los trenes de su día de la misma semana más cargado. Los ficheros solo coinciden {overlap}, "
            "así que ese día se compara con {others} {weekday} más. Los trenes que vienen del día anterior no cuentan.",
            "The timetable is that of {when}: the first Tuesday, Wednesday or Thursday inside every file, after the day "
            "the newest one was written, on which every operator and every Cercanías network runs at least 90% of the "
            "trains of its busiest day of the same weekday. The files only overlap from {overlap}, so that day "
            "is compared with {others} other {weekday_en}. Trains running on from the day before are not counted.",
        ).format(when=when, overlap=week_text(*window), others=others,
                 weekday=_WEEKDAYS["es"][day.weekday()], weekday_en=wd if others == 1 else wd + "s") + files,
        "router": tr(
            "El viaje más corto a cualquier estación del término municipal de Madrid entre todas las salidas del día "
            "(Connection Scan de perfiles), con {change} minutos como mínimo para cambiar de tren y paseos de hasta "
            "{walk} km en línea recta entre estaciones a {walkkmh} km/h, también para empezar el viaje en otra "
            "estación cercana. Se sube y se baja solo donde el horario lo permite.",
            "The shortest journey to any station in the municipality of Madrid over all of the day's departures "
            "(profile Connection Scan), with at least {change} minutes to change trains and walks of up to {walk} km in "
            "a straight line between stations at {walkkmh} km/h, also to start the journey at another station nearby. "
            "Trains are boarded and left only where the timetable allows it.").format(**params),
        "access": tr(
            "Cada hexágono suma al viaje de la mejor estación a {access} km o menos de su centro la distancia en línea "
            "recta a {accesskmh} km/h, una convención del mapa y no un tiempo en coche. Más lejos, sin dato.",
            "Each hex adds to the journey of the best station within {access} km of its centre the straight-line distance "
            "at {accesskmh} km/h, a map convention rather than a driving time. Further away, no value.").format(**params),
        "trains": tr(
            "Los trenes de una estación son los trenes distintos que se pueden tomar allí ese día; un tren que el horario "
            "escribe varias veces (una por cada tramo en que se puede subir) cuenta una vez, en las estaciones y en las "
            "vías. Las estaciones en las que ese día no se puede subir a ningún tren no se muestran.",
            "A station's trains are the distinct trains that can be boarded there that day; a train the timetable writes "
            "several times (once for each stretch where it may be boarded) counts once, at stations and on track. "
            "Stations where no train can be boarded that day are not shown."),
        "ghost": tr(
            "Las vías de OpenStreetMap se pasan a enlaces entre hexágonos. Cada par de paradas seguidas toma el camino "
            "más corto por esas vías, si mide como mucho {detour} veces la línea recta más {detourkm} km, y suma sus "
            "trenes a cada enlace; los de alta velocidad y los AVANT prefieren la vía de alta velocidad "
            "(highspeed=yes) y los demás la convencional, y cada tramo de la otra cuenta {penalty} veces su longitud. "
            "Una vía fantasma es una vía de Adif por la que no pasa ningún tren de viajeros ese día; puede tener "
            "mercancías. No se dibujan como fantasma la vía a {near} km o menos de un par de paradas que no casa con las "
            "vías ni los tramos de {short} enlaces o menos junto a vía con tren de la misma línea (ref de OSM), que "
            "suelen ser un tren contado en la vía paralela. Las vías de otros operadores sin tren no se dibujan.",
            "OpenStreetMap railways are snapped to links between hexes. Each pair of consecutive stops takes the shortest "
            "path along them, if it is at most {detour} times the straight line plus {detourkm} km, and adds its trains "
            "to each link; high-speed and AVANT trains prefer high-speed track (highspeed=yes) and the others "
            "conventional track, each link of the other kind counting {penalty} times its length. A ghost line is Adif "
            "track with no passenger train that day; it may carry freight. Not drawn as ghost: track within {near} km "
            "of a stop pair with no track path, and stretches of {short} links or fewer beside served track of the same "
            "line (OSM ref), which usually are a train counted on the parallel track. Other operators' track without "
            "trains is not drawn.").format(detour=Num(DETOUR, 1), detourkm=DETOUR_KM, penalty=HS_PENALTY,
                                           near=NEAR_KM, short=SHORT_RUN),
    }
    feve_text = "" if feve else tr(
        " Los trenes de Feve que trae el fichero de Renfe de alta velocidad, larga y media distancia cuentan; el fichero "
        "propio de Renfe Feve no entra, así que la vía métrica de Adif sin tren en el primero no se dibuja, aunque "
        "Feve pase por ella.",
        " The Feve trains in Renfe's high-speed, long and medium-distance file are counted; Renfe Feve's own file is "
        "not in the map, so Adif's metre-gauge track with no train in the first is not drawn, even where Feve runs.")
    unmatched_text = "" if not unmatched else tr(
        f" {unmatched} {'par' if unmatched == 1 else 'pares'} de paradas seguidas no casan con las vías de "
        "OpenStreetMap: su vía no se dibuja.",
        f" {unmatched} {'pair' if unmatched == 1 else 'pairs'} of consecutive stops match no OpenStreetMap track: "
        "their track is not drawn.")
    cut_list = [tr(f"la {c['route']}, que ese día solo tiene trenes de {c['from']} a {c['to']}",
                   f"those of the {c['route']}, whose trains that day only run from {c['from']} to {c['to']}")
                for c in cuts or []]
    stranded_text = "" if not stranded else tr(
        f" Desde {stranded} estaciones con tren no se llega a Madrid ese día"
        + (f"; entre ellas, las de {_join(cut_list)['es']}" if cut_list else "") + ".",
        f" From {stranded} stations with trains no journey reaches Madrid that day"
        + (f"; among them, {_join(cut_list)['en']}" if cut_list else "") + ".")
    lens = {
        "unit": tr("horas y minutos de viaje programado", "hours and minutes of timetabled travel"),
        "description": tr(
            "El viaje en tren más corto a Madrid el {when}, desde la mejor estación a {access} km o menos, más el "
            "camino hasta ella.",
            "The shortest train journey to Madrid on {when}, from the best station within {access} km, plus the way "
            "there.").format(when=when, **params),
        "note": tr(
            "Horario del {when} (semana {span}), con todas las salidas del día. Trenes de Renfe, Ouigo e Iryo (el de "
            "Iryo, de una recopilación no oficial). Fuera: {out}. Es el horario publicado: no cuenta retrasos, trenes "
            "llenos ni obras posteriores. El acceso a la estación en línea recta a {accesskmh} km/h, el radio de "
            "{access} km, los {change} minutos para cambiar de tren y los paseos de hasta {walk} km entre estaciones "
            "son convenciones del mapa, no tiempos medidos. Con la lente, las vías con tren van en líneas más gruesas "
            "cuantos más trenes, y las de Adif sin trenes de viajeros, en gris a trazos.",
            "Timetable of {when} (week of {span}), with every departure of the day. Trains of Renfe, Ouigo and Iryo "
            "(Iryo's from an unofficial compilation). Left out: {out}. It is the published timetable: delays, sold-out "
            "trains and later works are not counted. The straight-line access to the station at {accesskmh} km/h, the "
            "{access} km radius, the {change} minutes to change trains and the walks of up to {walk} km between "
            "stations are map conventions, not measured times. With the lens on, track with trains is drawn thicker "
            "the more trains it carries, and Adif track without passenger trains in dashed grey.",
        ).format(when=when, span=span, out=left_out, **params) + unmatched_text + feve_text + stranded_text,
        "null_label": tr("A más de {access} km de una estación con tren a Madrid ese día",
                         "More than {access} km from a station with a train to Madrid that day").format(**params),
    }
    return {"rules": rules, "lens": lens,
            "vintage": tr("Horarios de Renfe, Ouigo e Iryo del {when}", "Timetables of Renfe, Ouigo and Iryo for {when}")
            .format(when=when)}


# ------------------------------------------------------------------ build


def journey_record(j, trips: list, stops: dict) -> dict:
    """A journey as transit.json writes it; legs are [train label, from, to], a walk's label null."""
    legs = [[leg_label(trips[int(l.trip)]) if l.trip is not None else None, stops[l.frm][0], stops[l.to][0]]
            for l in j.legs]
    return {"min": round(j.duration / 60), "dep": clock(j.dep), "arr": clock(j.arr), "to": stops[j.to][0],
            "changes": j.changes, "legs": legs}


def cut_lines(trips: list, stops: dict, stranded: set[str]) -> list[dict]:
    """The routes of the day all of whose boarding stops are `stranded` (stops with trains but no journey to Madrid):
    {route, from, to}, the two ends of its trips that day farthest apart (the R3 runs from La Garriga north only)."""
    board, ends = defaultdict(set), defaultdict(set)
    for feed, _kind, route, _number, _train, calls in trips:
        if not route:
            continue
        board[(feed, route)] |= {c[0] for c in calls[:-1] if c[3]}
        ends[(feed, route)] |= {calls[0][0], calls[-1][0]}
    out = []
    for k in sorted(board):
        if board[k] and board[k] <= stranded:
            pts = sorted(ends[k])
            u, v = max(((u, v) for u in pts for v in pts if u < v),
                       key=lambda p: km(stops[p[0]][1:3], stops[p[1]][1:3]), default=(pts[0], pts[0]))
            out.append({"route": k[1], "from": stops[u][0], "to": stops[v][0]})
    return out


def operator_effect(trips, stops, targets, shown: list[dict], best: dict) -> str:
    """How much Ouigo and Iryo shorten the best journeys of the shown stations: routing again without them."""
    others = [t for t in trips if t[0] not in OPERATOR_FEEDS]
    prof = route(others, stops, targets)
    gains = []
    for r in shown:
        with_ = [best[s].duration for s in r["g"] if best.get(s)]
        without = [j.duration for s in r["g"] if (j := prof.best(s))]
        if with_ and (not without or min(without) > min(with_)):
            gains.append(((min(without) - min(with_)) // 60 if without else None, r["name"]))
    known = sorted((g for g in gains if g[0] is not None), reverse=True)
    return (f"Ouigo and Iryo shorten the best journey of {len(gains)} stations ({len(gains) - len(known)} reach Madrid "
            f"only with them), by up to {known[0][0] if known else 0} min: {known[:5]}")


def build() -> None:
    world = load_interim("_world")
    grid, owner = HexGrid(**world["grid"]), world["owner"]
    proj = active().world_projection(world)
    tt = load_interim("horarios_tren")
    osm = load_interim("osm_ferrocarril")
    munis = load_interim("siane")["municipalities"]
    spain = ShapeIndex([Shape([[proj(lon, lat) for lon, lat in r] for r in m["rings"]]) for m in munis])
    madrid_shape = spain.shapes[next(k for k, m in enumerate(munis) if m["geoid"] == MADRID)]
    stops, trips = tt["stops"], tt["trips"]
    xy = {s: proj(v[1], v[2]) for s, v in stops.items()}
    targets = {s for s in stops if madrid_shape.contains(*xy[s])}
    prof = route(trips, stops, targets)
    best = {s: prof.best(s) for s in prof.stops()}

    # stations: in Spain when inside a SIANE municipality (a border town's hex can be Spain's), drawn in a land hex
    board = boardings(trips)
    rows = []
    for g in cluster(stops):
        named = named_stop(g, stops, board)
        x, y = xy[named]
        trains = [len(set().union(*(board.get(s, {}).get(k, set()) for s in g))) for k in KINDS]
        madrid = all(s in targets for s in g)
        cell = grid.cell_at(x, y)
        rows.append({"g": g, "name": stops[named][0], "x": x, "y": y, "trains": trains, "madrid": madrid,
                     "spain": in_spain(spain, x, y), "cell": max(cell, 0)})
    name_of = {s: r["name"] for r in rows for s in r["g"]}
    abroad = {s for r in rows if not r["spain"] for s in r["g"]}
    shown = [r for r in rows if r["spain"] and (r["madrid"] or sum(r["trains"]))]  # no station one cannot board at

    def journey(r):
        js = [best[s] for s in r["g"] if best.get(s)]
        return min(js, key=lambda j: (j.duration, j.dep)) if js else None

    stations = []
    for r in shown:
        rec = {"name": r["name"], "x": round(r["x"], 1), "y": round(r["y"], 1),
               "cell": nearest_land(grid, owner, r["cell"], r["x"], r["y"], -1), "stops": r["g"],
               "trains": r["trains"], "best": None}
        if r["madrid"]:
            rec["madrid"] = True
        elif (j := journey(r)) is not None:
            rec["best"] = journey_record(j, trips, stops)
        stations.append(rec)
    stations.sort(key=lambda s: (-sum(s["trains"]), s["name"]))
    station_of = {stop: k for k, s in enumerate(stations) for stop in s["stops"]}
    stranded = {stop for r in rows if not r["madrid"] and journey(r) is None for stop in r["g"]}  # abroad too
    cuts = cut_lines(trips, stops, stranded)
    n_stranded = sum(1 for s in stations if s["best"] is None and not s.get("madrid"))

    # hexes
    points = [(*xy[s], 0 if s in targets else best[s].duration, station_of[s]) for s in station_of
              if s in targets or best.get(s)]
    values, station = hex_values(grid, owner, points)

    # track
    links = track_links(grid, proj, owner, osm["ways"])
    pairs = stop_pairs(trips)
    served, matching = match_pairs(grid, links, pairs, {s: xy[s] for s in stops}, abroad)
    feve = any(f["id"] == "renfe_feve" for f in tt["feeds"])
    ghost, gtally = ghosts(grid, links, served, feve, [(xy[u], xy[v]) for u, v in matching["unmatched_pairs"]])
    matching.update(gtally, hs_ghost=hs_ghosts(links, served, ghost))
    matching["unmatched_pairs"] = [[name_of[u], name_of[v]] for u, v in matching["unmatched_pairs"]]

    day = date.fromisoformat(tt["date"])
    week = tuple(date.fromisoformat(d) for d in tt["week"])
    window = tuple(date.fromisoformat(d) for d in tt["window"])
    tx = texts(day, week, tt["feeds"], window=window, unmatched=matching["unmatched"], stranded=n_stranded, cuts=cuts)
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
        "links": [[a, b, len(who)] for (a, b), who in sorted(served.items())],
        "ghost": [[a, b] for a, b in ghost],
        "matching": matching,
        "cuts": cuts,
    }
    write_web("transit.json", doc)
    land = sum(1 for o in owner if o >= 0)
    covered = sum(1 for i, v in enumerate(values) if v is not None and owner[i] >= 0)
    print(f"    {tt['date']}: {len(trips)} trips, {len(stations)} stations ({n_stranded} with trains but no journey to "
          f"Madrid; cut lines {cuts}), {covered}/{land} land hexes ({covered / land:.0%}); {len(served)} served links, "
          f"{len(ghost)} ghost in {matching['ghost_runs']} runs ({matching['near_unmatched']} links near an unmatched "
          f"pair and {matching['short_runs']} short runs beside their line left out); pairs {matching['pairs']}, "
          f"unmatched {matching['unmatched']}, abroad {matching['abroad']}")
    print(f"    {operator_effect(trips, stops, targets, shown, best)}")
    for d in tt.get("skipped", []):
        print(f"    day {d['date']} skipped: {', '.join(d['short'])}")


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
    if doc["matching"].get("hs_ghost"):
        out.append(("FAIL", f"transit.json: {doc['matching']['hs_ghost']} high-speed ghost links beside served "
                            "high-speed track of the same line (a train counted on the parallel track?)"))
    empty = [s["name"] for s in doc["stations"] if not s.get("madrid") and not sum(s["trains"])]
    if empty:
        out.append(("FAIL", f"transit.json: {len(empty)} stations where no train can be boarded, e.g. {empty[:3]}"))
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
    day = date.fromisoformat(doc["date"])
    for f in doc.get("feeds", []):
        left = (date.fromisoformat(f["window"][1]) - day).days
        if left < FEED_MARGIN_DAYS:
            out.append(("NOTE", f"transit.json: the {f['id']} file ends {left} days after the day of the timetable "
                                f"({f['window'][1]}, file of {f['file_date']}): refetch it, or take its NAP copy"))
    size = path.stat().st_size
    out.append(("NOTE", f"transit.json is {size / 1e3:.0f} kB (loaded when the lens opens)"))
    return out
