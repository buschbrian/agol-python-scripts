"""Fetch one raw four-band NAIP GeoTIFF for an extent from the USGS NAIP image service. Read-only; no sign-in.

    python reviews/2026-09-30/naip_fetch.py 12TVL2804 428000 4504000 429000 4505000 NEW_OUTPUT_DIR [--cell 0.5]

Follows reviews/2026-09-29/NAIP_GREENNESS.md: an unrendered TIFF (rasterFunction None, bandIds 0-3, never an RGB
preview), exported with the primary scenes locked so dates cannot mix. Only the newest acquisition date among the
primary four-band scenes that intersect the extent is used. Writes naip_TILE.tif and naip_TILE_metadata.json, which
carries what naip_review.py requires (source, survey_date, band_mapping, the image fingerprint) plus the scene
records, the exact request and the limits. The output folder must be new. Nothing on the service is changed.
"""
import argparse
import datetime
import json
from pathlib import Path
import sys

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from canopy.run_safeguards import fingerprint  # noqa: E402

SERVICE = "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer"
BAND_MAPPING = {"red": 1, "green": 2, "blue": 3, "nir": 4}
MAX_SIDE_PX = 4000            # the service's own maxImageWidth/Height
TIFF_SIGNATURES = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")


def _json(response):
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise RuntimeError(f"Service error: {data['error']}")
    return data


def day(ms):
    return datetime.datetime.fromtimestamp(ms/1000, datetime.timezone.utc).strftime("%Y-%m-%d")


def verify_bands(info):
    """Require four U8 bands and evidence that they are red, green, blue, near-infrared; return that evidence.

    The service names its bands band_1 to band_4, so the order is taken from its own raster-function descriptions:
    NaturalColor must use bands 1, 2, 3 as red, green, blue, and FalseColorComposite must use 4, 1, 2 as
    near-infrared, red, green. The quoted descriptions are returned for the metadata. Missing or different text
    refuses, rather than assuming the order.
    """
    if info.get("bandCount") != 4 or info.get("pixelType") != "U8":
        raise ValueError(f"Expected a four-band U8 service, got {info.get('bandCount')} bands, {info.get('pixelType')}")
    described = {f.get("name"): str(f.get("description") or "") for f in info.get("rasterFunctionInfos", [])}
    natural, false_colour = described.get("NaturalColor", ""), described.get("FalseColorComposite", "")
    ok = ("red, green, blue" in natural.lower() and "(1, 2, 3)" in natural and
          "near-infrared, red, green" in false_colour.lower() and "(4, 1, 2)" in false_colour)
    if not ok:
        raise ValueError("Band order is not confirmed as red, green, blue, near-infrared by the service's own "
                         f"raster-function descriptions: {natural!r} / {false_colour!r}")
    return {"NaturalColor": natural, "FalseColorComposite": false_colour}


def primary_scenes(rows):
    """The newest acquisition date's primary (Category 1) four-band scenes, by OBJECTID."""
    primary = [r for r in rows if r.get("Category") == 1 and r.get("band_count") == 4 and r.get("acquisition_date")]
    if not primary:
        raise ValueError("No primary four-band NAIP scene intersects this extent")
    newest = max(r["acquisition_date"] for r in primary)
    return sorted((r for r in primary if r["acquisition_date"] == newest), key=lambda r: r["OBJECTID"])


def export_params(extent, epsg, cell, scene_ids):
    xmin, ymin, xmax, ymax = extent
    width, height = round((xmax-xmin)/cell), round((ymax-ymin)/cell)
    if max(width, height) > MAX_SIDE_PX:
        raise ValueError(f"{width} x {height} pixels exceeds the service limit of {MAX_SIDE_PX}; fetch in pieces")
    if abs(width*cell-(xmax-xmin)) > 1e-6 or abs(height*cell-(ymax-ymin)) > 1e-6:
        raise ValueError("The extent is not a whole number of cells")
    return {"f": "image", "format": "tiff", "pixelType": "U8", "bbox": f"{xmin},{ymin},{xmax},{ymax}",
            "bboxSR": epsg, "imageSR": epsg, "size": f"{width},{height}", "bandIds": "0,1,2,3",
            "interpolation": "RSP_NearestNeighbor", "noDataInterpretation": "esriNoDataMatchAny",
            "renderingRule": json.dumps({"rasterFunction": "None"}),
            "mosaicRule": json.dumps({"mosaicMethod": "esriMosaicLockRaster", "lockRasterIds": list(scene_ids),
                                      "ascending": True, "mosaicOperation": "MT_FIRST"})}


