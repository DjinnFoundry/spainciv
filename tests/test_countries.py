"""Country configurations, per-country registries and the Spanish reference data."""

import json
import unittest
from pathlib import Path

import pipeline.__main__ as cli
from pipeline import countries
from pipeline.build import BUILDERS, builders_for, requires
from pipeline.sources import sources_for
from pipeline.sources.es.provinces import PROVINCES, display_name
from pipeline.sources.etopo import Etopo


class RegistryTest(unittest.TestCase):
    def test_known_countries(self):
        self.assertEqual(set(countries.COUNTRIES), {"us", "es"})
        self.assertEqual(countries.active().id, "us")

    def test_using_restores(self):
        with countries.using("es") as c:
            self.assertEqual(countries.active().id, "es")
            self.assertEqual(c.product, "spainciv")
        self.assertEqual(countries.active().id, "us")

    def test_using_with_dirs(self):
        with countries.using(interim_dir=Path("/tmp/x")):
            self.assertEqual(countries.active().interim_dir, Path("/tmp/x"))
            self.assertEqual(countries.active().id, "us")
        self.assertNotEqual(countries.active().interim_dir, Path("/tmp/x"))

    def test_unknown_country(self):
        with self.assertRaises(SystemExit):
            countries.set_active("xx")

    def test_us_keeps_its_output_folders(self):
        us, es = countries.COUNTRIES["us"], countries.COUNTRIES["es"]
        self.assertEqual(us.web_data_dir.parts[-2:], ("web", "data"))
        self.assertEqual(es.web_data_dir.parts[-3:], ("sites", "es", "data"))
        self.assertNotEqual(us.interim_dir, es.interim_dir)

    def test_serves(self):
        class OnlyUs:
            COUNTRIES = ("us",)

        self.assertTrue(countries.serves(OnlyUs, "us"))
        self.assertFalse(countries.serves(OnlyUs, "es"))
        self.assertTrue(countries.serves(object(), "es"))

    def test_builders_per_country(self):
        self.assertEqual(list(BUILDERS), list(builders_for("us")))
        es = builders_for("es")
        self.assertEqual(list(es)[0], "world")
        self.assertEqual(list(es)[-1], "catalog")
        self.assertNotIn("military", es)

    def test_requires_per_country(self):
        world = BUILDERS["world"]
        self.assertEqual(requires(world, "us"), ["census_boundaries", "natural_earth", "etopo", "nlcd"])
        self.assertIn("siane", requires(world, "es"))
        self.assertEqual(requires(BUILDERS["catalog"], "es"), [])

    def test_sources_per_country(self):
        us = {s.id for s in sources_for("us")}
        es = {s.id for s in sources_for("es")}
        self.assertIn("acs_1yr", us)
        self.assertIn("siane", es)
        self.assertFalse(us & es, "a source id belongs to one country")

    def test_cli_selects_country(self):
        before = (cli.BUILDERS, cli.BY_ID, cli.SOURCES)
        try:
            cli.select_country("es")
            self.assertIn("siane", cli.BY_ID)
            self.assertNotIn("cities", cli.BUILDERS)
        finally:
            cli.select_country("us")
            cli.BUILDERS, cli.BY_ID, cli.SOURCES = before

    def test_web_block(self):
        es = countries.COUNTRIES["es"]
        block = es.web_block(es.map_projection(-700.0, 520.0, es.margin_km))
        self.assertEqual(block["levels"]["region"], {"one": "Provincia", "many": "Provincias"})
        self.assertEqual(block["projection"]["kind"], "laea")
        self.assertEqual(block["projection"]["insets"][0]["name"], "Canarias")
        self.assertEqual(block["projection"]["margin"], es.margin_km)
        json.dumps(block, allow_nan=False)


