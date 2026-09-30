"""TRAINING-label review: domain exclusion, sampling, clustering, ordering, answers, exports (no ArcPy)."""
import copy
import datetime
import json
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from canopy import training_review as tr

X0, Y0 = 428000., 4504000.       # 12TVL2804 south-west corner


def square(x, y, half):
    return [[[x-half, y-half], [x-half, y+half], [x+half, y+half], [x+half, y-half], [x-half, y-half]]]


def frame(extra_units=(), plots=None):
    units = [{"sample": "treetop", "SAMPLE_ID": "TR0001", "TILE": "12TVL2804", "x": X0+500, "y": Y0+500},
             {"sample": "crown", "SAMPLE_ID": "CR0001", "TILE": "12TVL2804", "rings": square(X0+200, Y0+800, 5)},
             {"sample": "treetop", "SAMPLE_ID": "TR0002", "TILE": "12TVL3302", "x": 433500, "y": 4502500},
             *extra_units]
    plots = plots if plots is not None else [{"PLOT_ID": "12TVL2804_A", "TILE": "12TVL2804", "rings": square(X0+800, Y0+200, 15)}]
    return tr.exclusion_frame(units, plots)


def write_las(path, points, modern=True, origin=(X0, Y0)):
    """(x, y, z, class) records relative to origin, LAS 1.4 format 6 (or 1.2 format 0)."""
    rng = np.random.default_rng(1)
    size, length = (375, 30) if modern else (227, 20)
    header = bytearray(size); header[:4] = b"LASF"; header[24:26] = bytes([1, 4 if modern else 2])
    struct.pack_into("<HII", header, 94, size, size, 0)
    struct.pack_into("<BHI", header, 104, 6 if modern else 0, length, len(points))
    if modern:
        struct.pack_into("<Q", header, 247, len(points))
    xyz = np.array([p[:3] for p in points], float)
    struct.pack_into("<3d", header, 131, .001, .001, .001)
    struct.pack_into("<3d", header, 155, origin[0], origin[1], 0)
    struct.pack_into("<6d", header, 179, origin[0]+xyz[:, 0].max(), origin[0]+xyz[:, 0].min(),
                     origin[1]+xyz[:, 1].max(), origin[1]+xyz[:, 1].min(), xyz[:, 2].max(), xyz[:, 2].min())
    with Path(path).open("wb") as handle:
        handle.write(header)
        for x, y, z, code in points:
            record = bytearray(rng.integers(0, 256, length, dtype=np.uint8).tobytes())
            struct.pack_into("<iii", record, 0, round(x*1000), round(y*1000), round(z*1000))
            if modern:
                record[15] &= 0xF0         # no withheld/synthetic/overlap flags
                record[16] = code
            else:
                record[15] = code
            handle.write(record)


def unit(uid, x, y, label=None, zlow=0., zhigh=10., order=1, queue="Q6_RANDOM"):
    return {"UNIT_ID": uid, "QUEUE": queue, "REVIEW_ORDER": order, "X": x, "Y": y, "Z_LOW": zlow, "Z_HIGH": zhigh,
            "PATCH_R_M": 1.0, "LABEL": label, "IMAGERY_USABLE": "YES", "REVIEWER": "Fixture",
            "REVIEW_DATE": "2026-09-29", "NOTES": None}


