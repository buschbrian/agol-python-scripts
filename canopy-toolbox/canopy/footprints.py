"""Fetch reference building footprints for bounded extents into one geodatabase (EPSG:6341).

Hosted layers are read with the ArcGIS API for Python using ArcGIS Pro's sign-in, in their
own coordinate system, and projected locally with an explicit, recorded datum
transformation. Current OpenStreetMap buildings can be added from saved Overpass JSON or
from a small number of serial Overpass requests. Nothing is fetched outside the requested
extents plus the buffer. Every source keeps its own identifier in SOURCE_ID.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
import shutil
import time

import arcpy

from . import common

TARGET_WKID = 6341
SLCO_URL = "https://services1.arcgis.com/DJP723NX3ukQ2LtF/arcgis/rest/services/SLCo_BuildingFootprints/FeatureServer/0"
# Hosted sources. "coverage" says where a source claims to be complete:
#   tiles    - the source covers every requested extent (county-wide service)
#   boundary - clipped to the Millcreek municipal boundary
#   extent   - the layer's published full extent (a rectangle, not a verified footprint)
HOSTED = {
    "county": {"url": SLCO_URL, "id_field": "OBJECTID", "coverage": "tiles",
               "label": "Salt Lake County Surveyor building footprints (SLCo_BuildingFootprints)"},
    "millcreek_extract": {"item": "be996310ecaf4429b944154a0f8fc4d9", "layer": 0, "id_field": "OBJECTID_1",
                          "coverage": "boundary",
                          "label": "Salt Lake County Building Footprints (Extracted), Millcreek org item"},
    "osm2024": {"item": "de2f77dfb7164139a4f45b06fdb94439", "layer": 0, "id_field": "F_id",
                "coverage": "boundary", "label": "Millcreek Building Footprints (OSM Extract - June 2024)"},
    "lidar_same_method": {"item": "3ed9411f660c46a5ae69c9ecac56116c", "layer": 0, "id_field": "OBJECTID",
                          "coverage": "extent",
                          "label": "Building Footprint LiDAR (Classify LAS Building -> raster -> polygon); SAME METHOD, not independent"},
}
BOUNDARY = {"item": "875130c9316e49fb941263f311650d92", "layer": 0, "label": "Millcreek Municipal Boundary"}
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_MAX_REQUESTS = 3
OVERPASS_AGENT = ("canopy-toolbox/0.1 (Millcreek UT lidar building reconciliation; bounded one-off "
                  "building footprint pull; python-requests)")
FIELD_TYPES = {"esriFieldTypeString": "TEXT", "esriFieldTypeInteger": "LONG", "esriFieldTypeSmallInteger": "SHORT",
               "esriFieldTypeDouble": "DOUBLE", "esriFieldTypeSingle": "FLOAT", "esriFieldTypeDate": "DATE",
               "esriFieldTypeGlobalID": "TEXT", "esriFieldTypeGUID": "TEXT"}
SKIP_FIELDS = {"Shape__Area", "Shape__Length", "Shape_STAr", "Shape_STLe", "Shape__Area_2", "Shape__Length_2"}


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _rectangle(extent, sr):
    xmin, ymin, xmax, ymax = extent
    points = [(xmin, ymin), (xmin, ymax), (xmax, ymax), (xmax, ymin), (xmin, ymin)]
    return arcpy.Polygon(arcpy.Array([arcpy.Point(x, y) for x, y in points]), sr)


def _transformation(source, target, extent=None):
    """First transformation arcpy lists when datums differ; (chosen, options) for the record.

    extent (an arcpy.Extent in the source reference) orders the list by suitability for
    the area. Choices here move coordinates by up to about 1 m, so the reconcile step
    also measures the offset between each source and the lidar roofs.
    """
    if source.GCS.datumName == target.GCS.datumName:
        return None, []
    options = arcpy.ListTransformations(source, target, extent) if extent else arcpy.ListTransformations(source, target)
    if not options:
        raise ValueError(f"No datum transformation from {source.name} to {target.name}")
    return options[0], list(options[:8])


def _project(shape, target, transformation):
    return shape.projectAs(target, transformation) if transformation else shape.projectAs(target)


def _layer(gis, spec):
    from arcgis.features import FeatureLayer
    if "url" in spec:
        return FeatureLayer(spec["url"], gis), None
    item = gis.content.get(spec["item"])
    if item is None:
        raise ValueError(f"Item {spec['item']} is not visible to the signed-in user")
    return item.layers[spec["layer"]], item


def _native_sr(layer):
    ref = layer.properties.extent.spatialReference
    return arcpy.SpatialReference(ref.get("latestWkid") or ref["wkid"])


def _fetch_hosted(layer, id_field, envelopes, native):
    """Object IDs per envelope (checked against a server count), then features by ID."""
    oid_field = layer.properties.objectIdField
    ids = set()
    per_extent = []
    for envelope in envelopes:
        geometry = {"xmin": envelope.XMin, "ymin": envelope.YMin, "xmax": envelope.XMax, "ymax": envelope.YMax,
                    "spatialReference": {"wkid": native.factoryCode}}
        from arcgis.geometry.filters import intersects
        found = layer.query(geometry_filter=intersects(geometry), return_ids_only=True)["objectIds"] or []
        count = layer.query(geometry_filter=intersects(geometry), return_count_only=True)
        if count != len(found):
            raise RuntimeError(f"Server count {count} disagrees with {len(found)} returned IDs")
        per_extent.append(len(found))
        ids.update(found)
    ids = sorted(ids)
    batch = int(layer.properties.get("maxRecordCount") or 1000)
    batch = max(1, min(batch, 500))
    features = []
    for start in range(0, len(ids), batch):
        part = ids[start:start+batch]
        result = layer.query(object_ids=",".join(map(str, part)), out_fields="*", return_geometry=True)
        features.extend(result.features)
    if len(features) != len(ids):
        raise RuntimeError(f"Fetched {len(features)} features for {len(ids)} IDs")
    if len({f.attributes[oid_field] for f in features}) != len(ids):
        raise RuntimeError("Duplicate or missing object IDs in fetched features")
    return features, per_extent, oid_field


def _create(gdb, name, sr, fields):
    arcpy.management.CreateFeatureclass(gdb, name, "POLYGON", spatial_reference=sr)
    path = str(Path(gdb)/name)
    for field, kind, length in fields:
        arcpy.management.AddField(path, field, kind, field_length=length)
    return path


def _hosted_fields(layer, oid_field):
    fields, names = [("SOURCE_ID", "TEXT", 40), ("SOURCE_OID", "LONG", None)], []
    for field in layer.properties.fields:
        if field.name == oid_field or field.name in SKIP_FIELDS or field.type not in FIELD_TYPES:
            continue
        reserved = ("SOURCE_ID", "SOURCE_OID", "OBJECTID", "OID", "FID", "SHAPE")
        name = field.name + "_SRC" if field.name.upper() in reserved else field.name
        kind = FIELD_TYPES[field.type]
        length = min(int(field.get("length") or 255), 2000) if kind == "TEXT" else None
        if field.type in ("esriFieldTypeGlobalID", "esriFieldTypeGUID"):
            length = 38
        fields.append((name, kind, length))
        names.append((field.name, name, kind))
    return fields, names


def _value(value, kind):
    if value is None:
        return None
    if kind == "DATE":
        return datetime.datetime.fromtimestamp(value/1000, datetime.timezone.utc).replace(tzinfo=None)
    return value


def _write_hosted(features, layer, oid_field, id_field, native, path_native):
    fields, names = _hosted_fields(layer, oid_field)
    gdb, name = str(Path(path_native).parent), Path(path_native).name
    _create(gdb, name, native, fields)
    columns = ["SHAPE@", "SOURCE_ID", "SOURCE_OID"] + [target for _, target, _ in names]
    skipped = 0
    with arcpy.da.InsertCursor(path_native, columns) as cursor:
        for feature in features:
            geometry = dict(feature.geometry or {})
            if not geometry.get("rings"):
                skipped += 1
                continue
            geometry["spatialReference"] = {"wkid": native.factoryCode}
            shape = arcpy.AsShape(geometry, True)
            attributes = feature.attributes
            source_id = attributes.get(id_field)
            cursor.insertRow([shape, None if source_id is None else str(source_id), attributes.get(oid_field)] +
                             [_value(attributes.get(original), kind) for original, _, kind in names])
    return skipped


def _keep_intersecting(path, area):
    removed = 0
    with arcpy.da.UpdateCursor(path, ["SHAPE@"]) as cursor:
        for (shape,) in cursor:
            if shape is None or shape.disjoint(area):
                cursor.deleteRow()
                removed += 1
    return removed


# --- OpenStreetMap -------------------------------------------------------------------------

def _stitch(segments):
    """Join open member ways into closed rings; returns (rings, leftovers)."""
    pending, rings = [list(s) for s in segments if len(s) > 1], []
    while pending:
        current = pending.pop()
        while current[0] != current[-1]:
            for i, segment in enumerate(pending):
                if segment[0] == current[-1]:
                    current += segment[1:]
                elif segment[-1] == current[-1]:
                    current += segment[::-1][1:]
                elif segment[-1] == current[0]:
                    current = segment[:-1] + current
                elif segment[0] == current[0]:
                    current = segment[::-1][:-1] + current
                else:
                    continue
                pending.pop(i)
                break
            else:
                return rings, [current] + pending
        rings.append(current)
    return rings, []


def osm_polygons(document):
    """Overpass `out meta geom` JSON to (records, skipped); geometry is lon/lat rings."""
    records, skipped = [], []
    for element in document.get("elements", []):
        kind, tags = element.get("type"), element.get("tags", {})
        if kind == "way":
            ring = [(g["lon"], g["lat"]) for g in element.get("geometry", []) if g]
            if len(ring) < 4 or ring[0] != ring[-1]:
                skipped.append((kind, element["id"], "open way"))
                continue
            outer, inner = [ring], []
        elif kind == "relation":
            if tags.get("type") != "multipolygon":
                skipped.append((kind, element["id"], f"type={tags.get('type')}"))
                continue
            members = [m for m in element.get("members", []) if m.get("type") == "way" and m.get("geometry")]
            ring = lambda m: [(g["lon"], g["lat"]) for g in m["geometry"] if g]
            outer, left_out = _stitch([ring(m) for m in members if m.get("role") in ("outer", "")])
            inner, left_in = _stitch([ring(m) for m in members if m.get("role") == "inner"])
            if left_out or left_in or not outer:
                skipped.append((kind, element["id"], "unclosed ring (members clipped or incomplete)"))
                continue
        else:
            continue
        records.append({"osm_id": f"{kind}/{element['id']}", "timestamp": element.get("timestamp"),
                        "version": element.get("version"), "building": tags.get("building"),
                        "levels": tags.get("building:levels"), "height": tags.get("height"),
                        "start_date": tags.get("start_date"), "source_tag": tags.get("source"),
                        "outer": outer, "inner": inner})
    return records, skipped


def overpass_query(bbox):
    south, west, north, east = bbox
    return (f"[out:json][timeout:60][maxsize:67108864];\n(\n  way[\"building\"]({south},{west},{north},{east});\n"
            f"  relation[\"building\"]({south},{west},{north},{east});\n);\nout meta geom;")


def _overpass(bbox, path):
    import requests
    response = requests.post(OVERPASS_URL, data={"data": overpass_query(bbox)},
                             headers={"User-Agent": OVERPASS_AGENT}, timeout=120)
    response.raise_for_status()
    Path(path).write_bytes(response.content)
    return {"http_status": response.status_code, "bytes": len(response.content)}


def _wgs_bbox(extent, sr):
    """S, W, N, E of a projected rectangle's corners (densified edges)."""
    wgs = arcpy.SpatialReference(4326)
    transformation, _ = _transformation(sr, wgs, _rectangle(extent, sr).extent)
    shape = _project(_rectangle(extent, sr).densify("DISTANCE", 50, 1), wgs, transformation)
    e = shape.extent
    return [round(e.YMin, 6), round(e.XMin, 6), round(e.YMax, 6), round(e.XMax, 6)]


