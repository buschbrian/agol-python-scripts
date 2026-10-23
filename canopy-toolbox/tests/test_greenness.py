import unittest
import numpy as np
from canopy import greenness


class Greenness(unittest.TestCase):
    def test_unsigned_bands_use_signed_float_math_and_invalid_pixels_stay_unknown(self):
        red=np.array([200,20,0,0],dtype=np.uint8);nir=np.array([20,200,0,10],dtype=np.uint8)
        value=greenness.ndvi(red,nir,valid=np.array([True,True,True,False]))
        self.assertAlmostEqual(value[0],-180/220)
        self.assertAlmostEqual(value[1],180/220)
        self.assertTrue(np.isnan(value[2:]).all())

    def test_screen_is_a_review_flag_and_never_changes_classifications(self):
        result=greenness.screen(np.array([[.1,.8,np.nan]]),.3)
        self.assertEqual(result.tolist(),[['LOW_GREENNESS_REVIEW','GREEN_SPECTRAL_SUPPORT','UNKNOWN']])
        with self.assertRaises(ValueError): greenness.screen(np.array([.2]),2)
