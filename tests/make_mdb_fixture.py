"""Regenerate tests/fixtures/bd_embalses_pages.mdb.bz2, the Jet 4 pages tests/test_mdb.py reads.

    uv run python tests/make_mdb_fixture.py [path/to/BD-Embalses.mdb]

Copies from the Boletín Hidrológico's BD-Embalses.mdb (default: the one the pipeline extracted into
data/raw/boletin_hidrologico/) only the pages a read of two data pages needs: the header (page 0), the catalog's
definition (page 2) and data pages, the reservoir table's definition and its first two data pages. Every other page
is left zeroed at its place, so page numbers stay true; bz2 squeezes the zeros to nothing. Only rerun this on purpose.
"""

from __future__ import annotations

import bz2
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.core.mdb import CATALOG_PAGE, PAGE, Jet4  # noqa: E402
from pipeline.core.paths import RAW  # noqa: E402
from pipeline.sources.es.embalses import MDB_FILE, TABLE_PREFIX  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "bd_embalses_pages.mdb.bz2"
DATA_PAGES = 2


def tdef_pages(db: Jet4, pg: int) -> list[int]:
    out = [pg]
    while nxt := struct.unpack_from("<I", db.page(out[-1]), 4)[0]:
        out.append(nxt)
    return out


def main(path: Path) -> None:
    with Jet4(path) as db:
        table = next(t for t in db.tables() if t.startswith(TABLE_PREFIX))
        pg = db.tables()[table]
        owners = db._owners  # filled by tables(): data pages by their table's definition page
        pages = sorted({0, *tdef_pages(db, CATALOG_PAGE), *owners[CATALOG_PAGE], *tdef_pages(db, pg), *owners[pg][:DATA_PAGES]})
        out = bytearray((pages[-1] + 1) * PAGE)
        for n in pages:
            out[n * PAGE:(n + 1) * PAGE] = db.page(n)
    FIXTURE.write_bytes(bz2.compress(bytes(out), 9))
    print(f"{FIXTURE.name}: pages {pages}, {FIXTURE.stat().st_size} bytes")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else RAW / "boletin_hidrologico" / MDB_FILE)
