r"""Cloud-optimised GeoTIFF (COG) masters of the October 22 lidar rasters, for hosting in a cloud bucket (October 22, 2026).

    python reviews/2026-10-22/hosting/cogs/cogs.py build OUT     write the 16 masters
    python reviews/2026-10-22/hosting/cogs/cogs.py verify OUT    COG layout, every cell against its source, overviews
    python reviews/2026-10-22/hosting/cogs/cogs.py compare OUT   DEFLATE, ZSTD and LERC on three float rasters
    python reviews/2026-10-22/hosting/cogs/cogs.py summary OUT   cog-run.json from the three records above

ArcGIS Pro Python (GDAL 3.12; PYTHONNOUSERSITE=1). Read-only on the sources; writes only under OUT.
- Masters are lossless: floats DEFLATE with the floating-point predictor (3), 8-bit rasters DEFLATE (hillshade with the
  horizontal predictor, masks and classes without), 512 x 512 tiles, overviews down to one tile.
- Overviews are rebuilt (OVERVIEWS=IGNORE_EXISTING; the terrain rasters carry ArcGIS .ovr pyramids): NEAREST for aspect,
  masks and class rasters, whose values must stay values that exist; AVERAGE for continuous values.
- EPSG:6341 is assigned to every output. The terrain rasters' CRS is the same NAD83(2011) / UTM 12N but carries no EPSG
  code, which GDAL would write as a user-defined CRS; the ArcGIS Maps SDK reads COGs only with an EPSG code or Esri WKT.
  `build` checks each source's CRS is the same as EPSG:6341 before assigning it, so no cell moves.
- GDAL_PAM_ENABLED=NO: no .aux.xml sidecars are read or written, so each master is one self-contained file. (The two
  ArcGIS value attribute tables, hillshade's and terrain_neighborhood_complete's, hold only VALUE and COUNT.)
- `compare` writes trial copies under OUT\trials, never beside the masters.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time

os.environ["GDAL_PAM_ENABLED"] = "NO"
import numpy as np  # noqa: E402
from osgeo import gdal, osr  # noqa: E402
from osgeo_utils.samples import validate_cloud_optimized_geotiff  # noqa: E402

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[4]
sys.path.insert(0, str(TOOLBOX))
from canopy.lidar_root import lidar_root  # noqa: E402

gdal.UseExceptions()
gdal.SetConfigOption("GDAL_CACHEMAX", "2048")
RUNS = lidar_root()/"2023-salt-lake-valley"/"runs"
LIBRARY = RUNS/"millcreek-products-20261022"
TERRAIN = RUNS/"terrain-city-20261022"
WARNING = "Unvalidated LiDAR planning estimates, not surveyed or field-verified data. City of Millcreek, October 2026."
BLOCK = 512
STRIP = 512
# name: (folder, resampling, meaning). Meanings from reviews/2026-10-22/PRODUCTS.md and terrain-city/README.md.
PRODUCTS = {
    "chm_m": (LIBRARY, "AVERAGE", "Canopy height (m); NoData = unknown or outside the city"),
    "terrain_m": (LIBRARY, "AVERAGE", "Bare-earth elevation (m, NAVD88 Geoid18)"),
    "roof_elevation_m": (LIBRARY, "AVERAGE", "Consensus roof elevation (m), 2 of 3 sources"),
    "roof_height_m": (LIBRARY, "AVERAGE", "Consensus roof height above terrain (m); negatives kept"),
    "observed": (LIBRARY, "NEAREST", "1 observed, 0 unknown; 3 (NoData) outside the city"),
    "vegetation_support": (LIBRARY, "NEAREST", "1 where a vegetation return supports the cell"),
    "building_occlusion": (LIBRARY, "NEAREST", "1 where a consensus roof occludes lower vegetation"),
    "building_sources": (LIBRARY, "NEAREST", "Sources that saw roof in the cell: 1 native + 2 FRACTAL + 4 Esri"),
    "slope_degrees": (TERRAIN, "AVERAGE", "Slope (degrees) over a 3 m neighbourhood"),
    "slope_percent": (TERRAIN, "AVERAGE", "Slope (percent) over a 3 m neighbourhood"),
    "aspect_degrees": (TERRAIN, "NEAREST", "Downslope direction from north (degrees); flat cells -1"),
    "profile_curvature": (TERRAIN, "AVERAGE", "Curvature along the slope"),
    "tangential_curvature": (TERRAIN, "AVERAGE", "Curvature across the slope"),
    "terrain_position_m": (TERRAIN, "AVERAGE", "Elevation minus the mean terrain within 10 m (m)"),
    "hillshade": (TERRAIN, "AVERAGE", "Hillshade, sun 315 degrees at 45 degrees, no shadows; for display"),
    "terrain_neighborhood_complete": (TERRAIN, "NEAREST", "1 where the whole 10 m neighbourhood is terrain"),
}
# Trial encodings for `compare`; the masters' own encoding is the baseline.
TRIAL_RASTERS = ("slope_percent", "terrain_m", "chm_m")
MAX_Z_ERROR = 0.01  # in the raster's units: 0.01 m for terrain, 0.01 percentage points for slope


def source(name):
    return PRODUCTS[name][0]/f"{name}.tif"


def options(name, compress=None, predictor=None, extra=()):
    """COG creation options for one product; the masters' encoding unless overridden."""
    ds = gdal.Open(str(source(name)))
    floating = ds.GetRasterBand(1).DataType == gdal.GDT_Float32
    if compress is None:
        compress = "DEFLATE"
    if predictor is None:
        predictor = "FLOATING_POINT" if floating else ("STANDARD" if name == "hillshade" else "NO")
    opts = [f"COMPRESS={compress}", f"BLOCKSIZE={BLOCK}", f"OVERVIEW_RESAMPLING={PRODUCTS[name][1]}",
            "OVERVIEWS=IGNORE_EXISTING", "NUM_THREADS=ALL_CPUS", "BIGTIFF=IF_SAFER"]
    if compress != "LERC":
        opts.append(f"PREDICTOR={predictor}")
    if compress != "DEFLATE":
        opts.append(f"OVERVIEW_COMPRESS={compress}")
        if compress != "LERC":
            opts.append(f"OVERVIEW_PREDICTOR={predictor}")
    return opts + list(extra)


