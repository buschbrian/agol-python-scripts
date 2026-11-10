"""Cache the public county footprints intersecting the saved Millcreek boundary.

Uses the existing completeness-checked county fetch and projection helpers.
Native service geometry/attributes are preserved before local projection.
"""
import argparse
import json
from pathlib import Path
import sys

import arcpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from canopy import common, footprints


def main(boundary, output):
    from arcgis.gis import GIS
    destination = Path(output).resolve()
    previous = None
    if destination.exists():
        prior = destination / "footprints.json"
        previous = json.loads(prior.read_text(encoding="utf-8")) if prior.exists() else None
        if (not previous or previous["status"] != "failed" or
                (destination / "footprints.gdb").exists() or (destination / "native-response.json").exists()):
            raise FileExistsError("Use a fresh footprint output; partial datasets are retained")
    destination.mkdir(parents=True, exist_ok=True)
    record = {"status": "fetching", "started": footprints._now(), "boundary": str(boundary),
              "service": footprints.SLCO_URL, "runtime": common.runtime()}
    if previous:
        record["previous_attempt"] = previous
    manifest = destination / "footprints.json"
    common.write_json(manifest, record)
    try:
        parts = [row[0] for row in arcpy.da.SearchCursor(boundary, ["SHAPE@"])]
        city = parts[0]
        for part in parts[1:]:
            city = city.union(part)
        target = city.spatialReference
        assert target.factoryCode == 6341
        layer, _ = footprints._layer(GIS(), footprints.HOSTED["county"])
        native = footprints._native_sr(layer)
        query_transform, query_options = footprints._transformation(target, native, city.extent)
        query_city = footprints._project(city, native, query_transform)
        transform, options = footprints._transformation(native, target, query_city.extent)
        features, counts, oid = footprints._fetch_hosted(layer, "OBJECTID", [query_city.extent], native)
        common.write_json(destination / "native-response.json", {
            "wkid": native.factoryCode, "features": [
                {"attributes": dict(f.attributes), "geometry": dict(f.geometry) if f.geometry else None}
                for f in features]})
        gdb = str(destination / "footprints.gdb")
        arcpy.management.CreateFileGDB(str(destination), "footprints.gdb")
        native_fc = str(Path(gdb) / "county_native")
        skipped = footprints._write_hosted(features, layer, oid, "OBJECTID", native, native_fc)
        if skipped:
            raise ValueError(f"County response contains {skipped} footprints without polygon geometry")
        projected = str(Path(gdb) / "county_footprints")
        arcpy.management.Project(native_fc, projected, target, transform)
        removed = footprints._keep_intersecting(projected, city)
        ids = [r[0] for r in arcpy.da.SearchCursor(projected, ["SOURCE_ID"])]
        assert len(ids) == len(set(ids)) and all(v for v in ids)
        record.update(status="checking geometry", native_wkid=native.factoryCode,
            query_transform=query_transform, query_transform_options=query_options,
            transform=transform, transform_options=options, server_count=counts[0], fetched=len(features),
            removed_outside_city=removed, city_footprints=len(ids), footprints=projected,
            id_field="SOURCE_ID", source_attributes_preserved=True)
        common.write_json(manifest, record)
        check = str(Path(gdb) / "geometry_check")
        arcpy.management.CheckGeometry(projected, check, "OGC")
        problems = int(arcpy.management.GetCount(check)[0])
        if problems:
            raise ValueError(f"{problems} copied footprint geometry problems; inspect {check} before height processing")
        record.update(status="complete", finished=footprints._now(),
            native_wkid=native.factoryCode, query_transform=query_transform,
            query_transform_options=query_options, transform=transform, transform_options=options,
            server_count=counts[0], fetched=len(features), removed_outside_city=removed,
            city_footprints=len(ids), footprints=projected, id_field="SOURCE_ID",
            source_attributes_preserved=True, geometry_problems=problems,
            interpretation="Current county footprint snapshot; not established as capture-epoch geometry or reference truth")
        common.write_json(manifest, record)
        print(json.dumps(record, indent=2), flush=True)
    except BaseException as exc:
        record.update(status="failed", error=str(exc), finished=footprints._now())
        common.write_json(manifest, record)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("boundary")
    parser.add_argument("output")
    args = parser.parse_args()
    main(args.boundary, args.output)
