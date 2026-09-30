"""TRAINING-label review units, evaluation-domain exclusion and training exports. No ArcPy.

These labels exist only to train or fine-tune models. They are never evaluation
answers, never enter reference.gdb and are never drawn on or near evaluation units.

A review unit is a location plus a small patch: a vertical cylinder of radius
PATCH_RADIUS_M around (X, Y), cut to the height slab Z_LOW..Z_HIGH. A label says
what every lidar return in that slab is. Units come from priority queues (model
disagreements, shape evidence, roof candidates) plus an area-uniform random queue.

Domain rule: a patch is allowed only inside the training tile core, outside the
holdout tiles (with their 50 m halos) and at least EVAL_BUFFER_M from every
evaluation sample unit and census plot of every tile (edge to edge).
"""
import csv
import datetime
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil

import numpy as np

from . import evaluation_design as ed
from . import las_records

SCHEMA = "canopy-training-review/1"
TRAINING_TILE = "12TVL2804"
SEED = 20260929

# One object per unit: at ~27 returns/m2 a 1 m radius holds ~85 returns in plan view, enough
# to judge; small enough that a roof edge, a wire span or one crown part stays homogeneous.
PATCH_RADIUS_M = 1.0
Z_MARGIN_M = 1.0          # added above/below the evidence points of a cluster
TOP_LAYER_M = 2.0         # random/treetop units: the top 2 m of returns in the patch
MIN_SPACING_M = 2 * PATCH_RADIUS_M + 0.5   # patches never overlap, so labels never conflict

# Evaluation buffer, measured on 12TVL2804 on 2026-09-29: 1.5 m preregistered matching radius
# + 22.6 m (99th percentile of baseline crown bounding-box diagonal, 11,661 crowns; max 36.2 m)
# + the 1 m patch radius, rounded up. A labelled patch therefore cannot share a typical crown
# with any evaluation treetop, cell, omission point, crown outline or census plot.
MATCH_RADIUS_M = 1.5
CROWN_EXTENT_P99_M = 22.6
EVAL_BUFFER_M = 25.0
# Model blocks are larger (tree PointCNN 50 m, building RandLA-Net 100 m). Fully labelled blocks
# must lie at least this far from evaluation units; reported, not used for sparse patches.
BLOCK_BUFFER_M = 50.0

EXCLUDED_TILES = {
    "12TVL3302": {"extent": list(ed.HOLDOUT_EXTENT), "role": "PROSPECTIVE_HOLDOUT (tile + 50 m prepared halo)"},
    "12TVL2203": {"extent": [ed.TILES["12TVL2203"][0]-50, ed.TILES["12TVL2203"][1]-50,
                             ed.TILES["12TVL2203"][2]+50, ed.TILES["12TVL2203"][3]+50],
                  "role": "EXTERNAL_TRANSFER (tile + 50 m halo)"},
}

# Label -> (meaning, LAS class code for point-cloud training, exported to imagery).
# LAS codes: ASPRS where one fits; 72-75 are user-definable codes chosen to avoid 64-71, which
# the shape gate and footprint review copies already use with other meanings.
LABELS = {
    "TREE": ("Woody tree crown, branches or trunk (any height; includes overhanging branches)", 5),
    "BUILDING_ROOF": ("Roof of a building, including roof-mounted equipment", 6),
    "WALL": ("Vertical face: building facade, retaining or garden wall, solid fence", 72),
    "WIRE": ("Overhead wire or cable (power, telephone, guy wire)", 14),
    "POLE": ("Pole or mast: utility, light, sign or flag pole", 73),
    "OTHER_STRUCTURE": ("Other built structure: carport, shade sail, playground, bridge, tank", 74),
    "SHRUB_LOW_VEG": ("Non-tree vegetation: shrub, clipped hedge, lawn, garden, grass", 3),
    "GROUND": ("Bare ground, pavement, gravel or low hardscape", 2),
    "VEHICLE": ("Car, truck, trailer or other vehicle", 75),
    "WATER": ("Water surface (pool, pond, stream)", 9),
    "MIXED": ("The patch slab clearly holds two or more classes (e.g. branch over a roof edge); not exported", None),
    "UNSURE": ("Cannot tell from lidar cross-sections and imagery; not exported", None),
}
EXPORT_LABELS = tuple(k for k, v in LABELS.items() if v[1] is not None)
IMAGERY_CLASS = {label: i+1 for i, label in enumerate(EXPORT_LABELS)}   # 0 stays unlabelled
YES_NO = ("YES", "NO")
IGNORE_CODE = 250         # unlabelled points in the training LAS copy; excluded at preparation
NOISE_CODES = (7, 18)

QUEUES = {
    "Q1_TREE_ON_ROOF": "Tree model called tree (5) on baseline class 6",
    "Q2_BLDG_BACKGROUND": "Building model called background (0) on baseline class 6",
    "Q3_VEG_BACKGROUND": "Tree model called background (0) on baseline class 4 or 5",
    "Q4_SHAPE": "Shape gate wall_like, wire or pole on baseline class 4 or 5",
    "Q5_ROOF_CANDIDATE": "Baseline treetop flagged ROOF_EDGE or ON_ROOF by building reconciliation",
    "Q6_RANDOM": "Area-uniform random location (top 2 m of returns)",
}
QUEUE_CODES = {name: f"Q{i+1}" for i, name in enumerate(QUEUES)}
IDENTITY_FIELDS = ("UNIT_ID", "QUEUE", "REVIEW_ORDER", "X", "Y", "Z_LOW", "Z_HIGH", "PATCH_R_M")
ANSWER_FIELDS = ("LABEL", "IMAGERY_USABLE", "REVIEWER", "REVIEW_DATE", "NOTES")
SNAPSHOT_COLUMNS = ("UNIT_ID", "QUEUE", "REVIEW_ORDER", "UNIT_TOKEN", *ANSWER_FIELDS)


