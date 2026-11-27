"""Tables of a Microsoft Access 2000–2003 database (Jet 4, .mdb), read with the standard library only.

Enough of the format to read plain tables of numbers, dates and short texts, page by page with seeks (the file is
never read whole):

* The catalog is the table MSysObjects, whose definition is on page 2: a row with Type 1 is a table, and the low 24
  bits of its Id are the page of that table's definition (TDEF).
* A TDEF may run over continuation pages (each with an 8-byte header). It holds the row count, the columns (25 bytes
  each: type, number, offset among the variable-length columns, precision and scale, flags, offset among the fixed
  ones, length) and their names (UCS-2).
* A table's rows live on data pages (type 0x01) that name its TDEF page; they are found by scanning every page's
  header once. A row slot flagged 0x4000 is a deleted row and is skipped; one flagged 0x8000 points to a row moved to
  another page, which this reader does not follow, so meeting one in a table raises.
* Values: bool (in the null bitmap), byte, int16, int32, float, double, datetime (days since 1899-12-30), text (UCS-2,
  or the compressed form that starts 0xFF 0xFE, where a 0x00 byte toggles between one byte and two bytes a
  character) and numeric (a sign byte, then four little-endian 32-bit words, the most significant first, scaled by
  the column's scale, as a Decimal). Memo, OLE and every other type raise
  when they are read.

Format as documented by the mdbtools project (HACKING.md).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Iterator

PAGE = 4096
EPOCH = datetime(1899, 12, 30)
CATALOG_PAGE = 2
DELETED, OVERFLOW, OFFSET = 0x4000, 0x8000, 0x1FFF
BOOL, BYTE, INT, LONG, MONEY, FLOAT, DOUBLE, DATETIME, BINARY, TEXT, OLE, MEMO, GUID, NUMERIC = (
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 15, 16)
_FIXED = {BYTE: "<B", INT: "<h", LONG: "<i", FLOAT: "<f", DOUBLE: "<d"}
TYPE_NAMES = {BOOL: "bool", BYTE: "byte", INT: "int16", LONG: "int32", MONEY: "money", FLOAT: "float",
              DOUBLE: "double", DATETIME: "datetime", BINARY: "binary", TEXT: "text", OLE: "ole", MEMO: "memo",
              GUID: "guid", NUMERIC: "numeric"}


class MdbError(ValueError):
    """The file is not a Jet 4 database, or holds something this reader does not read."""


@dataclass(frozen=True)
class Column:
    name: str
    type: int
    number: int  # its bit in a row's null bitmap
    var_index: int  # its place among the variable-length columns
    fixed_offset: int  # where it starts among the fixed-length ones
    length: int
    fixed: bool
    scale: int  # numeric only

    @property
    def type_name(self) -> str:
        return TYPE_NAMES.get(self.type, f"type {self.type}")


def text(v: bytes) -> str:
    """A Jet 4 text value: UCS-2, or compressed (0xFF 0xFE, then runs of one-byte characters, a 0x00 switching to
    two-byte ones and back)."""
    if v[:2] != b"\xff\xfe":
        return v.decode("utf-16-le")
    out, one, i = [], True, 2
    while i < len(v):
        if v[i] == 0:
            one = not one
            i += 1
        elif one:
            out.append(chr(v[i]))
            i += 1
        else:
            out.append(v[i:i + 2].decode("utf-16-le"))
            i += 2
    return "".join(out)


def numeric(v: bytes, scale: int) -> Decimal:
    """A Jet 4 numeric (decimal) value: sign byte (0x80 = negative), four LE32 words from the most significant."""
    n = 0
    for k in range(4):
        n = (n << 32) | struct.unpack_from("<I", v, 1 + 4 * k)[0]
    return Decimal(-n if v[0] & 0x80 else n).scaleb(-scale)


def value(col: Column, v: bytes):
    """A column's value from its bytes (not null)."""
    t = col.type
    if t in _FIXED:
        return struct.unpack(_FIXED[t], v)[0]
    if t == DATETIME:
        return EPOCH + timedelta(days=struct.unpack("<d", v)[0])
    if t == TEXT:
        return text(v)
    if t == NUMERIC:
        return numeric(v, col.scale)
    raise MdbError(f"column {col.name!r}: {col.type_name} values are not read")


