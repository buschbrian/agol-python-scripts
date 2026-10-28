r"""Score roofer's LoD1.2 and LoD2.2 on a tile against the consensus lidar roof, beside Esri's LOD1.2 and LOD2.0 (October 24, 2026).

    python reviews/2026-10-23/lod2-check/score_roofer.py score ROOFER_DIR CHECK_DIR OUT
    python reviews/2026-10-23/lod2-check/score_roofer.py figures OUT FP_ID ...

ArcGIS Pro Python or the deep-learning clone (arcpy, numpy, Pillow, matplotlib; PYTHONNOUSERSITE=1). Read-only on both inputs.
- ROOFER_DIR: the folder roofer_input.py and the roofer run wrote (output\*.city.jsonl; the tile is read from roofer-input.json).
- CHECK_DIR: the citywide check of the filled massing (lod2-check-filled-20261023): the roof, footprint and Esri rasters on
  the 0.5 m grid, and the per-building roof type.
- Roofer's roof faces (RoofSurface of each BuildingPart's solid) are rasterized on the same grid: each face's plane is fitted
  through its outline, filled where the cell centre lies inside the outline (holes cut out), highest value per cell. That is
  Multipatch To Raster's rule for Esri's blocks too, except that ArcGIS samples at the cell centre exactly and Pillow's fill
  can differ on a cell whose centre lies on an edge.
- Per building the rules are lod2_check.py's: the same compared cells, _level statistics and _verdict, with Esri's LOD1.2 as
  the flat baseline for both Esri LOD2.0 and roofer LoD2.2. Roofer's own LoD1.2 is scored as a second flat model.
"""
import argparse
import csv
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve()
spec = importlib.util.spec_from_file_location("lod2_check", HERE.parent/"lod2_check.py")
lc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lc)
CELL = lc.CELL
MODELS = ("E12", "E20", "R12", "R22")
LABEL = {"E12": "Esri LOD1.2", "E20": "Esri LOD2.0", "R12": "roofer LoD1.2", "R22": "roofer LoD2.2"}


def roofer_rasters(jsonl, window, rows, cols):
    """Roof elevation (max per cell, nan = none) of each roofer LoD, plus the per-building attributes."""
    from PIL import Image, ImageDraw
    x0, y0 = window
    ytop = y0+rows*CELL
    out = {"1.2": np.full((rows, cols), np.nan, np.float32), "2.2": np.full((rows, cols), np.nan, np.float32)}
    attrs = {}
    lines = Path(jsonl).read_text(encoding="utf-8").splitlines()
    head = json.loads(lines[0])
    scale, translate = head["transform"]["scale"], head["transform"]["translate"]
    for line in lines[1:]:
        feature = json.loads(line)
        v = np.array(feature["vertices"], float)*scale+translate
        for key, o in feature["CityObjects"].items():
            if o["type"] == "Building":
                attrs[int(o["attributes"]["FP_ID"])] = o["attributes"]
            if o["type"] != "BuildingPart":
                continue
            for g in o["geometry"]:
                lod = g["lod"]
                if lod not in out or g["type"] != "Solid":
                    continue
                roof = {i for i, s in enumerate(g["semantics"]["surfaces"]) if s["type"] == "RoofSurface"}
                for shell, labels in zip(g["boundaries"], g["semantics"]["values"]):
                    for face, label in zip(shell, labels):
                        if label not in roof:
                            continue
                        ring = v[face[0]]
                        if len(ring) < 3:
                            continue
                        centre = ring[:, :2].mean(0)
                        A = np.c_[ring[:, 0]-centre[0], ring[:, 1]-centre[1], np.ones(len(ring))]
                        coef, *_ = np.linalg.lstsq(A, ring[:, 2], rcond=None)
                        px = (ring[:, 0]-x0)/CELL-0.5
                        py = (ytop-ring[:, 1])/CELL-0.5
                        ix0, ix1 = int(np.floor(px.min())), int(np.ceil(px.max()))
                        iy0, iy1 = int(np.floor(py.min())), int(np.ceil(py.max()))
                        if ix1 < 0 or iy1 < 0 or ix0 >= cols or iy0 >= rows:
                            continue
                        w, h = ix1-ix0+1, iy1-iy0+1
                        img = Image.new("L", (w, h), 0)
                        draw = ImageDraw.Draw(img)
                        draw.polygon([(a-ix0, b-iy0) for a, b in zip(px, py)], fill=1)
                        for hole in face[1:]:
                            hr = v[hole]
                            draw.polygon([((hx-x0)/CELL-0.5-ix0, (ytop-hy)/CELL-0.5-iy0) for hx, hy in hr[:, :2]], fill=0)
                        mask = np.asarray(img, bool)
                        jj, ii = np.nonzero(mask)
                        cx = x0+(ii+ix0+0.5)*CELL-centre[0]
                        cy = ytop-(jj+iy0+0.5)*CELL-centre[1]
                        z = (coef[0]*cx+coef[1]*cy+coef[2]).astype(np.float32)
                        r, c = jj+iy0, ii+ix0
                        keep = (r >= 0) & (r < rows) & (c >= 0) & (c < cols)
                        out[lod][r[keep], c[keep]] = np.fmax(out[lod][r[keep], c[keep]], z[keep])
    return out, attrs


