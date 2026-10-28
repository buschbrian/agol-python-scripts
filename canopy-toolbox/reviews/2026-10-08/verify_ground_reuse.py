"""Runtime check: a cached ground raster preserves all CHM products exactly."""
import json
from pathlib import Path
import sys

import arcpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from canopy import common, licensing, rasters
from canopy.tiling import Extent


def main(root):
    root = Path(root)
    work = root / 'ground-reuse-verification'
    work.mkdir(exist_ok=True)
    direct, reused = work / 'direct', work / 'reused'
    direct.mkdir(exist_ok=True); reused.mkdir(exist_ok=True)
    lasd = str(work / 'verification.lasd')
    point_file = root / 'prepared/points/12TVL2204.las'
    stat = point_file.stat()
    if not arcpy.Exists(lasd):
        arcpy.management.CreateLasDataset([str(point_file)], lasd, compute_stats='COMPUTE_STATS')
    extent = Extent(422450, 4504400, 422650, 4504600)
    with licensing.extensions('3D', 'Spatial'):
        original = rasters.build_chm(lasd, str(direct), extent=extent.as_arcpy_string(), z_unit='metres')
        cached = rasters.build_chm(lasd, str(reused), extent=extent.as_arcpy_string(), z_unit='metres',
                                   ground_raster=original['dtm'])
    checks = {}
    for key in original:
        a = arcpy.RasterToNumPyArray(original[key], nodata_to_value=-9999)
        b = arcpy.RasterToNumPyArray(cached[key], nodata_to_value=-9999)
        checks[key] = {'cells': int(a.size), 'exactly_equal': bool(np.array_equal(a, b))}
        if not checks[key]['exactly_equal']:
            raise AssertionError(f'Cached ground changed {key}')
    after = point_file.stat()
    unchanged = (stat.st_size, stat.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    assert unchanged
    record = {'status': 'passed', 'checks': checks, 'working_points_unchanged': unchanged,
              'extent': list(extent), 'cell_m': .5, 'point_file': str(point_file)}
    common.write_json(work / 'result.json', record)
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main(sys.argv[1])