def _bbox_polygon(bbox):
    south, west, north, east = bbox
    return _rectangle((west, south, east, north), arcpy.SpatialReference(4326)).densify("DISTANCE", .0005, .0001)


def _write_osm(records, path_native):
    wgs = arcpy.SpatialReference(4326)
    gdb, name = str(Path(path_native).parent), Path(path_native).name
    fields = [("SOURCE_ID", "TEXT", 40), ("OSM_ID", "TEXT", 40), ("OSM_TIMESTAMP", "TEXT", 24), ("OSM_VERSION", "LONG", None),
              ("BUILDING", "TEXT", 64), ("LEVELS", "TEXT", 16), ("HEIGHT_TAG", "TEXT", 16),
              ("START_DATE", "TEXT", 24), ("SOURCE_TAG", "TEXT", 255)]
    _create(gdb, name, wgs, fields)
    with arcpy.da.InsertCursor(path_native, ["SHAPE@"] + [f for f, _, _ in fields]) as cursor:
        for r in records:
            parts = arcpy.Array([arcpy.Array([arcpy.Point(x, y) for x, y in ring]) for ring in r["outer"] + r["inner"]])
            cursor.insertRow([arcpy.Polygon(parts, wgs), r["osm_id"], r["osm_id"], r["timestamp"], r["version"],
                              r["building"], r["levels"], r["height"], r["start_date"], r["source_tag"]])


