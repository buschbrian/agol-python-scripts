r"""Build the ArcGIS Online styling definitions for the Millcreek LiDAR layers (October 23, 2026).

    python reviews/2026-10-23/agol-styling/build_definitions.py

Standard library only. Reads the hosted services' own styles in originals/ and writes every definition that
apply_styling.py sends:
- styles/<layer>.json: the item resource styles/root.json of each vector tile layer (its layer-level default style);
- layers/<item>.json: item data (layer drawing and pop-ups) for the feature service and the scene service, and the
  service drawingInfo of each feature layer;
- maps/<name>.json: the three web maps and the web scene, each with its item properties.
Change the constants here and rebuild; apply_styling.py only reads the JSON, so the JSON in the repo is what goes online.
"""
import copy
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORIGINALS, STYLES, LAYERS, MAPS = (HERE/n for n in ("originals", "styles", "layers", "maps"))
CREATED = HERE/"created.json"   # the map and scene IDs apply_styling.py recorded (the scene's slide thumbnails use it)

PORTAL = "https://www.arcgis.com/sharing/rest"
TILES = "https://tiles.arcgis.com/tiles/XRrSFvEwSsReIxuA/arcgis/rest/services/"
FEATURES = ("https://services9.arcgis.com/XRrSFvEwSsReIxuA/arcgis/rest/services/"
            "Millcreek_buildings_and_canopy_cover_zones_2023_lidar_planning_estimate/FeatureServer")
ITEMS = {
    "features": {"id": "d5effaee6c66497eaeb64e4c2e0f496e", "url": FEATURES},
    "slope": {"id": "3b5b1a9110f14e93af68752be89e0df2",
              "url": TILES + "Millcreek_slope_classes_0_5_m_2023_lidar_planning_estimate/VectorTileServer"},
    "contours": {"id": "50573eeba93f405a869a1d78a08d68e8",
                 "url": TILES + "Millcreek_2_m_contours_2023_lidar_planning_estimate/VectorTileServer"},
    "treetops": {"id": "924b993cb23046cb87641253bcf786de",
                 "url": TILES + "Millcreek_treetops_2023_lidar_planning_estimate/VectorTileServer"},
    "crowns": {"id": "d9388dc83f894edbb63e0510a8c62fa8",
               "url": TILES + "Millcreek_tree_crowns_2023_lidar_planning_estimate/VectorTileServer"},
    "hillshade": {"id": "cab8824e44384d479e1f302cdf34daf9",
                  "url": TILES + "Millcreek_hillshade_0_5_m_2023_lidar_planning_estimate/MapServer"},
    "buildings3d": {"id": "5082b5bd063a4a03847f2082dc3533d1",
                    "url": TILES + "Millcreek_3D_buildings_LOD1_2_2023_lidar_planning_estimate/SceneServer"},
    "terrain": {"id": "ce1680a5196e458ebfb60ead5150b946",
                "url": TILES + "Millcreek_bare_earth_terrain_0_5_m_2023_lidar_planning_estimate/ImageServer"},
}
WARNING = ("Unvalidated LiDAR planning estimates from the 2023 Salt Lake Valley QL1 lidar (flown October-November 2023); "
           "not surveyed or field-verified data.")
# Written as ArcGIS Online stores it (it rewrites <br> and double-quoted attributes), so the read-back compares equal.
FOOTNOTE = ("<p style='font-size:11px;color:#6b6b6b'>Unvalidated lidar planning estimate (2023 Salt Lake Valley QL1 "
            "lidar); not surveyed or field-verified.</p>")
WEB_MERCATOR = {"wkid": 102100, "latestWkid": 3857}
# The services' full extent (Web Mercator), the hillshade's, which holds every other layer.
CITY = {"xmin": -12459067.21, "ymin": 4962105.56, "xmax": -12442851.81, "ymax": 4970359.57,
        "spatialReference": WEB_MERCATOR}
# Neighbourhoods, from the World Geocoding Service on October 23 (not stored): lon, lat, ground elevation (m, rough).
PLACES = {
    "Millcreek Common (city centre)": (-111.85236, 40.70112, 1335),
    "Canyon Rim": (-111.80611, 40.70392, 1400),
    "Evergreen and East Millcreek": (-111.82698, 40.69597, 1385),
    "Olympus Cove foothills": (-111.78600, 40.68400, 1500),
    "Scott Avenue (west Millcreek)": (-111.86687, 40.69561, 1310),
}


# ---------------------------------------------------------------- vector tile styles (layer-level defaults)

def rgba(hex_colour, alpha):
    h = hex_colour.lstrip("#")
    return "rgba({},{},{},{})".format(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), alpha)


