"""
road_labels.py

Labels UGRC's Utah Roads (SGID Transportation.Roads) for a 1:30,000 map in
ArcGIS Pro:

  * Interstate, US and State Route shields. By default these are vector
    shields drawn from the MUTCD / UDOT sign designs (mutcd_shields.json,
    the Utah beehive for state routes) with the route number as live text in
    Bahnschrift SemiBold (semi-condensed for three digits), sized and placed
    by build_shields.py so it sits on the sign design's centre and clears the
    frame. There is one label class per network and digit count, 24 x 24 or
    30 x 24 in proportion, as on the signs. The route comes from DOT_HWYNAM,
    falling back to DOT_RTNAME and the alias names where UDOT left it blank.
  * Street names in Arcade label classes keyed on CARTOCODE, set in the
    Roadgeek 2014 FHWA Series ("Highway Gothic") fonts, sized and spaced for
    1:30,000, with Maplex connecting the many short segments of each street
    and thinning the duplicate names on divided highways.

--shields ddv uses Data Deja View's pre-numbered 2003 font shields instead,
one label class per route; routes newer than the DDV set get a stand-in
built from the DDV beehive outline.

Usage (ArcGIS Pro's Python; close the project in Pro first):

    python road_labels.py C:\\maps\\roads.aprx --layer Roads
    python road_labels.py C:\\maps\\roads.aprx --layer Roads --dry-run
    python road_labels.py C:\\maps\\roads.aprx --layer Roads --vtpk C:\\maps\\roads.vtpk

Or in Pro's Python window, with the project open:

    import road_labels
    road_labels.label_layer(arcpy.mp.ArcGISProject("CURRENT").activeMap.listLayers("Roads")[0])

The Roadgeek fonts must be installed first (once per Windows user, then
restart Pro). Unzip RG2014-3.10.zip (github.com/sammdot/roadgeek-fonts
releases), and for --shields ddv also UtahDDV.ZIP
(github.com/VerdantSkys/DDVs_ALL), then:

    python road_labels.py --install-fonts C:\\temp\\RG2014 [C:\\temp\\UtahDDV]

With --shields ddv, re-run after UGRC adds a route: its shield classes are
made for the routes the layer holds when the script runs.
"""

import argparse
import glob
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHIELD_DATA = os.path.join(HERE, "ddv_utah_shields.json")
MUTCD_DATA = os.path.join(HERE, "mutcd_shields.json")

# ------------------------------- Settings -------------------------------- #
REFERENCE_SCALE = 30000
SHIELD_STYLE = "mutcd"       # "mutcd" (vector sign designs) or "ddv" (2003 fonts)
SERIES = "ddvut10i"          # --shields ddv only: ddvut10i, 13i, 16i or 19i
US_WIDE_SHIELDS = False      # --shields ddv only: wider 3-digit US shields
TITLE_CASE = True            # "Van Winkle Expy" rather than "VANWINKLE EXPY"

# Roadgeek 2014 FHWA Series. Only a Regular style exists. Its capitals are
# 0.57 em tall against Source Sans 3's 0.66 and Arial's 0.72, so sizes here
# run about 1.16x the layout standard's Source Sans sizes.
SERIES_C = "Roadgeek 2014 Series C"
SERIES_D = "Roadgeek 2014 Series D"
SERIES_E = "Roadgeek 2014 Series E"
SHIELD_NUMBER_FONTS = {2: SERIES_D, 3: SERIES_C}   # by digit count (DDV stand-ins)

POINTS_PER_INCH = 72

# Shield height in points (MUTCD shields: the whole sign; DDV: the font
# marker, of which the drawn shield is about 70%), how often a route repeats
# (page inches at the reference scale) and the scale beyond which it hides.
SHIELDS = {
    "I": {"height": 17, "size": 24, "repeat_in": 5.0, "hide_beyond": 500000, "priority": 1},
    "US": {"height": 16, "size": 22, "repeat_in": 4.5, "hide_beyond": 250000, "priority": 2},
    "SR": {"height": 17.5, "size": 22, "repeat_in": 4.0, "hide_beyond": 150000, "priority": 3},
}

# Label colours from the Millcreek layout standard (millcreek-arcgis-layouts,
# docs/map-type-guide.md): ink #1F2933 for names, brown for unpaved roads.
INK = (31, 41, 51)
UNPAVED = (110, 84, 58)

