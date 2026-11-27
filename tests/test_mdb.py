"""The standard-library Jet 4 reader (pipeline/core/mdb.py): on real pages of the Boletín Hidrológico's BD-Embalses
(tests/fixtures/bd_embalses_pages.mdb.bz2, made by tests/make_mdb_fixture.py) and on rows built byte by byte."""

import bz2
import struct
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from pipeline.core import mdb
from pipeline.core.mdb import Column, Jet4, MdbError

FIXTURE = Path(__file__).parent / "fixtures" / "bd_embalses_pages.mdb.bz2"
TABLE = "T_Datos Embalses 1988-2026"


def var_row(fixed: bytes, values: list[bytes], present: list[bool]) -> bytes:
    """A Jet 4 row: column count, fixed data, variable data, then offsets (end first), their count and the null mask."""
    ncols = len(present)
    head = struct.pack("<H", ncols) + fixed
    offs, body = [], b""
    for v in values:
        offs.append(len(head) + len(body))
        body += v
    offs.append(len(head) + len(body))
    mask = bytearray((ncols + 7) // 8)
    for k, on in enumerate(present):
        if on:
            mask[k // 8] |= 1 << (k % 8)
    tail = b"".join(struct.pack("<H", o) for o in reversed(offs)) + struct.pack("<H", len(values)) + bytes(mask)
    return head + body + tail


class FixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = Path(cls.tmp.name) / "bd.mdb"
        path.write_bytes(bz2.decompress(FIXTURE.read_bytes()))
        cls.db = Jet4(path)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()
        cls.tmp.cleanup()

    def test_tables_from_the_catalog_skip_system_ones(self):
        self.assertEqual(self.db.tables(), {"f_00AC97467C54401282090C3276B2DB3E_Data": 18, TABLE: 17200})

    def test_columns_and_types(self):
        cols = self.db.columns(TABLE)
        self.assertEqual([(c.name, c.type_name) for c in cols], [
            ("AMBITO_NOMBRE", "text"), ("EMBALSE_NOMBRE", "text"), ("FECHA", "datetime"), ("AGUA_TOTAL", "text"),
            ("AGUA_ACTUAL", "text"), ("ELECTRICO_FLAG", "numeric")])
        self.assertTrue(cols[2].fixed)
        self.assertEqual(cols[5].scale, 0)
        self.assertEqual(self.db.row_count(TABLE), 725717)  # the whole table's, as its definition records

    def test_row_values(self):
        rows = list(self.db.rows(TABLE))
        self.assertEqual(len(rows), 78)  # the two data pages copied, 39 rows each
        self.assertEqual(rows[0], {"AMBITO_NOMBRE": "Miño - Sil", "EMBALSE_NOMBRE": "Albarellos",
                                   "FECHA": datetime(1988, 1, 5), "AGUA_TOTAL": "91,00", "AGUA_ACTUAL": "32,00",
                                   "ELECTRICO_FLAG": Decimal(1)})
        self.assertEqual(list(self.db.rows(TABLE, ["FECHA"]))[1], {"FECHA": datetime(1988, 1, 12)})

    def test_deleted_rows_are_skipped(self):
        # The catalog page holds 154 slots, 129 of them deleted: only the live objects come back.
        p = self.db.page(17)
        slots = [struct.unpack_from("<H", p, 14 + 2 * r)[0] for r in range(struct.unpack_from("<H", p, 12)[0])]
        self.assertEqual((len(slots), sum(bool(s & mdb.DELETED) for s in slots)), (154, 129))
        names = [r["Name"] for r in self.db._rows(mdb.CATALOG_PAGE, ["Name"])]
        self.assertEqual(len(names), 154 - 129)
        self.assertIn(TABLE, names)

    def test_unknown_table_or_column_and_unread_types_raise(self):
        with self.assertRaises(MdbError):
            self.db.columns("T_Datos Embalses 1988-2027")
        with self.assertRaises(MdbError):
            list(self.db.rows(TABLE, ["AGUA"]))
        with self.assertRaises(MdbError):  # FileData is an OLE column
            list(self.db.rows("f_00AC97467C54401282090C3276B2DB3E_Data", ["FileData"]))

    def test_not_a_jet4_file(self):
        with tempfile.NamedTemporaryFile(suffix=".mdb") as f:
            f.write(b"\0" * mdb.PAGE * 3)
            f.flush()
            with self.assertRaises(MdbError):
                Jet4(f.name)


class ValuesTest(unittest.TestCase):
    def test_compressed_text_with_a_toggle(self):
        # "Pa" in one-byte characters, a 0x00 switches to two-byte ("ñ"), another back ("o").
        raw = b"\xff\xfe" + b"Pa" + b"\x00" + "ñ".encode("utf-16-le") + b"\x00" + b"o"
        self.assertEqual(mdb.text(raw), "Paño")
        self.assertEqual(mdb.text("Breña, La".encode("utf-16-le")), "Breña, La")

    def test_numeric_scale_and_sign(self):
        def num(n, negative=False):
            words = [(n >> (32 * k)) & 0xFFFFFFFF for k in (3, 2, 1, 0)]
            return bytes([0x80 if negative else 0]) + b"".join(struct.pack("<I", w) for w in words)

        self.assertEqual(mdb.numeric(num(12345), 2), Decimal("123.45"))
        self.assertEqual(mdb.numeric(num(12345, True), 2), Decimal("-123.45"))
        self.assertEqual(mdb.numeric(num(1), 0), Decimal(1))
        self.assertEqual(mdb.numeric(num(2 ** 64 + 5), 0), Decimal(2 ** 64 + 5))  # words beyond the first

    def test_datetime_counts_days_from_1899_12_30(self):
        col = Column("D", mdb.DATETIME, 0, 0, 0, 8, True, 0)
        self.assertEqual(mdb.value(col, struct.pack("<d", 32147.5)), datetime(1988, 1, 5, 12))

    def test_null_bitmap_and_mixed_columns(self):
        cols = [Column("N", mdb.LONG, 0, 0, 0, 4, True, 0), Column("T", mdb.TEXT, 1, 0, 0, 100, False, 0),
                Column("X", mdb.NUMERIC, 2, 1, 0, 17, False, 2), Column("B", mdb.BOOL, 3, 0, 0, 0, True, 0)]
        x = bytes([0]) + struct.pack("<IIII", 0, 0, 0, 9100)
        row = var_row(struct.pack("<i", -7), ["Sau".encode("utf-16-le"), x], [True, True, True, True])
        self.assertEqual(mdb.row(row, cols), {"N": -7, "T": "Sau", "X": Decimal("91.00"), "B": True})
        nulls = var_row(struct.pack("<i", 0), [b"", b""], [False, False, False, False])
        self.assertEqual(mdb.row(nulls, cols), {"N": None, "T": None, "X": None, "B": False})


if __name__ == "__main__":
    unittest.main()