# --- main ----------------------------------------------------------------------------------

def fetch(output_folder, extents, buffer=50.0, osm_files=(), overpass=False, names=None):
    """Write reference.gdb (one feature class per source, EPSG:6341) and reference.json.

    extents: projected EPSG:6341 rectangles (xmin, ymin, xmax, ymax), normally LAS tiles.
    osm_files: (path, [south, west, north, east]) Overpass JSON already fetched for a bbox.
    overpass: request current OSM for each extent not inside a supplied bbox (serial, capped).
    """
    common.positive(buffer, "Buffer", allow_zero=True)
    extents = [tuple(float(v) for v in e) for e in extents]
    if not extents or any(len(e) != 4 or e[0] >= e[2] or e[1] >= e[3] for e in extents):
        raise ValueError("Give at least one extent as xmin ymin xmax ymax")
    names = list(names or [f"extent{i+1}" for i in range(len(extents))])
    destination = Path(output_folder).resolve()
    gdb = destination/"reference.gdb"
    if gdb.exists() or (destination/"reference.json").exists():
        raise FileExistsError(f"Reference output already exists: {gdb}")
    destination.mkdir(parents=True, exist_ok=True)
    target = arcpy.SpatialReference(TARGET_WKID)
    buffered = [(e[0]-buffer, e[1]-buffer, e[2]+buffer, e[3]+buffer) for e in extents]
    area = None
    for extent in buffered:
        rectangle = _rectangle(extent, target)
        area = rectangle if area is None else area.union(rectangle)
    record = {"created": _now(), "target_wkid": TARGET_WKID, "buffer_m": buffer,
              "extents": dict(zip(names, extents)), "query_extents": dict(zip(names, buffered)),
              "runtime": common.runtime(), "sources": {}, "coverage": {}}
    arcpy.management.CreateFileGDB(str(destination), "reference.gdb")
    try:
        _fetch_all(record, destination, gdb, target, names, extents, buffered, area, osm_files, overpass)
    except Exception as exc:
        record["status"] = "failed"; record["error"] = str(exc)
        common.write_json(destination/"reference.json", record)
        raise
    record["status"] = "complete"
    common.write_json(destination/"reference.json", record)
    return record


