"""Summarize the refined copies citywide and measure what they mean for the October 8 candidate treetops. Read-only on inputs.

    python reviews/2026-10-19/fractal-city/summarize_refined.py NEW_OUTPUT_DIR

Run with the Myria3D environment's Python (laspy; PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT set). Writes into a new folder:
- summary.json: rule and class-change totals by tile and citywide, repeat agreement, inputs;
- treetops-refined.csv: for every October 8 treetop, the highest baseline-vegetation point in its 0.5 m cell (the point that set its
  canopy height), that point's refined class and rule, joined by TREE_ID to the October 15 evidence flags.
A treetop whose top point leaves vegetation is a candidate for removal, not a removal: rebuilding the canopy surface from the refined
classes would decide that, and neighbouring vegetation could still form a peak. Agreement with the October 15 flags is agreement
between two methods, neither of which is ground truth.
"""
import argparse
import csv
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
from canopy.lidar_root import lidar_root  # noqa: E402

LIDAR = lidar_root()/"2023-salt-lake-valley"
REFINED = LIDAR/"runs"/"refined-fractal-20261019"/"points"
TREETOPS = LIDAR/"runs"/"city-count-20261008"/"city-treetops.csv"
EVIDENCE = LIDAR/"runs"/"treetop-evidence-20261015"/"treetop-evidence.csv"
CELL = 0.5
VEGETATION = (3, 4, 5)
FLAGS = ("SUSPECT", "ROOF_HEIGHT", "OVERHANG", "FLAT_TOP", "WIRE_HINT", "POLE_HINT", "WALL_HINT", "NEAR_BUILDING")


def cell_keys(x, y):
    return np.floor(np.asarray(x)/CELL).astype(np.int64)*10_000_000+np.floor(np.asarray(y)/CELL).astype(np.int64)


def top_points(keys, z):
    """Index of the highest point for each distinct key, and the sorted distinct keys."""
    order = np.lexsort((-np.asarray(z), keys))
    sorted_keys = keys[order]
    first = np.ones(len(order), bool)
    first[1:] = sorted_keys[1:] != sorted_keys[:-1]
    return sorted_keys[first], order[first]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path)
    args = parser.parse_args(argv)
    if args.out.exists():
        raise FileExistsError(args.out)
    import laspy
    tiles = sorted(p.stem for p in REFINED.glob("*.json"))
    city = {"tiles": len(tiles), "points": 0, "changed": 0, "unanimous": 0, "withheld": 0, "no_ground_height": 0,
            "rules": {}, "changed_from_to": {}, "by_tile": {}}
    for tile in tiles:
        s = json.loads((REFINED/f"{tile}.json").read_text(encoding="utf-8"))
        for key in ("points", "changed", "unanimous", "withheld", "no_ground_height"):
            city[key] += s[key]
        for group in ("rules", "changed_from_to"):
            for k, v in s[group].items():
                city[group][k] = city[group].get(k, 0)+v
        city["by_tile"][tile] = {"points": s["points"], "changed": s["changed"], "changed_pct": round(100*s["changed"]/s["points"], 3),
                                 "unanimous_pct": round(100*s["unanimous"]/s["points"], 2), "rules": s["rules"]}
    evidence = {}
    with open(EVIDENCE, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            evidence[row["TREE_ID"]] = {f: row[f] == "1" for f in FLAGS}
    treetops = list(csv.DictReader(open(TREETOPS, encoding="utf-8", newline="")))
    tx, ty = np.array([float(t["X"]) for t in treetops]), np.array([float(t["Y"]) for t in treetops])
    tkeys = cell_keys(tx, ty)
    result = {i: None for i in range(len(treetops))}
    for tile in tiles:
        las = laspy.read(REFINED/f"{tile}.las")
        base = np.asarray(las.BASE_CLASS)
        veg = np.isin(base, VEGETATION) & ~np.asarray(las.withheld, bool)
        x, y, z = np.asarray(las.x)[veg], np.asarray(las.y)[veg], np.asarray(las.z)[veg]
        keys, top = top_points(cell_keys(x, y), z)
        refined, rule = np.asarray(las.classification)[veg][top], np.asarray(las.REFINE_RULE)[veg][top]
        lo, hi = las.header.mins, las.header.maxs
        inside = np.flatnonzero((tx >= lo[0]) & (tx <= hi[0]) & (ty >= lo[1]) & (ty <= hi[1]))
        where = np.searchsorted(keys, tkeys[inside])
        found = (where < len(keys)) & (keys[np.minimum(where, len(keys)-1)] == tkeys[inside])
        for i, w, ok in zip(inside, where, found):
            if result[i] is None and ok:
                result[i] = (tile, int(refined[w]), int(rule[w]))
        print(f"{tile}: {int(found.sum()):,} treetops matched", flush=True)
    args.out.mkdir(parents=True)
    impact = {"treetops": len(treetops), "matched": 0, "top_left_vegetation": 0, "by_rule": {},
              "flags_where_top_left_vegetation": {f: 0 for f in FLAGS}, "flags_where_top_stayed": {f: 0 for f in FLAGS},
              "evidence_missing": 0}
    with open(args.out/"treetops-refined.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["TREE_ID", "TILE", "X", "Y", "HEIGHT_M", "TOP_REFINED_CLASS", "TOP_RULE", "TOP_LEFT_VEGETATION", *FLAGS])
        for i, t in enumerate(treetops):
            hit = result[i]
            flags = evidence.get(t["TREE_ID"])
            if flags is None:
                impact["evidence_missing"] += 1
            left = hit is not None and hit[1] not in VEGETATION
            if hit is not None:
                impact["matched"] += 1
                if left:
                    impact["top_left_vegetation"] += 1
                    impact["by_rule"][str(hit[2])] = impact["by_rule"].get(str(hit[2]), 0)+1
                if flags:
                    bucket = impact["flags_where_top_left_vegetation" if left else "flags_where_top_stayed"]
                    for f in FLAGS:
                        bucket[f] += int(flags[f])
            writer.writerow([t["TREE_ID"], hit[0] if hit else "", t["X"], t["Y"], t["HEIGHT_M"],
                             hit[1] if hit else "", hit[2] if hit else "", int(left),
                             *[int(flags[f]) if flags else "" for f in FLAGS]])
    city["treetop_impact"] = impact
    city["interpretation"] = ("Provisional model-driven refinement. Treetops whose top point left vegetation are candidates for review, "
                              "not removals; the October 15 flags are a second, independent opinion, not truth.")
    (args.out/"summary.json").write_text(json.dumps(city, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in city.items() if k != "by_tile"}, indent=1))


if __name__ == "__main__":
    main()
