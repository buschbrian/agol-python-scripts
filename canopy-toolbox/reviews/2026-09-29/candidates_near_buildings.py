"""Count tree candidates that sit on or against buildings, and compare them with roof height.

For each run's trees_review points, finds class-6 points in the run's own prepared LAS tile.
A candidate is "near" a building when a class-6 point lies within the given horizontal
distance. For candidates within 1 m, the local roof height is the 90th-percentile Z of those
class-6 points minus the median class-2 Z within 5 m, and the candidate's HEIGHT_M is
compared with it. A candidate at roof height is a roof-edge suspect; one well above the roof
is more likely an overhanging tree. Neither is a verified label.

Usage (Pro Python, from canopy-toolbox): python reviews/2026-09-29/candidates_near_buildings.py
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import arcpy
import numpy as np
from scipy.spatial import cKDTree

from canopy import roofs

ROOT = Path(r"H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29")
HERE = Path(__file__).resolve().parent
# (tile, run folder, prepared LAS of that run relative to the tile folder)
RUNS = [("12TVL2804", "run", r"prepared\points\12TVL2804.las"),
        ("12TVL2804", "run-refined", r"roof-refined\points\12TVL2804.las"),
        ("12TVL3302", "run", r"prepared\points\12TVL3302.las"),
        ("12TVL2203", "run", r"prepared\points\12TVL2203.las")]
DISTANCES = (1.0, 1.5, 3.0)
BANDS = ("at_roof_height_le_0.5m", "0.5_to_2m_above_roof", "over_2m_above_roof")


def points(path, code):
    pts, scale, offset, _ = roofs._records(path)
    mask = pts["classification"] == code
    return np.column_stack([pts[axis][mask] * scale[i] + offset[i] for i, axis in enumerate("xyz")])


def main():
    near_report, height_report = {}, {}
    for tile, run, las in RUNS:
        building, ground = points(ROOT / tile / las, 6), points(ROOT / tile / las, 2)
        btree, gtree = cKDTree(building[:, :2]), cKDTree(ground[:, :2])
        fc = json.loads((ROOT / tile / run / "run.json").read_text())["outputs"]["trees_review"]
        rows = list(arcpy.da.SearchCursor(fc, ["SHAPE@X", "SHAPE@Y", "HEIGHT_M", "CROWN_STATUS"]))
        xy = np.array([(r[0], r[1]) for r in rows])
        small = np.array([r[3] == "CROWN_TOO_SMALL" for r in rows])
        row = {"candidates": len(rows), "small_crown": int(small.sum())}
        for d in DISTANCES:
            near = np.isfinite(btree.query(xy, distance_upper_bound=d, workers=-1)[0])
            row[f"within_{d}m"] = int(near.sum())
            row[f"within_{d}m_small_crown"] = int((near & small).sum())
        near_report[f"{tile}/{run}"] = row
        if run != "run":
            continue
        split, split_small = dict.fromkeys(BANDS, 0), dict.fromkeys(BANDS, 0)
        for (x, y, height, _), is_small in zip(rows, small):
            roof = btree.query_ball_point((x, y), 1.0)
            under = gtree.query_ball_point((x, y), 5.0)
            if not roof or not under:
                continue
            above = height - (np.percentile(building[roof, 2], 90) - np.median(ground[under, 2]))
            band = BANDS[0 if above <= .5 else 1 if above <= 2 else 2]
            split[band] += 1
            split_small[band] += int(is_small)
        height_report[tile] = {"candidates_within_1m": sum(split.values()),
                               "by_height_vs_roof": split, "small_crown_subset": split_small}
    (HERE / "candidates-near-buildings.json").write_text(json.dumps(near_report, indent=2))
    (HERE / "candidates-vs-roof-height.json").write_text(json.dumps({
        "method": "roof = 90th percentile Z of class-6 points within 1 m of the treetop; ground = "
                  "median class-2 Z within 5 m; candidate HEIGHT_M compared with roof height above ground",
        "tiles": height_report}, indent=2))
    print(json.dumps({"near": near_report, "vs_roof": height_report}, indent=2))


if __name__ == "__main__":
    main()