def tile_style(name, paints, layouts=None, minzooms=None):
    """The service's style with absolute URLs (it is served from the item, not the service) and new paint."""
    style = json.loads((ORIGINALS/f"{name}_service_style.json").read_text())
    url = ITEMS[name]["url"]
    style["sources"]["esri"]["url"] = url
    style["sprite"] = url + "/resources/sprites/sprite"
    style["glyphs"] = url + "/resources/fonts/{fontstack}/{range}.pbf"
    ids = [layer["id"] for layer in style["layers"]]
    if sorted(ids) != sorted(paints):
        raise ValueError(f"{name}: style layers {ids} do not match {list(paints)}")
    for layer in style["layers"]:
        layer["paint"] = paints[layer["id"]]
        if layouts and layer["id"] in layouts:
            layer["layout"] = layouts[layer["id"]]
        if minzooms and layer["id"] in minzooms:
            layer["minzoom"] = minzooms[layer["id"]]
    return style


# Slope: YlOrRd kept, deepened at the steep end; flat ground nearly clear so imagery and hillshade show through.
SLOPE = [("Under 10%", "#FFFFCC", 0.15), ("10% to 15%", "#FED976", 0.45), ("15% to 20%", "#FEB24C", 0.5),
         ("20% to 25%", "#FD8D3C", 0.55), ("25% to 30%", "#F03B20", 0.6), ("30% and over", "#BD0026", 0.62)]
# Treetops and crowns: YlGn by treetop height class; the lightest step is darker than the service's #FFFFCC so it
# shows on imagery. Treetop radius (px at level 17) grows with the class.
HEIGHTS = [("2 to 5 m", "#D9F0A3", 2.0), ("5 to 10 m", "#ADDD8E", 2.8), ("10 to 15 m", "#78C679", 3.6),
           ("15 to 20 m", "#31A354", 4.4), ("20 m and over", "#006837", 5.2)]


def styles():
    out = {"slope": tile_style("slope", {
        f"Slope classes/{label}/1": {"fill-color": colour, "fill-opacity": alpha,
                                     "fill-outline-color": rgba(colour, alpha)}
        for label, colour, alpha in SLOPE})}
    out["contours"] = tile_style("contours", {
        "Contours (2 m)": {"line-color": "#5A3A1A",
                           "line-opacity": {"stops": [[14, 0.3], [16, 0.5]]},
                           "line-width": {"stops": [[14, 0.5], [16, 0.7], [17, 0.8]]}},
        "Index contours (10 m)": {"line-color": "#3D2610", "line-opacity": 0.85,
                                  "line-width": {"stops": [[10, 0.9], [13, 1.3], [15, 1.6], [17, 2.0]]}},
    }, layouts={i: {"line-join": "round", "line-cap": "round"} for i in ("Contours (2 m)", "Index contours (10 m)")})
    out["treetops"] = tile_style("treetops", {
        f"Treetops by height/{label}": {
            "circle-color": colour,
            "circle-radius": {"stops": [[14, round(r*0.5, 2)], [16, round(r*0.8, 2)], [17, r], [19, round(r*1.4, 2)]]},
            "circle-stroke-color": "rgba(20,45,25,0.8)",
            "circle-stroke-width": {"stops": [[14, 0.3], [17, 0.6]]}}
        for label, colour, r in HEIGHTS})
    out["crowns"] = tile_style("crowns", {
        f"Crowns by treetop height/{label}": {"fill-color": colour, "fill-opacity": 0.5,
                                              "fill-outline-color": "rgba(0,68,27,0.85)"}
        for label, colour, _ in HEIGHTS})
    return out


# ---------------------------------------------------------------- feature layers: renderers and pop-ups

def fill(rgb, alpha=255, outline=(70, 70, 70, 140), width=0.4):
    return {"type": "esriSFS", "style": "esriSFSSolid", "color": [*rgb, alpha],
            "outline": {"type": "esriSLS", "style": "esriSLSSolid", "color": list(outline), "width": width}}


# Building median roof height classes (m, ft); breaks at roughly one, two and three storeys.
BUILDING_CLASSES = [(4, "Under 4 m (13 ft)", (242, 240, 247)), (6, "4 to 6 m (13 to 20 ft)", (203, 201, 226)),
                    (9, "6 to 9 m (20 to 30 ft)", (158, 154, 200)), (12, "9 to 12 m (30 to 39 ft)", (117, 107, 177)),
                    (60, "12 m (39 ft) and over", (84, 39, 143))]
NO_HEIGHT = "No lidar height (no roof points)"


def building_renderer():
    return {"type": "classBreaks", "field": "HEIGHT_P50_M", "classificationMethod": "esriClassifyManual",
            "minValue": 0,
            "classBreakInfos": [{"classMaxValue": top, "label": label, "symbol": fill(rgb, 255, (60, 60, 90, 70), 0.3)}
                                for top, label, rgb in BUILDING_CLASSES],
            "defaultLabel": NO_HEIGHT,
            "defaultSymbol": fill((215, 215, 215), 200, (120, 120, 120, 200), 0.6)}


FLAG_WORDS = {
    "LOW_ROOF_SUPPORT": "Lidar roof points cover less than 80% of the footprint, so the height is less certain.",
    "NO_ROOF_SUPPORT": "No lidar roof points fall inside the footprint, so no height was estimated.",
    "NO_CELL_CENTERS": "The footprint is too small to hold a 0.5 m cell centre, so no height was estimated.",
    "NEGATIVE_HEIGHT": "Some roof cells sit below the ground surface; the footprint may not match the building.",
    "PARTIAL_AOI": "Part of the footprint lies outside the lidar coverage.",
    "GEOMETRY_REPAIRED": "The county footprint's shape was repaired before measuring.",
}


