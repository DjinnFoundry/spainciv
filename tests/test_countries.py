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
        self.assertNotIn("military", es)  # the US builder; Spain's military.json comes from its own
        self.assertIn("spain_military", es)
        self.assertNotIn("spain_military", BUILDERS)

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
        self.assertEqual(block["levels"]["region"], {"one": {"es": "Provincia", "en": "Province"},
                                                     "many": {"es": "Provincias", "en": "Provinces"}})
        self.assertEqual(block["name"], {"es": "España", "en": "Spain"})  # split into world.json and world.en.json
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
        self.assertIn("2024", lens["description"]["es"])
        self.assertIn("2024", lens["description"]["en"])

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
        e = spain.econ(1000, 5e9, 2024, sections, 7)
        self.assertEqual(e["employed"], 210)
        self.assertEqual(e["yields"], {"food": 10, "production": 30, "gold": 5e9, "science": 7, "culture": 10})
        self.assertIsNone(spain.econ(1000, 5e9, 2024, sections)["yields"]["science"], "Science is R&D, never the census")
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


class SpainScienceTest(unittest.TestCase):
    """Science = INE R&D personnel by community, shared below it by the census Science workers (J + M)."""

    def test_every_province_in_one_community(self):
        from pipeline.sources.es.ine import UNIPROVINCIAL
        from pipeline.sources.es.provinces import COMMUNITIES, COMMUNITY_OF

        provs = [p for _, ps in COMMUNITIES.values() for p in ps]
        self.assertEqual(sorted(provs), sorted(PROVINCES), "each province exactly once")
        self.assertEqual(len(COMMUNITIES), 19)
        self.assertEqual(COMMUNITY_OF["03"], "10")  # Alicante, Comunitat Valenciana
        self.assertEqual(UNIPROVINCIAL, {"03": "33", "04": "07", "06": "39", "13": "28", "14": "30", "15": "31",
                                         "17": "26", "18": "51", "19": "52"})

    def _process(self, communities_csv: str, series_csv: str) -> dict:
        import tempfile
        from pathlib import Path
        from unittest import mock

        from pipeline.sources.es.ine import IneImasd

        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "82978.csv").write_text(communities_csv, encoding="utf-8")
            (Path(d) / "82944.csv").write_text(series_csv, encoding="utf-8")
            src = IneImasd()
            with mock.patch.object(type(src), "raw_dir", new_callable=mock.PropertyMock, return_value=Path(d)):
                return src.process()

    def _communities_csv(self) -> str:
        from pipeline.sources.es.provinces import COMMUNITIES

        out = "\ufeffComunidades autónomas;Tipo de indicador;Total\n"
        out += "Total Nacional;Gasto en I+D interna (miles de euros);25.321.275\nTotal Nacional;Personal en EJC: Total;310.336,2\n"
        out += "Total Nacional;Personal en EJC: Mujeres;129.278,2\n"
        for code, (name, _) in COMMUNITIES.items():
            v = ".." if code in ("18", "19") else "1.000,5"
            out += f"{code} {name};Personal en EJC: Total;{v}\n{code} {name};Gasto en I+D interna (miles de euros);{v}\n"
        return out

    def test_source_reads_communities_and_dates_them_by_the_series(self):
        series = "\ufeffSectores/unidad;Periodo;Total\nTotal (EJC);2025;310.336,2\nTotal (EJC);2024;295.289,7\n"
        series += "Empresas: Total (EJC);2024;310.336,2\n"  # another line with the same number is not the total
        out = self._process(self._communities_csv(), series)
        self.assertEqual(out["year"], 2025)
        self.assertEqual(out["nation"], {"spending_eur": 25_321_275_000, "personnel_fte": 310336.2})
        self.assertEqual(out["communities"]["13"], {"personnel_fte": 1000.5, "spending_eur": 1_000_500})
        self.assertEqual(out["communities"]["18"], {"personnel_fte": None, "spending_eur": None}, "secret stays null")
        self.assertIn("2025", out["vintage"])

    def test_source_fails_when_the_year_is_unclear(self):
        with self.assertRaises(RuntimeError):
            self._process(self._communities_csv(), "Sectores/unidad;Periodo;Total\nTotal (EJC);2024;295.289,7\n")
        with self.assertRaises(RuntimeError):  # a community missing
            self._process(self._communities_csv().replace("01 Andalucía", "99 Atlántida"),
                          "Sectores/unidad;Periodo;Total\nTotal (EJC);2025;310.336,2\n")

    def test_community_rd_is_shared_by_science_workers(self):
        from pipeline.build import spain

        rd = {"communities": {"10": {"personnel_fte": 3000.0}, "13": {"personnel_fte": 500.0}, "18": {"personnel_fte": None}}}
        provinces = {"03": {"J": 100, "M": 100}, "12": {"J": 50, "M": 50}, "46": {"J": 300, "M": 400}, "28": {"J": 1000, "M": 1500},
                     "51": {"J": 10, "M": 10}}
        rates = spain.rd_rates(rd, provinces)
        self.assertAlmostEqual(rates["10"], 3000 / 1000)  # Comunitat Valenciana: 1000 Science workers
        self.assertAlmostEqual(rates["13"], 500 / 2500)
        self.assertIsNone(rates["18"], "Ceuta: no R&D figure")
        self.assertIsNone(rates["01"], "no R&D row and no census rows")
        shares = [spain.rd_science({p: provinces[p]}, rates) for p in ("03", "12", "46")]
        self.assertEqual(shares, [600, 300, 2100])
        self.assertEqual(sum(shares), 3000, "provinces add up to their community")
        # an area straddling two communities takes each member at its own rate; unpublished members are left out
        self.assertEqual(spain.rd_science({"46250": {"J": 10, "M": 0}, "28079": {"J": 50, "M": 50}, "28001": None}, rates), 50)
        self.assertIsNone(spain.rd_science({"51001": {"J": 1, "M": 1}}, rates))
        self.assertIsNone(spain.rd_science({"46250": {"J": 10}}, rates), "Science workers unknown (no M)")
        self.assertIsNone(spain.rd_science({"46250": None}, rates))

    def test_science_yield_is_rd_with_its_own_source(self):
        from pipeline.build import spain

        ys = {y["key"]: y for y in spain.yields_es(2024, {"vintage": "INE Estadística sobre actividades de I+D, 2025",
                                                           "data": {"year": 2025}})}
        self.assertEqual(ys["science"]["industries"], [], "no census breakdown under an R&D total")
        self.assertEqual(ys["science"]["vintage"]["es"], "INE Estadística sobre actividades de I+D, 2025")
        self.assertIn("I+D del INE, 2025", ys["science"]["description"]["es"])
        self.assertIn("Censo anual de población (2024)", ys["science"]["description"]["es"])
        self.assertIn("INE R&D statistic, 2025", ys["science"]["description"]["en"])
        self.assertNotIn("vintage", ys["food"])
        self.assertEqual(ys["production"]["industries"], ["manufacturing", "construction", "mining"])

class SpainLivingTest(unittest.TestCase):
    """Unemployment, household income and rent of areas, provinces and Spain (spain.living)."""

    def test_unemployment_is_the_areas_own_rate(self):
        from pipeline.build import spain

        rows = [{"employed": 90, "unemployed": 10}, {"employed": 270, "unemployed": 30}, None]  # None: not published
        self.assertEqual(spain.unemployment_rate(rows), 0.1)
        self.assertEqual(spain.unemployment_rate([{"employed": 900, "unemployed": 100}, {"employed": 50, "unemployed": 50}]), 0.1364)
        self.assertIsNone(spain.unemployment_rate([None]))

    def test_household_income_weights_by_households(self):
        from pipeline.build import spain

        # 1,000 people at 20,000 €/person in 400 households (50,000 €) + 1,000 at 10,000 in 500 households (20,000):
        # 30 M € over 900 households, not the plain mean of 50,000 and 20,000.
        rows = [(1000, 20000.0, 50000.0), (1000, 10000.0, 20000.0), (500, None, 30000.0), (None, 9000.0, 20000.0)]
        self.assertEqual(spain.household_income(rows), 33333)
        self.assertIsNone(spain.household_income([(100, None, None)]))

    def test_rent_weights_medians_by_leases(self):
        from pipeline.build import spain

        self.assertEqual(spain.monthly_rent([[[300, 800.0], [100, 1200.0]], None, [[100, 400.0]]]), 800)
        self.assertIsNone(spain.monthly_rent([None, []]))

    def test_living_fields_follow_the_us_contract(self):
        from pipeline.build import spain

        e = spain.econ(1000, None, None, None, living_fields=spain.living([{"employed": 95, "unemployed": 5}], [(10, 1.0, 2.0)],
                                                            [[[1, 100.0]]]))
        self.assertEqual(list(spain.ECON_NULL), [k for k in e if k in spain.ECON_NULL], "same keys, same order")
        self.assertEqual((e["unemployment"], e["median_income"], e["median_rent"]), (0.05, 2, 100))
        self.assertEqual(e["rent_burden"], 600.0, "rent × 12 ÷ income, as in yields.economy")
        self.assertIsNone(e["home_value"], "no official value per dwelling by municipality")
        self.assertIsNone(spain.living([None], [], [None])["rent_burden"])

    def test_censo_actividad_levels(self):
        import tempfile
        from pathlib import Path
        from unittest import mock

        from pipeline.sources.es.ine import IneCensoActividad

        head = "\ufeffTotal Nacional;Provincias;Municipios;Secciones;Sexo;Relación con la actividad;Periodo;Total\n"
        rows = ["Total Nacional;;;;Total;Ocupado/a;2024;20.373.148", "Total Nacional;;;;Total;Parado/a;2024;2.648.306",
                "Total Nacional;;;;Total;Estudiante;2024;2.544.369", "Total Nacional;;;;Total;Parado/a;2023;1",
                "Total Nacional;28 Madrid;28079 Madrid;;Total;Ocupado/a;2024;1.564.226",
                "Total Nacional;28 Madrid;28079 Madrid;;Total;Parado/a;2024;133.509",
                "Total Nacional;28 Madrid;28079 Madrid;;Mujeres;Parado/a;2024;70.000",
                "Total Nacional;28 Madrid;28079 Madrid;2807901001 Madrid sección 01001;Total;Parado/a;2024;99"]
        rows += [f"Total Nacional;{code} P;;;Total;Ocupado/a;2024;1.000" for code in PROVINCES]
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "66594.csv").write_text(head + "\n".join(rows) + "\n", encoding="utf-8")
            src = IneCensoActividad()
            with mock.patch.object(type(src), "raw_dir", new_callable=mock.PropertyMock, return_value=Path(d)):
                out = src.process()
        self.assertEqual(out["year"], 2024)
        self.assertEqual(out["nation"], {"employed": 20373148, "unemployed": 2648306})
        self.assertEqual(out["municipalities"], {"28079": {"employed": 1564226, "unemployed": 133509}})
        self.assertEqual(out["provinces"]["28"], {"employed": 1000})

    def test_serpavi_rents(self):
        from pipeline.sources.es import serpavi

        header = ["CPRO", "NPRO", "CUMUN", "NMUN", "BI_ALVHEPCO_TVC_23", "BI_ALVHEPCO_TVU_23", "ALQTBID12_M_VC_23",
                  "ALQTBID12_M_VU_23", "BI_ALVHEPCO_TVC_24", "BI_ALVHEPCO_TVU_24", "ALQTBID12_M_VC_24", "ALQTBID12_M_VU_24"]
        rows = [header, ["28", "Madrid", "28079", "Madrid", "1", "1", "1", "1", "300447", "3248", "868.75", "1272.8083"],
                ["26", "Rioja, La", "26001", "Ábalos", None, None, None, None, "4"],  # too few leases: no median
                ["01", "Araba/Álava", "01001", "Alegría-Dulantzi", None, None, None, None, "95", None, "551.51"]]
        self.assertEqual(serpavi.latest_year(header), "24")
        self.assertEqual(serpavi.rents(rows, "CUMUN", "24"),
                         {"28079": [[300447, 868.75], [3248, 1272.81]], "01001": [[95, 551.51]]})
        with self.assertRaises(RuntimeError):
            serpavi.latest_year(["CPRO"])


