"""End-to-end reconcile-buildings fixture on a synthetic LAS 1.4 format-6 tile (ArcGIS Pro only)."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import tempfile
import unittest

ARCPY = importlib.util.find_spec("arcpy") is not None
X0, Y0 = 500000.0, 4500000.0


def write_las14(path, points, wkt):
    """points: (x, y, z, class, return_number, number_of_returns) relative to X0, Y0."""
    vlr = wkt.encode("utf-8") + b"\0"
    vlr_header = struct.pack("<H16sHH32s", 0, b"LASF_Projection", 2112, len(vlr), b"WKT")
    header = bytearray(375)
    header[:4] = b"LASF"
    struct.pack_into("<H", header, 6, 16)                      # WKT global encoding bit
    header[24:26] = bytes([1, 4])
    struct.pack_into("<HHHI", header, 90, 1, 2026, 375, 375 + len(vlr_header) + len(vlr))
    struct.pack_into("<I", header, 100, 1)
    struct.pack_into("<BHI", header, 104, 6, 30, 0)
    struct.pack_into("<3d", header, 131, .01, .01, .01)
    struct.pack_into("<3d", header, 155, X0, Y0, 0)
    xs, ys, zs = [p[0] for p in points], [p[1] for p in points], [p[2] for p in points]
    struct.pack_into("<6d", header, 179, X0 + max(xs), X0 + min(xs), Y0 + max(ys), Y0 + min(ys), max(zs), min(zs))
    struct.pack_into("<Q", header, 247, len(points))
    with open(path, "wb") as handle:
        handle.write(header); handle.write(vlr_header); handle.write(vlr)
        for x, y, z, code, number, count in points:
            record = bytearray(30)
            struct.pack_into("<iii", record, 0, round(x*100), round(y*100), round(z*100))
            record[14] = number | (count << 4)
            record[16] = code
            handle.write(record)


def scene():
    """Ground at 100 m; A: class-6 roof with a footprint; B: class-5 'roof' with a footprint
    (missed); C: class-6 roof with no footprint; D: a footprint with nothing above ground."""
    points = []
    step = .5
    for i in range(0, 121):
        for j in range(0, 121):
            points.append((i*step, j*step, 100.0, 2, 1, 1))
    def roof(x0, y0, x1, y1, z, code):
        x = x0 + .125
        while x < x1:
            y = y0 + .125
            while y < y1:
                points.append((x, y, z, code, 1, 1))
                y += .25
            x += .25
    roof(10, 10, 20, 20, 106, 6)      # A
    roof(35, 10, 43, 18, 105, 5)      # B, missed by the classifier
    roof(10, 35, 16, 41, 104, 6)      # C, lidar only
    return points


@unittest.skipUnless(ARCPY, "ArcGIS Pro Python required")
class ReconcileBuildings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global arcpy
        import arcpy
        cls.root = Path(tempfile.mkdtemp(prefix="canopy_buildings_"))
        cls.sr = arcpy.SpatialReference(6341)
        prepared = cls.root/"prepared"; (prepared/"points").mkdir(parents=True)
        cls.las = prepared/"points"/"TILE.las"
        write_las14(cls.las, scene(), cls.sr.exportToString())
        cls.lasd = str(prepared/"prepared.lasd")
        arcpy.management.CreateLasDataset([str(cls.las)], cls.lasd, spatial_reference=cls.sr, compute_stats="COMPUTE_STATS")
        cls.extent = [X0, Y0, X0 + 60, Y0 + 60]
        (prepared/"preparation.json").write_text(json.dumps(
            {"status": "complete", "working_lasd": cls.lasd, "extent": cls.extent}), encoding="utf-8")
        arcpy.management.CreateFileGDB(str(cls.root), "reference.gdb")
        cls.gdb = str(cls.root/"reference.gdb")
        county = os.path.join(cls.gdb, "county")
        arcpy.management.CreateFeatureclass(cls.gdb, "county", "POLYGON", spatial_reference=cls.sr)
        arcpy.management.AddField(county, "SOURCE_ID", "TEXT", field_length=40)
        arcpy.management.AddField(county, "BLDGHEIGHT", "DOUBLE")
        def box(x0, y0, x1, y1):
            return arcpy.Polygon(arcpy.Array([arcpy.Point(X0 + x, Y0 + y) for x, y in
                                              [(x0, y0), (x0, y1), (x1, y1), (x1, y0)]]), cls.sr)
        with arcpy.da.InsertCursor(county, ["SHAPE@", "SOURCE_ID", "BLDGHEIGHT"]) as cursor:
            cursor.insertRow([box(10.3, 10.3, 19.7, 19.7), "A", 6.2])
            cursor.insertRow([box(35.3, 10.3, 42.7, 17.7), "B", None])
            cursor.insertRow([box(40, 40, 50, 50), "D", None])
        coverage = os.path.join(cls.gdb, "coverage")
        arcpy.management.CreateFeatureclass(cls.gdb, "coverage", "POLYGON", spatial_reference=cls.sr)
        arcpy.management.AddField(coverage, "SOURCE", "TEXT", field_length=32)
        with arcpy.da.InsertCursor(coverage, ["SHAPE@", "SOURCE"]) as cursor:
            cursor.insertRow([box(-10, -10, 70, 70), "county"])
        trees = os.path.join(cls.gdb, "trees_review")
        arcpy.management.CreateFeatureclass(cls.gdb, "trees_review", "POINT", spatial_reference=cls.sr)
        for name, kind in [("TREE_ID", "TEXT"), ("HEIGHT_M", "DOUBLE"), ("CROWN_STATUS", "TEXT"), ("CROWN_AREA_M2", "DOUBLE")]:
            arcpy.management.AddField(trees, name, kind)
        with arcpy.da.InsertCursor(trees, ["SHAPE@XY", "TREE_ID", "HEIGHT_M", "CROWN_STATUS", "CROWN_AREA_M2"]) as cursor:
            cursor.insertRow([(X0 + 20.5, Y0 + 15), "edge", 6.2, "CROWN_TOO_SMALL", 1.0])
            cursor.insertRow([(X0 + 20.5, Y0 + 12), "overhang", 9.5, "OK", 20.0])
            cursor.insertRow([(X0 + 39, Y0 + 14), "missed", 5.1, "OK", 12.0])
            cursor.insertRow([(X0 + 55, Y0 + 5), "clear", 12.0, "OK", 30.0])
        cls.trees = trees
        cls.before = cls.las.read_bytes()
        from canopy import buildings
        cls.output = cls.root/"out"
        cls.result = buildings.reconcile(cls.lasd, str(cls.output), cls.extent, cls.gdb, trees=trees, tile="TILE")

    @classmethod
    def tearDownClass(cls):
        arcpy.management.ClearWorkspaceCache()
        shutil.rmtree(cls.root, ignore_errors=True)

    def rows(self, name, fields):
        return list(arcpy.da.SearchCursor(os.path.join(self.result["outputs"]["review_gdb"], name), fields))

    def test_footprint_statuses_and_heights(self):
        rows = {r[0]: r[1:] for r in self.rows("footprint_status", ["SOURCE_ID", "STATUS", "H6_MAX", "HALL_P50", "BLDGHEIGHT"])}
        self.assertEqual(rows["A"][0], "MATCHED")
        self.assertAlmostEqual(rows["A"][1], 6.0, places=1)
        self.assertEqual(rows["A"][3], 6.2)
        self.assertEqual(rows["B"][0], "LIDAR_MISSED")
        self.assertIsNone(rows["B"][1])
        self.assertAlmostEqual(rows["B"][2], 5.0, places=1)   # a missed building still gets a height
        self.assertEqual(rows["D"][0], "NO_RETURNS_ABOVE_2M")

    def test_lidar_regions(self):
        rows = self.rows("lidar_buildings", ["STATUS", "IN_COUNTY", "COV_COUNTY", "AREA_M2", "H6_P50"])
        self.assertEqual(sorted(r[0] for r in rows), ["MATCHED", "NO_FOOTPRINT"])
        lidar_only = next(r for r in rows if r[0] == "NO_FOOTPRINT")
        self.assertEqual((lidar_only[1], lidar_only[2]), (0, 1))
        self.assertAlmostEqual(lidar_only[3], 36, delta=1)
        self.assertAlmostEqual(lidar_only[4], 4.0, places=1)

    def test_candidate_flags_keep_tree_ids(self):
        flags = dict(self.rows("candidate_flags", ["TREE_ID", "FLAG"]))
        self.assertEqual(flags, {"edge": "ROOF_EDGE", "overhang": "OVERHANG", "missed": "ON_ROOF", "clear": "CLEAR"})

    def test_label_copy_changes_only_class_bytes_and_input_is_unchanged(self):
        self.assertEqual(self.las.read_bytes(), self.before)
        label = Path(self.result["outputs"]["label_las"])
        after = label.read_bytes()
        self.assertEqual(len(after), len(self.before))
        offset = 375 + 54 + len(self.sr.exportToString().encode("utf-8")) + 1
        changed = {(i - offset) % 30 for i, (a, b) in enumerate(zip(self.before, after)) if a != b}
        self.assertEqual(changed, {16})
        codes = self.result["label_las"]["after"]
        self.assertIn("6", codes)       # A: class 6 inside a footprint
        self.assertIn("64", codes)      # C: class 6 without a footprint
        self.assertIn("65", codes)      # B: class 5 inside a footprint at roof height
        self.assertNotIn("5", codes)

    def test_existing_output_is_refused(self):
        from canopy import buildings
        with self.assertRaises(FileExistsError):
            buildings.reconcile(self.lasd, str(self.output), self.extent, self.gdb, trees=self.trees, tile="TILE")

    def test_summary_records_parameters_and_layers(self):
        summary = json.loads((self.output/"reconcile.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["status"], "complete")
        self.assertEqual(summary["parameters"]["overhang_m"], 2.0)
        self.assertEqual(summary["height_comparison"]["n_with_height"], 1)
        self.assertTrue(all(Path(v["path"]).is_file() for v in summary["layer_files"].values()))


@unittest.skipUnless(ARCPY, "ArcGIS Pro Python required")
class OverpassParsing(unittest.TestCase):
    def test_ways_relations_and_skips(self):
        from canopy import footprints
        square = [{"lon": 0, "lat": 0}, {"lon": 1, "lat": 0}, {"lon": 1, "lat": 1}, {"lon": 0, "lat": 1}, {"lon": 0, "lat": 0}]
        document = {"elements": [
            {"type": "way", "id": 1, "tags": {"building": "yes", "source": "microsoft/BuildingFootprints"}, "geometry": square},
            {"type": "way", "id": 2, "tags": {"building": "yes"}, "geometry": square[:3]},
            {"type": "relation", "id": 3, "tags": {"type": "multipolygon", "building": "house"}, "members": [
                {"type": "way", "role": "outer", "geometry": square[:3]},
                {"type": "way", "role": "outer", "geometry": square[2:]}]},
            {"type": "relation", "id": 4, "tags": {"type": "building"}, "members": []}]}
        records, skipped = footprints.osm_polygons(document)
        self.assertEqual([r["osm_id"] for r in records], ["way/1", "relation/3"])
        self.assertEqual(records[0]["source_tag"], "microsoft/BuildingFootprints")
        self.assertEqual(len(records[1]["outer"][0]), 5)
        self.assertEqual([s[1] for s in skipped], [2, 4])
        self.assertIn("[maxsize:67108864]", footprints.overpass_query([1, 2, 3, 4]))


if __name__ == "__main__":
    unittest.main()
