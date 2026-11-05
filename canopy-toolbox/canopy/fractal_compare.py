"""Prespecified diagnostic comparison of FRACTAL votes with training patches.

No ArcPy, label writes or evaluation scoring. TREE and SHRUB_LOW_VEG share
VEGETATION because the seven-class model cannot distinguish them. Other human
structure labels have no unambiguous model counterpart and are not scored.
"""
import math

import numpy as np

PROTOCOL = "fractal-training-comparison/1"
MODEL_FAMILIES = {1: "OTHER", 2: "GROUND", 5: "VEGETATION", 6: "BUILDING",
                  9: "WATER", 17: "STRUCTURE", 64: "STRUCTURE"}
LABEL_FAMILIES = {"TREE": "VEGETATION", "SHRUB_LOW_VEG": "VEGETATION",
                  "BUILDING_ROOF": "BUILDING", "GROUND": "GROUND", "WATER": "WATER"}
MIN_PATCH_POINTS = 12


def validate_consensus(codes, agreement, tied, strict, repeats):
    """Refuse corrupt vote fields; agreement is consistency, not confidence."""
    codes, agreement, tied, strict = map(np.asarray, (codes, agreement, tied, strict))
    if repeats not in (3, 4, 5) or codes.ndim != 1 or any(a.shape != codes.shape for a in (agreement, tied, strict)):
        raise ValueError("Expected aligned vote fields and three to five repeats")
    if not np.isin(codes, [0, *MODEL_FAMILIES]).all():
        raise ValueError("Unknown FRACTAL class code")
    if not np.isfinite(agreement).all() or np.any(agreement < 1 / repeats - 1e-6) or np.any(agreement > 1):
        raise ValueError("Invalid repeat agreement")
    if not np.allclose(agreement * repeats, np.rint(agreement * repeats), atol=1e-5, rtol=0):
        raise ValueError("Repeat agreement does not represent a vote count")
    if not np.isin(tied, [0, 1]).all() or not np.isin(strict, [0, 1]).all():
        raise ValueError("Tie and strict-majority flags must be binary")
    if not np.array_equal(codes == 0, tied.astype(bool)):
        raise ValueError("Code 0 must correspond exactly to tied votes")
    expected = (agreement > 0.5) & ~tied.astype(bool)
    if not np.array_equal(expected, strict.astype(bool)) or np.any(tied.astype(bool) & (agreement > 0.5)):
        raise ValueError("Inconsistent strict-majority flag")


def patch_comparison(unit, x, y, z, codes, agreement, tied, strict, bounds):
    """Compare the cylinder/slab, using all its clean points as the denominator.

    Input arrays contain only eligible (not withheld/overlap/synthetic) points.
    Abstaining point votes cannot improve the patch score by being discarded.
    Bounds are conservative XY coverage limits for the inference input.
    """
    centre = (float(unit["X"]), float(unit["Y"]))
    radius = float(unit.get("PATCH_R_M", 1.0))
    low, high = float(unit["Z_LOW"]), float(unit["Z_HIGH"])
    if not all(math.isfinite(v) for v in (*centre, radius, low, high, *bounds)) or radius <= 0 or low > high:
        raise ValueError("Invalid patch geometry")
    if len(bounds) != 4 or bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
        raise ValueError("Invalid coverage bounds")
    result = {"UNIT_ID": unit["UNIT_ID"], "LABEL": unit.get("LABEL", ""),
              "HUMAN_FAMILY": LABEL_FAMILIES.get(unit.get("LABEL")), "MODEL_FAMILY": None,
              "STATUS": "", "AGREE": None, "PATCH_POINTS": 0, "MODEL_SHARE": None,
              "MEAN_REPEAT_AGREEMENT": None, "UNANIMOUS_POINT_SHARE": None,
              "TIED_POINTS": 0, "WEAK_POINTS": 0, "FAMILY_COUNTS": {}}
    cx, cy = centre
    if cx - radius < bounds[0] or cy - radius < bounds[1] or cx + radius > bounds[2] or cy + radius > bounds[3]:
        result["STATUS"] = "PARTIAL_COVERAGE"
        return result
    hit = (np.hypot(np.asarray(x) - cx, np.asarray(y) - cy) <= radius) & (np.asarray(z) >= low) & (np.asarray(z) <= high)
    n = int(hit.sum())
    result["PATCH_POINTS"] = n
    if n < MIN_PATCH_POINTS:
        result["STATUS"] = "INSUFFICIENT_POINTS"
        return result
    selected = np.asarray(codes)[hit]
    trusted = np.asarray(strict)[hit].astype(bool) & ~np.asarray(tied)[hit].astype(bool)
    counts = {family: int((np.isin(selected, [code for code, name in MODEL_FAMILIES.items() if name == family]) & trusted).sum())
              for family in sorted(set(MODEL_FAMILIES.values()))}
    counts["ABSTAIN"] = int((~trusted).sum())
    family = max(counts, key=counts.get)
    share = counts[family] / n
    chosen = family if family != "ABSTAIN" and share > 0.5 else None
    result.update(MODEL_FAMILY=chosen, MODEL_SHARE=share, FAMILY_COUNTS=counts,
                  MEAN_REPEAT_AGREEMENT=float(np.asarray(agreement)[hit].mean()),
                  UNANIMOUS_POINT_SHARE=float(np.isclose(np.asarray(agreement)[hit], 1, atol=1e-6).mean()),
                  TIED_POINTS=int(np.asarray(tied)[hit].sum()), WEAK_POINTS=int((~trusted).sum()))
    if result["HUMAN_FAMILY"] is None:
        result["STATUS"] = "LABEL_NOT_COMPARABLE"
    elif chosen is None:
        result.update(STATUS="ABSTAIN", AGREE=False)
    else:
        result.update(STATUS="COMPARED", AGREE=chosen == result["HUMAN_FAMILY"])
    return result


def summarize(rows):
    """Unit-weighted diagnostic agreement, with abstentions in the denominator."""
    labels = sorted({r["LABEL"] for r in rows if r["LABEL"]})
    by_label = {}
    for label in labels:
        selected = [r for r in rows if r["LABEL"] == label]
        eligible = [r for r in selected if r["AGREE"] is not None]
        by_label[label] = {"units": len(selected), "comparable_covered_units": len(eligible),
                           "agree": sum(r["AGREE"] for r in eligible),
                           "abstain": sum(r["STATUS"] == "ABSTAIN" for r in eligible),
                           "agreement": sum(r["AGREE"] for r in eligible) / len(eligible) if eligible else None,
                           "mean_repeat_agreement": float(np.mean([r["MEAN_REPEAT_AGREEMENT"] for r in eligible])) if eligible else None}
    return {"units": len(rows), "by_label": by_label,
            "status_counts": {status: sum(r["STATUS"] == status for r in rows) for status in sorted({r["STATUS"] for r in rows})},
            "interpretation": "Training-patch diagnostic agreement; not independent evaluation or a citywide accuracy estimate."}