def flags_expression():
    pairs = ", ".join(f"{json.dumps(k)}, {json.dumps(v)}" for k, v in FLAG_WORDS.items())
    return ("var words = Dictionary(" + pairs + ");\n"
            "var parts = Split(DefaultValue($feature.HEIGHT_STATUS, ''), ';');\n"
            "var out = [];\n"
            "for (var i in parts) { if (HasKey(words, parts[i])) { Push(out, words[parts[i]]); } }\n"
            "return IIf(Count(out) == 0, 'None beyond the estimate warning.', Concatenate(out, ' '));")


def height_expression(metres, feet=None):
    ft = f"$feature.{feet}" if feet else f"$feature.{metres} * 3.28084"
    return (f"var m = $feature.{metres};\n"
            "if (IsEmpty(m)) { return 'no estimate'; }\n"
            f"return Text(m, '#,##0.0') + ' m (' + Text({ft}, '#,##0') + ' ft)';")


SUPPORT = ("var c = $feature.ROOF_COV_PCT;\n"
           "if (IsEmpty(c)) { return 'none'; }\n"
           "return Text(c, '#,##0') + '% of the footprint\\'s 0.5 m cells have lidar roof points';")


def building_popup(feet_fields=True):
    expressions = [
        {"name": "h50", "title": "Median roof height",
         "expression": height_expression("HEIGHT_P50_M", "HEIGHT_P50_FT" if feet_fields else None),
         "returnType": "string"},
        {"name": "h95", "title": "95th percentile roof height",
         "expression": height_expression("HEIGHT_P95_M", "HEIGHT_P95_FT" if feet_fields else None),
         "returnType": "string"},
        {"name": "support", "title": "Roof support", "expression": SUPPORT, "returnType": "string"},
        {"name": "flags", "title": "Notes", "expression": flags_expression(), "returnType": "string"},
        {"name": "area", "title": "Footprint",
         "expression": "var a = $feature.FOOTPRINT_M2;\nif (IsEmpty(a)) { return 'unknown'; }\n"
                       "return Text(a, '#,##0') + ' m² (' + Text(a * 10.7639, '#,##0') + ' ft²)';",
         "returnType": "string"},
    ]
    text = ("<p><b>Roof height above the ground</b><br />Median: {expression/h50}<br />"
            "95th percentile: {expression/h95}</p>"
            "<p><b>Roof support:</b> {expression/support}.</p>"
            "<p><b>Notes:</b> {expression/flags}</p>"
            "<p>Footprint {expression/area}. Parcel {PARCEL_ID}. County building ID {SOURCE_ID}.</p>" + FOOTNOTE)
    return {"title": "Building {SOURCE_ID}", "expressionInfos": expressions,
            "popupElements": [{"type": "text", "text": text}],
            "fieldInfos": [{"fieldName": f, "visible": False, "isEditable": False} for f in ("PARCEL_ID", "SOURCE_ID")]
                          + [{"fieldName": f"expression/{e['name']}", "visible": True, "isEditable": False}
                             for e in expressions]}


# Canopy cover zones come in three nested tiers: the whole city; four ownership zones (private, public / government,
# uncertain owner, no parcel); and the eight public owners, which make up the public / government zone exactly
# (838.9 acres). The renderer draws the finest non-overlapping tier only: everything except the city and the
# public / government total, which return null and so draw nothing.
ZONE_SKIP = ("CITY", "OWNERSHIP:PUBLIC_GOVERNMENT")
ZONE_CLASSES = [(10, "Under 10%", (247, 252, 185)), (20, "10% to 20%", (173, 221, 142)),
                (30, "20% to 30%", (65, 171, 93)), (100, "30% and over", (0, 90, 50))]


def zone_renderer():
    skip = " || ".join(f"z == '{z}'" for z in ZONE_SKIP)
    return {"type": "classBreaks", "classificationMethod": "esriClassifyManual", "minValue": 0,
            "valueExpression": f"var z = $feature.ZONE_ID;\nif ({skip}) {{ return null; }}\nreturn $feature.CANOPY_PCT;",
            "valueExpressionTitle": "Canopy cover (% of the area the lidar observed)",
            "classBreakInfos": [{"classMaxValue": top, "label": label,
                                 "symbol": fill(rgb, 210, (255, 255, 255, 160), 0.5)}
                                for top, label, rgb in ZONE_CLASSES]}


