"""Consensus roof rasters for Millcreek from three independent building opinions per lidar point (October 21, 2026).

    python reviews/2026-10-21/roof-consensus/consensus_roofs.py NEW_ROOT [--tiles 12TVL2804 ...]

Run with the Myria3D environment's Python (numpy, GDAL; PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT set). Read-only on every input;
writes a NEW folder. Decided with Brian on October 21: a point is roof when at least two of three sources call it building.

The three opinions, one per point of the October 8 working LAS (all three files hold the same points in the same order, which
is checked on the raw X, Y and Z of every point):
- native: the October 8 classification (runs/city-count-20261008/prepared/points), the one the October 19 roofs used;
- fractal: FRACTAL's own opinion, the majority of its three passes (fractal/city-20261019/fractal/<tile>/consensus.las,
  MajorityClassification; a point copy of the colourised working LAS, checked on X, Y and Z);
- esri: Esri's pretrained building model (runs/esri-building-20261020/<tile>/building, tiles with integrity.json only).
The first build (October 21, kept as roof-consensus-20261021-rulesv2) used the rules-v2 refined copy as the FRACTAL vote. That
copy keeps the native class wherever the rules did not act (rule 12, building called ground, is only proposed), so it repeats
the native vote: on Brian's labels the consensus then called 34 ground parts roof. With FRACTAL's raw majority the two votes are
independent: roof recall 412 of 444 parts (rules-v2 vote 416), false roofs 22 of 773 (60). The variant was chosen after seeing
those labels, so its figures are slightly optimistic; the independence argument does not depend on them.

Rasters are built exactly as the October 19 roofs (canopy.rasters.build_chm): the maximum elevation per 0.5 m cell of class-6
first and single returns, excluding withheld, overlap and synthetic points, on the October 19 city grid (roof_elevation_m.tif),
NoData outside the city (observed.tif). The native raster must reproduce October 19's roof_elevation_m.tif; the run records
how closely it does in manifest.json before anything else is trusted.

Writes roof_elevation_{native,fractal,esri,consensus}_m.tif, roof_height_consensus_m.tif (consensus minus the October 19
terrain_m.tif, negative values kept), building_sources.tif (per cell, which sources have a roof point: 1 native, 2 fractal,
4 esri, summed; 0 none; NoData outside the city) and manifest.json with per-tile counts. Working arrays are disk-backed in
NEW_ROOT/work and can be deleted after the run.
"""
import argparse
import datetime
import json
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
from canopy import las_records  # noqa: E402
from canopy.lidar_root import lidar_root  # noqa: E402

RUNS = lidar_root()/"2023-salt-lake-valley"/"runs"
NATIVE = RUNS/"city-count-20261008"/"prepared"/"points"
FRACTAL = RUNS.parent/"fractal"/"city-20261019"/"fractal"          # <tile>/consensus.las
ESRI = RUNS/"esri-building-20261020"
OCT19 = RUNS/"millcreek-products-20261019"
SOURCES = ("native", "fractal", "esri")
BITS = {"native": 1, "fractal": 2, "esri": 4}
BUILDING = 6
MIN_VOTES = 2
NODATA = np.float32(-3.4028234663852886e+38)


def classes(block, modern):
    return np.asarray(block["classification"] if modern else block["classification"] & 31)


def esri_path(tile):
    root = ESRI/tile
    if not (root/"integrity.json").is_file():
        raise FileNotFoundError(f"{tile}: the Esri run has no verified output (integrity.json)")
    return root/"building"/f"{tile}.las"


def grid():
    from osgeo import gdal
    gdal.UseExceptions()
    ds = gdal.Open(str(OCT19/"roof_elevation_m.tif"))
    x0, cell, _, y0, _, neg = ds.GetGeoTransform()
    if cell != 0.5 or neg != -0.5:
        raise ValueError("Unexpected October 19 grid")
    return {"x0": x0, "y0": y0, "cell": cell, "cols": ds.RasterXSize, "rows": ds.RasterYSize,
            "projection": ds.GetProjection(), "geotransform": ds.GetGeoTransform()}


def cell_index(x, y, g):
    """Flat cell index on the city grid as ArcGIS LasDatasetToRaster bins, -1 off the grid.

    A point on a vertical cell edge goes to the cell on its right (floor), one on a horizontal edge to the cell above
    (ceil - 1 counted from the top). With 1 cm coordinates about 4% of cells hold an edge point; this convention, and only
    it of the four, reproduced every October 19 roof cell of 12TVL2804 exactly (October 21). Rounding to 1e-9 cells keeps
    floating-point error from moving a point that lies exactly on an edge.
    """
    col = np.floor(np.round((x-g["x0"])/g["cell"], 9)).astype(np.int64)
    row = (np.ceil(np.round((g["y0"]-y)/g["cell"], 9))-1).astype(np.int64)
    ok = (col >= 0) & (col < g["cols"]) & (row >= 0) & (row < g["rows"])
    return np.where(ok, row*g["cols"]+col, -1)