# Name classes, highest priority first. CARTOCODE 1 (Interstates) is named
# by its shields; 7 (ramps), 12-15, 17, 18 and 99 are not labelled.
# Sizes follow the layout standard's 8 pt major / 7 pt local Source Sans,
# converted to Roadgeek, with its 1.0 / 0.75 pt halos. "fit" drops names
# longer than their street (cul-de-sacs, stubs) instead of letting them run
# past its ends.
NAME_CLASSES = [
    {"name": "Highway names", "cartocodes": ["2", "3", "4", "5", "6"],
     "font": SERIES_E, "size": 9.5, "color": INK, "halo": 1.0,
     "repeat_in": 5.0, "hide_beyond": 60000, "priority": 4, "fit": False},
    {"name": "Major streets", "cartocodes": ["8", "10"],
     "font": SERIES_D, "size": 9.25, "color": INK, "halo": 1.0,
     "repeat_in": 5.0, "hide_beyond": 45000, "priority": 5, "fit": False},
    {"name": "Local streets", "cartocodes": ["11"],
     "font": SERIES_C, "size": 8.0, "color": INK, "halo": 0.75,
     "repeat_in": 6.0, "hide_beyond": 32000, "priority": 6, "fit": True},
    {"name": "Unpaved and 4WD roads", "cartocodes": ["9", "16"],
     "font": SERIES_C, "size": 8.0, "color": UNPAVED, "halo": 0.75,
     "repeat_in": 6.0, "hide_beyond": 32000, "priority": 7, "fit": True},
]
NAME_OFFSET = 1.5            # points between a name and its street line
# Word spacing for names, percent of the font's own. Roadgeek's spaces are
# sign spaces (0.34 em in Series D/E), wide enough that a street crossing
# under a name shows between its words even through the halo. At 60% the
# gap is no wider than the halo covers, and names get shorter.
NAME_WORD_SPACING = 60
NAME_THINNING = 72           # drop a repeated name within this many points
END_OF_STREET_CLEARANCE = 100  # Maplex preferred clearance from street ends (Esri's example value)

# Beehive outlines used for state routes the DDV set does not have.
# (font, character code) for 1-2 digit and 3 digit routes.
BEEHIVE = {2: ("ddvut16i", 63), 3: ("ddvut16i", 65)}

ROUTE_FIELDS = ["CARTOCODE", "DOT_HWYNAM", "DOT_RTNAME", "A1_NAME", "A2_NAME"]
DIRECTIONS_OF_TRAVEL = ("NB", "SB", "EB", "WB")

# ------------------------- Route identification -------------------------- #
# route_key() and ROUTE_KEY_ARCADE must agree; tests check them against each
# other in ArcGIS Pro.


def _alias_route(alias, cartocode):
    words = (alias or "").replace("-", " ").upper().split()
    if len(words) < 2 or not words[1].isdigit():
        return ""
    number = int(words[1])
    prefix = {"I": "I-", "US": "US ", "SR": "SR ", "UT": "SR "}.get(words[0])
    if words[0] == "HWY":
        prefix = "US " if cartocode in ("2", "3") else "SR "
    return prefix + str(number) if prefix else ""


def route_key(feature):
    """'I-15', 'US 89A', 'SR 152' or '' for a dict of ROUTE_FIELDS."""
    cartocode = str(feature.get("CARTOCODE") or "")
    highway = (feature.get("DOT_HWYNAM") or "").strip().upper()
    if highway:
        return highway
    route = (feature.get("DOT_RTNAME") or "").strip().upper()
    if len(route) == 5 and route[:4].isdigit() and route[4] in "PN":
        number = int(route[:4])
        if 0 < number < 1000:
            prefix = {"1": "I-", "2": "US ", "3": "US "}.get(cartocode, "SR ")
            return prefix + str(number)
    for alias in (feature.get("A1_NAME"), feature.get("A2_NAME")):
        key = _alias_route(alias, cartocode)
        if key:
            return key
    return ""


ROUTE_KEY_ARCADE = """
function digitsOnly(s) {
  if (Count(s) == 0) { return false; }
  for (var i = 0; i < Count(s); i++) {
    if (Find(Mid(s, i, 1), '0123456789') < 0) { return false; }
  }
  return true;
}
function aliasRoute(alias, cc) {
  var w = Split(Upper(Replace(DefaultValue(alias, ''), '-', ' ')), ' ', -1, true);
  if (Count(w) < 2 || !digitsOnly(w[1])) { return ''; }
  var n = Text(Number(w[1]));
  if (w[0] == 'I') { return 'I-' + n; }
  if (w[0] == 'US') { return 'US ' + n; }
  if (w[0] == 'SR' || w[0] == 'UT') { return 'SR ' + n; }
  if (w[0] == 'HWY') { return IIf(cc == '2' || cc == '3', 'US ', 'SR ') + n; }
  return '';
}
function routeKey() {
  var cc = Text(DefaultValue($feature.CARTOCODE, ''));
  var hwy = Upper(Trim(DefaultValue($feature.DOT_HWYNAM, '')));
  if (hwy != '') { return hwy; }
  var rt = Upper(Trim(DefaultValue($feature.DOT_RTNAME, '')));
  if (Count(rt) == 5 && digitsOnly(Left(rt, 4)) && Find(Right(rt, 1), 'PN') >= 0) {
    var n = Number(Left(rt, 4));
    if (n > 0 && n < 1000) {
      return Decode(cc, '1', 'I-', '2', 'US ', '3', 'US ', 'SR ') + Text(n);
    }
  }
  var k = aliasRoute($feature.A1_NAME, cc);
  if (k != '') { return k; }
  return aliasRoute($feature.A2_NAME, cc);
}
""".strip()


