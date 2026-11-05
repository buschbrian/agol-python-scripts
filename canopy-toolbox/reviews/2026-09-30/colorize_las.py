"""Write a copy of a LAS tile with NAIP colour attached, as input for the IGN FRACTAL model. Read-only on the source.

    python reviews/2026-09-30/colorize_las.py NEW_OUTPUT.las [--extent XMIN YMIN XMAX YMAX]

Run with ArcGIS Pro Python (PYTHONNOUSERSITE=1; it reads the NAIP image through ArcPy). The output is LAS 1.4 point format 8
(red, green, blue and near-infrared added to the 30-byte format 6 record), for Myria3D, which wants these dimensions:
- Colour is the NAIP digital number times 256, because Myria3D divides by 255 x 256 and asserts nothing is larger (x 257 would fail).
  It zeroes the colour of every point whose return number is above 1 itself, and computes NDVI and average colour itself.
- Classification is set to 1 everywhere. Myria3D's predict path only uses it to drop artefacts, and leaving our baseline classes
  in the file would leak them into what is meant to be an independent second opinion.
- Points outside the NAIP image get zero colour. Every other byte (position, intensity, returns, flags, time) is copied unchanged.
The NAIP is leaf-off, dated 2021-11-13, two years before the lidar; the FRACTAL model was trained with contemporaneous colour
orthophotos, so its results here are an opinion to compare, not a label.
"""
import argparse
import json
from pathlib import Path
import struct
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from canopy import las_records  # noqa: E402
from canopy.lidar_root import lidar_root, live  # noqa: E402

PILOT = lidar_root()/"2023-salt-lake-valley"/"runs"/"pilot-2026-09-29"
SOURCE = PILOT/"12TVL2804"/"prepared"/"points"/"12TVL2804.las"
NAIP = lidar_root()/"2023-salt-lake-valley"/"naip"/"12TVL2804"/"naip_12TVL2804.tif"
NEW_LENGTH = 38                         # point format 8: the 30-byte format 6 record plus red, green, blue, near-infrared
CHUNK = 2_000_000


def colorize_block(block30, x, y, naip, x0, y_top, cell):
    """(n, 38) records: the source bytes, classification 1, and NAIP red, green, blue, near-infrared times 256."""
    n = len(block30)
    out = np.zeros((n, NEW_LENGTH), dtype=np.uint8)
    out[:, :30] = block30
    out[:, 16] = 1
    col = np.floor((x-x0)/cell).astype(np.int64)
    row = np.floor((y_top-y)/cell).astype(np.int64)
    inside = (col >= 0) & (col < naip.shape[2]) & (row >= 0) & (row < naip.shape[1])
    colour = np.zeros((n, 4), dtype=np.uint16)
    colour[inside] = naip[:, row[inside], col[inside]].T.astype(np.uint16)*256
    out[:, 30:] = colour.astype("<u2").view(np.uint8).reshape(n, 8)
    return out


def output_header(source_bytes, points, bounds):
    """The source header and VLRs with point format 8, record length 38, the new count and the new bounds."""
    head = bytearray(source_bytes)
    head[104] = 8
    struct.pack_into("<H", head, 105, NEW_LENGTH)
    struct.pack_into("<I", head, 107, 0)                      # the legacy count must be zero for formats 6 to 10
    struct.pack_into("<5I", head, 111, 0, 0, 0, 0, 0)
    struct.pack_into("<Q", head, 247, points)
    struct.pack_into("<15Q", head, 255, *([0]*15))
    struct.pack_into("<Q", head, 235, 0)                      # no extended VLRs follow the points in the copy
    struct.pack_into("<I", head, 243, 0)
    xmin, ymin, xmax, ymax, zmin, zmax = bounds
    struct.pack_into("<6d", head, 179, xmax, xmin, ymax, ymin, zmax, zmin)
    return bytes(head)


def colorize(source, naip, x0, y_top, cell, out, extent=None):
    """Write the coloured copy of source to out (new file); returns a record of what was written."""
    out = Path(out)
    if out.exists():
        raise FileExistsError(f"Choose a new output file: {out}")
    block, scale, offset, modern, info = las_records.records(source, mode="r")
    if info["format"] != 6:
        raise ValueError(f"Expected LAS point format 6, found {info['format']}")
    x = block["x"]*scale[0]+offset[0]
    y = block["y"]*scale[1]+offset[1]
    z = block["z"]*scale[2]+offset[2]
    keep = np.arange(len(x)) if extent is None else np.flatnonzero(
        (x >= extent[0]) & (x <= extent[2]) & (y >= extent[1]) & (y <= extent[3]))
    if not len(keep):
        raise ValueError("No points inside the extent")
    bounds = (float(x[keep].min()), float(y[keep].min()), float(x[keep].max()), float(y[keep].max()),
              float(z[keep].min()), float(z[keep].max()))
    with open(source, "rb") as handle:
        source_head = handle.read(info["offset"])
    raw = np.memmap(source, dtype=np.uint8, mode="r", offset=info["offset"], shape=(info["points"], info["record_length"]))
    with open(out, "wb") as handle:
        handle.write(output_header(source_head, len(keep), bounds))
        for start in range(0, len(keep), CHUNK):
            index = keep[start:start+CHUNK]
            handle.write(colorize_block(np.asarray(raw[index]), x[index], y[index], naip, x0, y_top, cell).tobytes())
    return {"source": str(source), "output": str(out), "points": int(len(keep)), "extent": extent, "bounds": bounds,
            "colour_scale": 256, "classification": 1}


def load_naip(path):
    import arcpy
    raster = arcpy.Raster(str(path))
    return (arcpy.RasterToNumPyArray(str(path), nodata_to_value=0).astype(np.uint8),
            raster.extent.XMin, raster.extent.YMax, raster.meanCellWidth)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path)
    parser.add_argument("--extent", type=float, nargs=4, metavar=("XMIN", "YMIN", "XMAX", "YMAX"))
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--naip", type=Path, default=NAIP)
    args = parser.parse_args(argv)
    naip, x0, y_top, cell = load_naip(live(args.naip))
    record = colorize(live(args.source), naip, x0, y_top, cell, args.out, args.extent)
    args.out.with_suffix(".json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps(record, indent=1))


if __name__ == "__main__":
    main()
