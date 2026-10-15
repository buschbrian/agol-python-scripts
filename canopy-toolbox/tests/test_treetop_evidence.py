import unittest

import numpy as np

from canopy import treetop_evidence as te


def cloud(**parts):
    """A decoded point set from {name: (xyz array, class, count, number)} parts."""
    x, y, z, cls, count, number = [], [], [], [], [], []
    for xyz, c, k, m in parts.values():
        n = len(xyz)
        x.append(xyz[:, 0]); y.append(xyz[:, 1]); z.append(xyz[:, 2])
        cls.append(np.full(n, c, np.uint8))
        count.append(np.broadcast_to(np.asarray(k, np.uint8), (n,)))
        number.append(np.broadcast_to(np.asarray(m, np.uint8), (n,)))
    out = {"x": np.concatenate(x), "y": np.concatenate(y), "z": np.concatenate(z), "cls": np.concatenate(cls),
           "count": np.concatenate(count), "number": np.concatenate(number)}
    out["clean"] = np.ones(len(out["x"]), bool)
    return out


def ground(rng, half=8.0, n=4000):
    return np.c_[rng.uniform(-half, half, (n, 2)), rng.normal(0, .02, n)]


def pilot_loop(xy, height, building, ground_xyz):
    """The 29 September candidates_near_buildings.py loop, verbatim in substance."""
    from scipy.spatial import cKDTree
    btree, gtree = cKDTree(building[:, :2]), cKDTree(ground_xyz[:, :2])
    near = np.isfinite(btree.query(xy, distance_upper_bound=1.0)[0])
    bands = []
    for (x, y), h in zip(xy, height):
        roof, under = btree.query_ball_point((x, y), 1.0), gtree.query_ball_point((x, y), 5.0)
        if not roof or not under:
            bands.append(-1)
            continue
        above = h-(np.percentile(building[roof, 2], 90)-np.median(ground_xyz[under, 2]))
        bands.append(0 if above <= .5 else 1 if above <= 2 else 2)
    return near, np.array(bands)


class NearBuildingTest(unittest.TestCase):
    def test_matches_the_pilot_definition(self):
        rng = np.random.default_rng(3)
        building = np.c_[rng.uniform(-20, 20, (3000, 2)), rng.uniform(3, 9, 3000)]
        ground_xyz = np.c_[rng.uniform(-25, 25, (3000, 2)), rng.normal(0, .3, 3000)]
        xy = rng.uniform(-22, 22, (400, 2))
        height = rng.uniform(2, 15, 400)
        f = te.near_building(xy, height, building, ground_xyz)
        near, bands = pilot_loop(xy, height, building, ground_xyz)
        np.testing.assert_array_equal(f["n_building_1m"] > 0, near)
        np.testing.assert_array_equal(te.band(f["above_roof_m"]), bands)

    def test_no_building_or_ground_gives_nan(self):
        f = te.near_building(np.zeros((1, 2)), np.array([5.0]), np.empty((0, 3)), np.empty((0, 3)))
        self.assertEqual(f["n_building_1m"][0], 0)
        self.assertTrue(np.isnan(f["above_roof_m"][0]))


