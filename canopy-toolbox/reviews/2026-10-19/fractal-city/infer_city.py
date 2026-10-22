"""Run FRACTAL three times on every colourised Millcreek tile and keep the consensus. Resumable; one fresh process per tile.

    python reviews/2026-10-19/fractal-city/infer_city.py [--tiles 12TVL2804 ...] [--repeats 3] [--batch 10]

Run with the Myria3D environment's Python (PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT set; city_fractal.bat does both). Each tile goes
through ../../2026-09-30/fractal/repeat.py, which checks the input, runs the passes on the GPU, refuses any output whose points
moved or whose source changed, and writes `consensus.las`. Outputs: `fractal/city-20261019/fractal/<tile>/`.
- A tile whose manifest says complete is skipped. A failed or interrupted tile folder is renamed `<tile>.failed-<time>` (kept for
  diagnosis) and the tile is retried once at the end of the pass.
- While prepare_city.py is still writing colourised copies, tiles not yet ready are waited for, not skipped.
- The process asks Windows not to idle-sleep while it runs (SetThreadExecutionState, released when it exits); no setting changes.
- Before each tile it waits (up to 10 minutes) for at least 6 GB of commit headroom: on October 19 passes crashed with access
  violations while the machine's committed memory sat at its limit, and a pass needs about 4.5 GB plus its GPU spill.
  A crashed pass is rerun up to twice on its own (repeat.py --pass-retries); a tile is tried up to three times.
- A tile whose passes disagree unevenly (pairwise agreements more than 2 points apart) is rejected and rerun: on October 19
  one pass of 12TVL2702 agreed with the other two on 51% of points while they agreed on 98%, although every point-order and
  source check passed. Healthy tiles show pairs within 0.2 points of each other.
Model output is an opinion: nothing here changes the working LAS, labels or any GIS layer.
"""
import argparse
import ctypes
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
from canopy.lidar_root import lidar_root  # noqa: E402

LIDAR = lidar_root()/"2023-salt-lake-valley"
WORK = LIDAR/"runs"/"city-count-20261008"/"prepared"/"points"
RUN = LIDAR/"fractal"/"city-20261019"
REPEAT = TOOLBOX/"reviews"/"2026-09-30"/"fractal"/"repeat.py"
ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
POLL_SECONDS = 60
MIN_COMMIT_GB = 6.0
COMMIT_WAIT_SECONDS = 600
MAX_ATTEMPTS = 3
PASS_RETRIES = 2
MAX_PAIR_SPREAD = 0.02               # largest allowed gap between the best and worst pairwise pass agreement                     # a crashed pass is rerun on its own before the tile counts as failed


class MemoryStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong), ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def commit_headroom_gb():
    """Commit charge still available (RAM plus page file) in GB; None where it cannot be read."""
    if os.name != "nt":
        return None
    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(MemoryStatus)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return status.ullAvailPageFile/2**30


def wait_for_headroom(log):
    started = time.time()
    while True:
        free = commit_headroom_gb()
        if free is None or free >= MIN_COMMIT_GB:
            return free
        if time.time()-started > COMMIT_WAIT_SECONDS:
            log(f"only {free:.1f} GB commit headroom after {COMMIT_WAIT_SECONDS//60} min of waiting; starting anyway")
            return free
        log(f"waiting: {free:.1f} GB commit headroom, need {MIN_COMMIT_GB:.0f} GB")
        time.sleep(POLL_SECONDS)


def pass_spread(folder):
    """Gap between the highest and lowest pairwise agreement of a completed tile's passes."""
    pairs = [p["agreement"] for p in json.loads((folder/"manifest.json").read_text(encoding="utf-8"))["consensus"]["pairwise"]]
    return max(pairs)-min(pairs)


def complete(folder):
    manifest = folder/"manifest.json"
    if not manifest.exists():
        return False
    status = json.loads(manifest.read_text(encoding="utf-8")).get("status", "")
    return status.startswith("complete") and (folder/"consensus.las").exists()


