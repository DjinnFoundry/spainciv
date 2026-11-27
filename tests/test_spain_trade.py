"""Spain's trade routes: the EPTMC source parse (pipeline/sources/es/eptmc.py) on sheets laid out like the ministry's
workbook, the builder (pipeline/build/spain_trade.py) on a small grid, its check(), and the built file."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from pipeline.build import spain_trade
from pipeline.core.hexgrid import HexGrid
from pipeline.core.lang import pick_all
from pipeline.countries import COUNTRIES, using
from pipeline.sources.es import eptmc

# The survey's row and column order (Castilla-La Mancha before Castilla y León) and its short labels; table 6.3 and
# 7.5 use the long ones.
ORDER = ["01", "02", "03", "04", "05", "06", "08", "07", "09", "10", "11", "12", "13", "14", "15", "16", "17", "18+19"]
SHORT = {"01": "Andalucía", "02": "Aragón", "03": "Asturias, \nP. de", "04": "Balears,\n Illes", "05": "Canarias",
         "06": "Cantabria", "07": "Castilla \ny León", "08": "Castilla-\nLa Mancha", "09": "Cataluña",
         "10": "Comunidad\nValenciana", "11": "Extre-\nmadura", "12": "Galicia", "13": "Madrid, \nC. de",
         "14": "Murcia, \nR de", "15": "Navarra, \nC. F de", "16": "País \nVasco", "17": "Rioja, La",
         "18+19": "Ceuta \ny Melilla"}
ROW = {**SHORT, "03": "Asturias, P. de", "10": "Com. Valenciana", "13": "Madrid, C. de", "14": "Murcia, R. de",
       "15": "Navarra, C. F. de", "11": "Extremadura", "07": "Castilla y León", "08": "Castilla-La Mancha",
       "04": "Balears, Illes", "16": "País Vasco", "18+19": "Ceuta y Melilla"}
LONG = {**ROW, "03": "Asturias, Principado de", "10": "Comunidad Valenciana", "13": "Madrid, Comunidad de",
        "14": "Murcia, Región de", "15": "Navarra, C. Foral de"}
ISLANDS = {"04", "05", "18+19"}
GAP = 50.0  # thousand tonnes each mainland community sends to the islands (`..` in the matrix)


def flows():
    """Thousand tonnes origin → destination: 5000 inside each community, 100 between mainland ones, and CLM → Madrid
    999 against CyL → Madrid 111 (the order trap)."""
    t = {}
    for o in ORDER:
        for d in ORDER:
            if o == d:
                t[o, d] = 5000.0
            elif o in ISLANDS or d in ISLANDS:
                t[o, d] = None
            else:
                t[o, d] = 100.0
    t["08", "13"], t["07", "13"] = 999.0, 111.0
    return t


def sent(t, o):
    return sum(v for (a, b), v in t.items() if a == o and b != o and v is not None) + (0 if o in ISLANDS else GAP)


def received(t, d):
    return sum(v for (a, b), v in t.items() if b == d and a != d and v is not None) + (0 if d in ISLANDS else GAP)


def show(v):
    return ".." if v is None else repr(v)


def matrix_sheets(t):
    """6.7 and 6.7s as the workbook lays them out: the first ten destinations with the labels on the left; the other
    eight, the totals and the labels on the right."""
    left_cols, right_cols = ORDER[:10], ORDER[10:]
    nat = sum(sent(t, o) for o in ORDER)
    left = [["TRANSPORTE INTERIOR"], ["Tabla 6.7"], [], ["(Miles de tn)"],
            ["DESTINO\n", *(SHORT[d] for d in left_cols)], ["ORIGEN"]]
    right = [["TRANSPORTE INTERIOR"], ["Tabla 6.7"], [], [None] * 10 + ["(Miles de tn)"],
             [*(SHORT[d] for d in right_cols), "TOTAL\nDE ORIGEN", "Del cual, \nexpedido\na otras CC.AA", "DESTINO"],
             [None] * 10 + ["ORIGEN"]]
    for o in ORDER:
        left.append([ROW[o], *(show(t[o, d]) for d in left_cols)])
        right.append([*(show(t[o, d]) for d in right_cols), "1.0", repr(sent(t, o)), f"  {ROW[o]}"])
    left.append(["TOTAL DE DESTINO", *("1.0" for _ in left_cols), "999.0"])  # a stray cell past the header, as in 2025
    left.append(["Del cual, recibido \nde otras CC.AA.", *(repr(received(t, d)) for d in left_cols)])
    right.append([*("1.0" for _ in right_cols), "1.0", "-", "  TOTAL\n  DE DESTINO"])
    right.append([*(repr(received(t, d)) for d in right_cols), None, repr(nat), "  Del cual, recibido \n  de otras CC.AA."])
    right.append(["Fuente: Encuesta Permanente de Transporte de Mercancías por Carretera."])
    return left, right


def trips_sheet(t):
    rows = [["TRANSPORTE TOTAL"], ["Tabla 6.3"], [None] * 9 + ["(Miles de tn)"],
            ["Comunidad Autónoma", "Total", "Intra-municipal", "Inter-municipal", None, "Recibido de\notras CC.AA.",
             "Expedido a\notras CC.AA", None, "Recibido", "Expedido"]]
    nat = sum(sent(t, o) for o in ORDER)
    rows.append(["TOTAL", "90000.0", "18000.0", "72000.0", None, repr(nat), repr(nat), None, "30.0", "40.0"])
    for o in ORDER:
        rows.append([LONG[o], "5000.0", "1000.0", "4000.0", None, repr(received(t, o)), repr(sent(t, o)), None,
                     "." if o == "05" else "3.0", "4.0"])
    rows.append(["Fuente: Encuesta Permanente"])
    return rows


HEAD_LEFT = [["", "", "Productos", "Productos", "Combustibles", "Productos", "Minerales"],
             ["", "", "agrícolas", "alimenticios", "minerales", "petrolíferos", "y residuos"],
             ["Comunidad Autónoma", "TOTAL", "y animales", " y forrajes", "sólidos", "", "para "],
             ["y tipo de desplazamiento", "", "vivos", "", "", "", "refundición"]]
HEAD_RIGHT = [["Productos", "Minerales y ", "Abonos", "Productos ", "Máquinas,", "", ""],
              ["metalúrgicos", "materiales", "", "químicos", "vehículos,", "", ""],
              ["", "para ", "", "", "objetos", "", "Comunidad Autónoma"],
              ["", "construcción", "", "", "manufacturados", "", "y tipo de desplazamiento"]]
KINDS = ["  Total transportado (a+b+c+d)", "    Total de origen   (a+b+c)", "    Total de destino  (a+b+d)",
         "  Intramunicipal (a)", "  Intermunicipal intrarregional (b)", "  Interregional (c+d)", "    Expedido (c)",
         "    Recibido  (d)"]


def goods_sheets(t):
    """7.5p1…p8: four pairs, the communities split among them; each class sends and receives a tenth."""
    book = {}
    groups = [ORDER[0:5], ORDER[5:10], ORDER[10:14], ORDER[14:18]]
    for k, group in enumerate(groups):
        left = [["TRANSPORTE INTERIOR"], ["Tabla 7.5  Toneladas según clases de mercancía"], [], ["(Miles de tn)"],
                *HEAD_LEFT]
        right = [["TRANSPORTE INTERIOR", None, None, None, None, None, ""], ["Tabla 7.5"], [],
                 [None] * 6 + ["(Miles de tn)"], *HEAD_RIGHT]
        if k == 0:
            for lab in ("TOTAL", "  Intramunicipal", "  Intermunicipal intrarregional", "  Interregional"):
                left.append([lab, "1.0", *["0.1"] * 5])
                right.append([*["0.1"] * 5, None, lab])
        for c in group:
            left.append([LONG[c], "", "", "", "", "", ""])
            right.append(["", "", "", "", "", "", LONG[c]])
            for kind in KINDS:
                total = {"    Expedido (c)": sent(t, c), "    Recibido  (d)": received(t, c)}.get(kind, 1.0)
                share = ".." if c in ISLANDS and kind in ("    Expedido (c)", "    Recibido  (d)") else repr(total / 10)
                left.append([kind, repr(total), *[share] * 5])
                right.append([*[share] * 5, None, kind])
        left.append(["Fuente: Encuesta Permanente"])
        right.append(["Fuente: Encuesta Permanente"])
        book[f"7.5p{2 * k + 1}"], book[f"7.5p{2 * k + 2}"] = left, right
    return book


def workbook(t=None):
    t = t or flows()
    tons_l, tons_r = matrix_sheets(t)
    tkm_l, tkm_r = matrix_sheets({k: None if v is None else v * 0.3 for k, v in t.items()})
    # tonne-km totals are not checked; keep the tonnes' "expedido" column so the layouts match
    return {"6.7": tons_l, "6.7s": tons_r, "6.8": tkm_l, "6.8s": tkm_r, "6.3": trips_sheet(t), **goods_sheets(t)}


class ParseTest(unittest.TestCase):
    def test_labels_and_the_order_trap(self):
        d = eptmc.parse(workbook())
        self.assertEqual(d["tons_k"]["08"]["13"], 999.0)  # Castilla-La Mancha, listed before Castilla y León
        self.assertEqual(d["tons_k"]["07"]["13"], 111.0)
        self.assertEqual(d["tons_k"]["13"]["13"], 5000.0)
        self.assertAlmostEqual(d["tkm_m"]["08"]["13"], 299.7)
        self.assertEqual(d["codes"], eptmc.CODES)
        self.assertEqual(d["trips_k"]["13"]["sent"], sent(flows(), "13"))
        self.assertEqual(d["goods_k"]["13"]["sent"], [sent(flows(), "13") / 10] * 10)

    def test_label_forms(self):
        for label, code in [("Asturias, \nP. de", "03"), ("Asturias, Principado de", "03"), ("Com. Valenciana", "10"),
                            ("C. Valenciana", "10"), ("Comunidad\nValenciana", "10"), ("Madrid, C. de", "13"),
                            ("Madrid, Comunidad de", "13"), ("Murcia, \nR de", "14"), ("Navarra, C. F. de", "15"),
                            ("Navarra, Comunidad Foral de", "15"), ("Rioja, La", "17"), ("Extre-\nmadura", "11"),
                            ("Castilla-\nLa Mancha", "08"), ("Castilla \ny León", "07"), ("Ceuta \ny Melilla", "18+19")]:
            self.assertEqual(eptmc.LABELS.get(eptmc.norm(label)), code, label)

    def test_not_significant_is_null_not_zero(self):
        d = eptmc.parse(workbook())
        self.assertIsNone(d["tons_k"]["09"]["04"])
        self.assertIsNone(d["tons_k"]["05"]["13"])
        self.assertIsNone(d["goods_k"]["04"]["sent"][0])
        self.assertIsNone(d["trips_k"]["05"]["intl_received"])  # "." is null as well
        self.assertEqual(d["not_significant"], ["04", "05", "18+19"])

    def test_each_marker_is_null_and_a_blank_raises(self):
        # `..` not significant; `.` and `-`, marks the workbook leaves undefined: none of them is read as zero
        for mark in ("..", ".", "-", " .. "):
            self.assertIsNone(eptmc.cell(mark, "here"), mark)
        self.assertEqual(eptmc.cell("0", "here"), 0.0)
        for bad in ("", None, "n.d."):
            with self.assertRaises(eptmc.EptmcError):
                eptmc.cell(bad, "here")

    def test_updated_from_last_modified(self):
        self.assertEqual(eptmc.updated({"last_modified": "Mon, 16 Nov 2026 11:05:08 GMT"}), "2026-11-16")
        for entry in ({}, {"last_modified": "yesterday"}, {"last_modified": None}):
            with self.assertRaises(eptmc.EptmcError):
                eptmc.updated(entry)

    def test_unknown_label_raises(self):
        book = workbook()
        book["6.7"][7][0] = "Andalusia"
        with self.assertRaises(eptmc.EptmcError):
            eptmc.parse(book)
        book = workbook()
        book["7.5p2"][5][0] = "Productos siderúrgicos"
        with self.assertRaises(eptmc.EptmcError):
            eptmc.parse(book)

    def test_tampered_rows_raise(self):
        def tamper(edit):
            book = workbook()
            edit(book)
            with self.assertRaises(eptmc.EptmcError):
                eptmc.parse(book)

        andalucia = 6  # the first origin row of 6.7 / 6.7s
        tamper(lambda b: b["6.7"][andalucia].__setitem__(2, "900.0"))  # shown flows exceed "expedido"
        tamper(lambda b: b["6.7s"][andalucia].__setitem__(9, "5000.0"))  # 6 %+ of "expedido" not in the matrix
        tamper(lambda b: b["6.7"][andalucia].__setitem__(1, "4000.0"))  # diagonal ≠ intra + intermunicipal
        tamper(lambda b: b["6.7"][andalucia].__setitem__(2, ""))  # an empty matrix cell
        tamper(lambda b: b.pop("7.5p8"))

    def test_real_workbook(self):
        path = eptmc.Eptmc().raw_dir / eptmc.FILE
        if not path.exists():
            self.skipTest("the EPTMC workbook is not downloaded")
        d = eptmc.Eptmc().process()
        self.assertAlmostEqual(d["tons_k"]["08"]["13"], 23687.1, delta=0.05)
        self.assertAlmostEqual(d["tons_k"]["13"]["08"], 16955.8, delta=0.05)
        self.assertAlmostEqual(d["trips_k"]["national"]["sent"], 402640.3, delta=0.05)
        self.assertRegex(d["updated"], r"^\d{4}-\d{2}-\d{2}$")


# ------------------------------------------------------------------ builder

GRID = HexGrid(10.0, 12, 10)
STATES = ["28", "45", "08", "07", "04"]  # Madrid, Toledo (CLM), Barcelona (Cataluña), Balears, Almería (Andalucía)


def world_fixture():
    """Castilla-La Mancha a C (its cells' mean falls in the gap, on Madrid's cells); Cataluña in the east; the
    Balearics in a corner; Andalucía in the south."""
    owner = [-1] * GRID.size
    for i in range(GRID.size):
        col, row = GRID.col_row(i)
        if col == 3 and 2 <= row <= 6 or row in (2, 6) and 3 <= col <= 6:
            owner[i] = 1
        elif col in (4, 5) and 3 <= row <= 5:
            owner[i] = 0
        elif col >= 9 and row <= 4:
            owner[i] = 2
        elif (col, row) == (0, 0):
            owner[i] = 3
        elif row >= 8 and col <= 5:
            owner[i] = 4
    return {"grid": GRID.to_dict(), "owner": owner, "states": STATES}


class BuilderTest(unittest.TestCase):
    def setUp(self):
        self.data = eptmc.parse(workbook())
        self.world = world_fixture()
        self.zones = spain_trade.build_zones(self.world, self.data)

    def test_zones(self):
        self.assertEqual(sorted(self.zones), sorted(eptmc.CODES))
        z = self.zones["13"]
        self.assertEqual(z["provinces"], ["28"])
        self.assertEqual(z["name"]["es"], "Comunidad de Madrid")
        self.assertEqual(z["short"]["en"], "Madrid")
        self.assertTrue(z["significant"])
        self.assertFalse(self.zones["04"]["significant"])
        self.assertEqual(self.zones["18+19"]["provinces"], ["51", "52"])
        self.assertIsNone(self.zones["12"]["anchor"])  # Galicia has no cells here
        self.assertIsNone(self.zones["04"]["anchor"])  # the Balearics have cells, but no published flows
        self.assertEqual(self.zones["10"]["short"], {"es": "C. Valenciana", "en": "Valencia region"})
        self.assertEqual(self.zones["18+19"]["short"]["es"], "Ceuta y Melilla")
        self.assertEqual(z["totals_k"]["within"], 5000.0)

    def test_anchor_inside_a_c_shaped_zone(self):
        clm = self.zones["08"]["anchor"]
        self.assertEqual(self.world["owner"][clm["cell"]], STATES.index("45"))
        self.assertEqual(self.world["owner"][self.zones["13"]["anchor"]["cell"]], STATES.index("28"))

    def test_partners(self):
        self.assertEqual(self.zones["13"]["partners"][0], ["08", 1099.0, "truck"])
        self.assertEqual(len(self.zones["13"]["partners"]), spain_trade.PARTNERS)
        self.assertEqual(self.zones["04"]["partners"], [])  # all its cells are `..`

    def test_routes(self):
        routes = spain_trade.build_routes(self.zones, self.data)
        pairs = [(r["a"], r["b"]) for r in routes]
        self.assertEqual(pairs[0], ("08", "13"))
        self.assertTrue(all(a not in ISLANDS and b not in ISLANDS for a, b in pairs))  # Balears has cells, no routes
        self.assertEqual(len(routes), 6)  # the pairs of Andalucía, CLM, Cataluña and Madrid (the others lack cells)
        r = routes[0]
        self.assertEqual((r["tons_k"], r["ab_k"], r["ba_k"]), (1099.0, 999.0, 100.0))
        self.assertEqual(r["haul_km"], round(r["tkm_m"] * 1e3 / r["tons_k"]))
        self.assertEqual(r["haul_km"], 300)
        self.assertNotIn("path", r)
        self.assertEqual([r["rank"] for r in routes], list(range(1, 7)))

    def test_top_n_cut_with_ties(self):
        orig = spain_trade.TOP_N
        spain_trade.TOP_N = 3
        try:
            routes = spain_trade.build_routes(self.zones, self.data)
        finally:
            spain_trade.TOP_N = orig
        # 200 t each for the other pairs: the tie goes by the zone ids.
        self.assertEqual([(r["a"], r["b"]) for r in routes], [("08", "13"), ("01", "08"), ("01", "09")])


# ------------------------------------------------------------------ check


def doc_fixture():
    data = eptmc.parse(workbook())
    world = world_fixture()
    zones = spain_trade.build_zones(world, data)
    return pick_all({
        "version": 1, "vintage": "EPTMC 2025", "year": 2025, "updated": "2026-11-16", "sources": ["eptmc"],
        "measure": "tons", "rule": "r",
        "modes": [{"id": "truck", "name": "Carretera"}], "commodities": {}, "national_k": {},
        "zones": sorted(zones.values(), key=lambda z: z["id"]), "routes": spain_trade.build_routes(zones, data),
    }, "es"), world


class CheckTest(unittest.TestCase):
    def run_check(self, doc, world):
        with tempfile.TemporaryDirectory() as tmp, using("es"):
            web = Path(tmp)
            (web / "world.json").write_text(json.dumps({"grid": world["grid"], "owner": world["owner"]}))
            (web / "trade.json").write_text(json.dumps(doc))
            return spain_trade.check(web)

    def test_good_passes(self):
        out = self.run_check(*doc_fixture())
        self.assertEqual({lv for lv, _ in out}, {"PASS"}, out)

    def test_violations_fail(self):
        def island(d):
            d["routes"][0]["b"] = "04"
        cases = {
            "rank": lambda d: d["routes"][0].update(rank=5),
            "duplicate pair": lambda d: d["routes"].append(dict(d["routes"][-1], rank=len(d["routes"]) + 1)),
            "island route": island,
            "directions": lambda d: d["routes"][0].update(ab_k=1.0),
            "haul": lambda d: d["routes"][0].update(haul_km=0),
            "order": lambda d: d["routes"][1].update(tons_k=1e6, ab_k=5e5, ba_k=5e5),
            "measure": lambda d: d.update(measure="value"),
            "anchor": lambda d: d["zones"][0]["anchor"].update(cell=-1),
            "anchor without flows": lambda d: d["zones"][3].update(anchor=d["zones"][0]["anchor"]),
            "no update date": lambda d: d.pop("updated"),
            "bad update date": lambda d: d.update(updated="16/11/2026"),
            "a path": lambda d: d["routes"][0].update(path=[1, 2]),
        }
        for what, change in cases.items():
            doc, world = doc_fixture()
            change(doc)
            with self.subTest(what):
                self.assertIn("FAIL", {lv for lv, _ in self.run_check(doc, world)})

    def test_us_map_is_not_checked_here(self):
        doc, world = doc_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "trade.json").write_text(json.dumps(doc))
            self.assertEqual(spain_trade.check(Path(tmp)), [])  # the active country is the US


WEB = COUNTRIES["es"].web_data_dir


@unittest.skipUnless((WEB / "trade.json").exists(), "Spain's trade.json is not built")
class BuiltFileTest(unittest.TestCase):
    def test_built_file(self):
        with using("es"):
            out = spain_trade.check(WEB)
        self.assertEqual({lv for lv, _ in out}, {"PASS"}, out)
        doc = json.loads((WEB / "trade.json").read_text())
        top = doc["routes"][0]
        self.assertEqual((top["a"], top["b"]), ("08", "13"))  # Castilla-La Mancha – Madrid
        self.assertEqual(len(doc["routes"]), spain_trade.TOP_N)
        zones = {z["id"]: z for z in doc["zones"]}
        self.assertTrue(all(zones[r["a"]]["significant"] and zones[r["b"]]["significant"] for r in doc["routes"]))
        en = json.loads((WEB / "trade.en.json").read_text())
        self.assertIn("rule", en)
        bad = copy.deepcopy(doc)
        bad["routes"][0]["rank"] = 2
        with tempfile.TemporaryDirectory() as tmp, using("es"):
            (Path(tmp) / "trade.json").write_text(json.dumps(bad))
            self.assertIn("FAIL", {lv for lv, _ in spain_trade.check(Path(tmp))})


if __name__ == "__main__":
    unittest.main()
