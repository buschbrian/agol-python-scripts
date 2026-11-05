"""Treetop review evidence citywide with the rebuilt canopy.treetop_evidence (October 22, 2026).

    python reviews/2026-10-22/treetop-evidence/run_evidence.py reproduce NEW_FOLDER [--workers 4]
    python reviews/2026-10-22/treetop-evidence/run_evidence.py rebuilt NEW_FOLDER [--workers 4]

Myria3D environment's Python (numpy, scipy; PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT set). Read-only on every input; writes a
NEW folder. Brian asked on October 22 to rebuild the October 15 evidence from its manifest rules, the original script being
missing.

reproduce: the October 8 treetops on the October 8 working LAS, as October 15 ran, compared value for value with every tile's
stored results (runs/treetop-evidence-20261015/tiles/<tile>.npz). This is the proof that the rebuilt module is the October 15
method.
rebuilt: the 527,140 treetops of the rebuilt count (city-count-20261022) on the combined classification (canopy-rebuild
classes/<tile>.npy: consensus buildings, rules-v2 ground and the rest), the other point attributes from the working LAS.

Each tile reads its own points and, from every neighbouring tile, the points within 5 m of the shared edges (the October 15
"strips": a tile's own points within the halo of its edge, written once and read by its neighbours). Treetops belong to the
tile whose 1 km box holds them. Writes treetop-evidence.csv (October 15's columns and decimals), manifest.json with the
summary and per-tile flags, and for reproduce the comparison.
"""
import argparse
import csv
import datetime
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
from canopy import las_records, treetop_evidence as te  # noqa: E402
from canopy.lidar_root import lidar_root  # noqa: E402

RUNS = lidar_root()/"2023-salt-lake-valley"/"runs"
WORKING = RUNS/"city-count-20261008"/"prepared"/"points"
OCT15 = RUNS/"treetop-evidence-20261015"
SOURCES = {"reproduce": {"treetops": RUNS/"city-count-20261008"/"city-treetops.csv", "classes": None},
           "rebuilt": {"treetops": RUNS/"city-count-20261022"/"city-treetops.csv",
                       "classes": RUNS/"canopy-rebuild-20261022"/"classes"}}
DECIMALS = {"X": 2, "Y": 2, "HEIGHT_M": 4, "building_dist_m": 4, "ground_z": 3, "roof_hag_m": 3, "above_roof_m": 4,
            "top_hag_m": 3, "top_nonlast": 4, "top_thickness": 4, "top_normal_z": 4, "top_linearity": 4,
            "top_planarity": 4, "ctx_linearity": 4, "ctx_axis_z": 4, "ctx_extent_z": 2}


def box(tile):
    e, n = 400000+int(tile[5:7])*1000, 4500000+int(tile[7:9])*1000
    return e, n, e+1000, n+1000


def tile_points(tile, classes_dir):
    block, scale, offset, modern, _ = las_records.records(WORKING/f"{tile}.las")
    xyz = np.column_stack([np.asarray(block[a])*scale[i]+offset[i] for i, a in enumerate("xyz")])
    if classes_dir is None:
        cls = np.asarray(block["classification"] if modern else block["classification"] & 31)
    else:
        cls = np.load(Path(classes_dir)/f"{tile}.npy")
        if len(cls) != len(xyz):
            raise ValueError(f"{tile}: combined classes do not match the working LAS")
    ret = np.asarray(block["returns"])
    number = ret & (15 if modern else 7)
    count = (ret >> 4) if modern else ((ret >> 3) & 7)
    return xyz, cls.astype(np.uint8), number.astype(np.uint8), count.astype(np.uint8)


def write_strip(args):
    tile, classes_dir, folder = args
    xyz, cls, number, count = tile_points(tile, classes_dir)
    x0, y0, x1, y1 = box(tile)
    h = te.HALO_M
    near = (xyz[:, 0] < x0+h) | (xyz[:, 0] >= x1-h) | (xyz[:, 1] < y0+h) | (xyz[:, 1] >= y1-h)
    np.savez(Path(folder)/f"{tile}.npz", x=xyz[near, 0], y=xyz[near, 1], z=xyz[near, 2], cls=cls[near],
             number=number[near], count=count[near])
    return tile, int(near.sum())


def run_tile(args):
    tile, tiles, classes_dir, strips, tops = args
    t0 = time.time()
    xyz, cls, number, count = tile_points(tile, classes_dir)
    x0, y0, x1, y1 = box(tile)
    neighbours = [t for t in tiles if t != tile and abs(int(t[5:7])-int(tile[5:7])) <= 1 and abs(int(t[7:9])-int(tile[7:9])) <= 1]
    parts = [np.load(Path(strips)/f"{t}.npz") for t in neighbours]
    xyz = np.vstack([xyz]+[np.c_[p["x"], p["y"], p["z"]] for p in parts])
    cls = np.concatenate([cls]+[p["cls"] for p in parts])
    number = np.concatenate([number]+[p["number"] for p in parts])
    count = np.concatenate([count]+[p["count"] for p in parts])
    m = te.measure(np.asarray(tops, float)[:, :3], xyz, cls, number, count)
    f = te.flags(m)
    return tile, m, f, {"treetops": len(tops), "points": int(len(xyz)), "neighbours": neighbours,
                        "seconds": round(time.time()-t0, 1)}


