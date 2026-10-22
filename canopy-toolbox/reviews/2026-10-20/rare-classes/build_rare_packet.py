"""Build a review packet aimed at the classes FRACTAL still misses: vehicles, wires, poles, fences and other structures.

    python reviews/2026-10-20/rare-classes/build_rare_packet.py [NEW_PACKET_DIR] [--per-queue 80] [--dry-run]

Run with ArcGIS Pro Python (PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT set). Read-only on every input; writes a NEW packet folder
(default packet-20261020-rare beside the original) holding packet.json, patch_stats.json and training_review.gdb, the layout the
label page, restore, the training export and make_training_las.py use. --dry-run prints the candidate counts and writes nothing.

Why: fine-tune run-1 (fractal-finetune/README.md) left ground, vegetation and buildings at or near the ceiling, and nearly all
remaining misses were vehicles and wires (FRACTAL "other", 1) and poles and structures (FRACTAL "permanent structure", 64),
the classes with the fewest labels. These units put more of them in front of the reviewer.

Where the candidates come from (12TVL2804 only, the training tile; same evaluation frame as the original packet):
- R1 other, low: points the released FRACTAL calls 1 in all three passes, 0.3 to 3 m above ground (vehicles, bins, equipment);
- R2 other, high: the same above 3 m (wires, cables, high clutter);
- R3 structure: unanimous 64 (poles, fences, walls, sheds, play equipment);
- R4 models disagree: the released and the fine-tuned consensus differ and one of them says 1, 17 or 64.
Candidate points are grouped into 1 m-cell connected clusters; one unit per cluster, centred on the cluster point nearest the
cluster's median (a long cluster, such as a fence line, gets up to three, at least 5 m apart), a 0.5 m cylinder whose height slab is the candidate points' range there plus 10 cm (never lower than 20 cm
above ground). Only clean returns count (not withheld, synthetic or overlap, as everywhere else). Clusters under 6 points,
patches holding fewer than 4 candidate points, patches the frame refuses, and patches within reach of any existing unit of either
earlier packet are dropped; then up to --per-queue clusters per queue are drawn at random (fixed seed).

Blind as before: units carry no model field, and the four queues are interleaved and share the R- prefix, so the page cannot
show which queue (and so which model class) put a unit there. Model choice of *where* to look is fine for training labels; these
units are never an accuracy sample.
"""
import argparse
import datetime
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
from canopy import training_review as tr  # noqa: E402
from canopy.lidar_root import lidar_root, live  # noqa: E402

LIDAR = lidar_root()/"2023-salt-lake-valley"
REVIEW = LIDAR/"runs"/"pilot-2026-09-29"/"training-review"
ORIGINAL = REVIEW/"packet-20260929"
EARLIER = (ORIGINAL, REVIEW/"packet-20261020-refined")
RELEASED = LIDAR/"fractal"/"city-20261019"/"fractal"/"12TVL2804"/"consensus.las"
FINETUNED = LIDAR/"fractal"/"finetune-20261020"/"run-1"/"predict-12TVL2804"/"consensus.las"
RADIUS_M = 0.5
CELL_M = 1.0
GROUND_CELL_M = 2.0
MIN_POINTS = 6                   # candidate points in a cluster
MIN_PATCH_CANDIDATES = 4         # candidate points inside the 0.5 m patch itself
PAD_M = 0.1
MIN_HAG_M = 0.2
LOW_HIGH_SPLIT_M = 3.0
MAX_PER_CLUSTER = 3
POINTS_PER_UNIT = 300
SPACING_M = 5.0
SEED = 20261020
QUEUES = {"R1_OTHER_LOW": "released FRACTAL unanimous 1 (other), 0.3 to 3 m above ground",
          "R2_OTHER_HIGH": "released FRACTAL unanimous 1 (other), above 3 m",
          "R3_STRUCTURE": "released FRACTAL unanimous 64 (permanent structure)",
          "R4_MODELS_DISAGREE": "released and fine-tuned consensus differ, one of them 1, 17 or 64"}