class InsetOcclusionTest(unittest.TestCase):
    def test_sea_under_the_canary_box_is_occluded(self):
        proj = countries.COUNTRIES["es"].map_projection(0, 0, 0)
        box = proj.base.insets[0].box
        lon, lat = proj.base.base.inverse((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)  # real place under the box
        self.assertTrue(proj.occluded(lon, lat))
        self.assertFalse(proj.occluded(-15.43, 28.1))  # Las Palmas itself is drawn there
        self.assertFalse(proj.occluded(-3.7, 40.4))

    def test_us_never_occludes(self):
        proj = countries.COUNTRIES["us"].map_projection(0, 0, 0)
        self.assertFalse(proj.occluded(-100, 40))


class SpainReferenceTest(unittest.TestCase):
    def test_52_provinces(self):
        self.assertEqual(sorted(PROVINCES), [f"{i:02d}" for i in range(1, 53)])
        abbrs = [a for a, _ in PROVINCES.values()]
        self.assertEqual(len(set(abbrs)), 52)

    def test_display_name(self):
        self.assertEqual(display_name("Coruña, A"), "A Coruña")
        self.assertEqual(display_name("Balears, Illes"), "Illes Balears")
        self.assertEqual(display_name("Palmas, Las"), "Las Palmas")
        self.assertEqual(display_name("Rioja, La"), "La Rioja")
        self.assertEqual(display_name("Madrid"), "Madrid")


class EtopoWindowsTest(unittest.TestCase):
    def test_us_file_and_url_unchanged(self):
        ((url, file),) = Etopo()._files()
        self.assertEqual(file, "etopo_lat22_56_lon-131_-60_stride5.csv")
        self.assertEqual(url, "https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180.csv?altitude%5B(22):5:(56)%5D%5B(-131):5:(-60)%5D")

    def test_spain_bands_tile_the_peninsula_without_shared_rows(self):
        es = {s.id: s for s in sources_for("es")}["etopo_es"]
        *bands, canarias = es.WINDOWS
        self.assertEqual(canarias, ((27.4, 29.6), (-18.4, -13.2)))
        self.assertEqual(bands[0][0][0], 32.5)
        self.assertEqual(bands[-1][0][1], 44.6)
        for (lat_a, _), (lat_b, _) in zip(bands, bands[1:]):
            self.assertAlmostEqual(lat_b[0] - lat_a[1], 1 / 60, places=3)  # next band starts one arc-minute row later
        self.assertTrue(all("stride1" in f for _, f in es._files()))


if __name__ == "__main__":
    unittest.main()


class SpainBuilderTest(unittest.TestCase):
    def test_yields_keep_keys_and_gold_is_euros(self):
        from pipeline.build import spain
        from pipeline.build.yields import YIELDS

        ys = spain.yields_es()
        self.assertEqual([y["key"] for y in ys], [y["key"] for y in YIELDS])
        self.assertEqual({y["key"]: y["unit"] for y in ys}["gold"], "eur")
        self.assertTrue(all("ACS" not in y["description"] for y in ys))

    def test_econ_never_invents(self):
        from pipeline.build import spain

        e = spain.econ(250_000, None, 2023)
        self.assertEqual(e["population"], 250_000)
        self.assertIsNone(e["gdp"])
        self.assertIsNone(e["gdp_year"], "no GDP, no GDP year")
        self.assertTrue(all(v is None for v in e["yields"].values()))
        p = spain.econ(6_900_000, 2.6e11, 2023)
        self.assertEqual(p["yields"]["gold"], 2.6e11)
        self.assertIsNone(p["yields"]["food"])

    def test_growth(self):
        from pipeline.build import spain

        self.assertAlmostEqual(spain.growth_of({"2021": 100, "2025": 110}, [2021, 2025]), 0.1)
        self.assertIsNone(spain.growth_of({"2025": 110}, [2021, 2025]))
        self.assertIsNone(spain.growth_of({"2021": 100, "2025": 110}, []))

    def test_spain_builder_serves_only_spain(self):
        self.assertIn("spain", builders_for("es"))
        self.assertNotIn("spain", BUILDERS)


class PngAndCorineTest(unittest.TestCase):
    def test_png_roundtrip_with_filters(self):
        import zlib

        from pipeline.core import png

        rows = [[(230, 0, 77), (255, 255, 168), (0, 166, 0)], [(255, 255, 255), (230, 0, 77), (1, 2, 3)]]
        self.assertEqual(png.decode(png.encode_rgb(rows)), (3, 2, rows))
        # Same image with an Up (2) filter on the second row and a Paeth (4) filter on the first.
        raw0 = bytes(v for px in rows[0] for v in px)
        raw1 = bytes(v for px in rows[1] for v in px)
        up = bytes((b - a) & 255 for a, b in zip(raw0, raw1))
        paeth = bytes((raw0[i] - (raw0[i - 3] if i >= 3 else 0)) & 255 for i in range(len(raw0)))  # Paeth = left on row 0
        data = png.encode_rgb(rows)
        start = data.index(b"IDAT") + 4
        length = int.from_bytes(data[start - 8:start - 4], "big")
        body = zlib.compress(b"\x04" + paeth + b"\x02" + up)
        import struct

        chunk = struct.pack(">I", len(body)) + b"IDAT" + body + struct.pack(">I", zlib.crc32(b"IDAT" + body))
        filtered = data[:start - 8] + chunk + data[start + length + 4:]
        self.assertEqual(png.decode(filtered)[2], rows)

    def test_corine_legend_is_exact_and_complete(self):
        from pipeline.sources.es import corine

        self.assertEqual(len(corine.CLC), 44)
        self.assertEqual(len(corine.BY_RGB), 44, "every class has its own colour")
        chars, unknown = corine.classify([[(230, 0, 77), (255, 255, 255), (12, 34, 56)]])
        self.assertEqual(chars, [corine.CHAR[111] + ".."])
        self.assertEqual(unknown, {(12, 34, 56): 1})

    def test_corine_tiles_cover_the_windows(self):
        from pipeline.sources.es import corine

        for window in corine.WINDOWS.values():
            boxes = [b for _, b in corine.tiles(window)]
            self.assertLessEqual(min(b[0] for b in boxes), window[0])
            self.assertGreaterEqual(max(b[2] for b in boxes), window[2])
            self.assertLessEqual(min(b[1] for b in boxes), window[1])
            self.assertGreaterEqual(max(b[3] for b in boxes), window[3])

    def test_multi_tile_lookup(self):
        from pipeline.build.world_inputs import raster_lookup

        raster = {"legend": {"a": 41, "b": 82, ".": 0}, "rasters": [
            {"x0": 0.5, "dx": 1, "y0": 1.5, "dy": -1, "cols": 2, "rows": ["ab", "ba"]},
            {"x0": 10.5, "dx": 1, "y0": 1.5, "dy": -1, "cols": 1, "rows": ["b", "."]},
        ]}
        at = raster_lookup(raster, lambda lon, lat: (lon, lat))
        self.assertEqual(at(0.6, 1.4), 41)
        self.assertEqual(at(1.6, 1.4), 82)
        self.assertEqual(at(10.5, 0.5), 0)
        self.assertIsNone(at(5, 5))


class ReliefThresholdsTest(unittest.TestCase):
    def test_us_rule_text_and_classes_unchanged(self):
        from pipeline.build import world

        self.assertEqual(world.RELIEF_TABLE[0]["rule"], "Elevation standard deviation inside the hex under 85 m.")
        self.assertEqual(world.RELIEF_TABLE[2]["rule"], "Elevation standard deviation ≥ 260 m, or mean elevation ≥ 2,300 m.")
        self.assertEqual(countries.COUNTRIES["us"].relief_std_m, (85.0, 260.0))
        self.assertEqual(world.classify_relief(500, 84.9), world.FLAT)
        self.assertEqual(world.classify_relief(500, 85), world.HILLS)
        self.assertEqual(world.classify_relief(500, 260), world.MOUNTAINS)

    def test_spain_uses_its_calibrated_thresholds(self):
        from pipeline.build import world

        hills, mountains = countries.COUNTRIES["es"].relief_std_m
        self.assertLess(hills, 85)
        self.assertEqual(world.classify_relief(700, hills, hills, mountains), world.HILLS)
        self.assertEqual(world.classify_relief(700, mountains, hills, mountains), world.MOUNTAINS)
        self.assertIn(f"{hills:g} m", world.relief_table(hills, mountains)[1]["rule"])


class IncomeLensTest(unittest.TestCase):
    def test_population_weighted_and_null_without_data(self):
        from pipeline.build.spain import income_lens

        adrh = {"data": {"year": 2024, "municipalities": {"28079": {"net_per_person": 20000}, "28065": {"net_per_person": 10000}}}}
        geoids = ["28079", "28065", "44001"]
        weights = [[(0, 300.0), (1, 100.0)], [(2, 50.0)], []]
        lens = income_lens(adrh, geoids, weights)
        self.assertEqual(lens["values"], [17500, None, None])
        self.assertEqual((lens["id"], lens["format"], lens["source"]), ("income", "eur", "ine_adrh"))
        self.assertIn("2024", lens["description"])

    def test_adrh_keeps_municipal_rows_only(self):
        import tempfile
        from pathlib import Path
        from unittest import mock

        from pipeline.sources.es.ine import IneAdrh

        csv_text = (
            "﻿Municipios;Distritos;Secciones;Indicadores de renta media;Periodo;Total\n"
            + "".join(f"{c:05d} M{c};;;Renta neta media por persona;2024;1{c % 10}.000\n" for c in range(1, 7002))
            + "01001 Alegría-Dulantzi;0100101 Alegría-Dulantzi distrito 01;;Renta neta media por persona;2024;99.999\n"
            + "00001 M1;;;Renta neta media por hogar;2024;45.419\n"
        )
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "30824.csv").write_text(csv_text, encoding="utf-8")
            src = IneAdrh()
            with mock.patch.object(type(src), "raw_dir", new_callable=mock.PropertyMock, return_value=Path(d)):
                out = src.process()
        self.assertEqual(out["year"], 2024)
        self.assertEqual(out["municipalities"]["01001"]["net_per_person"], 11000.0)  # the district row is ignored
        self.assertEqual(out["municipalities"]["00001"]["net_per_household"], 45419.0)


