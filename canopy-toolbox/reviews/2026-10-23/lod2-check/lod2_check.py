r"""How well the October 22 LOD2.0 roof forms follow the lidar roof, against the LOD1.2 blocks (October 23, 2026).

    python reviews/2026-10-23/lod2-check/lod2_check.py rasterize OUT [--pilot]   both levels and the footprints on the roof grid
    python reviews/2026-10-23/lod2-check/lod2_check.py measure OUT                per-building errors, types, verdicts; CSV + gdb
    python reviews/2026-10-23/lod2-check/lod2_check.py figures OUT FP_ID ...      lidar / LOD2.0 / difference panels as PNG
    --massing GDB checks another massing geodatabase with lod12, lod20 and footprints (the fill trial, fill_trial.py)

ArcGIS Pro Python with 3D Analyst and Spatial Analyst (PYTHONNOUSERSITE=1). Read-only on the massing and the library; writes
only under OUT (a short path: ArcGIS raster saves fail with ERROR 2592 under the long scratch paths).
- Reference: the consensus roof elevation (`roof_elevation_m.tif`, the maximum first/single return per 0.5 m cell, 2 of 3
  sources). This is also what the massing was fitted to, so the check measures how well each level represents the lidar
  roof, not an independent truth.
- Models: each level's multipatches by Multipatch To Raster (highest Z on a vertical line through each cell centre) on the
  same grid, and the footprints by Polygon To Raster (cell centre, FP_ID).
- Compared cells: inside the footprint where the lidar has roof. Cells without roof support are not errors, but the share
  of the whole footprint where each level sits within 1 m of the footprint's median ground (GROUND_PCT) is reported, since
  a roof modelled at ground level shows as a pit whatever the lidar saw there.
- The rules for types and verdicts (TYPE_RULES, VERDICT_RULES) were written before the citywide results were read. The
  DROPPED flag was added after the 12TVL2804 pilot showed footprint parts set at ground level under a lidar roof.
"""
import argparse
import csv
import datetime
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
from canopy.lidar_root import lidar_root  # noqa: E402

VALLEY = lidar_root()/"2023-salt-lake-valley"
LIB = VALLEY/"runs"/"millcreek-products-20261022"
ROOF = LIB/"roof_elevation_m.tif"
MASSING = VALLEY/"runs"/"massing-20261022"/"massing.gdb"
OVERTURE = Path(r"Z:\GIS\overture\2026-10-21.0\millcreek\millcreek_overture.gpkg")
PILOT_TILE = (428000.0, 4504000.0, 429000.0, 4505000.0)        # 12TVL2804, the labelled tile
LEVELS = ("lod12", "lod20")
CELL = 0.5
MIN_CELLS = 20                                                  # 5 m2 of lidar roof before a verdict is given
TRANSFORM = "WGS_1984_(ITRF08)_To_NAD_1983_2011"

TYPE_RULES = """first match, from the lidar roof cells in the footprint:
multi-level: footprint >= 400 m2, median slope < 12 deg, relief (p95 - p5) >= 2 m, >= 15% of cells more than 1.5 m from the median
flat-parapet: median slope < 8 deg, relief < 1.5 m, footprint >= 150 m2, edge ring (within 1 m of the outline) p75 minus
              interior (2 m or more inside) median >= 0.3 m
flat: median slope < 8 deg, relief < 1.5 m
steep-pitched: median slope >= 25 deg (about 6/12 and steeper)
pitched: median slope >= 8 deg
other: the rest (low slope with relief)"""
VERDICT_RULES = """per building, on compared cells; margins: 10 points of within-1 m share, 0.5 m of |error| p95
too-few: fewer than 20 compared cells
broken (LOD2.0): top more than 1 m above the highest lidar roof cell in the footprint (TOP_ABOVE_LIDAR), or 10% or more
                 of compared cells more than 1 m above the lidar (ABOVE_1M), or 10% or more of compared cells dropped
                 (LOD2.0 within 1 m of the footprint's median ground where the lidar roof is 2 m or more above it; DROPPED,
                 added after the pilot), or the LOD2.0 surface missing on 5% or more of compared cells (MISSING)
better: not broken; LOD2.0 ahead by a margin on at least one measure and behind by a margin on neither
worse: not broken; LOD1.2 ahead by a margin on at least one measure and LOD2.0 ahead on neither
same: the rest (including mixed: ahead on one, behind on the other, counted as MIXED in the note)"""


