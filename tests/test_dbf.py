"""pipeline/core/dbf.py, the dBase III reader for a shapefile's table, and `make_dbf`, the table the other tests build."""

import io
import struct
import unittest


def make_dbf(fields: list[tuple[str, str, int, int]], rows: list[list], deleted: tuple[int, ...] = (),
             encoding: str = "utf-8") -> bytes:
    """A dBase III table: `fields` as (name, type, length, decimals), one list of values per row (None = blank); the
    rows at `deleted` carry the deletion flag. Text is written in `encoding`."""
    record_len = 1 + sum(f[2] for f in fields)
    out = bytearray(struct.pack("<B3BIHH20x", 3, 126, 11, 27, len(rows), 32 + 32 * len(fields) + 1, record_len))
    for name, kind, length, decimals in fields:
        out += struct.pack("<11sc4xBB14x", name.encode("ascii"), kind.encode("ascii"), length, decimals)
    out += b"\r"
    for i, row in enumerate(rows):
        out += b"*" if i in deleted else b" "
        for (_, kind, length, _), v in zip(fields, row):
            raw = b"" if v is None else str(v).encode(encoding)
            out += raw.ljust(length) if kind == "C" else raw.rjust(length)
    return bytes(out + b"\x1a")


class DbfTest(unittest.TestCase):
    FIELDS = [("CellCode10", "C", 15, 0), ("Especie", "C", 30, 0), ("OBJECTID", "N", 10, 0), ("Shape_Area", "F", 19, 11)]

    def table(self):
        return io.BytesIO(make_dbf(self.FIELDS, [["10kmE316N182", "Águila imperial", 1, 0.5],
                                                 ["10kmE1N1", "borrado", 2, 1.0],
                                                 ["10kmE2N2", "Lynx pardinus", None, None]], deleted=(1,)))

    def test_reads_text_and_numbers_and_skips_deleted_records(self):
        from pipeline.core.dbf import records

        self.assertEqual(list(records(self.table())), [
            {"CellCode10": "10kmE316N182", "Especie": "Águila imperial", "OBJECTID": 1, "Shape_Area": 0.5},
            {"CellCode10": "10kmE2N2", "Especie": "Lynx pardinus", "OBJECTID": None, "Shape_Area": None}])

    def test_a_numeric_field_with_decimals_is_a_float(self):
        from pipeline.core.dbf import records

        table = make_dbf([("Area", "N", 12, 3), ("Count", "N", 6, 0)], [["12.500", "7"], ["0.125", None]])
        rows = list(records(io.BytesIO(table)))
        self.assertEqual(rows, [{"Area": 12.5, "Count": 7}, {"Area": 0.125, "Count": None}])
        self.assertIsInstance(rows[0]["Area"], float)
        self.assertIsInstance(rows[0]["Count"], int)

    def test_text_in_the_tables_encoding(self):
        # A shapefile's .cpg names its encoding; Latin-1 bytes read as UTF-8 would fail.
        from pipeline.core.dbf import records

        table = make_dbf([("Nombre", "C", 20, 0)], [["Águila imperial"]], encoding="latin-1")
        self.assertEqual(list(records(io.BytesIO(table), encoding="latin-1")), [{"Nombre": "Águila imperial"}])
        with self.assertRaises(UnicodeDecodeError):
            list(records(io.BytesIO(table)))

    def test_only_the_fields_asked_for(self):
        from pipeline.core.dbf import records

        self.assertEqual([r for r in records(self.table(), ["Especie"])],
                         [{"Especie": "Águila imperial"}, {"Especie": "Lynx pardinus"}])
        with self.assertRaises(KeyError):
            list(records(self.table(), ["Nombre"]))

    def test_a_truncated_table_fails(self):
        from pipeline.core.dbf import records

        with self.assertRaises(ValueError):
            list(records(io.BytesIO(self.table().getvalue()[:-20])))


if __name__ == "__main__":
    unittest.main()
