"""Canopy cover with explicit observation coverage and full-zone bounds."""
from __future__ import annotations

import math
import os

import arcpy

from . import common
from .tiling import Extent, snap_extent


def summarize(chm_path, zones, zone_field, out_table, min_height=2.0, cell_size=None):
    from arcpy.sa import Con, Raster, ZonalStatisticsAsTable
    common.positive(min_height, "Minimum tree height")
    raster, resolution = common.grid(chm_path, cell_size)
    workspace = common.geodatabase(os.path.dirname(out_table))
    common.output(workspace, os.path.basename(out_table))
    describe = arcpy.Describe(zones)
    if describe.shapeType != "Polygon":
        raise ValueError("Zone features must be polygons")
    if not common.same_xy_reference(describe.spatialReference, raster.spatialReference):
        raise ValueError("Project zone polygons to the CHM spatial reference first")
    if zone_field not in {field.name for field in arcpy.ListFields(zones)}:
        raise ValueError("Zone field does not exist")
    geometries = {}
    with arcpy.da.SearchCursor(zones, [zone_field, "SHAPE@"]) as cursor:
        for value, shape in cursor:
            if value is None or not str(value).strip() or shape is None or shape.area <= 0:
                raise ValueError("Zones require nonempty IDs and nonempty polygon geometry")
            key = str(value)
            geometries[key] = shape if key not in geometries else geometries[key].union(shape)
    arcpy.management.CreateTable(workspace, os.path.basename(out_table))
    common.add_fields(out_table, [("ZONE_ID", "TEXT", 512), ("COVER_STATUS", "TEXT", 32)] + [
        (name, "DOUBLE", None) for name in [
            "CANOPY_M2", "CANOPY_ACRES", "ZONE_M2", "GRID_M2", "OBSERVED_M2", "MISSING_M2",
            "COVERAGE_PCT", "CANOPY_PCT", "OBS_CANOPY_PCT", "CANOPY_LOW_PCT", "CANOPY_HIGH_PCT"]])
    output_fields = ["ZONE_ID", "COVER_STATUS", "CANOPY_M2", "CANOPY_ACRES", "ZONE_M2", "GRID_M2",
                     "OBSERVED_M2", "MISSING_M2", "COVERAGE_PCT", "CANOPY_PCT", "OBS_CANOPY_PCT",
                     "CANOPY_LOW_PCT", "CANOPY_HIGH_PCT"]
    with common.scratch() as (_, scratch_gdb), common.environment(chm_path):
        binary_path = os.path.join(scratch_gdb, "binary")
        Con(Raster(chm_path) >= min_height, 1, 0).save(binary_path)
        with arcpy.da.InsertCursor(out_table, output_fields) as cursor:
            for index, (key, geometry) in enumerate(geometries.items()):
                # Each unique zone is processed separately, so overlapping IDs do not compete.
                feature = os.path.join(scratch_gdb, f"zone_{index}")
                with arcpy.EnvManager(extent=None):
                    arcpy.management.CopyFeatures([geometry], feature)
                oid = arcpy.Describe(feature).OIDFieldName
                bounds = geometry.extent
                bounds = snap_extent(Extent(bounds.XMin, bounds.YMin, bounds.XMax, bounds.YMax),
                                     resolution, (raster.extent.XMin, raster.extent.YMin))
                zone_raster = os.path.join(scratch_gdb, f"grid_{index}")
                stats = os.path.join(scratch_gdb, f"stats_{index}")
                with arcpy.EnvManager(extent=bounds.as_arcpy_string()):
                    arcpy.conversion.PolygonToRaster(feature, oid, zone_raster, "CELL_CENTER",
                                                     cellsize=resolution)
                    arcpy.management.BuildRasterAttributeTable(zone_raster, "Overwrite")
                    total = sum(row[0] for row in arcpy.da.SearchCursor(zone_raster, ["COUNT"]))
                    if total:
                        ZonalStatisticsAsTable(zone_raster, "Value", binary_path, stats, "DATA", "SUM")
                        stats_rows = list(arcpy.da.SearchCursor(stats, ["COUNT", "SUM"]))
                    else:
                        stats_rows = []
                observed = sum(row[0] or 0 for row in stats_rows)
                canopy = sum(row[1] or 0 for row in stats_rows)
                if observed > total:
                    raise RuntimeError("Observed cell count exceeds zone grid coverage")
                missing = total-observed
                cell_area = resolution**2
                observed_pct = 100*canopy/observed if observed else None
                status = "COMPLETE" if total and not missing else ("PARTIAL" if observed else "NO_DATA")
                if not total:
                    status = "NO_CELL_CENTERS"
                cursor.insertRow([
                    key, status, canopy*cell_area, canopy*cell_area/4046.8564224, geometry.area,
                    total*cell_area, observed*cell_area, missing*cell_area,
                    100*observed/total if total else None,
                    observed_pct if status == "COMPLETE" else None, observed_pct,
                    100*canopy/total if total else None, 100*(canopy+missing)/total if total else None,
                ])
    common.metadata(out_table, (
        "Cell-center area estimates. ZONE_M2 is polygon area; GRID_M2 is its rasterized area. "
        "CANOPY_PCT is null for incomplete coverage; OBS_CANOPY_PCT uses observed cells only. "
        "LOW/HIGH bounds reflect missing coverage, not statistical confidence intervals."
    ))
    return out_table
