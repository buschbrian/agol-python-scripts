r"""Existing buildings and elevation in NAD83(2011) UTM 12N for a local ArcGIS Urban model (October 26, 2026).

    python reviews/2026-10-26/urban-utm/urban_utm.py prepare OUT       buildings copy with FLOORS, footprints, 20-building test set
    python reviews/2026-10-26/urban-utm/urban_utm.py footprints OUT    the footprints alone (OUT\footprints\urban_footprints.gdb)
    python reviews/2026-10-26/urban-utm/urban_utm.py slpk OUT --test   the 20-building test package (OUT\test)
    python reviews/2026-10-26/urban-utm/urban_utm.py slpk OUT          the full package (OUT\scene)
    python reviews/2026-10-26/urban-utm/urban_utm.py scheme OUT        the UTM elevation tiling scheme (OUT\elevation\scheme.xml)
    python reviews/2026-10-26/urban-utm/urban_utm.py elevation OUT [--pilot]   elevation cache and .tpkx
    python reviews/2026-10-26/urban-utm/urban_utm.py verify OUT        read the elevation package back against the terrain

ArcGIS Pro Python with 3D Analyst (PYTHONNOUSERSITE=1). Read-only on the LiDAR runs; writes only under OUT. Nothing is
uploaded here: uploads go through reviews/2026-10-22/hosting/upload/upload.py, one item per command.
Brian approved on October 26 publishing the three-way hybrid (roofer LoD2.2, Esri LOD2.0/LOD1.2 fallbacks) org-only as the
Urban existing buildings, with the Urban model in NAD83(2011) UTM 12N metres, because every lidar product is native UTM.
- Buildings: hybrid.gdb\buildings_three_way (21,561 multipatches, absolute NAVD88 heights), copied with the field types a
  scene layer package cannot carry dropped (big integer, date only, time only, timestamp offset) and FLOORS added, then
  packaged by make_slpk.py in 6341 with no transformation.
- Footprints: one polygon per FP_ID from the same copy (Multipatch Footprint), with FP_ID, HEIGHT_P95_M, LEVEL and FLOORS.
- FLOORS = HEIGHT_P95_M / 3.5 m rounded half up, at least 1, null with no height. A planning estimate of storeys from roof
  height, for Urban's attribute-driven Convert existing buildings; not a count of floors.
- Elevation: terrain_context.tif (the unmasked lidar mosaic, identical to terrain_m.tif on every city cell) as LERC elevation
  tiles on a UTM tiling scheme whose finest level is the source's 0.5 m. Urban needs the basemap on the same scheme.
"""
import argparse
import datetime
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve()
REVIEWS = HERE.parents[2]
sys.path.insert(0, str(HERE.parents[3]))
from canopy.lidar_root import lidar_root  # noqa: E402

RUNS = lidar_root()/"2023-salt-lake-valley"/"runs"
SOURCE = RUNS/"roofer-city-v2-20261024"/"hybrid.gdb"/"buildings_three_way"
TERRAIN_CONTEXT = RUNS/"millcreek-products-20261019"/"terrain_context.tif"
TERRAIN_CITY = RUNS/"millcreek-products-20261022"/"terrain_m.tif"
WKID = 6341
EXPECTED = {"count": 21561, "fp_id_sum": 237493394}
STOREY_M = 3.5
UNSUPPORTED = {"BigInteger", "DateOnly", "TimeOnly", "TimestampOffset"}
FOOTPRINT_FIELDS = ("FP_ID", "HEIGHT_P95_M", "LEVEL", "FLOORS")
TEST_PER_LEVEL = 7


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


