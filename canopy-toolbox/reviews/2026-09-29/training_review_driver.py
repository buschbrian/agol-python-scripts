"""TRAINING-label review packet: build, snapshot (strict validate + audit) and training exports.

Run from canopy-toolbox with ArcGIS Pro Python (PYTHONNOUSERSITE=1). See TRAINING_REVIEW.md.

    python reviews/2026-09-29/training_review_driver.py build NEW_PACKET
    python reviews/2026-09-29/training_review_driver.py status [PACKET]
    python reviews/2026-09-29/training_review_driver.py backup [--packet PACKET] [--out DIR]
    python reviews/2026-09-29/training_review_driver.py restore [--packet PACKET] [--csv FILE] [--apply] [--replace]
    python reviews/2026-09-29/training_review_driver.py snapshot PACKET NEW_SNAPSHOT
    python reviews/2026-09-29/training_review_driver.py export-pointcloud PACKET SNAPSHOT NEW_EXPORT [--prepare]
    python reviews/2026-09-29/training_review_driver.py export-imagery PACKET SNAPSHOT NEW_EXPORT --raster NAIP.tif [--chips]

Training labels never enter reference.gdb and are refused inside the evaluation exclusion frame.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[2]
sys.path.insert(0, str(TOOLBOX))

import itertools  # noqa: E402

from canopy import evaluation_design as ed  # noqa: E402
from canopy import las_records  # noqa: E402
from canopy.lidar_root import live  # noqa: E402
from canopy import training_review as tr  # noqa: E402

from canopy.lidar_root import lidar_root  # noqa: E402
PILOT = lidar_root() / "2023-salt-lake-valley" / "runs" / "pilot-2026-09-29"
DEFAULTS = {
    "reference_gdb": PILOT/"validation"/"reference.gdb",
    "plots_json": TOOLBOX/"reviews"/"2026-09-29"/"packets"/"independent-plot-census-v2"/"plots.esri.json",
    "plots_fc": TOOLBOX/"reviews"/"2026-09-29"/"packets"/"census-review-final-20260929"/"review.gdb"/"plots",
    "baseline": PILOT/"12TVL2804"/"prepared"/"points"/"12TVL2804.las",
    "lasd": PILOT/"12TVL2804"/"prepared"/"prepared.lasd",
    "tree": PILOT/"deep-learning"/"experiments-20260929"/"tree-full"/"tree"/"12TVL2804.las",
    "building": PILOT/"deep-learning"/"experiments-20260929"/"building-abs"/"building"/"12TVL2804.las",
    "shape_gate": PILOT/"training-review"/"shape-gate",
    "candidates": PILOT/"buildings"/"12TVL2804"/"review.gdb"/"candidate_flags",
    "ground": PILOT/"deep-learning"/"experiments-20260929"/"building-hag"/"reference"/"ground.tif",
}
SHAPE_GROUPS = ("wall_like", "wire", "pole")
DEFAULT_PACKET = PILOT/"training-review"/"packet-20260929"
BACKUP_DIR = TOOLBOX/"reviews"/"2026-09-29"/"packets"/"training-labels"


def sha256(path, chunk=1 << 24):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    pending = path.with_name(path.name+".pending")
    pending.write_text(json.dumps(value, indent=1, default=str), encoding="utf-8")
    os.replace(pending, path)


def below_normal():
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:  # priority is a courtesy to the GPU queue; never blocks
        pass


def evaluation_frame(args):
    from canopy import training_review_arcpy as tra
    reference = tra.read_reference_units(args.reference_gdb)
    plots = tr.plots_from_esri_json(json.loads(Path(args.plots_json).read_text(encoding="utf-8")))
    if not tr.same_plots(plots, tra.read_plots(args.plots_fc)):
        raise ValueError("plots.esri.json and the census review.gdb plots differ; resolve before building")
    return tr.exclusion_frame(reference, plots), {"reference_units": len(reference), "plots": len(plots)}


# ---------------------------------------------------------------- build

def _gather_evidence(args, frame, mask_info, shape_index, chunk=2_000_000):
    """One pass over baseline + both DL outputs: integrity (XYZ identical) and queue evidence points."""
    base, scale, offset, modern, info = las_records.records(args.baseline)
    tree = las_records.records(args.tree)[0]
    bldg = las_records.records(args.building)[0]
    if not (len(base) == len(tree) == len(bldg)):
        raise ValueError("Baseline and model outputs differ in point count")
    mask, mx0, my0, cell = mask_info
    t = frame["training_extent"]
    queues = {"Q1_TREE_ON_ROOF": [], "Q2_BLDG_BACKGROUND": [], "Q3_VEG_BACKGROUND": [], "Q4_SHAPE": []}
    shape_flag = np.zeros(len(base), np.int8)-1
    shape_flag[shape_index[:, 0]] = shape_index[:, 1]
    for start in range(0, len(base), chunk):
        b, tr_, bl = base[start:start+chunk], tree[start:start+chunk], bldg[start:start+chunk]
        for axis in "xyz":
            if not (np.array_equal(b[axis], tr_[axis]) and np.array_equal(b[axis], bl[axis])):
                raise ValueError(f"Point order/coordinates differ from the baseline near record {start}")
        x, y, z, classes, _, flagged = las_records.decode(b, scale, offset, modern)
        tc = tr_["classification"] if modern else tr_["classification"] & 31
        bc = bl["classification"] if modern else bl["classification"] & 31
        col = np.floor((x-mx0)/cell).astype(np.int64)
        row = np.floor((y-my0)/cell).astype(np.int64)
        ok = (~flagged & (col >= 0) & (row >= 0) & (col < mask.shape[1]) & (row < mask.shape[0]))
        ok[ok] &= mask[row[ok], col[ok]]
        ok &= (x >= t[0]) & (x <= t[2]) & (y >= t[1]) & (y <= t[3])
        group = shape_flag[start:start+len(b)]
        tests = {"Q1_TREE_ON_ROOF": (classes == 6) & (tc == 5),
                 "Q2_BLDG_BACKGROUND": (classes == 6) & (bc == 0),
                 "Q3_VEG_BACKGROUND": np.isin(classes, (4, 5)) & (tc == 0),
                 "Q4_SHAPE": np.isin(classes, (4, 5)) & (group >= 0)}
        for name, test in tests.items():
            keep = np.flatnonzero(ok & test)
            queues[name].append(np.column_stack([x[keep], y[keep], z[keep], classes[keep], tc[keep], bc[keep],
                                                 group[keep], keep+start]))
    del base, tree, bldg
    return {k: np.concatenate(v) if v else np.zeros((0, 8)) for k, v in queues.items()}, info


def _shape_index(folder):
    """(point index in 12TVL2804.las, group 0..2) for wall_like/wire/pole on classes 4/5, all quadrants.

    Groups are read from each run's own review codes (new_class_byte + the manifest's code meanings),
    so the result does not depend on the shape_gate module version imported now."""
    runs, rows = [], []
    for run in sorted(Path(folder).iterdir()):
        manifest = run/"shape_gate.json"
        if not manifest.is_file():
            continue
        state = json.loads(manifest.read_text(encoding="utf-8"))
        if state.get("status") != "complete" or state.get("mode") != "review":
            raise ValueError(f"Shape-gate run is not a complete review: {run}")
        audit = np.load(run/"changes"/"12TVL2804.npz")
        names = {meaning.split(":", 1)[1].split()[0]: int(code) for code, meaning in state["review_codes"].items()}
        codes = {names[g]: i for i, g in enumerate(SHAPE_GROUPS)}
        keep = np.isin(audit["new_class_byte"], list(codes)) & np.isin(audit["previous_class_byte"], (4, 5))
        group = np.array([codes[int(c)] for c in audit["new_class_byte"][keep]], dtype=np.int64)
        rows.append(np.column_stack([audit["point_index"][keep].astype(np.int64), group]))
        runs.append({"run": str(run), "gate_extent": state["gate_extent"], "peak_memory_gb": state.get("peak_memory_gb"),
                     "seconds": state["seconds"].get("total"), "selected_points": int(keep.sum())})
    if not rows:
        raise ValueError(f"No shape-gate review runs found in {folder}")
    index = np.concatenate(rows).astype(np.int64)
    _, first = np.unique(index[:, 0], return_index=True)     # quadrant edges are inclusive: dedupe
    return index[np.sort(first)], runs


def _cluster_candidates(points, origin, extra_names=("base", "tree", "building"), min_points=10):
    if not len(points):
        return []
    labels = tr.cluster(points[:, :2], cell=1.0, min_points=min_points, max_extent=15.0, origin=origin)
    extra = {"base": points[:, 3].astype(int), "tree": points[:, 4].astype(int), "building": points[:, 5].astype(int)}
    out = tr.summarize_clusters(labels, points[:, 0], points[:, 1], points[:, 2],
                                extra={k: extra[k] for k in extra_names})
    for c in out:
        c["priority"] = float(c["points"])
    return out


def _thin(candidates, spacing=tr.MIN_SPACING_M):
    kept = []
    for c in candidates:
        if all(np.hypot(c["x"]-k["x"], c["y"]-k["y"]) >= spacing for k in kept[-2000:]):
            kept.append(c)
    return kept


def _top_layer(args, candidates, chunk=2_000_000, min_points=5):
    """Top TOP_LAYER_M of returns within the patch around each (pre-thinned) candidate."""
    from scipy.spatial import cKDTree
    if not candidates:
        return []
    base, scale, offset, modern, _ = las_records.records(args.baseline)
    tree_cls = las_records.records(args.tree)[0]
    bldg_cls = las_records.records(args.building)[0]
    centres = np.array([[c["x"], c["y"]] for c in candidates])
    kd = cKDTree(centres)
    hits = []
    for start in range(0, len(base), chunk):
        b = base[start:start+chunk]
        x, y, z, classes, _, flagged = las_records.decode(b, scale, offset, modern)
        d, j = kd.query(np.column_stack([x, y]), distance_upper_bound=tr.PATCH_RADIUS_M)
        keep = np.flatnonzero(np.isfinite(d) & ~flagged & ~np.isin(classes, tr.NOISE_CODES))
        tc = tree_cls["classification"][start:start+chunk][keep]
        bc = bldg_cls["classification"][start:start+chunk][keep]
        hits.append(np.column_stack([j[keep], z[keep], classes[keep], tc, bc]))
    del base, tree_cls, bldg_cls
    hits = np.concatenate(hits)
    out = []
    for i, c in enumerate(candidates):
        mine = hits[hits[:, 0] == i]
        if len(mine) < min_points:
            continue
        top = mine[:, 1].max()
        slab = mine[mine[:, 1] >= top-tr.TOP_LAYER_M]
        majority = lambda col: int(np.bincount(slab[:, col].astype(int)).argmax())
        out.append(dict(c, z_low=float(top-tr.TOP_LAYER_M), z_high=float(top+0.5), patch_points=int(len(slab)),
                        points=int(len(mine)), base=majority(2), tree=majority(3), building=majority(4)))
    return out


def build(args):
    from canopy import training_review_arcpy as tra
    import arcpy
    started = time.perf_counter()
    below_normal()
    packet = Path(args.packet)
    if packet.exists():
        raise FileExistsError(f"{packet} exists; choose a new packet folder")
    for key in ("reference_gdb", "plots_json", "baseline", "tree", "building", "candidates", "ground", "lasd"):
        if not arcpy.Exists(str(getattr(args, key))):
            raise FileNotFoundError(f"{key}: {getattr(args, key)}")
    frame, frame_counts = evaluation_frame(args)
    ed.assert_training_extents([frame["training_extent"]])     # the 12TVL3302 holdout guard
    print("evaluation frame:", frame_counts, "digest", frame["digest"][:12], flush=True)
    mask_info = tr.domain_mask(frame)
    areas = tr.domain_areas(frame)
    print("areas:", {k: v for k, v in areas.items() if not k.startswith("full_")},
          "clear 50 m blocks:", len(areas["full_50m_blocks_clear"]), flush=True)
    sources = {k: {"path": str(getattr(args, k)), "sha256_before": sha256(getattr(args, k)),
                   "header": las_records.header(getattr(args, k))} for k in ("baseline", "tree", "building")}
    shape_index, shape_runs = _shape_index(args.shape_gate)
    evidence, info = _gather_evidence(args, frame, mask_info, shape_index)
    print("evidence points:", {k: len(v) for k, v in evidence.items()}, flush=True)
    origin = tuple(frame["training_extent"][:2])
    queues, pools = {}, {}
    describe = lambda c: f"{c['points']} disagreement points; baseline {c['base']}, tree {c['tree']}, building {c['building']}"
    for name in ("Q1_TREE_ON_ROOF", "Q2_BLDG_BACKGROUND"):
        pool = _cluster_candidates(evidence[name], origin)
        for c in pool:
            c["evidence"] = describe(c)
        pools[name] = len(pool)
        queues[name] = tr.select(pool, args.cap, name)
    # Q3: class-4 evidence outnumbers class-5 about 10:1, so the cap is split by baseline class;
    # class-5 background calls are the tree model's real disagreements with high vegetation.
    halves = []
    for code in (5, 4):
        pts = evidence["Q3_VEG_BACKGROUND"][evidence["Q3_VEG_BACKGROUND"][:, 3] == code]
        pool = _cluster_candidates(pts, origin)
        for c in pool:
            c["evidence"] = describe(c)
        pools[f"Q3_VEG_BACKGROUND:class{code}"] = len(pool)
        halves.append(tr.select(pool, int(np.ceil(args.cap/2)), f"Q3_VEG_BACKGROUND:class{code}"))
    queues["Q3_VEG_BACKGROUND"] = [c for pair in itertools.zip_longest(*halves) for c in pair if c]
    shape_lists = []
    for g, group in enumerate(SHAPE_GROUPS):
        pts = evidence["Q4_SHAPE"][evidence["Q4_SHAPE"][:, 6] == g]
        pool = _cluster_candidates(pts, origin, min_points=5)
        for c in pool:
            c["shape_group"] = group
            c["evidence"] = f"{c['points']} {group} points (shape gate review) on baseline class {c['base']}"
        pools[f"Q4_SHAPE:{group}"] = len(pool)
        shape_lists.append(tr.select(pool, int(np.ceil(args.cap/len(SHAPE_GROUPS))), f"Q4_SHAPE:{group}"))
    queues["Q4_SHAPE"] = [c for trio in itertools.zip_longest(*shape_lists) for c in trio if c]
    flags = tra.read_candidate_flags(args.candidates)
    status = tr.patch_status([f["x"] for f in flags], [f["y"] for f in flags], frame)
    flags = [dict(f, priority=float(f["height_m"] or 0)) for f, s in zip(flags, status) if not s]
    pools["Q5_ROOF_CANDIDATE"] = len(flags)
    q5 = _top_layer(args, _thin(tr.select(flags, args.cap*2, "Q5_ROOF_CANDIDATE")))
    for c in q5:
        c["evidence"] = f"treetop {c['tree_id']} height {c['height_m']:.1f} m flagged {c['flag']}"
    queues["Q5_ROOF_CANDIDATE"] = q5[:args.cap]
    randoms = [{"x": float(x), "y": float(y), "priority": 0., "selection": "RANDOM"}
               for x, y in tr.random_locations(*mask_info, n=args.cap*2)]
    pools["Q6_RANDOM"] = len(randoms)
    q6 = _top_layer(args, _thin(randoms))
    for c in q6:
        c["evidence"] = "area-uniform random location; top 2 m of returns"
    queues["Q6_RANDOM"] = q6[:args.cap]
    units, dropped = tr.assemble(queues, frame)
    ground = tra.GroundRaster(args.ground)
    for u in units:
        g = ground.sample(u["X"], u["Y"])
        u["GROUND_Z"] = None if g is None else round(g, 2)
        u["HAG_LOW"] = None if g is None else round(u["Z_LOW"]-g, 2)
        u["HAG_HIGH"] = None if g is None else round(u["Z_HIGH"]-g, 2)
    packet.mkdir(parents=True)
    gdb = tra.create_review_gdb(packet/"training_review.gdb", units, frame, mask_info)
    project = tra.build_project(packet, gdb, args.lasd, toolbox=TOOLBOX/"TrainingReview.pyt")
    for k in sources:
        sources[k]["sha256_after"] = sha256(getattr(args, k))
        if sources[k]["sha256_after"] != sources[k]["sha256_before"]:
            raise RuntimeError(f"Source {k} changed during the build")
    counts = {q: sum(1 for u in units if u["QUEUE"] == q) for q in tr.QUEUES}
    document = {
        "schema": tr.SCHEMA, "purpose": "TRAINING labels only; never evaluation answers",
        "created": datetime.datetime.now().isoformat(timespec="seconds"), "seed": tr.SEED,
        "parameters": {"cap_per_queue": args.cap, "patch_radius_m": tr.PATCH_RADIUS_M, "z_margin_m": tr.Z_MARGIN_M,
                       "top_layer_m": tr.TOP_LAYER_M, "min_spacing_m": tr.MIN_SPACING_M,
                       "eval_buffer_m": tr.EVAL_BUFFER_M, "eval_buffer_basis": {
                           "match_radius_m": tr.MATCH_RADIUS_M, "crown_extent_p99_m": tr.CROWN_EXTENT_P99_M,
                           "patch_radius_m": tr.PATCH_RADIUS_M},
                       "block_buffer_m": tr.BLOCK_BUFFER_M, "cluster": {"cell_m": 1.0, "max_extent_m": 15.0,
                                                                        "min_points": {"Q1-Q3": 10, "Q4": 5}},
                       "top_share": 0.5, "ignore_code": tr.IGNORE_CODE,
                       "labels": {k: {"meaning": v[0], "las_code": v[1], "imagery_class": tr.IMAGERY_CLASS.get(k)}
                                  for k, v in tr.LABELS.items()}},
        "queues": tr.QUEUES, "queue_counts": counts, "candidate_pools": pools, "dropped_at_assembly": dropped,
        "areas": areas, "frame_counts": frame_counts,
        "sources": {**sources, "shape_gate_runs": shape_runs, "candidates": str(args.candidates),
                    "ground": str(args.ground), "reference_gdb": str(args.reference_gdb),
                    "plots_json": str(args.plots_json), "plots_fc": str(args.plots_fc), "lasd": str(args.lasd),
                    "shape_gate_py_sha256": sha256(TOOLBOX/"canopy"/"shape_gate.py")},
        "project": project, "gdb": str(gdb), "frame": frame, "units": units, "units_digest": tr.units_digest(units),
        "seconds": round(time.perf_counter()-started, 1)}
    write_json(packet/"packet.json", document)
    print(json.dumps({k: document[k] for k in ("queue_counts", "candidate_pools", "dropped_at_assembly", "seconds")},
                     indent=1), flush=True)
    print("project:", project["project"], project["notes"])
    return document


# ---------------------------------------------------------------- snapshot and exports

def load_packet(packet):
    document = json.loads((Path(packet)/"packet.json").read_text(encoding="utf-8"))
    if document.get("schema") != tr.SCHEMA:
        raise ValueError("Not a training-review packet")
    tr.check_frame(document["frame"])
    if tr.units_digest(document["units"]) != document["units_digest"]:
        raise ValueError("packet.json units were altered")
    return document


def _recheck_frame(args, document):
    """The live evaluation frame must still equal the one the packet was built against."""
    live, _ = evaluation_frame(args)
    if live["digest"] != document["frame"]["digest"]:
        raise ValueError("Evaluation units or census plots changed since this packet was built; rebuild the packet")
    return live


def review_gdb(packet, document):
    """The review GDB beside packet.json; the path recorded in packet.json may name another machine's drive."""
    beside = Path(packet)/"training_review.gdb"
    return beside if beside.exists() else live(document["gdb"])


