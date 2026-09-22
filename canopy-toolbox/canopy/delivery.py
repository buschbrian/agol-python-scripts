"""Index a LAS delivery from headers alone, with optional flight dates from a swath index.

Header bounds are rectangular screening coverage, not a verified point-support or
city-coverage footprint. Nothing here writes to the delivery or creates source-side
statistics; files are opened read-only through preparation.header.
"""
from pathlib import Path

import arcpy

from . import common, preparation

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


def index(folder, output_folder, swaths=None, date_field="DATE_D"):
    """Write a tile-bounds feature class, layer file, and JSON report for a delivery."""
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
    # Validate the swath index before creating anything, so a refusal leaves no partial output.
    matches = _swaths(swaths, date_field, spatial_reference) if swaths else None
    destination.mkdir(parents=True, exist_ok=False)
    gdb = str(destination / "delivery_index.gdb")
    arcpy.management.CreateFileGDB(str(destination), "delivery_index.gdb")
    feature_class = str(Path(gdb) / "las_tile_bounds")
    arcpy.management.CreateFeatureclass(gdb, "las_tile_bounds", "POLYGON",
                                        spatial_reference=spatial_reference)
    common.add_fields(feature_class, FIELDS)
    names = [name for name, _, _ in FIELDS]
    with arcpy.da.InsertCursor(feature_class, ["SHAPE@"] + names) as cursor:
        for row in rows:
            xmin, ymin, xmax, ymax = row["extent"]
            geometry = _rectangle(row["extent"], spatial_reference)
            area = (xmax - xmin) * (ymax - ymin)
            if area <= 0:
                raise ValueError(f"Degenerate header bounds: {row['path']}")
            values = {"TILE": Path(row["path"]).stem, "LAS_PATH": row["path"], "POINTS": row["points"],
                      "SIZE_GB": row["bytes"]/1e9, "Z_MIN_M": row["z_min"], "Z_MAX_M": row["z_max"],
                      "BOUNDS_KM2": area/1e6, "RETURNS_M2": row["points"]/area,
                      "FLIGHT_DATES": None, "FLIGHT_FIRST": None, "FLIGHT_LAST": None,
                      "SWATH_COUNT": None}
            if matches is not None:
                dates = [value for shape, value in matches if not geometry.disjoint(shape)]
                values.update(flight_summary(dates))
                row.update({key: values[key] for key in
                            ("FLIGHT_DATES", "FLIGHT_FIRST", "FLIGHT_LAST", "SWATH_COUNT")})
            cursor.insertRow([geometry] + [values[name] for name in names])
    item = arcpy.metadata.Metadata(feature_class)
    item.summary = "LAS header bounding rectangles, not a verified point-support or city-coverage footprint."
    item.description = NOTE + ("\n\n" + SWATH_NOTE if matches is not None else "")
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
    report = {"folder": str(source_root), "file_count": len(rows),
              "point_count": sum(row["points"] for row in rows),
              "bytes": sum(row["bytes"] for row in rows), "feature_class": feature_class,
              "layer_file": layer_file, "runtime": common.runtime(),
              "swath_index": {"path": str(swaths), "date_field": date_field,
                              "swaths": len(matches)} if matches is not None else None,
              "files": rows, "note": NOTE + ("\n\n" + SWATH_NOTE if matches is not None else "")}
    common.write_json(destination / "delivery-index.json", report)
    return report