def read_candidates(chunk_size=2_000_000):
    """Candidate points per queue and a 2 m ground grid (lowest FRACTAL ground point per cell), read in chunks."""
    import laspy
    picks = {q: [] for q in QUEUES}
    ground = {}
    start = 0
    with laspy.open(RELEASED) as ra, laspy.open(FINETUNED) as rb:
        if ra.header.point_count != rb.header.point_count:
            raise ValueError("The two consensus files hold different point counts")
        for a, b in zip(ra.chunk_iterator(chunk_size), rb.chunk_iterator(chunk_size)):
            x, y, z = np.asarray(a.x), np.asarray(a.y), np.asarray(a.z)
            if not (np.allclose(x, np.asarray(b.x)) and np.allclose(y, np.asarray(b.y))):
                raise ValueError("The two consensus files are not in the same point order")
            ca, cb = np.asarray(a["MajorityClassification"]), np.asarray(b["MajorityClassification"])
            # Only clean returns, the points the page, patch_stats and the training export count (las_records.clean_flags).
            clean = ~(np.asarray(a.withheld, bool) | np.asarray(a.synthetic, bool) | np.asarray(a.overlap, bool))
            unanimous = (np.asarray(a["RepeatAgreement"]) >= 0.999) & clean
            g = ca == 2
            keys = (np.floor(x[g]/GROUND_CELL_M).astype(np.int64)*1_000_000+np.floor(y[g]/GROUND_CELL_M).astype(np.int64))
            order = np.lexsort((z[g], keys))
            k, first = np.unique(keys[order], return_index=True)
            for key, zz in zip(k.tolist(), z[g][order][first].tolist()):
                ground[key] = min(ground.get(key, zz), zz)
            index = np.arange(start, start+len(x))
            rare = (1, 17, 64)
            masks = {"OTHER": unanimous & (ca == 1), "R3_STRUCTURE": unanimous & (ca == 64),
                     "R4_MODELS_DISAGREE": clean & (ca != cb) & (np.isin(ca, rare) | np.isin(cb, rare))}
            for name, m in masks.items():
                picks.setdefault(name, []).append(np.c_[index[m], x[m], y[m], z[m]])
            start += len(x)
    other = np.concatenate(picks.pop("OTHER"))
    out = {q: np.concatenate(v) if v else np.empty((0, 4)) for q, v in picks.items() if v}
    return other, out, ground


def ground_at(ground, x, y):
    """Ground elevation under each point: the lowest ground point of its 2 m cell, else of the nearest cell within 6 m."""
    x, y = np.atleast_1d(x), np.atleast_1d(y)
    out = np.full(len(x), np.nan)
    cx, cy = np.floor(x/GROUND_CELL_M).astype(np.int64), np.floor(y/GROUND_CELL_M).astype(np.int64)
    for ring in range(4):
        todo = np.flatnonzero(np.isnan(out))
        if not len(todo):
            break
        for dx in range(-ring, ring+1):
            for dy in range(-ring, ring+1):
                if max(abs(dx), abs(dy)) != ring:
                    continue
                for i in todo:
                    if np.isnan(out[i]):
                        v = ground.get(int(cx[i]+dx)*1_000_000+int(cy[i]+dy))
                        if v is not None:
                            out[i] = v
    return out


def clusters(points):
    """Connected 1 m-cell clusters (8-neighbour) of candidate points; returns a cluster id per point."""
    from scipy import ndimage
    ix = np.floor(points[:, 1]/CELL_M).astype(np.int64)
    iy = np.floor(points[:, 2]/CELL_M).astype(np.int64)
    ix0, iy0 = ix.min(), iy.min()
    grid = np.zeros((iy.max()-iy0+1, ix.max()-ix0+1), bool)
    grid[iy-iy0, ix-ix0] = True
    labels, _ = ndimage.label(grid, structure=np.ones((3, 3), bool))
    return labels[iy-iy0, ix-ix0]


