"""Read the cell values of a legacy .xls workbook (Excel 97-2003, BIFF8) with the standard library only.

Same interface as core/xlsx.py: `sheets(path, only=None)` gives {sheet name: rows of cell values}, a value being a
string or None for an empty cell. Numbers come back as `repr(float)` text ("211026.4"), so callers `float()` them as
they do the XML text of an .xlsx; a formula gives its cached value (a number, or its text from the STRING record that
follows it); booleans and errors are None. Rows are dense from the first row: a row without values is [].

An .xls is an OLE2 compound file (a little FAT file system: header, DIFAT, FAT, directory, and a mini stream for
streams under 4096 bytes) holding a `Workbook` stream (`Book` in some writers) of BIFF records. Only the worksheets
(BOUNDSHEET type 0) are read. Anything this reader does not understand that would hold a value (an older BIFF
version, an encrypted file, a pre-BIFF8 cell record) raises XlsError instead of being skipped.

References: [MS-CFB] Compound File Binary File Format and [MS-XLS] Excel Binary File Format, both from Microsoft's
open specifications (https://learn.microsoft.com/en-us/openspecs/).
"""

from __future__ import annotations

import struct
from pathlib import Path

SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
ENDOFCHAIN, FREESECT, NOSTREAM = 0xFFFFFFFE, 0xFFFFFFFF, 0xFFFFFFFF

# BIFF record types
BOF, EOF, FILEPASS, BOUNDSHEET, SST, CONTINUE = 0x0809, 0x000A, 0x002F, 0x0085, 0x00FC, 0x003C
NUMBER, LABEL, RK, MULRK, LABELSST, RSTRING = 0x0203, 0x0204, 0x027E, 0x00BD, 0x00FD, 0x00D6
FORMULA, STRING, BOOLERR, BLANK, MULBLANK = 0x0006, 0x0207, 0x0205, 0x0201, 0x00BE
OLD_CELLS = {0x0002, 0x0003, 0x0004, 0x0005, 0x0007}  # BIFF2-4 INTEGER, NUMBER, LABEL, BOOLERR, STRING
BIFF8 = 0x0600


class XlsError(ValueError):
    """The file is not a BIFF8 workbook this reader can read (corrupt, encrypted or of another version)."""


# ------------------------------------------------------------------ OLE2 compound file