class SpainPeopleTest(unittest.TestCase):
    """Mean age, born abroad, higher education, homeowners and poverty: sources and lenses (spain_people.py)."""

    @staticmethod
    def _process(src, files: dict[str, str]):
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as d:
            for name, text in files.items():
                (Path(d) / name).write_text(text, encoding="utf-8")
            with mock.patch.object(type(src), "raw_dir", new_callable=mock.PropertyMock, return_value=Path(d)):
                return src.process()

    def test_latest_complete_year(self):
        from pipeline.sources.es.ine_people import latest_complete

        self.assertEqual(latest_complete({"2023": {"a": 1, "b": 1}, "2024": {"a": 1, "b": 1}, "2025": {"a": 1}}), "2024")

    def test_adrh_indicators(self):
        from pipeline.sources.es.ine_people import IneAdrhIndicadores

        ages = ("﻿Municipios;Distritos;Secciones;Indicadores demográficos;Periodo;Total\n"
                "28079 Madrid;;;Edad media de la población;2024;44,5\n"
                "28079 Madrid;;;Edad media de la población;2023;44,2\n"
                "28079 Madrid;2807901 Madrid distrito 01;;Edad media de la población;2024;40\n"
                "28079 Madrid;;;Porcentaje de población menor de 18 años;2024;15,1\n"
                "42173 Soria;;;Edad media de la población;2024;46\n")
        below = "Población con ingresos por unidad de consumo por debajo {}% de la mediana"
        poverty = ("﻿Municipios;Distritos;Secciones;Sexo;Distribución de la renta por unidad de consumo;Periodo;Total\n"
                   f"28079 Madrid;;;Total;{below.format(60)};2024;18,2\n"
                   f"28079 Madrid;;;Mujeres;{below.format(60)};2024;19\n"
                   f"28079 Madrid;;;Total;{below.format(40)};2024;8\n"
                   f"42173 Soria;;;Total;{below.format(60)};2024;\"\"\n")
        out = self._process(IneAdrhIndicadores(), {"30832.csv": ages, "30829.csv": poverty})
        self.assertEqual(out["years"], {"mean_age": 2024, "poverty": 2024})
        self.assertEqual(out["mean_age"], {"28079": 44.5, "42173": 46.0})  # the district row is ignored
        self.assertEqual(out["poverty"], {"28079": 0.182})  # both sexes, as a fraction; Soria is confidential

    def test_census_by_section_levels(self):
        from pipeline.sources.es.ine_people import IneCensoNacimiento

        head = "﻿Total Nacional;Provincias;Municipios;Secciones;Sexo;Lugar de nacimiento;Periodo;Total\n"
        rows = ["Total Nacional;;;;Total;Total;2026;49.618.622", "Total Nacional;;;;Total;Extranjero;2026;10.084.277",
                "Total Nacional;;;;Total;España;2026;39.534.345", "Total Nacional;;;;Total;Total;2025;1",
                "Total Nacional;28 Madrid;28079 Madrid;;Total;Total;2026;3.500.000",
                "Total Nacional;28 Madrid;28079 Madrid;;Total;Extranjero;2026;900.000",
                "Total Nacional;28 Madrid;28079 Madrid;;Mujeres;Extranjero;2026;480.000",
                "Total Nacional;28 Madrid;28079 Madrid;2807901001 Madrid sección 01001;Total;Extranjero;2026;99"]
        rows += [f"Total Nacional;{code} P;;;Total;Total;2026;1.000" for code in PROVINCES]
        out = self._process(IneCensoNacimiento(), {"65031.csv": head + "\n".join(rows) + "\n"})
        self.assertEqual(out["year"], 2026)
        self.assertEqual(out["nation"], {"total": 49618622, "abroad": 10084277})
        self.assertEqual(out["municipalities"], {"28079": {"total": 3500000, "abroad": 900000}})
        self.assertEqual(out["provinces"]["28"], {"total": 1000})
        with self.assertRaises(RuntimeError):  # a province missing
            self._process(IneCensoNacimiento(), {"65031.csv": head + "\n".join(rows[:-1]) + "\n"})

    def test_census_2021_tenure_sums_sections(self):
        from pipeline.sources.es.ine_people import IneCenso2021Indicadores

        head = "ccaa,cpro,cmun,dist,secc,t1_1,t19_1,t20_1,t20_2,t20_3\n"
        rows = ["13,28,079,01,001,1000,400,300,80,20", "13,28,079,01,002,900,300,200,90,10",
                "13,28,079,01,003,10,,,,",  # a confidential section
                "08,42,900,01,001,20,,,,"]  # a municipality with no section published
        rows += [f"01,04,{k:03d},01,001,10,4,3,1,0" for k in range(1, 5001)]
        out = self._process(IneCenso2021Indicadores(), {"C2021_Indicadores.csv": head + "\n".join(rows) + "\n"})
        self.assertEqual(out["year"], 2021)
        self.assertEqual(out["municipalities"]["28079"], {"owned": 500, "rented": 170, "other": 30})
        self.assertNotIn("42900", out["municipalities"])
        with self.assertRaises(RuntimeError):  # too few municipalities: not the national file
            self._process(IneCenso2021Indicadores(), {"C2021_Indicadores.csv": head + "\n".join(rows[:4]) + "\n"})

    def test_shares(self):
        from pipeline.build.spain_people import share, tenure_share

        self.assertEqual(share({"total": 200, "abroad": 50}, "abroad"), 0.25)
        self.assertIsNone(share({"total": 0, "abroad": 0}, "abroad"))
        self.assertIsNone(share({"total": 10}, "abroad"))
        self.assertIsNone(share(None, "abroad"))
        self.assertEqual(tenure_share({"owned": 70, "rented": 20, "other": 10}), 0.7)
        self.assertIsNone(tenure_share(None))

    def test_lenses_keep_the_us_look_and_weight_by_population(self):
        from unittest import mock

        from pipeline.build import spain_people
        from pipeline.build.lenses import COUNTY_LENSES

        interims = {
            "ine_adrh_indicadores": {"years": {"mean_age": 2024, "poverty": 2024}, "mean_age": {"28079": 44.0, "42173": 48.0},
                                     "poverty": {"28079": 0.2}},
            "ine_censo_nacimiento": {"year": 2026, "municipalities": {"28079": {"total": 100, "abroad": 30},
                                                                        "42173": {"total": 100, "abroad": 10}}},
            "ine_censo_formacion": {"year": 2024, "municipalities": {"28079": {"total": 100, "higher": 50}}},
            "ine_censo2021_indicadores": {"year": 2021, "municipalities": {"28079": {"owned": 7, "rented": 2, "other": 1}}},
            "mivau_valor_tasado": {"year": 2026, "quarter": 2, "spain": 2355.0, "provinces": {"28": 4000.0, "42": 1200.0}},
        }
        payload = lambda name: {"data": interims[name]}
        geoids = ["28079", "42173", "44001"]
        weights = [[(0, 300.0), (1, 100.0)], [(1, 50.0)], [(2, 10.0)], []]
        with mock.patch.object(spain_people, "load_interim_payload", payload):
            lenses = {l["id"]: l for l in spain_people.people_lenses(geoids, weights)}
        self.assertEqual(list(lenses), ["poverty", "age", "foreign_born", "bachelors", "homeownership", "home"])
        for lid, lens in lenses.items():
            us = COUNTY_LENSES[lid][1]
            shared = [k for k in spain_people.SHARED if not (lid == "home" and k == "format")]  # euros, not dollars
            self.assertEqual({k: lens[k] for k in shared}, {k: us[k] for k in shared})
        self.assertEqual(lenses["home"]["format"], "eur")
        self.assertEqual(lenses["home"]["values"], [3300.0, 1200.0, None, None])  # every municipality, its province's
        self.assertEqual(lenses["age"]["values"], [45.0, 48.0, None, None])
        self.assertEqual(lenses["foreign_born"]["values"], [0.25, 0.1, None, None])
        self.assertEqual(lenses["poverty"]["values"], [0.2, None, None, None])  # Soria has no figure: not a zero
        self.assertEqual(lenses["homeownership"]["values"], [0.7, None, None, None])
        self.assertIn("2021", lenses["homeownership"]["description"]["es"])
        self.assertIn("15 años", lenses["bachelors"]["unit"]["es"])
        self.assertIn("aged 15+", lenses["bachelors"]["unit"]["en"])


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
        from pipeline.build.districts import badge_district, evaluate

        nation = {"total": 1_000_000, "23": 5_000, "10": 50_000, "47": 100_000}
        city = {"total": 100_000, "23": 4_000, "10": 5_000, "47": 10_000}  # ceramics at 8× the national share
        m = SD.CensusMetrics({"municipalities": {"12040": city}, "nation": nation})
        dists = evaluate(m, ["12040"], city["total"], False, SD.CATALOG)
        self.assertEqual([d["id"] for d in dists], ["industrial_zone"])
        self.assertEqual(dists[0]["sub"], "23")
        self.assertIsNone(dists[0]["avg_pay"], "the census has no wages")
        badge = SD.badge(badge_district(dists), False)
        self.assertEqual((badge["label"], badge["basis"]), ({"es": "Ciudad de la cerámica", "en": "Ceramics town"}, "census"))
        self.assertEqual(badge["text"], {"es": "Cerámica, vidrio y cemento: 8,0 veces la cuota nacional de empleo",
                                         "en": "Ceramics, glass and cement: 8.0× the national share of jobs"})
        self.assertEqual(SD.badge(badge_district(dists), False, SD.BADGE_LABELS["26089"])["label"]["en"], "Red wine town")
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
        self.assertEqual((a["id"], a["full"]), ("08019", {"es": "Área urbana de Barcelona", "en": "Barcelona urban area"}))
        (b,) = urban_areas([self.area(["Las Palmas de Gran Canaria"], 380_000)], self.muni, self.centre)
        self.assertEqual(b["members"], ["35016"])

    def test_area_names_are_written_as_names(self):
        """Each word of a hyphenated or co-official name keeps its capital, the AUDES misprint is corrected, and an
        article after the preposition goes to lower case in Spanish only."""
        from pipeline.build.spain import area_name

        for label, es, en in [
            ("ÁREA URBANA DE TARRAGONA-REUS", "Área urbana de Tarragona-Reus", "Tarragona-Reus urban area"),
            ("ÁREA URBANA DE ALCOY/ALCOI", "Área urbana de Alcoy/Alcoi", "Alcoy/Alcoi urban area"),
            ("ÁREA URBANA DE SALTA CRUZ DE TENERIFE - LA LAGUNA", "Área urbana de Santa Cruz de Tenerife - La Laguna",
             "Santa Cruz de Tenerife - La Laguna urban area"),
            ("ÁREA URBANA DE LA BAHÍA DE CÁDIZ", "Área urbana de la Bahía de Cádiz", "La Bahía de Cádiz urban area"),
            ("ÁREA URBANA DEL VALLE DE LA OROTAVA", "Área urbana del Valle de la Orotava", "Valle de la Orotava urban area"),
            ("ÁREA URBANADE SEGOVIA", "Área urbana de Segovia", "Segovia urban area"),
        ]:
            self.assertEqual(area_name(label), {"es": es, "en": en}, label)

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
            self.assertEqual(sheets(path, only={"LISTADO"})["LISTADO"], rows)
            self.assertEqual(sheets(path, only={"OTRA"}), {}, "sheets left out are not read")
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


class SpainTransportTest(unittest.TestCase):
    def test_airport_names(self):
        from pipeline.sources.es.transport import airport_name

        self.assertEqual(airport_name("AEROPUERTO INTL. REGIÓN MURCIA (**)"), "Aeropuerto Intl. Región Murcia")
        self.assertEqual(airport_name("CEUTA /HELIPUERTO"), "Ceuta (helipuerto)")
        self.assertEqual(airport_name("MÁLAGA-COSTA DEL SOL"), "Málaga-Costa del Sol")

    def test_hub_classes_and_words(self):
        from pipeline.build.spain_infrastructure import hub_class
        from pipeline.sources.es.transport import words

        self.assertEqual([hub_class(p, 1000) for p in (10, 9, 3, 1, 0)], ["L", "M", "M", "S", "N"])
        self.assertEqual(hub_class(5, 0), "N")
        self.assertEqual(words("ALICANTE-ELCHE MIGUEL HDEZ. Aeropuerto"), {"alicante", "elche", "miguel", "hdez"})


class SpainUniversitiesTest(unittest.TestCase):
    def test_names_and_place_keys(self):
        from pipeline.build.spain_wonders import place_key, university_name

        self.assertEqual(university_name("Complutense de Madrid"), "Universidad Complutense de Madrid")
        self.assertEqual(university_name("Sevilla"), "Universidad de Sevilla")
        self.assertEqual(university_name("País Vasco/Euskal Herriko Unibertsitatea"),
                         "Universidad del País Vasco/Euskal Herriko Unibertsitatea")
        self.assertEqual(place_key("HOSPITALET DE LLOBREGAT (L')"), place_key("Hospitalet de Llobregat, L'"))
        self.assertEqual(place_key("VALÈNCIA"), "valencia")

    def test_municipality_finder_prefers_province(self):
        from pipeline.build.spain_wonders import municipality_finder

        find = municipality_finder([{"geoid": "18087", "name": "Granada", "state_fips": "18"},
                                    {"geoid": "99001", "name": "Granada", "state_fips": "99"},
                                    {"geoid": "03122", "name": "Sant Vicent del Raspeig/San Vicente del Raspeig",
                                     "state_fips": "03"}])
        self.assertEqual(find("GRANADA", "18")["geoid"], "18087")
        self.assertEqual(find("SAN VICENTE DEL RASPEIG/SANT VICENT DEL RASPEIG", "03")["geoid"], "03122")
        with self.assertRaises(RuntimeError):
            find("GRANADA", "50")


