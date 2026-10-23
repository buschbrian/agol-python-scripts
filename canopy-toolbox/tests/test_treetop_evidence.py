import unittest

import numpy as np

from canopy import treetop_evidence as te


def ground(n=400, z=0.0, seed=1):
    rng = np.random.default_rng(seed)
    xy = rng.uniform(-5, 5, size=(n, 2))
    return np.c_[xy, np.full(n, z)], np.full(n, te.GROUND, np.uint8)


def single(n):
    return np.ones(n, np.uint8), np.ones(n, np.uint8)


class TreetopEvidence(unittest.TestCase):
    def run_one(self, top, xyz, cls, number=None, count=None):
        if number is None:
            number, count = single(len(xyz))
        m = te.measure(np.array([top]), xyz, cls, number, count)
        return m, te.flags(m)

    def test_flat_roof_peak_is_roof_height_and_flat_top(self):
        g, gc = ground()
        rng = np.random.default_rng(2)
        roof = np.c_[rng.uniform(-1.5, 1.5, (300, 2)), np.full(300, 5.0)]
        xyz = np.vstack([g, roof])
        cls = np.r_[gc, np.full(300, te.BUILDING, np.uint8)]
        m, f = self.run_one((0.0, 0.0, 5.0), xyz, cls)
        self.assertTrue(f["NEAR_BUILDING"][0])
        self.assertAlmostEqual(m["roof_hag_m"][0], 5.0, places=6)
        self.assertTrue(f["ROOF_HEIGHT"][0])
        self.assertTrue(f["FLAT_TOP"][0])
        self.assertTrue(f["SUSPECT"][0])
        self.assertFalse(f["CANOPY_RETURNS"][0])

    def test_tree_well_above_roof_is_overhang_not_suspect(self):
        g, gc = ground()
        rng = np.random.default_rng(3)
        roof = np.c_[rng.uniform(-1, 1, (100, 2)), np.full(100, 4.0)]
        crown = np.c_[rng.normal(0, .4, (200, 2)), rng.uniform(8, 9, 200)]
        xyz = np.vstack([g, roof, crown])
        cls = np.r_[gc, np.full(100, te.BUILDING, np.uint8), np.full(200, 5, np.uint8)]
        number = np.r_[np.ones(500, np.uint8), np.ones(200, np.uint8)]
        count = np.r_[np.ones(500, np.uint8), np.full(200, 2, np.uint8)]           # crown returns are not last
        m, f = self.run_one((0.0, 0.0, 9.0), xyz, cls, number, count)
        self.assertTrue(f["OVERHANG"][0])
        self.assertFalse(f["ROOF_HEIGHT"][0])
        self.assertTrue(f["CANOPY_RETURNS"][0])
        self.assertFalse(f["SUSPECT"][0])

    def test_pole_is_reported_but_not_suspect(self):
        g, gc = ground()
        pole = np.c_[np.zeros(60), np.zeros(60), np.linspace(0.5, 8, 60)]
        xyz = np.vstack([g, pole])
        cls = np.r_[gc, np.ones(60, np.uint8)]
        m, f = self.run_one((0.0, 0.0, 8.0), xyz, cls)
        self.assertTrue(f["POLE_HINT"][0])
        self.assertFalse(f["SUSPECT"][0])

    def test_suspect_is_the_union_of_four_flags(self):
        m = {c: np.array([np.nan]*4) for c in te.COLUMNS}
        m["n_building_1m"] = np.array([1, 0, 0, 0])
        m["above_roof_m"] = np.array([0.2, np.nan, np.nan, np.nan])
        m["n_top"] = np.array([20, 20, 20, 20])
        m["top_thickness"] = np.array([.5, .05, .5, .5])
        m["top_normal_z"] = np.array([.5, .95, .5, .5])
        m["top_nonlast"] = np.array([.5, .05, .5, .5])
        m["ctx_linearity"] = np.array([.1, .1, .9, .9])
        m["ctx_axis_z"] = np.array([.9, .9, .1, .95])
        m["ctx_extent_z"] = np.array([1., 1., 1., 5.])
        m["top_hag_m"] = np.array([5., 5., 6., 6.])
        f = te.flags(m)
        self.assertEqual(list(f["ROOF_HEIGHT"]), [True, False, False, False])
        self.assertEqual(list(f["FLAT_TOP"]), [False, True, False, False])
        self.assertEqual(list(f["WIRE_HINT"]), [False, False, True, False])
        self.assertEqual(list(f["POLE_HINT"]), [False, False, False, True])
        self.assertEqual(list(f["SUSPECT"]), [True, True, True, False])


if __name__ == "__main__":
    unittest.main()