def zone_popup():
    expressions = [
        {"name": "pct", "title": "Canopy cover", "returnType": "string",
         "expression": "return Text($feature.CANOPY_PCT, '#0.0') + '%';"},
        {"name": "bounds", "title": "Bounds", "returnType": "string",
         "expression": "return Text($feature.CANOPY_LOW_PCT, '#0.0') + '% to ' + "
                       "Text($feature.CANOPY_HIGH_PCT, '#0.0') + '%';"},
        {"name": "change", "title": "Against October 19", "returnType": "string",
         "expression": "var d = $feature.CANOPY_PCT - $feature.CANOPY_PCT_OCT19;\n"
                       "if (Abs(d) < 0.005) { return 'The same as'; }\n"
                       "return Text(Abs(d), '0.00') + ' points ' + IIf(d < 0, 'below', 'above');"},
    ]
    text = ("<p><b>Canopy cover {expression/pct}</b> of the area the lidar observed "
            "(bounds {expression/bounds}).</p>"
            "<p>About {CANOPY_ACRES} acres of tree canopy in {ZONE_ACRES} acres. The whole city: 25.59%.</p>"
            "<p>{expression/change} the October 19 estimate of {CANOPY_PCT_OCT19}%, which came from the earlier "
            "classification; the October 22 figure above is the current one.</p>"
            "<p>The lidar observed {OBSERVED_PCT}% of the zone; the bounds count the unobserved part as no canopy or "
            "as all canopy. Canopy is vegetation at least 2 m tall.</p>" + FOOTNOTE)
    fmt = {"CANOPY_ACRES": 1, "ZONE_ACRES": 1, "OBSERVED_PCT": 1, "CANOPY_PCT_OCT19": 2}
    expressions.append({"name": "title", "title": "Zone", "returnType": "string",
                        "expression": "var n = $feature.ZONE_NAME;\n"
                                      "return IIf(Left($feature.ZONE_ID, 7) == 'PUBLIC:', 'Public owner: ' + n, n);"})
    return {"title": "{expression/title}", "expressionInfos": expressions,
            "popupElements": [{"type": "text", "text": text}],
            "fieldInfos": [{"fieldName": f, "visible": False, "isEditable": False,
                            "format": {"places": p, "digitSeparator": True}} for f, p in fmt.items()]
                          + [{"fieldName": f"expression/{e['name']}", "visible": True, "isEditable": False}
                             for e in expressions]}


BUILDINGS_MIN_SCALE = 150000


def feature_item_data():
    return {"layers": [
        {"id": 0, "layerDefinition": {"drawingInfo": {"renderer": building_renderer(), "transparency": 0,
                                                      "labelingInfo": None},
                                      "minScale": BUILDINGS_MIN_SCALE, "maxScale": 0},
         "popupInfo": building_popup()},
        {"id": 1, "layerDefinition": {"drawingInfo": {"renderer": zone_renderer(), "transparency": 0,
                                                      "labelingInfo": None}},
         "popupInfo": zone_popup()},
    ]}


# ---------------------------------------------------------------- scene layer

def mesh(rgb, edge=True):
    layer = {"type": "Fill", "material": {"color": list(rgb), "colorMixMode": "replace"}}
    if edge:
        layer["edges"] = {"type": "solid", "color": [70, 70, 70], "size": 0.5, "transparency": 35}
    return {"type": "MeshSymbol3D", "symbolLayers": [layer]}


# The 3D blocks in near-white to mid grey, taller darker, as Esri's 3D basemaps draw buildings: the scene's sun and
# shadows give the form, and the edges the outlines. The breaks and labels are the 2D map's (BUILDING_CLASSES).
SCENE_GREYS = [(247, 246, 242), (233, 231, 226), (216, 214, 209), (196, 194, 190), (172, 170, 167)]
SCENE_NO_HEIGHT = (232, 220, 200)   # pale sand, so a block without a lidar height still stands out


def scene_renderer():
    return {"type": "classBreaks", "field": "HEIGHT_P50_M", "classificationMethod": "esriClassifyManual",
            "minValue": 0,
            "classBreakInfos": [{"classMaxValue": top, "label": label, "symbol": mesh(grey)}
                                for (top, label, _), grey in zip(BUILDING_CLASSES, SCENE_GREYS)],
            "defaultLabel": NO_HEIGHT, "defaultSymbol": mesh(SCENE_NO_HEIGHT),
            "legendOptions": {"title": "Median roof height above the ground"}}


def scene_item_data():
    return {"layers": [{"id": 0, "layerDefinition": {"drawingInfo": {"renderer": scene_renderer()}},
                        "popupInfo": building_popup(feet_fields=False)}]}


# ---------------------------------------------------------------- web maps

def lonlat_to_wm(lon, lat):
    r = 6378137.0
    return r*math.radians(lon), r*math.log(math.tan(math.pi/4 + math.radians(lat)/2))


def wm_to_lonlat(x, y):
    r = 6378137.0
    return math.degrees(x/r), math.degrees(2*math.atan(math.exp(y/r)) - math.pi/2)


def around(lon, lat, half_m=900):
    x, y = lonlat_to_wm(lon, lat)
    k = half_m/math.cos(math.radians(lat))   # Web Mercator units per ground metre at this latitude
    return {"xmin": round(x - k, 1), "ymin": round(y - k*0.6, 1), "xmax": round(x + k, 1), "ymax": round(y + k*0.6, 1),
            "spatialReference": WEB_MERCATOR}


