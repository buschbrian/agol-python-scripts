"""Grade Brian's regrade answers (outlines2 queue) into decisions, and regroup the queue so his next pass is only what
the answers cannot settle (October 27, 2026).

Brian, halfway through the five regrade groups: "you want to grade and then bring up a new queue". What his answers say:
- 1 joins (40 of 40): 23 keep the county outlines (the parcel cut already separated the neighbours), 5 LiDAR, 4 edit;
  five UNSURE notes say "separate buildings" or "split", so they count as SPLIT_BUILDINGS. Rule: the 550 waiting keep
  the county outlines (about 1 in 4 of his sample wanted the LiDAR shape or a split; the rule leaves those as they are).
- 5 county kept under trees (40 of 40): 29 keep (16 under trees, 12 small sheds, 1 offset) against 5 drop. The rule that
  keeps the 449 county outlines under trees stands.
- 2 reshaped, 10-30% canopy (18 of 40): split 5, add roof 5, edit 2, county 2, LiDAR 2, shift 1. Every answer is a
  different fix, so no rule: the 42 waiting become a group he answers one by one.
- 3 small LiDAR-only (24 of 40): measured cues sort them. Touching a building of 40 m2 or more: 3 of 5 part of it.
  Vehicle-shaped (at least 5.2 m long, at most 3.3 m wide, at most 3 m high) or in the street: 4 of 5 vehicles.
  Free-standing: 8 of 12 sheds or buildings, 4 not a building. Rules for the free-standing and vehicle-shaped ones;
  the touching ones (also 145 of the October 26 "vehicle" rule, likely strips of garages cut at a lot line) get a
  check sample of 20.
- 4 tangles (3 of 40): too few to say anything; the 142 keep waiting.

    python grade_regrade.py DATA     writes CITY/decisions.csv and regroups the outlines2 items (answers untouched)
"""
import collections
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sys

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import rule_groups as rg  # noqa: E402

CITY = rg.RUNS/"lidar-footprints-20261026"/"city2"
QUEUE, PREFIX, LAYER = "outlines2", "Q", "buildings_filled"
SEED = 20261027
CHECK_TOUCHING = 20
BIG_M2 = 40          # "a building" a small piece can be part of
GROUPS = {   # group -> (page label, decision or None when Brian decides), in page order
    "decide_joins": ("1 Decide: one LiDAR building over several county outlines (sample, done)", None),
    "decide_reshaped": ("2 Decide: reshaped, partly under trees (10-30% canopy, sample)", None),
    "decide_small": ("3 Decide: LiDAR-only under 20 m² (sample)", None),
    "decide_tangle": ("4 Decide: tangles (sample)", None),
    "check_county_kept": ("5 Check: county outline kept under trees (sample, done)", None),
    "answer_reshaped": ("6 Answer each: reshaped, partly under trees (the other 42)", None),
    "check_touching": ("7 Check: small piece touching a building (sample)", None),
    "touching_wait": ("Waits on 7: small piece touching a building", "PART_OF_BUILDING"),
    "tangle_wait": ("Waits on 4: tangles", None),
    "rule_joins_county": ("Rule from 1: one LiDAR building over several county outlines: keep the county", "KEEP_COUNTY"),
    "rule_small_shed": ("Rule from 3: small, free-standing: shed", "SHED"),
    "rule_small_vehicle": ("Rule from 3: small, vehicle-shaped or in the street: vehicle", "VEHICLE"),
    "auto_reshaped_lidar": ("Rule: reshaped, open ground, LiDAR replaces", "LIDAR_RIGHT"),
    "auto_reshaped_trees": ("Rule: reshaped under trees, keep the county outline", "KEEP_COUNTY"),
    "auto_splits": ("Rule: county outline over several LiDAR buildings, LiDAR replaces", "LIDAR_RIGHT"),
    "auto_county_gone": ("Rule: county footprint, no roof, open ground: gone", "GONE"),
    "auto_county_kept": ("Rule (checked by 5): county footprint, no roof, under trees: keep", "KEEP_COUNTY"),
    "auto_lidar_only": ("Rule: LiDAR-only building, added", "LIDAR_RIGHT"),
    "auto_vehicles": ("Rule: LiDAR-only, vehicle-shaped: not a building", "VEHICLE"),
}
WAS = {"joins_wait": "rule_joins_county", "reshaped_wait": "answer_reshaped"}   # October 26 groups that move as a whole


def decision(answer, note):
    """Brian's answer as a decision: COUNTY_RIGHT and UNDER_TREES both keep the county outline, and an UNSURE whose
    note names separate buildings is a split."""
    n = note.lower()
    if answer in ("COUNTY_RIGHT", "UNDER_TREES"):
        return "KEEP_COUNTY"
    if answer == "UNSURE" and ("sep" in n or "split" in n):
        return "SPLIT_BUILDINGS"
    if answer == "UNSURE" and "gone" in n:
        return "NEEDS_EDIT"
    return answer


def small_cue(g, h, big, big_tree, streets):
    """touching / vehicle / shed for a LiDAR-only outline, from its shape, height and place."""
    if any(g.distance(big[j]) < 0.1 for j in big_tree.query(g.buffer(0.1))):
        return "touching"
    c = list(g.minimum_rotated_rectangle.exterior.coords)
    a, b = math.dist(c[0], c[1]), math.dist(c[1], c[2])
    if (max(a, b) >= 5.2 and min(a, b) <= 3.3 and h <= 3.0) or not len(streets.query(g.centroid, "within")):
        return "vehicle"
    return "shed"


