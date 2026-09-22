"""Array-only quality metrics for bounded LiDAR planning products."""
from collections import deque

import numpy as np
from scipy import ndimage


def height_summary(roof, ground, mask):
    """Summarize paired roof/terrain cells without converting missing data to zero."""
    roof, ground, mask = np.asarray(roof), np.asarray(ground), np.asarray(mask, dtype=bool)
    if roof.shape != ground.shape or roof.shape != mask.shape:
        raise ValueError("Roof, ground, and mask grids must match")
    paired = mask & np.isfinite(roof) & np.isfinite(ground)
    n, supported = int(mask.sum()), int(paired.sum())
    heights = roof[paired] - ground[paired]
    result = {"GRID_CELLS": n, "ROOF_CELLS": supported,
              "ROOF_COV_PCT": 100 * supported / n if n else None,
              "ROOF_Z50_M": None, "GROUND_Z50_M": None,
              "HEIGHT_P50_M": None, "HEIGHT_P95_M": None, "HEIGHT_MAX_M": None,
              "NEG_H_CELLS": int((heights < 0).sum())}
    if supported:
        result.update(ROOF_Z50_M=float(np.median(roof[paired])),
                      GROUND_Z50_M=float(np.median(ground[paired])),
                      HEIGHT_P50_M=float(np.median(heights)),
                      HEIGHT_P95_M=float(np.percentile(heights, 95)),
                      HEIGHT_MAX_M=float(heights.max()))
    return result


def boundary_influence(direction, valid):
    """Conservative D8 downstream mask seeded at edges and cells beside NoData.

    A zero means no traced boundary connection, not hydrologic completeness.
    D8 uses east=1, southeast=2, south=4, southwest=8, west=16,
    northwest=32, north=64, northeast=128. Array rows increase southward.
    """
    direction, valid = np.asarray(direction), np.asarray(valid, dtype=bool)
    if direction.shape != valid.shape or valid.ndim != 2:
        raise ValueError("Direction and valid grids must be matching 2D arrays")
    marked = valid & ~ndimage.binary_erosion(valid, structure=np.ones((3, 3)), border_value=0)
    pending = deque(zip(*np.nonzero(marked)))
    offsets = {1: (0, 1), 2: (1, 1), 4: (1, 0), 8: (1, -1),
               16: (0, -1), 32: (-1, -1), 64: (-1, 0), 128: (-1, 1)}
    rows, cols = valid.shape
    while pending:
        row, col = pending.popleft()
        step = offsets.get(int(direction[row, col]))
        if step is None:
            continue
        nr, nc = row + step[0], col + step[1]
        if 0 <= nr < rows and 0 <= nc < cols and valid[nr, nc] and not marked[nr, nc]:
            marked[nr, nc] = True
            pending.append((nr, nc))
    return marked
