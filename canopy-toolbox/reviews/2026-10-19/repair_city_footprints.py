"""Repair only invalid copied county footprints, retaining their original WKB."""
import hashlib
import json
from pathlib import Path
import sys

import arcpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from canopy import common, footprints


def main(root):
    root = Path(root).resolve()
    record_path = root/"footprints.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["status"] == "failed" and "geometry problems" in record["error"]
    gdb = root/"footprints.gdb"
    source = str(gdb/"county_footprints")
    errors = list(arcpy.da.SearchCursor(str(gdb/"geometry_check"), ["FEATURE_ID","PROBLEM"]))
    bad = {r[0] for r in errors}
    assert bad
    originals = []
    columns = [f.name for f in arcpy.ListFields(source)
               if f.type not in ("OID","Geometry") and f.name not in ("Shape_Length","Shape_Area")]
    before = {r[0]:tuple(r[1:]) for r in arcpy.da.SearchCursor(source, ["SOURCE_ID"]+columns)}
    for oid, key, wkb, area in arcpy.da.SearchCursor(source, ["OID@","SOURCE_ID","SHAPE@WKB","SHAPE@AREA"]):
        if oid in bad:
            blob = bytes(wkb)
            originals.append({"oid":oid,"source_id":key,"area":area,"wkb_hex":blob.hex(),
                              "wkb_sha256":hashlib.sha256(blob).hexdigest()})
    common.write_json(root/"geometry-before-repair.json", {"errors":errors,"records":originals})
    layer = "invalid_county_footprints"
    oid_field = arcpy.Describe(source).OIDFieldName
    arcpy.management.MakeFeatureLayer(source, layer, f"{arcpy.AddFieldDelimiters(source,oid_field)} IN ({','.join(map(str,sorted(bad)))})")
    assert int(arcpy.management.GetCount(layer)[0]) == len(bad)
    arcpy.management.CopyFeatures(layer, str(gdb/"invalid_before_repair"))
    arcpy.management.RepairGeometry(layer, "KEEP_NULL", "OGC")
    arcpy.management.Delete(layer)
    checked = str(gdb/"geometry_check_after_repair")
    arcpy.management.CheckGeometry(source, checked, "OGC")
    assert int(arcpy.management.GetCount(checked)[0]) == 0
    after = {r[0]:tuple(r[1:]) for r in arcpy.da.SearchCursor(source, ["SOURCE_ID"]+columns)}
    assert before == after
    assert all(g and g.area for (g,) in arcpy.da.SearchCursor(source, ["SHAPE@"]))
    keys = {r["source_id"] for r in originals}
    changes = []
    for key, wkb, area in arcpy.da.SearchCursor(source, ["SOURCE_ID","SHAPE@WKB","SHAPE@AREA"]):
        if key in keys:
            old = next(r for r in originals if r["source_id"] == key)
            changes.append({"source_id":key,"old_area":old["area"],"new_area":area,
                            "area_change_m2":area-old["area"],"wkb_sha256":hashlib.sha256(bytes(wkb)).hexdigest()})
    # Reconstruct projection provenance from the unchanged native snapshot and boundary.
    native = arcpy.Describe(str(gdb/"county_native")).spatialReference
    city = next(arcpy.da.SearchCursor(record["boundary"], ["SHAPE@"]))[0]
    query_transform, query_options = footprints._transformation(city.spatialReference, native, city.extent)
    query_city = footprints._project(city, native, query_transform)
    transform, options = footprints._transformation(native, city.spatialReference, query_city.extent)
    raw = json.loads((root/"native-response.json").read_text(encoding="utf-8"))
    raw_ids = {str(f["attributes"]["OBJECTID"]) for f in raw["features"]}
    native_ids = [r[0] for r in arcpy.da.SearchCursor(str(gdb/"county_native"), ["SOURCE_ID"])]
    assert len(raw_ids) == len(raw["features"]) == len(native_ids) and raw_ids == set(native_ids)
    record.update(status="complete", finished=footprints._now(), previous_error=record.pop("error"),
        native_wkid=native.factoryCode, query_transform=query_transform, query_transform_options=query_options,
        transform=transform, transform_options=options, projection_provenance_reconstructed=True,
        server_count=len(raw_ids), fetched=len(raw_ids), removed_outside_city=len(raw_ids)-len(after),
        city_footprints=len(after), footprints=source, id_field="SOURCE_ID", geometry_problems=0,
        source_attributes_preserved=True, original_geometry_backup=str(root/"geometry-before-repair.json"),
        geometry_repaired_source_ids=sorted(keys), geometry_changes=changes,
        interpretation="Current county footprint snapshot; not established as capture-epoch geometry or reference truth")
    common.write_json(record_path, record)
    print(json.dumps({k:record[k] for k in ("status","city_footprints","geometry_repaired_source_ids","geometry_changes")},indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
