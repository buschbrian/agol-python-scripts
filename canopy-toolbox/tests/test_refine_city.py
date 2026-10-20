import importlib.util
from pathlib import Path
import unittest

import numpy as np

SCRIPT = Path(__file__).resolve().parents[1]/"reviews"/"2026-10-19"/"fractal-city"/"refine_city.py"
spec = importlib.util.spec_from_file_location("refine_city", SCRIPT)
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)


def run(base, fractal, unanimous=None, withheld=None, hag=None):
    n = len(base)
    return rc.rules(np.array(base, dtype=np.uint8), np.array(fractal, dtype=np.uint8),
                    np.ones(n, bool) if unanimous is None else np.array(unanimous),
                    np.zeros(n, bool) if withheld is None else np.array(withheld),
                    np.full(n, 10.0) if hag is None else np.array(hag, dtype=float))


class Band(unittest.TestCase):
    def test_october_8_thresholds(self):
        hag = np.array([-0.3, 0.0, 0.5, 0.51, 2.0, 2.1, 80.0, 80.5, np.nan])
        self.assertEqual(rc.band(hag).tolist(), [3, 3, 3, 4, 4, 5, 5, 0, 0])


class Rules(unittest.TestCase):
    def test_applied_changes_from_toolbox_classes(self):
        new, rule = run([3, 4, 5, 3, 6, 6, 6], [6, 64, 1, 5, 64, 1, 6])
        self.assertEqual(new.tolist(), [6, 64, 1, 3, 64, 1, 6])
        self.assertEqual(rule.tolist(), [1, 2, 3, 0, 5, 6, 0])

    def test_building_to_vegetation_is_banded_by_height(self):
        new, rule = run([6, 6, 6, 6], [5, 5, 5, 5], hag=[0.2, 1.0, 12.0, np.nan])
        self.assertEqual(new.tolist(), [3, 4, 5, 6])
        self.assertEqual(rule.tolist(), [4, 4, 4, 14])

    def test_nothing_changes_without_a_unanimous_vote(self):
        new, rule = run([5, 6], [6, 5], unanimous=[False, False])
        self.assertEqual((new.tolist(), rule.tolist()), ([5, 6], [0, 0]))

    def test_ties_and_withheld_points_never_change(self):
        new, rule = run([5, 5], [0, 6], withheld=[False, True])
        self.assertEqual((new.tolist(), rule.tolist()), ([5, 5], [0, 0]))

    def test_version_1_only_proposes_vegetation_to_ground(self):
        base = [4, 6, 2, 20, 9, 17, 5, 1, 7, 18]
        fractal = [2, 2, 6, 5, 2, 5, 9, 6, 6, 5]
        new, rule = rc.rules(np.array(base, np.uint8), np.array(fractal, np.uint8), np.ones(10, bool), np.zeros(10, bool),
                             np.full(10, 10.0), version=1)
        self.assertEqual(new.tolist(), base)
        self.assertEqual(rule.tolist(), [11, 12, 13, 13, 13, 13, 15, 16, 0, 0])

    def test_version_2_applies_vegetation_to_ground_and_proposes_the_rest(self):
        base = [4, 3, 6, 2, 20, 9, 17, 5, 1, 7, 18]
        fractal = [2, 2, 2, 6, 5, 2, 5, 9, 6, 6, 5]
        new, rule = run(base, fractal)
        self.assertEqual(new.tolist(), [2, 2, 6, 2, 20, 9, 17, 5, 1, 7, 18])
        self.assertEqual(rule.tolist(), [7, 7, 12, 13, 13, 13, 13, 15, 16, 0, 0])

    def test_version_2_vegetation_to_ground_needs_a_unanimous_vote(self):
        new, rule = run([3], [2], unanimous=[False])
        self.assertEqual((new.tolist(), rule.tolist()), ([3], [0]))

    def test_vendor_classes_that_agree_are_not_flagged(self):
        _, rule = run([2, 20, 9, 17], [2, 2, 9, 17])
        self.assertEqual(rule.tolist(), [0, 0, 0, 0])


class GroundHeights(unittest.TestCase):
    def test_nearest_cell_nodata_and_outside(self):
        data = np.array([[10.0, 11.0], [12.0, 3.4e38]])
        ground = (data, 100.0, 202.0, 1.0, 3.4e38)
        z = rc.ground_heights(ground, np.array([100.5, 101.5, 100.5, 101.5, 99.0]), np.array([201.5, 201.5, 200.5, 200.5, 201.5]))
        self.assertEqual(z[:3].tolist(), [10.0, 11.0, 12.0])
        self.assertTrue(np.isnan(z[3]) and np.isnan(z[4]))


if __name__ == "__main__":
    unittest.main()