class SpainJobsTest(unittest.TestCase):
    def test_sections_map_to_industries_and_yields(self):
        from pipeline.build import spain

        sections = {s: 10 for s in "ABCDEFGHIJKLMNOPQRSTU"} | {"total": 210}
        jobs = spain.jobs_of(sections)
        self.assertEqual(jobs["utilities"], 20)  # D + E
        self.assertEqual(jobs["other"], 30)  # S + T + U
        self.assertEqual(sum(jobs.values()), 210)
        e = spain.econ(1000, 5e9, 2024, sections)
        self.assertEqual(e["employed"], 210)
        self.assertEqual(e["yields"], {"food": 10, "production": 30, "gold": 5e9, "science": 20, "culture": 10})
        self.assertIsNone(spain.jobs_of(None))
        partial = spain.econ(1000, None, None, {s: 10 for s in "ABDEFGHIJKLMNOPQRSTU"})  # no section C
        self.assertIsNone(partial["jobs"]["manufacturing"])
        self.assertIsNone(partial["yields"]["production"], "a sum with an unknown part is unknown")
        self.assertEqual(partial["yields"]["food"], 10)

    def test_every_industry_has_a_label_and_a_known_key(self):
        from pipeline.build import spain
        from pipeline.build.yields import INDUSTRY_LINES

        self.assertEqual(set(spain.INDUSTRIES), {k for k, _ in spain.CNAE.values()})
        self.assertTrue(set(spain.INDUSTRIES) <= set(INDUSTRY_LINES))



