"""Pure reconciliation rules: rasterizing, regions, statuses, flags, labels, heights."""
import unittest

try:
    import numpy as np
    from canopy import building_rules as rules
    SCIENTIFIC = True
except ImportError:
    SCIENTIFIC = False


@unittest.skipUnless(SCIENTIFIC, "NumPy and SciPy required")
class Rasterize(unittest.TestCase):
    def cells(self, rings, shape=(10, 10), cell=1.0):
        indices, truncated = rules.rasterize(rings, 0, 10, cell, shape)
        grid = np.zeros(shape, dtype=bool)
        grid.flat[indices] = True
        return grid, truncated

    def test_square_uses_cell_centres(self):
        grid, truncated = self.cells([[(2, 2), (6, 2), (6, 5), (2, 5), (2, 2)]])
        self.assertFalse(truncated)
        self.assertEqual(grid.sum(), 12)
        # y from 2 to 5 is rows 5..7 (row r centre = 10 - r - .5); x from 2 to 6 is cols 2..5.
        self.assertTrue(grid[5:8, 2:6].all())

    def test_hole_is_excluded_and_open_ring_is_closed(self):
        outer = [(1, 1), (9, 1), (9, 9), (1, 9)]
        hole = [(4, 4), (6, 4), (6, 6), (4, 6)]
        grid, _ = self.cells([outer, hole])
        self.assertEqual(grid.sum(), 64 - 4)
        self.assertFalse(grid[4:6, 4:6].any())

    def test_polygon_beyond_grid_is_clipped_and_reported(self):
        grid, truncated = self.cells([[(-5, -5), (3, -5), (3, 3), (-5, 3)]])
        self.assertTrue(truncated)
        self.assertEqual(grid.sum(), 9)

    def test_sub_cell_polygon_between_centres_has_no_cells(self):
        grid, _ = self.cells([[(2.6, 2.6), (2.9, 2.6), (2.9, 2.9), (2.6, 2.9)]])
        self.assertEqual(grid.sum(), 0)

    def test_half_metre_cells(self):
        indices, _ = rules.rasterize([[(0, 0), (1, 0), (1, 1), (0, 1)]], 0, 2, .5, (4, 4))
        self.assertEqual(len(indices), 4)


@unittest.skipUnless(SCIENTIFIC, "NumPy and SciPy required")
class Regions(unittest.TestCase):
    def test_one_cell_gap_is_bridged_and_small_regions_dropped(self):
        support = np.zeros((20, 20), dtype=bool)
        support[2:8, 2:8] = True
        support[4, 5] = False              # an empty cell inside a roof
        support[2:8, 9:12] = True          # separated by one empty column: bridged
        support[15, 15] = True             # a single cell: below minimum area
        labels, count = rules.roof_regions(support, 1.0, 10)
        self.assertEqual(count, 1)
        self.assertEqual(labels[4, 5], 1)
        self.assertEqual(labels[4, 10], 1)
        self.assertEqual(labels[15, 15], 0)

    def test_closing_bridges_two_cells_but_not_three(self):
        support = np.zeros((10, 20), dtype=bool)
        support[2:8, 1:6] = True
        support[2:8, 8:13] = True          # two empty columns: bridged
        self.assertEqual(rules.roof_regions(support, 1.0, 10)[1], 1)
        support[2:8, 8] = False            # three empty columns: kept apart
        self.assertEqual(rules.roof_regions(support, 1.0, 10)[1], 2)

    def test_dilate_by_distance(self):
        mask = np.zeros((9, 9), dtype=bool); mask[4, 4] = True
        self.assertEqual(rules.dilate(mask, 1.0, 1.0).sum(), 5)
        self.assertEqual(rules.dilate(mask, 0, 1.0).sum(), 1)

    def test_gather_returns_points_in_requested_cells(self):
        cells = np.array([1, 1, 3, 5, 5, 5, 9])
        self.assertEqual(rules.gather(cells, [5, 1, 7]).tolist(), [0, 1, 3, 4, 5])
        self.assertEqual(rules.gather(cells, []).tolist(), [])


