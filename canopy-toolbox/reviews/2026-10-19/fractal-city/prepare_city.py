"""Prepare every Millcreek tile for the citywide FRACTAL run: a NAIP 2024 tile and a colourised LAS copy. Read-only on inputs.

    python reviews/2026-10-19/fractal-city/prepare_city.py [--tiles 12TVL2804 ...]

Run with ArcGIS Pro Python (PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT set; city_fractal.bat does both). For each working LAS of the
October 8 city run (`runs/city-count-20261008/prepared/points`, native building and height classes) it
1. makes a four-band 0.5 m NAIP 2024 tile over the 1 km tile plus a 5 m margin (../../2026-10-01/naip_local_tile.py), dated
   from UGRC's Hexagon service-dates layer: the flight covering the tile centre, with every intersecting flight recorded;
2. writes a colourised point-format-8 copy with classification 1 (../../2026-09-30/colorize_las.py), FRACTAL's input.
Outputs go to `naip/naip2024-tiles/<tile>/` and `fractal/city-20261019/colorized/<tile>.las` (+ .json). A tile whose outputs are
complete is skipped, so the run resumes; a colourised file without its .json is an interrupted write and is moved aside, never
deleted. The working LAS, the sheets and every GIS layer are only read; each working LAS's size and mtime are checked after use.
"""
import argparse
import datetime
import importlib.util
import json
from pathlib import Path
import struct
import sys
import time

import requests

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
from canopy.lidar_root import lidar_root  # noqa: E402

LIDAR = lidar_root()/"2023-salt-lake-valley"
WORK = LIDAR/"runs"/"city-count-20261008"/"prepared"/"points"
SHEETS = LIDAR/"naip"/"naip2024-sheets"
NAIP_TILES = LIDAR/"naip"/"naip2024-tiles"
RUN = LIDAR/"fractal"/"city-20261019"
MARGIN_M = 5.0
CELL_M = 0.5
HEXAGON_DATES = ("https://services1.arcgis.com/99lidPhWCzftIe9K/ArcGIS/rest/services/"
                 "Utah_Hexagon_Service_Dates/FeatureServer/0/query")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tile_origin(tile):
    """South-west corner of a 1 km USNG tile such as 12TVL2804 in EPSG 6341 (100 km square VL is 400000 E, 4500000 N)."""
    return 400000+int(tile[5:7])*1000, 4500000+int(tile[7:9])*1000


def header_bounds(path):
    with open(path, "rb") as handle:
        head = handle.read(375)
    xmax, xmin, ymax, ymin = struct.unpack_from("<4d", head, 179)
    return xmin, ymin, xmax, ymax


def naip_extent(tile, bounds):
    """The tile plus the margin, refusing points that would fall outside it."""
    x0, y0 = tile_origin(tile)
    extent = (x0-MARGIN_M, y0-MARGIN_M, x0+1000+MARGIN_M, y0+1000+MARGIN_M)
    xmin, ymin, xmax, ymax = bounds
    if xmin < extent[0] or ymin < extent[1] or xmax > extent[2] or ymax > extent[3]:
        raise ValueError(f"{tile}: points {bounds} extend beyond the imagery extent {extent}")
    return extent


