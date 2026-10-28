"""Local roof-surface refinement on synthetic gabled, hipped and courtyard roofs; no ArcPy."""
import importlib.util
import unittest

HAVE_SCIPY = importlib.util.find_spec("numpy") is not None and importlib.util.find_spec("scipy") is not None


def gable(x, ridge=105.5, slope=.5):
    """Gabled roof, ridge along y at x=0, falling `slope` m per m to both eaves."""
    import numpy as np
    return ridge-slope*np.abs(x)


def roof_support(seed=0, spacing=.25, half=5., missed_eave=.5, missed_ridge=.3, noise=.03, slope=.5):
    """Class-6 points the building classifier kept: the outer eave strip and the ridge strip are missed."""
    import numpy as np
    rng = np.random.default_rng(seed)
    grid = np.arange(-half, half+1e-9, spacing)
    x, y = [a.ravel() for a in np.meshgrid(grid, grid)]
    x = x+rng.uniform(-.05, .05, x.size); y = y+rng.uniform(-.05, .05, y.size)
    keep = (np.abs(x) <= half-missed_eave) & (np.abs(y) <= half) & (np.abs(x) >= missed_ridge)
    z = gable(x[keep], slope=slope)+rng.normal(0, noise, keep.sum())
    return np.column_stack((x[keep], y[keep], z))