slpk_mod = _load("make_slpk", REVIEWS/"2026-10-22"/"hosting"/"scene-layers"/"make_slpk.py")


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def write_json(path, record):
    path.write_text(json.dumps(record, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(record, default=str)[:3000], flush=True)


def floors(height_m):
    """Storeys from a roof height: height / 3.5 m rounded half up (not Python's half-to-even), at least 1."""
    if height_m is None:
        return None
    return max(1, int(height_m/STOREY_M + 0.5))


def fp_stats(arcpy, fc):
    ids = [r[0] for r in arcpy.da.SearchCursor(str(fc), ["FP_ID"])]
    return {"count": len(ids), "fp_id_sum": sum(ids), "unique": len(set(ids))}


def prepare(out):
    import arcpy
    out.mkdir(parents=True, exist_ok=True)
    gdb = out/"urban.gdb"
    if gdb.exists():
        raise SystemExit(f"{gdb} exists; prepare writes it once")
    arcpy.management.CreateFileGDB(str(out), "urban.gdb")
    sr = arcpy.Describe(str(SOURCE)).spatialReference
    assert sr.factoryCode == WKID, sr.factoryCode
    buildings = gdb/"buildings"
    arcpy.management.CopyFeatures(str(SOURCE), str(buildings))
    fields = {f.name: f.type for f in arcpy.ListFields(str(buildings))}
    dropped = sorted(n for n, t in fields.items() if t in UNSUPPORTED)
    if dropped:
        arcpy.management.DeleteField(str(buildings), dropped)
    arcpy.management.AddField(str(buildings), "FLOORS", "LONG", field_alias="Estimated floors")
    with arcpy.da.UpdateCursor(str(buildings), ["HEIGHT_P95_M", "FLOORS"]) as cur:
        for h, _ in cur:
            cur.updateRow([h, floors(h)])
    # Footprints: Multipatch Footprint grouped by FP_ID, then a fresh feature class with the four fields only.
    raw = gdb/"footprints_raw"
    arcpy.ddd.MultiPatchFootprint(str(buildings), str(raw), "FP_ID")
    footprints = gdb/"footprints"
    arcpy.management.CreateFeatureclass(str(gdb), "footprints", "POLYGON", spatial_reference=arcpy.SpatialReference(WKID))
    for name, ftype, alias in (("FP_ID", "LONG", "Footprint ID"), ("HEIGHT_P95_M", "DOUBLE", "Roof height, 95th percentile (m)"),
                               ("LEVEL", "TEXT", "Model used"), ("FLOORS", "LONG", "Estimated floors")):
        arcpy.management.AddField(str(footprints), name, ftype, field_length=16 if ftype == "TEXT" else None,
                                  field_alias=alias)
    attrs = {r[0]: r[1:] for r in arcpy.da.SearchCursor(str(buildings), list(FOOTPRINT_FIELDS))}
    empty = []
    with arcpy.da.SearchCursor(str(raw), ["FP_ID", "SHAPE@"]) as src, \
            arcpy.da.InsertCursor(str(footprints), ["SHAPE@"] + list(FOOTPRINT_FIELDS)) as ins:
        for fp_id, shape in src:
            if shape is None or shape.area <= 0:
                empty.append(fp_id)
                continue
            ins.insertRow([shape, fp_id, *attrs[fp_id]])
    # 20-building test set: the first TEST_PER_LEVEL FP_IDs of each LEVEL (7 + 7 + 6).
    by_level = {}
    for fp_id, level in sorted(arcpy.da.SearchCursor(str(buildings), ["FP_ID", "LEVEL"])):
        by_level.setdefault(level, []).append(fp_id)
    picks = {lv: ids[:TEST_PER_LEVEL] for lv, ids in sorted(by_level.items())}
    picks[max(picks)] = picks[max(picks)][:20 - TEST_PER_LEVEL*(len(picks) - 1)]
    test_ids = sorted(i for ids in picks.values() for i in ids)
    test = gdb/"buildings_test20"
    arcpy.analysis.Select(str(buildings), str(test), f"FP_ID IN ({','.join(map(str, test_ids))})")
    h = [r[0] for r in arcpy.da.SearchCursor(str(footprints), ["FLOORS"])]
    record = {
        "created": now(), "source": str(SOURCE), "source_stats": fp_stats(arcpy, SOURCE),
        "source_fields": fields, "dropped_unsupported_fields": dropped,
        "buildings": str(buildings), "buildings_stats": fp_stats(arcpy, buildings),
        "footprints": str(footprints), "footprints_stats": fp_stats(arcpy, footprints), "empty_footprints": empty,
        "footprint_sr": arcpy.Describe(str(footprints)).spatialReference.factoryCode,
        "footprint_area_m2": sum(r[0] for r in arcpy.da.SearchCursor(str(footprints), ["SHAPE@AREA"])),
        "floors": {"null": sum(v is None for v in h), "min": min(v for v in h if v is not None),
                   "max": max(v for v in h if v is not None),
                   "histogram": {str(k): h.count(k) for k in sorted(set(v for v in h if v is not None))}},
        "test": str(test), "test_stats": fp_stats(arcpy, test), "test_ids": test_ids,
        "test_levels": {lv: len(ids) for lv, ids in picks.items()},
    }
    for key in ("source_stats", "buildings_stats", "footprints_stats"):
        assert (record[key]["count"], record[key]["fp_id_sum"], record[key]["unique"]) == \
            (EXPECTED["count"], EXPECTED["fp_id_sum"], EXPECTED["count"]), (key, record[key])
    assert not empty and record["test_stats"]["count"] == 20
    write_json(out/"prepare.json", record)


def footprints_gdb(out):
    """The footprints alone in their own file geodatabase, for upload.py (which sends a whole .gdb as one feature service)."""
    import arcpy
    folder = out/"footprints"
    folder.mkdir(parents=True, exist_ok=False)
    arcpy.management.CreateFileGDB(str(folder), "urban_footprints.gdb")
    target = folder/"urban_footprints.gdb"/"building_footprints"
    arcpy.management.Copy(str(out/"urban.gdb"/"footprints"), str(target))
    stats = fp_stats(arcpy, target)
    assert (stats["count"], stats["fp_id_sum"], stats["unique"]) == (EXPECTED["count"], EXPECTED["fp_id_sum"], EXPECTED["count"])
    record = {"created": now(), "feature_class": str(target), **stats,
              "fields": [(f.name, f.type) for f in arcpy.ListFields(str(target))],
              "wkid": arcpy.Describe(str(target)).spatialReference.factoryCode,
              "floors_sum": sum(r[0] for r in arcpy.da.SearchCursor(str(target), ["FLOORS"])),
              "height_p95_sum": sum(r[0] for r in arcpy.da.SearchCursor(str(target), ["HEIGHT_P95_M"])),
              "area_m2": sum(r[0] for r in arcpy.da.SearchCursor(str(target), ["SHAPE@AREA"]))}
    write_json(folder/"footprints.json", record)


def slpk(out, test=False, vcs=None):
    gdb = out/"urban.gdb"
    folder = out/(("test" + (f"-vcs{vcs}" if vcs else "")) if test else "scene")
    folder.mkdir(parents=True, exist_ok=False)
    source = gdb/("buildings_test20" if test else "buildings")
    name = "buildings_utm_test20" if test else "buildings_three_way_utm"
    entry = slpk_mod.package(source, folder/f"{name}.slpk", folder/"validation.json", WKID, vcs, "")
    record = {"created": now(), "wkid": WKID, "vcs": vcs, "transformation": "", **entry}
    if not test:
        assert (entry["package"]["fp_id_count"], entry["package"]["fp_id_sum"]) == (EXPECTED["count"], EXPECTED["fp_id_sum"])
    assert entry["all_features_in_package"]
    write_json(folder/"slpk.json", record)


# Elevation -----------------------------------------------------------------------------------------------------------
# Elevation tiles: 256 px (257 stored, corner-registered), LERC 0.01 m as the Web Mercator terrain. Resolutions halve from
# 8,192 m to the source's 0.5 m (levels 0-14), so the finest level puts one pixel on each source cell corner. In UTM there is
# no Mercator scale factor: the Web Mercator scheme's level 18 would be 0.597 m here, coarser than the source. A basemap on
# this scheme can add finer levels (0.25 m, ...) below these.

FINEST_M = 0.5
LEVELS = 15
LERC_ERROR_M = 0.01
DPI = 96
ELEVATION_NAME = "millcreek_terrain_utm_20261026"


def scheme_scales():
    # Esri tiling schemes take 39.37 inches to the metre: scale = resolution x DPI x 39.37 gives exactly 0.5 m at level 14.
    return [round(FINEST_M*2**(LEVELS - 1 - k)*DPI*39.37, 6) for k in range(LEVELS)]


def read_scheme(xml):
    import re
    text = Path(xml).read_text(encoding="utf-8")
    lods = [{"level": int(a), "scale": float(b), "resolution": float(c)} for a, b, c in
            re.findall(r"<LODInfo[^>]*>\s*<LevelID>(\d+)</LevelID>\s*<Scale>([^<]+)</Scale>\s*<Resolution>([^<]+)</Resolution>",
                       text)]
    origin = re.search(r"<TileOrigin[^>]*>\s*<X>([^<]+)</X>\s*<Y>([^<]+)</Y>", text)
    return {"lods": lods, "origin": [float(origin.group(1)), float(origin.group(2))],
            "wkid": int(re.search(r"<LatestWKID>(\d+)<", text).group(1)),
            "format": re.search(r"<CacheTileFormat>(\w+)<", text).group(1),
            "lerc_error": float(re.search(r"<LERCError>([^<]*)<", text).group(1)),
            "tile_size": int(re.search(r"<TileCols>(\d+)<", text).group(1)),
            "dpi": int(re.search(r"<DPI>(\d+)<", text).group(1))}


def scheme(out):
    """A new tiling scheme in 6341 from the terrain, LERC 0.01 m, scales halving down to 0.5 m pixels."""
    import arcpy
    folder = out/"elevation"
    folder.mkdir(parents=True, exist_ok=True)
    xml = folder/"scheme.xml"
    arcpy.management.GenerateTileCacheTilingScheme(
        str(TERRAIN_CONTEXT), str(xml), "NEW", LEVELS, None, ";".join(repr(s) for s in scheme_scales()), "SCALE",
        None, DPI, "256 x 256", "LERC", 75, "COMPACT", LERC_ERROR_M)
    s = read_scheme(xml)
    assert s["wkid"] == WKID and s["format"] == "LERC" and s["lerc_error"] == LERC_ERROR_M and s["tile_size"] == 256, s
    assert len(s["lods"]) == LEVELS and abs(s["lods"][-1]["resolution"] - FINEST_M) < 1e-9, s["lods"][-1]
    write_json(folder/"scheme.json", {"created": now(), "file": str(xml), "requested_scales": scheme_scales(), **s})


def elevation(out, pilot=False):
    """The terrain mosaic cached on the scheme (no datum shift: source and scheme are both 6341), then a .tpkx."""
    import arcpy
    import shutil
    import time
    pt = _load("package_tiles", REVIEWS/"2026-10-22"/"hosting"/"tiles"/"package_tiles.py")
    folder = out/"elevation"
    xml = folder/"scheme.xml"
    s = read_scheme(xml)
    scales = [lod["scale"] for lod in s["lods"]]
    work = folder/("pilot" if pilot else "full")
    if work.exists():
        raise SystemExit(f"{work} exists")
    work.mkdir()
    scratch = work/"scratch"
    scratch.mkdir()
    arcpy.env.scratchWorkspace = str(scratch)
    arcpy.env.geographicTransformations = None
    if pilot:
        aoi = pt.window_aoi(arcpy, work/"window.shp")
        levels = (LEVELS - 3, LEVELS - 1)
    else:
        aoi = work/"aoi.shp"
        pt.context_footprint(arcpy, aoi)
        levels = (0, LEVELS - 1)
    record = {"created": now(), "pilot": pilot, "source": str(TERRAIN_CONTEXT), "scheme": str(xml),
              "levels": list(levels), "aoi": str(aoi), "seconds": {}}
    started = time.time()
    arcpy.management.ManageTileCache(str(work), "RECREATE_ALL_TILES", "terrain", str(TERRAIN_CONTEXT), "IMPORT_SCHEME",
                                     str(xml), None, str(aoi), None, repr(scales[levels[0]]), repr(scales[levels[1]]))
    record["seconds"]["cache"] = round(time.time() - started, 1)
    cache = work/"terrain"
    props = (cache/"conf.properties").read_text(encoding="utf-8") if (cache/"conf.properties").exists() else ""
    import re
    # conf.properties is an XML property set; keep its simple keys (MinScale, MaxScale, CacheTileContentType, PixelType).
    record["conf_properties"] = dict(re.findall(r"<Key>(\w+)</Key><Value xsi:type='xs:\w+'>([^<]*)</Value>", props))
    record["conf"] = pt.conf_summary((cache/"conf.xml").read_text(encoding="utf-8"))
    name = ELEVATION_NAME + ("_pilot" if pilot else "")
    started = time.time()
    arcpy.management.ExportTileCache(str(cache), str(out if not pilot else work), name, "TILE_PACKAGE_TPKX", "COMPACT_V2")
    record["seconds"]["package"] = round(time.time() - started, 1)
    tpkx = (out if not pilot else work)/f"{name}.tpkx"
    record["tpkx"] = {"file": str(tpkx), "bytes": tpkx.stat().st_size}
    record["levels_in_package"] = {lv: pt_level(pt, tpkx, lv) for lv in range(levels[0], levels[1] + 1)}
    import zipfile
    with zipfile.ZipFile(tpkx) as z:
        root = json.loads(z.read(next(n for n in z.namelist() if n.endswith("root.json"))))
        record["root"] = pt.root_summary(root)
        info = next((n for n in z.namelist() if n.endswith("iteminfo.json")), None)
        record["iteminfo"] = json.loads(z.read(info)) if info else None
    shutil.rmtree(scratch, ignore_errors=True)
    assert record["conf_properties"].get("CacheTileContentType") == "Elevation", record["conf_properties"]
    write_json(work/"elevation.json", record)


def pt_level(pt, tpkx, level):
    tiles = list(pt.package_tiles(tpkx, level))
    return {"tiles": len(tiles), "with_data": sum(bool(pt.decode("terrain", d)[1].any()) for _, _, d in tiles),
            "bytes": sum(len(d) for _, _, d in tiles)}


def verify(out, n_flat=150, n_steep=150, seed=20261026):
    """City cells away from the mask edge, half flat (slope under 2 degrees), half steep (over 25). Each goes to its nearest
    finest-level elevation pixel (a source cell corner), compared with terrain_m.tif interpolated bilinearly there and with
    the cell the point falls in. No projection: tiles, terrain and points are all 6341."""
    import numpy as np
    import rasterio
    pt = _load("package_tiles", REVIEWS/"2026-10-22"/"hosting"/"tiles"/"package_tiles.py")
    s = read_scheme(out/"elevation"/"scheme.xml")
    tpkx = out/f"{ELEVATION_NAME}.tpkx"
    top = LEVELS - 1
    res, (ox, oy) = s["lods"][top]["resolution"], s["origin"]
    rng = np.random.default_rng(seed)
    with rasterio.open(pt.SLOPE) as src:
        slope = src.read(1, out_shape=(src.height//4, src.width//4))
        nodata = src.nodata
    points, quota = [], {"flat": n_flat, "steep": n_steep}
    for stratum, test in (("flat", lambda v: v < 2), ("steep", lambda v: v > 25)):
        r, c = np.nonzero((slope != nodata) & test(slope))
        points += [(r[i]*4 + 2, c[i]*4 + 2, stratum) for i in rng.choice(len(r), quota[stratum]*3, replace=False)]
    with rasterio.open(TERRAIN_CITY) as city:
        t = city.transform
        kept = []
        for row, col, stratum in points:
            w = city.read(1, window=((row - 1, row + 2), (col - 1, col + 2)))
            if (np.abs(w) < 1e30).all() and sum(p[2] == stratum for p in kept) < quota[stratum]:
                kept.append((row, col, stratum))
        px = t.c + (np.array([k[1] for k in kept]) + 0.5)*t.a
        py = t.f + (np.array([k[0] for k in kept]) + 0.5)*t.e
        gi, gj = np.rint((px - ox)/res).astype(int), np.rint((oy - py)/res).astype(int)
        nx, ny = ox + gi*res, oy - gj*res
        expected = pt.bilinear(city, nx, ny)
        clicked = pt.containing(city, px, py)
    wanted = {}
    for k, (i, j) in enumerate(zip(gi, gj)):
        wanted.setdefault((j//256, i//256), []).append((k, i % 256, j % 256))
    values = np.full(len(kept), np.nan)
    for r, c, data in pt.package_tiles(tpkx, top):
        for k, i, j in wanted.get((r, c), []):
            v, ok = pt.decode("terrain", data)
            if ok[j, i]:
                values[k] = v[j, i]
    strata = np.array([k[2] for k in kept])
    samples = {"points": len(kept), "lerc_error_m": LERC_ERROR_M, "level": top, "resolution_m": res}
    for name, sel in (("all", np.ones(len(kept), bool)), ("flat", strata == "flat"), ("steep", strata == "steep")):
        ok = sel & ~np.isnan(values) & ~np.isnan(expected)
        d, dc = np.abs(values[ok] - expected[ok]), np.abs(values[ok] - clicked[ok])
        samples[name] = {"points": int(sel.sum()), "compared": int(ok.sum()),
                         "max_abs_vs_bilinear_m": round(float(d.max()), 4),
                         "median_abs_vs_bilinear_m": round(float(np.median(d)), 4),
                         "max_abs_vs_containing_cell_m": round(float(dc.max()), 3),
                         "median_abs_vs_containing_cell_m": round(float(np.median(dc)), 3)}
    samples["missing_from_package"] = int(np.isnan(values).sum())
    import lerc  # noqa: F401  (pt.lerc_headers needs it)
    record = {"verified": now(), "tpkx": str(tpkx), "bytes": tpkx.stat().st_size, "sha256": sha256(tpkx),
              "levels": {lv: pt_level(pt, tpkx, lv) for lv in range(LEVELS)},
              "lerc_headers": pt.lerc_headers(tpkx, level=top), "samples": samples}
    with rasterio.open(TERRAIN_CONTEXT) as src:
        record["source_crs"] = str(src.crs)
    write_json(out/"elevation"/"verify.json", record)


def sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("prepare", "footprints", "slpk", "scheme", "elevation", "verify"))
    p.add_argument("out", type=Path)
    p.add_argument("--test", action="store_true", help="slpk: the 20-building test package")
    p.add_argument("--vcs", type=int, help="slpk: vertical coordinate system for the package (default none)")
    p.add_argument("--pilot", action="store_true", help="elevation: a 1 km window only")
    a = p.parse_args(argv)
    out = a.out.resolve()
    if a.step == "prepare":
        prepare(out)
    elif a.step == "footprints":
        footprints_gdb(out)
    elif a.step == "slpk":
        slpk(out, a.test, a.vcs)
    elif a.step == "scheme":
        scheme(out)
    elif a.step == "elevation":
        elevation(out, a.pilot)
    else:
        verify(out)


if __name__ == "__main__":
    main()
