"""Ground-elevation raster for the building reference_height (HAG) experiment.

Copies the prepared tile and its neighbour halo files into a NEW folder, builds a
LAS dataset over those copies only, and interpolates class-2 ground with the
pipeline's DTM method. The prepared source files are only read (hash-checked).
Coverage of the processing boundary must be complete: the inference tool omits
points outside the raster. Run with ArcGIS Pro Python (PYTHONNOUSERSITE=1).

  python dl_reference_height.py OUT_DIR --sources A.las B.las ... --extent XMIN YMIN XMAX YMAX
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from canopy.run_safeguards import fingerprint, valid_extent


def full_margin(missing, extent, raster_extent, cell):
    """Largest margin (multiple of cell) around extent without NoData cells."""
    import numpy as np
    x0, y0, x1, y1 = extent
    rx0, ry0, rx1, ry1 = raster_extent
    rows, cols = missing.shape
    margin, best = 0.0, None
    while True:
        c0 = int(round((x0-margin-rx0)/cell)); c1 = int(round((x1+margin-rx0)/cell))
        r0 = int(round((ry1-(y1+margin))/cell)); r1 = int(round((ry1-(y0-margin))/cell))
        if c0 < 0 or r0 < 0 or c1 > cols or r1 > rows or missing[r0:r1, c0:c1].any():
            return best
        best = margin
        margin += cell


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('out', type=Path)
    parser.add_argument('--sources', type=Path, nargs='+', required=True)
    parser.add_argument('--extent', type=float, nargs=4, required=True, help='Processing boundary to cover')
    parser.add_argument('--context', type=float, default=50, help='Raster extent beyond the boundary, metres')
    parser.add_argument('--cell-size', type=float, default=0.5)
    args = parser.parse_args()
    extent = valid_extent(args.extent)
    out = args.out.resolve()
    if out.exists():
        raise ValueError(f"Output folder must be new: {out}")
    import arcpy
    import numpy as np
    from canopy.rasters import DTM_INTERPOLATION, GROUND_CLASSES
    started = time.monotonic()
    points = out / 'points'
    points.mkdir(parents=True)
    record = {"status": "running", "method": "class-2 ground of COPIED prepared LAS files, "
              "LasDatasetToRaster " + DTM_INTERPOLATION, "extent": extent, "context_m": args.context,
              "cell_size": args.cell_size, "copies": []}
    for source in args.sources:
        before = fingerprint(source)
        target = points / Path(source).name
        shutil.copyfile(source, target)
        copied = fingerprint(target)
        if copied['sha256'] != before['sha256'] or fingerprint(source) != before:
            raise RuntimeError(f"Copy or source changed: {source}")
        record['copies'].append({"source": before, "copy": copied})
    lasd = str(out / 'ground.lasd')
    arcpy.management.CreateLasDataset([str(p) for p in sorted(points.glob('*.las'))], lasd,
                                      compute_stats='COMPUTE_STATS')
    describe = arcpy.Describe(lasd)
    sr = describe.spatialReference
    record['spatial_reference'] = {"name": sr.name, "factory_code": sr.factoryCode, "linear_unit": sr.linearUnitName,
                                   "vertical": getattr(getattr(sr, 'VCS', None), 'name', None),
                                   "vertical_unit": getattr(getattr(sr, 'VCS', None), 'linearUnitName', None)}
    if sr.factoryCode != 6341 or sr.linearUnitName != 'Meter':
        raise ValueError(f"Expected EPSG:6341 metres, found {record['spatial_reference']}")
    layer = arcpy.management.MakeLasDatasetLayer(lasd, 'ground_layer', class_code=GROUND_CLASSES,
                                                 withheld='EXCLUDE_WITHHELD', overlap='EXCLUDE_OVERLAP',
                                                 synthetic='EXCLUDE_SYNTHETIC')[0]
    x0, y0, x1, y1 = extent
    c = args.context
    raster = out / 'ground.tif'
    with arcpy.EnvManager(extent=arcpy.Extent(x0-c, y0-c, x1+c, y1+c), outputCoordinateSystem=sr,
                          snapRaster=None, pyramid='NONE'):
        arcpy.conversion.LasDatasetToRaster(layer, str(raster), 'ELEVATION', DTM_INTERPOLATION, 'FLOAT',
                                            'CELLSIZE', args.cell_size, 1)
    arcpy.management.CalculateStatistics(str(raster))
    ras = arcpy.Raster(str(raster))
    e = ras.extent
    raster_extent = [e.XMin, e.YMin, e.XMax, e.YMax]
    values = arcpy.RasterToNumPyArray(ras, nodata_to_value=np.nan)
    missing = ~np.isfinite(values)
    margin = full_margin(missing, extent, raster_extent, ras.meanCellWidth)
    record.update(raster_extent=raster_extent, cell=[ras.meanCellWidth, ras.meanCellHeight],
                  shape=list(values.shape), nodata_cells_total=int(missing.sum()),
                  z_min=float(np.nanmin(values)), z_max=float(np.nanmax(values)),
                  complete_margin_beyond_boundary_m=margin,
                  raster_spatial_reference=ras.spatialReference.factoryCode)
    del ras
    if margin is None:
        record['status'] = 'failed'
        record['error'] = 'Ground raster has NoData inside the processing boundary'
    else:
        os.chmod(raster, stat.S_IREAD)
        record['status'] = 'complete'
        record['raster'] = fingerprint(raster)
        record['read_only'] = True
    record['elapsed_seconds'] = round(time.monotonic()-started, 1)
    (out / 'reference-height.json').write_text(json.dumps(record, indent=1), encoding='utf-8')
    print(json.dumps(record, indent=1))
    if record['status'] != 'complete':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
