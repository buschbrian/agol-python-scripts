"""Compare two canopy runs over the same extent: candidates, crowns, and CHM canopy area.

Both runs must share the CHM grid. Canopy is CHM >= 2 m (the lowest detection band).

Usage (Pro Python): python compare_runs.py BASE_RUN_DIR NEW_RUN_DIR REPORT.json
"""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from canopy.run_safeguards import fingerprint

import arcpy
import numpy as np

CANOPY_M = 2.0


def outputs(run):
    state = json.loads((Path(run) / "run.json").read_text())
    if state.get("status") != "complete":
        raise ValueError(f"Cannot compare incomplete run: {run}")
    required = ("chm", "treetops", "crowns")
    if any(not arcpy.Exists(state.get("outputs", {}).get(key, "")) for key in required):
        raise ValueError(f"Completed run has missing outputs: {run}")
    return state["outputs"]


def chm(path):
    raster = arcpy.Raster(path)
    array = arcpy.RasterToNumPyArray(raster, nodata_to_value=np.nan).astype(np.float64)
    grid = (raster.meanCellWidth, raster.meanCellHeight, raster.extent.XMin, raster.extent.YMin,
            raster.spatialReference.exportToString())
    return array, raster.meanCellWidth, grid


def main(base, new, report):
    a, b = outputs(base), outputs(new)
    base_chm, cell, origin = chm(a["chm"])
    new_chm, new_cell, new_origin = chm(b["chm"])
    if base_chm.shape != new_chm.shape or cell != new_cell or origin != new_origin:
        raise ValueError("Runs do not share a CHM grid")
    base_canopy, new_canopy = base_chm >= CANOPY_M, new_chm >= CANOPY_M
    changed = np.isfinite(base_chm) & np.isfinite(new_chm) & (np.abs(base_chm - new_chm) > 1e-6)
    area = cell * cell
    result = {
        "base": str(Path(base).name), "new": str(Path(new).name), "cell_m": cell,
        "base_run": str(Path(base).resolve()), "new_run": str(Path(new).resolve()),
        "base_manifest": fingerprint(Path(base) / "run.json"),
        "new_manifest": fingerprint(Path(new) / "run.json"),
        "quality_status": "UNVALIDATED_CLASSIFICATION_COMPARISON",
        "canopy_threshold_m": CANOPY_M,
        "treetops": [int(arcpy.management.GetCount(r["treetops"])[0]) for r in (a, b)],
        "crowns": [int(arcpy.management.GetCount(r["crowns"])[0]) for r in (a, b)],
        "canopy_m2": [float(base_canopy.sum() * area), float(new_canopy.sum() * area)],
        "canopy_removed_m2": float((base_canopy & ~new_canopy).sum() * area),
        "canopy_added_m2": float((~base_canopy & new_canopy).sum() * area),
        "cells_changed": int(changed.sum()),
        "heights_increased": int((changed & (new_chm > base_chm)).sum()),
        "nodata_changed": int((np.isnan(base_chm) != np.isnan(new_chm)).sum()),
    }
    Path(report).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main(*sys.argv[1:4])
