"""Validation harness: stratified reference samples, labelling layers, and scoring.

The sample is drawn once from a BASELINE run and stored with empty label fields.
Labels come from a person looking at reference imagery; nothing here classifies
imagery. Any run folder with the standard run.json outputs is then scored against
the same labels. Pure estimators live in validation_metrics (no arcpy).
"""
from __future__ import annotations

import datetime
import json
import math
import os
from pathlib import Path
import shutil

import arcpy
import numpy as np
from scipy.spatial import cKDTree

from . import common, preparation, roofs
from .lidar_root import live
from . import validation_metrics as vm
from .run_safeguards import fingerprint, verify_fingerprint

SAMPLES = {  # sample -> (feature class, geometry, targets)
    "treetop": ("treetop_sample", "POINT", vm.TREETOP_TARGETS),
    "omission": ("omission_sample", "POINT", vm.OMISSION_TARGETS),
    "cell": ("cell_sample", "POINT", vm.CELL_TARGETS),
    "crown": ("crown_sample", "POLYGON", vm.CROWN_TARGETS),
}
DESIGN_TABLE = "sample_design"
DOMAINS = {
    "POINT_LABEL": ("What is at the point", {
        "TREE": "Tree: woody crown at least 2 m tall covers the point",
        "ROOF_OR_BUILDING": "Roof, eave, wall or other part of a building",
        "OTHER_STRUCTURE": "Pole, wire, vehicle, fence, sign, play or other structure",
        "SHRUB_UNDER_2M": "Vegetation under 2 m (shrub, hedge, lawn edge)",
        "GROUND_OR_OPEN": "Ground, pavement, lawn, water; nothing above 2 m",
        "UNSURE": "Cannot tell from the imagery"}),
    "CROWN_LABEL": ("Crown outline quality", {
        "CORRECT": "One tree, outline mostly right",
        "MERGED": "Outline covers two or more trees",
        "SPLIT": "Outline is part of a tree that has other outlines",
        "NOT_A_TREE": "Mostly not a tree (roof, structure, shrub)",
        "UNSURE": "Cannot tell from the imagery"}),
    "YES_NO_UNSURE": ("Yes / no / unsure", {"YES": "Yes", "NO": "No", "UNSURE": "Unsure"}),
}
COMMON_FIELDS = [("SAMPLE_ID", "TEXT", 48, None), ("TILE", "TEXT", 16, None),
                 ("STRATUM", "TEXT", 16, None), ("REVIEW_ORDER", "LONG", None, None),
                 ("BATCH", "SHORT", None, None)]
REVIEW_FIELDS = [("REVIEWER", "TEXT", 64, None), ("REVIEW_DATE", "DATE", None, None),
                 ("NOTES", "TEXT", 500, None)]
SAMPLE_FIELDS = {
    "treetop": COMMON_FIELDS + [
        ("CONTEXT", "TEXT", 16, None), ("BASE_TREE_ID", "TEXT", 36, None),
        ("HEIGHT_M", "DOUBLE", None, None), ("CROWN_AREA_M2", "DOUBLE", None, None),
        ("ROOF_H_M", "DOUBLE", None, None), ("BLDG_DIST_M", "DOUBLE", None, None),
        ("SEAM_REVIEW", "SHORT", None, None),
        ("LABEL", "TEXT", 20, "POINT_LABEL")] + REVIEW_FIELDS,
    "omission": COMMON_FIELDS + [
        ("BASE_CHM_M", "DOUBLE", None, None), ("BLDG_DIST_M", "DOUBLE", None, None),
        ("CANOPY_DIST_M", "DOUBLE", None, None),
        ("LABEL", "TEXT", 20, "POINT_LABEL")] + REVIEW_FIELDS,
    "cell": COMMON_FIELDS + [
        ("BASE_CHM_M", "DOUBLE", None, None), ("BLDG_DIST_M", "DOUBLE", None, None),
        ("LABEL", "TEXT", 20, "POINT_LABEL")] + REVIEW_FIELDS,
    "crown": COMMON_FIELDS + [
        ("BASE_TREE_ID", "TEXT", 36, None), ("SEED_X", "DOUBLE", None, None),
        ("SEED_Y", "DOUBLE", None, None), ("HEIGHT_M", "DOUBLE", None, None),
        ("CROWN_AREA_M2", "DOUBLE", None, None), ("BLDG_OVERLAP_M2", "DOUBLE", None, None),
        ("CROWN_LABEL", "TEXT", 20, "CROWN_LABEL"),
        ("ROOF_IN_OUTLINE", "TEXT", 8, "YES_NO_UNSURE")] + REVIEW_FIELDS,
}
# Fields hidden in the review layers so the reviewer labels blind to the stratum
# and to the pipeline's own evidence.
HIDDEN = {"STRATUM", "CONTEXT", "ROOF_H_M", "BLDG_DIST_M", "CANOPY_DIST_M", "BASE_CHM_M",
          "HEIGHT_M", "CROWN_AREA_M2", "BLDG_OVERLAP_M2", "SEAM_REVIEW", "BATCH", "TILE",
          "BASE_TREE_ID", "SEED_X", "SEED_Y"}
LABEL_FIELD = {"treetop": "LABEL", "omission": "LABEL", "cell": "LABEL", "crown": "CROWN_LABEL"}
CANDIDATE_NEAR_M = 5.0


# ---------------------------------------------------------------- inputs