class CensoOcupadosTest(unittest.TestCase):
    def test_regions_and_municipalities(self):
        import tempfile
        from pathlib import Path
        from unittest import mock

        from pipeline.sources.es.ine import IneCensoOcupados
        from pipeline.sources.es.provinces import PROVINCES

        head = "\ufeffTotal Nacional;Comunidades y Ciudades Autónomas;Provincias;Actividad económica;Edad;Sexo;Periodo;Total\n"
        regions = head + "Total Nacional;;;Total CNAE;16 y más años;Total;2024;20.373.148\n"
        regions += "Total Nacional;;;A Agricultura, ganadería, silvicultura y pesca;16 y más años;Total;2024;829.713\n"
        regions += "Total Nacional;10 Comunitat Valenciana;;C Industria manufacturera;16 y más años;Total;2024;1\n"  # a community
        regions += "Total Nacional;;;A Agricultura, ganadería, silvicultura y pesca;De 16 a 19 años;Total;2024;5\n"  # an age band
        for code in PROVINCES:
            regions += f"Total Nacional;10 X;{code} P;C Industria manufacturera;16 y más años;Total;2024;1.000\n"
            regions += f"Total Nacional;10 X;{code} P;No consta;16 y más años;Total;2024;7\n"
        munis = "\ufeffMunicipios de 500 habitantes o más;Sexo;Actividad económica;Periodo;Total\n"
        munis += "12040 Castelló de la Plana/Castellón de la Plana;Total;C Industria manufacturera;2024;10.302\n"
        munis += "12040 Castelló de la Plana/Castellón de la Plana;Mujeres;C Industria manufacturera;2024;3.000\n"
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "69962.csv").write_text(regions, encoding="utf-8")
            (Path(d) / "69992.csv").write_text(munis, encoding="utf-8")
            src = IneCensoOcupados()
            with mock.patch.object(type(src), "raw_dir", new_callable=mock.PropertyMock, return_value=Path(d)):
                out = src.process()
        self.assertEqual(out["year"], 2024)
        self.assertEqual(out["nation"], {"total": 20373148, "A": 829713})
        self.assertEqual(out["provinces"]["12"], {"C": 1000})  # "No consta" only counts in the totals INE gives
        self.assertEqual(out["municipalities"], {"12040": {"C": 10302}})


