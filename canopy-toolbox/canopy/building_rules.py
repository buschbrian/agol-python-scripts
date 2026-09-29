"""Pure rules for reconciling lidar buildings with reference footprints (no arcpy).

Everything here works on NumPy arrays and plain values so the thresholds and status
rules can be tested anywhere. Statuses are review screens, not verified labels: a
footprint "MATCHED" by class-6 returns can still be a wrong footprint, and a lidar
region with "NO_FOOTPRINT" can be a real building that no source has mapped yet.
"""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

# Reference sources. The key is the feature-class name in reference.gdb; the tag is the
# field suffix (IN_<tag>, COV_<tag>). "same_method" sources were made by the same kind of
# classifier as our class 6 and never count as independent evidence for STATUS.
SOURCES = {
    "county": {"tag": "COUNTY", "same_method": False},
    "millcreek_extract": {"tag": "EXTRACT", "same_method": False},
    "osm2024": {"tag": "OSM2024", "same_method": False},
    "osm_current": {"tag": "OSMNOW", "same_method": False},
    "lidar_same_method": {"tag": "LIDARFP", "same_method": True},
}

DEFAULTS = {
    "cell_size_m": 0.5,
    "above_ground_m": 2.0,          # a return counts toward footprint shares above this height
    "min_region_area_m2": 10.0,     # same minimum as the prepare step's building classifier
    "no_returns_cover": 0.10,       # < this share of footprint cells with a return > 2 m: NO_RETURNS_ABOVE_2M
    "matched_share": 0.50,          # class-6 share of returns > 2 m for MATCHED
    "missed_share": 0.50,           # class 3/4/5 share for LIDAR_MISSED ...
    "missed_max_building": 0.10,    # ... while the class-6 share stays below this
    "source_overlap": 0.30,         # share of a footprint's cells inside another source's footprints
    "region_overlap": 0.50,         # share of a lidar region's cells inside a source's buffered footprints
    "footprint_buffer_m": 1.0,      # eaves overhang wall footprints; also the label-LAS exclusion buffer
    "near_roof_m": 1.0,             # candidate test: class-6 points within this horizontal distance
    "ground_radius_m": 5.0,         # candidate test: median class-2 Z within this radius
    "roof_percentile": 90.0,        # candidate test: local roof = this percentile of nearby class-6 Z
    "at_roof_m": 0.5,               # candidate no more than this above the roof: ON_ROOF / ROOF_EDGE
    "overhang_m": 2.0,              # candidate more than this above the roof: OVERHANG
    "fallback_min_building_returns": 10,  # footprint roof height uses class 6 when it has this many returns
}

FOOTPRINT_STATUSES = ("MATCHED", "PARTIAL", "LIDAR_MISSED", "NO_RETURNS_ABOVE_2M")
REGION_STATUSES = ("MATCHED", "NO_FOOTPRINT", "NO_FOOTPRINT_COVERAGE")
FLAGS = ("ON_ROOF", "ROOF_EDGE", "NEAR_ROOF", "OVERHANG", "CLEAR")

# User-definable LAS class codes (64-255 are available only in point formats 6-10).
LABEL_CODES = {
    6: "Confident building: class 6 inside a buffered reference footprint",
    3: "Confident non-building low vegetation class (kept): outside all buffered footprints, not a roof-edge suspect",
    4: "Confident non-building medium vegetation class (kept): as class 3",
    5: "Confident non-building high vegetation class (kept): as class 3",
    64: "Review: class 6 outside all buffered footprints, inside footprint coverage (lidar-only building)",
    65: "Review: class 5 inside a buffered footprint, not more than 2 m above its roof (missed roof, roof edge, or wall)",
    66: "Review: class 3/4/5 outside footprints but within 1 m of class-6 roof support at roof height (roof-edge suspect)",
    67: "Review: class 6 outside footprint coverage (cannot be confirmed)",
    68: "Review: class 5 inside a buffered footprint, more than 2 m above its roof (likely overhanging canopy)",
    69: "Review: class 3/4/5 outside footprint coverage (cannot be confirmed)",
    70: "Review: class 3/4 (below 2 m) inside a buffered footprint (lawn, shrub, or wall return beside a building)",
}


