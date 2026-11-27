"""The shortest timetabled journey of a day from every stop to a set of target stops: a profile Connection Scan.

Connection Scan (Dibbelt, Pajor, Strasser and Wagner, "Connection Scan Algorithm", 2013 and ACM JEA 2018) reads the
day's elementary connections (one train from one stop to the next) once, latest departure first. For every stop it
keeps a profile: the departures from that stop after which the earliest arrival at a target gets better, each with its
arrival. The shortest journey of the day from a stop is then the profile entry with the smallest arrival − departure.

- A train can be boarded at a call where `board` (GTFS pickup_type ≠ 1) and left where `alight` (drop_off_type ≠ 1);
  staying on it through a call where one cannot get off is always allowed.
- Changing trains at a stop takes at least `change` seconds; walking to a nearby stop takes its footpath's seconds,
  plus the same change time before the next train. A walk into a target stop ends the journey there.
- A journey may start on foot: from a stop, walking to a nearby one (its footpath, no change time) and taking the
  shortest journey from there counts when it is shorter than any train from the stop itself.
- Each profile entry keeps the decision that made it, so the journey can be rebuilt: its legs (trip, from, to,
  departure, arrival; a walk is a leg whose trip is None), its changes and the target stop it ends at.

Nothing here is about any one country: stops and trips are strings, times are seconds of the service day.
"""

from __future__ import annotations

import bisect
import math
from collections import defaultdict
from typing import Iterable, NamedTuple

INF = float("inf")
EARTH_KM = 6371.0088


class Connection(NamedTuple):
    dep: int
    arr: int
    frm: str
    to: str
    trip: str
    board: bool  # one may board at `frm`
    alight: bool  # one may get off at `to`
    seq: int  # position in the trip (keeps a trip's zero-minute hops in order)


class Leg(NamedTuple):
    trip: str | None  # None: a walk
    frm: str
    to: str
    dep: int
    arr: int


class Exit(NamedTuple):
    """Where a rider of a connection gets off and what comes next: walk `walk` seconds to `then_stop`, where the
    journey ends (`then` None, a target) or boards the entry `then`."""
    stop: str
    arr: int
    then_stop: str
    walk: int
    then: "Entry | None"


class Entry(NamedTuple):
    dep: int
    arr: int  # at the target
    stop: str
    trip: str
    exit: Exit


class Journey(NamedTuple):
    dep: int
    arr: int
    to: str  # the target stop reached
    legs: list[Leg]

    @property
    def duration(self) -> int:
        return self.arr - self.dep

    @property
    def changes(self) -> int:
        return sum(1 for l in self.legs if l.trip is not None) - 1


def trip_connections(trip: str, calls: list[tuple[str, int, int, bool, bool]]) -> list[Connection]:
    """A trip's connections from its calls in order: (stop, arrival, departure, can board, can alight)."""
    return [Connection(a[2], b[1], a[0], b[0], trip, a[3], b[4], k)
            for k, (a, b) in enumerate(zip(calls, calls[1:])) if a[0] != b[0]]


class Profiles:
    def __init__(self, by_stop: dict[str, tuple[list[int], list[Entry]]], walks: dict[str, list[tuple[str, int]]]):
        self._by_stop, self._walks = by_stop, walks

    def entries(self, stop: str) -> list[Entry]:
        """The stop's profile, latest departure first (arrivals strictly earlier as departures get earlier)."""
        return list(self._by_stop.get(stop, ([], []))[1])

    def stops(self) -> set[str]:
        """The stops with a journey: those with a profile and those a walk away from one."""
        return set(self._by_stop) | {s for s, near in self._walks.items() if any(j in self._by_stop for j, _ in near)}

    def best(self, stop: str) -> Journey | None:
        """The shortest journey of the day from `stop`, by train from it or after a walk to a nearby stop (the
        earliest departure among equally short ones)."""
        options = [(e.arr - e.dep, e.dep, 0, e) for e in self._by_stop.get(stop, ([], []))[1]]
        for j, w in self._walks.get(stop, ()):
            options += [(e.arr - e.dep + w, e.dep - w, w, e) for e in self._by_stop.get(j, ([], []))[1]]
        if not options:
            return None
        _, dep, walk, e = min(options, key=lambda o: o[:2])
        j = rebuild(e)
        if not walk:
            return j
        return Journey(dep, j.arr, j.to, [Leg(None, stop, e.stop, dep, e.dep), *j.legs])


