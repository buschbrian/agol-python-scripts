"""
build_shields.py

Regenerates mutcd_shields.json from the public-domain Wikimedia Commons
templates of the Interstate (M1-1), US route (M1-4) and Utah state route
shields, in their two-digit (24 x 24) and three-digit (30 x 24) widths:

    I-00 template.svg     I-000 template.svg
    US 00 template.svg    US 000 template.svg
    Utah 00 template.svg  Utah 000 template.svg

from https://commons.wikimedia.org/wiki/File:<name>. Each blank shield
becomes CIM vector-marker geometry (curves kept as Bezier segments, so the
shield stays sharp at any size). The template's placeholder numeral ("00")
records where the route number goes: its font, size, centre and baseline.
road_labels.py draws that number as live label text, at the size and
position fit_numerals() works out for map use.

Usage (any Python with fontTools, Pillow and NumPy, all in ArcGIS Pro's
Python, on Windows for the Bahnschrift numeral font):

    python build_shields.py C:\\temp\\shield-svgs

Only needed when the templates change. The JSON is committed.
"""

import argparse
import json
import os
import re
import xml.etree.ElementTree as ET

from fontTools.svgLib.path import parse_path

TEMPLATES = {
    "I-2": "I-00 template.svg",
    "I-3": "I-000 template.svg",
    "US-2": "US 00 template.svg",
    "US-3": "US 000 template.svg",
    "SR-2": "Utah 00 template.svg",
    "SR-3": "Utah 000 template.svg",
}
SKIP = {"defs", "metadata", "namedview", "clipPath", "title", "desc"}
PRECISION = 3


def local(tag):
    return tag.split("}")[-1]


def styles(element):
    """Presentation attributes, with style="" winning over attributes."""
    out = {local(k): v for k, v in element.attrib.items()}
    for item in (element.get("style") or "").split(";"):
        if ":" in item:
            key, value = item.split(":", 1)
            out[key.strip()] = value.strip()
    return out


def parse_transform(text):
    """SVG transform list as an affine (a, b, c, d, e, f)."""
    m = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    for name, args in re.findall(r"(\w+)\s*\(([^)]*)\)", text or ""):
        v = [float(x) for x in re.split(r"[\s,]+", args.strip()) if x]
        if name == "matrix":
            t = tuple(v)
        elif name == "translate":
            t = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
        elif name == "scale":
            t = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
        else:
            raise ValueError("unsupported transform %s" % name)
        m = multiply(m, t)
    return m


def multiply(m, t):
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = t
    return (a * a2 + c * b2, b * a2 + d * b2, a * c2 + c * d2, b * c2 + d * d2,
            a * e2 + c * f2 + e, b * e2 + d * f2 + f)


def apply(m, point):
    x, y = point
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


class RingPen:
    """Collects path segments as rings of points and cubic Beziers."""

    def __init__(self):
        self.rings, self.ring, self.start, self.current = [], None, None, None

    def moveTo(self, p):
        self._close()
        self.ring, self.start, self.current = [("M", p)], p, p

    def lineTo(self, p):
        self.ring.append(("L", p))
        self.current = p

    def curveTo(self, *points):
        c1, c2, p = points
        self.ring.append(("C", c1, c2, p))
        self.current = p

    def qCurveTo(self, *points):
        q, p = points  # SVG quadratics have one control point
        c1 = (self.current[0] + 2 / 3 * (q[0] - self.current[0]), self.current[1] + 2 / 3 * (q[1] - self.current[1]))
        c2 = (p[0] + 2 / 3 * (q[0] - p[0]), p[1] + 2 / 3 * (q[1] - p[1]))
        self.curveTo(c1, c2, p)

    def closePath(self):
        self._close()

    def endPath(self):
        self._close()

    def _close(self):
        if self.ring and len(self.ring) > 1:
            if self.current != self.start:
                self.ring.append(("L", self.start))
            self.rings.append(self.ring)
        self.ring = None


def rect_path(s):
    x, y = float(s.get("x", 0)), float(s.get("y", 0))
    w, h = float(s["width"]), float(s["height"])
    r = float(s.get("rx", s.get("ry", 0)))
    if not r:
        return "M%s %sh%sv%sh%sz" % (x, y, w, h, -w)
    k = r * 0.5523  # quarter-circle Bezier
    return ("M{0} {1}h{2}c{k} 0 {r} {rk} {r} {r}v{3}c0 {k} {rk} {r} {nr} {r}h{4}"
            "c{nk} 0 {nr} {nrk} {nr} {nr}v{5}c0 {nk} {rk} {nr} {r} {nr}z").format(
        x + r, y, w - 2 * r, h - 2 * r, -(w - 2 * r), -(h - 2 * r),
        k=k, r=r, rk=r - k, nr=-r, nk=-k, nrk=-(r - k))