def _fetch_all(record, destination, gdb, target, names, extents, buffered, area, osm_files, overpass):
    from arcgis.gis import GIS
    gis = GIS("pro")
    record["portal_user"] = getattr(gis.users.me, "username", None)
    with common.scratch() as (_, scratch_gdb):
        # Coverage boundary first; clipped sources are compared with it.
        layer, item = _layer(gis, BOUNDARY)
        native = _native_sr(layer)
        transformation, options = _transformation(native, target, area.extent.projectAs(native))
        features = layer.query(where="1=1", out_fields="*", return_geometry=True).features
        if len(features) != 1:
            raise RuntimeError(f"Expected one boundary polygon, found {len(features)}")
        geometry = dict(features[0].geometry); geometry["spatialReference"] = {"wkid": native.factoryCode}
        boundary = _project(arcpy.AsShape(geometry, True), target, transformation)
        boundary_fc = _create(str(gdb), "millcreek_boundary", target, [("NAME", "TEXT", 64), ("UPDATED", "DATE", None)])
        with arcpy.da.InsertCursor(boundary_fc, ["SHAPE@", "NAME", "UPDATED"]) as cursor:
            cursor.insertRow([boundary, features[0].attributes.get("NAME"),
                              _value(features[0].attributes.get("UPDATED"), "DATE")])
        record["boundary"] = {"item": BOUNDARY["item"], "title": item.title, "owner": item.owner,
                              "modified": _value(item.modified, "DATE"), "url": layer.url,
                              "native_wkid": native.factoryCode, "transformation": transformation,
                              "transformation_options": options, "fetched": _now(),
                              "area_km2": boundary.area/1e6,
                              "updated_attribute": _value(features[0].attributes.get("UPDATED"), "DATE"),
                              "share_of_each_query_extent_inside": {
                                  n: boundary.intersect(_rectangle(e, target), 4).area/_rectangle(e, target).area
                                  for n, e in zip(names, buffered)}}
        coverage_rows = []
        for name, spec in HOSTED.items():
            layer, item = _layer(gis, spec)
            native = _native_sr(layer)
            transformation, options = _transformation(native, target, area.extent.projectAs(native))
            inverse, _ = _transformation(target, native, area.extent)
            envelopes = [_project(_rectangle(e, target).densify("DISTANCE", 50, 1), native, inverse).extent
                         for e in buffered]
            started = _now()
            features, per_extent, oid_field = _fetch_hosted(layer, spec["id_field"], envelopes, native)
            native_fc = str(Path(scratch_gdb)/(name + "_native"))
            skipped = _write_hosted(features, layer, oid_field, spec["id_field"], native, native_fc)
            output = str(gdb/name)
            arcpy.management.Project(native_fc, output, target, transformation or "")
            removed = _keep_intersecting(output, area)
            count = int(arcpy.management.GetCount(output)[0])
            info = {"label": spec["label"], "url": layer.url, "item": spec.get("item"),
                    "title": item.title if item else layer.properties.name,
                    "owner": item.owner if item else None,
                    "item_modified": _value(item.modified, "DATE") if item else None,
                    "data_last_edit": _value((layer.properties.get("editingInfo") or {}).get("dataLastEditDate"), "DATE"),
                    "native_wkid": native.factoryCode, "transformation": transformation,
                    "transformation_options": options, "id_field": spec["id_field"], "object_id_field": oid_field,
                    "server_ids_per_extent": dict(zip(names, per_extent)), "fetched_features": len(features),
                    "skipped_without_geometry": skipped, "removed_outside_query_area": removed, "count": count,
                    "query_envelopes_native": [[e.XMin, e.YMin, e.XMax, e.YMax] for e in envelopes],
                    "fetch_started": started, "fetch_finished": _now(), "coverage": spec["coverage"]}
            if spec["coverage"] == "boundary":
                outside = sum(1 for (shape,) in arcpy.da.SearchCursor(output, ["SHAPE@"])
                              if shape and not boundary.contains(shape.labelPoint))
                info["features_with_label_point_outside_boundary"] = outside
                coverage_rows.append((name, boundary.intersect(area, 4), "Millcreek municipal boundary (clipped source)"))
            elif spec["coverage"] == "tiles":
                coverage_rows.append((name, area, "County-wide service; the requested extents are inside Salt Lake County"))
            else:
                e = layer.properties.extent
                full = _project(_rectangle((e["xmin"], e["ymin"], e["xmax"], e["ymax"]), native).densify("DISTANCE", 100, 1),
                                target, transformation)
                coverage_rows.append((name, full.intersect(area, 4), "Published layer extent rectangle; not a verified coverage"))
            record["sources"][name] = info
        # Current OpenStreetMap: saved files first, then (optionally) capped serial requests.
        osm_dir = destination/"osm"
        osm_inputs = []
        for path, bbox in osm_files:
            osm_dir.mkdir(exist_ok=True)
            copy = osm_dir/("supplied_" + Path(path).name)
            if copy.exists():
                raise FileExistsError(f"Saved OSM copy already exists: {copy}")
            shutil.copy2(path, copy)
            osm_inputs.append((copy, [float(v) for v in bbox], f"supplied ({Path(path).resolve()})"))
        requests_made = []
        if overpass:
            for name, extent in zip(names, extents):
                bbox = _wgs_bbox(extent, target)
                # About 2 m of tolerance: a saved bbox may have been computed without a datum shift.
                tol = 2e-5
                covered = any(b[0] <= bbox[0]+tol and b[1] <= bbox[1]+tol and b[2] >= bbox[2]-tol and b[3] >= bbox[3]-tol
                              for _, b, _ in osm_inputs)
                if covered:
                    continue
                if len(requests_made) >= OVERPASS_MAX_REQUESTS:
                    raise RuntimeError(f"More than {OVERPASS_MAX_REQUESTS} Overpass requests would be needed")
                query_bbox = _wgs_bbox(buffered[names.index(name)], target)
                osm_dir.mkdir(exist_ok=True)
                path = osm_dir/f"overpass_{name}.json"
                if requests_made:
                    time.sleep(10)
                started = _now()
                result = _overpass(query_bbox, path)
                requests_made.append({"extent": name, "bbox": query_bbox, "requested": started, **result})
                osm_inputs.append((path, query_bbox, "requested"))
        if osm_inputs:
            records, skipped, seen, files = [], [], set(), []
            for path, bbox, how in osm_inputs:
                document = json.loads(Path(path).read_text(encoding="utf-8"))
                found, bad = osm_polygons(document)
                skipped.extend(bad)
                new = [r for r in found if r["osm_id"] not in seen]
                seen.update(r["osm_id"] for r in new)
                records.extend(new)
                files.append({"path": str(path), "bbox_swne": bbox, "how": how,
                              "osm_base": (document.get("osm3s") or {}).get("timestamp_osm_base"),
                              "elements": len(document.get("elements", [])), "polygons": len(found)})
            native = arcpy.SpatialReference(4326)
            transformation, options = _transformation(native, target, area.extent.projectAs(native))
            native_fc = str(Path(scratch_gdb)/"osm_current_native")
            _write_osm(records, native_fc)
            output = str(gdb/"osm_current")
            arcpy.management.Project(native_fc, output, target, transformation or "")
            removed = _keep_intersecting(output, area)
            kept = [row for row in arcpy.da.SearchCursor(output, ["SOURCE_TAG", "OSM_TIMESTAMP"])]
            record["sources"]["osm_current"] = {
                "label": "OpenStreetMap buildings from Overpass (current at osm_base time)", "files": files,
                "overpass_requests_this_run": requests_made, "user_agent": OVERPASS_AGENT,
                "native_wkid": 4326, "transformation": transformation, "transformation_options": options,
                "polygons": len(records), "skipped": skipped[:50], "skipped_count": len(skipped),
                "removed_outside_query_area": removed,
                "count": len(kept), "microsoft_source_tag": sum(1 for s, _ in kept if s and "microsoft" in s.lower()),
                "coverage": "bbox", "licence": "ODbL; (c) OpenStreetMap contributors"}
            osm_area = None
            for _, bbox, _ in osm_inputs:
                shape = _project(_bbox_polygon(bbox), target, transformation)
                osm_area = shape if osm_area is None else osm_area.union(shape)
            coverage_rows.append(("osm_current", osm_area.intersect(area, 4), "Overpass query bounding boxes"))
        coverage = _create(str(gdb), "coverage", target, [("SOURCE", "TEXT", 32), ("BASIS", "TEXT", 255)])
        with arcpy.da.InsertCursor(coverage, ["SHAPE@", "SOURCE", "BASIS"]) as cursor:
            for name, shape, basis in coverage_rows:
                cursor.insertRow([shape, name, basis])
                record["coverage"][name] = {"basis": basis, "area_km2": shape.area/1e6}
    for name in list(record["sources"]) + ["coverage", "millcreek_boundary"]:
        item = arcpy.metadata.Metadata(str(gdb/name))
        item.summary = "Reference building footprints copied for lidar reconciliation; not verified by this toolbox."
        item.description = ("Fetched for bounded extents and projected to EPSG:6341. See reference.json for the "
                            "source, query extent, count, fetch time, and datum transformation.")
        item.save()
