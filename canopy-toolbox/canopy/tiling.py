"""Tile grid and seam reconciliation.

These helpers provide aligned, nonoverlapping raster cores with buffered
interpolation context. Point ownership is exact for supplied points, but neither
finite buffers nor ownership guarantee equivalent watershed segmentation.
The runner detects and segments the whole assembled AOI under a size limit.

Pure Python: no arcpy, so it is unit-testable outside ArcGIS Pro.
"""

from __future__ import annotations

import math
from typing import Iterable, Iterator, NamedTuple


class Extent(NamedTuple):
    xmin: float
    ymin: float
    xmax: float
    ymax: float

    @property
    def width(self) -> float:
        return self.xmax - self.xmin

    @property
    def height(self) -> float:
        return self.ymax - self.ymin

    def buffered(self, distance: float) -> "Extent":
        return Extent(
            self.xmin - distance,
            self.ymin - distance,
            self.xmax + distance,
            self.ymax + distance,
        )

    def clipped_to(self, other: "Extent") -> "Extent":
        return Extent(
            max(self.xmin, other.xmin),
            max(self.ymin, other.ymin),
            min(self.xmax, other.xmax),
            min(self.ymax, other.ymax),
        )

    def as_arcpy_string(self) -> str:
        return f"{self.xmin} {self.ymin} {self.xmax} {self.ymax}"


class Tile(NamedTuple):
    row: int
    col: int
    core: Extent
    buffered: Extent

    @property
    def name(self) -> str:
        return f"r{self.row:03d}c{self.col:03d}"

    def owns(self, x: float, y: float) -> bool:
        """Half-open on the upper edges so adjacent cores never both claim a point."""
        return (
            self.core.xmin <= x < self.core.xmax
            and self.core.ymin <= y < self.core.ymax
        )


def snap_extent(extent: Extent, cell_size: float, origin: tuple[float, float] | None = None) -> Extent:
    """Grow an extent outward to whole cells on a shared grid origin.

    Every tile must land on the same grid as the CHM. A half-cell offset between
    the DSM and DTM puts a rim of false height around every crown edge, and those
    rims become treetops.
    """
    if not math.isfinite(cell_size) or cell_size <= 0:
        raise ValueError("cell size must be positive")
    if not all(math.isfinite(v) for v in extent) or extent.width <= 0 or extent.height <= 0:
        raise ValueError('extent must be finite and have positive width and height')
    ox, oy = origin or (0.0, 0.0)
    if not all(math.isfinite(v) for v in (ox, oy)):
        raise ValueError('grid origin must be finite')
    return Extent(
        ox + math.floor((extent.xmin - ox) / cell_size) * cell_size,
        oy + math.floor((extent.ymin - oy) / cell_size) * cell_size,
        ox + math.ceil((extent.xmax - ox) / cell_size) * cell_size,
        oy + math.ceil((extent.ymax - oy) / cell_size) * cell_size,
    )


def tile_grid(
    extent: Extent,
    tile_size: float,
    overlap: float,
    cell_size: float = 0.5,
) -> list[Tile]:
    """Cover `extent` with snapped, non-overlapping cores plus buffered halos."""
    if not math.isfinite(tile_size) or tile_size <= 0:
        raise ValueError("tile size must be positive")
    if not math.isfinite(overlap) or overlap < 0:
        raise ValueError("overlap cannot be negative")
    if overlap >= tile_size / 2:
        raise ValueError("overlap must be smaller than half the tile size")

    grid = snap_extent(extent, cell_size)
    for name, value in [('tile size', tile_size), ('overlap', overlap)]:
        if not math.isclose(value / cell_size, round(value / cell_size), abs_tol=1e-8):
            raise ValueError(f'{name} must be a whole number of raster cells')
    n_cols = max(1, math.ceil(grid.width / tile_size))
    n_rows = max(1, math.ceil(grid.height / tile_size))

    tiles: list[Tile] = []
    for row in range(n_rows):
        for col in range(n_cols):
            core = Extent(
                grid.xmin + col * tile_size,
                grid.ymin + row * tile_size,
                min(grid.xmin + (col + 1) * tile_size, grid.xmax),
                min(grid.ymin + (row + 1) * tile_size, grid.ymax),
            )
            if core.width <= 0 or core.height <= 0:
                continue
            tiles.append(Tile(row, col, core, core.buffered(overlap)))
    return tiles


def owning_tile(tiles: Iterable[Tile], x: float, y: float) -> Tile | None:
    for tile in tiles:
        if tile.owns(x, y):
            return tile
    return None


def dedupe_by_core(
    detections: Iterable[tuple[float, float, object]],
    tile: Tile,
) -> Iterator[tuple[float, float, object]]:
    """Keep only the detections this tile owns. Run per tile before merging."""
    for x, y, payload in detections:
        if tile.owns(x, y):
            yield x, y, payload


def recommended_overlap(bands: Iterable[object], minimum: float = 15.0) -> float:
    """Halo wide enough that the largest search window fits inside it.

    The default is raster interpolation context, not a guarantee that all crown
    influence fits within a halo. Whole-AOI segmentation is required for that.
    """
    radii = [getattr(band, "radius", 0.0) for band in bands]
    return max(minimum, (max(radii) if radii else 0.0) * 6.0)