def _u32s(b: bytes) -> list[int]:
    return list(struct.unpack(f"<{len(b) // 4}I", b[: len(b) // 4 * 4]))


def _chain(table: list[int], start: int, limit: int) -> list[int]:
    """The sector numbers of a chain in a FAT (or mini FAT), from `start` to ENDOFCHAIN."""
    out, s = [], start
    while s != ENDOFCHAIN:
        if s >= len(table) or len(out) > limit:
            raise XlsError(f"broken sector chain at sector {s}")
        out.append(s)
        s = table[s]
    return out


def workbook_stream(data: bytes) -> bytes:
    """The bytes of the `Workbook` (or `Book`) stream of an OLE2 compound file."""
    if len(data) < 512 or data[:8] != SIGNATURE:
        raise XlsError("not an OLE2 compound file (bad signature)")
    shift, mini_shift = struct.unpack_from("<HH", data, 0x1E)
    if shift not in (9, 12) or mini_shift != 6:
        raise XlsError(f"unsupported sector sizes 2^{shift} / 2^{mini_shift}")
    ssize, msize = 1 << shift, 1 << mini_shift
    n_fat, dir_start = struct.unpack_from("<II", data, 0x2C)
    cutoff, minifat_start, _n_minifat, difat_start, n_difat = struct.unpack_from("<IIIII", data, 0x38)
    n_sectors = len(data) // ssize  # an upper bound on any chain's length

    def sector(n: int) -> bytes:
        off = (n + 1) * ssize
        if off >= len(data):
            raise XlsError(f"sector {n} is past the end of the file")
        return data[off: off + ssize]  # the last one may be cut short by the writer

    fat_sectors = [s for s in _u32s(data[0x4C:0x200]) if s != FREESECT]
    s, seen = difat_start, 0
    while s not in (ENDOFCHAIN, FREESECT) and seen < n_difat:
        entries = _u32s(sector(s))
        fat_sectors += [e for e in entries[:-1] if e != FREESECT]
        s, seen = entries[-1], seen + 1
    if len(fat_sectors) < n_fat:
        raise XlsError(f"the header lists {n_fat} FAT sectors, the DIFAT only {len(fat_sectors)}")
    fat = _u32s(b"".join(sector(s) for s in fat_sectors[:n_fat]))

    def stream(start: int, size: int) -> bytes:
        return _trim(b"".join(sector(s) for s in _chain(fat, start, n_sectors)), size)

    directory = b"".join(sector(s) for s in _chain(fat, dir_start, n_sectors))
    entries = []
    for off in range(0, len(directory) - 127, 128):
        e = directory[off: off + 128]
        name_len = struct.unpack_from("<H", e, 64)[0]
        name = e[: max(0, name_len - 2)].decode("utf-16-le", "replace")
        kind = e[66]
        left, right, child = struct.unpack_from("<III", e, 68)
        start, size = struct.unpack_from("<II", e, 116)
        entries.append((name, kind, left, right, child, start, size))
    if not entries or entries[0][1] != 5:
        raise XlsError("no root entry in the directory")

    # The root's children: a tree over the left/right sibling links, from the root's child.
    children, todo, seen_ids = [], [entries[0][4]], set()
    while todo:
        i = todo.pop()
        if i == NOSTREAM or i in seen_ids:
            continue
        if i >= len(entries):
            raise XlsError(f"directory entry {i} is out of range")
        seen_ids.add(i)
        children.append(entries[i])
        todo += [entries[i][2], entries[i][3]]
    found = {name.lower(): (start, size) for name, kind, *_, start, size in children if kind == 2}
    for want in ("workbook", "book"):
        if want in found:
            start, size = found[want]
            break
    else:
        raise XlsError("no Workbook stream in the file")
    if size >= cutoff:
        return stream(start, size)
    root = entries[0]
    ministream = stream(root[5], root[6])
    minifat = _u32s(b"".join(sector(s) for s in _chain(fat, minifat_start, n_sectors))) if minifat_start != ENDOFCHAIN else []
    return _trim(b"".join(ministream[m * msize: (m + 1) * msize] for m in _chain(minifat, start, len(minifat))), size)


def _trim(b: bytes, size: int) -> bytes:
    if len(b) < size:
        raise XlsError("a stream is shorter than its directory entry says")
    return b[:size]


# ------------------------------------------------------------------ BIFF records


def records(stream: bytes, pos: int = 0):
    """(type, data) of each BIFF record from `pos`."""
    n = len(stream)
    while pos + 4 <= n:
        kind, length = struct.unpack_from("<HH", stream, pos)
        if pos + 4 + length > n:
            raise XlsError(f"record 0x{kind:04X} at {pos} runs past the end of the stream")
        yield kind, stream[pos + 4: pos + 4 + length]
        pos += 4 + length


class _Segments:
    """A record's data and its CONTINUE records, read as one run of bytes, except that character data split by a
    CONTINUE starts again with a flags byte saying whether the rest is compressed (Latin-1) or UTF-16."""

    def __init__(self, parts: list[bytes]):
        self.parts, self.i, self.pos = parts, 0, 0

    def _ensure(self) -> None:
        while self.pos >= len(self.parts[self.i]):
            if self.i + 1 >= len(self.parts):
                raise XlsError("string data runs past its record")
            self.i, self.pos = self.i + 1, 0

    def take(self, n: int) -> bytes:
        out = b""
        while n:
            self._ensure()
            part = self.parts[self.i]
            chunk = part[self.pos: self.pos + n]
            out += chunk
            self.pos += len(chunk)
            n -= len(chunk)
        return out

    def u8(self) -> int:
        return self.take(1)[0]

    def u16(self) -> int:
        return struct.unpack("<H", self.take(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def chars(self, cch: int, wide: bool) -> str:
        out = []
        while cch:
            if self.pos >= len(self.parts[self.i]):  # a CONTINUE boundary inside the characters: a new flags byte
                if self.i + 1 >= len(self.parts):
                    raise XlsError("string characters run past their record")
                self.i, self.pos = self.i + 1, 0
                wide = bool(self.u8() & 0x01)
            room = len(self.parts[self.i]) - self.pos
            n = min(cch, room // 2 if wide else room)
            if n == 0:
                raise XlsError("half a UTF-16 character at a record boundary")
            raw = self.take(n * 2 if wide else n)
            out.append(raw.decode("utf-16-le" if wide else "latin-1"))
            cch -= n
        return "".join(out)

    def plain_string(self) -> str:
        """An XLUnicodeString (LABEL, STRING): count, flags, characters."""
        cch, flags = self.u16(), self.u8()
        return self.chars(cch, bool(flags & 0x01))

    def unicode_string(self, cch_bytes: int = 2) -> str:
        """An XLUnicodeRichExtendedString: count, flags, [runs count], [ext size], characters, [runs], [ext]."""
        cch = self.u8() if cch_bytes == 1 else self.u16()
        flags = self.u8()
        runs = self.u16() if flags & 0x08 else 0
        ext = self.u32() if flags & 0x04 else 0
        text = self.chars(cch, bool(flags & 0x01))
        self.take(4 * runs + ext)
        return text


def _rk(v: int) -> float:
    """An RK number: bit 1 set, a signed 30-bit integer; clear, the top 30 bits of a double. Bit 0 set: divide by 100."""
    if v & 0x02:
        x = float(struct.unpack("<i", struct.pack("<I", v))[0] >> 2)
    else:
        x = struct.unpack("<d", struct.pack("<Q", (v & 0xFFFFFFFC) << 32))[0]
    return x / 100 if v & 0x01 else x


def _num(x: float) -> str:
    return repr(float(x))


def _shared_strings(parts: list[bytes]) -> list[str]:
    seg = _Segments(parts)
    seg.u32()  # total references
    unique = seg.u32()
    return [seg.unicode_string() for _ in range(unique)]


def _bof_version(kind: int, data: bytes) -> None:
    if kind != BOF:
        raise XlsError(f"expected a BOF record, got 0x{kind:04X}")
    if struct.unpack_from("<H", data, 0)[0] != BIFF8:
        raise XlsError(f"BIFF version 0x{struct.unpack_from('<H', data, 0)[0]:04X} is not BIFF8")


def _with_continues(it, first: bytes, nxt):
    """A record's data and that of the CONTINUE records after it, given the record after it (`nxt`); also the first
    record that is not a CONTINUE (None at the end of the stream)."""
    parts = [first]
    while nxt is not None and nxt[0] == CONTINUE:
        parts.append(nxt[1])
        nxt = next(it, None)
    return parts, nxt


def _sheet(stream: bytes, pos: int, sst: list[str]) -> list[list[str | None]]:
    cells: dict[tuple[int, int], str | None] = {}
    it = records(stream, pos)
    try:
        _bof_version(*next(it))
    except StopIteration:
        raise XlsError(f"no sheet at offset {pos}") from None
    pending_formula = None  # (row, col) of a FORMULA whose text is in the next STRING record
    nxt = next(it, None)
    while nxt is not None:
        kind, data = nxt
        nxt = next(it, None)
        if kind == EOF:
            break
        if kind == NUMBER:
            r, c = struct.unpack_from("<HH", data)
            cells[r, c] = _num(struct.unpack_from("<d", data, 6)[0])
        elif kind == RK:
            r, c = struct.unpack_from("<HH", data)
            cells[r, c] = _num(_rk(struct.unpack_from("<I", data, 6)[0]))
        elif kind == MULRK:
            r, c0 = struct.unpack_from("<HH", data)
            for k in range((len(data) - 6) // 6):
                cells[r, c0 + k] = _num(_rk(struct.unpack_from("<I", data, 4 + 6 * k + 2)[0]))
        elif kind == LABELSST:
            r, c = struct.unpack_from("<HH", data)
            i = struct.unpack_from("<I", data, 6)[0]
            if i >= len(sst):
                raise XlsError(f"LABELSST index {i} past the {len(sst)} shared strings")
            cells[r, c] = sst[i]
        elif kind in (LABEL, RSTRING):
            r, c = struct.unpack_from("<HH", data)
            parts, nxt = _with_continues(it, data[6:], nxt)
            cells[r, c] = _Segments(parts).plain_string()
        elif kind == FORMULA:
            r, c = struct.unpack_from("<HH", data)
            result = data[6:14]
            if result[6:8] == b"\xff\xff":
                if result[0] == 0:
                    pending_formula = (r, c)
                cells[r, c] = None  # a boolean, an error or an empty string; a string is set by STRING
            else:
                cells[r, c] = _num(struct.unpack("<d", result)[0])
        elif kind == STRING:
            parts, nxt = _with_continues(it, data, nxt)
            if pending_formula is None:
                raise XlsError("a STRING record without a FORMULA before it")
            cells[pending_formula] = _Segments(parts).plain_string()
            pending_formula = None
        elif kind == BOOLERR:
            r, c = struct.unpack_from("<HH", data)
            cells[r, c] = None
        elif kind in OLD_CELLS:
            raise XlsError(f"pre-BIFF8 cell record 0x{kind:04X}")
        # BLANK, MULBLANK and every formatting or layout record hold no value.
    width: dict[int, int] = {}  # row → columns up to its last value
    for (r, c), v in cells.items():
        if v is not None:
            width[r] = max(width.get(r, 0), c + 1)
    return [[cells.get((r, c)) for c in range(width.get(r, 0))] for r in range(max(cells)[0] + 1)] if cells else []


def read(data: bytes, only: set[str] | None = None) -> dict[str, list[list[str | None]]]:
    """`sheets` on the bytes of an .xls file."""
    try:
        return _read(data, only)
    except struct.error as exc:  # a record or header shorter than its kind needs
        raise XlsError(f"malformed workbook: {exc}") from None


def _read(data: bytes, only: set[str] | None) -> dict[str, list[list[str | None]]]:
    stream = workbook_stream(data)
    it = records(stream)
    try:
        _bof_version(*next(it))
    except StopIteration:
        raise XlsError("empty Workbook stream") from None
    boundsheets, sst = [], []
    nxt = next(it, None)
    while nxt is not None:
        kind, data_ = nxt
        nxt = next(it, None)
        if kind == EOF:
            break
        if kind == FILEPASS:
            raise XlsError("the workbook is encrypted")
        if kind == BOUNDSHEET:
            pos, _visibility, sheet_type = struct.unpack_from("<IBB", data_)
            name = _Segments([data_[6:]]).unicode_string(cch_bytes=1)
            boundsheets.append((name, pos, sheet_type))
        elif kind == SST:
            parts, nxt = _with_continues(it, data_, nxt)
            sst = _shared_strings(parts)
    return {name: _sheet(stream, pos, sst) for name, pos, sheet_type in boundsheets
            if sheet_type == 0 and (only is None or name in only)}


def sheets(path: Path, only: set[str] | None = None) -> dict[str, list[list[str | None]]]:
    """{sheet name: rows of cell values} of the worksheets of an .xls file; `only` reads just those sheets."""
    return read(Path(path).read_bytes(), only)
