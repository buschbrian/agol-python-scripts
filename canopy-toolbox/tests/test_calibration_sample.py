import importlib.util
from pathlib import Path
import unittest

import numpy as np

from canopy import training_review as tr

REVIEWS = Path(__file__).resolve().parents[1]/"reviews"/"2026-10-15"
spec = importlib.util.spec_from_file_location("calibration_sample", REVIEWS/"calibration_sample.py")
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)


def row(**flags):
    base = {k: "0" for k in ("WIRE_HINT", "WALL_HINT", "FLAT_TOP", "ROOF_HEIGHT", "POLE_HINT")}
    base.update({k: "1" for k, v in flags.items() if v})
    return base


def frame():
    units = [{"sample": "treetop", "SAMPLE_ID": "T1", "TILE": "12TVL2804", "x": 428500.0, "y": 4504500.0}]
    plots = [{"PLOT_ID": "P1", "TILE": "12TVL2804",
              "rings": [[(428100, 4504100), (428140, 4504100), (428140, 4504140), (428100, 4504140), (428100, 4504100)]]}]
    return tr.exclusion_frame(units, plots)


class StratumTest(unittest.TestCase):
    def test_priority(self):
        self.assertEqual(cs.stratum(row(WIRE_HINT=1, ROOF_HEIGHT=1)), "WIRE")
        self.assertEqual(cs.stratum(row(WALL_HINT=1, FLAT_TOP=1)), "WALL")
        self.assertEqual(cs.stratum(row(FLAT_TOP=1, ROOF_HEIGHT=1)), "FLAT_TOP")
        self.assertEqual(cs.stratum(row(ROOF_HEIGHT=1, POLE_HINT=1)), "ROOF_HEIGHT")
        self.assertEqual(cs.stratum(row(POLE_HINT=1)), "POLE_ONLY")
        self.assertEqual(cs.stratum(row()), "UNFLAGGED")


class ExclusionTest(unittest.TestCase):
    def test_reasons(self):
        f = frame()
        x = np.array([428500.0+25.5, 428500.0+26.5, 428120.0, 428170.0, 433500.0, 422500.0, 429500.0])
        y = np.array([4504500.0, 4504500.0, 4504120.0, 4504120.0, 4502500.0, 4503500.0, 4504800.0])
        reason = cs.excluded_reason(x, y, f, [(429501.0, 4504801.0)])
        self.assertEqual(reason[0], "evaluation buffer")          # 25.5 m < 25 m buffer + 1 m top radius
        self.assertEqual(reason[1], "")
        self.assertEqual(reason[2], "evaluation buffer")          # inside a census plot: distance 0
        self.assertEqual(reason[3], "")                            # 30 m from the plot edge
        self.assertTrue(reason[4].startswith("excluded tile 12TVL3302"))
        self.assertTrue(reason[5].startswith("excluded tile 12TVL2203"))
        self.assertEqual(reason[6], "near a seen training unit")

    def test_altered_frame_is_refused(self):
        f = frame()
        f["buffer_m"] = 1.0
        with self.assertRaises(ValueError):
            cs.excluded_reason([0.0], [0.0], f, [])


class DrawTest(unittest.TestCase):
    def test_reproducible_and_spaced(self):
        xy = np.c_[np.arange(200)*1.0, np.zeros(200)]
        ids = [f"t{i:03d}" for i in range(200)]
        a = cs.draw_stratum(ids, xy, 30, np.random.default_rng(5), [])
        b = cs.draw_stratum(ids, xy, 30, np.random.default_rng(5), [])
        self.assertEqual(a, b)
        chosen = np.sort(xy[a, 0])
        self.assertEqual(len(a), 30)
        self.assertTrue(np.all(np.diff(chosen) >= cs.MIN_SPACING_M))

    def test_spacing_applies_across_strata(self):
        taken = [(0.0, 0.0)]
        got = cs.draw_stratum(["a", "b"], np.array([[1.0, 0.0], [10.0, 0.0]]), 2, np.random.default_rng(1), taken)
        self.assertEqual(got, [1])


