r"""Treetop review evidence: per-treetop roof-edge, wire, pole and wall suspects for the October 8 city count.

Steps (from canopy-toolbox):
    reproduce   Pro Python. Re-measures the 29 September 12TVL2804 pilot treetops against the pilot's own prepared
                tile with canopy.treetop_evidence and checks the published near-building counts exactly.
    city        Plain or Pro Python. Every city treetop against the city run's prepared LAS (own tile plus a
                HALO_M strip from each neighbour). Writes a NEW run folder; refuses an existing one.
    gdb         Pro Python. Point feature class from the city CSV, in the same new folder.

    python reviews/2026-10-15/treetop_evidence_driver.py reproduce
    python reviews/2026-10-15/treetop_evidence_driver.py city [--out FOLDER] [--tiles 12TVL2804 ...] [--workers 4]
    python reviews/2026-10-15/treetop_evidence_driver.py gdb --out FOLDER

Inputs are only read; their sizes and modification times are checked before and after. Everything written is
UNVALIDATED review evidence: never labels, never truth, never a corrected count.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from canopy import treetop_evidence as te  # noqa: E402
from canopy.lidar_root import lidar_root  # noqa: E402

VALLEY = lidar_root()/"2023-salt-lake-valley"
PILOT = VALLEY/"runs"/"pilot-2026-09-29"
CITY = VALLEY/"runs"/"city-count-20261008"
POINTS = CITY/"prepared"/"points"
TREETOPS = CITY/"city-treetops.csv"
DEFAULT_OUT = VALLEY/"runs"/"treetop-evidence-20261015"
PILOT_PUBLISHED = HERE.parent/"2026-09-29"/"candidates-vs-roof-height.json"
PILOT_NEAR = HERE.parent/"2026-09-29"/"candidates-near-buildings.json"
COLUMNS = ["TREE_ID", "TILE", "X", "Y", "HEIGHT_M", *te.FEATURES, *te.FLAGS]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 24), b""):
            h.update(block)
    return h.hexdigest()


def fingerprint(paths):
    return {str(p): [p.stat().st_size, p.stat().st_mtime_ns] for p in paths}


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o)))


def tile_extent(path):
    from canopy import las_records
    return tuple(las_records.header(path)["extent"])


# ---------------------------------------------------------------- reproduce
def reproduce():
    import arcpy
    tile = "12TVL2804"
    las = PILOT/tile/"prepared"/"points"/f"{tile}.las"
    fc = json.loads((PILOT/tile/"run"/"run.json").read_text())["outputs"]["trees_review"]
    before = fingerprint([las])
    rows = list(arcpy.da.SearchCursor(fc, ["SHAPE@X", "SHAPE@Y", "HEIGHT_M"]))
    xy = np.array([(r[0], r[1]) for r in rows])
    height = np.array([r[2] for r in rows], dtype=float)
    start = time.time()
    points = te.read_points(las)              # the pilot read only the tile's own file
    f = te.evaluate(xy, height, points)
    bands = te.band(f["above_roof_m"])
    near = f["n_building_1m"] > 0
    got = {"candidates": len(rows), "within_1m": int(near.sum()),
           "within_1m_no_ground_5m": int(np.count_nonzero(near & (bands == -1))),
           "by_height_vs_roof": {b: int(np.count_nonzero(near & (bands == i))) for i, b in enumerate(te.BANDS)}}
    published = json.loads(PILOT_PUBLISHED.read_text())["tiles"][tile]
    near_published = json.loads(PILOT_NEAR.read_text())[f"{tile}/run"]
    expected = {"candidates": near_published["candidates"], "within_1m": near_published["within_1.0m"],
                "by_height_vs_roof": published["by_height_vs_roof"]}
    checks = {"candidates": got["candidates"] == expected["candidates"],
              "within_1m": got["within_1m"] == expected["within_1m"],
              "by_height_vs_roof": got["by_height_vs_roof"] == expected["by_height_vs_roof"]}
    record = {"status": "passed" if all(checks.values()) else "FAILED", "evidence_status": te.STATUS,
              "rules_version": te.RULES_VERSION,
              "tile": tile, "las": str(las), "treetops": fc, "expected": expected, "got": got, "checks": checks,
              "summary": te.summary(f), "rules": te.RULES, "seconds": round(time.time()-start, 1),
              "inputs_unchanged": fingerprint([las]) == before,
              "note": "Pilot definition: class-6 and class-2 points of the tile's own file only, all flags. "
                      "Shape flags use clean non-ground, non-noise points of the same file."}
    write_json(HERE/"pilot-reproduction.json", record)
    print(json.dumps({k: record[k] for k in ("status", "expected", "got", "checks", "seconds")}, indent=2))
    if record["status"] != "passed" or not record["inputs_unchanged"]:
        raise SystemExit("Reproduction failed")


# ---------------------------------------------------------------- city
def strip_job(las, out):
    points = te.read_points(las)
    s = te.strip(points, tile_extent(las))
    np.savez(out, **s)
    return las.stem, len(s["x"])


def tile_job(tile, las, neighbours, strips, treetops, out):
    start = time.time()
    extent = tile_extent(las)
    halo = (extent[0]-te.HALO_M, extent[1]-te.HALO_M, extent[2]+te.HALO_M, extent[3]+te.HALO_M)
    parts = [te.read_points(las)]
    for name in neighbours:
        with np.load(strips/f"{name}.npz") as s:
            s = {k: s[k] for k in s.files}
        inside = (s["x"] >= halo[0]) & (s["x"] <= halo[2]) & (s["y"] >= halo[1]) & (s["y"] <= halo[3])
        parts.append({k: v[inside] for k, v in s.items()})
    points = te.concat(*parts)
    ids, xy, height = treetops
    f = te.evaluate(xy, height, points)
    np.savez(out/f"{tile}.npz", TREE_ID=np.array(ids), X=xy[:, 0], Y=xy[:, 1], HEIGHT_M=height,
             **{k: f[k] for k in (*te.FEATURES, *te.FLAGS)})
    record = {"tile": tile, "treetops": len(ids), "points": int(len(points["x"])), "neighbours": neighbours,
              "seconds": round(time.time()-start, 1), "summary": te.summary(f)}
    write_json(out/f"{tile}.json", record)
    return record


def load_treetops():
    by_tile = {}
    with open(TREETOPS, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            x, y = float(row["X"]), float(row["Y"])
            by_tile.setdefault(te.tile_name(x, y), []).append((row["TREE_ID"], x, y, float(row["HEIGHT_M"])))
    return {t: ([r[0] for r in rows], np.array([(r[1], r[2]) for r in rows]), np.array([r[3] for r in rows]))
            for t, rows in by_tile.items()}


def neighbours_of(tile, available):
    col, row = int(tile[5:7]), int(tile[7:9])
    names = [f"{tile[:5]}{col+dc:02d}{row+dr:02d}" for dc in (-1, 0, 1) for dr in (-1, 0, 1) if dc or dr]
    return [n for n in names if n in available]


def city(out, tiles=None, workers=4):
    out = Path(out)
    if out.exists():
        raise FileExistsError(f"Use a new folder: {out}")
    files = {p.stem: p for p in sorted(POINTS.glob("*.las"))}
    inputs = [TREETOPS, *files.values()]
    before = fingerprint(inputs)
    csv_sha = sha256(TREETOPS)
    treetops = load_treetops()
    unassigned = {t: len(v[0]) for t, v in treetops.items() if t not in files}
    run_tiles = sorted(t for t in treetops if t in files and (not tiles or t in tiles))
    (out/"strips").mkdir(parents=True)
    (out/"tiles").mkdir()
    manifest = {"status": "running", "evidence_status": te.STATUS, "rules_version": te.RULES_VERSION,
                "started": datetime.datetime.now().isoformat(),
                "treetops_csv": str(TREETOPS), "treetops_csv_sha256": csv_sha, "points": str(POINTS),
                "tiles": run_tiles, "unassigned_treetops": unassigned, "rules": te.RULES, "halo_m": te.HALO_M,
                "definitions": te.__doc__}
    write_json(out/"manifest.json", manifest)
    start = time.time()
    need = sorted({n for t in run_tiles for n in neighbours_of(t, files)} | set(run_tiles)) if tiles else sorted(files)
    with ProcessPoolExecutor(workers) as pool:
        for future in as_completed([pool.submit(strip_job, files[n], out/"strips"/f"{n}.npz") for n in need]):
            future.result()
    print(f"strips {len(need)} in {time.time()-start:.0f} s", flush=True)
    records = []
    with ProcessPoolExecutor(workers) as pool:
        jobs = [pool.submit(tile_job, t, files[t], neighbours_of(t, files), out/"strips", treetops[t], out/"tiles")
                for t in run_tiles]
        for future in as_completed(jobs):
            r = future.result()
            records.append(r)
            print(f"{r['tile']} {r['treetops']} treetops, {r['seconds']} s, suspect "
                  f"{r['summary']['flags']['SUSPECT']}", flush=True)
    merged = merge(out, run_tiles)
    after = fingerprint(inputs)
    manifest.update({"status": "complete", "finished": datetime.datetime.now().isoformat(),
                     "seconds": round(time.time()-start, 1), "inputs_unchanged": after == before,
                     "treetops_csv_sha256_after": sha256(TREETOPS), "summary": merged,
                     "per_tile": {r["tile"]: r["summary"]["flags"] for r in sorted(records, key=lambda r: r["tile"])}})
    write_json(out/"manifest.json", manifest)
    print(json.dumps(merged, indent=2))
    if not manifest["inputs_unchanged"] or manifest["treetops_csv_sha256_after"] != csv_sha:
        raise SystemExit("Inputs changed during the run")


def merge(out, tiles):
    cols = {c: [] for c in COLUMNS}
    for t in tiles:
        with np.load(out/"tiles"/f"{t}.npz") as d:
            for c in COLUMNS:
                cols[c].append(np.full(len(d["X"]), t) if c == "TILE" else d[c])
    cols = {c: np.concatenate(v) for c, v in cols.items()}
    with open(out/"treetop-evidence.csv", "w", newline="", encoding="utf-8") as handle:
        w = csv.writer(handle)
        w.writerow(COLUMNS)
        for i in range(len(cols["X"])):
            w.writerow([_cell(cols[c][i]) for c in COLUMNS])
    return te.summary(cols)


def _cell(v):
    if isinstance(v, (np.bool_, bool)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return "" if np.isnan(v) else round(float(v), 4)
    return v.item() if hasattr(v, "item") else v


# ---------------------------------------------------------------- gdb
def drop_extra_fields(fc):
    """XY Table To Point adds WGS84 longitude/latitude fields (named TILE_X/TILE_Y here); keep only the CSV columns."""
    import arcpy
    keep = {c.lower() for c in COLUMNS}
    extra = [f.name for f in arcpy.ListFields(fc) if f.type not in ("OID", "Geometry") and f.name.lower() not in keep]
    if extra:
        arcpy.management.DeleteField(fc, extra)
    return extra


def gdb(out):
    import arcpy
    out = Path(out)
    target = out/"treetop-evidence.gdb"
    if target.exists():
        raise FileExistsError(target)
    arcpy.management.CreateFileGDB(str(out), target.name)
    fc = str(target/"treetop_evidence")
    arcpy.management.XYTableToPoint(str(out/"treetop-evidence.csv"), fc, "X", "Y",
                                    coordinate_system=arcpy.SpatialReference(6341))
    drop_extra_fields(fc)
    warning = ("ESTIMATE WARNING: review evidence for UNVERIFIED lidar treetop detections (city count, 8 October "
               "2026). Flags are fixed rule outputs, not labels, not errors and not a corrected count.")
    md = arcpy.metadata.Metadata(fc)
    md.title, md.summary, md.description = "Treetop review evidence", warning, warning+"\n\n"+te.__doc__
    md.save()
    count = int(arcpy.management.GetCount(fc)[0])
    write_json(out/"gdb.json", {"feature_class": fc, "features": count, "evidence_status": te.STATUS, "rules_version": te.RULES_VERSION,
                                "warning": warning})
    print(fc, count)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("reproduce", "city", "gdb"))
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--tiles", nargs="*")
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    if os.environ.get("PYTHONNOUSERSITE") != "1" and "ArcGIS" in sys.executable:
        raise SystemExit("Set PYTHONNOUSERSITE=1 for ArcGIS Pro Python")
    {"reproduce": lambda: reproduce(), "city": lambda: city(a.out, a.tiles, a.workers),
     "gdb": lambda: gdb(a.out)}[a.step]()


if __name__ == "__main__":
    main()