def score(roofer_dir, check_dir, out, r22_raster=None):
    import arcpy
    roofer_dir, check_dir, out = Path(roofer_dir), Path(check_dir), Path(out)
    out.mkdir(parents=True, exist_ok=False)
    info = json.loads((roofer_dir/"input"/"roofer-input.json").read_text(encoding="utf-8"))
    window = (428000.0, 4504000.0)
    rows = cols = 2000
    like = (window, (rows, cols))
    fp, _ = lc._grid(check_dir/"fp_id.tif", like)
    fp = fp.astype(np.int64)
    roof, _ = lc._grid(lc.ROOF, like)
    z = {"E12": lc._grid(check_dir/"lod12_z.tif", like)[0], "E20": lc._grid(check_dir/"lod20_z.tif", like)[0]}
    jsonl = next((roofer_dir/"output").glob("*.city.jsonl"))
    rz, attrs = roofer_rasters(jsonl, window, rows, cols)
    z["R12"], z["R22"] = rz["1.2"], rz["2.2"]
    if r22_raster:      # roofer's LoD2.2 as ArcGIS rasterized the imported multipatches (roofer_to_multipatch.py)
        z["R22"] = lc._grid(Path(r22_raster), like)[0]
    ids = sorted(attrs)
    ground = {fid: g for fid, g in arcpy.da.SearchCursor(str(lc.MASSING/"footprints"), ["FP_ID", "GROUND_Z50_M"])}
    checked = {int(r["FP_ID"]): r for r in csv.DictReader(open(check_dir/"lod2-check.csv", encoding="utf-8"))}
    for m in MODELS:
        np.save(out/f"{m}_z.npy", z[m])
    rows_out = []
    for fid in ids:
        mine = fp == fid
        sel = mine & ~np.isnan(roof)
        n = int(sel.sum())
        row = {"FP_ID": fid, "ROOF_TYPE": checked[fid]["ROOF_TYPE"], "ROOF_COV_PCT": checked[fid]["ROOF_COV_PCT"],
               "FOOTPRINT_M2": checked[fid]["FOOTPRINT_M2"], "COMPARED_CELLS": n,
               "RF_EXTRUSION": attrs[fid].get("rf_extrusion_mode"), "RF_ROOF_TYPE": attrs[fid].get("rf_roof_type"),
               "RF_ROOF_PLANES": attrs[fid].get("rf_roof_planes"), "RF_RMSE_LOD22": attrs[fid].get("rf_rmse_lod22"),
               "RF_PT_DENSITY": attrs[fid].get("rf_pt_density"), "RF_PC_UNUSABLE": attrs[fid].get("rf_pointcloud_unusable")}
        if n < lc.MIN_CELLS:
            row.update({"VERDICT_E20": "too-few", "VERDICT_R22": "too-few"})
            rows_out.append(row)
            continue
        r = roof[sel]
        stats = {}
        for m in MODELS:
            e = z[m][sel]-r
            top = float(np.nanmax(z[m][mine])) if np.isfinite(z[m][mine]).any() else None
            stats[m] = lc._level(e, r, ground.get(fid), top)
            for k, v in stats[m].items():
                row[f"{m}_{k.upper()}"] = v
        row["VERDICT_E20"], row["NOTE_E20"] = lc._verdict(n, stats["E12"], stats["E20"])
        row["VERDICT_R22"], row["NOTE_R22"] = lc._verdict(n, stats["E12"], stats["R22"])
        if stats["R22"]["cells"] == 0:
            row["VERDICT_R22"], row["NOTE_R22"] = "no-model", "NO_ROOFER_GEOMETRY"
        row["VERDICT_R22_VS_R12"], row["NOTE_R22_VS_R12"] = ("no-model", "") if stats["R22"]["cells"] == 0 else             lc._verdict(n, stats["R12"], stats["R22"])
        rows_out.append(row)
    names = list(dict.fromkeys(k for row in rows_out for k in row))
    with open(out/"roofer-check.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, names)
        w.writeheader()
        for row in rows_out:
            w.writerow({k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items()})
    summary = summarize(rows_out)
    summary["input"] = info
    (out/"roofer-check.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "input"}, indent=1))


def summarize(rows):
    judged = [r for r in rows if r.get("VERDICT_E20") != "too-few"]
    out = {"buildings": len(rows), "judged": len(judged), "pooled": {}, "median": {}, "verdicts": {}, "by_type": {}}
    for m in MODELS:
        have = [r for r in judged if r[f"{m}_CELLS"] > 0]       # buildings the model covers at all
        cells = sum(r[f"{m}_CELLS"] for r in have)
        out["pooled"][m] = {"within_05_pct": round(sum(r[f"{m}_WITHIN_05_PCT"]*r[f"{m}_CELLS"] for r in have)/cells, 2),
                            "within_1_pct": round(sum(r[f"{m}_WITHIN_1_PCT"]*r[f"{m}_CELLS"] for r in have)/cells, 2),
                            "cells": int(cells), "buildings_with_model": len(have)}
        out["median"][m] = {k: round(float(np.median([r[f"{m}_{k}"] for r in have])), 3)
                            for k in ("ABS_P50_M", "ABS_P95_M", "WITHIN_05_PCT", "WITHIN_1_PCT")}
    for key in ("VERDICT_E20", "VERDICT_R22", "VERDICT_R22_VS_R12"):
        out["verdicts"][key] = {v: sum(1 for r in rows if r.get(key) == v) for v in
                                ("better", "same", "worse", "broken", "too-few", "no-model")}
    for t in sorted({r["ROOF_TYPE"] for r in judged}):
        part = [r for r in judged if r["ROOF_TYPE"] == t and r["VERDICT_R22"] != "no-model"]
        out["by_type"][t] = {"buildings": len(part),
                             **{m: {"p95_median": round(float(np.median([r[f"{m}_ABS_P95_M"] for r in part])), 2),
                                    "within_1_pct_median": round(float(np.median([r[f"{m}_WITHIN_1_PCT"] for r in part])), 1)}
                                for m in ("E20", "R22")},
                             "E20": {v: sum(1 for r in part if r["VERDICT_E20"] == v) for v in ("better", "same", "worse", "broken")},
                             "R22": {v: sum(1 for r in part if r["VERDICT_R22"] == v) for v in ("better", "same", "worse", "broken")}}
    out["by_type_note"] = "buildings roofer built nothing for are left out of by_type"
    out["roofer_extrusion"] = {k: sum(1 for r in rows if r["RF_EXTRUSION"] == k) for k in {r["RF_EXTRUSION"] for r in rows}}
    both = [r for r in judged]
    out["agree_better_or_same"] = sum(1 for r in both if (r["VERDICT_E20"] in ("better", "same")) and r["VERDICT_R22"] in ("better", "same"))
    return out


def figures(out, fp_ids):
    import arcpy
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out = Path(out)
    folder = out/"figures"
    folder.mkdir(exist_ok=True)
    rows = {int(r["FP_ID"]): r for r in csv.DictReader(open(out/"roofer-check.csv", encoding="utf-8"))}
    like = ((428000.0, 4504000.0), (2000, 2000))
    z = {m: np.load(out/f"{m}_z.npy") for m in MODELS}
    roof, _ = lc._grid(lc.ROOF, like)
    fp, _ = lc._grid(Path(json.loads((out/"roofer-check.json").read_text(encoding="utf-8"))["fp_raster"]), like)
    ext = {fid: shape.extent for fid, shape in arcpy.da.SearchCursor(str(lc.MASSING/"footprints"), ["FP_ID", "SHAPE@"])
           if fid in set(fp_ids)}
    for fid in fp_ids:
        e = ext[fid]
        c0 = int((e.XMin-3-428000.0)/CELL); c1 = int((e.XMax+3-428000.0)/CELL)+1
        r0 = int((4505000.0-(e.YMax+3))/CELL); r1 = int((4505000.0-(e.YMin-3))/CELL)+1
        sl = (slice(max(r0, 0), r1), slice(max(c0, 0), c1))
        mine = fp[sl] == fid
        panels = {"lidar": roof[sl], "Esri LOD2.0": z["E20"][sl], "roofer LoD2.2": z["R22"][sl], "roofer LoD1.2": z["R12"][sl]}
        panels = {k: np.where(mine, v, np.nan) for k, v in panels.items()}
        finite = np.concatenate([v[np.isfinite(v)] for v in panels.values()])
        lo, hi = (np.percentile(finite, 1), np.percentile(finite, 99.5)) if len(finite) else (0, 1)
        fig, axes = plt.subplots(1, 6, figsize=(22, 3.6), gridspec_kw={"width_ratios": [1, 1, 1, 1, 1, 1.4]})
        for ax, (name, v) in zip(axes[:4], panels.items()):
            im = ax.imshow(v, vmin=lo, vmax=hi, cmap="viridis")
            ax.set_title(name)
        fig.colorbar(im, ax=axes[3], fraction=0.046, label="m")
        d = panels["roofer LoD2.2"]-panels["lidar"]
        im = axes[4].imshow(d, vmin=-2, vmax=2, cmap="RdBu_r"); axes[4].set_title("roofer 2.2 - lidar")
        fig.colorbar(im, ax=axes[4], fraction=0.046, label="m")
        rr, cc = np.nonzero(mine)
        if len(rr):
            horizontal = np.ptp(cc) >= np.ptp(rr)
            line = int(np.median(rr if horizontal else cc))
            for name, v in panels.items():
                axes[5].plot(v[line, :] if horizontal else v[:, line], label=name, lw=2 if name == "lidar" else 1.1)
            axes[5].legend(fontsize=7)
        info = rows.get(fid, {})
        fig.suptitle(f"FP_ID {fid} {info.get('ROOF_TYPE')} | Esri LOD2.0 {info.get('VERDICT_E20')} p95 {info.get('E20_ABS_P95_M')} "
                     f"w1 {info.get('E20_WITHIN_1_PCT')}% | roofer 2.2 {info.get('VERDICT_R22')} {info.get('NOTE_R22')} "
                     f"p95 {info.get('R22_ABS_P95_M')} w1 {info.get('R22_WITHIN_1_PCT')}% | roofer rmse22 {info.get('RF_RMSE_LOD22')}",
                     fontsize=8)
        fig.tight_layout()
        fig.savefig(folder/f"fp{fid}.png", dpi=75)
        plt.close(fig)
        print(folder/f"fp{fid}.png", flush=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("score", "figures"))
    p.add_argument("a")
    p.add_argument("b", nargs="*")
    p.add_argument("--r22-raster", help="score roofer LoD2.2 from this raster (Multipatch To Raster of the import) instead of "
                                        "this script's own rasterization of the CityJSON roof faces")
    args = p.parse_args(argv)
    if args.step == "score":
        roofer_dir, check_dir, out = args.a, args.b[0], args.b[1]
        score(roofer_dir, check_dir, out, args.r22_raster)
        record = json.loads((Path(out)/"roofer-check.json").read_text(encoding="utf-8"))
        record["fp_raster"] = str(Path(check_dir)/"fp_id.tif")
        record["input"]["check"] = str(check_dir)
        (Path(out)/"roofer-check.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    else:
        figures(args.a, [int(x) for x in args.b])


if __name__ == "__main__":
    main()