def parameters(**overrides):
    values = dict(DEFAULTS)
    for key, value in overrides.items():
        if key not in values:
            raise ValueError(f"Unknown reconciliation parameter: {key}")
        if value is not None:
            values[key] = value
    for key, value in values.items():
        value = float(value)
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{key} must be finite and non-negative")
    if values["cell_size_m"] <= 0:
        raise ValueError("cell_size_m must be positive")
    for key in ("no_returns_cover", "matched_share", "missed_share", "missed_max_building",
                "source_overlap", "region_overlap"):
        if values[key] > 1:
            raise ValueError(f"{key} is a share and must be between 0 and 1")
    if not 0 <= values["roof_percentile"] <= 100:
        raise ValueError("roof_percentile must be between 0 and 100")
    if values["at_roof_m"] > values["overhang_m"]:
        raise ValueError("at_roof_m must not exceed overhang_m")
    return values


# --- grids -----------------------------------------------------------------------------

def rasterize(rings, xmin, ymax, cell, shape):
    """Flat indices of grid cells whose centres fall inside the polygon (even-odd rule).

    rings: list of (N, 2) coordinate arrays, outer rings and holes together. Holes are
    handled by the even-odd rule, which also matches how overlapping parts cancel.
    Returns (indices, truncated) where truncated is True when the polygon extends
    beyond the grid.
    """
    rows, cols = shape
    edges = []
    for ring in rings:
        ring = np.asarray(ring, dtype=float)
        if len(ring) < 3:
            continue
        if not np.array_equal(ring[0], ring[-1]):
            ring = np.vstack([ring, ring[:1]])
        edges.append(np.column_stack([ring[:-1], ring[1:]]))
    if not edges:
        return np.array([], dtype=np.int64), False
    edges = np.vstack(edges)
    xs, ys = edges[:, [0, 2]], edges[:, [1, 3]]
    xmax, ymin = xmin + cols*cell, ymax - rows*cell
    truncated = bool(xs.min() < xmin or xs.max() > xmax or ys.min() < ymin or ys.max() > ymax)
    # Row r has centre y = ymax - (r + .5) * cell.
    r0 = max(0, int(math.floor((ymax - ys.max())/cell - .5)))
    r1 = min(rows - 1, int(math.ceil((ymax - ys.min())/cell - .5)))
    x1, y1, x2, y2 = edges.T
    found = []
    for r in range(r0, r1 + 1):
        yc = ymax - (r + .5)*cell
        crossing = (y1 <= yc) != (y2 <= yc)
        if not crossing.any():
            continue
        t = (yc - y1[crossing])/(y2[crossing] - y1[crossing])
        xc = np.sort(x1[crossing] + t*(x2[crossing] - x1[crossing]))
        for left, right in zip(xc[0::2], xc[1::2]):
            # Cell c has centre x = xmin + (c + .5) * cell; include left <= centre < right.
            c0 = max(0, int(math.ceil((left - xmin)/cell - .5)))
            c1 = min(cols - 1, int(math.ceil((right - xmin)/cell - .5)) - 1)
            if c1 >= c0:
                found.append(r*cols + np.arange(c0, c1 + 1, dtype=np.int64))
    indices = np.unique(np.concatenate(found)) if found else np.array([], dtype=np.int64)
    return indices, truncated


def dilate(mask, distance, cell):
    """Cells within `distance` (Euclidean, cell-centre) of any True cell."""
    mask = np.asarray(mask, dtype=bool)
    if distance <= 0 or not mask.any():
        return mask.copy()
    return ndimage.distance_transform_edt(~mask, sampling=cell) <= distance + 1e-9


def roof_regions(support, cell, min_area):
    """Label class-6 roof support after a 3x3 closing, the same closing refine-roofs uses.

    A 3x3 closing bridges gaps of up to two empty cells (1 m at 0.5 m cells), so roofs
    closer than that merge into one region.

    Regions smaller than min_area (counted on supported cells, not bridged cells) are dropped.
    Returns (labels, count) with labels renumbered 1..count in scan order.
    """
    support = np.asarray(support, dtype=bool)
    connected = ndimage.binary_closing(support, structure=np.ones((3, 3))) | support
    labels, count = ndimage.label(connected, structure=np.ones((3, 3)))
    if not count:
        return labels, 0
    supported = np.bincount(labels[support], minlength=count + 1)
    keep = supported*cell**2 >= min_area
    keep[0] = False
    remap = np.zeros(count + 1, dtype=np.int32)
    remap[keep] = np.arange(1, int(keep.sum()) + 1)
    return remap[labels], int(keep.sum())


