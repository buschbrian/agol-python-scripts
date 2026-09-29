"""Tree candidates near buildings before and after a roof refinement, on one yardstick.

A parameterized version of candidates_near_buildings.py (whose hard-coded RUNS and outputs are
left unchanged). Both the baseline and the refined run's candidates are measured against the
BASELINE prepared LAS of the tile (class 6 = building, class 2 = ground), because the refinement
itself adds class-6 points, which would move the yardstick. Same method as the committed script:
for candidates with class-6 points within 1 m, roof height = 90th-percentile class-6 Z within 1 m
minus median class-2 Z within 5 m; the candidate's HEIGHT_M is compared with it.

Also counts baseline candidates with no candidate of the refined run within --match metres,
by band: removed candidates. Neither the bands nor removal are verified labels.

Usage (Pro Python, from canopy-toolbox):
    python reviews/2026-09-29/roof_local_candidates.py REPORT.json TILE BASE_RUN NEW_RUN [TILE BASE_RUN NEW_RUN ...]
Run folders are relative to ROOT\\<tile>\\ unless absolute.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import arcpy
import numpy as np
from scipy.spatial import cKDTree

from canopy import roofs
from canopy.matching import match_candidates
from canopy.run_safeguards import fingerprint

ROOT = Path(r"H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29")
BANDS = ("at_roof_height_le_0.5m", "0.5_to_2m_above_roof", "over_2m_above_roof")
MATCH_M = 1.0


def points(path, code):
    pts, scale, offset, modern = roofs._records(path)
    codes = pts["classification"] if modern else pts["classification"] & 31
    mask = codes == code
    return np.column_stack([pts[axis][mask] * scale[i] + offset[i] for i, axis in enumerate("xyz")])


def candidates(run):
    state = json.loads((run / "run.json").read_text())
    if state.get("status") != "complete":
        raise ValueError(f"Candidate run is incomplete: {run}")
    fc = state["outputs"]["trees_review"]
    if not arcpy.Exists(fc):
        raise ValueError(f"Candidate output is absent: {fc}")
    rows = list(arcpy.da.SearchCursor(fc, ["SHAPE@X", "SHAPE@Y", "HEIGHT_M", "CROWN_STATUS"]))
    return (np.array([(r[0], r[1]) for r in rows]).reshape(-1, 2), np.array([r[2] for r in rows], dtype=float),
            np.array([r[3] == "CROWN_TOO_SMALL" for r in rows], dtype=bool))


def bands(xy, height, building, btree, ground, gtree):
    """Band index per candidate: -1 not within 1 m of a building, -2 no ground within 5 m, else 0/1/2."""
    out = np.full(len(xy), -1)
    roof = btree.query_ball_point(xy, 1.0, workers=-1)
    under = gtree.query_ball_point(xy, 5.0, workers=-1)
    for i, (r, g) in enumerate(zip(roof, under)):
        if not r:
            continue
        if not g:
            out[i] = -2
            continue
        above = height[i] - (np.percentile(building[r, 2], 90) - np.median(ground[g, 2]))
        out[i] = 0 if above <= .5 else 1 if above <= 2 else 2
    return out


def summary(band, small):
    return {"candidates": int(len(band)), "within_1m": int((band != -1).sum()),
            "within_1m_no_ground_5m": int((band == -2).sum()),
            "by_height_vs_roof": {name: int((band == i).sum()) for i, name in enumerate(BANDS)},
            "small_crown_subset": {name: int(((band == i) & small).sum()) for i, name in enumerate(BANDS)}}


def main(report, *triples):
    if not triples or len(triples) % 3:
        raise SystemExit(__doc__)
    result = {"method": "yardstick = BASELINE prepared LAS of the tile file (prepared\\points\\<tile>.las): "
                        "roof = 90th percentile class-6 Z within 1 m of the treetop; ground = median class-2 Z "
                        "within 5 m; removed = unmatched baseline candidate under one-to-one "
                        f"maximum-cardinality/minimum-distance matching within {MATCH_M} m", "tiles": {}}
    for tile, base, new in zip(*[iter(triples)] * 3):
        las = ROOT / tile / "prepared" / "points" / f"{tile}.las"
        building, ground = points(las, 6), points(las, 2)
        btree, gtree = cKDTree(building[:, :2]), cKDTree(ground[:, :2])
        base_run, new_run = [Path(p) if Path(p).is_absolute() else ROOT / tile / p for p in (base, new)]
        # This report is specifically for the local method. Reject the older plane
        # experiment that was accidentally supplied for the residential tile.
        state = json.loads((new_run / "run.json").read_text())
        lasd = Path(state["lasd"]) if "lasd" in state else Path(state.get("input_lasd", new_run.parent / "refined" / "prepared.lasd"))
        prep = json.loads((lasd.parent / "preparation.json").read_text())
        if (prep.get("status") != "complete" or prep.get("parameters", {}).get("method") != "local_surface"
                or state.get("parameters", {}).get("source_id") != prep.get("source_id")):
            raise ValueError(f"Expected a completed local roof refinement, not another experiment: {new_run}")
        (bxy, bh, bs), (nxy, nh, ns) = candidates(base_run), candidates(new_run)
        bb, nb = bands(bxy, bh, building, btree, ground, gtree), bands(nxy, nh, building, btree, ground, gtree)
        matched = match_candidates(bxy, nxy, MATCH_M)
        kept = matched["baseline_to_variant"] >= 0
        removed = {"total": int((~kept).sum()), "not_within_1m": int((~kept & (bb == -1)).sum()),
                   "within_1m_no_ground_5m": int((~kept & (bb == -2)).sum()),
                   **{name: int((~kept & (bb == i)).sum()) for i, name in enumerate(BANDS)}}
        result["tiles"][tile] = {"base_run": str(base_run), "new_run": str(new_run),
                                 "base_manifest": fingerprint(base_run / "run.json"),
                                 "new_manifest": fingerprint(new_run / "run.json"),
                                 "preparation_manifest": fingerprint(lasd.parent / "preparation.json"),
                                 "new_candidates": int((matched["variant_to_baseline"] < 0).sum()),
                                 "matching_ambiguity": {k: matched[k] for k in ("ambiguous_baseline", "ambiguous_variant")},
                                 "before": summary(bb, bs), "after": summary(nb, ns),
                                 "baseline_candidates_removed": removed,
                                 "over_2m_removed_examples": [
                                     {"x": round(float(bxy[i, 0]), 2), "y": round(float(bxy[i, 1]), 2),
                                      "height_m": round(float(bh[i]), 2)}
                                     for i in np.flatnonzero(~kept & (bb == 2))[:25]]}
        print(tile, json.dumps({k: v for k, v in result["tiles"][tile].items() if k != "over_2m_removed_examples"}, indent=1))
    Path(report).write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main(*sys.argv[1:])
