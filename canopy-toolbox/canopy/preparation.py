"""Read-only LAS inventory and classification of newly extracted working copies."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import struct

import arcpy
import numpy as np

from . import common, rasters


def header(path):
    path = Path(path)
    with path.open("rb") as handle:
        data = handle.read(375)
        if data[:4] != b"LASF":
            raise ValueError(f"Not a LAS file: {path}")
        major, minor = data[24], data[25]
        fmt = data[104] & 63
        if data[104] & 128:
            raise ValueError("Compressed LAS needs extraction before direct point inspection")
        count = struct.unpack_from("<I", data, 107)[0]
        if (major, minor) >= (1, 4):
            count = struct.unpack_from("<Q", data, 247)[0] or count
        bounds = struct.unpack_from("<6d", data, 179)
        result = {
            "path": str(path.resolve()), "bytes": path.stat().st_size, "mtime_ns": path.stat().st_mtime_ns,
            "version": f"{major}.{minor}", "format": fmt, "points": count,
            "offset": struct.unpack_from("<I", data, 96)[0],
            "record_length": struct.unpack_from("<H", data, 105)[0],
            "extent": [bounds[1], bounds[3], bounds[0], bounds[2]],
            "z_min": bounds[5], "z_max": bounds[4],
            "file_creation_year": struct.unpack_from("<H", data, 92)[0],
            "file_creation_day": struct.unpack_from("<H", data, 90)[0],
        }
        # File creation date is not necessarily the flight date.
        handle.seek(struct.unpack_from("<H", data, 94)[0])
        for _ in range(struct.unpack_from("<I", data, 100)[0]):
            vlr = handle.read(54)
            size = struct.unpack_from("<H", vlr, 20)[0]
            content = handle.read(size)
            if struct.unpack_from("<H", vlr, 18)[0] == 2112:
                result["wkt"] = content.decode("utf-8", "replace").rstrip("\0")
    return result


def class_counts(path, sample=False):
    info = header(path)
    counts = np.zeros(256, dtype=np.int64)
    flags = {"withheld": 0, "overlap": 0, "synthetic": 0}
    returns = np.zeros(16, dtype=np.int64)
    with open(path, "rb") as handle:
        if sample:
            blocks = [(int(start), min(512, info["points"])) for start in
                      np.linspace(0, max(0, info["points"]-512), 16, dtype=np.int64)]
        else:
            blocks = ((start, min(1_000_000, info["points"]-start)) for start in
                      range(0, info["points"], 1_000_000))
        for start, count in blocks:
            handle.seek(info["offset"]+start*info["record_length"])
            data = np.frombuffer(handle.read(count*info["record_length"]), dtype=np.uint8)
            if data.size != count*info["record_length"]:
                raise ValueError(f"Truncated LAS point records: {path}")
            data = data.reshape(-1, info["record_length"])
            modern = info["format"] >= 6
            classes = data[:, 16] if modern else data[:, 15] & 31
            counts += np.bincount(classes, minlength=256)
            returns += np.bincount(data[:, 14] & (15 if modern else 7), minlength=16)
            flag = data[:, 15]
            flags["withheld"] += int(np.count_nonzero(flag & (4 if modern else 128)))
            flags["synthetic"] += int(np.count_nonzero(flag & (1 if modern else 32)))
            flags["overlap"] += int(np.count_nonzero(flag & 8)) if modern else 0
    return {
        "mode": "sample" if sample else "complete", "evaluated_points": int(counts.sum()),
        "classes": {str(i): int(n) for i, n in enumerate(counts) if n},
        "returns": {str(i): int(n) for i, n in enumerate(returns) if n}, "flags": flags,
    }


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