class Domain(unittest.TestCase):
    def test_buffer_is_edge_to_edge_and_includes_patch_radius(self):
        f = frame()
        reach = tr.EVAL_BUFFER_M+tr.PATCH_RADIUS_M
        ok = tr.patch_status([X0+500+reach+.01, X0+500+reach-.01], [Y0+500, Y0+500], f)
        self.assertEqual(ok[0], "")
        self.assertIn("evaluation unit", ok[1])
        # crown polygon: distance is measured from its edge, and inside is refused
        edge = X0+205
        self.assertEqual(tr.patch_status([edge+reach+.01], [Y0+800], f)[0], "")
        self.assertIn("evaluation", tr.patch_status([edge+reach-.01], [Y0+800], f)[0])
        self.assertIn("evaluation", tr.patch_status([X0+200], [Y0+800], f)[0])
        # census plot
        self.assertIn("evaluation", tr.patch_status([X0+800], [Y0+200], f)[0])

    def test_holdout_tiles_and_tile_edges_are_refused(self):
        f = frame()
        self.assertIn("12TVL3302", tr.patch_status([433500], [4502500], f)[0])
        self.assertIn("12TVL3302", tr.patch_status([434040], [4503040], f)[0])
        self.assertIn("12TVL2203", tr.patch_status([422500], [4503500], f)[0])
        self.assertIn("outside", tr.patch_status([X0+.5], [Y0+300], f)[0])
        with self.assertRaisesRegex(ValueError, "refused"):
            tr.assert_patch_allowed(X0+500, Y0+500, f)

    def test_evaluation_units_on_other_tiles_are_recorded_and_frame_is_tamper_evident(self):
        f = frame()
        self.assertEqual(len(f["features"]), 4)
        bad = copy.deepcopy(f)
        bad["features"] = bad["features"][1:]
        with self.assertRaisesRegex(ValueError, "digest"):
            tr.patch_status([X0+300], [Y0+300], bad)
        with self.assertRaisesRegex(ValueError, "unique"):
            tr.exclusion_frame([{"sample": "cell", "SAMPLE_ID": "A", "TILE": "12TVL2804", "x": 1, "y": 1}]*2, [])

    def test_domain_areas(self):
        f = tr.exclusion_frame([{"sample": "cell", "SAMPLE_ID": "C1", "TILE": "12TVL2804", "x": X0+500, "y": Y0+500}], [])
        areas = tr.domain_areas(f, cell=1.)
        reach = tr.EVAL_BUFFER_M+tr.PATCH_RADIUS_M
        expected = 998*998-np.pi*reach**2
        self.assertAlmostEqual(areas["patch_centre_domain_m2"], expected, delta=60)
        self.assertEqual(len(areas["full_50m_blocks_clear"]), 400-4)   # the 4 blocks meeting at the centre
        self.assertEqual(areas["evaluation_features_on_tile"], 1)

    def test_plots_json_and_feature_class_comparison(self):
        doc = {"spatialReference": {"wkid": 6341}, "features": [
            {"attributes": {"PLOT_ID": "P1", "TILE": "12TVL2804"}, "geometry": {"rings": square(X0+10, Y0+10, 15)}}]}
        plots = tr.plots_from_esri_json(doc)
        self.assertTrue(tr.same_plots(plots, [{"PLOT_ID": "P1", "TILE": "12TVL2804", "rings": square(X0+10, Y0+10, 15)}]))
        self.assertFalse(tr.same_plots(plots, [{"PLOT_ID": "P1", "TILE": "12TVL2804", "rings": square(X0+11, Y0+10, 15)}]))
        with self.assertRaisesRegex(ValueError, "6341"):
            tr.plots_from_esri_json({"spatialReference": {"wkid": 26912}, "features": []})


