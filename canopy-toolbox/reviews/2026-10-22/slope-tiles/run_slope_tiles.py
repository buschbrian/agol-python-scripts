r"""Millcreek slope in 6 classes as polygons and an ArcGIS Online vector tile package (October 22, 2026), from the
citywide 0.5 m lidar slope (reviews/2026-10-22/terrain-city).

    python reviews/2026-10-22/slope-tiles/run_slope_tiles.py classes OUT    class rasters (raw and cleaned) and counts
    python reviews/2026-10-22/slope-tiles/run_slope_tiles.py pilot OUT      polygons, project and .vtpk on one window
    python reviews/2026-10-22/slope-tiles/run_slope_tiles.py polygons OUT   the citywide polygon feature class
    python reviews/2026-10-22/slope-tiles/run_slope_tiles.py tiles OUT      the project (.aprx) and the .vtpk
    python reviews/2026-10-22/slope-tiles/run_slope_tiles.py verify OUT     polygon areas against the rasters; the package

ArcGIS Pro Python (PYTHONNOUSERSITE=1). Read-only on the slope raster; writes only under OUT. Nothing is published.
- Classes (percent slope; a break value belongs to the class above it): 1 under 10, 2 10 to 15, 3 15 to 20, 4 20 to 25,
  5 25 to 30, 6 30 and over. Fields SLOPE_CODE (1-6) and SLOPE_CLASS (the label).
- Cleanup: a minimum mapping unit of MMU_CELLS 0.5 m cells (4 m2). Every 4-connected patch of one class smaller than that
  joins its largest neighbouring patch (GDAL SieveFilter, repeated up to 10 times until no small patch is left; a patch
  with no 4-connected neighbour in the city stays); nothing else changes, so every polygon's class is the raster's class
  wherever the patch was large enough. No simplification: polygon edges are the cell edges, so polygon areas equal the
  cleaned raster's cell areas.
- The project is a copy of the install's Blank.aprx with one map in Web Mercator (the ArcGIS Online tiling scheme needs
  the map in 3857, set after the layer is added; the features stay in EPSG 6341). The package is tiled to vector level
  MAX_LOD of the 512-pixel scheme; clients overzoom past it.
"""
import argparse
import datetime
import json
from pathlib import Path
import shutil
import sys
import zipfile

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
from canopy.lidar_root import lidar_root  # noqa: E402

VALLEY = lidar_root()/"2023-salt-lake-valley"
SLOPE = VALLEY/"runs"/"terrain-city-20261022"/"slope_percent.tif"
BREAKS = (10, 15, 20, 25, 30)
CLASSES = {1: "Under 10%", 2: "10% to 15%", 3: "15% to 20%", 4: "20% to 25%", 5: "25% to 30%", 6: "30% and over"}
# ColorBrewer YlOrRd, 6 classes.
COLOURS = {1: (255, 255, 178), 2: (254, 217, 118), 3: (254, 178, 76), 4: (253, 141, 60), 5: (240, 59, 32),
           6: (189, 0, 38)}
MMU_CELLS = 16
CELL_AREA = 0.25
MAP_NAME = "Millcreek slope classes"
LAYER_NAME = "Slope classes"
# The ArcGIS Online vector tile scheme (512-pixel tiles): level n is 295,828,763.795777 / 2**n.
MIN_SCALE = 295828763.795777          # level 0
MAX_LOD = 17
MAX_SCALE = 2256.994353               # level 17, about 0.23 m per pixel on the ground here
# The terrain-city pilot window: the fully covered 1 km of the city with the most relief.
PILOT = (433149.0, 4505133.0, 434149.0, 4506133.0)
DESCRIPTION = ("Terrain slope in percent from the 2023 QL1 lidar (0.5 m, 3 m Surface Parameters neighbourhood), in six "
               "classes: SLOPE_CODE 1 under 10%, 2 10-15%, 3 15-20%, 4 20-25%, 5 25-30%, 6 30% and over (a break value "
               f"belongs to the class above). Patches under {MMU_CELLS*CELL_AREA:g} m2 are merged into their largest "
               "neighbour.")


def _classify(values, valid):
    return np.where(valid, np.digitize(values, BREAKS)+1, 0).astype(np.uint8)


def _census(classes):
    """Cells and 4-connected patches per class, and patches under the mapping unit."""
    from scipy import ndimage
    four = ndimage.generate_binary_structure(2, 1)
    out = {}
    for code in CLASSES:
        labels, n = ndimage.label(classes == code, four)
        sizes = np.bincount(labels.ravel())[1:]
        out[str(code)] = {"cells": int(sizes.sum()), "patches": int(n), "small_patches": int((sizes < MMU_CELLS).sum())}
    return out