def route_sort_key(route):
    family = route_family(route)
    digits = "".join(c for c in route if c.isdigit())
    return ({"I": 0, "US": 1, "SR": 2}.get(family, 3), int(digits or 0), route)


def route_family(route):
    if route.startswith("I-"):
        return "I"
    return route.split(" ")[0]


def route_number(route):
    return route[2:] if route.startswith("I-") else route.split(" ", 1)[1]


# ------------------------------ Street names ------------------------------ #


def street_name(fullname, title_case=TITLE_CASE):
    """Python twin of the name Arcade: '' when the shield says it all."""
    words = [w for w in (fullname or "").split() if w.upper() not in DIRECTIONS_OF_TRAVEL]
    if not words:
        return ""
    first = words[0].upper()
    if first.startswith("I-"):
        return ""
    if len(words) == 2 and first in ("HWY", "SR", "US", "I") and words[1].isdigit():
        return ""
    if title_case:
        words = [w[:1].upper() + w[1:].lower() for w in words]
    return " ".join(words)


def name_arcade(title_case=TITLE_CASE):
    # Not Proper(): it capitalises after digits ('8Th Ave').
    case = "Upper(Left(words[i], 1)) + Lower(Mid(words[i], 1))" if title_case else "words[i]"
    return """
// Utah Roads street name. Drops the direction of travel from divided
// highways ('VANWINKLE EXPY NB') and names that only repeat the route
// number, which the shield already shows ('HWY 189', 'I-15 SB FWY').
function digitsOnly(s) {
  if (Count(s) == 0) { return false; }
  for (var i = 0; i < Count(s); i++) {
    if (Find(Mid(s, i, 1), '0123456789') < 0) { return false; }
  }
  return true;
}
var words = Split(Trim(DefaultValue($feature.FULLNAME, '')), ' ', -1, true);
var kept = [];
for (var i in words) {
  if (!Includes(['NB', 'SB', 'EB', 'WB'], Upper(words[i]))) { Push(kept, %s); }
}
if (Count(kept) == 0) { return ''; }
var first = Upper(kept[0]);
if (Left(first, 2) == 'I-') { return ''; }
if (Count(kept) == 2 && Includes(['HWY', 'SR', 'US', 'I'], first) && digitsOnly(kept[1])) { return ''; }
return Concatenate(kept, ' ');
""".strip() % case


# ---------------------------- CIM, as dicts ------------------------------ #
# Plain dicts keep these testable without arcpy; to_cim() converts them.


def rgb(red, green, blue, alpha=100):
    return {"type": "CIMRGBColor", "values": [red, green, blue, alpha]}


def hex_rgb(value):
    return rgb(*(int(value[i:i + 2], 16) for i in (1, 3, 5)))


def solid(color):
    return {"type": "CIMPolygonSymbol",
            "symbolLayers": [{"type": "CIMSolidFill", "enable": True, "color": color}]}


def glyph(font, code, color, size, offset_y=0.0):
    return {"type": "CIMCharacterMarker", "enable": True, "fontFamilyName": font,
            "fontStyleName": "Regular", "characterIndex": code, "size": size,
            "respectFrame": True, "offsetY": offset_y, "symbol": solid(color)}


def square(color, size, corner=0.12, offset_y=0.0):
    """Rounded black square behind the beehive, as on the On Road signs."""
    c, r = 1.0, corner
    ring = [[-c + r, -c], [c - r, -c], [c, -c + r], [c, c - r], [c - r, c],
            [-c + r, c], [-c, c - r], [-c, -c + r], [-c + r, -c]]
    return {"type": "CIMVectorMarker", "enable": True, "size": size, "offsetY": offset_y,
            "frame": {"xmin": -1, "ymin": -1, "xmax": 1, "ymax": 1},
            "respectFrame": True,
            "markerGraphics": [{"type": "CIMMarkerGraphic",
                                "geometry": {"rings": [ring]},
                                "symbol": solid(color)}]}


def shield_callout(layers_bottom_first):
    # CIM draws symbolLayers[0] on top; DDV lists the bottom layer first.
    return {"type": "CIMPointSymbolCallout",
            "pointSymbol": {"type": "CIMPointSymbol",
                            "symbolLayers": list(reversed(layers_bottom_first))}}


def text_symbol(font, size, color, halo=0.0, callout=None, word_spacing=100, axes=None):
    symbol = {"type": "CIMTextSymbol", "fontFamilyName": font,
              "fontStyleName": "Regular", "height": size, "symbol": solid(color),
              "horizontalAlignment": "Center", "verticalAlignment": "Center",
              "wordSpacing": word_spacing}
    if axes:
        symbol["fontVariationSettings"] = [{"type": "CIMFontVariation", "tagName": tag, "value": value}
                                           for tag, value in axes.items()]
    if halo:
        symbol["haloSize"] = halo
        symbol["haloSymbol"] = solid(rgb(255, 255, 255))
    if callout:
        symbol["callout"] = callout
    return symbol


