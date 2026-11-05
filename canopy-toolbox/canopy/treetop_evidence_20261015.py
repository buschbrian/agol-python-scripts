"""Review evidence for detected treetops: is this peak on a roof edge, a wire, a pole or a wall? No ArcPy.

Every value here is a measurement of the points around a treetop, and every flag is a fixed rule over those values.
They are REVIEW EVIDENCE, never labels: they must not enter reference.gdb, training labels or a score, and a flagged
treetop is not thereby a false detection. A flag count is a suspect count, not an error rate; rates need the
independent reference labels.

Two groups of measurements:

* Near-building, exactly as the 29 September candidates_near_buildings.py review defined it: class-6 points within
  1 m horizontally, the local roof height (90th-percentile class-6 Z within 1 m minus the median class-2 Z within 5 m)
  and the treetop's HEIGHT_M against that roof height. These read the classification bytes, so they describe where a
  peak sits relative to what the building step called building, not what the peak is.
* Shape and returns, from the raw points as in triage.py: the top 1 m of non-ground, non-noise points within 1 m of
  the treetop (its plane-fit thickness, normal, linearity and non-last-return share) and the above-ground points
  within 3 m (whether they form one line, and its direction). The thresholds are triage.py's, fixed before any human
  label; footprint and NAIP cues are not used here.

Two definition corrections were made after the first 12TVL2804 pilot pass (15 October), from the geometry of
unlabelled treetops, with no human label consulted:
  1. POLE_HINT is reported but is not part of SUSPECT. Without NAIP greenness, a tall narrow crown inside a 3 m context
     is a vertical line too: the 2,120 pilot hits were mostly 8-20 m tall (10th-90th percentile), with a median crown
     of 13 m2 and a median non-last share of 0.95 in their top. triage.py already treats POLE as a hint for the same
     reason. Evidence: reviews/2026-10-15/pilot-feature-profile.json.
  2. CANOPY_RETURNS means "not a thin surface": top thickness above FLAT_TOP's 0.10 m limit. triage.py's 0.25 m was set
     for a tall patch cylinder; a 1 m deep, 1 m radius top cap cannot exceed about 0.29 m even when it is fully
     volumetric, so 0.25 m held only 1,366 of 17,389 pilot treetops.
"""
import math

import numpy as np
from scipy.spatial import cKDTree

from . import las_records
from .triage import eigen_features

STATUS = "UNVALIDATED_REVIEW_EVIDENCE"
NEAR_M = 1.0             # class-6 points this close (horizontal) make a treetop near a building
GROUND_M = 5.0           # local ground: median class-2 Z within this horizontal distance
ROOF_PERCENTILE = 90
TOP_RADIUS_M = 1.0       # the top set: points within this horizontal distance ...
TOP_DEPTH_M = 1.0        # ... and within this depth of the highest of them
CONTEXT_M = 3.0          # triage.CONTEXT_RADIUS_M
ABOVE_GROUND_M = 0.3     # triage.ABOVE_GROUND_M
BUILDING_SEARCH_M = 5.0  # nearest class-6 distance is reported up to this distance
HALO_M = max(GROUND_M, CONTEXT_M, BUILDING_SEARCH_M)
EXCLUDED_CLASSES = (2, 7, 18)
BANDS = ("at_roof_height_le_0.5m", "0.5_to_2m_above_roof", "over_2m_above_roof")