def colour(value):
    if not value or value == "none":
        return None
    value = value.strip().lower()
    if re.fullmatch(r"#[0-9a-f]{3}", value):
        value = "#" + "".join(c * 2 for c in value[1:])
    if not re.fullmatch(r"#[0-9a-f]{6}", value):
        raise ValueError("unsupported colour %r" % value)
    return value


def flatten(ring, steps=8):
    """Polyline approximation of a converted ring, for area and containment."""
    points, current = [], None
    for seg in ring:
        if isinstance(seg, dict):
            end, c1, c2 = seg["b"]
            for i in range(1, steps + 1):
                t = i / steps
                points.append(tuple((1 - t) ** 3 * current[k] + 3 * (1 - t) ** 2 * t * c1[k]
                                    + 3 * (1 - t) * t * t * c2[k] + t ** 3 * end[k] for k in (0, 1)))
            current = end
        else:
            points.append(tuple(seg))
            current = seg
    return points


def signed_area(points):
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1])) / 2


def inside(point, polygon):
    x, y = point
    hit = False
    for (x0, y0), (x1, y1) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def reverse(ring):
    """The same ring traversed backwards, Bezier control points swapped."""
    out = [_end(ring[-1])]
    for i in range(len(ring) - 1, 0, -1):
        seg, previous_end = ring[i], _end(ring[i - 1])
        out.append({"b": [previous_end, seg["b"][2], seg["b"][1]]} if isinstance(seg, dict) else previous_end)
    return out


def _end(seg):
    return seg["b"][0] if isinstance(seg, dict) else seg


def orient(rings):
    """Esri polygons: outer rings clockwise, holes counter-clockwise (y up).

    SVG fills by winding, and flipping y reverses every ring, so orientation
    is rebuilt from nesting: a ring inside an odd number of others is a hole.
    """
    flat = [flatten(r) for r in rings]
    out = []
    for i, ring in enumerate(rings):
        depth = sum(inside(flat[i][0], flat[j]) for j in range(len(rings)) if j != i)
        clockwise = signed_area(flat[i]) < 0
        out.append(ring if clockwise == (depth % 2 == 0) else reverse(ring))
    return out


def convert(path):
    root = ET.parse(path).getroot()
    box = [float(v) for v in re.split(r"[\s,]+", root.get("viewBox").strip())] if root.get("viewBox") else \
        [0, 0, float(root.get("width")), float(root.get("height"))]
    width, height = box[2], box[3]
    to_cim = (1, 0, 0, -1, -box[0], height + box[1])  # y down -> y up, frame at 0,0
    graphics, number = [], None

    def walk(element, matrix, inherited):
        tag = local(element.tag)
        if tag in SKIP:
            return
        s = dict(inherited)
        s.update(styles(element))
        m = multiply(matrix, parse_transform(element.get("transform")))
        if tag == "text":
            tspans = [e for e in element.iter() if (e.text or "").strip()]
            size = float(re.sub(r"px$", "", s["font-size"]))
            nonlocal number
            number = {"font": s["font-family"].strip("'\""), "size": size,
                      "x": float(element.get("x")), "baseline": float(element.get("y")),
                      "colour": colour(s.get("fill", "#000")), "sample": tspans[0].text.strip()}
            if abs(m[0] - 1) > 1e-6 or abs(m[3] - 1) > 1e-6 or m[4] or m[5]:
                raise ValueError("transformed text is not supported")
            return
        if tag in ("path", "rect"):
            d = element.get("d") if tag == "path" else rect_path(s)
            fill = colour(s.get("fill", "#000"))
            stroke = colour(s.get("stroke"))
            if float(s.get("opacity", 1)) == 0 or (fill is None and stroke is None):
                return
            pen = RingPen()
            parse_path(d, pen)
            pen._close()
            scale = (abs(m[0] * m[3] - m[1] * m[2])) ** 0.5
            rings = []
            for ring in pen.rings:
                out = []
                for seg in ring:
                    pts = [apply(to_cim, apply(m, p)) for p in seg[1:]]
                    pts = [[round(x, PRECISION), round(y, PRECISION)] for x, y in pts]
                    if seg[0] in "ML":
                        out.append(pts[0])
                    else:  # Esri JSON cubic: {"b": [end, control1, control2]}
                        out.append({"b": [pts[2], pts[0], pts[1]]})
                rings.append(out)
            if rings:
                graphics.append({"fill": fill, "stroke": stroke,
                                 "stroke_width": round(float(s.get("stroke-width", 1)) * scale, PRECISION),
                                 "curveRings": orient(rings)})
            return
        for child in element:
            walk(child, m, {k: v for k, v in s.items() if k in ("fill", "stroke", "stroke-width", "font-family", "font-size")})

    walk(root, (1, 0, 0, 1, 0, 0), {})
    if number is None:
        raise ValueError("%s has no placeholder number" % path)
    number["baseline"] = round(height - number["baseline"], PRECISION)  # to y up
    return {"source": os.path.basename(path), "width": width, "height": height,
            "number": number, "graphics": graphics}


