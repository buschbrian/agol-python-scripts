"""Verify the consensus roofs: against October 19, against Brian's labels, and against the county footprints (October 21, 2026).

    python reviews/2026-10-21/roof-consensus/verify_roofs.py ROOT [--out verification.json]

Run with the Myria3D environment's Python (numpy, scipy, GDAL; PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT set) after
consensus_roofs.py. Read-only on every input.

1. rasters: roof_elevation_native_m.tif must equal October 19's roof_elevation_m.tif cell for cell over the whole city (same
   points, same method); counts of cells by source combination (building_sources.tif).
2. labels (12TVL2804 only): every labelled part of the three packets' latest snapshots. A part's points are the clean points (all
   returns) within its patch radius and height slab; a source calls the part roof when most of them are class 6. Roof labels
   (BUILDING_ROOF) give each source's recall; tree, shrub, ground, vehicle, wire, pole, other structure and water give its false
   roof calls. WALL, MIXED and UNSURE are left out. These units were chosen partly by model disagreement, so the figures compare
   sources on the same hard sample; they are not citywide accuracies.
3. footprints: each source's roof cells inside and outside the county footprints (rasterized on the same grid, cell centres).
   Roof outside every footprint is not automatically wrong (sheds, new buildings, footprint gaps), but trees called roof
   show up there.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
sys.path.insert(0, str(HERE.parent))
from canopy import las_records, training_review as tr  # noqa: E402
import consensus_roofs as cr  # noqa: E402

REVIEW = cr.RUNS/"pilot-2026-09-29"/"training-review"
SNAPSHOTS = [("packet-20260929", "packet-20260929-20261020"),
             ("packet-20261020-refined", "packet-20261020-refined-20261021"),
             ("packet-20261020-rare", "packet-20261020-rare-20261021-1055")]
TILE = "12TVL2804"
ROOF = {"BUILDING_ROOF"}
NOT_ROOF = {"TREE", "SHRUB_LOW_VEG", "GROUND", "VEHICLE", "WIRE", "POLE", "OTHER_STRUCTURE", "WATER"}
NAMES = (*cr.SOURCES, "consensus")


def band(path):
    from osgeo import gdal
    gdal.UseExceptions()
    ds = gdal.Open(str(path))
    return ds, ds.GetRasterBand(1)


def check_rasters(root, g):
    """Native against October 19, block by block; source-combination counts."""
    a_ds, a = band(root/"roof_elevation_native_m.tif")
    b_ds, b = band(cr.OCT19/"roof_elevation_m.tif")
    s_ds, s = band(root/"building_sources.tif")
    na, nb = a.GetNoDataValue(), b.GetNoDataValue()
    out = {"both": 0, "only_native": 0, "only_oct19": 0, "differ_over_1mm": 0, "max_abs_difference_m": 0.0}
    combos = np.zeros(8, np.int64)
    for r0 in range(0, g["rows"], 512):
        n = min(512, g["rows"]-r0)
        x, y = a.ReadAsArray(0, r0, g["cols"], n), b.ReadAsArray(0, r0, g["cols"], n)
        hx, hy = x != na, y != nb
        both = hx & hy
        out["both"] += int(both.sum())
        out["only_native"] += int((hx & ~hy).sum())
        out["only_oct19"] += int((~hx & hy).sum())
        if both.any():
            d = np.abs(x[both]-y[both])
            out["differ_over_1mm"] += int((d > 1e-3).sum())
            out["max_abs_difference_m"] = max(out["max_abs_difference_m"], float(d.max()))
        c = s.ReadAsArray(0, r0, g["cols"], n)
        combos += np.bincount(c[c != 255].ravel(), minlength=8)[:8]
    a_ds = b_ds = s_ds = None
    out["native_reproduces_oct19"] = out["only_native"] == out["only_oct19"] == out["differ_over_1mm"] == 0
    label = {0: "none", 1: "native only", 2: "fractal only", 3: "native+fractal", 4: "esri only", 5: "native+esri",
             6: "fractal+esri", 7: "all three"}
    return {"native_vs_oct19": out, "city_cells_by_sources": {label[k]: int(v) for k, v in enumerate(combos)}}


def tile_classes(tile):
    native, scale, offset, modern, _ = las_records.records(cr.NATIVE/f"{tile}.las")
    esri, _, _, esri_modern, _ = las_records.records(cr.esri_path(tile))
    clean = las_records.clean_flags(np.asarray(native["flags"]), modern)
    xyz = np.column_stack([np.asarray(native[a])*scale[i]+offset[i] for i, a in enumerate("xyz")])
    roof = {"native": cr.classes(native, modern) == cr.BUILDING,
            "fractal": cr.fractal_building(tile, native, scale, offset),
            "esri": cr.classes(esri, esri_modern) == cr.BUILDING}
    votes = sum(roof[n].astype(np.uint8) for n in cr.SOURCES)
    roof["consensus"] = votes >= cr.MIN_VOTES
    return xyz, clean, roof


def check_labels():
    from scipy.spatial import cKDTree
    xyz, clean, roof = tile_classes(TILE)
    keep = np.flatnonzero(clean)
    tree = cKDTree(xyz[keep, :2])
    tally = {name: {"roof_parts": 0, "roof_called_roof": 0, "other_parts": 0, "other_called_roof": 0,
                    "other_called_roof_by_label": {}} for name in NAMES}
    parts_seen, empty = 0, 0
    for packet, snapshot in SNAPSHOTS:
        document = json.loads((REVIEW/packet/"packet.json").read_text(encoding="utf-8"))
        units = {u["UNIT_ID"]: u for u in document["units"]}
        for row in tr.load_snapshot(REVIEW/"snapshots"/snapshot, document):
            if not row.get("LABEL"):
                continue
            unit = {**units[row["UNIT_ID"]], **row}
            radius = float(unit.get("PATCH_R_M") or tr.PATCH_RADIUS_M)
            near = keep[np.asarray(tree.query_ball_point([float(unit["X"]), float(unit["Y"])], radius), dtype=np.int64)]
            parts = tr.answer_parts(unit, row)
            z = xyz[near, 2]
            for k, (label, z_low, z_high) in enumerate(parts):
                if label not in ROOF | NOT_ROOF:
                    continue
                # A split's lower part takes the points at or below SPLIT_Z (as the training export); the upper part
                # (listed first) only those above it.
                above = z > z_low if (len(parts) == 2 and k == 0) else z >= z_low
                inside = near[above & (z <= z_high)]
                if not len(inside):
                    empty += 1
                    continue
                parts_seen += 1
                for name in NAMES:
                    called = roof[name][inside].mean() > 0.5
                    t = tally[name]
                    if label in ROOF:
                        t["roof_parts"] += 1
                        t["roof_called_roof"] += int(called)
                    else:
                        t["other_parts"] += 1
                        t["other_called_roof"] += int(called)
                        if called:
                            t["other_called_roof_by_label"][label] = t["other_called_roof_by_label"].get(label, 0)+1
    for t in tally.values():
        t["roof_recall"] = round(t["roof_called_roof"]/max(t["roof_parts"], 1), 4)
        t["false_roof_rate"] = round(t["other_called_roof"]/max(t["other_parts"], 1), 4)
    return {"tile": TILE, "snapshots": [s for _, s in SNAPSHOTS], "parts": parts_seen, "parts_without_points": empty,
            "by_source": tally}


def check_footprints(root, g):
    from osgeo import gdal, ogr
    gdal.UseExceptions()
    fp = json.loads((cr.OCT19/"footprints"/"footprints.json").read_text(encoding="utf-8"))["footprints"]
    gdb, layer_name = str(Path(fp).parent), Path(fp).name
    src = ogr.Open(gdb)
    layer = src.GetLayerByName(layer_name)
    mem = gdal.GetDriverByName("MEM").Create("", g["cols"], g["rows"], 1, gdal.GDT_Byte)
    mem.SetGeoTransform(g["geotransform"])
    mem.SetProjection(g["projection"])
    gdal.RasterizeLayer(mem, [1], layer, burn_values=[1])          # cell centres, as the October 19 summaries
    inside = mem.GetRasterBand(1)
    out = {name: {"roof_cells": 0, "inside_footprint": 0, "outside_footprint": 0} for name in NAMES}
    bands = {name: band(root/f"roof_elevation_{name}_m.tif") for name in NAMES}
    observed_ds, observed = band(cr.OCT19/"observed.tif")
    footprint_cells = 0
    for r0 in range(0, g["rows"], 512):
        n = min(512, g["rows"]-r0)
        f = inside.ReadAsArray(0, r0, g["cols"], n) == 1
        for name in NAMES:
            ds, b = bands[name]
            has = b.ReadAsArray(0, r0, g["cols"], n) != b.GetNoDataValue()
            out[name]["roof_cells"] += int(has.sum())
            out[name]["inside_footprint"] += int((has & f).sum())
            out[name]["outside_footprint"] += int((has & ~f).sum())
        city = observed.ReadAsArray(0, r0, g["cols"], n) != observed.GetNoDataValue()
        footprint_cells += int((f & city).sum())
    observed_ds = bands = None
    for name in NAMES:
        o = out[name]
        o["share_outside"] = round(o["outside_footprint"]/max(o["roof_cells"], 1), 4)
        o["footprint_cells_covered"] = round(o["inside_footprint"]/max(footprint_cells, 1), 4)
    src = mem = None
    return {"footprint_layer": fp, "footprint_cells_in_city": footprint_cells, "by_source": out}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    manifest = json.loads((args.root/"manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise ValueError("The consensus run is not complete")
    g = cr.grid()
    report = {"root": str(args.root), "rasters": check_rasters(args.root, g)}
    print(json.dumps(report["rasters"], indent=1), flush=True)
    report["labels"] = check_labels()
    print(json.dumps({n: {k: v for k, v in t.items() if k != "other_called_roof_by_label"}
                      for n, t in report["labels"]["by_source"].items()}, indent=1), flush=True)
    report["footprints"] = check_footprints(args.root, g)
    print(json.dumps(report["footprints"]["by_source"], indent=1), flush=True)
    out = args.out or args.root/"verification.json"
    if out.exists():
        raise FileExistsError(out)
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
