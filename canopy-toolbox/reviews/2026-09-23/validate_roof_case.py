"""Read-only reproduction of the Millcreek roof-window comparison."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

import laspy
import numpy as np
import rasterio
from scipy.ndimage import label


ROOT = Path(__file__).resolve().parents[2] / "scratch" / "models"
LAS = {
    "standard": ROOT.parent / "planning_20260922/millcreek_prepared/points/12TVL2804.las",
    "tree_only": ROOT / "millcreek_tree_trial/12TVL2804.las",
    "building_then_tree": ROOT / "millcreek_building_tree_trial_v2/12TVL2804.las",
}
RUNS = {
    "tree_only": ROOT / "millcreek_tree_run_background/run.json",
    "building_then_tree": ROOT / "millcreek_building_tree_run/run.json",
}
OUT = ROOT / "roof_case_validation_20260923.json"
BOX = (428178, 428184, 4504334, 4504338)


def digest(path):
    h = sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def transitions(a, b):
    return {f"{x}->{y}": n for (x, y), n in sorted(Counter(zip(map(int, a), map(int, b))).items())}


before = {k: digest(v) for k, v in LAS.items()}
clouds = {k: laspy.read(v) for k, v in LAS.items()}
baseline = clouds["standard"]
integrity = {}
for k, las in clouds.items():
    integrity[k] = {
        "point_count": len(las.points),
        "xyz_identical_to_standard_in_order": all(
            np.array_equal(np.asarray(getattr(baseline, coord)), np.asarray(getattr(las, coord)))
            for coord in ("X", "Y", "Z")
        ),
        "returns_identical_to_standard_in_order": np.array_equal(
            np.asarray(baseline.return_number), np.asarray(las.return_number)
        ) and np.array_equal(np.asarray(baseline.number_of_returns), np.asarray(las.number_of_returns)),
        "flags_identical_to_standard_in_order": all(
            np.array_equal(np.asarray(getattr(baseline, flag)), np.asarray(getattr(las, flag)))
            for flag in ("withheld", "synthetic", "overlap", "key_point")
        ),
    }
x, y = np.asarray(baseline.x), np.asarray(baseline.y)
xmin, xmax, ymin, ymax = BOX
window = (x >= xmin) & (x <= xmax) & (y >= ymin) & (y <= ymax)
classes = {k: np.asarray(v.classification)[window] for k, v in clouds.items()}

run = {k: json.loads(v.read_text()) for k, v in RUNS.items()}
grid = {}
for k, manifest in run.items():
    with rasterio.open(manifest["outputs"]["chm"]) as src:
        grid[k] = src.read(1, masked=True).filled(-9999)
assert grid["tree_only"].shape == grid["building_then_tree"].shape
with rasterio.open(ROOT / "osm_roof_mask.tif") as src:
    roof = ~src.read(1, masked=True).mask
assert roof.shape == grid["tree_only"].shape
added = (grid["tree_only"] < 2) & (grid["building_then_tree"] >= 2) & roof
components, count = label(added, np.ones((3, 3), dtype=np.uint8))
sizes = np.bincount(components.ravel())[1:]
largest = []
for component in np.argsort(sizes)[::-1][:10] + 1:
    rr, cc = np.where(components == component)
    largest.append({
        "cells": int(len(rr)),
        "centroid_xy_m": [float(428100 + (cc.mean() + 0.5) * 0.5), float(4504400 - (rr.mean() + 0.5) * 0.5)],
        "bounds_xy_m": [float(428100 + cc.min() * 0.5), float(4504400 - (rr.max() + 1) * 0.5),
                        float(428100 + (cc.max() + 1) * 0.5), float(4504400 - rr.min() * 0.5)],
    })

stage = json.loads((ROOT / "millcreek_building_tree_trial_v2/model_trial.json").read_text())
result = {
    "comparison": "tree-only CHM vs sequential building-then-tree CHM, 2 m canopy threshold, current OSM roof mask",
    "roof_mask_cells_added_total": int(added.sum()),
    "roof_mask_added_components_eight_connected": int(count),
    "largest_added_components": largest,
    "point_window_xy_m_inclusive": BOX,
    "point_window_count": int(window.sum()),
    "point_window_classes": {k: dict(sorted(Counter(map(int, a)).items())) for k, a in classes.items()},
    "point_window_transitions_tree_only_to_sequential": transitions(classes["tree_only"], classes["building_then_tree"]),
    "point_window_transitions_standard_to_sequential": transitions(classes["standard"], classes["building_then_tree"]),
    "retained_stage_counts": stage["stages"],
    "intermediate_after_building_las_retained": False,
    "integrity": integrity,
    "las_sha256_before": before,
    "las_sha256_after": {k: digest(v) for k, v in LAS.items()},
    "imagery_manifest": str(ROOT / "nearmap_2023-08-31_pilot.json"),
}
result["las_hashes_unchanged_by_validation"] = result["las_sha256_before"] == result["las_sha256_after"]
print(json.dumps(result, indent=2))
