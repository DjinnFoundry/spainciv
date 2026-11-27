"""AEMET's official 1991-2020 normals by province and for the peninsula (Estadística de Vigilancia del Clima).

AEMET interpolates its stations to a grid and averages the grid over each province (evc_generalidades.pdf): mean
temperature, mean maximum, mean minimum (°C) and precipitation (mm) for each month and the year, for the 50 provinces,
Ceuta, Melilla and "ESPAÑA PENINSULAR". The CSVs are Latin-1, `;`-separated, one row per region.
"""

from __future__ import annotations

import calendar
import csv
import io
import zipfile

from ...core.source import Source, SourceInfo

URL = "https://www.aemet.es/documentos/es/datos_abiertos/Estadisticas/Vigilancia_Clima/evc_normales_1991-2020.zip"
ZIP = "evc_normales_1991-2020.zip"
PARAMS = {"tmed": "TMED", "tmax": "TMAX", "tmin": "TMIN", "prec": "PREC"}
PENINSULA = "ESPAÑA PENINSULAR"
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre"]
# AEMET's province names → INE province code (pipeline/sources/es/provinces.py).
PROVINCE_CODES = {
    "ARABA/ALAVA": "01", "ALBACETE": "02", "ALICANTE/ALACANT": "03", "ALMERIA": "04", "AVILA": "05", "BADAJOZ": "06",
    "ILLES BALEARS": "07", "BARCELONA": "08", "BURGOS": "09", "CACERES": "10", "CADIZ": "11",
    "CASTELLON/CASTELLÓ": "12", "CIUDAD REAL": "13", "CORDOBA": "14", "A CORUÑA": "15", "CUENCA": "16", "GIRONA": "17",
    "GRANADA": "18", "GUADALAJARA": "19", "GIPUZKOA": "20", "HUELVA": "21", "HUESCA": "22", "JAEN": "23", "LEON": "24",
    "LLEIDA": "25", "LA RIOJA": "26", "LUGO": "27", "MADRID": "28", "MALAGA": "29", "MURCIA": "30", "NAVARRA": "31",
    "OURENSE": "32", "ASTURIAS": "33", "PALENCIA": "34", "LAS PALMAS": "35", "PONTEVEDRA": "36", "SALAMANCA": "37",
    "SANTA CRUZ DE TENERIFE": "38", "CANTABRIA": "39", "SEGOVIA": "40", "SEVILLA": "41", "SORIA": "42",
    "TARRAGONA": "43", "TERUEL": "44", "TOLEDO": "45", "VALENCIA/VALÈNCIA": "46", "VALLADOLID": "47", "BIZKAIA": "48",
    "ZAMORA": "49", "ZARAGOZA": "50", "CEUTA": "51", "MELILLA": "52",
}


def rows(text: str) -> dict[str, list[float]]:
    """One CSV: region → its 12 monthly values (the annual column is left out)."""
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    out = {}
    for r in reader:
        region = r["región"].strip()
        if region in out:
            raise ValueError(f"{region}: two rows")
        out[region] = [float(r[m]) for m in MONTHS]
    return out


def by_province(tables: dict[str, dict[str, list[float]]]) -> dict[str, dict[str, list[float]]]:
    """{param: {AEMET name: [12]}} → {INE code: {param: [12]}}. Every name must map to its own code."""
    names = {n for t in tables.values() for n in t}
    if unmapped := sorted(names - set(PROVINCE_CODES)):
        raise ValueError(f"AEMET province names without an INE code: {unmapped}")
    if missing := sorted(set(PROVINCE_CODES) - names):
        raise ValueError(f"provinces missing from AEMET's tables: {missing}")
    if len(set(PROVINCE_CODES.values())) != len(PROVINCE_CODES):
        raise ValueError("two AEMET names share an INE code")
    return {code: {p: tables[p][name] for p in tables} for name, code in sorted(PROVINCE_CODES.items(), key=lambda kv: kv[1])}


def read_zip(path) -> tuple[dict, dict, list]:
    """(provinces {INE code: {param: [12]}}, peninsula {param: [12]}, the files' dates)."""
    with zipfile.ZipFile(path) as z:
        def table(param: str, level: str) -> dict:
            return rows(z.read(f"{PARAMS[param]}_1991_2020_{level}.csv").decode("latin-1"))

        provinces = by_province({p: table(p, "Provincias") for p in PARAMS})
        peninsula = {p: table(p, "Nacional")[PENINSULA] for p in PARAMS}
        dated = sorted({i.date_time[:3] for i in z.infolist()})
    return provinces, peninsula, dated


class AemetNormalesProvincias(Source):
    info = SourceInfo(
        id="aemet_normales_provincias",
        title="Normal values 1991-2020 by province (AEMET, “Estadística de Vigilancia del Clima”)",
        publisher="Agencia Estatal de Meteorología (AEMET)",
        homepage="https://www.aemet.es/es/datos_abiertos/estadisticas/vigilancia_clima",
        license="AEMET Nota legal: reuse allowed citing AEMET as the author (Ley 37/2007 as amended by Ley 18/2015)",
        description="AEMET's monthly normals for 1991-2020 of mean, maximum and minimum temperature and precipitation for "
        "each province, Ceuta, Melilla and the peninsula: station data interpolated to a grid by AEMET and averaged over "
        "each region.",
        used_for=["Climate this month (province chart, month strip, Ceuta and Melilla)"],
    )

    def fetch(self, force=False):
        self.download(URL, ZIP, force=force, expect_binary=True)

    def process(self):
        provinces, peninsula, dated = read_zip(self.raw_dir / ZIP)
        y, m, d = dated[-1]
        when = f"{d} {calendar.month_name[m]} {y}"
        return {"vintage": f"1991-2020 (AEMET CSVs of {when})", "_files": [ZIP],
                "provinces": provinces, "peninsula": peninsula}