def maplex(**properties):
    base = {"type": "CIMMaplexLabelPlacementProperties", "featureType": "Line",
            "enableConnection": True, "connectionType": "Unambiguous",
            "repeatLabel": True, "repetitionIntervalUnit": "Point",
            "thinDuplicateLabels": True, "thinningDistanceUnit": "Point",
            "canStackLabel": False, "canReduceFontSize": False,
            "canAbbreviateLabel": False, "canTruncateLabel": False,
            "canRemoveOverlappingLabel": True, "featureWeight": 0,
            "maximumLabelOverrunUnit": "Point"}
    base.update(properties)
    return base


def label_class(name, expression, where, text, priority, hide_beyond, placement):
    return {"type": "CIMLabelClass", "name": name, "expressionTitle": "Custom",
            "expression": expression, "expressionEngine": "Arcade",
            "whereClause": where, "featuresToLabel": "AllVisibleFeatures",
            "textSymbol": {"type": "CIMSymbolReference", "symbol": text},
            "priority": priority, "minimumScale": hide_beyond, "maximumScale": 0,
            "visibility": True, "useCodedValue": False,
            "maplexLabelPlacementProperties": placement}


def _sql_list(values):
    return ", ".join("'%s'" % v for v in values)


# ------------------------------ Label classes ---------------------------- #


def load_shields(series=SERIES, path=SHIELD_DATA):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if series not in data["series"]:
        raise ValueError("unknown series %r; choose from %s" % (series, ", ".join(data["series"])))
    return data["series"][series]["shields"]


def ddv_layers(route, shields, us_wide=US_WIDE_SHIELDS):
    if us_wide and route + " wide" in shields:
        return shields[route + " wide"]
    return shields.get(route)


def fallback_layers(route, series, size):
    """Beehive shield and number colour for a state route DDV never drew.

    The shield is raised slightly so the centred number sits low in the
    beehive, where DDV puts it.
    """
    digits = 3 if len(route_number(route)) >= 3 else 2
    font, code = BEEHIVE[digits]
    lift = size * 0.07
    if series in ("ddvut10i", "ddvut13i"):
        width = 0.78 if series == "ddvut13i" and digits == 3 else 0.70
        layers = [square(rgb(0, 0, 0), size * width, offset_y=lift),
                  glyph(font, code, rgb(255, 255, 255), size * 0.62, lift)]
        number = rgb(0, 0, 0)
    elif series == "ddvut16i":
        layers = [glyph(font, code, rgb(0, 0, 0), size * 0.98, lift),
                  glyph(font, code, rgb(255, 255, 255), size * 0.94, lift)]
        number = rgb(0, 0, 0)
    else:  # ddvut19i: black beehive, white number
        layers = [glyph(font, code, rgb(0, 0, 0), size * 0.94, lift)]
        number = rgb(255, 255, 255)
    return layers, number


SHIELD_WHERE = ("CARTOCODE IN ('1', '2', '3', '4', '5', '6') AND "
                "(DOT_HWYNAM {} OR DOT_HWYNAM IS NULL OR DOT_HWYNAM = '')")


def shield_placement(spec, overrun):
    """Horizontal and centred on the line, which Esri recommends for shields."""
    repeat = spec["repeat_in"] * POINTS_PER_INCH
    return maplex(
        lineFeatureType="General", linePlacementMethod="CenteredHorizontalOnLine",
        minimumRepetitionInterval=repeat, thinningDistance=repeat * 0.5,
        canOverrunFeature=True, maximumLabelOverrun=overrun, labelBuffer=40,
        preferHorizontalPlacement=True)


# ------------------------- MUTCD vector shields -------------------------- #

MUTCD_PREFIX = {"I": "I-", "US": "US ", "SR": "SR "}
MUTCD_NAMES = {"I": "Interstate", "US": "US route", "SR": "State route"}


def load_mutcd(path=MUTCD_DATA):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["shields"]


def shield_digits(route):
    return 3 if len(route_number(route)) >= 3 else 2


def vector_shield(shield, height):
    """The blank sign as one vector marker, height points tall.

    It is offset so the fitted numerals' centre (build_shields.py keeps the
    sign design's) lands on the label text's centre.
    """
    width, frame_height = shield["width"], shield["height"]
    scale = height / frame_height
    number = shield["number"]
    figure_centre_y = number["baseline"] + number["figure_height"] * number["size"] / 2
    graphics = []
    for g in shield["graphics"]:
        layers = []
        if g["stroke"]:
            layers.append({"type": "CIMSolidStroke", "enable": True, "color": hex_rgb(g["stroke"]),
                           "width": g["stroke_width"] * scale})
        if g["fill"]:
            layers.append({"type": "CIMSolidFill", "enable": True, "color": hex_rgb(g["fill"])})
        graphics.append({"type": "CIMMarkerGraphic", "geometry": {"curveRings": g["curveRings"]},
                         "symbol": {"type": "CIMPolygonSymbol", "symbolLayers": layers}})
    return {"type": "CIMVectorMarker", "enable": True, "size": height,
            "frame": {"xmin": 0, "ymin": 0, "xmax": width, "ymax": frame_height},
            "respectFrame": True, "scaleSymbolsProportionally": False,
            "offsetX": (width / 2 - number["x"]) * scale,
            "offsetY": (frame_height / 2 - figure_centre_y) * scale,
            "markerGraphics": graphics}


