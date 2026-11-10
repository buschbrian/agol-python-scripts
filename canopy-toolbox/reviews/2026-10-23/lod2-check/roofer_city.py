r"""Roofer LoD2.2 on every county footprint of Millcreek, scored and combined with Esri's levels (October 24, 2026).

    python reviews/2026-10-23/lod2-check/roofer_city.py prep    OUT          footprints per tile, tile extents
    python reviews/2026-10-23/lod2-check/roofer_city.py points  OUT          consensus roof + ground points per tile (4 workers)
    python reviews/2026-10-23/lod2-check/roofer_city.py run     OUT          roofer per tile, with its neighbours' points at the edges
    python reviews/2026-10-23/lod2-check/roofer_city.py convert OUT          one CityJSON, OBJ, multipatch feature class, raster
    python reviews/2026-10-23/lod2-check/roofer_city.py score   OUT          every building scored with lod2_check.py's rules
    python reviews/2026-10-23/lod2-check/roofer_city.py hybrid  OUT          roofer, else Esri LOD2.0, else LOD1.2; package it

OUT is a new folder holding the roofer release (OUT\roofer-1.0.0, copied from the pilot's), cjio's venv (OUT\tools) and every
output. ArcGIS Pro Python or the deep-learning clone (arcpy, laspy, numpy; PYTHONNOUSERSITE=1). Read-only on every input.
Every stage resumes: finished tiles are skipped. Nothing is uploaded.
- Points: roofer_input.py's rule per tile (class 6 where at least two of native, FRACTAL and Esri say building on a first or
  single clean return; class 2 native ground), for all 61 tiles.
- Footprints: the October 22 massing footprints (21,562), each given to the tile that holds its inside point; roofer is run
  on a tile's footprints with that tile's points plus every neighbouring tile's points inside the footprints' extent
  (plus 20 m), merged into one LAS (roofer would otherwise pick one point cloud per building).
"""
import argparse
import concurrent.futures as cf
import datetime
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

import numpy as np

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import roofer_input as ri  # noqa: E402
import consensus_roofs as cr  # noqa: E402

TOOLBOX = HERE.parents[3]
RUNS = cr.RUNS
PILOT = RUNS/"roofer-20261024"
FILLED = RUNS/"massing-filled-20261023"
CHECK_FILLED = RUNS/"lod2-check-filled-20261023"
BUFFER = 20.0
SRS = "EPSG:6341"


def log(msg):
    print(f"{datetime.datetime.now():%H:%M:%S} {msg}", flush=True)


def tiles():
    out = {}
    for f in sorted(cr.NATIVE.glob("*.las")):
        import laspy
        with laspy.open(f) as r:
            h = r.header
            out[f.stem] = (h.x_min, h.y_min, h.x_max, h.y_max)
    return out