class SpainDistrictsTest(unittest.TestCase):
    def test_catalog_follows_the_us_order_without_encampment(self):
        from pipeline.build import districts, spain_districts

        ids = [d["id"] for d in spain_districts.CATALOG]
        self.assertNotIn("encampment", ids)
        self.assertEqual(ids, [i for i in districts.IDS if i in ids])
        for d in spain_districts.CATALOG:
            self.assertTrue(all(len(c) == 2 and c.isdigit() for c in d["naics"]), d["id"])
            self.assertTrue(set(d["sub"]) <= set(d["naics"]), d["id"])

    def test_ceramics_city(self):
        from pipeline.build import spain_districts as SD
        from pipeline.build.districts import badge_district, badge_for, evaluate

        nation = {"total": 1_000_000, "23": 5_000, "10": 50_000, "47": 100_000}
        city = {"total": 100_000, "23": 4_000, "10": 5_000, "47": 10_000}  # ceramics at 8× the national share
        m = SD.CensusMetrics({"municipalities": {"12040": city}, "nation": nation})
        dists = evaluate(m, ["12040"], city["total"], False, SD.CATALOG)
        self.assertEqual([d["id"] for d in dists], ["industrial_zone"])
        self.assertEqual(dists[0]["sub"], "23")
        self.assertIsNone(dists[0]["avg_pay"], "the census has no wages")
        badge = badge_for(badge_district(dists), False, False, SD.BY_ID, "census")
        self.assertEqual((badge["label"], badge["basis"]), ("Ciudad de la cerámica", "census"))
        self.assertIsNone(m.industry(["23"], SD.ALL, ["99999"])["emp"], "a city without census divisions has no data")


