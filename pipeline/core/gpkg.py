"""Read features from a GeoPackage (standard library only: a GeoPackage is a SQLite file with WKB geometries).

Only what the map needs: polygons, multipolygons, points and multipoints, as lon/lat rings or points.
"""

from __future__ import annotations

import sqlite3
import struct
from pathlib import Path
from typing import Iterator

ENVELOPE_DOUBLES = {0: 0, 1: 4, 2: 6, 3: 6, 4: 8}  # GeoPackage header envelope indicator → number of doubles


def wkb_geometry(blob: bytes) -> tuple[str, list]:
    """('polygon', rings) | ('point', [(x, y)]) from a GeoPackage geometry blob (GP header + WKB)."""
    if blob[:2] != b"GP":
        raise ValueError("not a GeoPackage geometry")
    flags = blob[3]
    envelope = ENVELOPE_DOUBLES[(flags >> 1) & 0b111]
    return _wkb(memoryview(blob)[8 + 8 * envelope:])


def _wkb(buf) -> tuple[str, list]:
    rings: list[list[tuple[float, float]]] = []
    points: list[tuple[float, float]] = []
    pos = 0

    def geom():
        nonlocal pos
        order = "<" if buf[pos] == 1 else ">"
        (kind,) = struct.unpack_from(order + "I", buf, pos + 1)
        pos += 5
        base, dims = kind % 1000, 2 + (kind // 1000 in (1, 2)) + (kind // 1000 == 3) * 2  # Z, M, ZM variants
        if base == 1:
            x, y = struct.unpack_from(order + "dd", buf, pos)
            pos += 8 * dims
            points.append((x, y))
        elif base == 3:
            (n_rings,) = struct.unpack_from(order + "I", buf, pos)
            pos += 4
            for _ in range(n_rings):
                (n,) = struct.unpack_from(order + "I", buf, pos)
                pos += 4
                vals = struct.unpack_from(order + "d" * (n * dims), buf, pos)
                pos += 8 * n * dims
                rings.append([(vals[i], vals[i + 1]) for i in range(0, n * dims, dims)])
        elif base in (4, 6):
            (n,) = struct.unpack_from(order + "I", buf, pos)
            pos += 4
            for _ in range(n):
                geom()
        else:
            raise ValueError(f"unsupported WKB geometry type {kind}")

    geom()
    return ("polygon", rings) if rings else ("point", points)


def features(path: Path) -> Iterator[tuple[dict, str, list]]:
    """(properties, kind, rings or points) for every feature of the GeoPackage's first features table."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        (table,) = con.execute("select table_name from gpkg_contents where data_type = 'features' limit 1").fetchone()
        (geom_col,) = con.execute("select column_name from gpkg_geometry_columns where table_name = ?", (table,)).fetchone()
        cur = con.execute(f'select * from "{table}"')
        cols = [d[0] for d in cur.description]
        for row in cur:
            props = dict(zip(cols, row))
            blob = props.pop(geom_col)
            if blob is None:
                continue
            kind, coords = wkb_geometry(blob)
            yield props, kind, coords
    finally:
        con.close()
