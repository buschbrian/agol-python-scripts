import unittest
from canopy import plot_census as pc


class Census(unittest.TestCase):
    def test_draw_is_fixed_and_ignores_candidate_locations(self):
        plots=pc.draw_plots({'t':(0,0,100,100)},4,123)
        self.assertEqual(plots,pc.draw_plots({'t':(0,0,100,100)},4,123))
        self.assertEqual(len({p['plot_id'] for p in plots}),4)
        self.assertTrue(all(p['population_plots']==9 for p in plots))
        self.assertTrue(all(p['extent'][2]-p['extent'][0]==30 for p in plots))

    def test_one_tree_two_candidates_counts_duplicate_and_missed_tree(self):
        result=pc.score_objects([[5,5],[20,20]],[[5,5],[5.5,5],[29,29]],radius=1.5)
        self.assertEqual((result['tp'],result['fp'],result['fn'],result['duplicates']),(1,2,1,1))
        self.assertAlmostEqual(result['recall'],.5)
        self.assertAlmostEqual(result['false_detection_rate'],2/3)
        self.assertAlmostEqual(result['f1'],.4)

    def test_empty_plot_and_bad_coordinates(self):
        self.assertIsNone(pc.score_objects([],[])['f1'])
        self.assertEqual(pc.score_objects([],[[1,1]])['fp'],1)
        with self.assertRaises(ValueError): pc.score_objects([[float('nan'),0]],[])