def _env(out, window):
    import arcpy
    extent = " ".join(str(v) for v in window) if window else str(ROOF)
    return arcpy.EnvManager(scratchWorkspace=str(out), extent=extent, snapRaster=str(ROOF), cellSize=str(ROOF),
                            outputCoordinateSystem=arcpy.Describe(str(ROOF)).spatialReference, compression="LZW",
                            parallelProcessingFactor="100%")


def rasterize(out, window):
    import arcpy
    arcpy.CheckOutExtension("3D")
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    roof_sr = arcpy.Describe(str(ROOF)).spatialReference
    for key in LEVELS:
        sr = arcpy.Describe(str(MASSING/key)).spatialReference
        assert sr.factoryCode == roof_sr.factoryCode or sr.name == roof_sr.name, (sr.name, roof_sr.name)
    record = {"schema": "lod2-check/1", "started": datetime.datetime.now().isoformat(timespec="seconds"),
              "window": window, "roof": str(ROOF), "massing": str(MASSING), "rasters": {}}
    with _env(out, window):
        for key in LEVELS:
            started = datetime.datetime.now()
            target = str(out/f"{key}_z.tif")
            arcpy.conversion.MultipatchToRaster(str(MASSING/key), target, CELL, "MAXIMUM_HEIGHT")
            record["rasters"][key] = {"path": target, "seconds": round((datetime.datetime.now()-started).total_seconds())}
            print(key, record["rasters"][key], flush=True)
        target = str(out/"fp_id.tif")
        arcpy.conversion.PolygonToRaster(str(MASSING/"footprints"), "FP_ID", target, "CELL_CENTER", "", CELL)
        record["rasters"]["fp_id"] = {"path": target}
    (out/"rasterize.json").write_text(json.dumps(record, indent=1), encoding="utf-8")


def _grid(path, like=None):
    """A raster as a float32 array (NoData = nan) with its lower-left corner, optionally cut to another's frame."""
    import arcpy
    r = arcpy.Raster(str(path))
    if like is None:
        ll = arcpy.Point(r.extent.XMin, r.extent.YMin)
        a = arcpy.RasterToNumPyArray(r, ll, nodata_to_value=np.nan if r.pixelType.startswith("F") else 0)
        return a.astype(np.float32) if a.dtype.kind == "f" else a, (r.extent.XMin, r.extent.YMin)
    (x0, y0), (rows, cols) = like
    a = arcpy.RasterToNumPyArray(r, arcpy.Point(x0, y0), cols, rows,
                                 nodata_to_value=np.nan if r.pixelType.startswith("F") else 0)
    return a.astype(np.float32) if a.dtype.kind == "f" else a, (x0, y0)


def _arrays(out):
    from scipy import ndimage
    fp, origin = _grid(out/"fp_id.tif")
    fp = fp.astype(np.int32)
    like = (origin, fp.shape)
    roof, _ = _grid(ROOF, like)
    z = {key: _grid(out/f"{key}_z.tif", like)[0] for key in LEVELS}
    # depth inside the outline: same FP_ID over a (2k+1)-cell square
    inner = {}
    for k in (2, 4):
        lo = ndimage.minimum_filter(fp, size=2*k+1, mode="constant", cval=0)
        hi = ndimage.maximum_filter(fp, size=2*k+1, mode="constant", cval=0)
        inner[k] = (lo == fp) & (hi == fp)
    # slope from central differences over 1 m, only where both neighbours are roof cells of the same footprint
    gy = np.full(roof.shape, np.nan, np.float32)
    gx = np.full(roof.shape, np.nan, np.float32)
    same_y = (fp[2:, :] == fp[:-2, :])
    same_x = (fp[:, 2:] == fp[:, :-2])
    gy[1:-1, :] = np.where(same_y, (roof[:-2, :]-roof[2:, :])/(2*CELL), np.nan)
    gx[:, 1:-1] = np.where(same_x, (roof[:, 2:]-roof[:, :-2])/(2*CELL), np.nan)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    del gx, gy
    return fp, roof, z, inner, slope, origin