# Flag rules. Numbers are triage.py's ROOF/WIRE/POLE/WALL/TREE cues without their footprint and NDVI parts, and the
# 29 September roof bands. Changing one changes the evidence version recorded in every manifest.
RULES = {
    "roof_height_above_roof_max": .5, "overhang_above_roof_min": 2.0,
    "flat_thickness_max": .10, "flat_normal_z_min": .85, "flat_nonlast_max": .15, "min_top_points": 12,
    "wire_ctx_linearity_min": .85, "wire_ctx_axis_z_max": .50, "wire_top_hag_min": 4.0,
    "wire_building_clear_m": 2.0, "wire_top_points_max": 60,
    "pole_ctx_linearity_min": .85, "pole_ctx_axis_z_min": .90, "pole_ctx_extent_z_min": 2.5,
    "wall_normal_z_max": .35, "wall_thickness_max": .10, "wall_top_hag_min": 1.5, "wall_building_m": 2.5,
    "canopy_nonlast_min": .30, "canopy_thickness_gt": .10,
}
RULES_VERSION = "treetop-evidence/2"
FLAGS = ("NEAR_BUILDING", "ROOF_HEIGHT", "OVERHANG", "FLAT_TOP", "WIRE_HINT", "POLE_HINT", "WALL_HINT",
         "CANOPY_RETURNS", "SUSPECT")
SUSPECT_FLAGS = ("ROOF_HEIGHT", "FLAT_TOP", "WIRE_HINT", "WALL_HINT")     # POLE_HINT: see correction 1
FEATURES = ("n_building_1m", "building_dist_m", "ground_z", "roof_hag_m", "above_roof_m", "n_top", "top_hag_m",
            "top_nonlast", "top_thickness", "top_normal_z", "top_linearity", "top_planarity", "ctx_n",
            "ctx_linearity", "ctx_axis_z", "ctx_extent_z")


def read_points(path, extent=None, block=4_000_000):
    """Decoded points of one uncompressed LAS file, optionally only those inside extent (xmin, ymin, xmax, ymax).

    Returns x, y, z (float64), cls, number, count (uint8) and clean (not withheld, synthetic or overlap).
    """
    points, scale, offset, modern, _ = las_records.records(path)
    parts = []
    for start in range(0, len(points), block):
        chunk = np.asarray(points[start:start+block])
        x, y, z = (chunk[a]*scale[i]+offset[i] for i, a in enumerate("xyz"))
        keep = slice(None)
        if extent is not None:
            keep = (x >= extent[0]) & (x <= extent[2]) & (y >= extent[1]) & (y <= extent[3])
        ret = chunk["returns"][keep]
        parts.append({"x": x[keep], "y": y[keep], "z": z[keep],
                      "cls": (chunk["classification"] if modern else chunk["classification"] & 31)[keep],
                      "number": ret & (15 if modern else 7), "count": (ret >> 4) if modern else ((ret >> 3) & 7),
                      "clean": las_records.clean_flags(chunk["flags"][keep], modern)})
    if not parts:
        return {k: np.empty(0) for k in ("x", "y", "z", "cls", "number", "count", "clean")}
    return {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}


def concat(*sets):
    sets = [s for s in sets if s is not None and len(s["x"])]
    return {k: np.concatenate([s[k] for s in sets]) for k in sets[0]} if sets else None


def strip(points, extent, width=HALO_M):
    """Points inside extent and within width of its edge: what a neighbouring tile needs from this one."""
    x, y = points["x"], points["y"]
    inner = (x > extent[0]+width) & (x < extent[2]-width) & (y > extent[1]+width) & (y < extent[3]-width)
    return {k: v[~inner] for k, v in points.items()}


def near_building(xy, height, building_xyz, ground_xyz):
    """The 29 September near-building measurement for each treetop.

    Returns n_building_1m, roof_hag_m, ground_z and above_roof_m (NaN where there is no class-6 point within 1 m or
    no class-2 point within 5 m), with the same percentile, median and inclusive distances as that review.
    """
    n = len(xy)
    out = {k: np.full(n, np.nan) for k in ("roof_hag_m", "ground_z", "above_roof_m")}
    out["n_building_1m"] = np.zeros(n, dtype=np.int32)
    btree = cKDTree(building_xyz[:, :2]) if len(building_xyz) else None
    gtree = cKDTree(ground_xyz[:, :2]) if len(ground_xyz) else None
    roofs = btree.query_ball_point(xy, NEAR_M, workers=-1) if btree else [[]]*n
    unders = gtree.query_ball_point(xy, GROUND_M, workers=-1) if gtree else [[]]*n
    for i, (roof, under) in enumerate(zip(roofs, unders)):
        out["n_building_1m"][i] = len(roof)
        if under:
            out["ground_z"][i] = np.median(ground_xyz[under, 2])
        if roof and under:
            out["roof_hag_m"][i] = np.percentile(building_xyz[roof, 2], ROOF_PERCENTILE)-out["ground_z"][i]
            out["above_roof_m"][i] = height[i]-out["roof_hag_m"][i]
    return out