class SpainPowerTest(unittest.TestCase):
    def test_osm_capacity_and_fuels(self):
        from pipeline.sources.es.power import mw_of, ppm_fuel

        self.assertEqual(mw_of("697 MW"), 697)
        self.assertEqual(mw_of("800 kW"), 0.8)
        self.assertEqual(mw_of("1,2 GW"), 1200)
        self.assertIsNone(mw_of("yes"))
        self.assertEqual(ppm_fuel({"Fueltype": "Hydro", "Technology": "Pumped Storage"}), "pumped_storage")
        self.assertEqual(ppm_fuel({"Fueltype": "Lignite", "Technology": ""}), "coal")
        self.assertIsNone(ppm_fuel({"Fueltype": "Waste", "Technology": ""}))

    def test_site_merges_units(self):
        from pipeline.build.spain_resources import site

        p = lambda name, mw: ({"name": name, "mw": mw, "year": 1983, "offshore": False, "source": "ppm"}, 0.0, 0.0)
        s = site("nuclear", [p("Almaraz 1", 1049), p("Almaraz 2", 1044)], 7)
        self.assertEqual((s["name"]["es"], s["value"], s["cell"]), ("Almaraz", 2093, 7))
        # Names and details in each language, and capacities without float noise (123.1 + 123.2 = 246.29999999999998)
        s = site("solar", [p("Renopool Solar Farm", 123.1), p("Renopool Solar Farm", 123.2)], 7)
        self.assertEqual(s["name"], {"es": "Planta solar Renopool", "en": "Renopool Solar Farm"})
        self.assertEqual(s["detail"], {"es": "2 centrales, entre ellas Planta solar Renopool (123,2 MW), en servicio desde 1983",
                                       "en": "2 plants, including Renopool Solar Farm (123.2 MW), in service since 1983"})

    def test_plant_names_in_each_language(self):
        """Spanish rewrites the source's English kind words; English keeps the source's name, without its noise."""
        from pipeline.build.spain_resources import plant_name

        for en, es in [("Las Majas Wind Farm (+1)", "Parque eólico Las Majas (+1)"), ("Monlora Wind", "Parque eólico Monlora"),
                       ("La Cabana Wind Farm Spain", "Parque eólico La Cabana"),
                       ("Renopool Solar Farm (+5)", "Planta solar Renopool (+5)"),
                       ("Llevant Solar Solar Farm", "Planta solar Llevant"), ("Mula Solar Photovoltaic", "Planta solar Mula"),
                       ("Alcala De Guadaira Solar Park (+4)", "Planta solar Alcala de Guadaira (+4)"),
                       ("Guzman Thermosolar Farm", "Central termosolar Guzman"), ("Aste Csp Solar Farm", "Central termosolar Aste"),
                       ("Castile La Mancha Solar Xxxiii", "Castilla-La Mancha Solar Xxxiii"), ("Alcudia Phase", "Alcudia"),
                       ("Bajo Aragon Solar", "Bajo Aragón Solar"), ("Almaraz", "Almaraz")]:
            self.assertEqual(plant_name(en)["es"], es)
        for source, en in [("La Cabana Wind Farm Spain", "La Cabana Wind Farm"), ("Alcudia Phase", "Alcudia"),
                           ("Castile La Mancha Solar Xxxiii", "Castile La Mancha Solar Xxxiii"),
                           ("Alcala De Guadaira Solar Park (+4)", "Alcala de Guadaira Solar Park (+4)")]:
            self.assertEqual(plant_name(source)["en"], en)


class SpainFoodTest(unittest.TestCase):
    def test_label_kinds(self):
        from pipeline.sources.es.food import label

        self.assertEqual(label("Rioja", "Denominación de Origen Calificada"), "Rioja (DOP)")
        self.assertEqual(label("Orujo de Galicia", "Indicación Geográfica Protegida Bebida Espirituosa"),
                         "Orujo de Galicia (IGP)")
        self.assertEqual(label("Dehesa del Carrizal", "Vino de Pago"), "Dehesa del Carrizal (Vino de pago)")

    def test_names_match_across_spellings(self):
        from pipeline.sources.es.food import matches

        same = [(["Penedés, Comunidad de Cataluña", "Penedés"], ["Penedès"], "Wine"),
                (["Priorato, Comunidad de Cataluña", "Priorato"], ["Priorat", "Priorato"], "Wine"),
                (["Queso Idiazábal"], ["Idiazabal"], "Food"),
                (["Pago de Calzadilla", "Pago de Calzadilla"], ["Calzadilla"], "Wine"),
                (["Las Islas Canarias"], ["Islas Canarias"], "Wine"),
                (["Pimiento del Piquillo de Lodosa"], ["Pimientos del Piquillo de Lodosa"], "Food"),
                (["Aceite de Monterrubio"], ["Aceite Monterrubio"], "Food"),
                (["Jijona / Xixona"], ["Jijona"], "Food"),
                (["Ternera de Navarra o Nafarroako Aratxea"], ["Nafarroako Aratxea", "Ternera de Navarra"], "Food"),
                (["Chacolí de Getaria-Getariako Txakolina"],
                 ["Getariako Txakolina", "Chacolí de Getaria", "Txakoli de Getaria"], "Wine")]
        for ministry, protected, product in same:
            self.assertTrue(matches(ministry, protected, product), ministry)
        # one part of a hyphenated name is not enough; a product word comes off only where it is generic
        self.assertFalse(matches(["Alubia de La Bañeza-León"], ["León"], "Food"))
        self.assertFalse(matches(["Queso de Murcia"], ["Murcia"], "Wine"))
        self.assertFalse(matches(["Queso de Murcia"], ["Jumilla"], "Food"))

    def test_a_zone_filed_under_another_designations_code_keeps_its_own_key(self):
        from pipeline.sources.es.food import ministry_code

        seen = {"DO276": {"cal_ds_codigo": "DO276", "cal_ds_nombre": "I.G.P.Cordero de Extremadura"}}
        self.assertEqual(ministry_code(seen["DO276"], seen), "DO276")
        beans = {"cal_ds_codigo": "DO276", "cal_ds_nombre": "D.O.P.Mongeta del Ganxet"}
        self.assertEqual(ministry_code(beans, seen), "DO276|D.O.P.Mongeta del Ganxet")
        self.assertEqual(ministry_code(beans, {}), "DO276")

    def test_register_matching_by_product_and_renames(self):
        from pipeline.sources.es.food import match_register

        def gi(gid, names, product, file="X"):
            return {"giIdentifier": gid, "protectedNames": names, "productType": product,
                    "registration": {"fileNumber": file}}

        def zone(name, family, cal=None):
            return {"zon_ds_nombre": name, "cal_ds_nombre": cal or name, "fam_ds_nombre": family}

        register = [gi("W", ["Murcia"], "Wine"), gi("F", ["Queso de Murcia"], "Food"),
                    gi("L", ["León"], "Wine", "PDO-ES-A0882"), gi("S", ["Pacharán Navarro"], "Spirit drink")]
        got = match_register({"DO09": zone("Queso de Murcia", "Quesos y Mantequillas"),
                              "DO83": zone("Tierra de León", "Vinos", "D.O.Tierra de León"),
                              "DO99": zone("Pacharán Navarro", "Bebidas Espirituosas", "I.G.P.Pacharán Navarro"),
                              "DO307": zone("Aceite de la Comunitat Valenciana", "Aceites de Oliva Virgen")}, register)
        self.assertEqual({code: g["giIdentifier"] for code, g in got.items()}, {"DO09": "F", "DO83": "L", "DO99": "S"})
        with self.assertRaises(RuntimeError):
            match_register({"A": zone("Murcia", "Vinos"), "B": zone("D.O.Murcia", "Vinos")}, register)

    def test_area_units_and_labels(self):
        from pipeline.sources.es.food import area_label, parse_units

        self.assertEqual(parse_units("provincia:42 municipio:05057* isla:Mallorca comunidad:07"),
                         ["provincia:42", "municipio:05057*", "isla:Mallorca", "comunidad:07"])
        for bad in ("provincia:99", "municipio:5057", "isla:Atlántida", "comarca:Bierzo", "comunidad:42"):
            with self.assertRaises(ValueError):
                parse_units(bad)
        self.assertEqual(area_label("Torrezno de Soria", "IGP", ["provincia:42"]), "Torrezno de Soria (IGP · provincia)")
        self.assertEqual(area_label("X", "IGP", ["provincia:07", "municipio:05057"]), "X (IGP · provincia, municipios)")
        self.assertEqual(area_label("Urbezo", "Vino de pago", ["municipio:50080"]), "Urbezo (Vino de pago · finca)")
        self.assertEqual(area_label("Y", "DOP", []), "Y (DOP · sin zona)")

    def test_every_registered_name_needs_an_area(self):
        from pipeline.sources.es.food import register_areas

        def gi(gid, names, product):
            return {"giIdentifier": gid, "protectedNames": names, "productType": product, "giType": "PGI",
                    "registration": {"fileNumber": gid}}

        ministry = {"DO1": {"zon_ds_nombre": "Rioja", "cal_ds_nombre": "D.O.Ca.Rioja", "fam_ds_nombre": "Vinos",
                            "tpr_ds_descripcion": "Denominación de Origen Calificada"},
                    "DO2": {"zon_ds_nombre": "Aceite Viejo", "cal_ds_nombre": "Aceite Viejo",
                            "fam_ds_nombre": "Aceites de Oliva Virgen", "tpr_ds_descripcion": "Denominación de Origen Protegida"}}
        rings = {"DO1": [[(0, 0), (1, 0), (1, 1)]], "DO2": [[(0, 0), (1, 0), (1, 1)]]}
        row = {"eambrosia": "T", "nombre": "Torrezno de Soria", "figura": "IGP", "familia": "Embutidos y Productos Cárnicos",
               "units": ["provincia:42"], "fuente": "DOUE C/2024/4674", "nota": ""}
        register = [gi("R", ["Rioja"], "Wine"), gi("T", ["Torrezno de Soria"], "Food")]
        out = register_areas(register, ministry, rings, [row])
        self.assertEqual([(n["name"], n["area"]) for n in out["names"]],
                         [("Rioja (DOP)", "mapa"), ("Torrezno de Soria (IGP · provincia)", "unidades")])
        self.assertEqual(out["not_registered"], ["Aceite Viejo (DOP)"])
        self.assertEqual((out["eu_registered"], out["eu_register"]), (2, {"PGI Wine": 1, "PGI Food": 1}))
        with self.assertRaises(RuntimeError):  # a registered name with no area anywhere
            register_areas(register, ministry, rings, [])
        with self.assertRaises(RuntimeError):  # a row for a name the Ministry maps
            register_areas(register, ministry, rings, [row, {**row, "eambrosia": "R"}])
        with self.assertRaises(RuntimeError):  # a row for a name not in the register
            register_areas(register, ministry, rings, [row, {**row, "eambrosia": "Z"}])

    def test_the_areas_csv_reads(self):
        from pipeline.sources.es.food import read_areas

        rows = read_areas()
        self.assertTrue(rows)
        self.assertEqual(len({r["eambrosia"] for r in rows}), len(rows))
        for r in rows:
            self.assertIn(r["figura"], ("DOP", "IGP", "Vino de pago"))
            self.assertTrue(r["fuente"] and r["url"].startswith("https://"), r["nombre"])
            self.assertTrue(r["units"] or r["nota"], r["nombre"])  # no area: the note says why