@unittest.skipUnless(SCIENTIFIC, "NumPy and SciPy required")
class Statuses(unittest.TestCase):
    def setUp(self):
        self.p = rules.parameters()

    def test_parameters_are_validated(self):
        with self.assertRaises(ValueError):
            rules.parameters(matched_share=1.5)
        with self.assertRaises(ValueError):
            rules.parameters(unknown=1)
        with self.assertRaises(ValueError):
            rules.parameters(at_roof_m=3, overhang_m=2)
        self.assertEqual(rules.parameters(overhang_m=None)["overhang_m"], 2.0)

    def test_class_shares(self):
        shares = rules.class_shares([6, 6, 5, 4, 1])
        self.assertEqual((shares["n6"], shares["nveg"], shares["nother"]), (2, 2, 1))
        self.assertAlmostEqual(shares["share6"], .4)
        self.assertIsNone(rules.class_shares([])["share6"])

    def test_footprint_statuses(self):
        p = self.p
        self.assertEqual(rules.footprint_status(.8, .9, .1, p), "MATCHED")
        self.assertEqual(rules.footprint_status(.8, .5, .5, p), "MATCHED")
        self.assertEqual(rules.footprint_status(.8, .05, .9, p), "LIDAR_MISSED")
        self.assertEqual(rules.footprint_status(.8, .2, .7, p), "PARTIAL")
        self.assertEqual(rules.footprint_status(.8, .0, .3, p), "PARTIAL")
        self.assertEqual(rules.footprint_status(.05, .9, .1, p), "NO_RETURNS_ABOVE_2M")
        self.assertEqual(rules.footprint_status(0, None, None, p), "NO_RETURNS_ABOVE_2M")

    def test_footprint_roof_height_falls_back_to_all_returns(self):
        self.assertEqual(rules.footprint_roof_height(7.0, 50, 6.0, self.p), (7.0, "CLASS6_P90"))
        self.assertEqual(rules.footprint_roof_height(7.0, 3, 6.0, self.p), (6.0, "ALL_FIRST_P50"))
        self.assertEqual(rules.footprint_roof_height(None, 0, None, self.p), (None, None))

    def test_region_status_ignores_same_method_source(self):
        self.assertEqual(rules.region_status({"county": True, "lidar_same_method": False}, {"county": True}), "MATCHED")
        self.assertEqual(rules.region_status({"county": False, "lidar_same_method": True},
                                             {"county": True, "lidar_same_method": True}), "NO_FOOTPRINT")
        self.assertEqual(rules.region_status({"osm2024": False, "lidar_same_method": True},
                                             {"osm2024": False, "lidar_same_method": True}), "NO_FOOTPRINT_COVERAGE")

    def test_candidate_flags(self):
        p = self.p
        self.assertEqual(rules.candidate_flag(6.3, 6.0, True, 9.0, p)[0], "ON_ROOF")
        self.assertEqual(rules.candidate_flag(6.3, 6.0, False, None, p), ("ROOF_EDGE", 6.3 - 6.0, "CLASS6_1M"))
        self.assertEqual(rules.candidate_flag(7.5, 6.0, False, None, p)[0], "NEAR_ROOF")
        self.assertEqual(rules.candidate_flag(8.5, 6.0, True, None, p)[0], "OVERHANG")
        # A missed building: no class 6 nearby, but inside a footprint at its roof height.
        self.assertEqual(rules.candidate_flag(5.2, None, True, 5.0, p), ("ON_ROOF", 5.2 - 5.0, "FOOTPRINT"))
        self.assertEqual(rules.candidate_flag(12.0, None, True, 5.0, p)[0], "OVERHANG")
        self.assertEqual(rules.candidate_flag(12.0, None, False, None, p), ("CLEAR", None, None))
        self.assertEqual(rules.candidate_flag(12.0, None, True, None, p)[0], "CLEAR")


@unittest.skipUnless(SCIENTIFIC, "NumPy and SciPy required")
class Labels(unittest.TestCase):
    def test_label_codes(self):
        p = rules.parameters()
        classes = np.array([6, 6, 6, 5, 5, 4, 5, 3, 5, 2, 1, 7, 4, 5])
        zone = np.array([1, 0, 0, 1, 1, 0, 0, 0, 0, 1, 0, 0, 1, 1], dtype=bool)
        cover = np.array([1, 1, 0, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1], dtype=bool)
        edge = np.array([0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0], dtype=bool)
        above = np.array([np.nan, np.nan, np.nan, 0.5, 3.0, np.nan, np.nan, np.nan, np.nan, 0, 0, 0, -5, np.nan])
        codes = rules.label_codes(classes, zone, cover, edge, above, p)
        self.assertEqual(codes.tolist(), [6, 64, 67, 65, 68, 66, 5, 3, 69, 2, 1, 7, 70, 65])
        self.assertEqual(classes.tolist()[0], 6)  # input unchanged

    def test_label_codes_are_user_definable_and_documented(self):
        self.assertTrue(all(code >= 64 for code in rules.LABEL_CODES if code not in (3, 4, 5, 6)))


@unittest.skipUnless(SCIENTIFIC, "NumPy and SciPy required")
class Heights(unittest.TestCase):
    def test_height_stats(self):
        stats = rules.height_stats([1, 2, 3, 4, np.nan, 10])
        self.assertEqual(stats["n"], 5)
        self.assertEqual(stats["p50"], 3)
        self.assertEqual(stats["max"], 10)
        self.assertIsNone(rules.height_stats([])["p90"])

    def test_height_comparison_reports_bias_ratio_and_outliers(self):
        reference = [5.0, 6.0, 7.0, 8.0, 0.0, np.nan]
        lidar = [5.5, 6.5, 7.5, 14.0, 3.0, 4.0]
        result = rules.height_comparison(reference, lidar, ids=["a", "b", "c", "d", "e", "f"])
        self.assertEqual(result["n"], 4)
        self.assertAlmostEqual(result["bias_median_m"], .5)
        self.assertAlmostEqual(result["median_abs_difference_m"], .5)
        self.assertEqual([o["id"] for o in result["outliers"]], ["d"])
        self.assertGreater(result["median_ratio"], 1)

    def test_feet_reference_gives_ratio_near_point_three(self):
        feet = np.array([20.0, 25.0, 30.0])
        result = rules.height_comparison(feet, feet*.3048)
        self.assertAlmostEqual(result["median_ratio"], .3048)
        self.assertEqual(rules.height_comparison([np.nan], [1.0]), {"n": 0})


@unittest.skipUnless(SCIENTIFIC, "NumPy and SciPy required")
class Registration(unittest.TestCase):
    def test_best_shift_recovers_known_offset(self):
        roofs = np.zeros((30, 30), dtype=bool)
        roofs[10:16, 8:14] = True
        roofs[20:24, 18:25] = True
        # Footprints 2 cells west and 1 cell north of the roofs (rows increase southward).
        footprints = np.roll(np.roll(roofs, -2, axis=1), -1, axis=0)
        result = rules.best_shift(footprints, roofs, 3, .5)
        self.assertEqual((result["shift_east_m"], result["shift_north_m"]), (1.0, -.5))
        self.assertAlmostEqual(result["iou_best"], 1.0)
        self.assertLess(result["iou_at_zero"], .6)
        self.assertEqual(rules.best_shift(roofs, roofs, 2, .5)["shift_east_m"], 0)


if __name__ == "__main__":
    unittest.main()
