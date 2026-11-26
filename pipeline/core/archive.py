"""Deterministic zip archives: entries sorted by name, one fixed timestamp and mode, so the same contents always give
byte-identical bytes (the deploy zips of `pipeline package`, the Unciv mod)."""

from __future__ import annotations

import io
import zipfile

ZIP_TIME = (2026, 1, 1, 0, 0, 0)


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    """A zip of {name in the archive: contents}."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, entries[name], compresslevel=9)
    return buf.getvalue()
