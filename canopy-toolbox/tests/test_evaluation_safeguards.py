"""Regression safeguards for evaluating candidate and crown changes. No arcpy."""
import unittest

import numpy as np

from canopy import validation_metrics as vm


class CandidateMatching(unittest.TestCase):
    def assert_matches(self, result, baseline, variant):
        np.testing.assert_array_equal(result["baseline_to_variant"], baseline)
        np.testing.assert_array_equal(result["variant_to_baseline"], variant)
        self.assertTrue(np.issubdtype(result["baseline_to_variant"].dtype, np.integer))
        self.assertTrue(np.issubdtype(result["variant_to_baseline"].dtype, np.integer))

    def test_merged_candidates_retain_only_one_baseline_candidate(self):
        result = vm.match_candidates([[0, 0], [1, 0]], [[.2, 0]], .9)
        self.assert_matches(result, [0, -1], [0])
        self.assertEqual(result["ambiguous_baseline"], 0)
        self.assertEqual(result["ambiguous_variant"], 1)

    def test_maximum_cardinality_precedes_nearest_neighbor(self):
        result = vm.match_candidates([[0, 0], [1, 0]], [[.4, 0], [-.6, 0]], .7)
        self.assert_matches(result, [1, 0], [1, 0])

    def test_minimum_distance_resolves_multiple_full_matchings(self):
        result = vm.match_candidates([[0, 0], [3, 0]], [[1, 0], [2, 0]], 3)
        self.assert_matches(result, [0, 1], [0, 1])
        self.assertEqual(result["ambiguous_baseline"], 2)
        self.assertEqual(result["ambiguous_variant"], 2)

    def test_stable_identity_precedes_distance_when_it_is_in_radius(self):
        result = vm.match_candidates([[0, 0], [1, 0]], [[.9, 0], [.1, 0]], 1,
                                     baseline_ids=["A", "B"], variant_ids=["A", "B"])
        self.assert_matches(result, [0, 1], [0, 1])

    def test_identity_does_not_match_a_candidate_outside_radius(self):
        result = vm.match_candidates([[0, 0]], [[10, 0]], 1,
                                     baseline_ids=["A"], variant_ids=["A"])
        self.assert_matches(result, [-1], [-1])

    def test_boundary_is_inclusive(self):
        result = vm.match_candidates([[0, 0]], [[3, 4]], 5)
        self.assert_matches(result, [0], [0])

    def test_empty_frames_preserve_mapping_lengths(self):
        for baseline, variant, expected_baseline, expected_variant in (
                ([], [], [], []), ([], [[0, 0]], [], [-1]),
                ([[0, 0]], [], [-1], [])):
            with self.subTest(baseline=baseline, variant=variant):
                result = vm.match_candidates(baseline, variant, 1)
                self.assert_matches(result, expected_baseline, expected_variant)
                self.assertEqual(result["ambiguous_baseline"], 0)
                self.assertEqual(result["ambiguous_variant"], 0)

    def test_xy_translation_does_not_change_matching(self):
        baseline = np.array([[0, 0], [1, 0]], dtype=float)
        variant = np.array([[.4, 0], [-.6, 0]], dtype=float)
        offset = np.array([422350, 4503350])
        local = vm.match_candidates(baseline, variant, .7)
        projected = vm.match_candidates(baseline + offset, variant + offset, .7)
        self.assert_matches(projected, local["baseline_to_variant"], local["variant_to_baseline"])

    def test_duplicate_ids_are_rejected_on_either_side(self):
        for baseline_ids, variant_ids in ((["A", "A"], ["A", "B"]),
                                           (["A", "B"], ["A", "A"])):
            with self.subTest(baseline_ids=baseline_ids, variant_ids=variant_ids):
                with self.assertRaises(ValueError):
                    vm.match_candidates([[0, 0], [1, 0]], [[0, 0], [1, 0]], 1,
                                        baseline_ids=baseline_ids, variant_ids=variant_ids)

    def test_nonfinite_coordinates_are_rejected_on_either_side(self):
        for value in (np.nan, np.inf, -np.inf):
            for baseline, variant in (([[value, 0]], [[0, 0]]),
                                       ([[0, 0]], [[0, value]])):
                with self.subTest(value=value, baseline=baseline):
                    with self.assertRaises(ValueError):
                        vm.match_candidates(baseline, variant, 1)