class SpainFoodLensTest(unittest.TestCase):
    """A 4 × 4 grid in which every hex is land; municipalities are unit squares around hex centres."""

    def setUp(self):
        from pipeline.core.hexgrid import HexGrid

        self.grid = HexGrid(radius=10.0, cols=4, rows=4)
        self.centre = [self.grid.center(*self.grid.col_row(c)) for c in range(self.grid.size)]
        codes = [f"07{c:03d}" for c in range(self.grid.size)]
        self.world = {"owner": [0] * self.grid.size, "county": list(range(self.grid.size)), "counties": codes}
        self.munis = [{"geoid": g, "state_fips": "07", "centre": self.centre[c],
                       "rings": [[(self.centre[c][0] + dx, self.centre[c][1] + dy) for dx, dy in
                                  ((0, 0), (1, 0), (1, 1), (0, 1))]]} for c, g in enumerate(codes)]

    def lens(self, names):
        from pipeline.build.spain_food import food_lens

        return food_lens(names, lambda lon, lat: (lon, lat), self.grid, self.world, self.munis, [])

    def test_polygons_units_estates_and_order(self):
        cx, cy = self.centre[5]
        big = [[(-100, -100), (1000, -100), (1000, 1000), (-100, 1000)]]
        tiny = [[(cx - 1, cy - 1), (cx - 0.5, cy - 1), (cx - 0.5, cy - 0.5)]]
        lens = self.lens([{"name": "A (DOP)", "area": "mapa", "rings": big},
                          {"name": "B (IGP)", "area": "mapa", "rings": tiny},
                          {"name": "C (IGP · municipios)", "area": "unidades", "units": ["municipio:07005", "municipio:07006*"]},
                          {"name": "D (Vino de pago · finca)", "area": "finca", "units": ["municipio:07006"]},
                          {"name": "E (IGP · sin zona)", "area": "ninguna", "units": [], "note": "sin pliego"}])
        self.assertEqual([n["es"] for n in lens["names"]], ["A (DOP)", "B (IGP)", "C (IGP · municipios)", "D (Vino de pago · finca)"])
        self.assertEqual([n["en"] for n in lens["names"]], ["A (PDO)", "B (PGI)", "C (PGI · municipalities)", "D (Vino de Pago · estate)"])
        named = lambda c: [lens["names"][k]["es"] for k in lens["labels"][c]]
        self.assertEqual(named(5), ["B (IGP)", "C (IGP · municipios)", "A (DOP)"])  # smallest area first
        self.assertEqual(named(6), ["D (Vino de pago · finca)", "C (IGP · municipios)", "A (DOP)"])
        self.assertEqual(sum(lens["values"]), self.grid.size + 4)
        self.assertIn("Sin zona: E (IGP · sin zona), sin pliego.", lens["description"]["es"])
        self.assertIn("No area: E (PGI · no area), sin pliego.", lens["description"]["en"])

    def test_whole_province_and_island(self):
        from pipeline.build.spain_food import island, unit_municipalities

        # hexes 0 and 1 touch (shared corner); the rest stand apart
        self.munis[1]["rings"] = [[(x, y) for x, y in self.munis[1]["rings"][0]] + [self.munis[0]["rings"][0][2]]]
        self.assertEqual(island(self.munis, "07000"), {"07000", "07001"})
        self.assertEqual(len(unit_municipalities(["provincia:07"], self.munis)), self.grid.size)
        self.assertEqual(unit_municipalities(["municipio:07003*"], self.munis), {"07003"})


class SpainNamedLensTest(unittest.TestCase):
    def test_named_counts(self):
        from pipeline.build.spain_named import named_counts

        lens = named_counts(["A", "B", "C"], [[0, 1], [1], [-1, 2]], [0, 0, -1])
        self.assertEqual(lens["values"], [1, 2, None])
        self.assertEqual(lens["labels"], [[0], [0, 1], None])


