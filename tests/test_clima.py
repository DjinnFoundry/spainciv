"""The climate of the month (Spain): AEMET's sources (province normals, WMO station normals, ROCIO grids) and
clima.json (pipeline/build/spain_clima.py) with its check."""

import unittest

from pipeline.sources.es import aemet_normales as N
from pipeline.sources.es import omm_normales as O


# Trimmed from NCEI's BURGOSVILLAFRIA_8075.csv: its real rows, fewer blocks (and a MaxMon row to skip).
BURGOS_CSV = "\ufeff" + "\r\n".join([
    "World Meteorological Organization Climate Normals for 1991-2020,,,,,,,,,,,,,,,,",
    "Country_Name,Spain,,,,,,,,,,,,,,,",
    "Station_Name,BURGOS/VILLAFRÍA,,,,,,,,,,,,,,,",
    ",,,,,,,,,,,,,,,,",
    "WMO_Number,Latitude,Longitude,Station_Height,,,,,,,,,,,,,,",
    "8075,42|21|25|N,003|37|13|W,891.000000,,,,,,,,,,,,,",
    "Parameter_Code,Parameter_Name,Units,,,,,,,,,,,,,,",
    "1,Precipitation_Total,mm,,,,,,,,,,,,,,",
    "WMO_Number,Parameter_Code,Calculation_Name,Calculation_Code,January,February,March,April,May,June,July,August,"
    "September,October,November,December,Annual",
    "8075,1,Sum,4,47.2,35.0,44.1,59.9,57.3,43.0,24.1,18.8,33.4,62.8,63.3,57.4,546.3",
    "8075,1,MaxMon,19,145.3,83.5,147.1,126.8,194.0,146.0,100.8,63.8,85.0,131.8,151.5,166.4,",
    "8075,3,Mean,1,7.6,9.4,13.1,15.2,19.3,24.3,27.8,27.9,23.3,17.7,11.2,8.4,17.1",
    "8075,4,Mean,1,-0.4,-0.7,1.2,2.9,5.9,9.3,11.4,11.5,8.7,6.0,2.5,0.3,4.9",
    "8075,5,Mean,1,3.6,4.4,7.2,9.1,12.6,16.8,19.6,19.7,16.0,11.8,6.8,4.3,11.0",
    "8075,8,Sum,4,85.4,120.7,176.0,192.6,240.3,278.8,327.4,305.9,229.7,163.1,94.9,82.7,2297.5",
    "8075,15,Count,5,16.6,16.7,11.2,5.6,0.8,0.0,0.0,0.0,0.1,1.5,7.5,14.6,74.6",
])


