"""Index a LAS delivery from headers alone, and write its per-acquisition record.

Optional inputs add flight dates from a swath index and coverage of a boundary, checked
against an official tile index. Header bounds are rectangular screening coverage, not a
verified point-support or city-coverage footprint. Nothing here writes to the delivery or
creates source-side statistics; files are opened read-only through preparation.header.
"""
from datetime import date
from pathlib import Path

import arcpy

from . import common, preparation, record

FIELDS = [("TILE", "TEXT", 80), ("LAS_PATH", "TEXT", 500), ("POINTS", "DOUBLE", None),
          ("SIZE_GB", "DOUBLE", None), ("Z_MIN_M", "DOUBLE", None), ("Z_MAX_M", "DOUBLE", None),
          ("BOUNDS_KM2", "DOUBLE", None), ("RETURNS_M2", "DOUBLE", None),
          ("FLIGHT_FIRST", "TEXT", 32), ("FLIGHT_LAST", "TEXT", 32),
          ("FLIGHT_DATES", "TEXT", 250), ("SWATH_COUNT", "LONG", None)]

NOTE = ("Header bounds are screening coverage, not a verified point-support boundary. "
        "All returns per bounding-rectangle area is not nominal pulse density. "
        "Tile Z ranges include every class and possible noise. "
        "Header creation dates are not flight dates.")

SWATH_NOTE = ("Flight dates come from swath polygons that intersect the tile's header rectangle. "
              "A swath touching the rectangle did not necessarily contribute points to every part "
              "of the tile, so treat multiple dates as the range present, not a per-point date.")


def flight_summary(dates):
    """Reduce one tile's matched swath dates to ordered, de-duplicated fields.

    ``dates`` holds one entry per intersecting swath, so its length is the swath
    count while the reported dates are unique.
    """
    unique = sorted({text for text in (str(value).strip() for value in dates if value is not None) if text})
    joined = ";".join(unique)
    if len(joined) > 250:
        raise ValueError(f"A tile matched {len(unique)} distinct dates, which exceeds the field width")
    return {"FLIGHT_DATES": joined or None, "FLIGHT_FIRST": unique[0] if unique else None,
            "FLIGHT_LAST": unique[-1] if unique else None, "SWATH_COUNT": len(dates)}


def _rectangle(extent, spatial_reference):
    xmin, ymin, xmax, ymax = extent
    corners = [(xmin, ymin), (xmin, ymax), (xmax, ymax), (xmax, ymin), (xmin, ymin)]
    return arcpy.Polygon(arcpy.Array([arcpy.Point(x, y) for x, y in corners]), spatial_reference)


def _swaths(path, date_field, spatial_reference):
    """Read swath geometry and date, refusing a different horizontal reference."""
    described = arcpy.Describe(path)
    if described.shapeType != "Polygon":
        raise ValueError("The swath index must be polygons")
    if not common.same_xy_reference(described.spatialReference, spatial_reference):
        raise ValueError("The swath index must use the delivery's horizontal coordinate reference")
    if not any(f.name == date_field for f in arcpy.ListFields(path)):
        raise ValueError(f"The swath index has no {date_field} field")
    return [(shape, value) for shape, value in
            arcpy.da.SearchCursor(path, ["SHAPE@", date_field]) if shape is not None]


def _crs(spatial_reference):
    vertical = getattr(spatial_reference, "VCS", None)
    return {"horizontal": spatial_reference.name, "horizontal_code": spatial_reference.factoryCode or None,
            "vertical": getattr(vertical, "name", None) if vertical else None,
            "vertical_code": (getattr(vertical, "factoryCode", 0) or None) if vertical else None}


