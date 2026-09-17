import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from canopy.bands import (
    Band,
    DEFAULT_BANDS,
    DEFAULT_SPEC,
    parse_bands,
    radius_for_height,
    radius_in_cells,
    validate_bands,
)


class ParseBands(unittest.TestCase):
    def test_default_spec_round_trips(self):
        self.assertEqual(parse_bands(DEFAULT_SPEC), DEFAULT_BANDS)

    def test_open_ended_final_band(self):
        self.assertIsNone(parse_bands("2-:1.5")[0].high)

    def test_whitespace_and_trailing_comma(self):
        self.assertEqual(len(parse_bands(" 2-6:1.0 ,  6-:2.0 , ")), 2)

    def test_malformed_chunk_raises(self):
        with self.assertRaises(ValueError):
            parse_bands("2 to 6 = 1.0")


class ValidateBands(unittest.TestCase):
    def test_gap_between_bands_rejected(self):
        with self.assertRaises(ValueError):
            validate_bands([Band(2, 6, 1.0), Band(8, None, 2.0)])

    def test_overlap_rejected(self):
        with self.assertRaises(ValueError):
            validate_bands([Band(2, 8, 1.0), Band(6, None, 2.0)])

    def test_closed_final_band_rejected(self):
        # A closed top band silently drops every tree above it.
        with self.assertRaises(ValueError):
            validate_bands([Band(2, 20, 1.0)])

    def test_non_positive_radius_rejected(self):
        with self.assertRaises(ValueError):
            validate_bands([Band(2, None, 0)])

    def test_descending_band_rejected(self):
        with self.assertRaises(ValueError):
            validate_bands([Band(6, 2, 1.0)])

    def test_nonfinite_parameters_rejected(self):
        for spec in ("2-:nan", "2-:inf", "nan-:1", "2-inf:1"):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                parse_bands(spec)

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            validate_bands([])


class RadiusLookup(unittest.TestCase):
    def test_boundaries_are_half_open(self):
        self.assertEqual(radius_for_height(DEFAULT_BANDS, 6.0), 1.5)
        self.assertEqual(radius_for_height(DEFAULT_BANDS, 5.999), 1.0)

    def test_below_threshold_is_not_a_tree(self):
        self.assertIsNone(radius_for_height(DEFAULT_BANDS, 1.9))

    def test_tall_tree_uses_open_band(self):
        self.assertEqual(radius_for_height(DEFAULT_BANDS, 45.0), 2.5)

    def test_cells_never_round_to_zero(self):
        self.assertEqual(radius_in_cells(0.1, 0.5), 1)

    def test_cells_at_half_metre(self):
        self.assertEqual(radius_in_cells(1.5, 0.5), 3)
        self.assertEqual(radius_in_cells(2.5, 0.5), 5)

    def test_bad_cell_size_rejected(self):
        with self.assertRaises(ValueError):
            radius_in_cells(1.0, 0)


if __name__ == "__main__":
    unittest.main()
