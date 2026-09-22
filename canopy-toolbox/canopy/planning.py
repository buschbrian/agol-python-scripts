"""Bounded-AOI terrain, drainage screening, and footprint height estimates.

Use classified working copies. Products are capture-epoch planning estimates,
not regulatory building heights, flood predictions, or surveyed surfaces.
"""
from pathlib import Path
import hashlib
import json

import arcpy
import numpy as np
from scipy import ndimage

from . import common, planning_metrics, rasters
from .tiling import Extent, snap_extent

MAX_CELLS = 4_000_000
WARNING = ("Unvalidated LiDAR planning estimates. Building heights are roof-minus-terrain "
           "statistics, not code-defined heights. Drainage is terrain-only screening; "
           "storm drains, culverts, rainfall, and downstream controls are not modeled.")


def _metadata(path, description):
    item = arcpy.metadata.Metadata(path)
    item.summary = WARNING
    item.description = description + "\n\n" + WARNING
    item.save()


def _array(path):
    return arcpy.RasterToNumPyArray(path, nodata_to_value=np.nan)


def _save_array(array, reference, path, nodata=-9999):
    data = np.where(np.isfinite(array), array, nodata).astype(np.float32)
    arcpy.NumPyArrayToRaster(data, arcpy.Point(reference.extent.XMin, reference.extent.YMin),
                            reference.meanCellWidth, reference.meanCellHeight, nodata).save(path)
    arcpy.management.DefineProjection(path, reference.spatialReference)
    return path


def terrain(dtm_path, output_folder, neighborhood=3.0, tpi_radius=10.0,
            drainage_area=1000.0, contour_interval=2.0, z_unit=None):
    """Preserve the source DTM, including depressions; write new derivatives."""
    from arcpy.sa import (SurfaceParameters, Hillshade, Tan, FocalStatistics, NbrCircle,
                          DeriveContinuousFlow, Fill, SetNull, Raster, Contour)
    reference, cell = common.grid(dtm_path, max_cells=MAX_CELLS)
    if not getattr(reference.spatialReference, "VCS", None) and z_unit != "metres":
        raise ValueError("DTM has no vertical units; verify heights and declare z_unit='metres'")
    for value, name in [(neighborhood, "Terrain neighborhood"), (tpi_radius, "TPI radius"),
                        (drainage_area, "Drainage area"), (contour_interval, "Contour interval")]:
        common.positive(value, name)
    if neighborhood < cell or tpi_radius < cell:
        raise ValueError("Terrain neighborhoods must be at least one raster cell")
    folder = Path(output_folder)
    folder.mkdir(parents=True, exist_ok=False)
    paths = {}

    def save(key, raster):
        path = str(folder / (key + ".tif"))
        raster.save(path)
        paths[key] = path
        return path

    with arcpy.EnvManager(scratchWorkspace=str(folder)), common.environment(dtm_path):
        slope = SurfaceParameters(dtm_path, "SLOPE", neighborhood_distance=f"{neighborhood} Meters",
                                  z_unit="METER", output_slope_measurement="DEGREE")
        save("slope_degrees", slope)
        save("slope_percent", Tan(slope * (np.pi / 180)) * 100)
        for key, parameter in [("aspect_degrees", "ASPECT"), ("profile_curvature", "PROFILE_CURVATURE"),
                               ("tangential_curvature", "TANGENTIAL_CURVATURE")]:
            save(key, SurfaceParameters(dtm_path, parameter,
                                        neighborhood_distance=f"{neighborhood} Meters", z_unit="METER"))
        save("hillshade", Hillshade(dtm_path, 315, 45, "NO_SHADOWS", 1))
        save("terrain_position_m", Raster(dtm_path) - FocalStatistics(
            dtm_path, NbrCircle(tpi_radius, "MAP"), "MEAN", "DATA"))
        direction = str(folder / "flow_direction_d8.tif")
        accumulation = DeriveContinuousFlow(dtm_path, out_flow_direction_raster=direction,
                                            flow_direction_type="D8", force_flow="NORMAL")
        save("flow_accumulation_cells", accumulation)
        paths["flow_direction_d8"] = direction
        # ArcGIS accumulation excludes the receiving cell; this area includes it.
        area = (accumulation + 1) * cell * cell
        save("contributing_area_m2", area)
        save("drainage_paths", SetNull(area < drainage_area, 1))
        # Independent diagnostic AFTER continuous flow; never route on the filled surface.
        save("depression_fill_depth_m", Fill(dtm_path) - Raster(dtm_path))
        valid = np.isfinite(_array(dtm_path))
        directions = arcpy.RasterToNumPyArray(direction, nodata_to_value=0)
        influence = planning_metrics.boundary_influence(directions, valid)
        key = "flow_boundary_influence"
        paths[key] = _save_array(np.where(valid, influence, np.nan), reference, str(folder / (key + ".tif")))
        distance = ndimage.distance_transform_edt(np.pad(valid, 1), sampling=cell)[1:-1, 1:-1]
        key = "terrain_neighborhood_complete"
        paths[key] = _save_array(np.where(valid, distance > max(neighborhood, tpi_radius), np.nan),
                                 reference, str(folder / (key + ".tif")))
        gdb = str(folder / "terrain.gdb")
        arcpy.management.CreateFileGDB(str(folder), "terrain.gdb")
        contours = str(Path(gdb) / "contours")
        Contour(dtm_path, contours, contour_interval, 0, 1)
        paths["contours"] = contours
    descriptions = {
        "aspect_degrees": "Geodesic downslope azimuth from north; flat cells use ArcGIS's -1 convention.",
        "terrain_position_m": f"Elevation minus mean terrain within {tpi_radius} m radius. Scale-dependent relief.",
        "flow_accumulation_cells": "D8 upstream cell count; unconditioned terrain, no supplied real-depression inventory.",
        "contributing_area_m2": "(Upstream cell count + receiving cell) times cell area. Not water volume or discharge.",
        "drainage_paths": f"Candidate D8 routes receiving at least {drainage_area} square metres; not mapped streams.",
        "depression_fill_depth_m": "Depth to a spill surface from an independent Fill diagnostic; not inundation depth.",
        "flow_boundary_influence": "1: downstream of AOI edge or NoData neighbor. 0 does not prove complete catchment.",
        "terrain_neighborhood_complete": "1: full maximum terrain/TPI neighborhood is inside valid terrain; 0: edge affected.",
    }
    for key, path in paths.items():
        _metadata(path, descriptions.get(key, f"Terrain product: {key}. Elevation units metres; contours every {contour_interval} m."))
    common.write_json(folder / "terrain.json", {
        "input_dtm": str(dtm_path), "cell_size_m": cell, "neighborhood_radius_m": neighborhood,
        "tpi_radius_m": tpi_radius, "drainage_threshold_m2": drainage_area,
        "contour_interval_m": contour_interval, "flow_model": "D8, NORMAL edges, no known depression dataset",
        "warning": WARNING, "outputs": paths})
    return paths


