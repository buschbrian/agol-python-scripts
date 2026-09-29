"""Optional roof-edge refinement on new LAS copies, with auditable roof models.

Two methods share one audit trail (new LAS copies, previous class bytes, manifest):
- plane (refine): one low-slope plane per rasterized roof region; suits flat commercial roofs.
- local (refine_local): local roof faces from nearby class-6 points (roof_surface.py); suits
  gabled and hipped roofs.

Derived polygons describe rasterized roof support, not surveyed wall footprints.
Height gates reduce lateral clipping of nearby vegetation, but do not prove class.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import struct
import time

import arcpy
import numpy as np
from scipy import ndimage

from . import common, preparation, rasters, roof_surface
from .tiling import Extent, snap_extent

# Plane mode: ArcGIS roof/ground rasters and a distance transform over the review AOI.
MAX_CELLS = 4_000_000
# Local mode needs no ArcGIS rasters, only a 0.5 m NumPy prefilter grid (low/high roof Z). Its
# memory is dominated by class-6 support and per-block candidates, not by cells. Measured peak
# RSS on the 1.1 km prepared pilot tiles (4.84 M cells) is in reviews/2026-09-29/ROOF_SURFACE.md.
# The guard allows a 1.25 km square (1 km tile plus 125 m buffer); larger AOIs need a new measurement.
LOCAL_PREFILTER_CELL = .5
LOCAL_MAX_CELLS = 6_250_000


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
        "names": ["x", "y", "z", "returns", "flags", "classification"],
        "formats": ["<i4", "<i4", "<i4", "u1", "u1", "u1"],
        "offsets": [0, 4, 8, 14, 15, 16 if modern else 15],
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


def _check_input(prepared_lasd, output_folder):
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
    return manifest, previous, destination, files, [preparation.header(path) for path in files]


def _inputs_unchanged(inputs):
    for row in inputs:
        stat = Path(row["path"]).stat()
        if (stat.st_size, stat.st_mtime_ns) != (row["bytes"], row["mtime_ns"]):
            raise RuntimeError("Input working LAS changed during refinement")


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
    manifest, previous, destination, files, inputs = _check_input(prepared_lasd, output_folder)
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
        _inputs_unchanged(inputs)
        state["status"] = "complete"
    except Exception as exc:
        state["status"] = "failed"; state["error"] = str(exc)
        raise
    finally:
        common.write_json(out_manifest, state)
    return state


RETURN_TYPES = ("single", "first_of_many", "intermediate", "last_of_many")


def _return_type(return_byte, modern):
    """0 single, 1 first of many, 2 intermediate, 3 last of many (number > count counts as last)."""
    number = return_byte & (15 if modern else 7)
    count = (return_byte >> 4) if modern else ((return_byte >> 3) & 7)
    return np.where(count <= 1, 0, np.where(number <= 1, 1, np.where(number < count, 2, 3)))


def _load_support(paths, block=2_000_000):
    """Class-6 first/single returns (not withheld, synthetic or overlap) from read-only files."""
    parts, chunk = [], None
    for path in paths:
        points, scale, offset, modern = _records(path, "r")
        for start in range(0, len(points), block):
            chunk = points[start:start+block]
            codes = chunk["classification"] if modern else chunk["classification"] & 31
            first, _ = roof_surface.return_masks(chunk["returns"], modern)
            keep = np.flatnonzero((codes == 6) & first & roof_surface.clean_flags(chunk["flags"], modern))
            parts.append(np.column_stack([chunk[axis][keep]*scale[i]+offset[i] for i, axis in enumerate("xyz")]))
        del points, chunk
    return np.concatenate(parts) if parts else np.zeros((0, 3))


def _classify_local_copy(path, tree, support_z, gradient, face_status, low, high, xmin, ymax, cell,
                         parameters, audit_path, block=2_000_000):
    """Change only classification bytes of eligible points voted onto a local roof face.

    Eligible: parameters["eligible_classes"] (a subset of 3/4/5), any return, not withheld,
    synthetic or overlap. Returns counts by previous class and return type, and writes per-point
    previous class bytes and diagnostics.
    """
    p = parameters
    points, scale, offset, modern = _records(path, "r+")
    audit = {key: [] for key in ("point_index", "previous_class_byte", "residual_m", "votes",
                                 "faces", "support", "nearest_roof_m")}
    counts = {"eligible": 0, "evaluated": 0, "with_roof_support": 0, "changed": 0,
              "changed_by_class": {"3": 0, "4": 0, "5": 0},
              "changed_by_return": dict.fromkeys(RETURN_TYPES, 0)}
    chunk = None
    for start in range(0, len(points), block):
        chunk = points[start:start+block]
        codes = chunk["classification"] if modern else chunk["classification"] & 31
        eligible = np.flatnonzero(np.isin(codes, p["eligible_classes"]) & roof_surface.clean_flags(chunk["flags"], modern))
        counts["eligible"] += len(eligible)
        xyz = np.column_stack([chunk[axis][eligible]*scale[i]+offset[i] for i, axis in enumerate("xyz")])
        near = roof_surface.prefilter(xyz, low, high, xmin, ymax, cell, p["below_roof_m"], p["above_roof_m"],
                                      2*p["radius_m"]+roof_surface.INTERIOR_REACH_M, p["max_face_slope"])
        eligible, xyz = eligible[near], xyz[near]
        counts["evaluated"] += len(eligible)
        result = roof_surface.evaluate(tree, support_z, gradient, face_status, xyz, p["radius_m"],
                                       p["neighbors"], p["below_roof_m"], p["above_roof_m"])
        counts["with_roof_support"] += int((result["support"] > 0).sum())
        chosen = roof_surface.select(result, p["min_votes"])
        selected = eligible[chosen]
        if not selected.size:
            continue
        previous = chunk["classification"][selected].copy()
        old = previous if modern else previous & 31
        for code in (3, 4, 5):
            counts["changed_by_class"][str(code)] += int((old == code).sum())
        kinds = np.bincount(_return_type(chunk["returns"][selected], modern), minlength=4)
        for name, value in zip(RETURN_TYPES, kinds):
            counts["changed_by_return"][name] += int(value)
        chunk["classification"][selected] = 6 if modern else (previous & 224) | 6
        counts["changed"] += len(selected)
        audit["point_index"].append(selected.astype(np.int64)+start)
        audit["previous_class_byte"].append(previous)
        audit["residual_m"].append(result["residual"][chosen])
        audit["votes"].append(result["votes"][chosen])
        audit["faces"].append(result["faces"][chosen])
        audit["support"].append(result["support"][chosen])
        audit["nearest_roof_m"].append(result["nearest"][chosen])
    points.flush()
    del points, chunk
    empty = {"point_index": np.int64, "previous_class_byte": np.uint8, "residual_m": np.float32,
             "votes": np.uint8, "faces": np.uint8, "support": np.uint8, "nearest_roof_m": np.float32}
    np.savez_compressed(audit_path, **{key: np.concatenate(value) if value else np.array([], dtype=empty[key])
                                       for key, value in audit.items()})
    return counts


def refine_local(prepared_lasd, output_folder, radius=1.0, neighbors=16, min_neighbors=6, min_votes=3,
                 below_roof=.35, above_roof=.5, max_fit_rmse=.15, max_slope=1.5, classes=(4, 5)):
    """Reclassify eligible vegetation-class points that lie on a local roof face, on NEW LAS copies.

    Experimental opt-in for gabled and hipped roofs (see roof_surface.py). A point changes to
    class 6 only when at least `min_votes` nearby class-6 roof faces, extended to it, place it
    between `below_roof` below and `above_roof` above the roof. Overhanging canopy above that
    band and lower vegetation below it are unchanged. Canopy level with a roof edge is not
    distinguished from the roof; inspect before accepting.

    Class 3 (at most 0.5 m above ground) is not eligible by default: it never reaches the CHM,
    and in it the band mostly matched lawn or paving beside class-6 points at ground level.
    """
    roof_surface.check_parameters(radius, neighbors, min_neighbors, min_votes, below_roof, above_roof,
                                  max_fit_rmse, max_slope)
    classes = sorted({int(code) for code in classes})
    if not classes or not set(classes) <= {3, 4, 5}:
        raise ValueError("Eligible classes must be a non-empty subset of 3, 4 and 5")
    manifest, previous, destination, files, inputs = _check_input(prepared_lasd, output_folder)
    sr = common.metric_reference(arcpy.Describe(str(prepared_lasd)).spatialReference)
    if not rasters.audit(str(prepared_lasd))["has_building"]:
        raise ValueError("Local roof refinement needs classified buildings (class 6)")
    cell = LOCAL_PREFILTER_CELL
    bounds = snap_extent(Extent(*previous["extent"]), cell)
    shape = (round(bounds.height/cell), round(bounds.width/cell))
    if shape[0]*shape[1] > LOCAL_MAX_CELLS:
        raise ValueError(f"Local roof refinement supports at most {LOCAL_MAX_CELLS:,} prefilter cells "
                         f"({cell} m) per prepared AOI")
    parameters = {"method": "local_surface", "radius_m": radius, "neighbors": neighbors,
                  "min_face_neighbors": min_neighbors, "min_votes": min_votes, "below_roof_m": below_roof,
                  "above_roof_m": above_roof, "max_face_rmse_m": max_fit_rmse, "max_face_slope": max_slope,
                  "face_trim": "one refit without residuals beyond clip(3*1.4826*MAD, 0.15, 0.5) m",
                  "face_anchors": "interior class-6 support, eroded by 0.5 m plus 0.5 m grid uncertainty; fitted intercept retained",
                  "interior_cell_m": roof_surface.INTERIOR_CELL_M,
                  "interior_margin_m": roof_surface.INTERIOR_MARGIN_M,
                  "roof_support": "class 6, first or single returns, not withheld/synthetic/overlap, all input files",
                  "eligible_classes": classes, "eligible": "listed classes, all returns, not withheld/synthetic/overlap",
                  "iterative": False, "prefilter_cell_m": cell}
    destination.mkdir(parents=True)
    output_lasd = str(destination/"prepared.lasd")
    state = {"status": "modeling", "working_lasd": output_lasd, "extent": list(bounds),
             "source_id": previous["source_id"], "sources": previous.get("sources", []),
             "input_preparation": str(manifest), "input_files": inputs, "runtime": common.runtime(),
             "parameters": parameters, "quality_status": "EXPERIMENTAL_UNVALIDATED", "seconds": {}}
    out_manifest = destination/"preparation.json"
    common.write_json(out_manifest, state)
    try:
        clock = time.perf_counter()
        # Support comes from the unchanged inputs, so a reclassified point never becomes support.
        support = _load_support(files)
        if not len(support):
            raise ValueError("No class-6 first/single returns were found")
        tree = roof_surface.build_tree(support)
        support_z = support[:, 2].copy()
        state["seconds"]["support"] = round(time.perf_counter()-clock, 1); clock = time.perf_counter()
        gradient, face_rmse, face_status = roof_surface.faces(tree, support_z, radius, neighbors, min_neighbors,
                                                              max_fit_rmse, max_slope)
        state["seconds"]["faces"] = round(time.perf_counter()-clock, 1); clock = time.perf_counter()
        ok = face_status == roof_surface.FACE_OK
        slope = np.hypot(gradient[ok, 0], gradient[ok, 1])
        state["roof_faces"] = {
            "support_points": int(len(support)),
            "status": {name: int((face_status == code).sum()) for code, name in roof_surface.FACE_STATUS.items()},
            "ok_slope_percentiles": dict(zip(("p10", "p50", "p90", "p99"),
                                             np.round(np.percentile(slope, [10, 50, 90, 99]), 3).tolist()))
                                    if slope.size else None,
            "ok_rmse_median_m": round(float(np.median(face_rmse[ok])), 4) if slope.size else None}
        del face_rmse, slope, ok
        low, high = roof_surface.envelope(support, bounds.xmin, bounds.ymax, cell, shape,
                                         2*radius+roof_surface.INTERIOR_REACH_M)
        del support
        common.write_json(out_manifest, state)
        copied_root = destination/"points"; copied_root.mkdir()
        audit_root = destination/"changes"; audit_root.mkdir()
        state["before"], state["changed_points"] = {}, {}
        for path in files:
            copy = copied_root/path.name
            shutil.copy2(path, copy)
            state["before"][path.name] = preparation.class_counts(copy)
            state["changed_points"][path.name] = _classify_local_copy(
                copy, tree, support_z, gradient, face_status, low, high, bounds.xmin, bounds.ymax, cell,
                parameters, audit_root/(path.stem+".npz"))
        state["seconds"]["classify"] = round(time.perf_counter()-clock, 1)
        arcpy.management.CreateLasDataset([str(p) for p in copied_root.glob("*.las")], output_lasd,
                                          spatial_reference=sr, compute_stats="COMPUTE_STATS")
        state["after"] = {p.name: preparation.class_counts(p) for p in copied_root.glob("*.las")}
        _inputs_unchanged(inputs)
        state["status"] = "complete"
    except Exception as exc:
        state["status"] = "failed"; state["error"] = str(exc)
        raise
    finally:
        common.write_json(out_manifest, state)
    return state