def mutcd_shield_class(family, digits, shield):
    """One label class per network and digit count; the text is the route number."""
    spec = SHIELDS[family]
    height = spec["height"]
    number = shield["number"]
    # Bahnschrift is a variable font: weight and width go in as axes.
    text = text_symbol(number["font"], number["size"] * height / shield["height"],
                       hex_rgb(number["colour"]), callout=shield_callout([vector_shield(shield, height)]),
                       axes=number.get("axes"))
    prefix = MUTCD_PREFIX[family]
    fits = "Count(n) <= 2" if digits == 2 else "Count(n) >= 3"
    expression = "%s\n\nvar k = routeKey();\nif (Left(k, %d) != '%s') { return ''; }\n" \
                 "var n = Mid(k, %d);\nreturn IIf(%s, n, '');" % (
                     ROUTE_KEY_ARCADE, len(prefix), prefix, len(prefix), fits)
    name = "%s shields, %s digits" % (MUTCD_NAMES[family], "1-2" if digits == 2 else "3")
    width = shield["width"] * height / shield["height"]
    return label_class(name, expression, SHIELD_WHERE.format("LIKE '%s%%'" % prefix), text,
                       spec["priority"], spec["hide_beyond"], shield_placement(spec, width))


# ---------------------------- DDV font shields --------------------------- #


def ddv_shield_class(route, shields, series=SERIES, us_wide=US_WIDE_SHIELDS):
    """One label class per route: its callout is that route's shield."""
    family = route_family(route)
    spec = SHIELDS[family]
    size = spec["size"]
    number = route_number(route)
    digits = 3 if len(number) >= 3 else 2
    layers = ddv_layers(route, shields, us_wide)
    if layers:
        # The number is part of the DDV glyphs. The label text only reserves
        # the shield's room during placement, so it is fully transparent.
        callout = shield_callout([glyph(f, code, hex_rgb(c), size) for f, code, c in layers])
        text = text_symbol(SHIELD_NUMBER_FONTS[digits], size * 0.5, rgb(0, 0, 0, 0),
                           callout=callout)
        source = "DDV"
    elif family == "SR":
        drawn, color = fallback_layers(route, series, size)
        height = size * (0.35 if digits == 3 else 0.33)
        text = text_symbol(SHIELD_NUMBER_FONTS[digits], height, color,
                           callout=shield_callout(drawn))
        source = "beehive fallback"
    else:
        return None, "no shield"

    expression = "%s\n\nreturn IIf(routeKey() == '%s', '%s', '');" % (
        ROUTE_KEY_ARCADE, route, number)
    return label_class("Shield %s" % route, expression, SHIELD_WHERE.format("= '%s'" % route), text,
                       spec["priority"], spec["hide_beyond"], shield_placement(spec, size)), source


def name_classes(title_case=TITLE_CASE):
    classes = []
    for spec in NAME_CLASSES:
        repeat = spec["repeat_in"] * POINTS_PER_INCH
        # Beside the line, not on it: a centred name lets the street show
        # through the gaps between its words.
        placement = maplex(
            lineFeatureType="Street", linePlacementMethod="OffsetCurvedFromLine",
            primaryOffset=NAME_OFFSET, primaryOffsetUnit="Point",
            minimumRepetitionInterval=repeat, thinningDistance=NAME_THINNING,
            canOverrunFeature=not spec["fit"], maximumLabelOverrun=spec["size"],
            preferredEndOfStreetClearance=END_OF_STREET_CLEARANCE,
            labelBuffer=15, spreadWords=False, spreadCharacters=False)
        text = text_symbol(spec["font"], spec["size"], rgb(*spec["color"]), halo=spec["halo"],
                           word_spacing=NAME_WORD_SPACING)
        classes.append(label_class(
            spec["name"], name_arcade(title_case),
            "CARTOCODE IN (%s)" % _sql_list(spec["cartocodes"]),
            text, spec["priority"], spec["hide_beyond"], placement))
    return classes


