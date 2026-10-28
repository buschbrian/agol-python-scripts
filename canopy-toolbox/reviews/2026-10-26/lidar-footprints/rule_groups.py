"""Decide most of the LiDAR-vs-county disagreements by rule, and regroup the review queue so Brian answers only the
uncertain ones (October 26, 2026).

Brian: "figure out what exactly I need to answer so that we can start refining all of these other ones ... and I don't
have to review 6,213". The rules come from his answers so far, mapped onto the compare classes (167 building answers on
the earlier queues plus the new one):
- COUNTY_ONLY: with under 30% canopy over the county outline, all 4 he answered were gone (rebuilt); with 30% or more,
  16 of 20 were still standing, hidden by trees or too small for the LiDAR. Rule: under 30% gone, otherwise keep the
  county outline.
- RESHAPED: 30% or more canopy means the LiDAR outline is cut short by trees (his UNDER_TREES answers), so keep the
  county outline. Under 10%, the LiDAR outline replaces it. 10-30% is uncertain: a sample of 40 goes to him and the
  rest wait on it.
- LIDAR_SPLITS: his pair answers were BOTH_REAL, separate buildings. Rule: the LiDAR buildings replace the outline.
- LIDAR_ONLY: 29 of 33 accepted, 4 vehicles. Vehicle-shaped outlines (12-45 m2, at most 3.3 m wide, 2.5 times as long
  as wide, 2.3-4.5 m high, the October 23 rule) are not buildings: he called 14 of the first 16 vehicles (one shed,
  one unsure), so the group became a rule. A sample of 40 under 20 m2 checks the sheds. The rest are
  added as buildings.
- LIDAR_JOINS: keep the county unit lines or not is a judgment the cues cannot make, so a sample of 40 decides the
  class. The other 983 wait for that decision.
- TANGLE: all 13 to him.

    python rule_groups.py DATA        writes OUT/proposed-decisions.csv and regroups the outlines items in DATA
                                      (atomically, bundle by bundle; answers untouched)
"""
import collections
import csv
import json
import math
import os
from pathlib import Path
import random
import sys

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
from canopy.lidar_root import lidar_root  # noqa: E402

RUNS = lidar_root()/"2023-salt-lake-valley"/"runs"
CITY = RUNS/"lidar-footprints-20261026"/"city"
SEED = 20261026
GROUPS = {   # group -> (page label, rule decision or None when Brian decides), in page order
    "decide_joins": ("1 Decide: one LiDAR building over several county outlines (sample)", None),
    "decide_reshaped": ("2 Decide: reshaped, partly under trees (10-30% canopy, sample)", None),
    "decide_small": ("3 Decide: LiDAR-only under 20 m² (sample)", None),
    "decide_tangle": ("4 Decide: tangles (sample)", None),
    "check_county_kept": ("5 Check: county outline kept under trees (sample)", "KEEP_COUNTY"),
    "joins_wait": ("Waits on 1: one LiDAR building over several county outlines", None),
    "reshaped_wait": ("Waits on 2: reshaped, partly under trees", None),
    "tangle_wait": ("Waits on 4: tangles", None),
    "auto_reshaped_lidar": ("Rule: reshaped, open ground, LiDAR replaces", "LIDAR_RIGHT"),
    "auto_reshaped_trees": ("Rule: reshaped under trees, keep the county outline", "KEEP_COUNTY"),
    "auto_splits": ("Rule: county outline over several LiDAR buildings, LiDAR replaces", "LIDAR_RIGHT"),
    "auto_county_gone": ("Rule: county footprint, no roof, open ground: gone", "GONE"),
    "auto_county_kept": ("Rule: county footprint, no roof, under trees: keep", "KEEP_COUNTY"),
    "auto_lidar_only": ("Rule: LiDAR-only building, added", "LIDAR_RIGHT"),
    "auto_vehicles": ("Rule: LiDAR-only, vehicle-shaped: not a building", "NOT_A_BUILDING"),
    "small_rest": ("Rule after 4: LiDAR-only under 20 m²", None),
}


def f(v):
    return float(v) if v not in ("", None) else 0.0


def vehicle_like(g, h):
    c = list(g.minimum_rotated_rectangle.exterior.coords)
    a, b = math.dist(c[0], c[1]), math.dist(c[1], c[2])
    length, width = max(a, b), min(a, b)
    return 12 <= g.area <= 45 and width <= 3.3 and length >= 2.5 * width and 2.3 <= h <= 4.5