def _sieve(classes, valid):
    """GDAL SieveFilter, 4-connected, repeated until no patch is under MMU_CELLS. NoData never takes part: the mask keeps
    it out, and the source must not carry a NoData value (with one set, GDAL 3.12 writes an all-zero result)."""
    from osgeo import gdal
    gdal.UseExceptions()
    mem = gdal.GetDriverByName("MEM")
    rows, cols = classes.shape
    src = mem.Create("", cols, rows, 1, gdal.GDT_Byte)
    src.GetRasterBand(1).WriteArray(classes)
    mask = mem.Create("", cols, rows, 1, gdal.GDT_Byte)
    mask.GetRasterBand(1).WriteArray(valid.astype(np.uint8))
    passes = []
    for _ in range(10):
        gdal.SieveFilter(src.GetRasterBand(1), mask.GetRasterBand(1), src.GetRasterBand(1), MMU_CELLS, 4)
        census = _census(src.GetRasterBand(1).ReadAsArray())
        small = sum(c["small_patches"] for c in census.values())
        passes.append(small)
        if small == 0:
            break
    out = src.GetRasterBand(1).ReadAsArray()
    out[~valid] = 0
    return out, passes


def _write(array, reference, path):
    import arcpy
    from osgeo import gdal
    gdal.UseExceptions()
    target = gdal.GetDriverByName("GTiff").Create(str(path), array.shape[1], array.shape[0], 1, gdal.GDT_Byte,
                                                  ["COMPRESS=LZW", "TILED=YES"])
    target.SetGeoTransform(reference.GetGeoTransform())
    target.SetProjection(reference.GetProjection())
    target.GetRasterBand(1).SetNoDataValue(0)
    target.GetRasterBand(1).WriteArray(array)
    target.FlushCache()
    target = None
    arcpy.management.BuildPyramids(str(path), resample_technique="NEAREST")


