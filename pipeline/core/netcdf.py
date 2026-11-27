"""A reader for netCDF classic files (CDF-1, and CDF-2 with 64-bit offsets), standard library only.

The format is the "NetCDF Classic Format Specification" (Unidata, NetCDF Users Guide, "File Format Specifications"):
a header with the dimensions, the global attributes and the variables (each with its dimensions, attributes, type,
size and the offset of its data), then the data, big-endian. A variable whose first dimension is the unlimited one is
a record variable: its data comes one record (one time step) at a time, interleaved with the other record variables'
steps. netCDF-4 files are HDF5 and are refused with a clear error.

    nc = open_nc(f)           # bytes, or a binary file object (a gzip stream works: records are read in order)
    nc.dims                   # {"time": 365, "rlat": 240, …}; the unlimited dimension has its number of records
    nc.vars["maxtemp"].attrs  # {"missing_value": -9999.0, …}; one-value numeric attributes are plain numbers
    nc.read("lon")            # every value of a variable, flattened in C order (array.array, or str for chars)
    for t, v in nc.iter_records("time", "maxtemp"): …   # one record at a time, for files too big to hold
"""

from __future__ import annotations

import io
import struct
import sys
from array import array
from dataclasses import dataclass, field
from math import prod

# nc_type: (struct code, size in bytes, array typecode)
TYPES = {1: ("b", 1, "b"), 2: ("c", 1, None), 3: ("h", 2, "h"), 4: ("i", 4, "i"), 5: ("f", 4, "f"), 6: ("d", 8, "d")}
NC_DIMENSION, NC_VARIABLE, NC_ATTRIBUTE = 0x0A, 0x0B, 0x0C
STREAMING = 0xFFFFFFFF  # numrecs of a file still being written
SWAP = sys.byteorder == "little"


class NetCDFError(ValueError):
    """Not a netCDF classic file, or one this reader cannot read."""


@dataclass
class Var:
    name: str
    dims: tuple[str, ...]
    shape: tuple[int, ...]
    attrs: dict
    type: int
    begin: int
    record: bool  # its first dimension is the unlimited one
    step: int = field(default=0)  # bytes of one record (record variables) or of all the data (fixed ones)


def _pad(n: int) -> int:
    return (n + 3) // 4 * 4


def _decode(t: int, raw: bytes):
    if t == 2:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:  # older files write their texts in Latin-1
            text = raw.decode("latin-1")
        return text.rstrip("\x00")
    code, size, _ = TYPES[t]
    return struct.unpack(f">{len(raw) // size}{code}", raw)


def _values(t: int, raw: bytes):
    """Data of a variable as an array.array in the host's byte order (chars as a str)."""
    if t == 2:
        return raw.decode("latin-1")
    a = array(TYPES[t][2])
    a.frombytes(raw)
    if SWAP and a.itemsize > 1:
        a.byteswap()
    return a


class _Header:
    """Reads the header from the start of a stream, pulling more bytes as it needs them."""

    def __init__(self, f):
        self.f, self.buf, self.p = f, b"", 0

    def take(self, n: int) -> bytes:
        while len(self.buf) - self.p < n:
            more = self.f.read(max(1 << 16, n))
            if not more:
                raise NetCDFError("truncated netCDF header")
            self.buf += more
        out = self.buf[self.p:self.p + n]
        self.p += n
        return out

    def u32(self) -> int:
        return struct.unpack(">I", self.take(4))[0]

    def u64(self) -> int:
        return struct.unpack(">Q", self.take(8))[0]

    def name(self) -> str:
        n = self.u32()
        s = self.take(_pad(n))[:n]
        return s.decode("utf-8")

    def attrs(self) -> dict:
        tag, n = self.u32(), self.u32()
        if tag not in (0, NC_ATTRIBUTE):
            raise NetCDFError(f"bad attribute list tag {tag:#x}")
        out = {}
        for _ in range(n):
            key, t, m = self.name(), self.u32(), self.u32()
            if t not in TYPES:
                raise NetCDFError(f"attribute {key!r}: unknown type {t}")
            v = _decode(t, self.take(_pad(m * TYPES[t][1]))[:m * TYPES[t][1]])
            out[key] = v[0] if isinstance(v, tuple) and len(v) == 1 else v
        return out