def run_outputs(folder):
    manifest = Path(folder) / "run.json"
    if not manifest.is_file():
        raise FileNotFoundError(f"No run.json in {folder}")
    state = json.loads(manifest.read_text(encoding="utf-8"))
    if state.get("status") != "complete" or not state.get("outputs"):
        raise ValueError(f"Run in {folder} is not complete")
    missing = [k for k in ("chm", "treetops", "crowns", "trees_review") if k not in state["outputs"]]
    if missing:
        raise ValueError(f"Run in {folder} lacks outputs {missing}")
    outputs = {k: str(live(v)) if isinstance(v, str) else v for k, v in state["outputs"].items()}
    absent = [k for k, path in outputs.items() if not arcpy.Exists(path)]
    if absent:
        raise ValueError(f"Completed run in {folder} has missing datasets: {absent}")
    return outputs, state.get("parameters", {})


class Grid:
    def __init__(self, path):
        raster = arcpy.Raster(path)
        self.path = str(path)
        self.array = arcpy.RasterToNumPyArray(raster, nodata_to_value=np.nan).astype(np.float64)
        self.cell = raster.meanCellWidth
        if not math.isclose(self.cell, raster.meanCellHeight, rel_tol=0, abs_tol=1e-9):
            raise ValueError("Evaluation requires square raster cells")
        self.xmin, self.ymax = raster.extent.XMin, raster.extent.YMax
        self.sr = raster.spatialReference

    def index(self, x, y):
        col = np.floor((np.asarray(x) - self.xmin) / self.cell).astype(int)
        row = np.floor((self.ymax - np.asarray(y)) / self.cell).astype(int)
        inside = (row >= 0) & (row < self.array.shape[0]) & (col >= 0) & (col < self.array.shape[1])
        return row, col, inside

    def at(self, x, y):
        row, col, inside = self.index(x, y)
        values = np.full(np.shape(row), np.nan)
        values[inside] = self.array[row[inside], col[inside]]
        return values

    def centre(self, row, col):
        return self.xmin + (col + .5)*self.cell, self.ymax - (row + .5)*self.cell


def las_points(folder, extent, margin, codes):
    """Class code -> N x 3 array of points within extent + margin, from every LAS file."""
    xmin, ymin, xmax, ymax = extent[0]-margin, extent[1]-margin, extent[2]+margin, extent[3]+margin
    found = {code: [] for code in codes}
    for path in sorted(Path(folder).glob("*.las")):
        bounds = preparation.header(path)["extent"]
        if bounds[0] > xmax or bounds[2] < xmin or bounds[1] > ymax or bounds[3] < ymin:
            continue
        points, scale, offset, modern = roofs._records(path)
        classes = np.asarray(points["classification"])
        if not modern:
            classes = classes & 31
        for code in codes:
            chosen = np.flatnonzero(classes == code)
            if not len(chosen):
                continue
            subset = points[chosen]
            xyz = np.column_stack([subset[a]*scale[i] + offset[i] for i, a in enumerate("xyz")])
            keep = ((xyz[:, 0] >= xmin) & (xyz[:, 0] <= xmax) &
                    (xyz[:, 1] >= ymin) & (xyz[:, 1] <= ymax))
            found[code].append(xyz[keep])
        del points
    return {code: np.vstack(parts) if parts else np.zeros((0, 3)) for code, parts in found.items()}


def building_cells(grid, building):
    """Mark CHM cells holding at least one class-6 return."""
    row, col, inside = grid.index(building[:, 0], building[:, 1])
    mask = np.zeros(grid.array.shape, dtype=bool)
    mask[row[inside], col[inside]] = True
    return mask


# ---------------------------------------------------------------- sampling

def _treetop_frame(outputs, building, ground):
    rows = list(arcpy.da.SearchCursor(outputs["trees_review"], [
        "TREE_ID", "SHAPE@X", "SHAPE@Y", "HEIGHT_M", "CROWN_AREA_M2", "SEAM_REVIEW"]))
    xy = np.array([(r[1], r[2]) for r in rows]) if rows else np.zeros((0, 2))
    btree, gtree = cKDTree(building[:, :2]), cKDTree(ground[:, :2])
    distance = btree.query(xy, distance_upper_bound=50, workers=-1)[0] if len(building) else \
        np.full(len(rows), np.inf)
    frame = {}
    for (tree_id, x, y, height, area, seam), dist in zip(rows, distance):
        roof_h = None
        if dist <= vm.NEAR_BUILDING_M:
            roof = btree.query_ball_point((x, y), vm.NEAR_BUILDING_M)
            for radius in (5.0, 10.0):
                under = gtree.query_ball_point((x, y), radius)
                if under:
                    roof_h = float(np.percentile(building[roof, 2], 90) - np.median(ground[under, 2]))
                    break
        context = vm.treetop_context(float(dist) if np.isfinite(dist) else None, height, roof_h)
        frame[str(tree_id)] = {
            "x": x, "y": y, "stratum": vm.treetop_stratum(seam, context, area or 0.0),
            "CONTEXT": context, "BASE_TREE_ID": str(tree_id), "HEIGHT_M": height,
            "CROWN_AREA_M2": area, "ROOF_H_M": roof_h,
            "BLDG_DIST_M": float(dist) if np.isfinite(dist) else None, "SEAM_REVIEW": seam}
    return frame


def _crown_frame(outputs, grid, bcells, treetops):
    from scipy import ndimage
    dilated = ndimage.binary_dilation(bcells, iterations=max(1, int(round(1.0/grid.cell))))
    with common.scratch() as (_, gdb), common.environment(grid.path):
        labels = os.path.join(gdb, "crown_cells")
        oid = arcpy.Describe(outputs["crowns"]).OIDFieldName
        arcpy.conversion.PolygonToRaster(outputs["crowns"], oid, labels, "CELL_CENTER",
                                         cellsize=grid.cell)
        cells = arcpy.RasterToNumPyArray(labels, nodata_to_value=0).astype(np.int64)
    if cells.shape != grid.array.shape:
        raise RuntimeError("Crown raster does not align with the CHM")
    overlap = np.bincount(cells[dilated], minlength=int(cells.max())+1) * grid.cell**2
    frame = {}
    for oid_value, tree_id, height, area in arcpy.da.SearchCursor(
            outputs["crowns"], ["OID@", "TREE_ID", "HEIGHT_M", "CROWN_AREA_M2"]):
        over = float(overlap[oid_value]) if oid_value < len(overlap) else 0.0
        seed = treetops.get(str(tree_id))
        frame[int(oid_value)] = {
            "stratum": vm.crown_stratum(area, over), "BASE_TREE_ID": str(tree_id),
            "SEED_X": seed["x"] if seed else None, "SEED_Y": seed["y"] if seed else None,
            "HEIGHT_M": height, "CROWN_AREA_M2": area, "BLDG_OVERLAP_M2": over}
    return frame


