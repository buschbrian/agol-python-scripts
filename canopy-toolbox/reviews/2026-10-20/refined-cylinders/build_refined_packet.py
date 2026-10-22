"""Build a review packet of smaller, layered cylinders inside the units answered MIXED or UNSURE (decided October 20, 2026).

    python reviews/2026-10-20/refined-cylinders/build_refined_packet.py [NEW_PACKET_DIR] [--labels backup.csv]

Run with ArcGIS Pro Python (PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT set). Read-only on the parent packet, its LAS and the labels;
writes a NEW packet folder (default packet-20261020-refined beside the parent) holding packet.json, patch_stats.json and
training_review.gdb, the same layout the label page, restore and the training export use.

For each parent unit answered MIXED or UNSURE, the points inside a 0.5 m cylinder at the parent's centre and within the parent's
height slab are sorted by height and cut wherever two consecutive points are more than 0.5 m apart; each layer of at least 6
points becomes a sub-unit (its slab is the layer's height range plus 5 cm, never beyond the parent slab). A tree over a roof becomes
two sub-units. At most four layers per parent: if there are more, the cut threshold grows until four or fewer remain.
Sub-units keep the parent's QUEUE, frame and ground height, are named <parent>-a, -b, ... from the top down, and carry no baseline
class or model field, so labelling stays blind. Every sub-unit passes the evaluation exclusion check. Patches at the same centre
are separated in height, which the training export accepts (stacked patches); they are never labelled as one.
"""
import argparse
import datetime
import json
from pathlib import Path
import string
import sys

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
from canopy import training_review as tr  # noqa: E402
from canopy.lidar_root import lidar_root, live  # noqa: E402

PARENT = lidar_root()/"2023-salt-lake-valley"/"runs"/"pilot-2026-09-29"/"training-review"/"packet-20260929"
LABELS = TOOLBOX/"reviews"/"2026-09-29"/"packets"/"training-labels"/"labels-progress.csv"
RADIUS_M = 0.5
GAP_M = 0.5
MIN_POINTS = 6                     # a 0.5 m cylinder holds roughly 15 to 30 points in all; 12 skipped half the parents
MAX_LAYERS = 4
PAD_M = 0.05
SOURCE_LABELS = ("MIXED", "UNSURE")


def layers(z, gap=GAP_M, min_points=MIN_POINTS, max_layers=MAX_LAYERS):
    """[(low, high, n)] from the top down: the heights cut at gaps wider than `gap`, small layers dropped,
    the gap threshold raised until at most max_layers remain."""
    z = np.sort(np.asarray(z, dtype=float))
    if len(z) < min_points:
        return []
    while True:
        cuts = np.flatnonzero(np.diff(z) > gap)
        groups = np.split(z, cuts+1)
        kept = [(float(g[0]), float(g[-1]), len(g)) for g in groups if len(g) >= min_points]
        if len(kept) <= max_layers:
            return sorted(kept, key=lambda k: -k[0])
        gap *= 1.5