def band(above_roof_m):
    """BANDS index of a height above the roof, as in the 29 September review; -1 where unknown."""
    a = np.asarray(above_roof_m, dtype=float)
    return np.where(np.isnan(a), -1, np.where(a <= .5, 0, np.where(a <= 2, 1, 2)))


def shape_features(xy, ground_z, points):
    """Top-set and context features for each treetop from the non-ground, non-noise, clean points."""
    n = len(xy)
    out = {k: np.full(n, np.nan) for k in ("top_hag_m", "top_nonlast", "top_thickness", "top_normal_z",
                                           "top_linearity", "top_planarity", "ctx_linearity", "ctx_axis_z",
                                           "ctx_extent_z")}
    out["n_top"] = np.zeros(n, dtype=np.int32)
    out["ctx_n"] = np.zeros(n, dtype=np.int32)
    keep = points["clean"] & ~np.isin(points["cls"], EXCLUDED_CLASSES)
    x, y, z = points["x"][keep], points["y"][keep], points["z"][keep]
    nonlast = points["number"][keep] < points["count"][keep]
    if not len(x):
        return out
    tree = cKDTree(np.c_[x, y])
    tops = tree.query_ball_point(xy, TOP_RADIUS_M, workers=-1)
    contexts = tree.query_ball_point(xy, CONTEXT_M, workers=-1)
    for i, (top, ctx) in enumerate(zip(tops, contexts)):
        g = ground_z[i]
        if top:
            top = np.asarray(top)
            zt = z[top]
            top = top[zt >= zt.max()-TOP_DEPTH_M]
            out["n_top"][i] = len(top)
            out["top_nonlast"][i] = nonlast[top].mean()
            if not math.isnan(g):
                out["top_hag_m"][i] = z[top].max()-g
            f = eigen_features(np.c_[x[top], y[top], z[top]])
            out["top_thickness"][i], out["top_normal_z"][i] = f["thickness"], f["normal_z"]
            out["top_linearity"][i], out["top_planarity"][i] = f["linearity"], f["planarity"]
        if ctx and not math.isnan(g):
            ctx = np.asarray(ctx)
            ctx = ctx[z[ctx]-g >= ABOVE_GROUND_M]
            out["ctx_n"][i] = len(ctx)
            f = eigen_features(np.c_[x[ctx], y[ctx], z[ctx]])
            out["ctx_linearity"][i], out["ctx_axis_z"][i], out["ctx_extent_z"][i] = \
                f["linearity"], f["axis_z"], f["extent_z"]
    return out


def building_distance(xy, building_xyz):
    """Horizontal distance to the nearest class-6 point, NaN beyond BUILDING_SEARCH_M."""
    if not len(building_xyz):
        return np.full(len(xy), np.nan)
    d, _ = cKDTree(building_xyz[:, :2]).query(xy, distance_upper_bound=BUILDING_SEARCH_M, workers=-1)
    return np.where(np.isfinite(d), d, np.nan)


