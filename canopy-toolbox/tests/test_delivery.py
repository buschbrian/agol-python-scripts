"""Delivery-index fixtures. Skipped in plain Python because delivery imports arcpy."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ARCPY = importlib.util.find_spec("arcpy") is not None

WKT = ('PROJCS["NAD83(2011) / UTM zone 12N",GEOGCS["NAD83(2011)",DATUM["NAD83_National_Spatial_'
       'Reference_System_2011",SPHEROID["GRS 1980",6378137,298.257222101]],PRIMEM["Greenwich",0],'
       'UNIT["degree",0.0174532925199433]],PROJECTION["Transverse_Mercator"],'
       'PARAMETER["latitude_of_origin",0],PARAMETER["central_meridian",-111],'
       'PARAMETER["scale_factor",0.9996],PARAMETER["false_easting",500000],'
       'PARAMETER["false_northing",0],UNIT["meter",1],AUTHORITY["EPSG","6341"]]')


@unittest.skipUnless(ARCPY, "ArcGIS Pro Python required")
class FlightSummary(unittest.TestCase):
    """Pure date reduction; separated from geometry so the rules are readable."""

    @classmethod
    def setUpClass(cls):
        global delivery
        from canopy import delivery

    def test_no_swaths_leaves_every_date_field_null(self):
        result = delivery.flight_summary([])
        self.assertIsNone(result["FLIGHT_DATES"])
        self.assertIsNone(result["FLIGHT_FIRST"])
        self.assertIsNone(result["FLIGHT_LAST"])
        self.assertEqual(result["SWATH_COUNT"], 0)

    def test_repeated_dates_collapse_but_swath_count_does_not(self):
        result = delivery.flight_summary(["2023-11-02", "2023-11-02", "2023-10-07"])
        self.assertEqual(result["FLIGHT_DATES"], "2023-10-07;2023-11-02")
        self.assertEqual(result["FLIGHT_FIRST"], "2023-10-07")
        self.assertEqual(result["FLIGHT_LAST"], "2023-11-02")
        self.assertEqual(result["SWATH_COUNT"], 3)

    def test_blank_and_missing_dates_are_dropped_not_counted_as_a_date(self):
        result = delivery.flight_summary([None, "  ", "2023-10-07"])
        self.assertEqual(result["FLIGHT_DATES"], "2023-10-07")
        self.assertEqual(result["SWATH_COUNT"], 3)

    def test_too_many_distinct_dates_fail_rather_than_truncate(self):
        with self.assertRaises(ValueError):
            delivery.flight_summary([f"2023-10-{day:02d}" for day in range(1, 30)])


@unittest.skipUnless(ARCPY, "ArcGIS Pro Python required")
class DeliveryIndex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global arcpy, delivery
        import arcpy
        from canopy import delivery
        cls.root = Path(tempfile.mkdtemp(prefix="canopy_delivery_"))
        cls.sr = arcpy.SpatialReference(6341)
        arcpy.env.scratchWorkspace = str(cls.root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root, ignore_errors=True)

    def setUp(self):
        from tests.las_fixture import write_las
        self.case = Path(tempfile.mkdtemp(dir=self.root))
        self.source = self.case/"delivery"
        self.source.mkdir()
        write_las(self.source/"12TVL0001.las", wkt=WKT)
        write_las(self.source/"12TVL0002.las", wkt=WKT, origin=(500010, 4500000))

    def swath_index(self, name, extent, date, spatial_reference=None):
        """One rectangular swath polygon carrying a date."""
        gdb = str(self.case/(name+".gdb"))
        arcpy.management.CreateFileGDB(str(self.case), name+".gdb")
        path = str(Path(gdb)/"swaths")
        arcpy.management.CreateFeatureclass(gdb, "swaths", "POLYGON",
                                            spatial_reference=spatial_reference or self.sr)
        arcpy.management.AddField(path, "DATE_D", "TEXT", field_length=32)
        xmin, ymin, xmax, ymax = extent
        corners = [(xmin, ymin), (xmin, ymax), (xmax, ymax), (xmax, ymin), (xmin, ymin)]
        polygon = arcpy.Polygon(arcpy.Array([arcpy.Point(x, y) for x, y in corners]),
                                spatial_reference or self.sr)
        with arcpy.da.InsertCursor(path, ["SHAPE@", "DATE_D"]) as cursor:
            cursor.insertRow([polygon, date])
        return path

    def rows(self, feature_class, fields):
        return {row[0]: row[1:] for row in arcpy.da.SearchCursor(feature_class, ["TILE"]+fields)}

    def test_headers_alone_produce_one_row_per_tile(self):
        report = delivery.index(self.source, self.case/"index")
        self.assertEqual(report["file_count"], 2)
        self.assertIsNone(report["swath_index"])
        rows = self.rows(report["feature_class"], ["BOUNDS_KM2", "RETURNS_M2", "FLIGHT_DATES", "SWATH_COUNT"])
        self.assertEqual(set(rows), {"12TVL0001", "12TVL0002"})
        for area, density, dates, swaths in rows.values():
            self.assertAlmostEqual(area, 100/1e6)
            self.assertAlmostEqual(density, 191/100)
            self.assertIsNone(dates)
            self.assertIsNone(swaths)
        self.assertTrue(Path(report["layer_file"]).is_file())

    def test_only_intersecting_swaths_date_a_tile(self):
        swaths = self.swath_index("one", (500000, 4500000, 500009, 4500010), "2023-11-02")
        report = delivery.index(self.source, self.case/"dated", swaths)
        self.assertEqual(report["swath_index"]["swaths"], 1)
        rows = self.rows(report["feature_class"], ["FLIGHT_FIRST", "FLIGHT_LAST", "FLIGHT_DATES", "SWATH_COUNT"])
        self.assertEqual(rows["12TVL0001"], ("2023-11-02", "2023-11-02", "2023-11-02", 1))
        self.assertEqual(rows["12TVL0002"], (None, None, None, 0))

    def test_dates_also_reach_the_json_report(self):
        swaths = self.swath_index("two", (500000, 4500000, 500009, 4500010), "2023-11-02")
        report = delivery.index(self.source, self.case/"json", swaths)
        first = next(row for row in report["files"] if row["path"].endswith("12TVL0001.las"))
        second = next(row for row in report["files"] if row["path"].endswith("12TVL0002.las"))
        self.assertEqual(first["FLIGHT_DATES"], "2023-11-02")
        self.assertIsNone(second["FLIGHT_DATES"])

    def test_swath_index_in_another_reference_is_refused(self):
        swaths = self.swath_index("wrong", (-112, 40.6, -111.9, 40.7), "2023-11-02",
                                  arcpy.SpatialReference(4326))
        with self.assertRaises(ValueError):
            delivery.index(self.source, self.case/"mismatch", swaths)

    def test_missing_date_field_is_refused_before_any_output(self):
        swaths = self.swath_index("nodate", (500000, 4500000, 500009, 4500010), "2023-11-02")
        arcpy.management.DeleteField(swaths, "DATE_D")
        target = self.case/"nofield"
        with self.assertRaises(ValueError):
            delivery.index(self.source, target, swaths)
        self.assertFalse(target.exists())

    def test_existing_output_and_in_place_output_are_refused(self):
        delivery.index(self.source, self.case/"first")
        with self.assertRaises((ValueError, FileExistsError)):
            delivery.index(self.source, self.case/"first")
        with self.assertRaises(ValueError):
            delivery.index(self.source, self.source/"inside")

    def test_delivery_without_a_coordinate_reference_is_refused(self):
        from tests.las_fixture import write_las
        bare = self.case/"bare"
        bare.mkdir()
        write_las(bare/"12TVL0003.las")
        with self.assertRaises(ValueError):
            delivery.index(bare, self.case/"bare_index")

    def test_mixed_coordinate_references_are_refused(self):
        from tests.las_fixture import write_las
        write_las(self.source/"12TVL0004.las", wkt=WKT.replace("6341", "26912"))
        with self.assertRaises(ValueError):
            delivery.index(self.source, self.case/"mixed")