def build_label_classes(routes, style=SHIELD_STYLE, series=SERIES, us_wide=US_WIDE_SHIELDS,
                        title_case=TITLE_CASE):
    """(label class dicts, {route: shield source}) for the given routes."""
    routes = sorted(set(routes), key=route_sort_key)
    classes, sources = [], {}
    if style == "mutcd":
        shields = load_mutcd()
        groups = []
        for route in routes:
            family = route_family(route)
            if family not in MUTCD_PREFIX:
                sources[route] = "no shield"
                continue
            sources[route] = "MUTCD"
            if (family, shield_digits(route)) not in groups:
                groups.append((family, shield_digits(route)))
        classes = [mutcd_shield_class(f, d, shields["%s-%d" % (f, d)]) for f, d in groups]
    elif style == "ddv":
        shields = load_shields(series)
        for route in routes:
            cls, sources[route] = ddv_shield_class(route, shields, series, us_wide)
            if cls:
                classes.append(cls)
    else:
        raise ValueError("unknown shield style %r" % style)
    return classes + name_classes(title_case), sources


# --------------------------------- ArcPy --------------------------------- #


def to_cim(value):
    """Build arcpy.cim objects from the dicts above; unset keys keep Pro's defaults."""
    import arcpy

    if isinstance(value, list):
        return [to_cim(v) for v in value]
    if isinstance(value, dict) and value.get("type", "").startswith("CIM"):
        obj = arcpy.cim.CreateCIMObjectFromClassName(value["type"], "V3")
        for key, item in value.items():
            if key != "type":
                setattr(obj, key, to_cim(item))
        return obj
    return value  # numbers, strings, and geometry, which arcpy.cim keeps as JSON dicts


def routes_in_layer(layer):
    import arcpy

    where = "CARTOCODE IN ('1', '2', '3', '4', '5', '6')"
    routes = set()
    with arcpy.da.SearchCursor(layer, ROUTE_FIELDS, where) as rows:
        for row in rows:
            key = route_key(dict(zip(ROUTE_FIELDS, row)))
            if key:
                routes.add(key)
    return routes


def label_layer(layer, style=SHIELD_STYLE, series=SERIES, reference_scale=REFERENCE_SCALE,
                us_wide=US_WIDE_SHIELDS, title_case=TITLE_CASE, dry_run=False,
                map_=None):
    """Replace the layer's label classes. Returns {route: shield source}."""
    import arcpy

    fields = {f.name.upper() for f in arcpy.ListFields(layer)}
    missing = set(ROUTE_FIELDS + ["FULLNAME"]) - fields
    if missing:
        raise ValueError("%s is missing Utah Roads fields: %s" % (layer.name, ", ".join(sorted(missing))))

    classes, sources = build_label_classes(routes_in_layer(layer), style,
                                           series, us_wide, title_case)
    if dry_run:
        return sources
    missing = ensure_fonts_loaded(style, series)
    if missing:
        raise RuntimeError("fonts not installed: %s. Run road_labels.py --install-fonts; "
                           "Pro would draw Arial instead." % ", ".join(sorted(missing)))

    cim = layer.getDefinition("V3")
    cim.labelClasses = to_cim(classes)
    cim.labelVisibility = True
    layer.setDefinition(cim)
    if map_ is not None and reference_scale:
        map_.referenceScale = reference_scale
    return sources


def create_vector_tiles(map_, out_path, min_scale=577790.554289, max_scale=9027.977411):
    """Package the map as vector tiles (shields become sprites). Upload separately."""
    import arcpy

    # Create Vector Tile Package refuses a map without a description.
    metadata = map_.metadata
    if not (metadata.description or "").strip():
        metadata.description = "Utah Roads (UGRC SGID) labelled with DDV Utah highway shields and street names."
        if not (metadata.title or "").strip():
            metadata.title = map_.name
        metadata.save()

    # The ArcGIS Online tiling scheme is Web Mercator, and vector tiles size
    # symbols per level rather than to a reference scale.
    reference, spatial_reference = map_.referenceScale, map_.spatialReference
    map_.referenceScale = 0
    map_.spatialReference = arcpy.SpatialReference(3857)
    try:
        arcpy.management.CreateVectorTilePackage(
            map_, out_path, "ONLINE", None, "INDEXED", min_scale, max_scale,
            summary="Utah Roads with DDV highway shields and street names",
            tags="Utah, roads, labels, shields")
    finally:
        map_.referenceScale = reference
        map_.spatialReference = spatial_reference
    offset_vector_tile_names(out_path)
    return out_path


def name_text_offset(spec):
    """Vertical text-offset (ems) that puts a name beside its line, not on it."""
    return round(-(0.3 + NAME_OFFSET / spec["size"]), 3)


def offset_vector_tile_names(vtpk):
    """Add text-offset to the street-name layers of a vector tile package's style.

    Pro drops the Maplex offset when it writes the style, so names would
    sit on their street with the line showing between the words.
    """
    import tempfile
    import zipfile

    offsets = {spec["name"]: name_text_offset(spec) for spec in NAME_CLASSES}
    fd, temp = tempfile.mkstemp(suffix=".vtpk", dir=os.path.dirname(os.path.abspath(vtpk)))
    os.close(fd)
    patched = 0
    with zipfile.ZipFile(vtpk) as source, zipfile.ZipFile(temp, "w") as target:
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename.endswith("styles/root.json"):
                style = json.loads(data)
                for layer in style["layers"]:
                    offset = offsets.get(layer["id"].rsplit("/", 1)[-1])
                    if offset is not None and layer.get("type") == "symbol":
                        layer.setdefault("layout", {})["text-offset"] = [0, offset]
                        patched += 1
                data = json.dumps(style).encode("utf-8")
            target.writestr(info, data)
    os.replace(temp, vtpk)
    return patched