class Sampling(unittest.TestCase):
    def test_cluster_groups_objects_and_drops_small_pieces(self):
        rng = np.random.default_rng(0)
        a = rng.uniform(0, 3, (50, 2))+[10, 10]
        b = rng.uniform(0, 3, (40, 2))+[40, 40]
        c = rng.uniform(0, .5, (3, 2))+[80, 80]
        labels = tr.cluster(np.vstack([a, b, c]), min_points=10)
        self.assertEqual(len(set(labels[:50])), 1)
        self.assertEqual(len(set(labels[50:90])), 1)
        self.assertNotEqual(labels[0], labels[50])
        self.assertTrue((labels[90:] == -1).all())
        np.testing.assert_array_equal(labels, tr.cluster(np.vstack([a, b, c]), min_points=10))

    def test_long_objects_are_split_by_max_extent(self):
        xy = np.column_stack([np.arange(0, 60, .2), np.full(300, 5.)])
        labels = tr.cluster(xy, max_extent=15., min_points=10)
        self.assertEqual(len(set(labels)), 4)

    def test_summary_picks_an_evidence_point_and_its_slab(self):
        x = np.array([0, 0.1, 0.2, 0.3, 5.]); y = np.zeros(5); z = np.array([10, 11, 12, 13, 30.])
        rows = tr.summarize_clusters(np.array([0, 0, 0, 0, 0]), x, y, z, extra={"base": np.array([6, 6, 5, 6, 5])})
        self.assertEqual(rows[0]["x"], 0.2)
        self.assertEqual((rows[0]["z_low"], rows[0]["z_high"]), (10-tr.Z_MARGIN_M, 13+tr.Z_MARGIN_M))
        self.assertEqual(rows[0]["base"], 6)

    def test_select_is_seeded_mixes_top_and_random_and_caps(self):
        pool = [{"x": float(i), "y": 0., "priority": float(i)} for i in range(100)]
        chosen = tr.select(pool, 20, "Q1_TREE_ON_ROOF")
        self.assertEqual(len(chosen), 20)
        self.assertEqual(sum(c["selection"] == "TOP" for c in chosen), 10)
        self.assertEqual({c["x"] for c in chosen if c["selection"] == "TOP"}, set(map(float, range(90, 100))))
        self.assertEqual(chosen, tr.select(list(reversed(pool)), 20, "Q1_TREE_ON_ROOF"))
        self.assertNotEqual([c["x"] for c in chosen], sorted(c["x"] for c in chosen))
        self.assertEqual(len(tr.select(pool[:5], 20, "Q2_BLDG_BACKGROUND")), 5)

    def test_random_locations_are_area_uniform_within_the_mask(self):
        mask = np.zeros((10, 10), bool); mask[:, :5] = True
        xy = tr.random_locations(mask, 0., 0., 1., 30)
        self.assertEqual(len(xy), 30)
        self.assertTrue((xy[:, 0] < 5).all())
        np.testing.assert_array_equal(xy, tr.random_locations(mask, 0., 0., 1., 30))

    def test_assemble_interleaves_queues_refuses_domain_and_enforces_spacing(self):
        f = frame()
        cand = lambda x, y: {"x": X0+x, "y": Y0+y, "z_low": 1., "z_high": 2.}
        queues = {"Q1_TREE_ON_ROOF": [cand(100, 100), cand(101, 100), cand(150, 100)],
                  "Q3_VEG_BACKGROUND": [cand(500, 500), cand(300, 300)],
                  "Q6_RANDOM": [cand(400, 400)]}
        units, dropped = tr.assemble(queues, f)
        self.assertEqual([u["QUEUE"] for u in units], ["Q1_TREE_ON_ROOF", "Q3_VEG_BACKGROUND", "Q6_RANDOM",
                                                        "Q1_TREE_ON_ROOF"])
        self.assertEqual([u["REVIEW_ORDER"] for u in units], [1, 2, 3, 4])
        self.assertEqual([u["UNIT_ID"] for u in units], ["Q1-0001", "Q3-0001", "Q6-0001", "Q1-0002"])
        self.assertEqual(dropped["Q1_TREE_ON_ROOF"]["spacing"], 1)
        self.assertEqual(dropped["Q3_VEG_BACKGROUND"]["domain"], 1)
        self.assertEqual(units, tr.assemble(copy.deepcopy(queues), f)[0])
        with self.assertRaisesRegex(ValueError, "Unknown"):
            tr.assemble({"QX": []}, f)


