import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from canopy.bands import DEFAULT_BANDS
from canopy.tiling import (
    Extent,
    dedupe_by_core,
    owning_tile,
    recommended_overlap,
    snap_extent,
    tile_grid,
)


class SnapExtent(unittest.TestCase):
    def test_grows_outward_to_whole_cells(self):
        snapped = snap_extent(Extent(0.3, 0.3, 9.8, 9.8), 0.5)
        self.assertEqual(snapped, Extent(0.0, 0.0, 10.0, 10.0))

    def test_already_snapped_is_unchanged(self):
        extent = Extent(0.0, 0.0, 10.0, 10.0)
        self.assertEqual(snap_extent(extent, 0.5), extent)

    def test_negative_coordinates(self):
        snapped = snap_extent(Extent(-0.3, -0.3, 1.2, 1.2), 0.5)
        self.assertEqual(snapped, Extent(-0.5, -0.5, 1.5, 1.5))


class TileGrid(unittest.TestCase):
    def setUp(self):
        self.tiles = tile_grid(Extent(0, 0, 1000, 1000), 400, 15)

    def test_covers_extent(self):
        self.assertEqual(len(self.tiles), 9)

    def test_cores_do_not_overlap(self):
        for a in self.tiles:
            for b in self.tiles:
                if a is b:
                    continue
                separated = (
                    a.core.xmax <= b.core.xmin
                    or b.core.xmax <= a.core.xmin
                    or a.core.ymax <= b.core.ymin
                    or b.core.ymax <= a.core.ymin
                )
                self.assertTrue(separated, f"{a.name} overlaps {b.name}")

    def test_buffer_applied(self):
        tile = self.tiles[0]
        self.assertEqual(tile.buffered.xmin, tile.core.xmin - 15)
        self.assertEqual(tile.buffered.ymax, tile.core.ymax + 15)

    def test_edge_tiles_are_clipped_not_padded(self):
        last = self.tiles[-1]
        self.assertEqual(last.core.xmax, 1000)
        self.assertEqual(last.core.ymax, 1000)

    def test_overlap_at_least_half_tile_rejected(self):
        with self.assertRaises(ValueError):
            tile_grid(Extent(0, 0, 100, 100), 40, 20)

    def test_unsnapped_tile_and_halo_are_rejected(self):
        for size, overlap in [(4.1, .5), (4, .3)]:
            with self.subTest(size=size, overlap=overlap), self.assertRaises(ValueError):
                tile_grid(Extent(0, 0, 10, 10), size, overlap, .5)

    def test_invalid_extent_rejected(self):
        with self.assertRaises(ValueError):
            tile_grid(Extent(10, 0, 0, 10), 4, .5, .5)

    def test_area_smaller_than_tile_gives_one_tile(self):
        self.assertEqual(len(tile_grid(Extent(0, 0, 50, 50), 400, 15)), 1)


class SeamOwnership(unittest.TestCase):
    def setUp(self):
        self.tiles = tile_grid(Extent(0, 0, 1000, 1000), 400, 15)

    def test_every_point_owned_exactly_once(self):
        # A tree on a seam must be kept by one tile and dropped by its neighbour.
        for x, y in ((400.0, 400.0), (0.0, 0.0), (399.999, 200.0), (750.0, 999.999)):
            owners = [t for t in self.tiles if t.owns(x, y)]
            self.assertEqual(len(owners), 1, f"({x}, {y}) owned by {len(owners)} tiles")

    def test_upper_boundary_of_study_area_is_not_owned(self):
        # Half-open cores mean the outer max edge falls outside; the grid is
        # snapped outward so real data never sits exactly on it.
        self.assertIsNone(owning_tile(self.tiles, 1000.0, 1000.0))

    def test_dedupe_keeps_only_owned_detections(self):
        tile = self.tiles[0]  # core 0..400
        detections = [(10.0, 10.0, "a"), (410.0, 10.0, "b"), (399.0, 399.0, "c")]
        kept = [d[2] for d in dedupe_by_core(detections, tile)]
        self.assertEqual(kept, ["a", "c"])

    def test_halo_detections_dropped_by_both_tiles_but_kept_by_owner(self):
        detections = [(405.0, 100.0, "seam")]
        kept = []
        for tile in self.tiles:
            kept.extend(d[2] for d in dedupe_by_core(detections, tile))
        self.assertEqual(kept, ["seam"])


class RecommendedOverlap(unittest.TestCase):
    def test_floor_applies_for_small_radii(self):
        self.assertEqual(recommended_overlap(DEFAULT_BANDS), 15.0)

    def test_scales_with_largest_radius(self):
        from canopy.bands import Band

        self.assertEqual(recommended_overlap([Band(2, None, 4.0)]), 24.0)


if __name__ == "__main__":
    unittest.main()
