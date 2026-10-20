"""Run Esri's pretrained building point-classification model on every Millcreek tile, on copies, after the FRACTAL run.

    python reviews/2026-10-20/esri-city/building_city.py [--tiles 12TVL2804 ...] [--batch 8] [--no-wait]

Run with the ArcGIS Pro deep-learning environment's Python (arcgispro-py3-dl; PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT set).
A third, independent opinion on buildings beside the October 8 native classes and FRACTAL. For each tile it copies the October 8
working LAS to runs/esri-building-20261020/<tile>/building/<tile>.las, runs ../../2026-09-29/dl_run.py building on that copy
(the runner checks the copy against the source, isolates the runtime and records a manifest), then checks with
training_review.verify_only_classes_changed that every byte except classification is unchanged. The working LAS are never written.
- It waits for the citywide FRACTAL inference to finish so the two jobs never share the GPU (unless --no-wait).
- 12TVL2804 goes first. With a batch above 1 it is compared byte for byte with the September 29 batch-1 output of the same
  model on the same points; if they differ the run stops, because batch size would then change the result.
- Completed tiles are skipped; a failed tile folder is renamed <tile>.failed-<time> and the tile is tried twice in all.
- The process asks Windows not to idle-sleep while it runs. Model output is an opinion, not a label.
"""
import argparse
import ctypes
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
from canopy import las_records, training_review as tr  # noqa: E402
from canopy.lidar_root import lidar_root  # noqa: E402

LIDAR = lidar_root()/"2023-salt-lake-valley"
WORK = LIDAR/"runs"/"city-count-20261008"/"prepared"/"points"
OUT = LIDAR/"runs"/"esri-building-20261020"
FRACTAL_MANIFEST = LIDAR/"fractal"/"city-20261019"/"infer.json"
REFERENCE = LIDAR/"runs"/"pilot-2026-09-29"/"deep-learning"/"12TVL2804"/"building"/"12TVL2804.las"
DL_RUN = TOOLBOX/"reviews"/"2026-09-29"/"dl_run.py"
FIRST = "12TVL2804"
LABEL = "citywide second opinion (Esri building model), October 20, 2026; model output, not labels"


def manifest_status(root):
    path = root/"work"/"run-building.json"
    return json.loads(path.read_text(encoding="utf-8")).get("status") if path.exists() else None


def classes(path):
    block, *_ = las_records.records(path)
    return np.asarray(block["classification"])


def same_as_reference(output, log):
    """True when the new output's classes equal the September 29 batch-1 output wherever neither is noise."""
    if not REFERENCE.exists():
        log(f"no September 29 reference at {REFERENCE}; batch size cannot be checked")
        return None
    new, old = classes(output), classes(REFERENCE)
    if len(new) != len(old):
        log("reference has a different point count; batch size cannot be checked")
        return None
    keep = ~np.isin(old, (7, 18)) & ~np.isin(new, (7, 18))
    differ = int((new[keep] != old[keep]).sum())
    log(f"{FIRST}: {differ:,} of {int(keep.sum()):,} non-noise points differ from the September 29 batch-1 output")
    return differ == 0


def run_tile(tile, batch, log):
    root = OUT/tile
    if manifest_status(root) == "complete" and (root/"integrity.json").exists():
        return "complete (earlier run)"
    if root.exists():
        root.rename(root.with_name(f"{tile}.failed-{int(time.time())}"))
    source, copy = WORK/f"{tile}.las", root/"building"/f"{tile}.las"
    copy.parent.mkdir(parents=True)
    shutil.copyfile(source, copy)
    started = time.time()
    env = dict(os.environ, PYTHONNOUSERSITE="1")
    with open(root/"dl_run.log", "w", encoding="utf-8") as handle:
        result = subprocess.run([sys.executable, str(DL_RUN), "building", "--source", str(source), "--copy", str(copy),
                                 "--output-root", str(root), "--batch", str(batch), "--label", LABEL],
                                env=env, stdout=handle, stderr=subprocess.STDOUT)
    seconds = round(time.time()-started)
    if result.returncode or manifest_status(root) != "complete":
        log(f"{tile}: FAILED (exit {result.returncode}, manifest {manifest_status(root)}) after {seconds} s; see {root/'dl_run.log'}")
        return "failed"
    integrity = tr.verify_only_classes_changed(source, copy)
    counts = np.unique(classes(copy), return_counts=True)
    record = {"tile": tile, "batch": batch, "seconds": seconds, "integrity": integrity,
              "classes": {str(int(k)): int(v) for k, v in zip(*counts)}}
    (root/"integrity.json").write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
    log(f"{tile}: done in {seconds} s; classes {record['classes']}")
    return "complete"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tiles", nargs="+")
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--no-wait", action="store_true")
    args = parser.parse_args(argv)
    if os.name == "nt":
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)

    def log(text):
        print(f"{datetime.datetime.now():%H:%M:%S} {text}", flush=True)

    while not args.no_wait:
        status = json.loads(FRACTAL_MANIFEST.read_text(encoding="utf-8")).get("status", "") if FRACTAL_MANIFEST.exists() else ""
        if status and not status.startswith("running"):
            break
        time.sleep(120)
    tiles = args.tiles or sorted(p.stem for p in WORK.glob("*.las"))
    if FIRST in tiles:
        tiles = [FIRST] + [t for t in tiles if t != FIRST]
    OUT.mkdir(parents=True, exist_ok=True)
    log(f"Esri building model on {len(tiles)} tiles, batch {args.batch}")
    attempts = {}
    pending = list(tiles)
    while pending:
        tile = pending.pop(0)
        attempts[tile] = attempts.get(tile, 0)+1
        status = run_tile(tile, args.batch, log)
        if status == "failed" and attempts[tile] < 2:
            pending.append(tile)
        if tile == FIRST and status == "complete" and args.batch > 1:
            same = same_as_reference(OUT/FIRST/"building"/f"{FIRST}.las", log)
            if same is False:
                log("batch size changes the building model's result; stopping. Rerun with --batch 1.")
                return 2
    failed = [t for t in tiles if run_status(t) != "complete"]
    log(f"finished; {len(tiles)-len(failed)} complete, failed: {failed}")
    return 0 if not failed else 1


def run_status(tile):
    root = OUT/tile
    return "complete" if manifest_status(root) == "complete" and (root/"integrity.json").exists() else "not complete"


if __name__ == "__main__":
    sys.exit(main())
