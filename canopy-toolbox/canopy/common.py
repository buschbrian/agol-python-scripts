"""Shared ArcGIS output, grid, metadata, and scratch handling."""
from __future__ import annotations

import contextlib
import json
import math
import os
import re
import shutil
import tempfile
from pathlib import Path

import arcpy

ESTIMATE_WARNING = (
    "Estimated canopy and detected crowns; not a stem census. "
    "Species, condition, and local detection accuracy require independent verification."
)


def positive(value, name, allow_zero=False):
    value = float(value)
    if not math.isfinite(value) or value < 0 or (not allow_zero and value == 0):
        raise ValueError(f"{name} must be finite and {'non-negative' if allow_zero else 'positive'}")
    return value


def prefix_name(prefix):
    if prefix and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", prefix):
        raise ValueError("Prefix must start with a letter and contain only letters, numbers, underscores")
    return prefix


def metric_reference(sr):
    if sr.type != "Projected" or not math.isclose(sr.metersPerUnit, 1.0, rel_tol=1e-8):
        raise ValueError("Use a projected coordinate system with metre horizontal units")
    vcs = getattr(sr, "VCS", None)
    if vcs and getattr(vcs, "linearUnitName", "").lower() not in ("meter", "metre", "meters", "metres"):
        raise ValueError("Vertical reference must use metres; convert heights before analysis")
    return sr


def grid(path, cell_size=None, max_cells=None):
    raster = arcpy.Raster(path)
    metric_reference(raster.spatialReference)
    dx, dy = raster.meanCellWidth, raster.meanCellHeight
    positive(dx, "Raster cell width")
    if not math.isclose(dx, dy, rel_tol=1e-8):
        raise ValueError("Square raster cells are required")
    if cell_size is not None and not math.isclose(positive(cell_size, "Cell size"), dx, rel_tol=1e-8):
        raise ValueError(f"Cell size {cell_size} disagrees with raster resolution {dx}")
    if max_cells and raster.width * raster.height > max_cells:
        raise ValueError(f"Raster exceeds {max_cells:,} cells; use a smaller review AOI")
    return raster, dx


def geodatabase(workspace):
    workspace = os.path.abspath(workspace)
    if not workspace.lower().endswith(".gdb") or not arcpy.Exists(workspace):
        raise ValueError("Feature and table outputs require an existing file geodatabase (.gdb)")
    return workspace


def output(workspace, name):
    path = os.path.join(workspace, name)
    if arcpy.Exists(path) or os.path.exists(path):
        raise FileExistsError(f"Output already exists: {path}; use a new prefix or run folder")
    return path


@contextlib.contextmanager
def scratch():
    folder = tempfile.mkdtemp(prefix="canopy_")
    gdb = os.path.join(folder, "work.gdb")
    try:
        arcpy.management.CreateFileGDB(folder, "work.gdb")
        yield folder, gdb
    finally:
        arcpy.management.ClearWorkspaceCache(gdb)
        # Only this uniquely created scratch directory is eligible for cleanup.
        if Path(folder).resolve().parent == Path(tempfile.gettempdir()).resolve():
            shutil.rmtree(folder, ignore_errors=True)


def environment(raster):
    return arcpy.EnvManager(
        snapRaster=raster, cellSize=raster, extent=raster,
        outputCoordinateSystem=arcpy.Describe(raster).spatialReference,
        mask=None, parallelProcessingFactor="0",
    )


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + ".pending")
    pending.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
    os.replace(pending, path)


def metadata(path, description):
    item = arcpy.metadata.Metadata(path)
    item.summary = ESTIMATE_WARNING
    item.description = description + "\n\n" + ESTIMATE_WARNING
    item.save()


def add_fields(path, fields):
    for name, kind, length in fields:
        arcpy.management.AddField(path, name, kind, field_length=length)


def create_points(gdb, name, sr):
    arcpy.management.CreateFeatureclass(gdb, name, "POINT", spatial_reference=sr)
    path = os.path.join(gdb, name)
    add_fields(path, [
        ("TREE_ID", "TEXT", 36), ("HEIGHT_M", "DOUBLE", None),
        ("MIN_HEIGHT", "DOUBLE", None), ("SMOOTH", "LONG", None),
        ("SOURCE_ID", "TEXT", 128), ("REVIEW_STATUS", "TEXT", 32),
        ("SPECIES", "TEXT", 120), ("DBH_CM", "DOUBLE", None),
        ("CONDITION", "TEXT", 64), ("FIELD_NOTES", "TEXT", 500),
    ])
    return path



def same_xy_reference(left, right):
    """Ignore storage-domain/precision differences in equivalent spatial references."""
    if left.factoryCode and right.factoryCode:
        return left.factoryCode == right.factoryCode
    return left.exportToString().split(";")[0] == right.exportToString().split(";")[0]


def runtime():
    import platform
    import scipy
    info = arcpy.GetInstallInfo()
    return {"arcgis_pro": info.get("Version"), "build": info.get("BuildNumber"),
            "python": platform.python_version(), "scipy": scipy.__version__,
            "license": arcpy.ProductInfo()}
