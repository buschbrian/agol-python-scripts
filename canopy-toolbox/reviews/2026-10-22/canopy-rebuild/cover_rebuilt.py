"""Canopy cover by zone on the rebuilt canopy and on October 19's, with the toolbox's own cover.summarize (October 22, 2026).

    python reviews/2026-10-22/canopy-rebuild/cover_rebuilt.py NEW_FOLDER

Run with ArcGIS Pro Python (Spatial Analyst; PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT set). Read-only on every input; writes
NEW_FOLDER/cover.gdb and cover-comparison.csv. Brian: keep rebuilding with the better data (October 22).

Zones (NEW_FOLDER/cover.gdb/zones, field ZONE_ID), from the October 8 count's inputs (municipal boundary, 2025-tax-year parcel
snapshot) and its ownership rules (canopy.parcel_ownership.classify, as the treetop count used them):
- CITY: the municipal boundary;
- OWNERSHIP:<category>: parcels of each category (PRIVATE, PUBLIC_GOVERNMENT, UNKNOWN_OWNER), dissolved;
- PUBLIC:<group>: public parcels of each owner group (SALT_LAKE_COUNTY, MILLCREEK, PUBLIC_SCHOOL, ...), dissolved;
- OWNERSHIP:NO_PARCEL: the city outside every parcel (mostly streets and other rights-of-way).
Zones overlap (CITY holds all others); cover.summarize treats each zone on its own. Its definitions apply unchanged: cell
centres, canopy where the CHM is at least 2 m, OBS_CANOPY_PCT over observed cells, CANOPY_PCT only when the zone is fully
observed, LOW and HIGH bounds counting unobserved cells as no canopy or as all canopy. Run on October 19's chm_m.tif
(table cover_oct19) and the rebuilt chm_m.tif (table cover_rebuilt).
"""
import argparse
import collections
import csv
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
sys.path.insert(0, str(TOOLBOX/"reviews"/"2026-10-21"/"roof-consensus"))
import consensus_roofs as cr  # noqa: E402

OCT8 = cr.RUNS/"city-count-20261008"
REBUILT = cr.RUNS/"canopy-rebuild-20261022"
FIELDS = ["ZONE_ID", "COVER_STATUS", "CANOPY_M2", "CANOPY_ACRES", "ZONE_M2", "GRID_M2", "OBSERVED_M2", "MISSING_M2",
          "COVERAGE_PCT", "CANOPY_PCT", "OBS_CANOPY_PCT", "CANOPY_LOW_PCT", "CANOPY_HIGH_PCT"]


def build_zones(gdb, inputs):
    """Zones with ArcGIS's pairwise tools (a Python union of 21,743 parcels crashed the geometry engine, October 22)."""
    import arcpy
    from canopy import parcel_ownership
    g = Path(gdb)
    parcels = str(g/"parcels_classified")
    arcpy.management.CopyFeatures(inputs["parcels"], parcels)
    arcpy.management.AddFields(parcels, [["CATEGORY", "TEXT", "CATEGORY", 40], ["OWNER_GROUP", "TEXT", "OWNER_GROUP", 80],
                                         ["ALL_PARCELS", "SHORT"]])
    with arcpy.da.UpdateCursor(parcels, ["own_name", "CATEGORY", "OWNER_GROUP", "ALL_PARCELS"]) as cursor:
        for owner, *_ in cursor:
            category, group = parcel_ownership.classify(owner)
            cursor.updateRow([owner, category, group or "", 1])
    city = str(g/"city")
    arcpy.analysis.PairwiseDissolve(inputs["boundary"], city)
    pieces = []
    for name, field, where in (("by_category", "CATEGORY", None),
                               ("by_public_group", "OWNER_GROUP", "CATEGORY = 'PUBLIC_GOVERNMENT' AND OWNER_GROUP <> ''"),
                               ("all_parcels", "ALL_PARCELS", None)):
        source = parcels
        if where:
            source = arcpy.management.MakeFeatureLayer(parcels, f"{name}_layer", where)
        dissolved = str(g/f"{name}_raw")
        arcpy.analysis.PairwiseDissolve(source, dissolved, field)
        clipped = str(g/name)
        arcpy.analysis.PairwiseClip(dissolved, city, clipped)
        pieces.append((name, field, clipped))
    no_parcel = str(g/"no_parcel")
    arcpy.analysis.PairwiseErase(city, str(g/"all_parcels"), no_parcel)
    zones = str(g/"zones")
    arcpy.management.CreateFeatureclass(str(g), "zones", "POLYGON", spatial_reference=arcpy.Describe(city).spatialReference)
    arcpy.management.AddField(zones, "ZONE_ID", "TEXT", field_length=80)
    keys = []
    with arcpy.da.InsertCursor(zones, ["ZONE_ID", "SHAPE@"]) as cursor:
        def add(key, shape):
            if shape is not None and shape.area > 0:
                cursor.insertRow([key, shape])
                keys.append(key)
        for (shape,) in arcpy.da.SearchCursor(city, ["SHAPE@"]):
            add("CITY", shape)
        for name, field, fc in pieces:
            if name == "all_parcels":
                continue
            prefix = "OWNERSHIP" if name == "by_category" else "PUBLIC"
            for value, shape in arcpy.da.SearchCursor(fc, [field, "SHAPE@"]):
                add(f"{prefix}:{value}", shape)
        for (shape,) in arcpy.da.SearchCursor(no_parcel, ["SHAPE@"]):
            add("OWNERSHIP:NO_PARCEL", shape)
    return zones, keys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path)
    parser.add_argument("--resume", action="store_true",
                        help="reuse NEW_FOLDER's zones and complete tables after a crash; redo an incomplete table")
    args = parser.parse_args(argv)
    if args.out.exists() and not args.resume:
        raise FileExistsError(args.out)
    import arcpy
    from canopy import cover, licensing
    if json.loads((REBUILT/"manifest.json").read_text(encoding="utf-8")).get("status") != "complete":
        raise ValueError("The canopy rebuild is not complete")
    with licensing.extensions("Spatial"):
        run(args, arcpy, cover)