def overview_config(creation):
    """GDAL config options that make the overviews use the creation options' codec. ArcGIS Pro's GDAL 3.12 COG driver
    wrote DEFLATE overviews whatever COMPRESS and OVERVIEW_COMPRESS said once NUM_THREADS and the other options here were
    set (found October 22 from the files' own tags); the COMPRESS_OVERVIEW config option is honoured. The masters are
    DEFLATE throughout, so this matters only for the trial encodings."""
    values = dict(o.split("=", 1) for o in creation)
    config = {"COMPRESS_OVERVIEW": values.get("OVERVIEW_COMPRESS", values["COMPRESS"])}
    if "OVERVIEW_PREDICTOR" in values:
        config["PREDICTOR_OVERVIEW"] = {"FLOATING_POINT": "3", "STANDARD": "2", "NO": "1"}[values["OVERVIEW_PREDICTOR"]]
    if "MAX_Z_ERROR_OVERVIEW" in values:
        config["MAX_Z_ERROR_OVERVIEW"] = values["MAX_Z_ERROR_OVERVIEW"]
    return config


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def tiff_kind(path):
    with open(path, "rb") as f:
        head = f.read(4)
    return {b"II*\x00": "classic", b"II+\x00": "BigTIFF"}.get(head, head.hex())


TIFF_TAGS = {256: "width", 257: "height", 259: "compression", 317: "predictor", 34735: "geokeys"}
CODECS = {1: "NONE", 5: "LZW", 8: "DEFLATE", 34887: "LERC", 50000: "ZSTD"}


def tiff_ifds(path):
    """Every image directory's size, compression, predictor and GeoKeyDirectory, read from the file itself (little-endian
    classic TIFF or BigTIFF): GDAL reports only the full-resolution image's compression."""
    import struct
    formats = {3: ("H", 2), 4: ("I", 4), 16: ("Q", 8)}
    ifds = []
    with open(path, "rb") as f:
        head = f.read(16)
        big = head[2:4] == b"+\x00"
        offset = struct.unpack("<Q", head[8:16])[0] if big else struct.unpack("<I", head[4:8])[0]
        size, count_fmt, ptr_fmt = (20, "<Q", "<Q") if big else (12, "<H", "<I")
        while offset:
            f.seek(offset)
            count = struct.unpack(count_fmt, f.read(struct.calcsize(count_fmt)))[0]
            entries = f.read(count*size)
            offset = struct.unpack(ptr_fmt, f.read(struct.calcsize(ptr_fmt)))[0]
            ifd = {}
            for k in range(count):
                e = entries[k*size:(k+1)*size]
                tag, kind = struct.unpack("<HH", e[:4])
                if tag not in TIFF_TAGS or kind not in formats:
                    continue
                n = struct.unpack("<Q" if big else "<I", e[4:12] if big else e[4:8])[0]
                fmt, width = formats[kind]
                inline = e[12:20] if big else e[8:12]
                if n*width <= len(inline):
                    raw = inline[:n*width]
                else:
                    here = f.tell()
                    f.seek(struct.unpack(ptr_fmt, inline)[0])
                    raw = f.read(n*width)
                    f.seek(here)
                values = struct.unpack(f"<{n}{fmt}", raw)
                ifd[TIFF_TAGS[tag]] = values if tag == 34735 else values[0]
            ifds.append(ifd)
    return ifds


