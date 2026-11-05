"""Compare the rebuilt canopy with October 19 and October 8, and score it against Brian's labels (October 22, 2026).

    python reviews/2026-10-22/canopy-rebuild/compare_canopy.py ROOT

Run with the Myria3D environment's Python (numpy, scipy, GDAL; PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT set) after
canopy_rebuild.py. Read-only on every input; writes into ROOT:
- canopy_change.tif: per city cell, canopy of at least 2 m in October 19 and in the rebuild: 0 neither, 1 both, 2 lost,
  3 gained (255 outside the city), for review in Pro;
- treetops-canopy.csv: every October 8 treetop (city-treetops.csv) with the rebuilt CHM at its cell and why it would no
  longer stand: KEPT (CHM at least 2 m), BUILDING (a roof now occludes the cell), NO_VEGETATION (observed, no vegetation
  point left), LOWER (vegetation remains but under 2 m), UNOBSERVED; with the October 15 SUSPECT flag;
- comparison.json: the counts, including a SUSPECT cross-table, and the label check: on 12TVL2804 every labelled part of the
  three packets' latest snapshots, the share each classification (native, rules v2, combined) calls vegetation (3, 4, 5) by
  majority of the part's clean points. Treetops are not re-detected here: that waits for Brian's review.
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
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(TOOLBOX/"reviews"/"2026-10-21"/"roof-consensus"))
from canopy import las_records, training_review as tr  # noqa: E402
import canopy_rebuild as rb  # noqa: E402
import consensus_roofs as cr  # noqa: E402
import verify_roofs as vr  # noqa: E402

TREETOPS = cr.RUNS/"city-count-20261008"/"city-treetops.csv"
EVIDENCE = cr.RUNS/"treetop-evidence-20261015"/"treetop-evidence.csv"
VEG = set(rb.VEGETATION)
LABEL_GROUPS = {"TREE": "tree", "SHRUB_LOW_VEG": "shrub"}


def band(path):
    from osgeo import gdal
    gdal.UseExceptions()
    ds = gdal.Open(str(path))
    return ds, ds.GetRasterBand(1)


def compare_rasters(root, g):
    from osgeo import gdal
    old_ds, old = band(cr.OCT19/"chm_m.tif")
    new_ds, new = band(root/"chm_m.tif")
    obs_ds, obs = band(cr.OCT19/"observed.tif")
    out = gdal.GetDriverByName("GTiff").Create(str(root/"canopy_change.tif"), g["cols"], g["rows"], 1, gdal.GDT_Byte,
                                               options=["TILED=YES", "COMPRESS=DEFLATE", "BLOCKXSIZE=256", "BLOCKYSIZE=256"])
    out.SetGeoTransform(g["geotransform"])
    out.SetProjection(g["projection"])
    out.GetRasterBand(1).SetNoDataValue(255)
    counts = np.zeros(4, np.int64)
    for r0 in range(0, g["rows"], 512):
        n = min(512, g["rows"]-r0)
        a = old.ReadAsArray(0, r0, g["cols"], n)
        b = new.ReadAsArray(0, r0, g["cols"], n)
        city = obs.ReadAsArray(0, r0, g["cols"], n) != obs.GetNoDataValue()
        was, now = (a > -1e30) & (a >= 2), (b > -1e30) & (b >= 2)
        code = np.where(was & now, 1, np.where(was, 2, np.where(now, 3, 0))).astype(np.uint8)
        code[~city] = 255
        out.GetRasterBand(1).WriteArray(code, 0, r0)
        counts += np.bincount(code[city].ravel(), minlength=4)[:4]
    out.FlushCache()
    out = old_ds = new_ds = obs_ds = None
    keys = ("neither", "canopy_both", "canopy_lost", "canopy_gained")
    return {k: int(v) for k, v in zip(keys, counts)} | {"oct19_canopy_2m": int(counts[1]+counts[2]),
                                                       "rebuilt_canopy_2m": int(counts[1]+counts[3])}


def treetops(root, g):
    rows = list(csv.DictReader(open(TREETOPS, encoding="utf-8", newline="")))
    suspect = {}
    with open(EVIDENCE, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            suspect[row["TREE_ID"]] = row["SUSPECT"] == "1"
    x = np.array([float(r["X"]) for r in rows])
    y = np.array([float(r["Y"]) for r in rows])
    index = cr.cell_index(x, y, g)
    if (index < 0).any():
        raise ValueError("Treetops off the city grid")
    col, row_ = index % g["cols"], index // g["cols"]
    values = {}
    for name in ("chm_m", "observed", "vegetation_support", "building_occlusion"):
        ds, b = band(root/f"{name}.tif")
        v = np.empty(len(rows), np.float64)
        order = np.argsort(row_)
        for r0 in range(0, g["rows"], 512):
            sel = order[(row_[order] >= r0) & (row_[order] < r0+512)]
            if len(sel):
                block = b.ReadAsArray(0, r0, g["cols"], min(512, g["rows"]-r0))
                v[sel] = block[row_[sel]-r0, col[sel]]
        values[name] = v
        ds = None
    chm = np.where(values["chm_m"] > -1e30, values["chm_m"], np.nan)
    status = np.where(chm >= 2, "KEPT", np.where(values["observed"] != 1, "UNOBSERVED",
                      np.where(values["building_occlusion"] == 1, "BUILDING",
                               np.where(values["vegetation_support"] != 1, "NO_VEGETATION", "LOWER"))))
    with open(root/"treetops-canopy.csv", "w", encoding="utf-8", newline="") as handle:
        w = csv.writer(handle, lineterminator="\n")
        w.writerow(["TREE_ID", "X", "Y", "HEIGHT_M_OCT8", "CHM_REBUILT_M", "STATUS", "SUSPECT_OCT15"])
        for r, c, s in zip(rows, chm, status):
            w.writerow([r["TREE_ID"], r["X"], r["Y"], r["HEIGHT_M"], "" if np.isnan(c) else round(float(c), 3), s,
                        int(suspect.get(r["TREE_ID"], False))])
    sus = np.array([suspect.get(r["TREE_ID"], False) for r in rows])
    table = {s: {"treetops": int((status == s).sum()), "suspect": int(((status == s) & sus).sum())}
             for s in ("KEPT", "BUILDING", "NO_VEGETATION", "LOWER", "UNOBSERVED")}
    return {"treetops": len(rows), "suspect_total": int(sus.sum()), "by_status": table,
            "no_longer_standing": int((status != "KEPT").sum()),
            "share_suspect_among_lost": round(float(sus[status != "KEPT"].mean()), 4) if (status != "KEPT").any() else None,
            "share_suspect_among_kept": round(float(sus[status == "KEPT"].mean()), 4)}


def labels(root):
    from scipy.spatial import cKDTree
    native, scale, offset, modern, _ = las_records.records(cr.NATIVE/f"{vr.TILE}.las")
    refined, _, _, refined_modern, _ = las_records.records(rb.REFINED/f"{vr.TILE}.las")
    classes = {"native": cr.classes(native, modern), "rules_v2": cr.classes(refined, refined_modern),
               "combined": np.load(root/"classes"/f"{vr.TILE}.npy")}
    clean = las_records.clean_flags(np.asarray(native["flags"]), modern)
    xyz = np.column_stack([np.asarray(native[a])*scale[i]+offset[i] for i, a in enumerate("xyz")])
    keep = np.flatnonzero(clean)
    tree = cKDTree(xyz[keep, :2])
    veg = {k: np.isin(v, list(VEG)) for k, v in classes.items()}
    tally = {k: {"tree": [0, 0], "shrub": [0, 0], "other": [0, 0]} for k in classes}
    for packet, snapshot in vr.SNAPSHOTS:
        document = json.loads((vr.REVIEW/packet/"packet.json").read_text(encoding="utf-8"))
        units = {u["UNIT_ID"]: u for u in document["units"]}
        for row in tr.load_snapshot(vr.REVIEW/"snapshots"/snapshot, document):
            if not row.get("LABEL"):
                continue
            unit = {**units[row["UNIT_ID"]], **row}
            radius = float(unit.get("PATCH_R_M") or tr.PATCH_RADIUS_M)
            near = keep[np.asarray(tree.query_ball_point([float(unit["X"]), float(unit["Y"])], radius), dtype=np.int64)]
            parts = tr.answer_parts(unit, row)
            z = xyz[near, 2]
            for k, (label, z_low, z_high) in enumerate(parts):
                if label in ("WALL", "MIXED", "UNSURE"):
                    continue
                above = z > z_low if (len(parts) == 2 and k == 0) else z >= z_low
                inside = near[above & (z <= z_high)]
                if not len(inside):
                    continue
                group = LABEL_GROUPS.get(label, "other")
                for name in classes:
                    tally[name][group][0] += 1
                    tally[name][group][1] += int(veg[name][inside].mean() > 0.5)
    return {"tile": vr.TILE, "rule": "a part is vegetation when most of its clean points are class 3, 4 or 5",
            "by_classification": {k: {g: {"parts": v[0], "called_vegetation": v[1],
                                          "share": round(v[1]/max(v[0], 1), 4)} for g, v in t.items()}
                                  for k, t in tally.items()}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", type=Path)
    args = parser.parse_args(argv)
    manifest = json.loads((args.root/"manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "complete" or not manifest.get("native_reproduces_oct19_exactly"):
        raise ValueError("The rebuild is not complete or its native version did not reproduce October 19")
    g = cr.grid()
    report = {"root": str(args.root), "rasters": compare_rasters(args.root, g)}
    print(json.dumps(report["rasters"], indent=1), flush=True)
    report["treetops"] = treetops(args.root, g)
    print(json.dumps(report["treetops"], indent=1), flush=True)
    report["labels"] = labels(args.root)
    print(json.dumps(report["labels"], indent=1), flush=True)
    out = args.root/"comparison.json"
    if out.exists():
        raise FileExistsError(out)
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
