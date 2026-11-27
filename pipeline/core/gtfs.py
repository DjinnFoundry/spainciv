"""GTFS timetables read straight from their zip with the standard library.

Publishers write GTFS in their own ways, and these readers take what the Spanish feeds do: a UTF-8 byte-order mark,
fields padded with trailing spaces (Renfe), times without a leading zero ("8:30:00") and past midnight ("25:10:00", the
same service day), services given by `calendar.txt`, by `calendar_dates.txt` or by both.

- `columns(z, name, cols)`: the rows of one file as tuples of the named columns ("" for a column the file lacks).
- `seconds("8:30:00")`: a GTFS time in seconds from the start of its service day.
- `Calendar(z)`: which services run on a date (`on`), and the first and last date any service runs (`window`).
- `trains_by_day(trips, calendar, days)`: how many distinct trains run on each day, by a group of the trip (an
  operator, a network), for choosing a representative day (`pick_day`).
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Iterable, Iterator

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def columns(z: zipfile.ZipFile, name: str, cols: Iterable[str]) -> Iterator[tuple[str, ...]]:
    """Rows of `name` in the zip as tuples of `cols`, each field stripped; nothing if the zip has no such file."""
    cols = tuple(cols)
    try:
        f = z.open(name)
    except KeyError:
        return
    with f:
        reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig", newline=""))
        header = [h.strip() for h in next(reader, [])]
        at = [header.index(c) if c in header else None for c in cols]
        width = len(header)
        for row in reader:
            if not row or (len(row) == 1 and not row[0].strip()):
                continue
            if len(row) < width:
                row = row + [""] * (width - len(row))
            yield tuple(row[k].strip() if k is not None else "" for k in at)


def seconds(t: str) -> int:
    """'8:30:00' → 30600; '25:10:00' → 90600 (GTFS keeps times past midnight in the same service day)."""
    h, m, s = t.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + int(s)


def clock(secs: int) -> str:
    """30600 → '08:30'; 90600 → '25:10' (as the timetable writes a time past midnight)."""
    return f"{secs // 3600:02d}:{secs % 3600 // 60:02d}"


def parse_date(s: str) -> date:
    """'20261209' → date(2026, 12, 9)."""
    s = s.strip()
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


class Calendar:
    """The services of a feed: weekly patterns (calendar.txt) and the dates added or removed (calendar_dates.txt)."""

    def __init__(self, z: zipfile.ZipFile):
        self.weekly: dict[str, tuple[tuple[bool, ...], date, date]] = {}
        for sid, start, end, *days in columns(z, "calendar.txt", ("service_id", "start_date", "end_date", *WEEKDAYS)):
            self.weekly[sid] = (tuple(d == "1" for d in days), parse_date(start), parse_date(end))
        self.added: dict[date, set[str]] = defaultdict(set)
        self.removed: dict[date, set[str]] = defaultdict(set)
        for sid, day, kind in columns(z, "calendar_dates.txt", ("service_id", "date", "exception_type")):
            (self.added if kind == "1" else self.removed)[parse_date(day)].add(sid)

    def on(self, day: date) -> set[str]:
        """The services that run on `day`."""
        wd = day.weekday()
        out = {sid for sid, (days, start, end) in self.weekly.items() if start <= day <= end and days[wd]}
        return (out | self.added.get(day, set())) - self.removed.get(day, set())

    def window(self) -> tuple[date, date] | None:
        """(first, last) date of the weekly patterns and the added dates; None for an empty calendar."""
        starts = [s for _, s, _ in self.weekly.values()] + list(self.added)
        ends = [e for _, _, e in self.weekly.values()] + list(self.added)
        return (min(starts), max(ends)) if starts else None


def days_between(first: date, last: date) -> list[date]:
    return [first + timedelta(days=k) for k in range((last - first).days + 1)]


def trains_by_day(trips: Iterable[tuple[str, str, str]], calendar: Calendar, days: Iterable[date]) -> dict[str, dict[date, int]]:
    """{group: {day: distinct trains that run that day}} from (service_id, group, train) triples, one per trip. A train
    the feed writes as several trips (Renfe gives one per set of stops where it may be boarded; Iryo one per route
    through Madrid) counts once."""
    per_service: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for sid, group, train in trips:
        per_service[sid].add((group, train))
    groups = {g for trains in per_service.values() for g, _ in trains}
    out: dict[str, dict[date, int]] = {g: {} for g in groups}
    for day in days:
        running: set[tuple[str, str]] = set()
        for sid in calendar.on(day):
            running |= per_service.get(sid, set())
        totals = Counter(g for g, _ in running)
        for g in groups:
            out[g][day] = totals.get(g, 0)
    return out


class NoDayError(RuntimeError):
    """No candidate day has every group at its usual service."""


def pick_day(counts: dict[str, dict[date, int]], candidates: list[date], share: float) -> date:
    """The first candidate on which every group runs at least `share` of the trips of its busiest day of the same
    weekday among the days counted. Raises NoDayError when none does."""
    for day in candidates:
        if all(by_day.get(day, 0) >= share * max((n for d, n in by_day.items() if d.weekday() == day.weekday()), default=0)
               for by_day in counts.values()):
            return day
    raise NoDayError(f"no day among {[d.isoformat() for d in candidates]} has every group at "
                     f"{share:.0%} of its usual trips")


def failing(counts: dict[str, dict[date, int]], day: date, share: float) -> list[str]:
    """The groups below `share` of their busiest same weekday on `day` (why a candidate was skipped)."""
    out = []
    for g, by_day in sorted(counts.items()):
        top = max((n for d, n in by_day.items() if d.weekday() == day.weekday()), default=0)
        if by_day.get(day, 0) < share * top:
            out.append(f"{g} {by_day.get(day, 0)}/{top}")
    return out
