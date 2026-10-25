r"""The three-way hybrid with roof attributes, packaged as a scene layer (October 24, 2026): the candidate to replace the public LOD1.2.

    python reviews/2026-10-23/lod2-check/build_v2_package.py CITY_DIR OUT

ArcGIS Pro Python with 3D Analyst (PYTHONNOUSERSITE=1). Read-only on CITY_DIR (a roofer_city.py run through its `hybrid` stage);
writes OUT\\v2.gdb, OUT\\roof\\ (roof_attributes.py's tables), OUT\\buildings_hybrid_v2.slpk, its validation report, OUT\\fields.md
(the new fields, for the item's data dictionary) and OUT\\v2.json. Nothing is uploaded.
- Starts from CITY_DIR\\hybrid.gdb\\buildings_three_way: one feature per building, from roofer, Esri LOD2.0 or Esri LOD1.2 (LEVEL).
- Adds roof attributes (roof_attributes.py) to the buildings that come from roofer: roof planes, areas, slopes, azimuth, ridge,
  eave and building height above ground, flat and south, east, west and north-facing area, snag counts. They are empty on the
  buildings that fall back to Esri's levels, so LEVEL says whether they apply.
- Packaged as make_slpk.py does (WGS84, the ITRF08 transformation named, Desktop profile) and validated.
"""
import csv
import importlib.util
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve()


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ra = _load("roof_attributes", HERE.parent/"roof_attributes.py")
slpk_mod = _load("make_slpk", HERE.parents[2]/"2026-10-22"/"hosting"/"scene-layers"/"make_slpk.py")

# name, type, alias, description
FIELDS = [
    ("ROOF_PLANES", "LONG", "Roof planes", "Roof planes of 1 m2 or more in plan, from the lidar roof (roofer)"),
    ("ROOF_PLAN_M2", "DOUBLE", "Roof area in plan (m2)", "Area of those planes seen from above"),
    ("ROOF_AREA_M2", "DOUBLE", "Roof surface area (m2)", "True (sloped) area of those planes"),
    ("ROOF_SLOPE_MEAN", "DOUBLE", "Mean roof slope (degrees)", "Slope from horizontal, weighted by plane area"),
    ("ROOF_SLOPE_MAIN", "DOUBLE", "Main plane slope (degrees)", "Slope of the largest plane"),
    ("ROOF_AZIMUTH_MAIN", "DOUBLE", "Main plane azimuth (degrees)", "Compass bearing of the largest plane's downslope direction (0 north, clockwise); empty if flat"),
    ("RIDGE_HT_M", "DOUBLE", "Ridge height above ground (m)", "Highest roof point minus the building's ground elevation"),
    ("EAVE_HT_M", "DOUBLE", "Lowest roof height above ground (m)", "Lowest roof point minus the building's ground elevation"),
    ("BLDG_HT_M", "DOUBLE", "Building height (m)", "Same as the ridge height: highest roof point above the building's ground"),
    ("FLAT_AREA_M2", "DOUBLE", "Flat roof area (m2)", "Surface area of planes under 5 degrees"),
    ("SOUTH_AREA_M2", "DOUBLE", "South-facing roof area (m2)", "Surface area of planes of 5 to 70 degrees facing 135 to 225 degrees"),
    ("EAST_AREA_M2", "DOUBLE", "East-facing roof area (m2)", "Same, facing 45 to 135 degrees"),
    ("WEST_AREA_M2", "DOUBLE", "West-facing roof area (m2)", "Same, facing 225 to 315 degrees"),
    ("NORTH_AREA_M2", "DOUBLE", "North-facing roof area (m2)", "Same, facing 315 to 45 degrees"),
    ("RF_VOLUME_M3", "DOUBLE", "Model volume (m3)", "Volume of roofer's LoD 2.2 solid"),
    ("TINY_FACES", "LONG", "Tiny roof faces", "Roof faces under 0.5 m2 in plan (quality screening)"),
    ("SLIVER_FACES", "LONG", "Sliver roof faces", "Roof faces narrower than about 0.4 m (quality screening)"),
    ("STEEP_FACES", "LONG", "Steep roof faces", "Roof faces steeper than 75 degrees (quality screening)"),
]
ALIASES = {"LEVEL": "Model used", "CHECK_VERDICT": "Check against the lidar", "ROOFER_VERDICT": "Roofer's check",
           "ESRI_VERDICT": "Esri LOD2.0's check", "FALLBACK_REASON": "Why not roofer", "LOD20_GROUND_PCT": "Share of footprint at ground (%)"}


