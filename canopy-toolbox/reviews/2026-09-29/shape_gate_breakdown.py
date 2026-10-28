r"""Describe why the shape-gate apply rule selects what it does, from a REVIEW folder.

Reads shape_gate.json, changes\*.npz and the unchanged input files (read-only) and reports, for
class 4/5 points in the apply groups (wall_like, wire, pole): return types, neighbourhood shares,
and how many points each rule condition leaves. It also counts the diagnostic's own wall
definition (planarity >= 0.6 and PDAL Verticality >= 0.7) beside the normal-based one.

Descriptive only: no labels are read and nothing here changes the prespecified rule.

Usage (from canopy-toolbox; no ArcPy needed):
    python reviews/2026-09-29/shape_gate_breakdown.py REVIEW_FOLDER REPORT.json
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np

from canopy import las_records, shape_gate as sg
from canopy.lidar_root import live


def main(folder, report):
    folder = Path(folder)
    manifest = json.loads((folder/"shape_gate.json").read_text(encoding="utf-8"))
    if manifest["mode"] != "review":
        raise SystemExit("Use a review-mode shape-gate folder")
    p = manifest["parameters"]
    parts = []
    for source in manifest["input_files"]:
        path = live(source["path"])
        log = folder/"changes"/(path.stem+".npz")
        if not log.is_file():
            continue
        with np.load(log) as audit:
            data = {key: audit[key] for key in audit.files}
        points, _, _, modern, _ = las_records.records(path, "r")
        data["return_type"] = sg.return_type(np.asarray(points["returns"][data["point_index"]]), modern)
        data["class"] = data["previous_class_byte"] if modern else data["previous_class_byte"] & 31
        del points
        parts.append(data)
    d = {key: np.concatenate([part[key] for part in parts]) for key in parts[0]}
    result = {"source": str(folder), "gate_extent": manifest["gate_extent"], "classes": {}}
    for code in (4, 5):
        base = d["class"] == code
        row = {"points": int(base.sum())}
        for number in sg.APPLY_GROUPS:
            member = base & (d["group"] == number)
            single_share_ok = d["single_share"] >= p["min_single_share"]
            irregular_ok = d["irregular_share"] <= p["max_irregular_share"]
            row[sg.GROUPS[number]] = {
                "points": int(member.sum()),
                "return_type": {name: int((member & (d["return_type"] == i)).sum())
                                for i, name in enumerate(sg.RETURN_TYPES)},
                "single_share_median": _median(d["single_share"][member]),
                "irregular_share_median": _median(d["irregular_share"][member]),
                "near_building": int((member & (d["nearest_building_m"] <= p["near_building_m"])).sum()),
                "rule": {"own_single": int((member & d["own_single"]).sum()),
                         "and_single_share": int((member & d["own_single"] & single_share_ok).sum()),
                         "and_irregular_share": int((member & d["own_single"] & single_share_ok & irregular_ok).sum())},
                "without_return_conditions": {"irregular_share_only": int((member & irregular_ok).sum())},
            }
        planar = d["planarity"] >= p["dominant"]
        row["wall_definitions"] = {
            "normal_based_1_minus_normal_z_ge_0.7": int((base & planar & (1-d["normal_z"] >= p["vertical"])).sum()),
            "diagnostic_pdal_verticality_ge_0.7": int((base & planar & (d["pdal_verticality"] >= p["vertical"])).sum())}
        result["classes"][str(code)] = row
    Path(report).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


def _median(values):
    return round(float(np.median(values)), 3) if len(values) else None


if __name__ == "__main__":
    main(*sys.argv[1:])
