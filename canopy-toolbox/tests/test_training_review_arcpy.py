"""TRAINING review GDB, domains, label tool core, project, snapshot and export dry runs (ArcGIS Pro)."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from tests.test_training_review import X0, Y0, square, write_las

REVIEWS = Path(__file__).resolve().parents[1]/"reviews"/"2026-09-29"


def load_driver():
    spec = importlib.util.spec_from_file_location("training_review_driver", REVIEWS/"training_review_driver.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(importlib.util.find_spec("arcpy"), "ArcGIS Pro Python required")
class TrainingReviewArcGIS(unittest.TestCase):
    def setUp(self):
        import arcpy
        from canopy import training_review as tr, training_review_arcpy as tra, validation
        self.arcpy, self.tr, self.tra = arcpy, tr, tra
        self.tmp = tempfile.TemporaryDirectory(prefix="canopy_training_", ignore_cleanup_errors=True)
        self.root = Path(self.tmp.name)
        sr = arcpy.SpatialReference(6341)
        # a tiny evaluation frame: one reference point, one crown and one census plot
        self.reference = self.root/"reference.gdb"
        validation.create_reference_gdb(self.reference, sr)
        common = dict(tile="12TVL2804", stratum="A", REVIEW_ORDER=1, BATCH=1)
        units = {s: [] for s in validation.SAMPLES}
        units["treetop"].append(dict(common, SAMPLE_ID="TR0001", x=X0+900, y=Y0+900))
        units["crown"].append(dict(common, SAMPLE_ID="CR0001", x=X0+900, y=Y0+100, shape=arcpy.Polygon(
            arcpy.Array([arcpy.Point(*v) for v in square(X0+900, Y0+100, 4)[0]]), sr)))
        validation.write_units(self.reference, units)
        # other suites may leave arcpy.env workspaces pointing at deleted folders
        self.env = arcpy.EnvManager(workspace=str(self.root), scratchWorkspace=str(self.root))
        self.env.__enter__()
        self.plots_json = self.root/"plots.esri.json"
        self.plots_json.write_text(json.dumps({"spatialReference": {"wkid": 6341}, "features": [
            {"attributes": {"PLOT_ID": "12TVL2804_X", "TILE": "12TVL2804"}, "geometry": {"rings": square(X0+100, Y0+900, 15)}}]}))
        arcpy.management.CreateFileGDB(str(self.root), "census.gdb")
        self.plots_fc = self.root/"census.gdb"/"plots"
        arcpy.management.CreateFeatureclass(str(self.root/"census.gdb"), "plots", "POLYGON", spatial_reference=sr)
        arcpy.management.AddFields(str(self.plots_fc), [["PLOT_ID", "TEXT", "PLOT_ID", 40], ["TILE", "TEXT", "TILE", 16]])
        with arcpy.da.InsertCursor(str(self.plots_fc), ["SHAPE@", "PLOT_ID", "TILE"]) as cursor:
            cursor.insertRow([arcpy.Polygon(arcpy.Array([arcpy.Point(*v) for v in square(X0+100, Y0+900, 15)[0]]), sr),
                              "12TVL2804_X", "12TVL2804"])
        self.driver = load_driver()
        self.args = SimpleNamespace(reference_gdb=self.reference, plots_json=self.plots_json, plots_fc=self.plots_fc)
        self.frame, _ = self.driver.evaluation_frame(self.args)
        cand = lambda x, y: {"x": X0+x, "y": Y0+y, "z_low": 1., "z_high": 20., "priority": 1.}
        self.units, _ = tr.assemble({"Q1_TREE_ON_ROOF": [cand(400, 400), cand(460, 400)],
                                     "Q6_RANDOM": [cand(400, 460), cand(900, 905)]}, self.frame)
        self.assertEqual(len(self.units), 3)          # the unit beside the reference treetop is dropped
        self.packet = self.root/"packet"
        self.packet.mkdir()
        self.las = self.root/"baseline.las"
        points = [(x, y, z, 2 if z == 0 else 5) for x in range(380, 480, 2) for y in range(380, 480, 2) for z in (0, 8)]
        write_las(self.las, points)
        mask = tr.domain_mask(self.frame, cell=5.)
        self.gdb = tra.create_review_gdb(self.packet/"training_review.gdb", self.units, self.frame, mask)
        self.fc = str(self.gdb/tra.UNITS_FC)
        self.document = {"schema": tr.SCHEMA, "frame": self.frame, "units": self.units,
                         "units_digest": tr.units_digest(self.units), "gdb": str(self.gdb),
                         "sources": {"baseline": {"path": str(self.las)}}}
        (self.packet/"packet.json").write_text(json.dumps(self.document))

    def tearDown(self):
        import gc
        gc.collect()
        self.env.__exit__(None, None, None)
        self.arcpy.management.ClearWorkspaceCache()
        self.tmp.cleanup()

    def oid(self, unit_id):
        return next(r["OID@"] for r in self.tra.read_review_rows(self.fc) if r["UNIT_ID"] == unit_id)

    def test_gdb_domains_fields_and_layers(self):
        arcpy, tr, tra = self.arcpy, self.tr, self.tra
        self.assertEqual(tra.domain_codes(self.gdb), list(tr.LABELS))
        self.assertEqual(tra.domain_codes(self.gdb, tra.YES_NO_DOMAIN), list(tr.YES_NO))
        fields = {f.name: f for f in arcpy.ListFields(self.fc)}
        self.assertEqual(fields["LABEL"].domain, tra.LABEL_DOMAIN)
        self.assertEqual(fields["IMAGERY_USABLE"].domain, tra.YES_NO_DOMAIN)
        self.assertEqual(fields["QUEUE"].domain, tra.QUEUE_DOMAIN)
        self.assertEqual(fields["REVIEW_DATE"].type, "Date")
        self.assertEqual(int(arcpy.management.GetCount(str(self.gdb/tra.PATCHES_FC))[0]), 3)
        self.assertEqual(int(arcpy.management.GetCount(str(self.gdb/tra.EXCLUDED_FC))[0]), 3)
        self.assertTrue(arcpy.Exists(str(self.gdb/tra.DOMAIN_FC)))
        rows = tra.read_review_rows(self.fc)
        self.assertEqual(sorted(r["REVIEW_ORDER"] for r in rows), [1, 2, 3])
        lasd = tra.las_dataset(self.las, self.root/"baseline.lasd")
        result = tra.build_project(self.packet, self.gdb, lasd, toolbox=Path(__file__).resolve().parents[1]/"TrainingReview.pyt")
        self.assertTrue(Path(result["project"]).is_file())
        project = arcpy.mp.ArcGISProject(result["project"])
        names = [layer.name for layer in project.listMaps("Training review")[0].listLayers()]
        self.assertIn("Training units", names)
        self.assertTrue(any(n.startswith("Lidar all returns") for n in names))
        units_layer = project.listMaps("Training review")[0].listLayers("Training units")[0]
        queries = units_layer.listDefinitionQueries()
        self.assertEqual(len(queries), len(tra.queue_queries()))
        self.assertEqual([q["sql"] for q in queries if q["isActive"]], ["LABEL IS NULL"])
        self.assertTrue(any(t["toolboxPath"].endswith("TrainingReview.pyt") for t in project.toolboxes), result["notes"])
        del project
        with self.assertRaises(FileExistsError):
            tra.build_project(self.packet, self.gdb, lasd)

    def test_label_tool_core_next_unit_and_refusals(self):
        tra = self.tra
        first = tra.next_unit_row(self.fc)
        self.assertEqual(first["UNIT_ID"], "Q1-0001")
        answer = {"LABEL": "TREE", "IMAGERY_USABLE": "YES", "REVIEWER": "Fixture", "REVIEW_DATE": "2026-09-29", "NOTES": "x"}
        with self.assertRaisesRegex(ValueError, "exactly one"):
            tra.label_unit(self.fc, [], answer)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            tra.label_unit(self.fc, [self.oid("Q1-0001"), self.oid("Q6-0001")], answer)
        with self.assertRaisesRegex(ValueError, "domain"):
            tra.label_unit(self.fc, [first["OID@"]], dict(answer, LABEL="ROOF"))
        result = tra.label_unit(self.fc, [first["OID@"]], answer)
        self.assertEqual(result["after"]["LABEL"], "TREE")
        self.assertEqual(tra.next_unit_row(self.fc)["UNIT_ID"], "Q6-0001")
        self.assertEqual(tra.next_unit_row(self.fc, "Q1_TREE_ON_ROOF")["UNIT_ID"], "Q1-0002")
        with self.assertRaisesRegex(ValueError, "Replace"):
            tra.label_unit(self.fc, [first["OID@"]], dict(answer, LABEL="WALL"))
        tra.label_unit(self.fc, [first["OID@"]], dict(answer, LABEL="WALL"), replace=True)
        row = [r for r in tra.read_review_rows(self.fc) if r["UNIT_ID"] == "Q1-0001"][0]
        self.assertEqual((row["LABEL"], row["REVIEW_DATE"], row["REVIEWER"]), ("WALL", "2026-09-29", "Fixture"))

    def test_label_refused_when_unit_is_in_the_excluded_domain(self):
        tr, tra = self.tr, self.tra
        # A packet whose evaluation frame gained a unit next to Q6-0001 (e.g. an edited frame) refuses labels there.
        units = [{"sample": "cell", "SAMPLE_ID": "CE9", "TILE": "12TVL2804",
                  "x": self.units[2]["X"]+3, "y": self.units[2]["Y"]}]
        reference = tra.read_reference_units(self.reference)
        frame = tr.exclusion_frame(reference+units, tr.plots_from_esri_json(json.loads(self.plots_json.read_text())))
        document = dict(self.document, frame=frame)
        answer = {"LABEL": "TREE", "REVIEWER": "Fixture", "REVIEW_DATE": "2026-09-29"}
        target = next(u for u in self.units if abs(u["X"]-units[0]["x"]+3) < .01)
        with self.assertRaisesRegex(ValueError, "refused"):
            tra.label_unit(self.fc, [self.oid(target["UNIT_ID"])], answer, document=document)
        self.assertIsNone([r for r in tra.read_review_rows(self.fc) if r["UNIT_ID"] == target["UNIT_ID"]][0]["LABEL"])

    def test_snapshot_pointcloud_prepare_and_imagery_dry_run(self):
        arcpy, tr, tra = self.arcpy, self.tr, self.tra
        answer = {"IMAGERY_USABLE": "YES", "REVIEWER": "Fixture", "REVIEW_DATE": "2026-09-29"}
        tra.label_unit(self.fc, [self.oid("Q1-0001")], dict(answer, LABEL="TREE"))
        tra.label_unit(self.fc, [self.oid("Q1-0002")], dict(answer, LABEL="GROUND"))
        args = SimpleNamespace(**vars(self.args), packet=str(self.packet), out=str(self.root/"snap"))
        audit = self.driver.snapshot(args)
        self.assertEqual((audit["counts"]["labelled"], audit["counts"]["exportable"]), (2, 2))
        with self.assertRaises(FileExistsError):
            self.driver.snapshot(args)
        # point cloud: new LAS copy, protected bytes verified, Prepare (data preparation only; no training)
        export = SimpleNamespace(**vars(self.args), packet=str(self.packet), snapshot=str(self.root/"snap"),
                                 out=str(self.root/"pc"), source=None, prepare=arcpy.CheckExtension("3D") == "Available")
        before = self.las.read_bytes()
        self.driver.export_pointcloud(export)
        self.assertEqual(self.las.read_bytes(), before)
        manifest = json.loads((self.root/"pc"/"export.json").read_text())
        self.assertEqual(manifest["counts"]["units_exported"], 2)
        self.assertGreater(manifest["counts"]["classes"]["5"], 0)
        self.assertGreater(manifest["counts"]["classes"][str(tr.IGNORE_CODE)], 0)
        if export.prepare:
            self.assertTrue((self.root/"pc"/"training.pctd").exists(), manifest.get("prepare_messages"))
        # imagery: synthetic four-band raster in EPSG:6341
        import numpy as np
        tif = str(self.root/"naip.tif")
        with arcpy.EnvManager(workspace=str(self.root), scratchWorkspace=str(self.root)):
            raster = arcpy.NumPyArrayToRaster(np.random.default_rng(0).integers(0, 255, (4, 400, 400)).astype("uint8"),
                                              arcpy.Point(X0+300, Y0+300), 0.5, 0.5)
            raster.save(tif)
            del raster
        arcpy.management.DefineProjection(tif, arcpy.SpatialReference(6341))
        imagery = SimpleNamespace(**vars(self.args), packet=str(self.packet), snapshot=str(self.root/"snap"),
                                  out=str(self.root/"img"), raster=Path(tif), chips=arcpy.CheckExtension("Spatial") == "Available")
        self.driver.export_imagery(imagery)
        manifest = json.loads((self.root/"img"/"export.json").read_text())
        self.assertEqual(manifest["patches"], 2)
        values = sorted(r[0] for r in arcpy.da.SearchCursor(manifest["polygons"], ["CLASSVALUE"]))
        self.assertEqual(values, sorted([tr.IMAGERY_CLASS["TREE"], tr.IMAGERY_CLASS["GROUND"]]))
        self.assertIn("NOT exported", manifest["licensing"]["Esri World Imagery"])
        if imagery.chips:
            self.assertTrue(any((self.root/"img"/"chips").rglob("*.tif")), manifest.get("chip_messages"))
        # a tampered snapshot is refused before any export
        labels = self.root/"snap"/"labels.csv"
        labels.write_text(labels.read_text().replace("GROUND", "WATER"))
        with self.assertRaisesRegex(ValueError, "changed"):
            self.driver.export_pointcloud(SimpleNamespace(**{**vars(export), "out": str(self.root/"pc2")}))


if __name__ == "__main__":
    unittest.main()