def max_into(target, index, z):
    """target[index] = max(target[index], z) for many points, NaN meaning empty."""
    keep = index >= 0
    index, z = index[keep], z[keep]
    if not len(index):
        return 0
    order = np.argsort(index, kind="stable")
    index, z = index[order], z[order]
    starts = np.flatnonzero(np.r_[True, index[1:] != index[:-1]])
    cells = index[starts]
    best = np.maximum.reduceat(z, starts).astype(np.float32)
    target[cells] = np.fmax(target[cells], best)
    return len(cells)


def fractal_building(tile, native, scale, offset):
    """FRACTAL's three-pass majority says building, per working-LAS point."""
    return fractal_classes(tile, native, scale, offset) == BUILDING


def fractal_classes(tile, native, scale, offset, chunk=2_000_000):
    """FRACTAL's three-pass majority class (0 = tie) per working-LAS point; the point order is checked on X, Y and Z."""
    import laspy
    out = np.zeros(len(native), np.uint8)
    start = 0
    with laspy.open(FRACTAL/tile/"consensus.las") as reader:
        if reader.header.point_count != len(native):
            raise ValueError(f"{tile}: FRACTAL consensus has another point count")
        for block in reader.chunk_iterator(chunk):
            stop = start+len(block)
            for i, axis in enumerate("xyz"):
                mine = np.asarray(native[axis][start:stop])*scale[i]+offset[i]
                if not np.allclose(np.asarray(getattr(block, axis)), mine, atol=1e-6, rtol=0):
                    raise ValueError(f"{tile}: FRACTAL consensus points are not the working LAS points in order ({axis})")
            out[start:stop] = np.asarray(block["MajorityClassification"])
            start = stop
    return out


def tile_job(tile, g, arrays, flags):
    blocks = {"native": las_records.records(NATIVE/f"{tile}.las"), "esri": las_records.records(esri_path(tile))}
    native, scale, offset, modern, _ = blocks["native"]
    n = len(native)
    other, s2, o2, m2, _ = blocks["esri"]
    if len(other) != n or list(s2) != list(scale) or list(o2) != list(offset) or m2 != modern:
        raise ValueError(f"{tile}: esri LAS differs from the working LAS in size or header")
    for axis in "xyz":
        if not np.array_equal(np.asarray(other[axis]), np.asarray(native[axis])):
            raise ValueError(f"{tile}: esri LAS points are not the working LAS points in order ({axis})")
    first, _ = las_records.return_masks(np.asarray(native["returns"]), modern)
    eligible = first & las_records.clean_flags(np.asarray(native["flags"]), modern)
    says = {"native": (classes(native, modern) == BUILDING) & eligible,
            "fractal": fractal_building(tile, native, scale, offset) & eligible,
            "esri": (classes(other, m2) == BUILDING) & eligible}
    votes = sum(says[name].astype(np.uint8) for name in SOURCES)
    says["consensus"] = votes >= MIN_VOTES
    pick = np.flatnonzero(votes > 0)
    x = native["x"][pick]*scale[0]+offset[0]
    y = native["y"][pick]*scale[1]+offset[1]
    z = native["z"][pick]*scale[2]+offset[2]
    index = cell_index(x, y, g)
    record = {"points": int(n), "eligible_first_clean": int(eligible.sum()), "off_grid_building_points": int((index < 0).sum()),
              "building_points": {k: int(v.sum()) for k, v in says.items()},
              "votes": {str(k): int((votes[eligible] == k).sum()) for k in range(4)}, "cells": {}}
    for name, mask in says.items():
        sub = mask[pick]
        record["cells"][name] = max_into(arrays[name], index[sub], z[sub])
        if name in BITS:
            cells = np.unique(index[sub & (index >= 0)])
            flags[cells] |= np.uint8(BITS[name])
    blocks.clear()
    return record


def write_tif(path, array2d, g, dtype, nodata, description):
    from osgeo import gdal
    driver = gdal.GetDriverByName("GTiff")
    gdt = {"float32": gdal.GDT_Float32, "uint8": gdal.GDT_Byte}[dtype]
    ds = driver.Create(str(path), g["cols"], g["rows"], 1, gdt,
                       options=["TILED=YES", "COMPRESS=DEFLATE", "BIGTIFF=IF_SAFER", "BLOCKXSIZE=256", "BLOCKYSIZE=256"])
    ds.SetGeoTransform(g["geotransform"])
    ds.SetProjection(g["projection"])
    band = ds.GetRasterBand(1)
    band.SetNoDataValue(float(nodata))
    band.SetDescription(description)
    step = 512
    for r0 in range(0, g["rows"], step):
        band.WriteArray(np.ascontiguousarray(array2d(r0, min(r0+step, g["rows"]))), 0, r0)
    band.FlushCache()
    ds = None