class FlagTest(unittest.TestCase):
    def setUp(self):
        self.rng = np.random.default_rng(11)

    def test_roof_edge_peak(self):
        rng = self.rng
        roof = np.c_[rng.uniform(0, 8, (3000, 2)), 6+rng.normal(0, .01, 3000)]
        pts = cloud(g=(ground(rng), 2, 1, 1), roof=(roof, 6, 1, 1),
                    edge=(np.c_[rng.uniform(-.5, 0, (40, 2)), 6+rng.normal(0, .01, 40)], 5, 1, 1))
        f = te.evaluate([[-.2, .5]], [6.0], pts)
        self.assertTrue(f["NEAR_BUILDING"][0] and f["ROOF_HEIGHT"][0] and f["FLAT_TOP"][0] and f["SUSPECT"][0])
        self.assertFalse(f["OVERHANG"][0] or f["CANOPY_RETURNS"][0])

    def test_tree_crown_is_canopy_not_suspect(self):
        rng = self.rng
        n = 3000
        crown = np.c_[rng.normal(0, 1.5, (n, 2)), rng.uniform(4, 10, n)]
        count = np.where(rng.random(n) < .7, 3, 1)
        number = np.where(count == 3, rng.integers(1, 3, n), 1)
        pts = cloud(g=(ground(rng), 2, 1, 1), crown=(crown, 5, count, number))
        f = te.evaluate([[0, 0]], [10.0], pts)
        self.assertTrue(f["CANOPY_RETURNS"][0])
        self.assertFalse(f["SUSPECT"][0])
        self.assertFalse(f["NEAR_BUILDING"][0])

    def test_wire_peak(self):
        rng = self.rng
        wire = np.c_[rng.uniform(-6, 6, 120), rng.normal(0, .02, 120), 8+rng.normal(0, .02, 120)]
        pts = cloud(g=(ground(rng), 2, 1, 1), wire=(wire, 5, 2, 1))
        f = te.evaluate([[0, 0]], [8.0], pts)
        self.assertTrue(f["WIRE_HINT"][0] and f["SUSPECT"][0])
        self.assertFalse(f["POLE_HINT"][0])

    def test_pole_peak(self):
        rng = self.rng
        pole = np.c_[rng.normal(0, .03, (300, 2)), rng.uniform(.5, 9, 300)]
        pts = cloud(g=(ground(rng), 2, 1, 1), pole=(pole, 5, 1, 1))
        f = te.evaluate([[0, 0]], [9.0], pts)
        self.assertTrue(f["POLE_HINT"][0])
        self.assertFalse(f["WIRE_HINT"][0])
        self.assertFalse(f["SUSPECT"][0])         # a narrow crown is a vertical line too; POLE is a hint only

    def test_thin_flat_top_is_not_canopy_even_with_split_returns(self):
        rng = self.rng
        plane = np.c_[rng.uniform(-3, 3, (900, 2)), 4+rng.normal(0, .02, 900)]
        pts = cloud(g=(ground(rng), 2, 1, 1), plane=(plane, 5, 2, 1))
        f = te.evaluate([[0, 0]], [4.0], pts)
        self.assertFalse(f["CANOPY_RETURNS"][0])

    def test_noise_and_withheld_points_are_ignored(self):
        rng = self.rng
        noise = np.c_[rng.normal(0, .02, (60, 2)), np.full(60, 30.0)]
        pts = cloud(g=(ground(rng), 2, 1, 1), noise=(noise, 7, 1, 1),
                    lone=(np.array([[0., 0., 5.]]), 5, 1, 1))
        f = te.evaluate([[0, 0]], [5.0], pts)
        self.assertEqual(f["n_top"][0], 1)
        self.assertAlmostEqual(f["top_hag_m"][0], 5.0, delta=.1)

    def test_nan_never_flags(self):
        f = {k: np.array([np.nan]) for k in te.FEATURES}
        f["n_top"] = np.array([0]); f["n_building_1m"] = np.array([0])
        out = te.flags(f)
        self.assertFalse(any(out[k][0] for k in te.FLAGS))


class HelpersTest(unittest.TestCase):
    def test_tile_name(self):
        self.assertEqual(te.tile_name(428123.5, 4504567.25), "12TVL2804")
        self.assertEqual(te.tile_name(422000.25, 4503999.75), "12TVL2203")

    def test_strip_keeps_only_the_edge_band(self):
        x, y = np.meshgrid(np.arange(0, 1000, 10.), np.arange(0, 1000, 10.))
        pts = {"x": x.ravel(), "y": y.ravel(), "z": np.zeros(x.size)}
        s = te.strip(pts, (0, 0, 990, 990), width=5)
        self.assertTrue(np.all((s["x"] <= 5) | (s["x"] >= 985) | (s["y"] <= 5) | (s["y"] >= 985)))
        self.assertEqual(len(s["x"]), 4*100-4)

    def test_band_edges(self):
        np.testing.assert_array_equal(te.band([.5, .51, 2.0, 2.01, np.nan]), [0, 1, 1, 2, -1])


if __name__ == "__main__":
    unittest.main()