# --------------------------------- Fonts --------------------------------- #


ROADGEEK_PREFIX = "Roadgeek 2014 Series "
FONT_PATTERNS = ("DDVUT*.TTF", "RG2014*.TTF")


def font_file_stem(family):
    """'ddvut10i' -> 'DDVUT10I', 'Roadgeek 2014 Series D' -> 'RG2014D'."""
    if family.startswith(ROADGEEK_PREFIX):
        return "RG2014" + family[len(ROADGEEK_PREFIX):].upper()
    return family.upper()


def font_family(stem):
    stem = stem.upper()
    if stem.startswith("RG2014"):
        return ROADGEEK_PREFIX + stem[len("RG2014"):]
    return stem.lower()


def label_font_families(style=SHIELD_STYLE):
    """Text fonts: street names (Roadgeek) and shield numbers."""
    families = {spec["font"] for spec in NAME_CLASSES}
    if style == "mutcd":
        families |= {s["number"]["font"] for s in load_mutcd().values()}
    else:
        families |= set(SHIELD_NUMBER_FONTS.values())
    return families


def required_font_families(style=SHIELD_STYLE, series=SERIES):
    families = label_font_families(style)
    if style == "ddv":
        families |= {font for layers in load_shields(series).values() for font, _, _ in layers}
        families |= {font for font, _ in BEEHIVE.values()}
    return families


def required_font_files(style=SHIELD_STYLE, series=SERIES):
    return {font_file_stem(f) for f in required_font_families(style, series)}


SYSTEM_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
USER_FONTS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts")


def loaded_font_families():
    """Font families Windows (GDI) has loaded in this session, lower-cased.

    Pro draws with these. A family that is installed but not loaded is
    silently replaced by Arial, in layouts and in vector tiles alike.
    """
    import ctypes
    from ctypes import wintypes

    class LOGFONTW(ctypes.Structure):
        _fields_ = [("lfHeight", wintypes.LONG), ("lfWidth", wintypes.LONG), ("lfEscapement", wintypes.LONG),
                    ("lfOrientation", wintypes.LONG), ("lfWeight", wintypes.LONG), ("lfItalic", wintypes.BYTE),
                    ("lfUnderline", wintypes.BYTE), ("lfStrikeOut", wintypes.BYTE), ("lfCharSet", wintypes.BYTE),
                    ("lfOutPrecision", wintypes.BYTE), ("lfClipPrecision", wintypes.BYTE),
                    ("lfQuality", wintypes.BYTE), ("lfPitchAndFamily", wintypes.BYTE),
                    ("lfFaceName", wintypes.WCHAR * 32)]

    callback = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.POINTER(LOGFONTW), ctypes.c_void_p,
                                  wintypes.DWORD, wintypes.LPARAM)
    gdi, user = ctypes.windll.gdi32, ctypes.windll.user32
    gdi.EnumFontFamiliesExW.argtypes = [wintypes.HDC, ctypes.POINTER(LOGFONTW), callback,
                                        wintypes.LPARAM, wintypes.DWORD]
    found = set()

    def each(logfont, *_):
        found.add(logfont.contents.lfFaceName.lower())
        return 1

    query = LOGFONTW()
    query.lfCharSet = 1  # DEFAULT_CHARSET: every family once
    hdc = user.GetDC(None)
    try:
        gdi.EnumFontFamiliesExW(hdc, ctypes.byref(query), callback(each), 0, 0)
    finally:
        user.ReleaseDC(None, hdc)
    return found


def ensure_fonts_loaded(style=SHIELD_STYLE, series=SERIES):
    """Load any required font that is installed but not yet loaded.

    Returns the families still missing (not installed at all).
    """
    missing = {f for f in required_font_families(style, series) if f.lower() not in loaded_font_families()}
    if missing:
        stems = {font_file_stem(f) for f in missing}
        register_fonts([p for d in (USER_FONTS, SYSTEM_FONTS) for pattern in FONT_PATTERNS
                        for p in glob.glob(os.path.join(d, pattern))
                        if os.path.splitext(os.path.basename(p))[0].upper() in stems])
        missing = {f for f in missing if f.lower() not in loaded_font_families()}
    return missing


