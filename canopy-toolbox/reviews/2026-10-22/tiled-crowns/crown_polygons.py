"""Crown polygons and statistics from the tiled city label raster, as canopy.crowns.delineate makes them (October 22, 2026).

    python reviews/2026-10-22/tiled-crowns/crown_polygons.py RUN_FOLDER

Run with ArcGIS Pro Python after tiled_crowns.py run. Read-only on its inputs; writes RUN_FOLDER/crowns.gdb:
- crowns: one (multipart) polygon per accepted crown, fields TREE_ID, HEIGHT_M (highest raw CHM cell of the crown),
  CROWN_AREA_M2, CROWN_DIAM_M (diameter of the circle of the same area), as delineate;
- trees_review: a copy of the rebuilt city_treetops with CROWN_AREA_M2, CROWN_DIAM_M, CROWN_HEIGHT_M and CROWN_STATUS
  (ESTIMATED, or CROWN_TOO_SMALL under 3 m2 or with no cell).
Polygons are made per 950 m core (NumPyArrayToRaster, RasterToPolygon NO_SIMPLIFY on the accepted labels) and dissolved by
label across cores, so a crown crossing a core edge becomes one feature. Unseeded canopy (canopy cells no treetop reached)
is reported in RUN_FOLDER/polygons.json, as delineate warns about it.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import tiled_crowns as tc  # noqa: E402

MIN_CROWN_AREA_M2 = 3.0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", type=Path)
    args = parser.parse_args(argv)
    import arcpy
    from canopy import common
    manifest = json.loads((args.run/"manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise ValueError("The tiled crown run is not complete")
    g = tc.cr.grid()
    chm, rows, _, _, seed_labels = tc.load(g, args.run)       # peaks.npy cached by the run
    labels = np.load(args.run/"labels.npy", mmap_mode="r")
    n = len(rows)                                               # city treetops; labels above n are outside peaks
    total = int(seed_labels.max())
    counts = np.zeros(total+1, np.int64)
    maxima = np.full(total+1, -np.inf)
    unseeded = 0
    for r0 in range(0, g["rows"], 512):
        lab = np.asarray(labels[r0:r0+512])
        raw = np.asarray(chm[r0:r0+512], dtype=np.float64)
        canopy = np.isfinite(raw) & (raw >= tc.MIN_HEIGHT)
        counts += np.bincount(lab[canopy].ravel(), minlength=total+1)
        np.maximum.at(maxima, lab[canopy].ravel(), raw[canopy].ravel())
        unseeded += int((canopy & (lab == 0)).sum())
    area = counts*tc.CELL**2
    accepted = (counts > 0) & (area >= MIN_CROWN_AREA_M2)
    accepted[0] = False
    accepted[n+1:] = False                                     # crowns of peaks outside the city are not output
    gdb = str(args.run/"crowns.gdb")
    if arcpy.Exists(gdb):
        raise FileExistsError(gdb)
    arcpy.management.CreateFileGDB(str(args.run), "crowns.gdb")
    sr = arcpy.SpatialReference(6341)
    parts = str(Path(gdb)/"crown_parts")
    first = True
    with common.scratch() as (_, scratch_gdb):
        for name, info in manifest["tiles"].items():
            r0, r1, c0, c1 = info["core"]
            block = np.asarray(labels[r0:r1, c0:c1])
            kept = np.where(accepted[block], block, 0).astype(np.int32)
            if not kept.any():
                continue
            raster = arcpy.NumPyArrayToRaster(kept, arcpy.Point(g["x0"]+c0*tc.CELL, g["y0"]-r1*tc.CELL), tc.CELL, tc.CELL, 0)
            label_raster = str(Path(scratch_gdb)/f"labels_{name}")
            raster.save(label_raster)
            arcpy.management.DefineProjection(label_raster, sr)
            polygons = str(Path(scratch_gdb)/f"parts_{name}")
            arcpy.conversion.RasterToPolygon(label_raster, polygons, "NO_SIMPLIFY", "VALUE")
            if first:
                arcpy.management.CopyFeatures(polygons, parts)
                first = False
            else:
                arcpy.management.Append(polygons, parts, "NO_TEST")
            print(f"polygons {name}", flush=True)
    crowns = str(Path(gdb)/"crowns")
    arcpy.analysis.PairwiseDissolve(parts, crowns, "gridcode", multi_part="MULTI_PART")
    arcpy.management.Delete(parts)
    common.add_fields(crowns, [("TREE_ID", "TEXT", 36), ("HEIGHT_M", "DOUBLE", None),
                               ("CROWN_AREA_M2", "DOUBLE", None), ("CROWN_DIAM_M", "DOUBLE", None)])
    ids = [r["TREE_ID"] for r in rows]
    with arcpy.da.UpdateCursor(crowns, ["gridcode", "TREE_ID", "HEIGHT_M", "CROWN_AREA_M2", "CROWN_DIAM_M"]) as cursor:
        for row in cursor:
            k = row[0]
            row[1:] = [ids[k-1], float(maxima[k]), float(area[k]), 2*math.sqrt(area[k]/math.pi)]
            cursor.updateRow(row)
    arcpy.management.DeleteField(crowns, "gridcode")
    review = str(Path(gdb)/"trees_review")
    arcpy.management.CopyFeatures(str(tc.COUNT/"tree-count.gdb"/"city_treetops"), review)
    common.add_fields(review, [("CROWN_AREA_M2", "DOUBLE", None), ("CROWN_DIAM_M", "DOUBLE", None),
                               ("CROWN_HEIGHT_M", "DOUBLE", None), ("CROWN_STATUS", "TEXT", 32)])
    index = {tree_id: k+1 for k, tree_id in enumerate(ids)}
    with arcpy.da.UpdateCursor(review, ["TREE_ID", "CROWN_AREA_M2", "CROWN_DIAM_M", "CROWN_HEIGHT_M", "CROWN_STATUS"]) as cursor:
        for row in cursor:
            k = index[row[0]]
            row[1:] = [float(area[k]), 2*math.sqrt(area[k]/math.pi), float(maxima[k]) if counts[k] else None,
                       "ESTIMATED" if accepted[k] else "CROWN_TOO_SMALL"]
            cursor.updateRow(row)
    common.metadata(crowns, "Marker-controlled canopy watershed in 950 m tiles with a measured halo (tiled_crowns.py), "
                    f"dissolved across tiles. Unseeded canopy area: {unseeded*tc.CELL**2} m2. Estimated crowns, not surveyed.")
    report = {"treetops": n, "crowns": int(accepted.sum()), "crown_too_small": int(n-accepted.sum()),
              "crown_area_m2": round(float(area[accepted].sum()), 1),
              "median_crown_m2": round(float(np.median(area[accepted])), 2),
              "unseeded_canopy_m2": unseeded*tc.CELL**2,
              "features": int(arcpy.management.GetCount(crowns)[0])}
    if report["features"] != report["crowns"]:
        raise RuntimeError("Crown features and accepted crowns differ")
    (args.run/"polygons.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