def building_heights(footprints, id_field, roof_path, dtm_path, output_gdb):
    """Analyze each footprint independently, preserving overlap and missing data.

    Roof coverage uses in-AOI footprint cell centers; AOI_PCT separately records
    the polygon's geometric fraction inside the raster.
    """
    reference, cell = common.grid(dtm_path, max_cells=MAX_CELLS)
    roof_reference, _ = common.grid(roof_path, cell, MAX_CELLS)
    if (reference.width != roof_reference.width or reference.height != roof_reference.height or
            not common.same_xy_reference(reference.spatialReference, roof_reference.spatialReference) or
            abs(reference.extent.XMin - roof_reference.extent.XMin) > cell * 1e-6 or
            abs(reference.extent.YMin - roof_reference.extent.YMin) > cell * 1e-6):
        raise ValueError("Building and terrain rasters must share the exact grid")
    info = arcpy.Describe(footprints)
    if info.shapeType != "Polygon" or not common.same_xy_reference(info.spatialReference, reference.spatialReference):
        raise ValueError("Footprints must be polygons in the terrain's horizontal CRS")
    field = next((f for f in arcpy.ListFields(footprints) if f.name == id_field), None)
    if field is None or field.type == "OID":
        raise ValueError("Choose a stored unique footprint ID field, not a regenerated ObjectID")
    ids = [r[0] for r in arcpy.da.SearchCursor(footprints, [id_field])]
    if any(v is None or str(v) == "" for v in ids) or len(ids) != len(set(ids)):
        raise ValueError("Footprint IDs must be nonempty and unique")
    target = common.output(common.geodatabase(output_gdb), "building_heights")
    numeric = ["FOOTPRINT_M2", "AOI_PCT", "ROOF_COV_PCT", "ROOF_Z50_M", "GROUND_Z50_M",
               "HEIGHT_P50_M", "HEIGHT_P95_M", "HEIGHT_MAX_M"]
    integer = ["GRID_CELLS", "ROOF_CELLS", "NEG_H_CELLS", "PARTIAL_AOI"]
    reserved = numeric + integer + ["HEIGHT_STATUS"]
    if {f.name.upper() for f in arcpy.ListFields(footprints)} & set(reserved):
        raise ValueError("Footprint input already contains output height fields")
    roof, ground = _array(roof_path), _array(dtm_path)
    arcpy.management.CopyFeatures(footprints, target)
    common.add_fields(target, [(f, "DOUBLE", None) for f in numeric] +
                      [(f, "LONG", None) for f in integer] + [("HEIGHT_STATUS", "TEXT", 160)])
    e = reference.extent
    aoi = arcpy.Polygon(arcpy.Array([arcpy.Point(x, y) for x, y in
        [(e.XMin,e.YMin), (e.XMin,e.YMax), (e.XMax,e.YMax), (e.XMax,e.YMin), (e.XMin,e.YMin)]]), reference.spatialReference)
    summaries = []
    with common.scratch() as (_, scratch_gdb), common.environment(dtm_path):
        polygon = str(Path(scratch_gdb) / "one_footprint")
        mask_path = str(Path(scratch_gdb) / "footprint_mask")
        with arcpy.da.UpdateCursor(target, ["SHAPE@", id_field] + reserved) as cursor:
            for row in cursor:
                geometry = row[0]
                clipped = geometry.intersect(aoi, 4) if geometry and geometry.area else None
                inside_area = clipped.area if clipped else 0
                area = geometry.area if geometry else 0
                mask = np.zeros(ground.shape, dtype=bool)
                if inside_area:
                    arcpy.management.CopyFeatures([clipped], polygon)
                    arcpy.conversion.PolygonToRaster(polygon, arcpy.Describe(polygon).OIDFieldName,
                                                     mask_path, "CELL_CENTER", cellsize=cell)
                    mask = arcpy.RasterToNumPyArray(mask_path, nodata_to_value=0) > 0
                    arcpy.management.Delete(mask_path)
                    arcpy.management.Delete(polygon)
                values = planning_metrics.height_summary(roof, ground, mask)
                values.update(FOOTPRINT_M2=area, AOI_PCT=100 * inside_area / area if area else 0,
                              PARTIAL_AOI=int(inside_area < area - max(1e-6, area * 1e-8)))
                flags = ["UNVALIDATED"]
                if not inside_area:
                    flags.append("OUTSIDE_AOI")
                elif not values["GRID_CELLS"]:
                    flags.append("NO_CELL_CENTERS")
                elif not values["ROOF_CELLS"]:
                    flags.append("NO_ROOF_SUPPORT")
                elif values["ROOF_COV_PCT"] < 80:
                    flags.append("LOW_ROOF_SUPPORT")
                if values["PARTIAL_AOI"]:
                    flags.append("PARTIAL_AOI")
                if values["NEG_H_CELLS"]:
                    flags.append("NEGATIVE_HEIGHT")
                values["HEIGHT_STATUS"] = ";".join(flags)
                cursor.updateRow(row[:2] + [values[f] for f in reserved])
                summaries.append({"source_id": row[1], **values})
    _metadata(target, "Roof first/single-return cell maxima (class 6) minus interpolated ground at paired cell centers. "
              "P50/P95/MAX summarize this difference. Ground median uses the same roof-supported cells. "
              "ROOF_COV_PCT is paired support / in-AOI footprint cells. Review support below 80%; this is not accuracy. "
              "Footprints retain input geometry and attributes; overlapping polygons are analyzed independently.")
    return target, summaries


