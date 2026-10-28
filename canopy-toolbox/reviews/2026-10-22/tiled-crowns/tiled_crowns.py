"""Citywide crowns in tiles, checked against the single-window method (October 22, 2026).

    python reviews/2026-10-22/tiled-crowns/tiled_crowns.py validate NEW_FOLDER [--tile 12TVL2804] [--halos 5 10 20 40]
    python reviews/2026-10-22/tiled-crowns/tiled_crowns.py run NEW_FOLDER --halo H [--check-tiles 6]

Run with ArcGIS Pro Python (canopy.crowns imports arcpy; numpy, scipy, GDAL; PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT set).
Read-only on every input; writes a NEW folder. Brian said go ahead on October 22.

canopy.crowns.segment is a priority flood: each canopy cell (CHM at least 2 m, smoothed with the treetops' radius of one cell)
goes to the treetop it reaches along the path with the highest lowest point, ties broken by flood distance and then by the
treetop's integer label. It is bounded to 4,000,000 cells (crowns.MAX_CELLS) and AGENTS.md says a finite halo does not
guarantee exact seams, so the halo is measured, not assumed:
- validate: on one 1 km tile (exactly 4,000,000 cells, so the single-window method applies), segment the whole window once,
  then segment it again as 250 m cores each with a halo of H metres (seeds inside each core plus halo), keep every core's own
  cells, and count the cells whose label differs from the whole-window result, for each H.
- run: the October 8 count's 63 planned 950 m cores over the rebuilt canonical CHM (city-count-20261022), each segmented with
  its halo, its core cells written into one city label raster (labels.npy; label = 1 + the treetop's row in
  city-treetops.csv, the same everywhere, so ties break the same way in every tile). --check-tiles reruns that many tiles
  (spread across the city) with twice the halo; their core labels must not change, or the run reports it.
Seeds are the 527,140 rebuilt treetops (city-treetops.csv); treetops outside the city were never kept, so canopy in the margin
can only grow from city treetops. Crown polygons and statistics are made from labels.npy by crown_polygons.py.
"""
import argparse
import csv
import datetime
import json
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
sys.path.insert(0, str(TOOLBOX/"reviews"/"2026-10-21"/"roof-consensus"))
sys.path.insert(0, str(TOOLBOX/"reviews"/"2026-10-22"/"canopy-rebuild"))
import consensus_roofs as cr  # noqa: E402

COUNT = cr.RUNS/"city-count-20261022"
MIN_HEIGHT = 2.0
SMOOTH = 1
CELL = 0.5


def load(g, work=None):
    """CHM, city treetop rows, and seeds (row, col, label) for every peak of the canonical CHM.

    City treetops are labels 1..n in city-treetops.csv order. The count kept only peaks inside the city, but the canonical
    CHM covers whole 950 m cores, so canopy beyond the boundary had no seed and a city crown could flood across unseeded
    forest (validation on 12TVL3301, October 22: 303,334 cells differing even with a 40 m halo). So the peaks are detected
    again exactly as the count did (count_peaks.detect, default bands), the city ones must equal city-treetops.csv, and the
    others become seeds n+1.. that bound city crowns; their own crowns are never output.
    """
    from canopy import bands, count_peaks
    chm = np.memmap(COUNT/"canonical-chm-combined.bin", mode="r", dtype="float32", shape=(g["rows"], g["cols"]))
    rows = list(csv.DictReader(open(COUNT/"city-treetops.csv", encoding="utf-8", newline="")))
    x = np.array([float(r["X"]) for r in rows])
    y = np.array([float(r["Y"]) for r in rows])
    col = np.floor((x-g["x0"])/CELL).astype(np.int64)        # treetops sit on cell centres
    row = np.floor((g["y0"]-y)/CELL).astype(np.int64)
    cache = None if work is None else Path(work)/"peaks.npy"
    if cache is not None and cache.exists():
        peaks = np.load(cache)
    else:
        peaks = np.array([(r, c) for r, c, h in count_peaks.detect(chm, bands.DEFAULT_BANDS, CELL,
                                                                    Path(work or ".")/"peak-work")], dtype=np.int64)
        if cache is not None:
            np.save(cache, peaks)
    city_keys = row*g["cols"]+col
    peak_keys = peaks[:, 0]*g["cols"]+peaks[:, 1]
    if len(np.unique(city_keys)) != len(rows) or not np.isin(city_keys, peak_keys).all():
        raise ValueError("The city treetops are not a subset of the re-detected peaks")
    outside = peaks[~np.isin(peak_keys, city_keys)]
    seeds_row = np.concatenate([row, outside[:, 0]])
    seeds_col = np.concatenate([col, outside[:, 1]])
    label = np.arange(1, len(seeds_row)+1, dtype=np.int64)
    return chm, rows, seeds_row, seeds_col, label


