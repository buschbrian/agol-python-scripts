"""Validation estimators on synthetic labels with hand-computed answers. No arcpy."""
import importlib.util
import unittest

import numpy as np

from canopy import validation_metrics as vm


def units(stratum, labels, **flags):
    """Units for one stratum; flags are per-unit lists or scalars."""
    out = []
    for i, label in enumerate(labels):
        unit = {"stratum": stratum, "label": label}
        for key, value in flags.items():
            unit[key] = value[i] if isinstance(value, (list, tuple)) else value
        out.append(unit)
    return out


def est(result, key):
    return result["estimates"][key]["estimate"]


class Intervals(unittest.TestCase):
    def test_wilson_matches_published_values(self):
        p, low, high = vm.wilson(5, 10)
        self.assertAlmostEqual(p, .5)
        self.assertAlmostEqual(low, .2366, places=4)
        self.assertAlmostEqual(high, .7634, places=4)
        p, low, high = vm.wilson(0, 10)
        self.assertEqual((p, low), (0, 0))
        self.assertAlmostEqual(high, .2775, places=4)
        self.assertEqual(vm.wilson(0, 0), (None, None, None))

    def test_bootstrap_is_seeded_and_suppressed_when_labels_agree(self):
        population = {"A": 500, "B": 50}
        sample = units("A", ["TREE"]*6 + ["ROOF_OR_BUILDING"]*4, retained=True) + \
            units("B", ["TREE"]*5 + ["GROUND_OR_OPEN"]*5, retained=True)
        first = vm.score_treetops(sample, population, replicates=400, seed=3)
        second = vm.score_treetops(sample, population, replicates=400, seed=3)
        self.assertEqual(first["estimates"], second["estimates"])
        precision = first["estimates"]["precision"]
        self.assertLess(precision["low"], precision["estimate"])
        self.assertGreater(precision["high"], precision["estimate"])
        constant = vm.score_treetops(units("A", ["TREE"]*8, retained=True), {"A": 90}, replicates=200)
        entry = constant["estimates"]["precision"]
        self.assertEqual((entry["estimate"], entry["low"], entry["high"]), (1.0, None, None))
        self.assertEqual(entry["interval_status"], "HOMOGENEOUS_OR_DEGENERATE_SAMPLE")


class Treetops(unittest.TestCase):
    population = {"A": 1000, "B": 100}

    def sample(self):
        # A: 2 trees, 8 roofs; the variant removes 6 roofs. B: 9 trees, 1 pole; the
        # variant removes one tree. Extra unlabelled and UNSURE units must be ignored.
        a = units("A", ["TREE"]*2 + ["ROOF_OR_BUILDING"]*8, retained=[True]*4 + [False]*6)
        a += units("A", [None, None, None, "UNSURE"], retained=True)
        b = units("B", ["TREE"]*9 + ["OTHER_STRUCTURE"], retained=[False] + [True]*9)
        return a + b

    def test_baseline_precision_is_stratum_weighted(self):
        baseline = [dict(u, retained=True) for u in self.sample()]
        result = vm.score_treetops(baseline, self.population, replicates=200)
        self.assertEqual(result["status"], "OK")
        self.assertEqual((result["usable"], result["unsure"], result["labelled"]), (20, 1, 21))
        self.assertAlmostEqual(est(result, "precision"), 290/1100)
        self.assertAlmostEqual(est(result, "false_removed"), 0)
        self.assertAlmostEqual(est(result, "candidates_kept"), 1100)
        row = result["per_stratum"]["A"]
        self.assertEqual((row["usable"], row["successes"], row["unsure"], row["sampled"]), (10, 2, 1, 14))
        self.assertAlmostEqual(row["share"], .2)

    def test_variant_counts_false_and_true_removals(self):
        result = vm.score_treetops(self.sample(), self.population, new_candidates=10, replicates=200)
        self.assertAlmostEqual(est(result, "precision"), 280/490)
        self.assertAlmostEqual(est(result, "baseline_precision"), 290/1100)
        self.assertAlmostEqual(est(result, "false_removed"), 600)
        self.assertAlmostEqual(est(result, "true_removed"), 10)
        self.assertAlmostEqual(est(result, "false_kept"), 210)
        self.assertAlmostEqual(est(result, "share_of_false_removed"), 600/810)
        self.assertAlmostEqual(est(result, "precision_if_new_false"), 280/500)
        self.assertAlmostEqual(est(result, "precision_if_new_true"), 290/500)
        # Per-stratum precision covers only the candidates the run kept.
        self.assertAlmostEqual(result["per_stratum"]["A"]["share"], .5)

    def test_no_labels_and_partial_labels(self):
        empty = vm.score_treetops(units("A", [None]*5, retained=True), self.population)
        self.assertEqual(empty["status"], "NO_LABELS")
        self.assertNotIn("estimates", empty)
        partial = vm.score_treetops(units("A", ["TREE", "ROOF_OR_BUILDING"], retained=True),
                                    self.population, replicates=100)
        self.assertEqual(partial["status"], "PARTIAL")
        self.assertEqual(partial["strata_without_labels"], ["B"])
        self.assertAlmostEqual(partial["population_coverage"], 1000/1100)
        self.assertTrue(partial["per_stratum"]["A"]["unstable"])

    def test_unknown_stratum_is_refused(self):
        with self.assertRaises(ValueError):
            vm.score_treetops(units("Z", ["TREE"], retained=True), self.population)


