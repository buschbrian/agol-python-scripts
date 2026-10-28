r"""Publish-ready copies of the small feature layers (hosting plan step 2, October 22, 2026; projected October 23).

    python reviews/2026-10-22/hosting/feature-layers/prepare_features.py OUT

ArcGIS Pro Python (PYTHONNOUSERSITE=1). Read-only on the October 22 library; writes OUT\work.gdb (EPSG 6341),
OUT\features.gdb (Web Mercator, the file to publish) and OUT\features.json.
Nothing is uploaded: publishing them as hosted feature layers is Brian's step.
- buildings: the 22,042 county footprints with their consensus roof-height statistics (buildings.gdb/building_heights),
  without the county's editor-tracking fields, with heights also in feet and readable field aliases.
- canopy_cover_zones: the 13 cover zones (cover.gdb/zones) with the October 22 cover figures (cover-comparison.csv).
Both carry the estimate warning in their metadata. Both are projected to Web Mercator with
WGS_1984_(ITRF08)_To_NAD_1983_2011, the transformation every other hosted package carries (hosting/tiles README, Datum),
so ArcGIS Online never chooses one. Checks at the end: counts, every copied value equal to the library's, and every
projected shape equal to Esri's own projection of the source with that transformation (and not without it).
"""
import argparse
import csv
import datetime
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[4]
sys.path.insert(0, str(TOOLBOX))
from canopy.lidar_root import lidar_root  # noqa: E402

LIB = lidar_root()/"2023-salt-lake-valley"/"runs"/"millcreek-products-20261022"
BUILDINGS = LIB/"buildings.gdb"/"building_heights"
ZONES = LIB/"cover.gdb"/"zones"
COVER_CSV = LIB/"cover-comparison.csv"
FEET = 3.280839895
TRANSFORM = "WGS_1984_(ITRF08)_To_NAD_1983_2011"
WEB_MERCATOR = 3857
DROP = ("GlobalID", "CreationDate", "Creator", "EditDate", "Editor")
ALIASES = {
    "SOURCE_ID": "County building ID", "ADDRESS": "Address", "PARCEL_ID": "Parcel ID", "BuildType": "Building type",
    "BLDGHEIGHT": "County height field", "BuiltYear": "Year built", "FOOTPRINT_M2": "Footprint area (m2)",
    "ROOF_COV_PCT": "Roof support (% of footprint cells)", "ROOF_Z50_M": "Median roof elevation (m, NAVD88)",
    "GROUND_Z50_M": "Median ground elevation (m, NAVD88)", "HEIGHT_P50_M": "Median roof height (m)",
    "HEIGHT_P95_M": "95th percentile roof height (m)", "HEIGHT_MAX_M": "Maximum roof height (m)",
    "HEIGHT_P50_FT": "Median roof height (ft)", "HEIGHT_P95_FT": "95th percentile roof height (ft)",
    "HEIGHT_STATUS": "Height flags", "NEG_H_CELLS": "Cells with roof below terrain",
}
ZONE_FIELDS = (("ZONE_NAME", "TEXT", "Zone"), ("ZONE_ACRES", "DOUBLE", "Zone area (acres)"),
               ("OBSERVED_PCT", "DOUBLE", "Lidar coverage (% observed)"),
               ("CANOPY_PCT", "DOUBLE", "Canopy cover (% of observed area)"),
               ("CANOPY_LOW_PCT", "DOUBLE", "Canopy cover, low bound (%)"),
               ("CANOPY_HIGH_PCT", "DOUBLE", "Canopy cover, high bound (%)"),
               ("CANOPY_ACRES", "DOUBLE", "Canopy (acres)"), ("CANOPY_PCT_OCT19", "DOUBLE", "Canopy cover, October 19 (%)"))
NAMES = {"CITY": "Millcreek (whole city)", "OWNERSHIP:PRIVATE": "Private parcels",
         "OWNERSHIP:PUBLIC_GOVERNMENT": "Public / government parcels", "OWNERSHIP:UNKNOWN_OWNER": "Uncertain owner",
         "OWNERSHIP:NO_PARCEL": "No parcel (streets, rights-of-way)", "PUBLIC:FEDERAL": "Federal",
         "PUBLIC:MILLCREEK": "Millcreek (city-owned)", "PUBLIC:PUBLIC_DISTRICT": "Public districts",
         "PUBLIC:PUBLIC_HOUSING": "Public housing", "PUBLIC:PUBLIC_SCHOOL": "Public schools",
         "PUBLIC:SALT_LAKE_CITY": "Salt Lake City", "PUBLIC:SALT_LAKE_COUNTY": "Salt Lake County",
         "PUBLIC:STATE_OF_UTAH": "State of Utah"}