def main():
    import argparse
    import geopandas as gpd
    import shapely
    sys.path.insert(0, str(HERE.parent))
    import lidar_footprints as lf
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("data", type=Path)
    p.add_argument("--city", type=Path, default=CITY)
    a = p.parse_args()
    data, city = a.data.resolve(), a.city.resolve()
    answers_csv = data/"answers"/"footprint-review-answers.csv"
    digest = hashlib.sha256(answers_csv.read_bytes()).hexdigest()
    (city.parent/"answers-before-grade.sha256").write_text(f"{digest}  {answers_csv}\n", encoding="utf-8")
    with answers_csv.open(encoding="utf-8") as fh:
        answered = {r["ITEM_ID"][len(PREFIX):]: r for r in csv.DictReader(fh) if r["QUEUE"] == QUEUE and r["ANSWER"]}
    built = json.loads((data/"index.json").read_text(encoding="utf-8"))
    old = {it["id"][len(PREFIX):]: it["group"] for it in built["items"] if it["queue"] == QUEUE}
    with (city/"compare.csv").open(encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r["GROUP"] in old]

    lidar = gpd.read_file(city/"lidar.gdb", layer=LAYER).set_index("LB_ID")
    big = [g for g in lidar.geometry if g.area >= BIG_M2]
    big_tree = shapely.STRtree(big)
    parcels = gpd.read_file(lf.fc.INPUTS, layer="parcels", columns=[])
    streets = shapely.STRtree([g for g in parcels.geometry if g is not None])   # outside every parcel = street

    group, cue = {}, {}
    for r in rows:
        g0 = old[r["GROUP"]]
        if g0 in ("small_rest", "auto_vehicles", "decide_small"):
            b = lidar.loc[r["LIDAR_IDS"]]
            cue[r["GROUP"]] = small_cue(b.geometry, b.ROOF_H50_M, big, big_tree, streets)
        if g0.startswith(("decide", "check")):
            group[r["GROUP"]] = g0
        elif g0 in WAS:
            group[r["GROUP"]] = WAS[g0]
        elif g0 == "small_rest":
            group[r["GROUP"]] = {"touching": "touching_wait", "vehicle": "rule_small_vehicle", "shed": "rule_small_shed"}[cue[r["GROUP"]]]
        elif g0 == "auto_vehicles" and cue[r["GROUP"]] == "touching":
            group[r["GROUP"]] = "touching_wait"
        else:
            group[r["GROUP"]] = g0
    touching = sorted(g for g, v in group.items() if v == "touching_wait")
    for g in random.Random(SEED).sample(touching, CHECK_TOUCHING):
        group[g] = "check_touching"

    out = city/"decisions.csv"
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, ["GROUP", "CLASS", "COUNTY_IDS", "LIDAR_IDS", "REVIEW_GROUP", "SMALL_CUE", "DECISION", "BY",
                                "ANSWER", "NOTE"])
        w.writeheader()
        for r in rows:
            g, ans = group[r["GROUP"]], answered.get(r["GROUP"])
            if ans:
                dec, by = decision(ans["ANSWER"], ans["NOTE"]), "Brian"
            else:
                dec, by = GROUPS[g][1] or "", "rule" if GROUPS[g][1] else "waiting"
            w.writerow({"GROUP": r["GROUP"], "CLASS": r["CLASS"], "COUNTY_IDS": r["COUNTY_IDS"], "LIDAR_IDS": r["LIDAR_IDS"],
                        "REVIEW_GROUP": g, "SMALL_CUE": cue.get(r["GROUP"], ""), "DECISION": dec, "BY": by,
                        "ANSWER": ans["ANSWER"] if ans else "", "NOTE": ans["NOTE"] if ans else ""})

    # Regroup the page items as rule_groups.py does: bundles first (a partial file, then a rename), then the index.
    new_group = {PREFIX + g: v for g, v in group.items()}
    for name in sorted({it["bundle"] for it in built["items"] if it["queue"] == QUEUE}):
        path = data/"bundles"/name
        bundle = json.loads(path.read_text(encoding="utf-8"))
        for i, d in bundle.items():
            d["group"] = new_group[i]
        partial = path.with_suffix(".partial")
        partial.write_text(json.dumps(bundle, separators=(",", ":"), allow_nan=False), encoding="utf-8")
        os.replace(partial, path)
    rank = {g: k for k, g in enumerate(GROUPS)}
    others = [it for it in built["items"] if it["queue"] != QUEUE]
    mine = sorted((dict(it, group=new_group[it["id"]]) for it in built["items"] if it["queue"] == QUEUE),
                  key=lambda it: (rank[it["group"]], it["order"]))
    items = others + mine
    for k, it in enumerate(items, 1):
        it["order"] = k
    counts = {}
    for it in items:
        counts.setdefault(it["queue"], {}).setdefault(it["group"], 0)
        counts[it["queue"]][it["group"]] += 1
    built.update(items=items, counts=counts, outlines2_graded={"script": str(HERE), "seed": SEED, "decisions": str(out)})
    partial = data/"index.partial"
    partial.write_text(json.dumps(built, separators=(",", ":")), encoding="utf-8")
    os.replace(partial, data/"index.json")

    c = counts[QUEUE]
    print(json.dumps({g: c.get(g, 0) for g in GROUPS}, indent=1))
    with out.open(encoding="utf-8") as fh:
        d = list(csv.DictReader(fh))
    print("by:", dict(collections.Counter(r["BY"] for r in d)))
    print("decisions:", dict(collections.Counter(r["DECISION"] or "(waiting)" for r in d).most_common()))
    print("cues of answered small:", dict(collections.Counter((cue[g], answered[g]["ANSWER"]) for g in cue if g in answered)))
    print("to answer now:", sum(1 for r in d if r["BY"] == "waiting" and r["REVIEW_GROUP"].startswith(("decide", "check", "answer"))))


if __name__ == "__main__":
    main()
