r"""Test places for the COG drawing check (October 23, 2026): inside a tile, on a tile corner, in the last (partial)
column of tiles and in the last (partial) row, each centre in Web Mercator with the ITRF08 transformation.

    python reviews/2026-10-23/cog-drawing/places.py OUT_JSON [--cogs DIR]

ArcGIS Pro Python (PYTHONNOUSERSITE=1). Read-only. The COGs share one grid (24,501 x 12,247 cells of 0.5 m, 512-cell
tiles), so the last column of tiles starts at column 24,064 and is 437 cells wide, and the last row starts at row 11,776
and is 471 cells tall. The last-row place is the valid terrain cell nearest the middle of the data in that row of tiles.
"""
import argparse
import json
from pathlib import Path
import sys

import arcpy
import numpy as np
from osgeo import gdal

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
from canopy.lidar_root import lidar_root  # noqa: E402

COGS = lidar_root()/"2023-salt-lake-valley"/"runs"/"cog-20261022"
TRANSFORM = "WGS_1984_(ITRF08)_To_NAD_1983_2011"
TILE = 512


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out", type=Path)
    p.add_argument("--cogs", type=Path, default=COGS)
    args = p.parse_args(argv)
    gdal.UseExceptions()
    ds = gdal.Open(str(args.cogs/"terrain_m.tif"))
    band = ds.GetRasterBand(1)
    x0, cell, _, y0, _, _ = ds.GetGeoTransform()
    width, height, nodata = ds.RasterXSize, ds.RasterYSize, band.GetNoDataValue()
    last_col, last_row = (width // TILE) * TILE, (height // TILE) * TILE

    strip = band.ReadAsArray(0, last_row, width, height - last_row) != nodata
    rows, cols = np.nonzero(strip)
    k = np.argmin((cols - cols.mean())**2 + (rows - rows.mean())**2)
    places = {
        "interior": (24*TILE + TILE//2, 12*TILE + TILE//2),   # the middle of a full-resolution tile
        "tile_corner": (24*TILE, 12*TILE),                     # a corner of tiles at full resolution and two overviews
        "last_column": (24368, 2996),                          # cell 0 of the alignment test, which drew partly
        "last_row": (int(cols[k]), int(last_row + rows[k])),
    }
    merc = arcpy.SpatialReference(3857)
    out = []
    for name, (col, row) in places.items():
        value = float(band.ReadAsArray(col, row, 1, 1)[0, 0])
        x, y = x0 + (col + 0.5)*cell, y0 - (row + 0.5)*cell
        pt = arcpy.PointGeometry(arcpy.Point(x, y), arcpy.SpatialReference(6341)).projectAs(merc, TRANSFORM).firstPoint
        out.append({"name": name, "col": col, "row": row, "x": x, "y": y, "mercator": [pt.X, pt.Y],
                    "terrain_m": None if value == nodata else value})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"grid": {"width": width, "height": height, "tile": TILE, "last_column": last_col,
                                             "last_row": last_row}, "places": out}, indent=1))
    for o in out:
        print(o["name"], o["col"], o["row"], o["terrain_m"])


if __name__ == "__main__":
    main()