class Answers(unittest.TestCase):
    def setUp(self):
        self.frame = frame()
        self.units = [unit("Q6-0001", X0+100, Y0+100, order=2), unit("Q1-0001", X0+150, Y0+100, order=1, queue="Q1_TREE_ON_ROOF"),
                      unit("Q6-0002", X0+300, Y0+100, order=3)]
        for u in self.units:
            u["LABEL"] = u["IMAGERY_USABLE"] = None

    def test_next_unit(self):
        rows = copy.deepcopy(self.units)
        self.assertEqual(tr.next_unit(rows)["UNIT_ID"], "Q1-0001")
        rows[1]["LABEL"] = "TREE"
        self.assertEqual(tr.next_unit(rows)["UNIT_ID"], "Q6-0001")
        self.assertEqual(tr.next_unit(rows, "Q6_RANDOM")["UNIT_ID"], "Q6-0001")
        self.assertIsNone(tr.next_unit(rows, "Q1_TREE_ON_ROOF"))
        for r in rows:
            r["LABEL"] = "GROUND"
        self.assertIsNone(tr.next_unit(rows))

    def test_answer_validation(self):
        u = self.units[0]
        good = {"LABEL": "tree", "IMAGERY_USABLE": "yes", "REVIEWER": " BB ", "REVIEW_DATE": datetime.date(2026, 9, 29)}
        self.assertEqual(tr.normalize_answer(u, good, self.frame)["LABEL"], "TREE")
        for bad, message in [({"LABEL": "ROOF"}, "domain"), ({"REVIEWER": ""}, "reviewer"),
                             ({"REVIEW_DATE": "2026-13-01"}, "YYYY"), ({"IMAGERY_USABLE": "MAYBE"}, "IMAGERY"),
                             ({"NOTES": "x"*501}, "notes"), ({"REVIEW_DATE": "2030-01-01"}, "future")]:
            with self.assertRaisesRegex(ValueError, message):
                tr.normalize_answer(u, {**good, **bad}, self.frame)
        with self.assertRaisesRegex(ValueError, "domain"):
            tr.normalize_answer(u, good, self.frame, labels=["GROUND"])

    def test_label_inside_the_excluded_domain_is_refused(self):
        near = unit("Q6-0009", X0+510, Y0+500)
        with self.assertRaisesRegex(ValueError, "refused.*evaluation"):
            tr.normalize_answer(near, {"LABEL": "TREE", "REVIEWER": "BB", "REVIEW_DATE": "2026-09-29"}, self.frame)

    def test_snapshot_plan_is_strict(self):
        rows = copy.deepcopy(self.units)
        rows[0].update(LABEL="TREE", REVIEWER="BB", REVIEW_DATE="2026-09-29")
        plan = tr.plan_snapshot(rows, self.units, self.frame)
        self.assertEqual((plan["labelled"], plan["blank"], plan["exportable"]), (1, 2, 1))
        moved = copy.deepcopy(rows); moved[0]["X"] += 1
        with self.assertRaisesRegex(ValueError, "identity"):
            tr.plan_snapshot(moved, self.units, self.frame)
        with self.assertRaisesRegex(ValueError, "missing"):
            tr.plan_snapshot(rows[:2], self.units, self.frame)
        with self.assertRaisesRegex(ValueError, "Duplicate or unknown"):
            tr.plan_snapshot(rows+[unit("ZZ", X0+400, Y0+100)], self.units, self.frame)
        orphan = copy.deepcopy(rows); orphan[1]["IMAGERY_USABLE"] = "YES"; orphan[1]["LABEL"] = None
        with self.assertRaisesRegex(ValueError, "needs a LABEL"):
            tr.plan_snapshot(orphan, self.units, self.frame)
        bad = copy.deepcopy(rows); bad[0]["REVIEWER"] = None
        with self.assertRaisesRegex(ValueError, "reviewer"):
            tr.plan_snapshot(bad, self.units, self.frame)

    def test_snapshot_round_trip_and_tamper_detection(self):
        rows = copy.deepcopy(self.units)
        rows[0].update(LABEL="TREE", REVIEWER="BB", REVIEW_DATE="2026-09-29")
        plan = tr.plan_snapshot(rows, self.units, self.frame)
        packet = {"frame": self.frame, "units": self.units, "units_digest": tr.units_digest(self.units)}
        with tempfile.TemporaryDirectory() as tmp:
            text = tr.snapshot_csv(plan["rows"]).encode()
            Path(tmp, "labels.csv").write_bytes(text)
            import hashlib
            Path(tmp, "snapshot.json").write_text(json.dumps({"labels_csv_sha256": hashlib.sha256(text).hexdigest(),
                                                              "packet_units_digest": packet["units_digest"],
                                                              "frame_digest": self.frame["digest"]}))
            loaded = tr.load_snapshot(tmp, packet)
            self.assertEqual([r["LABEL"] for r in loaded], ["TREE"])
            Path(tmp, "labels.csv").write_bytes(text.replace(b"TREE", b"WALL"))
            with self.assertRaisesRegex(ValueError, "changed"):
                tr.load_snapshot(tmp, packet)


