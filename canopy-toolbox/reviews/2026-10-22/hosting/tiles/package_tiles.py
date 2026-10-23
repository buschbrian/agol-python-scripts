r"""Hillshade raster tile package and terrain elevation tile package for ArcGIS Online (October 22, 2026), built and checked
locally. Nothing here uploads, publishes or shares.

    python reviews/2026-10-22/hosting/tiles/package_tiles.py scheme OUT    tiling schemes from Pro's built-in ones, edited
    python reviews/2026-10-22/hosting/tiles/package_tiles.py layer OUT     the hillshade layer file (no stretch) and the AOIs
    python reviews/2026-10-22/hosting/tiles/package_tiles.py pilot OUT     both caches on a 1 km window, defaults against ours
    python reviews/2026-10-22/hosting/tiles/package_tiles.py build OUT     both caches and .tpkx packages, levels 0-18
    python reviews/2026-10-22/hosting/tiles/package_tiles.py verify OUT    tile counts, coverage, values, opens in Pro

ArcGIS Pro Python (PYTHONNOUSERSITE=1). Read-only on the inputs; writes only under OUT (keep OUT short: ERROR 2592).
- No map or Pro UI: Manage Tile Cache takes a raster dataset, or a raster layer file, as its data source, and Export Tile
  Cache turns the cache into a .tpkx. Create Map Tile Package is the tool that needs a map; it is not used.
- Hillshade: the layer file is needed because Manage Tile Cache renders a raster with its default renderer, a 2-standard-
  deviation stretch, which put every hillshade value below about 115 to black in the pilot. A rendered (253, 253, 253) is
  the cache's transparent background, so the layer file draws a copy capped at 252 with no stretch and bilinear display
  resampling. Tiles are PNG32 on the ArcGIS Online scheme.
- Terrain: the unmasked mosaic on the ArcGIS Online elevation scheme (LERC, 257 x 257 corner-registered pixels), with
  the LERC maximum error set to 0.01 m instead of the scheme's 0.1 m.
- No geographic transformation (env.geographicTransformations unset): NAD83(2011) coordinates are taken as WGS84 when
  projected to Web Mercator. The pilot showed this is what the tool does, and the verifier projects the same way.
- Levels 0-18: level 18 is 0.597 m in Web Mercator, about 0.45 m on the ground at Millcreek (x cos 40.7 degrees), the
  first level at least as fine as the 0.5 m source; level 19 would be 4x the tiles with nothing new in them.
"""
import argparse
import datetime
import glob
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import zipfile

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[4]
sys.path.insert(0, str(TOOLBOX))
from canopy.lidar_root import lidar_root  # noqa: E402

VALLEY = lidar_root()/"2023-salt-lake-valley"
RUNS = VALLEY/"runs"
HILLSHADE = RUNS/"terrain-city-20261022"/"hillshade.tif"
SLOPE = RUNS/"terrain-city-20261022"/"slope_degrees.tif"
TERRAIN_CITY = RUNS/"millcreek-products-20261022"/"terrain_m.tif"
TERRAIN_CONTEXT = RUNS/"millcreek-products-20261019"/"terrain_context.tif"
BOUNDARY = RUNS/"city-count-20261008"/"inputs.gdb"/"municipal_boundary"
PRO_SCHEMES = {"hillshade": "ARCGISONLINE_SCHEME", "terrain": "ARCGISONLINE_ELEVATION_SCHEME"}
# PNG32, not PNG: Pro's PNG writes gray RGB tiles with a (253, 253, 253) transparency key; PNG32 carries an alpha channel.
TILE_FORMAT = "PNG32"
# Manage Tile Cache treats a rendered (253, 253, 253) as its transparent background in either format, which punched the
# brightest hillshade pixels out. Bilinear display makes 253 from neighbouring 252 and 254, so the tiles are drawn from a
# copy capped at 252 (253 and 254 become 252) with no stretch: no rendered value can then reach 253.
HILLSHADE_TOP = 252
LERC_ERROR_M = 0.01
MAX_LEVEL = 18
ORIGIN = -20037508.342787001
RES0 = 156543.03392799999
EARTH_R = 6378137.0
PACKAGES = {"hillshade": "millcreek_hillshade_20261022", "terrain": "millcreek_terrain_20261022"}
# The pilot window: the north-east corner of the bounding box, where both the city edge and the mosaic edge cross it.
PILOT = (433349.0, 4506383.0, 434349.0, 4507383.0)
WARNING = ("Unvalidated LiDAR planning estimates. Hillshade is for display; terrain is interpolated class-2 ground at 0.5 m, "
           "NAVD88 (Geoid18) metres, not a surveyed surface.")


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def write_json(path, record):
    Path(path).write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")