def check_tiff(data):
    if data[:4] not in TIFF_SIGNATURES:
        raise RuntimeError(f"The service did not return a TIFF: {data[:200]!r}")


def fetch(tile, extent, epsg, cell, out_dir, session=requests, service=SERVICE):
    out_dir = Path(out_dir)
    if out_dir.exists():
        raise FileExistsError(f"Choose a new output folder: {out_dir}")
    info = _json(session.get(service, params={"f": "json"}, timeout=60))
    band_evidence = verify_bands(info)
    xmin, ymin, xmax, ymax = extent
    geometry = {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax, "spatialReference": {"wkid": epsg}}
    catalog = _json(session.get(service + "/query", params={
        "f": "json", "where": "1=1", "geometry": json.dumps(geometry), "geometryType": "esriGeometryEnvelope",
        "inSR": epsg, "spatialRel": "esriSpatialRelIntersects", "outFields": "*", "returnGeometry": "false"}, timeout=90))
    if catalog.get("exceededTransferLimit"):
        raise RuntimeError("The catalog query was truncated; narrow the extent")
    scenes = primary_scenes([f["attributes"] for f in catalog.get("features", [])])
    params = export_params(extent, epsg, cell, [s["OBJECTID"] for s in scenes])
    response = session.get(service + "/exportImage", params=params, timeout=300)
    response.raise_for_status()
    check_tiff(response.content)
    out_dir.mkdir(parents=True)
    image = out_dir/f"naip_{tile}.tif"
    image.write_bytes(response.content)
    dates = sorted({day(s["acquisition_date"]) for s in scenes})
    record = {"source": "NAIP", "survey_date": dates[-1], "band_mapping": dict(BAND_MAPPING),
              "image": fingerprint(image), "tile": tile, "epsg": epsg, "extent": list(extent), "cell_size_m": cell,
              "size_px": params["size"], "resampling": "nearest neighbour from the 0.6 m source scenes",
              "service": service, "band_order_evidence": band_evidence,
              "scenes": [{k: s.get(k) for k in ("OBJECTID", "Name", "acquisition_date", "vendor", "agency",
                                                "resolution_value", "resolution_units", "sensor_type", "download_url")}
                         | {"acquisition_day": day(s["acquisition_date"])} for s in scenes],
              "request": {k: v for k, v in params.items()},
              "fetched_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
              "limits": ["Acquired on the scene date above, not the lidar date (2023-10-07 to 2023-11-05).",
                         "Values are the source scenes' digital numbers, not reflectance; roof lean, shadow and "
                         "seasonal colour apply.",
                         "Nothing on the service was modified; the request is read-only."]}
    meta = out_dir/f"naip_{tile}_metadata.json"
    meta.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("tile")
    p.add_argument("xmin", type=float); p.add_argument("ymin", type=float)
    p.add_argument("xmax", type=float); p.add_argument("ymax", type=float)
    p.add_argument("out", type=Path)
    p.add_argument("--cell", type=float, default=0.5)
    p.add_argument("--epsg", type=int, default=6341)
    args = p.parse_args(argv)
    record = fetch(args.tile, (args.xmin, args.ymin, args.xmax, args.ymax), args.epsg, args.cell, args.out)
    print(json.dumps({k: record[k] for k in ("survey_date", "size_px", "cell_size_m")}, indent=1))
    print("scenes:", [(s["OBJECTID"], s["Name"]) for s in record["scenes"]])
    print("image:", record["image"]["path"], record["image"]["bytes"], "bytes")


if __name__ == "__main__":
    main()