def assign(city=CITY, layer="buildings"):
    import geopandas as gpd
    lidar = gpd.read_file(city/"lidar.gdb", layer=layer).set_index("LB_ID")
    with (city/"compare.csv").open(encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["CLASS"] != "MATCH"]
    rng = random.Random(SEED)
    group = {}
    joins = sorted(r["GROUP"] for r in rows if r["CLASS"] == "LIDAR_JOINS")
    joins_sample = set(rng.sample(joins, 40))
    small = []
    for r in rows:
        c, canopy = r["CLASS"], f(r["COUNTY_CANOPY_PCT"].split(";")[0] if r["COUNTY_CANOPY_PCT"] else "")
        if c == "LIDAR_JOINS":
            group[r["GROUP"]] = "decide_joins" if r["GROUP"] in joins_sample else "joins_wait"
        elif c == "RESHAPED":
            group[r["GROUP"]] = ("auto_reshaped_trees" if canopy >= 30 else "auto_reshaped_lidar" if canopy < 10
                                 else "decide_reshaped")
        elif c == "LIDAR_SPLITS":
            group[r["GROUP"]] = "auto_splits"
        elif c == "TANGLE":
            group[r["GROUP"]] = "decide_tangle"
        elif c == "COUNTY_ONLY":
            group[r["GROUP"]] = "auto_county_kept" if canopy >= 30 else "auto_county_gone"
        elif c == "LIDAR_ONLY":
            b = lidar.loc[r["LIDAR_IDS"]]
            if vehicle_like(b.geometry, b.ROOF_H50_M):
                group[r["GROUP"]] = "auto_vehicles"
            elif b.geometry.area < 20:
                small.append(r["GROUP"])
                group[r["GROUP"]] = "small_rest"
            else:
                group[r["GROUP"]] = "auto_lidar_only"
    for g in rng.sample(sorted(small), 40):
        group[g] = "decide_small"
    tangles = sorted(g for g, v in group.items() if v == "decide_tangle")
    keep_t = set(rng.sample(tangles, min(40, len(tangles))))
    for g in tangles:
        if g not in keep_t:
            group[g] = "tangle_wait"
    middle = sorted(g for g, v in group.items() if v == "decide_reshaped")
    keep = set(rng.sample(middle, 40))
    for g in middle:
        if g not in keep:
            group[g] = "reshaped_wait"
    kept = sorted(g for g, v in group.items() if v == "auto_county_kept")
    for g in rng.sample(kept, 40):
        group[g] = "check_county_kept"
    return rows, group


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("data", type=Path)
    p.add_argument("--city", type=Path, default=CITY)
    p.add_argument("--layer", default="buildings")
    p.add_argument("--queue", default="outlines")
    p.add_argument("--prefix", default="O")
    a = p.parse_args()
    data, city, queue = a.data.resolve(), a.city.resolve(), a.queue
    rows, group = assign(city, a.layer)
    out = city/"proposed-decisions.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, ["GROUP", "CLASS", "COUNTY_IDS", "LIDAR_IDS", "REVIEW_GROUP", "PROPOSED", "BY"])
        w.writeheader()
        for r in rows:
            g = group[r["GROUP"]]
            w.writerow({"GROUP": r["GROUP"], "CLASS": r["CLASS"], "COUNTY_IDS": r["COUNTY_IDS"], "LIDAR_IDS": r["LIDAR_IDS"],
                        "REVIEW_GROUP": g, "PROPOSED": GROUPS[g][1] or "", "BY": "rule" if GROUPS[g][1] else "Brian"})
    # Regroup the page items: bundles first (a partial file, then a rename), then the index in page order.
    built = json.loads((data/"index.json").read_text(encoding="utf-8"))
    new_group = {a.prefix + g: v for g, v in group.items()}
    for name in sorted({it["bundle"] for it in built["items"] if it["queue"] == queue}):
        path = data/"bundles"/name
        bundle = json.loads(path.read_text(encoding="utf-8"))
        for i, d in bundle.items():
            d["group"] = new_group[i]
        partial = path.with_suffix(".partial")
        partial.write_text(json.dumps(bundle, separators=(",", ":"), allow_nan=False), encoding="utf-8")
        os.replace(partial, path)
    rank = {g: k for k, g in enumerate(GROUPS)}
    others = [it for it in built["items"] if it["queue"] != queue]
    mine = sorted((dict(it, group=new_group[it["id"]]) for it in built["items"] if it["queue"] == queue),
                  key=lambda it: (rank[it["group"]], it["order"]))
    items = others + mine
    for k, it in enumerate(items, 1):
        it["order"] = k
    counts = {}
    for it in items:
        counts.setdefault(it["queue"], {}).setdefault(it["group"], 0)
        counts[it["queue"]][it["group"]] += 1
    built.update(items=items, counts=counts, outlines_regrouped={"rules": str(HERE), "seed": SEED})
    partial = data/"index.partial"
    partial.write_text(json.dumps(built, separators=(",", ":")), encoding="utf-8")
    os.replace(partial, data/"index.json")
    c = counts[queue]
    print(json.dumps({g: c.get(g, 0) for g in GROUPS}, indent=1))
    print("to answer now:", sum(c.get(g, 0) for g in GROUPS if g.startswith(("decide", "check"))))


if __name__ == "__main__":
    main()
