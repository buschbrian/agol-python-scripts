import unittest

import numpy as np

from canopy import fractal_compare as fc


class Comparison(unittest.TestCase):
    def patch(self, codes, strict=None, label="TREE", centre=(10, 10), bounds=(0, 0, 20, 20)):
        n = len(codes)
        unit = {"UNIT_ID": "fixture", "LABEL": label, "X": centre[0], "Y": centre[1], "Z_LOW": 1, "Z_HIGH": 3}
        tied = np.asarray(codes) == 0
        strict = ~tied if strict is None else np.asarray(strict, bool)
        shares = np.where(strict, 1, 1 / 3)
        return fc.patch_comparison(unit, np.full(n, 10), np.full(n, 10), np.full(n, 2),
                                   np.asarray(codes), shares, tied, strict, bounds)

    def test_tree_and_shrub_only_agree_at_vegetation_level(self):
        for label in ("TREE", "SHRUB_LOW_VEG"):
            row = self.patch([5] * 12, label=label)
            self.assertEqual(row["MODEL_FAMILY"], "VEGETATION")
            self.assertTrue(row["AGREE"])

    def test_ties_and_weak_point_votes_stay_in_denominator(self):
        row = self.patch([5] * 6 + [0] * 6)
        self.assertEqual(row["STATUS"], "ABSTAIN")
        self.assertFalse(row["AGREE"])
        row = self.patch([5] * 12, strict=[True] * 6 + [False] * 6)
        self.assertEqual(row["STATUS"], "ABSTAIN")
        self.assertEqual(row["WEAK_POINTS"], 6)

    def test_sparse_and_partial_patches_are_not_scored(self):
        self.assertEqual(self.patch([5] * 11)["STATUS"], "INSUFFICIENT_POINTS")
        self.assertEqual(self.patch([5] * 12, bounds=(10, 0, 20, 20))["STATUS"], "PARTIAL_COVERAGE")

    def test_structure_labels_are_not_forced_into_roof_mapping(self):
        for label in ("OTHER_STRUCTURE", "WALL", "POLE", "WIRE", "VEHICLE", "MIXED", "UNSURE"):
            row = self.patch([6] * 12, label=label)
            self.assertEqual(row["STATUS"], "LABEL_NOT_COMPARABLE")
            self.assertIsNone(row["AGREE"])

    def test_summary_retains_abstentions(self):
        result = fc.summarize([self.patch([5] * 12), self.patch([0] * 12), self.patch([6] * 12)])
        self.assertEqual(result["by_label"]["TREE"]["agreement"], 1 / 3)
        self.assertEqual(result["by_label"]["TREE"]["abstain"], 1)

    def test_radius_and_height_slab_are_both_applied(self):
        unit = {"UNIT_ID": "fixture", "LABEL": "GROUND", "X": 10, "Y": 10, "Z_LOW": 1, "Z_HIGH": 3}
        row = fc.patch_comparison(unit, [10] * 12 + [15, 10], [10] * 14, [2] * 12 + [2, 5],
                                  np.array([2] * 12 + [5, 5]), np.ones(14), np.zeros(14), np.ones(14), (0, 0, 20, 20))
        self.assertEqual(row["PATCH_POINTS"], 12)
        self.assertTrue(row["AGREE"])

    def test_vote_field_validation(self):
        fc.validate_consensus([5, 0, 2], [1, 1 / 3, 2 / 3], [0, 1, 0], [1, 0, 1], 3)
        for args in (([65], [1], [0], [1], 3), ([5], [0.9], [0], [1], 3),
                     ([0], [1 / 3], [0], [0], 3), ([5], [1], [0], [0], 3),
                     ([5], [float("nan")], [0], [1], 3)):
            with self.assertRaises(ValueError):
                fc.validate_consensus(*args)


if __name__ == "__main__":
    unittest.main()
