"""Build the data for the click-through training-label page: points, an imagery chip and facts for every review unit.

    python reviews/2026-10-20/label-page/build_label_data.py [--packet PACKET_DIR] [--out DATA_DIR] [--labels BACKUP.csv]

Run with the Myria3D environment's Python (laspy, numpy, scipy, GDAL, Pillow; PYTHONNOUSERSITE=1). Read-only on the packet,
the LAS and the imagery; writes a new folder (default `<packet>/label-page`). For each of the packet's units, in review order:
- points/<UNIT_ID>.bin: every clean point within 12 m of the patch centre (at most 40,000; the patch's own points are always
  kept), as float32 x, y, z relative to the patch centre and the packet's ground height, then uint8 NAIP 2024 red, green, blue,
  scaled intensity and returns (return number * 16 + number of returns);
- chips/<UNIT_ID>.png: a 40 m NAIP 2024 chip centred on the patch;
- units.json: patch geometry, point counts, the patch height summary, the audit-2 flag and any label already saved.
**Blind by design**: no baseline class, model output, triage proposal or queue hypothesis is written, so the page cannot show
one. Labels go back only through `training_labels.bat restore --csv`, which checks every answer.
"""
import argparse
import csv
import datetime
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
from canopy import training_review as tr  # noqa: E402
from canopy.lidar_root import lidar_root, live  # noqa: E402

LIDAR = lidar_root()/"2023-salt-lake-valley"
PACKET = LIDAR/"runs"/"pilot-2026-09-29"/"training-review"/"packet-20260929"
NAIP = LIDAR/"naip"/"naip2024-tiles"/"12TVL2804"/"naip_12TVL2804.tif"
LABELS = TOOLBOX/"reviews"/"2026-09-29"/"packets"/"training-labels"/"labels-progress.csv"
AUDIT = TOOLBOX/"reviews"/"2026-09-30"/"audit-2"/"audit-units.txt"
RADIUS_M = 12.0
MAX_POINTS = 40_000
CHIP_M = 40.0


def subsample(distance_xy, in_patch, limit, seed):
    """Indices to keep: all patch points, then the nearest others up to the limit (deterministic)."""
    keep = np.flatnonzero(in_patch)
    rest = np.flatnonzero(~in_patch)
    room = max(limit-len(keep), 0)
    if len(rest) > room:
        order = np.lexsort((np.random.default_rng(seed).random(len(rest)), distance_xy[rest]))
        rest = rest[order[:room]]
    return np.sort(np.concatenate([keep, rest]))


def add_latlon(units):
    """LAT/LON (EPSG 4326) of each patch centre, for placing it on web-map imagery. NAD83(2011) and WGS84 differ by about a
    metre here, and web imagery is no better than that, so the circle on the map is a guide, not a survey position."""
    from pyproj import Transformer
    to_geo = Transformer.from_crs(6341, 4326, always_xy=True)
    for u in units:
        lon, lat = to_geo.transform(u["X"], u["Y"])
        u["LAT"], u["LON"] = round(lat, 8), round(lon, 8)