def digest(value):
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def seed_for(*parts):
    text = "|".join(map(str, (SEED, *parts)))
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "little") >> 1


# ---------------------------------------------------------------- exclusions

def _ring_array(ring):
    ring = np.asarray(ring, dtype=float)
    if len(ring) < 3:
        raise ValueError("Polygon rings need at least three vertices")
    return ring


def inside_polygon(x, y, rings):
    """Even-odd point-in-polygon over all rings (holes included); x, y arrays."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    inside = np.zeros(np.broadcast(x, y).shape, bool)
    for ring in rings:
        ring = _ring_array(ring)
        x0, y0 = ring[:, 0], ring[:, 1]
        x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
        for a, b, c, d in zip(x0, y0, x1, y1):
            if b == d:
                continue
            cross = ((b > y) != (d > y)) & (x < (c-a)*(y-b)/(d-b)+a)
            inside ^= cross
    return inside


def distance_to_polygon(x, y, rings):
    """Euclidean distance from points to a polygon; zero inside."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    best = np.full(np.broadcast(x, y).shape, np.inf)
    for ring in rings:
        ring = _ring_array(ring)
        a, b = ring, np.roll(ring, -1, axis=0)
        for (ax, ay), (bx, by) in zip(a, b):
            dx, dy = bx-ax, by-ay
            length = dx*dx+dy*dy
            t = np.clip(((x-ax)*dx+(y-ay)*dy)/length, 0, 1) if length else 0.
            best = np.minimum(best, np.hypot(x-(ax+t*dx), y-(ay+t*dy)))
    return np.where(inside_polygon(x, y, rings), 0., best)


def plots_from_esri_json(document):
    """Census plots from the packet's projected Esri JSON (EPSG:6341)."""
    wkid = (document.get("spatialReference") or {}).get("latestWkid") or (document.get("spatialReference") or {}).get("wkid")
    if wkid not in (6341, None):
        raise ValueError(f"Census plots must be EPSG:6341, found {wkid}")
    return [{"PLOT_ID": f["attributes"]["PLOT_ID"], "TILE": f["attributes"]["TILE"], "rings": f["geometry"]["rings"]}
            for f in document["features"]]


def same_plots(left, right, tolerance=0.01):
    """True when two plot lists have the same IDs and the same ring vertices."""
    key = lambda plots: {p["PLOT_ID"]: (p["TILE"], [[tuple(np.round(v, 2)) for v in ring] for ring in p["rings"]]) for p in plots}
    a, b = key(left), key(right)
    if set(a) != set(b):
        return False
    for pid in a:
        if a[pid][0] != b[pid][0]:
            return False
        va = np.array([v for ring in a[pid][1] for v in ring])
        vb = np.array([v for ring in b[pid][1] for v in ring])
        box_a, box_b = np.r_[va.min(0), va.max(0)], np.r_[vb.min(0), vb.max(0)]
        if np.abs(box_a-box_b).max() > tolerance:
            return False
    return True


def exclusion_frame(reference_units, plots, buffer_m=EVAL_BUFFER_M):
    """Evaluation geometry to keep away from: [{'source','id','tile','kind','coords'}].

    reference_units: dicts with sample, SAMPLE_ID, TILE and either x/y (points) or rings (crowns).
    plots: dicts with PLOT_ID, TILE, rings. Identity and geometry only; labels never enter.
    """
    features = []
    for unit in reference_units:
        entry = {"source": f"reference:{unit['sample']}", "id": unit["SAMPLE_ID"], "tile": unit["TILE"]}
        if unit.get("rings"):
            entry.update(kind="polygon", coords=[[[round(float(x), 3), round(float(y), 3)] for x, y in ring]
                                                 for ring in unit["rings"]])
        else:
            entry.update(kind="point", coords=[round(float(unit["x"]), 3), round(float(unit["y"]), 3)])
        features.append(entry)
    for plot in plots:
        features.append({"source": "census:plot", "id": plot["PLOT_ID"], "tile": plot["TILE"], "kind": "polygon",
                         "coords": [[[round(float(x), 3), round(float(y), 3)] for x, y in ring] for ring in plot["rings"]]})
    keys = [(f["source"], f["id"]) for f in features]
    if len(set(keys)) != len(keys) or any(not f["id"] for f in features):
        raise ValueError("Evaluation feature identities must be known and unique")
    features.sort(key=lambda f: (f["source"], f["id"]))
    frame = {"buffer_m": float(buffer_m), "patch_radius_m": PATCH_RADIUS_M, "training_tile": TRAINING_TILE,
             "training_extent": list(ed.TILES[TRAINING_TILE]), "excluded_tiles": EXCLUDED_TILES,
             "features": features}
    frame["digest"] = digest({k: v for k, v in frame.items() if k != "digest"})
    return frame


def check_frame(frame):
    """Recompute the stored digest so an edited exclusions file is refused."""
    if frame.get("digest") != digest({k: v for k, v in frame.items() if k != "digest"}):
        raise ValueError("Exclusion frame digest mismatch: the stored evaluation domain was altered")
    return frame


