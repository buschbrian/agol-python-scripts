import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import road_labels as rl

try:
    import arcpy
except ImportError:
    arcpy = None


def feature(cartocode="5", hwy="", rt="", a1="", a2="", fullname=""):
    return {"CARTOCODE": cartocode, "DOT_HWYNAM": hwy, "DOT_RTNAME": rt,
            "A1_NAME": a1, "A2_NAME": a2, "FULLNAME": fullname}


# Real attribute combinations sampled from UtahRoads, plus edge cases.
ROUTE_CASES = [
    (feature("1", "I-15", "0015N"), "I-15"),
    (feature("1", "I-215", "0215P"), "I-215"),
    (feature("3", "US 89A"), "US 89A"),
    (feature("4", "SR 152", "0152N"), "SR 152"),
    (feature("4", "", "0177P", "HWY 177"), "SR 177"),           # blank DOT_HWYNAM
    (feature("5", "", "0045P"), "SR 45"),
    (feature("3", "", "0189P"), "US 189"),                      # cartocode names the family
    (feature("5", "", "3201P", "SR-17", "HWY 17"), "SR 17"),    # not a real route number
    (feature("5", "", "", "NEW BINGHAM", "HWY 48"), "SR 48"),
    (feature("6", "", "0080PR11105", "HWY 283"), "SR 283"),     # ramp route id
    (feature("4", "", "", "HWY 152 NB"), "SR 152"),
    (feature("2", "", "", "HWY 40"), "US 40"),
    (feature("6", "", "", "PONY EXPRESS"), ""),
    (feature("5", None, None, None, None), ""),
]

NAME_CASES = [
    ("VANWINKLE EXPY NB", "Vanwinkle Expy"),
    ("WEST DAVIS SB HWY", "West Davis Hwy"),
    ("4500 S", "4500 S"),
    ("8TH AVE", "8th Ave"),
    ("HWY 189", ""),
    ("HWY 40 WB", ""),
    ("I-15 SB FWY", ""),
    ("STATE HWY", "State Hwy"),
    ("", ""),
    (None, ""),
]


class RouteKey(unittest.TestCase):
    def test_sampled_features(self):
        for attrs, expected in ROUTE_CASES:
            with self.subTest(attrs=attrs):
                self.assertEqual(rl.route_key(attrs), expected)

    def test_sort_puts_interstates_first_then_numeric(self):
        routes = ["SR 9", "US 6", "SR 152", "I-215", "I-15", "SR 85"]
        self.assertEqual(sorted(routes, key=rl.route_sort_key),
                         ["I-15", "I-215", "US 6", "SR 9", "SR 85", "SR 152"])

    def test_number_and_family(self):
        self.assertEqual((rl.route_family("I-215"), rl.route_number("I-215")), ("I", "215"))
        self.assertEqual((rl.route_family("US 89A"), rl.route_number("US 89A")), ("US", "89A"))


class StreetName(unittest.TestCase):
    def test_names(self):
        for fullname, expected in NAME_CASES:
            with self.subTest(fullname=fullname):
                self.assertEqual(rl.street_name(fullname), expected)

    def test_upper_case_option(self):
        self.assertEqual(rl.street_name("VANWINKLE EXPY NB", title_case=False), "VANWINKLE EXPY")


class ShieldData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(rl.SHIELD_DATA, encoding="utf-8") as f:
            cls.data = json.load(f)["series"]

    def test_every_series_has_the_same_routes(self):
        routes = [list(s["shields"]) for s in self.data.values()]
        self.assertTrue(all(r == routes[0] for r in routes))
        self.assertEqual(len(routes[0]), 270)

    def test_known_counts(self):
        shields = self.data["ddvut10i"]["shields"]
        self.assertEqual(sum(r.startswith("I-") for r in shields), 5)
        self.assertEqual(sum(r.startswith("SR ") for r in shields), 244)
        self.assertIn("US 89A", shields)
        self.assertIn("US 191 wide", shields)

    def test_layers_are_series_fonts_and_hex_colours(self):
        for series, entry in self.data.items():
            fonts = {series, series[:5] + "%02di" % (int(series[5:7]) + 1),
                     series[:5] + "%02di" % (int(series[5:7]) + 2)}
            for route, layers in entry["shields"].items():
                for font, code, colour in layers:
                    self.assertIn(font, fonts, (series, route))
                    self.assertTrue(32 <= code < 256)
                    self.assertRegex(colour, r"^#[0-9a-f]{6}$")

    def test_interstate_colours(self):
        colours = [c for _, _, c in self.data["ddvut10i"]["shields"]["I-15"]]
        self.assertEqual(colours, ["#ff2b06", "#1922fb", "#ffffff", "#000000"])