def build(lasd, output_folder, extent, footprints=None, id_field=None, cell_size=.5,
          neighborhood=3, tpi_radius=10, drainage_area=1000, contour_interval=2, z_unit=None):
    """Build a new auditable pilot bundle independently of the crown workflow."""
    common.positive(cell_size, "Cell size")
    bounds = snap_extent(Extent(*extent), cell_size)
    if round(bounds.width/cell_size) * round(bounds.height/cell_size) > MAX_CELLS:
        raise ValueError("Planning pilot supports at most 4,000,000 cells; choose a smaller AOI")
    if footprints and not id_field:
        raise ValueError("A footprint ID field is required")
    preparation_path = Path(lasd).resolve().parent / "preparation.json"
    if not preparation_path.is_file():
        raise ValueError("Use a prepared working-copy LAS dataset with preparation.json")
    prepared = json.loads(preparation_path.read_text(encoding="utf-8"))
    if prepared.get("status") != "complete" or Path(prepared["working_lasd"]).resolve() != Path(lasd).resolve():
        raise ValueError("Preparation manifest must match a completed working-copy dataset")
    bx = prepared["extent"]
    if bounds.xmin < bx[0] or bounds.ymin < bx[1] or bounds.xmax > bx[2] or bounds.ymax > bx[3]:
        raise ValueError("Planning extent must stay inside prepared LAS extent")
    destination = Path(output_folder).resolve()
    if destination == preparation_path.parent or preparation_path.parent in destination.parents:
        raise ValueError("Choose a new planning folder outside the preparation folder")
    destination.mkdir(parents=True, exist_ok=False)
    state = {"status": "running", "source_id": prepared["source_id"], "preparation": str(preparation_path),
             "extent": list(bounds), "runtime": common.runtime(), "warning": WARNING,
             "parameters": {"cell_size_m": cell_size, "terrain_neighborhood_m": neighborhood,
                            "tpi_radius_m": tpi_radius, "drainage_threshold_m2": drainage_area,
                            "contour_interval_m": contour_interval, "declared_z_unit": z_unit},
             "surface_policy": {"ground_class": 2, "roof_class": 6,
                                "surface_classes": [0,1,2,3,4,5,6,9,10,11,13,14,15,16,17,20],
                                "surface_returns": rasters.VEG_RETURNS,
                                "excluded_flags": ["withheld", "overlap", "synthetic"],
                                "ground_interpolation": rasters.DTM_INTERPOLATION,
                                "surface_interpolation": rasters.DSM_INTERPOLATION},
             "quality_status": "PILOT_UNVALIDATED", "outputs": {},
             "code_sha256": hashlib.sha256(b"".join(p.read_bytes() for p in sorted(Path(__file__).parent.glob("*.py")))).hexdigest()}
    manifest = destination / "planning.json"
    common.write_json(manifest, state)
    try:
        surfaces = destination / "surfaces"
        surfaces.mkdir()
        arcpy_extent = arcpy.Extent(*list(bounds))
        with arcpy.EnvManager(scratchWorkspace=str(destination)):
            outputs = rasters.build_chm(lasd, str(surfaces), cell_size, arcpy_extent,
                                       z_unit=z_unit, source_id=prepared["source_id"])
            state["outputs"].update(outputs)
            reference, cell = common.grid(outputs["dtm"], max_cells=MAX_CELLS)
            with common.scratch() as (_, scratch_gdb), common.environment(outputs["dtm"]):
                layers = []
                try:
                    for key, codes, returns in [("ground_direct", "2", None),
                                                ("dsm_all", "0;1;2;3;4;5;6;9;10;11;13;14;15;16;17;20", rasters.VEG_RETURNS)]:
                        layer = rasters._las_layer(lasd, Path(scratch_gdb).parent.name + "_" + key, codes, returns)
                        layers.append(layer)
                        path = str(surfaces / (key + ".tif"))
                        rasters._to_raster(layer, path, rasters.DSM_INTERPOLATION, cell)
                        state["outputs"][key] = path
                    direct = np.isfinite(_array(state["outputs"]["ground_direct"]))
                    distances = ndimage.distance_transform_edt(~direct, sampling=cell) if direct.any() else np.full(direct.shape, np.nan)
                    state["outputs"]["ground_distance_m"] = _save_array(distances, reference, str(surfaces / "ground_distance_m.tif"))
                    _metadata(state["outputs"]["ground_distance_m"], "Distance to nearest cell with eligible class-2 return; support diagnostic, not vertical error.")
                    normalized = arcpy.sa.Raster(state["outputs"]["dsm_all"]) - arcpy.sa.Raster(outputs["dtm"])
                    normalized.save(str(surfaces / "surface_height_m.tif"))
                    state["outputs"]["surface_height_m"] = str(surfaces / "surface_height_m.tif")
                    _metadata(state["outputs"]["surface_height_m"], "Listed non-noise first/single-return maximum minus terrain; includes buildings and vegetation. No gap filling or negative clipping.")
                finally:
                    for layer in layers:
                        arcpy.management.Delete(layer)
            state["outputs"].update(terrain(outputs["dtm"], destination / "terrain", neighborhood,
                                             tpi_radius, drainage_area, contour_interval, "metres"))
            if footprints:
                arcpy.management.CreateFileGDB(str(destination), "planning.gdb")
                path, rows = building_heights(footprints, id_field, outputs["building"], outputs["dtm"],
                                              str(destination / "planning.gdb"))
                state["outputs"]["building_heights"] = path
                common.write_json(destination / "building-heights.json", rows)
                state["footprints"] = {"path": str(footprints), "id_field": id_field, "count": len(rows)}
        state["status"] = "complete"
    except Exception as exc:
        state.update(status="failed", error=str(exc))
        raise
    finally:
        common.write_json(manifest, state)
    return state

