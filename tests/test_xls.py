"""core/xls.py: the BIFF8 .xls reader, on workbooks written here byte by byte (OLE2 container and BIFF records), and on
the EPTMC workbook when it has been downloaded."""

import struct
import tempfile
import unittest
from pathlib import Path

from pipeline.core import xls
from pipeline.core.paths import RAW

END, FREE, FATSECT, NOSTREAM = 0xFFFFFFFE, 0xFFFFFFFF, 0xFFFFFFFD, 0xFFFFFFFF


# ------------------------------------------------------------------ a tiny BIFF8 writer


def rec(kind: int, data: bytes) -> bytes:
    return struct.pack("<HH", kind, len(data)) + data


def bof(dt: int) -> bytes:
    return rec(xls.BOF, struct.pack("<HHHHII", 0x0600, dt, 0x0DBB, 0x07CC, 0, 0))


def short_name(name: str, wide: bool) -> bytes:
    return struct.pack("<BB", len(name), 1 if wide else 0) + name.encode("utf-16-le" if wide else "latin-1")


def xl_string(text: str, wide: bool = False) -> bytes:
    return struct.pack("<HB", len(text), 1 if wide else 0) + text.encode("utf-16-le" if wide else "latin-1")


def cell_head(r: int, c: int) -> bytes:
    return struct.pack("<HHH", r, c, 15)


def number(r, c, x):
    return rec(xls.NUMBER, cell_head(r, c) + struct.pack("<d", x))


def rk_int(n: int, div100: bool = False) -> int:
    return ((n << 2) & 0xFFFFFFFF) | 0x02 | (0x01 if div100 else 0)


def rk_float(x: float) -> int:
    return struct.unpack("<Q", struct.pack("<d", x))[0] >> 32


def sst_records() -> tuple[bytes, list[str]]:
    """An SST over three records: a string split by a CONTINUE that switches from Latin-1 to UTF-16 mid-string, a
    rich-text string whose formatting runs cross the next CONTINUE, then, right at the record boundary, a string with
    an ext-rst block, and one after it."""
    first = struct.pack("<II", 5, 5)
    first += xl_string("Andalucía")
    first += struct.pack("<HB", 6, 0) + b"abc"                      # "abcdéf": three Latin-1 chars here…
    second = b"\x01" + "déf".encode("utf-16-le")                    # …a new flags byte, then UTF-16
    second += struct.pack("<HBH", 4, 0x08, 2) + b"Rich" + b"\x00" * 3  # rich text, 2 runs: 8 bytes, 3 here…
    third = b"\x00" * 5                                             # …and 5 after the boundary, no flags byte
    third += struct.pack("<HBI", 3, 0x04, 6) + b"Ext" + b"\xAA" * 6  # a string at the start of the part, ext-rst of 6
    third += xl_string("Next")
    return rec(xls.SST, first) + rec(xls.CONTINUE, second) + rec(xls.CONTINUE, third), \
        ["Andalucía", "abcdéf", "Rich", "Ext", "Next"]


def workbook(sheets: list[tuple[str, bool, bytes]], sst: bytes = b"") -> bytes:
    """A Workbook stream: globals (BOF, a BOUNDSHEET per sheet, the SST, EOF), then each sheet's BOF, cells and EOF."""
    def globals_(offsets):
        out = bof(0x0005)
        for (name, wide, _), off in zip(sheets, offsets):
            out += rec(xls.BOUNDSHEET, struct.pack("<IBB", off, 0, 0) + short_name(name, wide))
        return out + sst + rec(xls.EOF, b"")

    head = len(globals_([0] * len(sheets)))
    offsets, pos = [], head
    bodies = []
    for _, _, cells in sheets:
        body = bof(0x0010) + cells + rec(xls.EOF, b"")
        offsets.append(pos)
        pos += len(body)
        bodies.append(body)
    return globals_(offsets) + b"".join(bodies)


# ------------------------------------------------------------------ a tiny OLE2 writer


def dir_entry(name: str, kind: int, child=NOSTREAM, start=0, size=0) -> bytes:
    raw = (name.encode("utf-16-le") + b"\x00\x00") if name else b""
    e = raw.ljust(64, b"\x00") + struct.pack("<HBB", len(raw), kind, 1)
    e += struct.pack("<III", NOSTREAM, NOSTREAM, child) + b"\x00" * 36 + struct.pack("<III", start, size, 0)
    return e


