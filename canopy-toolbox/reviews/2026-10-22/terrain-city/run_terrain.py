r"""Citywide terrain products from the lidar terrain (October 22, 2026): slope, aspect, curvature, hillshade, terrain
position and contours, by the planning pilot's method (canopy.planning.terrain) on the whole 0.5 m grid.

    python reviews/2026-10-22/terrain-city/run_terrain.py pilot OUT     the pilot method and this script on one window
    python reviews/2026-10-22/terrain-city/run_terrain.py run OUT       the whole grid, then the city mask
    python reviews/2026-10-22/terrain-city/run_terrain.py verify OUT    the city run against the pilot window; the mask

ArcGIS Pro Python with Spatial Analyst (PYTHONNOUSERSITE=1). Read-only on the terrain; writes only under OUT.
- Input: `millcreek-products-20261019\terrain_context.tif`, the unmasked terrain mosaic, which runs past the city and equals
  the city terrain (`terrain_m.tif`, the one in the October 22 library) on every city cell. Everything is computed on it
  and masked to the city only at the end, so neighbourhoods at the city edge are complete wherever the mosaic is.
- Products (same tools and parameters as the pilot: 3 m Surface Parameters neighbourhood, 10 m terrain-position radius,
  315/45 hillshade, 2 m contours): slope_degrees, slope_percent, aspect_degrees, profile_curvature, tangential_curvature,
  hillshade, terrain_position_m and terrain_neighborhood_complete (1 where the full 10 m neighbourhood is valid terrain),
  in OUT\context (whole grid) and OUT (city only), and contours of the city terrain in OUT\terrain.gdb.
- Drainage is left out: routing needs the whole contributing catchment, not a city-shaped grid.
- `pilot` runs canopy.planning.terrain unchanged and this script's derive() on the same window of at most 4,000,000 cells;
  `verify` compares the citywide context products with the pilot's on that window, away from its edges.
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
CONTEXT = VALLEY/"runs"/"millcreek-products-20261019"/"terrain_context.tif"
CITY = VALLEY/"runs"/"millcreek-products-20261022"/"terrain_m.tif"
NEIGHBORHOOD_M = 3.0
TPI_RADIUS_M = 10.0
CONTOUR_M = 2.0
INDEX_CONTOUR_M = 10.0
# The 1 km window of city terrain with the most relief (467 m) that is fully inside the city: 2,000 x 2,000 cells, the
# pilot's 4,000,000 limit (found by scanning every 250 m step on October 22).
PILOT = (433149.0, 4505133.0, 434149.0, 4506133.0)
RASTERS = ("slope_degrees", "slope_percent", "aspect_degrees", "profile_curvature", "tangential_curvature", "hillshade",
           "terrain_position_m")
DESCRIPTIONS = {
    "slope_degrees": f"Terrain slope in degrees, Surface Parameters with a {NEIGHBORHOOD_M:g} m neighbourhood.",
    "slope_percent": "Terrain slope in percent, tan(slope) x 100.",
    "aspect_degrees": "Geodesic downslope azimuth from north; flat cells use ArcGIS's -1 convention.",
    "profile_curvature": "Curvature along the slope (Surface Parameters).",
    "tangential_curvature": "Curvature across the slope (Surface Parameters).",
    "hillshade": "Hillshade, sun azimuth 315, altitude 45, no shadows, z factor 1. For display.",
    "terrain_position_m": f"Elevation minus mean terrain within {TPI_RADIUS_M:g} m radius. Scale-dependent relief.",
    "terrain_neighborhood_complete": f"1: the full {TPI_RADIUS_M:g} m neighbourhood is valid terrain; 0: edge affected.",
}


def derive(dtm, folder, parallel="0"):
    """This script's products for one terrain raster: the pilot's tool calls, without drainage."""
    import arcpy
    from arcpy.sa import FocalStatistics, Hillshade, NbrCircle, Raster, SurfaceParameters, Tan
    from canopy import common
    folder.mkdir(parents=True)
    paths = {}
    with arcpy.EnvManager(scratchWorkspace=str(folder), compression="LZW", pyramid="PYRAMIDS -1 NEAREST"), \
            common.environment(dtm), arcpy.EnvManager(parallelProcessingFactor=parallel):
        def save(key, raster):
            path = str(folder/f"{key}.tif")
            raster.save(path)
            paths[key] = path
            print(f"  {key}", flush=True)
        slope = SurfaceParameters(dtm, "SLOPE", neighborhood_distance=f"{NEIGHBORHOOD_M} Meters", z_unit="METER",
                                  output_slope_measurement="DEGREE")
        save("slope_degrees", slope)
        save("slope_percent", Tan(slope*(np.pi/180))*100)
        for key, parameter in (("aspect_degrees", "ASPECT"), ("profile_curvature", "PROFILE_CURVATURE"),
                               ("tangential_curvature", "TANGENTIAL_CURVATURE")):
            save(key, SurfaceParameters(dtm, parameter, neighborhood_distance=f"{NEIGHBORHOOD_M} Meters", z_unit="METER"))
        save("hillshade", Hillshade(dtm, 315, 45, "NO_SHADOWS", 1))
        save("terrain_position_m", Raster(dtm)-FocalStatistics(dtm, NbrCircle(TPI_RADIUS_M, "MAP"), "MEAN", "DATA"))
    return paths


def neighborhood_complete(dtm, path):
    """1 where every cell within TPI_RADIUS_M is valid terrain, 0 where not, NoData off the terrain (planning's rule)."""
    import arcpy
    from osgeo import gdal
    from scipy import ndimage
    gdal.UseExceptions()
    source = gdal.Open(str(dtm))
    band = source.GetRasterBand(1)
    nodata = band.GetNoDataValue()
    values = band.ReadAsArray()
    valid = np.isfinite(values) & (values != nodata)
    del values
    cell = source.GetGeoTransform()[1]
    distance = ndimage.distance_transform_edt(np.pad(valid, 1), sampling=cell)[1:-1, 1:-1]
    out = np.where(valid, (distance > max(NEIGHBORHOOD_M, TPI_RADIUS_M)).astype(np.uint8), 255).astype(np.uint8)
    del distance
    driver = gdal.GetDriverByName("GTiff")
    target = driver.Create(str(path), source.RasterXSize, source.RasterYSize, 1, gdal.GDT_Byte,
                           ["COMPRESS=LZW", "TILED=YES"])
    target.SetGeoTransform(source.GetGeoTransform())
    target.SetProjection(source.GetProjection())
    target.GetRasterBand(1).SetNoDataValue(255)
    target.GetRasterBand(1).WriteArray(out)
    target.FlushCache()
    target = None
    arcpy.management.BuildPyramids(str(path), resample_technique="NEAREST")
    return {"valid": int(valid.sum()), "complete": int((out == 1).sum())}


def run(out):
    import arcpy
    from arcpy.sa import IsNull, Raster, SetNull
    from canopy import planning
    arcpy.CheckOutExtension("Spatial")
    out = Path(out).resolve()
    if (out/"context").exists() or (out/"terrain.json").exists():
        raise FileExistsError(f"{out} already holds a run")
    out.mkdir(parents=True, exist_ok=True)            # the pilot may already be in it
    started = datetime.datetime.now().isoformat(timespec="seconds")
    print("context products", flush=True)
    context = derive(str(CONTEXT), out/"context", parallel="100%")
    context["terrain_neighborhood_complete"] = str(out/"context"/"terrain_neighborhood_complete.tif")
    counts = neighborhood_complete(CONTEXT, Path(context["terrain_neighborhood_complete"]))
    print("city mask", flush=True)
    city = {}
    outside = IsNull(Raster(str(CITY)))
    with arcpy.EnvManager(compression="LZW", pyramid="PYRAMIDS -1 NEAREST", snapRaster=str(CITY), cellSize=str(CITY),
                          extent=str(CITY), parallelProcessingFactor="100%"):
        for key in (*RASTERS, "terrain_neighborhood_complete"):
            path = str(out/f"{key}.tif")
            SetNull(outside, Raster(context[key])).save(path)
            city[key] = path
            print(f"  {key}", flush=True)
    print("contours", flush=True)
    gdb = out/"terrain.gdb"
    arcpy.management.CreateFileGDB(str(out), gdb.name)
    contours = str(gdb/"contours")
    arcpy.sa.Contour(str(CITY), contours, CONTOUR_M, 0, 1)
    arcpy.management.AddField(contours, "INDEX", "SHORT")
    arcpy.management.CalculateField(contours, "INDEX", f"1 if round(!Contour!, 3) % {INDEX_CONTOUR_M:g} == 0 else 0",
                                    "PYTHON3")
    city["contours"] = contours
    for key, path in {**city, **{f"context/{k}": v for k, v in context.items()}}.items():
        planning._metadata(path, DESCRIPTIONS.get(key.split("/")[-1],
                                                  f"Terrain contours every {CONTOUR_M:g} m (INDEX = 1 every "
                                                  f"{INDEX_CONTOUR_M:g} m), from the city terrain."))
    record = {
        "schema": "terrain-city/1", "started": started, "finished": datetime.datetime.now().isoformat(timespec="seconds"),
        "input_context": str(CONTEXT), "input_city": str(CITY), "cell_size_m": 0.5,
        "neighborhood_radius_m": NEIGHBORHOOD_M, "tpi_radius_m": TPI_RADIUS_M, "contour_interval_m": CONTOUR_M,
        "index_contour_m": INDEX_CONTOUR_M, "hillshade": {"azimuth": 315, "altitude": 45, "shadows": False, "z_factor": 1},
        "method": "canopy.planning.terrain's calls (drainage left out) on the unmasked mosaic; SetNull outside the city terrain",
        "context_cells": counts, "warning": planning.WARNING,
        "outputs": city, "context_outputs": context,
    }
    (out/"terrain.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps({"context_cells": counts}, indent=1))


def window(path, extent):
    """The raster's values over extent (on its grid) as float64, NaN where NoData or off the raster."""
    from osgeo import gdal
    gdal.UseExceptions()
    source = gdal.Open(str(path))
    gt = source.GetGeoTransform()
    x0, y0, x1, y1 = extent
    col, row = int(round((x0-gt[0])/gt[1])), int(round((gt[3]-y1)/-gt[5]))
    ncol, nrow = int(round((x1-x0)/gt[1])), int(round((y1-y0)/-gt[5]))
    out = np.full((nrow, ncol), np.nan)
    c0, r0 = max(col, 0), max(row, 0)
    c1, r1 = min(col+ncol, source.RasterXSize), min(row+nrow, source.RasterYSize)
    if c1 > c0 and r1 > r0:
        band = source.GetRasterBand(1)
        values = band.ReadAsArray(c0, r0, c1-c0, r1-r0).astype(np.float64)
        nodata = band.GetNoDataValue()
        if nodata is not None:
            values[values == np.float64(np.array(nodata, dtype=band.ReadAsArray(c0, r0, 1, 1).dtype))] = np.nan
        out[r0-row:r1-row, c0-col:c1-col] = values
    return out


def pilot(out):
    import arcpy
    from canopy import planning
    arcpy.CheckOutExtension("Spatial")
    out = Path(out).resolve()/"pilot"
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(parents=True)
    dtm = str(out/"dtm_window.tif")
    x0, y0, x1, y1 = PILOT
    arcpy.management.Clip(str(CONTEXT), f"{x0} {y0} {x1} {y1}", dtm, maintain_clipping_extent="MAINTAIN_EXTENT")
    print("planning.terrain (unchanged)", flush=True)
    reference = planning.terrain(dtm, out/"planning", NEIGHBORHOOD_M, TPI_RADIUS_M, 1000.0, CONTOUR_M, "metres")
    print("this script's derive()", flush=True)
    mine = derive(dtm, out/"derive")
    result = {"window": PILOT, "cells": int(np.isfinite(window(dtm, PILOT)).sum()), "products": {}}
    for key in RASTERS:
        a, b = window(reference[key], PILOT), window(mine[key], PILOT)
        same_nodata = bool(np.array_equal(np.isnan(a), np.isnan(b)))
        both = np.isfinite(a) & np.isfinite(b)
        result["products"][key] = {"nodata_equal": same_nodata, "max_abs_diff": float(np.abs(a[both]-b[both]).max()),
                                   "cells": int(both.sum())}
    (out/"pilot.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))


def verify(out):
    """The city run's context products against the pilot's planning.terrain on the window, away from the window's edges
    (whose neighbourhoods the window cuts), and the city mask against the city terrain."""
    import arcpy
    from osgeo import gdal
    gdal.UseExceptions()
    out = Path(out).resolve()
    record = json.loads((out/"terrain.json").read_text(encoding="utf-8"))
    pilot_paths = json.loads((out/"pilot"/"planning"/"terrain.json").read_text(encoding="utf-8"))["outputs"]
    margin = max(NEIGHBORHOOD_M, TPI_RADIUS_M)+1.0
    x0, y0, x1, y1 = PILOT
    inner = (x0+margin, y0+margin, x1-margin, y1-margin)
    result = {"inner_window": inner, "products": {}, "mask": {}}
    for key in RASTERS:
        a, b = window(pilot_paths[key], inner), window(record["context_outputs"][key], inner)
        both = np.isfinite(a) & np.isfinite(b)
        result["products"][key] = {"nodata_equal": bool(np.array_equal(np.isnan(a), np.isnan(b))),
                                   "max_abs_diff": float(np.abs(a[both]-b[both]).max()), "cells": int(both.sum())}
    city = gdal.Open(str(CITY))
    city_band = city.GetRasterBand(1)
    for key in (*RASTERS, "terrain_neighborhood_complete"):
        product = gdal.Open(record["outputs"][key])
        band = product.GetRasterBand(1)
        missing = extra = 0
        for row in range(0, city.RasterYSize, 1024):
            n = min(1024, city.RasterYSize-row)
            t = city_band.ReadAsArray(0, row, city.RasterXSize, n)
            p = band.ReadAsArray(0, row, city.RasterXSize, n)
            t_ok = np.isfinite(t) & (t != city_band.GetNoDataValue())
            p_ok = (p != band.GetNoDataValue()) & np.isfinite(p.astype(np.float64))
            missing += int((t_ok & ~p_ok).sum())
            extra += int((p_ok & ~t_ok).sum())
        result["mask"][key] = {"city_cells_without_value": missing, "values_outside_city": extra}
        product = None
    fc = record["outputs"]["contours"]
    result["contours"] = {"features": int(arcpy.management.GetCount(fc)[0]),
                          "index": sum(1 for r in arcpy.da.SearchCursor(fc, ["INDEX"]) if r[0] == 1)}
    (out/"verify.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("pilot", "run", "verify"))
    p.add_argument("out", type=Path)
    a = p.parse_args(argv)
    {"pilot": pilot, "run": run, "verify": verify}[a.step](a.out)


if __name__ == "__main__":
    main()
