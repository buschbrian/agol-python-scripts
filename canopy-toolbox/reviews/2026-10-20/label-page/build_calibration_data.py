"""Build the label-page data for a treetop calibration packet: points, an imagery chip and facts for every unit.

    python reviews/2026-10-20/label-page/build_calibration_data.py PACKET_DIR [--out DATA_DIR]

Run with ArcGIS Pro's Python (laspy, numpy, scipy, GDAL, Pillow, pyproj; PYTHONNOUSERSITE=1). Read-only on the packet, the
LAS and the imagery; writes a new folder (default `label-page` in the packet's SSD folder, beside calibration.gdb). For
each unit, in review order:
- points/<UNIT_ID>.bin: every clean point (not withheld, not class 7 or 18) within 12 m of the unit, from every ORIGINAL
  delivery tile the circle reaches (at most 40,000; the points within 1 m are always kept), in build_label_data's format:
  float32 x, y, z relative to the unit and its ground height, then uint8 NAIP 2024 red, green, blue, intensity and returns;
- chips/<UNIT_ID>.png: a 40 m NAIP 2024 chip centred on the unit, from a mosaic of the 61 tile images;
- units.json: the 1 m column drawn on the page, point counts, and any label already in the packet's labels.csv.
Ground is the median delivery class-2 Z within 5 m, widened to 12 m, else the lowest point (recorded per unit).
**Blind by design**: the only inputs are units.csv and labels.csv from the packet, the delivery LAS (classes 1/2/7/18 only)
and NAIP. sample.json and the evidence are never read, and HEIGHT_M from units.csv is not written, so the page cannot show a
flag, a stratum, a tree ID or the treetop's height.
"""
import argparse
import csv
import datetime
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
sys.path.insert(0, str(HERE.parent))
from canopy import training_review as tr  # noqa: E402
from canopy.lidar_root import lidar_root  # noqa: E402
from build_label_data import add_latlon, pack, subsample  # noqa: E402

VALLEY = lidar_root()/"2023-salt-lake-valley"
DELIVERY_LAS = VALLEY/"las"
NAIP_TILES = VALLEY/"naip"/"naip2024-tiles"
RADIUS_M = 12.0
COLUMN_R_M = 1.0              # the calibration question: the highest object within 1 m of the point
MAX_POINTS = 40_000
CHIP_M = 40.0
GROUND_RADII_M = (5.0, 12.0)
NOISE = (7, 18)


def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def ssd_folder(packet_dir):
    """The packet's folder on the SSD, found from build.json of the calibration build (calibration_sample.py build-gdb)."""
    hits = sorted(VALLEY.glob(f"runs/*/calibration-{packet_dir.name}/build.json"))
    if len(hits) != 1:
        raise FileNotFoundError(f"Expected one calibration-{packet_dir.name} folder under {VALLEY/'runs'}, found {len(hits)}")
    return hits[0].parent


