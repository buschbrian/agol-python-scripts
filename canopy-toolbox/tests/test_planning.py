"""Numerical and real ArcGIS fixtures for the planning bundle."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

try:
    import numpy as np
    from canopy import planning_metrics
    SCIENTIFIC = True
except ImportError:
    SCIENTIFIC = False

ARCPY = importlib.util.find_spec("arcpy") is not None


@unittest.skipUnless(SCIENTIFIC, "NumPy and SciPy required")
class PlanningMetrics(unittest.TestCase):
    def test_paired_heights_preserve_nodata_and_negative_values(self):
        result = planning_metrics.height_summary(
            [[110., np.nan, 99., 200.]], [[100., 100., 100., np.nan]], [[True]*4])
        self.assertEqual(result["GRID_CELLS"], 4)
        self.assertEqual(result["ROOF_CELLS"], 2)
        self.assertEqual(result["ROOF_COV_PCT"], 50)
        self.assertEqual(result["HEIGHT_P50_M"], 4.5)
        self.assertEqual(result["NEG_H_CELLS"], 1)
        self.assertEqual(result["HEIGHT_MAX_M"], 10)

    def test_no_roof_and_no_cells_have_null_heights(self):
        missing = planning_metrics.height_summary([[np.nan]], [[100]], [[True]])
        tiny = planning_metrics.height_summary([[110]], [[100]], [[False]])
        self.assertEqual(missing["ROOF_COV_PCT"], 0)
        self.assertIsNone(missing["HEIGHT_P50_M"])
        self.assertIsNone(tiny["ROOF_COV_PCT"])
        self.assertIsNone(tiny["HEIGHT_MAX_M"])

    def test_boundary_connection_traces_east_and_stops_at_cycle(self):
        valid = np.ones((7, 7), dtype=bool)
        direction = np.zeros((7, 7), dtype=int)
        direction[3, :5] = 1
        direction[3, 5] = 16
        marked = planning_metrics.boundary_influence(direction, valid)
        self.assertTrue(marked[3, 1:6].all())
        self.assertFalse(marked[2, 2])

    def test_nodata_neighbors_seed_downstream_uncertainty(self):
        valid = np.ones((9, 9), dtype=bool)
        valid[4, 4] = False
        direction = np.zeros((9, 9), dtype=int)
        direction[4, 5:7] = 1
        marked = planning_metrics.boundary_influence(direction, valid)
        self.assertTrue(marked[4, 7])
        self.assertFalse(marked[4, 4])
        self.assertFalse(marked[2, 2])


@unittest.skipUnless(ARCPY, "ArcGIS Pro Python required")
class PlanningArcGIS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global arcpy, planning
        import arcpy
        from canopy import planning
        cls.root = Path(tempfile.mkdtemp(prefix="planning_tests_"))
        cls.gdb = str(cls.root/"tests.gdb")
        cls.sr = arcpy.SpatialReference(26912)
        arcpy.management.CreateFileGDB(str(cls.root), "tests.gdb")
        arcpy.env.parallelProcessingFactor = "0"
        arcpy.env.scratchWorkspace = str(cls.root)
        arcpy.CheckOutExtension("Spatial")
        arcpy.CheckOutExtension("3D")

    @classmethod
    def tearDownClass(cls):
        arcpy.CheckInExtension("Spatial")
        arcpy.CheckInExtension("3D")
        arcpy.management.ClearWorkspaceCache()
        shutil.rmtree(cls.root, ignore_errors=True)

    def raster(self, name, data):
        path = str(self.root/(name+".tif"))
        array = np.asarray(data, dtype=np.float32)
        array = np.where(np.isfinite(array), array, -9999)
        arcpy.NumPyArrayToRaster(array, arcpy.Point(500000, 4500000), 1, 1, -9999).save(path)
        arcpy.management.DefineProjection(path, self.sr)
        return path

    def test_terrain_plane_pit_area_units_and_source_preservation(self):
        data = np.tile(100 + .1*np.arange(31), (31, 1))
        data[15, 15] -= 2
        dtm = self.raster("plane", data)
        before = planning._array(dtm).copy()
        with self.assertRaises(ValueError):
            planning.terrain(dtm, self.root/"bad_units")
        outputs = planning.terrain(dtm, self.root/"terrain", 2, 3, 10, 1, "metres")
        slope = planning._array(outputs["slope_degrees"])
        self.assertAlmostEqual(float(np.median(slope[4:10, 4:10])), 5.7106, delta=.05)
        depth = planning._array(outputs["depression_fill_depth_m"])
        self.assertGreater(depth[15, 15], 1.5)
        area = planning._array(outputs["contributing_area_m2"])
        accumulation = planning._array(outputs["flow_accumulation_cells"])
        np.testing.assert_allclose(area, accumulation + 1)
        np.testing.assert_array_equal(before, planning._array(dtm))
        complete = planning._array(outputs["terrain_neighborhood_complete"])
        self.assertEqual(complete[0, 0], 0)
        self.assertEqual(complete[10, 10], 1)
        with self.assertRaises(FileExistsError):
            planning.terrain(dtm, self.root/"terrain", z_unit="metres")

    def test_footprint_overlap_missing_tiny_outside_and_partial(self):
        dtm = self.raster("ground", np.full((8, 8), 100.))
        roof = np.full((8, 8), np.nan)
        roof[4:, :4] = 110.
        roof_path = self.raster("roof", roof)
        footprints = str(Path(self.gdb)/"footprints")
        arcpy.management.CreateFeatureclass(self.gdb, "footprints", "POLYGON", spatial_reference=self.sr)
        arcpy.management.AddField(footprints, "KEY", "TEXT", field_length=30)
        entries = [("full",0,0,4,4), ("overlap",0,0,2,2), ("missing",4,4,4,4),
                   ("outside",20,20,2,2), ("tiny",.05,.05,.1,.1), ("partial",-2,0,4,4)]
        with arcpy.da.InsertCursor(footprints, ["KEY", "SHAPE@"]) as cursor:
            for key,x,y,w,h in entries:
                points = [(x,y), (x+w,y), (x+w,y+h), (x,y+h), (x,y)]
                geometry = arcpy.Polygon(arcpy.Array([arcpy.Point(500000+a,4500000+b) for a,b in points]),self.sr)
                cursor.insertRow([key, geometry])
        target, rows = planning.building_heights(footprints, "KEY", roof_path, dtm, self.gdb)
        values = {r["source_id"]:r for r in rows}
        self.assertEqual(values["full"]["HEIGHT_P50_M"], 10)
        self.assertEqual(values["full"]["ROOF_COV_PCT"], 100)
        self.assertEqual(values["overlap"]["ROOF_CELLS"], 4)
        self.assertIsNone(values["missing"]["HEIGHT_P50_M"])
        self.assertIn("OUTSIDE_AOI", values["outside"]["HEIGHT_STATUS"])
        self.assertIn("NO_CELL_CENTERS", values["tiny"]["HEIGHT_STATUS"])
        self.assertAlmostEqual(values["partial"]["AOI_PCT"], 50)
        self.assertEqual(values["partial"]["PARTIAL_AOI"], 1)
        self.assertNotIn("HEIGHT_P50_M", [f.name for f in arcpy.ListFields(footprints)])
        self.assertEqual(int(arcpy.management.GetCount(target)[0]), len(entries))

    def test_end_to_end_prepared_las_bundle(self):
        import json
        from tests.las_fixture import write_las
        prepared = self.root/"prepared"
        prepared.mkdir()
        las = str(prepared/"points.las")
        write_las(las)
        lasd = str(prepared/"prepared.lasd")
        arcpy.management.CreateLasDataset(las, lasd, spatial_reference=self.sr, compute_stats="COMPUTE_STATS")
        (prepared/"preparation.json").write_text(json.dumps({
            "status":"complete", "source_id":"fixture", "working_lasd":lasd,
            "extent":[500000,4500000,500010,4500010]}),encoding="utf8")
        state = planning.build(lasd, self.root/"bundle", [500000,4500000,500010,4500010],
                               cell_size=1, neighborhood=1, tpi_radius=2, drainage_area=10,
                               contour_interval=2, z_unit="metres")
        self.assertEqual(state["status"], "complete")
        self.assertIn("surface_height_m", state["outputs"])
        self.assertIn("ground_distance_m", state["outputs"])
        self.assertIn("flow_boundary_influence", state["outputs"])