def segment_window(chm, seeds_row, seeds_col, seeds_label, r0, r1, c0, c1):
    """crowns.delineate's surface, mask and segment on one window; seeds in global grid coordinates."""
    from canopy import crowns
    from canopy.treetops import smooth_surface
    raw = np.asarray(chm[r0:r1, c0:c1], dtype=np.float64)
    surface = smooth_surface(raw, SMOOTH)
    mask = np.isfinite(raw) & (raw >= MIN_HEIGHT)
    inside = (seeds_row >= r0) & (seeds_row < r1) & (seeds_col >= c0) & (seeds_col < c1)
    seeds = [(int(r-r0), int(c-c0), int(l)) for r, c, l in zip(seeds_row[inside], seeds_col[inside], seeds_label[inside])]
    return crowns.segment(surface, mask, seeds), int(inside.sum())


def tile_window(tile, g):
    import canopy_rebuild as rb
    return rb.tile_rows_cols(tile, g)


def validate(args, g):
    chm, rows, sr, sc, sl = load(g, args.out)
    r0, r1, c0, c1 = tile_window(args.tile, g)
    t0 = time.time()
    reference, n = segment_window(chm, sr, sc, sl, r0, r1, c0, c1)
    report = {"tile": args.tile, "cells": (r1-r0)*(c1-c0), "seeds": n, "whole_window_seconds": round(time.time()-t0, 1),
              "core_m": args.core, "halos": {}}
    print(f"whole window: {n} seeds, {report['whole_window_seconds']} s", flush=True)
    step = int(args.core/CELL)
    for halo_m in args.halos:
        h = int(halo_m/CELL)
        tiled = np.zeros_like(reference)
        t0 = time.time()
        for a in range(r0, r1, step):
            for b in range(c0, c1, step):
                a1, b1 = min(a+step, r1), min(b+step, c1)
                w0, w1, v0, v1 = max(a-h, r0), min(a1+h, r1), max(b-h, c0), min(b1+h, c1)
                labels, _ = segment_window(chm, sr, sc, sl, w0, w1, v0, v1)
                tiled[a-r0:a1-r0, b-c0:b1-c0] = labels[a-w0:a1-w0, b-v0:b1-v0]
        diff = tiled != reference
        canopy = reference > 0
        moved = np.unique(np.concatenate([reference[diff], tiled[diff]]))
        report["halos"][str(halo_m)] = {"differing_cells": int(diff.sum()), "canopy_cells": int(canopy.sum()),
                                        "crowns_touched": int((moved > 0).sum()), "seconds": round(time.time()-t0, 1)}
        print(f"halo {halo_m} m: {report['halos'][str(halo_m)]}", flush=True)
    (args.out/"validation.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


def planned_cores(g):
    """The October 8 count's 63 planned 950 m cores, as grid rows and columns."""
    import arcpy
    import shapely
    from canopy.tiling import Extent, snap_extent, tile_grid
    inputs = json.loads((cr.RUNS/"city-count-20261008"/"inputs.json").read_text(encoding="utf-8"))
    city = shapely.union_all([shapely.from_wkb(bytes(w)) for w, in arcpy.da.SearchCursor(inputs["boundary"], ["SHAPE@WKB"])])
    extent = snap_extent(Extent(*inputs["extent"]).buffered(20), .5)
    context = shapely.buffer(city, 20)
    cores = []
    for t in tile_grid(extent, 950, 20, .5):
        if shapely.intersects(context, shapely.box(*t.core)):
            r0, c0 = round((extent.ymax-t.core.ymax)/CELL), round((t.core.xmin-extent.xmin)/CELL)
            cores.append((t.name, r0, r0+round(t.core.height/CELL), c0, c0+round(t.core.width/CELL)))
    return cores


def run(args, g):
    chm, rows, sr, sc, sl = load(g, args.out)
    cores = planned_cores(g)
    if len(cores) != 63:
        raise ValueError(f"{len(cores)} cores planned; the October 8 count planned 63")
    labels = np.lib.format.open_memmap(args.out/"labels.npy", mode="w+", dtype=np.int32, shape=(g["rows"], g["cols"]))
    labels[:] = 0
    h = int(args.halo/CELL)
    manifest = {"status": "running", "started": datetime.datetime.now().isoformat(timespec="seconds"), "halo_m": args.halo,
                "cores": len(cores), "treetops": len(rows), "seeds": int(len(sl)), "chm": str(COUNT/"canonical-chm-combined.bin"),
                "label": "1 + row in city-treetops.csv for city treetops; above that, peaks outside the city (bounds only)",
                "tiles": {}}
    path = args.out/"manifest.json"

    def save():
        path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    save()
    try:
        for i, (name, r0, r1, c0, c1) in enumerate(cores, 1):
            t0 = time.time()
            w0, w1, v0, v1 = max(r0-h, 0), min(r1+h, g["rows"]), max(c0-h, 0), min(c1+h, g["cols"])
            window, n = segment_window(chm, sr, sc, sl, w0, w1, v0, v1)
            labels[r0:r1, c0:c1] = window[r0-w0:r1-w0, c0-v0:c1-v0]
            manifest["tiles"][name] = {"core": [r0, r1, c0, c1], "seeds": n, "seconds": round(time.time()-t0, 1)}
            labels.flush()
            save()
            print(f"{datetime.datetime.now():%H:%M:%S} {name} ({i}/{len(cores)}): {n} seeds, "
                  f"{manifest['tiles'][name]['seconds']} s", flush=True)
        # Stability: a few tiles again with twice the halo; core labels must not change.
        check = {}
        picks = [cores[k] for k in np.linspace(0, len(cores)-1, args.check_tiles).round().astype(int)] if args.check_tiles else []
        for name, r0, r1, c0, c1 in picks:
            hh = 2*h
            w0, w1, v0, v1 = max(r0-hh, 0), min(r1+hh, g["rows"]), max(c0-hh, 0), min(c1+hh, g["cols"])
            window, _ = segment_window(chm, sr, sc, sl, w0, w1, v0, v1)
            changed = int((window[r0-w0:r1-w0, c0-v0:c1-v0] != labels[r0:r1, c0:c1]).sum())
            check[name] = changed
            print(f"stability {name} with {2*args.halo} m halo: {changed} cells changed", flush=True)
        manifest["stability_double_halo"] = check
        seeded = np.zeros(len(sl)+1, bool)
        for r0 in range(0, g["rows"], 1024):
            seeded[np.unique(labels[r0:r0+1024])] = True
        manifest["treetops_with_cells"] = int(seeded[1:len(rows)+1].sum())
        manifest.update(status="complete", finished=datetime.datetime.now().isoformat(timespec="seconds"))
        save()
        print(json.dumps({k: manifest[k] for k in ("stability_double_halo", "treetops_with_cells")}, indent=1), flush=True)
    except BaseException as exc:
        manifest.update(status="failed", error=repr(exc))
        save()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("validate")
    v.add_argument("out", type=Path)
    v.add_argument("--tile", default="12TVL2804")
    v.add_argument("--core", type=float, default=250.0)
    v.add_argument("--halos", type=float, nargs="+", default=[5, 10, 20, 40])
    r = sub.add_parser("run")
    r.add_argument("out", type=Path)
    r.add_argument("--halo", type=float, required=True)
    r.add_argument("--check-tiles", type=int, default=6)
    args = parser.parse_args(argv)
    if args.out.exists():
        raise FileExistsError(args.out)
    args.out.mkdir(parents=True)
    g = cr.grid()
    (validate if args.command == "validate" else run)(args, g)


if __name__ == "__main__":
    main()