class EvaluationIntervals(unittest.TestCase):
    def test_invalid_populations_and_labels_are_rejected(self):
        sample = [{"stratum": "A", "label": "TREE", "retained": True}]
        for population in (0, -1, .5, np.nan):
            with self.subTest(population=population), self.assertRaises(ValueError):
                vm.score_treetops(sample, {"A": population}, replicates=20)
        with self.assertRaises(ValueError):
            vm.score_treetops([{**sample[0], "label": "TRE"}], {"A": 10})

    def test_complete_census_has_exact_interval(self):
        result = vm.score_treetops([{"stratum": "A", "label": "TREE", "retained": True}],
                                  {"A": 1}, variant_candidates=1, replicates=20)
        interval = result["estimates"]["precision"]
        self.assertEqual((interval["low"], interval["high"], interval["interval_status"]), (1, 1, "CENSUS"))

    def test_five_agreeing_labels_do_not_claim_a_zero_width_interval(self):
        for label, expected in (("TREE", 1.0), ("ROOF_OR_BUILDING", 0.0)):
            with self.subTest(label=label):
                sample = [{"stratum": "A", "label": label, "retained": True} for _ in range(5)]
                result = vm.score_treetops(sample, {"A": 100}, replicates=100, seed=7)
                for metric in ("precision", "baseline_precision"):
                    interval = result["estimates"][metric]
                    self.assertEqual(interval["estimate"], expected)
                    if interval["low"] is None or interval["high"] is None:
                        self.assertIsNone(interval["low"])
                        self.assertIsNone(interval["high"])
                        self.assertTrue(interval.get("interval_status"))
                        self.assertNotEqual(interval["interval_status"], "OK")
                    else:
                        self.assertLess(interval["low"], interval["high"])
                        self.assertLessEqual(interval["low"], expected)
                        self.assertGreaterEqual(interval["high"], expected)

    def test_conflicting_exact_variant_count_is_rejected(self):
        sample = [{"stratum": "A", "label": "TREE", "retained": True} for _ in range(5)]
        with self.assertRaises(ValueError):
            vm.score_treetops(sample, {"A": 100}, variant_candidates=1, replicates=20)

    def test_new_candidates_cannot_exceed_exact_variant_count(self):
        sample = [{"stratum": "A", "label": None, "retained": False}]
        with self.assertRaises(ValueError):
            vm.score_treetops(sample, {"A": 100}, new_candidates=2, variant_candidates=1)


class CrownScope(unittest.TestCase):
    def test_selective_changes_keep_original_stratum_design_weights(self):
        # A represents 100 crowns with two respondents: one kept correct, one changed.
        # B represents 50 with two respondents: both kept, neither correct.
        # Retained weights are 50 for A and 25 + 25 for B, so correct share is 1/2.
        sample = [{"stratum": "A", "label": "CORRECT", "roof": "NO", "same": True},
                  {"stratum": "A", "label": "NOT_A_TREE", "roof": "YES", "same": False},
                  {"stratum": "B", "label": "MERGED", "roof": "NO", "same": True},
                  {"stratum": "B", "label": "SPLIT", "roof": "YES", "same": True}]
        result = vm.score_crowns(sample, {"A": 100, "B": 50}, replicates=50)
        estimates = result["estimates"]
        self.assertAlmostEqual(estimates["share_correct"]["estimate"], .5)
        self.assertAlmostEqual(estimates["share_merged"]["estimate"], .25)
        self.assertAlmostEqual(estimates["share_split"]["estimate"], .25)
        self.assertAlmostEqual(estimates["share_includes_roof"]["estimate"], .25)
        self.assertEqual(result["changed_by_run"], 1)
        self.assertEqual(result["status"], "PARTIAL")

    def test_selective_label_transfer_identifies_its_conditional_scope(self):
        sample = [{"stratum": "A", "label": "CORRECT", "roof": "NO", "same": True},
                  {"stratum": "A", "label": "NOT_A_TREE", "roof": "YES", "same": False}]
        result = vm.score_crowns(sample, {"A": 100}, replicates=20)
        self.assertEqual(result["changed_by_run"], 1)
        self.assertEqual(result["usable"], 1)
        self.assertEqual(result.get("estimand_scope"), "UNCHANGED_MATCHED_BASELINE_CROWNS")
        rows = vm.comparison_rows({("variant", "tile"): {"crowns": result}})
        row = next(row for row in rows if row["key"] == "crowns.share_correct")
        self.assertIn("unchanged", row["metric"].lower())


if __name__ == "__main__":
    unittest.main()
