"""End-to-end scoring on synthetic run folders and a synthetic label set (ArcGIS Pro).

Nothing here touches the real reference geodatabase. A baseline run has one tree
crown, a second tree, and a false 'roof edge' object; a variant removes the roof
object and gains canopy where a reference point says a tree was missed.
"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

XMIN, YMIN, CELL, SIZE = 500000.0, 4500000.0, 0.5, 40
YMAX = YMIN + SIZE*CELL


def centre(row, col):
    return XMIN + (col + .5)*CELL, YMAX - (row + .5)*CELL


@unittest.skipUnless(importlib.util.find_spec("arcpy") is not None, "ArcGIS Pro Python required")
class ScoreSyntheticRuns(unittest.TestCase):
    def setUp(self):
        import arcpy
        self.arcpy = arcpy
        self.folder = Path(tempfile.mkdtemp(prefix="canopy_validation_"))
        self.sr = arcpy.SpatialReference(6341)

    def tearDown(self):
        import shutil
        self.arcpy.management.ClearWorkspaceCache()
        shutil.rmtree(self.folder, ignore_errors=True)

    def make_run(self, name, chm, tops, crowns):
        arcpy = self.arcpy
        from canopy import common
        assembly = self.folder / name / "assembly_x"
        assembly.mkdir(parents=True)
        path = str(assembly / "chm.tif")
        raster = arcpy.NumPyArrayToRaster(np.where(np.isnan(chm), -9999, chm).astype(np.float32),
                                          arcpy.Point(XMIN, YMIN), CELL, CELL, -9999)
        raster.save(path)
        arcpy.management.DefineProjection(path, self.sr)
        arcpy.management.CreateFileGDB(str(assembly), "inventory.gdb")
        gdb = str(assembly / "inventory.gdb")
        common.create_points(gdb, "treetops", self.sr)
        with arcpy.da.InsertCursor(gdb + r"\treetops", ["SHAPE@XY", "TREE_ID", "HEIGHT_M"]) as cursor:
            for tree_id, (row, col) in tops.items():
                cursor.insertRow([centre(row, col), tree_id, 8.0])
        arcpy.management.CopyFeatures(gdb + r"\treetops", gdb + r"\trees_review")
        arcpy.management.CreateFeatureclass(gdb, "crowns", "POLYGON", spatial_reference=self.sr)
        arcpy.management.AddField(gdb + r"\crowns", "TREE_ID", "TEXT", field_length=36)
        with arcpy.da.InsertCursor(gdb + r"\crowns", ["SHAPE@", "TREE_ID"]) as cursor:
            for tree_id, (r0, r1, c0, c1) in crowns.items():
                cursor.insertRow([self.box(r0, r1, c0, c1), tree_id])
        outputs = {"chm": path, "treetops": gdb + r"\treetops", "crowns": gdb + r"\crowns",
                   "trees_review": gdb + r"\trees_review"}
        (self.folder / name / "run.json").write_text(json.dumps(
            {"status": "complete", "outputs": outputs, "parameters": {}}))
        return self.folder / name

    def box(self, r0, r1, c0, c1):
        arcpy = self.arcpy
        x0, x1 = XMIN + c0*CELL, XMIN + c1*CELL
        y0, y1 = YMAX - r1*CELL, YMAX - r0*CELL
        ring = arcpy.Array([arcpy.Point(x0, y0), arcpy.Point(x0, y1), arcpy.Point(x1, y1),
                            arcpy.Point(x1, y0), arcpy.Point(x0, y0)])
        return arcpy.Polygon(ring, self.sr)

    def build(self):
        from canopy import validation
        chm = np.full((SIZE, SIZE), 0.5)
        chm[2:12, 2:12] = 8.0        # tree A
        chm[2:8, 28:34] = 6.0        # tree B
        chm[20:22, 20:22] = 5.0      # false canopy on a roof edge
        chm[35:38, 35:38] = np.nan   # unobserved
        tops = {"A": (6, 6), "B": (4, 30), "ROOF": (20, 20)}
        crowns = {"A": (2, 12, 2, 12), "B": (2, 8, 28, 34), "ROOF": (20, 22, 20, 22)}
        base = self.make_run("base", chm, tops, crowns)
        variant_chm = chm.copy()
        variant_chm[20:22, 20:22] = 0.5   # roof object removed
        variant_chm[30, 5] = 3.0          # a missed tree is now canopy
        variant = self.make_run("variant", variant_chm, {"A": (6, 6), "B": (4, 30), "NEW": (30, 5)},
                                {"A": (2, 12, 2, 12), "B": (2, 8, 28, 34), "NEW": (30, 31, 5, 6)})
        gdb = self.folder / "reference.gdb"
        validation.create_reference_gdb(gdb, self.sr)

        def point(order, stratum, rc, **extra):
            x, y = centre(*rc)
            return {"tile": "T1", "stratum": stratum, "x": x, "y": y, "SAMPLE_ID": f"S{order}",
                    "REVIEW_ORDER": order, "BATCH": 1, **extra}
        units = {
            "treetop": [point(1, "ROOF_LEVEL", (20, 20)), point(2, "NORMAL", (6, 6)),
                        point(3, "NORMAL", (4, 30))],
            "cell": [point(1, "CANOPY_FAR", (7, 7)), point(2, "CANOPY_FAR", (21, 21)),
                     point(3, "NONCAN_FAR", (30, 5)), point(4, "NONCAN_FAR", (15, 30))],
            "omission": [point(1, "OM_OPEN", (30, 5)), point(2, "OM_OPEN", (15, 30)),
                         point(3, "OM_OPEN", (25, 15))],
            "crown": [dict(point(1, "CR_LARGE", (6, 6)), shape=self.box(2, 12, 2, 12)),
                      dict(point(2, "CR_BLDG", (20, 20)), shape=self.box(20, 22, 20, 22))],
        }
        validation.write_units(gdb, units)
        design = []
        for sample, strata in {"treetop": {"ROOF_LEVEL": 100, "NORMAL": 300},
                               "cell": {"CANOPY_FAR": 1000, "NONCAN_FAR": 3000},
                               "omission": {"OM_OPEN": 2000},
                               "crown": {"CR_LARGE": 50, "CR_BLDG": 20}}.items():
            for stratum, population in strata.items():
                design.append({"sample": sample, "tile": "T1", "stratum": stratum,
                               "population": population, "target": 2, "sampled": 2,
                               "unit_area_m2": .25 if sample in ("cell", "omission") else None,
                               "frame": "synthetic", "base_run": str(base), "chm": ""})
        validation.write_design(gdb, design)
        return gdb, base, variant

    def label(self, gdb):
        arcpy = self.arcpy
        labels = {"treetop_sample": {"S1": "ROOF_OR_BUILDING", "S2": "TREE", "S3": "TREE"},
                  "cell_sample": {"S1": "TREE", "S2": "ROOF_OR_BUILDING", "S3": "TREE",
                                  "S4": "GROUND_OR_OPEN"},
                  "omission_sample": {"S1": "TREE", "S2": "GROUND_OR_OPEN"}}   # S3 left unlabelled
        for fc, values in labels.items():
            with arcpy.da.UpdateCursor(str(gdb / fc), ["SAMPLE_ID", "LABEL", "REVIEWER"]) as cursor:
                for row in cursor:
                    if row[0] in values:
                        cursor.updateRow([row[0], values[row[0]], "synthetic"])
        crowns = {"S1": ("CORRECT", "NO"), "S2": ("NOT_A_TREE", "YES")}
        with arcpy.da.UpdateCursor(str(gdb / "crown_sample"),
                                   ["SAMPLE_ID", "CROWN_LABEL", "ROOF_IN_OUTLINE"]) as cursor:
            for row in cursor:
                cursor.updateRow([row[0], *crowns[row[0]]])

    def runs(self, base, variant):
        return [{"name": "baseline", "folders": {"T1": base}},
                {"name": "variant", "folders": {"T1": variant}},
                {"name": "flags", "folders": {"T1": base}, "drop": {"T1": {"ROOF"}}}]

    def test_unlabelled_reference_reports_no_labels(self):
        from canopy import validation
        gdb, base, variant = self.build()
        report = validation.score(gdb, self.runs(base, variant), self.folder / "score0", replicates=50)
        self.assertEqual(report["status"], "NO_LABELS")
        self.assertIn("No labels yet: 0 of 12", validation._summary(report))
        scope = report["runs"]["variant"]["scopes"]["T1"]
        self.assertEqual(scope["treetops"]["status"], "NO_LABELS")
        self.assertEqual(scope["treetops"]["retained_by_stratum"], {"T1|ROOF_LEVEL": 0, "T1|NORMAL": 2})
        self.assertEqual(scope["inputs"]["T1"]["new_candidates"], 1)
        self.assertIn("no labels yet", (self.folder / "score0" / "comparison.md").read_text(encoding="utf-8"))

    def test_merged_run_candidates_are_scored_once(self):
        from canopy import validation
        chm = np.full((SIZE, SIZE), .5)
        base = self.make_run("merge_base", chm, {"A": (6, 6), "B": (6, 8)}, {})
        variant = self.make_run("merge_variant", chm, {"MERGED": (6, 6)}, {})
        units = {"treetop": [
            {"TILE": "T1", "STRATUM": "NORMAL", "BASE_TREE_ID": tree_id,
             "LABEL": label, "x": centre(*rc)[0], "y": centre(*rc)[1]}
            for tree_id, rc, label in (("A", (6, 6), "ROOF_OR_BUILDING"),
                                       ("B", (6, 8), "TREE"))],
                 "cell": [], "omission": [], "crown": []}
        design = [{"tile": "T1", "sample": sample, "stratum": "NORMAL",
                   "population": 2 if sample == "treetop" else 0,
                   "unit_area_m2": .25 if sample in ("cell", "omission") else None,
                   "base_run": str(base)} for sample in units]
        answers, info = validation.run_units(units, design, "T1", validation.RunView(variant))
        self.assertEqual([u["retained"] for u in answers["treetop"]], [True, False])
        self.assertEqual(info["run_candidates"], 1)
        self.assertEqual(info["new_candidates"], 0)
        self.assertEqual(info["ambiguous_variant"], 1)
        score = validation.score_units({"T1": answers}, {"T1": info}, design, ["T1"], replicates=20)
        estimates = score["treetops"]["estimates"]
        self.assertEqual(estimates["candidates_kept"]["estimate"], 1)
        self.assertEqual(estimates["true_removed"]["estimate"], 1)
        self.assertEqual(estimates["false_kept"]["estimate"], 1)
        self.assertEqual(estimates["precision"]["estimate"], 0)

    def test_same_folder_flag_removal_preserves_the_baseline_sampling_frame(self):
        from canopy import validation
        chm = np.full((SIZE, SIZE), .5)
        base = self.make_run("flag_base", chm, {"A": (6, 6), "B": (6, 8)}, {})
        units = {"treetop": [
            {"TILE": "T1", "STRATUM": "NORMAL", "BASE_TREE_ID": tree_id,
             "LABEL": label, "x": centre(*rc)[0], "y": centre(*rc)[1]}
            for tree_id, rc, label in (("A", (6, 6), "ROOF_OR_BUILDING"),
                                       ("B", (6, 8), "TREE"))],
                 "cell": [], "omission": [], "crown": []}
        design = [{"tile": "T1", "sample": sample, "stratum": "NORMAL",
                   "population": 2 if sample == "treetop" else 0,
                   "unit_area_m2": .25 if sample in ("cell", "omission") else None,
                   "base_run": str(base)} for sample in units]
        answers, info = validation.run_units(units, design, "T1", validation.RunView(base, {"A"}))
        self.assertEqual([u["retained"] for u in answers["treetop"]], [False, True])
        self.assertEqual(info["dropped_by_flags"], 1)
        self.assertEqual(info["new_candidates"], 0)
        score = validation.score_units({"T1": answers}, {"T1": info}, design, ["T1"], replicates=20)
        estimates = score["treetops"]["estimates"]
        self.assertEqual(estimates["baseline_precision"]["estimate"], .5)
        self.assertEqual(estimates["false_removed"]["estimate"], 1)
        self.assertEqual(estimates["true_kept"]["estimate"], 1)
        self.assertEqual(estimates["precision"]["estimate"], 1)

    def test_run_units_rejects_a_different_raster_grid(self):
        from canopy import validation
        chm = np.full((SIZE, SIZE), .5)
        base = self.make_run("grid_base", chm, {}, {})
        variant = self.make_run("grid_variant", chm, {}, {})
        units = {"treetop": [], "cell": [], "omission": [], "crown": []}
        design = [{"tile": "T1", "base_run": str(base)}]
        outputs, _ = validation.run_outputs(variant)
        self.arcpy.management.DefineProjection(outputs["chm"], self.arcpy.SpatialReference(26912))
        with self.assertRaisesRegex(ValueError, "Run grid differs"):
            validation.run_units(units, design, "T1", validation.RunView(variant))

    def test_run_units_rejects_a_shifted_raster_grid(self):
        from canopy import validation
        chm = np.full((SIZE, SIZE), .5)
        base = self.make_run("shift_base", chm, {}, {})
        variant = self.make_run("shift_variant", chm, {}, {})
        view = validation.RunView(variant)
        shifted = str(self.folder / "shifted.tif")
        raster = self.arcpy.NumPyArrayToRaster(chm.astype(np.float32),
            self.arcpy.Point(XMIN + CELL / 2, YMIN), CELL, CELL)
        raster.save(shifted)
        self.arcpy.management.DefineProjection(shifted, self.sr)
        view.grid = validation.Grid(shifted)
        units = {"treetop": [], "cell": [], "omission": [], "crown": []}
        design = [{"tile": "T1", "base_run": str(base)}]
        with self.assertRaisesRegex(ValueError, "Run grid differs"):
            validation.run_units(units, design, "T1", view)

    def test_synthetic_labels_score_every_metric(self):
        from canopy import validation
        gdb, base, variant = self.build()
        self.label(gdb)
        report = validation.score(gdb, self.runs(base, variant), self.folder / "score1", replicates=200)
        self.assertEqual(report["status"], "LABELLED")
        get = lambda run, group, key: report["runs"][run]["scopes"]["T1"][group]["estimates"][key]["estimate"]
        # Treetops: roof-level stratum (100) all false, normal stratum (300) all trees.
        self.assertAlmostEqual(get("baseline", "treetops", "precision"), .75)
        self.assertAlmostEqual(get("variant", "treetops", "precision"), 1.0)
        self.assertAlmostEqual(get("variant", "treetops", "false_removed"), 100)
        self.assertAlmostEqual(get("variant", "treetops", "true_removed"), 0)
        self.assertAlmostEqual(get("variant", "treetops", "precision_if_new_false"), 300/301)
        self.assertAlmostEqual(get("flags", "treetops", "precision"), 1.0)
        self.assertEqual(report["runs"]["flags"]["scopes"]["T1"]["inputs"]["T1"]["new_candidates"], 0)
        # Cells: canopy stratum half false; the non-canopy tree is recovered by the variant.
        self.assertAlmostEqual(get("baseline", "cells", "commission"), .5)
        self.assertAlmostEqual(get("baseline", "cells", "omission"), .75)
        self.assertAlmostEqual(get("baseline", "cells", "area_bias_m2"), -250)
        self.assertAlmostEqual(get("variant", "cells", "commission"), 0)
        self.assertAlmostEqual(get("variant", "cells", "omission"), 0)
        self.assertAlmostEqual(get("flags", "cells", "commission"), .5)
        # Omission search: half of 2000 open cells hide a tree; the variant recovers it.
        self.assertAlmostEqual(get("baseline", "omission", "missed_m2"), 250)
        self.assertAlmostEqual(get("variant", "omission", "missed_m2"), 0)
        self.assertAlmostEqual(get("variant", "omission", "recovered_m2"), 250)
        # Crowns: the variant no longer has the roof crown, so that label does not carry over.
        self.assertAlmostEqual(get("baseline", "crowns", "share_correct"), 50/70)
        self.assertAlmostEqual(get("baseline", "crowns", "share_includes_roof"), 20/70)
        variant_crowns = report["runs"]["variant"]["scopes"]["T1"]["crowns"]
        self.assertEqual(variant_crowns["changed_by_run"], 1)
        self.assertEqual(variant_crowns["status"], "PARTIAL")
        self.assertAlmostEqual(get("variant", "crowns", "share_correct"), 1.0)
        rows = (self.folder / "score1" / "comparison.csv").read_text(encoding="utf-8")
        self.assertIn("treetops.precision", rows)
        self.assertIn("75.0%", rows)


if __name__ == "__main__":
    unittest.main()
