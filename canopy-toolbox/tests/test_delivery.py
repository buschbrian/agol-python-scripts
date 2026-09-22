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

    # Coverage: the two fixture tiles span x 500000-500020, y 4500000-4500010.

    def rectangle(self, extent, spatial_reference=None):
        xmin, ymin, xmax, ymax = extent
        corners = [(xmin, ymin), (xmin, ymax), (xmax, ymax), (xmax, ymin), (xmin, ymin)]
        return arcpy.Polygon(arcpy.Array([arcpy.Point(x, y) for x, y in corners]), spatial_reference or self.sr)

    def polygons(self, name, shapes, field=None, spatial_reference=None):
        """A feature class of polygons, optionally carrying one text value each."""
        gdb = str(self.case/(name+".gdb"))
        arcpy.management.CreateFileGDB(str(self.case), name+".gdb")
        path = str(Path(gdb)/"polygons")
        arcpy.management.CreateFeatureclass(gdb, "polygons", "POLYGON",
                                            spatial_reference=spatial_reference or self.sr)
        columns = ["SHAPE@"]
        if field:
            arcpy.management.AddField(path, field, "TEXT", field_length=32)
            columns.append(field)
        with arcpy.da.InsertCursor(path, columns) as cursor:
            for shape, value in shapes:
                cursor.insertRow([shape] + ([value] if field else []))
        return path

    def boundary(self):
        """200 m² straddling both tiles and 5 m past the second: 150 m² is covered."""
        return self.polygons("city", [(self.rectangle((500005, 4500000, 500025, 4500010)), None)])

    def tile_index(self, spatial_reference=None):
        extents = {"T1": (500000, 4500000, 500010, 4500010), "T2": (500010, 4500000, 500020, 4500010),
                   "T3": (500020, 4500000, 500030, 4500010), "T4": (500040, 4500000, 500050, 4500010)}
        return self.polygons("index", [(self.rectangle(e, spatial_reference), n) for n, e in extents.items()],
                             "Tile_Name", spatial_reference)

    def test_boundary_coverage_is_the_covered_share_of_its_area(self):
        report = delivery.index(self.source, self.case/"cover", boundary=self.boundary())
        coverage = report["coverage"]
        self.assertAlmostEqual(coverage["boundary_m2"], 200)
        self.assertAlmostEqual(coverage["covered_m2"], 150)
        self.assertAlmostEqual(coverage["covered_pct"], 75)
        self.assertEqual(coverage["outside"], [])
        self.assertIsNone(coverage["projected_from"])

    def test_tile_index_reports_the_uncovered_tile_by_boundary_area(self):
        report = delivery.index(self.source, self.case/"tiles", boundary=self.boundary(),
                                tile_index=self.tile_index())
        tiles = report["coverage"]["tile_index"]
        self.assertEqual(tiles["touching"], 3)  # T4 is clear of the boundary
        self.assertEqual(tiles["in_hand"], 2)
        self.assertEqual([m["tile"] for m in tiles["missing"]], ["T3"])
        self.assertAlmostEqual(tiles["missing"][0]["boundary_m2"], 50)
        self.assertAlmostEqual(tiles["missing"][0]["share_pct"], 25)

    def test_boundary_in_web_mercator_is_projected_with_a_transformation(self):
        mercator = arcpy.SpatialReference(3857)
        native = self.rectangle((500005, 4500000, 500025, 4500010))
        transformation = arcpy.ListTransformations(self.sr, mercator, native.extent)[0]
        path = self.polygons("mercator", [(native.projectAs(mercator, transformation), None)],
                             spatial_reference=mercator)
        coverage = delivery.index(self.source, self.case/"projected", boundary=path)["coverage"]
        self.assertIn("3857", coverage["projected_from"])
        self.assertTrue(coverage["transformation"])
        self.assertAlmostEqual(coverage["covered_pct"], 75, delta=1)

    def test_tile_index_in_another_reference_is_refused_before_any_output(self):
        index = self.tile_index(arcpy.SpatialReference(26912))
        target = self.case/"wrong_index"
        with self.assertRaises(ValueError):
            delivery.index(self.source, target, boundary=self.boundary(), tile_index=index)
        self.assertFalse(target.exists())

    def test_tile_index_without_a_boundary_is_refused(self):
        with self.assertRaises(ValueError):
            delivery.index(self.source, self.case/"no_boundary", tile_index=self.tile_index())

    def test_record_and_facts_are_written_without_filesystem_paths(self):
        report = delivery.index(self.source, self.case/"record", boundary=self.boundary(),
                                tile_index=self.tile_index(), label="fixture epoch")
        acquisition = Path(report["record"]).read_text(encoding="utf-8")
        facts = Path(report["facts"]).read_text(encoding="utf-8")
        self.assertIn("12TVL0001", acquisition)
        # The folder is kept exactly as passed; resolved per-file paths never appear.
        self.assertNotIn(".las", acquisition)
        self.assertIn("# Acquisition facts — fixture epoch", facts)
        self.assertIn("| T3 |", facts)
