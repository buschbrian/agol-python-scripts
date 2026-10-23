r"""Vector tile packages of the treetops, crowns and 2 m contours for ArcGIS Online (October 22, 2026), step 4 of the
hosting plan. Same scripted-map method as the slope classes (reviews/2026-10-22/slope-tiles/run_slope_tiles.py).

    python reviews/2026-10-22/hosting/vector-tiles/build_vector_tiles.py pilot OUT          each layer on a 1 km window
    python reviews/2026-10-22/hosting/vector-tiles/build_vector_tiles.py build OUT [LAYER]  the citywide packages
    python reviews/2026-10-22/hosting/vector-tiles/build_vector_tiles.py verify OUT         counts, packages, attributes

ArcGIS Pro Python (PYTHONNOUSERSITE=1). Read-only on the sources (the pilot clips copies); writes only under OUT. Nothing
is uploaded or published.
- Each package: a copy of the install's Blank.aprx, one map set to Web Mercator after its layers are added (adding the
  first layer resets the map to the data's EPSG 6341, and the ArcGIS Online scheme needs 3857), map metadata carrying the
  estimate warning (the tool refuses a map without a description), then Create Vector Tile Package, ONLINE, INDEXED.
- Levels are the vector tile scheme's (512-pixel tiles, level n = 295,828,763.795777 / 2**n). Treetops and crowns from
  level 14 (1:18,056, neighbourhood scale) to 17; contours from 10 (1:288,895) to 17, with the 2 m lines only from level 14
  and the 10 m index lines heavier at every level. Clients overzoom past level 17.
- `verify` counts features, reads each package's tiling and style, decodes one tile per layer to list the attributes the
  tiles keep, and adds each package to a map in Pro.
"""
import argparse
import datetime
import gzip
import json
from pathlib import Path
import shutil
import sys
import zipfile

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[4]
sys.path.insert(0, str(TOOLBOX))
from canopy.lidar_root import lidar_root  # noqa: E402

RUNS = lidar_root()/"2023-salt-lake-valley"/"runs"
TOP = 295828763.795777


def level(n):
    return TOP/2**n


HEIGHTS = [(5, "2 to 5 m"), (10, "5 to 10 m"), (15, "10 to 15 m"), (20, "15 to 20 m"), (50, "20 m and over")]
# ColorBrewer YlGn, 5 classes.
GREENS = [(255, 255, 204), (194, 230, 153), (120, 198, 121), (49, 163, 84), (0, 104, 55)]
TREE_WARNING = ("Unvalidated LiDAR planning estimate. Treetops are lidar detections, not a stem census: low or suppressed "
                "trees can be missed and broad trees can have several peaks. Crowns are estimated canopy regions, not "
                "surveyed crowns.")
TERRAIN_WARNING = "Unvalidated LiDAR planning estimate, not a surveyed surface."
LAYERS = {
    "treetops": {
        "source": RUNS/"millcreek-products-20261022"/"tree-count.gdb"/"city_treetops",
        "title": "Millcreek treetops (lidar)", "levels": (14, 17),
        "summary": "527,140 treetops at least 2 m tall detected in the 2023 QL1 lidar, by height. " + TREE_WARNING,
        "tags": "treetops, trees, lidar, Millcreek, planning estimate",
    },
    "crowns": {
        "source": RUNS/"millcreek-products-20261022"/"crowns.gdb"/"crowns",
        "title": "Millcreek tree crowns (lidar)", "levels": (14, 17),
        "summary": "400,063 estimated tree crowns of at least 3 m2 from the 2023 QL1 lidar, by treetop height. " + TREE_WARNING,
        "tags": "crowns, canopy, trees, lidar, Millcreek, planning estimate",
    },
    "contours": {
        "source": RUNS/"terrain-city-20261022"/"terrain.gdb"/"contours",
        "title": "Millcreek 2 m contours (lidar)", "levels": (10, 17),
        "summary": ("2 m contours of the 2023 QL1 lidar terrain, index contours every 10 m; the 2 m lines from 1:18,056. "
                    "At 0.5 m they follow curbs and berms. " + TERRAIN_WARNING),
        "tags": "contours, terrain, elevation, lidar, Millcreek, planning estimate",
    },
}
# A 1 km window in the middle of the city's grid (the slope pilot's window is foothills with few trees).
PILOT = (427774.0, 4503821.0, 428774.0, 4504821.0)


def _rgb(rgb, alpha=100):
    return {"RGB": [*rgb, alpha]}