class Cells(unittest.TestCase):
    def test_commission_omission_and_area_bias(self):
        population = {"CAN": 800, "NON": 3200}
        sample = units("CAN", ["TREE"]*8 + ["ROOF_OR_BUILDING", "SHRUB_UNDER_2M"], canopy=True) + \
            units("NON", ["TREE"] + ["GROUND_OR_OPEN"]*9, canopy=False)
        result = vm.score_cells(sample, population, .25, mapped_in_frame=800, replicates=200)
        self.assertAlmostEqual(est(result, "commission"), .2)
        self.assertAlmostEqual(est(result, "omission"), 320/960)
        self.assertAlmostEqual(est(result, "true_canopy_m2"), 240)
        self.assertAlmostEqual(est(result, "mapped_canopy_m2"), 200)
        self.assertAlmostEqual(est(result, "area_bias_m2"), -40)
        self.assertAlmostEqual(est(result, "relative_bias"), -160/960)
        self.assertEqual(result["mapped_canopy_m2_in_frame"], 200)

    def test_variant_that_drops_false_canopy(self):
        population = {"CAN": 800, "NON": 3200}
        sample = units("CAN", ["TREE"]*8 + ["ROOF_OR_BUILDING"]*2, canopy=[True]*8 + [False]*2) + \
            units("NON", ["TREE"] + ["GROUND_OR_OPEN"]*9, canopy=False)
        result = vm.score_cells(sample, population, .25, replicates=200)
        self.assertAlmostEqual(est(result, "commission"), 0)
        self.assertAlmostEqual(est(result, "mapped_canopy_m2"), 160)
        self.assertAlmostEqual(est(result, "area_bias_m2"), -80)


class Omission(unittest.TestCase):
    population = {"OM_ROOF": 400, "OM_OPEN": 600}

    def sample(self, recovered):
        return units("OM_ROOF", ["TREE", "ROOF_OR_BUILDING", "ROOF_OR_BUILDING", "ROOF_OR_BUILDING",
                                 "UNSURE"], canopy=[recovered, False, False, False, False],
                     candidate_near=False) + \
            units("OM_OPEN", ["GROUND_OR_OPEN"]*5, canopy=False, candidate_near=False)

    def test_missed_canopy_area(self):
        result = vm.score_omission(self.sample(False), self.population, .25, replicates=200)
        self.assertAlmostEqual(est(result, "tree_share_of_noncanopy"), 100/1000)
        self.assertAlmostEqual(est(result, "baseline_missed_m2"), 25)
        self.assertAlmostEqual(est(result, "missed_m2"), 25)
        self.assertAlmostEqual(est(result, "missed_without_nearby_candidate_m2"), 25)

    def test_recovery_by_a_variant(self):
        result = vm.score_omission(self.sample(True), self.population, .25, replicates=200)
        self.assertAlmostEqual(est(result, "missed_m2"), 0)
        self.assertAlmostEqual(est(result, "recovered_m2"), 25)

    def test_combined_rate_uses_canopy_strata_of_the_cell_sample(self):
        cells = units("T|CANOPY_FAR", ["TREE"]*3 + ["ROOF_OR_BUILDING"], canopy=True) + \
            units("T|NONCAN_FAR", ["TREE"]*4, canopy=False)
        cell_pop = {"T|CANOPY_FAR": 400, "T|NONCAN_FAR": 1000}
        omission = units("T|OM_OPEN", ["TREE", "GROUND_OR_OPEN", "GROUND_OR_OPEN", "GROUND_OR_OPEN"],
                         canopy=False)
        result = vm.combined_omission_rate(cells, cell_pop, omission, {"T|OM_OPEN": 1000}, replicates=200)
        # Hits 400 * 3/4 = 300; misses 1000 * 1/4 = 250 (the NONCAN cell stratum is not used).
        self.assertAlmostEqual(result["omission_rate"]["estimate"], 250/550)


