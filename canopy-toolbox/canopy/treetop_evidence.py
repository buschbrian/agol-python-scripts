"""Review evidence for detected treetops: is a peak on a roof edge, a wire, a pole or a wall? No ArcPy.

Rebuilt on October 22, 2026 from the rules and definitions stored in the October 15 run's manifest
(runs/treetop-evidence-20261015/manifest.json, rules_version treetop-evidence/2) because the original script was not in the
repository; it is checked against every value that run stored (reviews/2026-10-22/treetop-evidence).

Every value is a measurement of the points around a treetop and every flag a fixed rule over those values. They are REVIEW
EVIDENCE, never labels: they must not enter reference.gdb, training labels or a score, and a flagged treetop is not thereby a
false detection.
- Near-building, as the 29 September candidates_near_buildings.py review: class-6 points within 1 m horizontally, the local
  roof height (90th-percentile class-6 Z within 1 m minus the median class-2 Z within 5 m) and HEIGHT_M against it.
- Shape and returns, as triage.py: the top 1 m of non-ground, non-noise points within 1 m of the treetop (plane-fit
  thickness, normal, linearity, planarity, non-last-return share) and the points at least 0.3 m above ground within 3 m (one
  line or not, and its direction).
SUSPECT = ROOF_HEIGHT or FLAT_TOP or WIRE_HINT or WALL_HINT; POLE_HINT and OVERHANG are reported but not suspect.
"""
from __future__ import annotations

import math

import numpy as np

from .triage import ABOVE_GROUND_M, CONTEXT_RADIUS_M, eigen_features

RULES_VERSION = "treetop-evidence/2"
RULES = {"roof_height_above_roof_max": 0.5, "overhang_above_roof_min": 2.0, "flat_thickness_max": 0.1,
         "flat_normal_z_min": 0.85, "flat_nonlast_max": 0.15, "min_top_points": 12, "wire_ctx_linearity_min": 0.85,
         "wire_ctx_axis_z_max": 0.5, "wire_top_hag_min": 4.0, "wire_building_clear_m": 2.0, "wire_top_points_max": 60,
         "pole_ctx_linearity_min": 0.85, "pole_ctx_axis_z_min": 0.9, "pole_ctx_extent_z_min": 2.5, "wall_normal_z_max": 0.35,
         "wall_thickness_max": 0.1, "wall_top_hag_min": 1.5, "wall_building_m": 2.5, "canopy_nonlast_min": 0.3,
         "canopy_thickness_gt": 0.1}
NEAR_M = 1.0
GROUND_RADIUS_M = 5.0
TOP_RADIUS_M = 1.0
TOP_DEPTH_M = 1.0
HALO_M = 5.0
BUILDING, GROUND = 6, 2
NOISE = (7, 18)
COLUMNS = ("n_building_1m", "building_dist_m", "ground_z", "roof_hag_m", "above_roof_m", "n_top", "top_hag_m",
           "top_nonlast", "top_thickness", "top_normal_z", "top_linearity", "top_planarity", "ctx_n", "ctx_linearity",
           "ctx_axis_z", "ctx_extent_z")
FLAGS = ("NEAR_BUILDING", "ROOF_HEIGHT", "OVERHANG", "FLAT_TOP", "WIRE_HINT", "POLE_HINT", "WALL_HINT", "CANOPY_RETURNS",
         "SUSPECT")


