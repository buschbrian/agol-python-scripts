r"""Light UTM 12N basemap for the local ArcGIS Urban model, on the elevation layer's tiling scheme (October 27, 2026).

    python reviews/2026-10-26/urban-utm/basemap.py data OUT            hillshade of the unmasked terrain + linework in 6341
    python reviews/2026-10-26/urban-utm/basemap.py map OUT             OUT\basemap\basemap.aprx with the "Urban UTM basemap" map
    python reviews/2026-10-26/urban-utm/basemap.py scheme OUT          the elevation scheme with PNG tiles (OUT\basemap\scheme.xml)
    python reviews/2026-10-26/urban-utm/basemap.py cache OUT [--pilot] the tile cache and .tpkx
    python reviews/2026-10-26/urban-utm/basemap.py verify OUT          package scheme against the hosted terrain's tileInfo
    python reviews/2026-10-26/urban-utm/basemap.py webmap OUT --layer ID [--go]   org-only web map wrapper for Urban's gallery

ArcGIS Pro Python with 3D Analyst (PYTHONNOUSERSITE=1), after urban_utm.py's scheme and elevation steps (it reuses
OUT\elevation\scheme.xml and the elevation AOI). Writes only under OUT\basemap; uploads go through upload.py.
Urban creates a local model only from a projected basemap, and the elevation layer "must have the same coordinate system
and tiling scheme as the basemap". So the basemap is cached on exactly the elevation scheme (origin, 256 px, 96 dpi,
levels 0-14 to 0.5 m), over the same footprint, with PNG tiles instead of LERC.
- Hillshade: computed from terrain_context.tif (315 degrees, 45, no shadows, z 1, as terrain-city), because every
  existing hillshade is masked to the city and the elevation covers the unmasked mosaic.
- Linework: Millcreek parcels, Centerlines_Millcreek (UGRC schema, CARTOCODE), the Millcreek municipal boundary. These are
  NAD83 State Plane Utah Central feet, projected to 6341 with no datum transformation (sub-metre on a basemap).
"""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve()
REVIEWS = HERE.parents[2]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


uu = _load("urban_utm", HERE.parent/"urban_utm.py")
pt = _load("package_tiles", REVIEWS/"2026-10-22"/"hosting"/"tiles"/"package_tiles.py")

SERVICES = "https://services9.arcgis.com/XRrSFvEwSsReIxuA/arcgis/rest/services"
SOURCES = {"parcels": f"{SERVICES}/Millcreek_Parcels/FeatureServer/0",
           "streets": f"{SERVICES}/Centerlines_Millcreek/FeatureServer/0",
           "boundary": f"{SERVICES}/Municipal_Boundary/FeatureServer/0"}
TERRAIN_SERVICE = ("https://tiles.arcgis.com/tiles/XRrSFvEwSsReIxuA/arcgis/rest/services/Millcreek_bare_earth_terrain_for_"
                   "ArcGIS_Urban_UTM_12N_0_5_m_2023_lidar_planning_/ImageServer")
MAP_NAME = "Urban UTM basemap"
NAME = "millcreek_basemap_utm_20261027"
MAJOR = "CARTOCODE IN ('1','2','3','4','5','6','7','8')"
GROUND = [245, 245, 242]
PARCEL_MAX_SCALE = 9000     # parcels from level 12 (1:7,560)
LOCAL_LABEL_SCALE = 16000   # local street names from level 11 (1:15,120)
MAJOR_LABEL_SCALE = 61000   # major street names from level 9 (1:60,472)


def folder(out):
    f = out/"basemap"
    f.mkdir(parents=True, exist_ok=True)
    return f


