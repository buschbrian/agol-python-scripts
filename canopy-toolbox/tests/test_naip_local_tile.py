import importlib.util
from pathlib import Path
import unittest

import numpy as np

REVIEWS = Path(__file__).resolve().parents[1]/"reviews"/"2026-10-01"
spec = importlib.util.spec_from_file_location("naip_local_tile", REVIEWS/"naip_local_tile.py")
nl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nl)


class GridIndices(unittest.TestCase):
    def test_cell_centres_map_to_the_containing_sheet_cell(self):
        # Sheet origin x 100, top y 200, 0.6 m cells; output is 2 x 2 cells of 0.5 m over x 100..101, y 199..200.
        col, row = nl.grid_indices(100.0, 200.0, 0.6, (100.0, 199.0, 101.0, 200.0), 0.5)
        # centres x = 100.25, 100.75 -> columns 0, 1; centres y = 199.75, 199.25 -> rows 0, 1
        self.assertEqual(col.tolist(), [[0, 1], [0, 1]])
        self.assertEqual(row.tolist(), [[0, 0], [1, 1]])

    def test_rows_run_north_to_south(self):
        _, row = nl.grid_indices(0.0, 10.0, 1.0, (0.0, 6.0, 2.0, 10.0), 1.0)
        self.assertEqual(row[:, 0].tolist(), [0, 1, 2, 3])

    def test_rejects_an_extent_that_is_not_whole_cells(self):
        with self.assertRaises(ValueError):
            nl.grid_indices(0.0, 10.0, 0.6, (0.0, 0.0, 1.0, 0.7), 0.5)


class Paste(unittest.TestCase):
    def sheet(self, value, h, w):
        return np.full((4, h, w), value, dtype=np.uint8)

    def test_first_sheet_wins_and_overlap_is_counted(self):
        out = np.zeros((4, 2, 2), dtype=np.uint8)
        filled = np.zeros((2, 2), dtype=bool)
        col, row = np.meshgrid(np.arange(2), np.arange(2))
        written, overlap, _ = nl.paste(out, filled, self.sheet(10, 2, 2), col, row)
        self.assertEqual((written, overlap), (4, 0))
        written, overlap, mask = nl.paste(out, filled, self.sheet(99, 2, 2), col, row)
        self.assertEqual((written, overlap, int(mask.sum())), (0, 4, 4))
        self.assertTrue((out == 10).all())

    def test_cells_outside_the_sheet_are_left_for_the_next_one(self):
        out = np.zeros((4, 1, 4), dtype=np.uint8)
        filled = np.zeros((1, 4), dtype=bool)
        col = np.array([[-1, 0, 1, 2]])
        row = np.zeros((1, 4), dtype=np.int64)
        written, overlap, _ = nl.paste(out, filled, self.sheet(5, 1, 2), col, row)
        self.assertEqual((written, overlap), (2, 0))
        self.assertEqual(filled.tolist(), [[False, True, True, False]])
        self.assertEqual(out[0, 0].tolist(), [0, 5, 5, 0])


if __name__ == "__main__":
    unittest.main()