def summarize_packaged_roofs(rows, selected_ids):
    """Only count the roofer models actually retained in the hybrid package."""
    selected = [rows[fid] for fid in sorted(selected_ids)]
    fields = {"roof_area_m2_total": "ROOF_AREA_M2", "flat_area_m2": "FLAT_AREA_M2",
              "south_area_m2": "SOUTH_AREA_M2", "east_area_m2": "EAST_AREA_M2",
              "west_area_m2": "WEST_AREA_M2", "north_area_m2": "NORTH_AREA_M2"}
    return {"buildings": len(selected),
            "roof_planes": sum(int(r["ROOF_PLANES_ALL"]) for r in selected),
            **{name: round(math.fsum(float(r[field]) for r in selected), 1)
               for name, field in fields.items()}}


def main(city_dir, out):
    import arcpy
    arcpy.CheckOutExtension("3D")
    city_dir, out = Path(city_dir), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    summary = ra.compute(city_dir/"convert"/"roofer.city.json", out/"roof")
    rows = {int(r["FP_ID"]): r for r in csv.DictReader(open(out/"roof"/"building_roofs.csv", encoding="utf-8"))}
    gdb = out/"v2.gdb"
    if arcpy.Exists(str(gdb)):
        arcpy.management.Delete(str(gdb))
    arcpy.management.CreateFileGDB(str(out), gdb.name)
    fc = str(gdb/"buildings")
    arcpy.management.CopyFeatures(str(city_dir/"hybrid.gdb"/"buildings_three_way"), fc)
    have = {f.name for f in arcpy.ListFields(fc)}
    for name, kind, alias, _ in FIELDS:
        if name not in have:
            arcpy.management.AddField(fc, name, kind, field_alias=alias)
    for name, alias in ALIASES.items():
        if name in have:
            arcpy.management.AlterField(fc, name, new_field_alias=alias)
    names = [f[0] for f in FIELDS]
    selected_ids = set()
    with arcpy.da.UpdateCursor(fc, ["FP_ID", "LEVEL"]+names) as cursor:
        for fid, level, *_ in cursor:
            if level != "roofer LoD2.2":
                continue
            r = rows[fid]
            values = []
            for name, kind, _, _ in FIELDS:
                v = r.get(name)
                values.append(None if v in (None, "", "None") else (int(float(v)) if kind == "LONG" else float(v)))
            cursor.updateRow([fid, level]+values)
            selected_ids.add(fid)
    ids = [r[0] for r in arcpy.da.SearchCursor(fc, ["FP_ID"])]
    slpk = out/"buildings_hybrid_v2.slpk"
    slpk.unlink(missing_ok=True)
    with arcpy.EnvManager(scratchWorkspace=str(out)):
        arcpy.management.Create3DObjectSceneLayerPackage(fc, str(slpk), arcpy.SpatialReference(4326), slpk_mod.TRANSFORM, "Desktop")
    report = out/"v2-validation.json"
    report.unlink(missing_ok=True)
    arcpy.management.ValidateSceneLayerPackage(str(slpk), str(report))
    stats = slpk_mod.package_stats(str(slpk))
    record = {"slpk": str(slpk), "mb": round(slpk.stat().st_size/2**20, 1), "features": len(ids), "unique_fp_ids": len(set(ids)),
              "buildings_with_roof_attributes": len(selected_ids), "package": stats,
              "fp_id_stats_equal_source": (stats["fp_id_count"], stats["fp_id_sum"]) == (len(ids), sum(ids)),
              "fields": [f.name for f in arcpy.ListFields(fc)],
              "roof_attributes": summarize_packaged_roofs(rows, selected_ids),
              "all_roofer_roof_attributes": summary,
              "validation_messages": json.loads(report.read_text(encoding="utf-8")).get("Messages")}
    (out/"v2.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    with open(out/"fields.md", "w", encoding="utf-8") as f:
        f.write("| Field | Meaning |\n|---|---|\n")
        for name, kind, alias, desc in FIELDS:
            f.write(f"| {name} | {desc}. Empty where LEVEL is not roofer LoD2.2. |\n")
        for name, alias in ALIASES.items():
            if name in have:
                f.write(f"| {name} | {alias} |\n")
    print(json.dumps({k: record[k] for k in ("mb", "features", "unique_fp_ids", "buildings_with_roof_attributes",
                                              "fp_id_stats_equal_source", "validation_messages")}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