def status(args):
    from canopy import training_review_arcpy as tra
    document = load_packet(args.packet)
    rows = tra.read_review_rows(review_gdb(args.packet, document)/tra.UNITS_FC)
    table = {}
    for r in rows:
        entry = table.setdefault(r["QUEUE"], {"units": 0, "labelled": 0})
        entry["units"] += 1
        entry["labelled"] += bool(r["LABEL"])
    nxt = tr.next_unit(rows)
    print(json.dumps({"queues": table, "next": nxt and nxt["UNIT_ID"]}, indent=1))


def snapshot(args):
    from canopy import training_review_arcpy as tra
    document = load_packet(args.packet)
    out = Path(args.out)
    if out.exists():
        raise FileExistsError(f"{out} exists; each snapshot needs a new folder")
    _recheck_frame(args, document)
    gdb = review_gdb(args.packet, document)
    rows = tra.read_review_rows(gdb/tra.UNITS_FC)
    plan = tr.plan_snapshot(rows, document["units"], document["frame"], labels=tra.domain_codes(gdb))
    out.mkdir(parents=True)
    text = tr.snapshot_csv(plan["rows"])
    (out/"labels.csv").write_bytes(text.encode("utf-8"))
    audit = {"schema": tr.SCHEMA, "kind": "TRAINING_LABEL_SNAPSHOT",
             "created": datetime.datetime.now().isoformat(timespec="seconds"),
             "packet": str(Path(args.packet).resolve()), "packet_json_sha256": sha256(Path(args.packet)/"packet.json"),
             "gdb": document["gdb"], "frame_digest": document["frame"]["digest"],
             "packet_units_digest": document["units_digest"], "labels_csv_sha256": hashlib.sha256(text.encode()).hexdigest(),
             "counts": {k: plan[k] for k in ("units", "labelled", "blank", "exportable", "by_label")},
             "reviewers": sorted({r["REVIEWER"] for r in plan["rows"]}),
             "domain_check": "every labelled patch re-checked against the live evaluation frame"}
    write_json(out/"snapshot.json", audit)
    print(json.dumps(audit["counts"], indent=1))
    return audit