def geokeys(path):
    """The GeoKeyDirectory as {key: value}. ArcGIS Pro's GDAL build adds an ESRI PE string to the citation and then
    reports the CRS without its EPSG code, so the code is checked in the file."""
    v = tiff_ifds(path)[0].get("geokeys", ())
    return {v[i]: (v[i+3] if v[i+1] == 0 else f"tag {v[i+1]}") for i in range(4, 4+4*v[3], 4)} if v else {}


def codecs(path):
    """[width, height, compression, predictor] for the full-resolution image and each overview."""
    return [[d.get("width"), d.get("height"), CODECS.get(d.get("compression"), d.get("compression")),
             d.get("predictor", 1)] for d in tiff_ifds(path)]


def epsg_6341():
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(6341)
    return srs


def translate(name, dst, creation):
    src = gdal.Open(str(source(name)))
    if not src.GetSpatialRef().IsSame(epsg_6341()):
        raise SystemExit(f"{name}: CRS is not EPSG:6341; refusing to assign it")
    if src.GetRasterBand(1).GetNoDataValue() is None:
        raise SystemExit(f"{name}: source has no NoData value")
    dst.parent.mkdir(parents=True, exist_ok=True)
    # The masters (DEFLATE) were built without the config options; they apply only to the trial encodings.
    config = overview_config(creation) if "COMPRESS=DEFLATE" not in creation else {}
    start = time.perf_counter()
    with gdal.config_options(config):
        gdal.Translate(str(dst), src, format="COG", outputSRS="EPSG:6341", creationOptions=creation,
                       metadataOptions=[f"WARNING={WARNING}", f"MEANING={PRODUCTS[name][2]}",
                                        "SOURCE=" + str(source(name)).replace("\\", "/")])
    return round(time.perf_counter()-start, 1)


