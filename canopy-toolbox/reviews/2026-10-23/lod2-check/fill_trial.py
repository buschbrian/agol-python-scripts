r"""Trial of a fixed height source for the massing on 12TVL2804 (October 23, 2026).

    python reviews/2026-10-23/lod2-check/fill_trial.py OUT          the pilot tile's footprints
    python reviews/2026-10-23/lod2-check/fill_trial.py OUT --city   every footprint (about an hour; run in the background)

The October 22 massing (run_massing.py) fed Extract LOD2 Buildings the consensus roof where there is one and the terrain
everywhere else, including footprint cells the lidar did not see as roof (tree overhang, dark or wet roofs, edges). The
tool then modelled those parts of the building at ground level. This trial fills each footprint's missing roof cells
with the nearest roof cell of the same footprint and leaves terrain outside the footprints (and under footprints with no
roof cell at all), then runs the tool exactly as run_massing.py does, on the pilot tile's footprints. Check the result
with `lod2_check.py rasterize OUT --pilot --massing OUT\massing.gdb` (into a new folder), then `measure`.

ArcGIS Pro Python with 3D Analyst and Spatial Analyst (PYTHONNOUSERSITE=1). Writes only under OUT.
"""
import argparse
import datetime
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
from canopy.lidar_root import lidar_root  # noqa: E402

VALLEY = lidar_root()/"2023-salt-lake-valley"
ROOF = VALLEY/"runs"/"millcreek-products-20261022"/"roof_elevation_m.tif"
TERRAIN = VALLEY/"runs"/"millcreek-products-20261019"/"terrain_context.tif"
MASSING = VALLEY/"runs"/"massing-20261022"/"massing.gdb"
PILOT_TILE = (428000.0, 4504000.0, 429000.0, 4505000.0)        # 12TVL2804, the labelled tile
LEVELS = {"lod12": "LOD1.2", "lod20": "LOD2.0"}
CELL = 0.5
HALO = 50.0                                                     # metres around the tile, so edge footprints are whole


def filled(fp, roof, terrain):
    """Roof where there is one; inside a footprint, the nearest roof cell of that footprint; terrain elsewhere."""
    from scipy import ndimage
    out = np.where(np.isnan(roof), terrain, roof)
    filled_cells = 0
    for fid, sl in enumerate(ndimage.find_objects(fp), start=1):
        if sl is None:
            continue
        mine = fp[sl] == fid
        have = mine & ~np.isnan(roof[sl])
        need = mine & np.isnan(roof[sl])
        if not have.any() or not need.any():
            continue
        _, (iy, ix) = ndimage.distance_transform_edt(~have, return_indices=True)
        block = out[sl]
        block[need] = roof[sl][iy[need], ix[need]]
        filled_cells += int(need.sum())
    return out, filled_cells


def main(argv=None):
    import arcpy
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out", type=Path)
    p.add_argument("--city", action="store_true", help="every footprint on the whole roof grid, not the pilot tile")
    a = p.parse_args(argv)
    arcpy.CheckOutExtension("3D")
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    started = datetime.datetime.now().isoformat(timespec="seconds")
    x0, y0, x1, y1 = PILOT_TILE
    x0, y0, x1, y1 = x0-HALO, y0-HALO, x1+HALO, y1+HALO
    sr = arcpy.Describe(str(ROOF)).spatialReference
    if a.city:
        e = arcpy.Describe(str(ROOF)).extent
        x0, y0, x1, y1 = e.XMin, e.YMin, e.XMax, e.YMax
    gdb = Path(arcpy.management.CreateFileGDB(str(out), "massing.gdb")[0])
    layer = arcpy.management.MakeFeatureLayer(str(MASSING/"footprints"), "fp").getOutput(0)
    box = arcpy.Polygon(arcpy.Array([arcpy.Point(*PILOT_TILE[:2]), arcpy.Point(PILOT_TILE[2], PILOT_TILE[1]),
                                     arcpy.Point(*PILOT_TILE[2:]), arcpy.Point(PILOT_TILE[0], PILOT_TILE[3])]), sr)
    if not a.city:
        arcpy.management.SelectLayerByLocation(layer, "INTERSECT", box)
    footprints = str(gdb/"footprints")
    arcpy.management.CopyFeatures(layer, footprints)
    extent = f"{x0} {y0} {x1} {y1}"
    with arcpy.EnvManager(extent=extent, snapRaster=str(ROOF), cellSize=str(ROOF), outputCoordinateSystem=sr,
                          scratchWorkspace=str(out), compression="LZW"):
        arcpy.conversion.PolygonToRaster(footprints, "FP_ID", str(out/"fp_id.tif"), "CELL_CENTER", "", CELL)
    fp_r = arcpy.Raster(str(out/"fp_id.tif"))
    ll = arcpy.Point(fp_r.extent.XMin, fp_r.extent.YMin)
    fp = arcpy.RasterToNumPyArray(fp_r, ll, nodata_to_value=0).astype(np.int32)
    rows, cols = fp.shape
    roof = arcpy.RasterToNumPyArray(str(ROOF), ll, cols, rows, nodata_to_value=np.nan).astype(np.float32)
    terrain = arcpy.RasterToNumPyArray(str(TERRAIN), ll, cols, rows, nodata_to_value=np.nan).astype(np.float32)
    surface, n_filled = filled(fp, roof, terrain)
    dsm = str(out/"height_source_filled.tif")
    r = arcpy.NumPyArrayToRaster(surface, ll, CELL, CELL, value_to_nodata=np.nan)
    arcpy.management.DefineProjection(r, sr)
    r.save(dsm)
    print(f"{int((fp > 0).sum())} footprint cells, {n_filled} filled from roof", flush=True)
    record = {"schema": "fill-trial/1", "started": started, "tile": None if a.city else PILOT_TILE, "halo_m": HALO,
              "footprints": int(arcpy.management.GetCount(footprints)[0]), "footprint_cells": int((fp > 0).sum()),
              "filled_cells": n_filled, "height_source": dsm, "outputs": {}}
    for key, level in LEVELS.items():
        t = datetime.datetime.now()
        with arcpy.EnvManager(scratchWorkspace=str(out)):
            arcpy.ddd.ExtractLOD2Buildings(dsm, footprints, str(gdb/key), level)
        arcpy.management.AddField(str(gdb/key), "TOP_Z", "DOUBLE")
        with arcpy.da.UpdateCursor(str(gdb/key), ["SHAPE@", "TOP_Z"]) as cursor:
            for shape, _ in cursor:
                if shape is None or shape.area == 0 or shape.extent.ZMax == 0:
                    cursor.deleteRow()
                else:
                    cursor.updateRow([shape, shape.extent.ZMax])
        record["outputs"][key] = {"blocks": int(arcpy.management.GetCount(str(gdb/key))[0]),
                                  "seconds": round((datetime.datetime.now()-t).total_seconds())}
        print(key, record["outputs"][key], flush=True)
    (out/"fill-trial.json").write_text(json.dumps(record, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