def read_rows(path, r0, r1):
    from osgeo import gdal
    ds = gdal.Open(str(path))
    band = ds.GetRasterBand(1)
    out = band.ReadAsArray(0, r0, ds.RasterXSize, r1-r0)
    band = ds = None
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path)
    parser.add_argument("--tiles", nargs="*")
    args = parser.parse_args(argv)
    if args.out.exists():
        raise FileExistsError(args.out)
    tiles = args.tiles or sorted(p.stem for p in NATIVE.glob("*.las"))
    g = grid()
    work = args.out/"work"
    work.mkdir(parents=True)
    size = g["rows"]*g["cols"]
    arrays = {}
    for name in (*SOURCES, "consensus"):
        arrays[name] = np.lib.format.open_memmap(work/f"{name}.npy", mode="w+", dtype=np.float32, shape=(size,))
        arrays[name][:] = np.nan
    flags = np.lib.format.open_memmap(work/"sources.npy", mode="w+", dtype=np.uint8, shape=(size,))
    manifest = {"status": "running", "started": datetime.datetime.now().isoformat(timespec="seconds"),
                "rule": f"roof where at least {MIN_VOTES} of {list(SOURCES)} say class {BUILDING}",
                "inputs": {"native": str(NATIVE), "fractal": str(FRACTAL), "esri": str(ESRI), "grid": str(OCT19/"roof_elevation_m.tif")},
                "method": "max elevation per 0.5 m cell of first/single returns, withheld/overlap/synthetic excluded (as canopy.rasters.build_chm)",
                "tiles": {}}
    path = args.out/"manifest.json"

    def save():
        path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    save()
    try:
        for i, tile in enumerate(tiles, 1):
            t0 = time.time()
            manifest["tiles"][tile] = {**tile_job(tile, g, arrays, flags), "seconds": round(time.time()-t0, 1)}
            for a in (*arrays.values(), flags):
                a.flush()
            save()
            print(f"{datetime.datetime.now():%H:%M:%S} {tile} ({i}/{len(tiles)}): "
                  f"{manifest['tiles'][tile]['building_points']} in {manifest['tiles'][tile]['seconds']} s", flush=True)
        # City mask: October 19 observed.tif is NoData outside the municipal boundary.
        observed = OCT19/"observed.tif"
        from osgeo import gdal
        observed_ds = gdal.Open(str(observed))          # keep the dataset alive while its band is read
        city_nodata = observed_ds.GetRasterBand(1).GetNoDataValue()
        observed_ds = None

        def masked(name):
            def rows(r0, r1):
                out = arrays[name][r0*g["cols"]:r1*g["cols"]].reshape(r1-r0, g["cols"]).copy()
                outside = read_rows(observed, r0, r1) == city_nodata
                out[np.isnan(out) | outside] = NODATA
                return out
            return rows

        for name in (*SOURCES, "consensus"):
            write_tif(args.out/f"roof_elevation_{name}_m.tif", masked(name), g, "float32", NODATA,
                      f"Roof elevation (m), {name} building points; max first/single return per 0.5 m cell")

        def height(r0, r1):
            roof = masked("consensus")(r0, r1)
            ground = read_rows(OCT19/"terrain_m.tif", r0, r1)
            out = np.full(roof.shape, NODATA, np.float32)
            ok = (roof != NODATA) & (ground > -1e30)
            out[ok] = roof[ok]-ground[ok]
            return out

        write_tif(args.out/"roof_height_consensus_m.tif", height, g, "float32", NODATA,
                  "Consensus roof elevation minus October 19 terrain (m); negative values kept")

        def sources(r0, r1):
            out = flags[r0*g["cols"]:r1*g["cols"]].reshape(r1-r0, g["cols"]).copy()
            out[read_rows(observed, r0, r1) == city_nodata] = 255
            return out

        write_tif(args.out/"building_sources.tif", sources, g, "uint8", 255,
                  "Sources with a roof point in the cell: 1 native + 2 fractal + 4 esri; 0 none")
        manifest.update(status="complete", finished=datetime.datetime.now().isoformat(timespec="seconds"))
        save()
    except BaseException as exc:
        manifest.update(status="failed", error=repr(exc))
        save()
        raise


if __name__ == "__main__":
    main()
