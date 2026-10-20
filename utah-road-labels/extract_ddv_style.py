"""
extract_ddv_style.py

Regenerates ddv_utah_shields.json from Data Deja View's Utah highway shield
styles (UtahDDV.ZIP, version "I", 2003-09-10). The .Style files are ArcMap
style databases (Microsoft Access); each marker symbol is a stack of
TrueType glyph layers. This script reads every layer's font, character code
and colour so road_labels.py can rebuild the shields as CIM character
markers without ArcMap.

The .Style files name their symbols 1..277 with no route numbers, so the
route for each symbol ID was transcribed from rendered contact sheets and is
recorded in ROUTES below. IDs are identical across the four On Road series.

Usage (ArcGIS Pro's Python has pyodbc; the Microsoft Access ODBC driver must
be installed, and Access cannot open very long paths, so unzip somewhere
short):

    python extract_ddv_style.py C:\\temp\\UtahDDV

Only needed when the DDV files change. The JSON is committed.
"""

import argparse
import json
import os
import struct
import sys

# ArcObjects GUIDs as they appear in the persisted symbol stream.
CHARACTER_MARKER = bytes.fromhex("e6147992c8d0118bb6080009ee4e41")
STD_FONT = bytes.fromhex("0352e30b918fce119de300aa004bb851")
RGB_COLOR = bytes.fromhex("96c4e97e23d1d011838308")

# The four "On Road" series: the Utah beehive for state routes, as signed.
SERIES = {
    "ddvut10i": "On Road (black square)",
    "ddvut13i": "On Road variant two (wider 3-digit squares)",
    "ddvut16i": "On Road variant four (beehive only, no square)",
    "ddvut19i": "On Road variant five (reversed beehive)",
}

# Symbol ID -> route, transcribed from the rendered symbols.
INTERSTATES = ["I-15", "I-70", "I-80", "I-84", "I-215"]                    # IDs 1-5
US_ROUTES = ["US 6", "US 30", "US 40", "US 50", "US 89", "US 89A", "US 91",
             "US 160", "US 163", "US 180", "US 189", "US 191", "US 491",
             "US 666"]                                                     # IDs 6-19
US_WIDE = ["US 160", "US 163", "US 180", "US 189", "US 191", "US 491",
           "US 666"]                                                       # IDs 20-26
STATE_ROUTES = (                                                           # IDs 27-270
    [8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 28,
     29, 30, 31, 32, 34, 35, 36, 37, 38, 39, 41, 42, 43, 44, 45, 46, 48, 51,
     52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 68, 69, 71,
     72, 73, 74, 75, 76, 77, 78, 79, 81, 82, 83, 86, 87, 88, 90, 91, 92, 93,
     94]
    + list(range(95, 129)) + [130, 131, 132, 133, 134] + list(range(136, 162))
    + [163, 164, 165, 167, 168, 171, 172, 173, 174, 178, 181, 184, 186, 190,
       193] + list(range(195, 205))
    + [208, 209, 210, 211, 212, 214, 218, 219, 222, 224, 225, 226, 227, 228,
       232, 235, 237, 238, 239, 240, 241, 243, 244, 248]
    + list(range(256, 263)) + [264, 265, 266, 268, 269, 270, 271, 272, 273,
                               274, 275, 276, 279, 280] + list(range(282, 300))
    + [301, 302, 303, 304, 305, 308, 310] + list(range(311, 321))
)
# ID 271 is a "999" sample and 272-277 are blank county shields: not routes.


def route_for_id(symbol_id):
    if symbol_id <= 5:
        return INTERSTATES[symbol_id - 1]
    if symbol_id <= 19:
        return US_ROUTES[symbol_id - 6]
    if symbol_id <= 26:
        return US_WIDE[symbol_id - 20] + " wide"
    if symbol_id <= 270:
        return "SR %d" % STATE_ROUTES[symbol_id - 27]
    return None


