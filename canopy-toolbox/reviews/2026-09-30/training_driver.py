"""CPU phase for the September 30 training tiles: prepare + baseline run, sequentially, below-normal priority.

Run with ArcGIS Pro Python (PYTHONNOUSERSITE=1):
    python reviews/2026-09-30/training_driver.py [TILE ...]
Default tiles: training-tiles.json "draw_order".

Same commands and parameters as the September 29 pilot (reviews/2026-09-29/pilot_driver.py):
  prepare D:\\lidar\\2023-salt-lake-valley\\las ROOT\\TILE\\prepared --extent core+/-50 m   (all defaults)
  run ROOT\\TILE\\prepared\\prepared.lasd ROOT\\TILE\\run --extent core                   (all defaults)
Before each step it waits while another process runs whole-tile canopy CPU work (command-line match).
One CSV row per step in ROOT\\training-timings.csv, logs in ROOT\\logs, and ROOT\\TILE\\cpu-record.json with
parameter comparison against the 12TVL2804 pilot manifests and code provenance.
"""
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import psutil

TOOLBOX = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(TOOLBOX))
from canopy import evaluation_design as ed  # noqa: E402
from canopy.run_safeguards import completed_preparation, run_resume_args  # noqa: E402

PY = r"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
LAS = Path(r"D:\lidar\2023-salt-lake-valley\las")
ROOT = Path(r"H:\lidar\2023-salt-lake-valley\runs\training-2026-09-30")
PILOT = Path(r"H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29")
INVENTORY = PILOT / "las-inventory.json"
SELECTION = Path(__file__).with_name("training-tiles.json")
BUFFER = 50.0
BELOW_NORMAL = 0x00004000
HEAVY = re.compile(r"-m\s+canopy\s+(prepare|run|refine-roofs|shape-gate|hag|planning|index-delivery)\b"
                   r"|(pilot_driver|buildings_driver|roof_local_driver|plot_census_driver|dl_thin|"
                   r"shape_diagnostic|validation_harness)\.py", re.I)


def log(message):
    line = f"{datetime.datetime.now().astimezone().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    with open(ROOT / "driver.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def dir_bytes(p):
    return sum(f.stat().st_size for f in Path(p).rglob("*") if f.is_file()) if Path(p).exists() else 0


def others_heavy():
    mine = {os.getpid()} | {c.pid for c in psutil.Process().children(recursive=True)}
    found = []
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["pid"] in mine or "python" not in (proc.info["name"] or "").lower():
                continue
            cmd = " ".join(proc.info["cmdline"] or [])
            if HEAVY.search(cmd):
                found.append(f"{proc.info['pid']}: {cmd[:240]}")
        except psutil.Error:
            continue
    return found


def wait_for_cpu():
    waited = 0
    while True:
        found = others_heavy()
        if not found:
            return waited
        if waited % 600 == 0:
            log(f"waiting: another whole-tile CPU job is running: {found}")
        time.sleep(60)
        waited += 60


def code_provenance():
    files = sorted((TOOLBOX / "canopy").glob("*.py"))
    digest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=TOOLBOX, capture_output=True, text=True).stdout.strip()
        status = subprocess.run(["git", "status", "--short", "--", "canopy"], cwd=TOOLBOX, capture_output=True,
                                text=True).stdout.splitlines()
    except OSError as exc:
        head, status = f"git unavailable: {exc}", []
    return {"git_head": head, "canopy_status_short": status, "canopy_py_sha256": digest}


def step(tile, name, args, out):
    waited = wait_for_cpu()
    logs = ROOT / "logs"; logs.mkdir(exist_ok=True)
    scratch = ROOT / "scratch" / f"{tile}-{name}"; scratch.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TEMP=str(scratch), TMP=str(scratch), PYTHONNOUSERSITE="1")
    start = datetime.datetime.now().astimezone(); t0 = time.time(); peak = 0
    command = [PY, "-m", "canopy", *args]
    log(f"{tile} {name} start: {' '.join(command)}")
    with open(logs / f"{tile}-{name}.log", "w", encoding="utf-8") as out_log:
        proc = subprocess.Popen(command, cwd=TOOLBOX, env=env, stdout=out_log, stderr=subprocess.STDOUT,
                                creationflags=BELOW_NORMAL)
        try:
            ps = psutil.Process(proc.pid)
        except psutil.NoSuchProcess:
            ps = None
        while proc.poll() is None:
            try:
                rss = ps.memory_info().rss + sum(c.memory_info().rss for c in ps.children(recursive=True)) if ps else 0
                peak = max(peak, rss)
            except psutil.Error:
                pass
            time.sleep(2)
    secs = time.time() - t0
    row = {"tile": tile, "step": name, "status": "ok" if proc.returncode == 0 else f"exit {proc.returncode}",
           "start": start.isoformat(timespec="seconds"), "minutes": round(secs / 60, 2),
           "waited_for_other_cpu_minutes": round(waited / 60, 1), "peak_rss_gb": round(peak / 1e9, 2),
           "output_gb": round(dir_bytes(out) / 1e9, 2), "scratch_gb": round(dir_bytes(scratch) / 1e9, 2),
           "free_ram_gb_after": round(psutil.virtual_memory().available / 1e9, 1), "priority": "BELOW_NORMAL"}
    path = ROOT / "training-timings.csv"; new = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row)); new and w.writeheader(); w.writerow(row)
    log(f"{tile} {name} end: {json.dumps(row)}")
    return row


