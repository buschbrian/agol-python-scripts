"""Do the refined classes of a tile agree with the human training labels more or less often than the October 8 baseline?

    python reviews/2026-10-19/fractal-city/label_check_refined.py REFINED.las PACKET_DIR LABELS.csv OUT.json

Run with the Myria3D environment's Python (PYTHONNOUSERSITE=1). Training diagnostic only, never evaluation: the labelled
units are training patches on 12TVL2804, and the audit-2 units are unlabelled and untouched. Labels are read through
compare.load_answers, which checks the packet digest and every label token; nothing is written except OUT.json.
For each answered unit, the clean points in its circle and height slab are taken from the refined copy; the patch's family is
the one that more than half of those points share, once from BASE_CLASS (baseline) and once from the refined classification.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
from canopy import fractal_compare as fc  # noqa: E402

CLASS_FAMILIES = {1: "OTHER", 2: "GROUND", 20: "GROUND", 3: "VEGETATION", 4: "VEGETATION", 5: "VEGETATION",
                  6: "BUILDING", 9: "WATER", 17: "STRUCTURE", 64: "STRUCTURE", 7: "NOISE", 18: "NOISE"}


def patch_family(classes):
    """The family shared by more than half the patch's points, else None."""
    if not len(classes):
        return None, {}
    families = np.array([CLASS_FAMILIES.get(int(c), "OTHER") for c in classes])
    names, counts = np.unique(families, return_counts=True)
    best = int(counts.argmax())
    return (str(names[best]) if counts[best] > len(classes)/2 else None), dict(zip(names.tolist(), counts.tolist()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("refined", type=Path)
    parser.add_argument("packet", type=Path)
    parser.add_argument("labels", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args(argv)
    if args.out.exists():
        raise FileExistsError(args.out)
    spec = importlib.util.spec_from_file_location("compare", TOOLBOX/"reviews"/"2026-09-30"/"fractal"/"compare.py")
    compare = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compare)
    answers, _ = compare.load_answers(args.packet, args.labels)
    import laspy
    las = laspy.read(args.refined)
    clean = ~(np.asarray(las.withheld, bool) | np.asarray(las.synthetic, bool) | np.asarray(las.overlap, bool))
    x, y, z = (np.asarray(v)[clean] for v in (las.x, las.y, las.z))
    base, refined = np.asarray(las.BASE_CLASS)[clean], np.asarray(las.classification)[clean]
    rule = np.asarray(las.REFINE_RULE)[clean]
    rows = []
    for unit in answers:
        cx, cy, r = float(unit["X"]), float(unit["Y"]), float(unit.get("PATCH_R_M", 1.0))
        hit = (np.hypot(x-cx, y-cy) <= r) & (z >= float(unit["Z_LOW"])) & (z <= float(unit["Z_HIGH"]))
        human = fc.LABEL_FAMILIES.get(unit["LABEL"])
        before, before_counts = patch_family(base[hit])
        after, after_counts = patch_family(refined[hit])
        rows.append({"UNIT_ID": unit["UNIT_ID"], "LABEL": unit["LABEL"], "HUMAN_FAMILY": human, "POINTS": int(hit.sum()),
                     "CHANGED_POINTS": int((base[hit] != refined[hit]).sum()),
                     "RULES": {str(int(k)): int(v) for k, v in zip(*np.unique(rule[hit][rule[hit] > 0], return_counts=True))},
                     "BASELINE_FAMILY": before, "REFINED_FAMILY": after,
                     "BASELINE_AGREE": None if human is None or hit.sum() < fc.MIN_PATCH_POINTS else before == human,
                     "REFINED_AGREE": None if human is None or hit.sum() < fc.MIN_PATCH_POINTS else after == human,
                     "BASELINE_COUNTS": before_counts, "REFINED_COUNTS": after_counts})
    comparable = [r for r in rows if r["BASELINE_AGREE"] is not None]
    by_label = {}
    for label in sorted({r["LABEL"] for r in comparable}):
        sel = [r for r in comparable if r["LABEL"] == label]
        by_label[label] = {"units": len(sel), "baseline_agree": sum(r["BASELINE_AGREE"] for r in sel),
                           "refined_agree": sum(r["REFINED_AGREE"] for r in sel)}
    report = {"refined": str(args.refined), "answered_units": len(rows), "comparable_units": len(comparable),
              "baseline_agree": sum(r["BASELINE_AGREE"] for r in comparable),
              "refined_agree": sum(r["REFINED_AGREE"] for r in comparable),
              "improved": [r["UNIT_ID"] for r in comparable if r["REFINED_AGREE"] and not r["BASELINE_AGREE"]],
              "worsened": [r["UNIT_ID"] for r in comparable if r["BASELINE_AGREE"] and not r["REFINED_AGREE"]],
              "units_with_changed_points": sum(r["CHANGED_POINTS"] > 0 for r in rows), "by_label": by_label,
              "not_comparable_labels": sorted({r["LABEL"] for r in rows if r["HUMAN_FAMILY"] is None}),
              "interpretation": "Training-patch diagnostic on 58 answered units of one tile; not evaluation, not an accuracy estimate.",
              "units": rows}
    args.out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "units"}, indent=1))


if __name__ == "__main__":
    main()