def buildings(gdb):
    import arcpy
    out = str(gdb/"buildings")
    arcpy.management.CopyFeatures(str(BUILDINGS), out)
    arcpy.management.DeleteField(out, [f.name for f in arcpy.ListFields(out) if f.name in DROP])
    for name in ("HEIGHT_P50_FT", "HEIGHT_P95_FT"):
        arcpy.management.AddField(out, name, "DOUBLE")
    with arcpy.da.UpdateCursor(out, ["HEIGHT_P50_M", "HEIGHT_P95_M", "HEIGHT_P50_FT", "HEIGHT_P95_FT"]) as cursor:
        for p50, p95, _, _ in cursor:
            cursor.updateRow([p50, p95, None if p50 is None else round(p50*FEET, 2),
                              None if p95 is None else round(p95*FEET, 2)])
    for name, alias in ALIASES.items():
        if arcpy.ListFields(out, name):
            arcpy.management.AlterField(out, name, new_field_alias=alias)
    return out


def zones(gdb):
    import arcpy
    cover = {r["ZONE_ID"]: r for r in csv.DictReader(open(COVER_CSV, newline="", encoding="utf-8"))}
    out = str(gdb/"canopy_cover_zones")
    arcpy.management.CopyFeatures(str(ZONES), out)
    for name, kind, alias in ZONE_FIELDS:
        arcpy.management.AddField(out, name, kind, field_alias=alias, field_length=60 if kind == "TEXT" else None)
    keys = ("ZONE_ACRES", "COVERAGE_PCT", "OBS_CANOPY_PCT_REBUILT", "LOW_PCT_REBUILT", "HIGH_PCT_REBUILT",
            "CANOPY_ACRES_REBUILT", "OBS_CANOPY_PCT_OCT19")
    with arcpy.da.UpdateCursor(out, ["ZONE_ID"] + [f[0] for f in ZONE_FIELDS]) as cursor:
        for row in cursor:
            c = cover[row[0]]
            cursor.updateRow([row[0], NAMES[row[0]]] + [float(c[k]) for k in keys])
    return out


def metadata(path, text):
    from canopy import planning
    planning._metadata(path, text)


def check(gdb):
    """Counts and every copied value equal the library's."""
    import arcpy
    out = {}
    src_fields = [f.name for f in arcpy.ListFields(str(BUILDINGS)) if f.type not in ("Geometry", "OID", "GlobalID")
                  and f.name not in DROP and not f.name.startswith("Shape_")]
    src = {r[0]: r for r in arcpy.da.SearchCursor(str(BUILDINGS), ["SOURCE_OID"] + src_fields + ["SHAPE@WKB"])}
    dst = {r[0]: r for r in arcpy.da.SearchCursor(str(gdb/"buildings"), ["SOURCE_OID"] + src_fields + ["SHAPE@WKB"])}
    out["buildings"] = {"source": len(src), "copied": len(dst), "rows_differing": sum(1 for k in src if src[k] != dst.get(k)),
                        "with_height": sum(1 for r in dst.values() if r[src_fields.index("HEIGHT_P50_M")+1] is not None)}
    cover = {r["ZONE_ID"]: r for r in csv.DictReader(open(COVER_CSV, newline="", encoding="utf-8"))}
    rows = list(arcpy.da.SearchCursor(str(gdb/"canopy_cover_zones"), ["ZONE_ID", "CANOPY_PCT", "ZONE_ACRES"]))
    out["canopy_cover_zones"] = {"zones": len(rows), "csv_rows": len(cover),
                                 "values_differing": sum(1 for z, p, a in rows if (p, a) != (
                                     float(cover[z]["OBS_CANOPY_PCT_REBUILT"]), float(cover[z]["ZONE_ACRES"])))}
    return out


def project(work, gdb, name):
    import arcpy
    arcpy.env.geographicTransformations = None
    out = str(gdb/name)
    arcpy.management.Project(str(work/name), out, arcpy.SpatialReference(WEB_MERCATOR), TRANSFORM)
    return out