@unittest.skipUnless(HAVE_SCIPY, "numpy and scipy required")
class GabledRoof(unittest.TestCase):
    def evaluate(self, support, queries, radius=1.0, below=.35, above=.5, min_votes=3):
        import numpy as np
        from canopy import roof_surface as rs
        tree = rs.build_tree(support)
        gradient, _, status = rs.faces(tree, support[:, 2], radius=radius)
        result = rs.evaluate(tree, support[:, 2], gradient, status, np.asarray(queries, dtype=float),
                             radius=radius, below=below, above=above)
        return result, rs.select(result, min_votes)

    def test_eave_and_ridge_points_are_reclassified(self):
        # 6/12 and 12/12 pitches; a single plane across the ridge would sit ~slope*0.4 m low.
        for slope in (.5, 1.):
            with self.subTest(slope=slope):
                g = lambda x: gable(x, slope=slope)
                support = roof_support(slope=slope)
                queries = [(4.6, 0, g(4.6)), (-4.8, 2, g(4.8)), (5.2, -1, g(5.2)+.1),  # eaves
                           (0, 0, 105.5), (.1, 3, 105.55), (-.1, -4, 105.45)]         # ridge
                result, chosen = self.evaluate(support, queries)
                self.assertTrue(chosen.all(), (result["votes"], result["residual"]))
                self.assertTrue((abs(result["residual"]) < .2).all(), result["residual"])

    def test_overhanging_tree_hedge_and_wall_vegetation_stay(self):
        for slope in (.5, 1.):
            with self.subTest(slope=slope):
                g = lambda x: gable(x, slope=slope)
                support = roof_support(slope=slope)
                queries = [(4, 0, g(4)+3),         # canopy overhanging the roof, 3 m above it
                           (0, 2, 105.5+3),        # canopy over the ridge
                           (5.6, 0, g(5)-1.5),     # hedge just outside the eave, 1.5 m below it
                           (4.8, 1, g(4.8)-1),     # shrub against the wall under the eave
                           (4.5, 0, g(4.5)+.8),    # something 0.8 m above the roof, e.g. a low branch
                           (5.3, 0, g(0))]         # tree beside the eave, as tall as the ridge
                result, chosen = self.evaluate(support, queries)
                self.assertFalse(chosen.any(), result["residual"])

    def test_band_edges_are_explicit(self):
        support = roof_support(noise=0)
        queries = [(3, 0, gable(3)-.3), (3, 0, gable(3)-.4), (3, 0, gable(3)+.45), (3, 0, gable(3)+.55)]
        result, chosen = self.evaluate(support, queries)
        self.assertEqual(chosen.tolist(), [True, False, True, False])
        self.assertTrue((abs(result["residual"]-[-.3, -.4, .45, .55]) < .02).all(), result["residual"])
        _, chosen = self.evaluate(support, queries, below=.5, above=.4)
        self.assertEqual(chosen.tolist(), [True, True, False, False])

    def test_points_beyond_the_radius_have_no_support(self):
        import numpy as np
        from canopy import roof_surface as rs
        support = roof_support()
        result, chosen = self.evaluate(support, [(6.0, 0, gable(6)), (0, 7, 105.5)], radius=1.0)
        self.assertFalse(chosen.any())
        self.assertEqual(result["support"].tolist(), [0, 0])
        self.assertTrue(np.isnan(result["residual"]).all())

    def test_hipped_roof_corner(self):
        import numpy as np
        rng = np.random.default_rng(3)
        grid = np.arange(-5, 5.01, .25)
        x, y = [a.ravel() for a in np.meshgrid(grid, grid)]
        hip = lambda x, y: 104-.6*np.maximum(np.abs(x), np.abs(y))  # hipped (pyramid) roof, eaves at 101
        keep = np.maximum(np.abs(x), np.abs(y)) <= 4.5
        support = np.column_stack((x[keep], y[keep], hip(x[keep], y[keep])+rng.normal(0, .03, keep.sum())))
        corner = (4.8, 4.8, hip(4.8, 4.8)); hip_line = (3, 3, hip(3, 3)); tree = (4.8, 4.8, hip(4.8, 4.8)+2.5)
        result, chosen = self.evaluate(support, [corner, hip_line, tree])
        self.assertEqual(chosen.tolist(), [True, True, False], result["residual"])

    def test_step_between_roof_levels_is_not_bridged(self):
        import numpy as np
        grid = np.arange(-5, 5.01, .25)
        x, y = [a.ravel() for a in np.meshgrid(grid, grid)]
        z = np.where(x < 0, 106., 103.)  # two-storey roof beside a single-storey roof
        support = np.column_stack((x, y, z))
        # Vegetation halfway up the step (e.g. a tree against the upper wall) is on neither roof.
        result, chosen = self.evaluate(support, [(0.1, 0, 104.5), (1.5, 0, 103.1), (-1.5, 0, 106.1)])
        self.assertEqual(chosen.tolist(), [False, True, True], (result["votes"], result["residual"]))

    def test_collinear_support_is_degenerate(self):
        import numpy as np
        from canopy import roof_surface as rs
        line = np.column_stack((np.linspace(0, 2, 20), np.zeros(20), np.full(20, 103.)))
        _, _, status = rs.faces(rs.build_tree(line), line[:, 2])
        self.assertTrue((status == rs.DEGENERATE).all())
        result, chosen = self.evaluate(line, [(1, .2, 103.)])
        self.assertEqual(result["faces"].tolist(), [0])
        self.assertFalse(chosen.any())

    def test_courtyard_centre_is_not_reached(self):
        import numpy as np
        grid = np.arange(-10, 10.01, .25)
        x, y = [a.ravel() for a in np.meshgrid(grid, grid)]
        keep = np.maximum(np.abs(x), np.abs(y)) > 2.5  # flat roof around a 5 m courtyard
        support = np.column_stack((x[keep], y[keep], np.full(keep.sum(), 108.)))
        # Courtyard tree at roof height in the centre: 2.5 m from any roof point, so no support.
        result, chosen = self.evaluate(support, [(0, 0, 108.2), (0, 0, 104.), (2.2, 0, 108.1)])
        self.assertEqual(chosen.tolist(), [False, False, True])

    def test_chunking_matches_single_pass(self):
        import numpy as np
        from canopy import roof_surface as rs
        support = roof_support()
        rng = np.random.default_rng(1)
        q = np.column_stack((rng.uniform(-6, 6, 999), rng.uniform(-6, 6, 999), rng.uniform(101, 108, 999)))
        tree = rs.build_tree(support)
        face_one = rs.faces(tree, support[:, 2])
        face_many = rs.faces(tree, support[:, 2], chunk=101)
        for a, b in zip(face_one, face_many):
            np.testing.assert_array_equal(a, b)
        one = rs.evaluate(tree, support[:, 2], face_one[0], face_one[2], q)
        many = rs.evaluate(tree, support[:, 2], face_one[0], face_one[2], q, chunk=97)
        for key in one:
            np.testing.assert_array_equal(one[key], many[key])

    def test_envelope_prefilter_keeps_every_selected_point(self):
        import numpy as np
        from canopy import roof_surface as rs
        support = roof_support()
        rng = np.random.default_rng(2)
        q = np.column_stack((rng.uniform(-6.5, 6.5, 5000), rng.uniform(-6.5, 6.5, 5000), rng.uniform(99, 110, 5000)))
        result, chosen = self.evaluate(support, q)
        low, high = rs.envelope(support, -8, 8, .5, (32, 32), 1.0)
        kept = rs.prefilter(q, low, high, -8, 8, .5, .35, .5, 1.0, 1.5)
        self.assertTrue(chosen.any())
        self.assertFalse((chosen & ~kept).any())
        self.assertLess(kept.mean(), .8)

    def test_return_and_flag_masks(self):
        import numpy as np
        from canopy import roof_surface as rs
        modern = np.array([0x11, 0x21, 0x22, 0x33], dtype=np.uint8)   # single, first of 2, 2 of 2, 3 of 3
        legacy = np.array([0x09, 0x11, 0x12, 0x1b], dtype=np.uint8)
        for data, is_modern in ((modern, True), (legacy, False)):
            first, single = rs.return_masks(data, is_modern)
            self.assertEqual(first.tolist(), [True, True, False, False])
            self.assertEqual(single.tolist(), [True, False, False, False])
        self.assertEqual(rs.clean_flags(np.array([0, 1, 4, 8, 2, 16], np.uint8), True).tolist(),
                         [True, False, False, False, True, True])
        self.assertEqual(rs.clean_flags(np.array([0, 32, 128, 64, 5], np.uint8), False).tolist(),
                         [True, False, False, True, True])

    def test_cli_rejects_options_of_the_other_method(self):
        import contextlib, io
        from canopy.__main__ import main
        for argv in (["refine-roofs", "in.lasd", "out", "--radius", "1.5"],
                     ["refine-roofs", "in.lasd", "out", "--method", "plane", "--classes", "5"],
                     ["refine-roofs", "in.lasd", "out", "--method", "local", "--edge-distance", "2"],
                     ["refine-roofs", "in.lasd", "out", "--method", "local", "--classes", "6"]):
            with self.subTest(argv=argv), self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                main(argv)

    def test_parameters_are_checked(self):
        from canopy import roof_surface as rs
        rs.check_parameters(1, 16, 6, 3, .35, .5, .15, 1.5)
        for bad in [(0, 16, 6, 3, .35, .5, .15, 1.5), (1, 16, 2, 3, .35, .5, .15, 1.5), (1, 4, 6, 3, .35, .5, .15, 1.5),
                    (1, 16, 6, 3, -.1, .5, .15, 1.5), (1, 16, 6, 3, .35, float("nan"), .15, 1.5),
                    (1, 16.5, 6, 3, .35, .5, .15, 1.5), (1, 16, 6, 0, .35, .5, .15, 1.5), (1, 16, 6, 17, .35, .5, .15, 1.5)]:
            with self.assertRaises(ValueError):
                rs.check_parameters(*bad)