def bookmarks():
    marks = [{"name": "Whole city", "extent": CITY, "viewpoint": {"targetGeometry": CITY}}]
    for name, (lon, lat, _) in PLACES.items():
        e = around(lon, lat)
        marks.append({"name": name, "extent": e, "viewpoint": {"targetGeometry": e}})
    return marks


def item_style_url(name):
    return f"{PORTAL}/content/items/{ITEMS[name]['id']}/resources/styles/root.json"


def vector_layer(name, title, min_scale, max_scale=0, visible=True):
    return {"id": name, "title": title, "layerType": "VectorTileLayer", "itemId": ITEMS[name]["id"],
            "styleUrl": item_style_url(name), "visibility": visible, "opacity": 1,
            "minScale": min_scale, "maxScale": max_scale}


def colour_list(hex_colour, alpha=1):
    h = hex_colour.lstrip("#")
    return [int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), round(alpha*255)]


def key_layer(name, title, geometry, rows, min_scale, max_scale=0):
    """A legend-only layer: an empty feature collection whose class renderer gives the Legend (Map Viewer's and the
    apps') the entries it cannot read from a vector tile style. It lives in the map, so there is no item to share."""
    renderer = {"type": "uniqueValue", "field1": "CLASS",
                "uniqueValueInfos": [{"value": label, "label": label, "symbol": symbol} for label, symbol in rows]}
    definition = {"name": title, "type": "Feature Layer", "geometryType": geometry, "objectIdField": "OBJECTID",
                  "fields": [{"name": "OBJECTID", "type": "esriFieldTypeOID", "alias": "OBJECTID"},
                             {"name": "CLASS", "type": "esriFieldTypeString", "alias": "Class", "length": 40}],
                  "drawingInfo": {"renderer": renderer}, "extent": CITY}
    return {"id": f"{name}-key", "title": title, "layerType": "ArcGISFeatureLayer", "visibility": True, "opacity": 1,
            "minScale": min_scale, "maxScale": max_scale,
            "featureCollection": {"layers": [{"layerDefinition": definition,
                                              "featureSet": {"geometryType": geometry, "features": []}}],
                                  "showLegend": True}}


def keyed(tiles, key):
    """The vector tile layer and its key as one entry in the layer list (one switch for both)."""
    tiles = dict(tiles, showLegend=False)
    return {"id": f"{tiles['id']}-group", "title": tiles["title"], "layerType": "GroupLayer", "visibility": True,
            "opacity": 1, "listMode": "hide-children", "layers": [tiles, key]}


def no_outline():
    return {"type": "esriSLS", "style": "esriSLSNull", "color": [0, 0, 0, 0], "width": 0}


# The keys repeat the item styles (styles()): style pixels to symbol points at 0.75, treetop sizes as at level 17.
def slope_key():
    return key_layer("slope", "Slope classes", "esriGeometryPolygon",
                     [(label, {"type": "esriSFS", "style": "esriSFSSolid", "color": colour_list(colour, alpha),
                               "outline": no_outline()}) for label, colour, alpha in SLOPE], 0)


def contour_key(min_scale):
    def line(colour, alpha, px):
        return {"type": "esriSLS", "style": "esriSLSSolid", "color": colour_list(colour, alpha), "width": round(px*0.75, 2)}
    return key_layer("contours", "Contour lines", "esriGeometryPolyline",
                     [("10 m index contour", line("#3D2610", 0.85, 1.6)),
                      ("2 m contour", line("#5A3A1A", 0.5, 0.7))], min_scale)


def treetop_key(min_scale):
    return key_layer("treetops", "Treetop height", "esriGeometryPoint",
                     [(label, {"type": "esriSMS", "style": "esriSMSCircle", "color": colour_list(colour),
                               "size": round(2*r*0.75, 2),
                               "outline": {"type": "esriSLS", "style": "esriSLSSolid", "color": [20, 45, 25, 204],
                                           "width": 0.45}}) for label, colour, r in HEIGHTS], min_scale)


def crown_key(min_scale):
    return key_layer("crowns", "Crowns by treetop height", "esriGeometryPolygon",
                     [(label, {"type": "esriSFS", "style": "esriSFSSolid", "color": colour_list(colour, 0.5),
                               "outline": {"type": "esriSLS", "style": "esriSLSSolid", "color": [0, 68, 27, 217],
                                           "width": 0.75}}) for label, colour, _ in HEIGHTS], min_scale)


def hillshade_layer(opacity, blend=None, brightness=None):
    """The hillshade blended over what lies below it. Brightness lifts flat ground (about 180 of 255) towards white, so a
    multiply blend shades slopes without greying the whole city."""
    layer = {"id": "hillshade", "title": "Hillshade (0.5 m lidar terrain)", "layerType": "ArcGISTiledMapServiceLayer",
             "url": ITEMS["hillshade"]["url"], "itemId": ITEMS["hillshade"]["id"], "visibility": True,
             "opacity": opacity, "showLegend": False, "minScale": 300000, "maxScale": 0}
    if blend:
        layer["blendMode"] = blend
    if brightness:
        layer["effect"] = [{"type": "brightness", "amount": brightness}]
    return layer