def _boundary(path, spatial_reference):
    """Union a boundary's polygons in the delivery CRS, projecting with a datum transformation.

    Unlike the vendor's own indexes, a city boundary routinely arrives in another CRS and is
    used only for area accounting, so it is projected rather than refused. The source CRS and
    the transformation go into the record.
    """
    described = arcpy.Describe(path)
    if described.shapeType != "Polygon":
        raise ValueError("The boundary must be polygons")
    source = described.spatialReference
    if source is None or source.name == "Unknown" or source.type == "Unknown":
        raise ValueError("The boundary has an unknown coordinate reference; define its projection first")
    shapes = [row[0] for row in arcpy.da.SearchCursor(path, ["SHAPE@"]) if row[0] and row[0].area]
    if not shapes:
        raise ValueError("The boundary has no polygons with area")
    info = {"projected_from": None, "transformation": None}
    if not common.same_xy_reference(source, spatial_reference):
        transformation = None
        if source.GCS.datumName != spatial_reference.GCS.datumName:
            options = arcpy.ListTransformations(source, spatial_reference, described.extent)
            if not options:
                raise ValueError("No datum transformation to the delivery CRS; project the boundary first")
            transformation = options[0]
        shapes = [shape.projectAs(spatial_reference, transformation) if transformation
                  else shape.projectAs(spatial_reference) for shape in shapes]
        info = {"projected_from": f"{source.name} (EPSG {source.factoryCode})",
                "transformation": transformation}
    union = shapes[0]
    for shape in shapes[1:]:
        union = union.union(shape)
    return union, info


def _index_tiles(path, field, spatial_reference):
    """Read an official tile index, refusing a different horizontal reference."""
    described = arcpy.Describe(path)
    if described.shapeType != "Polygon":
        raise ValueError("The tile index must be polygons")
    if not common.same_xy_reference(described.spatialReference, spatial_reference):
        raise ValueError("The tile index must use the delivery's horizontal coordinate reference")
    if not any(f.name == field for f in arcpy.ListFields(path)):
        raise ValueError(f"The tile index has no {field} field")
    return [(str(name), shape) for shape, name in arcpy.da.SearchCursor(path, ["SHAPE@", field]) if shape]


def _extents_overlap(left, right):
    a, b = left.extent, right.extent
    return a.XMin < b.XMax and b.XMin < a.XMax and a.YMin < b.YMax and b.YMin < a.YMax


def _area(geometry):
    return geometry.area if geometry else 0.0


def coverage(rows, spatial_reference, boundary, tile_index=None, tile_field="Tile_Name"):
    """Share of a boundary inside the delivery's header rectangles, and the index tiles missing.

    A delivery tile holds an index tile when its header rectangle covers at least half the
    index tile's area, so matching does not depend on the two using the same names. Index
    tiles that touch the boundary only along an edge are not counted.
    """
    city, info = _boundary(boundary, spatial_reference)
    rectangles = {row["tile"]: _rectangle(row["extent"], spatial_reference) for row in rows}
    footprint = None
    for rectangle in rectangles.values():
        footprint = rectangle if footprint is None else footprint.union(rectangle)
    covered = _area(city.intersect(footprint, 4))
    result = {"boundary": str(boundary), "boundary_m2": city.area, "covered_m2": covered,
              "covered_pct": 100 * covered / city.area, **info,
              "outside": sorted(name for name, shape in rectangles.items() if shape.disjoint(city)),
              "tile_index": None}
    if tile_index:
        touching = in_hand = 0
        missing = []
        for name, shape in _index_tiles(tile_index, tile_field, spatial_reference):
            if shape.disjoint(city):
                continue
            inside = _area(shape.intersect(city, 4))
            if inside <= 0:
                continue
            touching += 1
            if any(_area(shape.intersect(rectangle, 4)) >= .5 * shape.area
                   for rectangle in rectangles.values() if _extents_overlap(shape, rectangle)):
                in_hand += 1
            else:
                missing.append({"tile": name, "boundary_m2": inside, "share_pct": 100 * inside / city.area})
        result["tile_index"] = {"path": str(tile_index), "field": tile_field, "touching": touching,
                                "in_hand": in_hand,
                                "missing": sorted(missing, key=lambda m: (-m["boundary_m2"], m["tile"]))}
    return result