def run(args, arcpy, cover):
    gdb = str(args.out/"cover.gdb")
    zones = str(Path(gdb)/"zones")
    if args.resume and arcpy.Exists(zones):
        keys = [k for (k,) in arcpy.da.SearchCursor(zones, ["ZONE_ID"])]
        print(f"resuming with {len(keys)} zones", flush=True)
    else:
        args.out.mkdir(parents=True, exist_ok=args.resume)
        if arcpy.Exists(gdb):
            arcpy.management.Delete(gdb)
        arcpy.management.CreateFileGDB(str(args.out), "cover.gdb")
        inputs = json.loads((OCT8/"inputs.json").read_text(encoding="utf-8"))
        zones, keys = build_zones(gdb, inputs)
        print(f"{len(keys)} zones: {keys}", flush=True)
    tables = {}
    for name, chm in (("oct19", cr.OCT19/"chm_m.tif"), ("rebuilt", REBUILT/"chm_m.tif")):
        table = str(Path(gdb)/f"cover_{name}")
        if arcpy.Exists(table):
            if int(arcpy.management.GetCount(table)[0]) == len(keys):
                tables[name] = table
                print(f"cover_{name} already complete", flush=True)
                continue
            arcpy.management.Delete(table)                    # a crash left it part-written
        tables[name] = cover.summarize(str(chm), zones, "ZONE_ID", table)
        print(f"cover_{name} done", flush=True)
    rows = {name: {r[0]: dict(zip(FIELDS, r)) for r in arcpy.da.SearchCursor(t, FIELDS)} for name, t in tables.items()}
    with open(args.out/"cover-comparison.csv", "w", encoding="utf-8", newline="") as handle:
        w = csv.writer(handle)
        w.writerow(["ZONE_ID", "STATUS", "ZONE_ACRES", "COVERAGE_PCT", "OBS_CANOPY_PCT_OCT19", "OBS_CANOPY_PCT_REBUILT",
                    "CHANGE_POINTS", "CANOPY_ACRES_OCT19", "CANOPY_ACRES_REBUILT", "LOW_PCT_REBUILT", "HIGH_PCT_REBUILT"])
        for key in keys:
            a, b = rows["oct19"][key], rows["rebuilt"][key]
            change = None if a["OBS_CANOPY_PCT"] is None or b["OBS_CANOPY_PCT"] is None else round(b["OBS_CANOPY_PCT"]-a["OBS_CANOPY_PCT"], 2)
            w.writerow([key, b["COVER_STATUS"], round(b["ZONE_M2"]/4046.8564224, 1), round(b["COVERAGE_PCT"] or 0, 3),
                        round(a["OBS_CANOPY_PCT"] or 0, 2), round(b["OBS_CANOPY_PCT"] or 0, 2), change,
                        round(a["CANOPY_ACRES"], 1), round(b["CANOPY_ACRES"], 1),
                        round(b["CANOPY_LOW_PCT"] or 0, 2), round(b["CANOPY_HIGH_PCT"] or 0, 2)])
    print((args.out/"cover-comparison.csv").read_text(encoding="utf-8"), flush=True)


if __name__ == "__main__":
    main()