def _rect_distance(x, y, rect):
    dx = np.maximum(np.maximum(rect[0]-x, 0), x-rect[2])
    dy = np.maximum(np.maximum(rect[1]-y, 0), y-rect[3])
    return np.hypot(dx, dy)


def evaluation_distance(x, y, frame):
    """Distance from points to the nearest evaluation feature of any tile."""
    x, y = np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float))
    best = np.full(x.shape, np.inf)
    points = np.array([f["coords"] for f in frame["features"] if f["kind"] == "point"], float).reshape(-1, 2)
    if len(points):
        from scipy.spatial import cKDTree
        best = np.minimum(best, cKDTree(points).query(np.column_stack([x, y]))[0])
    for f in frame["features"]:
        if f["kind"] == "polygon":
            rings = f["coords"]
            box = np.array([r for ring in rings for r in ring])
            near = _rect_distance(x, y, (*box.min(0), *box.max(0))) < best
            if near.any():
                best[near] = np.minimum(best[near], distance_to_polygon(x[near], y[near], rings))
    return best


def patch_status(x, y, frame, radius=PATCH_RADIUS_M):
    """Per location: '' when a patch of `radius` is allowed, else the refusal reason."""
    check_frame(frame)
    x, y = np.atleast_1d(np.asarray(x, float)), np.atleast_1d(np.asarray(y, float))
    reason = np.full(x.shape, "", dtype=object)
    t = frame["training_extent"]
    outside = (x-radius < t[0]) | (x+radius > t[2]) | (y-radius < t[1]) | (y+radius > t[3])
    reason[outside] = f"outside the {frame['training_tile']} training tile core"
    for tile, row in frame["excluded_tiles"].items():
        hit = _rect_distance(x, y, row["extent"]) < radius
        reason[hit] = f"inside excluded tile {tile} ({row['role']})"
    close = (reason == "") & (evaluation_distance(x, y, frame) < frame["buffer_m"]+radius)
    reason[close] = f"within {frame['buffer_m']} m of an evaluation unit or census plot"
    return reason


def assert_patch_allowed(x, y, frame, radius=PATCH_RADIUS_M, what="Training label"):
    reason = patch_status([x], [y], frame, radius)[0]
    if reason:
        raise ValueError(f"{what} refused at ({x:.2f}, {y:.2f}): {reason}")


def domain_mask(frame, cell=0.5, buffer_m=None, radius=PATCH_RADIUS_M):
    """Cell centres of the training tile where a patch is allowed. Returns (mask, x0, y0, cell)."""
    check_frame(frame)
    buffer_m = frame["buffer_m"] if buffer_m is None else buffer_m
    t = frame["training_extent"]
    nx, ny = int(round((t[2]-t[0])/cell)), int(round((t[3]-t[1])/cell))
    xs = t[0]+(np.arange(nx)+.5)*cell
    ys = t[1]+(np.arange(ny)+.5)*cell
    mask = np.zeros((ny, nx), bool)
    for row, y in enumerate(ys):
        mask[row] = ((xs-radius >= t[0]) & (xs+radius <= t[2]) & (y-radius >= t[1]) & (y+radius <= t[3]))
    gx, gy = np.meshgrid(xs, ys)
    flat = mask.ravel()
    candidates = np.flatnonzero(flat)
    if len(candidates):
        d = evaluation_distance(gx.ravel()[candidates], gy.ravel()[candidates], frame)
        flat[candidates] = d >= buffer_m+radius
        for tile, rowinfo in frame["excluded_tiles"].items():
            flat[candidates] &= _rect_distance(gx.ravel()[candidates], gy.ravel()[candidates], rowinfo["extent"]) >= radius
    return flat.reshape(ny, nx), t[0], t[1], cell


def domain_areas(frame, cell=0.5):
    """Training and excluded area of the tile core (m2) for the patch and block buffers."""
    t = frame["training_extent"]
    total = (t[2]-t[0])*(t[3]-t[1])
    patch = domain_mask(frame, cell)[0]
    block = domain_mask(frame, cell, buffer_m=BLOCK_BUFFER_M, radius=0.)[0]
    area = lambda m: float(m.sum())*cell*cell
    return {"tile_core_m2": total, "cell_m": cell,
            "patch_centre_domain_m2": area(patch), "patch_excluded_m2": total-area(patch),
            "patch_buffer_m": frame["buffer_m"], "patch_radius_m": PATCH_RADIUS_M,
            "block_buffer_m": BLOCK_BUFFER_M, "block_domain_m2": area(block),
            "full_50m_blocks_clear": full_blocks_clear(frame, 50.),
            "full_100m_blocks_clear": full_blocks_clear(frame, 100.),
            "evaluation_features_on_tile": sum(1 for f in frame["features"] if f["tile"] == frame["training_tile"]),
            "evaluation_features_all_tiles": len(frame["features"])}


def full_blocks_clear(frame, size):
    """Tile-aligned square blocks whose every point is >= BLOCK_BUFFER_M from evaluation features."""
    t = frame["training_extent"]
    clear = []
    for y in np.arange(t[1], t[3]-size+1e-6, size):
        for x in np.arange(t[0], t[2]-size+1e-6, size):
            # distance from a block to a feature >= buffer iff the feature is outside the block grown by buffer;
            # test on a dense boundary sample (0.5 m) plus the interior centre.
            s = np.arange(0, size+1e-6, .5)
            bx = np.concatenate([x+s, x+s, np.full_like(s, x), np.full_like(s, x+size), [x+size/2]])
            by = np.concatenate([np.full_like(s, y), np.full_like(s, y+size), y+s, y+s, [y+size/2]])
            inside_feature = any(
                x <= vx <= x+size and y <= vy <= y+size
                for f in frame["features"]
                for vx, vy in ([f["coords"]] if f["kind"] == "point" else [v for ring in f["coords"] for v in ring]))
            if not inside_feature and evaluation_distance(bx, by, frame).min() >= BLOCK_BUFFER_M:
                clear.append([float(x), float(y), float(x+size), float(y+size)])
    return clear