def index(folder, output_folder, swaths=None, date_field="DATE_D", boundary=None,
          tile_index=None, tile_field="Tile_Name", label=None):
    """Write a tile-bounds feature class, layer file, JSON report, and acquisition record.

    Everything is read and validated before the output folder exists, so a refusal leaves
    no partial output.
    """
    if tile_index and not boundary:
        raise ValueError("A tile index is compared against a boundary; supply a boundary too")
    paths = sorted(Path(folder).rglob("*.las"))
    if not paths:
        raise ValueError("No uncompressed LAS files found; LAZ is not read by the direct header reader")
    source_root = Path(folder).resolve()
    destination = Path(output_folder).resolve()
    if destination == source_root or source_root in destination.parents:
        raise ValueError("Write the index outside the delivery directory")
    rows = [preparation.header(path) for path in paths]
    references = {row.get("wkt") for row in rows}
    if len(references) != 1:
        raise ValueError(f"The delivery mixes {len(references)} coordinate references; index each separately")
    if not rows[0].get("wkt"):
        raise ValueError("LAS headers carry no coordinate reference; index them only after confirming one")
    spatial_reference = arcpy.SpatialReference()
    spatial_reference.loadFromString(rows[0]["wkt"])
    for row in rows:
        xmin, ymin, xmax, ymax = row["extent"]
        if (xmax - xmin) * (ymax - ymin) <= 0:
            raise ValueError(f"Degenerate header bounds: {row['path']}")
        row["tile"] = Path(row["path"]).stem
    names = [row["tile"] for row in rows]
    if len(set(names)) != len(names):
        raise ValueError("Tile file names repeat across folders; index each folder separately")

    matches = _swaths(swaths, date_field, spatial_reference) if swaths else None
    if matches is not None:
        for row in rows:
            geometry = _rectangle(row["extent"], spatial_reference)
            row.update(flight_summary([value for shape, value in matches if not geometry.disjoint(shape)]))
    covered = coverage(rows, spatial_reference, boundary, tile_index, tile_field) if boundary else None
    swath_info = ({"path": str(swaths), "date_field": date_field, "swaths": len(matches)}
                  if matches is not None else None)
    acquisition = record.build(rows, label or Path(folder).name, folder, _crs(spatial_reference),
                               date.today().isoformat(), swath_info, covered)

    destination.mkdir(parents=True, exist_ok=False)
    gdb = str(destination / "delivery_index.gdb")
    arcpy.management.CreateFileGDB(str(destination), "delivery_index.gdb")
    feature_class = str(Path(gdb) / "las_tile_bounds")
    arcpy.management.CreateFeatureclass(gdb, "las_tile_bounds", "POLYGON",
                                        spatial_reference=spatial_reference)
    common.add_fields(feature_class, FIELDS)
    fields = [name for name, _, _ in FIELDS]
    with arcpy.da.InsertCursor(feature_class, ["SHAPE@"] + fields) as cursor:
        for row in rows:
            xmin, ymin, xmax, ymax = row["extent"]
            area = (xmax - xmin) * (ymax - ymin)
            values = {"TILE": row["tile"], "LAS_PATH": row["path"], "POINTS": row["points"],
                      "SIZE_GB": row["bytes"]/1e9, "Z_MIN_M": row["z_min"], "Z_MAX_M": row["z_max"],
                      "BOUNDS_KM2": area/1e6, "RETURNS_M2": row["points"]/area}
            values.update({key: row.get(key) for key in
                           ("FLIGHT_DATES", "FLIGHT_FIRST", "FLIGHT_LAST", "SWATH_COUNT")})
            cursor.insertRow([_rectangle(row["extent"], spatial_reference)] + [values[name] for name in fields])
    note = NOTE + ("\n\n" + SWATH_NOTE if matches is not None else "")
    item = arcpy.metadata.Metadata(feature_class)
    item.summary = "LAS header bounding rectangles, not a verified point-support or city-coverage footprint."
    item.description = note
    item.save()
    # The layer name is session state, so clear it before and after rather than colliding
    # with an earlier index built in the same Python process.
    layer_name = f"LiDAR delivery - {len(rows)} LAS bounds"
    if arcpy.Exists(layer_name):
        arcpy.management.Delete(layer_name)
    layer = arcpy.management.MakeFeatureLayer(feature_class, layer_name)[0]
    layer_file = str(destination / "delivery-index.lyrx")
    try:
        arcpy.management.SaveToLayerFile(layer, layer_file, "ABSOLUTE")
    finally:
        arcpy.management.Delete(layer)
    common.write_json(destination / "acquisition.json", acquisition)
    (destination / "acquisition-facts.md").write_text(record.render(acquisition), encoding="utf-8")
    report = {"folder": str(source_root), "file_count": len(rows),
              "point_count": sum(row["points"] for row in rows),
              "bytes": sum(row["bytes"] for row in rows), "feature_class": feature_class,
              "layer_file": layer_file, "record": str(destination / "acquisition.json"),
              "facts": str(destination / "acquisition-facts.md"), "runtime": common.runtime(),
              "swath_index": swath_info, "coverage": covered, "files": rows, "note": note}
    common.write_json(destination / "delivery-index.json", report)
    return report
