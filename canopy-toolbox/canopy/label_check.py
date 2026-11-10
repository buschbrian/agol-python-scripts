"""Does a training label fit the points inside its own unit patch? No ArcPy.

Labelling protocol (decided September 30, 2026): a unit's label says what the returns inside its 1 m patch and height
slab are, because the training export applies it to exactly those points. A label that names a nearby object, or what
the imagery shows, marks the wrong points. This module flags labels that the patch's own points cannot support, so a
person can re-look at them. A flag is not a correction and never changes a label; the thresholds are plain physical
minimums (a vehicle is taller than 0.8 m, a roof is well above the ground), not fitted to any data.

Heights are measured against the ground height stored with the unit in the review packet. That reference comes from the
baseline ground surface; it is used here only to judge plausibility, never as a label.
"""
import math

import numpy as np

MIN_POINTS = 12

# label: (statistic, comparison, limit_m, what it means). Flag when the statistic breaks the limit.
EXPECTATIONS = {
    "VEHICLE": ("max", ">=", 0.8, "a vehicle is taller than 0.8 m"),
    "POLE": ("max", ">=", 1.5, "a pole is taller than 1.5 m"),
    "WALL": ("max", ">=", 1.0, "a wall face is taller than 1 m"),
    "WIRE": ("mean", ">=", 2.5, "an overhead wire is higher than 2.5 m"),
    "BUILDING_ROOF": ("mean", ">=", 2.0, "a roof is higher than 2 m"),
    "OTHER_STRUCTURE": ("max", ">=", 0.8, "a structure is taller than 0.8 m"),
    "TREE": ("max", ">=", 1.5, "a tree is taller than 1.5 m"),
    "SHRUB_LOW_VEG": ("mean", "<=", 3.0, "shrub, hedge and lawn are lower than 3 m"),
    "GROUND": ("max", "<=", 1.0, "ground has no points more than 1 m above it"),
}


def patch_stats(unit, x, y, z, ground_z):
    """Height above ground of the points inside the unit's patch (radius and height slab), nothing else."""
    x, y, z = (np.asarray(a, dtype=float) for a in (x, y, z))
    inside = (np.hypot(x-unit["X"], y-unit["Y"]) <= unit.get("PATCH_R_M", 1.0)) & \
             (z >= unit["Z_LOW"]) & (z <= unit["Z_HIGH"])
    hag = z[inside]-ground_z
    if not len(hag):
        return {"n": 0, "min": math.nan, "mean": math.nan, "max": math.nan}
    return {"n": int(len(hag)), "min": float(hag.min()), "mean": float(hag.mean()), "max": float(hag.max())}


def check_label(label, stats):
    """Reasons the patch's points cannot support this label; an empty list means nothing is implausible."""
    reasons = []
    if not label or label in ("MIXED", "UNSURE"):
        return reasons
    if stats["n"] < MIN_POINTS:
        reasons.append(f"only {stats['n']} points in the patch, too few to support any label")
    rule = EXPECTATIONS.get(label)
    if rule is None or stats["n"] == 0:
        return reasons
    statistic, comparison, limit, meaning = rule
    value = stats[statistic]
    broken = value < limit if comparison == ">=" else value > limit
    if broken:
        reasons.append(f"the patch's {statistic} height is {value:.2f} m above ground, but {meaning}")
    return reasons