# ------------------------------ Numeral fit ------------------------------ #
# The numerals are Bahnschrift (Windows' DIN 1451-based face), SemiBold, and
# semi-condensed for three digits. It was chosen over the signs' own Roadgeek
# Series D/C on a board of candidates rendered by Pro at 1:30,000: it reads
# more solidly at a quarter inch. Bahnschrift is a variable font, so weight
# and width are axes (Pro: CIMTextSymbol.fontVariationSettings). It is a
# Microsoft-supplied Windows font, fine for Pro layouts and PDFs; vector
# tiles would redistribute its glyphs (see the README).
NUMERAL_FILE = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "bahnschrift.ttf")
NUMERALS = {2: {"font": "Bahnschrift", "axes": {"wght": 600, "wdth": 100}},
            3: {"font": "Bahnschrift", "axes": {"wght": 600, "wdth": 87.5}}}

# A sign's numerals are sized for a 24-inch sign seen from a car. On a map
# the shield is a quarter inch, so the same proportions leave the numbers
# touching the frame. fit_numerals() starts from the sign's numeral height,
# then shrinks the numbers, about the centre the sign design puts them on,
# until the widest possible numbers keep a margin from every edge of the
# field behind them. The centre never moves: the templates already place
# each number where it reads as centred (the Interstate's a little above the
# middle of its tapering field, the beehive's just above the door), and
# moving it for a larger size looks off.

# Clearance as a fraction of shield height: 7.5% (1.2 pt on a 16 pt shield)
# for the Interstate and US frames. The beehive's door sits just under its
# numbers, so 7.5% there shrinks them below the layout standard's type
# floor; it gets 5%.
MARGINS = {"I": 0.075, "US": 0.075, "SR": 0.05}
FIT_PX = 480                 # raster height used for fitting
TEMPLATE_FIGURE = 0.571      # the templates' Roadgeek 2005 numerals: height in em
WORST = {2: ["33", "30", "88", "66", "44", "1"],
         3: ["466", "644", "888", "300", "89A", "111"]}


def _raster(shield):
    """RGB raster of the shield plus the mask of the field behind its number."""
    from PIL import Image, ImageChops, ImageDraw
    import numpy as np

    s = FIT_PX / shield["height"]
    img = Image.new("RGB", (round(shield["width"] * s), FIT_PX), (255, 0, 255))
    for g in shield["graphics"]:
        if not g["fill"]:
            continue
        mask = Image.new("L", img.size, 0)
        for ring in g["curveRings"]:
            m = Image.new("L", img.size, 0)
            ImageDraw.Draw(m).polygon([(x * s, (shield["height"] - y) * s) for x, y in flatten(ring, 24)], fill=255)
            mask = ImageChops.add(mask, m) if signed_area(flatten(ring)) < 0 else ImageChops.subtract(mask, m)
        img.paste(Image.new("RGB", img.size, g["fill"]), (0, 0), mask)
    n = shield["number"]
    a = np.asarray(img).astype(int)
    cy = round((shield["height"] - n["baseline"] - TEMPLATE_FIGURE / 2 * n["size"]) * s)
    cx = round(n["x"] * s)
    same = np.all(np.abs(a - a[cy, cx]) < 40, axis=2)
    return same, (cx, cy), s