def row(b: bytes, cols: list[Column]) -> dict:
    """One row's values by column name. Layout: column count (2 bytes), fixed-length values, variable-length values,
    then from the end backwards: the null bitmap, the variable-length count and their offsets."""
    ncols = struct.unpack_from("<H", b, 0)[0]
    bm = (ncols + 7) // 8
    mask = b[len(b) - bm:]
    nvar = struct.unpack_from("<H", b, len(b) - bm - 2)[0]
    offs = [struct.unpack_from("<H", b, len(b) - bm - 4 - 2 * k)[0] for k in range(nvar + 1)]
    out = {}
    for c in cols:
        present = c.number < ncols and (mask[c.number // 8] >> (c.number % 8)) & 1
        if c.type == BOOL:
            out[c.name] = bool(present)
        elif not present:
            out[c.name] = None
        elif c.fixed:
            out[c.name] = value(c, b[2 + c.fixed_offset: 2 + c.fixed_offset + c.length])
        elif c.var_index >= nvar:
            out[c.name] = None
        else:
            out[c.name] = value(c, b[offs[c.var_index]: offs[c.var_index + 1]])
    return out


class Jet4:
    """An open .mdb file: Jet4(path).tables(), .columns(name), .row_count(name), .rows(name), .data_pages(tdef page)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.f = open(self.path, "rb")
        head = self.page(0)
        if head[4:19] != b"Standard Jet DB" or head[0x14] != 1:
            self.f.close()
            raise MdbError(f"{self.path.name}: not a Jet 4 (Access 2000–2003) database")
        self.f.seek(0, 2)
        self.pages = self.f.tell() // PAGE
        self._owners: dict[int, list[int]] | None = None
        self._tables: dict[str, int] | None = None

    def close(self) -> None:
        self.f.close()

    def __enter__(self) -> "Jet4":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def page(self, n: int) -> bytes:
        self.f.seek(n * PAGE)
        p = self.f.read(PAGE)
        if len(p) != PAGE:
            raise MdbError(f"{self.path.name}: page {n} is past the end of the file")
        return p

    def _tdef(self, pg: int) -> tuple[int, list[Column]]:
        """(row count, columns) of the table defined on page `pg`."""
        p = self.page(pg)
        if p[0] != 0x02:
            raise MdbError(f"{self.path.name}: page {pg} is not a table definition")
        buf = bytearray(p)
        nxt = struct.unpack_from("<I", p, 4)[0]
        while nxt:
            q = self.page(nxt)
            buf += q[8:]
            nxt = struct.unpack_from("<I", q, 4)[0]
        num_rows = struct.unpack_from("<I", buf, 0x10)[0]
        num_cols = struct.unpack_from("<H", buf, 0x2D)[0]
        num_real_idx = struct.unpack_from("<I", buf, 0x33)[0]
        off = 0x3F + num_real_idx * 12
        raw = []
        for k in range(num_cols):
            c = buf[off + 25 * k: off + 25 * (k + 1)]
            raw.append((c[0], struct.unpack_from("<H", c, 5)[0], struct.unpack_from("<H", c, 7)[0], c[12],
                        bool(c[15] & 1), struct.unpack_from("<H", c, 21)[0], struct.unpack_from("<H", c, 23)[0]))
        off += 25 * num_cols
        cols = []
        for t, num, var, scale, fixed, fo, ln in raw:
            n = struct.unpack_from("<H", buf, off)[0]
            name = bytes(buf[off + 2: off + 2 + n]).decode("utf-16-le")
            off += 2 + n
            cols.append(Column(name, t, num, var, fo, ln, fixed, scale))
        return num_rows, cols

    def data_pages(self, tdef_page: int) -> list[int]:
        """The data pages of the table defined on page `tdef_page`, in file order (every page is scanned once)."""
        if self._owners is None:  # every data page, by the TDEF page it belongs to
            self._owners = {}
            for n in range(self.pages):
                self.f.seek(n * PAGE)
                h = self.f.read(8)
                if h[0] == 0x01:
                    self._owners.setdefault(struct.unpack_from("<I", h, 4)[0], []).append(n)
        return self._owners.get(tdef_page, [])

    def _rows(self, pg: int, names: list[str] | None = None) -> Iterator[dict]:
        _, cols = self._tdef(pg)
        if names is not None:
            missing = set(names) - {c.name for c in cols}
            if missing:
                raise MdbError(f"{self.path.name}: no column {', '.join(sorted(missing))}")
            cols = [c for c in cols if c.name in names]
        for n in self.data_pages(pg):
            p = self.page(n)
            end = PAGE
            for r in range(struct.unpack_from("<H", p, 12)[0]):
                slot = struct.unpack_from("<H", p, 14 + 2 * r)[0]
                start = slot & OFFSET
                if not slot & DELETED:
                    if slot & OVERFLOW:
                        raise MdbError(f"{self.path.name}: page {n} row {r} has moved to another page (not read)")
                    yield row(p[start:end], cols)
                end = start

    def tables(self) -> dict[str, int]:
        """The user tables (not MSys*), by name: their TDEF page."""
        if self._tables is None:
            self._tables = {r["Name"]: r["Id"] & 0xFFFFFF for r in self._rows(CATALOG_PAGE, ["Name", "Type", "Id"])
                            if r.get("Type") == 1 and r.get("Name") and not r["Name"].startswith("MSys")}
        return self._tables

    def _page_of(self, name: str) -> int:
        try:
            return self.tables()[name]
        except KeyError:
            raise MdbError(f"{self.path.name}: no table {name!r}") from None

    def columns(self, name: str) -> list[Column]:
        return self._tdef(self._page_of(name))[1]

    def row_count(self, name: str) -> int:
        """The row count the table's definition records."""
        return self._tdef(self._page_of(name))[0]

    def rows(self, name: str, columns: list[str] | None = None) -> Iterator[dict]:
        """The table's rows, as {column name: value} (of `columns`, or all of them), in page order. Only the columns
        asked for are decoded, so a table with a memo column can still be read without it."""
        return self._rows(self._page_of(name), columns)
