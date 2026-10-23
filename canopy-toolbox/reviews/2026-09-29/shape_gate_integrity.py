r"""Full byte comparison of shape-gate LAS copies against the unchanged prepared inputs.

For every copied point file, checks that (1) sizes match, (2) the header and VLRs are identical,
(3) the only differing bytes are classification bytes of points in changes\<file>.npz, (4) their
previous and new bytes match the log, the new class is 1 (apply) or 64-71 (review), and legacy
flag bits are kept, and (5) the input size and mtime still match the manifest. Works for both
modes: apply folders hold preparation.json, review folders shape_gate.json.

Usage (from canopy-toolbox; no ArcPy needed):
    python reviews/2026-09-29/shape_gate_integrity.py REPORT.json GATE_FOLDER [GATE_FOLDER ...]
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np

from canopy import las_records
from canopy.lidar_root import live

BLOCK = 2_000_000


def check(folder):
    manifest_path = folder/"preparation.json"
    if not manifest_path.is_file():
        manifest_path = folder/"shape_gate.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    apply = manifest["mode"] == "apply"
    allowed = {1} if apply else set(range(64, 73))
    rows = {}
    for source in manifest["input_files"]:
        original = live(source["path"])
        copy = folder/"points"/original.name
        stat = original.stat()
        if not copy.is_file():
            rows[original.name] = {"copied": False}
            continue
        info = las_records.header(copy)
        modern, length, start = info["format"] >= 6, info["record_length"], info["offset"]
        byte = 16 if modern else 15
        with np.load(folder/"changes"/(copy.stem+".npz")) as log:
            logged, previous, new = log["point_index"], log["previous_class_byte"], log["new_class_byte"]
        found, before, after = [], [], []
        other_bytes = 0
        with open(original, "rb") as a, open(copy, "rb") as b:
            head_same = a.read(start) == b.read(start)
            for first in range(0, info["points"], BLOCK):
                x = np.frombuffer(a.read(BLOCK*length), np.uint8).reshape(-1, length)
                y = np.frombuffer(b.read(BLOCK*length), np.uint8).reshape(-1, length)
                diff = x != y
                other_bytes += int(np.delete(diff, byte, axis=1).sum())
                idx = np.flatnonzero(diff[:, byte])
                found.append(idx+first); before.append(x[idx, byte]); after.append(y[idx, byte])
            tail_same = a.read() == b.read()
        found, before, after = np.concatenate(found), np.concatenate(before), np.concatenate(after)
        class_now = after if modern else after & 31
        rows[copy.name] = {
            "copied": True, "points": info["points"], "changed_logged": int(len(logged)),
            "changed_found": int(len(found)), "same_size": stat.st_size == copy.stat().st_size,
            "header_and_vlrs_identical": head_same, "trailing_bytes_identical": tail_same,
            "non_class_bytes_differing": other_bytes,
            "changed_indices_match_log": bool(np.array_equal(found, logged)),
            "previous_bytes_match_log": bool(len(found) == len(logged) and np.array_equal(before, previous)),
            "new_bytes_match_log": bool(len(found) == len(logged) and np.array_equal(after, new)),
            "new_classes_allowed": bool(set(np.unique(class_now).tolist()) <= allowed),
            "legacy_flag_bits_kept": True if modern else bool(((after & 224) == (before & 224)).all()),
            "input_unchanged_since_gate": (stat.st_size, stat.st_mtime_ns) == (source["bytes"], source["mtime_ns"])}
    checks = ("same_size", "header_and_vlrs_identical", "trailing_bytes_identical", "changed_indices_match_log",
              "previous_bytes_match_log", "new_bytes_match_log", "new_classes_allowed", "legacy_flag_bits_kept",
              "input_unchanged_since_gate")
    ok = all(all(r[c] for c in checks) and r["non_class_bytes_differing"] == 0 for r in rows.values() if r["copied"])
    return {"mode": manifest["mode"], "all_checks_pass": ok, "files": rows}


def main(report, *folders):
    result = {str(f): check(Path(f)) for f in folders}
    Path(report).write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v["all_checks_pass"] for k, v in result.items()}, indent=2))


if __name__ == "__main__":
    main(*sys.argv[1:])