# ---------------------------------------------------------------- prep
def prep(out):
    import arcpy
    out.mkdir(parents=True, exist_ok=True)
    cells = {(int(b[0]//1000), int(b[1]//1000)): t for t, b in tiles().items()}
    gdb = out/"prep.gdb"
    if not arcpy.Exists(str(gdb)):
        arcpy.management.CreateFileGDB(str(out), gdb.name)
    fc = str(gdb/"footprints")
    if arcpy.Exists(fc):
        arcpy.management.Delete(fc)
    arcpy.management.CopyFeatures(str(FILLED/"massing.gdb"/"footprints"), fc)
    arcpy.management.AddField(fc, "TILE", "TEXT", field_length=12)
    info = {}
    with arcpy.da.UpdateCursor(fc, ["SHAPE@", "TILE", "FP_ID"]) as cursor:
        for shape, _, fid in cursor:
            p = shape.labelPoint
            tile = cells.get((int(p.X//1000), int(p.Y//1000)), "NONE")
            e = shape.extent
            d = info.setdefault(tile, {"n": 0, "xmin": e.XMin, "ymin": e.YMin, "xmax": e.XMax, "ymax": e.YMax})
            d["n"] += 1
            d["xmin"], d["ymin"] = min(d["xmin"], e.XMin), min(d["ymin"], e.YMin)
            d["xmax"], d["ymax"] = max(d["xmax"], e.XMax), max(d["ymax"], e.YMax)
            cursor.updateRow([shape, tile, fid])
    shp_dir = out/"footprints"
    shp_dir.mkdir(exist_ok=True)
    layer = arcpy.management.MakeFeatureLayer(fc, "fp_all").getOutput(0)
    for tile in sorted(info):
        if tile == "NONE":
            continue
        arcpy.management.SelectLayerByAttribute(layer, "NEW_SELECTION", f"TILE = '{tile}'")
        shp = shp_dir/f"{tile}.shp"
        if not shp.exists():
            arcpy.conversion.ExportFeatures(
                layer, str(shp), field_mapping='FP_ID "FP_ID" true true false 4 Long 0 0, First, #, fp_all, FP_ID, -1, -1')
    record = {"footprints": sum(d["n"] for d in info.values()), "unassigned": info.get("NONE", {}).get("n", 0),
              "tiles_with_footprints": len([t for t in info if t != "NONE"]), "tiles": info}
    (out/"prep.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    log(f"prep: {record['footprints']} footprints, {record['unassigned']} unassigned, "
        f"{record['tiles_with_footprints']} tiles")


# ---------------------------------------------------------------- points
def _tile_points(args):
    tile, folder = args
    done = Path(folder)/f"{tile}.json"
    if done.exists():
        return tile, json.loads(done.read_text(encoding="utf-8")), 0
    started = datetime.datetime.now()
    tmp = Path(folder)/"tmp"
    tmp.mkdir(exist_ok=True)
    record = ri.points(tile, tmp)
    os.replace(tmp/f"{tile}.las", Path(folder)/f"{tile}.las")
    record["seconds"] = round((datetime.datetime.now()-started).total_seconds())
    done.write_text(json.dumps(record), encoding="utf-8")
    return tile, record, record["seconds"]


def points(out, workers=4):
    folder = out/"points"
    folder.mkdir(parents=True, exist_ok=True)
    names = sorted(tiles())
    with cf.ProcessPoolExecutor(max_workers=workers) as pool:
        for tile, record, seconds in pool.map(_tile_points, [(t, str(folder)) for t in names]):
            log(f"points {tile}: {record['written']:,} of {record['points_in_tile']:,} ({seconds} s)")


# ---------------------------------------------------------------- run
def _merge(tile, bounds, out_las, folder, prep_info, points_dir):
    """The tile's own points plus every neighbour's points inside the footprints' extent plus the buffer."""
    import laspy
    t = bounds[tile]
    info = prep_info["tiles"][tile]
    box = (min(t[0], info["xmin"])-BUFFER, min(t[1], info["ymin"])-BUFFER,
           max(t[2], info["xmax"])+BUFFER, max(t[3], info["ymax"])+BUFFER)
    own = points_dir/f"{tile}.las"
    n_own = n_nb = 0
    with laspy.open(own) as r:
        header = r.header
        with laspy.open(out_las, mode="w", header=header) as w:
            for chunk in r.chunk_iterator(4_000_000):
                w.write_points(chunk)
                n_own += len(chunk)
            for other, b in bounds.items():
                if other == tile or b[2] <= box[0] or b[0] >= box[2] or b[3] <= box[1] or b[1] >= box[3]:
                    continue
                with laspy.open(points_dir/f"{other}.las") as q:
                    if list(q.header.scales) != list(header.scales) or list(q.header.offsets) != list(header.offsets):
                        raise ValueError(f"{other}: scales or offsets differ from {tile}")
                    for chunk in q.chunk_iterator(4_000_000):
                        x, y = np.asarray(chunk.x), np.asarray(chunk.y)
                        m = (x >= box[0]) & (x < box[2]) & (y >= box[1]) & (y < box[3])
                        if m.any():
                            w.write_points(chunk[m])
                            n_nb += int(m.sum())
    return {"box": box, "own_points": n_own, "neighbour_points": n_nb}


def run(out, jobs=12, flags=(), points_from=None):
    prep_info = json.loads((out/"prep.json").read_text(encoding="utf-8"))
    bounds = tiles()
    exe = out/"roofer-1.0.0"/"bin"/"roofer.exe"
    if not exe.exists():
        shutil.copytree(PILOT/"roofer-1.0.0", out/"roofer-1.0.0")
    work = out/"work"
    work.mkdir(exist_ok=True)
    (out/"output").mkdir(exist_ok=True)
    for tile in sorted(prep_info["tiles"]):
        if tile == "NONE":
            continue
        dest = out/"output"/tile
        if (dest/"done.json").exists():
            continue
        started = datetime.datetime.now()
        merged = work/f"{tile}.las"
        m = _merge(tile, bounds, merged, out, prep_info, Path(points_from) if points_from else out/"points")
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir()
        cmd = [str(exe), "--lod22", "--id-attribute", "FP_ID", "--srs", SRS, "--jobs", str(jobs), *flags, str(merged),
               str(out/"footprints"/f"{tile}.shp"), str(dest)]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(work))
        (dest/"roofer.log").write_text(proc.stdout+proc.stderr, encoding="utf-8")
        wrote = re.search(r"wrote (\d+) buildings in", proc.stdout)
        ok = proc.returncode == 0 and wrote is not None
        record = {**m, "flags": list(flags), "returncode": proc.returncode, "buildings_written": int(wrote.group(1)) if wrote else None,
                  "footprints": prep_info["tiles"][tile]["n"], "seconds": round((datetime.datetime.now()-started).total_seconds())}
        merged.unlink(missing_ok=True)
        if not ok:
            log(f"run {tile}: FAILED, see {dest/'roofer.log'}")
            (dest/"failed.json").write_text(json.dumps(record), encoding="utf-8")
            continue
        (dest/"done.json").write_text(json.dumps(record), encoding="utf-8")
        log(f"run {tile}: {record['buildings_written']} of {record['footprints']} buildings, "
            f"{record['neighbour_points']:,} neighbour points ({record['seconds']} s)")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stage", choices=("prep", "points", "run", "convert", "score", "hybrid"))
    p.add_argument("out", type=Path)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--roofer-flags", default="", help="extra roofer options, one string, e.g. \"--plane-detect-min-points 30\"")
    p.add_argument("--points-from", help="the points folder of an earlier run (a new run need not rebuild them)")
    a = p.parse_args(argv)
    out = a.out.resolve()
    if a.stage == "prep":
        prep(out)
    elif a.stage == "points":
        points(out, a.workers)
    elif a.stage == "run":
        run(out, flags=shlex.split(a.roofer_flags), points_from=a.points_from)
    else:
        import roofer_city_stages as stages
        getattr(stages, a.stage)(out)


if __name__ == "__main__":
    main()