def flags(f, rules=RULES):
    """Boolean flag columns from the feature columns. NaN never satisfies a test."""
    r = rules

    def ge(a, v):
        a = np.asarray(a, dtype=float)
        return np.isfinite(a) & (a >= v)

    def le(a, v):
        a = np.asarray(a, dtype=float)
        return np.isfinite(a) & (a <= v)

    enough = np.asarray(f["n_top"]) >= r["min_top_points"]
    out = {
        "NEAR_BUILDING": np.asarray(f["n_building_1m"]) > 0,
        "ROOF_HEIGHT": le(f["above_roof_m"], r["roof_height_above_roof_max"]),
        "OVERHANG": ge(f["above_roof_m"], r["overhang_above_roof_min"]) &
                    (np.asarray(f["above_roof_m"], dtype=float) != r["overhang_above_roof_min"]),
        "FLAT_TOP": enough & le(f["top_thickness"], r["flat_thickness_max"]) &
                    ge(f["top_normal_z"], r["flat_normal_z_min"]) & le(f["top_nonlast"], r["flat_nonlast_max"]),
        "WIRE_HINT": ge(f["ctx_linearity"], r["wire_ctx_linearity_min"]) &
                     le(f["ctx_axis_z"], r["wire_ctx_axis_z_max"]) & ge(f["top_hag_m"], r["wire_top_hag_min"]) &
                     ~le(f["building_dist_m"], r["wire_building_clear_m"]) &
                     (np.asarray(f["n_top"]) <= r["wire_top_points_max"]),
        "POLE_HINT": ge(f["ctx_linearity"], r["pole_ctx_linearity_min"]) &
                     ge(f["ctx_axis_z"], r["pole_ctx_axis_z_min"]) & ge(f["ctx_extent_z"], r["pole_ctx_extent_z_min"]),
        "WALL_HINT": enough & le(f["top_normal_z"], r["wall_normal_z_max"]) &
                     le(f["top_thickness"], r["wall_thickness_max"]) & ge(f["top_hag_m"], r["wall_top_hag_min"]) &
                     le(f["building_dist_m"], r["wall_building_m"]),
        "CANOPY_RETURNS": enough & ge(f["top_nonlast"], r["canopy_nonlast_min"]) &
                          ge(f["top_thickness"], r["canopy_thickness_gt"]) &
                          (np.asarray(f["top_thickness"], dtype=float) != r["canopy_thickness_gt"]),
    }
    out["SUSPECT"] = np.logical_or.reduce([out[k] for k in SUSPECT_FLAGS])
    return out


def evaluate(xy, height, points):
    """All feature and flag columns for treetops xy (n x 2) with CHM heights, from one decoded point set."""
    xy, height = np.asarray(xy, dtype=float).reshape(-1, 2), np.asarray(height, dtype=float)
    cls = points["cls"]
    building = np.c_[points["x"], points["y"], points["z"]][cls == 6]
    ground = np.c_[points["x"], points["y"], points["z"]][cls == 2]
    f = near_building(xy, height, building, ground)
    f["building_dist_m"] = building_distance(xy, building)
    f.update(shape_features(xy, f["ground_z"], points))
    f.update(flags(f))
    return f


def tile_name(x, y, prefix="12TVL", easting0=400000, northing0=4500000):
    """USGS 1 km tile name of a location, e.g. 428123, 4504567 -> 12TVL2804."""
    return f"{prefix}{int((x-easting0)//1000):02d}{int((y-northing0)//1000):02d}"


def summary(f):
    """Counts of every flag, the near-building height bands and the main overlaps, as plain ints."""
    n = len(f["SUSPECT"])
    bands = band(f["above_roof_m"])
    near = f["NEAR_BUILDING"]
    out = {"treetops": int(n), "flags": {k: int(np.count_nonzero(f[k])) for k in FLAGS},
           "near_building_bands": {b: int(np.count_nonzero(near & (bands == i))) for i, b in enumerate(BANDS)},
           "near_building_no_ground": int(np.count_nonzero(near & (bands == -1))),
           "suspect_with_canopy_returns": int(np.count_nonzero(f["SUSPECT"] & f["CANOPY_RETURNS"])),
           "suspect_without_canopy_returns": int(np.count_nonzero(f["SUSPECT"] & ~f["CANOPY_RETURNS"])),
           "suspect_flag_count": {str(k): int(v) for k, v in
                                  zip(*np.unique(sum(f[k].astype(int) for k in SUSPECT_FLAGS), return_counts=True))}}
    return out
