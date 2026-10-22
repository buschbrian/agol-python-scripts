"""Rebuild Millcreek's canopy rasters from the combined classification (October 22, 2026).

    python reviews/2026-10-22/canopy-rebuild/canopy_rebuild.py NEW_ROOT [--tiles 12TVL2804 ...]

Run with the Myria3D environment's Python (numpy, laspy, GDAL; PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT set). Read-only on every
input; writes a NEW folder. Decided with Brian: roofs first, then canopy (October 21); go ahead, and points classed 1 (other)
or 64 (permanent structure) count as observed non-canopy (October 22).

The combined class of each point of the October 8 working LAS:
- building (6) where the roof consensus says so: at least two of the native class, FRACTAL's three-pass majority and the Esri
  model call it building (../../2026-10-21/roof-consensus);
- otherwise the refinement rules-v2 class (runs/refined-fractal-20261020/points), except where rules v2 says building but the
  consensus does not: then the native class, or FRACTAL's majority where the native class is the building (a tie becomes 1).
The combined classes are saved per tile as NEW_ROOT/classes/<tile>.npy (uint8, working-LAS point order) for later LAS copies.

Rasters follow canopy.rasters.build_chm as the October 8 count ran it (building clearance 0.35 m, classified background off),
from first and single returns without withheld, overlap or synthetic points, binned on the October 19 city grid with the
ArcGIS edge rule (consensus_roofs.cell_index), against the October 19 terrain (terrain_m.tif, not rebuilt):
- vegetation DSM: maximum of classes 3, 4, 5; building DSM: maximum of class 6; non-canopy: any point of the non-canopy classes;
- occluded where a building is more than 0.35 m above the vegetation in the cell; support where vegetation and not occluded;
- observed where terrain exists and the cell holds vegetation or non-canopy; CHM = vegetation minus terrain (negatives 0, 0 where
  occluded or without vegetation), NoData where not observed or outside the city.
Two versions are built in the same pass. "native" uses the October 8 classes and non-canopy list and must reproduce October 19's
chm_m.tif, observed.tif, vegetation_support.tif and building_occlusion.tif cell for cell (checked, written to manifest.json);
"combined" uses the combined classes with 1 and 64 added to the non-canopy list and is written as GeoTIFFs in NEW_ROOT with
October 19's encodings (float32 CHM; byte masks 0/1, NoData 3 outside the city).
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
sys.path.insert(0, str(TOOLBOX/"reviews"/"2026-10-21"/"roof-consensus"))
from canopy import las_records  # noqa: E402
import consensus_roofs as cr  # noqa: E402

REFINED = cr.RUNS/"refined-fractal-20261020"/"points"
VEGETATION = (3, 4, 5)
NON_CANOPY_OCT8 = (2, 6, 9, 10, 11, 13, 14, 15, 16, 17, 20)            # canopy.rasters.NON_CANOPY_CLASSES
NON_CANOPY_COMBINED = (*NON_CANOPY_OCT8, 1, 64)                          # Brian, October 22
CLEARANCE_M = np.float32(0.35)
VERSIONS = {"native": NON_CANOPY_OCT8, "combined": NON_CANOPY_COMBINED}
BYTE_NODATA = 3


def combined_classes(native_c, refined_c, fractal_c, consensus):
    """The combined class per point (see the module docstring)."""
    out = refined_c.copy()
    overruled = (refined_c == cr.BUILDING) & ~consensus
    fallback = np.where(native_c != cr.BUILDING, native_c, fractal_c)
    fallback[fallback == 0] = 1                                          # a FRACTAL tie stays unlabelled-but-observed
    out[overruled] = fallback[overruled]
    out[consensus] = cr.BUILDING
    return out


def tile_job(tile, g, arrays, out_classes):
    native, scale, offset, modern, _ = las_records.records(cr.NATIVE/f"{tile}.las")
    n = len(native)
    others = {"esri": las_records.records(cr.esri_path(tile)), "refined": las_records.records(REFINED/f"{tile}.las")}
    for name, (block, s2, o2, m2, _) in others.items():
        if len(block) != n or list(s2) != list(scale) or list(o2) != list(offset):
            raise ValueError(f"{tile}: {name} LAS differs from the working LAS in size or header")
        for axis in "xyz":
            if not np.array_equal(np.asarray(block[axis]), np.asarray(native[axis])):
                raise ValueError(f"{tile}: {name} LAS points are not the working LAS points in order ({axis})")
    native_c = cr.classes(native, modern)
    esri_c = cr.classes(others["esri"][0], others["esri"][3])
    refined_c = cr.classes(others["refined"][0], others["refined"][3])
    fractal_c = cr.fractal_classes(tile, native, scale, offset)
    first, _ = las_records.return_masks(np.asarray(native["returns"]), modern)
    eligible = first & las_records.clean_flags(np.asarray(native["flags"]), modern)
    votes = ((native_c == cr.BUILDING).astype(np.uint8)+(fractal_c == cr.BUILDING)+(esri_c == cr.BUILDING))
    consensus = votes >= cr.MIN_VOTES
    combined = combined_classes(native_c, refined_c, fractal_c, consensus)
    np.save(out_classes/f"{tile}.npy", combined)
    x = native["x"]*scale[0]+offset[0]
    y = native["y"]*scale[1]+offset[1]
    z = native["z"]*scale[2]+offset[2]
    index = cr.cell_index(x, y, g)
    index[~eligible] = -1
    record = {"points": int(n), "eligible": int(eligible.sum()), "changed_from_native": int((combined != native_c).sum()),
              "combined_classes": {str(int(k)): int(v) for k, v in zip(*np.unique(combined, return_counts=True))}}
    for version, classes in (("native", native_c), ("combined", combined)):
        veg = np.isin(classes, VEGETATION)
        bld = classes == cr.BUILDING
        non = np.isin(classes, VERSIONS[version])
        cr.max_into(arrays[version]["veg"], np.where(veg, index, -1), z)
        cr.max_into(arrays[version]["bld"], np.where(bld, index, -1), z)
        cells = np.unique(index[non & (index >= 0)])
        arrays[version]["non"][cells] = 1
    return record


def tile_rows_cols(tile, g):
    """Grid rows and columns covered by a 1 km tile named like 12TVL2804 (easting 428 km, northing 4504 km)."""
    e, n = 400000+int(tile[5:7])*1000, 4500000+int(tile[7:9])*1000
    c0, c1 = int((e-g["x0"])/g["cell"]), int((e+1000-g["x0"])/g["cell"])
    r0, r1 = int((g["y0"]-(n+1000))/g["cell"]), int((g["y0"]-n)/g["cell"])
    return max(r0, 0), min(r1, g["rows"]), max(c0, 0), min(c1, g["cols"])


def rasters(arrays, version, g, r0, r1, terrain=None):
    """CHM, observed, support and occlusion rows for one version, before the city mask (canopy.rasters.build_chm).
    terrain: the terrain raster on the same grid; October 19's city-clipped terrain_m.tif by default, terrain_context.tif for
    the October 8 count's canonical CHM (city plus a 20 m margin)."""
    sl = slice(r0*g["cols"], r1*g["cols"])
    shape = (r1-r0, g["cols"])
    veg = arrays[version]["veg"][sl].reshape(shape)
    bld = arrays[version]["bld"][sl].reshape(shape)
    non = arrays[version]["non"][sl].reshape(shape) == 1
    dtm = cr.read_rows(terrain or cr.OCT19/"terrain_m.tif", r0, r1).astype(np.float32)
    has_dtm = dtm > -1e30
    has_veg, has_bld = ~np.isnan(veg), ~np.isnan(bld)
    occluded = has_bld & has_veg & (bld > veg+CLEARANCE_M)
    support = has_veg & ~occluded
    observed = has_dtm & (has_veg | non)
    difference = (veg-dtm).astype(np.float32)
    heights = np.where(~has_veg | occluded, np.float32(0), np.where(difference < 0, np.float32(0), difference))
    chm = np.where(observed, heights, np.nan).astype(np.float32)
    return chm, observed, support, occluded


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path)
    parser.add_argument("--tiles", nargs="*")
    args = parser.parse_args(argv)
    if args.out.exists():
        raise FileExistsError(args.out)
    tiles = args.tiles or sorted(p.stem for p in cr.NATIVE.glob("*.las"))
    g = cr.grid()
    work, out_classes = args.out/"work", args.out/"classes"
    work.mkdir(parents=True)
    out_classes.mkdir()
    size = g["rows"]*g["cols"]
    arrays = {}
    for version in VERSIONS:
        arrays[version] = {}
        for key, dtype, fill in (("veg", np.float32, np.nan), ("bld", np.float32, np.nan), ("non", np.uint8, 0)):
            a = np.lib.format.open_memmap(work/f"{version}_{key}.npy", mode="w+", dtype=dtype, shape=(size,))
            a[:] = fill
            arrays[version][key] = a
    manifest = {"status": "running", "started": datetime.datetime.now().isoformat(timespec="seconds"),
                "non_canopy": {k: list(v) for k, v in VERSIONS.items()}, "clearance_m": float(CLEARANCE_M),
                "inputs": {"native": str(cr.NATIVE), "refined_v2": str(REFINED), "fractal": str(cr.FRACTAL), "esri": str(cr.ESRI),
                           "terrain_and_grid": str(cr.OCT19)}, "tiles": {}}
    path = args.out/"manifest.json"

    def save():
        path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    save()
    try:
        for i, tile in enumerate(tiles, 1):
            t0 = time.time()
            manifest["tiles"][tile] = {**tile_job(tile, g, arrays, out_classes), "seconds": round(time.time()-t0, 1)}
            for version in arrays.values():
                for a in version.values():
                    a.flush()
            save()
            print(f"{datetime.datetime.now():%H:%M:%S} {tile} ({i}/{len(tiles)}): "
                  f"{manifest['tiles'][tile]['changed_from_native']:,} points changed in {manifest['tiles'][tile]['seconds']} s",
                  flush=True)
        manifest["status"] = "writing"
        save()
        from osgeo import gdal
        gdal.UseExceptions()
        oct19 = {name: gdal.Open(str(cr.OCT19/f"{name}.tif")) for name in ("chm_m", "observed", "vegetation_support", "building_occlusion")}
        city_nodata = oct19["observed"].GetRasterBand(1).GetNoDataValue()
        check = {k: {"cells_compared": 0, "mismatches": 0} for k in oct19}
        check["chm_m"]["max_abs_difference_m"] = 0.0
        summary = {v: {"observed": 0, "canopy_2m": 0, "support": 0, "occluded": 0} for v in VERSIONS}
        driver = gdal.GetDriverByName("GTiff")
        opts = ["TILED=YES", "COMPRESS=DEFLATE", "BIGTIFF=IF_SAFER", "BLOCKXSIZE=256", "BLOCKYSIZE=256"]
        outs = {}
        for name, gdt, nodata in (("chm_m", gdal.GDT_Float32, float(cr.NODATA)), ("observed", gdal.GDT_Byte, BYTE_NODATA),
                                  ("vegetation_support", gdal.GDT_Byte, BYTE_NODATA), ("building_occlusion", gdal.GDT_Byte, BYTE_NODATA)):
            ds = driver.Create(str(args.out/f"{name}.tif"), g["cols"], g["rows"], 1, gdt, options=opts)
            ds.SetGeoTransform(g["geotransform"])
            ds.SetProjection(g["projection"])
            ds.GetRasterBand(1).SetNoDataValue(nodata)
            outs[name] = ds
        for r0 in range(0, g["rows"], 512):
            r1 = min(r0+512, g["rows"])
            ref = {k: ds.GetRasterBand(1).ReadAsArray(0, r0, g["cols"], r1-r0) for k, ds in oct19.items()}
            outside = ref["observed"] == city_nodata
            if args.tiles:                                  # a partial run checks and summarizes only its own tiles
                mine = np.zeros_like(outside)
                for tile in tiles:
                    a0, a1, b0, b1 = tile_rows_cols(tile, g)
                    if a1 > r0 and a0 < r1:
                        mine[max(a0, r0)-r0:min(a1, r1)-r0, b0:b1] = True
                outside = outside | ~mine
            for version in VERSIONS:
                chm, observed, support, occluded = rasters(arrays, version, g, r0, r1)
                inside = ~outside
                s = summary[version]
                s["observed"] += int((observed & inside).sum())
                s["canopy_2m"] += int(((chm >= 2) & observed & inside).sum())
                s["support"] += int((support & inside).sum())
                s["occluded"] += int((occluded & inside).sum())
                masks = {"observed": observed, "vegetation_support": support, "building_occlusion": occluded}
                if version == "native":
                    for k, m in masks.items():
                        check[k]["cells_compared"] += int(inside.sum())
                        check[k]["mismatches"] += int((m.astype(np.uint8)[inside] != ref[k][inside]).sum())
                    old = ref["chm_m"].astype(np.float32)
                    old_has = old > -1e30
                    new_has = ~np.isnan(chm)
                    check["chm_m"]["cells_compared"] += int(inside.sum())
                    check["chm_m"]["mismatches"] += int(((old_has != new_has) & inside).sum())
                    both = old_has & new_has & inside
                    if both.any():
                        d = np.abs(old[both]-chm[both])
                        check["chm_m"]["max_abs_difference_m"] = max(check["chm_m"]["max_abs_difference_m"], float(d.max()))
                        check["chm_m"]["mismatches"] += int((d > 1e-4).sum())
                else:
                    chm_out = np.where(np.isnan(chm) | outside, cr.NODATA, chm).astype(np.float32)
                    outs["chm_m"].GetRasterBand(1).WriteArray(chm_out, 0, r0)
                    for k, m in masks.items():
                        b = m.astype(np.uint8)
                        b[outside] = BYTE_NODATA
                        outs[k].GetRasterBand(1).WriteArray(b, 0, r0)
        for ds in outs.values():
            ds.FlushCache()
        outs = oct19 = None
        manifest["native_reproduces_oct19"] = check
        manifest["native_reproduces_oct19_exactly"] = all(v["mismatches"] == 0 for v in check.values())
        manifest["city_summary"] = summary
        manifest.update(status="complete", finished=datetime.datetime.now().isoformat(timespec="seconds"))
        save()
        print(json.dumps({k: manifest[k] for k in ("native_reproduces_oct19", "native_reproduces_oct19_exactly", "city_summary")},
                         indent=1))
    except BaseException as exc:
        manifest.update(status="failed", error=repr(exc))
        save()
        raise


if __name__ == "__main__":
    main()
