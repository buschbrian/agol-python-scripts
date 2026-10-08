"""Cut one tile out of locally downloaded UGRC NAIP quarter-quad sheets as a raw four-band GeoTIFF. Read-only on the sheets.

    python reviews/2026-10-01/naip_local_tile.py 12TVL2804 428000 4504000 429000 4505000 NEW_OUTPUT_DIR \
        --sheets C:\\Users\\bbusch\\tools\\naip-2024 --flight-date 2024-07-07 [--cell 0.5]

Run with ArcGIS Pro Python (PYTHONNOUSERSITE=1). It reads NAIP2024 sheets as UGRC serves them: for each quarter-quad a three-band
RGB file and a one-band B4 file, both 0.6 m. The output matches naip_fetch.py's layout (four U8 bands, red, green, blue, B4 as
near-infrared, `naip_TILE.tif` plus `naip_TILE_metadata.json`), so colorize_las.py, the triage and naip_review.py take either year.
- Sampling is nearest neighbour from the 0.6 m sheets onto the output grid, as naip_fetch.py does for the USGS service.
- The sheets are labelled NAD83 UTM 12N (26912) and are used as EPSG 6341 coordinates with no shift. NAD83 and NAD83(2011)
  differ by about a metre in Utah, and UGRC states a horizontal CE90 of 1.07 m and 2.6 m, so register against the lidar before
  trusting a sub-metre overlay.
- Where two sheets cover the same pixel the first sheet in sorted name order wins; the metadata records the overlap count and how
  closely the two sheets agree there (a check on seams and radiometry).
- The metadata states that B4 is near-infrared by inference from the data (vegetation is brighter than pavement), because the UGRC
  files carry no band description. The flight date comes from UGRC's Hexagon service-dates layer, which UGRC says is the same
  2024 flight; it is passed in with --flight-date, never read from the sheets.
Nothing outside the new output folder is written.
"""
import argparse
import datetime
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from canopy.run_safeguards import fingerprint  # noqa: E402

BAND_MAPPING = {"red": 1, "green": 2, "blue": 3, "nir": 4}
RGB_SUFFIX, B4_SUFFIX = "_RGB", "_B4"


def grid_indices(x0, y_top, cell, extent, out_cell):
    """Sheet column and row of every output cell centre of extent, as 2-D arrays (rows run north to south)."""
    xmin, ymin, xmax, ymax = extent
    width, height = round((xmax-xmin)/out_cell), round((ymax-ymin)/out_cell)
    if abs(width*out_cell-(xmax-xmin)) > 1e-6 or abs(height*out_cell-(ymax-ymin)) > 1e-6:
        raise ValueError("The extent is not a whole number of cells")
    x = xmin+(np.arange(width)+0.5)*out_cell
    y = ymax-(np.arange(height)+0.5)*out_cell
    col = np.floor((x-x0)/cell).astype(np.int64)
    row = np.floor((y_top-y)/cell).astype(np.int64)
    return np.broadcast_to(col, (height, width)), np.broadcast_to(row[:, None], (height, width))


def paste(out, filled, bands, col, row):
    """Copy sheet pixels into the output where this sheet covers it and nothing has been written yet.

    bands is the whole-window (4, h, w) array whose origin is the first element of col/row ranges (col.min(), row.min()).
    Returns (cells written, cells that were already filled and so form the overlap, the overlap's index mask).
    """
    inside = (col >= 0) & (col < bands.shape[2]) & (row >= 0) & (row < bands.shape[1])
    take = inside & ~filled
    overlap = inside & filled
    out[:, take] = bands[:, row[take], col[take]]
    filled |= inside
    return int(take.sum()), int(overlap.sum()), overlap


def sheet_names(root):
    """Quarter-quad names that have both an _RGB and a _B4 file under root, e.g. q1320_nw_NAIP2024."""
    rgb = {p.stem[:-len(RGB_SUFFIX)] for p in Path(root).glob(f"*/*{RGB_SUFFIX}.tif")}
    b4 = {p.stem[:-len(B4_SUFFIX)] for p in Path(root).glob(f"*/*{B4_SUFFIX}.tif")}
    return sorted(rgb & b4)