def backup(args):
    """Save every answered unit from the live review GDB into the repo working copy (labels-progress.csv).

    Lenient: nothing is refused. A row that would fail the snapshot rules is saved with the reason in CHECK and the
    command exits 3 so the problem is seen. The output is deterministic, so unchanged work makes no git diff.
    The repo copy is byte-for-byte (packets/** -text); the GDB stays the working master until you restore.
    """
    from canopy import training_review_arcpy as tra
    document = load_packet(args.packet)
    gdb = review_gdb(args.packet, document)
    rows = tra.read_review_rows(gdb/tra.UNITS_FC)
    plan = tr.plan_backup(rows, document["units"], document["frame"], labels=tra.domain_codes(gdb))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    text = tr.backup_csv(plan["rows"]).encode("utf-8")
    pending = out/"labels-progress.csv.pending"
    pending.write_bytes(text)
    os.replace(pending, out/"labels-progress.csv")
    progress = {"schema": tr.SCHEMA, "kind": "TRAINING_LABEL_BACKUP",
                "packet_units_digest": document["units_digest"], "frame_digest": document["frame"]["digest"],
                "counts": {k: plan[k] for k in ("units", "saved", "labelled", "by_label")},
                "reviewers": sorted({r["REVIEWER"] for r in plan["rows"] if r["REVIEWER"]}),
                "flagged": plan["flagged"], "problems": plan["problems"],
                "labels_csv_sha256": hashlib.sha256(text).hexdigest(),
                "note": "Working copy of TRAINING labels. Not evaluation answers; never enters reference.gdb."}
    write_json(out/"progress.json", progress)
    print(f"Saved {plan['saved']} answered units ({plan['labelled']} labelled) of {plan['units']} to {out}")
    if plan["by_label"]:
        print("By label:", ", ".join(f"{k} {v}" for k, v in sorted(plan["by_label"].items())))
    for line in plan["flagged"]+plan["problems"]:
        print("CHECK:", line)
    if plan["flagged"] or plan["problems"]:
        print("Saved anyway. Fix the units above in Pro (or restore over them) before you take a snapshot.")
        return 3
    return 0


