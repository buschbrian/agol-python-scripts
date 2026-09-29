import unittest
from canopy import evaluation_design as ed


class Domains(unittest.TestCase):
    def test_external_tile_never_enters_millcreek_scope(self):
        scopes=dict(ed.scopes(ed.TILES))
        self.assertEqual(scopes['EXTERNAL_TRANSFER'],['12TVL2203'])
        self.assertNotIn('12TVL2203',scopes['MILLCREEK_PILOT_TILES'])
        self.assertNotIn('ALL',scopes)

    def test_training_excludes_holdout_and_context(self):
        self.assertTrue(ed.assert_training_extents([ed.TILES['12TVL2804']]))
        for extent in (ed.TILES['12TVL3302'],(432900,4502000,432960,4502100)):
            with self.assertRaises(ValueError): ed.assert_training_extents([extent])