def measure(tops, xyz, cls, number, count, options=None):
    """Measurements for treetops (N x 3: X, Y, HEIGHT_M) from the points around them (xyz, class, return number, count).

    options: dict of the choices the October 15 description leaves open, settled by matching its stored values.
    Returns a dict of arrays, one per COLUMNS entry (NaN where undefined).
    """
    from scipy.spatial import cKDTree
    o = {"top_from": "max", **(options or {})}
    tops = np.asarray(tops, dtype=float)
    n = len(tops)
    out = {c: np.full(n, np.nan) for c in COLUMNS}
    out["n_building_1m"] = np.zeros(n, np.int32)
    out["n_top"] = np.zeros(n, np.int32)
    out["ctx_n"] = np.zeros(n, np.int32)
    building = np.flatnonzero(cls == BUILDING)
    ground = np.flatnonzero(cls == GROUND)
    other = np.flatnonzero(~np.isin(cls, (GROUND, *NOISE)))
    bt = cKDTree(xyz[building, :2]) if len(building) else None
    gt = cKDTree(xyz[ground, :2]) if len(ground) else None
    ot = cKDTree(xyz[other, :2]) if len(other) else None
    allt = cKDTree(xyz[:, :2])
    for i, (x, y, height) in enumerate(tops):
        if gt is not None:
            g = gt.query_ball_point((x, y), GROUND_RADIUS_M)
            if g:
                out["ground_z"][i] = float(np.median(xyz[ground[g], 2]))
        gz = out["ground_z"][i]
        if bt is not None:
            dist, _ = bt.query((x, y), distance_upper_bound=HALO_M)          # nearest class-6 point, out to the halo
            if np.isfinite(dist):
                out["building_dist_m"][i] = float(dist)
            b = bt.query_ball_point((x, y), NEAR_M)
            out["n_building_1m"][i] = len(b)
            if b:
                bb = building[b]
                if not math.isnan(gz):
                    out["roof_hag_m"][i] = float(np.percentile(xyz[bb, 2], 90))-gz
                    out["above_roof_m"][i] = height-out["roof_hag_m"][i]
        if ot is not None:
            near = other[ot.query_ball_point((x, y), TOP_RADIUS_M)]
            if len(near):
                zmax = float(xyz[near, 2].max())
                top = near[xyz[near, 2] >= zmax-TOP_DEPTH_M]
                out["n_top"][i] = len(top)
                if not math.isnan(gz):
                    out["top_hag_m"][i] = zmax-gz
                out["top_nonlast"][i] = float((number[top] < count[top]).mean())
                f = eigen_features(xyz[top])
                out["top_thickness"][i], out["top_normal_z"][i] = f["thickness"], f["normal_z"]
                out["top_linearity"][i], out["top_planarity"][i] = f["linearity"], f["planarity"]
        if not math.isnan(gz) and ot is not None:
            ctx = other[np.asarray(ot.query_ball_point((x, y), CONTEXT_RADIUS_M), dtype=np.int64)]
            ctx = ctx[xyz[ctx, 2]-gz >= ABOVE_GROUND_M]
            out["ctx_n"][i] = len(ctx)
            f = eigen_features(xyz[ctx])
            out["ctx_linearity"][i], out["ctx_axis_z"][i], out["ctx_extent_z"][i] = f["linearity"], f["axis_z"], f["extent_z"]
    return out


def flags(m):
    """The fixed rules over the measurements (arrays from measure)."""
    r = RULES
    near = m["n_building_1m"] > 0
    with np.errstate(invalid="ignore"):
        f = {"NEAR_BUILDING": near,
             "ROOF_HEIGHT": near & (m["above_roof_m"] <= r["roof_height_above_roof_max"]),
             "OVERHANG": near & (m["above_roof_m"] > r["overhang_above_roof_min"]),
             "FLAT_TOP": (m["n_top"] >= r["min_top_points"]) & (m["top_thickness"] <= r["flat_thickness_max"]) &
                         (m["top_normal_z"] >= r["flat_normal_z_min"]) & (m["top_nonlast"] <= r["flat_nonlast_max"]),
             "WIRE_HINT": (m["ctx_linearity"] >= r["wire_ctx_linearity_min"]) & (m["ctx_axis_z"] <= r["wire_ctx_axis_z_max"]) &
                          (m["top_hag_m"] >= r["wire_top_hag_min"]) & (m["n_top"] <= r["wire_top_points_max"]) &
                          ~(m["building_dist_m"] <= r["wire_building_clear_m"]),
             "POLE_HINT": (m["ctx_linearity"] >= r["pole_ctx_linearity_min"]) & (m["ctx_axis_z"] >= r["pole_ctx_axis_z_min"]) &
                          (m["ctx_extent_z"] >= r["pole_ctx_extent_z_min"]),
             "WALL_HINT": (m["n_top"] >= r["min_top_points"]) & (m["top_normal_z"] <= r["wall_normal_z_max"]) &
                          (m["top_thickness"] <= r["wall_thickness_max"]) & (m["top_hag_m"] >= r["wall_top_hag_min"]) &
                          (m["building_dist_m"] <= r["wall_building_m"]),
             "CANOPY_RETURNS": (m["n_top"] >= r["min_top_points"]) & (m["top_nonlast"] >= r["canopy_nonlast_min"]) &
                               (m["top_thickness"] > r["canopy_thickness_gt"])}
    f["SUSPECT"] = f["ROOF_HEIGHT"] | f["FLAT_TOP"] | f["WIRE_HINT"] | f["WALL_HINT"]
    return f
