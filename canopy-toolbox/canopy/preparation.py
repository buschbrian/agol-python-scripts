"""Read-only LAS inventory and classification of newly extracted working copies."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path

import arcpy
import numpy as np

from . import common, rasters


from .las_records import header, class_counts


def inventory(folder, sample=True):
    paths = sorted(Path(folder).rglob("*.las"))
    if not paths:
        raise ValueError("No uncompressed LAS files found")
    files = []
    for path in paths:
        row = header(path)
        row["classification"] = class_counts(path, sample=sample)
        files.append(row)
    return {
        "folder": str(Path(folder).resolve()), "file_count": len(files),
        "bytes": sum(row["bytes"] for row in files), "point_count": sum(row["points"] for row in files),
        "files": files,
        "note": "Sampled classes are screening evidence, not full class counts. Header creation dates are not flight dates.",
    }


def prepare(input_folder, output_folder, extent, max_vegetation_height=80.0,
            classify_noise=False, ground_method="CONSERVATIVE", roof_tolerance=3.0,
            building_method="STANDARD"):
    """Extract a new copy, retain ground/noise, classify buildings then height.

    This entry point never classifies the source LAS dataset. Every classification
    target references only new files beneath output_folder/points.
    """
    from .tiling import Extent
    extent = list(Extent(*[float(v) for v in extent]))
    common.positive(roof_tolerance, "Maximum height above roof", allow_zero=True)
    if building_method not in {"CONSERVATIVE", "STANDARD", "AGGRESSIVE"}:
        raise ValueError("Building method must be CONSERVATIVE, STANDARD, or AGGRESSIVE")
    if not all(math.isfinite(v) for v in extent) or len(extent) != 4 or extent[0] >= extent[2] or extent[1] >= extent[3]:
        raise ValueError("Extent must be xmin ymin xmax ymax")
    common.positive(max_vegetation_height, "Maximum vegetation height")
    if max_vegetation_height <= 2:
        raise ValueError("Maximum vegetation height must exceed 2 metres")
    destination = Path(output_folder).resolve()
    source_root = Path(input_folder).resolve()
    if destination == source_root or source_root in destination.parents:
        raise ValueError("Working copy must be outside the original delivery directory")
    if destination.exists():
        raise FileExistsError("Choose a new working-copy directory")
    sources = []
    for path in sorted(source_root.rglob("*.las")):
        row = header(path)
        xmin, ymin, xmax, ymax = row["extent"]
        if xmax > extent[0] and ymax > extent[1] and xmin < extent[2] and ymin < extent[3]:
            sources.append(row)
    if not sources:
        raise ValueError("No LAS files intersect the pilot extent")
    destination.mkdir(parents=True)
    points_folder = destination/"points"; points_folder.mkdir()
    source_lasd = str(destination/"source_reference.lasd")
    working_lasd = str(destination/"prepared.lasd")
    state = {
        "status": "extracting", "sources": sources, "extent": extent,
        "parameters": {"max_vegetation_height_m": max_vegetation_height,
                       "classify_noise": classify_noise, "ground_method": ground_method,
                       "building_min_height_m": 2, "building_min_area_m2": 10,
                       "building_method": building_method,
                       "above_roof_height_m": roof_tolerance, "above_roof_class": 6,
                       "below_roof_class": 6},
        "steps": [], "working_lasd": working_lasd, "runtime": common.runtime(),
    }
    manifest = destination/"preparation.json"
    common.write_json(manifest, state)
    try:
        arcpy.management.CreateLasDataset([row["path"] for row in sources], source_lasd,
                                          compute_stats="NO_COMPUTE_STATS")
        common.metric_reference(arcpy.Describe(source_lasd).spatialReference)
        arcpy.ddd.ExtractLas(source_lasd, str(points_folder), " ".join(map(str, extent)),
                             process_entire_files="PROCESS_EXTENT", rearrange_points="REARRANGE_POINTS",
                             compute_stats="COMPUTE_STATS", out_las_dataset=working_lasd)
        copied = sorted(points_folder.glob("*.las"))
        if not copied or any(destination not in path.resolve().parents for path in copied):
            raise RuntimeError("Extraction did not create an isolated LAS working copy")
        before = {path.name: class_counts(path) for path in copied}
        state["before"] = before
        state["status"] = "classifying"; common.write_json(manifest, state)
        if classify_noise:
            arcpy.ddd.ClassifyLasNoise(working_lasd, method="ISOLATION", edit_las="CLASSIFY",
                                      max_neighbors=2, step_width="2 Meters", step_height="2 Meters")
            state["steps"].append("isolation noise (2 m bins, <=2 neighbours)")
        else:
            state["steps"].append("preserved delivered noise; no new noise thresholds applied")
        if any("2" not in info["classes"] for info in before.values()):
            arcpy.ddd.ClassifyLasGround(working_lasd, method=ground_method,
                                        reuse_ground="REUSE_GROUND", compute_stats="COMPUTE_STATS")
            state["steps"].append("classified ground")
        else:
            state["steps"].append("retained existing ground")
        arcpy.ddd.ClassifyLasBuilding(
            working_lasd, min_height="2 Meters", min_area="10 SquareMeters",
            reuse_building="REUSE_BUILDING", method=building_method, compute_stats="COMPUTE_STATS",
            classify_above_roof="CLASSIFY_ABOVE_ROOF" if roof_tolerance else "NO_CLASSIFY_ABOVE_ROOF",
            above_roof_height=f"{roof_tolerance} Meters", above_roof_code=6,
            classify_below_roof="CLASSIFY_BELOW_ROOF", below_roof_code=6)
        state["steps"].append("classified buildings including roof equipment and below-roof returns; inspect overhanging trees")
        arcpy.ddd.ClassifyLasByHeight(
            working_lasd, "GROUND", [[3, .5], [4, 2.0], [5, max_vegetation_height]],
            noise="NONE", compute_stats="COMPUTE_STATS")
        state["steps"].append("height-classified remaining class-0/1 points; unvalidated vegetation candidates")
        state["after"] = {path.name: class_counts(path) for path in copied}
        state["source_id"] = hashlib.sha256(json.dumps(
            [(row["path"], row["bytes"], row["mtime_ns"]) for row in sources]).encode()).hexdigest()[:24]
        state["status"] = "complete"
        state["quality_status"] = "PILOT_UNVALIDATED"
        for row in sources:
            current = Path(row["path"]).stat()
            if (current.st_size, current.st_mtime_ns) != (row["bytes"], row["mtime_ns"]):
                raise RuntimeError("A source file changed during pilot preparation")
    except Exception as exc:
        state["status"] = "failed"; state["error"] = str(exc)
        raise
    finally:
        common.write_json(manifest, state)
    return state