def read_sheet_window(root, name, extent):
    """The four bands of one sheet over the part that intersects extent, plus its grid. None if it does not intersect."""
    import arcpy
    rgb_path = Path(root)/f"{name}{RGB_SUFFIX}"/f"{name}{RGB_SUFFIX}.tif"
    b4_path = Path(root)/f"{name}{B4_SUFFIX}"/f"{name}{B4_SUFFIX}.tif"
    rgb, b4 = arcpy.Raster(str(rgb_path)), arcpy.Raster(str(b4_path))
    if (rgb.width, rgb.height, round(rgb.meanCellWidth, 6), round(rgb.extent.XMin, 3), round(rgb.extent.YMax, 3)) != \
       (b4.width, b4.height, round(b4.meanCellWidth, 6), round(b4.extent.XMin, 3), round(b4.extent.YMax, 3)):
        raise ValueError(f"{name}: the RGB and B4 files are not on the same grid")
    x0, y_top, cell = rgb.extent.XMin, rgb.extent.YMax, rgb.meanCellWidth
    xmin, ymin, xmax, ymax = extent
    c0, c1 = int(np.floor((xmin-x0)/cell)), int(np.floor((xmax-x0)/cell))
    r0, r1 = int(np.floor((y_top-ymax)/cell)), int(np.floor((y_top-ymin)/cell))
    c0, c1, r0, r1 = max(c0, 0), min(c1, rgb.width-1), max(r0, 0), min(r1, rgb.height-1)
    if c0 > c1 or r0 > r1:
        return None
    ncols, nrows = c1-c0+1, r1-r0+1
    corner = arcpy.Point(x0+c0*cell, y_top-(r1+1)*cell)
    bands = np.concatenate([arcpy.RasterToNumPyArray(str(rgb_path), corner, ncols, nrows).astype(np.uint8),
                            arcpy.RasterToNumPyArray(str(b4_path), corner, ncols, nrows).astype(np.uint8)[None]])
    return {"name": name, "bands": bands, "x0": x0+c0*cell, "y_top": y_top-r0*cell, "cell": cell,
            "files": [str(rgb_path), str(b4_path)]}


def write_geotiff(path, bands, top_left, cell, epsg):
    """Write (4, h, w) uint8 as an uncompressed four-band 8-bit GeoTIFF (arcpy would widen it to 16 bit)."""
    from osgeo import gdal, osr
    gdal.UseExceptions()
    count, height, width = bands.shape
    dataset = gdal.GetDriverByName("GTiff").Create(str(path), width, height, count, gdal.GDT_Byte, ["INTERLEAVE=PIXEL"])
    dataset.SetGeoTransform((top_left[0], cell, 0.0, top_left[1], 0.0, -cell))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    dataset.SetProjection(srs.ExportToWkt())
    for i in range(count):
        dataset.GetRasterBand(i+1).WriteArray(bands[i])
    dataset.FlushCache()
    dataset = None