def compound(stream: bytes, name: str = "Workbook", difat_chain: bool = False) -> bytes:
    """An OLE2 file of 512-byte sectors holding one stream, in the mini stream when under 4096 bytes. With
    `difat_chain` the FAT sector is listed in a DIFAT sector instead of the header."""
    S = 512
    sectors: list[bytes] = []
    fat: dict[int, int] = {}

    def chain(data: bytes, mark: int | None = None) -> int:
        start = len(sectors)
        n = max(1, -(-len(data) // S))
        for k in range(n):
            sectors.append(data[k * S:(k + 1) * S].ljust(S, b"\x00"))
            fat[start + k] = mark if mark is not None else (start + k + 1 if k < n - 1 else END)
        return start

    mini = len(stream) < 4096
    if mini:
        ministream = stream.ljust(-(-len(stream) // 64) * 64, b"\x00")
        n_mini = len(ministream) // 64
        minifat = b"".join(struct.pack("<I", k + 1 if k < n_mini - 1 else END) for k in range(n_mini))
        minifat_start = chain(minifat.ljust(S, b"\xff"))  # first, so regular sector 0 is not the stream
        root_start = chain(ministream)
        entries = dir_entry("Root Entry", 5, child=1, start=root_start, size=len(ministream))
        entries += dir_entry(name, 2, start=0, size=len(stream))
    else:
        start = chain(stream)
        minifat_start = END
        entries = dir_entry("Root Entry", 5, child=1, start=END, size=0) + dir_entry(name, 2, start=start, size=len(stream))
    entries += dir_entry("", 0) + dir_entry("", 0)
    dir_start = chain(entries)
    difat_sector = None
    if difat_chain:
        difat_sector = len(sectors)
        sectors.append(b"")
        fat[difat_sector] = 0xFFFFFFFC  # DIFSECT
    fat_sector = len(sectors)
    sectors.append(b"")
    fat[fat_sector] = FATSECT
    sectors[fat_sector] = b"".join(struct.pack("<I", fat.get(k, FREE)) for k in range(S // 4))
    header_difat = [FREE] * 109
    if difat_chain:
        sectors[difat_sector] = (struct.pack("<I", fat_sector) + struct.pack("<I", FREE) * (S // 4 - 2)
                                 + struct.pack("<I", END))
    else:
        header_difat[0] = fat_sector
    header = xls.SIGNATURE + b"\x00" * 16 + struct.pack("<HHHHH", 0x3E, 3, 0xFFFE, 9, 6) + b"\x00" * 6
    header += struct.pack("<IIIIIIIII", 0, 1, dir_start, 0, 4096, minifat_start, 1 if mini else 0,
                          difat_sector if difat_chain else END, 1 if difat_chain else 0)
    header += b"".join(struct.pack("<I", x) for x in header_difat)
    assert len(header) == 512
    return header + b"".join(sectors)


def sample_cells() -> bytes:
    c = number(0, 0, 211026.4)
    c += rec(xls.RK, cell_head(0, 1) + struct.pack("<I", rk_int(123)))
    c += rec(xls.RK, cell_head(0, 2) + struct.pack("<I", rk_int(12345, div100=True)))
    c += rec(xls.RK, cell_head(0, 3) + struct.pack("<I", rk_float(1.5)))
    c += rec(xls.RK, cell_head(0, 4) + struct.pack("<I", rk_int(-7)))
    c += rec(xls.MULRK, struct.pack("<HH", 1, 1) + b"".join(struct.pack("<HI", 15, rk_int(n)) for n in (1, 2, 3))
             + struct.pack("<H", 3))
    c += rec(xls.LABEL, cell_head(2, 0) + xl_string("Total"))
    c += rec(xls.LABEL, cell_head(2, 1) + xl_string("Señal ☃", wide=True))
    c += rec(xls.LABELSST, cell_head(3, 0) + struct.pack("<I", 1))
    c += rec(xls.LABELSST, cell_head(3, 1) + struct.pack("<I", 4))
    c += rec(xls.FORMULA, cell_head(4, 0) + struct.pack("<d", 2.5) + b"\x00" * 6)
    c += rec(xls.FORMULA, cell_head(4, 1) + bytes([0, 0, 0, 0, 0, 0, 0xFF, 0xFF]) + b"\x00" * 6)
    c += rec(xls.STRING, xl_string("fx"))
    c += rec(xls.FORMULA, cell_head(4, 2) + bytes([1, 0, 1, 0, 0, 0, 0xFF, 0xFF]) + b"\x00" * 6)  # a boolean
    c += rec(xls.BOOLERR, cell_head(4, 3) + b"\x01\x00")
    c += rec(xls.BLANK, cell_head(5, 3))
    c += rec(xls.MULBLANK, struct.pack("<HHHHH", 6, 0, 15, 15, 1))
    c += number(7, 2, -0.25)
    return c


EXPECTED = [
    ["211026.4", "123.0", "123.45", "1.5", "-7.0"],
    [None, "1.0", "2.0", "3.0"],
    ["Total", "Señal ☃"],
    ["abcdéf", "Next"],
    ["2.5", "fx"],
    [],
    [],
    [None, None, "-0.25"],
]


class XlsTest(unittest.TestCase):
    def book(self, big: bool, **kw) -> bytes:
        sst, _ = sst_records()
        filler = b"".join(number(100 + k, 0, float(k)) for k in range(300)) if big else b""
        stream = workbook([("6.7", False, sample_cells() + filler), ("Índice", True, number(0, 0, 1.0))], sst)
        self.assertEqual(len(stream) >= 4096, big)
        return compound(stream, **kw)

    def test_regular_stream(self):
        got = xls.read(self.book(big=True))
        self.assertEqual(list(got), ["6.7", "Índice"])
        self.assertEqual(got["6.7"][:8], EXPECTED)
        self.assertEqual(got["6.7"][399], ["299.0"])
        self.assertEqual(got["Índice"], [["1.0"]])

    def test_mini_stream(self):
        got = xls.read(self.book(big=False))
        self.assertEqual(got["6.7"], EXPECTED)

    def test_difat_chain(self):
        self.assertEqual(xls.read(self.book(big=True, difat_chain=True))["6.7"][:8], EXPECTED)

    def test_book_stream_name(self):
        self.assertEqual(xls.read(self.book(big=False, name="Book"))["6.7"], EXPECTED)

    def test_shared_strings_across_continue(self):
        sst, strings = sst_records()
        kinds, parts = [], []
        for kind, data in xls.records(sst):
            kinds.append(kind)
            parts.append(data)
        self.assertEqual(kinds, [xls.SST, xls.CONTINUE, xls.CONTINUE])
        self.assertEqual(xls._shared_strings(parts), strings)

    def test_only_and_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t.xls"
            path.write_bytes(self.book(big=False))
            self.assertEqual(list(xls.sheets(path, only={"Índice"})), ["Índice"])

    def test_corrupt_files_raise(self):
        good = self.book(big=True)
        for what, data in {
            "not OLE2": b"PK\x03\x04" + good[4:],
            "truncated": good[:1500],
            "empty": b"",
        }.items():
            with self.subTest(what), self.assertRaises(xls.XlsError):
                xls.read(data)

    def test_old_biff_and_encryption_raise(self):
        biff5 = rec(xls.BOF, struct.pack("<HHHH", 0x0500, 5, 0, 0)) + rec(xls.EOF, b"")
        with self.assertRaises(xls.XlsError):
            xls.read(compound(biff5))
        encrypted = bof(5) + rec(xls.FILEPASS, b"\x00" * 6) + rec(xls.EOF, b"")
        with self.assertRaises(xls.XlsError):
            xls.read(compound(encrypted))
        old_cell = workbook([("s", False, rec(0x0003, b"\x00" * 15))])
        with self.assertRaises(xls.XlsError):
            xls.read(compound(old_cell))
        short = workbook([("s", False, rec(xls.MULRK, b"\x00\x00"))])  # a cell record cut short
        with self.assertRaises(xls.XlsError):
            xls.read(compound(short))


EPTMC = RAW / "eptmc" / "eptmc2025.tablas.xls"


@unittest.skipUnless(EPTMC.exists(), "the EPTMC workbook is not downloaded (fetch eptmc --country es)")
class RealWorkbookTest(unittest.TestCase):
    def test_eptmc_matrix_cell(self):
        book = xls.sheets(EPTMC, only={"6.7", "Índice"})
        self.assertEqual(set(book), {"6.7", "Índice"})
        row = next(r for r in book["6.7"] if r and r[0] == "Andalucía")
        self.assertAlmostEqual(float(row[1]), 211026.4, delta=0.05)  # Andalucía → Andalucía, thousand tonnes


if __name__ == "__main__":
    unittest.main()