def feature_layer(layer_id, name, title, data, min_scale=0, max_scale=0, opacity=1):
    definition = copy.deepcopy(data["layerDefinition"])
    definition.update(minScale=min_scale, maxScale=max_scale)
    return {"id": name, "title": title, "layerType": "ArcGISFeatureLayer", "url": f"{FEATURES}/{layer_id}",
            "itemId": ITEMS["features"]["id"], "visibility": True, "opacity": opacity,
            "minScale": min_scale, "maxScale": max_scale, "layerDefinition": definition,
            "popupInfo": copy.deepcopy(data["popupInfo"])}


def basemap(kind):
    if kind == "light":
        return {"title": "Light Gray Canvas", "baseMapLayers": [
            {"id": "light-gray-base", "title": "Light Gray Base", "layerType": "VectorTileLayer",
             "styleUrl": "https://cdn.arcgis.com/sharing/rest/content/items/291da5eab3a0412593b66d384379f89f/"
                         "resources/styles/root.json", "visibility": True, "opacity": 1},
            {"id": "light-gray-reference", "title": "Light Gray Reference", "layerType": "VectorTileLayer",
             "isReference": True,
             "styleUrl": "https://cdn.arcgis.com/sharing/rest/content/items/1768e8369a214dfab4e2167d5c5f2454/"
                         "resources/styles/root.json", "visibility": True, "opacity": 1}]}
    return {"title": "Imagery Hybrid", "baseMapLayers": [
        {"id": "world-imagery", "title": "World Imagery", "layerType": "ArcGISTiledMapServiceLayer",
         "url": "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer",
         "visibility": True, "opacity": 1, "showLegend": False},
        {"id": "hybrid-reference", "title": "Hybrid Reference Layer", "layerType": "VectorTileLayer",
         "isReference": True,
         "styleUrl": "https://cdn.arcgis.com/sharing/rest/content/items/30d6b8271e1849cd9c3042060001f425/"
                     "resources/styles/root.json", "visibility": True, "opacity": 1}]}


def wgs_extent():
    (x0, y0), (x1, y1) = wm_to_lonlat(CITY["xmin"], CITY["ymin"]), wm_to_lonlat(CITY["xmax"], CITY["ymax"])
    return [[round(x0, 5), round(y0, 5)], [round(x1, 5), round(y1, 5)]]


def description(lines):
    return (f"<p><b>{WARNING}</b></p>" + "".join(f"<p>{line}</p>" for line in lines) +
            "<p>Datum: NAD83(2011) taken to WGS84 / Web Mercator with WGS_1984_(ITRF08)_To_NAD_1983_2011, the same "
            "for every layer. Records: canopy-toolbox/reviews/2026-10-23/agol-styling in "
            "buschbrian/agol-python-scripts.</p>")


def key(title, rows):
    """A class key for a vector tile layer in the map description, beside the key layers in the legend."""
    swatches = " &nbsp; ".join(f"<span style='color:{colour}'>■</span> {label}" for label, colour in rows)
    return f"<b>{title}:</b> {swatches}"


SLOPE_KEY = key("Slope classes", [(label, colour) for label, colour, _ in SLOPE])
CONTOUR_KEY = ("<b>Contours:</b> <span style='color:#3D2610'>▬</span> 10 m index (heavy) &nbsp; "
               "<span style='color:#5A3A1A'>─</span> 2 m (thin), elevations in metres (NAVD88); the tiles "
               "carry no elevation values, so the lines are unlabelled")
HEIGHT_KEY = key("Treetop height (crowns and treetops)", [(label, colour) for label, colour, _ in HEIGHTS])

TAGS = ["Millcreek", "lidar", "2023", "planning estimate"]


def web_map(title, snippet, lines, tags, base, layers):
    return {"item": {"title": title, "type": "Web Map", "snippet": f"{snippet} {WARNING}",
                     "description": description(lines), "tags": TAGS + tags,
                     "typeKeywords": ["ArcGIS Online", "Explorer Web Map", "Map", "Online Map", "Web Map"],
                     "extent": wgs_extent(), "accessInformation": "Millcreek GIS; 2023 Salt Lake Valley QL1 lidar"},
            "data": {"operationalLayers": layers, "baseMap": basemap(base), "spatialReference": WEB_MERCATOR,
                     "initialState": {"viewpoint": {"targetGeometry": CITY}}, "bookmarks": bookmarks(),
                     "authoringApp": "apply_styling.py (ArcGIS API for Python)", "authoringAppVersion": "2.4.3",
                     "version": "2.31"}}


