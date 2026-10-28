"""Interior-supported roof faces must reach eaves without following edge contamination.

The synthetic reference roof is known exactly. Class-6 edge returns are deliberately
coherent at an incorrect height, so a small residual at an edge is not enough evidence
to move vegetation to class 6. These are pure geometry tests; no LAS files are edited.
"""
import importlib.util
import unittest


HAVE_SCIPY = (importlib.util.find_spec("numpy") is not None
              and importlib.util.find_spec("scipy") is not None)


def gable_height(x):
    import numpy as np
    return 105.5 - .5 * np.abs(x)


def gable_support(edge_bias=0.):
    """Interior roof is correct; the outer 0.75 m contains wall/parapet returns."""
    import numpy as np
    x, y = np.meshgrid(np.arange(-4.75, 4.76, .25), np.arange(-2., 2.01, .25))
    x, y = x.ravel(), y.ravel()
    z = gable_height(x) + np.where(np.abs(x) >= 4.25, edge_bias, 0.)
    return np.column_stack((x, y, z))


@unittest.skipUnless(HAVE_SCIPY, "numpy and scipy required")
class InteriorAnchoredRoof(unittest.TestCase):
    def evaluate(self, support, queries, radius=1.5, neighbors=16):
        import numpy as np
        from canopy import roof_surface as rs
        tree = rs.build_tree(support)
        gradient, _, status = rs.faces(tree, support[:, 2], radius=radius,
                                       neighbors=neighbors, workers=1)
        result = rs.evaluate(tree, support[:, 2], gradient, status,
                             np.asarray(queries, dtype=float), radius=radius,
                             neighbors=neighbors, workers=1)
        return result, rs.select(result)

    def test_clean_interior_extends_both_gable_faces_to_missing_eaves(self):
        import numpy as np
        support = gable_support()
        support = support[np.abs(support[:, 0]) <= 4.]
        queries = [(x, 0., float(gable_height(x))) for x in (-5., 5.)]
        result, chosen = self.evaluate(support, queries)
        self.assertEqual(chosen.tolist(), [True, True], result)
        np.testing.assert_allclose(result["residual"], [0., 0.], atol=.05)

    def test_lower_wall_returns_do_not_anchor_downward_eave_extrapolation(self):
        import numpy as np
        support = gable_support(edge_bias=-.8)
        queries = [(x, 0., float(gable_height(x))) for x in (-5., 5.)]
        result, chosen = self.evaluate(support, queries)
        self.assertEqual(chosen.tolist(), [True, True], result)
        np.testing.assert_allclose(result["residual"], [0., 0.], atol=.05)

    def test_upper_parapet_returns_do_not_anchor_upward_eave_extrapolation(self):
        import numpy as np
        support = gable_support(edge_bias=.8)
        queries = [(x, 0., float(gable_height(x))) for x in (-5., 5.)]
        result, chosen = self.evaluate(support, queries)
        self.assertEqual(chosen.tolist(), [True, True], result)
        np.testing.assert_allclose(result["residual"], [0., 0.], atol=.05)

    def test_edge_contamination_does_not_reclassify_above_or_below_roof_vegetation(self):
        # +/-0.8 m is outside the accepted [-0.35,+0.5] m band around the
        # *reference roof*. The contaminated class-6 edge must not redefine it.
        for edge_bias in (-.8, .8):
            with self.subTest(edge_bias=edge_bias):
                support = gable_support(edge_bias=edge_bias)
                queries = [(x, 0., float(gable_height(x)) + offset)
                           for x in (-5., 5.) for offset in (-.8, .8, -1.5, 2.5)]
                result, chosen = self.evaluate(support, queries)
                self.assertFalse(chosen.any(), result)

    def test_trimmed_face_is_not_reanchored_to_its_rejected_support_point(self):
        import numpy as np
        # Three bad anchors are surrounded by dozens of exact interior face
        # points. A robust face fit has enough uncontaminated 2-D support.
        x, y = np.meshgrid(np.arange(1.5, 4.51, .25), np.arange(-1.5, 1.51, .25))
        x, y = x.ravel(), y.ravel()
        z = gable_height(x)
        z[(x == 3.) & (np.abs(y) <= .25)] += .8
        support = np.column_stack((x, y, z))
        roof_z = float(gable_height(3.))
        result, chosen = self.evaluate(support, [(3., 0., roof_z),
                                                (3., 0., roof_z + .8),
                                                (3., 0., roof_z - .8)],
                                       radius=1., neighbors=64)
        self.assertEqual(chosen.tolist(), [True, False, False], result)


if __name__ == "__main__":
    unittest.main()