# ---------------------------------------------------------------- clustering and sampling

def cluster(xy, cell=1.0, min_points=10, max_extent=15.0, origin=(0., 0.)):
    """Group evidence points into objects. Returns an int label per point (-1: dropped).

    Points are binned into `cell` squares; 8-connected occupied cells form a component; each
    component is split along a `max_extent` grid (anchored at origin) so one unit stays about
    one object; pieces with fewer than min_points points are dropped. Deterministic.
    """
    from scipy import ndimage
    xy = np.asarray(xy, float).reshape(-1, 2)
    labels = np.full(len(xy), -1, np.int64)
    if not len(xy):
        return labels
    ij = np.floor((xy-np.asarray(origin))/cell).astype(np.int64)
    low = ij.min(0)
    ij -= low
    shape = ij.max(0)+1
    if shape[0]*shape[1] > 50_000_000:
        raise ValueError("Clustering grid too large; restrict the evidence extent")
    grid = np.zeros((shape[1], shape[0]), bool)
    grid[ij[:, 1], ij[:, 0]] = True
    components, _ = ndimage.label(grid, structure=np.ones((3, 3), int))
    comp = components[ij[:, 1], ij[:, 0]].astype(np.int64)
    block = np.floor((xy-np.asarray(origin))/max_extent).astype(np.int64)
    key = np.column_stack([comp, block])
    _, inverse, counts = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    inverse = inverse.ravel()
    keep = counts[inverse] >= min_points
    kept_ids = np.unique(inverse[keep])
    remap = np.full(len(counts), -1, np.int64)
    remap[kept_ids] = np.arange(len(kept_ids))
    labels[keep] = remap[inverse[keep]]
    return labels


def summarize_clusters(labels, x, y, z, radius=PATCH_RADIUS_M, extra=None):
    """One candidate per cluster: the cluster point nearest its median XY, and the slab of cluster
    points within `radius` of it. `extra` maps name -> per-point integer array (majority kept)."""
    order = np.argsort(labels, kind="stable")
    labels_sorted = labels[order]
    starts = np.searchsorted(labels_sorted, np.arange(labels.max()+1 if len(labels) and labels.max() >= 0 else 0))
    ends = np.searchsorted(labels_sorted, np.arange(len(starts)), side="right")
    out = []
    for cid, (s, e) in enumerate(zip(starts, ends)):
        members = order[s:e]
        if not len(members):
            continue
        mx, my = np.median(x[members]), np.median(y[members])
        pick = members[np.argmin(np.hypot(x[members]-mx, y[members]-my))]
        near = members[np.hypot(x[members]-x[pick], y[members]-y[pick]) <= radius]
        row = {"cluster": cid, "x": float(x[pick]), "y": float(y[pick]),
               "z_low": float(z[near].min()-Z_MARGIN_M), "z_high": float(z[near].max()+Z_MARGIN_M),
               "points": int(len(members)), "patch_points": int(len(near))}
        for name, values in (extra or {}).items():
            row[name] = int(np.bincount(values[members].astype(np.int64)).argmax())
        out.append(row)
    return out


def select(candidates, cap, queue, top_share=0.5):
    """Deterministic priority + background selection within one queue.

    The first ceil(cap*top_share) candidates by descending priority are TOP; the rest are a
    seeded simple random sample of the remainder (RANDOM). Returns selected candidates in a
    seeded random review order within the queue, so a short session is not only large clusters.
    """
    ranked = sorted(candidates, key=lambda c: (-c["priority"], c["x"], c["y"]))
    top_n = min(len(ranked), math.ceil(cap*top_share))
    chosen = [dict(c, selection="TOP") for c in ranked[:top_n]]
    rest = ranked[top_n:]
    rng = np.random.default_rng(seed_for(queue, "background"))
    if rest and cap > top_n:
        idx = rng.choice(len(rest), size=min(len(rest), cap-top_n), replace=False)
        chosen += [dict(rest[i], selection="RANDOM") for i in sorted(idx)]
    rng = np.random.default_rng(seed_for(queue, "order"))
    return [chosen[i] for i in rng.permutation(len(chosen))]


def random_locations(mask, x0, y0, cell, n, queue="Q6_RANDOM"):
    """Area-uniform random cell centres (jittered inside the cell) from an allowed-domain mask."""
    rng = np.random.default_rng(seed_for(queue, "locations"))
    allowed = np.flatnonzero(mask.ravel())
    if not len(allowed):
        return np.zeros((0, 2))
    idx = rng.choice(allowed, size=min(n, len(allowed)), replace=False)
    rows, cols = np.divmod(idx, mask.shape[1])
    jitter = rng.uniform(-.25, .25, size=(len(idx), 2))*cell
    return np.column_stack([x0+(cols+.5)*cell+jitter[:, 0], y0+(rows+.5)*cell+jitter[:, 1]])