class Crowns(unittest.TestCase):
    def test_shares_roof_and_changed_crowns(self):
        population = {"S": 100, "L": 50}
        sample = units("S", ["CORRECT", "CORRECT", "SPLIT", "NOT_A_TREE"],
                       roof=["YES", "NO", "NO", "UNSURE"], same=True) + \
            units("L", ["MERGED", "CORRECT", "CORRECT"], roof=["NO", "NO", "YES"],
                  same=[True, True, False])
        result = vm.score_crowns(sample, population, replicates=200)
        self.assertEqual(result["changed_by_run"], 1)
        # All labelled respondents retain their N/n weights. L contributes 50/3
        # per unchanged crown, rather than redistributing changed-crown weight.
        denominator = 100 + 50*2/3
        self.assertAlmostEqual(est(result, "share_correct"), (50 + 50/3)/denominator)
        self.assertAlmostEqual(est(result, "share_merged"), (50/3)/denominator)
        self.assertAlmostEqual(est(result, "share_split"), 25/denominator)
        self.assertAlmostEqual(est(result, "share_not_a_tree"), 25/denominator)
        self.assertAlmostEqual(est(result, "share_includes_roof"), 25/(75 + 50*2/3))


class Sampling(unittest.TestCase):
    def test_draw_is_reproducible_and_order_independent(self):
        keys = [f"id{i}" for i in range(200)]
        first = vm.draw(keys, 30, vm.seed_for(1, "treetop", "T", "A"))
        self.assertEqual(first, vm.draw(list(reversed(keys)), 30, vm.seed_for(1, "treetop", "T", "A")))
        self.assertEqual(len(set(first)), 30)
        self.assertNotEqual(first, vm.draw(keys, 30, vm.seed_for(2, "treetop", "T", "A")))
        self.assertEqual(sorted(vm.draw(keys[:5], 30, 1)), keys[:5])
        self.assertEqual(vm.draw([], 30, 1), [])
        self.assertEqual(len(vm.draw(np.arange(4_000_000), 30, 9)), 30)
        with self.assertRaises(ValueError):
            vm.draw(["a", "a"], 1, 1)

    def test_review_order_prefix_is_balanced(self):
        units_ = [(f"a{i}", "A") for i in range(40)] + [(f"b{i}", "B") for i in range(7)]
        order = vm.review_order(units_, 5)
        self.assertEqual(sorted(o for o, _ in order.values()), list(range(1, 48)))
        batch1 = [k for k, (o, b) in order.items() if b == 1]
        self.assertEqual(len([k for k in batch1 if k.startswith("a")]), 20)
        self.assertEqual(len([k for k in batch1 if k.startswith("b")]), 4)
        self.assertTrue(max(order[k][0] for k in batch1) < min(o for o, b in order.values() if b == 2))
        self.assertEqual(order, vm.review_order(units_, 5))

    def test_treetop_and_crown_strata(self):
        self.assertEqual(vm.treetop_context(None, 5, None), "AWAY")
        self.assertEqual(vm.treetop_context(1.5, 5, 5.0), "AWAY")
        self.assertEqual(vm.treetop_context(.5, 5.5, 5.0), "ROOF_LEVEL")
        self.assertEqual(vm.treetop_context(1.0, 5.75, 5.0), "ROOF_MID")
        self.assertEqual(vm.treetop_context(.5, 7.0, 5.0), "ROOF_MID")
        self.assertEqual(vm.treetop_context(.5, 7.25, 5.0), "ABOVE_ROOF")
        self.assertEqual(vm.treetop_context(.5, 7.0, None), "ROOF_MID")
        self.assertEqual(vm.treetop_stratum(1, "ROOF_LEVEL", 1), "SEAM")
        self.assertEqual(vm.treetop_stratum(0, "ROOF_LEVEL", 1), "ROOF_LEVEL")
        self.assertEqual(vm.treetop_stratum(0, "AWAY", 2.75), "SMALL_CROWN")
        self.assertEqual(vm.treetop_stratum(0, "AWAY", 3.0), "NORMAL")
        self.assertEqual(vm.crown_stratum(80, 1.0), "CR_BLDG")
        self.assertEqual(vm.crown_stratum(9.75, .75), "CR_SMALL")
        self.assertEqual(vm.crown_stratum(10, 0), "CR_MEDIUM")
        self.assertEqual(vm.crown_stratum(50, 0), "CR_LARGE")

    @unittest.skipUnless(importlib.util.find_spec("scipy"), "SciPy required")
    def test_cell_strata_partition_the_grid(self):
        chm = np.zeros((80, 80))
        chm[5:35, 5:35] = 8           # 15 m canopy block
        chm[20, 20] = 0.5             # gap inside dense canopy
        chm[60:63, 60:63] = np.nan    # unobserved
        building = np.zeros_like(chm, dtype=bool)
        building[45:49, 2:6] = True
        chm[45:49, 2:6] = 0           # roof: observed non-canopy
        omission, cells, bdist, cdist = vm.cell_strata(chm, building, .5)
        self.assertEqual(omission[20, 20], "OM_DENSE")
        self.assertEqual(omission[46, 3], "OM_ROOF")
        self.assertEqual(omission[46, 8], "OM_NEAR_BLDG")
        self.assertEqual(omission[61, 61], "OM_NODATA")
        self.assertEqual(omission[4, 20], "OM_EDGE")
        self.assertEqual(omission[75, 40], "OM_OPEN")
        self.assertEqual(omission[10, 10], "")
        self.assertEqual(cells[10, 10], "CANOPY_FAR")
        self.assertEqual(cells[46, 3], "NONCAN_NEAR")
        self.assertEqual(cells[61, 61], "")
        self.assertEqual(cells[75, 40], "NONCAN_FAR")
        self.assertAlmostEqual(bdist[46, 8], 1.5)
        observed_noncanopy = (omission != "") & (omission != "OM_NODATA")
        self.assertTrue(np.array_equal(observed_noncanopy, np.char.startswith(cells.astype(str), "NONCAN")))


