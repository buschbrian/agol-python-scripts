"""Actual ArcGIS regression for footprint-contact review flags."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ARCPY = importlib.util.find_spec("arcpy") is not None


@unittest.skipUnless(ARCPY, "ArcGIS Pro Python required")
class FootprintReviewArcGIS(unittest.TestCase):
    def test_flags_contact_without_mutating_candidates(self):
        import arcpy
        from canopy import qa

        root = Path(tempfile.mkdtemp(prefix="footprint_qa_"))
        try:
            gdb = str(root/"review.gdb")
            arcpy.management.CreateFileGDB(str(root), "review.gdb")
            sr = arcpy.SpatialReference(26912)
            points = str(Path(gdb)/"candidates")
            footprints = str(Path(gdb)/"footprints")
            arcpy.management.CreateFeatureclass(gdb, "candidates", "POINT", spatial_reference=sr)
            arcpy.management.AddField(points, "TREE_ID", "TEXT", field_length=36)
            arcpy.management.AddField(points, "CROWN_STATUS", "TEXT", field_length=30)
            with arcpy.da.InsertCursor(points, ["SHAPE@XY", "TREE_ID", "CROWN_STATUS"]) as cursor:
                cursor.insertRow([(500005, 4500005), "inside", "ESTIMATED"])
                cursor.insertRow([(500011, 4500005), "near", "CROWN_TOO_SMALL"])
                cursor.insertRow([(500020, 4500005), "far", "ESTIMATED"])
            arcpy.management.CreateFeatureclass(gdb, "footprints", "POLYGON", spatial_reference=sr)
            ring = [(500000,4500000),(500010,4500000),(500010,4500010),
                    (500000,4500010),(500000,4500000)]
            shape = arcpy.Polygon(arcpy.Array([arcpy.Point(x,y) for x,y in ring]), sr)
            with arcpy.da.InsertCursor(footprints, ["SHAPE@"]) as cursor:
                cursor.insertRow([shape])
            report = qa.flag_footprint_contact(points, footprints, gdb, 2, "reviewed")
            self.assertEqual(report["counts"],
                             {"ON_FOOTPRINT":1, "NEAR_FOOTPRINT":1, "OTHER":1})
            actual = {tree_id:(distance,label) for tree_id,distance,label in
                      arcpy.da.SearchCursor(report["output"], ["TREE_ID","NEAR_DIST","FOOT_QA"])}
            self.assertEqual(actual["inside"], (0, "ON_FOOTPRINT"))
            self.assertAlmostEqual(actual["near"][0], 1)
            self.assertEqual(actual["near"][1], "NEAR_FOOTPRINT")
            self.assertEqual(actual["far"], (-1, "OTHER"))
            self.assertNotIn("FOOT_QA", [f.name for f in arcpy.ListFields(points)])
            with self.assertRaises(FileExistsError):
                qa.flag_footprint_contact(points, footprints, gdb, 2, "reviewed")
            with self.assertRaises(ValueError):
                qa.flag_footprint_contact(points, footprints, gdb, 0, "invalid")
        finally:
            arcpy.management.ClearWorkspaceCache()
            shutil.rmtree(root, ignore_errors=True)
