import importlib.util
from pathlib import Path
import unittest

import numpy as np

SCRIPT = Path(__file__).resolve().parents[1]/"reviews"/"2026-10-19"/"fractal-city"/"summarize_refined.py"
spec = importlib.util.spec_from_file_location("summarize_refined", SCRIPT)
sr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sr)


class Cells(unittest.TestCase):
    def test_a_treetop_centre_and_its_cell_points_share_a_key(self):
        centre = sr.cell_keys([430193.75], [4507301.25])[0]
        inside = sr.cell_keys([430193.5, 430193.99], [4507301.0, 4507301.49])
        outside = sr.cell_keys([430194.0, 430193.75], [4507301.25, 4507301.5])
        self.assertTrue((inside == centre).all())
        self.assertTrue((outside != centre).all())

    def test_top_point_is_the_highest_in_each_cell(self):
        keys = np.array([7, 3, 7, 3, 9])
        z = np.array([1.0, 5.0, 4.0, 2.0, 0.5])
        distinct, top = sr.top_points(keys, z)
        self.assertEqual(distinct.tolist(), [3, 7, 9])
        self.assertEqual(top.tolist(), [1, 2, 4])


if __name__ == "__main__":
    unittest.main()
