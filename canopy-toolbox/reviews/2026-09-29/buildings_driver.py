"""Run reconcile-buildings on the three pilot tiles, recording wall-clock time and peak memory.

Run with ArcGIS Pro Python after `fetch-footprints` has written buildings\\reference.gdb.
One CSV row per tile in buildings-timings.csv; stdout/stderr per tile in buildings\\logs\\.
Tiles whose output folder already exists are skipped (the command refuses them anyway).
"""
import csv, datetime, json, os, subprocess, sys, time
from pathlib import Path
import psutil

PY = r"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
TOOLBOX = Path(__file__).resolve().parents[2]
ROOT = Path(r"H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29")
OUT = ROOT / "buildings"
HERE = Path(__file__).resolve().parent
TILES = {"12TVL2804": (428000, 4504000, 429000, 4505000),
         "12TVL3302": (433000, 4502000, 434000, 4503000),
         "12TVL2203": (422000, 4503000, 423000, 4504000)}

def main(argv=None):
    import argparse
    global ROOT, OUT, PY
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tiles',nargs='*',default=list(TILES),choices=list(TILES))
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--output-root',type=Path)
    parser.add_argument('--python',default=PY)
    args=parser.parse_args(argv)
    ROOT, OUT, PY=args.root,args.output_root or args.root/'buildings',args.python
    OUT.mkdir(parents=True,exist_ok=True)
    for tile in args.tiles:
        output = OUT / tile
        if output.exists():
            manifest=output/'reconcile.json'
            if not manifest.is_file() or json.loads(manifest.read_text()).get('status')!='complete':
                raise ValueError(f'Existing reconciliation is incomplete; choose a new output root: {output}')
            print(f"skip {tile}: completed historical reconciliation exists at {output}")
            continue
        trees = json.loads((ROOT / tile / "run" / "run.json").read_text())["outputs"]["trees_review"]
        args = [PY, "-m", "canopy", "reconcile-buildings", str(ROOT / tile / "prepared" / "prepared.lasd"), str(output),
                "--extent", *map(str, TILES[tile]), "--footprints", str(OUT / "reference.gdb"), "--trees", trees]
        logs = OUT / "logs"; logs.mkdir(parents=True, exist_ok=True)
        start = datetime.datetime.now(); t0 = time.time(); peak = 0
        with open(logs / f"{tile}-reconcile.log", "w", encoding="utf-8") as log:
            proc = subprocess.Popen(args, cwd=TOOLBOX, stdout=log, stderr=subprocess.STDOUT)
            ps = psutil.Process(proc.pid)
            while proc.poll() is None:
                try:
                    peak = max(peak, ps.memory_info().rss + sum(c.memory_info().rss for c in ps.children(recursive=True)))
                except psutil.Error:
                    pass
                time.sleep(1)
        row = {"tile": tile, "step": "reconcile-buildings", "status": "ok" if proc.returncode == 0 else f"exit {proc.returncode}",
               "start": start.isoformat(timespec="seconds"), "minutes": round((time.time() - t0) / 60, 2),
               "peak_rss_gb": round(peak / 1e9, 2)}
        path = OUT / "buildings-timings.csv"; new = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(row)); new and w.writeheader(); w.writerow(row)
        print(json.dumps(row), flush=True)


if __name__ == '__main__':
    main()