def fmt(value, column):
    if isinstance(value, (bool, np.bool_)):
        return int(value)
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    if column in DECIMALS:
        return round(float(value), DECIMALS[column])
    return int(value) if float(value).is_integer() else value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=sorted(SOURCES))
    parser.add_argument("out", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)
    if args.out.exists():
        raise FileExistsError(args.out)
    src = SOURCES[args.mode]
    tiles = sorted(p.stem for p in WORKING.glob("*.las"))
    rows = list(csv.DictReader(open(src["treetops"], encoding="utf-8", newline="")))
    by_tile = {t: [] for t in tiles}
    unassigned = []
    for r in rows:
        x, y = float(r["X"]), float(r["Y"])
        tile = next((t for t in tiles if box(t)[0] <= x < box(t)[2] and box(t)[1] <= y < box(t)[3]), None)
        (by_tile[tile] if tile else unassigned).append((x, y, float(r["HEIGHT_M"]), r["TREE_ID"]))
    if unassigned:
        raise ValueError(f"{len(unassigned)} treetops fall in no tile")
    args.out.mkdir(parents=True)
    strips = args.out/"strips"
    strips.mkdir()
    manifest = {"status": "running", "mode": args.mode, "rules_version": te.RULES_VERSION, "rules": te.RULES,
                "halo_m": te.HALO_M, "started": datetime.datetime.now().isoformat(timespec="seconds"),
                "treetops_csv": str(src["treetops"]), "points": str(WORKING), "classes": str(src["classes"]),
                "evidence_status": "UNVALIDATED_REVIEW_EVIDENCE", "definitions": te.__doc__, "per_tile": {}}
    path = args.out/"manifest.json"

    def save():
        path.write_text(json.dumps(manifest, indent=1, default=str), encoding="utf-8")

    save()
    try:
        with ProcessPoolExecutor(args.workers) as pool:
            for tile, n in pool.map(write_strip, [(t, src["classes"], strips) for t in tiles]):
                pass
            print(f"strips written for {len(tiles)} tiles", flush=True)
            jobs = [(t, tiles, src["classes"], strips, [p[:3] for p in by_tile[t]]) for t in tiles if by_tile[t]]
            results = {}
            for tile, m, f, info in pool.map(run_tile, jobs):
                results[tile] = (m, f)
                manifest["per_tile"][tile] = {**info, "flags": {k: int(v.sum()) for k, v in f.items()}}
                save()
                print(f"{datetime.datetime.now():%H:%M:%S} {tile}: {info['treetops']} treetops, {info['seconds']} s", flush=True)
        columns = ["TREE_ID", "TILE", "X", "Y", "HEIGHT_M", *te.COLUMNS, *te.FLAGS]
        summary = {"treetops": 0, "flags": {k: 0 for k in te.FLAGS}}
        with open(args.out/"treetop-evidence.csv", "w", encoding="utf-8", newline="") as handle:
            w = csv.writer(handle)                      # csv's default \r\n, as the October 15 file
            w.writerow(columns)
            for tile in tiles:
                if tile not in results:
                    continue
                m, f = results[tile]
                for i, (x, y, h, tree_id) in enumerate(by_tile[tile]):
                    values = {"X": x, "Y": y, "HEIGHT_M": h, **{c: m[c][i] for c in te.COLUMNS}, **{k: f[k][i] for k in te.FLAGS}}
                    w.writerow([tree_id, tile]+[fmt(values[c], c) for c in columns[2:]])
                    summary["treetops"] += 1
                for k in te.FLAGS:
                    summary["flags"][k] += int(f[k].sum())
        manifest["summary"] = summary
        if args.mode == "reproduce":
            check = {"tiles": 0, "treetops": 0, "column_mismatches": {c: 0 for c in te.COLUMNS},
                     "flag_mismatches": {k: 0 for k in te.FLAGS}}
            for tile, (m, f) in results.items():
                ref = np.load(OCT15/"tiles"/f"{tile}.npz")
                if list(ref["TREE_ID"]) != [p[3] for p in by_tile[tile]]:
                    raise ValueError(f"{tile}: treetop order differs from October 15")
                check["tiles"] += 1
                check["treetops"] += len(by_tile[tile])
                for c in te.COLUMNS:
                    a, b = np.asarray(m[c], float), np.asarray(ref[c], float)
                    check["column_mismatches"][c] += int(((np.isfinite(a) != np.isfinite(b)) |
                                                          (np.isfinite(a) & np.isfinite(b) & (np.abs(a-b) > 1e-6))).sum())
                for k in te.FLAGS:
                    check["flag_mismatches"][k] += int((f[k] != ref[k]).sum())
            check["exact"] = not any(check["column_mismatches"].values()) and not any(check["flag_mismatches"].values())
            manifest["reproduces_october15"] = check
        manifest.update(status="complete", finished=datetime.datetime.now().isoformat(timespec="seconds"))
        save()
        print(json.dumps({k: manifest[k] for k in ("summary", "reproduces_october15") if k in manifest}, indent=1), flush=True)
    except BaseException as exc:
        manifest.update(status="failed", error=repr(exc))
        save()
        raise


if __name__ == "__main__":
    main()