class BackupAndRestore(unittest.TestCase):
    def setUp(self):
        self.frame = frame()
        self.units = [unit("Q6-0001", X0+100, Y0+100, order=2), unit("Q1-0001", X0+150, Y0+100, order=1, queue="Q1_TREE_ON_ROOF"),
                      unit("Q6-0002", X0+300, Y0+100, order=3)]
        for u in self.units:
            u["LABEL"] = u["IMAGERY_USABLE"] = u["REVIEWER"] = u["REVIEW_DATE"] = u["NOTES"] = None

    def rows(self, **answers):
        rows = copy.deepcopy(self.units)
        for uid, values in answers.items():
            next(r for r in rows if r["UNIT_ID"] == uid.replace("_", "-")).update(values)
        return rows

    GOOD = {"LABEL": "TREE", "REVIEWER": "BB", "REVIEW_DATE": "2026-09-29"}

    def test_backup_saves_only_answered_units_in_review_order(self):
        rows = self.rows(Q6_0002=self.GOOD, Q1_0001=dict(self.GOOD, LABEL="WALL", NOTES="a, \"quoted\"\nnote"))
        plan = tr.plan_backup(rows, self.units, self.frame)
        self.assertEqual([r["UNIT_ID"] for r in plan["rows"]], ["Q1-0001", "Q6-0002"])
        self.assertEqual((plan["units"], plan["saved"], plan["labelled"]), (3, 2, 2))
        self.assertEqual(plan["by_label"], {"WALL": 1, "TREE": 1})
        self.assertEqual((plan["flagged"], plan["problems"]), ([], []))
        self.assertEqual({r["CHECK"] for r in plan["rows"]}, {"OK"})

    def test_a_bad_row_is_saved_and_flagged_instead_of_blocking_the_backup(self):
        rows = self.rows(Q1_0001=dict(self.GOOD, REVIEWER=""), Q6_0001=dict(self.GOOD, LABEL="ROOF"),
                         Q6_0002=dict(LABEL="", NOTES="look again"))
        plan = tr.plan_backup(rows, self.units, self.frame)
        self.assertEqual(plan["saved"], 3)                      # nothing lost
        checks = {r["UNIT_ID"]: r["CHECK"] for r in plan["rows"]}
        self.assertIn("reviewer", checks["Q1-0001"])
        self.assertIn("domain", checks["Q6-0001"])
        self.assertIn("no LABEL", checks["Q6-0002"])
        self.assertEqual(len(plan["flagged"]), 3)
        moved = self.rows(Q6_0001=self.GOOD)
        moved[0]["X"] += 5
        self.assertIn("identity field X changed", tr.plan_backup(moved, self.units, self.frame)["rows"][0]["CHECK"])

    def test_unknown_duplicate_and_missing_units_are_reported_not_written(self):
        rows = self.rows(Q6_0001=self.GOOD)
        rows.append(dict(unit("ZZ", X0+400, Y0+100), **self.GOOD))
        rows.append(dict(copy.deepcopy(rows[0])))
        plan = tr.plan_backup(rows, self.units, self.frame)
        self.assertEqual([r["UNIT_ID"] for r in plan["rows"]], ["Q6-0001"])
        self.assertTrue(any("ZZ" in p and "not a unit" in p for p in plan["problems"]))
        self.assertTrue(any("more than once" in p for p in plan["problems"]))
        short = tr.plan_backup(self.rows(Q6_0001=self.GOOD)[:2], self.units, self.frame)
        self.assertTrue(any("missing" in p for p in short["problems"]))

    def test_backup_csv_is_deterministic_and_round_trips(self):
        rows = self.rows(Q6_0002=self.GOOD, Q1_0001=dict(self.GOOD, NOTES="a, \"q\"\nline"))
        first = tr.backup_csv(tr.plan_backup(rows, self.units, self.frame)["rows"])
        second = tr.backup_csv(tr.plan_backup(copy.deepcopy(rows), self.units, self.frame)["rows"])
        self.assertEqual(first, second)                         # unchanged work makes no diff in git
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "labels-progress.csv")
            path.write_bytes(first.encode("utf-8"))
            back = tr.read_backup(path)
            self.assertEqual([r["UNIT_ID"] for r in back], ["Q1-0001", "Q6-0002"])
            self.assertEqual(back[0]["NOTES"], "a, \"q\"\nline")
            path.write_text("UNIT_ID,LABEL\nQ1-0001,TREE\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not a training label backup"):
                tr.read_backup(path)

    def restore(self, live_rows, backup_rows, **kw):
        return tr.plan_restore(backup_rows, live_rows, self.units, self.frame, **kw)

    def test_restore_writes_blank_units_and_leaves_matching_ones(self):
        saved = tr.plan_backup(self.rows(Q6_0002=self.GOOD, Q1_0001=self.GOOD), self.units, self.frame)["rows"]
        plan = self.restore(self.rows(Q1_0001=dict(self.GOOD, NOTES="kept")), saved)
        self.assertEqual([w["UNIT_ID"] for w in plan["write"]], ["Q6-0002"])
        self.assertEqual(plan["unchanged"], ["Q1-0001"])
        self.assertEqual((plan["conflicts"], plan["refused"], plan["replace"]), ([], [], []))

    def test_restore_conflicts_need_replace(self):
        saved = tr.plan_backup(self.rows(Q6_0001=self.GOOD), self.units, self.frame)["rows"]
        live_rows = self.rows(Q6_0001=dict(self.GOOD, LABEL="WALL"))
        plan = self.restore(live_rows, saved)
        self.assertEqual((plan["write"], plan["replace"]), ([], []))
        self.assertTrue(plan["conflicts"] and "WALL" in plan["conflicts"][0])
        plan = self.restore(live_rows, saved, replace=True)
        self.assertEqual([(r["UNIT_ID"], r["was"]) for r in plan["replace"]], [("Q6-0001", "WALL")])
        self.assertEqual(plan["conflicts"], [])

    def test_restore_refuses_bad_rows_without_stopping_good_ones(self):
        saved = tr.plan_backup(self.rows(Q6_0001=self.GOOD, Q1_0001=self.GOOD, Q6_0002=self.GOOD), self.units, self.frame)["rows"]
        by_id = {r["UNIT_ID"]: r for r in saved}
        by_id["Q6-0001"]["UNIT_TOKEN"] = "0" * 16                      # a different packet
        by_id["Q1-0001"]["REVIEWER"] = ""                               # fails the snapshot rules
        plan = self.restore(self.rows(), list(by_id.values()))
        self.assertEqual([w["UNIT_ID"] for w in plan["write"]], ["Q6-0002"])
        reasons = " | ".join(plan["refused"])
        self.assertIn("token", reasons)
        self.assertIn("reviewer", reasons)
        ghost = dict(saved[0], UNIT_ID="ZZ")
        self.assertTrue(self.restore(self.rows(), [ghost])["refused"])
        blank = dict(saved[0], LABEL="")
        self.assertIn("no LABEL", self.restore(self.rows(), [blank])["refused"][0])

    def test_restore_refuses_a_label_in_the_excluded_domain(self):
        near = unit("Q6-0009", X0+510, Y0+500)
        near.update(LABEL=None, IMAGERY_USABLE=None)
        units = self.units + [near]
        row = {"UNIT_ID": "Q6-0009", "QUEUE": near["QUEUE"], "REVIEW_ORDER": near["REVIEW_ORDER"],
               "UNIT_TOKEN": tr.unit_token(self.frame["digest"], near), "LABEL": "TREE", "IMAGERY_USABLE": "",
               "REVIEWER": "BB", "REVIEW_DATE": "2026-09-29", "NOTES": "", "CHECK": "OK"}
        plan = tr.plan_restore([row], copy.deepcopy(units), units, self.frame)
        self.assertEqual(plan["write"], [])
        self.assertIn("evaluation", plan["refused"][0])