def data(out):
    import arcpy
    f = folder(out)
    arcpy.env.overwriteOutput = True
    arcpy.CheckOutExtension("3D")
    hs = f/"hillshade_context.tif"
    arcpy.ddd.HillShade(str(uu.TERRAIN_CONTEXT), str(hs), 315, 45, "NO_SHADOWS", 1)
    gdb = f/"basemap.gdb"
    if not arcpy.Exists(str(gdb)):
        arcpy.management.CreateFileGDB(str(f), gdb.name)
    sr = arcpy.SpatialReference(uu.WKID)
    record = {"created": uu.now(), "hillshade": {"file": str(hs), "source": str(uu.TERRAIN_CONTEXT),
                                                 "azimuth": 315, "altitude": 45, "shadows": False, "z_factor": 1},
              "layers": {}}
    for key, url in SOURCES.items():
        target = gdb/key
        where = "NAME = 'Millcreek'" if key == "boundary" else None
        lyr = arcpy.management.MakeFeatureLayer(url, f"src_{key}", where).getOutput(0)
        arcpy.management.Project(lyr, str(target), sr)
        record["layers"][key] = {"source": url, "where": where, "count": int(arcpy.management.GetCount(str(target))[0]),
                                 "transformation": None}
    r = arcpy.Raster(str(hs))
    record["hillshade"]["extent"] = [r.extent.XMin, r.extent.YMin, r.extent.XMax, r.extent.YMax]
    uu.write_json(f/"data.json", record)
    print(json.dumps(record["layers"], indent=1))


def _stroke(cim, rgb, width, dashes=None):
    s = cim.CreateCIMObjectFromClassName("CIMSolidStroke", "V3")
    s.color = cim.CreateCIMObjectFromClassName("CIMRGBColor", "V3")
    s.color.values = list(rgb) + [100]
    s.width = width
    s.capStyle, s.joinStyle = "Round", "Round"
    if dashes:
        d = cim.CreateCIMObjectFromClassName("CIMGeometricEffectDashes", "V3")
        d.dashTemplate = dashes
        s.effects = [d]
    return s


def _lines(lyr, strokes):
    """Strokes are drawn bottom to top in the list order given (CIM draws its first symbol layer on top)."""
    from arcpy import cim
    d = lyr.getDefinition("V3")
    d.renderer.symbol.symbol.symbolLayers = [_stroke(cim, *s) for s in reversed(strokes)]
    lyr.setDefinition(d)


def _fill(lyr, rgb, outline=None, width=0):
    s = lyr.symbology
    s.updateRenderer("SimpleRenderer")
    s.renderer.symbol.color = {"RGB": (list(rgb) + [100]) if rgb else [0, 0, 0, 0]}
    s.renderer.symbol.outlineColor = {"RGB": (list(outline) + [100]) if outline else [0, 0, 0, 0]}
    s.renderer.symbol.outlineWidth = width
    lyr.symbology = s


def _labels(lyr, min_scale, size):
    d = lyr.getDefinition("V3")
    for lc in d.labelClasses:
        lc.expression = "$feature.FULLNAME"
        lc.expressionEngine = "Arcade"
        lc.minimumScale = min_scale
        lc.textSymbol.symbol.height = size
        lc.textSymbol.symbol.symbol.symbolLayers[0].color.values = [95, 95, 95, 100]
        mp =lc.maplexLabelPlacementProperties
        mp.connectionType = "MinimizeLabels"
        mp.thinDuplicateLabels = True
        mp.repeatLabel = True
        lc.visibility = True
    lyr.setDefinition(d)
    lyr.showLabels = True


def _halo(lyr):
    """White halo on the street names (the text symbol's halo polygon symbol)."""
    from arcpy import cim
    d = lyr.getDefinition("V3")
    for lc in d.labelClasses:
        fill = cim.CreateCIMObjectFromClassName("CIMSolidFill", "V3")
        fill.color = cim.CreateCIMObjectFromClassName("CIMRGBColor", "V3")
        fill.color.values = [255, 255, 255, 100]
        poly = cim.CreateCIMObjectFromClassName("CIMPolygonSymbol", "V3")
        poly.symbolLayers = [fill]
        lc.textSymbol.symbol.haloSymbol = poly
        lc.textSymbol.symbol.haloSize = 1
    lyr.setDefinition(d)


