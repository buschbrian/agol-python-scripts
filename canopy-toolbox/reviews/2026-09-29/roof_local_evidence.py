r"""Describe the points that refine-roofs --method local reclassified, to look for over-removal.

For one tile, reads the per-point change log (refined\changes\<tile>.npz) and the UNCHANGED
prepared LAS (read-only). Reports, for the tile's own LAS file:
- counts and distributions: height above the local roof face (residual), distance to the
  nearest roof point, height above ground (median class-2 Z within 5 m), return type;
- neighbourhood evidence for a seeded random sample: eigenvalue shape of all non-noise points
  within 1 m (3D), vegetation-class first returns more than 2 m above the point within 1 m
  horizontally (canopy overhead), and the roof's own height above ground.
None of this is a label. It shows whether the changed points look like roof edges or like canopy.

Usage (Pro Python, from canopy-toolbox):
    python reviews/2026-09-29/roof_local_evidence.py TILE REPORT.json [--sample 20] [--shape-sample 2000]
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np
from scipy.spatial import cKDTree

from canopy import roofs

ROOT = Path(r"H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29")
RETURN_NAMES = roofs.RETURN_TYPES


def pct(values, q=(5, 25, 50, 75, 95)):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return {f"p{p}": round(float(v), 3) for p, v in zip(q, np.percentile(values, q))} if values.size else None


def shape(points):
    """Eigenvalue features of a 3D neighbourhood: linearity, planarity, scattering, verticality."""
    if len(points) < 4:
        return None
    centred = points - points.mean(0)
    values, vectors = np.linalg.eigh(np.cov(centred.T))
    l3, l2, l1 = np.maximum(values, 1e-12)
    normal = vectors[:, 0]
    return {"linearity": (l1 - l2) / l1, "planarity": (l2 - l3) / l1, "scattering": l3 / l1,
            "verticality": 1 - abs(normal[2])}


def label(features):
    if features is None:
        return "sparse"
    if features["planarity"] >= .5 and features["verticality"] < .3:
        return "roof_like"
    if features["planarity"] >= .5 and features["verticality"] > .7:
        return "wall_like"
    if features["linearity"] >= .6:
        return "linear"
    if features["scattering"] >= .25:
        return "scattered"
    return "mixed"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tile"); parser.add_argument("report")
    parser.add_argument("--sample", type=int, default=20)
    parser.add_argument("--shape-sample", type=int, default=2000)
    parser.add_argument("--refined", default="roof-local\\{tile}\\refined")
    args = parser.parse_args()
    tile = args.tile
    refined = ROOT / args.refined.format(tile=tile)
    changes = np.load(refined / "changes" / f"{tile}.npz")
    index = changes["point_index"]
    points, scale, offset, modern = roofs._records(ROOT / tile / "prepared" / "points" / f"{tile}.las", "r")
    codes = points["classification"] if modern else points["classification"] & 31
    xyz = np.column_stack([points[a] * scale[i] + offset[i] for i, a in enumerate("xyz")])
    returns = np.asarray(points["returns"])
    first = (returns & (15 if modern else 7)) == 1
    codes = np.asarray(codes)
    changed = xyz[index]
    previous = codes[index]
    kind = roofs._return_type(returns[index], modern)

    ground = xyz[codes == 2]
    gtree = cKDTree(ground[:, :2])
    roof = xyz[(codes == 6) & first]
    rtree = cKDTree(roof[:, :2])

    def above_ground(p):
        near = gtree.query_ball_point(p[:, :2], 5.0, workers=-1)
        return np.array([p[i, 2] - np.median(ground[n, 2]) if n else np.nan for i, n in enumerate(near)])

    hag = above_ground(changed)
    report = {"tile": tile, "changed_points_in_tile_file": int(len(index)),
              "by_previous_class": {str(c): int((previous == c).sum()) for c in (3, 4, 5)},
              "by_return_type": {n: int((kind == i).sum()) for i, n in enumerate(RETURN_NAMES)},
              "residual_above_roof_face_m": pct(changes["residual_m"]),
              "nearest_roof_point_m": pct(changes["nearest_roof_m"]),
              "votes": pct(changes["votes"]),
              "height_above_ground_m_by_class": {str(c): pct(hag[previous == c]) for c in (3, 4, 5)}}

    # Neighbourhood evidence. Non-noise points only (exclude 7 and 18), from the unchanged LAS.
    rng = np.random.default_rng(20260929)
    keep = ~np.isin(codes, [7, 18])
    allpts = xyz[keep]
    atree = cKDTree(allpts)
    veg_first = xyz[np.isin(codes, [3, 4, 5]) & first]
    vtree = cKDTree(veg_first[:, :2])

    def describe(i):
        p = changed[i]
        f = shape(allpts[atree.query_ball_point(p, 1.0)])
        overhead = vtree.query_ball_point(p[:2], 1.0)
        overhead = int((veg_first[overhead, 2] > p[2] + 2).sum()) if overhead else 0
        roof_near = rtree.query_ball_point(p[:2], 1.0)
        roof_z = np.percentile(roof[roof_near, 2], 90) if roof_near else np.nan
        count = int(returns[index[i]] >> 4) if modern else int((returns[index[i]] >> 3) & 7)
        number = int(returns[index[i]] & (15 if modern else 7))
        return {"x": round(float(p[0]), 2), "y": round(float(p[1]), 2), "z": round(float(p[2]), 2),
                "previous_class": int(previous[i]), "return": f"{number} of {count}",
                "height_above_ground_m": None if np.isnan(hag[i]) else round(float(hag[i]), 2),
                "above_local_roof_face_m": round(float(changes["residual_m"][i]), 2),
                "roof_p90_above_ground_m": None if np.isnan(roof_z) or np.isnan(hag[i]) else
                    round(float(roof_z - (p[2] - hag[i])), 2),
                "nearest_roof_point_m": round(float(changes["nearest_roof_m"][i]), 2),
                "votes": int(changes["votes"][i]), "faces": int(changes["faces"][i]),
                "shape": label(f), "planarity": None if f is None else round(float(f["planarity"]), 2),
                "scattering": None if f is None else round(float(f["scattering"]), 3),
                "veg_first_returns_2m_above_within_1m": overhead}

    sample = rng.choice(len(index), min(args.sample, len(index)), replace=False)
    report["random_sample"] = [describe(int(i)) for i in sorted(sample)]
    bulk = rng.choice(len(index), min(args.shape_sample, len(index)), replace=False)
    rows = [describe(int(i)) for i in bulk]
    labels = [r["shape"] for r in rows]
    report["shape_sample"] = {
        "n": len(rows),
        "shape": {k: labels.count(k) for k in ("roof_like", "wall_like", "linear", "scattered", "mixed", "sparse")},
        "multi_return_pulse": sum(not r["return"].endswith("of 1") and not r["return"].endswith("of 0") for r in rows),
        "with_canopy_overhead": sum(r["veg_first_returns_2m_above_within_1m"] > 0 for r in rows),
        # The riskier subset: the point is itself a first/single return, beside canopy that is
        # more than 2 m higher. Later returns under canopy are usually the roof seen through it.
        "first_or_single_with_canopy_overhead": sum(r["veg_first_returns_2m_above_within_1m"] > 0 and
                                                    r["return"].startswith("1 of") for r in rows),
        "first_or_single": sum(r["return"].startswith("1 of") for r in rows),
        "roof_p90_above_ground_m": pct([r["roof_p90_above_ground_m"] for r in rows if r["roof_p90_above_ground_m"] is not None]),
        "note": "shape thresholds (planarity>=.5, verticality<.3 or >.7, linearity>=.6, scattering>=.25) are "
                "screening choices, not validated class boundaries"}
    del points
    Path(args.report).write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "random_sample"}, indent=2))


if __name__ == "__main__":
    main()