def gather(sorted_cells, cells):
    """Positions in a cell-sorted point array whose cell is in `cells`."""
    cells = np.unique(np.asarray(cells, dtype=np.int64))
    if not cells.size or not len(sorted_cells):
        return np.array([], dtype=np.int64)
    start = np.searchsorted(sorted_cells, cells, "left")
    stop = np.searchsorted(sorted_cells, cells, "right")
    lengths = stop - start
    total = int(lengths.sum())
    if not total:
        return np.array([], dtype=np.int64)
    offsets = np.repeat(start - np.concatenate([[0], np.cumsum(lengths)[:-1]]), lengths)
    return offsets + np.arange(total)


# --- statistics and statuses -------------------------------------------------------------

def height_stats(heights):
    """Median, 90th percentile, and maximum; None when there are no values."""
    heights = np.asarray(heights, dtype=float)
    heights = heights[np.isfinite(heights)]
    if not heights.size:
        return {"n": 0, "p50": None, "p90": None, "max": None}
    return {"n": int(heights.size), "p50": float(np.median(heights)),
            "p90": float(np.percentile(heights, 90)), "max": float(heights.max())}


def class_shares(classes):
    """Counts and shares of class 6, class 3/4/5, and other classes among returns."""
    classes = np.asarray(classes)
    n = int(classes.size)
    n6 = int(np.count_nonzero(classes == 6))
    nveg = int(np.count_nonzero(np.isin(classes, (3, 4, 5))))
    other = n - n6 - nveg
    share = (lambda k: k/n) if n else (lambda k: None)
    return {"n": n, "n6": n6, "nveg": nveg, "nother": other,
            "share6": share(n6), "shareveg": share(nveg), "shareother": share(other)}


def footprint_status(cover_above, share6, shareveg, p):
    """Status of one footprint from the returns more than 2 m above ground inside it.

    cover_above: share of the footprint's cells holding at least one such first return.
    """
    if cover_above is None or cover_above < p["no_returns_cover"] or share6 is None:
        return "NO_RETURNS_ABOVE_2M"
    if share6 >= p["matched_share"]:
        return "MATCHED"
    if shareveg >= p["missed_share"] and share6 < p["missed_max_building"]:
        return "LIDAR_MISSED"
    return "PARTIAL"


def footprint_roof_height(h6_p90, n6, hall_p50, p):
    """Roof height used to judge candidates inside a footprint, with its basis."""
    if h6_p90 is not None and n6 >= p["fallback_min_building_returns"]:
        return h6_p90, "CLASS6_P90"
    if hall_p50 is not None:
        return hall_p50, "ALL_FIRST_P50"
    return None, None


def region_status(inside, covered):
    """inside/covered: {source: bool}. Same-method sources never decide the status."""
    independent = [name for name in inside if not SOURCES.get(name, {}).get("same_method", False)]
    if any(inside[name] for name in independent):
        return "MATCHED"
    if any(covered.get(name, False) for name in independent):
        return "NO_FOOTPRINT"
    return "NO_FOOTPRINT_COVERAGE"


def candidate_flag(height, local_roof, inside, footprint_roof, p):
    """Flag one tree candidate. Returns (flag, above_roof_m, basis).

    local_roof: roof height above ground from class-6 points within near_roof_m, or None.
    footprint_roof: roof height of the footprint containing the candidate, or None.
    """
    if local_roof is not None:
        roof, basis = local_roof, "CLASS6_1M"
    elif inside and footprint_roof is not None:
        roof, basis = footprint_roof, "FOOTPRINT"
    else:
        return "CLEAR", None, None
    above = float(height - roof)
    if above > p["overhang_m"]:
        return "OVERHANG", above, basis
    if above <= p["at_roof_m"]:
        return ("ON_ROOF" if inside else "ROOF_EDGE"), above, basis
    return "NEAR_ROOF", above, basis