def ground_height(x, y, z, cls, cx, cy):
    d = np.hypot(x-cx, y-cy)
    for r in GROUND_RADII_M:
        g = z[(cls == 2) & (d <= r)]
        if len(g):
            return float(np.median(g)), f"class-2 median within {r:g} m"
    return float(z.min()), "lowest point within 12 m (no class-2 point)"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("packet", type=Path, help="the calibration packet folder in the repo (units.csv, labels.csv)")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    import laspy
    from osgeo import gdal
    from PIL import Image
    gdal.UseExceptions()
    packet = args.packet.resolve()
    units_csv = packet/"units.csv"
    rows = sorted(read_csv(units_csv), key=lambda r: int(r["ORDER"]))
    labels = {r["UNIT_ID"]: r for r in read_csv(packet/"labels.csv")} if (packet/"labels.csv").exists() else {}
    out = args.out or ssd_folder(packet)/"label-page"
    if out.exists():
        raise FileExistsError(f"Choose a new output folder (or move the old one aside): {out}")
    cx = np.array([float(r["X"]) for r in rows])
    cy = np.array([float(r["Y"]) for r in rows])

    # Points: every delivery tile whose extent reaches a unit's 12 m circle, accumulated per unit.
    parts = [[] for _ in rows]
    tiles_used = []
    for path in sorted(DELIVERY_LAS.glob("*.las")):
        with laspy.open(path) as reader:
            h = reader.header
            lo, hi = h.mins, h.maxs
        near = np.flatnonzero((cx+RADIUS_M >= lo[0]) & (cx-RADIUS_M <= hi[0]) & (cy+RADIUS_M >= lo[1]) & (cy-RADIUS_M <= hi[1]))
        if not len(near):
            continue
        las = laspy.read(path)
        cls = np.asarray(las.classification)
        clean = ~(np.asarray(las.withheld, bool) | np.asarray(las.synthetic, bool) | np.isin(cls, NOISE))
        x, y, z = np.asarray(las.x)[clean], np.asarray(las.y)[clean], np.asarray(las.z)[clean]
        cls = cls[clean]
        intensity = np.asarray(las.intensity)[clean]
        returns = (np.minimum(np.asarray(las.return_number)[clean], 15)*16 +
                   np.minimum(np.asarray(las.number_of_returns)[clean], 15)).astype(np.uint8)
        for k in near:
            m = (np.abs(x-cx[k]) <= RADIUS_M) & (np.abs(y-cy[k]) <= RADIUS_M)
            m[m] = np.hypot(x[m]-cx[k], y[m]-cy[k]) <= RADIUS_M
            if m.any():
                parts[k].append((x[m], y[m], z[m], cls[m], intensity[m], returns[m]))
        tiles_used.append(path.stem)
        print(f"{path.stem}: {len(near)} units", flush=True)
        del las, x, y, z, cls, intensity, returns

    # Imagery: one mosaic of the tile images, read in a window per unit for point colour and the chip.
    naip_files = sorted(str(p) for p in NAIP_TILES.glob("*/naip_*.tif"))
    vrt = gdal.BuildVRT("/vsimem/naip-calibration.vrt", naip_files)
    gt = vrt.GetGeoTransform()
    px = gt[1]

    def window(x0, y1, size_m):
        c0, r0 = int(np.floor((x0-gt[0])/px)), int(np.floor((gt[3]-y1)/px))
        n = int(np.ceil(size_m/px))
        c_lo, r_lo = max(c0, 0), max(r0, 0)
        c_hi, r_hi = min(c0+n, vrt.RasterXSize), min(r0+n, vrt.RasterYSize)
        img = np.zeros((3, n, n), dtype=np.uint8)
        if c_hi > c_lo and r_hi > r_lo:
            img[:, r_lo-r0:r_hi-r0, c_lo-c0:c_hi-c0] = vrt.ReadAsArray(c_lo, r_lo, c_hi-c_lo, r_hi-r_lo)[:3]
        return img, gt[0]+c0*px, gt[3]-r0*px

    (out/"points").mkdir(parents=True)
    (out/"chips").mkdir()
    units = []
    for k, r in enumerate(rows):
        uid = r["UNIT_ID"]
        if not parts[k]:
            raise ValueError(f"{uid}: no delivery points within {RADIUS_M} m")
        x, y, z, cls, raw_i, ret = (np.concatenate(a) for a in zip(*parts[k]))
        ground, ground_rule = ground_height(x, y, z, cls, cx[k], cy[k])
        d = np.hypot(x-cx[k], y-cy[k])
        column = d <= COLUMN_R_M
        keep = subsample(d, column, MAX_POINTS, int(r["ORDER"]))
        lo_i, hi_i = np.percentile(raw_i, [1, 99])
        intensity = np.clip((raw_i.astype(np.float64)-lo_i)/max(hi_i-lo_i, 1)*255, 0, 255).astype(np.uint8)
        img, wx0, wy1 = window(cx[k]-RADIUS_M, cy[k]+RADIUS_M, 2*RADIUS_M)
        col = np.clip(np.floor((x-wx0)/px).astype(np.int64), 0, img.shape[2]-1)
        row = np.clip(np.floor((wy1-y)/px).astype(np.int64), 0, img.shape[1]-1)
        rgb = np.stack([img[b][row, col] for b in range(3)], axis=1)
        (out/"points"/f"{uid}.bin").write_bytes(pack(x[keep]-cx[k], y[keep]-cy[k], z[keep]-ground, rgb[keep],
                                                     intensity[keep], ret[keep]))
        chip, _, _ = window(cx[k]-CHIP_M/2, cy[k]+CHIP_M/2, CHIP_M)
        size = chip.shape[1]
        Image.fromarray(chip.transpose(1, 2, 0)).resize((size*4, size*4), Image.BILINEAR).save(out/"chips"/f"{uid}.png")
        top = float((z[column]-ground).max()) if column.any() else 0.0
        saved = labels.get(uid, {})
        units.append({"UNIT_ID": uid, "REVIEW_ORDER": int(r["ORDER"]), "QUEUE_NO": "", "X": float(cx[k]),
                      "Y": float(cy[k]), "GROUND_Z": round(ground, 3), "GROUND_RULE": ground_rule, "R": COLUMN_R_M,
                      "Z_LOW": round(min(0.0, float((z[column]-ground).min()) if column.any() else 0.0)-0.3, 2),
                      "Z_HIGH": round(top+0.3, 2), "PATCH_POINTS": int(column.sum()), "POINTS": int(len(keep)),
                      "AUDIT": False, "SAVED_LABEL": (saved.get("LABEL") or "").strip() or None,
                      "SAVED_REVIEWER": (saved.get("REVIEWER") or "").strip() or None})
    add_latlon(units)
    labels_meta = [{"code": k, "description": v[0], "exported": v[1] is not None} for k, v in tr.LABELS.items()]
    (out/"units.json").write_text(json.dumps({
        "schema": "canopy-label-page/1", "mode": "calibration", "packet": str(packet),
        "units_csv_sha256": hashlib.sha256(units_csv.read_bytes()).hexdigest(), "las": str(DELIVERY_LAS),
        "tiles": tiles_used, "naip": str(NAIP_TILES), "chip_m": CHIP_M, "radius_m": RADIUS_M,
        "built": datetime.datetime.now().isoformat(timespec="seconds"), "labels": labels_meta,
        "question": "What is the highest object within 1 m (horizontally) of this point?",
        "blind": "Built from units.csv, labels.csv, the delivery LAS (classes 1/2/7/18) and NAIP only; no flag, stratum, "
                 "tree ID or treetop height is included.",
        "units": units}, indent=1), encoding="utf-8")
    print(f"{len(units)} units from {len(tiles_used)} tiles; {sum(u['SAVED_LABEL'] is not None for u in units)} already "
          f"labelled; data in {out}")


if __name__ == "__main__":
    main()