def classes(out):
    from osgeo import gdal
    from canopy import planning
    gdal.UseExceptions()
    out = Path(out).resolve()
    if (out/"classes.json").exists():
        raise FileExistsError(f"{out} already holds the class rasters")
    out.mkdir(parents=True, exist_ok=True)
    started = datetime.datetime.now().isoformat(timespec="seconds")
    source = gdal.Open(str(SLOPE))
    band = source.GetRasterBand(1)
    values = band.ReadAsArray()
    valid = (values != np.float32(band.GetNoDataValue())) & np.isfinite(values)
    raw = _classify(values, valid)
    del values
    print("raw classes", flush=True)
    raw_census = _census(raw)
    _write(raw, source, out/"slope_class_raw.tif")
    print("sieve", flush=True)
    clean, passes = _sieve(raw, valid)
    del raw
    clean_census = _census(clean)
    _write(clean, source, out/"slope_class.tif")
    planning._metadata(str(out/"slope_class_raw.tif"), DESCRIPTION.split(" Patches")[0]+" No cleanup.")
    planning._metadata(str(out/"slope_class.tif"), DESCRIPTION)
    record = {"schema": "slope-tiles-classes/1", "started": started,
              "finished": datetime.datetime.now().isoformat(timespec="seconds"), "input": str(SLOPE),
              "valid_cells": int(valid.sum()), "breaks_percent": BREAKS, "classes": CLASSES,
              "mmu_cells": MMU_CELLS, "mmu_m2": MMU_CELLS*CELL_AREA, "connectivity": 4, "sieve_passes_small_left": passes,
              "raw": raw_census, "clean": clean_census,
              "outputs": {"raw": str(out/"slope_class_raw.tif"), "clean": str(out/"slope_class.tif")}}
    (out/"classes.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps({"passes": passes, "raw": raw_census, "clean": clean_census}, indent=1))


def _polygons(raster, fc):
    """RasterToPolygon without simplification, single parts, plus the code and label fields."""
    import arcpy
    from canopy import planning
    arcpy.conversion.RasterToPolygon(str(raster), fc, "NO_SIMPLIFY", "Value", "SINGLE_OUTER_PART")
    arcpy.management.AlterField(fc, "gridcode", "SLOPE_CODE", "Slope class code")
    # RasterToPolygon's Id is a per-polygon number; left in, a new unique value renderer defaults to it and, with 129k
    # values, comes back without settable fields.
    arcpy.management.DeleteField(fc, "Id")
    arcpy.management.AddField(fc, "SLOPE_CLASS", "TEXT", field_length=16, field_alias="Slope class")
    with arcpy.da.UpdateCursor(fc, ["SLOPE_CODE", "SLOPE_CLASS"]) as rows:
        for code, _ in rows:
            rows.updateRow([code, CLASSES[code]])
    planning._metadata(fc, DESCRIPTION)
    return fc


def _gdb(folder):
    import arcpy
    gdb = folder/"slope_tiles.gdb"
    if not gdb.exists():
        arcpy.management.CreateFileGDB(str(folder), gdb.name)
    return gdb


def polygons(out):
    import arcpy
    out = Path(out).resolve()
    fc = _gdb(out)/"slope_classes"
    if arcpy.Exists(str(fc)):
        raise FileExistsError(fc)
    started = datetime.datetime.now().isoformat(timespec="seconds")
    with arcpy.EnvManager(parallelProcessingFactor="100%"):
        _polygons(out/"slope_class.tif", str(fc))
    record = {"started": started, "finished": datetime.datetime.now().isoformat(timespec="seconds"),
              "feature_class": str(fc), "features": int(arcpy.management.GetCount(str(fc))[0])}
    (out/"polygons.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps(record, indent=1))


def _symbolise(layer):
    """Unique values on SLOPE_CODE in class order, labelled, solid fills without outlines."""
    sym = layer.symbology
    sym.updateRenderer("UniqueValueRenderer")
    sym.renderer.fields = ["SLOPE_CODE"]
    group = sym.renderer.groups[0]
    group.heading = "Slope (percent)"
    found = []
    for item in group.items:
        code = int(item.values[0][0])
        found.append(code)
        item.label = CLASSES[code]
        item.symbol.color = {"RGB": [*COLOURS[code], 100]}
        item.symbol.outlineColor = {"RGB": [0, 0, 0, 0]}
        item.symbol.outlineWidth = 0
    if found != sorted(CLASSES):
        raise RuntimeError(f"the layer's classes are {found}, not 1-6 in order")
    layer.symbology = sym


def _package(folder, fc, name, summary):
    """A new project from Blank.aprx, one Web Mercator map with the symbolised layer, and the .vtpk."""
    import arcpy
    from canopy import planning
    project_path = folder/f"{name}.aprx"
    vtpk = folder/f"{name}.vtpk"
    for path in (project_path, vtpk):
        if path.exists():
            raise FileExistsError(path)
    template = Path(arcpy.GetInstallInfo()["InstallDir"])/r"Resources\ArcToolBox\Services\routingservices\data\Blank.aprx"
    shutil.copyfile(template, project_path)
    project = arcpy.mp.ArcGISProject(str(project_path))
    for existing in project.listMaps():
        project.deleteItem(existing)
    slope_map = project.createMap(MAP_NAME, "MAP")
    for basemap in slope_map.listLayers():
        slope_map.removeLayer(basemap)
    item = slope_map.metadata                           # the package tool refuses a map without a description
    item.title = MAP_NAME
    item.summary = summary
    item.description = f"{DESCRIPTION}\n\n{planning.WARNING}"
    item.tags = TAGS
    item.credits = "Millcreek GIS from the 2023 Salt Lake Valley QL1 lidar"
    item.save()
    layer = slope_map.addDataFromPath(str(fc))
    layer.name = LAYER_NAME
    _symbolise(layer)
    slope_map.spatialReference = arcpy.SpatialReference(3857)   # after the layer: adding the first one resets it
    project.save()
    started = datetime.datetime.now().isoformat(timespec="seconds")
    arcpy.management.CreateVectorTilePackage(slope_map, str(vtpk), "ONLINE", None, "INDEXED", MIN_SCALE, MAX_SCALE,
                                             None, summary, TAGS)
    project.save()
    del project
    return {"project": str(project_path), "vtpk": str(vtpk), "vtpk_bytes": vtpk.stat().st_size,
            "tiling_started": started, "tiling_finished": datetime.datetime.now().isoformat(timespec="seconds")}


TAGS = "slope, lidar, Millcreek, planning estimate"
SUMMARY = ("Millcreek terrain slope in six classes (under 10%, 10-15%, 15-20%, 20-25%, 25-30%, 30% and over) from the 2023 "
           "QL1 lidar at 0.5 m; patches under 4 m2 merged into their neighbours. Unvalidated LiDAR planning estimate, not a "
           "surveyed surface.")


def pilot(out):
    """The whole chain on the pilot window: clip the cleaned class raster, polygonize, project and package."""
    import arcpy
    out = Path(out).resolve()
    folder = out/"pilot"
    if folder.exists():
        raise FileExistsError(folder)
    folder.mkdir(parents=True)
    x0, y0, x1, y1 = PILOT
    window = str(folder/"slope_class_window.tif")
    arcpy.management.Clip(str(out/"slope_class.tif"), f"{x0} {y0} {x1} {y1}", window,
                          maintain_clipping_extent="MAINTAIN_EXTENT")
    fc = str(_gdb(folder)/"slope_classes")
    _polygons(window, fc)
    record = {"window": PILOT, "features": int(arcpy.management.GetCount(fc)[0]),
              **_package(folder, fc, "slope_classes_pilot", SUMMARY)}
    record["package"] = _inspect(record["vtpk"])
    (folder/"pilot.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps(record, indent=1))


def tiles(out):
    out = Path(out).resolve()
    fc = out/"slope_tiles.gdb"/"slope_classes"
    record = _package(out, fc, "millcreek_slope_classes", SUMMARY)
    (out/"tiles.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps(record, indent=1))


def _inspect(vtpk):
    """The package's tiling (p12/root.json) and style layers (p12/resources/styles/root.json), read from the zip."""
    with zipfile.ZipFile(vtpk) as z:
        names = z.namelist()
        root = json.loads(z.read("p12/root.json"))
        style = json.loads(z.read("p12/resources/styles/root.json"))
    lods = root.get("tileInfo", {}).get("lods", [])
    return {"entries": len(names), "bundles": sum(1 for n in names if n.endswith(".bundle")),
            "spatial_reference": root.get("tileInfo", {}).get("spatialReference"),
            "lods": [lods[0]["level"], lods[-1]["level"]] if lods else None,
            "min_scale": root.get("minScale"), "max_scale": root.get("maxScale"),
            "full_extent": root.get("fullExtent"),
            "style_layers": [{"id": s.get("id"), "type": s.get("type"),
                              "filter": s.get("filter"), "fill": s.get("paint", {}).get("fill-color")}
                             for s in style.get("layers", [])]}


def verify(out):
    """Polygon area per class against the cleaned raster (equal without simplification) and the raw raster (the cleanup
    change); the footprint; the package's tiling and styles; and that Pro opens the package."""
    import arcpy
    out = Path(out).resolve()
    record = json.loads((out/"classes.json").read_text(encoding="utf-8"))
    package = json.loads((out/"tiles.json").read_text(encoding="utf-8"))
    fc = str(out/"slope_tiles.gdb"/"slope_classes")
    area, count = {str(c): 0.0 for c in CLASSES}, {str(c): 0 for c in CLASSES}
    labels_ok = True
    with arcpy.da.SearchCursor(fc, ["SLOPE_CODE", "SLOPE_CLASS", "SHAPE@AREA"]) as rows:
        for code, label, a in rows:
            area[str(code)] += a
            count[str(code)] += 1
            labels_ok &= label == CLASSES[code]
    total = record["valid_cells"]*CELL_AREA
    classes_out = {}
    for c in area:
        raw = record["raw"][c]["cells"]*CELL_AREA
        clean = record["clean"][c]["cells"]*CELL_AREA
        classes_out[c] = {"label": CLASSES[int(c)], "polygon_m2": round(area[c], 2), "clean_raster_m2": clean,
                          "raw_raster_m2": raw, "polygon_minus_clean_m2": round(area[c]-clean, 4),
                          "cleanup_change_m2": round(area[c]-raw, 2),
                          "raw_pct_city": round(100*raw/total, 3), "polygon_pct_city": round(100*area[c]/total, 3),
                          "polygons": count[c], "raw_patches": record["raw"][c]["patches"],
                          "clean_patches": record["clean"][c]["patches"]}
    above = {}
    for i, b in enumerate(BREAKS, start=2):
        raw = sum(record["raw"][str(c)]["cells"] for c in range(i, 7))*CELL_AREA
        poly = sum(area[str(c)] for c in range(i, 7))
        above[f">={b}%"] = {"raw_pct_city": round(100*raw/total, 3), "polygon_pct_city": round(100*poly/total, 3)}
    aprx = arcpy.mp.ArcGISProject(package["project"])
    probe = aprx.createMap("vtpk check", "MAP")
    layer = probe.addDataFromPath(package["vtpk"])
    opened = {"layer": layer.name, "cim_class": type(layer.getDefinition("V3")).__name__,
              "data_source": layer.dataSource}
    aprx.deleteItem(probe)
    del aprx
    result = {"feature_class": fc, "features": sum(count.values()), "labels_match_codes": bool(labels_ok),
              "city_m2": total, "polygon_total_m2": round(sum(area.values()), 2), "classes": classes_out,
              "area_above_threshold": above, "package": _inspect(package["vtpk"]), "opened_in_pro": opened}
    (out/"verify.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("classes", "pilot", "polygons", "tiles", "verify"))
    p.add_argument("out", type=Path)
    a = p.parse_args(argv)
    {"classes": classes, "pilot": pilot, "polygons": polygons, "tiles": tiles, "verify": verify}[a.step](a.out)


if __name__ == "__main__":
    main()