def label_codes(classes, in_zone, covered, edge_suspect, above_footprint_roof, p):
    """Label class for each point (vectorized). Classes outside 3/4/5/6 are unchanged.

    above_footprint_roof: height above the local footprint roof (NaN when unknown).
    """
    classes = np.asarray(classes)
    codes = classes.copy()
    building = classes == 6
    vegetation = np.isin(classes, (3, 4, 5))
    codes[building & ~in_zone & covered] = 64
    codes[building & ~in_zone & ~covered] = 67
    over = np.nan_to_num(np.asarray(above_footprint_roof, dtype=float), nan=-np.inf) > p["overhang_m"]
    high = classes == 5
    codes[high & in_zone & ~over] = 65
    codes[high & in_zone & over] = 68
    codes[vegetation & ~high & in_zone] = 70
    outside = vegetation & ~in_zone
    codes[outside & edge_suspect] = 66
    codes[outside & ~covered & ~edge_suspect] = 69
    return codes


def height_comparison(reference, lidar, ids=None, outlier_m=3.0):
    """Compare reference heights (BLDGHEIGHT) with lidar heights in the same unit.

    Returns n, median ratio lidar/reference (about 1 for metres, about 0.30 if the
    reference were feet), bias (median lidar - reference), mean difference, median
    absolute difference, and the pairs whose absolute difference exceeds outlier_m.
    """
    reference = np.asarray(reference, dtype=float)
    lidar = np.asarray(lidar, dtype=float)
    ids = list(ids) if ids is not None else list(range(len(reference)))
    valid = np.isfinite(reference) & np.isfinite(lidar) & (reference > 0)
    if not valid.any():
        return {"n": 0}
    ref, lid = reference[valid], lidar[valid]
    kept = [i for i, ok in zip(ids, valid) if ok]
    diff = lid - ref
    outliers = [{"id": kept[i], "reference": float(ref[i]), "lidar": float(lid[i]), "difference": float(diff[i])}
                for i in np.flatnonzero(np.abs(diff) > outlier_m)]
    return {"n": int(valid.sum()), "median_ratio": float(np.median(lid/ref)),
            "bias_median_m": float(np.median(diff)), "mean_difference_m": float(diff.mean()),
            "median_abs_difference_m": float(np.median(np.abs(diff))),
            "p90_abs_difference_m": float(np.percentile(np.abs(diff), 90)),
            "outlier_threshold_m": outlier_m, "outliers": sorted(outliers, key=lambda o: -abs(o["difference"]))}


def best_shift(footprints, roofs, max_shift, cell):
    """Offset (metres, east/north) that moves footprint cells onto lidar roof cells.

    Compares two boolean grids for every whole-cell shift up to max_shift cells and
    reports overlap (intersection over union) at zero shift and at the best shift. A
    best shift near zero means footprints and lidar are registered to within a cell. It
    does not measure footprint accuracy: roofs overhang walls and imagery tracing leans.
    """
    a, b = np.asarray(footprints, dtype=bool), np.asarray(roofs, dtype=bool)
    if a.shape != b.shape:
        raise ValueError("Grids must match")
    m = int(max_shift)
    rows, cols = a.shape
    if rows <= 2*m or cols <= 2*m:
        raise ValueError("Grid too small for the requested shift")
    target = b[m:rows-m, m:cols-m]
    results = []
    for dy in range(-m, m+1):
        for dx in range(-m, m+1):
            # Footprints moved east by dx and north by dy: target cell (r, c) takes (r + dy, c - dx).
            moved = a[m+dy:rows-m+dy, m-dx:cols-m-dx]
            both = int(np.count_nonzero(moved & target))
            union = int(np.count_nonzero(moved)) + int(np.count_nonzero(target)) - both
            results.append((both/union if union else 0.0, dx, dy))
    zero = next(r for r in results if r[1] == 0 and r[2] == 0)
    best = max(results, key=lambda r: (r[0], -abs(r[1])-abs(r[2])))
    return {"iou_at_zero": zero[0], "iou_best": best[0], "shift_east_m": best[1]*cell,
            "shift_north_m": best[2]*cell, "max_shift_m": m*cell}
