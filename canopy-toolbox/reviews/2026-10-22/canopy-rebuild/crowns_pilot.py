"""Crown pilot on one 1 km tile: October 8 and rebuilt canopy side by side (October 22, 2026).

    python reviews/2026-10-22/canopy-rebuild/crowns_pilot.py NEW_FOLDER [--tile 12TVL2804]

Run with ArcGIS Pro Python (PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT set) after count_rebuilt.py. Read-only on every input.
Crown delineation (canopy.crowns.delineate) is bounded to 4,000,000 cells (AGENTS.md); a 1 km tile at 0.5 m is exactly that,
so citywide crowns need a new tiled method, validated first. For the tile, this writes into NEW_FOLDER/crowns.gdb:
- oct8_crowns and oct8_trees_review: the October 8 canonical CHM and treetops;
- rebuilt_crowns and rebuilt_trees_review: the rebuilt (combined-classification) canonical CHM and treetops;
with the default settings (minimum height 2 m as the treetops, minimum crown area 3 m2). Crowns are cut at the tile edge, so
treat edge crowns as partial. The CHM windows are written as GeoTIFFs beside the geodatabase.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(TOOLBOX/"reviews"/"2026-10-21"/"roof-consensus"))
import canopy_rebuild as rb  # noqa: E402
import consensus_roofs as cr  # noqa: E402

OCT8 = cr.RUNS/"city-count-20261008"
REBUILT = cr.RUNS/"city-count-20261022"


def window_tif(binary, g, tile, path):
    from osgeo import gdal
    gdal.UseExceptions()
    r0, r1, c0, c1 = rb.tile_rows_cols(tile, g)
    array = np.memmap(binary, mode="r", dtype="float32", shape=(g["rows"], g["cols"]))
    block = np.where(np.isnan(array[r0:r1, c0:c1]), cr.NODATA, array[r0:r1, c0:c1]).astype(np.float32)
    ds = gdal.GetDriverByName("GTiff").Create(str(path), c1-c0, r1-r0, 1, gdal.GDT_Float32, options=["COMPRESS=DEFLATE"])
    ds.SetGeoTransform((g["x0"]+c0*g["cell"], g["cell"], 0, g["y0"]-r0*g["cell"], 0, -g["cell"]))
    ds.SetProjection(g["projection"])
    ds.GetRasterBand(1).SetNoDataValue(float(cr.NODATA))
    ds.GetRasterBand(1).WriteArray(block)
    ds = None
    return (g["x0"]+c0*g["cell"], g["y0"]-r1*g["cell"], g["x0"]+c1*g["cell"], g["y0"]-r0*g["cell"]), (r1-r0)*(c1-c0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path)
    parser.add_argument("--tile", default="12TVL2804")
    args = parser.parse_args(argv)
    if args.out.exists():
        raise FileExistsError(args.out)
    import arcpy
    from canopy import crowns
    if json.loads((REBUILT/"count.json").read_text(encoding="utf-8")).get("status") != "complete":
        raise ValueError("The rebuilt count is not complete")
    g = cr.grid()
    args.out.mkdir(parents=True)
    gdb = str(args.out/"crowns.gdb")
    arcpy.management.CreateFileGDB(str(args.out), "crowns.gdb")
    report = {"tile": args.tile, "runs": {}}
    for name, run, binary in (("oct8", OCT8, OCT8/"canonical-chm.bin"), ("rebuilt", REBUILT, REBUILT/"canonical-chm-combined.bin")):
        chm = args.out/f"{name}_chm_{args.tile}.tif"
        box, cells = window_tif(binary, g, args.tile, chm)
        if cells > crowns.MAX_CELLS:
            raise ValueError(f"{cells} cells exceed the crown bound")
        tops = str(Path(gdb)/f"{name}_treetops")
        where = arcpy.SpatialReference(6341)
        layer = arcpy.management.MakeFeatureLayer(str(run/"tree-count.gdb"/"city_treetops"), f"{name}_layer")
        extent = arcpy.Polygon(arcpy.Array([arcpy.Point(box[0], box[1]), arcpy.Point(box[0], box[3]),
                                            arcpy.Point(box[2], box[3]), arcpy.Point(box[2], box[1])]), where)
        arcpy.management.SelectLayerByLocation(layer, "COMPLETELY_WITHIN", extent)
        arcpy.management.CopyFeatures(layer, tops)
        arcpy.management.Delete(layer)
        crowns.delineate(str(chm), tops, gdb, prefix=f"{name}_")
        counts = {fc: int(arcpy.management.GetCount(str(Path(gdb)/f"{name}_{fc}"))[0]) for fc in ("treetops", "crowns", "trees_review")}
        statuses = {}
        with arcpy.da.SearchCursor(str(Path(gdb)/f"{name}_trees_review"), ["CROWN_STATUS"]) as cursor:
            for (s,) in cursor:
                statuses[s] = statuses.get(s, 0)+1
        areas = [a for (a,) in arcpy.da.SearchCursor(str(Path(gdb)/f"{name}_crowns"), ["CROWN_AREA_M2"]) if a]
        report["runs"][name] = {"cells": cells, **counts, "crown_status": statuses,
                                "crown_area_m2": {"total": round(sum(areas), 1), "median": round(float(np.median(areas)), 2) if areas else None}}
        print(name, json.dumps(report["runs"][name]), flush=True)
    (args.out/"crowns-pilot.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