class ScoreTest(unittest.TestCase):
    def test_clopper_pearson(self):
        lo, hi = cs.clopper_pearson(0, 10)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.3085, places=4)
        lo, hi = cs.clopper_pearson(5, 10)
        self.assertAlmostEqual(lo, 0.1871, places=4)
        self.assertAlmostEqual(hi, 0.8129, places=4)
        self.assertEqual(cs.clopper_pearson(0, 0), (0.0, 1.0))

    def sample(self, per=40):
        units, n = [], 0
        for s in cs.STRATA:
            for _ in range(per):
                n += 1
                units.append({"UNIT_ID": f"C1-{n:04d}", "ORDER": n, "TREE_ID": f"t{n}", "STRATUM": s})
        return {"units": units, "populations": {"citywide": {s: 1000 for s in cs.STRATA}}}

    def test_partial_scores_and_mixed_is_apart(self):
        sample = self.sample()
        roof = [u["UNIT_ID"] for u in sample["units"] if u["STRATUM"] == "ROOF_HEIGHT"]
        labels = {roof[0]: "TREE", roof[1]: "BUILDING_ROOF", roof[2]: "MIXED", roof[3]: ""}
        s = cs.score(sample, labels)["strata"]["ROOF_HEIGHT"]
        self.assertEqual((s["labelled"], s["definite"], s["not_tree"], s["mixed_or_unsure"]), (3, 2, 1, 1))
        self.assertFalse(s["measured"])
        self.assertIsNone(cs.score(sample, labels)["suspect_not_tree_projection"])

    def test_projection_when_every_suspect_stratum_is_measured(self):
        sample = self.sample(per=30)
        labels = {}
        for u in sample["units"]:
            labels[u["UNIT_ID"]] = "BUILDING_ROOF" if u["STRATUM"] in cs.SUSPECT_STRATA and int(u["UNIT_ID"][3:]) % 2 \
                else "TREE"
        out = cs.score(sample, labels)
        self.assertTrue(all(out["strata"][s]["measured"] for s in cs.SUSPECT_STRATA))
        self.assertEqual(out["suspect_not_tree_projection"]["estimate"], 2000)

    def test_unknown_units_and_labels_are_refused(self):
        sample = self.sample()
        with self.assertRaises(ValueError):
            cs.score(sample, {"C9-9999": "TREE"})
        with self.assertRaises(ValueError):
            cs.score(sample, {"C1-0001": "TREEE"})


class MergeLabelsTest(unittest.TestCase):
    @staticmethod
    def row(uid, label, reviewer="BB"):
        return {"UNIT_ID": uid, "LABEL": label, "REVIEWER": reviewer, "REVIEW_DATE": "2026-10-22", "NOTE": ""}

    def test_new_and_unchanged(self):
        existing = {"C2-0001": self.row("C2-0001", "TREE"), "C2-0002": self.row("C2-0002", "")}
        merged, report = cs.merge_labels(existing, {"C2-0001": self.row("C2-0001", "TREE", "XX"),
                                                    "C2-0002": self.row("C2-0002", "WIRE")})
        self.assertEqual((report["new"], report["unchanged"], report["conflicts"]), (1, 1, []))
        self.assertEqual(merged["C2-0002"]["LABEL"], "WIRE")
        self.assertEqual(merged["C2-0001"]["REVIEWER"], "XX")

    def test_a_label_is_never_changed_or_blanked_without_replace(self):
        existing = {"C2-0001": self.row("C2-0001", "TREE"), "C2-0002": self.row("C2-0002", "WALL")}
        incoming = {"C2-0001": self.row("C2-0001", ""), "C2-0002": self.row("C2-0002", "POLE")}
        merged, report = cs.merge_labels(existing, incoming)
        self.assertEqual(len(report["conflicts"]), 2)
        self.assertEqual((merged["C2-0001"]["LABEL"], merged["C2-0002"]["LABEL"]), ("TREE", "WALL"))
        merged, report = cs.merge_labels(existing, incoming, replace=True)
        self.assertEqual(report["replaced"], 2)
        self.assertEqual((merged["C2-0001"]["LABEL"], merged["C2-0002"]["LABEL"]), ("", "POLE"))


if __name__ == "__main__":
    unittest.main()
