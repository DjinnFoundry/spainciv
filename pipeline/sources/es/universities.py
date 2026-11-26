"""Spanish universities and their students by municipality (SIIU, Ministerio de Ciencia, Innovación y Universidades)."""

from __future__ import annotations

from ...core.source import Source, SourceInfo
from ...core.xlsx import sheets

BASE = "https://www.ciencia.gob.es/dam/"
FILES = {
    "students": ("jcr:717ab000-0372-44e4-bec3-e49afcb2838b/Matriculados.xlsx", "Matriculados.xlsx"),
    "centres": ("jcr:6eedf644-5ee3-4dd0-a136-f1bf858cba5d/Clasificaciones-Centros-2025.xlsx", "Clasificaciones-Centros-2025.xlsx"),
    "universities": ("jcr:e783a3d5-8967-492f-bdf2-6196066e859a/Clasificaciones-Universidades-2025.xlsx",
                     "Clasificaciones-Universidades-2025.xlsx"),
}
YEAR = "2024-2025"  # the latest final course (2025-2026 is a provisional preview)


def header_row(rows: list[list], first: str) -> int:
    return next(i for i, r in enumerate(rows) if r and r[0] == first)


class Siiu(Source):
    info = SourceInfo(
        id="siiu_universidades",
        title=f"University students by centre and the municipality of each centre (SIIU, {YEAR})",
        publisher="Sistema Integrado de Información Universitaria, Ministerio de Ciencia, Innovación y Universidades",
        homepage="https://www.ciencia.gob.es/Ministerio/Estadisticas/SIIU.html",
        license="Reuse permitted, commercial or not, citing the Ministerio de Ciencia, Innovación y Universidades",
        description=f"Students enrolled in degree, master's and doctoral programmes in {YEAR} at every centre of every "
        "Spanish university, with the municipality of each centre and whether the university teaches on site.",
        used_for=["Great-university wonders"],
    )

    def fetch(self, force=False):
        for url, file in FILES.values():
            self.download(BASE + url, file, force=force, expect_binary=True)

    def process(self):
        uni_rows = sheets(self.raw_dir / FILES["universities"][1])["Universidades"]
        h = header_row(uni_rows, "Universidad")
        unis = {r[0]: {"name": r[0], "code": r[1], "type": r[2], "on_site": r[3] == "Presencial", "students": 0,
                       "places": {}}
                for r in uni_rows[h + 1:] if r and r[0] and len(r) > 3}
        centre_rows = sheets(self.raw_dir / FILES["centres"][1])["Unidades"]
        h = header_row(centre_rows, "Comunidad autónoma")
        muni_of = {r[3]: r[5] for r in centre_rows[h + 1:] if r and len(r) > 5 and r[3]}
        st = sheets(self.raw_dir / FILES["students"][1])["Matriculados Global por centro"]
        years = st[2]
        col = years.index(YEAR)
        h = header_row(st, "Nivel")
        missing_centres = set()
        for r in st[h + 1:]:
            if len(r) <= col or not r[col] or r[2] not in unis:
                continue
            n = int(float(r[col]))
            centre = r[3]
            muni = muni_of.get(centre)
            u = unis[r[2]]
            u["students"] += n
            if muni:
                key = f"{centre[:2]}|{muni}"
                u["places"][key] = u["places"].get(key, 0) + n
            else:
                missing_centres.add(centre)
        if missing_centres:
            print(f"    {len(missing_centres)} centres without a municipality in the classification (left out of placing)")
        return {"vintage": f"SIIU, students {YEAR}", "_files": [f for _, f in FILES.values()], "year": YEAR,
                "universities": sorted((u for u in unis.values() if u["students"]), key=lambda u: -u["students"])}
