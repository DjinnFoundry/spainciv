"""pipeline/core/netcdf.py on small files written here byte by byte (the netCDF classic format specification)."""

import gzip
import io
import struct
import unittest

from pipeline.core.netcdf import NetCDFError, open_nc

TYPES = {"b": (1, 1), "c": (2, 1), "h": (3, 2), "i": (4, 4), "f": (5, 4), "d": (6, 8)}


def _pad(b: bytes) -> bytes:
    return b + b"\0" * (-len(b) % 4)


def _name(s: str) -> bytes:
    raw = s.encode()
    return struct.pack(">I", len(raw)) + _pad(raw)


def _attrs(attrs: dict) -> bytes:
    if not attrs:
        return struct.pack(">II", 0, 0)
    out = struct.pack(">II", 0x0C, len(attrs))
    for k, (code, v) in attrs.items():
        t, _ = TYPES[code]
        raw = v.encode("latin-1") if code == "c" else struct.pack(f">{len(v)}{code}", *v)
        out += _name(k) + struct.pack(">II", t, len(v)) + _pad(raw)
    return out


def write_nc(version: int, dims: list[tuple[str, int]], gattrs: dict, variables: list[dict], numrecs: int = 0) -> bytes:
    """A netCDF classic file. variables: {name, dims (indices), code, attrs, data (flat list: for a record variable
    the records one after the other)}. A dimension of length 0 is the unlimited one."""
    dim_len = {i: n for i, (_, n) in enumerate(dims)}

    def is_rec(v):
        return bool(v["dims"]) and dim_len[v["dims"][0]] == 0

    def step(v):  # bytes of one record (record variable) or of all the data
        n = 1
        for d in (v["dims"][1:] if is_rec(v) else v["dims"]):
            n *= dim_len[d]
        return n * TYPES[v["code"]][1]

    off = 8 if version == 2 else 4

    def header(begins):
        h = b"CDF" + bytes([version]) + struct.pack(">I", numrecs)
        h += struct.pack(">II", 0x0A, len(dims)) + b"".join(_name(n) + struct.pack(">I", size) for n, size in dims)
        h += _attrs(gattrs)
        h += struct.pack(">II", 0x0B, len(variables))
        for v, b in zip(variables, begins):
            h += _name(v["name"]) + struct.pack(">I", len(v["dims"])) + b"".join(struct.pack(">I", d) for d in v["dims"])
            h += _attrs(v.get("attrs", {})) + struct.pack(">II", TYPES[v["code"]][0], (step(v) + 3) // 4 * 4)
            h += struct.pack(">Q" if off == 8 else ">I", b)
        return h

    size = len(header([0] * len(variables)))
    fixed = [v for v in variables if not is_rec(v)]
    rec = [v for v in variables if is_rec(v)]
    begins, pos, body = {}, size, b""
    for v in fixed:
        begins[v["name"]] = pos
        raw = _pad(struct.pack(f">{len(v['data'])}{v['code']}", *v["data"]))
        body += raw
        pos += len(raw)
    recsize = step(rec[0]) if len(rec) == 1 else sum((step(v) + 3) // 4 * 4 for v in rec)
    rpos = pos
    for v in rec:
        begins[v["name"]] = rpos
        rpos += step(v) if len(rec) == 1 else (step(v) + 3) // 4 * 4
    for r in range(numrecs):
        for v in rec:
            per = step(v) // TYPES[v["code"]][1]
            raw = struct.pack(f">{per}{v['code']}", *v["data"][r * per:(r + 1) * per])
            body += raw if len(rec) == 1 else _pad(raw)
    assert recsize * numrecs == len(body) - (pos - size)
    return header([begins[v["name"]] for v in variables]) + body


class ClassicTest(unittest.TestCase):
    def test_cdf1_fixed_variables_attributes_and_types(self):
        data = write_nc(1, [("y", 2), ("x", 3), ("n", 5)], {"title": ("c", "Rejilla de prueba"), "version": ("d", [2.0])},
                        [{"name": "lon", "dims": [0, 1], "code": "f", "data": [-3.5, -3.0, -2.5, -3.5, -3.0, -2.5],
                          "attrs": {"units": ("c", "degrees_east")}},
                         {"name": "temp", "dims": [0, 1], "code": "f", "data": [1.5, -9999.0, 3.25, 4.0, 5.0, 6.0],
                          "attrs": {"missing_value": ("f", [-9999.0]), "units": ("c", "°C")}},
                         {"name": "depth", "dims": [1], "code": "d", "data": [0.5, 1.5, 2.5]},
                         {"name": "code", "dims": [2], "code": "c", "data": [b"a", b"b", b"c", b"d", b"e"]},
                         {"name": "flag", "dims": [1], "code": "h", "data": [1, -2, 3]},
                         {"name": "count", "dims": [1], "code": "i", "data": [10, 20, 30]},
                         {"name": "tiny", "dims": [1], "code": "b", "data": [1, 2, -3]}])
        nc = open_nc(data)
        self.assertEqual(nc.version, 1)
        self.assertEqual(nc.dims, {"y": 2, "x": 3, "n": 5})
        self.assertEqual(nc.attrs, {"title": "Rejilla de prueba", "version": 2.0})
        t = nc.vars["temp"]
        self.assertEqual((t.dims, t.shape, t.record), (("y", "x"), (2, 3), False))
        self.assertEqual(t.attrs, {"missing_value": -9999.0, "units": "°C"})
        self.assertEqual(list(nc.read("temp")), [1.5, -9999.0, 3.25, 4.0, 5.0, 6.0])
        self.assertEqual(list(nc.read("lon")), [-3.5, -3.0, -2.5, -3.5, -3.0, -2.5])
        self.assertEqual(list(nc.read("depth")), [0.5, 1.5, 2.5])
        self.assertEqual(nc.read("code"), "abcde")
        self.assertEqual(list(nc.read("flag")), [1, -2, 3])
        self.assertEqual(list(nc.read("count")), [10, 20, 30])
        self.assertEqual(list(nc.read("tiny")), [1, 2, -3])

    def test_cdf2_interleaved_record_variables_from_a_gzip_stream(self):
        days = [0.0, 1.0, 2.0]
        temps = [280.0, 281.0, 282.0, 283.0, 284.0, 285.0]  # 3 records × 2 points, in kelvin
        data = write_nc(2, [("time", 0), ("lon", 2)], {},
                        [{"name": "time", "dims": [0], "code": "d", "data": days,
                          "attrs": {"units": ("c", "days since 1990-1-1 06:00:00")}},
                         {"name": "lon", "dims": [1], "code": "f", "data": [-16.0, -15.5]},
                         {"name": "maxtemp", "dims": [0, 1], "code": "f", "data": temps}], numrecs=3)
        nc = open_nc(gzip.GzipFile(fileobj=io.BytesIO(gzip.compress(data))))
        self.assertEqual(nc.version, 2)
        self.assertEqual(nc.dims, {"time": 3, "lon": 2})
        self.assertEqual(nc.unlimited, "time")
        self.assertTrue(nc.vars["maxtemp"].record)
        self.assertEqual(nc.vars["maxtemp"].shape, (3, 2))
        self.assertEqual(nc.recsize, 8 + 8)
        self.assertEqual([(list(t), list(v)) for t, v in nc.iter_records("time", "maxtemp")],
                         [([0.0], [280.0, 281.0]), ([1.0], [282.0, 283.0]), ([2.0], [284.0, 285.0])])
        nc = open_nc(data)
        self.assertEqual(list(nc.read("maxtemp")), temps)
        self.assertEqual(list(nc.read("lon")), [-16.0, -15.5])
        self.assertEqual([list(v) for v in nc.iter_records("maxtemp")], [[280.0, 281.0], [282.0, 283.0], [284.0, 285.0]])

    def test_a_single_record_variable_of_shorts_is_not_padded(self):
        data = write_nc(1, [("time", 0)], {}, [{"name": "s", "dims": [0], "code": "h", "data": [1, 2, 3]}], numrecs=3)
        nc = open_nc(data)
        self.assertEqual(nc.recsize, 2)
        self.assertEqual(list(nc.read("s")), [1, 2, 3])

    def test_netcdf4_and_other_files_are_refused_clearly(self):
        with self.assertRaisesRegex(NetCDFError, "netCDF-4"):
            open_nc(b"\x89HDF\r\n\x1a\n" + b"\0" * 64)
        with self.assertRaisesRegex(NetCDFError, "not a netCDF classic"):
            open_nc(b"PK\x03\x04" + b"\0" * 64)
        with self.assertRaisesRegex(NetCDFError, "truncated"):
            open_nc(b"CDF\x01\0\0")

    def test_a_latin1_attribute_is_read(self):
        data = write_nc(1, [("x", 1)], {"references": ("c", "Peral, Navascués")},
                        [{"name": "v", "dims": [0], "code": "f", "data": [1.0]}])
        self.assertEqual(open_nc(data).attrs["references"], "Peral, Navascués")


if __name__ == "__main__":
    unittest.main()