def lab_to_hex(L, a, b):
    """CIELAB (D65) to sRGB hex. ArcObjects stores style colours as Lab."""
    fy = (L + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200

    def f(t):
        return t ** 3 if t ** 3 > 0.008856 else (t - 16 / 116) / 7.787

    x, y, z = 0.95047 * f(fx), f(fy), 1.08883 * f(fz)
    linear = (3.2406 * x - 1.5372 * y - 0.4986 * z,
              -0.9689 * x + 1.8758 * y + 0.0415 * z,
              0.0557 * x - 0.2040 * y + 1.0570 * z)

    def gamma(v):
        v = 1.055 * v ** (1 / 2.4) - 0.055 if v > 0.0031308 else 12.92 * v
        return max(0, min(255, round(255 * v)))

    return "#%02x%02x%02x" % tuple(gamma(v) for v in linear)


def glyph_layers(blob):
    """[font, character code, colour] for each layer, bottom layer first."""
    layers, start = [], 0
    while True:
        font_at = blob.find(STD_FONT, start)
        if font_at < 0:
            return layers
        marker_at = blob.rfind(CHARACTER_MARKER, start, font_at)
        segment = blob[marker_at:font_at]
        colour_at = segment.find(RGB_COLOR) + 16 + 5
        lab = struct.unpack_from("<3d", segment, colour_at)
        char_code = struct.unpack_from("<i", segment, colour_at + 24 + 2)[0]
        name_at = font_at + 16 + 10
        font = blob[name_at + 1:name_at + 1 + blob[name_at]].decode("latin-1")
        layers.append([font.lower(), char_code, lab_to_hex(*lab)])
        start = font_at + 16


def read_style(path):
    import pyodbc

    connection = pyodbc.connect(
        "DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=" + path)
    try:
        rows = connection.cursor().execute(
            "SELECT Name, Object FROM [Marker Symbols]").fetchall()
    finally:
        connection.close()
    return {int(row.Name): glyph_layers(bytes(row.Object)) for row in rows}


def dumps(data):
    """JSON with one shield per line, so a diff shows which shields changed."""
    series = []
    for name, entry in data["series"].items():
        shields = ",\n".join("    %s: %s" % (json.dumps(route), json.dumps(layers))
                             for route, layers in entry["shields"].items())
        series.append('  %s: {"title": %s, "shields": {\n%s\n  }}' % (
            json.dumps(name), json.dumps(entry["title"]), shields))
    return '{"source": %s,\n "series": {\n%s\n }}' % (
        json.dumps(data["source"], indent=2).replace("\n", "\n "), ",\n".join(series))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("folder", help="folder holding the unzipped UtahDDV files")
    parser.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "ddv_utah_shields.json"))
    args = parser.parse_args()

    assert len(STATE_ROUTES) == 244 and STATE_ROUTES == sorted(set(STATE_ROUTES))

    data = {
        "source": {
            "archive": "UtahDDV.ZIP (Data Deja View, Jim Mossman), version I, 2003-09-10",
            "url": "https://github.com/VerdantSkys/DDVs_ALL",
            "note": "Layers are [font, character code, colour], bottom layer first. "
                    "Regenerate with extract_ddv_style.py.",
        },
        "series": {},
    }
    numbered = None
    for series, title in SERIES.items():
        symbols = read_style(os.path.join(args.folder, series + ".Style"))
        # The route number is always in the top layer; the transcription is
        # only valid if every series numbers its symbols the same way.
        top = {i: tuple(layers[-1][1:2]) for i, layers in symbols.items() if i <= 270}
        if numbered is None:
            numbered = top
        elif top != numbered:
            sys.exit("%s numbers its symbols differently; re-transcribe ROUTES" % series)
        data["series"][series] = {
            "title": title,
            "shields": {route_for_id(i): layers
                        for i, layers in sorted(symbols.items()) if route_for_id(i)},
        }

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(dumps(data) + "\n")
    print("wrote %s (%d series, %d shields each)" % (
        args.out, len(data["series"]), len(data["series"]["ddvut10i"]["shields"])))


if __name__ == "__main__":
    main()
