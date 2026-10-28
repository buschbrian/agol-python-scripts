"""Rank the unlabelled review units whose answers would settle open refinement questions.

Writes <data>/priority.json (the order only, which the page reads) and <packet>/label-page-priority-groups.json (the order with
each unit's group, outside the folder the page server publishes).

    python reviews/2026-10-20/label-page/build_priority.py [--per-group 40]

Run with the Myria3D environment's Python (laspy; PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT set). Reads the refined copy and the
FRACTAL consensus of 12TVL2804, the packet, the page answers and the label backup; writes only the two files above.
Each unlabelled, non-audit unit's patch is put in at most one group, in this order:
- rule11_green / rule11_bare: at least half the patch is vegetation that all FRACTAL passes call ground (rule 11), with a green
  (NDVI above 0.10) or bare median colour: answers test rule 11 and the lawn question;
- changed: at least a third of the patch changed class under the applied rules 1 to 6: answers test those changes;
- unsure_model: at least a third of the patch did not get a unanimous FRACTAL vote.
Groups are interleaved and shuffled within (fixed seed), up to --per-group units each. The page shows the order only, never the
group, so labelling stays blind; the groups are kept here for the analysis. Units chosen this way are not a random sample: use
them to test the rules, never to estimate an accuracy.
"""
import argparse
import csv
import json
from pathlib import Path
import random
import sys

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
from canopy.lidar_root import lidar_root  # noqa: E402

LIDAR = lidar_root()/"2023-salt-lake-valley"
PACKET = LIDAR/"runs"/"pilot-2026-09-29"/"training-review"/"packet-20260929"
TILE = "12TVL2804"
REFINED = LIDAR/"runs"/"refined-fractal-20261019"/"points"/f"{TILE}.las"
CONSENSUS = LIDAR/"fractal"/"city-20261019"/"fractal"/TILE/"consensus.las"
LABELS = TOOLBOX/"reviews"/"2026-09-29"/"packets"/"training-labels"/"labels-progress.csv"
NDVI_GREEN = 0.10
SEED = 20261020
GROUPS = ("rule11_green", "rule11_bare", "changed", "unsure_model")


def classify(rule, votes, ndvi, repeats=3):
    """The group of one patch from its points' rule codes, FRACTAL votes and NDVI; None when it fits no group."""
    if not len(rule):
        return None
    if (rule == 11).mean() >= 0.5:
        return "rule11_green" if np.nanmedian(ndvi) > NDVI_GREEN else "rule11_bare"
    if np.isin(rule, (1, 2, 3, 4, 5, 6)).mean() >= 1/3:
        return "changed"
    if (votes < repeats).mean() >= 1/3:
        return "unsure_model"
    return None


def interleave(groups, per_group, seed=SEED):
    rng = random.Random(seed)
    lists = {g: sorted(ids) for g, ids in groups.items()}
    for ids in lists.values():
        rng.shuffle(ids)
    lists = {g: ids[:per_group] for g, ids in lists.items()}
    order = []
    while any(lists.values()):
        for g in GROUPS:
            if lists.get(g):
                order.append((lists[g].pop(0), g))
    return order


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--per-group", type=int, default=40)
    parser.add_argument("--data", type=Path, default=PACKET/"label-page")
    args = parser.parse_args(argv)
    import laspy
    units = {u["UNIT_ID"]: u for u in json.loads((PACKET/"packet.json").read_text(encoding="utf-8"))["units"]}
    page = json.loads((args.data/"units.json").read_text(encoding="utf-8"))["units"]
    audit = {u["UNIT_ID"] for u in page if u["AUDIT"]}
    labelled = {r["UNIT_ID"] for r in csv.DictReader(open(LABELS, encoding="utf-8")) if r["LABEL"]}
    answers = args.data/"answers"/"label-page-answers.csv"
    if answers.exists():
        labelled |= {r["UNIT_ID"] for r in csv.DictReader(open(answers, encoding="utf-8")) if r["LABEL"]}
    ref, cons = laspy.read(REFINED), laspy.read(CONSENSUS)
    for name in ("X", "Y", "Z", "gps_time"):
        if not np.array_equal(np.asarray(ref[name]), np.asarray(cons[name])):
            raise ValueError(f"Refined copy and consensus are not aligned ({name})")
    clean = ~np.asarray(ref.withheld, bool)
    x, y, z = (np.asarray(v)[clean] for v in (ref.x, ref.y, ref.z))
    rule, votes = np.asarray(ref.REFINE_RULE)[clean], np.asarray(ref.FRACTAL_VOTES)[clean]
    red, nir = (np.asarray(cons[c], dtype=np.float64)[clean] for c in ("red", "nir"))
    ndvi = np.where(red+nir > 0, (nir-red)/np.maximum(red+nir, 1), np.nan)
    from scipy.spatial import cKDTree
    tree = cKDTree(np.c_[x, y])
    groups = {g: [] for g in GROUPS}
    for uid, u in units.items():
        if uid in labelled or uid in audit:
            continue
        idx = np.asarray(tree.query_ball_point([u["X"], u["Y"]], u["PATCH_R_M"]), dtype=np.int64)
        idx = idx[(z[idx] >= u["Z_LOW"]) & (z[idx] <= u["Z_HIGH"])]
        group = classify(rule[idx], votes[idx], ndvi[idx])
        if group:
            groups[group].append(uid)
    order = interleave(groups, args.per_group)
    document = {"schema": "canopy-label-priority/1", "tile": TILE, "seed": SEED, "per_group": args.per_group,
                "ndvi_green": NDVI_GREEN, "available": {g: len(v) for g, v in groups.items()},
                "interpretation": "Units chosen by model disagreement to test refinement rules; not a random sample.",
                "order": [uid for uid, _ in order], "groups": {uid: g for uid, g in order}}
    # The page gets the order only (the server publishes the whole data folder); the groups stay beside the packet.
    write(args.data.parent/"label-page-priority-groups.json", document)
    write(args.data/"priority.json", {"order": document["order"]})
    print(json.dumps({k: document[k] for k in ("available", "per_group")}), "->", len(order), "units")


def write(path, document):
    partial = path.with_suffix(".partial")
    partial.write_text(json.dumps(document, indent=1), encoding="utf-8")
    partial.replace(path)


if __name__ == "__main__":
    main()
