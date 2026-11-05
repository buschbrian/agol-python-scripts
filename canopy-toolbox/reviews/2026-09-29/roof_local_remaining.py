r"""Why do some at-roof-height tree candidates survive the local roof refinement?

For each candidate of the refined run that is still within 1 m of a (baseline) building point and
at roof height (same yardstick as roof_local_candidates.py), takes the highest class-4/5
first-or-single return within 0.5 m of the treetop in the REFINED LAS (the point that made the
CHM peak) and re-evaluates it with the refinement's own parameters and baseline roof support.
Each is sorted into one reason:
  no_roof_within_radius, too_few_usable_faces, above_band, below_band, few_votes (1..min_votes-1),
  no_vegetation_point (peak not found within 0.5 m).
Diagnostic only; not a label.

Usage (Pro Python, from canopy-toolbox):
    python reviews/2026-09-29/roof_local_remaining.py REPORT.json TILE [TILE ...]
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
from scipy.spatial import cKDTree

from canopy import roofs, roof_surface as rs
import roof_local_candidates as rc

ROOT = rc.ROOT
OUT = ROOT / "roof-local"


def main(report, *tiles):
    result = {}
    for tile in tiles:
        refined = OUT / tile / "refined"
        p = json.loads((refined / "preparation.json").read_text())["parameters"]
        base_las = ROOT / tile / "prepared" / "points" / f"{tile}.las"
        building, ground = rc.points(base_las, 6), rc.points(base_las, 2)
        btree, gtree = cKDTree(building[:, :2]), cKDTree(ground[:, :2])
        xy, height, small = rc.candidates(OUT / tile / "run")
        band = rc.bands(xy, height, building, btree, ground, gtree)
        xy = xy[band == 0]
        # Roof support and faces exactly as the refinement built them (all prepared files).
        support = roofs._load_support(sorted((ROOT / tile / "prepared" / "points").glob("*.las")))
        tree = rs.build_tree(support)
        gradient, _, status = rs.faces(tree, support[:, 2], p["radius_m"], p["neighbors"], p["min_face_neighbors"],
                                       p["max_face_rmse_m"], p["max_face_slope"])
        pts, scale, offset, modern = roofs._records(refined / "points" / f"{tile}.las")
        first, _ = rs.return_masks(np.asarray(pts["returns"]), modern)
        codes = np.asarray(pts["classification"] if modern else pts["classification"] & 31)
        veg = np.flatnonzero(np.isin(codes, [4, 5]) & first)
        vxyz = np.column_stack([pts[a][veg] * scale[i] + offset[i] for i, a in enumerate("xyz")])
        del pts
        vtree = cKDTree(vxyz[:, :2])
        peaks, missing = [], 0
        for near in vtree.query_ball_point(xy, .5, workers=-1):
            if near:
                peaks.append(vxyz[near[int(np.argmax(vxyz[near, 2]))]])
            else:
                missing += 1
        peaks = np.array(peaks).reshape(-1, 3)
        r = rs.evaluate(tree, support[:, 2], gradient, status, peaks, p["radius_m"], p["neighbors"],
                        p["below_roof_m"], p["above_roof_m"])
        reason = np.where(r["support"] == 0, "no_roof_within_radius",
                 np.where(r["faces"] < p["min_votes"], "too_few_usable_faces",
                 np.where(r["votes"] >= p["min_votes"], "selected_now",
                 np.where(r["votes"] > 0, "few_votes",
                 np.where(r["residual"] > p["above_roof_m"], "above_band", "below_band")))))
        counts = {k: int((reason == k).sum()) for k in ("no_roof_within_radius", "too_few_usable_faces", "few_votes",
                                                         "above_band", "below_band", "selected_now")}
        counts["no_vegetation_point"] = missing
        residual = r["residual"]
        result[tile] = {"remaining_at_roof_height": int(len(xy)), "reasons": counts,
                        "above_band_residual_m": rc_pct(residual[reason == "above_band"]),
                        "below_band_residual_m": rc_pct(residual[reason == "below_band"]),
                        "nearest_roof_m_when_faces_too_few": rc_pct(r["nearest"][reason == "too_few_usable_faces"])}
        print(tile, json.dumps(result[tile], indent=1))
    Path(report).write_text(json.dumps({"method": __doc__.strip().splitlines()[0], "tiles": result}, indent=2))


def rc_pct(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return {f"p{q}": round(float(v), 2) for q, v in zip((10, 25, 50, 75, 90), np.percentile(values, (10, 25, 50, 75, 90)))} \
        if values.size else None


if __name__ == "__main__":
    main(*sys.argv[1:])