def install_fonts(folders):
    """Install the DDV and Roadgeek fonts in folders for the current Windows user (no admin)."""
    import winreg

    paths = sorted({p for folder in folders for pattern in FONT_PATTERNS
                    for p in glob.glob(os.path.join(folder, pattern))})
    if not paths:
        raise FileNotFoundError("no DDVUT*.TTF or RG2014*.TTF files in %s" % ", ".join(folders))
    target_dir = os.path.join(os.environ["LOCALAPPDATA"], "Microsoft", "Windows", "Fonts")
    os.makedirs(target_dir, exist_ok=True)
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows NT\CurrentVersion\Fonts")
    targets = []
    with key:
        for path in paths:
            target = os.path.join(target_dir, os.path.basename(path))
            shutil.copy2(path, target)
            face = font_family(os.path.splitext(os.path.basename(path))[0])
            winreg.SetValueEx(key, "%s (TrueType)" % face, 0, winreg.REG_SZ, target)
            targets.append(target)
    register_fonts(targets)
    return [os.path.basename(p) for p in paths]


def register_fonts(paths):
    """Load installed font files into this Windows session.

    Windows reads the per-user font registry only at sign-in. Without this,
    Pro silently draws Arial in place of fonts installed during the session.
    """
    import ctypes
    from ctypes import wintypes

    gdi, user = ctypes.windll.gdi32, ctypes.windll.user32
    gdi.AddFontResourceW.argtypes = [wintypes.LPCWSTR]
    loaded = sum(gdi.AddFontResourceW(p) > 0 for p in paths)
    hwnd_broadcast, wm_fontchange, smto_abortifhung = 0xFFFF, 0x001D, 0x0002
    user.SendMessageTimeoutW(hwnd_broadcast, wm_fontchange, 0, 0, smto_abortifhung, 2000,
                             ctypes.byref(wintypes.DWORD()))
    return loaded


# ---------------------------------- CLI ---------------------------------- #


def main():
    parser = argparse.ArgumentParser(description="Label Utah Roads with highway shields and street names.")
    parser.add_argument("project", nargs="?", help=".aprx to update (close it in Pro first)")
    parser.add_argument("--map", help="map name (default: the first map)")
    parser.add_argument("--layer", default="Roads", help="Utah Roads layer name (default: Roads)")
    parser.add_argument("--shields", default=SHIELD_STYLE, choices=["mutcd", "ddv"],
                        help="mutcd: vector sign designs (default); ddv: 2003 DDV font shields")
    parser.add_argument("--series", default=SERIES, choices=["ddvut10i", "ddvut13i", "ddvut16i", "ddvut19i"],
                        help="DDV shield series (--shields ddv)")
    parser.add_argument("--reference-scale", type=float, default=REFERENCE_SCALE)
    parser.add_argument("--us-wide", action="store_true", help="wider 3-digit US shields (--shields ddv)")
    parser.add_argument("--upper-case", action="store_true", help="keep names in capitals")
    parser.add_argument("--save-as", help="save to a new .aprx instead of in place")
    parser.add_argument("--vtpk", help="also write a vector tile package here")
    parser.add_argument("--dry-run", action="store_true", help="report routes and shields; change nothing")
    parser.add_argument("--install-fonts", metavar="FOLDER", nargs="+",
                        help="install the DDVUT*.TTF and RG2014*.TTF fonts in these folders and exit")
    args = parser.parse_args()

    if args.install_fonts:
        for name in install_fonts(args.install_fonts):
            print("installed", name)
        print("Restart ArcGIS Pro so it sees the new fonts.")
        return
    if not args.project:
        parser.error("a project is required")

    missing_fonts = ensure_fonts_loaded(args.shields, args.series)
    if missing_fonts and not args.dry_run:
        sys.exit("fonts not installed: %s. Run --install-fonts first; Pro would draw Arial instead."
                 % ", ".join(sorted(missing_fonts)))

    import arcpy

    aprx = arcpy.mp.ArcGISProject(args.project)
    maps = aprx.listMaps(args.map) if args.map else aprx.listMaps()
    if not maps:
        sys.exit("no map %r in %s" % (args.map, args.project))
    map_ = maps[0]
    layers = [l for l in map_.listLayers(args.layer) if l.isFeatureLayer]
    if len(layers) != 1:
        sys.exit("expected one feature layer named %r in map %r, found %d" % (args.layer, map_.name, len(layers)))

    sources = label_layer(layers[0], args.shields, args.series, args.reference_scale, args.us_wide,
                          not args.upper_case, args.dry_run, map_)
    for route in sorted(sources, key=route_sort_key):
        print("  %-8s %s" % (route, sources[route]))
    counts = {}
    for source in sources.values():
        counts[source] = counts.get(source, 0) + 1
    print("%d routes: %s" % (len(sources), ", ".join("%d %s" % (n, s) for s, n in sorted(counts.items()))))
    if args.dry_run:
        return

    if args.save_as:
        aprx.saveACopy(args.save_as)
    else:
        aprx.save()
    print("labels written to %s in %s" % (layers[0].name, args.save_as or args.project))
    if args.vtpk:
        if args.shields == "mutcd":
            print("note: shield numbers are Bahnschrift, a Microsoft-supplied Windows font; the package "
                  "embeds its glyphs. Check its licence before publishing the tiles.")
        print("vector tiles:", create_vector_tiles(map_, args.vtpk))


if __name__ == "__main__":
    main()