def _pct(v, q):
    return float(np.percentile(v, q)) if len(v) else None


def _level(e, lidar, ground, top):
    """Error statistics of one level on the compared cells (e = model - lidar, nan where the model is missing)."""
    have = ~np.isnan(e)
    a = np.abs(e[have])
    lidar_max = float(lidar.max())
    dropped = None if ground is None else 100*float(((lidar+np.nan_to_num(e, nan=np.inf)-ground < 1)
                                                      & (lidar-ground >= 2)).mean())
    return {"cells": int(have.sum()), "missing_pct": 100*(1-have.mean()),
            "bias_m": float(np.median(e[have])) if have.any() else None,
            "abs_p50_m": _pct(a, 50), "abs_p95_m": _pct(a, 95),
            "within_05_pct": 100*float((a <= 0.5).mean()) if len(a) else None,
            "within_1_pct": 100*float((a <= 1).mean()) if len(a) else None,
            "above_1_pct": 100*float((e[have] > 1).mean()) if have.any() else None,
            "below_1_pct": 100*float((e[have] < -1).mean()) if have.any() else None,
            "dropped_pct": dropped,
            "top_minus_lidar_max_m": None if top is None else top-lidar_max}


def _type(area, n, slope50, relief, off15, ring, interior):
    if n < MIN_CELLS:
        return "too-few"
    if area >= 400 and slope50 < 12 and relief >= 2 and off15 >= 15:
        return "multi-level"
    if slope50 < 8 and relief < 1.5:
        if area >= 150 and len(ring) and len(interior) and np.percentile(ring, 75)-np.median(interior) >= 0.3:
            return "flat-parapet"
        return "flat"
    if slope50 >= 25:
        return "steep-pitched"
    if slope50 >= 8:
        return "pitched"
    return "other"


def _verdict(n, l12, l20):
    if n < MIN_CELLS:
        return "too-few", ""
    broken = []
    if l20["top_minus_lidar_max_m"] is not None and l20["top_minus_lidar_max_m"] > 1:
        broken.append("TOP_ABOVE_LIDAR")
    if l20["above_1_pct"] is not None and l20["above_1_pct"] >= 10:
        broken.append("ABOVE_1M")
    if l20["dropped_pct"] is not None and l20["dropped_pct"] >= 10:
        broken.append("DROPPED")
    if l20["missing_pct"] >= 5:
        broken.append("MISSING")
    if broken:
        return "broken", ";".join(broken)
    if l12["within_1_pct"] is None:
        return "better", "NO_LOD12"
    d1 = l20["within_1_pct"]-l12["within_1_pct"]
    dp = l12["abs_p95_m"]-l20["abs_p95_m"]
    ahead = d1 >= 10 or dp >= 0.5
    behind = d1 <= -10 or dp <= -0.5
    if ahead and not behind:
        return "better", ""
    if behind and not ahead:
        return "worse", ""
    return "same", "MIXED" if ahead and behind else ""