class NC:
    def __init__(self, f):
        self.f = f
        h = _Header(f)
        magic = h.take(4)
        if magic[:4] == b"\x89HDF":
            raise NetCDFError("this is a netCDF-4 (HDF5) file: only netCDF classic (CDF-1, CDF-2) is read here")
        if magic[:3] != b"CDF" or magic[3] not in (1, 2):
            raise NetCDFError(f"not a netCDF classic file (magic {magic!r})")
        self.version = magic[3]
        numrecs = h.u32()
        tag, n = h.u32(), h.u32()
        if tag not in (0, NC_DIMENSION):
            raise NetCDFError(f"bad dimension list tag {tag:#x}")
        dims = [(h.name(), h.u32()) for _ in range(n)]
        self.unlimited = next((d for d, size in dims if size == 0), None)
        self.attrs = h.attrs()
        tag, n = h.u32(), h.u32()
        if tag not in (0, NC_VARIABLE):
            raise NetCDFError(f"bad variable list tag {tag:#x}")
        self.vars: dict[str, Var] = {}
        for _ in range(n):
            name = h.name()
            ids = [h.u32() for _ in range(h.u32())]
            attrs = h.attrs()
            t = h.u32()
            if t not in TYPES:
                raise NetCDFError(f"variable {name!r}: unknown type {t}")
            h.u32()  # vsize: recomputed from the shape (it saturates at 2**32 - 1 for big variables)
            begin = h.u32() if self.version == 1 else h.u64()
            names = tuple(dims[i][0] for i in ids)
            record = bool(ids) and dims[ids[0]][1] == 0
            self.vars[name] = Var(name, names, tuple(dims[i][1] for i in ids), attrs, t, begin, record)
        self.header_size = h.p
        rec = [v for v in self.vars.values() if v.record]
        if numrecs == STREAMING:
            raise NetCDFError("numrecs is STREAMING: the file was not closed")
        self.numrecs = numrecs
        self.dims = {d: (numrecs if size == 0 else size) for d, size in dims}
        for v in self.vars.values():
            if v.record:
                v.shape = (numrecs, *v.shape[1:])
                v.step = prod(v.shape[1:]) * TYPES[v.type][1]
            else:
                v.step = prod(v.shape) * TYPES[v.type][1]
        # A record holds every record variable's step, each padded to 4 bytes, except when there is only one.
        self.recsize = rec[0].step if len(rec) == 1 else sum(_pad(v.step) for v in rec)
        self._head = h

    # --- reading -----------------------------------------------------------------------------------------------
    def _read_at(self, offset: int, n: int) -> bytes:
        h = self._head
        if offset + n <= len(h.buf):  # still in what the header read
            return h.buf[offset:offset + n]
        self.f.seek(offset)
        raw = self.f.read(n)
        if len(raw) != n:
            raise NetCDFError(f"truncated data: {len(raw)} of {n} bytes at {offset}")
        return raw

    def var(self, name: str) -> Var:
        if name not in self.vars:
            raise KeyError(f"no variable {name!r} (has {', '.join(self.vars)})")
        return self.vars[name]

    def read(self, name: str):
        """Every value of a variable, flattened in C order; a record variable's records one after the other."""
        v = self.var(name)
        if not v.record:
            return _values(v.type, self._read_at(v.begin, v.step))
        out = _values(v.type, b"")
        for part in self.iter_records(name):
            out += part
        return out

    def iter_records(self, *names: str):
        """One record at a time: each variable's values for that step (a tuple when several names are given). The
        records are read in file order, so a forward-only stream (gzip) is read once."""
        vs = [self.var(n) for n in names]
        if not all(v.record for v in vs):
            raise NetCDFError(f"not record variables: {[v.name for v in vs if not v.record]}")
        for r in range(self.numrecs):
            parts = [_values(v.type, self._read_at(v.begin + r * self.recsize, v.step))
                     for v in sorted(vs, key=lambda v: v.begin)]
            by_name = dict(zip(sorted(names, key=lambda n: self.vars[n].begin), parts))
            yield by_name[names[0]] if len(names) == 1 else tuple(by_name[n] for n in names)


def open_nc(src) -> NC:
    """A netCDF classic file from bytes or a binary file object (seekable, or a gzip stream read forwards)."""
    return NC(io.BytesIO(src) if isinstance(src, (bytes, bytearray, memoryview)) else src)