def _connected(mask, seed):
    from PIL import Image, ImageDraw
    import numpy as np

    im = Image.fromarray(mask.astype("uint8") * 128).copy()  # fromarray images are read-only
    ImageDraw.floodfill(im, seed, 255, thresh=0)
    return np.asarray(im) == 255


def numeral_font(axes, px, path=NUMERAL_FILE):
    """Pillow font at the given variable-font axes."""
    from fontTools.ttLib import TTFont
    from PIL import ImageFont

    font = ImageFont.truetype(path, max(1, px))
    order = [a.axisTag for a in TTFont(path, lazy=True)["fvar"].axes]
    font.set_variation_by_axes([axes[tag] for tag in order])
    return font


def figure_height(axes, path=NUMERAL_FILE):
    """Height of the numeral '0' above the baseline, in em."""
    return -numeral_font(axes, 1000, path).getbbox("0", anchor="ls")[1] / 1000


def _ink(shield, font, text, baseline, s, shape):
    from PIL import Image, ImageDraw
    import numpy as np

    m = Image.new("L", (shape[1], shape[0]), 0)
    ImageDraw.Draw(m).text((shield["number"]["x"] * s, (shield["height"] - baseline) * s),
                           text, font=font, fill=255, anchor="ms")
    return np.asarray(m) > 127


def fit_numerals(shield, digits, margin, path=NUMERAL_FILE):
    """(size, baseline, scale, figure height): the largest numerals, about the
    design's centre, keeping margin (a fraction of the shield height) from the frame."""
    from PIL import Image, ImageFilter
    import numpy as np

    same, seed, s = _raster(shield)
    field = _connected(same, seed)
    grow = 2 * round(margin * FIT_PX) + 1
    frame = Image.fromarray((~field).astype("uint8") * 255)
    allowed = np.asarray(frame.filter(ImageFilter.MaxFilter(grow))) == 0
    n = shield["number"]
    axes = NUMERALS[digits]["axes"]
    fh = figure_height(axes, path)
    centre = n["baseline"] + TEMPLATE_FIGURE / 2 * n["size"]
    sign_size = TEMPLATE_FIGURE * n["size"] / fh             # the sign's numeral height
    for k in [1 - i * 0.01 for i in range(41)]:              # down to 60% of it
        size = sign_size * k
        baseline = centre - fh / 2 * size
        font = numeral_font(axes, round(size * s), path)
        if all(not (_ink(shield, font, t, baseline, s, field.shape) & ~allowed).any() for t in WORST[digits]):
            return round(size, 2), round(baseline, 2), round(k, 2), round(fh, 4)
    raise ValueError("no numeral size fits %s" % shield["source"])


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[1])
    parser.add_argument("folder", help="folder holding the six template .svg files")
    parser.add_argument("--numeral-font", default=NUMERAL_FILE, help="numeral font file (default: Bahnschrift)")
    parser.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "mutcd_shields.json"))
    args = parser.parse_args()

    data = {"source": {
        "templates": "Wikimedia Commons, public domain (MUTCD / UDOT sign designs)",
        "url": "https://commons.wikimedia.org/wiki/File:<template name>",
        "note": "Units are the template's (y up, frame from 0,0). Regenerate with build_shields.py."},
        "shields": {key: convert(os.path.join(args.folder, name)) for key, name in TEMPLATES.items()}}
    data["source"]["fit"] = (
        "number.font/axes/size/baseline are the map numerals, fitted so the widest keep number.margin of "
        "the shield height from the frame, about the sign's own numeral centre; template_* are the sign's.")
    for key, shield in data["shields"].items():
        n = shield["number"]
        digits, margin = int(key[-1]), MARGINS[key.split("-")[0]]
        size, baseline, k, fh = fit_numerals(shield, digits, margin, args.numeral_font)
        n.update({"template_font": n["font"], "template_size": round(n["size"], 2),
                  "template_baseline": n["baseline"], "margin": margin,
                  "font": NUMERALS[digits]["font"], "axes": NUMERALS[digits]["axes"],
                  "figure_height": fh, "size": size, "baseline": baseline})
        print("%-5s %-22s %4gx%-4g %d graphics  %s %s at %d%% of the sign's numeral height" % (
            key, shield["source"], shield["width"], shield["height"], len(shield["graphics"]),
            n["font"], n["axes"], k * 100))
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
        f.write("\n")
    print("wrote", args.out, os.path.getsize(args.out), "bytes")


if __name__ == "__main__":
    main()