def compare_parameters(tile):
    """Prepared/run parameters vs the 12TVL2804 pilot manifests (extent and source id excluded)."""
    result = {}
    ref_prep = json.loads((PILOT / "12TVL2804" / "prepared" / "preparation.json").read_text())["parameters"]
    ref_run = json.loads((PILOT / "12TVL2804" / "run" / "run.json").read_text())["parameters"]
    prep_path = ROOT / tile / "prepared" / "preparation.json"
    run_path = ROOT / tile / "run" / "run.json"
    if prep_path.exists():
        prep = json.loads(prep_path.read_text())
        result["prepare_parameters_equal_12TVL2804"] = prep.get("parameters") == ref_prep
        result["prepare_parameters"] = prep.get("parameters")
        result["prepare_status"] = prep.get("status")
        result["prepare_sources"] = [s["path"] for s in prep.get("sources", [])]
        result["prepare_extent"] = prep.get("extent")
        result["prepare_before_after"] = {"before": prep.get("before"), "after": prep.get("after")}
    if run_path.exists():
        run = json.loads(run_path.read_text())
        strip = lambda d: {k: v for k, v in (d or {}).items() if k not in ("extent", "source_id")}  # noqa: E731
        result["run_parameters_equal_12TVL2804_except_extent_source"] = strip(run.get("parameters")) == strip(ref_run)
        result["run_parameters"] = run.get("parameters")
        result["run_status"] = run.get("status")
        result["run_signature"] = run.get("signature")
        result["run_signature_12TVL2804"] = json.loads((PILOT / "12TVL2804" / "run" / "run.json").read_text()).get("signature")
        result["run_outputs"] = run.get("outputs")
        result["run_runtime"] = run.get("runtime")
    return result


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    tiles = sys.argv[1:] or json.loads(SELECTION.read_text())["draw_order"]
    extents = {Path(f["path"]).stem: f["extent"] for f in json.loads(INVENTORY.read_text())["files"]}
    provenance = code_provenance()
    log(f"driver start: tiles {tiles}; git {provenance['git_head']}; canopy changes {provenance['canopy_status_short']}")
    failed = False
    for tile in tiles:
        xmin, ymin, xmax, ymax = extents[tile]
        xmax, ymax = round(xmax), round(ymax)
        buf = [xmin - BUFFER, ymin - BUFFER, xmax + BUFFER, ymax + BUFFER]
        ed.assert_training_extents([buf, [xmin, ymin, xmax, ymax]])
        prepared, run = ROOT / tile / "prepared", ROOT / tile / "run"
        record = {"tile": tile, "domain": "TRAINING (September 30 draw; see training-tiles.json)",
                  "code_provenance_at_start": provenance, "steps": []}
        if not prepared.exists() or not completed_preparation(prepared):
            row = step(tile, "prepare", ["prepare", str(LAS), str(prepared), "--extent", *map(str, buf)], prepared)
            record["steps"].append(row)
        try:
            complete = completed_preparation(prepared)
        except ValueError as exc:
            complete, record["error_detail"] = False, str(exc)
        if not complete:
            log(f"{tile}: preparation incomplete; skipping run ({record.get('error_detail', '')})")
            record["error"] = "preparation incomplete"
            failed = True
        else:
            row = step(tile, "run", ["run", str(prepared / "prepared.lasd"), str(run), "--extent",
                                     *map(str, [xmin, ymin, xmax, ymax]), *run_resume_args(run)], run)
            record["steps"].append(row)
            failed |= row["status"] != "ok"
        record.update(compare_parameters(tile))
        (ROOT / tile / "cpu-record.json").write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
    log("driver done" + (" with failures" if failed else ""))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