def assemble(queues, frame, spacing=MIN_SPACING_M):
    """Interleave queues round-robin into one REVIEW_ORDER, refusing any unit outside the training
    domain and any unit whose patch would come within `spacing` of an earlier unit.

    queues: {queue_name: [candidate dicts in within-queue order]}. Returns (units, dropped counts).
    """
    names = [q for q in QUEUES if q in queues]
    unknown = set(queues) - set(QUEUES)
    if unknown:
        raise ValueError(f"Unknown queues: {sorted(unknown)}")
    pointers = {q: 0 for q in names}
    accepted, xy = [], []
    dropped = {q: {"domain": 0, "spacing": 0} for q in names}
    per_queue = {q: 0 for q in names}
    while any(pointers[q] < len(queues[q]) for q in names):
        for q in names:
            while pointers[q] < len(queues[q]):
                c = queues[q][pointers[q]]
                pointers[q] += 1
                if patch_status([c["x"]], [c["y"]], frame)[0]:
                    dropped[q]["domain"] += 1
                    continue
                if xy and np.min(np.hypot(*(np.array(xy)-[c["x"], c["y"]]).T)) < spacing:
                    dropped[q]["spacing"] += 1
                    continue
                per_queue[q] += 1
                unit = {"UNIT_ID": f"{QUEUE_CODES[q]}-{per_queue[q]:04d}", "QUEUE": q,
                        "REVIEW_ORDER": len(accepted)+1, "QUEUE_ORDER": per_queue[q],
                        "X": round(c["x"], 3), "Y": round(c["y"], 3),
                        "Z_LOW": round(c["z_low"], 2), "Z_HIGH": round(c["z_high"], 2),
                        "PATCH_R_M": PATCH_RADIUS_M, "TILE": frame["training_tile"],
                        "PRIORITY": float(c.get("priority", 0.)), "SELECTION": c.get("selection", "RANDOM"),
                        "CLUSTER_PTS": int(c.get("points", 0)), "PATCH_PTS": int(c.get("patch_points", 0)),
                        "BASE_CLASS": c.get("base"), "TREE_MODEL": c.get("tree"), "BLDG_MODEL": c.get("building"),
                        "SHAPE_GROUP": c.get("shape_group"), "CAND_FLAG": c.get("flag"),
                        "EVIDENCE": c.get("evidence", "")[:120]}
                accepted.append(unit)
                xy.append([c["x"], c["y"]])
                break
    return accepted, dropped


def unit_token(frame_digest, unit):
    return digest([frame_digest, *[unit[k] for k in IDENTITY_FIELDS]])[:24]


def units_digest(units):
    return digest([[u[k] for k in IDENTITY_FIELDS] for u in sorted(units, key=lambda u: u["UNIT_ID"])])


# ---------------------------------------------------------------- review answers

def _text(value):
    return "" if value is None else str(value).strip()


def next_unit(rows, queue=None):
    """Lowest REVIEW_ORDER row whose LABEL is blank (optionally within one QUEUE), else None."""
    open_rows = [r for r in rows if not _text(r.get("LABEL")) and (not queue or r.get("QUEUE") == queue)]
    return min(open_rows, key=lambda r: (int(r["REVIEW_ORDER"]), r["UNIT_ID"])) if open_rows else None


def normalize_answer(unit, answer, frame, labels=None, today=None):
    """Validate one labelled answer; returns the normalized answer dict or raises ValueError."""
    labels = tuple(labels or LABELS)
    uid = unit["UNIT_ID"]
    label = _text(answer.get("LABEL")).upper()
    if label not in labels or label not in LABELS:
        raise ValueError(f"{uid}: label {label!r} is not in the training label domain")
    usable = _text(answer.get("IMAGERY_USABLE")).upper()
    if usable and usable not in YES_NO:
        raise ValueError(f"{uid}: IMAGERY_USABLE must be YES, NO or blank")
    reviewer = _text(answer.get("REVIEWER"))
    notes = "" if answer.get("NOTES") is None else str(answer.get("NOTES"))
    if not reviewer or len(reviewer) > 64 or len(notes) > 500:
        raise ValueError(f"{uid}: reviewer is required (max 64 chars); notes max 500 chars")
    date = answer.get("REVIEW_DATE")
    if isinstance(date, datetime.datetime):
        date = date.date()
    if isinstance(date, datetime.date):
        date = date.isoformat()
    date = _text(date)[:10]
    try:
        parsed = datetime.date.fromisoformat(date)
    except ValueError:
        raise ValueError(f"{uid}: REVIEW_DATE must be a valid YYYY-MM-DD date") from None
    if parsed > (today or datetime.date.today()) + datetime.timedelta(days=1):
        raise ValueError(f"{uid}: REVIEW_DATE is in the future")
    assert_patch_allowed(unit["X"], unit["Y"], frame, unit.get("PATCH_R_M", PATCH_RADIUS_M), what=f"{uid} label")
    return {"LABEL": label, "IMAGERY_USABLE": usable or None, "REVIEWER": reviewer,
            "REVIEW_DATE": date, "NOTES": notes or None}


