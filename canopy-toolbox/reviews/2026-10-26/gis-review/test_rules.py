import unittest
from review_rules import roof_queue, tree_queue, metres_to_feet


class ReviewRules(unittest.TestCase):
    def test_no_model_is_evidence_gap_not_demolition(self):
        p, flags = roof_queue(None, 'UNVALIDATED;NO_ROOF_SUPPORT')
        self.assertEqual(p, 1)
        self.assertIn('NO_HYBRID_MODEL', flags)
        self.assertIn('NO_ROOF_SUPPORT', flags)
        self.assertNotIn('DEMOLISHED', flags)

    def test_fallback_and_support_remain_separate(self):
        self.assertEqual(roof_queue('Esri LOD1.2', 'UNVALIDATED'), (2, 'BLOCK_FALLBACK'))
        self.assertEqual(roof_queue('Esri LOD2.0', 'UNVALIDATED;LOW_ROOF_SUPPORT'),
                         (2, 'LOD20_FALLBACK;LOW_ROOF_SUPPORT'))

    def test_typical_roofer_is_still_pending_review(self):
        self.assertEqual(roof_queue('roofer LoD2.2', 'UNVALIDATED'), (4, 'ROUTINE_REVIEW'))

    def test_tree_overlap_and_edges_are_only_candidates(self):
        self.assertEqual(tree_queue(True, 26, False, False), (3, 'ROOF_OVERLAP;TILE_EDGE'))
        self.assertEqual(tree_queue(False, 80, True, True),
                         (2, 'ROOF_CENTER;ROOF_OVERLAP;SEAM_OVERLAP_CANDIDATE'))
        self.assertEqual(tree_queue(False, 0, False, False), (4, 'ROUTINE_REVIEW'))

    def test_unit_conversion_preserves_missing_and_rejects_nonfinite(self):
        self.assertIsNone(metres_to_feet(None))
        self.assertIsNone(metres_to_feet(float('nan')))
        self.assertAlmostEqual(metres_to_feet(1), 3.280839895)


if __name__ == '__main__':
    unittest.main()