class MutcdShieldData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shields = rl.load_mutcd()

    def test_six_templates_at_sign_proportions(self):
        self.assertEqual(sorted(self.shields), ["I-2", "I-3", "SR-2", "SR-3", "US-2", "US-3"])
        for key, shield in self.shields.items():
            ratio = shield["width"] / shield["height"]
            self.assertAlmostEqual(ratio, 1.25 if key.endswith("3") else 1.0, places=2, msg=key)

    def test_numerals(self):
        for key, shield in self.shields.items():
            n = shield["number"]
            three = key.endswith("3")
            # The signs' own numerals: Series C only where three digits must fit.
            self.assertEqual(n["template_font"], "Roadgeek 2005 Series %s" % ("C" if three else "D"), key)
            # The map's: Bahnschrift SemiBold, semi-condensed for three digits.
            self.assertEqual((n["font"], n["axes"]), ("Bahnschrift", {"wght": 600, "wdth": 87.5 if three else 100}), key)
            self.assertAlmostEqual(n["x"], shield["width"] / 2, delta=1, msg=key)

    def test_numerals_keep_the_sign_designs_centre(self):
        for key, shield in self.shields.items():
            n = shield["number"]
            sign = n["template_baseline"] + 0.571 / 2 * n["template_size"]
            self.assertAlmostEqual(n["baseline"] + n["figure_height"] / 2 * n["size"], sign, delta=1, msg=key)

    def test_geometry_is_curve_rings_with_outer_rings_clockwise(self):
        from build_shields import flatten, signed_area
        for key, shield in self.shields.items():
            self.assertTrue(shield["graphics"], key)
            for g in shield["graphics"]:
                self.assertRegex(g["fill"] or g["stroke"], r"^#[0-9a-f]{6}$")
                self.assertLess(signed_area(flatten(g["curveRings"][0])), 0, key)

    def test_numerals_are_fitted_but_never_below_the_type_floor(self):
        # The layout standard's 6.5 pt floor is Source Sans 3, whose figures
        # are 0.66 em: 4.29 pt tall. Compare figure heights, not point sizes.
        for key, shield in self.shields.items():
            n = shield["number"]
            self.assertIn(n["margin"], (0.05, 0.075), key)
            family = key.split("-")[0]
            figures = n["size"] * n["figure_height"] * rl.SHIELDS[family]["height"] / shield["height"]
            self.assertGreaterEqual(figures, 6.5 * 0.66, "%s figures %.2f pt" % (key, figures))

    def test_interstate_colours(self):
        fills = {g["fill"] for g in self.shields["I-2"]["graphics"]}
        self.assertTrue({"#003f87", "#af1e2d", "#ffffff"} <= fills)


class MutcdClasses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classes, cls.sources = rl.build_label_classes(
            ["SR 152", "I-15", "SR 85", "US 89A", "I-215", "SR 85"], "mutcd")
        cls.by_name = {c["name"]: c for c in cls.classes}

    def test_one_class_per_network_and_digit_count(self):
        self.assertEqual([c["name"] for c in self.classes][:5],
                         ["Interstate shields, 1-2 digits", "Interstate shields, 3 digits",
                          "US route shields, 3 digits", "State route shields, 1-2 digits",
                          "State route shields, 3 digits"])
        self.assertEqual(set(self.sources.values()), {"MUTCD"})

    def test_number_is_live_bahnschrift_text_over_a_vector_shield(self):
        text = self.by_name["State route shields, 3 digits"]["textSymbol"]["symbol"]
        self.assertEqual(text["fontFamilyName"], "Bahnschrift")
        self.assertEqual({v["tagName"]: v["value"] for v in text["fontVariationSettings"]},
                         {"wght": 600, "wdth": 87.5})
        marker = text["callout"]["pointSymbol"]["symbolLayers"][0]
        self.assertEqual(marker["type"], "CIMVectorMarker")
        self.assertEqual(marker["size"], rl.SHIELDS["SR"]["height"])
        self.assertEqual(marker["frame"]["xmax"], 750)

    def test_expression_and_filter(self):
        cls = self.by_name["Interstate shields, 1-2 digits"]
        self.assertIn("DOT_HWYNAM LIKE 'I-%'", cls["whereClause"])
        self.assertTrue(cls["expression"].endswith(
            "if (Left(k, 2) != 'I-') { return ''; }\nvar n = Mid(k, 2);\nreturn IIf(Count(n) <= 2, n, '');"))

    def test_shield_is_offset_so_the_number_sits_on_the_template_baseline(self):
        shield = rl.load_mutcd()["SR-2"]
        marker = rl.vector_shield(shield, 16)
        n = shield["number"]
        centre = n["baseline"] + n["figure_height"] * n["size"] / 2
        self.assertAlmostEqual(marker["offsetY"], (300 - centre) * 16 / 600)