class WmoStationTest(unittest.TestCase):
    def test_burgos_blocks_and_calculations(self):
        s = O.parse_station(BURGOS_CSV)
        self.assertEqual((s["wmo"], s["name"], s["alt"]), ("08075", "BURGOS/VILLAFRÍA", 891))
        self.assertAlmostEqual(s["lat"], 42 + 21 / 60 + 25 / 3600, places=4)
        self.assertAlmostEqual(s["lon"], -(3 + 37 / 60 + 13 / 3600), places=4)
        self.assertEqual(s["prec"][0], 47.2)  # the Sum row, not MaxMon
        self.assertEqual(s["tmean"][0], 3.6)  # the Mean row
        self.assertEqual(s["tmin"][0], -0.4)
        self.assertEqual(s["frost_lt0"][0], 16.6)  # Count
        self.assertEqual(round(sum(s["sun"]), 1), 2297.5)

    def test_missing_sunshine_is_none(self):
        text = BURGOS_CSV.replace("8075,8,Sum,4,85.4,", "8075,8,Sum,4,-9999,")
        self.assertIsNone(O.parse_station(text)["sun"])
        no_block = "\r\n".join(line for line in BURGOS_CSV.split("\r\n") if not line.startswith("8075,8,"))
        self.assertIsNone(O.parse_station(no_block)["sun"])

    def test_aemet_page_coordinates_win_over_a_wrong_header(self):
        wmo = O.parse_station(BURGOS_CSV.replace("003|37|13|W", "003|37|53|W"))  # a Murcia-like wrong longitude
        page = O.parse_page("<p><b>Estación</b>:&nbsp;Burgos Aeropuerto&nbsp;-&nbsp;<b>Periodo</b> :&nbsp;1981-2010"
                            "&nbsp;-&nbsp;Altitud (m) :&nbsp;891&nbsp;</p><p>Latitud :&nbsp;42° 21' 25'' N&nbsp;-&nbsp;"
                            "Longitud :&nbsp;3° 37' 13'' O</p>")
        s = O.station(wmo, page, {"aemet": "2331", "province": "09"})
        self.assertEqual((s["name"], s["coords"], s["aemet"], s["province"]), ("Burgos Aeropuerto", "aemet", "2331", "09"))
        self.assertAlmostEqual(s["lon"], -(3 + 37 / 60 + 13 / 3600), places=4)
        rota = O.station(wmo, None, {"aemet": None, "province": "09"})
        self.assertEqual((rota["coords"], rota["name"], rota["lon"]), ("wmo", "BURGOS/VILLAFRÍA", wmo["lon"]))

    def test_a_station_without_a_required_parameter_fails(self):
        text = "\r\n".join(line for line in BURGOS_CSV.split("\r\n") if not line.startswith("8075,15,"))
        with self.assertRaisesRegex(ValueError, "frost_lt0"):
            O.station(O.parse_station(text), None, {"aemet": None, "province": "09"})

    def test_committed_table_lists_83_stations_with_provinces(self):
        table = O.read_table()
        self.assertEqual(len(table), 83)
        self.assertEqual(table["08430"], {"aemet": "7178I", "province": "30"})  # Murcia: its header is wrong
        self.assertEqual(table["08449"], {"aemet": None, "province": "11"})  # Rota: no AEMET page
        self.assertTrue(all(len(r["province"]) == 2 for r in table.values()))


class ProvinceNormalsTest(unittest.TestCase):
    def csv(self, names, param="Temperatura media"):
        head = "Parámetro;periodo de referencia;región;" + ";".join(N.MONTHS) + ";anual"
        body = [f"{param};1991-2020;{n};" + ";".join(f"{k + m / 10:.1f}" for m in range(12)) + ";9.9"
                for k, n in enumerate(names)]
        return "\r\n".join([head, *body])

    def test_all_52_names_map_to_distinct_ine_codes(self):
        names = list(N.PROVINCE_CODES)
        rows = N.rows(self.csv(names).encode("latin-1").decode("latin-1"))  # the files are Latin-1
        self.assertEqual(rows["CASTELLON/CASTELLÓ"][:2], [names.index("CASTELLON/CASTELLÓ"), names.index("CASTELLON/CASTELLÓ") + 0.1])
        out = N.by_province({p: rows for p in N.PARAMS})
        self.assertEqual(len(out), 52)
        self.assertEqual(sorted(out), [f"{c:02d}" for c in range(1, 53)])
        self.assertEqual(out["46"]["tmed"], rows["VALENCIA/VALÈNCIA"])
        self.assertEqual(out["35"]["prec"], rows["LAS PALMAS"])

    def test_an_unmapped_name_or_a_missing_province_fails(self):
        names = list(N.PROVINCE_CODES)
        with self.assertRaisesRegex(ValueError, "without an INE code"):
            N.by_province({"tmed": N.rows(self.csv(names + ["ATLÁNTIDA"]))})
        with self.assertRaisesRegex(ValueError, "missing"):
            N.by_province({"tmed": N.rows(self.csv(names[1:]))})
        with self.assertRaisesRegex(ValueError, "two rows"):
            N.rows(self.csv(names + names[:1]))

    def test_the_real_zip_when_cached(self):
        from pipeline.core.paths import RAW
        path = RAW / "aemet_normales_provincias" / N.ZIP
        if not path.exists():
            self.skipTest("AEMET normals zip not fetched")
        provinces, peninsula, _ = N.read_zip(path)
        self.assertEqual(provinces["09"]["tmed"][0], 3.6)  # BURGOS, January
        self.assertEqual(round(sum(provinces["09"]["prec"]), 1), 658.4)
        self.assertEqual(len(peninsula["tmed"]), 12)


if __name__ == "__main__":
    unittest.main()
