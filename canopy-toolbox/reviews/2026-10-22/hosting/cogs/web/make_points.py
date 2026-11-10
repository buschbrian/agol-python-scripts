r"""Check points for the web trial: cell centres with their slope read by GDAL from the source raster (not the COG).

    python reviews/2026-10-22/hosting/cogs/web/make_points.py      writes points.json beside this script

Two random city cells in each class of the trial renderer (under 10, 10-15, 15-20, 20-25, 25-30, 30 and over percent), the
cell nearest each class break, and two NoData cells outside the city. Seeded, so reruns give the same points.
"""
import json
import os
from pathlib import Path
import sys

os.environ["GDAL_PAM_ENABLED"] = "NO"
import numpy as np  # noqa: E402
from osgeo import gdal  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[4]))
from canopy.lidar_root import lidar_root  # noqa: E402

gdal.UseExceptions()
SOURCE = lidar_root()/"2023-salt-lake-valley"/"runs"/"terrain-city-20261022"/"slope_percent.tif"
BREAKS = (10, 15, 20, 25, 30)
EDGES = (-np.inf, *BREAKS, np.inf)


def main():
    ds = gdal.Open(str(SOURCE))
    band = ds.GetRasterBand(1)
    x0, dx, _, y0, _, dy = ds.GetGeoTransform()
    nodata = np.float32(band.GetNoDataValue())
    rng = np.random.default_rng(20261022)
    found = {k: [] for k in range(len(EDGES)-1)}
    near = {b: None for b in BREAKS}
    outside = []
    size = 512
    while any(len(v) < 2 for v in found.values()) or len(outside) < 2 or any(v is None for v in near.values()):
        cx, cy = int(rng.integers(ds.RasterXSize-size)), int(rng.integers(ds.RasterYSize-size))
        w = band.ReadAsArray(cx, cy, size, size)
        r, c = int(rng.integers(size)), int(rng.integers(size))
        v = w[r, c]
        if v == nodata:
            if len(outside) < 2:
                outside.append((cx+c, cy+r, None))
            continue
        k = int(np.searchsorted(EDGES, v, side="right"))-1
        if len(found[k]) < 2:
            found[k].append((cx+c, cy+r, float(v)))
        for b in BREAKS:
            valid = w != nodata
            if not valid.any():
                continue
            d = np.where(valid, np.abs(w.astype(np.float64)-b), np.inf)
            rr, cc = np.unravel_index(int(np.argmin(d)), d.shape)
            if near[b] is None or d[rr, cc] < abs(near[b][2]-b):
                near[b] = (cx+int(cc), cy+int(rr), float(w[rr, cc]))
    cells = [p for v in found.values() for p in v] + list(near.values()) + outside
    points = [{"col": col, "row": row, "x": x0+(col+0.5)*dx, "y": y0+(row+0.5)*dy, "slope_percent": value}
              for col, row, value in cells]
    record = {"source": str(SOURCE), "spatial_reference": {"wkid": 6341}, "breaks": BREAKS,
              "note": "x, y are cell centres in EPSG:6341; slope_percent is the float32 cell value read by GDAL, or null "
                      "for NoData", "points": points}
    (HERE/"points.json").write_text(json.dumps(record, indent=1))
    for p in points:
        print(p)


if __name__ == "__main__":
    main()