def build_map(out):
    import arcpy
    f = folder(out)
    gdb = f/"basemap.gdb"
    aprx_path = f/"basemap.aprx"
    if not aprx_path.exists():
        arcpy.mp.ArcGISProject(r"D:\ArcGISProjects\900E_SAP\900E_SAP.aprx").saveACopy(str(aprx_path))
    aprx = arcpy.mp.ArcGISProject(str(aprx_path))
    for lo in aprx.listLayouts():
        aprx.deleteItem(lo)
    for m in aprx.listMaps():
        aprx.deleteItem(m)
    m = aprx.createMap(MAP_NAME, "MAP")
    for lyr in m.listLayers():
        m.removeLayer(lyr)
    m.spatialReference = arcpy.SpatialReference(uu.WKID)

    ground = m.addDataFromPath(str(out/"elevation"/"full"/"aoi.shp"))
    ground.name = "ground"
    _fill(ground, GROUND)
    hs = m.addDataFromPath(str(f/"hillshade_context.tif"))
    hs.name = "hillshade"
    hs.transparency = 62
    m.moveLayer(ground, hs, "BEFORE")   # rasters are added at the bottom; the hillshade shades the ground fill
    parcels = m.addDataFromPath(str(gdb/"parcels"))
    parcels.name = "parcels"
    _fill(parcels, None, (196, 196, 194), 0.4)
    parcels.minThreshold = PARCEL_MAX_SCALE
    boundary = m.addDataFromPath(str(gdb/"boundary"))
    boundary.name = "Millcreek boundary"
    _fill(boundary, None)
    _boundary_as_outline(boundary)
    local = m.addDataFromPath(str(gdb/"streets"))
    local.name = "local streets"
    local.definitionQuery = f"NOT ({MAJOR})"
    major = m.addDataFromPath(str(gdb/"streets"))
    major.name = "major streets"
    major.definitionQuery = MAJOR
    _lines(local, [((205, 205, 205), 2.6), ((255, 255, 255), 1.6)])
    _lines(major, [((180, 180, 180), 4.6), ((255, 255, 255), 3.4)])
    _labels(local, LOCAL_LABEL_SCALE, 7.5)
    _labels(major, MAJOR_LABEL_SCALE, 8.5)
    _halo(local)
    _halo(major)
    aprx.save()
    m.exportToMAPX(str(f/"basemap.mapx"))
    print([(lyr.name, lyr.isBasemapLayer) for lyr in m.listLayers()])


def _boundary_as_outline(lyr):
    """The boundary polygon drawn as its outline only: a white under-stroke and a dashed grey line, no fill."""
    from arcpy import cim
    d = lyr.getDefinition("V3")
    poly = d.renderer.symbol.symbol
    poly.symbolLayers = [_stroke(cim, (105, 105, 110), 1.6, [6, 3]), _stroke(cim, (255, 255, 255), 4.0)]
    lyr.setDefinition(d)


def scheme(out):
    f = folder(out)
    src = out/"elevation"/"scheme.xml"
    text = src.read_text(encoding="utf-8")
    assert text.count("<CacheTileFormat>LERC</CacheTileFormat>") == 1
    xml = f/"scheme.xml"
    xml.write_text(text.replace("<CacheTileFormat>LERC</CacheTileFormat>", "<CacheTileFormat>PNG</CacheTileFormat>"),
                   encoding="utf-8")
    s, e = uu.read_scheme(xml), uu.read_scheme(src)
    assert s["format"] == "PNG" and {k: s[k] for k in s if k != "format"} == {k: e[k] for k in e if k != "format"}, s
    uu.write_json(f/"scheme.json", {"created": uu.now(), "file": str(xml), "from": str(src), **s})