def build(tile, extent, epsg, out_cell, out_dir, sheets_root, flight_date):
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise FileExistsError(f"Choose a new output folder: {out_dir}")
    xmin, ymin, xmax, ymax = extent
    width, height = round((xmax-xmin)/out_cell), round((ymax-ymin)/out_cell)
    out = np.zeros((4, height, width), dtype=np.uint8)
    filled = np.zeros((height, width), dtype=bool)
    used, overlaps = [], []
    for name in sheet_names(sheets_root):
        window = read_sheet_window(sheets_root, name, extent)
        if window is None:
            continue
        col, row = grid_indices(window["x0"], window["y_top"], window["cell"], extent, out_cell)
        earlier = [u["sheet"] for u in used]
        written, overlap, mask = paste(out, filled, window["bands"], col, row)
        used.append({"sheet": name, "cells_written": written, "overlap_cells": overlap, "files": window["files"]})
        if overlap:
            overlaps.append((name, earlier, mask, window["bands"], col, row))
    if not filled.all():
        raise ValueError(f"{int((~filled).sum())} output cells are outside every sheet")
    # Agreement in the overlap: what the later sheet shows at those cells against what the earlier sheet already wrote.
    seams = []
    for name, earlier, mask, bands, col, row in overlaps:
        alt = bands[:, row[mask], col[mask]].astype(np.float64)
        kept = out[:, mask].astype(np.float64)
        seams.append({"sheet": name, "against": earlier, "cells": int(mask.sum()),
                      "mean_signed_difference_per_band": [round(float((alt[b]-kept[b]).mean()), 2) for b in range(4)],
                      "mean_abs_difference_per_band": [round(float(np.abs(alt[b]-kept[b]).mean()), 2) for b in range(4)],
                      "correlation_per_band": [round(float(np.corrcoef(alt[b], kept[b])[0, 1]), 3)
                                               if alt[b].std() and kept[b].std() else None for b in range(4)]})
    out_dir.mkdir(parents=True)
    image = out_dir/f"naip_{tile}.tif"
    write_geotiff(image, out, (xmin, ymax), out_cell, epsg)
    record = {"source": "NAIP", "survey_date": flight_date, "band_mapping": dict(BAND_MAPPING),
              "image": fingerprint(image), "tile": tile, "epsg": epsg, "extent": list(extent), "cell_size_m": out_cell,
              "size_px": f"{width},{height}", "resampling": "nearest neighbour from the 0.6 m UGRC NAIP 2024 sheets",
              "sheets": used, "sheet_overlap_agreement": seams,
              "source_crs_label": "NAD83 UTM zone 12N (EPSG 26912), relabelled as EPSG 6341 with no shift",
              "band_order_evidence": "B4 is taken to be near-infrared by inference from the data, not from a UGRC band description: "
                                     "it is much brighter on vegetation than on pavement and roofs and nearly uncorrelated with luminance.",
              "flight_date_source": "UGRC Utah Hexagon Service Dates layer (flight 2024-07-07 at the tile centre and corners); "
                                    "UGRC describes Hexagon as the same 2024 flight. Not read from the sheets.",
              "fetched_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
              "limits": ["Acquired 2024-07-07 (summer, leaf-on), about eight months after the lidar (2023-10-07 to 2023-11-05).",
                         "Sheets are lossy JPEG (quality 65): colour and especially B4 are slightly smoothed and blocky.",
                         "Values are digital numbers, not reflectance; roof lean, shadow and seasonal colour apply.",
                         "RGB and B4 are separate delivered products and may not share a stretch: NDVI from them is uncalibrated "
                         "and not comparable with NDVI from the original four-band 2021 scenes. Use it as a relative cue.",
                         "Positional accuracy per UGRC: CE90 1.07 m and 2.6 m; check registration against the lidar."]}
    (out_dir/f"naip_{tile}_metadata.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("tile")
    p.add_argument("xmin", type=float); p.add_argument("ymin", type=float)
    p.add_argument("xmax", type=float); p.add_argument("ymax", type=float)
    p.add_argument("out", type=Path)
    p.add_argument("--sheets", type=Path, required=True)
    p.add_argument("--flight-date", required=True)
    p.add_argument("--cell", type=float, default=0.5)
    p.add_argument("--epsg", type=int, default=6341)
    args = p.parse_args(argv)
    record = build(args.tile, (args.xmin, args.ymin, args.xmax, args.ymax), args.epsg, args.cell, args.out, args.sheets,
                   args.flight_date)
    print(json.dumps({k: record[k] for k in ("survey_date", "size_px", "cell_size_m", "sheets", "sheet_overlap_agreement")}, indent=1))
    print("image:", record["image"]["path"], record["image"]["bytes"], "bytes")


if __name__ == "__main__":
    main()