def flight_dates(extent, session=requests):
    """(date at the tile centre, sorted dates of every flight intersecting the extent), from the Hexagon layer."""
    def query(geometry, geometry_type):
        response = session.get(HEXAGON_DATES, params={
            "where": "NAME = 'Hexagon 15cm 2024'", "geometry": json.dumps(geometry), "geometryType": geometry_type,
            "inSR": 6341, "spatialRel": "esriSpatialRelIntersects", "outFields": "DATE", "returnGeometry": "false",
            "f": "json"}, timeout=60)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise RuntimeError(f"Hexagon dates service error: {data['error']}")
        return sorted({datetime.datetime.fromtimestamp(f["attributes"]["DATE"]/1000, datetime.timezone.utc).date().isoformat()
                       for f in data["features"]})
    xmin, ymin, xmax, ymax = extent
    centre = query({"x": (xmin+xmax)/2, "y": (ymin+ymax)/2, "spatialReference": {"wkid": 6341}}, "esriGeometryPoint")
    every = query({"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax, "spatialReference": {"wkid": 6341}},
                  "esriGeometryEnvelope")
    if len(centre) != 1:
        raise RuntimeError(f"Expected one flight at the tile centre, found {centre}")
    return centre[0], every


def stamp(path):
    stat = Path(path).stat()
    return {"bytes": stat.st_size, "mtime": stat.st_mtime}


def prepare_tile(tile, nlt, colorize, log):
    source = WORK/f"{tile}.las"
    before = stamp(source)
    extent = naip_extent(tile, header_bounds(source))
    record = {"tile": tile, "source": str(source), "source_before": before, "naip_extent": list(extent)}
    naip_dir = NAIP_TILES/tile
    meta_path = naip_dir/f"naip_{tile}_metadata.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if stamp(meta["image"]["path"])["bytes"] != meta["image"]["bytes"] or meta["extent"] != list(extent):
            raise RuntimeError(f"{tile}: existing NAIP tile does not match its metadata; inspect {naip_dir}")
        record["naip"] = "reused"
    else:
        if naip_dir.exists():
            naip_dir.rename(naip_dir.with_name(f"{tile}.incomplete-{int(time.time())}"))
        date, every = flight_dates(extent)
        meta = nlt.build(tile, extent, 6341, CELL_M, naip_dir, SHEETS, date,
                         flight_date_source=(f"UGRC Utah Hexagon Service Dates layer: flight {date} at the tile centre; "
                                             f"flights intersecting the tile: {', '.join(every)}. UGRC describes Hexagon "
                                             "as the same 2024 flight. Not read from the sheets."))
        record["naip"] = "built"
    record["naip_date"], record["naip_image"] = meta["survey_date"], meta["image"]
    record["naip_sheets"] = [s["sheet"] for s in meta["sheets"] if s["cells_written"]]

    out = RUN/"colorized"/f"{tile}.las"
    done = out.with_suffix(".json")
    if out.exists() and done.exists():
        record["colorized"] = json.loads(done.read_text(encoding="utf-8")) | {"status": "reused"}
    else:
        if out.exists():
            out.rename(out.with_name(f"{tile}.las.interrupted-{int(time.time())}"))
        out.parent.mkdir(parents=True, exist_ok=True)
        naip, x0, y_top, cell = colorize.load_naip(Path(meta["image"]["path"]))
        result = colorize.colorize(source, naip, x0, y_top, cell, out)
        result |= {"naip": meta["image"], "naip_date": meta["survey_date"]}
        done.write_text(json.dumps(result, indent=1), encoding="utf-8")
        record["colorized"] = result | {"status": "written"}
    after = stamp(source)
    if after != before:
        raise RuntimeError(f"{tile}: the working LAS changed while it was read")
    log(f"{tile}: NAIP {record['naip']} ({record['naip_date']}, sheets {', '.join(record['naip_sheets'])}), "
        f"colourised {record['colorized']['status']} {record['colorized']['points']:,} points")
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tiles", nargs="+")
    args = parser.parse_args(argv)
    nlt = load("naip_local_tile", TOOLBOX/"reviews"/"2026-10-01"/"naip_local_tile.py")
    colorize = load("colorize_las", TOOLBOX/"reviews"/"2026-09-30"/"colorize_las.py")
    tiles = args.tiles or sorted(p.stem for p in WORK.glob("*.las"))
    RUN.mkdir(parents=True, exist_ok=True)
    manifest_path = RUN/"prepare.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"tiles": {}}
    manifest.update(status="running", started=time.time(), work=str(WORK), sheets=str(SHEETS), requested=tiles)

    def save():
        manifest_path.write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    def log(text):
        print(f"{datetime.datetime.now():%H:%M:%S} {text}", flush=True)

    save()
    for tile in tiles:
        started = time.time()
        manifest["tiles"][tile] = prepare_tile(tile, nlt, colorize, log) | {"seconds": round(time.time()-started, 1)}
        save()
    all_tiles = sorted(p.stem for p in WORK.glob("*.las"))
    complete = all((RUN/"colorized"/f"{t}.json").exists() for t in all_tiles)
    manifest.update(status="complete" if complete else "partial", finished=time.time())
    save()
    log(f"prepare {manifest['status']}: {sum((RUN/'colorized'/f'{t}.json').exists() for t in all_tiles)} of {len(all_tiles)} tiles")


if __name__ == "__main__":
    main()