def _overture(out):
    """A use hint per FP_ID: the Overture building subtype under the footprint's inside point, else the land use."""
    import arcpy
    hints = {}
    sr = arcpy.Describe(str(MASSING/"footprints")).spatialReference
    with arcpy.EnvManager(outputCoordinateSystem=sr, geographicTransformations=TRANSFORM, overwriteOutput=True):
        points = arcpy.management.FeatureToPoint(str(MASSING/"footprints"), "memory/fp_pts", "INSIDE")[0]
        for layer, field in (("main.land_use_polygons", "land"), ("main.buildings", "bldg")):
            joined = arcpy.analysis.SpatialJoin(points, str(OVERTURE/layer), f"memory/join_{field}",
                                                "JOIN_ONE_TO_ONE", "KEEP_ALL", match_option="INTERSECT")[0]
            names = [f.name for f in arcpy.ListFields(joined)]
            sub = "subtype" if "subtype" in names else "subtype_1"
            cls = "class" if "class" in names else "class_1"
            extra = ["roof_shape"] if field == "bldg" else []
            for fp, s, c, *r in arcpy.da.SearchCursor(joined, ["FP_ID", sub, cls] + extra):
                hints.setdefault(fp, {})[field] = (s, c) + tuple(r)
    use, roof_shape = {}, {}
    commercial = {"commercial", "retail", "industrial", "office", "warehouse"}
    for fp, h in hints.items():
        b, land = h.get("bldg", (None, None, None)), h.get("land", (None, None))
        roof_shape[fp] = b[2]
        words = {w for w in (b[0], b[1], land[0], land[1]) if w}
        if words & commercial:
            use[fp] = "commercial"
        elif words & {"residential", "house", "detached", "apartments", "terrace", "semidetached_house"}:
            use[fp] = "residential"
        elif words:
            use[fp] = "other:" + (b[0] or b[1] or land[0] or land[1])
        else:
            use[fp] = ""
    return use, roof_shape


