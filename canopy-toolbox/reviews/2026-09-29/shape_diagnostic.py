"""Measure how much of the height-classified "vegetation" has a non-vegetation shape.

Reads one prepared LAS copy with PDAL (bundled with ArcGIS Pro), drops ground and noise,
and computes eigenvalue shape features from each point's 16 nearest non-ground neighbours.
Classes 3/4/5 are then split by dominant shape:

- planar, near-horizontal: roof-like (roof edges, flat structures)
- planar, near-vertical: wall-like (facades, fences)
- linear: wire-, pole- or edge-like
- scattered: vegetation-like

Each group is also counted within 1 m (3D) of a class-6 building point: roof-edge leakage.
Shape is evidence, not truth: a clipped hedge is planar and a roof corner can scatter.
The thresholds below are screening choices, not validated class boundaries.

Optionally writes a review copy whose class codes mark each group, for display in Pro.
The prepared LAS is only read; the review copy goes to a new path.

Usage (Pro Python):
    python shape_diagnostic.py PREPARED.las REPORT.json [--extent XMIN YMIN XMAX YMAX]
                               [--review-las OUT.las]
"""
import argparse
import json
from pathlib import Path
import time

import numpy as np
import pdal
from scipy.spatial import cKDTree

KNN = 16
DOMINANT = 0.6   # share of the three dimensionality features that makes a shape dominant
VERTICAL = 0.7   # PDAL Verticality (1 - |normal z|) above this is a wall-like plane
NEAR_BUILDING = 1.0  # metres, 3D, to the nearest class-6 point
# User-definable class codes (64-255) used only in the review copy.
REVIEW = {"roof_like": 64, "wall_like": 65, "linear": 66, "scattered": 67, "mixed": 68}
VEGETATION = {3: "low", 4: "medium", 5: "high"}


def features(path, extent):
    stages = [{"type": "readers.las", "filename": str(path)}]
    if extent:
        xmin, ymin, xmax, ymax = extent
        stages.append({"type": "filters.crop", "bounds": f"([{xmin},{xmax}],[{ymin},{ymax}])"})
    stages += [
        {"type": "filters.expression",
         "expression": "Classification != 2 && Classification != 7 && Classification != 18"},
        {"type": "filters.covariancefeatures", "knn": KNN, "threads": 8,
         "feature_set": "Dimensionality"},
    ]
    pipeline = pdal.Pipeline(json.dumps(stages))
    pipeline.execute()
    return pipeline.arrays[0], pipeline


def groups(points):
    lin, pla, sca = points["Linearity"], points["Planarity"], points["Scattering"]
    vert = points["Verticality"]
    label = np.full(points.size, "mixed", dtype=object)
    label[sca >= DOMINANT] = "scattered"
    label[lin >= DOMINANT] = "linear"
    label[(pla >= DOMINANT) & (vert < VERTICAL)] = "roof_like"
    label[(pla >= DOMINANT) & (vert >= VERTICAL)] = "wall_like"
    return label


def near_building(points):
    """True where a class-6 point lies within NEAR_BUILDING metres in 3D."""
    building = points["Classification"] == 6
    near = np.zeros(points.size, dtype=bool)
    if building.any():
        xyz = np.column_stack([points["X"], points["Y"], points["Z"]])
        distance, _ = cKDTree(xyz[building]).query(xyz, distance_upper_bound=NEAR_BUILDING, workers=-1)
        near = np.isfinite(distance) & ~building
    return near


def summarize(points, label, near):
    single = points["NumberOfReturns"] == 1
    report = {}
    for code, name in VEGETATION.items():
        mask = points["Classification"] == code
        total = int(mask.sum())
        row = {"points": total, "single_return_pct": pct(single & mask, total),
               "near_building_pct": pct(mask & near, total)}
        for group in REVIEW:
            member = mask & (label == group)
            row[f"{group}_pct"] = pct(member, total)
            row[f"{group}_single_return_pct"] = pct(member & single, total)
            row[f"{group}_near_building_pct"] = pct(member & near, total)
        report[f"class_{code}_{name}"] = row
    return report


def pct(mask, total):
    return round(100 * int(mask.sum()) / total, 2) if total else None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("las"); parser.add_argument("report")
    parser.add_argument("--extent", type=float, nargs=4)
    parser.add_argument("--review-las")
    args = parser.parse_args()
    start = time.time()
    points, _ = features(args.las, args.extent)
    label = groups(points)
    near = near_building(points)
    result = {
        "source": Path(args.las).name, "extent": args.extent,
        "parameters": {"knn": KNN, "dominant_share": DOMINANT, "wall_verticality": VERTICAL,
                       "near_building_m": NEAR_BUILDING, "excluded_classes": [2, 7, 18]},
        "non_ground_points": int(points.size),
        "by_class": summarize(points, label, near),
        "note": "Shape groups are screening evidence, not validated classes.",
    }
    if args.review_las:
        review = Path(args.review_las)
        if review.exists():
            raise FileExistsError(review)
        out = points.copy()
        veg = np.isin(out["Classification"], list(VEGETATION))
        for group, code in REVIEW.items():
            out["Classification"][veg & (label == group)] = code
        writer = pdal.Pipeline(json.dumps([{
            "type": "writers.las", "filename": str(review), "minor_version": 4,
            "dataformat_id": 6, "forward": "all", "extra_dims": "all"}]), arrays=[out])
        writer.execute()
        result["review_las"] = {"path": review.name, "codes": REVIEW,
                                "note": "Only class 3/4/5 points are recoded; others keep their class."}
    result["seconds"] = round(time.time() - start, 1)
    Path(args.report).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
