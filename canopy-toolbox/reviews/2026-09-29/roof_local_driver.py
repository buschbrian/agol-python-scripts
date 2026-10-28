r"""Local roof-surface refinement pilot: refine-roofs --method local, run, compare, per tile.

Run with ArcGIS Pro Python from canopy-toolbox:
    python reviews/2026-09-29/roof_local_driver.py [refine] [run] [compare] [--tiles T1 T2 ...]
With no step names, all three run. Outputs go ONLY under ROOT\roof-local\<tile>\; the baseline
prepared\ and run\ folders are read, never written. Each step's wall-clock and peak resident
memory (the process and its children, sampled every 2 s) are appended to roof-local\timings.csv.
Preparation requires a complete manifest; existing runs use signature-checked resume.
"""
import argparse, csv, datetime, json, os, subprocess, sys, time
from pathlib import Path

import psutil

PY = sys.executable
TOOLBOX = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLBOX))
from canopy.run_safeguards import completed_preparation, run_resume_args
from canopy.lidar_root import lidar_root  # noqa: E402
ROOT = lidar_root() / "2023-salt-lake-valley" / "runs" / "pilot-2026-09-29"
OUT = ROOT / "roof-local"
EXTENTS = {"12TVL2804": (428000, 4504000, 429000, 4505000),
           "12TVL3302": (433000, 4502000, 434000, 4503000),
           "12TVL2203": (422000, 4503000, 423000, 4504000)}
REFINE_OPTIONS = []  # defaults: --radius 1 --neighbors 16 --min-neighbors 6 --min-votes 3 --below-roof .35 --above-roof .5


def step(tile, name, command, out):
    logs = OUT / "logs"; logs.mkdir(parents=True, exist_ok=True)
    scratch = OUT / "scratch" / f"{tile}-{name}"; scratch.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TEMP=str(scratch), TMP=str(scratch))
    start = datetime.datetime.now(); t0 = time.time(); peak = 0
    with open(logs / f"{tile}-{name}.log", "w", encoding="utf-8") as log:
        proc = subprocess.Popen(command, cwd=TOOLBOX, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            ps = psutil.Process(proc.pid)
        except psutil.NoSuchProcess:
            ps = None
        while proc.poll() is None:
            try:
                peak = max(peak, ps.memory_info().rss + sum(c.memory_info().rss for c in ps.children(recursive=True))) if ps else peak
            except psutil.Error:
                pass
            time.sleep(2)
    row = {"tile": tile, "step": name, "status": "ok" if proc.returncode == 0 else f"exit {proc.returncode}",
           "start": start.isoformat(timespec="seconds"), "minutes": round((time.time() - t0) / 60, 2),
           "peak_rss_gb": round(peak / 1e9, 2), "output": str(out)}
    path = OUT / "timings.csv"; new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row)); new and w.writeheader(); w.writerow(row)
    print(json.dumps(row), flush=True)
    return proc.returncode == 0


def main():
    global ROOT, OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("steps", nargs="*", default=["refine", "run", "compare"])
    parser.add_argument("--tiles", nargs="+", default=list(EXTENTS))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    ROOT, OUT = args.root, args.out or args.root / "roof-local"
    invalid = set(args.steps) - {"refine", "run", "compare"}
    if invalid:
        parser.error(f"Unknown steps: {sorted(invalid)}")
    failed = False
    for tile in args.tiles:
        refined, run = OUT / tile / "refined", OUT / tile / "run"
        if "refine" in args.steps and not completed_preparation(refined):
            if not step(tile, "refine", [PY, "-m", "canopy", "refine-roofs", str(ROOT / tile / "prepared" / "prepared.lasd"),
                                         str(refined), "--method", "local", *REFINE_OPTIONS], refined):
                failed = True
                continue
        if "run" in args.steps:
            if not completed_preparation(refined):
                raise ValueError(f"Refined preparation is absent: {refined}")
            if not step(tile, "run", [PY, "-m", "canopy", "run", str(refined / "prepared.lasd"), str(run),
                                      "--extent", *map(str, EXTENTS[tile]), *run_resume_args(run)], run):
                failed = True
                continue
        report = OUT / tile / "comparison.json"
        if "compare" in args.steps:
            if not step(tile, "compare", [PY, str(TOOLBOX / "reviews" / "2026-09-29" / "compare_runs.py"),
                                   str(ROOT / tile / "run"), str(run), str(report)], report):
                failed = True
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
