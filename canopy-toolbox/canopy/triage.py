"""Independent-evidence triage of training-review units. No ArcPy.

Option 2 of the labelling plan: a unit is proposed as easy only when evidence that does not come from our models
agrees. The evidence is the raw points' geometry (never a classification byte), building footprints from the County
Surveyor and OSM, and NAIP greenness. Baseline classes, the Esri tree and building models and the shape-gate rules are
never inputs here, because the project rule is that model output, baseline classes and rule codes are never truth.

A proposal is a suggestion to be confirmed or audited by a person, not a label. A unit is AUTO_CANDIDATE only when
exactly one class fits every one of its cues and that class is in AUTO_CLASSES; anything else (no class fits, several
fit, too few points, a needed cue missing, or a class that cannot be told apart reliably) is REVIEW.

How the rules were made. The thresholds come from lidar geometry and were fixed before any human label was compared.
They were then corrected twice, and both corrections are definitions, not thresholds fitted to labels:
  1. (testing on synthetic clouds) a review patch is a tall narrow cylinder, so linear shapes are judged on the
     surrounding above-ground points, and flatness uses the plane-fit thickness, because the eigenvalue planarity ratio
     is unstable on a small round patch;
  2. (after the first run showed them against the first 15 human labels) vegetation is the share of NON-LAST returns,
     not of multi-return pulses, because a roof or the ground under canopy is the last return of a multi-return pulse;
     and low versus tall uses the top of the 3 m neighbourhood, not the patch slab, which can sit low on a trunk.
Because the second correction used those 15 labels, they cannot be the accuracy test of these rules; that needs a fresh,
randomly drawn human audit sample.

NAIP is leaf-off (mid-November), so high greenness supports vegetation but low greenness says nothing: trees are never
proposed without it, and no class is ever ruled out by low greenness alone. For the same reason a bare trunk cannot be
told from a pole, so POLE and WIRE are only ever hints for a person.
"""
import math

import numpy as np

MIN_POINTS = 12
CONTEXT_RADIUS_M = 3.0
ABOVE_GROUND_M = 0.3            # context points lower than this are ground and ignored for linear shapes
TOP_PERCENTILE = 98             # 'top of the neighbourhood', robust to a stray noise point

ROOF = dict(hag=2.0, thickness_max=.10, normal_z=.85, nonlast=.15, ndvi_max=.20)
TREE = dict(ndvi=.25, nonlast=.30, thickness=.25, hag=2.5)
SHRUB = dict(ndvi=.25, nonlast=.20, top_hag_max=2.0)
GROUND = dict(hag_max=.35, thickness_max=.10, normal_z=.95, nonlast=.10)
WALL = dict(normal_z_max=.35, thickness_max=.10, hag=1.5, edge_m=2.5)
WIRE = dict(ctx_linearity=.85, ctx_axis_z_max=.50, hag=4.0, footprint_clear_m=2.0, ndvi_max=.15, points_max=60)
POLE = dict(ctx_linearity=.85, ctx_axis_z=.90, extent_z=2.5, ndvi_max=.15)

LABELS = ("TREE", "BUILDING_ROOF", "WALL", "WIRE", "POLE", "SHRUB_LOW_VEG", "GROUND")
AUTO_CLASSES = ("BUILDING_ROOF", "TREE", "SHRUB_LOW_VEG", "GROUND", "WALL")     # POLE and WIRE are hints only


def eigen_features(xyz):
    """Shape of a small point set from its covariance: linearity, planarity, scattering, orientation, thickness."""
    xyz = np.asarray(xyz, dtype=float)
    empty = {"linearity": math.nan, "planarity": math.nan, "scattering": math.nan, "normal_z": math.nan,
             "axis_z": math.nan, "extent_z": math.nan, "thickness": math.nan}
    if len(xyz) < 4:
        return empty
    centred = xyz - xyz.mean(axis=0)
    values, vectors = np.linalg.eigh(centred.T @ centred / len(xyz))     # ascending
    l3, l2, l1 = (max(float(v), 0.0) for v in values)
    if l1 <= 1e-12:
        return empty
    return {"linearity": (l1-l2)/l1, "planarity": (l2-l3)/l1, "scattering": l3/l1,
            "normal_z": float(abs(vectors[2, 0])), "axis_z": float(abs(vectors[2, 2])),
            "extent_z": float(np.ptp(xyz[:, 2])), "thickness": math.sqrt(l3)}


def unit_features(unit, x, y, z, num_returns, return_number, ground_z, ndvi=None, footprint=None):
    """Independent features of one unit from the points around it (all heights, within the context radius).

    unit: X, Y, Z_LOW, Z_HIGH, PATCH_R_M. x, y, z, num_returns, return_number: the points within CONTEXT_RADIUS_M of
    the unit. ground_z: this code's own local ground height (not a baseline class). ndvi: mean NAIP NDVI near the unit
    or None. footprint: {"inside": bool, "edge_m": distance to the nearest footprint edge} or None.
    """
    x, y, z, num_returns, return_number = (np.asarray(a) for a in (x, y, z, num_returns, return_number))
    d = np.hypot(x-unit["X"], y-unit["Y"])
    patch = (d <= unit.get("PATCH_R_M", 1.0)) & (z >= unit["Z_LOW"]) & (z <= unit["Z_HIGH"])
    context = d <= CONTEXT_RADIUS_M
    f = {"n_patch": int(patch.sum()), "n_context": int(context.sum())}
    if f["n_patch"]:
        f["hag"] = float(z[patch].mean()-ground_z)
        f["nonlast"] = float((return_number[patch] < num_returns[patch]).mean())
    else:
        f["hag"] = f["nonlast"] = math.nan
    f.update(eigen_features(np.c_[x[patch], y[patch], z[patch]]))
    f["top_hag"] = float(np.percentile(z[context], TOP_PERCENTILE)-ground_z) if context.any() else math.nan
    above = context & (z-ground_z >= ABOVE_GROUND_M)
    ctx = eigen_features(np.c_[x[above], y[above], z[above]])
    f["ctx_linearity"], f["ctx_axis_z"], f["ctx_n"] = ctx["linearity"], ctx["axis_z"], int(above.sum())
    f["ndvi"] = None if ndvi is None or (isinstance(ndvi, float) and math.isnan(ndvi)) else float(ndvi)
    f["in_footprint"] = None if footprint is None else bool(footprint["inside"])
    f["edge_m"] = None if footprint is None else float(footprint["edge_m"])
    return f


