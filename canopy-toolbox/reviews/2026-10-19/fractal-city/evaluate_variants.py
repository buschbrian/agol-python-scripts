"""Score classification variants of one tile against the human training labels (training diagnostic, never evaluation).

    python reviews/2026-10-19/fractal-city/evaluate_variants.py TILE PACKET_DIR LABELS.csv OUT.json [--ndvi 0.10]

Run with the Myria3D environment's Python (laspy; PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT set). Variants, all from the refined copy:
- baseline: BASE_CLASS (the October 8 classes);
- refined: the applied rules 1 to 6;
- rule11: refined, plus every point with rule 11 (vegetation that all FRACTAL passes call ground) moved to ground;
- rule11_green: the same, except points whose NAIP 2024 colour is green (NDVI above the threshold) stay vegetation, so lawns
  and gardens are spared.
The NDVI threshold (default 0.10) was fixed on October 20 before scoring: the midpoint of the NAIP 2024 NDVI measured on visibly
green pixels (about 0.33) and on pavement and roofs (about -0.13) on October 1. NDVI comes from each point's colour in the
consensus copy (red and near-infrared). A split answer is scored as its two parts (training_review.answer_parts), each needing
12 points. A part agrees when more than half its points fall in the label's family. Nothing is written except OUT.json.
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
from canopy import fractal_compare as fc, training_review as tr  # noqa: E402
from canopy.lidar_root import lidar_root  # noqa: E402

LIDAR = lidar_root()/"2023-salt-lake-valley"
REFINED = LIDAR/"runs"/"refined-fractal-20261019"/"points"
CONSENSUS = LIDAR/"fractal"/"city-20261019"/"fractal"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def variants(base, refined, rule, ndvi, threshold):
    out = {"baseline": base, "refined": refined}
    r11 = refined.copy()
    r11[rule == 11] = 2
    out["rule11"] = r11
    green = refined.copy()
    green[(rule == 11) & ~(ndvi > threshold)] = 2
    out["rule11_green"] = green
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tile")
    parser.add_argument("packet", type=Path)
    parser.add_argument("labels", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--ndvi", type=float, default=0.10)
    args = parser.parse_args(argv)
    if args.out.exists():
        raise FileExistsError(args.out)
    import laspy
    lcr = load("label_check_refined", HERE.parent/"label_check_refined.py")
    compare = load("compare", TOOLBOX/"reviews"/"2026-09-30"/"fractal"/"compare.py")
    answers, _ = compare.load_answers(args.packet, args.labels)
    ref = laspy.read(REFINED/f"{args.tile}.las")
    cons = laspy.read(CONSENSUS/args.tile/"consensus.las")
    for name in ("X", "Y", "Z", "gps_time"):
        if not np.array_equal(np.asarray(ref[name]), np.asarray(cons[name])):
            raise ValueError(f"Refined copy and consensus are not aligned ({name})")
    clean = ~(np.asarray(ref.withheld, bool) | np.asarray(ref.synthetic, bool) | np.asarray(ref.overlap, bool))
    x, y, z = (np.asarray(v)[clean] for v in (ref.x, ref.y, ref.z))
    red, nir = (np.asarray(cons[c], dtype=np.float64)[clean] for c in ("red", "nir"))
    ndvi = np.where(red+nir > 0, (nir-red)/np.maximum(red+nir, 1), np.nan)
    rule = np.asarray(ref.REFINE_RULE)[clean]
    table = variants(np.asarray(ref.BASE_CLASS)[clean], np.asarray(ref.classification)[clean], rule, ndvi, args.ndvi)
    rows = []
    for unit in answers:
        for part, (label, low, high) in enumerate(tr.answer_parts(unit, unit)):
            human = fc.LABEL_FAMILIES.get(label)
            if human is None:
                continue
            hit = (np.hypot(x-unit["X"], y-unit["Y"]) <= unit["PATCH_R_M"]) & (z >= low) & (z <= high)
            if hit.sum() < fc.MIN_PATCH_POINTS:
                continue
            row = {"UNIT_ID": unit["UNIT_ID"], "PART": ("above", "below")[part] if unit.get("SPLIT_Z") is not None else "",
                   "LABEL": label, "POINTS": int(hit.sum()), "RULE11_POINTS": int((rule[hit] == 11).sum()),
                   "NDVI_MEDIAN": float(np.nanmedian(ndvi[hit])) if np.isfinite(ndvi[hit]).any() else None}
            for name, classes in table.items():
                family, _ = lcr.patch_family(classes[hit])
                row[name] = family == human
            rows.append(row)
    summary = {}
    for label in sorted({r["LABEL"] for r in rows}):
        sel = [r for r in rows if r["LABEL"] == label]
        summary[label] = {"parts": len(sel), **{name: sum(r[name] for r in sel) for name in table}}
    summary["TOTAL"] = {"parts": len(rows), **{name: sum(r[name] for r in rows) for name in table}}
    report = {"tile": args.tile, "labels": str(args.labels), "answers": len(answers),
              "split_answers": sum(u.get("SPLIT_Z") is not None for u in answers), "ndvi_threshold": args.ndvi,
              "summary": summary,
              "interpretation": "Training-patch diagnostic on one tile's labels; not evaluation or an accuracy estimate.",
              "parts": rows}
    args.out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"{report['answers']} answers ({report['split_answers']} split), {len(rows)} comparable parts, NDVI threshold {args.ndvi}")
    names = list(table)
    print(f"{'label':15s} {'parts':>5s} " + " ".join(f"{n:>13s}" for n in names))
    for label, s in summary.items():
        print(f"{label:15s} {s['parts']:5d} " + " ".join(f"{s[n]:13d}" for n in names))


if __name__ == "__main__":
    main()
