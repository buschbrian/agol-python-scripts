r"""Check cells for the COG alignment test (October 23, 2026): steep cells with a value no neighbour shares, and where
each cell centre belongs in Web Mercator with and without the ITRF08 datum transformation.

    python reviews/2026-10-23/cog-alignment/cells.py OUT_JSON [--cogs DIR] [--count 8]

ArcGIS Pro Python (PYTHONNOUSERSITE=1). Read-only. Candidate areas come from the slope COG's 4 m overview (mean slope
45-90%, spread across the city); in each, the full-resolution cell nearest the area's centre whose float32 value differs
from every other cell within 20 cells by at least 1e-4 is taken, so a renderer that colours only that value draws only
that cell. The first area also gives the steep edge for the contour picture: its centre in Web Mercator.
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
HALF = 20         # cells either side searched for a shared value
GAP = 1e-4        # smallest difference from any neighbour, in percent slope
SPACING_M = 400   # least distance between chosen areas


def project(x, y):
    """The cell centre in Web Mercator with the transformation and with none."""
    point = arcpy.PointGeometry(arcpy.Point(x, y), arcpy.SpatialReference(6341))
    mercator = arcpy.SpatialReference(3857)
    itrf = point.projectAs(mercator, TRANSFORM).firstPoint
    null = point.projectAs(mercator).firstPoint
    return {"itrf08": [itrf.X, itrf.Y], "none": [null.X, null.Y]}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out", type=Path)
    p.add_argument("--cogs", type=Path, default=COGS)
    p.add_argument("--count", type=int, default=8)
    args = p.parse_args(argv)

    path = args.cogs/"slope_percent.tif"
    ds = gdal.Open(str(path))
    band = ds.GetRasterBand(1)
    x0, cell, _, y0, _, _ = ds.GetGeoTransform()
    nodata = band.GetNoDataValue()
    ov = next(band.GetOverview(i) for i in range(band.GetOverviewCount()) if ds.RasterXSize/band.GetOverview(i).XSize >= 8)
    factor = ds.RasterXSize/ov.XSize
    coarse = ov.ReadAsArray().astype(np.float64)
    coarse[coarse == nodata] = np.nan
    rows, cols = np.where((coarse >= 45) & (coarse <= 90))
    order = np.argsort(np.abs(coarse[rows, cols]-60))  # steady hillside first
    areas = []
    for i in order:
        cx, cy = (cols[i]+0.5)*factor, (rows[i]+0.5)*factor
        if all(np.hypot(cx-a[0], cy-a[1])*cell >= SPACING_M for a in areas):
            areas.append((cx, cy))
        if len(areas) == args.count:
            break

    cells = []
    for cx, cy in areas:
        c0, r0 = int(cx)-2*HALF, int(cy)-2*HALF
        win = band.ReadAsArray(c0, r0, 4*HALF+1, 4*HALF+1).astype(np.float64)
        best = None
        for dr in range(HALF, 3*HALF+1):
            for dc in range(HALF, 3*HALF+1):
                v = win[dr, dc]
                if v == nodata or v < 30:
                    continue
                around = win[dr-HALF:dr+HALF+1, dc-HALF:dc+HALF+1].copy()
                around[HALF, HALF] = np.inf
                if np.min(np.abs(around-v)) < GAP:
                    continue
                d = (dr-2*HALF)**2+(dc-2*HALF)**2
                if best is None or d < best[0]:
                    best = (d, dr, dc, v)
        if best is None:
            continue
        _, dr, dc, v = best
        col, row = c0+dc, r0+dr
        x, y = x0+(col+0.5)*cell, y0-(row+0.5)*cell
        around = win[dr-HALF:dr+HALF+1, dc-HALF:dc+HALF+1].copy()
        around[HALF, HALF] = np.inf
        cells.append({"col": col, "row": row, "x": x, "y": y, "slope_percent": float(np.float32(v)),
                      "nearest_other_value": float(np.min(np.abs(around-v))), **project(x, y)})

    first = cells[0]
    shift = [first["itrf08"][k]-first["none"][k] for k in (0, 1)]
    out = {
        "source": str(path), "transformation": TRANSFORM, "grid": {"x0": x0, "y0": y0, "cell": cell},
        "note": "x, y are EPSG:6341 cell centres; itrf08 and none are the same centre in Web Mercator (EPSG:3857), "
                "projected with the transformation and with none",
        "itrf08_minus_none_mercator_m": shift, "itrf08_minus_none_length_m": float(np.hypot(*shift)),
        "steep_edge": {"x": first["x"], "y": first["y"], "mercator_itrf08": first["itrf08"]},
        "cells": cells,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1))
    print(f"{len(cells)} cells; ITRF08 minus none in Web Mercator {shift[0]:+.3f}, {shift[1]:+.3f} m "
          f"({out['itrf08_minus_none_length_m']:.3f} m)")


if __name__ == "__main__":
    main()
