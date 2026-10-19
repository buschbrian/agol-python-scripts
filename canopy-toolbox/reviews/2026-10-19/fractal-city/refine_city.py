"""Write provisional refined copies of the Millcreek working LAS: the baseline class changes only where all FRACTAL passes agree
and contradict it. Every change is coded and reversible.

    python reviews/2026-10-19/fractal-city/refine_city.py [--tiles 12TVL2804 ...] [--wait]

Run with the Myria3D environment's Python (laspy, GDAL; PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT set). Inputs: the October 8 working
LAS (`runs/city-count-20261008/prepared/points`) and each tile's FRACTAL `consensus.las` (infer_city.py). Output: new copies in
`runs/refined-fractal-20261019/points/<tile>.las` plus `<tile>.json`. The working LAS, the consensus and every GIS layer are only read.

Each copy keeps every byte of the working point except the classification, and adds four extra dimensions:
BASE_CLASS (the October 8 class), FRACTAL_CLASS (consensus plurality; 0 for a tie), FRACTAL_VOTES (passes that chose it) and
REFINE_RULE. Set the classification back from BASE_CLASS to undo everything, or only where REFINE_RULE is a given code.

Applied (all passes agree, the point is not withheld, and the baseline class came from the toolbox, not the vendor):
  1  height vegetation 3/4/5  -> 6  building                    4  building 6 -> vegetation 3/4/5, banded by height above
  2  height vegetation 3/4/5  -> 64 permanent structure            the run's ground mosaic at 0.5 m, 2 m and 80 m
  3  height vegetation 3/4/5  -> 1  other                       5  building 6 -> 64 permanent structure
                                                                6  building 6 -> 1  other
Proposed only, class unchanged (recorded for review):
  11 vegetation that FRACTAL calls ground       12 building that FRACTAL calls ground
  13 a vendor class (ground 2/20, water 9, bridge 17) that FRACTAL contradicts
  14 building that FRACTAL calls vegetation where no ground height exists (or above 80 m)
  15 a toolbox class that FRACTAL calls water or bridge
  16 a baseline class-1 point that FRACTAL calls vegetation, building or permanent structure
Ground stays where the vendor and the terrain recovery put it, because the terrain and every height product are built on it.
These are model-driven proposals, not validated labels: FRACTAL was trained in France with other imagery, and three passes that
agree remove its run-to-run noise, not its systematic errors.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
from canopy.lidar_root import lidar_root  # noqa: E402

LIDAR = lidar_root()/"2023-salt-lake-valley"
WORK = LIDAR/"runs"/"city-count-20261008"/"prepared"/"points"
GROUND = LIDAR/"runs"/"city-count-20261008"/"raster-ground-recovery"/"ground_mosaic.tif"
FRACTAL = LIDAR/"fractal"/"city-20261019"/"fractal"
OUT = LIDAR/"runs"/"refined-fractal-20261019"
CHUNK = 2_000_000
MAX_PAIR_SPREAD = 0.02                                     # as infer_city.py: uneven passes mean a corrupt pass
VEGETATION = (3, 4, 5)
VENDOR_FAMILY = {2: 2, 20: 2, 9: 9, 17: 17}             # vendor class -> the FRACTAL code that agrees with it
BANDS = ((0.5, 3), (2.0, 4), (80.0, 5))                    # October 8 upper thresholds for classes 3, 4 and 5
APPLIED = {1: "vegetation -> building", 2: "vegetation -> permanent structure", 3: "vegetation -> other",
           4: "building -> vegetation (height-banded)", 5: "building -> permanent structure", 6: "building -> other"}
PROPOSED = {11: "vegetation called ground", 12: "building called ground", 13: "vendor class contradicted",
            14: "building called vegetation, no usable height", 15: "toolbox class called water or bridge",
            16: "baseline class 1 called vegetation, building or structure"}


def band(hag):
    """Vegetation class for heights above ground; 0 where the height is missing or above 80 m.

    A point below the ground surface falls in the lowest band; NaN compares false everywhere and stays 0.
    """
    out = np.zeros(len(hag), dtype=np.uint8)
    lower = -np.inf
    for upper, code in BANDS:
        out[(hag > lower) & (hag <= upper)] = code
        lower = upper
    return out


def rules(base, fractal, unanimous, withheld, hag):
    """(new class, rule code) for one block. Pure: arrays in, arrays out."""
    new = base.copy()
    rule = np.zeros(len(base), dtype=np.uint8)
    eligible = unanimous & ~withheld & (fractal != 0)
    veg = eligible & np.isin(base, VEGETATION)
    bld = eligible & (base == 6)
    for mask, target, code in ((veg & (fractal == 6), 6, 1), (veg & (fractal == 64), 64, 2), (veg & (fractal == 1), 1, 3),
                               (bld & (fractal == 64), 64, 5), (bld & (fractal == 1), 1, 6)):
        new[mask] = target
        rule[mask] = code
    to_veg = bld & (fractal == 5)
    banded = band(hag)
    ok = to_veg & (banded != 0)
    new[ok] = banded[ok]
    rule[ok] = 4
    rule[to_veg & (banded == 0)] = 14
    rule[veg & (fractal == 2)] = 11
    rule[bld & (fractal == 2)] = 12
    rule[(veg | bld) & np.isin(fractal, (9, 17))] = 15
    for vendor, agrees in VENDOR_FAMILY.items():
        rule[eligible & (base == vendor) & (fractal != agrees)] = 13
    rule[eligible & (base == 1) & np.isin(fractal, (5, 6, 64))] = 16
    return new, rule


def ground_heights(ground, x, y):
    """Ground mosaic value under each point (nearest cell); NaN outside the mosaic or on NoData."""
    data, x0, y_top, cell, nodata = ground
    col = np.floor((x-x0)/cell).astype(np.int64)
    row = np.floor((y_top-y)/cell).astype(np.int64)
    inside = (col >= 0) & (col < data.shape[1]) & (row >= 0) & (row < data.shape[0])
    out = np.full(len(x), np.nan)
    out[inside] = data[row[inside], col[inside]]
    out[(out >= nodata*0.99) | ~np.isfinite(out)] = np.nan
    return out


def read_ground(bounds):
    from osgeo import gdal
    gdal.UseExceptions()
    dataset = gdal.Open(str(GROUND))
    gt = dataset.GetGeoTransform()
    band_ = dataset.GetRasterBand(1)
    xmin, ymin, xmax, ymax = bounds
    c0 = max(int(np.floor((xmin-1-gt[0])/gt[1])), 0)
    c1 = min(int(np.ceil((xmax+1-gt[0])/gt[1])), dataset.RasterXSize)
    r0 = max(int(np.floor((gt[3]-ymax-1)/-gt[5])), 0)
    r1 = min(int(np.ceil((gt[3]-ymin+1)/-gt[5])), dataset.RasterYSize)
    if c0 >= c1 or r0 >= r1:
        return np.full((1, 1), np.nan, dtype=np.float32), 0.0, 0.0, 1.0, np.inf
    data = band_.ReadAsArray(c0, r0, c1-c0, r1-r0).astype(np.float64)
    return data, gt[0]+c0*gt[1], gt[3]+r0*gt[5], gt[1], band_.GetNoDataValue() or np.inf


def refine_tile(tile, log):
    import laspy
    source, consensus = WORK/f"{tile}.las", FRACTAL/tile/"consensus.las"
    out = OUT/"points"/f"{tile}.las"
    partial = out.with_name(f"{tile}.partial.las")
    if partial.exists():
        partial.rename(out.with_name(f"{tile}.interrupted-{int(time.time())}.las"))
    before = os.stat(source)
    repeats = json.loads((FRACTAL/tile/"manifest.json").read_text(encoding="utf-8"))["repeats"]
    summary = {"tile": tile, "source": str(source), "consensus": str(consensus), "repeats": repeats, "points": 0,
               "withheld": 0, "unanimous": 0, "no_ground_height": 0,
               "rules": {str(k): 0 for k in (*APPLIED, *PROPOSED)},
               "baseline_by_fractal": {}, "baseline_by_fractal_unanimous": {}, "changed_from_to": {}}
    with laspy.open(source) as base_reader, laspy.open(consensus) as cons_reader:
        if base_reader.header.point_count != cons_reader.header.point_count:
            raise ValueError(f"{tile}: point counts differ")
        header = base_reader.header.copy()
        for name in ("BASE_CLASS", "FRACTAL_CLASS", "FRACTAL_VOTES", "REFINE_RULE"):
            header.add_extra_dim(laspy.ExtraBytesParams(name=name, type=np.uint8))
        hb = base_reader.header
        ground = read_ground((hb.mins[0], hb.mins[1], hb.maxs[0], hb.maxs[1]))
        OUT.joinpath("points").mkdir(parents=True, exist_ok=True)
        with laspy.open(partial, mode="w", header=header) as writer:
            for block in base_reader.chunk_iterator(CHUNK):
                cons = cons_reader.read_points(len(block))
                for name in ("X", "Y", "Z", "gps_time", "intensity", "return_number"):
                    if not np.array_equal(np.asarray(block[name]), np.asarray(cons[name])):
                        raise ValueError(f"{tile}: consensus differs from the working LAS in {name}; points are not aligned")
                base = np.asarray(block.classification).astype(np.uint8)
                fractal = np.asarray(cons["MajorityClassification"]).astype(np.uint8)
                votes = np.rint(np.asarray(cons["RepeatAgreement"], dtype=np.float64)*repeats).astype(np.uint8)
                unanimous = votes == repeats
                withheld = np.asarray(block.withheld).astype(bool)
                x, y, z = np.asarray(block.x), np.asarray(block.y), np.asarray(block.z)
                hag = z-ground_heights(ground, x, y)
                new, rule = rules(base, fractal, unanimous, withheld, hag)
                record = laspy.ScaleAwarePointRecord.zeros(len(block), header=header)
                for name in hb.point_format.dimension_names:
                    record[name] = block[name]
                record["classification"] = new
                record["BASE_CLASS"], record["FRACTAL_CLASS"] = base, fractal
                record["FRACTAL_VOTES"], record["REFINE_RULE"] = votes, rule
                writer.write_points(record)
                summary["points"] += len(block)
                summary["withheld"] += int(withheld.sum())
                summary["unanimous"] += int(unanimous.sum())
                summary["no_ground_height"] += int(np.isnan(hag).sum())
                codes, counts = np.unique(rule, return_counts=True)
                for code, count in zip(codes, counts):
                    if code:
                        summary["rules"][str(int(code))] += int(count)
                for key, mask in (("baseline_by_fractal", ~withheld), ("baseline_by_fractal_unanimous", ~withheld & unanimous)):
                    pairs, counts = np.unique(base[mask].astype(np.int64)*1000+fractal[mask], return_counts=True)
                    for pair, count in zip(pairs, counts):
                        k = f"{pair//1000}>{pair % 1000}"
                        summary[key][k] = summary[key].get(k, 0)+int(count)
                changed = new != base
                pairs, counts = np.unique(base[changed].astype(np.int64)*1000+new[changed], return_counts=True)
                for pair, count in zip(pairs, counts):
                    k = f"{pair//1000}>{pair % 1000}"
                    summary["changed_from_to"][k] = summary["changed_from_to"].get(k, 0)+int(count)
    after = os.stat(source)
    if (before.st_size, before.st_mtime) != (after.st_size, after.st_mtime):
        raise RuntimeError(f"{tile}: the working LAS changed while it was read")
    partial.rename(out)
    summary["changed"] = sum(summary["changed_from_to"].values())
    summary["output"] = str(out)
    (OUT/"points"/f"{tile}.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    log(f"{tile}: {summary['changed']:,} of {summary['points']:,} points changed "
        f"({100*summary['changed']/summary['points']:.2f}%); unanimous {100*summary['unanimous']/summary['points']:.1f}%")
    return summary


def consensus_ready(tile):
    """A complete consensus whose passes agree evenly; a tile with one corrupt pass is never refined."""
    manifest = FRACTAL/tile/"manifest.json"
    if not manifest.exists():
        return False
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if not data.get("status", "").startswith("complete"):
        return False
    pairs = [p["agreement"] for p in data["consensus"]["pairwise"]]
    return max(pairs)-min(pairs) <= MAX_PAIR_SPREAD


def inference_finished():
    path = FRACTAL.parent/"infer.json"
    if not path.exists():
        return False
    return not json.loads(path.read_text(encoding="utf-8")).get("status", "running").startswith("running")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tiles", nargs="+")
    parser.add_argument("--wait", action="store_true", help="wait for tiles whose inference has not finished")
    args = parser.parse_args(argv)

    def log(text):
        print(f"{datetime.datetime.now():%H:%M:%S} {text}", flush=True)

    tiles = args.tiles or sorted(p.stem for p in WORK.glob("*.las"))
    pending = [t for t in tiles if not (OUT/"points"/f"{t}.json").exists()]
    failed = {}
    while pending:
        ready = [t for t in pending if consensus_ready(t)]
        for tile in ready:
            try:
                refine_tile(tile, log)
            except Exception as exc:                        # record and continue with the other tiles
                failed[tile] = str(exc)
                log(f"{tile}: FAILED {exc}")
            pending.remove(tile)
        if not pending:
            break
        if not args.wait or (inference_finished() and not any(consensus_ready(t) for t in pending)):
            log(f"not refined (no complete consensus): {', '.join(pending)}")
            break
        if not ready:
            time.sleep(60)
    if failed:
        log(f"failed: {json.dumps(failed)}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
