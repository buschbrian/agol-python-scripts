"""Marker-controlled crown segmentation constrained to measured canopy.

A deterministic priority flood avoids hydrology FlowDirection's one-cell sink
handling. No Fill operation is used. Only components with an explicit seed grow.
"""
from __future__ import annotations

import heapq
import math
import os

import arcpy
import numpy as np

from . import common

MAX_CELLS = 4_000_000


def segment(surface, mask, seeds):
    """Flood valid canopy from (row, col, integer_label) markers.

    Minimax elevation cost defines a watershed on the inverted surface.
    Distance on equal flood levels breaks ties; labels give reproducible ties.
    Markers remain fixed. Unseeded components remain zero.
    """
    labels = np.zeros(surface.shape, dtype=np.int32)
    costs = np.full(surface.shape, np.inf)
    distances = np.full(surface.shape, np.inf)
    fixed = {}
    queue = []
    height, width = surface.shape
    for row, col, label in seeds:
        if not (0 <= row < height and 0 <= col < width and mask[row, col]):
            raise ValueError("A treetop seed lies outside the valid canopy mask")
        if (row, col) in fixed:
            raise ValueError("Multiple treetops occupy the same raster cell")
        fixed[row, col] = label
        cost = -float(surface[row, col])
        costs[row, col], distances[row, col], labels[row, col] = cost, 0, label
        heapq.heappush(queue, (cost, 0.0, label, row, col))
    neighbours = [(dr, dc, math.hypot(dr, dc)) for dr in (-1, 0, 1)
                  for dc in (-1, 0, 1) if dr or dc]
    while queue:
        cost, distance, label, row, col = heapq.heappop(queue)
        if (cost, distance, label) != (costs[row, col], distances[row, col], labels[row, col]):
            continue
        for dr, dc, step in neighbours:
            rr, cc = row + dr, col + dc
            if not (0 <= rr < height and 0 <= cc < width) or not mask[rr, cc] or (rr, cc) in fixed:
                continue
            next_cost = max(cost, -float(surface[rr, cc]))
            next_distance = distance + step if next_cost == cost else step
            candidate = (next_cost, next_distance, label)
            current = (costs[rr, cc], distances[rr, cc], labels[rr, cc] or 2**31-1)
            if candidate < current:
                costs[rr, cc], distances[rr, cc], labels[rr, cc] = candidate
                heapq.heappush(queue, (*candidate, rr, cc))
    return labels