def web_maps(data):
    buildings, zones = data["layers"]
    return {
        "terrain-and-slope": web_map(
            "Millcreek terrain and slope", "Slope classes, 2 m contours and hillshade from the 0.5 m lidar terrain.",
            ["Slope in six classes from the 0.5 m bare-earth terrain (3 m neighbourhood, 4 m² minimum mapping "
             "unit), shaded by the lidar hillshade blended over it (multiply), with 2 m contours (10 m index lines "
             "heavier) from 1:288,000 inward and the 2 m lines from 1:18,000.",
             SLOPE_KEY, CONTOUR_KEY,
             "Slope and contours are vector tiles: they draw but have no pop-ups. The legend cannot read a vector "
             "tile style, so each is grouped with a small key layer that carries its classes into the legend."],
            ["slope", "terrain", "contours", "hillshade"], "light",
            [keyed(vector_layer("slope", "Slope (percent)", 0), slope_key()),
             hillshade_layer(0.9, "multiply", 1.3),
             keyed(vector_layer("contours", "Contours (2 m, 10 m index)", 288895), contour_key(288895))]),
        "tree-canopy": web_map(
            "Millcreek tree canopy",
            "Canopy cover by ownership zone, and lidar tree crowns and treetops by height, over imagery.",
            ["At city scale: canopy cover (vegetation at least 2 m tall, as a share of the area the lidar observed) "
             "for each ownership zone; click a zone for its figure, bounds and the October 19 comparison. "
             "Zoom in past 1:20,000 for the tree crowns and, from 1:10,000, the treetops, coloured and sized by "
             "treetop height. The lidar hillshade is blended over the imagery (soft light).",
             "Treetops and crowns are unvalidated automatic detections; about 6% of treetops carry an unreviewed "
             "SUSPECT flag.", HEIGHT_KEY + "; larger treetop dots are taller trees.",
             "Crowns and treetops are vector tiles: they draw but have no pop-ups. The legend cannot read a vector "
             "tile style, so each is grouped with a small key layer that carries its classes into the legend."],
            ["canopy", "tree canopy", "trees", "treetops", "crowns"], "imagery",
            [hillshade_layer(0.5, "soft-light"),
             feature_layer(1, "canopy-zones", "Canopy cover by ownership zone", zones, 0, 20000, 0.85),
             keyed(vector_layer("crowns", "Tree crowns by treetop height", 18056), crown_key(18056)),
             keyed(vector_layer("treetops", "Treetops by height", 10000), treetop_key(10000))]),
        "buildings": web_map(
            "Millcreek buildings", "County building footprints coloured by lidar roof height, over the hillshade.",
            ["22,042 county footprints coloured by median roof height above the ground (October 22 consensus roofs); "
             "grey where the lidar saw no roof. Click a building for its median and 95th percentile heights in "
             "metres and feet, the share of the footprint with lidar roof points, and any flags in plain words. "
             "Buildings draw from 1:150,000 inward."],
            ["buildings", "building height"], "light",
            [hillshade_layer(0.9, "multiply", 1.4),
             feature_layer(0, "buildings", "Building height (median roof)", buildings, BUILDINGS_MIN_SCALE)]),
    }


# ---------------------------------------------------------------- web scene

def camera(lon, lat, ground, heading, tilt, distance):
    """A camera `distance` metres from a target on the ground, looking along `heading` with `tilt` (0 = straight down)."""
    h, t = math.radians(heading), math.radians(tilt)
    across = distance*math.sin(t)
    dlon = -across*math.sin(h)/(111320*math.cos(math.radians(lat)))
    dlat = -across*math.cos(h)/110574
    x, y = lonlat_to_wm(lon + dlon, lat + dlat)
    return {"position": {"x": round(x, 2), "y": round(y, 2), "z": round(ground + distance*math.cos(t), 1),
                         "spatialReference": WEB_MERCATOR}, "heading": heading, "tilt": tilt}


ENVIRONMENT = {"lighting": {"type": "sun", "datetime": 1697389200000, "directShadows": True,
                            "displayUTCOffset": -6},   # October 15, 2023, 11:00 MDT
               "atmosphereEnabled": True, "starsEnabled": False}
SLIDES = [("Millcreek and the Wasatch", (-111.845, 40.690, 1350), 80, 64, 7500),
          ("Millcreek Common", PLACES["Millcreek Common (city centre)"], 60, 62, 900),
          ("Canyon Rim", PLACES["Canyon Rim"], 100, 64, 1000),
          ("Olympus Cove foothills", PLACES["Olympus Cove foothills"], 110, 66, 1400)]


# Esri's OpenStreetMap 3D layers, as its Topographic 3D basemap uses them (public). Its trees layer
# (OpenStreetMap3D_Trees_Thematic_v1) is left out: OpenStreetMap maps no trees in Millcreek, so it drew none at any slide
# or at 1:1,500 over Canyon Rim Park (October 23).
BASEMAPS3D = "https://basemaps3d.arcgis.com/arcgis/rest/services/"


def osm_scene_layer(layer_id, title, service):
    return {"id": layer_id, "title": title, "layerType": "ArcGISSceneServiceLayer",
            "url": f"{BASEMAPS3D}{service}/SceneServer/layers/0", "visibility": True, "opacity": 1, "showLegend": False}


def slide_thumbnail(slide_id):
    """The slide's picture, an item resource of the scene (apply_styling.py thumbnails sends it)."""
    scene = json.loads(CREATED.read_text()).get("in-3d", {}).get("id") if CREATED.exists() else None
    return {"url": f"{PORTAL}/content/items/{scene}/resources/slides/{slide_id}.jpg"} if scene else None