def plan_snapshot(rows, packet_units, frame, labels=None, tolerance=0.005):
    """Strictly validate the whole live review table against the packet before any export.

    rows: current table rows (identity + answers). Every packet unit must be present exactly once
    with unchanged identity; nothing else may appear. Blank labels are unreviewed. Any invalid
    labelled row refuses the entire snapshot.
    """
    check_frame(frame)
    index = {u["UNIT_ID"]: u for u in packet_units}
    seen, labelled, blank = set(), [], 0
    for row in rows:
        uid = row.get("UNIT_ID")
        if uid in seen or uid not in index:
            raise ValueError(f"Duplicate or unknown training unit: {uid}")
        seen.add(uid)
        unit = index[uid]
        for key in IDENTITY_FIELDS:
            a, b = row.get(key), unit[key]
            same = (abs(float(a)-float(b)) <= tolerance) if isinstance(b, float) else (str(a) == str(b))
            if a is None or not same:
                raise ValueError(f"{uid}: identity field {key} changed ({b!r} -> {a!r})")
        if not _text(row.get("LABEL")):
            if any(_text(row.get(k)) for k in ("IMAGERY_USABLE",)):
                raise ValueError(f"{uid}: IMAGERY_USABLE needs a LABEL")
            blank += 1
            continue
        labelled.append({"UNIT_ID": uid, "QUEUE": unit["QUEUE"], "REVIEW_ORDER": unit["REVIEW_ORDER"],
                         "UNIT_TOKEN": unit_token(frame["digest"], unit),
                         **normalize_answer(unit, row, frame, labels)})
    missing = set(index) - seen
    if missing:
        raise ValueError(f"{len(missing)} packet units are missing from the review table, e.g. {sorted(missing)[:3]}")
    labelled.sort(key=lambda r: r["REVIEW_ORDER"])
    counts = {}
    for r in labelled:
        counts[r["LABEL"]] = counts.get(r["LABEL"], 0)+1
    return {"units": len(index), "labelled": len(labelled), "blank": blank, "by_label": counts,
            "exportable": sum(1 for r in labelled if r["LABEL"] in EXPORT_LABELS), "rows": labelled}