class Simulation(unittest.TestCase):
    def test_stratified_estimate_recovers_known_precision(self):
        """Draw repeated samples from a synthetic population with known truth."""
        rng = np.random.default_rng(11)
        sizes = {"ROOF": 3000, "NORMAL": 12000, "SMALL": 4000}
        truth_share = {"ROOF": .1, "NORMAL": .92, "SMALL": .55}
        population = {h: rng.random(n) < truth_share[h] for h, n in sizes.items()}
        truth = sum(v.sum() for v in population.values()) / sum(sizes.values())
        covered, issued, estimates = 0, 0, []
        for repeat in range(60):
            sample = []
            for h, trees in population.items():
                chosen = rng.choice(len(trees), 40, replace=False)
                sample += [{"stratum": h, "label": "TREE" if trees[i] else "ROOF_OR_BUILDING",
                            "retained": True} for i in chosen]
            result = vm.score_treetops(sample, sizes, replicates=300, seed=repeat)
            entry = result["estimates"]["precision"]
            estimates.append(entry["estimate"])
            if entry["low"] is None:
                self.assertEqual(entry["interval_status"], "HOMOGENEOUS_OR_DEGENERATE_SAMPLE")
            else:
                issued += 1
                covered += entry["low"] <= truth <= entry["high"]
        self.assertAlmostEqual(np.mean(estimates), truth, delta=.01)
        self.assertGreaterEqual(issued, 50)
        self.assertGreaterEqual(covered / issued, 52/60)


class Table(unittest.TestCase):
    def test_rows_and_markdown(self):
        sample = units("A", ["TREE", "ROOF_OR_BUILDING"], retained=True)
        scores = {("baseline", "T"): {"treetops": vm.score_treetops(sample, {"A": 10}, replicates=50)},
                  ("variant", "T"): {"treetops": vm.score_treetops(units("A", [None], retained=True),
                                                                   {"A": 10})}}
        rows = vm.comparison_rows(scores)
        values = {(r["run"], r["key"]): r["value"] for r in rows}
        self.assertTrue(values[("baseline", "treetops.precision")].startswith("50.0%"))
        self.assertEqual(values[("variant", "treetops.precision")], "no labels yet")
        self.assertEqual(values[("baseline", "cells.commission")], "n/a")
        table = vm.markdown_table(rows)
        self.assertIn("| Treetop precision", table)
        self.assertIn("baseline (T)", table)


if __name__ == "__main__":
    unittest.main()
