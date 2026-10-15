r"""Feature profile of the 12TVL2804 pilot treetops: the evidence behind the two treetop_evidence corrections.

Pro Python with PYTHONNOUSERSITE=1, from canopy-toolbox:
    python reviews/2026-10-15/pilot_feature_profile.py

Reads the 29 September pilot run's trees_review and its own prepared tile, as `treetop_evidence_driver.py reproduce`
does, and writes pilot-feature-profile.json: percentiles (10, 25, 50, 75, 90) of each feature for the ROOF_HEIGHT,
OVERHANG, POLE_HINT and far-from-building groups, plus CANOPY_RETURNS counts under triage's 0.25 m thickness and
under the corrected rule. Unlabelled treetops only; no human label is read.
"""
import json
from pathlib import Path
import sys

import arcpy
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from canopy import treetop_evidence as te  # noqa: E402
from canopy.lidar_root import lidar_root  # noqa: E402

TILE = lidar_root()/"2023-salt-lake-valley"/"runs"/"pilot-2026-09-29"/"12TVL2804"
KEYS = ("top_nonlast", "top_thickness", "top_normal_z", "n_top", "ctx_linearity", "ctx_axis_z", "ctx_extent_z",
        "ctx_n", "height_m", "crown_area_m2")


def percentiles(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return [round(float(v), 3) for v in np.percentile(values, [10, 25, 50, 75, 90])] if len(values) else []


def main():
    fc = json.loads((TILE/"run"/"run.json").read_text())["outputs"]["trees_review"]
    rows = list(arcpy.da.SearchCursor(fc, ["SHAPE@X", "SHAPE@Y", "HEIGHT_M", "CROWN_AREA_M2"]))
    xy = np.array([(r[0], r[1]) for r in rows])
    height = np.array([r[2] for r in rows], dtype=float)
    f = te.evaluate(xy, height, te.read_points(TILE/"prepared"/"points"/"12TVL2804.las"))
    f["height_m"] = height
    f["crown_area_m2"] = np.array([np.nan if r[3] is None else r[3] for r in rows], dtype=float)
    groups = {"ROOF_HEIGHT": f["ROOF_HEIGHT"], "OVERHANG": f["OVERHANG"], "POLE_HINT": f["POLE_HINT"],
              "no_building_within_5m": np.isnan(f["building_dist_m"]), "all": np.ones(len(rows), bool)}
    enough = f["n_top"] >= te.RULES["min_top_points"]
    nonlast = np.nan_to_num(f["top_nonlast"]) >= te.RULES["canopy_nonlast_min"]
    thickness = np.nan_to_num(f["top_thickness"])
    record = {
        "rules_version": te.RULES_VERSION, "treetops": len(rows), "percentiles": [10, 25, 50, 75, 90],
        "groups": {g: {"n": int(m.sum()), **{k: percentiles(np.asarray(f[k], float)[m]) for k in KEYS}}
                   for g, m in groups.items()},
        "pole_hint_top_nonlast_ge_0.5_share": round(float(np.mean(f["top_nonlast"][f["POLE_HINT"]] >= .5)), 3),
        "canopy_returns": {"triage_thickness_0.25": int(np.count_nonzero(enough & nonlast & (thickness >= .25))),
                           "corrected_thickness_gt_0.10": int(np.count_nonzero(f["CANOPY_RETURNS"]))},
        "note": "Unlabelled pilot treetops; these profiles motivated definition corrections 1 and 2 in "
                "canopy/treetop_evidence.py. They are not accuracy evidence.",
    }
    (HERE/"pilot-feature-profile.json").write_text(json.dumps(record, indent=2))
    print(json.dumps({g: {k: v for k, v in s.items() if k in ("n", "height_m", "crown_area_m2", "top_thickness",
                                                                "top_nonlast")} for g, s in record["groups"].items()},
                     indent=1))
    print(record["canopy_returns"], record["pole_hint_top_nonlast_ge_0.5_share"])


if __name__ == "__main__":
    main()