def snapshot_csv(rows):
    handle = io.StringIO()
    writer = csv.DictWriter(handle, fieldnames=SNAPSHOT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({k: "" if r.get(k) is None else r[k] for k in SNAPSHOT_COLUMNS})
    return handle.getvalue()


def load_snapshot(folder, packet):
    """Re-verify a written snapshot against its packet before any training export."""
    folder = Path(folder)
    audit = json.loads((folder/"snapshot.json").read_text(encoding="utf-8"))
    raw = (folder/"labels.csv").read_bytes()
    if hashlib.sha256(raw).hexdigest() != audit["labels_csv_sha256"]:
        raise ValueError("Snapshot labels.csv changed after it was written")
    if audit["packet_units_digest"] != packet["units_digest"] or audit["frame_digest"] != packet["frame"]["digest"]:
        raise ValueError("Snapshot belongs to a different packet or evaluation frame")
    frame = check_frame(packet["frame"])
    index = {u["UNIT_ID"]: u for u in packet["units"]}
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    out = []
    for row in rows:
        unit = index.get(row["UNIT_ID"])
        if unit is None or row["UNIT_TOKEN"] != unit_token(frame["digest"], unit):
            raise ValueError(f"Snapshot row does not match the packet: {row.get('UNIT_ID')}")
        out.append({**unit, **normalize_answer(unit, row, frame)})
    return out


# ---------------------------------------------------------------- backup and restore (the repo working copy)

BACKUP_COLUMNS = ("UNIT_ID", "QUEUE", "REVIEW_ORDER", "UNIT_TOKEN", *ANSWER_FIELDS, "CHECK")
TOUCHED_FIELDS = ("LABEL", "IMAGERY_USABLE", "NOTES")


def plan_backup(rows, packet_units, frame, labels=None, tolerance=0.005):
    """Lenient copy of every answered unit, for saving into the repo while labelling is in progress.

    Unlike plan_snapshot this never refuses: a row that would fail snapshot validation is still saved, with the
    reason in CHECK, so one mistake cannot stop the rest of the work from being saved. A unit counts as answered
    when LABEL, IMAGERY_USABLE or NOTES is set. Rows that are not units of the packet (unknown or duplicate UNIT_ID)
    have no token and cannot be restored, so they are listed in problems instead. Blank units are not written.
    """
    index = {u["UNIT_ID"]: u for u in packet_units}
    seen, out, problems = set(), [], []
    for row in rows:
        uid = row.get("UNIT_ID")
        if uid not in index:
            problems.append(f"{uid}: not a unit of this packet; its answer is not saved")
            continue
        if uid in seen:
            problems.append(f"{uid}: appears more than once in the review table; only the first is saved")
            continue
        seen.add(uid)
        if not any(_text(row.get(k)) for k in TOUCHED_FIELDS):
            continue
        unit = index[uid]
        check = "OK"
        try:
            for key in IDENTITY_FIELDS:
                a, b = row.get(key), unit[key]
                same = (abs(float(a)-float(b)) <= tolerance) if isinstance(b, float) and a is not None else (str(a) == str(b))
                if a is None or not same:
                    raise ValueError(f"identity field {key} changed")
            if not _text(row.get("LABEL")):
                raise ValueError("has notes or IMAGERY_USABLE but no LABEL")
            normalize_answer(unit, row, frame, labels)
        except ValueError as exc:
            check = str(exc).removeprefix(f"{uid}: ")
        date = row.get("REVIEW_DATE")
        if isinstance(date, (datetime.datetime, datetime.date)):
            date = date.isoformat()[:10]
        out.append({"UNIT_ID": uid, "QUEUE": unit["QUEUE"], "REVIEW_ORDER": unit["REVIEW_ORDER"],
                    "UNIT_TOKEN": unit_token(frame["digest"], unit),
                    "LABEL": _text(row.get("LABEL")), "IMAGERY_USABLE": _text(row.get("IMAGERY_USABLE")),
                    "REVIEWER": _text(row.get("REVIEWER")), "REVIEW_DATE": _text(date),
                    "NOTES": "" if row.get("NOTES") is None else str(row.get("NOTES")), "CHECK": check})
    missing = sorted(set(index) - seen)
    if missing:
        problems.append(f"{len(missing)} packet units are missing from the review table, e.g. {missing[:3]}")
    out.sort(key=lambda r: (int(r["REVIEW_ORDER"]), r["UNIT_ID"]))
    by_label = {}
    for r in out:
        if r["LABEL"]:
            by_label[r["LABEL"]] = by_label.get(r["LABEL"], 0)+1
    flagged = [f"{r['UNIT_ID']}: {r['CHECK']}" for r in out if r["CHECK"] != "OK"]
    return {"units": len(index), "saved": len(out), "labelled": sum(by_label.values()), "by_label": by_label,
            "flagged": flagged, "problems": problems, "rows": out}


def backup_csv(rows):
    handle = io.StringIO()
    writer = csv.DictWriter(handle, fieldnames=BACKUP_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({k: "" if r.get(k) is None else r[k] for k in BACKUP_COLUMNS})
    return handle.getvalue()


def plan_restore(backup_rows, current_rows, packet_units, frame, labels=None, replace=False):
    """What restoring a backup CSV into the live review table would do. Writes nothing.

    Each backup row is checked like a snapshot row (token, label domain, reviewer, date, excluded domain).
    A unit whose live LABEL is blank is written; an identical answer is left alone; a different live label is a
    conflict and is skipped unless replace. Rows that fail any check are refused with the reason; they never stop
    the valid rows.
    """
    index = {u["UNIT_ID"]: u for u in packet_units}
    live = {r["UNIT_ID"]: r for r in current_rows}
    plan = {"write": [], "replace": [], "unchanged": [], "conflicts": [], "refused": []}
    seen = set()
    for row in backup_rows:
        uid = row.get("UNIT_ID")
        unit = index.get(uid)
        if unit is None or uid not in live:
            plan["refused"].append(f"{uid}: not a unit of this packet")
            continue
        if uid in seen:
            plan["refused"].append(f"{uid}: appears more than once in the backup")
            continue
        seen.add(uid)
        if row.get("UNIT_TOKEN") != unit_token(frame["digest"], unit):
            plan["refused"].append(f"{uid}: token does not match this packet or evaluation frame")
            continue
        if not _text(row.get("LABEL")):
            plan["refused"].append(f"{uid}: no LABEL to restore")
            continue
        try:
            answer = normalize_answer(unit, row, frame, labels)
        except ValueError as exc:
            plan["refused"].append(str(exc))
            continue
        current = live[uid]
        now = _text(current.get("LABEL"))
        if not now:
            plan["write"].append({"UNIT_ID": uid, "answer": answer})
        elif now == answer["LABEL"]:
            plan["unchanged"].append(uid)       # same label: the live answer (reviewer, notes) is kept
        elif replace:
            plan["replace"].append({"UNIT_ID": uid, "answer": answer, "was": now})
        else:
            plan["conflicts"].append(f"{uid}: live label {now} differs from backup {answer['LABEL']}")
    return plan


def read_backup(path):
    """Rows of a backup CSV as dicts; the header must be the backup columns."""
    with open(path, encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != BACKUP_COLUMNS:
            raise ValueError(f"{path} is not a training label backup (unexpected columns)")
        return list(reader)


# ---------------------------------------------------------------- point-cloud training export

def point_split(units, block=50., valid_share=0.2, origin=None):
    """Spatial train/validation split by tile-aligned blocks (the tree model's 50 m block)."""
    origin = origin or ed.TILES[TRAINING_TILE][:2]
    keys = sorted({(int((u["X"]-origin[0])//block), int((u["Y"]-origin[1])//block)) for u in units})
    rng = np.random.default_rng(seed_for("split", block))
    n_valid = max(1, int(round(len(keys)*valid_share))) if len(keys) > 1 else 0   # Prepare needs validation data
    valid = {keys[i] for i in rng.choice(len(keys), size=n_valid, replace=False)} if n_valid else set()
    split = {}
    for u in units:
        key = (int((u["X"]-origin[0])//block), int((u["Y"]-origin[1])//block))
        split[u["UNIT_ID"]] = "VALIDATION" if key in valid else "TRAINING"
    squares = {name: [[origin[0]+i*block, origin[1]+j*block, origin[0]+(i+1)*block, origin[1]+(j+1)*block]
                      for (i, j) in keys if (name == "VALIDATION") == ((i, j) in valid)]
               for name in ("TRAINING", "VALIDATION")}
    return split, squares


def export_training_las(source, destination, units, frame, chunk=2_000_000):
    """Write a NEW training LAS copy: labelled patch slabs get their LAS training code; noise 7/18 is
    kept; every other point gets IGNORE_CODE. The source is only read (size/mtime rechecked).

    units: validated snapshot rows (identity + LABEL). Only EXPORT_LABELS are written. Returns counts.
    """
    check_frame(frame)
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise FileExistsError(f"{destination} exists; choose a new export folder")
    info = las_records.header(source)
    if info["format"] < 6:
        raise ValueError("Training codes above 31 need LAS point formats 6-10; the source is a legacy format")
    exported = [u for u in units if u["LABEL"] in EXPORT_LABELS]
    for u in exported:
        assert_patch_allowed(u["X"], u["Y"], frame, u.get("PATCH_R_M", PATCH_RADIUS_M), what=f"{u['UNIT_ID']} export")
    centres = np.array([[u["X"], u["Y"]] for u in exported], float).reshape(-1, 2)
    if len(centres) > 1:
        from scipy.spatial import cKDTree
        pairs = cKDTree(centres).query_pairs(2*max(u.get("PATCH_R_M", PATCH_RADIUS_M) for u in exported))
        if pairs:
            raise ValueError("Labelled patches overlap; refusing ambiguous training labels")
    before = (source.stat().st_size, source.stat().st_mtime_ns)
    destination.parent.mkdir(parents=True, exist_ok=True)
    pending = destination.with_name(destination.name+".pending")
    shutil.copyfile(source, pending)
    try:
        per_unit, counts = _recode_copy(pending, exported, centres, chunk)
    except BaseException:
        import gc
        gc.collect()
        os.remove(pending)
        raise
    import gc
    gc.collect()            # release the writable map before renaming (Windows)
    if (source.stat().st_size, source.stat().st_mtime_ns) != before:
        os.remove(pending)
        raise RuntimeError("Source LAS changed during the training export")
    os.replace(pending, destination)
    return {"points": int(info["points"]), "classes": {str(i): int(n) for i, n in enumerate(counts) if n},
            "ignore_code": IGNORE_CODE, "units_exported": len(exported),
            "units_with_no_points": [u["UNIT_ID"] for u, n in zip(exported, per_unit) if n == 0],
            "points_per_unit": {u["UNIT_ID"]: int(n) for u, n in zip(exported, per_unit)},
            "label_codes": {k: v[1] for k, v in LABELS.items() if v[1] is not None}}


def _recode_copy(path, exported, centres, chunk):
    """Write training codes into the modern-format copy at `path`; returns (per-unit, per-class) counts."""
    points, scale, offset, modern, _ = las_records.records(path, "r+")
    codes = np.array([LABELS[u["LABEL"]][1] for u in exported], np.uint8)
    radius = np.array([u.get("PATCH_R_M", PATCH_RADIUS_M) for u in exported], float)
    zlow = np.array([u["Z_LOW"] for u in exported], float)
    zhigh = np.array([u["Z_HIGH"] for u in exported], float)
    per_unit = np.zeros(len(exported), np.int64)
    counts = np.zeros(256, np.int64)
    tree = None
    if len(exported):
        from scipy.spatial import cKDTree
        tree = cKDTree(centres)
    for start in range(0, len(points), chunk):
        block = points[start:start+chunk]
        x, y, z, classes, _, _ = las_records.decode(block, scale, offset, modern)
        classes = np.array(classes)
        new = np.full(len(block), IGNORE_CODE, np.uint8)
        noise = np.isin(classes, NOISE_CODES)
        new[noise] = classes[noise]
        if tree is not None:
            d, j = tree.query(np.column_stack([x, y]), distance_upper_bound=float(radius.max()))
            hit = np.isfinite(d)
            hit[hit] &= (d[hit] <= radius[j[hit]]) & (z[hit] >= zlow[j[hit]]) & (z[hit] <= zhigh[j[hit]]) & ~noise[hit]
            new[hit] = codes[j[hit]]
            per_unit += np.bincount(j[hit], minlength=len(exported))
        counts += np.bincount(new, minlength=256)
        block["classification"] = new
        del block
    if isinstance(points, np.memmap):
        points.flush()
    return per_unit, counts


def verify_only_classes_changed(source, copy, chunk=1_000_000):
    """Every non-classification byte of every record (and the header/VLRs) must be identical."""
    a, b = las_records.header(source), las_records.header(copy)
    if (a["points"], a["record_length"], a["offset"], a["format"]) != (b["points"], b["record_length"], b["offset"], b["format"]):
        raise ValueError("Training copy layout differs from its source")
    column = 16 if a["format"] >= 6 else 15
    with open(source, "rb") as s, open(copy, "rb") as c:
        if s.read(a["offset"]) != c.read(b["offset"]):
            raise ValueError("Training copy header or VLRs differ from the source")
        changed = 0
        for start in range(0, a["points"], chunk):
            n = min(chunk, a["points"]-start)
            left = np.frombuffer(s.read(n*a["record_length"]), np.uint8).reshape(n, -1)
            right = np.frombuffer(c.read(n*a["record_length"]), np.uint8).reshape(n, -1)
            other = np.ones(a["record_length"], bool)
            other[column] = False
            if not np.array_equal(left[:, other], right[:, other]):
                raise ValueError("A protected (non-classification) byte differs in the training copy")
            changed += int(np.count_nonzero(left[:, column] != right[:, column]))
        if s.read() != c.read():
            raise ValueError("Trailing bytes (EVLRs) differ in the training copy")
    return {"records": a["points"], "classification_bytes_changed": changed}


def prepare_parameters(training_las, training_boundary, validation_boundary, block_size=50.):
    """Documented inputs for Prepare Point Cloud Training Data (Pro 3.7) on the export."""
    return {"tool": "arcpy.ddd.PreparePointCloudTrainingData",
            "in_point_cloud": str(training_las), "block_size": f"{block_size} Meters",
            "training_boundary": str(training_boundary), "validation_boundary": str(validation_boundary),
            "excluded_class_codes": [IGNORE_CODE, *NOISE_CODES],
            "class_codes_of_interest": sorted({v[1] for v in LABELS.values() if v[1] is not None}),
            "note": ("excluded_class_codes REMOVES points from the blocks (input and label), so unlabelled "
                     "points are not ignored-with-context. Only the Semantic Query Network architecture is "
                     "documented as not requiring comprehensive classification; see TRAINING_REVIEW.md.")}
