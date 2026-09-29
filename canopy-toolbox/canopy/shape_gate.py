"""Shape gate for walls, poles and wires: eigen-shape evidence for class 3/4/5 points. No ArcPy.

Each point's neighbourhood is the point plus its 16 nearest non-ground, non-noise neighbours
(17 points, the set PDAL filters.covariancefeatures uses for knn=16). Square-root eigenvalues
s1 >= s2 >= s3 of its covariance give (PDAL SQRT mode, verified against PDAL 3.5):

- linearity (s1-s2)/s1, planarity (s2-s3)/s1, scattering s3/s1 (they sum to 1);
- normal_z: |z| of the smallest-eigenvalue eigenvector (the plane normal);
- axis_z: |z| of the largest-eigenvalue eigenvector (the line direction);
- pdal_verticality: PDAL's Verticality, the z share of the eigenvalue-weighted unary vector.
  Recorded only for comparison with reviews/2026-09-29/shape_diagnostic.py. An isotropic
  vertical wall scores about 0.71 on it, so the diagnostic's 0.7 wall gate split real walls
  almost arbitrarily. Groups here use the plane normal, as the diagnostic documented.

Groups use the diagnostic's prespecified screening values (dominant share 0.6, vertical 0.7). A
direction is horizontal when its vertical component is at most 1 - 0.7 = 0.3, and vertical when
its horizontal component is at most 0.3 (both 17.5 degrees):

    roof_like  planarity >= 0.6, normal not horizontal
    wall_like  planarity >= 0.6, normal horizontal (1 - normal_z >= 0.7)
    wire       linearity >= 0.6, axis horizontal
    pole       linearity >= 0.6, axis vertical
    linear     linearity >= 0.6, sloped axis (roof rakes, guy wires, branches)
    scattered  scattering >= 0.6
    mixed      no dominant shape
    sparse     fewer than 17 points within radius_m, or a degenerate neighbourhood

Neighbourhoods are capped at radius_m so the work splits into blocks with an exact halo: the
features of every point within radius_m of a block come from points within 2*radius_m, so block
results equal a single pass (up to exact distance ties). Loaded points and the gated extent have
hard limits.

Shape is evidence, not truth: a clipped hedge side is wall-like and a branch is linear. Review
codes and apply-rule selections are never scoring truth.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import platform
import shutil
import time

import numpy as np
import scipy
from scipy.spatial import cKDTree

from . import las_records

GROUPS = ("roof_like", "wall_like", "linear", "scattered", "mixed", "wire", "pole", "sparse")
ROOF_LIKE, WALL_LIKE, LINEAR, SCATTERED, MIXED, WIRE, POLE, SPARSE = range(len(GROUPS))
# User-definable LAS codes, available only in point formats 6-10. 64-68 keep the meaning of the
# diagnostic's review copies, except that 66 no longer includes wires and poles. Footprint
# review-label copies (building_rules.py) use 64-70 for unrelated meanings.
REVIEW_CODES = {name: 64+i for i, name in enumerate(GROUPS)}
REVIEW_MEANING = {
    64: "shape review: roof_like (planar, normal not horizontal)",
    65: "shape review: wall_like (planar, normal within 17.5 degrees of horizontal)",
    66: "shape review: linear with a sloped axis (rake, guy wire, branch)",
    67: "shape review: scattered (vegetation-like)",
    68: "shape review: mixed (no dominant shape)",
    69: "shape review: wire (linear, axis within 17.5 degrees of horizontal)",
    70: "shape review: pole (linear, axis within 17.5 degrees of vertical)",
    71: "shape review: sparse (fewer than 17 points within the radius cap, or degenerate)",
}
FEATURES = ("linearity", "planarity", "scattering", "normal_z", "axis_z", "pdal_verticality")
DEFAULTS = {"neighbors": 16, "radius_m": 5.0, "dominant": .6, "vertical": .7, "near_building_m": 1.0,
            "min_single_share": .6, "max_irregular_share": .4}
APPLY_GROUPS = (WALL_LIKE, WIRE, POLE)
IRREGULAR = (SCATTERED, MIXED)
EXCLUDED_CLASSES = (2, 7, 18)
CANDIDATE_CLASSES = (3, 4, 5)
APPLY_CLASS = 1
BLOCK_M = 100.
MARGIN_M = .01
# The gated extent plus its halo may not exceed the roof local grid (6,250,000 half-metre cells,
# a 1.25 km square). Loaded non-ground points are capped separately: a 1 km tile with a 50 m
# buffer held 24.3 M non-ground points on 12TVL2804.
GRID_CELL_M = .5
MAX_CELLS = 6_250_000
MAX_POINTS = 40_000_000
RETURN_TYPES = ("single", "first_of_many", "intermediate", "last_of_many")
AUDIT_TYPES = {"point_index": np.int64, "previous_class_byte": np.uint8, "new_class_byte": np.uint8,
               "group": np.uint8, "neighbors": np.uint8, "own_single": bool, "single_share": np.float32,
               "irregular_share": np.float32, "nearest_building_m": np.float32,
               **{name: np.float32 for name in FEATURES}}
RULE = ("previous class in the eligible classes; not withheld, synthetic or overlap; group wall_like, "
        "wire or pole; the point itself is a single return; single returns are at least "
        "min_single_share of its 17-point neighbourhood; scattered or mixed points are at most "
        "max_irregular_share of that neighbourhood. Selected points become class 1.")


def check_parameters(p):
    for name in ("radius_m", "near_building_m"):
        if not math.isfinite(p[name]) or p[name] <= 0:
            raise ValueError(f"Shape gate {name} must be finite and positive")
    for name in ("dominant", "vertical", "min_single_share", "max_irregular_share"):
        if not math.isfinite(p[name]) or not 0 <= p[name] <= 1:
            raise ValueError(f"Shape gate {name} must lie between 0 and 1")
    if int(p["neighbors"]) != p["neighbors"] or not 3 <= p["neighbors"] <= 64:
        raise ValueError("Shape gate neighbours must be a whole number from 3 to 64")
    if p["dominant"] <= .5:
        raise ValueError("A dominant share must exceed 0.5 so that only one shape can dominate")


def features(local, tree, rows, neighbors=DEFAULTS["neighbors"], radius=DEFAULTS["radius_m"], chunk=100_000):
    """Shape features of local[rows] from the point and its `neighbors` nearest points within `radius`.

    Returns (features, count, index): float32 feature arrays (NaN where the neighbourhood is
    incomplete or degenerate), the number of points found (at most neighbors + 1, including the
    point) and their tree indices sorted by distance; missing neighbours repeat the point itself.
    """
    k = int(neighbors)+1
    rows = np.asarray(rows, dtype=np.int64)
    m = len(rows)
    out = {name: np.full(m, np.nan, dtype=np.float32) for name in FEATURES}
    count = np.zeros(m, dtype=np.uint8)
    index = np.zeros((m, k), dtype=np.int64)
    for start in range(0, m, chunk):
        stop = min(m, start+chunk)
        distance, found = tree.query(local[rows[start:stop]], k=k, distance_upper_bound=radius, workers=-1)
        valid = np.isfinite(distance)
        count[start:stop] = valid.sum(1)
        index[start:stop] = np.where(valid, found, rows[start:stop, None])
        full = np.flatnonzero(valid.all(1))
        if not len(full):
            continue
        members = local[index[start+full]]
        centred = members-members.mean(1, keepdims=True)
        values, vectors = np.linalg.eigh(np.einsum("nki,nkj->nij", centred, centred)/k)
        s = np.sqrt(np.clip(values, 0, None))
        s1, s2, s3 = s[:, 2], s[:, 1], s[:, 0]
        ok = s1 > 0
        full, s1, s2, s3, vectors, s = full[ok], s1[ok], s2[ok], s3[ok], vectors[ok], s[ok]
        unary = np.einsum("nj,nij->ni", s, np.abs(vectors))
        rows_out = start+full
        out["linearity"][rows_out] = (s1-s2)/s1
        out["planarity"][rows_out] = (s2-s3)/s1
        out["scattering"][rows_out] = s3/s1
        out["normal_z"][rows_out] = np.abs(vectors[:, 2, 0])
        out["axis_z"][rows_out] = np.abs(vectors[:, 2, 2])
        out["pdal_verticality"][rows_out] = unary[:, 2]/np.linalg.norm(unary, axis=1)
    return out, count, index


def classify(f, dominant=DEFAULTS["dominant"], vertical=DEFAULTS["vertical"]):
    """Group code per point from features(); NaN features are sparse."""
    tolerance = 1-vertical
    group = np.full(len(f["linearity"]), MIXED, dtype=np.uint8)
    group[f["scattering"] >= dominant] = SCATTERED
    linear = f["linearity"] >= dominant
    axis_z = f["axis_z"].astype(float)
    group[linear] = LINEAR
    group[linear & (axis_z <= tolerance)] = WIRE
    group[linear & (np.sqrt(np.clip(1-axis_z**2, 0, None)) <= tolerance)] = POLE
    planar = f["planarity"] >= dominant
    group[planar] = ROOF_LIKE
    group[planar & (1-f["normal_z"].astype(float) >= vertical)] = WALL_LIKE
    group[np.isnan(f["linearity"])] = SPARSE
    return group


def evaluate(xyz, single, building, candidate, neighbors=DEFAULTS["neighbors"], radius=DEFAULTS["radius_m"],
             dominant=DEFAULTS["dominant"], vertical=DEFAULTS["vertical"], block=BLOCK_M, chunk=100_000):
    """Features, group and neighbourhood evidence for every candidate, block by block.

    xyz holds every neighbour-eligible point (non-ground, non-noise, clean flags) within the gated
    extent plus 2*radius; single and building are own single-return and class-6 masks; candidate
    marks the rows to evaluate. Returned arrays follow np.flatnonzero(candidate).
    """
    rows = np.flatnonzero(candidate)
    n = len(rows)
    result = {name: np.full(n, np.nan, dtype=np.float32) for name in FEATURES+("single_share", "irregular_share")}
    result.update(group=np.full(n, SPARSE, dtype=np.uint8), neighbors=np.zeros(n, dtype=np.uint8),
                  nearest_building_m=np.full(n, np.inf, dtype=np.float32))
    if not n:
        return result
    origin = xyz[rows, :2].min(0).astype(float)
    cells = np.floor((xyz[rows, :2]-origin)/block).astype(np.int64)
    key = cells[:, 1]*(int(cells[:, 0].max())+1)+cells[:, 0]
    order = np.argsort(key, kind="stable")
    starts = np.flatnonzero(np.r_[True, np.diff(key[order]) != 0])
    reach = radius+MARGIN_M
    k = int(neighbors)+1
    for lo, hi in zip(starts, np.r_[starts[1:], n]):
        members = order[lo:hi]
        core = rows[members]
        low, high = xyz[core, :2].min(0).astype(float), xyz[core, :2].max(0).astype(float)
        halo = _inside(xyz, low-2*reach, high+2*reach)
        local = xyz[halo].astype(float)
        tree = cKDTree(local)
        inner = _inside(local, low-reach, high+reach)
        found, count, index = features(local, tree, inner, neighbors, radius, chunk)
        group = np.full(len(local), SPARSE, dtype=np.uint8)
        group[inner] = classify(found, dominant, vertical)
        at = np.searchsorted(halo, core)
        slot = np.searchsorted(inner, at)
        neighbourhood, count = index[slot], count[slot]
        valid = np.arange(k)[None, :] < count[:, None]
        own = np.maximum(count, 1)
        result["single_share"][members] = (single[halo][neighbourhood] & valid).sum(1)/own
        result["irregular_share"][members] = (np.isin(group[neighbourhood], IRREGULAR) & valid).sum(1)/own
        result["neighbors"][members] = count
        result["group"][members] = group[at]
        for name in FEATURES:
            result[name][members] = found[name][slot]
        roofs = np.flatnonzero(building[halo])
        if len(roofs):
            distance, _ = cKDTree(local[roofs]).query(local[at], k=1, distance_upper_bound=radius, workers=-1)
            result["nearest_building_m"][members] = distance
    return result


def _inside(xyz, low, high):
    """Indices (sorted) of points whose x, y lie within [low, high]."""
    x, y = xyz[:, 0], xyz[:, 1]
    return np.flatnonzero((x >= low[0]) & (x <= high[0]) & (y >= low[1]) & (y <= high[1]))


def select(result, own_single, p=None):
    """The conservative apply rule (see RULE); callers restrict the previous class and flags."""
    p = dict(DEFAULTS, **(p or {}))
    return (np.isin(result["group"], APPLY_GROUPS) & own_single &
            (result["single_share"] >= p["min_single_share"]) &
            (result["irregular_share"] <= p["max_irregular_share"]))


def return_type(return_byte, modern):
    """0 single, 1 first of many, 2 intermediate, 3 last of many (number > count counts as last)."""
    number = return_byte & (15 if modern else 7)
    count = (return_byte >> 4) if modern else ((return_byte >> 3) & 7)
    return np.where(count <= 1, 0, np.where(number <= 1, 1, np.where(number < count, 2, 3)))


def load(files, extent, halo, max_points=MAX_POINTS, block=2_000_000):
    """Neighbour-eligible points from read-only LAS files.

    Keeps classes other than 2, 7 and 18 without withheld, synthetic or overlap flags, with x, y
    inside extent plus halo. Coordinates are float32 relative to the returned origin.
    """
    xmin, ymin, xmax, ymax = extent
    low, high = (xmin-halo, ymin-halo), (xmax+halo, ymax+halo)
    headers = [las_records.header(path) for path in files]
    used = [(i, h) for i, h in enumerate(headers) if _overlaps(h["extent"], (*low, *high))]
    origin = np.array([low[0], low[1], math.floor(min((h["z_min"] for _, h in used), default=0.))])
    parts = {key: [] for key in ("xyz", "classes", "single", "file", "index")}
    total, chunk = 0, None
    for number, info in used:
        points, scale, offset, modern, _ = las_records.records(files[number], "r")
        for start in range(0, len(points), block):
            chunk = points[start:start+block]
            x, y, z, classes, _, flagged = las_records.decode(chunk, scale, offset, modern)
            keep = np.flatnonzero(~flagged & ~np.isin(classes, EXCLUDED_CLASSES) &
                                  (x >= low[0]) & (x <= high[0]) & (y >= low[1]) & (y <= high[1]))
            total += len(keep)
            if total > max_points:
                raise ValueError(f"The shape gate loads at most {max_points:,} non-ground points; "
                                 "use a smaller --extent")
            parts["xyz"].append(np.column_stack([(v[keep]-o).astype(np.float32) for v, o in zip((x, y, z), origin)]))
            parts["classes"].append(np.asarray(classes[keep], dtype=np.uint8))
            parts["single"].append(las_records.return_masks(chunk["returns"][keep], modern)[1])
            parts["file"].append(np.full(len(keep), number, dtype=np.uint8))
            parts["index"].append((keep+start).astype(np.int64))
        points = chunk = None  # release the read-only map before the next file
    empty ={"xyz": np.zeros((0, 3), np.float32), "classes": np.zeros(0, np.uint8), "single": np.zeros(0, bool),
             "file": np.zeros(0, np.uint8), "index": np.zeros(0, np.int64)}
    loaded = {key: np.concatenate(value) if value else empty[key] for key, value in parts.items()}
    loaded["origin"] = origin
    return loaded


def _overlaps(a, b):
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def recode(path, point_index, codes, audit_path, audit=None):
    """Write new class codes to an existing LAS copy; return previous class bytes.

    Only classification bytes change. Legacy formats keep their synthetic, key-point and withheld
    bits; codes above 31 therefore need formats 6-10. The audit log records point indices,
    previous and new class bytes, and any extra per-point arrays.
    """
    points, _, _, modern, _ = las_records.records(path, "r+")
    order = np.argsort(point_index, kind="stable")
    point_index = np.asarray(point_index, dtype=np.int64)[order]
    codes = np.asarray(codes, dtype=np.uint8)[order]
    if not modern and (codes > 31).any():
        raise ValueError("Legacy LAS point formats hold class codes 0-31 only")
    field = points["classification"]
    previous = np.asarray(field[point_index]).copy()
    new = codes if modern else (previous & 224) | codes
    field[point_index] = new
    points.flush()
    del points, field
    extra = {key: np.asarray(value)[order] for key, value in (audit or {}).items()}
    np.savez_compressed(audit_path, point_index=point_index, previous_class_byte=previous,
                        new_class_byte=new, **extra)
    return previous


def _write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name+".pending")
    pending.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
    os.replace(pending, path)


def _check_input(prepared_lasd, output_folder):
    input_root = Path(prepared_lasd).resolve().parent
    manifest = input_root/"preparation.json"
    if not manifest.is_file():
        raise ValueError("Use a prepared working-copy LAS dataset with preparation.json")
    previous = json.loads(manifest.read_text(encoding="utf8"))
    if previous.get("status") != "complete" or Path(previous["working_lasd"]).resolve() != Path(prepared_lasd).resolve():
        raise ValueError("Preparation manifest does not match a completed LAS dataset")
    destination = Path(output_folder).resolve()
    if destination == input_root or input_root in destination.parents:
        raise ValueError("Choose a new shape-gate folder outside the input preparation")
    if destination.exists():
        raise FileExistsError("Shape-gate output already exists")
    files = sorted((input_root/"points").glob("*.las"))
    if not files:
        raise ValueError("Prepared point files were not found")
    return manifest, previous, destination, files, [las_records.header(path) for path in files]


def _inputs_unchanged(inputs):
    for row in inputs:
        stat = Path(row["path"]).stat()
        if (stat.st_size, stat.st_mtime_ns) != (row["bytes"], row["mtime_ns"]):
            raise RuntimeError("Input working LAS changed during the shape gate")


def _peak_memory_gb():
    try:
        import psutil
        info = psutil.Process().memory_info()
        return round(getattr(info, "peak_wset", info.rss)/1e9, 2)
    except Exception:  # memory is reported when available; it never blocks processing
        return None


def _summary(classes, result, own_single, near_m):
    near = result["nearest_building_m"] <= near_m
    table = {}
    for code in CANDIDATE_CLASSES:
        mask = classes == code
        total = int(mask.sum())
        row = {"points": total, "single_return": int((mask & own_single).sum()),
               "near_building": int((mask & near).sum()), "groups": {}}
        for number, name in enumerate(GROUPS):
            member = mask & (result["group"] == number)
            row["groups"][name] = {"points": int(member.sum()), "pct": _pct(member.sum(), total),
                                   "single_return": int((member & own_single).sum()),
                                   "near_building": int((member & near).sum())}
        table[str(code)] = row
    return table


def _pct(part, total):
    return round(100*int(part)/total, 2) if total else None


def run(prepared_lasd, output_folder, extent=None, apply=False, classes=(4, 5), dataset=None,
        parameters=None, block=BLOCK_M, max_points=MAX_POINTS):
    """Shape evidence for class 3/4/5 points of a prepared dataset, written to a NEW folder.

    Review (default): LAS copies of the files the gated extent touches, in which every class
    3/4/5 point inside the extent carries its group's review code (REVIEW_CODES), plus
    shape_gate.json and changes/*.npz. Nothing here is a prepared dataset.

    Apply: a new prepared dataset (every input file copied) in which only points meeting RULE
    change from an eligible class to class 1, with changes/*.npz and preparation.json.
    `dataset(files, output_lasd)` creates the LAS dataset (ArcGIS Pro), so that `canopy run`
    reads the output exactly as it reads refine-roofs output.
    """
    started = time.perf_counter()
    p = dict(DEFAULTS, **(parameters or {}))
    check_parameters(p)
    classes = sorted({int(code) for code in classes})
    if not classes or not set(classes) <= set(CANDIDATE_CLASSES):
        raise ValueError("Eligible classes must be a non-empty subset of 3, 4 and 5")
    if apply and dataset is None:
        raise ValueError("Apply mode needs a LAS dataset writer (ArcGIS Pro)")
    manifest, previous, destination, files, inputs = _check_input(prepared_lasd, output_folder)
    prepared = [float(v) for v in previous["extent"]]
    gate = prepared if extent is None else [float(v) for v in extent]
    if len(gate) != 4 or not all(map(math.isfinite, gate)) or gate[0] >= gate[2] or gate[1] >= gate[3]:
        raise ValueError("Extent must be xmin ymin xmax ymax")
    if gate[0] < prepared[0] or gate[1] < prepared[1] or gate[2] > prepared[2] or gate[3] > prepared[3]:
        raise ValueError("The gated extent must lie inside the prepared extent")
    halo = 2*(p["radius_m"]+MARGIN_M)
    cells = math.ceil((gate[2]-gate[0]+2*halo)/GRID_CELL_M)*math.ceil((gate[3]-gate[1]+2*halo)/GRID_CELL_M)
    if cells > MAX_CELLS:
        raise ValueError(f"The shape gate supports at most {MAX_CELLS:,} {GRID_CELL_M} m cells "
                         "(gated extent plus halo); use a smaller --extent")
    touched = [i for i, row in enumerate(inputs) if _overlaps(row["extent"], gate)]
    if not apply:
        legacy = [inputs[i]["path"] for i in touched if inputs[i]["format"] < 6]
        if legacy:
            raise ValueError("Review codes 64-71 need LAS point formats 6-10; legacy files: "+", ".join(legacy))
    margin = min(gate[0]-prepared[0], gate[1]-prepared[1], prepared[2]-gate[2], prepared[3]-gate[3])
    destination.mkdir(parents=True)
    output_lasd = destination/"prepared.lasd"
    out_manifest = destination/("preparation.json" if apply else "shape_gate.json")
    state = {"status": "computing", "mode": "apply" if apply else "review",
             "quality_status": "EXPERIMENTAL_UNVALIDATED",
             "note": "Shape groups and rule selections are screening evidence, never scoring truth.",
             "input_preparation": str(manifest), "input_files": inputs,
             "prepared_extent": prepared, "gate_extent": gate,
             "edge_margin_m": round(margin, 3), "edge_effects_possible": bool(margin < halo),
             "parameters": {**p, "neighbourhood": "the point and its neighbors nearest non-ground points within radius_m",
                            "feature_mode": "square-root eigenvalues (PDAL SQRT mode)",
                            "direction_tolerance": "1 - vertical, as a unit-vector component",
                            "excluded_neighbour_classes": list(EXCLUDED_CLASSES),
                            "excluded_flags": "withheld, synthetic, overlap (points and neighbours)",
                            "candidate_classes": list(CANDIDATE_CLASSES), "block_m": block,
                            "halo_m": halo, "max_points": max_points, "max_cells": MAX_CELLS},
             "review_codes": REVIEW_MEANING, "runtime": {"python": platform.python_version(),
                                                         "numpy": np.__version__, "scipy": scipy.__version__},
             "seconds": {}}
    if apply:
        state.update(working_lasd=str(output_lasd), extent=prepared, source_id=previous.get("source_id"),
                     sources=previous.get("sources", []), apply_rule=RULE, apply_class=APPLY_CLASS,
                     eligible_classes=classes)
    _write_json(out_manifest, state)
    try:
        clock = time.perf_counter()
        loaded = load(files, gate, halo, max_points)
        xyz = loaded["xyz"]
        gx0, gy0 = gate[0]-loaded["origin"][0], gate[1]-loaded["origin"][1]
        gx1, gy1 = gate[2]-loaded["origin"][0], gate[3]-loaded["origin"][1]
        candidate = (np.isin(loaded["classes"], CANDIDATE_CLASSES) & (xyz[:, 0] >= gx0) & (xyz[:, 0] <= gx1)
                     & (xyz[:, 1] >= gy0) & (xyz[:, 1] <= gy1))
        state["loaded_points"] = int(len(xyz))
        state["seconds"]["load"] = round(time.perf_counter()-clock, 1); clock = time.perf_counter()
        result = evaluate(xyz, loaded["single"], loaded["classes"] == 6, candidate, p["neighbors"], p["radius_m"],
                          p["dominant"], p["vertical"], block)
        state["seconds"]["features"] = round(time.perf_counter()-clock, 1); clock = time.perf_counter()
        rows = np.flatnonzero(candidate)
        cand_classes, cand_single = loaded["classes"][rows], loaded["single"][rows]
        cand_file, cand_index = loaded["file"][rows], loaded["index"][rows]
        del xyz, loaded, candidate
        state["candidates"] = int(len(rows))
        state["by_class"] = _summary(cand_classes, result, cand_single, p["near_building_m"])
        audit = lambda keep: {"group": result["group"][keep], "neighbors": result["neighbors"][keep],
                              "own_single": cand_single[keep], "single_share": result["single_share"][keep],
                              "irregular_share": result["irregular_share"][keep],
                              "nearest_building_m": result["nearest_building_m"][keep],
                              **{name: result[name][keep] for name in FEATURES}}
        copies = destination/"points"; copies.mkdir()
        changes = destination/"changes"; changes.mkdir()
        state["files"] = {}
        if apply:
            chosen = np.isin(cand_classes, classes) & select(result, cand_single, p)
            state["rule_stages"] = {
                "eligible_class": int(np.isin(cand_classes, classes).sum()),
                "and_group": int((np.isin(cand_classes, classes) & np.isin(result["group"], APPLY_GROUPS)).sum()),
                "and_own_single": int((np.isin(cand_classes, classes) & np.isin(result["group"], APPLY_GROUPS)
                                       & cand_single).sum()),
                "and_single_share": int((np.isin(cand_classes, classes) & np.isin(result["group"], APPLY_GROUPS)
                                         & cand_single & (result["single_share"] >= p["min_single_share"])).sum()),
                "changed": int(chosen.sum())}
            state["before"], state["after"] = {}, {}
            targets = range(len(files))
        else:
            chosen = np.ones(len(rows), dtype=bool)
            targets = touched
        near = result["nearest_building_m"] <= p["near_building_m"]
        for number in targets:
            path = files[number]
            copy = copies/path.name
            shutil.copy2(path, copy)
            keep = np.flatnonzero(chosen & (cand_file == number))
            if apply:
                state["before"][path.name] = las_records.class_counts(copy)
                codes = np.full(len(keep), APPLY_CLASS, dtype=np.uint8)
            else:
                codes = np.array([REVIEW_CODES[GROUPS[g]] for g in range(len(GROUPS))], dtype=np.uint8)[result["group"][keep]]
            recode(copy, cand_index[keep], codes, changes/(path.stem+".npz"), audit(keep))
            row = {"changed": int(len(keep))}
            if apply:
                modern = inputs[number]["format"] >= 6
                returns = np.asarray(las_records.records(path, "r")[0]["returns"][cand_index[keep]])
                kinds = np.bincount(return_type(returns, modern), minlength=4)
                row.update(changed_by_class={str(c): int((cand_classes[keep] == c).sum()) for c in CANDIDATE_CLASSES},
                           changed_by_group={GROUPS[g]: int((result["group"][keep] == g).sum()) for g in APPLY_GROUPS},
                           changed_by_return={name: int(v) for name, v in zip(RETURN_TYPES, kinds)},
                           changed_near_building=int(near[keep].sum()))
            state["files"][path.name] = row
        state["seconds"]["write"] = round(time.perf_counter()-clock, 1); clock = time.perf_counter()
        if apply:
            dataset(sorted(copies.glob("*.las")), output_lasd)
            state["after"] = {p_.name: las_records.class_counts(p_) for p_ in sorted(copies.glob("*.las"))}
            state["seconds"]["dataset"] = round(time.perf_counter()-clock, 1)
        _inputs_unchanged(inputs)
        state["seconds"]["total"] = round(time.perf_counter()-started, 1)
        state["peak_memory_gb"] = _peak_memory_gb()
        state["status"] = "complete"
    except Exception as exc:
        state["status"] = "failed"; state["error"] = str(exc)
        raise
    finally:
        _write_json(out_manifest, state)
    return state
