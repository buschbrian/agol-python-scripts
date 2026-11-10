"""Reconcile class-6 lidar buildings with reference footprints for one prepared tile.

Reads the prepared LAS copies directly (read-only memory maps), a ground surface built
with the same triangulation as the CHM, the reference footprints from fetch-footprints,
and optionally the run's trees_review candidates. Writes a review geodatabase, a JSON
summary, layer files, and a NEW label LAS copy of the tile core. Decision rules live in
building_rules.py. Every status is a review screen, not a verified label, and every
height is an unvalidated lidar estimate.
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
import shutil
import time

import arcpy
import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

from . import building_rules as rules
from . import las_records, common, preparation, rasters
from .tiling import Extent, snap_extent

REVIEW_GDB = "review.gdb"
WARNING = ("Unvalidated review screens. Statuses compare lidar class 6 with reference footprints "
           "and do not establish which is right. Heights are lidar roof-minus-ground estimates, "
           "not surveyed or code-defined building heights.")
BLOCK = 2_000_000
COLORS = {
    "MATCHED": (56, 168, 0), "PARTIAL": (255, 170, 0), "LIDAR_MISSED": (230, 0, 0),
    "NO_RETURNS_ABOVE_2M": (132, 0, 168), "NO_FOOTPRINT": (230, 0, 169), "NO_FOOTPRINT_COVERAGE": (130, 130, 130),
    "ON_ROOF": (230, 0, 0), "ROOF_EDGE": (255, 127, 0), "NEAR_ROOF": (255, 211, 0), "OVERHANG": (0, 112, 255),
    "CLEAR": (56, 168, 0),
    "UNKNOWN": (130, 130, 130),
}


# --- LAS ---------------------------------------------------------------------------------

_points = las_records.records
_decode = las_records.decode


class Grid:
    def __init__(self, xmin, ymax, cell, shape):
        self.xmin, self.ymax, self.cell, self.shape = xmin, ymax, cell, shape
        self.rows, self.cols = shape

    def cells(self, x, y):
        col = np.floor((x - self.xmin)/self.cell).astype(np.int64)
        row = np.floor((self.ymax - y)/self.cell).astype(np.int64)
        inside = (col >= 0) & (col < self.cols) & (row >= 0) & (row < self.rows)
        return row*self.cols + col, inside

    def window(self, extent):
        c0 = int(round((extent[0] - self.xmin)/self.cell)); c1 = int(round((extent[2] - self.xmin)/self.cell))
        r0 = int(round((self.ymax - extent[3])/self.cell)); r1 = int(round((self.ymax - extent[1])/self.cell))
        return max(r0, 0), min(r1, self.rows), max(c0, 0), min(c1, self.cols)


def _read_points(files, grid, dtm, p):
    """One pass over every prepared file; returns compact arrays and per-cell grids."""
    above, b6first, b6all, ground = [], [], [], []
    n6_any = np.zeros(grid.rows*grid.cols, dtype=np.int32)
    roof_lo = np.full(grid.rows*grid.cols, np.inf, dtype=np.float32)
    roof_hi = np.full(grid.rows*grid.cols, -np.inf, dtype=np.float32)
    flat_dtm = dtm.ravel()
    totals = {"points": 0, "in_grid": 0, "excluded_flags": 0}
    for path in files:
        points, scale, offset, modern, _ = _points(path)
        for start in range(0, len(points), BLOCK):
            block = np.asarray(points[start:start+BLOCK])
            x, y, z, classes, first, excluded = _decode(block, scale, offset, modern)
            cell, inside = grid.cells(x, y)
            totals["points"] += len(block)
            totals["excluded_flags"] += int(np.count_nonzero(excluded))
            keep = inside & ~excluded
            totals["in_grid"] += int(np.count_nonzero(keep))
            x, y, z, classes, first, cell = x[keep], y[keep], z[keep], classes[keep], first[keep], cell[keep]
            hag = z - flat_dtm[cell]
            building = classes == 6
            n6_any += np.bincount(cell[building], minlength=n6_any.size).astype(np.int32)
            b6all.append(np.column_stack([x[building], y[building], z[building]]))
            is_ground = classes == 2
            ground.append(np.column_stack([x[is_ground], y[is_ground], z[is_ground]]))
            sel = first & building
            b6first.append((cell[sel].astype(np.int32), hag[sel].astype(np.float32)))
            np.minimum.at(roof_lo, cell[sel], z[sel].astype(np.float32))
            np.maximum.at(roof_hi, cell[sel], z[sel].astype(np.float32))
            sel = first & (hag > p["above_ground_m"]) & ~np.isin(classes, (7, 18))
            above.append((cell[sel].astype(np.int32), classes[sel].astype(np.uint8), hag[sel].astype(np.float32)))
        del points
    join = lambda parts, i: np.concatenate([part[i] for part in parts]) if parts else np.array([])
    result = {
        "above_cell": join(above, 0), "above_class": join(above, 1), "above_hag": join(above, 2),
        "b6_cell": join(b6first, 0), "b6_hag": join(b6first, 1),
        "b6_xyz": np.vstack(b6all) if b6all else np.zeros((0, 3)),
        "ground_xyz": np.vstack(ground) if ground else np.zeros((0, 3)),
        "n6_any": n6_any.reshape(grid.shape),
        "roof_lo": np.where(np.isfinite(roof_lo), roof_lo, np.nan).reshape(grid.shape),
        "roof_hi": np.where(np.isfinite(roof_hi), roof_hi, np.nan).reshape(grid.shape),
    }
    return result, totals


# --- footprints ----------------------------------------------------------------------------

def _rings(shape):
    rings = []
    for part in shape:
        ring = []
        for point in part:
            if point is None:
                if ring:
                    rings.append(np.array(ring))
                ring = []
            else:
                ring.append((point.X, point.Y))
        if ring:
            rings.append(np.array(ring))
    return rings


def _pcs(sr):
    return getattr(sr, "PCSCode", 0) or sr.factoryCode


def _read_footprints(gdb, name, grid, prepared_rect, core_rect, sr):
    path = os.path.join(gdb, name)
    described = arcpy.Describe(path)
    if described.shapeType != "Polygon":
        raise ValueError(f"{path} must be polygons")
    if _pcs(described.spatialReference) != _pcs(sr):
        raise ValueError(f"{path} is not in the LAS horizontal reference; run fetch-footprints")
    fields = {f.name.upper(): f.name for f in arcpy.ListFields(path)}
    extras = [fields[k] for k in ("BLDGHEIGHT", "BUILDING_T", "BUILDING", "BUILDTYPE", "LEVELS", "HEIGHT_TAG")
              if k in fields]
    rows = []
    with arcpy.da.SearchCursor(path, ["SHAPE@", "SOURCE_ID"] + extras,
                               spatial_filter=prepared_rect, spatial_relationship="INTERSECTS") as cursor:
        for shape, source_id, *values in cursor:
            if shape is None or not shape.area:
                continue
            cells, truncated = rules.rasterize(_rings(shape), grid.xmin, grid.ymax, grid.cell, grid.shape)
            attrs = {k.upper(): v for k, v in zip(extras, values)}
            rows.append({"source": name, "source_id": source_id, "shape": shape, "cells": cells,
                         "truncated": truncated or not prepared_rect.contains(shape),
                         "in_core": not shape.disjoint(core_rect), "area": shape.area, "attrs": attrs})
    return rows


def _coverage(path, grid, sr):
    fields = [f.name.upper() for f in arcpy.ListFields(path)]
    if "SOURCE" not in fields:
        raise ValueError("Coverage polygons need a SOURCE field naming the footprint source")
    if _pcs(arcpy.Describe(path).spatialReference) != _pcs(sr):
        raise ValueError("Coverage must be in the LAS horizontal reference")
    masks = {}
    for shape, source in arcpy.da.SearchCursor(path, ["SHAPE@", "SOURCE"]):
        if shape is None:
            continue
        cells, _ = rules.rasterize(_rings(shape), grid.xmin, grid.ymax, grid.cell, grid.shape)
        mask = masks.setdefault(source, np.zeros(grid.shape, dtype=bool))
        mask.flat[cells] = True
    return masks


# --- outputs -------------------------------------------------------------------------------

def _create(gdb, name, geometry, sr, fields):
    arcpy.management.CreateFeatureclass(gdb, name, geometry, spatial_reference=sr)
    path = os.path.join(gdb, name)
    common.add_fields(path, fields)
    return path


def _describe(path, text):
    item = arcpy.metadata.Metadata(path)
    item.summary = WARNING
    item.description = text + "\n\n" + WARNING
    item.save()


def _layer_file(fc, path, field, title):
    """Unique-value layer file; returns None (and the reason) if symbology cannot be set."""
    name = f"{title} {os.getpid()} {time.time_ns()}"
    layer = arcpy.management.MakeFeatureLayer(fc, name)[0]
    try:
        arcpy.management.SaveToLayerFile(layer, path, "ABSOLUTE")
    finally:
        arcpy.management.Delete(layer)
    try:
        document = arcpy.mp.LayerFile(path)
        lyr = document.listLayers()[0]
        lyr.name = title
        symbology = lyr.symbology
        symbology.updateRenderer("UniqueValueRenderer")
        symbology.renderer.fields = [field]
        for group in symbology.renderer.groups:
            for item in group.items:
                value = str(item.values[0][0])
                if value in COLORS:
                    color = {"RGB": list(COLORS[value]) + [100]}
                    item.symbol.color = color
                    if lyr.isFeatureLayer and arcpy.Describe(fc).shapeType == "Polygon":
                        item.symbol.outlineColor = color
                        item.symbol.color = {"RGB": list(COLORS[value]) + [35]}
                    item.label = value
        lyr.symbology = symbology
        document.save()
        return None
    except Exception as exc:  # the layer file still opens with default symbology
        return f"Symbology not set: {exc}"


def _region_polygons(labels, keep_ids, grid, sr, scratch_gdb, output):
    raster = np.where(np.isin(labels, keep_ids), labels, 0).astype(np.int32)
    lower_left = arcpy.Point(grid.xmin, grid.ymax - grid.rows*grid.cell)
    label_path = os.path.join(scratch_gdb, "region_ids")
    arcpy.NumPyArrayToRaster(raster, lower_left, grid.cell, grid.cell, 0).save(label_path)
    arcpy.management.DefineProjection(label_path, sr)
    parts = os.path.join(scratch_gdb, "region_parts")
    arcpy.conversion.RasterToPolygon(label_path, parts, "NO_SIMPLIFY", "VALUE")
    arcpy.management.Dissolve(parts, output, "gridcode", multi_part="MULTI_PART")
    arcpy.management.AlterField(output, "gridcode", "REGION_ID", "REGION_ID")


# --- main ----------------------------------------------------------------------------------

def reconcile(prepared_lasd, output_folder, extent, footprints_gdb, coverage=None, trees=None, tile=None,
              **thresholds):
    """Reconcile one tile core. Refuses an existing output folder; never edits inputs."""
    started = time.time()
    p = rules.parameters(**thresholds)
    core = list(Extent(*[float(v) for v in extent]))
    input_root = Path(prepared_lasd).resolve().parent
    manifest = input_root/"preparation.json"
    if not manifest.is_file():
        raise ValueError("Use a prepared working-copy LAS dataset with preparation.json")
    previous = json.loads(manifest.read_text(encoding="utf8"))
    if previous["status"] != "complete" or Path(previous["working_lasd"]).resolve() != Path(prepared_lasd).resolve():
        raise ValueError("Preparation manifest does not match a completed LAS dataset")
    destination = Path(output_folder).resolve()
    if destination == input_root or input_root in destination.parents:
        raise ValueError("Choose an output folder outside the input preparation")
    if destination.exists():
        raise FileExistsError(f"Output already exists: {destination}; choose a new folder")
    footprints_gdb = str(Path(footprints_gdb).resolve())
    coverage = coverage or os.path.join(footprints_gdb, "coverage")
    if not arcpy.Exists(footprints_gdb) or not arcpy.Exists(coverage):
        raise ValueError("Footprint geodatabase or coverage feature class not found")
    sources = [name for name in rules.SOURCES if arcpy.Exists(os.path.join(footprints_gdb, name))]
    independent = [name for name in sources if not rules.SOURCES[name]["same_method"]]
    if not independent:
        raise ValueError("No independent footprint source found in the reference geodatabase")
    files = sorted((input_root/"points").glob("*.las"))
    if not files:
        raise ValueError("Prepared point files were not found")
    inputs = [preparation.header(path) for path in files]
    if tile:
        core_file = input_root/"points"/(tile if tile.lower().endswith(".las") else tile + ".las")
    else:
        inside = [Path(h["path"]) for h in inputs if h["extent"][0] >= core[0] - .01 and h["extent"][1] >= core[1] - .01
                  and h["extent"][2] <= core[2] + .01 and h["extent"][3] <= core[3] + .01]
        if len(inside) != 1:
            raise ValueError("Could not identify one core LAS file inside the extent; pass --tile")
        core_file = inside[0]
    core_info = preparation.header(core_file)
    if core_info["format"] < 6:
        raise ValueError("Label codes 64 and above need LAS point formats 6-10; this core file is a legacy format")
    sr = common.metric_reference(arcpy.Describe(str(prepared_lasd)).spatialReference)
    if trees:
        tree_sr = arcpy.Describe(trees).spatialReference
        if _pcs(tree_sr) != _pcs(sr):
            raise ValueError("Tree candidates must use the LAS horizontal reference")
    cell = p["cell_size_m"]
    bounds = snap_extent(Extent(*previous["extent"]), cell)
    destination.mkdir(parents=True)
    summary_path = destination/"reconcile.json"
    state = {"status": "running", "started": datetime.datetime.now().isoformat(timespec="seconds"),
             "tile_extent": core, "analysis_extent": list(bounds), "prepared_lasd": str(Path(prepared_lasd).resolve()),
             "preparation": str(manifest), "core_file": str(core_file), "input_files": inputs,
             "footprints": footprints_gdb, "coverage": coverage, "trees": trees, "sources": sources,
             "independent_sources": independent, "parameters": p, "label_codes": rules.LABEL_CODES,
             "runtime": common.runtime(), "quality_status": "REVIEW_SCREEN_UNVALIDATED", "warning": WARNING,
             "timings_s": {}}
    reference_json = Path(footprints_gdb).parent/"reference.json"
    if reference_json.is_file():
        reference = json.loads(reference_json.read_text(encoding="utf-8"))
        state["reference_record"] = {"path": str(reference_json), "created": reference.get("created"),
                                     "transformations": {k: v.get("transformation") for k, v in reference.get("sources", {}).items()}}
    common.write_json(summary_path, state)
    tick = time.time()

    def lap(name):
        nonlocal tick
        now = time.time()
        state["timings_s"][name] = round(now - tick, 1)
        tick = now

    try:
        with common.scratch() as (_, scratch_gdb):
            token = Path(scratch_gdb).parent.name
            ground_path = str(destination/"ground.tif")
            layer = None
            try:
                with arcpy.EnvManager(extent=bounds.as_arcpy_string(), cellSize=cell, snapRaster=None,
                                      outputCoordinateSystem=sr, mask=None, parallelProcessingFactor="0"):
                    layer = rasters._las_layer(str(prepared_lasd), token + "_ground", rasters.GROUND_CLASSES, None)
                    rasters._to_raster(layer, ground_path, rasters.DTM_INTERPOLATION, cell)
            finally:
                if layer:
                    arcpy.management.Delete(layer)
            reference, resolution = common.grid(ground_path, cell)
            dtm = arcpy.RasterToNumPyArray(ground_path, nodata_to_value=np.nan).astype(np.float32)
            grid = Grid(reference.extent.XMin, reference.extent.YMax, resolution, dtm.shape)
            lap("ground_surface")
            data, totals = _read_points(files, grid, dtm, p)
            state["points"] = totals
            lap("read_points")

            prepared_rect = arcpy.Polygon(arcpy.Array([arcpy.Point(*xy) for xy in [
                (grid.xmin, grid.ymax - grid.rows*grid.cell), (grid.xmin, grid.ymax),
                (grid.xmin + grid.cols*grid.cell, grid.ymax),
                (grid.xmin + grid.cols*grid.cell, grid.ymax - grid.rows*grid.cell)]]), sr)
            core_rect = arcpy.Polygon(arcpy.Array([arcpy.Point(*xy) for xy in [
                (core[0], core[1]), (core[0], core[3]), (core[2], core[3]), (core[2], core[1])]]), sr)
            footprints = {name: _read_footprints(footprints_gdb, name, grid, prepared_rect, core_rect, sr)
                          for name in sources}
            covered = _coverage(coverage, grid, sr)
            masks = {}
            for name, rows in footprints.items():
                mask = np.zeros(grid.shape, dtype=bool)
                for row in rows:
                    mask.flat[row["cells"]] = True
                masks[name] = mask
            buffered = {name: rules.dilate(mask, p["footprint_buffer_m"], cell) for name, mask in masks.items()}
            independent_mask = np.logical_or.reduce([masks[n] for n in independent])
            zone = np.logical_or.reduce([buffered[n] for n in independent])
            covered_any = np.logical_or.reduce([covered.get(n, np.zeros(grid.shape, bool)) for n in independent])
            lap("footprints")

            # Footprint statistics from first returns more than above_ground_m above ground.
            order = np.argsort(data["above_cell"], kind="stable")
            above_cell = data["above_cell"][order].astype(np.int64)
            above_class, above_hag = data["above_class"][order], data["above_hag"][order]
            has_above = np.zeros(grid.rows*grid.cols, dtype=bool)
            has_above[above_cell] = True
            fp_roof = np.full(grid.rows*grid.cols, np.nan, dtype=np.float32)
            status_rows = []
            for name, rows in footprints.items():
                for row in rows:
                    cells = row["cells"]
                    index = rules.gather(above_cell, cells)
                    classes, hag = above_class[index], above_hag[index]
                    shares = rules.class_shares(classes)
                    cover = float(has_above[cells].mean()) if cells.size else None
                    h6 = rules.height_stats(hag[classes == 6])
                    hall = rules.height_stats(hag)
                    status = rules.footprint_status(cover, shares["share6"], shares["shareveg"], p)
                    roof, basis = rules.footprint_roof_height(h6["p90"], shares["n6"], hall["p50"], p)
                    if roof is not None and name in independent and status != "NO_RETURNS_ABOVE_2M" and cells.size:
                        fp_roof[cells] = np.fmax(fp_roof[cells], roof)
                    inside = {other: (1 if other == name else
                                      int(cells.size > 0 and masks[other].flat[cells].mean() >= p["source_overlap"]))
                              for other in sources}
                    row.update(shares=shares, cover=cover, h6=h6, hall=hall, status=status, roof=roof,
                               roof_basis=basis, inside=inside, n6_any=int(data["n6_any"].flat[cells].sum()))
                    if row["in_core"]:
                        status_rows.append(row)
            fp_roof = fp_roof.reshape(grid.shape)
            lap("footprint_status")

            # Lidar roof regions from class-6 first/single returns.
            support = np.zeros(grid.rows*grid.cols, dtype=bool)
            support[data["b6_cell"]] = True
            support = support.reshape(grid.shape)
            labels, count = rules.roof_regions(support, cell, p["min_region_area_m2"])
            r0, r1, c0, c1 = grid.window(core)
            in_core = np.zeros(count + 1, dtype=bool)
            in_core[np.unique(labels[r0:r1, c0:c1])] = True
            in_core[0] = False
            area_cells = np.bincount(labels.ravel(), minlength=count + 1)
            support_cells = np.bincount(labels[support], minlength=count + 1)
            edge = np.zeros(count + 1, dtype=bool)
            edge[np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))] = True
            overlap = {name: np.bincount(labels[buffered[name]], minlength=count + 1)/np.maximum(area_cells, 1)
                       for name in sources}
            coverage_share = {name: np.bincount(labels[covered[name]], minlength=count + 1)/np.maximum(area_cells, 1)
                              for name in sources if name in covered}
            b6_label = labels.ravel()[data["b6_cell"]]
            order6 = np.argsort(b6_label, kind="stable")
            b6_sorted, hag6 = b6_label[order6], data["b6_hag"][order6]
            regions = []
            for rid in np.flatnonzero(in_core):
                lo, hi = np.searchsorted(b6_sorted, rid, "left"), np.searchsorted(b6_sorted, rid, "right")
                inside = {name: bool(overlap[name][rid] >= p["region_overlap"]) for name in sources}
                cov = {name: bool(coverage_share.get(name, np.zeros(count + 1))[rid] >= .5) for name in sources}
                regions.append({"id": int(rid), "area": float(area_cells[rid]*cell**2),
                                "support": float(support_cells[rid]*cell**2), "partial": bool(edge[rid]),
                                "h6": rules.height_stats(hag6[lo:hi]), "inside": inside, "covered": cov,
                                "status": rules.region_status(inside, cov)})
            lap("lidar_regions")

            # Registration: footprints (unbuffered) against closed class-6 roof support.
            closed = labels > 0
            state["registration"] = {name: rules.best_shift(masks[name], closed, 6, cell)
                                     for name in sources if masks[name].any()}
            lap("registration")

            # Tree candidate flags.
            flag_rows = []
            if trees:
                tree_fields = {f.name.upper(): f.name for f in arcpy.ListFields(trees)}
                wanted = ["TREE_ID", "HEIGHT_M", "CROWN_STATUS", "CROWN_AREA_M2"]
                missing = [w for w in wanted[:2] if w not in tree_fields]
                if missing:
                    raise ValueError(f"Tree candidates lack {missing}")
                columns = ["SHAPE@XY"] + [tree_fields[w] if w in tree_fields else "OID@" for w in wanted]
                candidates = [row for row in arcpy.da.SearchCursor(trees, columns) if row[0] and row[2] is not None]
                xy = np.array([row[0] for row in candidates], dtype=float).reshape(-1, 2)
                btree = cKDTree(data["b6_xyz"][:, :2]) if len(data["b6_xyz"]) else None
                gtree = cKDTree(data["ground_xyz"][:, :2]) if len(data["ground_xyz"]) else None
                near = btree.query_ball_point(xy, p["near_roof_m"], workers=-1) if btree else [[] for _ in xy]
                under = gtree.query_ball_point(xy, p["ground_radius_m"], workers=-1) if gtree else [[] for _ in xy]
                cells, valid = grid.cells(xy[:, 0], xy[:, 1])
                source_masks = [(name, masks[name]) for name in independent]
                for i, row in enumerate(candidates):
                    height = float(row[2])
                    local = None
                    if near[i] and under[i]:
                        local = float(np.percentile(data["b6_xyz"][near[i], 2], p["roof_percentile"]) -
                                      np.median(data["ground_xyz"][under[i], 2]))
                    inside_names = [name for name, mask in source_masks if valid[i] and mask.flat[cells[i]]]
                    roof = float(fp_roof.flat[cells[i]]) if valid[i] and np.isfinite(fp_roof.flat[cells[i]]) else None
                    flag, above, basis = rules.candidate_flag(height, local, bool(inside_names), roof, p)
                    flag_rows.append({"xy": row[0], "tree_id": row[1], "height": height, "crown_status": row[3],
                                      "crown_area": row[4], "flag": flag, "above": above,
                                      "roof": local if basis == "CLASS6_1M" else (roof if basis else None),
                                      "basis": basis, "near6": bool(near[i]), "ground": bool(under[i]),
                                      "inside": bool(inside_names), "sources": ",".join(inside_names)})
            lap("candidates")

            # Geodatabase.
            gdb = str(destination/REVIEW_GDB)
            arcpy.management.CreateFileGDB(str(destination), REVIEW_GDB)
            tags = [rules.SOURCES[name]["tag"] for name in rules.SOURCES]
            in_fields = [(f"IN_{t}", "SHORT", None) for t in tags]
            cov_fields = [(f"COV_{t}", "SHORT", None) for t in tags]
            fp_fields = [("SOURCE", "TEXT", 24), ("SOURCE_ID", "TEXT", 40), ("STATUS", "TEXT", 24),
                         ("AREA_M2", "DOUBLE", None), ("CELLS", "LONG", None), ("PARTIAL_AOI", "SHORT", None),
                         ("SMALL", "SHORT", None), ("N_ABOVE", "LONG", None), ("N6", "LONG", None), ("NVEG", "LONG", None),
                         ("NOTHER", "LONG", None), ("SHARE6", "DOUBLE", None), ("SHAREVEG", "DOUBLE", None),
                         ("SHAREOTHER", "DOUBLE", None), ("COVER_ABOVE", "DOUBLE", None), ("N6_ANYRET", "LONG", None),
                         ("H6_P50", "DOUBLE", None), ("H6_P90", "DOUBLE", None), ("H6_MAX", "DOUBLE", None),
                         ("HALL_P50", "DOUBLE", None), ("HALL_P90", "DOUBLE", None), ("HALL_MAX", "DOUBLE", None),
                         ("ROOF_H_M", "DOUBLE", None), ("ROOF_BASIS", "TEXT", 16), ("BLDGHEIGHT", "DOUBLE", None),
                         ("FLOORS", "SHORT", None), ("OSM_LEVELS", "TEXT", 16), ("BUILDING", "TEXT", 64),
                         ("N_INDEP", "SHORT", None)] + in_fields
            fc = _create(gdb, "footprint_status", "POLYGON", sr, fp_fields)
            names = ["SHAPE@"] + [f[0] for f in fp_fields]
            with arcpy.da.InsertCursor(fc, names) as cursor:
                for row in status_rows:
                    s, a = row["shares"], row["attrs"]
                    building = a.get("BUILDING_T") or a.get("BUILDING") or a.get("BUILDTYPE")
                    levels = a.get("LEVELS")
                    cursor.insertRow([row["shape"], row["source"], row["source_id"], row["status"], row["area"],
                                      int(row["cells"].size), int(row["truncated"]),
                                      int(row["area"] < p["min_region_area_m2"]), s["n"], s["n6"], s["nveg"], s["nother"],
                                      s["share6"], s["shareveg"], s["shareother"], row["cover"], row["n6_any"],
                                      row["h6"]["p50"], row["h6"]["p90"], row["h6"]["max"],
                                      row["hall"]["p50"], row["hall"]["p90"], row["hall"]["max"],
                                      row["roof"], row["roof_basis"],
                                      a.get("BLDGHEIGHT") if row["source"] == "county" else None, None,
                                      str(levels)[:16] if levels else None, str(building)[:64] if building else None,
                                      sum(row["inside"][n] for n in independent)] +
                                     [row["inside"].get(name) for name in rules.SOURCES])
            _describe(fc, "One row per reference footprint (per source) intersecting the tile core. Shares use first "
                      "returns more than {0} m above the triangulated ground; H6_* use class-6 returns among them and "
                      "HALL_* all of them. IN_<source> is 1 when at least {1:.0%} of the footprint's cells lie in that "
                      "source's footprints. FLOORS is empty because the county service has no floors field."
                      .format(p["above_ground_m"], p["source_overlap"]))
            lb_fields = [("AREA_M2", "DOUBLE", None), ("SUPPORT_M2", "DOUBLE", None), ("PARTIAL_AOI", "SHORT", None),
                         ("N6_FIRST", "LONG", None), ("H6_P50", "DOUBLE", None), ("H6_P90", "DOUBLE", None),
                         ("H6_MAX", "DOUBLE", None), ("STATUS", "TEXT", 24)] + in_fields + cov_fields
            lidar_fc = os.path.join(gdb, "lidar_buildings")
            if regions:
                _region_polygons(labels, [r["id"] for r in regions], grid, sr, scratch_gdb, lidar_fc)
                common.add_fields(lidar_fc, lb_fields)
            else:
                _create(gdb, "lidar_buildings", "POLYGON", sr, [("REGION_ID", "LONG", None)] + lb_fields)
            by_id = {r["id"]: r for r in regions}
            with arcpy.da.UpdateCursor(lidar_fc, ["REGION_ID"] + [f[0] for f in lb_fields]) as cursor:
                for values in cursor:
                    r = by_id[values[0]]
                    cursor.updateRow([values[0], r["area"], r["support"], int(r["partial"]), r["h6"]["n"],
                                      r["h6"]["p50"], r["h6"]["p90"], r["h6"]["max"], r["status"]] +
                                     [int(r["inside"].get(n, False)) if n in sources else None for n in rules.SOURCES] +
                                     [int(r["covered"].get(n, False)) if n in sources else None for n in rules.SOURCES])
            _describe(lidar_fc, "Connected class-6 first/single-return roof support at {0} m cells after a 3x3 closing, "
                      "at least {1} m2 of supported cells, touching the tile core. IN_<source> is 1 when at least "
                      "{2:.0%} of the region lies within {3} m of that source's footprints; COV_<source> when at least "
                      "half lies in its coverage. Same-method lidar footprints (LIDARFP) never decide STATUS. Raster "
                      "outlines are not surveyed walls.".format(cell, p["min_region_area_m2"], p["region_overlap"],
                                                                p["footprint_buffer_m"]))
            flag_fields = [("TREE_ID", "TEXT", 36), ("HEIGHT_M", "DOUBLE", None), ("CROWN_STATUS", "TEXT", 32),
                           ("CROWN_AREA_M2", "DOUBLE", None), ("FLAG", "TEXT", 16), ("ABOVE_ROOF_M", "DOUBLE", None),
                           ("ROOF_H_M", "DOUBLE", None), ("ROOF_BASIS", "TEXT", 16), ("NEAR_B6", "SHORT", None),
                           ("GROUND_5M", "SHORT", None), ("IN_FOOTPRINT", "SHORT", None), ("FP_SOURCES", "TEXT", 80)]
            flags_fc = _create(gdb, "candidate_flags", "POINT", sr, flag_fields)
            with arcpy.da.InsertCursor(flags_fc, ["SHAPE@XY"] + [f[0] for f in flag_fields]) as cursor:
                for r in flag_rows:
                    cursor.insertRow([r["xy"], str(r["tree_id"]), r["height"], r["crown_status"], r["crown_area"],
                                      r["flag"], r["above"], r["roof"], r["basis"], int(r["near6"]), int(r["ground"]),
                                      int(r["inside"]), r["sources"]])
            _describe(flags_fc, "Every trees_review candidate, keeping TREE_ID. With class-6 points within {0} m: "
                      "roof = {1:g}th percentile class-6 Z minus median class-2 Z within {2} m. Otherwise, inside a "
                      "footprint: that footprint's lidar roof height. ABOVE_ROOF_M = HEIGHT_M - roof. OVERHANG above "
                      "{3} m; ON_ROOF (inside a footprint) or ROOF_EDGE at most {4} m above; NEAR_ROOF between."
                      .format(p["near_roof_m"], p["roof_percentile"], p["ground_radius_m"], p["overhang_m"],
                              p["at_roof_m"]))
            lap("geodatabase")

            # Label LAS copy of the tile core.
            labels_dir = destination/"labels"; labels_dir.mkdir()
            label_las = labels_dir/core_file.name
            shutil.copy2(core_file, label_las)
            near_b6 = rules.dilate(support, p["near_roof_m"], cell)
            radius = int(np.ceil(p["near_roof_m"]/cell))
            yy, xx = np.mgrid[-radius:radius+1, -radius:radius+1]
            disk = (xx**2 + yy**2)*cell**2 <= p["near_roof_m"]**2 + 1e-9
            lo = ndimage.grey_erosion(np.nan_to_num(data["roof_lo"], nan=np.inf), footprint=disk)
            hi = ndimage.grey_dilation(np.nan_to_num(data["roof_hi"], nan=-np.inf), footprint=disk)
            radius = int(np.ceil(p["footprint_buffer_m"]/cell))
            yy, xx = np.mgrid[-radius:radius+1, -radius:radius+1]
            disk = (xx**2 + yy**2)*cell**2 <= p["footprint_buffer_m"]**2 + 1e-9
            roof_zone = ndimage.grey_dilation(np.nan_to_num(fp_roof, nan=-np.inf), footprint=disk)
            points, scale, offset, modern, _ = _points(label_las, "r+")
            before, after = np.zeros(256, dtype=np.int64), np.zeros(256, dtype=np.int64)
            flat = {k: v.ravel() for k, v in dict(zone=zone, covered=covered_any, near=near_b6, lo=lo, hi=hi,
                                                   roof=roof_zone, dtm=dtm).items()}
            outside_grid, block = 0, None
            for start in range(0, len(points), BLOCK):
                block = points[start:start+BLOCK]
                x, y, z, classes, first, excluded = _decode(block, scale, offset, modern)
                cellx, inside = grid.cells(x, y)
                outside_grid += int(np.count_nonzero(~inside))
                cellx = np.where(inside, cellx, 0)
                in_zone = flat["zone"][cellx] & inside
                cov = flat["covered"][cellx] & inside
                edge_suspect = (flat["near"][cellx] & inside & (z >= flat["lo"][cellx] - p["at_roof_m"]) &
                                (z <= flat["hi"][cellx] + p["at_roof_m"]))
                hag = z - flat["dtm"][cellx]
                roof = flat["roof"][cellx]
                above_roof = np.where(np.isfinite(roof), hag - roof, np.nan)
                codes = rules.label_codes(classes, in_zone, cov, edge_suspect, above_roof, p)
                before += np.bincount(classes, minlength=256)
                after += np.bincount(codes, minlength=256)
                changed = codes != classes
                if changed.any():
                    block["classification"][changed] = codes[changed]
            points.flush()
            del points, block
            label_lasd = str(labels_dir/"labels.lasd")
            arcpy.management.CreateLasDataset([str(label_las)], label_lasd, spatial_reference=sr,
                                              compute_stats="COMPUTE_STATS")
            state["label_las"] = {"path": str(label_las), "lasd": label_lasd, "points_outside_grid": outside_grid,
                                  "before": {str(i): int(n) for i, n in enumerate(before) if n},
                                  "after": {str(i): int(n) for i, n in enumerate(after) if n},
                                  "edge_band": "class 3/4/5 within {0} m of class-6 support, between the lowest "
                                               "class-6 first return there minus {1} m and the highest plus {1} m"
                                               .format(p["near_roof_m"], p["at_roof_m"])}
            lap("label_las")

            # Layer files.
            layers = destination/"layers"; layers.mkdir()
            state["layer_files"] = {}
            for name, fc_path, field, title in [("footprint_status", fc, "STATUS", "Footprint status"),
                                                ("lidar_buildings", lidar_fc, "STATUS", "Lidar buildings"),
                                                ("candidate_flags", flags_fc, "FLAG", "Candidate flags")]:
                path = str(layers/(name + ".lyrx"))
                problem = _layer_file(fc_path, path, field, title)
                state["layer_files"][name] = {"path": path, "symbology": problem or "unique values by " + field}
            lap("layers")

        # Summary.
        count_by = lambda rows, key: {k: sum(1 for r in rows if r[key] == k) for k in sorted({r[key] for r in rows})}
        state["footprint_status"] = {name: {"count": sum(1 for r in status_rows if r["source"] == name),
                                            "status": count_by([r for r in status_rows if r["source"] == name], "status"),
                                            "partial_aoi": sum(1 for r in status_rows if r["source"] == name and r["truncated"]),
                                            "small": sum(1 for r in status_rows if r["source"] == name and
                                                         r["area"] < p["min_region_area_m2"])}
                                     for name in sources}
        state["lidar_buildings"] = {
            "count": len(regions), "status": count_by(regions, "status"),
            "partial_aoi": sum(r["partial"] for r in regions),
            "inside_by_source": {n: sum(r["inside"][n] for r in regions) for n in sources},
            "status_if_only_millcreek_clipped_sources": count_by(
                [{"s": rules.region_status({n: r["inside"][n] for n in ("millcreek_extract", "osm2024") if n in sources},
                                           {n: r["covered"][n] for n in ("millcreek_extract", "osm2024") if n in sources})}
                 for r in regions], "s") if any(n in sources for n in ("millcreek_extract", "osm2024")) else None,
            "no_footprint_but_in_same_method": sum(1 for r in regions if r["status"] != "MATCHED" and
                                                   r["inside"].get("lidar_same_method"))}
        flags = count_by(flag_rows, "flag")
        state["candidate_flags"] = {
            "count": len(flag_rows), "flag": flags,
            "by_basis": {str(basis): count_by([r for r in flag_rows if r["basis"] == basis], "flag")
                         for basis in {r["basis"] for r in flag_rows}},
            "near_class6_1m": sum(r["near6"] for r in flag_rows),
            "near_class6_1m_no_ground_5m": sum(r["near6"] and not r["ground"] for r in flag_rows),
            "small_crown_by_flag": count_by([r for r in flag_rows if r["crown_status"] == "CROWN_TOO_SMALL"], "flag")}
        heights = [r for r in status_rows if r["source"] == "county" and r["attrs"].get("BLDGHEIGHT")]
        ids = [r["source_id"] for r in heights]
        ref = [r["attrs"]["BLDGHEIGHT"] for r in heights]
        state["height_comparison"] = {
            "reference": "county BLDGHEIGHT (units checked by the median ratio; about 1 means metres)",
            "n_with_height": len(heights),
            "status_of_those": count_by(heights, "status"),
            **{stat: rules.height_comparison(ref, [r[group][key] for r in heights], ids)
               for stat, group, key in [("class6_p50", "h6", "p50"), ("class6_p90", "h6", "p90"), ("class6_max", "h6", "max"),
                                        ("all_first_p50", "hall", "p50"), ("all_first_p90", "hall", "p90"),
                                        ("all_first_max", "hall", "max")]}}
        for row in inputs:
            stat = Path(row["path"]).stat()
            if (stat.st_size, stat.st_mtime_ns) != (row["bytes"], row["mtime_ns"]):
                raise RuntimeError("An input LAS file changed during reconciliation")
        state["outputs"] = {"review_gdb": str(destination/REVIEW_GDB), "footprint_status": fc,
                            "lidar_buildings": lidar_fc, "candidate_flags": flags_fc,
                            "label_las": str(label_las), "ground": ground_path}
        state["status"] = "complete"
    except Exception as exc:
        state["status"] = "failed"; state["error"] = str(exc)
        raise
    finally:
        state["elapsed_s"] = round(time.time() - started, 1)
        common.write_json(summary_path, state)
    return state