def resolution(level):
    return RES0/2**level


def scale(level):
    """The scheme's scale for a level, exactly as Manage Tile Cache lists it (a computed value is refused)."""
    return SCALES[level]


SCALES = (591657527.591555, 295828763.795777, 147914381.897889, 73957190.948944, 36978595.474472, 18489297.737236,
          9244648.868618, 4622324.434309, 2311162.217155, 1155581.108577, 577790.554289, 288895.277144, 144447.638572,
          72223.819286, 36111.909643, 18055.954822, 9027.977411, 4513.988705, 2256.994353)


def env(out):
    import arcpy
    scratch = Path(out)/"scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    arcpy.env.scratchWorkspace = str(scratch)
    arcpy.env.workspace = str(scratch)
    arcpy.env.overwriteOutput = True
    arcpy.env.geographicTransformations = None
    return arcpy


# Tiling schemes ------------------------------------------------------------------------------------------------------

def scheme(out):
    """Pro's ArcGIS Online and elevation schemes, as Manage Tile Cache writes them, with the format and LERC error set."""
    arcpy = env(out)
    folder = Path(out)/"schemes"
    folder.mkdir(exist_ok=True)
    base = folder/"base"
    base.mkdir(exist_ok=True)
    # Two levels of a 200 m square are enough for the tool to write its conf.xml (a cache of levels 0-1 fails).
    aoi = window_aoi(arcpy, base/"aoi.shp", (PILOT[0], PILOT[1], PILOT[0] + 200, PILOT[1] + 200))
    record = {}
    for key, builtin in PRO_SCHEMES.items():
        source = str(HILLSHADE if key == "hillshade" else TERRAIN_CONTEXT)
        arcpy.management.ManageTileCache(str(base), "RECREATE_ALL_TILES", key, source, builtin, None, None, str(aoi),
                                         None, scale(17), scale(18))
        text = (base/key/"conf.xml").read_text(encoding="utf-8")
        default = {"format": re.search(r"<CacheTileFormat>(\w+)<", text).group(1),
                   "lerc_error": float(re.search(r"<LERCError>([^<]*)<", text).group(1))}
        if key == "hillshade":
            text = re.sub(r"<CacheTileFormat>\w+<", f"<CacheTileFormat>{TILE_FORMAT}<", text)
        else:
            text = re.sub(r"<LERCError>[^<]*<", f"<LERCError>{LERC_ERROR_M}<", text)
        (folder/f"{key}.xml").write_text(text, encoding="utf-8")
        record[key] = {"builtin": builtin, "default": default, "file": str(folder/f"{key}.xml"),
                       "levels": len(re.findall("<LevelID>", text)),
                       "tile_size": int(re.search(r"<TileCols>(\d+)<", text).group(1))}
    shutil.rmtree(folder/"base")
    write_json(folder/"schemes.json", record)
    print(json.dumps(record, indent=1))


# Layer file and areas of interest ------------------------------------------------------------------------------------

def capped_hillshade(target):
    """A copy of the hillshade with 253 and 254 set to HILLSHADE_TOP; NoData (255) and everything else unchanged."""
    import rasterio
    with rasterio.open(HILLSHADE) as src:
        data = src.read(1)
        profile = src.profile
    valid = data != src.nodata
    changed = int((valid & (data > HILLSHADE_TOP)).sum())
    data[valid & (data > HILLSHADE_TOP)] = HILLSHADE_TOP
    profile.update(compress="lzw", tiled=True, blockxsize=512, blockysize=512)
    with rasterio.open(target, "w", **profile) as dst:
        dst.write(data, 1)
    return {"cells": int(valid.sum()), "changed": changed}


def layer(out):
    """The capped hillshade as a layer file drawn with no stretch, and the areas of interest for both caches."""
    arcpy = env(out)
    folder = Path(out)/"layer"
    folder.mkdir(exist_ok=True)
    display = folder/"hillshade_display.tif"
    capped = capped_hillshade(display)
    if not (folder/"layers.aprx").exists():
        arcpy.mp.CreateArcGISProject(str(folder), "layers", False)
    aprx = arcpy.mp.ArcGISProject(str(folder/"layers.aprx"))
    for m in aprx.listMaps():
        aprx.deleteItem(m)
    m = aprx.createMap("hillshade", "Map")
    m.spatialReference = arcpy.SpatialReference(3857)
    lyr = m.addDataFromPath(str(display))
    definition = lyr.getDefinition("V3")
    c = definition.colorizer
    default = {"stretchType": c.stretchType, "standardDeviationParam": c.standardDeviationParam,
               "resamplingType": c.resamplingType}
    c.stretchType = "eNone"
    c.useGammaStretch = False
    c.gammaValue = 1
    c.resamplingType = "BilinearInterpolation"
    lyr.setDefinition(definition)
    lyrx = folder/"hillshade_identity.lyrx"
    lyr.saveACopy(str(lyrx))
    aprx.save()

    gdb = folder/"aoi.gdb"
    if not gdb.exists():
        arcpy.management.CreateFileGDB(str(folder), "aoi.gdb")
    arcpy.analysis.PairwiseBuffer(str(BOUNDARY), str(gdb/"hillshade"), "5 Meters", "ALL")
    context_footprint(arcpy, gdb/"terrain")
    write_json(folder/"layer.json", {"lyrx": str(lyrx), "display_raster": str(display),
                                     "capped_at": HILLSHADE_TOP, "capped_cells": capped, "default_colorizer": default,
                                     "colorizer": "no stretch (eNone), no gamma, bilinear resampling",
                                     "aoi": {"hillshade": str(gdb/"hillshade"), "terrain": str(gdb/"terrain")}})
    print(lyrx)