def pack(dx, dy, dz, rgb, intensity, returns):
    """Struct-of-arrays bytes: three float32 arrays, then five uint8 arrays."""
    n = len(dx)
    parts = [np.asarray(a, dtype="<f4").tobytes() for a in (dx, dy, dz)]
    parts += [np.asarray(rgb[:, i], dtype=np.uint8).tobytes() for i in range(3)]
    parts += [np.asarray(intensity, dtype=np.uint8).tobytes(), np.asarray(returns, dtype=np.uint8).tobytes()]
    data = b"".join(parts)
    assert len(data) == n*17
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--packet", type=Path, default=PACKET)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--labels", type=Path, default=LABELS, help="a training-label backup CSV (training_labels.bat backup)")
    parser.add_argument("--add-latlon", action="store_true",
                        help="only add LAT/LON to an existing units.json (for the web-map imagery panel), then stop")
    args = parser.parse_args(argv)
    if args.add_latlon:
        target = (args.out or args.packet/"label-page")/"units.json"
        document = json.loads(target.read_text(encoding="utf-8"))
        add_latlon(document["units"])
        partial = target.with_suffix(".partial")
        partial.write_text(json.dumps(document, indent=1), encoding="utf-8")
        partial.replace(target)
        print(f"Added LAT/LON to {len(document['units'])} units in {target}")
        return
    import laspy
    from osgeo import gdal
    from PIL import Image
    from scipy.spatial import cKDTree
    gdal.UseExceptions()
    packet = json.loads((args.packet/"packet.json").read_text(encoding="utf-8"))
    if packet.get("schema") != tr.SCHEMA or tr.units_digest(packet["units"]) != packet["units_digest"]:
        raise ValueError("Not an unaltered training review packet")
    frame = tr.check_frame(packet["frame"])
    out = args.out or args.packet/"label-page"
    if out.exists():
        raise FileExistsError(f"Choose a new output folder (or move the old one aside): {out}")
    stats = json.loads((args.packet/"patch_stats.json").read_text(encoding="utf-8"))
    source = live(stats["las"]["path"])
    labels = {r["UNIT_ID"]: r for r in tr.read_backup(args.labels)} if args.labels and args.labels.exists() else {}
    audit = {line.strip() for line in AUDIT.read_text(encoding="utf-8").splitlines() if line.strip()}

    las = laspy.read(source)
    if len(las.points) != stats["las"]["points"]:
        raise ValueError("The LAS does not have the point count patch_stats.json recorded")
    clean = ~(np.asarray(las.withheld, bool) | np.asarray(las.synthetic, bool))
    x, y, z = np.asarray(las.x)[clean], np.asarray(las.y)[clean], np.asarray(las.z)[clean]
    raw_intensity = np.asarray(las.intensity)[clean].astype(np.float64)
    lo, hi = np.percentile(raw_intensity, [1, 99])
    intensity = np.clip((raw_intensity-lo)/max(hi-lo, 1)*255, 0, 255).astype(np.uint8)
    returns = (np.minimum(np.asarray(las.return_number)[clean], 15)*16+np.minimum(np.asarray(las.number_of_returns)[clean], 15)).astype(np.uint8)
    tree = cKDTree(np.c_[x, y])
    image = gdal.Open(str(NAIP))
    gt = image.GetGeoTransform()
    naip = image.ReadAsArray()[:3]                          # red, green, blue
    col = np.clip(np.floor((x-gt[0])/gt[1]).astype(np.int64), 0, naip.shape[2]-1)
    row = np.clip(np.floor((gt[3]-y)/-gt[5]).astype(np.int64), 0, naip.shape[1]-1)
    rgb = np.stack([naip[b][row, col] for b in range(3)], axis=1)

    (out/"points").mkdir(parents=True)
    (out/"chips").mkdir()
    units = []
    for unit in sorted(packet["units"], key=lambda u: (int(u["REVIEW_ORDER"]), u["UNIT_ID"])):
        uid, cx, cy, r = unit["UNIT_ID"], float(unit["X"]), float(unit["Y"]), float(unit["PATCH_R_M"])
        ground = float(unit["GROUND_Z"])
        idx = np.asarray(tree.query_ball_point([cx, cy], RADIUS_M), dtype=np.int64)
        d = np.hypot(x[idx]-cx, y[idx]-cy)
        in_patch = (d <= r) & (z[idx] >= unit["Z_LOW"]) & (z[idx] <= unit["Z_HIGH"])
        keep = idx[subsample(d, in_patch, MAX_POINTS, int(unit["REVIEW_ORDER"]))]
        (out/"points"/f"{uid}.bin").write_bytes(pack(x[keep]-cx, y[keep]-cy, z[keep]-ground, rgb[keep], intensity[keep], returns[keep]))
        c0, r0 = int(round((cx-CHIP_M/2-gt[0])/gt[1])), int(round((gt[3]-(cy+CHIP_M/2))/-gt[5]))
        size = int(round(CHIP_M/gt[1]))
        chip = np.zeros((size, size, 3), dtype=np.uint8)
        rs, cs = slice(max(r0, 0), min(r0+size, naip.shape[1])), slice(max(c0, 0), min(c0+size, naip.shape[2]))
        chip[rs.start-r0:rs.stop-r0, cs.start-c0:cs.stop-c0] = naip[:, rs, cs].transpose(1, 2, 0)
        Image.fromarray(chip).resize((size*4, size*4), Image.BILINEAR).save(out/"chips"/f"{uid}.png")
        saved = labels.get(uid, {})
        units.append({"UNIT_ID": uid, "REVIEW_ORDER": int(unit["REVIEW_ORDER"]), "QUEUE_NO": uid.split("-")[0],
                      "UNIT_TOKEN": tr.unit_token(frame["digest"], unit), "X": cx, "Y": cy, "GROUND_Z": ground,
                      "R": r, "Z_LOW": float(unit["Z_LOW"])-ground, "Z_HIGH": float(unit["Z_HIGH"])-ground,
                      "PATCH_POINTS": int(in_patch.sum()), "POINTS": int(len(keep)),
                      "PATCH_HEIGHT": stats["units"].get(uid), "AUDIT": uid in audit,
                      "SAVED_LABEL": saved.get("LABEL") or None, "SAVED_REVIEWER": saved.get("REVIEWER") or None})
    add_latlon(units)
    labels_meta = [{"code": k, "description": v[0], "exported": v[1] is not None} for k, v in tr.LABELS.items()]
    (out/"units.json").write_text(json.dumps({
        "schema": "canopy-label-page/1", "packet": str(args.packet), "packet_units_digest": packet["units_digest"],
        "frame_digest": frame["digest"], "las": str(source), "naip": str(NAIP), "chip_m": CHIP_M, "radius_m": RADIUS_M,
        "labels_backup": str(args.labels) if labels else None,
        "built": datetime.datetime.now().isoformat(timespec="seconds"), "labels": labels_meta,
        "blind": "No baseline class, model output, triage proposal or queue hypothesis is included.",
        "units": units}, indent=1), encoding="utf-8")
    print(f"{len(units)} units; {sum(u['SAVED_LABEL'] is not None for u in units)} already labelled; "
          f"{sum(u['AUDIT'] for u in units)} audit units; data in {out}")


if __name__ == "__main__":
    main()