def prepare_finished(stale_seconds=1800):
    """Preparation has ended, or its manifest has not been touched for 30 minutes (a crashed run never says so)."""
    path = RUN/"prepare.json"
    if not path.exists():
        return False
    if json.loads(path.read_text(encoding="utf-8")).get("status") in ("complete", "partial"):
        return True
    return time.time()-path.stat().st_mtime > stale_seconds


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tiles", nargs="+")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--batch", type=int, default=10)
    args = parser.parse_args(argv)
    if os.name == "nt":
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    tiles = args.tiles or sorted(p.stem for p in WORK.glob("*.las"))
    out_root = RUN/"fractal"
    out_root.mkdir(parents=True, exist_ok=True)
    manifest_path = RUN/"infer.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"tiles": {}}
    manifest.update(status="running", started=time.time(), repeats=args.repeats, batch=args.batch, requested=tiles,
                    python=sys.executable)

    def save():
        manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    def log(text):
        print(f"{datetime.datetime.now():%H:%M:%S} {text}", flush=True)

    save()
    env = dict(os.environ, PYTHONNOUSERSITE="1")
    attempts = {t: 0 for t in tiles}
    pending = list(tiles)
    while pending:
        progressed = False
        for tile in list(pending):
            folder = out_root/tile
            if complete(folder):
                if pass_spread(folder) <= MAX_PAIR_SPREAD:
                    pending.remove(tile)
                    manifest["tiles"].setdefault(tile, {"status": "complete (earlier run)"})
                    continue
                log(f"{tile}: earlier result has inconsistent passes (spread {pass_spread(folder):.3f}); rerunning")
                folder.rename(folder.with_name(f"{tile}.inconsistent-{int(time.time())}"))
            source = RUN/"colorized"/f"{tile}.las"
            if not source.with_suffix(".json").exists():
                if prepare_finished():
                    log(f"{tile}: no colourised input and preparation has finished; skipped")
                    manifest["tiles"][tile] = {"status": "no input"}
                    pending.remove(tile)
                    save()
                continue
            if attempts[tile] >= MAX_ATTEMPTS:
                pending.remove(tile)
                continue
            if folder.exists():
                folder.rename(folder.with_name(f"{tile}.failed-{int(time.time())}"))
            attempts[tile] += 1
            headroom = wait_for_headroom(log)
            started = time.time()
            log(f"{tile}: FRACTAL x{args.repeats} (attempt {attempts[tile]}, "
                f"{'?' if headroom is None else f'{headroom:.1f}'} GB commit headroom)")
            with open(out_root/f"{tile}.log", "a", encoding="utf-8") as handle:
                result = subprocess.run([sys.executable, str(REPEAT), str(source), str(folder),
                                         "--repeats", str(args.repeats), "--batch", str(args.batch),
                                         "--pass-retries", str(PASS_RETRIES)],
                                        cwd=str(REPEAT.parent), env=env, stdout=handle, stderr=subprocess.STDOUT)
            seconds = round(time.time()-started, 1)
            progressed = True
            if result.returncode == 0 and complete(folder) and pass_spread(folder) > MAX_PAIR_SPREAD:
                spread = pass_spread(folder)
                folder.rename(folder.with_name(f"{tile}.inconsistent-{int(time.time())}"))
                manifest["tiles"][tile] = {"status": "failed (inconsistent passes)", "spread": spread, "seconds": seconds,
                                           "attempts": attempts[tile]}
                log(f"{tile}: FAILED (inconsistent passes, pairwise spread {spread:.3f}) after {seconds:.0f} s"
                    + ("; will retry" if attempts[tile] < MAX_ATTEMPTS else "; no attempts left"))
            elif result.returncode == 0 and complete(folder):
                tile_manifest = json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
                summary = tile_manifest["consensus"]
                manifest["tiles"][tile] = {"status": "complete", "seconds": seconds, "attempts": attempts[tile],
                                           "points": summary["points"],
                                           "unanimous_share": summary["unanimous_points"]/summary["points"],
                                           "tie_points": summary["tie_points"],
                                           "pairwise": [p["agreement"] for p in summary["pairwise"]]}
                pending.remove(tile)
                log(f"{tile}: done in {seconds:.0f} s, {summary['points']:,} points, "
                    f"unanimous {100*summary['unanimous_points']/summary['points']:.2f}%")
            else:
                manifest["tiles"][tile] = {"status": f"failed (exit {result.returncode})", "seconds": seconds,
                                           "attempts": attempts[tile], "log": str(out_root/f"{tile}.log")}
                log(f"{tile}: FAILED (exit {result.returncode}) after {seconds:.0f} s"
                    + ("; will retry" if attempts[tile] < MAX_ATTEMPTS else "; no attempts left"))
            save()
        if pending and not progressed:
            if prepare_finished() and all(attempts[t] >= MAX_ATTEMPTS for t in pending
                                          if (RUN/"colorized"/f"{t}.json").exists()):
                break
            time.sleep(POLL_SECONDS)
    failed = [t for t, r in manifest["tiles"].items() if not r["status"].startswith("complete")]
    manifest.update(status="complete" if not failed else f"finished with {len(failed)} tiles not complete",
                    not_complete=failed, finished=time.time())
    save()
    log(manifest["status"])


if __name__ == "__main__":
    main()