def rebuild(e: Entry) -> Journey:
    legs, first, end = [], e, e.stop
    while e is not None:
        x = e.exit
        legs.append(Leg(e.trip, e.stop, x.stop, e.dep, x.arr))
        if x.then_stop != x.stop:
            legs.append(Leg(None, x.stop, x.then_stop, x.arr, x.arr + x.walk))
        end = x.then_stop
        e = x.then
    return Journey(first.dep, first.arr, end, legs)


def profile(connections: Iterable[Connection], targets: set[str], change: int,
            walks: dict[str, list[tuple[str, int]]]) -> Profiles:
    """Profiles of every stop that reaches a target. `walks[stop]` = [(other stop, seconds)], not including itself."""
    conns = sorted(connections, key=lambda c: (-c.dep, -c.arr, -c.seq))
    by_stop: dict[str, tuple[list[int], list[Entry]]] = {}
    trip_best: dict[str, tuple[float, Exit]] = {}

    def earliest(stop: str, t: int) -> Entry | None:
        """The entry of `stop` that departs at `t` or later and arrives first."""
        p = by_stop.get(stop)
        if p is None:
            return None
        i = bisect.bisect_right(p[0], -t)
        return p[1][i - 1] if i else None

    for c in conns:
        best, how = INF, None
        if c.alight:
            options = [(c.to, 0), *walks.get(c.to, ())]
            for j, w in options:
                if j in targets:
                    if c.arr + w < best:
                        best, how = c.arr + w, Exit(c.to, c.arr, j, w, None)
                    continue
                e = earliest(j, c.arr + w + change)
                if e is not None and e.arr < best:
                    best, how = e.arr, Exit(c.to, c.arr, j, w, e)
        stay = trip_best.get(c.trip)
        if stay is not None and stay[0] <= best:
            best, how = stay
        elif how is not None:
            trip_best[c.trip] = (best, how)
        if how is None or not c.board or c.frm in targets:
            continue
        negdeps, entries = by_stop.setdefault(c.frm, ([], []))
        if entries and best >= entries[-1].arr:
            continue
        entry = Entry(c.dep, best, c.frm, c.trip, how)
        if negdeps and negdeps[-1] == -c.dep:
            entries[-1] = entry
        else:
            negdeps.append(-c.dep)
            entries.append(entry)
    return Profiles(by_stop, walks)


def km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lon, lat) points."""
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(h))


def footpaths(coords: dict[str, tuple[float, float]], max_km: float, kmh: float) -> dict[str, list[tuple[str, int]]]:
    """{stop: [(other stop, walking seconds)]} for every pair of stops at most `max_km` apart in a straight line."""
    cell = max_km / 111.0  # degrees of latitude: a bucket at least `max_km` tall (and wider than that in longitude)
    buckets: dict[tuple[int, int], list[str]] = defaultdict(list)
    for s, (lon, lat) in coords.items():
        buckets[(math.floor(lat / cell), math.floor(lon / cell))].append(s)
    out: dict[str, list[tuple[str, int]]] = {}
    for s, p in coords.items():
        by, bx = math.floor(p[1] / cell), math.floor(p[0] / cell)
        near = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for j in buckets.get((by + dy, bx + dx), ()):
                    if j != s and (d := km(p, coords[j])) <= max_km:
                        near.append((j, round(d / kmh * 3600)))
        if near:
            out[s] = sorted(near)
    return out