def cache(out, pilot=False):
    import arcpy
    import time
    f = folder(out)
    xml = f/"scheme.xml"
    s = uu.read_scheme(xml)
    scales = [lod["scale"] for lod in s["lods"]]
    work = f/("pilot" if pilot else "full")
    if work.exists():
        raise SystemExit(f"{work} exists")
    work.mkdir()
    scratch = work/"scratch"
    scratch.mkdir()
    arcpy.env.scratchWorkspace = str(scratch)
    if pilot:
        aoi = pt.window_aoi(arcpy, work/"window.shp")
        levels = (len(scales) - 3, len(scales) - 1)
    else:
        aoi = out/"elevation"/"full"/"aoi.shp"
        levels = (0, len(scales) - 1)
    m = arcpy.mp.ArcGISProject(str(f/"basemap.aprx")).listMaps(MAP_NAME)[0]
    record = {"created": uu.now(), "pilot": pilot, "map": str(f/"basemap.aprx"), "scheme": str(xml),
              "levels": list(levels), "aoi": str(aoi), "seconds": {}}
    started = time.time()
    arcpy.management.ManageTileCache(str(work), "RECREATE_ALL_TILES", "basemap", m, "IMPORT_SCHEME", str(xml), None,
                                     str(aoi), None, repr(scales[levels[0]]), repr(scales[levels[1]]))
    record["seconds"]["cache"] = round(time.time() - started, 1)
    cache_dir = work/"basemap"/MAP_NAME   # a map source caches into <cache name>\<map name>
    record["conf"] = pt.conf_summary((cache_dir/"conf.xml").read_text(encoding="utf-8"))
    name = NAME + ("_pilot" if pilot else "")
    target = work if pilot else f
    started = time.time()
    arcpy.management.ExportTileCache(str(cache_dir), str(target), name, "TILE_PACKAGE_TPKX", "COMPACT_V2")
    record["seconds"]["package"] = round(time.time() - started, 1)
    tpkx = target/f"{name}.tpkx"
    record["tpkx"] = {"file": str(tpkx), "bytes": tpkx.stat().st_size}
    record["levels_in_package"] = {}
    for lv in range(levels[0], levels[1] + 1):
        tiles = list(pt.package_tiles(tpkx, lv))
        record["levels_in_package"][lv] = {"tiles": len(tiles), "bytes": sum(len(d) for _, _, d in tiles)}
        if tiles and lv == levels[1]:
            biggest = max(tiles, key=lambda t: len(t[2]))
            (work/f"sample_L{lv}_r{biggest[0]}_c{biggest[1]}.png").write_bytes(biggest[2])
    shutil.rmtree(scratch, ignore_errors=True)
    uu.write_json(work/"cache.json", record)
    print(json.dumps({k: record[k] for k in ("seconds", "tpkx", "levels_in_package", "conf")}, indent=1, default=str))


def verify(out):
    """The package's tiling scheme against the hosted terrain's tileInfo, field by field."""
    import urllib.request
    import zipfile
    f = folder(out)
    tpkx = f/f"{NAME}.tpkx"
    with zipfile.ZipFile(tpkx) as z:
        root = json.loads(z.read(next(n for n in z.namelist() if n.endswith("root.json"))))
    ti = root["tileInfo"]
    try:
        with urllib.request.urlopen(TERRAIN_SERVICE + "?f=json") as r:
            terrain = json.loads(r.read())
    except Exception as exc:   # the terrain is organization-only: anonymous requests are refused
        terrain = {"error": str(exc)}
    if "tileInfo" not in terrain:
        from arcgis.gis import GIS
        terrain = GIS("pro")._con.get(TERRAIN_SERVICE, {"f": "json"})
    tt = terrain["tileInfo"]
    checks = {
        "wkid": (ti["spatialReference"].get("latestWkid") or ti["spatialReference"].get("wkid"),
                 tt["spatialReference"].get("latestWkid") or tt["spatialReference"].get("wkid")),
        "origin": ([ti["origin"]["x"], ti["origin"]["y"]], [tt["origin"]["x"], tt["origin"]["y"]]),
        "size": ([ti["rows"], ti["cols"]], [tt["rows"], tt["cols"]]),
        "dpi": (ti["dpi"], tt["dpi"]),
        "lods": ([(l["level"], round(l["scale"], 4), round(l["resolution"], 9)) for l in ti["lods"]],
                 [(l["level"], round(l["scale"], 4), round(l["resolution"], 9)) for l in tt["lods"]]),
    }
    result = {k: {"basemap": a, "terrain": b, "equal": a == b} for k, (a, b) in checks.items()}
    record = {"created": uu.now(), "tpkx": str(tpkx), "sha256": uu.sha256(tpkx), "bytes": tpkx.stat().st_size,
              "format": ti.get("format"), "checks": result, "all_equal": all(v["equal"] for v in result.values())}
    uu.write_json(f/"verify.json", record)
    print(json.dumps({k: v["equal"] for k, v in result.items()}), "format", ti.get("format"), "all", record["all_equal"])