def restore(args):
    """Put a backup CSV's labels back into the live review GDB. Preview unless --apply.

    Blank units are filled. A unit that already has the same label is left alone. A different live label is a
    conflict and is skipped unless --replace. Rows failing the snapshot checks are refused and listed; they never
    stop the valid rows. Every written unit is read back and compared.
    """
    from canopy import training_review_arcpy as tra
    document = load_packet(args.packet)
    gdb = review_gdb(args.packet, document)
    fc = gdb/tra.UNITS_FC
    backup_rows = tr.read_backup(args.csv)
    live_rows = tra.read_review_rows(fc)
    plan = tr.plan_restore(backup_rows, live_rows, document["units"], document["frame"],
                           labels=tra.domain_codes(gdb), replace=args.replace)
    summary = {"write": len(plan["write"]), "replace": len(plan["replace"]), "unchanged": len(plan["unchanged"]),
               "conflicts": len(plan["conflicts"]), "refused": len(plan["refused"])}
    print(json.dumps({"mode": "APPLY" if args.apply else "PREVIEW", **summary}, indent=1))
    for line in (plan["conflicts"]+plan["refused"])[:20]:
        print("SKIPPED:", line)
    if not args.apply:
        print("Preview only. Re-run with --apply to write these labels.")
        return 3 if plan["conflicts"] or plan["refused"] else 0
    oids = {r["UNIT_ID"]: r["OID@"] for r in live_rows}
    todo = [(w, False) for w in plan["write"]] + [(w, True) for w in plan["replace"]]
    for item, replacing in todo:
        tra.write_answer(fc, oids[item["UNIT_ID"]], item["answer"], replace=replacing)
    after = {r["UNIT_ID"]: r for r in tra.read_review_rows(fc)}
    wrong = [item["UNIT_ID"] for item, _ in todo if after[item["UNIT_ID"]]["LABEL"] != item["answer"]["LABEL"]]
    if wrong:
        raise RuntimeError(f"Read-back mismatch after restore for {wrong[:5]}")
    print(f"Restored {len(todo)} units and read them back.")
    return 3 if plan["conflicts"] or plan["refused"] else 0