def web_scene(data):
    layers = [
        {"id": "hillshade", "title": "Hillshade (0.5 m lidar terrain)", "layerType": "ArcGISTiledMapServiceLayer",
         "url": ITEMS["hillshade"]["url"], "itemId": ITEMS["hillshade"]["id"], "visibility": True, "opacity": 0.4,
         "showLegend": False},
        {"id": "buildings3d", "title": "Buildings by median roof height (LOD1.2)", "layerType": "ArcGISSceneServiceLayer",
         "url": ITEMS["buildings3d"]["url"] + "/layers/0", "itemId": ITEMS["buildings3d"]["id"], "visibility": True,
         "opacity": 1, "layerDefinition": copy.deepcopy(data["layers"][0]["layerDefinition"]),
         "popupInfo": copy.deepcopy(data["layers"][0]["popupInfo"])},
        osm_scene_layer("osm-labels", "Place labels (OpenStreetMap)", "OpenStreetMap3D_DarkLabels_v1"),
    ]
    base = basemap("light")
    # The 3D labels replace the basemap's draped reference labels.
    base["baseMapLayers"] = [layer for layer in base["baseMapLayers"] if not layer.get("isReference")]
    ground = {"layers": [
        {"id": "world-elevation", "title": "Terrain3D", "listMode": "hide", "layerType": "ArcGISTiledElevationServiceLayer",
         "url": "https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer",
         "itemId": "7029fb60158543ad845c7e1527af11e4", "visibility": True},
        {"id": "millcreek-terrain", "title": "Millcreek bare-earth terrain (0.5 m lidar)",
         "layerType": "ArcGISTiledElevationServiceLayer", "url": ITEMS["terrain"]["url"],
         "itemId": ITEMS["terrain"]["id"], "visibility": True}],
        "transparency": 0, "navigationConstraint": {"type": "stayAbove"}}
    slides = [{"id": f"slide_{i}", "title": {"text": title}, "thumbnail": slide_thumbnail(f"slide_{i}"),
               "viewpoint": {"camera": camera(lon, lat, z, heading, tilt, dist)},
               "baseMap": base, "ground": {"transparency": 0}, "environment": ENVIRONMENT,
               "visibleLayers": [{"id": layer["id"]} for layer in layers] + [{"id": g["id"]} for g in ground["layers"]]}
              for i, (title, (lon, lat, z), heading, tilt, dist) in enumerate(SLIDES, 1)]
    return {"item": {"title": "Millcreek in 3D", "type": "Web Scene",
                     "snippet": "Lidar building blocks shaded by roof height on the 0.5 m lidar terrain. " + WARNING,
                     "description": description([
                         "The 0.5 m lidar bare-earth terrain in the ground (above Esri's World Elevation), the "
                         "LOD1.2 building blocks shaded light to darker grey by median roof height, with edges (click "
                         "one for its heights and flags), and the lidar hillshade draped on the ground. Slides show "
                         "four parts of the city.",
                         "Place labels are Esri's OpenStreetMap 3D labels (map data © OpenStreetMap contributors).",
                         "Trees are not in the scene: the lidar treetops are vector tiles without heights, which can "
                         "only lie flat on the ground, and OpenStreetMap maps no trees in Millcreek. 3D trees need the "
                         "lidar treetops as a hosted point layer with their heights."]),
                     "tags": TAGS + ["3D", "buildings", "terrain", "scene"],
                     "typeKeywords": ["ArcGIS Online", "Web Scene", "ViewingMode-Global"],
                     "extent": wgs_extent(),
                     "accessInformation": "Millcreek GIS; 2023 Salt Lake Valley QL1 lidar; place labels © "
                                          "OpenStreetMap contributors, scene layer by Esri"},
            "data": {"operationalLayers": layers, "baseMap": base, "ground": ground,
                     "heightModelInfo": {"heightModel": "gravity_related_height", "heightUnit": "meter"},
                     "initialState": {"environment": ENVIRONMENT,
                                      "viewpoint": {"camera": slides[0]["viewpoint"]["camera"]}},
                     "presentation": {"slides": slides}, "spatialReference": WEB_MERCATOR,
                     "viewingMode": "global", "version": "1.29",
                     "authoringApp": "apply_styling.py (ArcGIS API for Python)", "authoringAppVersion": "2.4.3"}}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", path.relative_to(HERE))


def main():
    for name, style in styles().items():
        write(STYLES/f"{name}.json", style)
    data = feature_item_data()
    write(LAYERS/"features_item_data.json", data)
    for layer in data["layers"]:
        write(LAYERS/f"features_layer{layer['id']}_drawingInfo.json", layer["layerDefinition"]["drawingInfo"])
    scene = scene_item_data()
    write(LAYERS/"buildings3d_item_data.json", scene)
    for name, web in web_maps(data).items():
        write(MAPS/f"{name}.json", web)
    write(MAPS/"in-3d.json", web_scene(scene))


if __name__ == "__main__":
    main()