def build_reference(root, tiles, out_folder, seed, run_name="run", prepared_name="prepared"):
    """Draw every sample from the baseline runs of the given tiles.

    tiles: {tile: (xmin, ymin, xmax, ymax)}. Writes out_folder/reference.gdb and
    out_folder/sample_design.json. Refuses to overwrite an existing reference.
    """
    out_folder = Path(out_folder)
    gdb = out_folder / "reference.gdb"
    if gdb.exists() or (out_folder / "sample_design.json").exists():
        raise FileExistsError(f"{gdb} already exists; labels are never overwritten. "
                              "Use a new validation folder for a new sample.")
    units = {name: [] for name in SAMPLES}
    design = []
    sr = None
    for tile, extent in tiles.items():
        run_folder = Path(root) / tile / run_name
        outputs, parameters = run_outputs(run_folder)
        grid = Grid(outputs["chm"])
        sr = sr or grid.sr
        if not common.same_xy_reference(sr, grid.sr):
            raise ValueError("All tiles must share one spatial reference")
        if not math.isclose(grid.cell, 0.5):
            arcpy.AddWarning(f"{tile}: CHM cell is {grid.cell} m, not 0.5 m")
        points = las_points(Path(root) / tile / prepared_name / "points", extent, 12.0, (2, 6))
        building, ground = points[6], points[2]
        bcells = building_cells(grid, building)
        omission_codes, cell_codes, bdist, cdist = vm.cell_strata(grid.array, bcells, grid.cell)
        cell_area = grid.cell**2
        treetops = _treetop_frame(outputs, building, ground)
        crowns = _crown_frame(outputs, grid, bcells, treetops)
        frames = {
            "treetop": (treetops, 1.0, "baseline trees_review candidates"),
            "crown": (crowns, 1.0, "baseline crown polygons (>= minimum crown area)"),
        }
        for name, (frame, unit_area, what) in frames.items():
            for stratum, target in SAMPLES[name][2].items():
                keys = [k for k, v in frame.items() if v["stratum"] == stratum]
                chosen = vm.draw(keys, target, vm.seed_for(seed, name, tile, stratum))
                design.append({"sample": name, "tile": tile, "stratum": stratum,
                               "population": len(keys), "unit_area_m2": None, "target": target,
                               "sampled": len(chosen), "frame": what})
                for rank, key in enumerate(chosen, 1):
                    units[name].append({**frame[key], "key": f"{tile}|{name}|{key}", "tile": tile,
                                        "stratum": stratum, "rank": rank, "source": key})
        for name, codes, what in (("omission", omission_codes, "baseline non-canopy CHM cells"),
                                  ("cell", cell_codes, "baseline observed CHM cells")):
            flat = codes.ravel()
            for stratum, target in SAMPLES[name][2].items():
                keys = np.flatnonzero(flat == stratum)
                chosen = vm.draw(keys, target, vm.seed_for(seed, name, tile, stratum))
                design.append({"sample": name, "tile": tile, "stratum": stratum,
                               "population": int(len(keys)), "unit_area_m2": cell_area,
                               "target": target, "sampled": len(chosen), "frame": what})
                for rank, key in enumerate(chosen, 1):
                    row, col = divmod(int(key), codes.shape[1])
                    x, y = grid.centre(row, col)
                    value = grid.array[row, col]
                    unit = {"key": f"{tile}|{name}|{row}_{col}", "tile": tile, "stratum": stratum,
                            "rank": rank, "x": x, "y": y,
                            "BASE_CHM_M": None if np.isnan(value) else float(value),
                            "BLDG_DIST_M": float(bdist[row, col])}
                    if name == "omission":
                        unit["CANOPY_DIST_M"] = float(cdist[row, col])
                    units[name].append(unit)
        for entry in design:
            if entry["tile"] == tile:
                entry["base_run"] = str(run_folder)
                entry["chm"] = outputs["chm"]
        arcpy.AddMessage(f"{tile}: sample drawn")
    for name in SAMPLES:
        order = vm.review_order([(u["key"], (u["tile"], u["stratum"])) for u in units[name]],
                                vm.seed_for(seed, name, "review-order"))
        for unit in units[name]:
            unit["REVIEW_ORDER"], unit["BATCH"] = order[unit["key"]]
            unit["SAMPLE_ID"] = f"{name[:2].upper()}{unit['REVIEW_ORDER']:04d}"
    out_folder.mkdir(parents=True, exist_ok=True)
    create_reference_gdb(gdb, sr)
    write_units(gdb, units, root_crowns={t: run_outputs(Path(root)/t/run_name)[0]["crowns"]
                                         for t in tiles})
    write_design(gdb, design)
    document = {"created": datetime.datetime.now().isoformat(timespec="seconds"), "seed": seed,
                "root": str(root), "tiles": {t: list(e) for t, e in tiles.items()},
                "run_name": run_name, "prepared_name": prepared_name,
                "baseline_manifests": {t: fingerprint(Path(root) / t / run_name / "run.json") for t in tiles},
                "parameters": _design_parameters(), "strata": design}
    common.write_json(out_folder / "sample_design.json", document)
    return document