def _graduated(layer, point):
    """HEIGHT_M in the HEIGHTS classes, YlGn; points as small circles, crowns as fills with a thin darker edge. The
    labels go in through the CIM: arcpy.mp rewrites a break's label whenever the renderer is assigned."""
    sym = layer.symbology
    sym.updateRenderer("GraduatedColorsRenderer")
    sym.renderer.classificationField = "HEIGHT_M"
    sym.renderer.breakCount = len(HEIGHTS)
    for brk, (upper, _), rgb in zip(sym.renderer.classBreaks, HEIGHTS, GREENS):
        brk.upperBound = upper
        brk.symbol.color = _rgb(rgb)
        if point:
            brk.symbol.size = 4
            brk.symbol.outlineColor = _rgb((60, 60, 60))
            brk.symbol.outlineWidth = 0.4
        else:
            brk.symbol.outlineColor = _rgb((0, 80, 40), 60)
            brk.symbol.outlineWidth = 0.4
    layer.symbology = sym
    cim = layer.getDefinition("V3")
    for brk, (_, label) in zip(cim.renderer.breaks, HEIGHTS):
        brk.label = label
    cim.renderer.heading = "Height (treetop)"
    layer.setDefinition(cim)
    got = [(b.upperBound, b.label) for b in layer.getDefinition("V3").renderer.breaks]
    if got != HEIGHTS:
        raise RuntimeError(f"height classes did not stick: {got}")


def _line(layer, rgb, width, alpha=100):
    sym = layer.symbology
    sym.updateRenderer("SimpleRenderer")
    sym.renderer.symbol.color = _rgb(rgb, alpha)
    sym.renderer.symbol.width = width
    sym.renderer.label = layer.name
    layer.symbology = sym


def _add_layers(name, fc, layer_map):
    if name == "treetops":
        layer = layer_map.addDataFromPath(str(fc))
        layer.name = "Treetops by height"
        _graduated(layer, point=True)
    elif name == "crowns":
        layer = layer_map.addDataFromPath(str(fc))
        layer.name = "Crowns by treetop height"
        _graduated(layer, point=False)
    else:
        minor = layer_map.addDataFromPath(str(fc))
        minor.name = "Contours (2 m)"
        minor.definitionQuery = "INDEX = 0"
        minor.minThreshold = level(14)*1.0001        # visible at level 14 and closer
        _line(minor, (140, 81, 10), 0.5, 60)
        index = layer_map.addDataFromPath(str(fc))
        index.name = "Index contours (10 m)"
        index.definitionQuery = "INDEX = 1"
        _line(index, (140, 81, 10), 1.2)


def _package(folder, name, fc):
    import arcpy
    spec = LAYERS[name]
    project_path, vtpk = folder/f"{name}.aprx", folder/f"millcreek_{name}.vtpk"
    for path in (project_path, vtpk):
        if path.exists():
            raise FileExistsError(path)
    template = Path(arcpy.GetInstallInfo()["InstallDir"])/r"Resources\ArcToolBox\Services\routingservices\data\Blank.aprx"
    shutil.copyfile(template, project_path)
    project = arcpy.mp.ArcGISProject(str(project_path))
    for existing in project.listMaps():
        project.deleteItem(existing)
    layer_map = project.createMap(spec["title"], "MAP")
    for basemap in layer_map.listLayers():
        layer_map.removeLayer(basemap)
    item = layer_map.metadata
    item.title = spec["title"]
    item.summary = spec["summary"]
    item.description = spec["summary"]
    item.tags = spec["tags"]
    item.credits = "Millcreek GIS from the 2023 Salt Lake Valley QL1 lidar"
    item.save()
    _add_layers(name, fc, layer_map)
    layer_map.spatialReference = arcpy.SpatialReference(3857)
    project.save()
    lo, hi = spec["levels"]
    started = datetime.datetime.now().isoformat(timespec="seconds")
    arcpy.management.CreateVectorTilePackage(layer_map, str(vtpk), "ONLINE", None, "INDEXED", level(lo), level(hi),
                                             None, spec["summary"], spec["tags"])
    project.save()
    del project
    return {"source": str(fc), "features_in": int(arcpy.management.GetCount(str(fc))[0]), "levels": [lo, hi],
            "project": str(project_path), "vtpk": str(vtpk), "vtpk_bytes": vtpk.stat().st_size,
            "started": started, "finished": datetime.datetime.now().isoformat(timespec="seconds")}


