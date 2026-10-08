import unittest

import numpy as np

from canopy import label_check as lc

UNIT = {"X": 0.0, "Y": 0.0, "Z_LOW": -5.0, "Z_HIGH": 50.0, "PATCH_R_M": 1.0}


def cloud(rng, heights, n=60):
    r = np.sqrt(rng.random(n))
    a = rng.random(n)*2*np.pi
    z = rng.uniform(heights[0], heights[1], n)
    return r*np.cos(a), r*np.sin(a), z


class Stats(unittest.TestCase):
    def test_only_the_patch_points_count(self):
        rng = np.random.default_rng(3)
        x, y, z = cloud(rng, (0.0, 0.3))
        near_pole = (np.array([2.0, 2.1, 2.2]), np.array([0.0, 0.0, 0.0]), np.array([1.0, 2.0, 3.8]))   # outside the 1 m radius
        stats = lc.patch_stats(UNIT, np.r_[x, near_pole[0]], np.r_[y, near_pole[1]], np.r_[z, near_pole[2]], 0.0)
        self.assertLess(stats["max"], 0.31)                                 # the pole beside the patch is not in it
        slab = dict(UNIT, Z_LOW=0.0, Z_HIGH=0.1)
        self.assertLess(lc.patch_stats(slab, x, y, z, 0.0)["max"], 0.11)    # and the slab limits heights too
        self.assertEqual(lc.patch_stats(dict(UNIT, X=50.0), x, y, z, 0.0)["n"], 0)


class Check(unittest.TestCase):
    def stats(self, low, high, n=60, ground=0.0):
        rng = np.random.default_rng(5)
        return lc.patch_stats(UNIT, *cloud(rng, (low, high), n), ground)

    def test_labels_the_points_support_are_not_flagged(self):
        for label, heights in (("VEHICLE", (0, 1.6)), ("POLE", (0, 6)), ("WALL", (0.5, 3)), ("BUILDING_ROOF", (5, 5.1)),
                               ("TREE", (3, 12)), ("GROUND", (0, 0.3)), ("SHRUB_LOW_VEG", (0, 1.2)),
                               ("OTHER_STRUCTURE", (2.3, 2.5)), ("WIRE", (8, 8.1))):
            self.assertEqual(lc.check_label(label, self.stats(*heights)), [], label)

    def test_a_label_naming_something_the_patch_does_not_contain_is_flagged(self):
        ground_only = self.stats(0.0, 0.3)                                   # what the audit found under two VEHICLE labels
        for label in ("VEHICLE", "POLE", "WALL", "BUILDING_ROOF", "TREE", "OTHER_STRUCTURE", "WIRE"):
            reasons = lc.check_label(label, ground_only)
            self.assertEqual(len(reasons), 1, label)
            self.assertIn("m above ground", reasons[0])
        self.assertTrue(lc.check_label("GROUND", self.stats(0, 4)))          # tall points in a 'ground' patch
        self.assertTrue(lc.check_label("SHRUB_LOW_VEG", self.stats(5, 9)))   # a tall patch called lawn

    def test_uncertain_or_blank_labels_and_thin_patches(self):
        self.assertEqual(lc.check_label("MIXED", self.stats(0, 0.2)), [])
        self.assertEqual(lc.check_label("UNSURE", self.stats(0, 0.2)), [])
        self.assertEqual(lc.check_label("", self.stats(0, 0.2)), [])
        thin = self.stats(0, 2, n=5)
        self.assertTrue(any("only 5 points" in r and "too few" in r for r in lc.check_label("GROUND", thin)))
        empty = lc.patch_stats(dict(UNIT, X=50.0), [0.0], [0.0], [0.0], 0.0)
        self.assertTrue(any("only 0 points" in r for r in lc.check_label("TREE", empty)))


if __name__ == "__main__":
    unittest.main()
