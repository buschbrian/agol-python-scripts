"""Optional roof-edge refinement on new LAS copies, with auditable roof models.

Derived polygons describe rasterized roof support, not surveyed wall footprints.
Height gates reduce lateral clipping of nearby vegetation, but do not prove class.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import struct

import arcpy
import numpy as np
from scipy import ndimage

from . import common, preparation, rasters
from .tiling import Extent, snap_extent

MAX_CELLS = 4_000_000


def _records(path, mode="r"):
    info = preparation.header(path)
    fmt = info["format"]
    if not 0 <= fmt <= 10:
        raise ValueError("Unsupported LAS point format")
    modern = fmt >= 6
    with open(path, "rb") as handle:
        head = handle.read(227)
    scale = np.array(struct.unpack_from("<3d", head, 131))
    offset = np.array(struct.unpack_from("<3d", head, 155))
    if not np.isfinite(scale).all() or not (scale > 0).all() or not np.isfinite(offset).all():
        raise ValueError("LAS scales and offsets must be finite; scales must be positive")
    if info["offset"] + info["points"]*info["record_length"] > Path(path).stat().st_size:
        raise ValueError("Truncated LAS point records")
    dtype = np.dtype({
        "names": ["x", "y", "z", "flags", "classification"],
        "formats": ["<i4", "<i4", "<i4", "u1", "u1"],
        "offsets": [0, 4, 8, 15, 16 if modern else 15],
        "itemsize": info["record_length"],
    })
    points = np.memmap(path, dtype=dtype, offset=info["offset"], shape=(info["points"],), mode=mode)
    return points, scale, offset, modern


def _models(roof, ground, cell, xmin, ymax, min_area):
    support = np.isfinite(roof)
    # Only bridge one-cell gaps. Large courtyards remain holes.
    connected = ndimage.binary_closing(support, structure=np.ones((3, 3))) | support
    regions, count = ndimage.label(connected, structure=np.ones((3, 3)))
    models = {}
    for label, box in enumerate(ndimage.find_objects(regions), 1):
        local = regions[box] == label
        rows, cols = np.nonzero(local & support[box])
        rows, cols = rows+box[0].start, cols+box[1].start
        if len(rows)*cell**2 < min_area:
            regions[box][local] = 0
            continue
        x, y = xmin+(cols+.5)*cell, ymax-(rows+.5)*cell
        z = roof[rows, cols]
        origin = np.array([x.mean(), y.mean()])
        matrix = np.column_stack((x-origin[0], y-origin[1], np.ones(len(x))))
        keep = np.ones(len(x), dtype=bool)
        coefficients = np.array([0., 0., np.median(z)])
        for _ in range(8):
            if keep.sum() < 3 or np.linalg.matrix_rank(matrix[keep]) < 3:
                break
            coefficients = np.linalg.lstsq(matrix[keep], z[keep], rcond=None)[0]
            residual = z-matrix@coefficients
            cutoff = min(.5, max(.15, 3*1.4826*np.median(np.abs(residual-np.median(residual)))))
            updated = np.abs(residual) <= cutoff
            if np.array_equal(updated, keep):
                break
            keep = updated
        rank_ok = keep.sum() >= 3 and np.linalg.matrix_rank(matrix[keep]) == 3
        if rank_ok:
            coefficients = np.linalg.lstsq(matrix[keep], z[keep], rcond=None)[0]
        residual = z-matrix@coefficients
        rmse = float(np.sqrt(np.mean(residual[keep]**2))) if keep.any() else None
        fraction = float(keep.mean())
        ok = bool(rank_ok and fraction >= .8 and rmse <= .15 and np.hypot(*coefficients[:2]) < .25)
        heights = z-ground[rows, cols]
        heights = heights[np.isfinite(heights)]
        models[label] = {
            "origin": origin.tolist(), "plane": coefficients.tolist(), "fit_rmse_m": rmse,
            "inlier_fraction": fraction, "model_ok": ok,
            "area_m2": float(local.sum()*cell**2), "roof_z_m": float(np.median(z)),
            "roof_height_m": float(np.median(heights)) if heights.size else None,
            "partial_aoi": bool(box[0].start == 0 or box[1].start == 0 or
                                box[0].stop == roof.shape[0] or box[1].stop == roof.shape[1]),
        }
    return regions, models


def _classify_copy(path, regions, models, cell, xmin, ymax, edge_distance, below, above, audit_path):
    """Change only classification bytes; preserve coordinates, returns, flags, and all other bytes."""
    points, scale, offset, modern = _records(path, "r+")
    if regions.any():
        distance, index = ndimage.distance_transform_edt(regions == 0, sampling=cell, return_indices=True)
        nearest = regions[tuple(index)]
    else:
        distance = np.full(regions.shape, np.inf)
        nearest = np.zeros(regions.shape, dtype=np.int32)
    changed_indices, old_codes = [], []
    height, width = regions.shape
    counts = {label: 0 for label in models}
    for start in range(0, len(points), 1_000_000):
        block = points[start:start+1_000_000]
        codes = block["classification"] if modern else block["classification"] & 31
        eligible = np.isin(codes, [3, 4, 5]) & ((block["flags"] & (13 if modern else 160)) == 0)
        candidates = np.flatnonzero(eligible)
        x = block["x"][candidates]*scale[0]+offset[0]
        y = block["y"][candidates]*scale[1]+offset[1]
        z = block["z"][candidates]*scale[2]+offset[2]
        cols, rows = np.floor((x-xmin)/cell).astype(int), np.floor((ymax-y)/cell).astype(int)
        valid = (cols >= 0) & (cols < width) & (rows >= 0) & (rows < height)
        candidates, x, y, z, rows, cols = [value[valid] for value in (candidates, x, y, z, rows, cols)]
        near = distance[rows, cols] <= edge_distance
        for label, model in models.items():
            if not model["model_ok"]:
                continue
            a, b, c = model["plane"]
            ox, oy = model["origin"]
            residual = z-((x-ox)*a+(y-oy)*b+c)
            selected = candidates[near & (nearest[rows, cols] == label) &
                                  (residual >= -below) & (residual <= above)]
            if not selected.size:
                continue
            changed_indices.append(selected+start)
            old_codes.append(block["classification"][selected].copy())
            block["classification"][selected] = 6 if modern else (block["classification"][selected] & 224) | 6
            counts[label] += len(selected)
    points.flush()
    del block, points
    np.savez_compressed(audit_path,
                        point_index=np.concatenate(changed_indices) if changed_indices else np.array([], dtype=np.int64),
                        previous_class_byte=np.concatenate(old_codes) if old_codes else np.array([], dtype=np.uint8))
    return counts


def refine(prepared_lasd, output_folder, cell_size=.5, edge_distance=1.0, below_roof=.35, above_roof=3.0,
           min_roof_area=25.0):
    """Fit supported low-slope roofs, then refine eligible vegetation on new point files.

    Experimental opt-in: retain an unchanged input, per-point change logs, model
    diagnostics, and polygons for visual inspection before accepting the result.
    """
    for value, label in [(cell_size, "Cell size"), (min_roof_area, "Minimum roof area")]:
        common.positive(value, label)
    for value, label in [(edge_distance, "Roof edge distance"), (below_roof, "Below-roof tolerance"),
                         (above_roof, "Above-roof tolerance")]:
        common.positive(value, label, allow_zero=True)
    input_root = Path(prepared_lasd).resolve().parent
    manifest = input_root/"preparation.json"
    if not manifest.is_file():
        raise ValueError("Use a prepared working-copy LAS dataset with preparation.json")
    previous = json.loads(manifest.read_text(encoding="utf8"))
    if previous["status"] != "complete" or Path(previous["working_lasd"]).resolve() != Path(prepared_lasd).resolve():
        raise ValueError("Preparation manifest does not match a completed LAS dataset")
    destination = Path(output_folder).resolve()
    if destination == input_root or input_root in destination.parents:
        raise ValueError("Choose a new refinement folder outside the input preparation")
    if destination.exists():
        raise FileExistsError("Refinement output already exists")
    files = sorted((input_root/"points").glob("*.las"))
    if not files:
        raise ValueError("Prepared point files were not found")
    inputs = [preparation.header(path) for path in files]
    sr = common.metric_reference(arcpy.Describe(str(prepared_lasd)).spatialReference)
    info = rasters.audit(str(prepared_lasd))
    if not info["has_building"] or not info["has_ground"]:
        raise ValueError("Roof refinement needs classified buildings and ground")
    bounds = snap_extent(Extent(*previous["extent"]), cell_size)
    if round(bounds.width/cell_size)*round(bounds.height/cell_size) > MAX_CELLS:
        raise ValueError("Roof refinement supports at most 4,000,000 cells per review AOI")
    destination.mkdir(parents=True)
    output_lasd = str(destination/"prepared.lasd")
    state = {"status": "modeling", "working_lasd": output_lasd, "extent": list(bounds),
             "source_id": previous["source_id"], "sources": previous.get("sources", []),
             "input_preparation": str(manifest), "input_files": inputs, "runtime": common.runtime(),
             "parameters": {"cell_size_m": cell_size, "edge_distance_m": edge_distance,
                            "below_roof_m": below_roof, "above_roof_m": above_roof,
                            "min_roof_area_m2": min_roof_area, "min_inlier_fraction": .8,
                            "max_fit_rmse_m": .15, "max_slope": .25},
             "quality_status": "EXPERIMENTAL_UNVALIDATED"}
    out_manifest = destination/"preparation.json"
    common.write_json(out_manifest, state)
    try:
        layers = []
        with common.scratch() as (_, scratch_gdb):
            token = Path(scratch_gdb).parent.name
            try:
                with arcpy.EnvManager(extent=bounds.as_arcpy_string(), cellSize=cell_size, snapRaster=None,
                                      outputCoordinateSystem=sr, mask=None, parallelProcessingFactor="0"):
                    ground_layer = rasters._las_layer(prepared_lasd, token+"_ground", "2", None)
                    layers.append(ground_layer)
                    ground_path = str(destination/"ground.tif")
                    rasters._to_raster(ground_layer, ground_path, rasters.DTM_INTERPOLATION, cell_size)
                with common.environment(ground_path):
                    roof_layer = rasters._las_layer(prepared_lasd, token+"_roof", "6", rasters.VEG_RETURNS)
                    layers.append(roof_layer)
                    roof_path = str(destination/"roof_elevation.tif")
                    rasters._to_raster(roof_layer, roof_path, rasters.DSM_INTERPOLATION, cell_size)
                    roof = arcpy.RasterToNumPyArray(roof_path, nodata_to_value=np.nan)
                    ground = arcpy.RasterToNumPyArray(ground_path, nodata_to_value=np.nan)
                    reference, resolution = common.grid(ground_path, cell_size, MAX_CELLS)
                    regions, models = _models(roof, ground, resolution, reference.extent.XMin,
                                              reference.extent.YMax, min_roof_area)
                    gdb = str(destination/"roof_review.gdb")
                    arcpy.management.CreateFileGDB(str(destination), "roof_review.gdb")
                    outlines = str(Path(gdb)/"roof_outlines")
                    if regions.any():
                        label_path = str(Path(scratch_gdb)/"roof_ids")
                        arcpy.NumPyArrayToRaster(regions, arcpy.Point(reference.extent.XMin, reference.extent.YMin),
                                                resolution, resolution, 0).save(label_path)
                        arcpy.management.DefineProjection(label_path, sr)
                        parts = str(Path(scratch_gdb)/"parts")
                        arcpy.conversion.RasterToPolygon(label_path, parts, "NO_SIMPLIFY", "VALUE")
                        arcpy.management.Dissolve(parts, outlines, "gridcode", multi_part="MULTI_PART")
                    else:
                        arcpy.management.CreateFeatureclass(gdb, "roof_outlines", "POLYGON", spatial_reference=sr)
                        arcpy.management.AddField(outlines, "gridcode", "LONG")
                    common.add_fields(outlines, [("ROOF_Z_M","DOUBLE",None),("ROOF_H_M","DOUBLE",None),
                        ("FIT_RMSE_M","DOUBLE",None),("FIT_FRACTION","DOUBLE",None),("MODEL_OK","SHORT",None),
                        ("PARTIAL_AOI","SHORT",None),("REVIEW_STATUS","TEXT",32)])
                    with arcpy.da.UpdateCursor(outlines, ["gridcode","ROOF_Z_M","ROOF_H_M","FIT_RMSE_M",
                                                          "FIT_FRACTION","MODEL_OK","PARTIAL_AOI","REVIEW_STATUS"]) as cursor:
                        for row in cursor:
                            model = models[row[0]]
                            row[1:] = [model["roof_z_m"], model["roof_height_m"], model["fit_rmse_m"],
                                       model["inlier_fraction"], int(model["model_ok"]), int(model["partial_aoi"]),
                                       "UNVERIFIED" if model["model_ok"] else "MODEL_REJECTED"]
                            cursor.updateRow(row)
                    common.metadata(outlines, "Class-6 roof support closed across one-cell gaps. Raster outlines "
                                    "are not surveyed wall footprints. ROOF_H_M uses interpolated ground; "
                                    "FIT_RMSE_M is model residual, not positional or vertical accuracy.")
                    state["roof_models"] = models
                    state["roof_outlines"] = outlines
            finally:
                for layer in layers:
                    arcpy.management.Delete(layer)
        copied_root = destination/"points"; copied_root.mkdir()
        audit_root = destination/"changes"; audit_root.mkdir()
        state["before"] = {}
        state["changed_points"] = {}
        for path in files:
            copy = copied_root/path.name
            shutil.copy2(path, copy)
            state["before"][path.name] = preparation.class_counts(copy)
            counts = _classify_copy(copy, regions, models, cell_size, reference.extent.XMin,
                                    reference.extent.YMax, edge_distance, below_roof, above_roof,
                                    audit_root/(path.stem+".npz"))
            state["changed_points"][path.name] = counts
        arcpy.management.CreateLasDataset([str(p) for p in copied_root.glob("*.las")], output_lasd,
                                          spatial_reference=sr, compute_stats="COMPUTE_STATS")
        state["after"] = {p.name: preparation.class_counts(p) for p in copied_root.glob("*.las")}
        for row in inputs:
            stat = Path(row["path"]).stat()
            if (stat.st_size, stat.st_mtime_ns) != (row["bytes"], row["mtime_ns"]):
                raise RuntimeError("Input working LAS changed during refinement")
        state["status"] = "complete"
    except Exception as exc:
        state["status"] = "failed"; state["error"] = str(exc)
        raise
    finally:
        common.write_json(out_manifest, state)
    return state