WEBMAP_TITLE = "Millcreek light UTM 12N (ArcGIS Urban)"


def webmap(out, layer_id, go=False):
    """An organization-only web map whose basemap is the hosted tile layer, in 6341: Urban lists basemaps as web maps
    from the organization's basemap gallery group. Sharing it to that group is a separate decision (not done here)."""
    from arcgis.gis import GIS
    from arcgis.gis import ItemProperties
    gis = GIS("pro")
    layer = gis.content.get(layer_id)
    info = gis._con.get(layer.url, {"f": "json"})
    e = info["fullExtent"]
    data = {"operationalLayers": [],
            "baseMap": {"title": WEBMAP_TITLE, "baseMapLayers": [
                {"id": "millcreek_basemap_utm", "layerType": "ArcGISTiledMapServiceLayer", "url": layer.url,
                 "itemId": layer.id, "title": layer.title, "visibility": True, "opacity": 1}]},
            "spatialReference": {"wkid": 102059, "latestWkid": uu.WKID},
            "initialState": {"viewpoint": {"targetGeometry": {k: e[k] for k in ("xmin", "ymin", "xmax", "ymax")}
                                           | {"spatialReference": {"wkid": 102059, "latestWkid": uu.WKID}}}},
            "authoringApp": "basemap.py", "authoringAppVersion": "1", "version": "2.31"}
    print(json.dumps(data, indent=1))
    if not go:
        print("Dry run: add --go to create the web map (organization-only).")
        return
    if [i for i in gis.content.search(f'title:"{WEBMAP_TITLE}" AND owner:{gis.users.me.username}', item_type="Web Map")
            if i.title == WEBMAP_TITLE]:
        raise SystemExit("a web map with this title already exists")
    folder_name = "Millcreek LiDAR 2023"
    props = ItemProperties(
        title=WEBMAP_TITLE, item_type="Web Map", tags=["basemap", "ArcGIS Urban", "UTM", "Millcreek"],
        snippet="Basemap for a local ArcGIS Urban model in NAD83(2011) UTM 12N: the Millcreek light UTM tile layer.",
        description=f"<p>Web map wrapper so ArcGIS Urban can list the tile layer {layer.id} as a basemap. Its tiling "
                    "scheme equals the Millcreek bare-earth terrain for ArcGIS Urban.</p>",
        access_information=layer.accessInformation, text=json.dumps(data))
    item = gis.content.folders.get(folder_name).add(item_properties=props).result()
    item.sharing.sharing_level = "ORGANIZATION"
    item.protect(enable=True)
    record = {"created": uu.now(), "webmap": item.id, "layer": layer.id, "folder": folder_name, "access": item.access,
              "protected": item.protected, "groups": [g.id for g in item.shared_with.get("groups", [])]}
    uu.write_json(out/"basemap"/"webmap.json", record)
    print(json.dumps(record))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("data", "map", "scheme", "cache", "verify", "webmap"))
    p.add_argument("out", type=Path)
    p.add_argument("--pilot", action="store_true", help="cache: the 1 km window, finest three levels")
    p.add_argument("--layer", help="webmap: the hosted basemap tile layer's item id")
    p.add_argument("--go", action="store_true", help="webmap: create it (organization-only)")
    a = p.parse_args(argv)
    out = a.out.resolve()
    if a.step == "webmap":
        webmap(out, a.layer, a.go)
        return
    {"data": data, "map": build_map, "scheme": scheme, "verify": verify}.get(a.step, lambda o: cache(o, a.pilot))(out)


if __name__ == "__main__":
    main()