class DdvClasses(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shields = rl.load_shields("ddvut10i")
        cls.classes, cls.sources = rl.build_label_classes(
            ["SR 152", "I-15", "SR 85", "US 89", "SR 152"], "ddv")
        cls.by_name = {c["name"]: c for c in cls.classes}

    def test_one_class_per_route_then_names(self):
        self.assertEqual([c["name"] for c in self.classes],
                         ["Shield I-15", "Shield US 89", "Shield SR 85", "Shield SR 152",
                          "Highway names", "Major streets", "Local streets",
                          "Unpaved and 4WD roads"])

    def test_sources(self):
        self.assertEqual(self.sources, {"I-15": "DDV", "US 89": "DDV", "SR 152": "DDV",
                                        "SR 85": "beehive fallback"})

    def test_ddv_shield_is_the_callout_and_text_is_transparent(self):
        text = self.by_name["Shield SR 152"]["textSymbol"]["symbol"]
        self.assertEqual(text["symbol"]["symbolLayers"][0]["color"]["values"][3], 0)
        layers = text["callout"]["pointSymbol"]["symbolLayers"]
        ddv = self.shields["SR 152"]
        # CIM order is top first; DDV order is bottom first.
        self.assertEqual([(l["fontFamilyName"], l["characterIndex"]) for l in layers],
                         [(f, c) for f, c, _ in reversed(ddv)])

    def test_fallback_number_is_visible_roadgeek(self):
        text = self.by_name["Shield SR 85"]["textSymbol"]["symbol"]
        self.assertEqual(text["fontFamilyName"], rl.SERIES_D)
        self.assertEqual(text["symbol"]["symbolLayers"][0]["color"]["values"][3], 100)

    def test_shield_filters(self):
        cls = self.by_name["Shield SR 152"]
        self.assertIn("DOT_HWYNAM = 'SR 152'", cls["whereClause"])
        self.assertTrue(cls["expression"].endswith("return IIf(routeKey() == 'SR 152', '152', '');"))

    def test_spacing_is_in_points_at_reference_scale(self):
        placement = self.by_name["Shield I-15"]["maplexLabelPlacementProperties"]
        self.assertEqual(placement["minimumRepetitionInterval"],
                         rl.SHIELDS["I"]["repeat_in"] * 72)
        self.assertEqual(placement["repetitionIntervalUnit"], "Point")

    def test_names_have_tight_word_spacing_and_standard_halos(self):
        text = self.by_name["Local streets"]["textSymbol"]["symbol"]
        self.assertEqual(text["wordSpacing"], rl.NAME_WORD_SPACING)
        self.assertEqual(text["haloSize"], 0.75)
        self.assertEqual(self.by_name["Major streets"]["textSymbol"]["symbol"]["haloSize"], 1.0)

    def test_names_sit_beside_the_line(self):
        placement = self.by_name["Local streets"]["maplexLabelPlacementProperties"]
        self.assertEqual(placement["linePlacementMethod"], "OffsetCurvedFromLine")
        self.assertFalse(placement["canOverrunFeature"])
        self.assertEqual(self.by_name["Local streets"]["whereClause"], "CARTOCODE IN ('11')")

    def test_no_shield_for_unknown_family(self):
        cls, source = rl.ddv_shield_class("US 999", self.shields)
        self.assertIsNone(cls)
        self.assertEqual(source, "no shield")

    def test_us_wide(self):
        wide = rl.ddv_layers("US 191", self.shields, us_wide=True)
        self.assertEqual(wide, self.shields["US 191 wide"])
        self.assertEqual(rl.ddv_layers("US 89", self.shields, us_wide=True), self.shields["US 89"])


class Fonts(unittest.TestCase):
    def test_stems(self):
        self.assertEqual(rl.font_file_stem("ddvut10i"), "DDVUT10I")
        self.assertEqual(rl.font_file_stem(rl.SERIES_D), "RG2014D")
        self.assertEqual(rl.font_family("RG2014EM"), "Roadgeek 2014 Series EM")
        self.assertEqual(rl.font_family("DDVUT16I"), "ddvut16i")

    def test_required(self):
        self.assertEqual(rl.required_font_files("mutcd"), {"RG2014C", "RG2014D", "RG2014E", "BAHNSCHRIFT"})
        self.assertEqual(rl.required_font_files("ddv", "ddvut10i"),
                         {"DDVUT10I", "DDVUT11I", "DDVUT12I", "DDVUT16I",
                          "RG2014C", "RG2014D", "RG2014E"})


class VectorTileStyle(unittest.TestCase):
    def test_names_get_a_text_offset(self):
        import tempfile
        import zipfile

        style = {"layers": [
            {"id": "Roads/label/Local streets", "type": "symbol", "layout": {}},
            {"id": "Roads/label/State route shields, 1-2 digits", "type": "symbol", "layout": {}},
            {"id": "Roads", "type": "line"}]}
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "t.vtpk")
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("p12/resources/styles/root.json", json.dumps(style))
                z.writestr("p12/tile/L00/R0000C0000.bundle", b"tiles")
            self.assertEqual(rl.offset_vector_tile_names(path), 1)
            with zipfile.ZipFile(path) as z:
                layers = json.loads(z.read("p12/resources/styles/root.json"))["layers"]
                self.assertEqual(z.read("p12/tile/L00/R0000C0000.bundle"), b"tiles")
        local = next(s for s in rl.NAME_CLASSES if s["name"] == "Local streets")
        self.assertEqual(layers[0]["layout"]["text-offset"], [0, rl.name_text_offset(local)])
        self.assertNotIn("text-offset", layers[1]["layout"])