def projection_check(work, gdb, name):
    """Each output shape against the work shape projected by Esri's engine with the transformation and without it: the
    largest vertex distance per feature (vertex counts must agree), then the largest over all features."""
    import arcpy
    merc = arcpy.SpatialReference(WEB_MERCATOR)
    arcpy.env.geographicTransformations = None
    src = {r[0]: r[1] for r in arcpy.da.SearchCursor(str(work/name), ["OID@", "SHAPE@"])}
    worst = {"transformed": 0.0, "untransformed_min": None}
    vertex_mismatch = 0
    for oid, shape in arcpy.da.SearchCursor(str(gdb/name), ["OID@", "SHAPE@"]):
        source = src[oid]
        a = [(q.X, q.Y) for part in shape for q in part if q]
        for key, transformation in (("transformed", TRANSFORM), ("untransformed", None)):
            ref = source.projectAs(merc, transformation) if transformation else source.projectAs(merc)
            b = [(q.X, q.Y) for part in ref for q in part if q]
            if len(a) != len(b):
                vertex_mismatch += 1
                continue
            d = max(((x1 - x2)**2 + (y1 - y2)**2)**0.5 for (x1, y1), (x2, y2) in zip(a, b))
            if key == "transformed":
                worst["transformed"] = max(worst["transformed"], d)
            else:
                worst["untransformed_min"] = d if worst["untransformed_min"] is None else min(worst["untransformed_min"], d)
    fields = [f.name for f in arcpy.ListFields(str(work/name)) if f.type not in ("Geometry", "OID")
              and not f.name.startswith("Shape_")]
    before = {r[0]: r[1:] for r in arcpy.da.SearchCursor(str(work/name), ["OID@"] + fields)}
    after = {r[0]: r[1:] for r in arcpy.da.SearchCursor(str(gdb/name), ["OID@"] + fields)}
    return {"features": len(src), "projected": len(after), "attribute_rows_differing": sum(
                1 for k in before if before[k] != after.get(k)),
            "wkid": arcpy.Describe(str(gdb/name)).spatialReference.factoryCode,
            "max_vertex_distance_m_vs_transformed": round(worst["transformed"], 6),
            "min_vertex_distance_m_vs_untransformed": round(worst["untransformed_min"], 4),
            "vertex_count_mismatches": vertex_mismatch,
            "metadata_warning": "planning estimate" in (arcpy.metadata.Metadata(str(gdb/name)).summary or "").lower()}


def main(argv=None):
    import arcpy
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out", type=Path)
    a = p.parse_args(argv)
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    work = Path(arcpy.management.CreateFileGDB(str(out), "work.gdb")[0])
    gdb = Path(arcpy.management.CreateFileGDB(str(out), "features.gdb")[0])
    text = {}
    b = buildings(work)
    text["buildings"] = ("County building footprints with lidar roof-height statistics from the October 22 consensus roofs "
                "(2 of 3 sources). Heights are roof minus interpolated terrain, cell by cell; not code-defined building "
                "heights. HEIGHT_STATUS flags missing or low roof support and negative heights.")
    z = zones(work)
    text["canopy_cover_zones"] = ("Canopy cover by ownership zone, October 22 lidar canopy (canopy at least 2 m as a share of observed "
                "cells). Low and high bounds count unobserved cells as no canopy or all canopy.")
    outputs = {}
    for name in ("buildings", "canopy_cover_zones"):
        metadata(str(work/name), text[name])
        outputs[name] = project(work, gdb, name)
        metadata(outputs[name], text[name] + " Projected to Web Mercator with " + TRANSFORM + ".")
    checks = check(work)
    checks["projection"] = {name: projection_check(work, gdb, name) for name in outputs}
    result = {"schema": "hosting-features/2", "created": datetime.datetime.now().isoformat(timespec="seconds"),
              "sources": {"buildings": str(BUILDINGS), "zones": str(ZONES), "cover": str(COVER_CSV)},
              "work_6341": {"buildings": b, "canopy_cover_zones": z}, "outputs": outputs,
              "coordinate_system": f"WGS 1984 Web Mercator (auxiliary sphere), EPSG {WEB_MERCATOR}",
              "transformation": TRANSFORM, "dropped_fields": list(DROP), "checks": checks}
    (out/"features.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result["checks"], indent=1))


if __name__ == "__main__":
    main()