class GeometryHelpersTest(unittest.TestCase):
    def test_ring_centroid_and_area(self):
        from pipeline.core.geo import ring_area, ring_centroid

        square = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
        self.assertEqual(ring_area(square), 4.0)
        self.assertEqual(ring_area(list(reversed(square))), -4.0)
        self.assertEqual(ring_centroid(square), (1.0, 1.0))
        self.assertEqual(ring_centroid([(1.0, 1.0), (1.0, 1.0), (1.0, 1.0)]), (1.0, 1.0))

    def test_gpkg_wkb(self):
        import sqlite3
        import struct
        import tempfile
        from pathlib import Path

        from pipeline.core.gpkg import features, wkb_geometry

        poly = struct.pack("<BII", 1, 6, 1) + struct.pack("<BII", 1, 3, 1) + struct.pack("<I", 4) + struct.pack(
            "<8d", 0, 0, 1, 0, 1, 1, 0, 0)  # MULTIPOLYGON with one ring, little-endian
        header = b"GP" + bytes([0, 0b00000011]) + struct.pack("<i", 4258) + struct.pack("<4d", 0, 1, 0, 1)  # xy envelope
        self.assertEqual(wkb_geometry(header + poly), ("polygon", [[(0, 0), (1, 0), (1, 1), (0, 0)]]))
        point = struct.pack(">BI", 0, 1) + struct.pack(">2d", -3.7, 40.4)  # big-endian POINT
        self.assertEqual(wkb_geometry(b"GP" + bytes([0, 0]) + struct.pack("<i", 4258) + point), ("point", [(-3.7, 40.4)]))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t.gpkg"
            con = sqlite3.connect(path)
            con.executescript("create table gpkg_contents (table_name, data_type, srs_id);"
                              "create table gpkg_geometry_columns (table_name, column_name, geometry_type_name);"
                              "insert into gpkg_contents values ('m', 'features', 4258);"
                              "insert into gpkg_geometry_columns values ('m', 'geom', 'MULTIPOLYGON');"
                              "create table m (fid integer primary key, geom blob, id_ine text);")
            con.execute("insert into m values (1, ?, '12040')", (header + poly,))
            con.commit()
            con.close()
            (props, kind, rings), = list(features(path))
        self.assertEqual((props["id_ine"], kind, len(rings)), ("12040", "polygon", 1))



class UrbanAreasTest(unittest.TestCase):
    def setUp(self):
        self.muni = {
            "08019": {"name": "Barcelona", "pop": {"2024": 1_700_000}},
            "08094": {"name": "Granada, La", "pop": {"2024": 2_300}},
            "18087": {"name": "Granada", "pop": {"2024": 230_000}},
            "08023": {"name": "Bigues i Riells del Fai", "pop": {"2024": 9_000}},
            "35016": {"name": "Palmas de Gran Canaria, Las", "pop": {"2024": 380_000}},
        }
        self.centre = {"08019": (2.17, 41.38), "08094": (1.72, 41.37), "18087": (-3.60, 37.18), "08023": (2.23, 41.68),
                       "35016": (-15.43, 28.1)}

    def area(self, members, pop, n=None):
        return {"name": "X", "label": "ÁREA URBANA DE BARCELONA", "municipalities": n or len(members), "population": pop,
                "members": members}

    def test_names_aliases_and_homonyms(self):
        from pipeline.build.spain import name_keys, urban_areas

        self.assertIn("las palmas de gran canaria", name_keys("Palmas de Gran Canaria, Las"))
        self.assertIn("alacant", name_keys("Alicante/Alacant"))
        (a,) = urban_areas([self.area(["Barcelona", "Granada, La", "Bigues i Riells"], 1_711_300)], self.muni, self.centre)
        self.assertEqual(a["members"], ["08019", "08094", "08023"])  # La Granada next to Barcelona, not Granada city
        self.assertEqual((a["id"], a["full"]), ("08019", "Área urbana de Barcelona"))
        (b,) = urban_areas([self.area(["Las Palmas de Gran Canaria"], 380_000)], self.muni, self.centre)
        self.assertEqual(b["members"], ["35016"])

    def test_mismatches_fail_loudly(self):
        from pipeline.build.spain import urban_areas

        with self.assertRaises(RuntimeError):
            urban_areas([self.area(["Barcelona", "Nowhere"], 1_700_000)], self.muni, self.centre)
        with self.assertRaises(RuntimeError):  # population off by more than 3%
            urban_areas([self.area(["Barcelona"], 2_000_000)], self.muni, self.centre)

    def test_sums(self):
        from pipeline.build.spain import add_sections, add_series

        self.assertEqual(add_series([{"2024": 1, "2025": 2}, {"2024": 10}]), {"2024": 11, "2025": None})
        self.assertEqual(add_sections([{"A": 1, "total": 5}, None, {"A": 2, "total": 7}]), {"A": 3, "total": 12})
        self.assertIsNone(add_sections([None, None]))