def sub_units(parent, z, start_order):
    """Sub-unit dicts for one parent from the heights of its 0.5 m cylinder's points."""
    out = []
    for k, (low, high, n) in enumerate(layers(z)):
        z_low = max(float(parent["Z_LOW"]), round(low-PAD_M, 3))
        z_high = min(float(parent["Z_HIGH"]), round(high+PAD_M, 3))
        ground = parent.get("GROUND_Z")
        out.append({"UNIT_ID": f"{parent['UNIT_ID']}-{string.ascii_lowercase[k]}", "QUEUE": parent["QUEUE"],
                    "REVIEW_ORDER": start_order+k, "QUEUE_ORDER": parent.get("QUEUE_ORDER"), "TILE": parent.get("TILE"),
                    "X": parent["X"], "Y": parent["Y"], "Z_LOW": z_low, "Z_HIGH": z_high, "GROUND_Z": ground,
                    "HAG_LOW": None if ground is None else round(z_low-ground, 2),
                    "HAG_HIGH": None if ground is None else round(z_high-ground, 2), "PATCH_R_M": RADIUS_M,
                    "PRIORITY": parent.get("PRIORITY"), "SELECTION": "REFINED", "CLUSTER_PTS": n, "PATCH_PTS": n,
                    "BASE_CLASS": None, "TREE_MODEL": None, "BLDG_MODEL": None, "SHAPE_GROUP": None, "CAND_FLAG": None,
                    "EVIDENCE": f"layer {k+1} of {parent['UNIT_ID']}"})
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path, nargs="?", default=PARENT.with_name("packet-20261020-refined"))
    parser.add_argument("--parent", type=Path, default=PARENT)
    parser.add_argument("--labels", type=Path, default=LABELS)
    args = parser.parse_args(argv)
    if args.out.exists():
        raise FileExistsError(f"Choose a new packet folder: {args.out}")
    from canopy import las_records
    parent_doc = json.loads((args.parent/"packet.json").read_text(encoding="utf-8"))
    if parent_doc.get("schema") != tr.SCHEMA or tr.units_digest(parent_doc["units"]) != parent_doc["units_digest"]:
        raise ValueError("Not an unaltered training review packet")
    frame = tr.check_frame(parent_doc["frame"])
    stats = json.loads((args.parent/"patch_stats.json").read_text(encoding="utf-8"))
    source = live(stats["las"]["path"])
    answers = {r["UNIT_ID"]: r["LABEL"] for r in tr.read_backup(args.labels) if r["LABEL"]}
    parents = [u for u in sorted(parent_doc["units"], key=lambda u: (int(u["REVIEW_ORDER"]), u["UNIT_ID"]))
               if answers.get(u["UNIT_ID"]) in SOURCE_LABELS]
    block, scale, offset, modern, _ = las_records.records(source)
    clean = las_records.clean_flags(block["flags"], modern)          # withheld, synthetic and overlap points left out
    x, y, z = ((block[c][clean]*scale[i]+offset[i]) for i, c in enumerate(("x", "y", "z")))
    from scipy.spatial import cKDTree
    tree = cKDTree(np.c_[x, y])
    units, skipped, per_parent = [], [], {}
    for parent in parents:
        idx = np.asarray(tree.query_ball_point([parent["X"], parent["Y"]], RADIUS_M), dtype=np.int64)
        idx = idx[(z[idx] >= parent["Z_LOW"]) & (z[idx] <= parent["Z_HIGH"])]
        subs = sub_units(parent, z[idx], len(units)+1)
        if not subs:
            skipped.append(parent["UNIT_ID"])
            continue
        for s in subs:
            tr.assert_patch_allowed(s["X"], s["Y"], frame, s["PATCH_R_M"], what=f"{s['UNIT_ID']} refined patch")
        per_parent[parent["UNIT_ID"]] = {"label": answers[parent["UNIT_ID"]], "sub_units": [s["UNIT_ID"] for s in subs]}
        units.extend(subs)
    unit_stats = {}
    for u in units:
        idx = np.asarray(tree.query_ball_point([u["X"], u["Y"]], u["PATCH_R_M"]), dtype=np.int64)
        hz = z[idx[(z[idx] >= u["Z_LOW"]) & (z[idx] <= u["Z_HIGH"])]]-u["GROUND_Z"]
        unit_stats[u["UNIT_ID"]] = ({"n": int(len(hz)), "min": round(float(hz.min()), 2), "mean": round(float(hz.mean()), 3),
                                     "max": round(float(hz.max()), 2)} if len(hz) else {"n": 0, "min": None, "mean": None, "max": None})
    from canopy import training_review_arcpy as tra
    args.out.mkdir(parents=True)
    gdb = tra.create_review_gdb(args.out/"training_review.gdb", units, frame, tr.domain_mask(frame))
    document = {"schema": tr.SCHEMA, "purpose": "TRAINING labels only; never evaluation answers",
                "created": datetime.datetime.now().isoformat(timespec="seconds"), "kind": "REFINED_SUB_PATCHES",
                "parent_packet": str(args.parent), "parent_units_digest": parent_doc["units_digest"],
                "parameters": {"radius_m": RADIUS_M, "gap_m": GAP_M, "min_points": MIN_POINTS, "max_layers": MAX_LAYERS,
                               "pad_m": PAD_M, "source_labels": SOURCE_LABELS, "labels_backup": str(args.labels)},
                "parents": per_parent, "skipped_parents_too_few_points": skipped, "gdb": str(gdb),
                "frame": frame, "units": units, "units_digest": tr.units_digest(units)}
    (args.out/"packet.json").write_text(json.dumps(document, indent=1), encoding="utf-8")
    (args.out/"patch_stats.json").write_text(json.dumps({"schema": "canopy-patch-stats/1", "las": stats["las"],
                                                         "packet_units_digest": document["units_digest"],
                                                         "ground": "parent GROUND_Z", "units": unit_stats}, indent=1),
                                             encoding="utf-8")
    sizes = {}
    for p in per_parent.values():
        sizes[len(p["sub_units"])] = sizes.get(len(p["sub_units"]), 0)+1
    print(f"{len(parents)} MIXED/UNSURE parents -> {len(units)} sub-units in {args.out}; layers per parent {dict(sorted(sizes.items()))}; "
          f"skipped (too few points in 0.5 m): {len(skipped)}")


if __name__ == "__main__":
    main()
