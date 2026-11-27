"""Reading/writing interim and web output files.

All writes are atomic (temp file + os.replace), so an interrupted run never
leaves a truncated JSON file for the next step or the browser to choke on.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import lang



def interim_dir() -> Path:
    """data/interim (or the active country's own folder): see pipeline/countries."""
    from ..countries import active

    return active().interim_dir


def web_dir() -> Path:
    """web/data (or the active country's own folder): what the browser loads."""
    from ..countries import active

    return active().web_data_dir


def atomic_write_text(path: Path, text: str) -> None:
    """Write `text` to `path` via a sibling temp file and os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def save_interim(name: str, data: dict, *, vintage: str | None = None) -> None:
    """Save data/interim/<name>.json. A "_files" key (raw files used) is stored as payload["files"]."""
    data = dict(data)
    files = data.pop("_files", None)
    payload = {
        "name": name,
        "processed": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "vintage": vintage,
        "data": data,
    }
    if files is not None:
        payload["files"] = sorted(str(f) for f in files)
    atomic_write_text(interim_dir() / f"{name}.json", json.dumps(payload, separators=(",", ":")))


def load_interim_payload(name: str) -> dict:
    path = interim_dir() / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"interim '{name}' missing – run: uv run python -m pipeline process {name}")
    return json.loads(path.read_text())


def load_interim(name: str) -> Any:
    return load_interim_payload(name)["data"]


def _dump(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), allow_nan=False)


def write_web(name: str, data: Any) -> None:
    """Write web data/<name>. For a country in several languages (core/lang.py), its texts go in the first language
    and <name minus .json>.<lang>.json gets the other languages' overlay, written even when empty so the browser can
    always ask for it."""
    from ..countries import active

    langs = active().langs
    base, overlays = lang.split(data, langs) if len(langs) > 1 else (data, {})
    text = _dump(base)
    atomic_write_text(web_dir() / name, text)
    extra = ""
    for code, overlay in overlays.items():
        o = _dump(overlay)
        atomic_write_text(web_dir() / lang.overlay_name(name, code), o)
        extra += f", {code} {len(o) / 1e3:.0f} kB"
    print(f"    → {web_dir().parent.name}/{web_dir().name}/{name} ({len(text) / 1e3:.0f} kB{extra})")


def load_web(name: str, optional: bool = False, texts: bool = False) -> Any:
    """Read a web data file another builder wrote (None if `optional` and it does not exist): its texts in the country's
    first language, or with `texts` as lang.Text in every language (for a builder that writes the file again)."""
    from ..countries import active

    return read_web(web_dir(), name, active().langs if texts else (), optional)


def read_web(folder: Path, name: str, langs: tuple[str, ...] = (), optional: bool = False) -> Any:
    """A web data file of `folder` with the overlays of langs[1:] joined back as lang.Text (none: as it is)."""
    path = Path(folder) / name
    if optional and not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if len(langs) < 2:
        return data
    overlays = {code: json.loads((path.parent / lang.overlay_name(name, code)).read_text(encoding="utf-8")) for code in langs[1:]}
    return lang.join(data, overlays, langs[0])