def _design_parameters():
    return {k: getattr(vm, k) for k in (
        "CANOPY_M", "ROOF_LEVEL_M", "OVERHANG_M", "NEAR_BUILDING_M", "SMALL_CROWN_M2",
        "CELL_NEAR_M", "DENSE_RADIUS_M", "DENSE_SHARE", "EDGE_M", "CROWN_BLDG_M2",
        "CROWN_SMALL_MAX_M2", "CROWN_LARGE_MIN_M2", "MATCH_RADIUS_M", "CROWN_SAME_IOU",
        "TREETOP_TARGETS", "OMISSION_TARGETS", "CELL_TARGETS", "CROWN_TARGETS")}


# ---------------------------------------------------------------- reference gdb

def create_reference_gdb(gdb, sr):
    gdb = Path(gdb)
    arcpy.management.CreateFileGDB(str(gdb.parent), gdb.name)
    for name, (description, codes) in DOMAINS.items():
        arcpy.management.CreateDomain(str(gdb), name, description, "TEXT", "CODED")
        for code, text in codes.items():
            arcpy.management.AddCodedValueToDomain(str(gdb), name, code, text)
    for sample, (fc, geometry, _) in SAMPLES.items():
        arcpy.management.CreateFeatureclass(str(gdb), fc, geometry, spatial_reference=sr)
        arcpy.management.AddFields(str(gdb / fc), [
            [n, t, n, length or "", "", domain or ""] for n, t, length, domain in SAMPLE_FIELDS[sample]])
    arcpy.management.CreateTable(str(gdb), DESIGN_TABLE)
    arcpy.management.AddFields(str(gdb / DESIGN_TABLE), [
        ["SAMPLE", "TEXT", "SAMPLE", 16], ["TILE", "TEXT", "TILE", 16],
        ["STRATUM", "TEXT", "STRATUM", 16], ["POP_N", "LONG"], ["UNIT_AREA_M2", "DOUBLE"],
        ["TARGET_N", "LONG"], ["N_SAMPLED", "LONG"], ["FRAME", "TEXT", "FRAME", 120],
        ["BASE_RUN", "TEXT", "BASE_RUN", 400], ["BASE_CHM", "TEXT", "BASE_CHM", 400]])


def write_units(gdb, units, root_crowns=None):
    """Insert units. Crown units need root_crowns {tile: crowns fc} for geometry."""
    gdb = Path(gdb)
    for sample, rows in units.items():
        fc = str(gdb / SAMPLES[sample][0])
        names = [f[0] for f in SAMPLE_FIELDS[sample]
                 if f[0] not in ("LABEL", "CROWN_LABEL", "ROOF_IN_OUTLINE", "REVIEWER",
                                 "REVIEW_DATE", "NOTES")]
        values = [n for n in names if n not in ("TILE", "STRATUM")]
        with arcpy.da.InsertCursor(fc, ["SHAPE@", "TILE", "STRATUM", *values]) as cursor:
            for unit in rows:
                if sample == "crown":
                    shape = unit.get("shape") or _crown_shape(root_crowns[unit["tile"]], unit["source"])
                else:
                    shape = arcpy.PointGeometry(arcpy.Point(unit["x"], unit["y"]))
                cursor.insertRow([shape, unit["tile"], unit["stratum"], *[unit.get(n) for n in values]])


def _crown_shape(crowns, oid):
    where = f"{arcpy.Describe(crowns).OIDFieldName} = {int(oid)}"
    shapes = [r[0] for r in arcpy.da.SearchCursor(crowns, ["SHAPE@"], where)]
    if len(shapes) != 1:
        raise RuntimeError(f"Expected one crown with OID {oid}, found {len(shapes)}")
    return shapes[0]


def write_design(gdb, design):
    with arcpy.da.InsertCursor(str(Path(gdb) / DESIGN_TABLE), [
            "SAMPLE", "TILE", "STRATUM", "POP_N", "UNIT_AREA_M2", "TARGET_N", "N_SAMPLED",
            "FRAME", "BASE_RUN", "BASE_CHM"]) as cursor:
        for d in design:
            cursor.insertRow([d["sample"], d["tile"], d["stratum"], d["population"],
                              d["unit_area_m2"], d["target"], d["sampled"], d["frame"],
                              d.get("base_run"), d.get("chm")])


def read_reference(gdb):
    """Return (units {sample: [dict]}, design [dict])."""
    gdb = Path(gdb)
    design = []
    with arcpy.da.SearchCursor(str(gdb / DESIGN_TABLE), [
            "SAMPLE", "TILE", "STRATUM", "POP_N", "UNIT_AREA_M2", "BASE_RUN"]) as cursor:
        for sample, tile, stratum, pop, area, base in cursor:
            design.append({"sample": sample, "tile": tile, "stratum": stratum,
                           "population": pop, "unit_area_m2": area, "base_run": base})
    units = {}
    for sample, (fc, _, _) in SAMPLES.items():
        names = [f[0] for f in SAMPLE_FIELDS[sample]]
        rows = []
        with arcpy.da.SearchCursor(str(gdb / fc), ["SHAPE@", "SHAPE@X", "SHAPE@Y", *names]) as cursor:
            for shape, x, y, *values in cursor:
                row = dict(zip(names, values))
                row.update(shape=shape, x=x, y=y)
                rows.append(row)
        units[sample] = rows
    return units, design


# ---------------------------------------------------------------- reference labels

def _label_frame(gdb):
    """Canonical sample identity/geometry, with review answers kept separately."""
    import hashlib
    units, design = read_reference(gdb)
    frames = []
    for sample, rows in units.items():
        for unit in rows:
            shape = unit['shape']
            if shape is None:
                raise ValueError('Reference sample has missing geometry')
            frames.append({k: v for k, v in unit.items() if k != 'shape'} | {
                'sample': sample, 'geometry_sha256': hashlib.sha256(bytes(shape.WKB)).hexdigest()})
    return frames, design


