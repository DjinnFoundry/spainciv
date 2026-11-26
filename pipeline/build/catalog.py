"""sources.json – the Almanac's bibliography, generated from the registry + manifests.

Each source cites only the raw files its latest process() used (interim "files"),
or every manifest entry if it did not say.
"""

from ..core.fetch import read_manifest
from ..core.store import load_interim_payload, write_web
from ..countries import active
from ..sources import sources_for
from . import texts_es

# A country whose interface is not in English gives its sources' Almanac texts in its language (by source id).
LOCAL = {"es": texts_es.source}

REQUIRES: list[str] = []
PRODUCES = ["sources.json"]
RUN_LAST = True


def build() -> None:
    out = []
    for s in sources_for(active().id):
        try:
            payload = load_interim_payload(s.id)
        except FileNotFoundError:
            payload = {}
        manifest = read_manifest(s.id)
        used = payload.get("files")  # raw files the latest process() said it used, else cite them all
        names = sorted(manifest) if used is None else [f for f in sorted(used) if f in manifest]
        if used is not None and len(names) < len(used):
            print(f"    ! {s.id}: {len(used) - len(names)} used file(s) missing from manifest")
        files = [
            {"file": name, "url": m["url"], "retrieved": m["retrieved"], "sha256": m["sha256"], "bytes": m["bytes"]}
            for name in names
            for m in [manifest[name]]
        ]
        vintage = payload.get("vintage")
        entry = {**s.info.to_dict(), "vintage": vintage, "files": files}
        out.append(LOCAL.get(active().id, lambda e: e)(entry))
    write_web("sources.json", out)