def export_pointcloud(args):
    from canopy import training_review_arcpy as tra
    document = load_packet(args.packet)
    _recheck_frame(args, document)
    rows = tr.load_snapshot(args.snapshot, document)
    exported = [r for r in rows if r["LABEL"] in tr.EXPORT_LABELS]
    if not exported:
        raise ValueError("The snapshot has no exportable training labels")
    out = Path(args.out)
    if out.exists():
        raise FileExistsError(f"{out} exists")
    source = live(args.source or document["sources"]["baseline"]["path"])
    before = sha256(source)
    out.mkdir(parents=True)
    las = out/"points"/f"{source.stem}_training.las"
    counts = tr.export_training_las(source, las, rows, document["frame"])
    integrity = tr.verify_only_classes_changed(source, las)
    split, squares = tr.point_split(exported)
    gdb = Path(args.out)/"boundaries.gdb"
    import arcpy
    arcpy.management.CreateFileGDB(str(out), gdb.name)
    boundaries = tra.write_boundaries(gdb, squares)
    lasd = tra.las_dataset(las, out/"training.lasd")
    parameters = tr.prepare_parameters(lasd, boundaries["TRAINING"], boundaries["VALIDATION"])
    manifest = {"schema": tr.SCHEMA, "kind": "POINT_CLOUD_TRAINING_EXPORT", "snapshot": str(Path(args.snapshot).resolve()),
                "source": str(source), "source_sha256_before": before, "training_las": str(las), "counts": counts,
                "integrity": integrity, "split": split, "prepare_parameters": parameters}
    if args.prepare:
        manifest["prepare_messages"] = tra.prepare_point_cloud(lasd, out/"training.pctd", boundaries["TRAINING"],
                                                               boundaries["VALIDATION"])
    manifest["source_sha256_after"] = sha256(source)
    if manifest["source_sha256_after"] != before:
        raise RuntimeError("Source LAS changed during export")
    write_json(out/"export.json", manifest)
    print(json.dumps({k: manifest[k] for k in ("counts", "integrity")}, indent=1, default=str))


