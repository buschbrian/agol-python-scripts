"""Sequential pilot: prepare + run for each tile, recording wall-clock, peak memory, and output size.

Run with ArcGIS Pro Python. One CSV row per step per tile in pilot-timings.csv; stdout/stderr per step in logs/.
Re-running skips steps whose output folder already exists (prepare refuses existing folders anyway).
"""
import csv, datetime, json, os, subprocess, sys, time
from pathlib import Path
import psutil

PY = r"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
TOOLBOX = Path(r"V:\Developer\agol-python-scripts\canopy-toolbox")
LAS = Path(r"D:\lidar\2023-salt-lake-valley\las")
ROOT = Path(__file__).resolve().parent
INVENTORY = ROOT / "las-inventory.json"
BUFFER = 50.0  # metres of neighbour context for prepare; run's halo is 15 m
TILES = sys.argv[1:] or ["12TVL2804", "12TVL3302", "12TVL2203"]

def dir_bytes(p):
    return sum(f.stat().st_size for f in Path(p).rglob("*") if f.is_file()) if Path(p).exists() else 0

def step(tile, name, args, out):
    logs = ROOT / "logs"; logs.mkdir(exist_ok=True)
    scratch = ROOT / "scratch" / f"{tile}-{name}"; scratch.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TEMP=str(scratch), TMP=str(scratch))
    start = datetime.datetime.now(); t0 = time.time(); peak = 0
    with open(logs / f"{tile}-{name}.log", "w", encoding="utf-8") as log:
        proc = subprocess.Popen([PY, "-m", "canopy", *args], cwd=TOOLBOX, env=env, stdout=log, stderr=subprocess.STDOUT)
        ps = psutil.Process(proc.pid)
        while proc.poll() is None:
            try:
                rss = ps.memory_info().rss + sum(c.memory_info().rss for c in ps.children(recursive=True))
                peak = max(peak, rss)
            except psutil.Error:
                pass
            time.sleep(2)
    secs = time.time() - t0
    row = {"tile": tile, "step": name, "status": "ok" if proc.returncode == 0 else f"exit {proc.returncode}",
           "start": start.isoformat(timespec="seconds"), "minutes": round(secs / 60, 2),
           "peak_rss_gb": round(peak / 1e9, 2), "output_gb": round(dir_bytes(out) / 1e9, 2),
           "scratch_gb": round(dir_bytes(scratch) / 1e9, 2), "free_ram_gb_after": round(psutil.virtual_memory().available / 1e9, 1)}
    path = ROOT / "pilot-timings.csv"; new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row)); new and w.writeheader(); w.writerow(row)
    print(json.dumps(row), flush=True)
    return proc.returncode == 0

extents = {Path(f["path"]).stem: f["extent"] for f in json.loads(INVENTORY.read_text())["files"]}
for tile in TILES:
    xmin, ymin, xmax, ymax = extents[tile]
    xmax, ymax = round(xmax), round(ymax)  # header max is the last point (e.g. 422999.99); the tile edge is the km line
    prepared = ROOT / tile / "prepared"; run = ROOT / tile / "run"
    if not prepared.exists():
        buf = [xmin - BUFFER, ymin - BUFFER, xmax + BUFFER, ymax + BUFFER]
        if not step(tile, "prepare", ["prepare", str(LAS), str(prepared), "--extent", *map(str, buf)], prepared):
            continue
    if not run.exists():
        step(tile, "run", ["run", str(prepared / "prepared.lasd"), str(run), "--extent", *map(str, [xmin, ymin, xmax, ymax])], run)