def measure(out):
    import arcpy
    out = Path(out).resolve()
    started = datetime.datetime.now().isoformat(timespec="seconds")
    fp, roof, z, inner, slope, origin = _arrays(out)
    print("arrays", fp.shape, flush=True)
    attrs = {}
    fields = ["FP_ID", "FOOTPRINT_M2", "ROOF_COV_PCT", "HEIGHT_STATUS", "GROUND_Z50_M", "RMSE", "PCT_HI_ERR", "TOP_Z"]
    for key in LEVELS:
        with arcpy.da.SearchCursor(str(MASSING/key), fields) as cursor:
            for row in cursor:
                a = attrs.setdefault(row[0], {"area": row[1], "cov": row[2], "status": row[3], "ground": row[4]})
                a[key] = {"tool_rmse": row[5], "tool_pct_hi": row[6], "top": row[7]}
    footprint_cells = np.bincount(fp.ravel(), minlength=max(attrs)+1)
    # over the whole footprint, lidar roof or not: cells where the level sits within 1 m of the footprint's median ground
    ground = np.full(len(footprint_cells), np.nan, np.float32)
    for fid, a in attrs.items():
        ground[fid] = np.nan if a["ground"] is None else a["ground"]
    inside = fp > 0
    level_ground = {key: np.bincount(fp[inside], weights=(z[key][inside] < ground[fp[inside]]+1),
                                     minlength=len(footprint_cells)) for key in LEVELS}
    del inside
    sel = (fp > 0) & ~np.isnan(roof)
    ids = fp[sel]
    order = np.argsort(ids, kind="stable")
    ids = ids[order]
    cols = {"roof": roof[sel][order], "slope": slope[sel][order], "ring": ~inner[2][sel][order],
            "interior": inner[4][sel][order]}
    for key in LEVELS:
        cols[key] = z[key][sel][order]-cols["roof"]
    del fp, roof, z, inner, slope
    use, roof_shape = _overture(out)
    starts = np.flatnonzero(np.r_[True, ids[1:] != ids[:-1]])
    bounds = dict(zip(ids[starts].tolist(), zip(starts, np.r_[starts[1:], len(ids)])))
    rows = []
    for fid in sorted(attrs):
        a = attrs[fid]
        i, j = bounds.get(fid, (0, 0))
        r = cols["roof"][i:j]
        n = j-i
        lidar_max = float(r.max()) if n else None
        s = cols["slope"][i:j]
        s = s[~np.isnan(s)]
        slope50 = float(np.median(s)) if len(s) else float("nan")
        relief = float(np.percentile(r, 95)-np.percentile(r, 5)) if n else float("nan")
        off15 = 100*float((np.abs(r-np.median(r)) > 1.5).mean()) if n else 0.0
        ring, interior = r[cols["ring"][i:j]], r[cols["interior"][i:j]]
        parapet = (float(np.percentile(ring, 75)-np.median(interior)) if len(ring) and len(interior) else None)
        lv = {key: _level(cols[key][i:j], r, a["ground"], a.get(key, {}).get("top")) if n else None for key in LEVELS}
        kind = _type(a["area"], n, slope50, relief, off15, ring, interior)
        verdict, note = _verdict(n, lv["lod12"], lv["lod20"]) if n else ("too-few", "")
        row = {"FP_ID": fid, "FOOTPRINT_M2": a["area"], "ROOF_COV_PCT": a["cov"], "HEIGHT_STATUS": a["status"],
               "FP_CELLS": int(footprint_cells[fid]) if fid < len(footprint_cells) else 0, "COMPARED_CELLS": n,
               "ROOF_TYPE": kind, "USE_HINT": use.get(fid, ""), "OVERTURE_ROOF_SHAPE": roof_shape.get(fid) or "",
               "SLOPE_P50_DEG": slope50, "RELIEF_M": relief, "OFF_1P5_PCT": off15, "PARAPET_RISE_M": parapet,
               "HEIGHT_ABOVE_GROUND_M": None if lidar_max is None or a["ground"] is None else lidar_max-a["ground"],
               "VERDICT": verdict, "NOTE": note}
        for key in LEVELS:
            p = key.upper()
            for name, value in (lv[key] or {}).items():
                row[f"{p}_{name.upper()}"] = value
            row[f"{p}_GROUND_PCT"] = (100*float(level_ground[key][fid])/row["FP_CELLS"] if row["FP_CELLS"]
                                      and a["ground"] is not None else None)
            row[f"{p}_TOOL_RMSE"] = a.get(key, {}).get("tool_rmse")
            row[f"{p}_TOOL_PCT_HI"] = a.get(key, {}).get("tool_pct_hi")
        rows.append(row)
    names = list(dict.fromkeys(k for row in rows for k in row))
    with open(out/"lod2-check.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, names)
        w.writeheader()
        for row in rows:
            w.writerow({k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items()})
    _gdb(out, rows, names)
    record = {"schema": "lod2-check/1", "started": started,
              "finished": datetime.datetime.now().isoformat(timespec="seconds"), "roof": str(ROOF),
              "massing": str(MASSING), "type_rules": TYPE_RULES, "verdict_rules": VERDICT_RULES,
              "summary": summarize(rows)}
    (out/"lod2-check.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps(record["summary"]["overall"], indent=1))


def _gdb(out, rows, names):
    """The results as a table and joined onto a copy of the footprints, for review in Pro."""
    import arcpy
    gdb = out/"lod2-check.gdb"
    if not arcpy.Exists(str(gdb)):
        arcpy.management.CreateFileGDB(str(out), gdb.name)
    table = str(gdb/"results")
    if arcpy.Exists(table):
        arcpy.management.Delete(table)
    arcpy.management.CreateTable(str(gdb), "results")
    kinds = {}
    for name in names:
        values = [row.get(name) for row in rows if row.get(name) is not None]
        kinds[name] = ("LONG" if values and all(isinstance(v, (int, np.integer)) and not isinstance(v, bool)
                                                 for v in values)
                       else "DOUBLE" if values and all(isinstance(v, (int, float)) for v in values) else "TEXT")
        arcpy.management.AddField(table, name, kinds[name], field_length=60 if kinds[name] == "TEXT" else None)
    with arcpy.da.InsertCursor(table, names) as cursor:
        for row in rows:
            cursor.insertRow([None if (v := row.get(n)) is None or (isinstance(v, float) and np.isnan(v)) else v
                              for n in names])
    fc = str(gdb/"footprints")
    if arcpy.Exists(fc):
        arcpy.management.Delete(fc)
    arcpy.management.CopyFeatures(str(MASSING/"footprints"), fc)
    arcpy.management.JoinField(fc, "FP_ID", table, "FP_ID", [n for n in names if n not in
                                                              ("FP_ID", "FOOTPRINT_M2", "ROOF_COV_PCT", "HEIGHT_STATUS")])


def summarize(rows):
    def stats(part):
        out = {"buildings": len(part), "verdicts": {}}
        for v in ("better", "same", "worse", "broken", "too-few"):
            out["verdicts"][v] = sum(1 for r in part if r["VERDICT"] == v)
        out["mixed"] = sum(1 for r in part if r["NOTE"] == "MIXED")
        for flag in ("TOP_ABOVE_LIDAR", "ABOVE_1M", "DROPPED", "MISSING"):
            out[f"broken_{flag}"] = sum(1 for r in part if flag in r["NOTE"].split(";"))
        judged = [r for r in part if r["VERDICT"] != "too-few"]
        for key in ("LOD12", "LOD20"):
            m = {}
            for name in ("ABS_P50_M", "ABS_P95_M", "WITHIN_05_PCT", "WITHIN_1_PCT", "BIAS_M", "DROPPED_PCT", "GROUND_PCT"):
                v = np.array([r[f"{key}_{name}"] for r in judged if r.get(f"{key}_{name}") is not None], float)
                m[name.lower()] = ({"p25": round(float(np.percentile(v, 25)), 3), "p50": round(float(np.median(v)), 3),
                                    "p75": round(float(np.percentile(v, 75)), 3)} if len(v) else None)
            cells = sum(r[f"{key}_CELLS"] for r in judged)
            if cells:
                m["pooled_within_05_pct"] = round(sum(r[f"{key}_WITHIN_05_PCT"]*r[f"{key}_CELLS"] for r in judged)/cells, 2)
                m["pooled_within_1_pct"] = round(sum(r[f"{key}_WITHIN_1_PCT"]*r[f"{key}_CELLS"] for r in judged)/cells, 2)
            out[key.lower()] = m
        return out
    result = {"overall": stats(rows), "by_type": {}, "by_use": {}, "by_coverage": {}}
    for kind in sorted({r["ROOF_TYPE"] for r in rows}):
        result["by_type"][kind] = stats([r for r in rows if r["ROOF_TYPE"] == kind])
    for use in sorted({r["USE_HINT"].split(":")[0] for r in rows}):
        result["by_use"][use or "none"] = stats([r for r in rows if r["USE_HINT"].split(":")[0] == use])
    for name, lo, hi in (("under 80%", 0, 80), ("80-95%", 80, 95), ("95% and over", 95, 1000)):
        result["by_coverage"][name] = stats([r for r in rows if r["ROOF_COV_PCT"] is not None
                                             and lo <= r["ROOF_COV_PCT"] < hi])
    return result


def figures(out, fp_ids):
    """Per building: lidar roof, LOD2.0 surface, LOD1.2 surface, LOD2.0 minus lidar, and a long-axis profile."""
    import arcpy
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out = Path(out).resolve()
    folder = out/"figures"
    folder.mkdir(exist_ok=True)
    rows = {int(r["FP_ID"]): r for r in csv.DictReader(open(out/"lod2-check.csv", encoding="utf-8"))}
    ext = {fid: shape.extent for fid, shape in arcpy.da.SearchCursor(str(MASSING/"footprints"), ["FP_ID", "SHAPE@"])
           if fid in set(fp_ids)}
    for fid in fp_ids:
        e = ext[fid]
        x0 = np.floor((e.XMin-3)/CELL)*CELL
        y0 = np.floor((e.YMin-3)/CELL)*CELL
        cols = int(np.ceil((e.XMax+3-x0)/CELL))
        rows_ = int(np.ceil((e.YMax+3-y0)/CELL))
        like = ((x0, y0), (rows_, cols))
        fp, _ = _grid(out/"fp_id.tif", like)
        roof, _ = _grid(ROOF, like)
        m20, _ = _grid(out/"lod20_z.tif", like)
        m12, _ = _grid(out/"lod12_z.tif", like)
        mine = fp == fid
        show = {k: np.where(mine, v, np.nan) for k, v in (("lidar", roof), ("LOD2.0", m20), ("LOD1.2", m12))}
        finite = np.concatenate([v[~np.isnan(v)] for v in show.values()])
        lo, hi = (np.percentile(finite, 1), np.percentile(finite, 99.5)) if len(finite) else (0, 1)
        fig, axes = plt.subplots(1, 5, figsize=(19, 4), gridspec_kw={"width_ratios": [1, 1, 1, 1, 1.4]})
        extent = (0, cols*CELL, 0, rows_*CELL)
        for ax, (name, v) in zip(axes[:3], show.items()):
            im = ax.imshow(v, vmin=lo, vmax=hi, cmap="viridis", extent=extent)
            ax.set_title(name)
        fig.colorbar(im, ax=axes[2], fraction=0.046, label="elevation (m)")
        d = show["LOD2.0"]-show["lidar"]
        im = axes[3].imshow(d, vmin=-2, vmax=2, cmap="RdBu_r", extent=extent)
        axes[3].set_title("LOD2.0 - lidar")
        fig.colorbar(im, ax=axes[3], fraction=0.046, label="m")
        r, c = np.nonzero(mine)
        if len(r):
            if np.ptp(c) >= np.ptp(r):
                row = int(np.median(r))
                xs = np.arange(cols)*CELL
                for name, v in show.items():
                    axes[4].plot(xs, v[row, :], label=name, lw=2 if name == "lidar" else 1.2)
                axes[4].set_title(f"profile along row {row} (west to east)")
            else:
                col = int(np.median(c))
                xs = np.arange(rows_)*CELL
                for name, v in show.items():
                    axes[4].plot(xs, v[:, col], label=name, lw=2 if name == "lidar" else 1.2)
                axes[4].set_title(f"profile along column {col} (north to south)")
            axes[4].legend()
            axes[4].set_xlabel("m")
        info = rows.get(fid, {})
        fig.suptitle(f"FP_ID {fid}  {info.get('ROOF_TYPE')}  {info.get('USE_HINT')}  verdict {info.get('VERDICT')} "
                     f"{info.get('NOTE')}  |  LOD2.0 |e| p50 {info.get('LOD20_ABS_P50_M')} p95 {info.get('LOD20_ABS_P95_M')} "
                     f"within 1 m {info.get('LOD20_WITHIN_1_PCT')}%  |  LOD1.2 |e| p50 {info.get('LOD12_ABS_P50_M')} "
                     f"p95 {info.get('LOD12_ABS_P95_M')} within 1 m {info.get('LOD12_WITHIN_1_PCT')}%", fontsize=9)
        fig.tight_layout()
        fig.savefig(folder/f"fp{fid}.png", dpi=80)
        plt.close(fig)
        print(folder/f"fp{fid}.png", flush=True)


def _use(massing):
    global MASSING
    if massing:
        MASSING = Path(massing)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("rasterize", "measure", "figures"))
    p.add_argument("out", type=Path)
    p.add_argument("fp_ids", nargs="*", type=int)
    p.add_argument("--pilot", action="store_true", help="12TVL2804 only")
    p.add_argument("--massing", help="another massing.gdb (default: the October 22 citywide run)")
    a = p.parse_args(argv)
    _use(a.massing)
    if a.step == "rasterize":
        rasterize(a.out, PILOT_TILE if a.pilot else None)
    elif a.step == "measure":
        measure(a.out)
    else:
        figures(a.out, a.fp_ids)


if __name__ == "__main__":
    main()