def context_footprint(arcpy, target, block=20, buffer_m=15.0):
    """The unmasked mosaic's footprint: 10 m blocks with any valid cell, as polygons buffered by 15 m."""
    import rasterio
    import rasterio.features
    import shapely
    from shapely.geometry import shape
    with rasterio.open(TERRAIN_CONTEXT) as src:
        rows, cols = src.height//block + 1, src.width//block + 1
        mask = np.zeros((rows, cols), np.uint8)
        for r0 in range(0, src.height, block*200):
            data = src.read(1, window=((r0, min(r0 + block*200, src.height)), (0, src.width)))
            valid = data < 1e30
            h = valid.shape[0]
            padded = np.zeros((-(-h//block)*block, cols*block), bool)
            padded[:h, :src.width] = valid
            mask[r0//block:r0//block + padded.shape[0]//block] = padded.reshape(
                padded.shape[0]//block, block, cols, block).any(axis=(1, 3))
        transform = src.transform*src.transform.scale(block, block)
    polys = [shape(g) for g, v in rasterio.features.shapes(mask, mask=mask.astype(bool), transform=transform) if v]
    footprint = shapely.union_all(polys).buffer(buffer_m)
    geometry = arcpy.FromWKT(footprint.wkt, arcpy.SpatialReference(6341))
    arcpy.management.CopyFeatures([geometry], str(target))


# Caches and packages -------------------------------------------------------------------------------------------------

def cache(arcpy, folder, name, source, scheme_xml, aoi, levels):
    started = time.time()
    arcpy.management.ManageTileCache(str(folder), "RECREATE_ALL_TILES", name, str(source), "IMPORT_SCHEME",
                                     str(scheme_xml), None, str(aoi), None, scale(min(levels)), scale(max(levels)))
    return round(time.time() - started, 1)


def package(arcpy, cache_folder, out_folder, name):
    started = time.time()
    arcpy.management.ExportTileCache(str(cache_folder), str(out_folder), name, "TILE_PACKAGE_TPKX", "COMPACT_V2")
    return round(time.time() - started, 1)


def window_aoi(arcpy, target, window=PILOT):
    x0, y0, x1, y1 = window
    ring = arcpy.Array([arcpy.Point(x0, y0), arcpy.Point(x0, y1), arcpy.Point(x1, y1), arcpy.Point(x1, y0)])
    arcpy.management.CopyFeatures([arcpy.Polygon(ring, arcpy.SpatialReference(6341))], str(target))
    return target


def pilot(out):
    """Defaults against this script's settings on the pilot window, levels 16-18."""
    arcpy = env(out)
    folder = Path(out)/"pilot"
    folder.mkdir(exist_ok=True)
    aoi = window_aoi(arcpy, folder/"window.shp")
    schemes = Path(out)/"schemes"
    lyrx = Path(out)/"layer"/"hillshade_identity.lyrx"
    defaults = folder/"defaults"
    defaults.mkdir(exist_ok=True)
    runs = {}
    for name, source, builtin in (("hillshade_default", HILLSHADE, PRO_SCHEMES["hillshade"]),
                                  ("terrain_default", TERRAIN_CONTEXT, PRO_SCHEMES["terrain"])):
        started = time.time()
        arcpy.management.ManageTileCache(str(folder), "RECREATE_ALL_TILES", name, str(source), builtin, None, None,
                                         str(aoi), None, scale(16), scale(18))
        runs[name] = round(time.time() - started, 1)
    runs["hillshade"] = cache(arcpy, folder, "hillshade", lyrx, schemes/"hillshade.xml", aoi, (16, 18))
    runs["terrain"] = cache(arcpy, folder, "terrain", TERRAIN_CONTEXT, schemes/"terrain.xml", aoi, (16, 18))
    runs["package_terrain"] = package(arcpy, folder/"terrain", folder, "terrain_pilot")
    record = {"schema": "tiles-pilot/1", "finished": now(), "window_utm": PILOT, "levels": [16, 17, 18],
              "seconds": runs, "caches": {}}
    for name in ("hillshade_default", "hillshade", "terrain_default", "terrain"):
        tiles = {lv: list(cache_tiles(folder/name, lv)) for lv in (16, 17, 18)}
        entry = {"conf": conf_summary((folder/name/"conf.xml").read_text(encoding="utf-8")),
                 "levels": {lv: level_summary(name.split("_")[0], t) for lv, t in tiles.items()}}
        if name.startswith("hillshade"):
            entry["values_L18"] = hillshade_values(tiles[18], np.random.default_rng(3), per_tile=30)
        else:
            entry["values_L18"] = terrain_values(tiles[18], np.random.default_rng(1), per_tile=6)
        record["caches"][name] = entry
    with zipfile.ZipFile(folder/"terrain_pilot.tpkx") as z:
        record["tpkx_members"] = sorted({re.sub(r"R[0-9a-f]+C[0-9a-f]+", "R*C*", n) for n in z.namelist()})
    write_json(folder/"pilot.json", record)
    print(json.dumps(record, indent=1))


def build(out):
    arcpy = env(out)
    schemes = Path(out)/"schemes"
    layer_record = json.loads((Path(out)/"layer"/"layer.json").read_text(encoding="utf-8"))
    caches = Path(out)/"caches"
    caches.mkdir(exist_ok=True)
    record = {"schema": "tiles-run/1", "started": now(), "warning": WARNING,
              "inputs": {"hillshade": str(HILLSHADE), "hillshade_layer": layer_record["lyrx"],
                         "terrain": str(TERRAIN_CONTEXT), "terrain_city_check": str(TERRAIN_CITY),
                         "boundary": str(BOUNDARY)},
              "parameters": {"levels": [0, MAX_LEVEL], "hillshade_format": TILE_FORMAT, "lerc_error_m": LERC_ERROR_M,
                             "tiling_schemes": {k: str(schemes/f"{k}.xml") for k in PRO_SCHEMES},
                             "builtin_schemes": PRO_SCHEMES, "geographic_transformation": None,
                             "hillshade_colorizer": layer_record["colorizer"], "aoi": layer_record["aoi"],
                             "storage": "COMPACT_V2", "export": "TILE_PACKAGE_TPKX"},
              "seconds": {}, "packages": {}}
    sources = {"hillshade": layer_record["lyrx"], "terrain": TERRAIN_CONTEXT}
    for key in ("hillshade", "terrain"):
        print(f"{now()} cache {key}", flush=True)
        record["seconds"][f"cache_{key}"] = cache(arcpy, caches, key, sources[key], schemes/f"{key}.xml",
                                                  layer_record["aoi"][key], (0, MAX_LEVEL))
        print(f"{now()} package {key}", flush=True)
        record["seconds"][f"package_{key}"] = package(arcpy, caches/key, out, PACKAGES[key])
        tpkx = Path(out)/f"{PACKAGES[key]}.tpkx"
        record["packages"][key] = {"file": str(tpkx), "bytes": tpkx.stat().st_size}
        write_json(Path(out)/"run.json", record)
    record["finished"] = now()
    write_json(Path(out)/"run.json", record)
    print(json.dumps(record, indent=1))


# Reading tiles -------------------------------------------------------------------------------------------------------

def bundle_tiles(data, name):
    """(row, col, bytes) for every tile in a Compact V2 bundle: 64-byte header, 128 x 128 index of 8-byte entries with the
    offset in the low 40 bits and the size in the high 24, named RrrrrCcccc after its top-left tile in hex."""
    r0, c0 = (int(v, 16) for v in re.match(r"R([0-9a-fA-F]+)C([0-9a-fA-F]+)", name).groups())
    index = np.frombuffer(data[64:64 + 16384*8], dtype="<u8")
    for i in np.flatnonzero(index >> 40):
        entry = int(index[i])
        offset, size = entry & ((1 << 40) - 1), entry >> 40
        yield r0 + i//128, c0 + i % 128, data[offset:offset + size]


def cache_tiles(folder, level):
    for path in glob.glob(str(Path(folder)/"_alllayers"/f"L{level:02d}"/"*.bundle")):
        yield from bundle_tiles(Path(path).read_bytes(), Path(path).name)


def package_tiles(tpkx, level):
    with zipfile.ZipFile(tpkx) as z:
        for member in z.namelist():
            if member.endswith(".bundle") and f"/L{level:02d}/" in member:
                yield from bundle_tiles(z.read(member), member.rsplit("/", 1)[1])


def decode(kind, data):
    """Hillshade tile -> (gray, opaque); terrain tile -> (values, valid)."""
    if kind == "hillshade":
        from PIL import Image
        image = Image.open(io.BytesIO(data)).convert("RGBA")
        a = np.asarray(image)
        if (a[..., 0] != a[..., 1]).any() or (a[..., 0] != a[..., 2]).any():
            raise ValueError("hillshade tile is not gray")
        return a[..., 0], a[..., 3] > 0
    import lerc
    _, values, valid = lerc.decode(data)
    return values, (np.ones(values.shape, bool) if valid is None else valid)


def conf_summary(text):
    return {"format": re.search(r"<CacheTileFormat>(\w+)<", text).group(1),
            "lerc_error": float(re.search(r"<LERCError>([^<]*)<", text).group(1)),
            "tile_size": int(re.search(r"<TileCols>(\d+)<", text).group(1))}


def root_summary(root):
    """A .tpkx carries root.json, not conf.xml."""
    info = root["tileInfo"]
    return {"wkid": root["spatialReference"]["latestWkid"], "tile_size": [info["rows"], info["cols"]],
            "lods_in_scheme": len(info["lods"]), "minLOD": root["minLOD"], "maxLOD": root["maxLOD"],
            "minScale": root["minScale"], "maxScale": root["maxScale"], "tileImageInfo": root["tileImageInfo"],
            "storageFormat": root["storageInfo"]["storageFormat"], "fullExtent": root["fullExtent"]}


def level_summary(kind, tiles):
    with_data = 0
    for _, _, data in tiles:
        with_data += bool(decode(kind, data)[1].any())
    return {"tiles": len(tiles), "with_data": with_data, "bytes": sum(len(t[2]) for t in tiles)}


# Coordinates: no datum shift, so Web Mercator <-> NAD83(2011) geographic is the sphere formula, then UTM 12N.

def _transforms():
    from osgeo import osr
    osr.UseExceptions()
    geo, utm = osr.SpatialReference(), osr.SpatialReference()
    geo.ImportFromEPSG(6318)
    utm.ImportFromEPSG(6341)
    for s in (geo, utm):
        s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return osr.CoordinateTransformation(geo, utm), osr.CoordinateTransformation(utm, geo)


def merc_to_utm(x, y):
    to_utm, _ = _transforms()
    lon = np.degrees(np.asarray(x)/EARTH_R)
    lat = np.degrees(2*np.arctan(np.exp(np.asarray(y)/EARTH_R)) - np.pi/2)
    p = np.array(to_utm.TransformPoints(np.column_stack([lon, lat]).tolist()))
    return p[:, 0], p[:, 1]


def utm_to_merc(x, y):
    _, to_geo = _transforms()
    p = np.array(to_geo.TransformPoints(np.column_stack([x, y]).tolist()))
    lon, lat = np.radians(p[:, 0]), np.radians(p[:, 1])
    return EARTH_R*lon, EARTH_R*np.log(np.tan(np.pi/4 + lat/2))


def bilinear(src, x, y):
    """Bilinear interpolation between cell centres; NaN where any of the four cells is NoData."""
    t = src.transform
    c, r = (np.asarray(x) - t.c)/t.a - 0.5, (np.asarray(y) - t.f)/t.e - 0.5
    c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int)
    fc, fr = c - c0, r - r0
    out = np.full(len(c), np.nan)
    for i in range(len(c)):
        if not (0 <= r0[i] < src.height - 1 and 0 <= c0[i] < src.width - 1):
            continue
        w = src.read(1, window=((r0[i], r0[i] + 2), (c0[i], c0[i] + 2))).astype(float)
        if src.nodata is not None and (np.abs(w) >= 1e30).any():
            continue
        out[i] = (w[0, 0]*(1 - fc[i])*(1 - fr[i]) + w[0, 1]*fc[i]*(1 - fr[i]) + w[1, 0]*(1 - fc[i])*fr[i]
                  + w[1, 1]*fc[i]*fr[i])
    return out


def containing(src, x, y):
    t = src.transform
    col, row = np.floor((np.asarray(x) - t.c)/t.a).astype(int), np.floor((np.asarray(y) - t.f)/t.e).astype(int)
    return np.array([src.read(1, window=((r, r + 1), (c, c + 1)))[0, 0] for r, c in zip(row, col)], float)


def hillshade_values(tiles, rng, per_tile):
    """Random L18 pixels: tile gray against the source hillshade cell containing the pixel centre."""
    import rasterio
    res = resolution(18)
    xs, ys, gray, opaque = [], [], [], []
    for r, c, data in tiles:
        g, o = decode("hillshade", data)
        for i, j in rng.integers(0, 256, (per_tile, 2)):
            xs.append(ORIGIN + (c*256 + i + 0.5)*res)
            ys.append(-ORIGIN - (r*256 + j + 0.5)*res)
            gray.append(int(g[j, i]))
            opaque.append(bool(o[j, i]))
    ux, uy = merc_to_utm(xs, ys)
    with rasterio.open(HILLSHADE) as src:
        t = src.transform
        inside = (ux > t.c) & (ux < t.c + t.a*src.width) & (uy < t.f) & (uy > t.f + t.e*src.height)
        source = np.full(len(ux), 255.0)
        source[inside] = containing(src, ux[inside], uy[inside])
    gray, opaque, valid = np.array(gray), np.array(opaque), source != 255
    both = valid & opaque
    d = gray[both] - source[both]
    capped = gray[both] - np.minimum(source[both], HILLSHADE_TOP)
    return {"pixels": len(gray), "source_valid": int(valid.sum()), "opaque": int(opaque.sum()),
            "valid_but_transparent": int((valid & ~opaque).sum()), "opaque_but_nodata": int((~valid & opaque).sum()),
            "gray_above_cap_pixels": int((gray[opaque] > HILLSHADE_TOP).sum()),
            "mean_difference_vs_capped_source": round(float(capped.mean()), 2),
            "median_abs_difference_vs_capped_source": round(float(np.median(np.abs(capped))), 2),
            "mean_difference": round(float(d.mean()), 2), "median_abs_difference": float(np.median(np.abs(d))),
            "p95_abs_difference": float(np.percentile(np.abs(d), 95)), "max_abs_difference": int(np.abs(d).max())}


def terrain_values(tiles, rng, per_tile):
    """Random L18 pixels (corner-registered: pixel i sits at col*256 + i) against bilinear source at the same place."""
    import rasterio
    res = resolution(18)
    xs, ys, values = [], [], []
    for r, c, data in tiles:
        v, ok = decode("terrain", data)
        for i, j in rng.integers(0, 257, (per_tile, 2)):
            if ok[j, i]:
                xs.append(ORIGIN + (c*256 + i)*res)
                ys.append(-ORIGIN - (r*256 + j)*res)
                values.append(float(v[j, i]))
    ux, uy = merc_to_utm(xs, ys)
    with rasterio.open(TERRAIN_CONTEXT) as src:
        expected = bilinear(src, ux, uy)
    ok = ~np.isnan(expected)
    d = np.abs(np.array(values)[ok] - expected[ok])
    return {"pixels": int(ok.sum()), "max_abs_vs_bilinear_m": round(float(d.max()), 4),
            "median_abs_vs_bilinear_m": round(float(np.median(d)), 4)}


# Verification --------------------------------------------------------------------------------------------------------

def expected_tiles(level=MAX_LEVEL, stride=10):
    """L18 tiles holding a valid hillshade cell centre: every edge cell exactly, interior cells every 10th row and column
    (an L18 tile is about 230 cells across, so an all-interior tile cannot be missed). Also how many cells each holds."""
    import rasterio
    from scipy import ndimage
    with rasterio.open(HILLSHADE) as src:
        valid = src.read(1) != src.nodata
        t = src.transform
    edge = valid & ~ndimage.binary_erosion(valid, structure=np.ones((3, 3), bool), border_value=0)
    sparse = np.zeros_like(valid)
    sparse[::stride, ::stride] = True
    rows, cols = np.nonzero(edge | (valid & sparse))
    del valid, edge, sparse
    x, y = t.c + (cols + 0.5)*t.a, t.f + (rows + 0.5)*t.e
    tiles = {}
    res = resolution(level)*256
    for start in range(0, len(x), 2_000_000):
        mx, my = utm_to_merc(x[start:start + 2_000_000], y[start:start + 2_000_000])
        keys = np.floor((-ORIGIN - my)/res).astype(np.int64)*(1 << 32) + np.floor((mx - ORIGIN)/res).astype(np.int64)
        k, n = np.unique(keys, return_counts=True)
        for key, count in zip(k.tolist(), n.tolist()):
            tiles[key] = tiles.get(key, 0) + count
    return {(key >> 32, key & 0xFFFFFFFF): n for key, n in tiles.items()}


def hillshade_holes(tpkx, level=MAX_LEVEL):
    """Transparent pixels whose eight neighbours are all opaque, and the PNG modes and transparency keys used."""
    from PIL import Image
    from scipy import ndimage
    holes, opaque, modes = 0, 0, {}
    for _, _, data in package_tiles(tpkx, level):
        image = Image.open(io.BytesIO(data))
        mode = f"{image.mode} key={image.info.get('transparency')}"
        modes[mode] = modes.get(mode, 0) + 1
        _, o = decode("hillshade", data)
        opaque += int(o.sum())
        holes += int(((~o) & (ndimage.convolve(o.astype(int), np.ones((3, 3), int), mode="constant") == 8)).sum())
    return {"opaque_pixels": opaque, "single_pixel_holes": holes, "png_modes": modes}


def tile_inventory(tpkx, kind):
    levels = {}
    with_data = {}
    for level in range(0, MAX_LEVEL + 1):
        tiles = list(package_tiles(tpkx, level))
        present = {(r, c) for r, c, d in tiles if decode(kind, d)[1].any()}
        levels[level] = {"tiles": len(tiles), "with_data": len(present), "bytes": sum(len(t[2]) for t in tiles)}
        with_data[level] = present
    return levels, with_data


def hillshade_coverage(with_data):
    expected = expected_tiles()
    result = {}
    for level in range(MAX_LEVEL, -1, -1):
        shift = MAX_LEVEL - level
        wanted = {(r >> shift, c >> shift) for r, c in expected}
        missing = sorted(wanted - with_data[level])
        result[level] = {"expected": len(wanted), "present_with_data": len(with_data[level]), "missing": len(missing),
                         "extra_with_data": len(with_data[level] - wanted)}
        if level == MAX_LEVEL:
            result[level]["missing_source_cells"] = sorted(expected[m] for m in missing)[:20]
    return result


def terrain_samples(tpkx, n_flat=150, n_steep=150, seed=20261022):
    """City cells away from the mask edge, half flat (slope < 2 degrees) and half steep (slope > 25 degrees). Each is moved
    to the nearest L18 elevation pixel, whose value is compared with terrain_m.tif there by bilinear interpolation (the
    resampling the cache uses), and with the terrain_m cell the original point falls in (what a click would compare)."""
    import rasterio
    rng = np.random.default_rng(seed)
    with rasterio.open(SLOPE) as s:
        slope = s.read(1, out_shape=(s.height//4, s.width//4))
        nodata = s.nodata
    points = []
    quota = {"flat": n_flat, "steep": n_steep}
    for stratum, test in (("flat", lambda v: v < 2), ("steep", lambda v: v > 25)):
        r, c = np.nonzero((slope != nodata) & test(slope))
        pick = rng.choice(len(r), quota[stratum]*3, replace=False)
        points += [(r[i]*4 + 2, c[i]*4 + 2, stratum) for i in pick]
    res = resolution(MAX_LEVEL)
    with rasterio.open(TERRAIN_CITY) as city:
        t = city.transform
        kept = []
        for row, col, stratum in points:
            w = city.read(1, window=((row - 1, row + 2), (col - 1, col + 2)))
            if (np.abs(w) < 1e30).all() and sum(p[2] == stratum for p in kept) < quota[stratum]:
                kept.append((row, col, stratum))
        px, py = t.c + (np.array([k[1] for k in kept]) + 0.5)*t.a, t.f + (np.array([k[0] for k in kept]) + 0.5)*t.e
        mx, my = utm_to_merc(px, py)
        gi, gj = np.rint((mx - ORIGIN)/res).astype(int), np.rint((-ORIGIN - my)/res).astype(int)
        nx, ny = merc_to_utm(ORIGIN + gi*res, -ORIGIN - gj*res)
        expected = bilinear(city, nx, ny)
        clicked = containing(city, px, py)
    wanted = {}
    for k, (i, j) in enumerate(zip(gi, gj)):
        # A pixel on a shared tile edge is in both tiles; take it from the tile to its lower right.
        wanted.setdefault((j//256, i//256), []).append((k, i % 256, j % 256))
    values = np.full(len(kept), np.nan)
    for r, c, data in package_tiles(tpkx, MAX_LEVEL):
        if (r, c) not in wanted:
            continue
        v, ok = decode("terrain", data)
        for k, i, j in wanted[(r, c)]:
            if ok[j, i]:
                values[k] = v[j, i]
    strata = np.array([k[2] for k in kept])
    out = {"points": len(kept), "lerc_error_m": LERC_ERROR_M}
    for name, sel in (("all", np.ones(len(kept), bool)), ("flat", strata == "flat"), ("steep", strata == "steep")):
        ok = sel & ~np.isnan(values) & ~np.isnan(expected)
        d, dc = np.abs(values[ok] - expected[ok]), np.abs(values[ok] - clicked[ok])
        out[name] = {"points": int(sel.sum()), "compared": int(ok.sum()),
                     "max_abs_vs_bilinear_m": round(float(d.max()), 4),
                     "median_abs_vs_bilinear_m": round(float(np.median(d)), 4),
                     "max_abs_vs_containing_cell_m": round(float(dc.max()), 3),
                     "median_abs_vs_containing_cell_m": round(float(np.median(dc)), 3)}
    out["missing_from_package"] = int(np.isnan(values).sum())
    out["sample"] = [{"utm": [round(float(a), 2), round(float(b), 2)], "stratum": s, "tile_m": round(float(v), 3),
                      "bilinear_m": round(float(e), 3), "cell_m": round(float(cl), 3)}
                     for a, b, s, v, e, cl in list(zip(px, py, strata, values, expected, clicked))[::15]]
    return out


def lerc_headers(tpkx, level=MAX_LEVEL, every=50):
    import lerc
    errors = set()
    tiles = list(package_tiles(tpkx, level))
    for _, _, data in tiles[::every]:
        errors.add(round(float(lerc.getLercBlobInfo(data, 0)[12]), 6))
    return {"tiles_read": len(tiles[::every]), "max_z_error_in_blobs": sorted(errors)}


def opens_in_pro(out, packages):
    """Pro's engine, not the UI: a new project, the hillshade package in a map, the terrain package in a scene, and
    the terrain package as a ground source in that scene."""
    import arcpy
    folder = Path(out)/"check"
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir()
    arcpy.mp.CreateArcGISProject(str(folder), "check", False)
    aprx = arcpy.mp.ArcGISProject(str(folder/"check.aprx"))
    record = {}
    m = aprx.createMap("hillshade", "Map")
    for key, map_type in (("hillshade", "Map"), ("terrain", "Scene")):
        target = m if map_type == "Map" else aprx.createMap("terrain", "Scene")
        lyr = target.addDataFromPath(packages[key])
        record[key] = {"layer": lyr.name, "isRasterLayer": lyr.isRasterLayer, "isBroken": lyr.isBroken,
                       "dataSource": lyr.dataSource}
        try:
            record[key]["describe_dataType"] = arcpy.Describe(packages[key]).dataType
        except Exception as error:
            record[key]["describe_dataType"] = f"unavailable: {error}"
        try:
            e = lyr.getDefinition("V3")
            record[key]["cim_type"] = type(e).__name__
        except Exception as error:
            record[key]["cim_type"] = f"unavailable: {error}"
        if key == "terrain":
            surfaces = target.listElevationSurfaces()
            record[key]["elevation_surfaces"] = [s.name for s in surfaces]
            try:
                surface = surfaces[0]
                surface.addSource(packages[key])
                record[key]["ground_sources"] = [s.name for s in surface.listLayers()]
            except Exception as error:
                record[key]["ground_source"] = f"not added by arcpy: {error}"
    aprx.save()
    record["project"] = str(folder/"check.aprx")
    return record


def verify(out):
    run = json.loads((Path(out)/"run.json").read_text(encoding="utf-8"))
    packages = {k: v["file"] for k, v in run["packages"].items()}
    record = {"schema": "tiles-verify/1", "started": now(), "levels": {}, "packages": {}}
    for key in ("hillshade", "terrain"):
        with zipfile.ZipFile(packages[key]) as z:
            members = z.namelist()
            record["packages"][key] = {"bytes": Path(packages[key]).stat().st_size, "members": len(members),
                                       "compressed": any(i.compress_type != zipfile.ZIP_STORED for i in z.infolist()),
                                       "root": root_summary(json.loads(z.read("root.json")))}
        levels, with_data = tile_inventory(packages[key], key)
        record["levels"][key] = levels
        print(f"{now()} {key} inventory done", flush=True)
        if key == "hillshade":
            record["hillshade_coverage"] = hillshade_coverage(with_data)
            record["hillshade_holes_L18"] = hillshade_holes(packages[key])
            record["hillshade_values_L18"] = hillshade_values(
                [t for t in package_tiles(packages[key], MAX_LEVEL)][::7], np.random.default_rng(5), per_tile=20)
        else:
            record["terrain_lerc_headers"] = lerc_headers(packages[key])
            record["terrain_samples"] = terrain_samples(packages[key])
        write_json(Path(out)/"verify.json", record)
    record["opens_in_pro"] = opens_in_pro(out, packages)
    record["finished"] = now()
    write_json(Path(out)/"verify.json", record)
    print(json.dumps({k: v for k, v in record.items() if k != "terrain_samples"}, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("scheme", "layer", "pilot", "build", "verify"))
    p.add_argument("out", type=Path)
    a = p.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    {"scheme": scheme, "layer": layer, "pilot": pilot, "build": build, "verify": verify}[a.step](a.out)


if __name__ == "__main__":
    main()
