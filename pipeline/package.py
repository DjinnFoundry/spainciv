"""Build the deploy package: one file, <product>.zip in the project root (usaciv.zip, or spainciv.zip with --country es).
It unzips to a <product>/ folder holding the static site, ready to upload as /<product>/. (dist/<product>/ is the same
folder unzipped, kept for local testing.) The site is web/ with the active country's data as its data/ folder, and the
files pipeline/site.py makes from code over web/'s: index.html, and the social card of a country with a page.

The site gets a copy of the source code as <product>-source.zip, linked from the in-app help, so anyone can download,
run and remix it. Both zips are deterministic (sorted entries, fixed timestamps), so rebuilding from unchanged files
gives byte-identical archives.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from .core.paths import ROOT, WEB
from .core.store import web_dir
from .countries import active
from .site import generated_files

DIST = ROOT / "dist"

# What goes into the source zip (relative to ROOT). Downloads, caches and build output are left out: anyone can
# recreate them with `uv run python -m pipeline all`.
SOURCE_ITEMS = ["README.md", "LICENSE", "NOTICE", "UPSTREAM.md", "CHANGELOG.md", "ROADMAP.md", "DECISIONS.md", "pyproject.toml", "uv.lock", ".gitignore", "docs", "pipeline", "tests", "web", "sites"]
SKIP_NAMES = {"__pycache__", ".DS_Store"}
SKIP_SUFFIXES = {".pyc", ".part"}
# Dev-only pages (art gallery, trailer maker) ship in the source zip but not on the public site.
SITE_SKIP_DIRS = {"dev"}

ZIP_TIME = (2026, 1, 1, 0, 0, 0)


def _files(base: Path, rel_items):
    for item in rel_items:
        p = base / item
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and not (SKIP_NAMES & set(f.relative_to(base).parts)) and f.suffix not in SKIP_SUFFIXES:
                    yield f


def _zip(path: Path, files, base: Path, prefix: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".zip.part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(set(files), key=lambda f: f.relative_to(base).as_posix()):
            info = zipfile.ZipInfo(f"{prefix}/{f.relative_to(base).as_posix()}", ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, f.read_bytes(), compresslevel=9)
    tmp.replace(path)
    return path.stat().st_size


def cmd_package() -> None:
    NAME = active().product
    SITE = DIST / NAME
    SOURCE_ZIP = f"{NAME}-source.zip"
    data = web_dir()
    missing = [p for p in (data / "cities.json", data / "world.json", WEB / "index.html") if not p.exists()]
    if missing:
        raise SystemExit(f"the site is incomplete ({', '.join(map(str, missing))} missing): run `uv run python -m pipeline all` first")
    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir(parents=True)

    # 1. The site: web/ without the dev pages, with the country's data as data/ and the generated files over web/'s.
    site_files = {f.relative_to(WEB): f for f in _files(WEB, ["."]) if f.relative_to(WEB).parts[0] not in SITE_SKIP_DIRS | {"data"}}
    site_files |= {Path("data") / f.relative_to(data): f for f in _files(data, ["."])}
    generated = generated_files()
    for rel, f in site_files.items():
        if rel.as_posix() not in generated:
            dst = SITE / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
    for name, make in generated.items():
        (SITE / name).write_bytes(make())
    n_site = len(site_files.keys() | {Path(name) for name in generated})

    # The site ships the code itself, so the MIT notice (and NOTICE's credit) goes with it, not only in the source zip.
    for name in ("LICENSE", "NOTICE"):
        shutil.copy2(ROOT / name, SITE / name)
        n_site += 1

    # 2. The source code, served next to the site.
    src_files = list(_files(ROOT, SOURCE_ITEMS))
    src_size = _zip(SITE / SOURCE_ZIP, src_files, ROOT, NAME)

    # 3. The whole site as one zip, for uploading.
    bundle = ROOT / f"{NAME}.zip"
    site_size = _zip(bundle, _files(SITE, ["."]), SITE, NAME)
    (DIST / f"{NAME}-site.zip").unlink(missing_ok=True)  # older layout

    mb = lambda b: f"{b / 1e6:.1f} MB"
    print(f"{bundle.name}  ({mb(site_size)})  ← upload this: it unzips to {NAME}/ ({n_site} site files + {SOURCE_ZIP})")
    print(f"  {SOURCE_ZIP}: {len(src_files)} files, {mb(src_size)}")