@unittest.skipIf(arcpy is None, "needs ArcGIS Pro's Python")
class FontsLoaded(unittest.TestCase):
    """The fonts must be loaded, not only installed, or Pro silently draws Arial."""

    def test_windows_lists_arial(self):
        self.assertIn("arial", rl.loaded_font_families())

    def test_required_fonts_are_loaded(self):
        self.assertEqual(rl.ensure_fonts_loaded("mutcd"), set())


@unittest.skipIf(arcpy is None, "needs ArcGIS Pro's Python")
class ArcadeMatchesPython(unittest.TestCase):
    """Runs the label Arcade through Calculate Field and compares with Python."""

    def test_route_key_and_names(self):
        fc = arcpy.management.CreateFeatureclass("memory", "roads_arcade", "POLYLINE")[0]
        for name, length in [("CARTOCODE", 10), ("DOT_HWYNAM", 15), ("DOT_RTNAME", 11),
                             ("A1_NAME", 40), ("A2_NAME", 40), ("FULLNAME", 50),
                             ("K", 20), ("N", 80)]:
            arcpy.management.AddField(fc, name, "TEXT", field_length=length)
        fields = ["CARTOCODE", "DOT_HWYNAM", "DOT_RTNAME", "A1_NAME", "A2_NAME", "FULLNAME"]
        names = [n for n, _ in NAME_CASES]
        rows = [dict(attrs, FULLNAME=names[i % len(names)]) for i, (attrs, _) in enumerate(ROUTE_CASES)]
        with arcpy.da.InsertCursor(fc, fields) as cursor:
            for row in rows:
                cursor.insertRow([row[f] for f in fields])
        try:
            arcpy.management.CalculateField(fc, "K", rl.ROUTE_KEY_ARCADE + "\nreturn routeKey();", "ARCADE")
            arcpy.management.CalculateField(fc, "N", rl.name_arcade(), "ARCADE")
            with arcpy.da.SearchCursor(fc, fields + ["K", "N"]) as cursor:
                for values in cursor:
                    attrs = dict(zip(fields, values))
                    self.assertEqual(values[-2] or "", rl.route_key(attrs), attrs)
                    self.assertEqual(values[-1] or "", rl.street_name(attrs["FULLNAME"]), attrs)

            # Each MUTCD shield class returns the number only for its own
            # network and digit count.
            shields = rl.load_mutcd()
            for family in rl.MUTCD_PREFIX:
                for digits in (2, 3):
                    cls = rl.mutcd_shield_class(family, digits, shields["%s-%d" % (family, digits)])
                    arcpy.management.CalculateField(fc, "K", cls["expression"], "ARCADE")
                    with arcpy.da.SearchCursor(fc, fields + ["K"]) as cursor:
                        for values in cursor:
                            route = rl.route_key(dict(zip(fields, values)))
                            mine = route and rl.route_family(route) == family and rl.shield_digits(route) == digits
                            self.assertEqual(values[-1] or "", rl.route_number(route) if mine else "",
                                             (cls["name"], route))
        finally:
            arcpy.management.Delete(fc)


if __name__ == "__main__":
    unittest.main()
