"""Read a dBase III table (the .dbf of a shapefile) with the standard library.

`records` streams the rows of an open binary file one record at a time (the records have a fixed length, given in
the header), so a table can be read straight from a zip member without extracting it. Character fields (C) come back
as stripped text in the table's encoding (a shapefile names it in its .cpg); numeric fields (N, F) as int or float,
or None when blank. Deleted records (flag "*") are skipped.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from typing import BinaryIO

TYPES = "CNF"  # the field types this reader decodes


def fields_of(fileobj: BinaryIO) -> tuple[int, int, list[tuple[str, str, int, int]]]:
    """Read the header: (number of records, record length, [(name, type, length, decimals)]). Leaves the file at the
    first record."""
    head = fileobj.read(32)
    if len(head) < 32:
        raise ValueError("not a dBase table: header too short")
    count, header_len, record_len = struct.unpack("<IHH", head[4:12])
    descriptors = fileobj.read(header_len - 32)
    out = []
    for i in range(0, len(descriptors) - 1, 32):
        d = descriptors[i:i + 32]
        if d[0] == 0x0D:
            break
        out.append((d[:11].split(b"\0")[0].decode("ascii"), chr(d[11]), d[16], d[17]))
    return count, record_len, out


def _value(raw: bytes, kind: str, decimals: int, encoding: str):
    if kind == "C":
        return raw.decode(encoding).strip()
    text = raw.decode("ascii").strip()
    if not text or text.strip("*") == "":
        return None
    return int(text) if kind == "N" and decimals == 0 else float(text)


def records(fileobj: BinaryIO, fields: list[str] | None = None, encoding: str = "utf-8") -> Iterator[dict]:
    """Rows of the table as {field: value}, only `fields` if given (each must exist and be of type C, N or F)."""
    count, record_len, descriptors = fields_of(fileobj)
    layout, offset = {}, 1  # byte 0 of a record is the deletion flag
    for name, kind, length, decimals in descriptors:
        layout[name] = (offset, length, kind, decimals)
        offset += length
    wanted = list(layout) if fields is None else fields
    for name in wanted:
        if name not in layout:
            raise KeyError(f"dBase table has no field {name!r} (fields: {', '.join(layout)})")
        if layout[name][2] not in TYPES and fields is not None:
            raise ValueError(f"field {name!r} is of type {layout[name][2]!r}; this reader decodes {TYPES}")
    wanted = [n for n in wanted if layout[n][2] in TYPES]
    for _ in range(count):
        rec = fileobj.read(record_len)
        if len(rec) < record_len:
            raise ValueError(f"dBase table ends early: a record of {len(rec)} bytes, {record_len} expected")
        if rec[:1] == b"*":
            continue
        row = {}
        for name in wanted:
            start, length, kind, decimals = layout[name]
            row[name] = _value(rec[start:start + length], kind, decimals, encoding)
        yield row
