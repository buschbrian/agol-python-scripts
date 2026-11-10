"""Score FRACTAL predictions against the held-out training labels: the released model against a fine-tuned one.

    python reviews/2026-10-20/fractal-finetune/evaluate_finetune.py LABELS.las NAME=PREDICTION.las [NAME=PREDICTION.las ...] [--out FILE.json]

Run with the Myria3D environment's Python (PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT set). Read-only on every input.
LABELS.las is val/12TVL2804.las from make_training_las.py: held-out labels as FRACTAL classes, 250 unlabelled, 65 noise.
Each PREDICTION.las is a FRACTAL output over the same points in the same order (checked on X, Y and Z): a consensus.las from
repeat.py (MajorityClassification, 0 = tie) or one pass (PredictedClassification).

Two scores, both on the held-out side only:
- points: share of labelled points whose predicted class is the label, overall and per class, with the confusion table;
- parts: one vote per labelled part (a unit, or one side of a split or one refined layer), the plurality class of its points
  against its label. Points in a patch are not independent, so the part score is the one to quote; the paired table (right in
  both, only in one) and an exact two-sided sign test on the discordant parts say whether two predictions differ.
These units were labelled where the reviewer chose to look, partly from model-disagreement queues, so the scores compare
models on the same hard sample; they are not an accuracy estimate for the city.
"""
import argparse
import json
import math
from pathlib import Path
import sys

import numpy as np
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import make_training_las as mtl  # noqa: E402
from canopy import las_records  # noqa: E402

UNLABELLED = (mtl.IGNORE, mtl.DROP)
CHUNK = 2_000_000


def labelled_points(path):
    """Indices, coordinates and labels of the labelled points of a make_training_las output."""
    block, scale, offset, *_ = las_records.records(path)
    classes = np.asarray(block["classification"])
    index = np.flatnonzero(~np.isin(classes, UNLABELLED))
    xyz = np.column_stack([np.asarray(block[a])[index]*scale[i]+offset[i] for i, a in enumerate("xyz")])
    return index, xyz, classes[index]


def predicted_at(path, index, xyz):
    """The predicted class at the given point indices, after checking the points are the same points."""
    import laspy
    with laspy.open(path) as reader:
        names = set(reader.header.point_format.dimension_names)
        dimension = "MajorityClassification" if "MajorityClassification" in names else "PredictedClassification"
        if dimension not in names:
            raise ValueError(f"{path} has no FRACTAL prediction")
        out = np.zeros(len(index), np.uint8)
        start = 0
        for chunk in reader.chunk_iterator(CHUNK):
            stop = start + len(chunk)
            take = (index >= start) & (index < stop)
            local = index[take] - start
            here = np.c_[np.asarray(chunk.x)[local], np.asarray(chunk.y)[local], np.asarray(chunk.z)[local]]
            if not np.allclose(here, xyz[take], atol=1e-3):
                raise ValueError(f"{path} does not hold the labelled points in the same order")
            out[take] = np.asarray(chunk[dimension])[local]
            start = stop
        if start <= index.max():
            raise ValueError(f"{path} has fewer points than the labels")
    return out, dimension


def held_out_centres(labels_path):
    """Centres of the held-out units: holdout_units.json beside val/ when make_training_las wrote one, else run-1's split."""
    listed = Path(labels_path).resolve().parent.parent/"holdout_units.json"
    if listed.is_file():
        return sorted({(u["X"], u["Y"]) for u in json.loads(listed.read_text(encoding="utf-8"))})
    units, _, split = mtl.load_units()
    return sorted({(u["X"], u["Y"]) for u in units if split[u["UNIT_ID"]] == "VALIDATION"})


def parts(xyz, labels, centres):
    """A part id per labelled point: the nearest held-out unit centre and the point's label."""
    _, nearest = cKDTree(np.array(centres)).query(xyz[:, :2])
    keys = nearest.astype(np.int64)*256 + labels
    _, part = np.unique(keys, return_inverse=True)
    return part


def plurality(values, part):
    """The most frequent value in each part (ties to the lower code)."""
    n = part.max()+1
    codes = np.unique(values)
    counts = np.zeros((n, len(codes)), np.int64)
    np.add.at(counts, (part, np.searchsorted(codes, values)), 1)
    return codes[counts.argmax(axis=1)]


def sign_test(b, c):
    """Exact two-sided binomial test of b against c discordant pairs."""
    n = b + c
    if not n:
        return 1.0
    k = min(b, c)
    return min(1.0, 2*sum(math.comb(n, i) for i in range(k+1))/2**n)


def score(labels, predicted, part, part_label):
    right = predicted == labels
    classes = sorted(set(labels.tolist()))
    confusion = {int(a): {int(b): int(((labels == a) & (predicted == b)).sum()) for b in np.unique(predicted)} for a in classes}
    part_right = plurality(predicted, part) == part_label
    return {"points": {"labelled": int(len(labels)), "agree": int(right.sum()), "share": round(float(right.mean()), 4),
                       "by_class": {int(a): f"{int(right[labels == a].sum())} of {int((labels == a).sum())}" for a in classes},
                       "confusion_label_to_predicted": confusion},
            "parts": {"count": int(len(part_label)), "agree": int(part_right.sum()),
                      "share": round(float(part_right.mean()), 4),
                      "by_class": {int(a): f"{int(part_right[part_label == a].sum())} of {int((part_label == a).sum())}"
                                   for a in classes}}}, part_right


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("labels", type=Path)
    parser.add_argument("predictions", nargs="+", help="NAME=PATH")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if args.out and args.out.exists():
        raise FileExistsError(args.out)
    index, xyz, labels = labelled_points(args.labels)
    part = parts(xyz, labels, held_out_centres(args.labels))
    part_label = plurality(labels, part)
    report = {"labels": str(args.labels), "classes": "FRACTAL codes: 1 other, 2 ground, 5 vegetation, 6 building, 64 structure",
              "predictions": {}, "paired_parts": {}}
    rights = {}
    for item in args.predictions:
        name, _, path = item.partition("=")
        predicted, dimension = predicted_at(Path(path), index, xyz)
        result, rights[name] = score(labels, predicted, part, part_label)
        report["predictions"][name] = {"path": path, "dimension": dimension, **result}
    names = list(rights)
    for i, a in enumerate(names):
        for b in names[i+1:]:
            only_a, only_b = int((rights[a] & ~rights[b]).sum()), int((rights[b] & ~rights[a]).sum())
            report["paired_parts"][f"{a} vs {b}"] = {"both": int((rights[a] & rights[b]).sum()), f"only {a}": only_a,
                                                     f"only {b}": only_b, "neither": int((~rights[a] & ~rights[b]).sum()),
                                                     "sign_test_p": round(sign_test(only_a, only_b), 4)}
    text = json.dumps(report, indent=1)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    brief = {n: {"points": r["points"]["share"], "parts": f'{r["parts"]["agree"]} of {r["parts"]["count"]}',
                 "parts_by_class": r["parts"]["by_class"]} for n, r in report["predictions"].items()}
    print(json.dumps({"predictions": brief, "paired_parts": report["paired_parts"]}, indent=1))


if __name__ == "__main__":
    main()
