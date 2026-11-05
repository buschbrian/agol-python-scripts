r"""Full byte comparison of refined LAS copies against the unchanged prepared inputs.

For every point file, checks that (1) sizes match, (2) the header and VLRs are identical, (3) the
only differing bytes are classification bytes of the points in changes\<file>.npz, (4) those
points' previous bytes match the log and their class is now 6 (legacy flag bits preserved), and
(5) the input file size and mtime still match the refinement manifest.

Usage (Pro Python, from canopy-toolbox):
    python reviews/2026-09-29/roof_local_integrity.py REPORT.json REFINED_FOLDER [REFINED_FOLDER ...]
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np

from canopy import preparation
from canopy.lidar_root import live

BLOCK = 2_000_000


def check(refined):
    manifest = json.loads((refined / "preparation.json").read_text())
    rows = {}
    for source in manifest["input_files"]:
        original, copy = live(source["path"]), refined / "points" / Path(source["path"]).name
        stat = original.stat()
        info = preparation.header(copy)
        modern, length, start = info["format"] >= 6, info["record_length"], info["offset"]
        byte = 16 if modern else 15
        log = np.load(refined / "changes" / (copy.stem + ".npz"))
        logged = log["point_index"]
        order = np.argsort(logged)
        logged, previous = logged[order], log["previous_class_byte"][order]
        found, before, after = [], [], []
        other_bytes = 0
        with open(original, "rb") as a, open(copy, "rb") as b:
            head_same = a.read(start) == b.read(start)
            for first in range(0, info["points"], BLOCK):
                x = np.frombuffer(a.read(BLOCK * length), np.uint8)
                y = np.frombuffer(b.read(BLOCK * length), np.uint8)
                x, y = x.reshape(-1, length), y.reshape(-1, length)
                diff = x != y
                other_bytes += int(np.delete(diff, byte, axis=1).sum())
                idx = np.flatnonzero(diff[:, byte])
                found.append(idx + first); before.append(x[idx, byte]); after.append(y[idx, byte])
            tail_same = a.read() == b.read()
        found, before, after = np.concatenate(found), np.concatenate(before), np.concatenate(after)
        class_now = after if modern else after & 31
        flags_kept = True if modern else bool(((after & 224) == (before & 224)).all())
        rows[copy.name] = {
            "points": info["points"], "changed_logged": int(len(logged)), "changed_found": int(len(found)),
            "same_size": stat.st_size == copy.stat().st_size, "header_and_vlrs_identical": head_same,
            "trailing_bytes_identical": tail_same, "non_class_bytes_differing": other_bytes,
            "changed_indices_match_log": bool(np.array_equal(found, logged)),
            "previous_bytes_match_log": bool(np.array_equal(before, previous)) if len(found) == len(logged) else False,
            "all_changed_now_class_6": bool((class_now == 6).all()), "legacy_flag_bits_kept": flags_kept,
            "input_unchanged_since_refine": (stat.st_size, stat.st_mtime_ns) == (source["bytes"], source["mtime_ns"])}
    ok = all(r["same_size"] and r["header_and_vlrs_identical"] and r["trailing_bytes_identical"] and
             r["non_class_bytes_differing"] == 0 and r["changed_indices_match_log"] and r["previous_bytes_match_log"]
             and r["all_changed_now_class_6"] and r["legacy_flag_bits_kept"] and r["input_unchanged_since_refine"]
             for r in rows.values())
    return {"all_checks_pass": ok, "files": rows}


def main(report, *folders):
    result = {str(f): check(Path(f)) for f in folders}
    Path(report).write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v["all_checks_pass"] for k, v in result.items()}, indent=2))


if __name__ == "__main__":
    main(*sys.argv[1:])
