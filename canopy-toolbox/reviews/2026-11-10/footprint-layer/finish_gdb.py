"""Copy the built footprint layer into a file geodatabase and repair what ArcGIS's stricter geometry check finds
(November 10, 2026). Run with the ArcGIS Pro Python (-I).

shapely accepts every outline; ArcGIS flags about 50 (self-intersections, duplicate vertices and short segments, most
where unit cuts meet), and roofer drops a whole tile on one invalid polygon. Repair Geometry (OGC) fixes them in the
copy, and both checks must then come back empty.

    finish_gdb.py OUT      OUT/footprints.gpkg -> OUT/footprints.gdb/footprints, OUT/finish.json
"""
import json
import os
import sys

import arcpy


def problems(fc, gdb, kind):
    report = os.path.join(gdb, f"check_{kind.lower()}")
    arcpy.management.CheckGeometry(fc, report, kind)
    rows = [r[0] for r in arcpy.da.SearchCursor(report, ["PROBLEM"])]
    return {p: rows.count(p) for p in sorted(set(rows))}


def main(out):
    arcpy.env.overwriteOutput = True
    gdb = os.path.join(out, "footprints.gdb")
    if not arcpy.Exists(gdb):
        arcpy.management.CreateFileGDB(out, "footprints.gdb")
    fc = os.path.join(gdb, "footprints")
    arcpy.conversion.ExportFeatures(os.path.join(out, "footprints.gpkg", "main.footprints"), fc)
    before = {k: problems(fc, gdb, k) for k in ("OGC", "ESRI")}
    n0 = int(arcpy.management.GetCount(fc)[0])
    arcpy.management.RepairGeometry(fc, "KEEP_NULL", "OGC")
    after = {k: problems(fc, gdb, k) for k in ("OGC", "ESRI")}
    empty = sum(1 for (s,) in arcpy.da.SearchCursor(fc, ["SHAPE@"]) if s is None or s.area == 0)
    summary = {"features": n0, "after_repair": int(arcpy.management.GetCount(fc)[0]), "empty_after_repair": empty,
               "problems_before": before, "problems_after": after,
               "spatial_reference": arcpy.Describe(fc).spatialReference.factoryCode}
    with open(os.path.join(out, "finish.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps(summary, indent=1))
    if any(after.values()) or empty:
        raise SystemExit("geometry problems remain")


if __name__ == "__main__":
    main(sys.argv[1])