def pilot(out):
    import arcpy
    folder = Path(out).resolve()/"pilot"
    if folder.exists():
        raise FileExistsError(folder)
    folder.mkdir(parents=True)
    arcpy.management.CreateFileGDB(str(folder), "pilot.gdb")
    x0, y0, x1, y1 = PILOT
    window = arcpy.Polygon(arcpy.Array([arcpy.Point(x0, y0), arcpy.Point(x0, y1), arcpy.Point(x1, y1),
                                        arcpy.Point(x1, y0), arcpy.Point(x0, y0)]), arcpy.SpatialReference(6341))
    result = {"window": PILOT}
    for name, spec in LAYERS.items():
        fc = str(folder/"pilot.gdb"/name)
        arcpy.analysis.Clip(str(spec["source"]), window, fc)
        result[name] = _package(folder, name, fc)
        result[name]["package"] = inspect(result[name]["vtpk"])
        print(name, result[name]["features_in"], result[name]["vtpk_bytes"], flush=True)
    (folder/"pilot.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))


def build(out, names):
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    record_path = out/"packages.json"
    record = json.loads(record_path.read_text(encoding="utf-8")) if record_path.exists() else {}
    for name in names or LAYERS:
        print(f"{name} {datetime.datetime.now():%H:%M:%S}", flush=True)
        record[name] = _package(out, name, LAYERS[name]["source"])
        record_path.write_text(json.dumps(record, indent=1), encoding="utf-8")
        print(json.dumps(record[name], indent=1), flush=True)


def _varints(buf):
    """(field, wire type, value) for each field of one protobuf message; value is bytes for length-delimited fields."""
    i = 0

    def varint():
        nonlocal i
        shift = result = 0
        while True:
            b = buf[i]
            i += 1
            result |= (b & 0x7F) << shift
            if not b & 0x80:
                return result
            shift += 7
    while i < len(buf):
        key = varint()
        field, wire = key >> 3, key & 7
        if wire == 0:
            yield field, wire, varint()
        elif wire == 2:
            n = varint()
            yield field, wire, buf[i:i+n]
            i += n
        elif wire == 5:
            i += 4
        elif wire == 1:
            i += 8
        else:
            raise ValueError(f"wire type {wire}")


def tile_attributes(vtpk):
    """The layers and attribute keys of the fullest tile in the package's deepest bundle (compact cache v2: a 64-byte
    header, then 128 x 128 eight-byte index entries of 40-bit offset and 24-bit size; tiles are gzipped Mapbox vector
    tiles). Esri merges features that share a symbol, so "features" counts symbol groups, not source features; "extent"
    is the tile's coordinate range (4096 for a 512-pixel tile, larger in sparse areas kept at a shallower level)."""
    with zipfile.ZipFile(vtpk) as z:
        bundles = [n for n in z.namelist() if n.endswith(".bundle")]
        deepest = max(bundles, key=lambda n: (int(n.split("/L")[1][:2]), z.getinfo(n).file_size))
        data = z.read(deepest)
    best = None
    for k in range(128*128):
        entry = int.from_bytes(data[64+8*k:72+8*k], "little")
        offset, size = entry & ((1 << 40)-1), entry >> 40
        if size and (best is None or size > best[1]):
            best = (offset, size)
    raw = data[best[0]:best[0]+best[1]]
    tile = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
    layers = {}
    for field, _, value in _varints(tile):
        if field == 3:
            name, keys, features, extent = None, [], 0, None
            for f, _, v in _varints(value):
                if f == 1:
                    name = v.decode()
                elif f == 2:
                    features += 1
                elif f == 3:
                    keys.append(v.decode())
                elif f == 5:
                    extent = v
            layers[name] = {"keys": keys, "features": features, "extent": extent}
    return {"bundle": deepest, "tile_bytes": best[1], "layers": layers}


def _tiles(vtpk):
    """(level, row, column, decoded tile) for every tile in the package (bundle names give the first row and column in
    hex; the index runs row-major over 128 x 128 tiles)."""
    with zipfile.ZipFile(vtpk) as z:
        for name in sorted(n for n in z.namelist() if n.endswith(".bundle")):
            data, stem = z.read(name), name.split("/")
            lvl = int(stem[-2][1:])
            r0, c0 = int(stem[-1][1:5], 16), int(stem[-1][6:10], 16)
            for k in range(128*128):
                entry = int.from_bytes(data[64+8*k:72+8*k], "little")
                offset, size = entry & ((1 << 40)-1), entry >> 40
                if size:
                    raw = data[offset:offset+size]
                    yield lvl, r0+k//128, c0+k % 128, gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw


def _commands(geometry):
    """The geometry's packed uint32 commands and parameters."""
    out, i, shift, value = [], 0, 0, 0
    for b in geometry:
        value |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            out.append(value)
            value = shift = 0
    return out


def point_census(vtpk):
    """Points per tile inside the tile's own extent (tiles carry a buffer of their neighbours' points, left out), by
    level and summed over the leaf tiles (no child tile at the next level). The package is indexed: sparse areas stop at
    a shallower level and are overzoomed, so the leaves together cover the data once and should hold every point."""
    counts = {}
    for lvl, row, col, tile in _tiles(vtpk):
        n = e = 0
        for field, _, layer in _varints(tile):
            if field != 3:
                continue
            extent, geoms = 4096, []
            for f, _, v in _varints(layer):
                if f == 5:
                    extent = v
                elif f == 2:
                    geoms.extend(g for gf, _, g in _varints(v) if gf == 4)
            for g in geoms:
                c = _commands(g)
                x = y = i = 0
                while i < len(c):
                    cmd, count = c[i] & 7, c[i] >> 3
                    i += 1
                    if cmd == 7:
                        continue
                    for _ in range(count):
                        dx, dy = c[i], c[i+1]
                        x += (dx >> 1) ^ -(dx & 1)
                        y += (dy >> 1) ^ -(dy & 1)
                        i += 2
                        if cmd != 1:
                            continue
                        if 0 <= x < extent and 0 <= y < extent:
                            n += 1
                        elif -1 <= x <= extent and -1 <= y <= extent:
                            e += 1
        counts[(lvl, row, col)] = (n, e)
    by_level, leaves, edges = {}, 0, 0
    for (lvl, row, col), (n, e) in counts.items():
        by_level[lvl] = by_level.get(lvl, 0)+n
        if not any((lvl+1, 2*row+dr, 2*col+dc) in counts for dr in (0, 1) for dc in (0, 1)):
            leaves += n
            edges += e
    # A point rounded onto a tile edge sits at x = extent in one tile and x = -1 in its neighbour, inside neither; each
    # such point is counted once per copy in "on_leaf_tile_edges".
    return {"by_level": dict(sorted(by_level.items())), "in_leaf_tiles": leaves, "on_leaf_tile_edges": edges}


def inspect(vtpk):
    with zipfile.ZipFile(vtpk) as z:
        names = z.namelist()
        root = json.loads(z.read("p12/root.json"))
        style = json.loads(z.read("p12/resources/styles/root.json"))
    lods = root.get("tileInfo", {}).get("lods", [])
    return {"entries": len(names), "bundles": sum(1 for n in names if n.endswith(".bundle")),
            "lods": [lods[0]["level"], lods[-1]["level"]] if lods else None,
            "min_scale": root.get("minScale"), "max_scale": root.get("maxScale"),
            "style_layers": [{"id": s.get("id"), "type": s.get("type"), "minzoom": s.get("minzoom"),
                              "maxzoom": s.get("maxzoom")} for s in style.get("layers", [])]}


def verify(out):
    import arcpy
    out = Path(out).resolve()
    record = json.loads((out/"packages.json").read_text(encoding="utf-8"))
    slope = RUNS/"slope-tiles-20261022"/"tiles.json"         # the slope package, so one record covers all four
    if slope.exists():
        entry = json.loads(slope.read_text(encoding="utf-8"))
        fc = str(slope.parent/"slope_tiles.gdb"/"slope_classes")
        record["slope"] = {**entry, "source": fc, "features_in": int(arcpy.management.GetCount(fc)[0]),
                           "levels": [0, 17]}
    result = {}
    for name, entry in record.items():
        project = arcpy.mp.ArcGISProject(entry["project"])
        probe = project.createMap("vtpk check", "MAP")
        layer = probe.addDataFromPath(entry["vtpk"])
        opened = {"layer": layer.name, "cim_class": type(layer.getDefinition("V3")).__name__}
        project.deleteItem(probe)
        del project
        fields = [f.name for f in arcpy.ListFields(entry["source"]) if f.type not in ("OID", "Geometry")]
        tiles = tile_attributes(entry["vtpk"])
        kept = sorted({k for layer_info in tiles["layers"].values() for k in layer_info["keys"]})
        result[name] = {"features_in": int(arcpy.management.GetCount(entry["source"])[0]),
                        "recorded_features_in": entry["features_in"], "vtpk_bytes": Path(entry["vtpk"]).stat().st_size,
                        "levels": entry["levels"], "package": inspect(entry["vtpk"]), "opened_in_pro": opened,
                        "tile_sample": tiles, "source_fields": fields, "tile_keys": kept,
                        "fields_dropped": [f for f in fields if f not in kept]}
        if name == "treetops":
            result[name]["points_in_tiles"] = point_census(entry["vtpk"])
    (out/"verify.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("pilot", "build", "verify"))
    p.add_argument("out", type=Path)
    p.add_argument("layers", nargs="*", help=f"build only these of {', '.join(LAYERS)}")
    a = p.parse_args(argv)
    unknown = set(a.layers)-set(LAYERS)
    if unknown:
        p.error(f"unknown layers {sorted(unknown)}")
    if a.step == "pilot":
        pilot(a.out)
    elif a.step == "build":
        build(a.out, a.layers)
    else:
        verify(a.out)


if __name__ == "__main__":
    main()
