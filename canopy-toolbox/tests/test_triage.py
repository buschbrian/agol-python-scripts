import unittest
from unittest import mock

import numpy as np

from canopy import triage

UNIT = {"X": 0.0, "Y": 0.0, "Z_LOW": 0.0, "Z_HIGH": 0.0, "PATCH_R_M": 1.0}


def disk(rng, n, radius=3.0):
    r = radius*np.sqrt(rng.random(n))
    a = rng.random(n)*2*np.pi
    return r*np.cos(a), r*np.sin(a)


def features(kind, ndvi=0.05, footprint=None, rng=None, ground_z=0.0, n=400):
    """Features of a synthetic patch. Returns: count, number of returns, return number for every point."""
    rng = rng or np.random.default_rng(7)
    x, y = disk(rng, n)
    count, number = np.ones(n, dtype=int), np.ones(n, dtype=int)
    if kind == "roof":
        z, slab = 8+rng.normal(0, .02, n), (7.5, 8.5)
    elif kind == "roof_under_canopy":
        # the roof is seen through the canopy: each point is the LAST return of a multi-return pulse
        z, slab = 8+rng.normal(0, .02, n), (7.5, 8.5)
        count, number = np.full(n, 3), np.full(n, 3)
    elif kind == "tree":
        z, slab = rng.uniform(4, 10, n), (3.5, 10.5)
        count = np.where(rng.random(n) < .7, 3, 1)
        number = np.where(count == 3, rng.integers(1, 3, n), 1)          # first or second of three: canopy returns
    elif kind == "tree_low_slab":
        z, slab = rng.uniform(0, 9, n), (0.2, 1.5)                        # the slab sits low on a tall tree
        count = np.where(rng.random(n) < .7, 3, 1)
        number = np.where(count == 3, rng.integers(1, 3, n), 1)
    elif kind == "shrub":
        z, slab = rng.uniform(0.2, 1.4, n), (0.0, 1.5)
        count = np.where(rng.random(n) < .7, 3, 1)
        number = np.where(count == 3, rng.integers(1, 3, n), 1)
    elif kind == "ground":
        z, slab = .05+rng.normal(0, .02, n), (-.5, .5)
    elif kind == "wall":
        x, y = rng.normal(0, .02, n), rng.uniform(-2.5, 2.5, n)
        z, slab = rng.uniform(2, 6, n), (1.5, 6.5)
    elif kind == "wire":
        x, y = rng.uniform(-3, 3, n), rng.normal(0, .02, n)
        z, slab = 8+rng.normal(0, .02, n), (7.5, 8.5)
        x, y, z, count, number = x[:40], y[:40], z[:40], count[:40], number[:40]
    elif kind == "pole":
        x, y = rng.normal(0, .05, n), rng.normal(0, .05, n)
        z, slab = rng.uniform(0, 7, n), (0, 7)
    elif kind == "tree_over_roof":
        roof = 8+rng.normal(0, .02, n)
        upper = rng.random(n) < .5
        z = np.where(upper, rng.uniform(9, 12, n), roof)
        count = np.where(upper, 3, 1)
        number = np.where(upper, rng.integers(1, 3, n), 1)
        slab = (7.5, 12.5)
    elif kind == "few":
        x, y, z, slab = x[:5], y[:5], 8+rng.normal(0, .02, 5), (7.5, 8.5)
        count, number = count[:5], number[:5]
    else:
        raise ValueError(kind)
    unit = dict(UNIT, Z_LOW=slab[0], Z_HIGH=slab[1])
    return triage.unit_features(unit, x, y, z, count, number, ground_z, ndvi=ndvi, footprint=footprint)


OUT = {"inside": False, "edge_m": 25.0}
IN = {"inside": True, "edge_m": 6.0}
EDGE = {"inside": False, "edge_m": .5}


class Shape(unittest.TestCase):
    def test_eigen_features_tell_plane_line_and_blob_apart(self):
        rng = np.random.default_rng(1)
        plane = np.c_[rng.uniform(-1, 1, 300), rng.uniform(-1, 1, 300), rng.normal(0, .01, 300)]
        line = np.c_[rng.uniform(-1, 1, 300), rng.normal(0, .01, 300), rng.normal(0, .01, 300)]
        blob = rng.normal(0, 1, (300, 3))
        p, l, b = (triage.eigen_features(a) for a in (plane, line, blob))
        self.assertGreater(p["normal_z"], .99); self.assertLess(p["thickness"], .02)
        self.assertGreater(l["linearity"], .9)
        self.assertGreater(b["scattering"], .3); self.assertGreater(b["thickness"], .5)
        self.assertTrue(np.isnan(triage.eigen_features(plane[:3])["thickness"]))


