"""TRAINING review GDB, domains, label tool core, project, snapshot and export dry runs (ArcGIS Pro)."""
import importlib.util
import json
import os
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


    def test_label_dialog_keeps_the_common_fields_up_front(self):
        import importlib.machinery
        path = Path(__file__).resolve().parents[1]/"TrainingReview.pyt"
        loader = importlib.machinery.SourceFileLoader("training_review_pyt", str(path))
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader("training_review_pyt", loader))
        loader.exec_module(module)
        params = module.LabelTrainingUnit().getParameterInfo()
        # execute() reads parameters by index, so the order is part of the contract
        self.assertEqual([p.name for p in params], ["in_layer", "label", "imagery_usable", "notes", "reviewer",
                                                     "replace", "advance", "queue", "view_m"])
        self.assertEqual([p.name for p in params if not p.category],
                         ["in_layer", "label", "imagery_usable", "notes", "reviewer"])
        self.assertEqual({p.category for p in params if p.category}, {"Advanced"})
        nxt = module.NextTrainingUnit().getParameterInfo()
        self.assertEqual([p.name for p in nxt], ["in_layer", "queue", "view_m"])
        self.assertEqual([p.name for p in nxt if p.category], ["view_m"])
        self.assertEqual([c.__name__ for c in module.Toolbox().tools],
                         ["NextTrainingUnit", "LabelTrainingUnit", "LabelSelectedUnits"])
        bulk = module.LabelSelectedUnits().getParameterInfo()
        self.assertEqual([p.name for p in bulk], [p.name for p in params])   # same dialog, same order
        self.assertEqual([p.name for p in bulk if not p.category],
                         ["in_layer", "label", "imagery_usable", "notes", "reviewer"])

    def test_backup_and_restore_round_trip(self):
        arcpy, tra = self.arcpy, self.tra
        answer = {"LABEL": "TREE", "IMAGERY_USABLE": "YES", "REVIEWER": "Fixture", "REVIEW_DATE": "2026-09-29", "NOTES": "a, b"}
        tra.label_unit(self.fc, [self.oid("Q1-0001")], answer)
        tra.label_unit(self.fc, [self.oid("Q6-0001")], dict(answer, LABEL="GROUND", IMAGERY_USABLE=None, NOTES=None))
        out = self.root/"repo"/"training-labels"
        args = SimpleNamespace(packet=self.packet, out=out)

        self.assertEqual(self.driver.backup(args), 0)
        first = (out/"labels-progress.csv").read_bytes()
        self.assertEqual(self.driver.backup(args), 0)
        self.assertEqual(first, (out/"labels-progress.csv").read_bytes())       # unchanged work, no diff
        progress = json.loads((out/"progress.json").read_text())
        self.assertEqual((progress["counts"]["saved"], progress["counts"]["labelled"]), (2, 2))
        self.assertEqual(progress["reviewers"], ["Fixture"])
        self.assertFalse((out/"labels-progress.csv.pending").exists())

        def live(uid):
            return next(r for r in tra.read_review_rows(self.fc) if r["UNIT_ID"] == uid)

        def clear(uid):
            fields = ["LABEL", "IMAGERY_USABLE", "REVIEWER", "REVIEW_DATE", "NOTES"]
            with arcpy.da.UpdateCursor(self.fc, fields, f"UNIT_ID = '{uid}'") as cursor:
                for _ in cursor:
                    cursor.updateRow([None]*5)

        clear("Q1-0001")                                                          # a label is lost
        tra.label_unit(self.fc, [self.oid("Q6-0001")], dict(answer, LABEL="WALL"), replace=True)   # and one conflicts
        restore = SimpleNamespace(packet=self.packet, csv=out/"labels-progress.csv", apply=False, replace=False)
        self.assertEqual(self.driver.restore(restore), 3)                         # conflict reported ...
        self.assertIsNone(live("Q1-0001")["LABEL"])                               # ... and a preview writes nothing
        restore.apply = True
        self.assertEqual(self.driver.restore(restore), 3)
        self.assertEqual(live("Q1-0001")["LABEL"], "TREE")
        self.assertEqual(live("Q1-0001")["NOTES"], "a, b")
        self.assertEqual(live("Q6-0001")["LABEL"], "WALL")                        # never overwritten without --replace
        restore.replace = True
        self.assertEqual(self.driver.restore(restore), 0)
        self.assertEqual(live("Q6-0001")["LABEL"], "GROUND")

        # a hand edit that breaks the snapshot rules is still saved, flagged, and exits 3
        with arcpy.da.UpdateCursor(self.fc, ["REVIEWER"], "UNIT_ID = 'Q6-0001'") as cursor:
            for _ in cursor:
                cursor.updateRow([None])
        self.assertEqual(self.driver.backup(args), 3)
        text = (out/"labels-progress.csv").read_text()
        self.assertIn("Q6-0001", text)
        self.assertIn("reviewer", text)
        self.assertEqual(json.loads((out/"progress.json").read_text())["counts"]["saved"], 2)
        with self.assertRaisesRegex(ValueError, "reviewer"):
            self.driver.snapshot(SimpleNamespace(**vars(self.args), packet=str(self.packet), out=str(self.root/"strict")))


    def test_repair_project_adds_the_working_toolbox_and_reports_the_stale_one(self):
        import shutil
        arcpy, tra = self.arcpy, self.tra
        real = Path(__file__).resolve().parents[1]/"TrainingReview.pyt"
        # a project built where the repo lived elsewhere: attach a real copy, then move that folder away so the
        # path stored in the project goes stale (Pro will not record a path that never existed)
        old_home = self.root/"old_repo"
        old_home.mkdir()
        shutil.copy2(real, old_home/"TrainingReview.pyt")
        stale = old_home/"TrainingReview.pyt"
        lasd = tra.las_dataset(self.las, self.root/"baseline.lasd")
        aprx = Path(tra.build_project(self.packet, self.gdb, lasd, toolbox=stale)["project"])

        def entries():
            project = arcpy.mp.ArcGISProject(str(aprx))
            found = [t["toolboxPath"] for t in project.toolboxes if t["toolboxPath"].lower().endswith("trainingreview.pyt")]
            del project
            # Pro stores a path relative to the project folder when both are on the same drive
            return [os.path.normpath(os.path.join(aprx.parent, f)) for f in found]
        self.assertEqual(entries(), [os.path.normpath(str(stale))])
        arcpy.management.ClearWorkspaceCache()
        old_home.rename(self.root/"old_repo_gone")
        self.assertFalse(stale.exists())
        self.assertEqual(entries(), [os.path.normpath(str(stale))])   # still recorded, now broken
        real_path, stale_path = os.path.normpath(str(real)), os.path.normpath(str(stale))
        done = tra.repair_project(aprx, real)
        self.assertEqual(done["notes"] and [n for n in done["notes"] if "not added" in n], [])
        found = entries()
        self.assertEqual(found.count(real_path), 1)                    # the working toolbox is listed ...
        self.assertEqual([os.path.normpath(os.path.join(aprx.parent, s)) for s in done["stale_entries"]], [stale_path])
        self.assertIn(stale_path, found)                               # ... and arcpy cannot remove the stale one
        self.assertTrue(Path(done["backup"]).is_file())                # the project file was kept first
        self.assertIn("before-repair", Path(done["backup"]).name)
        self.assertEqual(done["broken_layers"], [])                    # layers are found by relative path
        with self.assertRaises(FileNotFoundError):
            tra.repair_project(aprx, self.root/"missing.pyt")
        # repairing again adds nothing (and the driver command reaches the same code; Pro may be open while the
        # suite runs, so force past its open-project check)
        args = SimpleNamespace(packet=self.packet, toolbox=real, even_if_pro_is_open=True)
        self.assertEqual(self.driver.repair_project(args), 0)
        self.assertEqual(entries().count(real_path), 1)

    def test_select_unit_reads_the_selection_back(self):
        arcpy, tra = self.arcpy, self.tra
        layer = arcpy.management.MakeFeatureLayer(self.fc, "tu_select")[0]
        oid = self.oid("Q6-0001")
        self.assertTrue(tra.select_unit(layer, oid))
        self.assertEqual(tra.selected_oids(layer), [oid])
        self.assertTrue(tra.select_unit(layer, self.oid("Q1-0001")))             # NEW selection replaces it
        self.assertEqual(tra.selected_oids(layer), [self.oid("Q1-0001")])
        hidden = arcpy.management.MakeFeatureLayer(self.fc, "tu_hidden", "UNIT_ID = 'Q1-0001'")[0]
        self.assertFalse(tra.select_unit(hidden, oid))                            # a definition query hides the unit
        tra.clear_selection(layer)
        self.assertEqual(tra.selected_oids(layer), [])

    def test_map_view_falls_back_when_the_table_is_the_active_view(self):
        from types import SimpleNamespace as NS
        tra = self.tra
        table, mapview = NS(name="table"), NS(camera=NS(setExtent=lambda extent: None))
        view, note = tra.pick_map_view(NS(activeView=table, listMaps=lambda: [NS(defaultView=mapview)]))
        self.assertIs(view, mapview)
        self.assertIn("not a map", note)
        self.assertEqual(tra.pick_map_view(NS(activeView=mapview, listMaps=lambda: [])), (mapview, ""))
        view, note = tra.pick_map_view(NS(activeView=table, listMaps=lambda: [NS(defaultView=None)]))
        self.assertIsNone(view)
        self.assertIn("No map view is open", note)
        self.assertIsNone(tra.pick_map_view(NS(activeView=None, listMaps=lambda: []))[0])

    def test_go_to_next_selects_zooms_and_reports(self):
        from types import SimpleNamespace as NS
        arcpy, tra = self.arcpy, self.tra
        layer = arcpy.management.MakeFeatureLayer(self.fc, "tu_next")[0]
        extents = []
        mapview = NS(camera=NS(setExtent=extents.append))
        table_active = NS(activeView=NS(), listMaps=lambda: [NS(defaultView=mapview)])
        unit_id, messages = tra.go_to_next(layer, None, 30, table_active)
        self.assertEqual(unit_id, "Q1-0001")
        self.assertEqual(tra.selected_oids(layer), [self.oid("Q1-0001")])        # selected, read back from the layer
        self.assertEqual(len(extents), 1)
        self.assertAlmostEqual(extents[0].XMax-extents[0].XMin, 30.0)
        text = " | ".join(m for _, m in messages)
        self.assertIn("label the returns within", text)
        self.assertIn("open map view was moved", text)
        self.assertFalse([m for level, m in messages if level == "warning"])
        # no map view open at all: still selected, with a clear warning
        unit_id, messages = tra.go_to_next(layer, None, 30, NS(activeView=NS(), listMaps=lambda: []))
        self.assertEqual(unit_id, "Q1-0001")
        self.assertEqual(tra.selected_oids(layer), [self.oid("Q1-0001")])
        self.assertTrue([m for level, m in messages if level == "warning" and "No map view is open" in m])
        # the queue filter, and running out of units
        self.assertEqual(tra.go_to_next(layer, "Q6_RANDOM", 30, table_active)[0], "Q6-0001")
        answer = {"LABEL": "TREE", "IMAGERY_USABLE": "YES", "REVIEWER": "Fixture", "REVIEW_DATE": "2026-09-29", "NOTES": None}
        for uid in ("Q1-0001", "Q1-0002", "Q6-0001"):
            tra.label_unit(self.fc, [self.oid(uid)], answer)
        unit_id, messages = tra.go_to_next(layer, None, 30, table_active)
        self.assertIsNone(unit_id)
        self.assertEqual(tra.selected_oids(layer), [])
        self.assertIn("No unlabelled units remain", messages[0][1])


    def test_label_several_selected_units_at_once_is_all_or_nothing(self):
        tra = self.tra
        answer = {"LABEL": "TREE", "IMAGERY_USABLE": "NO", "REVIEWER": "Fixture", "REVIEW_DATE": "2026-09-29", "NOTES": "bulk"}
        oids = [self.oid(u) for u in ("Q1-0001", "Q1-0002", "Q6-0001")]
        history = self.root/"bulk-history"

        def labels():
            return {r["UNIT_ID"]: r["LABEL"] for r in tra.read_review_rows(self.fc)}
        with self.assertRaisesRegex(ValueError, "at least one"):
            tra.label_units(self.fc, [], answer)
        with self.assertRaisesRegex(ValueError, "at most 2"):
            tra.label_units(self.fc, oids, answer, max_units=2)
        with self.assertRaisesRegex(ValueError, "Nothing was written. 3 of 3 selected units failed"):
            tra.label_units(self.fc, oids, dict(answer, REVIEWER=""))
        self.assertEqual(set(labels().values()), {None})                      # a failing batch wrote nothing
        with self.assertRaisesRegex(ValueError, "domain"):
            tra.label_units(self.fc, oids, dict(answer, LABEL="ROOF"))
        tra.label_unit(self.fc, [oids[0]], dict(answer, LABEL="WALL"))        # one unit already has another label
        with self.assertRaisesRegex(ValueError, "already labelled WALL"):
            tra.label_units(self.fc, oids, answer)
        self.assertEqual(labels(), {"Q1-0001": "WALL", "Q1-0002": None, "Q6-0001": None})   # still nothing written
        result = tra.label_units(self.fc, oids, answer, replace=True, history_dir=history)
        self.assertEqual((result["units"], result["label"], result["replaced"]), (3, "TREE", 1))
        self.assertEqual(set(labels().values()), {"TREE"})
        rows = {r["UNIT_ID"]: r for r in tra.read_review_rows(self.fc)}
        self.assertEqual({(r["REVIEWER"], r["NOTES"], r["IMAGERY_USABLE"]) for r in rows.values()}, {("Fixture", "bulk", "NO")})
        saved = [json.loads(f.read_text()) for f in history.glob("bulk-*.json")]
        self.assertEqual(len(saved), 1)                                        # what was overwritten is recorded
        previous = {u["UNIT_ID"]: u["LABEL"] for u in saved[0]["previous_answers"]}
        self.assertEqual(previous, {"Q1-0001": "WALL", "Q1-0002": None, "Q6-0001": None})


    def test_patch_height_is_shown_and_labels_the_patch_cannot_fit_are_warned(self):
        from types import SimpleNamespace as NS
        import numpy as np
        arcpy, tra = self.arcpy, self.tra
        layer = arcpy.management.MakeFeatureLayer(self.fc, "tu_patch")[0]
        table_active = NS(activeView=NS(), listMaps=lambda: [])
        answer = {"LABEL": "GROUND", "IMAGERY_USABLE": "NO", "REVIEWER": "Fixture", "REVIEW_DATE": "2026-09-29", "NOTES": None}

        # no sidecar yet: the tool says so, and no label is ever warned about
        unit_id, messages = tra.go_to_next(layer, None, 30, table_active)
        self.assertIn("not available", " ".join(m for _, m in messages))
        self.assertEqual(tra.label_unit(self.fc, [self.oid("Q1-0001")], answer)["warnings"], [])

        # a denser tile: 60 points at 8 m inside each unit's patch, ground at 0 m around it
        rng = np.random.default_rng(11)
        points = []
        for u in self.units:
            for _ in range(60):
                r, a = 0.9*np.sqrt(rng.random()), rng.random()*2*np.pi
                points.append((u["X"]-X0+r*np.cos(a), u["Y"]-Y0+r*np.sin(a), 8.0+rng.normal(0, .02), 1))
            for _ in range(200):
                r, a = 2.0+4.0*rng.random(), rng.random()*2*np.pi
                points.append((u["X"]-X0+r*np.cos(a), u["Y"]-Y0+r*np.sin(a), rng.normal(0, .02), 2))
        dense = self.root/"dense.las"
        write_las(dense, points)
        document = json.loads((self.packet/"packet.json").read_text())
        document["sources"]["baseline"]["path"] = str(dense)              # the sources are not part of the units hash
        (self.packet/"packet.json").write_text(json.dumps(document))

        self.driver.patch_stats(NS(packet=self.packet, force=False))
        with self.assertRaises(FileExistsError):
            self.driver.patch_stats(NS(packet=self.packet, force=False))
        stats = tra.load_patch_stats(self.fc)
        self.assertEqual(set(stats), {u["UNIT_ID"] for u in self.units})
        for s in stats.values():
            self.assertGreaterEqual(s["n"], 50)
            self.assertAlmostEqual(s["mean"], 8.0, delta=0.15)             # measured against the local ground at 0 m

        unit_id, messages = tra.go_to_next(layer, None, 30, table_active)   # the next unlabelled unit
        text = " ".join(m for _, m in messages)
        self.assertIn("points,", text)
        self.assertIn("m above ground", text)
        self.assertIn("not an object beside", text)

        # a GROUND label on a patch that holds points 8 m up is warned about, not blocked
        result = tra.label_unit(self.fc, [self.oid("Q1-0002")], answer)
        self.assertEqual(result["after"]["LABEL"], "GROUND")
        self.assertTrue(result["warnings"] and "Q1-0002" in result["warnings"][0] and "m above ground" in result["warnings"][0])
        row = [r for r in tra.read_review_rows(self.fc) if r["UNIT_ID"] == "Q1-0002"][0]
        self.assertEqual(row["LABEL"], "GROUND")                              # the label was written
        ok = tra.label_units(self.fc, [self.oid("Q6-0001")], dict(answer, LABEL="BUILDING_ROOF"))
        self.assertEqual(ok["warnings"], [])                                  # a roof at 8 m fits its patch
        again = tra.label_units(self.fc, [self.oid("Q6-0001")], dict(answer, LABEL="GROUND"), replace=True)
        self.assertTrue(again["warnings"] and "Q6-0001" in again["warnings"][0])


if __name__ == "__main__":
    unittest.main()