def export_labels(gdb, out_folder, batch=1):
    """Export a blind worksheet bound to this fixed reference, without editing it."""
    import csv
    from . import label_exchange as exchange
    gdb, out_folder = Path(gdb).resolve(), Path(out_folder).resolve()
    if out_folder.exists() and any(out_folder.iterdir()):
        raise FileExistsError('Label packet folder is not empty; choose a new folder')
    frames, design = _label_frame(gdb)
    digest = exchange.reference_digest(frames, design)
    rows = exchange.export_rows(frames, digest, batch)
    out_folder.mkdir(parents=True, exist_ok=True)
    path = out_folder / 'labels.csv'
    with path.open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.DictWriter(handle, fieldnames=exchange.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    counts = {sample: sum(r['SAMPLE'] == sample for r in rows) for sample in SAMPLES}
    manifest = {'schema_version': 1, 'created': datetime.datetime.now().isoformat(),
        'reference': str(gdb), 'frame_digest': digest, 'batch': batch,
        'worksheet': fingerprint(path), 'exported_counts': counts,
        'units': [[r['SAMPLE'], r['SAMPLE_ID']] for r in rows],
        'reference_units': len(frames), 'quality_status': 'UNLABELLED_UNTIL_INDEPENDENT_REVIEW'}
    common.write_json(out_folder / 'packet.json', manifest)
    guide = ['# Independent reference review', '',
        'Work through each sample type in REVIEW_ORDER. Find SAMPLE_ID in the corresponding ArcGIS sample layer.',
        'Keep SAMPLE, SAMPLE_ID, REVIEW_ORDER and UNIT_TOKEN unchanged. Edit only the five answer fields.',
        'Use acquisition-matched imagery; turn off baseline CHM/crown overlays while answering point questions.',
        'For crown questions, inspect the sampled outline. Keep model outputs and stratum diagnostics hidden.',
        'Do not skip hard cases: use UNSURE and explain the ambiguity in NOTES. Leave unreviewed LABEL cells blank.',
        'REVIEWER is required; REVIEW_DATE must be YYYY-MM-DD. Notes can contain up to 500 characters.',
        'ROOF_IN_OUTLINE is for crowns only (YES, NO or UNSURE); it may remain blank if not assessed.',
        'Review in the seeded order. Choosing only easy cases can bias the stratified estimates.', '',
        'Point labels:', '']
    guide += [f'- {key}: {value}' for key, value in DOMAINS['POINT_LABEL'][1].items()]
    guide += ['', 'Crown labels:', '']
    guide += [f'- {key}: {value}' for key, value in DOMAINS['CROWN_LABEL'][1].items()]
    project = gdb.parent / 'review' / 'validation_review.aprx'
    if project.is_file():
        guide += ['', f'[Open the existing ArcGIS review project]({project.as_posix()})']
    guide += ['', 'The worksheet is for independent answers. packet.json is the coordinator manifest.',
        'Preview the import first; apply requires --apply and a fresh --audit-dir. Then rerun score.', '']
    (out_folder / 'REVIEW.md').write_text('\n'.join(guide), encoding='utf-8')
    return manifest


def _write_label_changes(gdb, changes):
    """Update only review fields; called inside one geodatabase edit operation."""
    for sample in SAMPLES:
        mine = {change['sample_id']: change for change in changes if change['sample'] == sample}
        if not mine:
            continue
        fields = list(next(iter(mine.values()))['after'])
        seen = set()
        with arcpy.da.UpdateCursor(str(Path(gdb) / SAMPLES[sample][0]), ['SAMPLE_ID', *fields]) as cursor:
            for row in cursor:
                change = mine.get(row[0])
                if change is None:
                    continue
                if row[0] in seen:
                    raise ValueError('Duplicate sample appeared during label import')
                seen.add(row[0])
                values = [change['after'][field] for field in fields]
                values[fields.index('REVIEW_DATE')] = datetime.datetime.fromisoformat(change['after']['REVIEW_DATE'])
                cursor.updateRow([row[0], *values])
        if seen != set(mine):
            raise ValueError('Sample disappeared during label import')


def import_labels(gdb, csv_path, packet_path, apply=False, audit_folder=None, replace_existing=False):
    """Preview a fully validated import; explicit apply uses an atomic edit session."""
    import csv
    import hashlib
    import io
    from . import label_exchange as exchange
    gdb, csv_path, packet_path = Path(gdb).resolve(), Path(csv_path).resolve(), Path(packet_path).resolve()
    packet_bytes, submitted = packet_path.read_bytes(), csv_path.read_bytes()
    packet = json.loads(packet_bytes.decode('utf-8'))
    if packet.get('schema_version') != 1 or Path(packet.get('reference', '')).resolve() != gdb:
        raise ValueError('Label packet belongs to a different reference geodatabase')
    with io.StringIO(submitted.decode('utf-8-sig'), newline='') as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(exchange.COLUMNS):
            raise ValueError('Worksheet columns/order differ from the exported label schema')
        rows = list(reader)
    allowed = {tuple(key) for key in packet['units']}
    if any((row.get('SAMPLE'), row.get('SAMPLE_ID')) not in allowed for row in rows):
        raise ValueError('Worksheet contains a sample that was not exported in this packet')

    def plan():
        frames, design = _label_frame(gdb)
        digest = exchange.reference_digest(frames, design)
        if digest != packet['frame_digest']:
            raise ValueError('Reference sampling frame/geometry changed after export; create a new packet')
        result = exchange.plan_import(rows, frames, digest, replace_existing)
        return result | {'status': 'DRY_RUN', 'reference': str(gdb), 'frame_digest': digest,
            'worksheet': {'path': str(csv_path), 'bytes': len(submitted), 'sha256': hashlib.sha256(submitted).hexdigest()},
            'packet': {'path': str(packet_path), 'bytes': len(packet_bytes), 'sha256': hashlib.sha256(packet_bytes).hexdigest()},
            'replace_existing': replace_existing, 'created': datetime.datetime.now().isoformat()}

    report = plan()
    if not apply:
        return report
    if audit_folder is None:
        raise ValueError('Applying labels requires a new audit folder')
    audit_folder = Path(audit_folder).resolve()
    if audit_folder.exists() and any(audit_folder.iterdir()):
        raise FileExistsError('Audit folder is not empty; choose a new folder')
    audit_folder.mkdir(parents=True, exist_ok=True)
    audit_path = audit_folder / 'import.json'
    # Keep the submitted bytes beside the before/after audit. These are review
    # records, not source geometry, and the preview above already validated them.
    (audit_folder / 'submitted-labels.csv').write_bytes(submitted)
    report['status'] = 'PENDING'
    common.write_json(audit_path, report)
    try:
        with arcpy.da.Editor(str(gdb), multiuser_mode=False):
            # Revalidate the current reference/answers after entering the session.
            report = plan()
            report['status'] = 'PENDING_COMMIT'
            common.write_json(audit_path, report)
            _write_label_changes(gdb, report['changes'])
    except Exception as exc:
        report.update(status='ROLLED_BACK', error=str(exc))
        common.write_json(audit_path, report)
        raise
    report['status'] = 'APPLIED'
    common.write_json(audit_path, report)
    return report


# ---------------------------------------------------------------- scoring

class RunView:
    """A run's outputs as seen by the scorer; optional TREE_IDs dropped from its treetops."""

    def __init__(self, folder, drop_ids=None):
        self.folder = str(folder)
        self.outputs, self.parameters = run_outputs(folder)
        self.grid = Grid(self.outputs["chm"])
        rows = list(arcpy.da.SearchCursor(self.outputs["treetops"], ["TREE_ID", "SHAPE@X", "SHAPE@Y"]))
        drop = set(drop_ids or ())
        kept = [r for r in rows if str(r[0]) not in drop]
        self.dropped = len(rows) - len(kept)
        rows = kept
        self.ids = [str(r[0]) for r in rows]
        if len(set(self.ids)) != len(self.ids):
            raise ValueError("Run has duplicate TREE_ID values")
        self.xy = np.array([(r[1], r[2]) for r in rows]) if rows else np.zeros((0, 2))
        self.tree = cKDTree(self.xy) if len(self.xy) else None

    def near(self, xy, radius):
        if self.tree is None or not len(xy):
            return np.zeros(len(xy), dtype=bool)
        return self.tree.query(xy, workers=-1)[0] <= radius

    def crown_iou(self, polygon):
        best = 0.0
        with arcpy.da.SearchCursor(self.outputs["crowns"], ["SHAPE@"], spatial_filter=polygon,
                                   spatial_relationship="INTERSECTS") as cursor:
            for (shape,) in cursor:
                inter = shape.intersect(polygon, 4).area
                union = shape.area + polygon.area - inter
                if union > 0:
                    best = max(best, inter/union)
        return best


def flagged_ids(table, field, values, key="TREE_ID"):
    """TREE_IDs whose flag field takes one of values (e.g. ON_ROOF, ROOF_EDGE)."""
    values = {str(v) for v in values}
    return {str(r[0]) for r in arcpy.da.SearchCursor(table, [key, field]) if str(r[1]) in values}


def run_units(units, design, tile, view):
    """Attach the run's answers (retained / canopy / crown IoU) to one tile's units."""
    base = next(d["base_run"] for d in design if d["tile"] == tile)
    same_folder = os.path.normcase(os.path.abspath(base)) == os.path.normcase(os.path.abspath(view.folder))
    baseline = view if same_folder and not view.dropped else RunView(base)
    if (view.grid.array.shape != baseline.grid.array.shape or
            view.grid.sr.exportToString() != baseline.grid.sr.exportToString() or
            any(not math.isclose(a, b, rel_tol=0, abs_tol=1e-6) for a, b in (
                (view.grid.cell, baseline.grid.cell), (view.grid.xmin, baseline.grid.xmin),
                (view.grid.ymax, baseline.grid.ymax)))):
        raise ValueError(f"Run grid differs from reference baseline for {tile}")
    correspondence = vm.match_candidates(baseline.xy, view.xy, vm.MATCH_RADIUS_M,
        baseline.ids if same_folder else None, view.ids if same_folder else None)
    out = {}
    tt = [u for u in units["treetop"] if u["TILE"] == tile]
    xy = np.array([(u["x"], u["y"]) for u in tt]) if tt else np.zeros((0, 2))
    source = {key: i for i, key in enumerate(baseline.ids)}
    retained = []
    for unit, point in zip(tt, xy):
        key = unit.get("BASE_TREE_ID")
        index = source.get(str(key)) if key not in (None, "") else None
        if index is None and key in (None, "") and baseline.tree is not None:
            distance, index = baseline.tree.query(point)
            index = int(index) if distance <= 1e-6 else None
        if index is None or np.linalg.norm(baseline.xy[index] - point) > 1e-6:
            raise ValueError("Reference treetop is absent or moved in its baseline run; redraw the sample")
        retained.append(correspondence["baseline_to_variant"][index] >= 0)
    out["treetop"] = [{"stratum": f"{tile}|{u['STRATUM']}", "label": u["LABEL"], "retained": bool(k)}
                      for u, k in zip(tt, retained)]
    # Run candidates with no baseline candidate nearby were never in the sampling frame.
    new = int((correspondence["variant_to_baseline"] < 0).sum())
    for sample in ("omission", "cell"):
        mine = [u for u in units[sample] if u["TILE"] == tile]
        xy = np.array([(u["x"], u["y"]) for u in mine]) if mine else np.zeros((0, 2))
        chm = view.grid.at(xy[:, 0], xy[:, 1]) if len(xy) else np.zeros(0)
        near = view.near(xy, CANDIDATE_NEAR_M)
        out[sample] = [{"stratum": f"{tile}|{u['STRATUM']}", "label": u["LABEL"],
                        "canopy": bool(np.isfinite(v) and v >= vm.CANOPY_M), "candidate_near": bool(n)}
                       for u, v, n in zip(mine, chm, near)]
    crowns = []
    for u in (u for u in units["crown"] if u["TILE"] == tile):
        iou = 1.0 if view is baseline else view.crown_iou(u["shape"])
        crowns.append({"stratum": f"{tile}|{u['STRATUM']}", "label": u["CROWN_LABEL"],
                       "roof": u["ROOF_IN_OUTLINE"], "same": iou >= vm.CROWN_SAME_IOU, "iou": iou})
    out["crown"] = crowns
    base_grid = baseline.grid
    base_observed = np.isfinite(base_grid.array)
    canopy = np.isfinite(view.grid.array) & (view.grid.array >= vm.CANOPY_M)
    if view.grid.array.shape == base_grid.array.shape and \
            math.isclose(view.grid.xmin, base_grid.xmin) and math.isclose(view.grid.ymax, base_grid.ymax):
        mapped = int((canopy & base_observed).sum())
    else:
        mapped = None
    return out, {"new_candidates": new, "run_candidates": len(view.xy), "dropped_by_flags": view.dropped,
                 "matching_method": "ONE_TO_ONE_MAX_CARDINALITY_MIN_DISTANCE",
                 "ambiguous_baseline": correspondence["ambiguous_baseline"],
                 "ambiguous_variant": correspondence["ambiguous_variant"],
                 "mapped_canopy_cells_in_frame": mapped,
                 "mapped_canopy_m2_total": float(canopy.sum()*view.grid.cell**2)}


def score_units(tile_units, info, design, tiles, replicates=2000, seed=0):
    """Score answers already gathered for one or more tiles."""
    population = {}
    area = {}
    for d in design:
        if d["tile"] in tiles:
            population.setdefault(d["sample"], {})[f"{d['tile']}|{d['stratum']}"] = d["population"]
            if d["unit_area_m2"]:
                if d["sample"] in area and not math.isclose(area[d["sample"]], d["unit_area_m2"]):
                    raise ValueError("Cannot combine reference samples with different cell areas")
                area[d["sample"]] = d["unit_area_m2"]
    merged = {s: [u for t in tiles for u in tile_units[t][s]] for s in SAMPLES}
    new = sum(info[t]["new_candidates"] for t in tiles)
    mapped = [info[t]["mapped_canopy_cells_in_frame"] for t in tiles]
    mapped = None if any(m is None for m in mapped) else sum(mapped)
    return {
        "treetops": vm.score_treetops(merged["treetop"], population["treetop"], new,
                                      sum(info[t]["run_candidates"] for t in tiles), replicates, seed),
        "cells": vm.score_cells(merged["cell"], population["cell"], area.get("cell", .25), mapped,
                                replicates, seed),
        "omission": vm.score_omission(merged["omission"], population["omission"],
                                      area.get("omission", .25), replicates, seed),
        "combined": vm.combined_omission_rate(merged["cell"], population["cell"], merged["omission"],
                                              population["omission"], replicates, seed),
        "crowns": vm.score_crowns(merged["crown"], population["crown"], replicates, seed),
        "inputs": {t: info[t] for t in tiles},
    }


def score(gdb, runs, out_folder, replicates=2000, seed=0):
    """Score every run against the reference labels.

    runs: [{"name": str, "folders": {tile: folder}, "drop": {tile: set(TREE_ID)} (optional)}].
    Writes score.json, comparison.csv and comparison.md in out_folder. Returns the report.
    """
    out_folder = Path(out_folder)
    if out_folder.exists() and any(out_folder.iterdir()):
        raise ValueError("Score output is not empty; choose a new report folder")
    reference_document = Path(gdb).parent / "sample_design.json"
    reference_info = json.loads(reference_document.read_text(encoding="utf-8")) if reference_document.is_file() else {}
    for record in reference_info.get("baseline_manifests", {}).values():
        verify_fingerprint(record, record["path"])
    units, design = read_reference(gdb)
    labelled = {s: sum(1 for u in rows if u[LABEL_FIELD[s]] not in (None, "")) for s, rows in units.items()}
    total = {s: len(rows) for s, rows in units.items()}
    report = {"created": datetime.datetime.now().isoformat(timespec="seconds"),
              "evaluation_version": 2,
              "reference_provenance": "MANIFESTS_VERIFIED" if reference_info.get("baseline_manifests") else "LEGACY_SAMPLE_WITHOUT_MANIFEST_FINGERPRINTS",
              "reference": str(gdb), "labelled": labelled, "units": total,
              "status": "NO_LABELS" if not any(labelled.values()) else "LABELLED", "runs": {}}
    scores = {}
    for run in runs:
        tile_units, info, skipped = {}, {}, {}
        for tile, folder in run["folders"].items():
            if tile not in {d["tile"] for d in design}:
                skipped[tile] = "tile not in the reference sample"
                continue
            try:
                view = RunView(folder, (run.get("drop") or {}).get(tile))
            except (FileNotFoundError, ValueError) as exc:
                skipped[tile] = str(exc)
                continue
            tile_units[tile], info[tile] = run_units(units, design, tile, view)
        tiles = sorted(tile_units)
        entry = {"folders": {t: str(f) for t, f in run["folders"].items()}, "skipped": skipped,
                 "run_manifests": {t: fingerprint(Path(run["folders"][t]) / "run.json") for t in tiles},
                 "scopes": {}}
        from .evaluation_design import scopes as reporting_scopes
        scopes = reporting_scopes(tiles)
        for scope, members in scopes:
            result = score_units(tile_units, info, design, members, replicates, seed)
            entry["scopes"][scope] = result
            scores[(run["name"], scope)] = result
        report["runs"][run["name"]] = entry
    rows = vm.comparison_rows(scores)
    out_folder = Path(out_folder)
    out_folder.mkdir(parents=True, exist_ok=True)
    common.write_json(out_folder / "score.json", report)
    import csv
    with open(out_folder / "comparison.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["run", "scope", "metric", "key", "status", "value"])
        writer.writeheader()
        writer.writerows(rows)
    table = vm.markdown_table(rows) if rows else "(no runs scored)"
    (out_folder / "comparison.md").write_text(_summary(report) + "\n\n" + table + "\n", encoding="utf-8")
    report["table"] = table
    return report


def _summary(report):
    parts = ", ".join(f"{s} {report['labelled'][s]}/{report['units'][s]}" for s in report["units"])
    if report["status"] == "NO_LABELS":
        return (f"No labels yet: 0 of {sum(report['units'].values())} reference units are labelled "
                f"({parts}). Label the samples in ArcGIS Pro, then score again.")
    return f"Labelled units: {parts}."


# ---------------------------------------------------------------- review layers

def review_layers(gdb, out_folder, chm_paths=None, crown_paths=None):
    """Write one .lyrx per sample (blind fields hidden) and a review .aprx.

    The Nearmap WMS is NOT added: its URL carries a private key. Add it once in Pro
    (Insert > Connections > New WMS Server).
    """
    out_folder = Path(out_folder)
    out_folder.mkdir(parents=True, exist_ok=True)
    template = Path(arcpy.GetInstallInfo()["InstallDir"]) / \
        r"Resources\ArcToolBox\Services\routingservices\data\Blank.aprx"
    project_path = out_folder / "validation_review.aprx"
    if project_path.exists():
        raise FileExistsError(f"{project_path} exists; move it aside to rebuild the review project")
    shutil.copyfile(template, project_path)
    project = arcpy.mp.ArcGISProject(str(project_path))
    for existing in project.listMaps():
        project.deleteItem(existing)
    review_map = project.createMap("Validation review", "MAP")
    for basemap in review_map.listLayers():
        review_map.removeLayer(basemap)
    review_map.spatialReference = arcpy.Describe(str(Path(gdb) / SAMPLES["treetop"][0])).spatialReference
    for tile, path in (chm_paths or {}).items():
        layer = review_map.addDataFromPath(path)
        layer.name = f"Baseline CHM {tile}"
        layer.visible = False
    for tile, path in (crown_paths or {}).items():
        layer = review_map.addDataFromPath(path)
        layer.name = f"Baseline crowns {tile}"
        _outline(layer, [0, 160, 255, 100], 0.7)
    written = []
    colours = {"crown": [255, 0, 255, 100], "treetop": [255, 0, 255, 100],
               "omission": [255, 170, 0, 100], "cell": [0, 230, 255, 100]}
    for sample in ("crown", "cell", "omission", "treetop"):
        fc = str(Path(gdb) / SAMPLES[sample][0])
        info = arcpy.FieldInfo()
        for field in arcpy.ListFields(fc):
            info.addField(field.name, field.name, "HIDDEN" if field.name in HIDDEN else "VISIBLE", "NONE")
        name = f"{sample.capitalize()} sample"
        temp = arcpy.management.MakeFeatureLayer(fc, name, field_info=info)[0]
        lyrx = out_folder / f"{sample}_sample.lyrx"
        if lyrx.exists():
            lyrx.unlink()
        arcpy.management.SaveToLayerFile(temp, str(lyrx), "ABSOLUTE")
        arcpy.management.Delete(temp)
        layer_file = arcpy.mp.LayerFile(str(lyrx))
        layer = layer_file.listLayers()[0]
        if sample == "crown":
            _outline(layer, colours[sample], 2.0)
        else:
            _point(layer, colours[sample])
        _label(layer)
        layer_file.save()
        review_map.addLayer(arcpy.mp.LayerFile(str(lyrx)))
        written.append(str(lyrx))
    project.save()
    del project
    return {"project": str(project_path), "layers": written}


def _outline(layer, colour, width):
    try:
        symbology = layer.symbology
        symbol = symbology.renderer.symbol
        symbol.color = {"RGB": [0, 0, 0, 0]}
        symbol.outlineColor = {"RGB": colour}
        symbol.outlineWidth = width
        layer.symbology = symbology
    except Exception as exc:  # symbology is cosmetic; never fail the build for it
        arcpy.AddWarning(f"Could not style {layer.name}: {exc}")


def _point(layer, colour):
    try:
        symbology = layer.symbology
        symbol = symbology.renderer.symbol
        symbol.applySymbolFromGallery("Circle 2")
        symbol.color = {"RGB": [0, 0, 0, 0]}
        symbol.outlineColor = {"RGB": colour}
        symbol.size = 14
        layer.symbology = symbology
    except Exception as exc:
        arcpy.AddWarning(f"Could not style {layer.name}: {exc}")


def _label(layer):
    try:
        label = layer.listLabelClasses()[0]
        label.expression = "$feature.SAMPLE_ID"
        label.visible = True
        layer.showLabels = True
    except Exception as exc:
        arcpy.AddWarning(f"Could not label {layer.name}: {exc}")