class Proposals(unittest.TestCase):
    def check(self, f, label, tier="AUTO_CANDIDATE"):
        proposal = triage.propose(f)
        self.assertEqual((proposal["label"], proposal["tier"]), (label, tier), proposal)
        return proposal

    def test_each_clear_case_is_proposed_with_its_cues(self):
        self.check(features("roof", ndvi=.05, footprint=IN), "BUILDING_ROOF")
        self.check(features("tree", ndvi=.5, footprint=OUT), "TREE")
        self.check(features("shrub", ndvi=.5, footprint=OUT), "SHRUB_LOW_VEG")
        self.check(features("ground", ndvi=.1, footprint=OUT), "GROUND")
        self.check(features("wall", ndvi=.05, footprint=EDGE), "WALL")
        self.assertIn("inside a surveyed footprint", triage.propose(features("roof", footprint=IN))["cues"])

    def test_a_roof_seen_through_canopy_is_still_a_roof(self):
        # seen on a real unit: a thin flat plane inside a footprint whose points are nearly all multi-return pulses,
        # because each is the last return of a pulse that passed through a tree
        f = features("roof_under_canopy", ndvi=.05, footprint=IN)
        self.assertEqual(f["nonlast"], 0.0)
        self.check(f, "BUILDING_ROOF")

    def test_a_low_slab_on_a_tall_tree_is_not_a_shrub(self):
        f = features("tree_low_slab", ndvi=.5, footprint=OUT)
        self.assertGreater(f["top_hag"], 6)                                              # the neighbourhood is tall
        self.check(f, None, "REVIEW")

    def test_pole_and_wire_are_only_hints_never_auto(self):
        for kind, hint in (("pole", "POLE"), ("wire", "WIRE")):
            proposal = self.check(features(kind, ndvi=.05, footprint=OUT), None, "REVIEW")
            self.assertEqual(proposal["hint"], hint)
            self.assertIn("leaf-off", " ".join(proposal["cues"]))
        self.assertNotIn("POLE", triage.AUTO_CLASSES)
        self.assertNotIn("WIRE", triage.AUTO_CLASSES)

    def test_ambiguous_cases_go_to_review(self):
        self.check(features("tree_over_roof", ndvi=.4, footprint=IN), None, "REVIEW")      # branches over a roof
        self.check(features("roof", ndvi=.05, footprint=OUT), None, "REVIEW")             # a roof-like plane with no footprint
        self.check(features("few", footprint=IN), None, "REVIEW")                         # too few points
        self.assertIn("points in the patch", triage.propose(features("few", footprint=IN))["cues"][0])

    def test_leaf_off_trees_and_missing_cues_are_never_proposed(self):
        self.check(features("tree", ndvi=.05, footprint=OUT), None, "REVIEW")             # low greenness is not evidence
        self.check(features("tree", ndvi=None, footprint=OUT), None, "REVIEW")            # greenness unavailable
        self.check(features("roof", ndvi=None, footprint=IN), None, "REVIEW")             # a needed cue is missing
        self.check(features("tree", ndvi=.5, footprint=None), None, "REVIEW")             # footprint unknown
        self.check(features("roof", ndvi=.5, footprint=IN), None, "REVIEW")               # green on a 'roof'

    def test_several_fitting_classes_go_to_review(self):
        f = features("roof", footprint=IN)
        with mock.patch.object(triage, "fits", return_value={"TREE": ["x"], "BUILDING_ROOF": ["y"]}):
            proposal = triage.propose(f)
        self.assertEqual((proposal["label"], proposal["tier"]), (None, "REVIEW"))
        self.assertIn("several classes fit", proposal["cues"][0])

    def test_no_classification_byte_or_model_field_is_an_input(self):
        import inspect
        source = inspect.getsource(triage.unit_features)
        for forbidden in ("classification", "BASE_CLASS", "TREE_MODEL", "BLDG_MODEL", "SHAPE_GROUP", "CAND_FLAG"):
            self.assertNotIn(forbidden, source)
        self.assertEqual(list(inspect.signature(triage.unit_features).parameters),
                         ["unit", "x", "y", "z", "num_returns", "return_number", "ground_z", "ndvi", "footprint"])

    def test_classes_cannot_overlap_on_the_synthetic_cases(self):
        cases = {"roof": IN, "roof_under_canopy": IN, "tree": OUT, "shrub": OUT, "ground": OUT, "wall": EDGE,
                 "wire": OUT, "pole": OUT}
        for kind, footprint in cases.items():
            for ndvi in (.05, .5):
                found = triage.fits(features(kind, ndvi=ndvi, footprint=footprint))
                self.assertLessEqual(len(found), 1, (kind, ndvi, found))


if __name__ == "__main__":
    unittest.main()
