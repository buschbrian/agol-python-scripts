"""Triage the training-review units with independent evidence. Read-only; writes only into a NEW output folder.

    python reviews/2026-09-30/triage_units.py NEW_OUTPUT_DIR

Run with ArcGIS Pro Python (PYTHONNOUSERSITE=1). For each unit of the packet it computes geometry from the raw points
of the prepared tile (classification bytes are never read), NAIP greenness, and building-footprint state from two
independent sources, then applies the fixed rules in canopy/triage.py. Nothing is written to the review geodatabase,
the LAS files or any label. Baseline classes and model outputs stored in the packet are used only AFTER the proposal,
for a diagnostic cross-tab that shows where the independent evidence agrees with them; they are never inputs.

Footprints: the County Surveyor layer is authoritative for "inside". A unit counts as outside footprints only when both
the County and OSM layers place it outside; if OSM says inside while the County says outside, the footprint state is
unknown and the unit goes to review.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from canopy import las_records, triage  # noqa: E402
from canopy.lidar_root import lidar_root, live  # noqa: E402

LIDAR = lidar_root()/"2023-salt-lake-valley"
PILOT = LIDAR/"runs"/"pilot-2026-09-29"
PACKET = PILOT/"training-review"/"packet-20260929"
LAS = PILOT/"12TVL2804"/"prepared"/"points"/"12TVL2804.las"
FOOTPRINTS = PILOT/"buildings"/"reference.gdb"
NAIP = LIDAR/"naip"/"12TVL2804"/"naip_12TVL2804.tif"
GROUND_RADIUS_M, GROUND_PERCENTILE = 12.0, 5
NDVI_RADIUS_M = 1.5

def load_points(path):
    """x, y, z, number of returns and return number of every point not flagged withheld, overlap or synthetic."""
    block, scale, offset, modern, info = las_records.records(path)
    clean = las_records.clean_flags(block["flags"], modern)
    x = block["x"]*scale[0]+offset[0]
    y = block["y"]*scale[1]+offset[1]
    z = block["z"]*scale[2]+offset[2]
    count = (block["returns"] >> 4) if modern else ((block["returns"] >> 3) & 7)
    number = block["returns"] & (15 if modern else 7)
    keep = np.flatnonzero(clean)
    return x[keep], y[keep], z[keep], np.asarray(count[keep]), np.asarray(number[keep]), info["points"]


def load_ndvi(path):
    import arcpy
    raster = arcpy.Raster(str(path))
    bands = arcpy.RasterToNumPyArray(str(path), nodata_to_value=-1).astype("float64")
    red, nir = bands[0], bands[3]
    total = nir+red
    valid = (red >= 0) & (nir >= 0) & (total > 0)
    ndvi = np.where(valid, (nir-red)/np.where(total == 0, 1, total), np.nan)
    return ndvi, raster.extent.XMin, raster.extent.YMax, raster.meanCellWidth


def ndvi_at(ndvi, x0, y_top, cell, x, y, radius=NDVI_RADIUS_M):
    col, row = (x-x0)/cell, (y_top-y)/cell
    reach = int(math.ceil(radius/cell))
    r0, c0 = int(row), int(col)
    rows, cols = np.arange(max(r0-reach, 0), min(r0+reach+1, ndvi.shape[0])), np.arange(max(c0-reach, 0), min(c0+reach+1, ndvi.shape[1]))
    if not len(rows) or not len(cols):
        return None
    rr, cc = np.meshgrid(rows, cols, indexing="ij")
    cx, cy = x0+(cc+.5)*cell, y_top-(rr+.5)*cell
    window = ndvi[rr, cc][np.hypot(cx-x, cy-y) <= radius]
    window = window[np.isfinite(window)]
    return float(window.mean()) if len(window) else None


def load_footprints(gdb, name):
    """Footprint polygons as triage.polygon_record dicts, read once as Esri JSON (no geometry objects in the unit loop)."""
    import arcpy
    records = []
    for (text,) in arcpy.da.SearchCursor(str(Path(gdb)/name), ["SHAPE@JSON"]):
        records.append(triage.polygon_record(json.loads(text)["rings"]))
    return records


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path)
    args = parser.parse_args(argv)
    if args.out.exists():
        raise FileExistsError(f"Choose a new output folder: {args.out}")
    import arcpy
    from scipy.spatial import cKDTree
    from canopy import training_review_arcpy as tra

    started = time.perf_counter()
    document = json.loads((live(PACKET)/"packet.json").read_text(encoding="utf-8"))
    units = document["units"]
    rows = {r["UNIT_ID"]: r for r in tra.read_review_rows(live(PACKET)/"training_review.gdb"/tra.UNITS_FC)}
    print(f"{len(units)} units; {sum(1 for r in rows.values() if r['LABEL'])} already labelled by a person", flush=True)

    x, y, z, returns, number, total = load_points(live(LAS))
    print(f"{len(x):,} of {total:,} points kept (flagged points dropped); {time.perf_counter()-started:.0f}s", flush=True)
    tree = cKDTree(np.c_[x, y])
    print(f"kd-tree built; {time.perf_counter()-started:.0f}s", flush=True)
    ndvi, nx0, ny_top, ncell = load_ndvi(live(NAIP))
    county, osm = load_footprints(live(FOOTPRINTS), "county"), load_footprints(live(FOOTPRINTS), "osm_current")
    print(f"NAIP {ndvi.shape}, footprints county {len(county)} / osm {len(osm)}; {time.perf_counter()-started:.0f}s", flush=True)

    results = []
    for unit in units:
        idx = np.asarray(tree.query_ball_point([unit["X"], unit["Y"]], r=GROUND_RADIUS_M), dtype=np.int64)
        if len(idx) == 0:
            ground = math.nan
        else:
            ground = float(np.percentile(z[idx], GROUND_PERCENTILE))
        near = idx[np.hypot(x[idx]-unit["X"], y[idx]-unit["Y"]) <= triage.CONTEXT_RADIUS_M] if len(idx) else idx
        footprint = triage.combine_footprints(triage.footprint_state(unit["X"], unit["Y"], county),
                                              triage.footprint_state(unit["X"], unit["Y"], osm))
        greenness = ndvi_at(ndvi, nx0, ny_top, ncell, unit["X"], unit["Y"])
        f = triage.unit_features(unit, x[near], y[near], z[near], returns[near], number[near], ground,
                                 ndvi=greenness, footprint=footprint)
        proposal = triage.propose(f)
        human = rows[unit["UNIT_ID"]]["LABEL"] or ""
        results.append({"UNIT_ID": unit["UNIT_ID"], "QUEUE": unit["QUEUE"], "HUMAN_LABEL": human,
                        "PROPOSED": proposal["label"] or "", "TIER": proposal["tier"], "HINT": proposal["hint"] or "",
                        "CUES": "; ".join(proposal["cues"]),
                        "own_ground_z": ground, "packet_ground_z": unit.get("GROUND_Z"),
                        **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in f.items()},
                        "BASE_CLASS": unit.get("BASE_CLASS"), "TREE_MODEL": unit.get("TREE_MODEL"),
                        "BLDG_MODEL": unit.get("BLDG_MODEL")})
    print(f"features and rules done; {time.perf_counter()-started:.0f}s", flush=True)

    args.out.mkdir(parents=True)
    with open(args.out/"triage-proposals.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(results)

    def count(filter_fn, key):
        out = {}
        for r in results:
            if filter_fn(r):
                out[r[key]] = out.get(r[key], 0)+1
        return dict(sorted(out.items()))
    summary = {"units": len(results),
               "auto_candidates": sum(r["TIER"] == "AUTO_CANDIDATE" for r in results),
               "review": sum(r["TIER"] == "REVIEW" for r in results),
               "proposed_by_label": count(lambda r: r["PROPOSED"], "PROPOSED"),
               "hints_for_review": count(lambda r: r["HINT"], "HINT"),
               "by_queue": {q: {"units": sum(r["QUEUE"] == q for r in results),
                                "auto": sum(r["QUEUE"] == q and r["TIER"] == "AUTO_CANDIDATE" for r in results)}
                            for q in sorted({r["QUEUE"] for r in results})},
               "footprint_state": {"inside": sum(r["in_footprint"] is True for r in results),
                                   "outside_both": sum(r["in_footprint"] is False for r in results),
                                   "unknown": sum(r["in_footprint"] is None for r in results)},
               "ndvi_missing": sum(r["ndvi"] is None for r in results),
               "own_ground_vs_packet_ground_m": None}
    diffs = np.array([r["own_ground_z"]-r["packet_ground_z"] for r in results
                      if r["packet_ground_z"] is not None and np.isfinite(r["own_ground_z"])])
    if len(diffs):
        summary["own_ground_vs_packet_ground_m"] = {"median": round(float(np.median(diffs)), 2),
                                                    "p5": round(float(np.percentile(diffs, 5)), 2),
                                                    "p95": round(float(np.percentile(diffs, 95)), 2)}
    labelled = [r for r in results if r["HUMAN_LABEL"]]
    summary["human_labelled"] = [{"unit": r["UNIT_ID"], "human": r["HUMAN_LABEL"], "proposed": r["PROPOSED"] or None,
                                  "tier": r["TIER"]} for r in labelled]
    # Diagnostic only, after the fact: where do the independent proposals agree with the models and baseline?
    diag = {}
    for label, field, positive in (("BUILDING_ROOF", "BLDG_MODEL", 6), ("BUILDING_ROOF", "BASE_CLASS", 6),
                                   ("TREE", "TREE_MODEL", 5), ("TREE", "BASE_CLASS", 5)):
        chosen = [r for r in results if r["PROPOSED"] == label and r[field] is not None]
        diag[f"{label} proposals vs {field}={positive}"] = {
            "n": len(chosen), "agree": sum(int(r[field]) == positive for r in chosen)}
    summary["diagnostic_vs_models_not_an_input"] = diag
    summary["seconds"] = round(time.perf_counter()-started, 1)
    (args.out/"triage-summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "human_labelled"}, indent=1, default=str))
    print("human-labelled units:", json.dumps(summary["human_labelled"]))


if __name__ == "__main__":
    main()