def units_for_queue(queue, points, ground, frame, taken, rng, per_queue):
    """Up to per_queue unit dicts for one queue, one per cluster, with the counts of what was dropped."""
    dropped = {"under_min_points": 0, "frame_refused": 0, "near_existing_unit": 0, "empty_slab": 0}  # empty: < 4 in patch
    if not len(points):
        return [], dropped, 0
    ids = clusters(points)
    from scipy.spatial import cKDTree
    taken_tree = cKDTree(np.array(taken)) if taken else None
    candidates = []
    for c in np.unique(ids):
        p = points[ids == c]
        if len(p) < MIN_POINTS:
            dropped["under_min_points"] += 1
            continue
        med = np.median(p[:, 1:3], axis=0)
        centres = [p[np.argmin(np.hypot(p[:, 1]-med[0], p[:, 2]-med[1]))]]
        # A long cluster (a fence line, a row of parked cars) gets more units: farthest points, at least SPACING_M apart.
        for _ in range(min(MAX_PER_CLUSTER, 1+len(p)//POINTS_PER_UNIT)-1):
            d = np.min([np.hypot(p[:, 1]-q[1], p[:, 2]-q[2]) for q in centres], axis=0)
            if d.max() < SPACING_M:
                break
            centres.append(p[np.argmax(d)])
        candidates += [(int(c), float(q[1]), float(q[2]), p) for q in centres]
    rng.shuffle(candidates)
    units = []
    for c, x, y, p in candidates:
        if len(units) >= per_queue:
            break
        if tr.patch_status([x], [y], frame, RADIUS_M)[0]:
            dropped["frame_refused"] += 1
            continue
        if taken_tree is not None and taken_tree.query([x, y], distance_upper_bound=taken_reach)[0] < np.inf:
            dropped["near_existing_unit"] += 1
            continue
        inside = p[np.hypot(p[:, 1]-x, p[:, 2]-y) <= RADIUS_M]
        g = float(ground_at(ground, [x], [y])[0])
        if np.isnan(g) or len(inside) < MIN_PATCH_CANDIDATES:
            dropped["empty_slab"] += 1
            continue
        z_low = max(float(inside[:, 3].min())-PAD_M, g+MIN_HAG_M)
        z_high = float(inside[:, 3].max())+PAD_M
        if z_high <= z_low:
            dropped["empty_slab"] += 1
            continue
        units.append({"QUEUE": queue, "X": round(x, 2), "Y": round(y, 2), "Z_LOW": round(z_low, 2), "Z_HIGH": round(z_high, 2),
                      "GROUND_Z": round(g, 2), "HAG_LOW": round(z_low-g, 2), "HAG_HIGH": round(z_high-g, 2),
                      "PATCH_R_M": RADIUS_M, "TILE": tr.TRAINING_TILE, "PRIORITY": None, "SELECTION": "RARE",
                      "CLUSTER_PTS": int(len(p)), "PATCH_PTS": None, "BASE_CLASS": None, "TREE_MODEL": None,
                      "BLDG_MODEL": None, "SHAPE_GROUP": None, "CAND_FLAG": None, "EVIDENCE": "rare-class review queue"})
        taken.append((x, y))
        taken_tree = cKDTree(np.array(taken))
    return units, dropped, len(candidates)


taken_reach = 1.0 + RADIUS_M     # an earlier unit's 1 m patch plus this 0.5 m one: no XY overlap at all


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path, nargs="?", default=ORIGINAL.with_name("packet-20261020-rare"))
    parser.add_argument("--per-queue", type=int, default=80)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.out.exists() and not args.dry_run:
        raise FileExistsError(f"Choose a new packet folder: {args.out}")
    original = json.loads((ORIGINAL/"packet.json").read_text(encoding="utf-8"))
    if original.get("schema") != tr.SCHEMA or tr.units_digest(original["units"]) != original["units_digest"]:
        raise ValueError("Not an unaltered training review packet")
    frame = tr.check_frame(original["frame"])
    taken = []
    for packet in EARLIER:
        doc = json.loads((packet/"packet.json").read_text(encoding="utf-8"))
        if doc["frame"]["digest"] != frame["digest"]:
            raise ValueError(f"{packet} uses another evaluation frame")
        taken += [(float(u["X"]), float(u["Y"])) for u in doc["units"]]
    other, picks, ground = read_candidates()
    gz = ground_at(ground, other[:, 1], other[:, 2])
    hag = other[:, 3]-gz
    picks["R1_OTHER_LOW"] = other[(hag >= 0.3) & (hag < LOW_HIGH_SPLIT_M)]
    picks["R2_OTHER_HIGH"] = other[hag >= LOW_HIGH_SPLIT_M]
    rng = np.random.default_rng(SEED)
    by_queue, report = {}, {}
    for queue in QUEUES:
        units, dropped, n_clusters = units_for_queue(queue, picks.get(queue, np.empty((0, 4))), ground, frame, taken, rng,
                                                     args.per_queue)
        by_queue[queue] = units
        report[queue] = {"candidate_points": int(len(picks.get(queue, []))), "clusters": n_clusters, "units": len(units),
                         "dropped": dropped}
    print(json.dumps(report, indent=1))
    if args.dry_run:
        return
    # Interleave the queues so the review order does not reveal which queue (and model class) chose a unit.
    units = []
    while any(by_queue.values()):
        for queue in QUEUES:
            if by_queue[queue]:
                units.append(by_queue[queue].pop(0))
    for i, u in enumerate(units, 1):
        u.update(UNIT_ID=f"R-{i:04d}", REVIEW_ORDER=i, QUEUE_ORDER=i)
        tr.assert_patch_allowed(u["X"], u["Y"], frame, u["PATCH_R_M"], what=f"{u['UNIT_ID']} rare-class patch")
    if tr.overlapping_patches(units):
        raise ValueError("New patches overlap one another")
    from canopy import las_records
    stats = json.loads((ORIGINAL/"patch_stats.json").read_text(encoding="utf-8"))
    block, scale, offset, modern, _ = las_records.records(live(stats["las"]["path"]))
    clean = las_records.clean_flags(block["flags"], modern)
    x, y, z = ((block[c][clean]*scale[i]+offset[i]) for i, c in enumerate(("x", "y", "z")))
    from scipy.spatial import cKDTree
    tree = cKDTree(np.c_[x, y])
    unit_stats = {}
    for u in units:
        idx = np.asarray(tree.query_ball_point([u["X"], u["Y"]], u["PATCH_R_M"]), dtype=np.int64)
        hz = z[idx[(z[idx] >= u["Z_LOW"]) & (z[idx] <= u["Z_HIGH"])]]-u["GROUND_Z"]
        u["PATCH_PTS"] = int(len(hz))
        unit_stats[u["UNIT_ID"]] = ({"n": int(len(hz)), "min": round(float(hz.min()), 2), "mean": round(float(hz.mean()), 3),
                                     "max": round(float(hz.max()), 2)} if len(hz) else {"n": 0, "min": None, "mean": None, "max": None})
    from canopy import training_review_arcpy as tra
    args.out.mkdir(parents=True)
    gdb = tra.create_review_gdb(args.out/"training_review.gdb", units, frame, tr.domain_mask(frame))
    document = {"schema": tr.SCHEMA, "purpose": "TRAINING labels only; never evaluation answers",
                "created": datetime.datetime.now().isoformat(timespec="seconds"), "kind": "RARE_CLASS_QUEUE",
                "parameters": {"radius_m": RADIUS_M, "cell_m": CELL_M, "ground_cell_m": GROUND_CELL_M,
                               "min_points": MIN_POINTS, "pad_m": PAD_M, "min_hag_m": MIN_HAG_M,
                               "low_high_split_m": LOW_HIGH_SPLIT_M, "per_queue": args.per_queue, "seed": SEED,
                               "released": str(RELEASED), "finetuned": str(FINETUNED)},
                "queues": QUEUES, "report": report, "earlier_packets": [str(p) for p in EARLIER], "gdb": str(gdb),
                "frame": frame, "units": units, "units_digest": tr.units_digest(units)}
    (args.out/"packet.json").write_text(json.dumps(document, indent=1), encoding="utf-8")
    (args.out/"patch_stats.json").write_text(json.dumps({"schema": "canopy-patch-stats/1", "las": stats["las"],
                                                         "packet_units_digest": document["units_digest"],
                                                         "ground": "lowest FRACTAL ground point of the 2 m cell",
                                                         "units": unit_stats}, indent=1), encoding="utf-8")
    print(f"{len(units)} units in {args.out}")


if __name__ == "__main__":
    main()