class PointCloudExport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.frame = frame()
        pts = []
        for x in (100., 100.5, 103., 300.):
            for z in (0., 5., 12.):
                pts.append((x, 100., z, 2 if z == 0 else 5))
        pts += [(100.2, 100., 6., 7), (100.2, 100.1, 6., 18)]   # noise inside a labelled patch
        self.points = pts
        self.source = self.root/"src.las"
        write_las(self.source, pts)
        self.units = [unit("A", X0+100, Y0+100, "TREE", zlow=4., zhigh=13.), unit("B", X0+300, Y0+100, "UNSURE"),
                      unit("C", X0+103, Y0+100, "GROUND", zlow=-1, zhigh=1)]

    def tearDown(self):
        self.tmp.cleanup()

    def test_labelled_slabs_get_codes_noise_kept_rest_ignored(self):
        from canopy import las_records
        before = self.source.read_bytes()
        out = self.root/"out"/"train.las"
        counts = tr.export_training_las(self.source, out, self.units, self.frame)
        self.assertEqual(self.source.read_bytes(), before)
        classes = np.asarray(las_records.records(out)[0]["classification"])
        expected = []
        for x, _, z, c in self.points:
            if c in (7, 18):
                expected.append(c)
            elif x in (100., 100.5) and 4 <= z <= 13:
                expected.append(5)
            elif x == 103. and z == 0:
                expected.append(2)
            else:
                expected.append(tr.IGNORE_CODE)
        self.assertEqual(classes.tolist(), expected)
        self.assertEqual(counts["units_exported"], 2)
        self.assertEqual(counts["points_per_unit"], {"A": 4, "C": 1})
        check = tr.verify_only_classes_changed(self.source, out)
        self.assertEqual(check["records"], len(self.points))
        with self.assertRaises(FileExistsError):
            tr.export_training_las(self.source, out, self.units, self.frame)

    def test_refusals(self):
        legacy = self.root/"legacy.las"
        write_las(legacy, self.points, modern=False)
        with self.assertRaisesRegex(ValueError, "legacy"):
            tr.export_training_las(legacy, self.root/"a.las", self.units, self.frame)
        near_eval = [unit("X", X0+505, Y0+500, "TREE")]
        with self.assertRaisesRegex(ValueError, "refused"):
            tr.export_training_las(self.source, self.root/"b.las", near_eval, self.frame)
        overlap = [unit("A", X0+100, Y0+100, "TREE"), unit("D", X0+101, Y0+100, "WALL")]
        with self.assertRaisesRegex(ValueError, "overlap"):
            tr.export_training_las(self.source, self.root/"c.las", overlap, self.frame)
        self.assertFalse(any(self.root.glob("[abc].las*")))

    def test_split_and_prepare_parameters(self):
        units = [unit(f"U{i}", X0+25+50*i, Y0+25) for i in range(10)]
        split, squares = tr.point_split(units)
        self.assertEqual(sum(v == "VALIDATION" for v in split.values()), 2)
        self.assertEqual(len(squares["TRAINING"])+len(squares["VALIDATION"]), 10)
        self.assertEqual((split, squares), tr.point_split(list(reversed(units))))
        params = tr.prepare_parameters("t.lasd", "tb", "vb")
        self.assertEqual(params["excluded_class_codes"], [tr.IGNORE_CODE, 7, 18])
        self.assertNotIn(tr.IGNORE_CODE, params["class_codes_of_interest"])

    def test_label_codes_avoid_review_code_ranges(self):
        codes = [v[1] for v in tr.LABELS.values() if v[1] is not None]
        self.assertEqual(len(codes), len(set(codes)))
        self.assertFalse(set(codes) & set(range(64, 72)))
        self.assertNotIn(tr.IGNORE_CODE, codes)
        self.assertEqual(sorted(tr.IMAGERY_CLASS.values()), list(range(1, len(tr.EXPORT_LABELS)+1)))


if __name__ == "__main__":
    unittest.main()
