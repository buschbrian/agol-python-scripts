"""Index-paired comparison of two tree outputs that should be identical, for the step b reproducibility row.

    python reviews/2026-09-30/repeat_compare.py FIRST.las SECOND.las OUT.json

Step b repeats the September 29 tree-full row (absolute Z, 12TVL2804 core, same model, batch 1). Any difference
between the two outputs is run-to-run nondeterminism of the tree model. Uses the same paired_predictions as the
HAG-Z pairing (dl_hag_check.py), so the counts compare directly with its 267,073 changed points. Read-only on
both inputs. Target class is 5 (tree).
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "2026-09-29"))
from canopy.lidar_root import live  # noqa: E402
from dl_hag_check import paired_predictions  # noqa: E402


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(first, second, out):
    first, second = live(first), live(second)
    result = paired_predictions(first, second, 5)
    result["first"] = {"path": str(first), "sha256": sha256(first)}
    result["second"] = {"path": str(second), "sha256": sha256(second)}
    result["byte_identical_files"] = result["first"]["sha256"] == result["second"]["sha256"]
    result["points_changed"] = result["target_absolute_only"] + result["target_hag_only"]
    Path(out).write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("points", "target_both", "target_absolute_only", "target_hag_only",
                                             "identical_predictions", "byte_identical_files")}, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
