"""Local roof-surface test for the roof-edge refinement. Pure numpy/scipy; must not import arcpy.

Two steps, both local:

1. Face planes. Interior class-6 points anchor planes fitted only to interior neighbours
   (with one trimmed refit and its fitted intercept retained). Measured boundary strips
   cannot anchor a face. Faces that
   are collinear, rough (e.g. straddling a step between roof levels) or steeper than a gate are
   not used.
2. Votes. Each eligible vegetation-class point must have measured roof support within the
   horizontal radius. Interior anchors may lie one additional metre away to reach the eave.
   Each usable face is extended to the point, and the point's height above that extended
   face is its offset. The point is reclassified when at least `min_votes` faces place it within
   the band [-below, +above].

A point on a gable or hip therefore sees only the faces it belongs to: eaves continue their own
face downwards, and a ridge or hip line is where both faces meet, so both agree. A step between
roof levels is not bridged, because faces on each level predict their own level. Fitted planes
are processing models; their residuals are not vertical accuracies.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage
from scipy.spatial import cKDTree

# Face status per roof point. Only FACE_OK faces vote.
FACE_OK = 0
FEW_NEIGHBOURS = 1   # fewer than min_neighbors roof points within the radius
DEGENERATE = 2       # neighbours (nearly) collinear, so no plane is defined
ROUGH = 3            # inlier residual RMSE above the gate, e.g. a step between roof levels
STEEP = 4            # fitted slope above the gate, e.g. roof mixed with a wall
EDGE_SUPPORT = 5     # measured boundary strip, not a face-fitting anchor
FACE_STATUS = {FACE_OK: "ok", FEW_NEIGHBOURS: "few_neighbours", DEGENERATE: "degenerate",
               ROUGH: "rough", STEEP: "steep", EDGE_SUPPORT: "edge_support"}
INTERIOR_CELL_M = .5
INTERIOR_MARGIN_M = .5
INTERIOR_REACH_M = INTERIOR_MARGIN_M + INTERIOR_CELL_M
MAX_INTERIOR_CELLS = 6_250_000

DEFAULTS = {"radius": 1.0, "neighbors": 16, "min_neighbors": 6, "min_votes": 3, "below": .35, "above": .5,
            "max_rmse": .15, "max_slope": 1.5}


def check_parameters(radius, neighbors, min_neighbors, min_votes, below, above, max_rmse, max_slope):
    values = {"radius": radius, "below": below, "above": above, "max_rmse": max_rmse, "max_slope": max_slope}
    for name, value in values.items():
        zero_ok = name in ("below", "above")
        if not np.isfinite(value) or value < 0 or (value == 0 and not zero_ok):
            raise ValueError(f"Local roof {name} must be finite and {'non-negative' if zero_ok else 'positive'}")
    for value in (neighbors, min_neighbors, min_votes):
        if int(value) != value:
            raise ValueError("Neighbour and vote counts must be whole numbers")
    if not 3 <= min_neighbors <= neighbors <= 64:
        raise ValueError("Use 3 <= minimum neighbours <= neighbours <= 64")
    if not 1 <= min_votes <= neighbors:
        raise ValueError("Use 1 <= minimum votes <= neighbours")


from .las_records import return_masks, clean_flags


def build_tree(support):
    return cKDTree(np.ascontiguousarray(support[:, :2], dtype=float), balanced_tree=False, compact_nodes=False)


def _solve(dx, dy, dz, weight):
    """Batched weighted least squares for dz = a*dx + b*dy + c. Returns coefficients and an ok mask."""
    columns = (dx, dy, np.ones_like(dx))
    normal = np.empty(dx.shape[:1]+(3, 3))
    rhs = np.empty(dx.shape[:1]+(3,))
    for i in range(3):
        rhs[:, i] = (weight*columns[i]*dz).sum(1)
        for j in range(i, 3):
            normal[:, i, j] = normal[:, j, i] = (weight*columns[i]*columns[j]).sum(1)
    # Collinear or coincident neighbours define no plane: the minor axis of the weighted xy
    # spread must exceed 5 cm (standard deviation).
    count = np.maximum(weight.sum(1), 1)
    mx, my = normal[:, 0, 2]/count, normal[:, 1, 2]/count
    sxx, syy = normal[:, 0, 0]/count-mx*mx, normal[:, 1, 1]/count-my*my
    sxy = normal[:, 0, 1]/count-mx*my
    minor = (sxx+syy)/2-np.sqrt(((sxx-syy)/2)**2+sxy**2)
    ok = (weight.sum(1) >= 3) & (minor > .05**2)
    coefficients = np.zeros(dx.shape[:1]+(3,))
    if ok.any():
        coefficients[ok] = np.linalg.solve(normal[ok], rhs[ok][..., None])[..., 0]
    return coefficients, ok


def _neighbours(tree, xy, k, radius, workers):
    distance, index = tree.query(xy, k=k, distance_upper_bound=radius, workers=workers)
    distance, index = distance.reshape(len(xy), k), index.reshape(len(xy), k)
    valid = np.isfinite(distance)
    return distance, np.where(valid, index, 0), valid


def interior_support(xy):
    """Conservatively exclude the measured boundary and holes from face anchors."""
    if not len(xy):
        return np.zeros(0, dtype=bool)
    cells = np.floor((xy-xy.min(0))/INTERIOR_CELL_M).astype(np.int64)+1
    shape = tuple((cells.max(0)+2)[::-1])
    if shape[0]*shape[1] > MAX_INTERIOR_CELLS:
        raise ValueError('Roof interior-support grid exceeds the bounded pilot limit')
    occupied = np.zeros(shape, dtype=bool)
    occupied[cells[:, 1], cells[:, 0]] = True
    # Bridge sub-metre sampling gaps; larger courtyards remain boundaries.
    occupied |= ndimage.binary_closing(occupied, structure=np.ones((3, 3)))
    distance = ndimage.distance_transform_edt(occupied)*INTERIOR_CELL_M
    return distance[cells[:, 1], cells[:, 0]] > INTERIOR_REACH_M


def faces(tree, support_z, radius=DEFAULTS["radius"], neighbors=DEFAULTS["neighbors"],
          min_neighbors=DEFAULTS["min_neighbors"], max_rmse=DEFAULTS["max_rmse"],
          max_slope=DEFAULTS["max_slope"], workers=-1, chunk=200_000):
    """Interior face coefficients (dz/dx, dz/dy, fitted anchor offset), RMSE and status."""
    n = tree.n
    gradient = np.zeros((n, 3), dtype=np.float32)
    rmse = np.full(n, np.nan, dtype=np.float32)
    status = np.full(n, FEW_NEIGHBOURS, dtype=np.uint8)
    data = tree.data
    interior = interior_support(data)
    status[~interior] = EDGE_SUPPORT
    anchors = np.flatnonzero(interior)
    if not len(anchors):
        if n >= 3 and np.linalg.matrix_rank(data-data[0]) < 2:
            status[:] = DEGENERATE
        return gradient, rmse, status
    fit_tree = build_tree(data[anchors])
    k = min(int(neighbors), len(anchors))
    for start in range(0, n, chunk):
        stop = min(n, start+chunk)
        xyz = np.column_stack((data[start:stop], support_z[start:stop]))
        _, index, valid = _neighbours(fit_tree, xyz[:, :2], k, radius, workers)
        index = anchors[index]
        fit = interior[start:stop] & (valid.sum(1) >= min_neighbors)
        if not fit.any():
            continue
        index, valid, xyz = index[fit], valid[fit], xyz[fit]
        dx = np.where(valid, data[index, 0]-xyz[:, 0, None], 0.)
        dy = np.where(valid, data[index, 1]-xyz[:, 1, None], 0.)
        dz = np.where(valid, support_z[index]-xyz[:, 2, None], 0.)
        coefficients, ok = _solve(dx, dy, dz, valid.astype(float))
        residual = dz-(coefficients[:, :1]*dx+coefficients[:, 1:2]*dy+coefficients[:, 2:])
        # One trimmed refit, with the same cutoff rule as the whole-roof plane mode.
        masked = np.where(valid, residual, np.nan)
        centre = np.nanmedian(masked, axis=1)
        mad = np.nanmedian(np.abs(masked-centre[:, None]), axis=1)
        inlier = valid & (np.abs(residual) <= np.clip(3*1.4826*mad, .15, .5)[:, None])
        trimmed, ok2 = _solve(dx, dy, dz, inlier.astype(float))
        use = ok & ok2 & (inlier.sum(1) >= min_neighbors)
        coefficients[use] = trimmed[use]
        weight = np.where(use[:, None], inlier, valid).astype(float)
        residual = dz-(coefficients[:, :1]*dx+coefficients[:, 1:2]*dy+coefficients[:, 2:])
        fit_rmse = np.sqrt((weight*residual**2).sum(1)/np.maximum(weight.sum(1), 1))
        slope = np.hypot(coefficients[:, 0], coefficients[:, 1])
        rows = np.flatnonzero(fit)+start
        status[rows] = np.where(~ok, DEGENERATE, np.where(fit_rmse > max_rmse, ROUGH,
                                                          np.where(slope > max_slope, STEEP, FACE_OK)))
        gradient[rows] = coefficients
        rmse[rows] = np.where(ok, fit_rmse, np.nan)
    return gradient, rmse, status


def evaluate(tree, support_z, gradient, face_status, xyz, radius=DEFAULTS["radius"],
             neighbors=DEFAULTS["neighbors"], below=DEFAULTS["below"], above=DEFAULTS["above"],
             workers=-1, chunk=500_000):
    """Offsets from interior faces within `radius + INTERIOR_REACH_M`.

    Returns arrays: support (roof points within the radius, capped at `neighbors`), faces (of
    nearby interior anchors, usable faces), votes (faces placing the candidate within [-below, +above]), nearest
    (horizontal distance to the nearest roof point), and residual: the median offset of the
    voting faces, or, with no votes, the offset of the closest face (NaN without faces).
    Offsets are candidate Z minus the extended face Z, so positive means above the roof.
    """
    n = len(xyz)
    result = {"support": np.zeros(n, dtype=np.uint8), "faces": np.zeros(n, dtype=np.uint8),
              "votes": np.zeros(n, dtype=np.uint8), "nearest": np.full(n, np.inf, dtype=np.float32),
              "residual": np.full(n, np.nan, dtype=np.float32)}
    if n == 0 or tree.n == 0:
        return result
    k = min(int(neighbors), tree.n)
    data = tree.data
    anchors = np.flatnonzero(face_status == FACE_OK)
    face_tree = build_tree(data[anchors]) if len(anchors) else None
    for start in range(0, n, chunk):
        stop = min(n, start+chunk)
        part = np.asarray(xyz[start:stop], dtype=float)
        distance, index, valid = _neighbours(tree, part[:, :2], k, radius, workers)
        result['support'][start:stop] = valid.sum(1)
        result['nearest'][start:stop] = distance[:, 0]
        if face_tree is None:
            continue
        _, face_index, usable = _neighbours(face_tree, part[:, :2], min(int(neighbors), len(anchors)),
                                           radius+INTERIOR_REACH_M, workers)
        index = anchors[face_index]
        usable &= valid.any(1)[:, None]
        predicted = (support_z[index]+gradient[index, 0]*(part[:, 0, None]-data[index, 0])
                     + gradient[index, 1]*(part[:, 1, None]-data[index, 1])+gradient[index, 2])
        offset = np.where(usable, part[:, 2, None]-predicted, np.nan)
        vote = usable & (offset >= -below) & (offset <= above)
        votes = vote.sum(1)
        with np.errstate(invalid="ignore"):
            voted = np.where(vote, offset, np.nan)
            closest = np.take_along_axis(offset, np.argmin(np.where(usable, np.abs(offset), np.inf), 1)[:, None], 1)[:, 0]
        median = np.full(len(part), np.nan)
        if votes.any():
            median[votes > 0] = np.nanmedian(voted[votes > 0], axis=1)
        result["support"][start:stop] = valid.sum(1)
        result["faces"][start:stop] = usable.sum(1)
        result["votes"][start:stop] = votes
        result["nearest"][start:stop] = distance[:, 0]
        result["residual"][start:stop] = np.where(votes > 0, median, closest)
    return result


def select(result, min_votes=DEFAULTS["min_votes"]):
    """Candidates that at least `min_votes` usable roof faces place within the band."""
    return result["votes"] >= min_votes


def envelope(support, xmin, ymax, cell, shape, radius):
    """Per-cell lowest and highest roof Z within `radius` (plus one cell) of each cell.

    A cheap prefilter only: cells with no roof point within reach get +inf/-inf.
    """
    rows = np.floor((ymax-support[:, 1])/cell).astype(np.int64)
    cols = np.floor((support[:, 0]-xmin)/cell).astype(np.int64)
    inside = (rows >= 0) & (rows < shape[0]) & (cols >= 0) & (cols < shape[1])
    flat = rows[inside]*shape[1]+cols[inside]
    low = np.full(shape[0]*shape[1], np.inf, dtype=np.float32)
    high = np.full(shape[0]*shape[1], -np.inf, dtype=np.float32)
    np.minimum.at(low, flat, support[inside, 2].astype(np.float32))
    np.maximum.at(high, flat, support[inside, 2].astype(np.float32))
    reach = int(np.ceil(radius/cell))+1
    yy, xx = np.mgrid[-reach:reach+1, -reach:reach+1]
    disc = np.hypot(yy, xx) <= reach
    low = ndimage.minimum_filter(low.reshape(shape), footprint=disc, mode="constant", cval=np.inf)
    high = ndimage.maximum_filter(high.reshape(shape), footprint=disc, mode="constant", cval=-np.inf)
    return low, high


def prefilter(xyz, low, high, xmin, ymax, cell, below, above, radius, max_slope):
    """Candidates that could fall inside the band; every other candidate is certainly unchanged."""
    rows = np.floor((ymax-xyz[:, 1])/cell).astype(np.int64)
    cols = np.floor((xyz[:, 0]-xmin)/cell).astype(np.int64)
    inside = (rows >= 0) & (rows < low.shape[0]) & (cols >= 0) & (cols < low.shape[1])
    keep = np.zeros(len(xyz), dtype=bool)
    r, c = rows[inside], cols[inside]
    # An extended face may rise or fall up to max_slope*radius beyond its roof point's Z.
    slack = max_slope*radius
    z = xyz[inside, 2]
    keep[inside] = (z >= low[r, c]-below-slack) & (z <= high[r, c]+above+slack)
    return keep