def _ok(value, test):
    return value is not None and not (isinstance(value, float) and math.isnan(value)) and test(value)


def fits(f):
    """Every class whose cues are all met, each with the cues that supported it."""
    found = {}
    inside, edge, ndvi = f["in_footprint"], f["edge_m"], f["ndvi"]
    out = inside is False
    if inside and _ok(f["hag"], lambda v: v >= ROOF["hag"]) and _ok(f["thickness"], lambda v: v <= ROOF["thickness_max"]) \
            and _ok(f["normal_z"], lambda v: v >= ROOF["normal_z"]) and _ok(f["nonlast"], lambda v: v <= ROOF["nonlast"]) \
            and _ok(ndvi, lambda v: v < ROOF["ndvi_max"]):
        found["BUILDING_ROOF"] = ["inside a surveyed footprint", "a thin flat plane", "flat to gently sloped",
                                  "no vegetation returns", "not green"]
    if out and _ok(ndvi, lambda v: v >= TREE["ndvi"]) and _ok(f["nonlast"], lambda v: v >= TREE["nonlast"]) \
            and _ok(f["thickness"], lambda v: v >= TREE["thickness"]) and _ok(f["hag"], lambda v: v >= TREE["hag"]):
        found["TREE"] = ["green (NAIP)", "canopy returns", "points scattered in 3D", "tall", "outside footprints"]
    if out and _ok(ndvi, lambda v: v >= SHRUB["ndvi"]) and _ok(f["nonlast"], lambda v: v >= SHRUB["nonlast"]) \
            and _ok(f["top_hag"], lambda v: v <= SHRUB["top_hag_max"]):
        found["SHRUB_LOW_VEG"] = ["green (NAIP)", "canopy returns", "nothing tall nearby", "outside footprints"]
    if out and _ok(f["hag"], lambda v: v <= GROUND["hag_max"]) \
            and _ok(f["thickness"], lambda v: v <= GROUND["thickness_max"]) \
            and _ok(f["normal_z"], lambda v: v >= GROUND["normal_z"]) and _ok(f["nonlast"], lambda v: v <= GROUND["nonlast"]):
        found["GROUND"] = ["at ground height", "a thin flat plane", "no vegetation returns", "outside footprints"]
    if _ok(edge, lambda v: v <= WALL["edge_m"]) and _ok(f["normal_z"], lambda v: v <= WALL["normal_z_max"]) \
            and _ok(f["thickness"], lambda v: v <= WALL["thickness_max"]) and _ok(f["hag"], lambda v: v >= WALL["hag"]):
        found["WALL"] = ["a thin vertical plane", "at a footprint edge"]
    if out and _ok(edge, lambda v: v >= WIRE["footprint_clear_m"]) \
            and _ok(f["ctx_linearity"], lambda v: v >= WIRE["ctx_linearity"]) \
            and _ok(f["ctx_axis_z"], lambda v: v <= WIRE["ctx_axis_z_max"]) and _ok(f["hag"], lambda v: v >= WIRE["hag"]) \
            and _ok(ndvi, lambda v: v < WIRE["ndvi_max"]) and f["n_patch"] <= WIRE["points_max"]:
        found["WIRE"] = ["the surroundings are one horizontal line", "high", "clear of footprints", "not green"]
    if out and _ok(f["ctx_linearity"], lambda v: v >= POLE["ctx_linearity"]) \
            and _ok(f["ctx_axis_z"], lambda v: v >= POLE["ctx_axis_z"]) \
            and _ok(f["extent_z"], lambda v: v >= POLE["extent_z"]) and _ok(ndvi, lambda v: v < POLE["ndvi_max"]):
        found["POLE"] = ["the surroundings are one vertical line", "tall", "outside footprints", "not green"]
    return found


def propose(f):
    """{"label", "tier", "cues", "hint"}.

    AUTO_CANDIDATE only when exactly one class fits, that class is in AUTO_CLASSES and the unit has enough points.
    A fitting class that cannot be trusted (POLE, WIRE) is returned as a hint with tier REVIEW.
    """
    if f["n_patch"] < MIN_POINTS:
        return {"label": None, "tier": "REVIEW", "cues": [f"only {f['n_patch']} points in the patch"], "hint": None}
    found = fits(f)
    if len(found) == 1:
        label, cues = next(iter(found.items()))
        if label in AUTO_CLASSES:
            return {"label": label, "tier": "AUTO_CANDIDATE", "cues": cues, "hint": None}
        return {"label": None, "tier": "REVIEW", "hint": label,
                "cues": cues+["a bare trunk cannot be told from a pole or wire in leaf-off imagery"]}
    if len(found) > 1:
        return {"label": None, "tier": "REVIEW", "cues": ["several classes fit: " + ", ".join(sorted(found))],
                "hint": None}
    return {"label": None, "tier": "REVIEW", "cues": ["no class has all its cues"], "hint": None}