def export_imagery(args):
    from canopy import training_review_arcpy as tra
    import arcpy
    document = load_packet(args.packet)
    _recheck_frame(args, document)
    rows = tr.load_snapshot(args.snapshot, document)
    out = Path(args.out)
    if out.exists():
        raise FileExistsError(f"{out} exists")
    out.mkdir(parents=True)
    arcpy.management.CreateFileGDB(str(out), "imagery.gdb")
    fc, n = tra.imagery_patches(out/"imagery.gdb", rows, args.raster)
    manifest = {"schema": tr.SCHEMA, "kind": "IMAGERY_TRAINING_EXPORT", "snapshot": str(Path(args.snapshot).resolve()),
                "raster": str(args.raster), "raster_sha256": sha256(args.raster), "polygons": fc, "patches": n,
                "class_values": tr.IMAGERY_CLASS, "unlabelled_value": 0,
                "tool": "Export Training Data For Deep Learning, metadata Classified Tiles, class_value_field CLASSVALUE",
                "licensing": {"NAIP": "USGS NAIP four-band imagery (public domain); the intended training raster",
                              "Esri World Imagery": ("NOT exported. Its terms may restrict use as machine-learning "
                                                     "training data; the user must decide before any such use."),
                              "date_note": "NAIP 2021 vs lidar 2023 (November): changes and season differ"}}
    if args.chips:
        manifest["chip_messages"] = tra.export_imagery_chips(args.raster, fc, out/"chips")
    write_json(out/"export.json", manifest)
    print(json.dumps({k: manifest[k] for k in ("patches", "class_values")}, indent=1))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for key, value in DEFAULTS.items():
        parser.add_argument("--"+key.replace("_", "-"), dest=key, default=value, type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build"); b.add_argument("packet"); b.add_argument("--cap", type=int, default=200)
    s = sub.add_parser("status"); s.add_argument("packet", nargs="?", default=DEFAULT_PACKET, type=Path)
    k = sub.add_parser("backup"); k.add_argument("--packet", default=DEFAULT_PACKET, type=Path)
    k.add_argument("--out", default=BACKUP_DIR, type=Path)
    r = sub.add_parser("restore"); r.add_argument("--packet", default=DEFAULT_PACKET, type=Path)
    r.add_argument("--csv", default=BACKUP_DIR/"labels-progress.csv", type=Path)
    r.add_argument("--apply", action="store_true"); r.add_argument("--replace", action="store_true")
    s = sub.add_parser("snapshot"); s.add_argument("packet"); s.add_argument("out")
    p = sub.add_parser("export-pointcloud"); p.add_argument("packet"); p.add_argument("snapshot"); p.add_argument("out")
    p.add_argument("--source", type=Path); p.add_argument("--prepare", action="store_true")
    i = sub.add_parser("export-imagery"); i.add_argument("packet"); i.add_argument("snapshot"); i.add_argument("out")
    i.add_argument("--raster", type=Path, required=True); i.add_argument("--chips", action="store_true")
    args = parser.parse_args(argv)
    result = {"build": build, "status": status, "snapshot": snapshot, "backup": backup, "restore": restore,
              "export-pointcloud": export_pointcloud, "export-imagery": export_imagery}[args.command](args)
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    sys.exit(main())
