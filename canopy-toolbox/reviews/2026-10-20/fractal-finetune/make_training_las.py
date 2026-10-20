"""Write the FRACTAL fine-tuning inputs from the training labels: one training and one validation LAS of 12TVL2804.

    python reviews/2026-10-20/fractal-finetune/make_training_las.py NEW_DIR

Run with the Myria3D environment's Python (PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT set). Read-only on every input; writes a new folder.
Inputs: the two label snapshots of October 20 (original packet and refined cylinders, re-verified by training_review.load_snapshot),
the colourised 12TVL2804 copy that FRACTAL reads (NAIP 2024 colour, point format 8) and the October 8 working LAS of the same
points (only to find noise, 7 and 18).

1. training_review.export_training_las codes every labelled patch point with its label's LAS code (splits and stacked refined
   layers included) and every other point 250, on a copy of the colourised file.
2. Labels become FRACTAL classes (LABEL_TO_FRACTAL below); WALL is left unlabelled (250) because our walls mix building facades,
   which FRACTAL calls building, with garden walls and fences, which it calls permanent structure. Noise becomes 65, which
   Myria3D drops. 250 stays in the cloud as context and must be ignored by the loss (see the Myria3D patch).
3. Spatial hold-out: training_review.point_split puts each labelled unit's 50 m block in TRAINING or VALIDATION (20% of blocks,
   fixed seed). train/12TVL2804.las keeps only training-block labels and val/12TVL2804.las only validation-block labels; the other
   blocks' labelled points become 250 in each, so no label is seen by both. Both files keep every point, so context is never cut.
Writes split.csv (Myria3D format), mapping.json and summary.json beside the two LAS files.
"""
import argparse
import json
from pathlib import Path
import shutil
import sys

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
from canopy import las_records, training_review as tr  # noqa: E402
from canopy.lidar_root import lidar_root  # noqa: E402

LIDAR = lidar_root()/"2023-salt-lake-valley"
REVIEW = LIDAR/"runs"/"pilot-2026-09-29"/"training-review"
SNAPSHOTS = [(REVIEW/"packet-20260929", REVIEW/"snapshots"/"packet-20260929-20261020"),
             (REVIEW/"packet-20261020-refined", REVIEW/"snapshots"/"packet-20261020-refined-20261020")]
COLOURISED = LIDAR/"fractal"/"city-20261019"/"colorized"/"12TVL2804.las"
WORKING = LIDAR/"runs"/"city-count-20261008"/"prepared"/"points"/"12TVL2804.las"
TILE = "12TVL2804"
IGNORE = tr.IGNORE_CODE                       # 250: kept as context, ignored by the loss
DROP = 65                                     # Myria3D's artefact code: dropped before the model sees the block
LABEL_TO_FRACTAL = {"TREE": 5, "SHRUB_LOW_VEG": 5, "BUILDING_ROOF": 6, "GROUND": 2, "WATER": 9, "POLE": 64,
                    "OTHER_STRUCTURE": 64, "VEHICLE": 1, "WIRE": 1, "WALL": IGNORE}


def code_map():
    """LAS training code (training_review.LABELS) -> FRACTAL class, for every exported label."""
    return {tr.LABELS[label][1]: fractal for label, fractal in LABEL_TO_FRACTAL.items()}


def remap(classes, mapping, noise):
    """FRACTAL classes for one block of exported codes; 250 stays 250, noise becomes 65."""
    out = np.full(len(classes), IGNORE, np.uint8)
    for code, target in mapping.items():
        out[classes == code] = target
    out[noise] = DROP
    return out


def load_units():
    """The exportable labelled units of both snapshots, the shared evaluation frame and the 50 m block hold-out split."""
    units, frame = [], None
    for packet, snapshot in SNAPSHOTS:
        document = json.loads((packet/"packet.json").read_text(encoding="utf-8"))
        rows = tr.load_snapshot(snapshot, document)
        frame = frame or document["frame"]
        if document["frame"]["digest"] != frame["digest"]:
            raise ValueError("The two packets use different evaluation frames")
        units += [r for r in rows if r["LABEL"] in tr.EXPORT_LABELS]
    if tr.overlapping_patches(units):
        raise ValueError("Labelled patches from the two packets overlap")
    split, _ = tr.point_split(units)
    return units, frame, split


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path)
    args = parser.parse_args(argv)
    if args.out.exists():
        raise FileExistsError(args.out)
    units, frame, split = load_units()
    args.out.mkdir(parents=True)
    work = args.out/"work"
    work.mkdir()
    coded = work/f"{TILE}_coded.las"
    counts = tr.export_training_las(COLOURISED, coded, units, frame)
    tr.verify_only_classes_changed(COLOURISED, coded)
    mapping = code_map()
    centres = {(u["X"], u["Y"]): split[u["UNIT_ID"]] for u in units}
    block, scale, offset, modern, info = las_records.records(coded)
    exported = np.asarray(block["classification"])
    working, *_ = las_records.records(WORKING)
    if len(working) != len(block):
        raise ValueError("Working LAS and colourised copy differ in point count")
    noise = np.isin(np.asarray(working["classification"]), tr.NOISE_CODES)
    fractal = remap(exported, mapping, noise)
    # Which hold-out side each labelled point belongs to: the block of the nearest labelled centre.
    x = block["x"]*scale[0]+offset[0]
    y = block["y"]*scale[1]+offset[1]
    labelled = np.flatnonzero((exported != IGNORE) & ~noise)
    from scipy.spatial import cKDTree
    keys = list(centres)
    _, nearest = cKDTree(np.array(keys)).query(np.c_[x[labelled], y[labelled]])
    side = np.array([centres[keys[k]] for k in nearest])
    summary = {"units": len(units), "unit_split": {s: sum(v == s for v in split.values()) for s in ("TRAINING", "VALIDATION")},
               "export_counts": counts, "mapping": {k: v for k, v in LABEL_TO_FRACTAL.items()}, "files": {}}
    for name, keep in (("train", "TRAINING"), ("val", "VALIDATION")):
        target = args.out/name/f"{TILE}.las"
        target.parent.mkdir()
        shutil.copyfile(coded, target)
        out, *_ = las_records.records(target, "r+")
        classes = fractal.copy()
        classes[labelled[side != keep]] = IGNORE
        out["classification"] = classes
        if isinstance(out, np.memmap):
            out.flush()
        del out
        values, n = np.unique(classes, return_counts=True)
        summary["files"][name] = {str(int(v)): int(c) for v, c in zip(values, n)}
    import gc
    gc.collect()
    (args.out/"split.csv").write_text(f"basename,split\n{TILE}.las,train\n{TILE}.las,val\n", encoding="utf-8")
    (args.out/"mapping.json").write_text(json.dumps({"label_to_fractal": LABEL_TO_FRACTAL, "ignore": IGNORE, "drop": DROP},
                                                    indent=1), encoding="utf-8")
    (args.out/"summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("units", "unit_split", "files")}, indent=1))


if __name__ == "__main__":
    main()
