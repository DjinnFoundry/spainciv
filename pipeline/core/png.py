"""A small PNG decoder (standard library only) for map images served by WMS: 8-bit RGB, RGBA, grey or palette.

Rasters that are only published as rendered maps (e.g. CORINE through the Spanish IDEE WMS) are read back to classes
by their exact legend colours; decode() returns the pixels as (r, g, b) tuples, row by row.
"""

from __future__ import annotations

import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}  # colour type → samples per pixel


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def decode(data: bytes) -> tuple[int, int, list[list[tuple[int, int, int]]]]:
    """(width, height, rows of (r, g, b)). Transparent pixels (alpha 0, or a tRNS palette entry of 0) are None."""
    if data[:8] != SIGNATURE:
        raise ValueError("not a PNG file")
    pos, idat, palette, trns = 8, [], None, None
    width = height = depth = ctype = interlace = None
    while pos < len(data):
        (n,) = struct.unpack(">I", data[pos:pos + 4])
        kind, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if kind == b"IHDR":
            width, height, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            palette = [tuple(body[i:i + 3]) for i in range(0, len(body), 3)]
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    if depth != 8 or interlace or ctype not in CHANNELS:
        raise ValueError(f"unsupported PNG: bit depth {depth}, colour type {ctype}, interlace {interlace}")
    bpp = CHANNELS[ctype]
    raw = zlib.decompress(b"".join(idat))
    stride = width * bpp
    rows, prev, i = [], bytearray(stride), 0
    for _ in range(height):
        ftype, line = raw[i], bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b = prev[x]
            c = prev[x - bpp] if x >= bpp else 0
            if ftype == 1:
                line[x] = (line[x] + a) & 255
            elif ftype == 2:
                line[x] = (line[x] + b) & 255
            elif ftype == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif ftype == 4:
                line[x] = (line[x] + _paeth(a, b, c)) & 255
            elif ftype != 0:
                raise ValueError(f"bad PNG filter {ftype}")
        prev = line
        rows.append(_pixels(line, ctype, palette, trns))
    return width, height, rows


def _pixels(line: bytearray, ctype: int, palette, trns) -> list:
    if ctype == 2:
        return [tuple(line[k:k + 3]) for k in range(0, len(line), 3)]
    if ctype == 6:
        return [tuple(line[k:k + 3]) if line[k + 3] else None for k in range(0, len(line), 4)]
    if ctype == 3:
        return [None if trns and v < len(trns) and trns[v] == 0 else palette[v] for v in line]
    if ctype == 0:
        return [(v, v, v) for v in line]
    return [(line[k],) * 3 if line[k + 1] else None for k in range(0, len(line), 2)]  # grey + alpha


def encode_rgb(rows: list[list[tuple[int, int, int]]]) -> bytes:
    """An 8-bit RGB PNG (filter 0), for tests."""
    h, w = len(rows), len(rows[0])
    raw = b"".join(b"\x00" + bytes(v for px in row for v in px) for row in rows)

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    return SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