class XlsxTest(unittest.TestCase):
    def test_shared_inline_and_sparse_cells(self):
        import tempfile
        import zipfile
        from pathlib import Path

        from pipeline.core.xlsx import sheets

        m = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        r = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
        parts = {
            "xl/workbook.xml": f'<workbook {m} {r}><sheets><sheet name="LISTADO" sheetId="1" r:id="rId1"/></sheets></workbook>',
            "xl/_rels/workbook.xml.rels": '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
            "xl/sharedStrings.xml": f"<sst {m}><si><t>ÁREA URBANA DE MADRID</t></si><si><r><t>Mad</t></r><r><t>rid</t></r></si></sst>",
            "xl/worksheets/sheet1.xml": f'<worksheet {m}><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="D1"><v>6495480</v></c></row>'
            f'<row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2" t="inlineStr"><is><t>x</t></is></c></row></sheetData></worksheet>',
        }
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t.xlsx"
            with zipfile.ZipFile(path, "w") as z:
                for name, text in parts.items():
                    z.writestr(name, text)
            rows = sheets(path)["LISTADO"]
        self.assertEqual(rows, [["ÁREA URBANA DE MADRID", None, None, "6495480"], ["Madrid", "x"]])


class SpainRoadsTest(unittest.TestCase):
    def test_road_classes(self):
        from pipeline.build.infrastructure import us_road_class
        from pipeline.build.spain_infrastructure import es_road_class

        road = {"type": "Major Highway", "expressway": 1, "scalerank": 9, "name": None, "level": None}
        self.assertEqual(es_road_class(road), (0, None))
        self.assertEqual(es_road_class({**road, "expressway": 0, "scalerank": 6}), (1, None))
        self.assertIsNone(es_road_class({**road, "expressway": 0, "scalerank": 9}))
        self.assertIsNone(es_road_class({**road, "type": "Ferry Route", "expressway": 0, "scalerank": 3}))
        self.assertEqual(us_road_class({**road, "level": "Interstate", "name": "95"}), (0, "I-95"))


class SpainWondersTest(unittest.TestCase):
    def test_names(self):
        from pipeline.build.spain_wonders import short_name, slug
        from pipeline.sources.es.oapn import number

        self.assertEqual(short_name("Parque Nacional de la Sierra de Guadarrama"), "Sierra de Guadarrama")
        self.assertEqual(short_name("Parque Nacional Marítimo-Terrestre del Archipiélago de Cabrera"), "Archipiélago de Cabrera")
        self.assertEqual(short_name("Parque Nacional del Teide"), "Teide")
        self.assertEqual(slug("Parque Nacional de Doñana"), "donana")
        from pipeline.build.spain_wonders import motif
        from pipeline.sources.es.wikidata import label, point

        self.assertEqual(motif("Catedral de Burgos", False), "spire")
        self.assertEqual(motif("Alhambra, Generalife y Albaicín de Granada", False), "rotunda")
        self.assertEqual(motif("Cueva de Altamira", False), "mound")
        self.assertEqual(motif("Parque Nacional del Teide", True), "peak")
        self.assertEqual(motif("Las Médulas", False), "obelisk")
        self.assertIsNone(label({"sLabel": {"value": "Q696803"}}), "the label service echoes the QID when it has no label")
        self.assertEqual(label({"sLabel": {"value": "Las Médulas"}}), "Las Médulas")
        self.assertEqual(point("Point(-6.759002 42.458699)"), (-6.759, 42.4587))
        self.assertEqual(number("18.396,00"), 18396.0)
        self.assertIsNone(number(None))