class SpainPeoplesTest(unittest.TestCase):
    def test_territories_and_colours(self):
        from pipeline.build.spain import peoples_lens
        from pipeline.core.hexgrid import HexGrid

        grid = HexGrid(radius=10.0, cols=6, rows=2)
        owner = [0] * grid.size
        left, right = grid.center(0, 0), grid.center(5, 0)
        peoples = [{"id": "1", "name": "Vaccaei", "lon": left[0], "lat": left[1]},
                   {"id": "2", "name": "Vascones", "lon": right[0], "lat": right[1]},
                   {"id": "3", "name": "Far away", "lon": 1e6, "lat": 1e6}]
        lens = peoples_lens(peoples, lambda lon, lat: (lon, lat), grid, owner)
        self.assertEqual([c["name"] for c in lens["categories"]], ["Vaccaei", "Vascones"])  # unused peoples drop out
        self.assertEqual(lens["values"][grid.size // 2 - 6], 0)
        self.assertEqual(lens["values"][5], 1)
        self.assertNotEqual(lens["categories"][0]["color"], lens["categories"][1]["color"])  # they touch
        self.assertEqual(lens["domain"], [0, 1])


class SpainLanguagesTest(unittest.TestCase):
    MUNIS = [{"geoid": "46250", "name": "València", "state_fips": "46", "centre": [-0.37, 39.47]},
             {"geoid": "46098", "name": "Cofrentes", "state_fips": "46", "centre": [-1.06, 39.23]},
             {"geoid": "03903", "name": "Los Montesinos", "state_fips": "03", "centre": [-0.74, 38.03]},
             {"geoid": "12022", "name": "Bejís", "state_fips": "12", "centre": [-0.71, 39.9]},
             {"geoid": "25243", "name": "Vielha e Mijaran", "state_fips": "25", "centre": [0.8, 42.7]},
             {"geoid": "31201", "name": "Pamplona/Iruña", "state_fips": "31", "centre": [-1.64, 42.82]},
             {"geoid": "31232", "name": "Tudela", "state_fips": "31", "centre": [-1.6, 42.06]},
             {"geoid": "28079", "name": "Madrid", "state_fips": "28", "centre": [-3.7, 40.4]}]

    def test_castilian_list_parsing(self):
        from pipeline.sources.es.languages import castilian_valencia

        xml = ("<p>1. Provincia de Alicante: Albatera, Orihuela.</p><p>2. Provincia de Castellón: Bejfs.</p>"
               "<p>3. Provincia de Valencia: Cofrentes, Requena.</p>")
        self.assertEqual(castilian_valencia(xml), {"03": ["Albatera", "Orihuela"], "12": ["Bejfs"],
                                                   "46": ["Cofrentes", "Requena"]})

    def test_language_of_municipalities(self):
        from pipeline.build.spain import language_of

        mixed = {"type": "Polygon", "coordinates": [[[-2, 42.5], [-1, 42.5], [-1, 43], [-2, 43], [-2, 42.5]]]}
        lang = language_of({"valencia_castilian": {"03": [], "12": ["Bejfs"], "46": ["Cofrentes"]},
                            "navarra_zones": [{"zone": "basque_mixed", "geometry": mixed}]}, self.MUNIS)
        self.assertEqual(lang, {"46250": "valencian", "46098": "valencia_castilian", "03903": "valencia_castilian",
                                "12022": "valencia_castilian", "25243": "aranese", "31201": "basque_mixed",
                                "31232": "spanish", "28079": "spanish"})

    def test_unknown_castilian_name_fails(self):
        from pipeline.build.spain import castilian_codes

        with self.assertRaises(RuntimeError):
            castilian_codes({"46": ["Atlántida"]}, self.MUNIS)


class SpainMinesTest(unittest.TestCase):
    @staticmethod
    def dep(code, name, size, municipality="Almonaster la Real", province="21", substance=" Pirita, Cobre"):
        return {"code": code, "name": name, "size": size, "municipality": municipality, "province": province,
                "substance": substance, "lon": 0.0, "lat": 0.0}

    def test_locate_prefers_a_deposit_sharing_the_name(self):
        from pipeline.sources.es.mines import locate

        mine = {"name": "AGUAS TEÑIDAS-HERRERITOS", "municipality": "Almonaster la Real", "province": "21",
                "substance": "COBRE"}
        deposits = [self.dep("1", "Cueva de la Mora", "grande"), self.dep("2", "Aguas Teñidas", "mediano"),
                    self.dep("3", "Aguas Teñidas", "grande", municipality="Calañas"),  # another municipality
                    self.dep("4", "Aguas Teñidas", "grande", substance=" Manganeso")]  # another mineral
        self.assertEqual(locate(mine, deposits)["code"], "2")
        riotinto = {"name": "MINAS DE RIO TINTO", "municipality": "Minas de Riotinto", "province": "21",
                    "substance": "COBRE"}
        found = locate(riotinto, [self.dep("5", "Cerro Colorado", "grande", "Minas de Riotinto"),
                                  self.dep("6", "Minas de Riotinto", "grande", "Minas de Riotinto")])
        self.assertEqual(found["code"], "6")  # the words run together: 'Rio Tinto' = 'Riotinto'

    def test_locate_falls_back_to_the_only_large_or_medium_deposit(self):
        from pipeline.sources.es.mines import locate

        sotiel = {"name": "Concesión de Explotación, derivada del PI “Sotiel”", "municipality": "Almonaster la Real",
                  "province": "21", "substance": "COBRE"}
        only = [self.dep("1", "Cueva de la Mora", "grande"), self.dep("2", "Sorpresa", "pequeño")]
        self.assertEqual(locate(sotiel, only)["code"], "1")
        self.assertIsNone(locate(sotiel, only + [self.dep("3", "Angelita", "mediano")]))  # two: none is chosen
        self.assertIsNone(locate(sotiel, [self.dep("2", "Sorpresa", "pequeño")]))  # a small one never stands alone

    def test_names_and_provinces(self):
        from pipeline.sources.es.names import title_es
        from pipeline.sources.es.mines import norm, province_code

        self.assertEqual(norm("Santos (Los)"), norm("Santos, Los"))
        self.assertEqual((province_code("ORENSE"), province_code("OURENSE"), province_code("LA CORUÑA")),
                         ("32", "32", "15"))
        with self.assertRaises(RuntimeError):
            province_code("ATLÁNTIDA")
        self.assertEqual(title_es("MINA FATIMA (FATIMA, JARAMA, Y FATIMA FR. II)"),
                         "Mina Fatima (Fatima, Jarama, y Fatima Fr. II)")
        self.assertEqual(title_es("PENOUTA Olga"), "PENOUTA Olga")  # mixed case is left alone
        self.assertEqual(title_es("JEREZ DE LA FRONTERA"), "Jerez de la Frontera")
        self.assertEqual(title_es("TENERIFE NORTE-C. LA LAGUNA"), "Tenerife Norte-C. La Laguna")
        self.assertEqual(title_es("FGL GRANADA-JAÉN"), "FGL Granada-Jaén")
        self.assertEqual(title_es("A CORUÑA"), "A Coruña")
        self.assertEqual(title_es("MOROS I CRISTIANS"), "Moros i Cristians")
        self.assertEqual(title_es("CARLOS I DE ESPAÑA"), "Carlos I de España")
        self.assertEqual(title_es("FESTA DO POLBO DE O CARBALLIÑO"), "Festa do Polbo de O Carballiño")
        self.assertEqual(title_es("MINERALES Y PRODUCTOS DERIVADOS, S.A"), "Minerales y Productos Derivados, S.A")
        self.assertEqual(title_es("Central termosolar Palma Del Rio"), "Central termosolar Palma del Rio")



class SpainVintageTest(unittest.TestCase):
    def test_source_vintages_in_both_languages(self):
        """The source's own vintage is the English; the Spanish translates its dates and words."""
        from pipeline.build.texts_es import vintage

        for en, es in [("INE Padrón, 1 January 2025", "INE Padrón, 1 de enero de 2025"),
                       ("AENA 2025 (final)", "AENA 2025 (datos definitivos)"), ("SIIU, students 2024-2025", "SIIU, matriculados 2024-2025"),
                       ("OAPN, Red de Parques Nacionales; visitors 2025", "OAPN, Red de Parques Nacionales; visitantes 2025"),
                       ("MAPA, Calidad diferenciada (2017 areas); eAmbrosia", "MAPA, Calidad diferenciada (zonas de 2017); eAmbrosia"),
                       ("powerplantmatching 2889ad9d1; OpenStreetMap (Canary Islands)", "powerplantmatching 2889ad9d1; OpenStreetMap (Canarias)")]:
            self.assertEqual(vintage(en), {"es": es, "en": en})
        for es, en in [("Cobertura de banda ancha (Ministerio para la Transformación Digital), junio de 2025",
                        "Broadband coverage (Ministerio para la Transformación Digital), June 2025"),
                       ("Ministerio de Vivienda, valor tasado, 2.º trimestre de 2026", "Ministerio de Vivienda, appraised value, Q2 2026")]:
            self.assertEqual(vintage(es), {"es": es, "en": en})  # a vintage the source writes in Spanish
        self.assertIsNone(vintage(None))


class SpainBeachesTest(unittest.TestCase):
    """Blue Flag beaches: municipality, name matching against Wikidata and OSM, and placement (spain_beaches)."""

    def test_beach_towns(self):
        from pipeline.build.spain_beaches import beach_towns

        by_key = {("29", "marbella"): "29069", ("30", "san javier"): "30035", ("30", "cartagena"): "30016"}
        self.assertEqual(beach_towns({"province": "29", "municipality": "Marbella"}, by_key), ["29069"])
        self.assertEqual(beach_towns({"province": "30", "municipality": "San Javier/Cartagena"}, by_key),
                         ["30035", "30016"])
        self.assertEqual(beach_towns({"province": "07", "municipality": "Palma de Mallorca"}, by_key), ["07040"])
        with self.assertRaises(RuntimeError):
            beach_towns({"province": "29", "municipality": "Atlántida"}, by_key)

    def test_name_key_drops_accents_articles_and_the_word_for_beach(self):
        from pipeline.build.spain_beaches import name_key

        for a, b in [("Playa de la Concha", "La Concha"), ("Praia da Rapadoira", "A Rapadoira"),
                     ("Platja de l'Arenal", "L´Arenal"), ("Platja de Sa Conca", "Sa Conca"),
                     ("Playa de Nagüeles", "Nagueles"), ("Hondartza de Laida", "Laida"),
                     ("Playa fluvial A Calzada", "A Calzada")]:
            self.assertEqual(name_key(a), name_key(b), (a, b))
        self.assertNotEqual(name_key("Playa de Levante"), name_key("Playa de Poniente"))
        self.assertEqual(name_key("Playa de Levante"), "levante")

    def test_forms_try_the_whole_name_first_then_its_parts(self):
        from pipeline.build.spain_beaches import forms

        self.assertEqual(forms("Venus-Bajadilla"), ["venus bajadilla", "venus", "bajadilla"])
        self.assertEqual(forms("Sant Francesc (Cala Bona)"), ["sant francesc cala bona", "sant francesc", "cala bona"])
        self.assertEqual(forms("Punta Umbría (Tramo El Albergue)")[:2], ["punta umbria tramo albergue", "punta umbria"])
        self.assertEqual(forms("Arenal y Bol"), ["arenal bol", "arenal", "bol"])

    @staticmethod
    def _town():
        """A square municipality 29069 of about 11 × 11 km (0.1° side) and its outline."""
        from pipeline.build.spain_beaches import Outline

        rings = [[(-4.9, 36.5), (-4.8, 36.5), (-4.8, 36.6), (-4.9, 36.6)]]
        return rings, {"29069": Outline(rings)}

    def test_match_prefers_wikidata_by_ine_code_then_osm_near_the_outline(self):
        from pipeline.build.spain_beaches import forms, index, match

        _, outlines = self._town()
        wd = index([{"id": "Q1", "names": ["Playa de Venus"], "ine": ["29069"], "lonlat": [-4.85, 36.55]},
                    {"id": "Q2", "names": ["Playa de Cabopino"], "ine": ["29051"], "lonlat": [-4.86, 36.55]}])
        osm = index([{"id": "way/1", "names": ["Playa de Venus"], "lonlat": [-4.84, 36.54]},
                     {"id": "way/2", "names": ["Playa de Cabopino"], "lonlat": [-4.795, 36.55]},  # 0.45 km offshore
                     {"id": "way/3", "names": ["Playa del Faro"], "lonlat": [-4.7, 36.55]}])  # 9 km away
        self.assertEqual(match(forms("Venus"), ["29069"], outlines, wd, osm), ("wikidata_playas", "Q1", (-4.85, 36.55)))
        # Q2 gives another municipality's code: the OSM beach just off the outline answers.
        self.assertEqual(match(forms("Cabopino"), ["29069"], outlines, wd, osm), ("osm_playas", "way/2", (-4.795, 36.55)))
        self.assertIsNone(match(forms("El Faro"), ["29069"], outlines, wd, osm))
        self.assertEqual(match(forms("Venus-Bajadilla"), ["29069"], outlines, wd, osm)[1], "Q1")  # by its first part

    def test_match_joins_the_pieces_of_one_beach_and_refuses_two_beaches_of_one_name(self):
        from pipeline.build.spain_beaches import forms, index, match

        _, outlines = self._town()
        pieces = index([{"id": "way/1", "names": ["Playa de Levante"], "lonlat": [-4.85, 36.55]},
                        {"id": "way/2", "names": ["Playa de Levante"], "lonlat": [-4.84, 36.55]}])
        self.assertEqual(match(forms("Levante"), ["29069"], outlines, {}, pieces),
                         ("osm_playas", "way/1+way/2", (-4.845, 36.55)))
        apart = index([{"id": "way/1", "names": ["Playa de Levante"], "lonlat": [-4.89, 36.51]},
                       {"id": "way/2", "names": ["Playa de Levante"], "lonlat": [-4.81, 36.59]}])
        self.assertIsNone(match(forms("Levante"), ["29069"], outlines, {}, apart))
        inside_first = index([{"id": "way/1", "names": ["Playa de Levante"], "lonlat": [-4.85, 36.55]},
                              {"id": "way/2", "names": ["Playa de Levante"], "lonlat": [-4.79, 36.59]}])
        self.assertEqual(match(forms("Levante"), ["29069"], outlines, {}, inside_first)[2], (-4.85, 36.55))

    def _lens(self, osm):
        from pipeline.build.spain_beaches import beaches_lens, place
        from pipeline.core.hexgrid import HexGrid

        rings, _ = self._town()
        grid = HexGrid(radius=10.0, cols=5, rows=1)
        owner = [0, 0, 0, -1, -1]  # three land hexes, the third on the sea
        world = {"owner": owner, "county": [0, 0, 0, -1, -1], "counties": ["29069"]}
        munis = [{"geoid": "29069", "name": "Marbella", "state_fips": "29", "centre": list(grid.center(0, 0)),
                  "rings": rings}]
        beaches = [{"beach": b, "municipality": "Marbella", "province": "29"} for b in ("Cabopino", "Venus")]
        placed = place(beaches, munis, [], osm)
        proj = lambda lon, lat: grid.center(0, 0) if lon < -4.85 else grid.center(1, 0)  # west half → hex 0, east → 1
        return placed, beaches_lens(placed, munis, world, grid, proj)

    def test_unmatched_beaches_take_coastal_hexes_in_turn(self):
        placed, lens = self._lens([])
        self.assertTrue(all("lonlat" not in b for b in placed))
        self.assertEqual(lens["values"][:3], [0, 0, 2])  # both on the only coastal hex
        self.assertEqual([lens["names"][k] for k in lens["labels"][2]], ["Cabopino (Marbella)", "Venus (Marbella)"])
        self.assertIn("0 están en su sitio", lens["description"]["es"])

    def test_matched_beaches_sit_at_their_point(self):
        placed, lens = self._lens([{"id": "way/9", "names": ["Platja de Venus"], "lonlat": [-4.82, 36.55]}])
        self.assertEqual(placed[1]["record"], "way/9")
        self.assertEqual(lens["values"][:3], [0, 1, 1])  # Venus at its point (hex 1), Cabopino on the coast
        self.assertEqual([lens["names"][k] for k in lens["labels"][1]], ["Venus (Marbella)"])
        self.assertIn("1 are in place", lens["description"]["en"])


class SpainDishesTest(unittest.TestCase):
    def test_dishes_lens_lists_a_province_dishes_on_its_hexes(self):
        from pipeline.build.spain import dishes_lens

        world = {"owner": [0, 0, 1, -1], "states": ["09", "28"]}
        lens = dishes_lens([{"name": "Morcilla de Burgos", "provinces": ["09"]},
                            {"name": "Papas arrugadas", "provinces": ["35", "38"]}], world)
        self.assertEqual(lens["values"], [1, 1, 0, None])
        self.assertEqual([lens["names"][k] for k in lens["labels"][0]], ["Morcilla de Burgos"])

    def test_category_slug(self):
        from pipeline.sources.es.dishes import slug

        self.assertEqual(slug("la provincia de Córdoba (España)"), "la_provincia_de_crdoba_espaa")


class SpainDailyLensesTest(unittest.TestCase):
    """Broadband, commuting, life expectancy, religious weddings and wildfires (spain_daily and its sources)."""

    @staticmethod
    def process(src, files: dict[str, str]) -> dict:
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as d:
            for name, text in files.items():
                (Path(d) / name).write_text(text, encoding="utf-8")
            with mock.patch.object(type(src), "raw_dir", new_callable=mock.PropertyMock, return_value=Path(d)):
                return src.process()

    def test_rest_of_province_is_the_province_minus_its_listed_municipalities(self):
        from pipeline.sources.es.ine_daily import rest_of_provinces

        rest = rest_of_provinces({"28": {"total": 100, "religious": 20}, "08": {"total": 5}},
                                 {"28079": {"total": 60, "religious": 15}})
        self.assertEqual(rest, {"28": {"total": 40, "religious": 5}, "08": {"total": 5}})
        with self.assertRaises(RuntimeError):
            rest_of_provinces({"28": {"total": 10}}, {"28079": {"total": 11}})

    def test_place_of_work_keeps_totals_of_provinces_and_cities(self):
        from pipeline.sources.es.ine_daily import IneLugarTrabajo

        head = ("﻿Total Nacional;Comunidades y Ciudades Autónomas;Provincias;Actividad económica;Lugar trabajo;Sexo;"
                "Periodo;Total\n")
        rows = ["Total Nacional;;;Total CNAE;Mismo municipio al de residencia;Total;2024;8.487.050",
                "Total Nacional;;;Total CNAE;Otra comunidad autónoma;Total;2024;1.216.891",
                "Total Nacional;;;A Agricultura;Otra comunidad autónoma;Total;2024;5",
                "Total Nacional;13 Madrid, Comunidad de;;Total CNAE;Mismo municipio al de residencia;Total;2024;1",
                "Total Nacional;;;Total CNAE;Mismo municipio al de residencia;Total;2023;9"]
        for code in PROVINCES:
            rows += [f"Total Nacional;X;{code} P;Total CNAE;Mismo municipio al de residencia;Total;2024;1.000",
                     f"Total Nacional;X;{code} P;Total CNAE;Distinto municipio de la misma provincia;Total;2024;500",
                     f"Total Nacional;X;{code} P;Total CNAE;Distinto municipio de la misma provincia;Mujeres;2024;7"]
        cities = ("﻿Capitales de provincia y principales ciudades;Lugar trabajo;Sexo;Actividad económica;"
                  "Situación profesional;Periodo;Total\n"
                  "28079 Madrid;Mismo municipio al de residencia;Total;Total CNAE;Total;2024;600\n"
                  "28079 Madrid;Distinto municipio de la misma provincia;Total;Total CNAE;Total;2024;100\n"
                  "28079 Madrid;Distinto municipio de la misma provincia;Total;Total CNAE;Asalariado;2024;99\n")
        out = self.process(IneLugarTrabajo(), {"69968.csv": head + "\n".join(rows) + "\n", "69987.csv": cities})
        self.assertEqual(out["year"], 2024)
        self.assertEqual(out["nation"], {"same": 8487050, "other_community": 1216891})
        self.assertEqual(out["provinces"]["28"], {"same": 1000, "province": 500})
        self.assertEqual(out["municipalities"], {"28079": {"same": 600, "province": 100}})
        self.assertEqual(out["rest_of_province"]["28"], {"same": 400, "province": 400})

    def test_weddings_by_province_nation_and_main_municipalities(self):
        from pipeline.sources.es.ine_daily import IneMatrimonios

        prov = "﻿Nacional y provincias;Mes de celebración;Forma de celebración;Periodo;Total\n" + "".join(
            f"{code} P;Total;{form};2025;{n}\n" for code in PROVINCES
            for form, n in (("Total", "1.000"), ("Matrimonios religiosos", "200")))
        prov += ("Total Nacional;Total;Total;2025;179.823\nTotal Nacional;Total;Matrimonios religiosos;2025;29.023\n"
                 "No residente;Total;Total;2025;5\n28 P;Enero;Total;2025;80\n")
        muni = ("﻿Provincias;Municipios;Mes de celebración;Forma de celebración;Periodo;Total\n"
                "28 Madrid;;Total;Total;2025;1.000\n28 Madrid;28079 Madrid;Total;Total;2025;600\n"
                "28 Madrid;28079 Madrid;Total;Matrimonios religiosos;2025;150\n")
        out = self.process(IneMatrimonios(), {"77172.csv": prov, "37645.csv": muni})
        self.assertEqual(out["nation"], {"total": 179823, "religious": 29023})
        self.assertEqual(out["provinces"]["28"], {"total": 1000, "religious": 200})
        self.assertEqual(out["rest_of_province"]["28"], {"total": 400, "religious": 50})

    def test_life_expectancy_takes_the_latest_year_of_both_tables(self):
        from pipeline.sources.es.ine_daily import IneEsperanzaVida

        prov = "﻿Provincias;Sexo;Periodo;Total\n" + "".join(
            f"{code} P;Ambos sexos;{y};8{y % 10},5\n" for code in PROVINCES for y in (2024, 2025))
        muni = "﻿Municipios;Sexo;Periodo;Total\n28079 Madrid;Ambos sexos;2024;85,3\n28079 Madrid;Mujeres;2024;87,9\n"
        out = self.process(IneEsperanzaVida(), {"1485.csv": prov, "30687.csv": muni})
        self.assertEqual(out["year"], 2024, "2025 has provinces but no municipalities")
        self.assertEqual((out["provinces"]["28"], out["municipalities"]), (84.5, {"28079": 85.3}))

    def test_broadband_reads_the_newest_100_mbps_column(self):
        from pipeline.sources.es import broadband

        header = ["Comunidad Autónoma", "Provincia", "CMUN", "Municipio",
                  "Cob. 100Mbps condiciones máxima demanda\n(junio 2024)",
                  "Cob. 100Mbps condiciones máxima demanda\n(junio 2025)",
                  "Cob. 1Gbps descarga condiciones máxima demanda\n(junio 2026)"]
        rows = [header, ["X", "Y", "01001", "A", "0.5", "0.98588235294117643", "0.1"], ["X", "Y", "01002", "B", "0.5", None],
                ["X", "Y", "01003", "C", "0", "1.0000000030050729"]]
        self.assertEqual(broadband.latest_column(header), (5, 2025))
        self.assertEqual(broadband.coverage(rows, 2, 5), {"01001": 0.9859, "01003": 1.0})
        with self.assertRaises(RuntimeError):
            broadband.latest_column(header[:4])

    def test_effis_keeps_spanish_polygons_of_every_geometry_kind(self):
        from pipeline.sources.es.effis import fires

        sq = [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]
        poly = {"type": "Polygon", "coordinates": sq}
        date = "2025-08-11 13:40:00"
        feats = [{"properties": {"COUNTRY": "ES", "AREA_HA": "40", "PROVINCE": "Ourense", "FIREDATE": date}, "geometry": poly},
                 {"properties": {"COUNTRY": "ES", "AREA_HA": "9", "FIREDATE": date}, "geometry": {
                     "type": "GeometryCollection", "geometries": [poly, {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}]}},
                 {"properties": {"COUNTRY": "PT", "AREA_HA": "500"}, "geometry": poly},
                 {"properties": {"COUNTRY": "ES", "AREA_HA": "0"}, "geometry": poly}]
        self.assertEqual([(f["area_ha"], len(f["rings"])) for f in fires(feats, 2025)], [(40.0, 1), (9.0, 1)])

    def test_effis_keeps_the_start_month(self):
        from pipeline.sources.es.effis import fires

        poly = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
        feats = [{"properties": {"COUNTRY": "ES", "AREA_HA": "600", "FIREDATE": d}, "geometry": poly}
                 for d in ("2022-07-17 00:00:00", "2022-12-01 09:05:00")]
        self.assertEqual([(f["year"], f["month"]) for f in fires(feats, 2022)], [(2022, 7), (2022, 12)])

    def test_burnt_area_is_shared_by_the_hexes_a_fire_covers(self):
        from pipeline.build.spain_daily import burnt_cells
        from pipeline.core.hexgrid import HexGrid

        grid = HexGrid(radius=10.0, cols=2, rows=1)  # cell centres at x = 0 and 17.32; the edge between them at 8.66

        def box(x0, x1, y0=-1.0, y1=1.0):
            return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]

        fires = [{"area_ha": 30.0, "rings": [box(-2, 2)]},
                 {"area_ha": 700.0, "rings": [box(5.0, 12.0)]},
                 {"area_ha": 1.0, "rings": [box(16.0, 16.05, 0.0, 0.05)]}]  # smaller than a sample: its centroid's hex
        out = burnt_cells(fires, lambda lon, lat: (lon, lat), grid)
        self.assertAlmostEqual(sum(out.values()), 731.0)
        sample = 700 * 0.2 / 7  # one 0.2 km column of samples across the 7 km fire
        self.assertAlmostEqual(out[0], 30 + 700 * 3.66 / 7, delta=sample)
        self.assertAlmostEqual(out[1], 1 + 700 * 3.34 / 7, delta=sample)

    def test_lenses_use_a_listed_municipality_or_the_rest_of_its_province(self):
        from pipeline.build import spain_daily

        geoids = ["28079", "28065", "08019"]
        weights = [[(0, 300.0), (1, 100.0)], [(2, 10.0)], []]
        work = {"year": 2024, "nation": {"same": 1, "province": 1, "community": 0, "other_community": 0},
                "municipalities": {"28079": {"same": 75, "province": 25, "community": 0, "other_community": 0}},
                "rest_of_province": {"28": {"same": 20, "province": 70, "community": 0, "other_community": 10}}}
        # (0.25 × 300 + 0.8 × 100) ÷ 400; Barcelona has no figure
        self.assertEqual(spain_daily.commuters_lens(work, geoids, weights)["values"], [0.3875, None, None])
        life = {"year": 2024, "municipalities": {"28079": 85.0}, "provinces": {"28": 84.0, "08": 83.5}}
        self.assertEqual(spain_daily.life_expectancy_lens(life, geoids, weights)["values"], [84.75, 83.5, None])
        weddings = {"year": 2025, "nation": {"total": 10, "religious": 2}, "municipalities": {},
                    "rest_of_province": {"28": {"total": 10, "religious": 1}, "08": {"total": 0, "religious": 0}}}
        self.assertEqual(spain_daily.weddings_lens(weddings, geoids, weights)["values"], [0.1, None, None])
        bb = spain_daily.broadband_lens({"year": 2025, "nation": 0.98, "municipalities": {"28079": 1.0, "28065": 0.6}},
                                        geoids, weights)
        self.assertEqual((bb["id"], bb["group"], bb["values"]), ("broadband", "knowledge", [0.9, None, None]))
        self.assertIn("98,0 %", bb["description"]["es"])
        self.assertIn("Spain: 98.0%", bb["description"]["en"])
class SpainFiestasTest(unittest.TestCase):
    PAGE = ('<dl class="accordion"><dt id="dt1" class="close">Andalucía</dt><dd style="display: none;"><ul>'
            "<li>Semana Santa de Baena, Córdoba (2026)</li><li>Romería del Rocío de Almonte (1980)</li></ul></dd>"
            '<dt id="dt1" class="close">Comunitat Valenciana</dt><dd><ul><li>Callosa de Ensarriá, Alicante (1984)</li>'
            "<li>Fiesta de Moros y Cristianos en honor de la Virgen de las Injurias de\n    </li></ul></dd></dl>")

    def test_entries_and_years(self):
        from pipeline.sources.es.fiestas import entries, split_year

        found = entries(self.PAGE)
        self.assertEqual(found[0], ("Andalucía", "Semana Santa de Baena, Córdoba (2026)"))
        self.assertEqual(found[3], ("Comunitat Valenciana",
                                    "Fiesta de Moros y Cristianos en honor de la Virgen de las Injurias de"))
        self.assertEqual(split_year("Ruta del Tambor y el Bombo (2014, incluye las Semanas Santas de Calanda)"),
                         ("Ruta del Tambor y el Bombo", 2014))
        self.assertEqual(split_year("Fiesta de las Injurias de"), ("Fiesta de las Injurias de", None))

    def test_each_fiesta_once_at_its_highest_category(self):
        from pipeline.sources.es.fiestas import fiestas

        listed = {"internacional": [("Andalucía", "Semana Santa de Baena, Córdoba (2026)")],
                  "nacional": [("Andalucía", "Semana Santa de Baena (2001)"),
                               ("Comunitat Valenciana", "Callosa de Ensarriá, Alicante (1984)"),
                               ("Comunitat Valenciana", "Moros y Cristianos de las Injurias de")]}

        def row(cat, name, munis="", same=""):
            return {"category": cat, "name": name, "municipalities": munis, "same_as": same}

        table = [row("internacional", "Semana Santa de Baena, Córdoba (2026)", "14007"),
                 row("nacional", "Semana Santa de Baena (2001)", same="Semana Santa de Baena, Córdoba (2026)"),
                 row("nacional", "Callosa de Ensarriá, Alicante (1984)", "03048"),
                 row("nacional", "Moros y Cristianos de las Injurias de", same="Callosa de Ensarriá, Alicante (1984)")]
        found = fiestas(listed, table)
        self.assertEqual([(f["name"], f["category"], f["year"], f["municipalities"]) for f in found],
                         [("Semana Santa de Baena, Córdoba", "internacional", 2026, ["14007"]),
                          ("Moros y Cristianos de las Injurias de Callosa de Ensarriá, Alicante", "nacional", 1984,
                           ["03048"])])
        with self.assertRaises(RuntimeError):  # a new declaration nobody placed
            fiestas({**listed, "nacional": listed["nacional"] + [("Galicia", "Entroido de Laza (2027)")]}, table)
        with self.assertRaises(RuntimeError):  # a row the pages no longer list
            fiestas(listed, table + [row("nacional", "Fiesta retirada (1980)", "01001")])

    def test_table_covers_the_cached_pages(self):
        """The table in the repository places every fiesta of the cached official pages, in valid INE codes."""
        import csv

        from pipeline.core.paths import RAW
        from pipeline.sources.es.fiestas import PAGES, TABLE, entries, fiestas

        pages = {c: RAW / "fiestas_interes_turistico" / f"{c}.html" for c in PAGES}
        if not all(p.exists() for p in pages.values()):
            self.skipTest("turismo.gob.es pages not fetched")
        listed = {c: entries(p.read_text(encoding="utf-8")) for c, p in pages.items()}
        with open(TABLE, encoding="utf-8") as f:
            table = list(csv.DictReader(line for line in f if not line.startswith("#")))
        found = fiestas(listed, table)
        self.assertTrue(all(len(m) == 5 and m.isdigit() and m[:2] in PROVINCES for f in found for m in f["municipalities"]))


class SpainRegionalFiestasTest(unittest.TestCase):
    def test_months_named_in_a_date_text(self):
        from pipeline.sources.es.fiestas_autonomicas import months

        self.assertEqual(months("del 30 de abril al 3 de mayo"), [4, 5])
        self.assertEqual(months("Julio: Primer fin de semana"), [7])
        self.assertEqual(months("o último domingo de xullo"), [7])  # Galician
        self.assertEqual(months("el cap de setmana més proper al 24 de juny"), [6])  # Catalan
        self.assertEqual(months("Semana Santa"), [])  # movable: no month

    def test_rows_are_checked(self):
        from pipeline.sources.es.fiestas_autonomicas import fiestas

        def row(**kw):
            return {"community": "galicia", "name": "FESTA DO PULPO", "place": "O Carballiño", "municipalities": "32019",
                    "when": "Agosto: segundo domingo", "state_same": "", "source": "https://www.turismo.gal/", **kw}

        found = fiestas([row(), row(place="Outro")], {"Fiesta del Pulpo (1969)"})
        self.assertEqual((found[0]["municipalities"], found[0]["months"], found[0]["state_same"]), (["32019"], [8], None))
        for bad in ([row(), row()], [row(community="atlantida")], [row(municipalities="3201")],
                    [row(state_same="Fiesta que no existe (1999)")], [row(source="")]):
            with self.assertRaises(RuntimeError):
                fiestas(bad, {"Fiesta del Pulpo (1969)"})
        self.assertEqual(fiestas([row(municipalities="", when="")], set())[0]["municipalities"], [])

    def test_a_machine_readable_list_must_match_the_table(self):
        from pipeline.sources.es.fiestas_autonomicas import check_lists

        rows = [{"community": "andalucia", "name": n} for n in ("Semana Santa", "Semana Santa", "Feria")]
        check_lists(rows, {"andalucia": ["Feria", "Semana Santa", "Semana Santa"]})
        for listed in (["Feria", "Semana Santa"], ["Feria", "Semana Santa", "Semana Santa", "Romería nueva"]):
            with self.assertRaises(RuntimeError):
                check_lists(rows, {"andalucia": listed})

    def test_list_readers(self):
        from pipeline.sources.es.fiestas_autonomicas import (andalucia_names, canarias_names, cantabria_names,
                                                              extremadura_names, galicia_names)

        csv_text = ('DECLARACIÓN DE INTERÉS TURÍSTICO =LOCALIDAD=PROVINCIA=FECHA DE RESOLUCIÓN=ÁMBITO=PROMOTOR=TIPO\n'
                    'Romería de  los Ángeles =Alajar=Huelva =24/01/1970=Autonómico=Ayto.=Fiesta\n'
                    'Cabalgata =Linares=Jaén=01/01/2000=Autonómico=Ayto.=Acontecimiento\n'
                    'Semana Santa de Sevilla=Sevilla=Sevilla=1980=Internacional=Ayto.=Fiesta\n')
        self.assertEqual(andalucia_names(csv_text), ["Romería de los Ángeles"])
        self.assertEqual(galicia_names('<a href="/recurso/-/detalle/x/y" class="title mod-href">FESTA DE  EXALTACIÓN '
                                       'DO PAN DE CEA</a>'), ["FESTA DE EXALTACIÓN DO PAN DE CEA"])
        page = ('<tr data-estacion="v" data-tipo="regional" data-url="u"><td>Fiesta de la Anchoa</td><td>Santoña</td>'
                '<td>Septiembre</td></tr><tr data-estacion="v" data-tipo="nacional" data-url="u"><td>La Folía</td>'
                '<td>San Vicente</td><td>Abril</td></tr>')
        self.assertEqual(cantabria_names(page), ["Fiesta de la Anchoa"])
        register = ('<p>(Registro)</p><table><thead><tr><td>Fiesta</td></tr></thead><tbody><tr><td><a href="x">Fiesta '
                    'de la Manzana</a></td><td>BOC</td></tr></tbody></table>')
        self.assertEqual(canarias_names(register), ["Fiesta de la Manzana"])
        self.assertEqual(extremadura_names('<h2 class="titu2" position="lrr1">\n <a href="/es/explora/x/" alt="y"> '
                                           'Los Empalaos</a></h2>'), ["Los Empalaos"])

    def test_table_places_every_fiesta_in_a_municipality_of_spain(self):
        """The table in the repository: valid rows, INE codes of real municipalities; the machine-readable lists, when
        cached, match it."""
        from pipeline.core.paths import RAW
        from pipeline.sources.es.fiestas import TABLE as STATE
        from pipeline.sources.es.fiestas_autonomicas import LISTS, cache_name, check_lists, fiestas, listed, read_table

        rows = read_table()
        found = fiestas(rows, {r["name"] for r in read_table(STATE)})
        self.assertGreater(len(found), 1000)
        self.assertTrue(all(m[:2] in PROVINCES for f in found for m in f["municipalities"]))
        raw = RAW / "fiestas_autonomicas"
        check_lists(rows, {c: listed(raw, c) for c, (urls, _) in LISTS.items()
                           if all((raw / cache_name(u)).exists() for u in urls)})


class SpainFiestaLensesTest(unittest.TestCase):
    def test_per_inhabitant_is_the_hex_share_of_counts_over_its_residents(self):
        from pipeline.build.spain_fiesta import hex_totals, per_inhabitant

        # Hex 0 holds all of A (1,000 people, 10 bars) and half of B (2,000 of 4,000 people, 4 bars): 12 / 3,000.
        weights = [[(0, 1000), (1, 2000)], [(1, 2000)], [], [(2, 50)]]
        totals = hex_totals({"A": 10, "B": 4, "C": None}, ["A", "B", "C"], [1000, 4000, 50], weights)
        self.assertEqual(totals, [(12.0, 3000), (2.0, 2000), None, None])
        self.assertEqual(per_inhabitant(totals), [4.0, 1.0, None, None])

    def test_times_spain_draws_small_hexes_towards_spain(self):
        from pipeline.build.spain_fiesta import times_spain

        # Spain: 40 bars for 20,000 people (2 per 1,000). A hamlet of 50 with 1 bar reads 20 per 1,000 raw, but
        # (1 + 1,000 × 0.002) / 1,050 = 1.43× Spain's with a prior of 1,000; a town of 19,950 with 39 barely moves.
        hamlet, town = times_spain([(1, 50), (39, 19950), None], 1000)[:2]
        self.assertAlmostEqual(hamlet, 3 / 1050 / 0.002)
        self.assertAlmostEqual(town, 41 / 20950 / 0.002)
        self.assertIsNone(times_spain([(1, 50), None], 1000)[1])

    def test_party_index_is_the_geometric_mean(self):
        from pipeline.build.spain_fiesta import party_index

        self.assertEqual(party_index([[2, 1, 1], [4, 1, None], [1, 1, 3]]), [2.0, 1.0, None])

    def test_a_fiesta_counts_once_per_hex(self):
        from pipeline.build.spain_fiesta import fiesta_cells, fiestas_lens

        cells = fiesta_cells([{"municipalities": ["10107", "10183", "10035"]}], {"10107": 4, "10183": 4, "10035": 5})
        self.assertEqual(cells, [[4, 5]])
        lens = fiestas_lens([{"name": "El Cerezo en Flor", "category": "nacional", "declaration": None,
                              "community": "Extremadura"}], cells, [0] * 6)
        self.assertEqual(lens["values"][4:], [1, 1])
        self.assertEqual(lens["names"], [{"es": "El Cerezo en Flor (Nacional)", "en": "El Cerezo en Flor (National)"}])

    def test_regional_fiestas_join_the_states_once(self):
        from pipeline.build.spain_fiesta import FIESTA_WEIGHT, all_fiestas, fiesta_calendar, fiesta_label

        state = [{"name": "Fiesta del Pulpo", "category": "nacional", "year": 1969, "community": "Galicia",
                  "municipalities": ["32019"]}]
        regional = {"communities": {"galicia": {"name": "Galicia", "declaration": "Festa de Interese Turístico de Galicia"}},
                    "fiestas": [
                        {"name": "FESTA DO PULPO", "community": "galicia", "place": "O Carballiño",
                         "municipalities": ["32019"], "when": "Agosto", "months": [8], "state_same": "Fiesta del Pulpo (1969)"},
                        {"name": "ENTROIDO DE LAZA", "community": "galicia", "place": "Laza", "municipalities": ["32041"],
                         "when": None, "months": [], "state_same": None}]}
        found = all_fiestas(state, regional)
        self.assertEqual([(f["name"], f["category"]) for f in found],
                         [("Fiesta del Pulpo", "nacional"), ("ENTROIDO DE LAZA", "autonomica")])
        self.assertEqual(fiesta_label(found[1]), {"es": "ENTROIDO DE LAZA (Autonómica · Festa de Interese Turístico de "
                                                        "Galicia)",
                                                  "en": "ENTROIDO DE LAZA (Regional · Festa de Interese Turístico de "
                                                        "Galicia)"})
        self.assertEqual(FIESTA_WEIGHT["autonomica"] * 2, FIESTA_WEIGHT["nacional"])
        doc = fiesta_calendar(found, [[3], [5]], "2026-11-27")
        # The State publishes no dates: its entry takes those of the community's entry for the same fiesta.
        self.assertEqual((doc["fiestas"][0]["when"], doc["fiestas"][0]["months"]), ("Agosto", [8]))
        self.assertEqual(doc["fiestas"][1], {"name": "ENTROIDO DE LAZA", "category": "autonomica",
                                             "declaration": "Festa de Interese Turístico de Galicia",
                                             "community": "Galicia", "place": "Laza", "municipalities": ["32041"],
                                             "cells": [5], "when": None, "months": []})

    def test_a_state_fiesta_takes_the_dates_of_all_its_community_entries(self):
        from pipeline.build.spain_fiesta import all_fiestas

        state = [{"name": "Ruta del Tambor", "category": "nacional", "year": 2014, "community": "Aragón",
                  "municipalities": ["44013"]},
                 {"name": "Fiesta sin fecha", "category": "internacional", "year": 1980, "community": "Aragón",
                  "municipalities": ["44216"]}]

        def twin(when, months, same="Ruta del Tambor (2014, incluye las Semanas Santas de Calanda)"):
            return {"name": "X", "community": "aragon", "place": "", "municipalities": [], "when": when,
                    "months": months, "state_same": same}

        regional = {"communities": {"aragon": {"name": "Aragón", "declaration": None}},
                    "fiestas": [twin("Semana Santa", []), twin("Del 9 al 15 de Agosto", [8]),
                                twin("Semana Santa", []), twin("Julio y Septiembre", [7, 9])]}
        found = all_fiestas(state, regional)
        self.assertEqual([(f["when"], f["months"]) for f in found],
                         [("Semana Santa; Del 9 al 15 de Agosto; Julio y Septiembre", [7, 8, 9]), (None, [])])
        with self.assertRaises(RuntimeError):
            all_fiestas(state, {**regional, "fiestas": [twin("Agosto", [8], same="Fiesta que no está (1999)")]})

    def test_the_calendar_must_match_the_lens(self):
        import tempfile

        from pipeline.build.spain_fiesta import check

        with tempfile.TemporaryDirectory() as d:
            web = Path(d)
            (web / "lenses.json").write_text(json.dumps({"lenses": [
                {"id": "fiestas", "names": ["A", "B"], "labels": [[0], [0, 1], None]}]}))
            items = [{"name": "A", "cells": [0, 1], "when": "agosto", "months": [8]},
                     {"name": "B", "cells": [1], "when": None, "months": []}]
            (web / "fiestas.json").write_text(json.dumps({"fiestas": items}))
            self.assertEqual(check(web)[0][0], "PASS")
            items[1]["cells"] = [2]
            (web / "fiestas.json").write_text(json.dumps({"fiestas": items}))
            self.assertEqual(check(web)[0][0], "FAIL")

    def test_bars_go_to_their_municipality_or_the_nearest_capital(self):
        from pipeline.build.spain_fiesta import locate

        def square(x0):
            return [[[x0, 0], [x0 + 10, 0], [x0 + 10, 10], [x0, 10]]]

        munis = [{"geoid": "A", "rings": square(0), "centre": [5, 5]},
                 {"geoid": "B", "rings": square(10), "centre": [15, 5]}]
        codes, outside = locate([[2, 2], [12, 8], [19, 30]], munis, lambda lon, lat: (lon, lat))
        self.assertEqual((codes, outside), (["A", "B", "B"], 1))

    def test_wikidata_named_items_once_with_label_and_position(self):
        from pipeline.sources.es.wikidata import WikidataEs

        rows = [{"s": {"value": "http://www.wikidata.org/entity/Q1"}, "sLabel": {"value": "Castillo de Loarre"},
                 "coord": {"value": "Point(-0.6127 42.3256)"}},
                {"s": {"value": "http://www.wikidata.org/entity/Q1"}, "sLabel": {"value": "Castillo de Loarre"},
                 "coord": {"value": "Point(-0.6 42.3)"}},
                {"s": {"value": "http://www.wikidata.org/entity/Q2"}, "sLabel": {"value": "Q2"},
                 "coord": {"value": "Point(-1 40)"}}]
        source = WikidataEs()
        source._rows = lambda name: rows
        self.assertEqual(source._named("castles"), [{"qid": "Q1", "label": "Castillo de Loarre",
                                                     "coord": (-0.6127, 42.3256)}])


def person(**kw) -> dict:
    """A processed great person (wikidata_personajes) with what a test does not care about filled in."""
    return {"qid": "Q1", "name": "X", "description": None, "female": False, "born": None, "died": None,
            "kinds": ["writers"], "primary": "writers", "role": "Q36180", "word": None, "trade": None,
            "sitelinks": 50, "birthplaces": [], **kw}


class SpainGreatPeopleRulesTest(unittest.TestCase):
    """The category, fame and primary-category rules of pipeline/sources/es/personajes.py."""

    TREES = {"Q36180": {"Q36180", "Q49757"}, "Q1028181": {"Q1028181", "Q3374326"}, "Q81096": {"Q81096", "Q2079935"},
             "Q116": {"Q116", "Q3847454", "Q49967564"}}

    def trees(self):
        from pipeline.sources.es.personajes import DEEP

        return {c: self.TREES.get(c, {c}) for c in DEEP}

    def test_every_rule_class_has_a_noun_and_every_category_a_style(self):
        from pipeline.build.spain_personajes import NOUNS, STYLE
        from pipeline.sources.es.personajes import KIND_IDS, KINDS, WORDS

        self.assertEqual(list(STYLE), KIND_IDS)
        self.assertEqual({r.cls for k in KINDS for r in k.rules} - set(NOUNS), set())
        self.assertLessEqual(set(WORDS), set(KIND_IDS))
        self.assertEqual(len({c for _, c in STYLE.values()}), len(STYLE))  # one colour each

    def test_trees_count_subclasses_exact_classes_do_not_and_excluded_classes_never(self):
        from pipeline.sources.es.personajes import BY_ID, hits

        trees = self.trees()
        self.assertEqual(list(hits(BY_ID["writers"], {"P106": {"Q49757"}}, trees)), [BY_ID["writers"].rules[0]])
        sailor = {"P106": {"Q476246"}}  # a sport sailor: under sailor (Q45199), which counts without its tree
        self.assertEqual(hits(BY_ID["explorers"], sailor, {**trees, "Q45199": {"Q45199", "Q476246"}}), {})
        bishop = {"P39": {"Q49967564"}}  # the bishop of Urgell, which Wikidata files under monarch
        self.assertEqual(hits(BY_ID["monarchs"], bishop, trees), {})
        self.assertTrue(hits(BY_ID["monarchs"], {"P39": {"Q3847454"}}, trees))

    def test_classify_keeps_categories_whose_threshold_the_person_meets(self):
        from pipeline.sources.es.personajes import BY_ID, classify

        values = {"P106": {"Q36180", "Q1028181"}}
        self.assertIsNone(classify(values, BY_ID["artists"].min_sitelinks - 1, self.trees()))
        c = classify(values, BY_ID["artists"].min_sitelinks, self.trees())
        self.assertEqual((c["kinds"], c["kept"]), (["artists", "writers"], ["artists"]))
        # A conquistador counts whatever his fame.
        self.assertEqual(classify({"P106": {"Q126236"}}, 0, self.trees())["kept"], ["conquistadors"])
        # A Guanche king is named by his own title: mencey in Tenerife, guanarteme in Gran Canaria.
        from pipeline.sources.es.personajes import GUANARTEME, MENCEY
        for title in (MENCEY, GUANARTEME):
            c = classify({"P39": {title, "Q116"}}, BY_ID["monarchs"].min_sitelinks, self.trees())
            self.assertEqual(c["roles"]["monarchs"], title)

    def test_primary_decisive_then_description_then_most_occupations(self):
        from pipeline.sources.es.personajes import classify, primary

        trees = self.trees()
        picasso = classify({"P106": {"Q1028181", "Q3374326", "Q1281618", "Q36180", "Q2079935"}}, 266, trees)
        self.assertEqual(picasso["counts"], {"engineers": 1, "artists": 3, "writers": 1})
        self.assertEqual(primary(picasso, None)["primary"], "artists")  # most occupations
        self.assertEqual(primary(picasso, None)["role"], "Q1028181")  # a painter before a sculptor
        writer = primary(picasso, "poeta y pintor español")  # the description's first trade wins over the count
        self.assertEqual((writer["primary"], writer["word"], writer["trade"]), ("writers", "poeta", "poeta"))
        pizarro = classify({"P106": {"Q126236", "Q189290", "Q1402561", "Q11900058"}}, 90, trees)
        self.assertEqual(primary(pizarro, "militar y explorador español")["primary"], "conquistadors")  # decisive
        tie = classify({"P106": {"Q36180", "Q1028181"}}, 266, trees)
        self.assertEqual(primary(tie, "diplomático")["primary"], "artists")  # a tie goes to the first in KINDS

    def test_described_matches_phrases_and_only_the_persons_categories(self):
        from pipeline.sources.es.personajes import described

        self.assertEqual(described("Director de orquesta y compositor español", ["musicians"]),
                         [("musicians", "director de orquesta"), ("musicians", "compositor")])
        self.assertEqual(described("cineasta y escritor hispanomexicano", ["writers"]), [("writers", "escritor")])
        self.assertEqual(described(None, ["writers"]), [])

    def test_dates_years_before_christ_precision_and_rank(self):
        from pipeline.build.spain_personajes import date_text, years
        from pipeline.sources.es.personajes import best_date, year

        self.assertEqual(year("-0003-01-01T00:00:00Z"), -3)
        self.assertEqual(year("1881-10-25T00:00:00Z"), 1881)
        self.assertIsNone(year("http://www.wikidata.org/.well-known/genid/abc"))
        self.assertEqual(best_date([("NormalRank", 1500, 7), ("NormalRank", 1547, 11), ("NormalRank", 1546, 11)]),
                         {"year": 1546, "precision": 11})
        self.assertEqual(best_date([("NormalRank", 1547, 11), ("PreferredRank", 1548, 9)]),
                         {"year": 1548, "precision": 9})
        self.assertEqual(date_text({"year": -3, "precision": 9}), "4 a. C.")  # SPARQL counts a year 0
        self.assertEqual(date_text({"year": 1550, "precision": 8}), "h. 1550")
        self.assertEqual(date_text({"year": 1501, "precision": 7}), "s. XVI")
        self.assertIsNone(date_text({"year": 1000, "precision": 6}))
        self.assertEqual(years({"year": 1881, "precision": 11}, {"year": 1973, "precision": 11}), "1881–1973")
        self.assertEqual(years({"year": 1986, "precision": 11}, None), "n. 1986")
        self.assertEqual(years(None, {"year": 1550, "precision": 9}), "m. 1550")
        self.assertEqual(date_text({"year": -3, "precision": 9}, "en"), "4 BC")
        self.assertEqual(date_text({"year": 1550, "precision": 8}, "en"), "c. 1550")
        self.assertEqual([date_text({"year": y, "precision": 7}, "en") for y in (1501, 1001, 1101, 201, 301)],
                         ["16th century", "11th century", "12th century", "3rd century", "4th century"])
        self.assertEqual(years({"year": 1986, "precision": 11}, None, "en"), "b. 1986")
        self.assertEqual(years(None, {"year": 1550, "precision": 9}, "en"), "d. 1550")

    def test_noun_is_the_descriptions_word_a_nobels_trade_or_the_roles_noun_in_the_persons_gender(self):
        from pipeline.build.spain_personajes import noun, note

        self.assertEqual(noun(person(word="poeta")), "poeta")
        self.assertEqual(noun(person(primary="nobel", role="Q7191", trade="médico")), "médico, premio Nobel")
        self.assertEqual(noun(person(primary="artists", role="Q1028181", female=True)), "pintora")
        # A Guanche king's own title wins over the description's "rey".
        self.assertEqual(noun(person(primary="monarchs", role="Q3323725", word="rey")), "guanarteme")
        self.assertEqual(note(person(born={"year": 1547, "precision": 11}, died={"year": 1616, "precision": 11})),
                         {"es": "escritor, 1547–1616", "en": "writer, 1547–1616"})
        self.assertEqual(noun(person(primary="nobel", role="Q7191", trade="médico"), "en"), "physician, Nobel laureate")
        self.assertEqual(noun(person(primary="artists", role="Q1028181", female=True), "en"), "painter")

    def test_birthplace_without_coordinates_takes_the_place_it_is_in_and_regions_do_not_count(self):
        from pipeline.sources.es.personajes import birthplace

        oratorio = {"qid": "Q9", "name": "Oratorio", "coord": None, "types": {"Q1"},
                    "up": {"Q30": {"coord": (1.0, 2.0), "types": set()}, "Q20": {"coord": (3.0, 4.0), "types": set()}}}
        self.assertEqual(birthplace(oratorio), {"qid": "Q9", "name": "Oratorio", "coord": (3.0, 4.0), "via": "P131",
                                                "area": False})
        spain = {"qid": "Q29", "name": "España", "coord": (-4.0, 40.0), "types": {"Q3624078"}, "up": {}}
        self.assertTrue(birthplace(spain)["area"])
        self.assertIsNone(birthplace({**spain, "coord": None, "types": set()})["via"])


class SpainGreatPeopleMapTest(unittest.TestCase):
    """Placement and lenses of pipeline/build/spain_personajes.py on a row of six hexes, 17 km apart: the sea, three of
    Spain (the first two inside a municipality), France and the sea again."""

    MUNI = {"rings": [[[8, -8], [44, -8], [44, 8], [8, 8]]]}  # holds the centres of hexes 1 and 2

    def setUp(self):
        from pipeline.build.spain_personajes import Placer
        from pipeline.build.world import FOREIGN, WATER
        from pipeline.core.hexgrid import HexGrid

        self.grid = HexGrid(radius=10.0, cols=6, rows=1)
        self.owner = [WATER, 0, 0, 0, FOREIGN, WATER]
        self.at = [self.grid.center(c, 0) for c in range(6)]  # lon/lat = map km (identity projection)
        self.placer = Placer(lambda lon, lat: (lon, lat), self.grid, self.owner, [self.MUNI])

    def test_placer(self):
        self.assertEqual(self.placer.cell(*self.at[1]), 1)  # inside a municipality
        self.assertEqual(self.placer.cell(*self.at[0]), 1)  # a port on a sea hex: the Spanish land next to it
        self.assertIsNone(self.placer.cell(*self.at[3]))  # outside every outline, next to France
        self.assertIsNone(self.placer.cell(*self.at[4]))  # France
        self.assertIsNone(self.placer.cell(500.0, 0.0))  # off the map

    def test_place_takes_the_first_birthplace_in_spain_or_says_why_not(self):
        from pipeline.build.spain_personajes import place

        def bp(coord, area=False):
            return {"qid": "Q2", "name": "P", "coord": coord, "via": "P625" if coord else None, "area": area}

        self.assertEqual(place(person(birthplaces=[bp(self.at[4]), bp(self.at[2])]), self.placer)[0], 2)
        self.assertEqual(place(person(birthplaces=[bp(self.at[4])]), self.placer), "abroad")
        self.assertEqual(place(person(birthplaces=[bp(self.at[1], area=True)]), self.placer), "area")
        self.assertEqual(place(person(birthplaces=[bp(None)]), self.placer), "no_coordinates")
        self.assertEqual(place(person(birthplaces=[]), self.placer), "no_coordinates")

    def test_lenses_and_people_file(self):
        from unittest import mock

        from pipeline.build import spain_personajes as sp
        from pipeline.sources.es.personajes import KIND_IDS

        def at(c, **kw):
            return person(birthplaces=[{"qid": "Q2", "name": f"Lugar {c}", "coord": self.at[c], "via": "P625",
                                        "area": False}], **kw)

        people = [at(1, name="Pintor A", primary="artists", role="Q1028181"),
                  at(1, name="Escritor", born={"year": 1547, "precision": 11}),
                  at(1, name="Pintor B", primary="artists", role="Q1028181"),
                  at(2, name="Escritora", female=True), at(4, name="Francés"), person(name="Sin lugar")]
        payload = {"vintage": "Wikidata, 2026-11-26", "data": {"people": people, "conquistadors_without_birthplace": 2}}
        with mock.patch.object(sp, "load_interim_payload", return_value=payload):
            (count, kind), doc = sp.great_people({"owner": self.owner}, lambda lon, lat: (lon, lat), self.grid,
                                                 [self.MUNI])
        self.assertEqual(count["values"], [None, 3, 1, 0, None, None])
        artists, writers = KIND_IDS.index("artists"), KIND_IDS.index("writers")
        self.assertEqual(kind["values"], [None, artists, writers, None, None, None])  # two painters, one writer
        self.assertEqual(kind["categories"][artists]["name"], {"es": "Pintores y escultores", "en": "Painters and sculptors"})
        self.assertEqual({count["names_from"], kind["names_from"]}, {sp.FILE})
        self.assertNotIn("names", count)  # the names stay in the people file
        self.assertEqual([(p["name"], p["note"]["es"], p["place"], p["cell"]) for p in doc["people"]],
                         [("Pintor A", "pintor", "Lugar 1", 1), ("Escritor", "escritor, n. 1547", "Lugar 1", 1),
                          ("Pintor B", "pintor", "Lugar 1", 1), ("Escritora", "escritora", "Lugar 2", 2)])
        self.assertIn("Fuera quedan 2: 1 nacieron fuera de la España actual", count["description"]["es"])
        self.assertIn("Left out: 2, of whom 1 were born outside today's Spain", count["description"]["en"])
        self.assertEqual(doc["people"][1]["note"]["en"], "writer, b. 1547")

    def test_check_matches_the_lenses_against_the_people_file(self):
        import tempfile

        from pipeline.build import spain_personajes as sp
        from pipeline.sources.es.personajes import KIND_IDS

        people = {"categories": [{"id": k} for k in KIND_IDS],
                  "people": [{"name": "A", "cell": 1, "kind": KIND_IDS.index("writers")}]}
        lenses = {"lenses": [{"id": "great_people", "names_from": sp.FILE, "values": [None, 1, 0, 0, None, None]},
                             {"id": "great_people_kind", "names_from": sp.FILE,
                              "values": [None, KIND_IDS.index("writers"), None, None, None, None]}]}
        with tempfile.TemporaryDirectory() as d:
            for name, doc in (("lenses", lenses), ("world", {"owner": self.owner}), (sp.FILE, people)):
                Path(d, f"{name}.json").write_text(json.dumps(doc))
            self.assertEqual(sp.check(d)[0][0], "PASS")
            lenses["lenses"][0]["values"][2] = 5
            Path(d, "lenses.json").write_text(json.dumps(lenses))
            self.assertEqual(sp.check(d), [("FAIL", "lens great_people: values differ from personajes.json")])
            Path(d, "lenses.json").write_text(json.dumps({"lenses": [{"id": "density", "values": []}]}))
            self.assertEqual(sp.check(d), [])  # a map without people lenses (the US)