def delineate(chm_path, treetops, out_workspace, min_height=2.0,
              min_crown_area=3.0, cell_size=None, prefix=""):
    """Create crowns and a separate tree-review layer; never edit input points."""
    from .treetops import smooth_surface
    gdb = common.geodatabase(out_workspace)
    common.prefix_name(prefix)
    common.positive(min_height, "Minimum height")
    common.positive(min_crown_area, "Minimum crown area", allow_zero=True)
    raster, resolution = common.grid(chm_path, cell_size, MAX_CELLS)
    output = common.output(gdb, prefix + "crowns")
    reviewed = common.output(gdb, prefix + "trees_review")
    raw = arcpy.RasterToNumPyArray(raster, nodata_to_value=np.nan)
    fields = {f.name for f in arcpy.ListFields(treetops)}
    if not {"TREE_ID", "MIN_HEIGHT", "SMOOTH"} <= fields:
        raise ValueError("Use treetops created by this toolbox (TREE_ID, MIN_HEIGHT, SMOOTH required)")
    if not common.same_xy_reference(arcpy.Describe(treetops).spatialReference, raster.spatialReference):
        raise ValueError("Treetops and CHM must have the same spatial reference")
    rows = list(arcpy.da.SearchCursor(treetops, ["TREE_ID", "SHAPE@XY", "MIN_HEIGHT", "SMOOTH"]))
    ids = [str(row[0]) for row in rows]
    if any(not row[0] for row in rows) or len(set(ids)) != len(ids):
        raise ValueError("TREE_ID values must be populated and unique")
    if any(not math.isclose(row[2], min_height) for row in rows):
        raise ValueError("Crown minimum height must match the treetop detection threshold")
    smoothing = {row[3] for row in rows}
    if len(smoothing) > 1:
        raise ValueError("Treetops must share one smoothing radius")
    surface = smooth_surface(raw, next(iter(smoothing), 0))
    mask = np.isfinite(raw) & (raw >= min_height)
    seeds = []
    for label, (_, (x, y), _, _) in enumerate(rows, 1):
        col = int(math.floor((x-raster.extent.XMin)/resolution))
        row = int(math.floor((raster.extent.YMax-y)/resolution))
        seeds.append((row, col, label))
    labels = segment(surface, mask, seeds)
    counts = np.bincount(labels.ravel(), minlength=len(rows)+1)
    accepted = {i for i in range(1, len(rows)+1) if counts[i]*resolution**2 >= min_crown_area and counts[i]}
    maxima = np.full(len(rows)+1, -np.inf)
    np.maximum.at(maxima, labels[mask], raw[mask])
    stats = {}
    for label in range(1, len(rows)+1):
        stats[ids[label-1]] = {
            "area": int(counts[label])*resolution**2,
            "height": float(maxima[label]) if counts[label] else None,
            "status": "ESTIMATED" if label in accepted else "CROWN_TOO_SMALL",
        }
    kept = np.where(np.isin(labels, list(accepted)), labels, 0).astype(np.int32)
    with common.scratch() as (_, scratch_gdb), common.environment(chm_path):
        if accepted:
            label_raster = os.path.join(scratch_gdb, "labels")
            arcpy.NumPyArrayToRaster(kept, arcpy.Point(raster.extent.XMin, raster.extent.YMin),
                                    resolution, resolution, 0).save(label_raster)
            arcpy.management.DefineProjection(label_raster, raster.spatialReference)
            polygons = os.path.join(scratch_gdb, "parts")
            arcpy.conversion.RasterToPolygon(label_raster, polygons, "NO_SIMPLIFY", "VALUE")
            arcpy.management.Dissolve(polygons, output, "gridcode", multi_part="MULTI_PART")
        else:
            arcpy.management.CreateFeatureclass(gdb, os.path.basename(output), "POLYGON",
                                                spatial_reference=raster.spatialReference)
            arcpy.management.AddField(output, "gridcode", "LONG")
        common.add_fields(output, [("TREE_ID", "TEXT", 36), ("HEIGHT_M", "DOUBLE", None),
                                  ("CROWN_AREA_M2", "DOUBLE", None), ("CROWN_DIAM_M", "DOUBLE", None)])
        with arcpy.da.UpdateCursor(output, ["gridcode", "TREE_ID", "HEIGHT_M", "CROWN_AREA_M2", "CROWN_DIAM_M"]) as cursor:
            for row in cursor:
                tree_id = ids[row[0]-1]
                entry = stats[tree_id]
                row[1:] = [tree_id, entry["height"], entry["area"], 2*math.sqrt(entry["area"]/math.pi)]
                cursor.updateRow(row)
        arcpy.management.DeleteField(output, "gridcode")
        arcpy.management.CopyFeatures(treetops, reviewed)
        common.add_fields(reviewed, [("CROWN_AREA_M2", "DOUBLE", None), ("CROWN_DIAM_M", "DOUBLE", None),
                                    ("CROWN_HEIGHT_M", "DOUBLE", None), ("CROWN_STATUS", "TEXT", 32)])
        with arcpy.da.UpdateCursor(reviewed, ["TREE_ID", "CROWN_AREA_M2", "CROWN_DIAM_M", "CROWN_HEIGHT_M", "CROWN_STATUS"]) as cursor:
            for row in cursor:
                entry = stats[str(row[0])]
                row[1:] = [entry["area"], 2*math.sqrt(entry["area"]/math.pi), entry["height"], entry["status"]]
                cursor.updateRow(row)
    missing = int(np.count_nonzero(mask & (labels == 0)))
    common.metadata(output, f"Marker-controlled canopy watershed. Unseeded canopy area: {missing*resolution**2} m2.")
    common.metadata(reviewed, "Copy of detections with crown acceptance status; original input points unchanged.")
    if missing:
        arcpy.AddWarning(f"{missing*resolution**2:.2f} m2 of canopy has no treetop seed")
    return output
