"""The climate of the month (Spain): AEMET's sources (province normals, WMO station normals, ROCIO grids) and
clima.json (pipeline/build/spain_clima.py) with its check."""

import unittest

from pipeline.sources.es import aemet_normales as N


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