def build(out):
    library = json.loads((LIBRARY/"library.json").read_text())["products"]
    record = {"schema": "cog-masters/1", "started": datetime.datetime.now().isoformat(timespec="seconds"),
              "gdal": gdal.__version__, "warning": WARNING, "block": BLOCK, "products": {}}
    for name in PRODUCTS:
        src = source(name)
        digest = sha256(src)
        listed = library.get(f"{name}.tif", {}).get("sha256")
        if listed and listed != digest:
            raise SystemExit(f"{name}: source SHA-256 differs from library.json")
        creation = options(name)
        dst = out/f"{name}.tif"
        print(f"{name} ...", flush=True)
        seconds = translate(name, dst, creation)
        record["products"][name] = {
            "source": str(src), "source_sha256": digest, "source_sha256_in_library_json": bool(listed),
            "source_bytes": src.stat().st_size, "cog": str(dst), "cog_bytes": dst.stat().st_size,
            "cog_sha256": sha256(dst), "tiff": tiff_kind(dst), "creation_options": creation,
            "overview_resampling": PRODUCTS[name][1], "meaning": PRODUCTS[name][2], "seconds": seconds}
        print(f"  {dst.stat().st_size/1e6:,.1f} MB in {seconds} s", flush=True)
    record["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
    (out/"build.json").write_text(json.dumps(record, indent=1))


def strips(ds, rows=STRIP):
    for y in range(0, ds.RasterYSize, rows):
        yield y, min(rows, ds.RasterYSize-y)


def equal_cells(src, cog):
    """Byte comparison of every cell in strips, so NoData and every float bit pattern are included."""
    a, b = src.GetRasterBand(1), cog.GetRasterBand(1)
    width = src.RasterXSize
    dtype = np.float32 if a.DataType == gdal.GDT_Float32 else np.uint8
    nodata = a.GetNoDataValue()
    valid = 0
    summary = {"min": np.inf, "max": -np.inf, "sum": 0.0, "sumsq": 0.0}
    counts = np.zeros(256, np.int64) if dtype == np.uint8 else None
    for y, rows in strips(src):
        sa, sb = a.ReadRaster(0, y, width, rows), b.ReadRaster(0, y, width, rows)
        if sa != sb:
            return {"equal": False, "first_bad_strip_row": y}
        v = np.frombuffer(sa, dtype)
        if counts is not None:
            counts += np.bincount(v, minlength=256)
        keep = v[v != dtype(nodata)]
        valid += keep.size
        if keep.size:
            k = keep.astype(np.float64)
            summary["min"] = min(summary["min"], k.min())
            summary["max"] = max(summary["max"], k.max())
            summary["sum"] += k.sum()
            summary["sumsq"] += (k*k).sum()
    mean = summary["sum"]/valid
    result = {"equal": True, "cells": width*src.RasterYSize, "valid_cells": valid,
              "min": float(summary["min"]), "max": float(summary["max"]), "mean": round(mean, 6),
              "std": round(float(np.sqrt(summary["sumsq"]/valid-mean*mean)), 6)}
    if counts is not None:
        result["values"] = {str(i): int(c) for i, c in enumerate(counts) if c}
    return result


def window(band, x, y, w, h, dtype):
    return np.frombuffer(band.ReadRaster(x, y, w, h), dtype).reshape(h, w)


def footprints(size, osize, start, n):
    """Source cells under overview cells start..start+n-1 on one axis: the first index and how many (2 or 3). The grid is
    odd (24,501 x 12,247), so an overview cell covers 1.9998 source cells, not exactly 2, and blocks drift off a 2 x 2
    alignment across the grid."""
    ratio = size/osize
    i = np.arange(start, start+n)
    lo = np.floor(i*ratio).astype(int)
    hi = np.minimum(np.ceil((i+1)*ratio).astype(int), size)
    # The core: cells wholly inside the overview cell, which any resampling window includes.
    core = (np.ceil(i*ratio).astype(int)-lo, np.floor((i+1)*ratio).astype(int)-lo)
    return lo, hi-lo, core


def check_overview(src, cog, resampling):
    """Overview level 1 against the source on a 1,024 x 1,024 window at the centre of the grid. NEAREST: every overview
    value is one of the source cells it covers. AVERAGE: every value lies within the range of the valid source cells it
    covers, and NoData only where all the cells wholly inside it are NoData."""
    a, ov = src.GetRasterBand(1), cog.GetRasterBand(1).GetOverview(0)
    dtype = np.float32 if a.DataType == gdal.GDT_Float32 else np.uint8
    nodata = dtype(a.GetNoDataValue())
    n = 1024
    ox, oy = ov.XSize//2 - n//2, ov.YSize//2 - n//2
    lx, cx, (bx, ex) = footprints(src.RasterXSize, ov.XSize, ox, n)
    ly, cy, (by, ey) = footprints(src.RasterYSize, ov.YSize, oy, n)
    x0, y0 = int(lx[0]), int(ly[0])
    s = window(a, x0, y0, int(lx[-1]+cx[-1])-x0, int(ly[-1]+cy[-1])-y0, dtype)
    o = window(ov, ox, oy, n, n, dtype)
    # Up to 3 x 3 source cells per overview cell; stack them with flags for the footprint and its core.
    cells, inside, core = [], [], []
    for ky in range(3):
        for kx in range(3):
            iy, ix = np.minimum(ly-y0+ky, s.shape[0]-1), np.minimum(lx-x0+kx, s.shape[1]-1)
            cells.append(s[iy[:, None], ix[None, :]])
            inside.append((ky < cy)[:, None] & (kx < cx)[None, :])
            core.append(((ky >= by) & (ky < ey))[:, None] & ((kx >= bx) & (kx < ex))[None, :])
    cells, inside, core = np.stack(cells, axis=2), np.stack(inside, axis=2), np.stack(core, axis=2)
    result = {"overview_window": [int(ox), int(oy), n, n], "source_window": [x0, y0, *s.shape[::-1]],
              "valid_overview_cells": int((o != nodata).sum())}
    if resampling == "NEAREST":
        member = ((cells == o[:, :, None]) & inside).any(axis=2)
        result["every_value_from_its_footprint"] = bool(member.all())
        result["ok"] = result["every_value_from_its_footprint"]
    else:
        valid = inside & (cells != nodata)
        empty = ~(core & (cells != nodata)).any(axis=2)
        k = cells.astype(np.float64)
        low = np.where(valid, k, np.inf).min(axis=2)
        high = np.where(valid, k, -np.inf).max(axis=2)
        has = o != nodata
        v = o.astype(np.float64)
        tol = 1e-6*max(1.0, float(np.abs(v[has]).max(initial=0)))
        within = ~has | ((v >= low-tol) & (v <= high+tol))
        result.update({"values_within_footprint_range": bool(within.all()),
                       "nodata_only_where_core_empty": bool(not (~has & ~empty).any()),
                       "core_empty_but_value": int((has & empty).sum())})
        result["ok"] = result["values_within_footprint_range"] and result["nodata_only_where_core_empty"]
    return result


def describe(path, cog):
    band = cog.GetRasterBand(1)
    keys = geokeys(path)
    return {"size": [cog.RasterXSize, cog.RasterYSize], "block": band.GetBlockSize(),
            "overviews": [[band.GetOverview(i).XSize, band.GetOverview(i).YSize] for i in range(band.GetOverviewCount())],
            "projected_cs_type_geokey": keys.get(3072), "geographic_type_geokey": keys.get(2048),
            "tiff": tiff_kind(path), "ifd_codecs": codecs(path), "structure": cog.GetMetadata("IMAGE_STRUCTURE"), "metadata": cog.GetMetadata()}


def verify(out):
    build_record = json.loads((out/"build.json").read_text())
    record = {"schema": "cog-masters-verify/1", "started": datetime.datetime.now().isoformat(timespec="seconds"),
              "strip_rows": STRIP, "products": {}}
    for name in PRODUCTS:
        print(f"{name} ...", flush=True)
        path = out/f"{name}.tif"
        src, cog = gdal.Open(str(source(name))), gdal.Open(str(path))
        warnings, errors, details = validate_cloud_optimized_geotiff.validate(str(path), full_check=True)
        a, b = src.GetRasterBand(1), cog.GetRasterBand(1)
        info = describe(path, cog)
        same = {"size": (src.RasterXSize, src.RasterYSize) == (cog.RasterXSize, cog.RasterYSize),
                "geotransform": src.GetGeoTransform() == cog.GetGeoTransform(),
                "dtype": a.DataType == b.DataType, "nodata": a.GetNoDataValue() == b.GetNoDataValue(),
                "crs": src.GetSpatialRef().IsSame(cog.GetSpatialRef()) == 1}
        cells = equal_cells(src, cog)
        overview = check_overview(src, cog, PRODUCTS[name][1])
        predictor = {"FLOATING_POINT": 3, "STANDARD": 2, "NO": 1}[
            next(o.split("=")[1] for o in build_record["products"][name]["creation_options"] if o.startswith("PREDICTOR="))]
        info["every_ifd_deflate_with_predictor"] = all(c[2] == "DEFLATE" and c[3] == predictor for c in info["ifd_codecs"])
        ok = (not errors and all(same.values()) and cells["equal"] and overview["ok"]
              and info["projected_cs_type_geokey"] == 6341 and info["every_ifd_deflate_with_predictor"]
              and build_record["products"][name]["cog_sha256"] == sha256(path))
        record["products"][name] = {"ok": ok, "cog_validation": {"errors": errors, "warnings": warnings,
                                                                 "details": details},
                                    "same_as_source": same, "dtype": gdal.GetDataTypeName(a.DataType),
                                    "nodata": a.GetNoDataValue(), "cells": cells, "overview_level_1": overview, **info}
        print(f"  {'ok' if ok else 'FAILED'}", flush=True)
    record["all_ok"] = all(p["ok"] for p in record["products"].values())
    record["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
    (out/"verify.json").write_text(json.dumps(record, indent=1))
    if not record["all_ok"]:
        raise SystemExit("verification failed")


def read_speed(path, tiles=400, seed=20261022, repeats=3):
    """Seconds to read every cell in strips, and to read random full-resolution 512 x 512 tiles, best of `repeats` (the
    laptop runs other work, and single timings varied by 2x). The file was just written or read, so it is in the OS
    cache: these are decode times, not disk or network times."""
    rng = np.random.default_rng(seed)
    full, random = [], []
    for _ in range(repeats):
        ds = gdal.Open(str(path))  # a fresh dataset has an empty GDAL block cache
        band = ds.GetRasterBand(1)
        start = time.perf_counter()
        for y, rows in strips(ds):
            band.ReadRaster(0, y, ds.RasterXSize, rows)
        full.append(time.perf_counter()-start)
        nx, ny = ds.RasterXSize//BLOCK, ds.RasterYSize//BLOCK
        picks = [(int(rng.integers(nx)), int(rng.integers(ny))) for _ in range(tiles)]
        ds = gdal.Open(str(path))
        band = ds.GetRasterBand(1)
        start = time.perf_counter()
        for tx, ty in picks:
            band.ReadRaster(tx*BLOCK, ty*BLOCK, BLOCK, BLOCK)
        random.append(time.perf_counter()-start)
    return {"full_read_s": round(min(full), 2), "full_read_s_all": [round(s, 2) for s in full],
            "random_tiles": tiles, "random_tiles_s": round(min(random), 3),
            "ms_per_tile": round(1000*min(random)/tiles, 2), "repeats": repeats}


def level_bytes(path):
    """Compressed bytes of the full-resolution tiles and of all overview tiles, from the TIFF tile byte counts."""
    ds = gdal.Open(str(path))
    band = ds.GetRasterBand(1)

    def total(b):
        bx, by = b.GetBlockSize()
        return sum(int(b.GetMetadataItem(f"BLOCK_SIZE_{x}_{y}", "TIFF") or 0)
                   for y in range(-(-b.YSize//by)) for x in range(-(-b.XSize//bx)))
    return {"full_resolution_bytes": total(band),
            "overview_bytes": sum(total(band.GetOverview(i)) for i in range(band.GetOverviewCount()))}


def lossy_error(src_path, path):
    """Largest absolute difference from the source on valid cells, and whether NoData stays exactly where it was."""
    src, ds = gdal.Open(str(src_path)), gdal.Open(str(path))
    a, b = src.GetRasterBand(1), ds.GetRasterBand(1)
    nodata = np.float32(a.GetNoDataValue())
    worst, same_mask, valid = 0.0, True, 0
    for y, rows in strips(src):
        s = np.frombuffer(a.ReadRaster(0, y, src.RasterXSize, rows), np.float32)
        d = np.frombuffer(b.ReadRaster(0, y, src.RasterXSize, rows), np.float32)
        ms, md = s == nodata, d == np.float32(b.GetNoDataValue())
        same_mask &= bool(np.array_equal(ms, md))
        both = ~ms & ~md
        valid += int(both.sum())
        if both.any():
            worst = max(worst, float(np.abs(s[both].astype(np.float64)-d[both]).max()))
    return {"max_abs_error": worst, "nodata_cells_unchanged": same_mask, "valid_cells_compared": valid}


def compare(out):
    trials = out/"trials"
    record = {"schema": "cog-compression-trial/1", "started": datetime.datetime.now().isoformat(timespec="seconds"),
              "gdal": gdal.__version__, "max_z_error": MAX_Z_ERROR, "rasters": {}}
    variants = {
        "deflate-pred3": None,  # the master itself
        "deflate-nopred": ("DEFLATE", "NO", ()),
        "zstd-pred3": ("ZSTD", "FLOATING_POINT", ()),
        f"lerc-{MAX_Z_ERROR:g}": ("LERC", None, (f"MAX_Z_ERROR={MAX_Z_ERROR}", f"MAX_Z_ERROR_OVERVIEW={MAX_Z_ERROR}")),
    }
    for name in TRIAL_RASTERS:
        src = source(name)
        raw = gdal.Open(str(src))
        uncompressed = raw.RasterXSize*raw.RasterYSize*4
        rows = {}
        for key, spec in variants.items():
            print(f"{name} {key} ...", flush=True)
            if spec is None:
                path, seconds, creation = out/f"{name}.tif", None, options(name)
            else:
                compress, predictor, extra = spec
                path = trials/f"{name}.{key}.tif"
                creation = options(name, compress, predictor, extra)
                seconds = translate(name, path, creation)
            row = {"file": str(path), "creation_options": creation, "bytes": path.stat().st_size, "write_s": seconds,
                   "ratio_vs_uncompressed_float32": round(uncompressed/path.stat().st_size, 2),
                   "cog_errors": validate_cloud_optimized_geotiff.validate(str(path), full_check=False)[1],
                   "ifd_codecs": codecs(path), **level_bytes(path), **read_speed(path)}
            asked = dict(o.split("=", 1) for o in creation)["COMPRESS"]
            row["every_ifd_codec_as_asked"] = all(c[2] == asked for c in row["ifd_codecs"])
            if not row["every_ifd_codec_as_asked"]:
                raise SystemExit(f"{path}: overviews not written as {asked}: {row['ifd_codecs']}")
            if spec is not None and spec[0] == "LERC":
                row.update(lossy_error(src, path))
            elif spec is not None:
                row["cells_equal_master"] = equal_cells(raw, gdal.Open(str(path)))["equal"]
            rows[key] = row
            print(f"  {row['bytes']/1e6:,.1f} MB, full read {row['full_read_s']} s, {row['ms_per_tile']} ms/tile", flush=True)
        record["rasters"][name] = {"uncompressed_float32_bytes": uncompressed, "source_bytes": src.stat().st_size,
                                   "source_compression": raw.GetMetadata("IMAGE_STRUCTURE"), "variants": rows}
    record["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
    (out/"compare.json").write_text(json.dumps(record, indent=1))


def summary(out):
    """cog-run.json: one row per master (sizes, ratios, checks) and the comparison's sizes and speeds."""
    built = json.loads((out/"build.json").read_text())
    checked = json.loads((out/"verify.json").read_text())
    compared = json.loads((out/"compare.json").read_text())
    rows = {}
    for name, b in built["products"].items():
        v = checked["products"][name]
        width, height = v["size"]
        uncompressed = width*height*(4 if v["dtype"] == "Float32" else 1)
        rows[name] = {
            "dtype": v["dtype"], "nodata": v["nodata"], "overview_resampling": b["overview_resampling"],
            "predictor": next(o.split("=")[1] for o in b["creation_options"] if o.startswith("PREDICTOR=")),
            "source_bytes": b["source_bytes"], "cog_bytes": b["cog_bytes"], **level_bytes(out/f"{name}.tif"),
            "uncompressed_bytes": uncompressed, "ratio_vs_uncompressed": round(uncompressed/b["cog_bytes"], 2),
            "cog_vs_source": round(b["cog_bytes"]/b["source_bytes"], 3), "overviews": len(v["overviews"]),
            "tiff": b["tiff"], "cog_sha256": b["cog_sha256"], "valid_cells": v["cells"]["valid_cells"],
            "checks": {"cog_layout_errors": len(v["cog_validation"]["errors"]),
                       "cog_layout_warnings": len(v["cog_validation"]["warnings"]),
                       "every_cell_equal": v["cells"]["equal"], "same_as_source": all(v["same_as_source"].values()),
                       "epsg_6341_key": v["projected_cs_type_geokey"] == 6341,
                       "every_ifd_deflate_with_predictor": v["every_ifd_deflate_with_predictor"],
                       "overview_level_1": v["overview_level_1"]["ok"], "ok": v["ok"]}}
    trial = {name: {key: {k: r.get(k) for k in ("bytes", "full_resolution_bytes", "overview_bytes",
                                                   "ratio_vs_uncompressed_float32", "write_s", "full_read_s",
                                                   "ms_per_tile", "max_abs_error", "nodata_cells_unchanged",
                                                   "cells_equal_master", "ifd_codecs") if k in r}
                     for key, r in t["variants"].items()}
             for name, t in compared["rasters"].items()}
    record = {"schema": "cog-run/1", "status": "PRELIMINARY_UNVALIDATED planning estimates", "warning": WARNING,
              "gdal": built["gdal"], "output": str(out), "built": [built["started"], built["finished"]],
              "verified": [checked["started"], checked["finished"]], "all_ok": checked["all_ok"],
              "total_cog_bytes": sum(r["cog_bytes"] for r in rows.values()),
              "total_source_bytes": sum(r["source_bytes"] for r in rows.values()),
              "products": rows, "compression_trial": {"max_z_error": compared["max_z_error"], "rasters": trial}}
    (out/"cog-run.json").write_text(json.dumps(record, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=("build", "verify", "compare", "summary"))
    p.add_argument("out", type=Path)
    args = p.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    {"build": build, "verify": verify, "compare": compare, "summary": summary}[args.command](args.out)


if __name__ == "__main__":
    main()
