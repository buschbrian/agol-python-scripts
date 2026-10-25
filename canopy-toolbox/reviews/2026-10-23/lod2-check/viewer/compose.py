r"""Combine each bookmark's three screenshots into one labelled image (October 24, 2026).

    python reviews/2026-10-23/lod2-check/viewer/compose.py SCREENS_DIR web/bookmarks.json

Pillow (ArcGIS Pro's Python has it). Reads SCREENS_DIR\<id>_<esri|roofer|threeway>.png, writes SCREENS_DIR\composite\<id>.png:
the bookmark's title and numbers on top, the three scenes side by side with their names, and the colour key below.
"""
import json
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

PANELS = [("esri", "Esri LOD2.0 hybrid"), ("roofer", "roofer LoD2.2 only"), ("threeway", "three-way hybrid")]
KEY = [((207, 213, 219), "roofer LoD2.2"), ((91, 143, 214), "Esri LOD2.0"), ((240, 162, 75), "Esri LOD1.2")]


def font(size, bold=False):
    for name in (("arialbd.ttf" if bold else "arial.ttf"), "segoeui.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def compose(screens, bookmarks):
    out = Path(screens)/"composite"
    out.mkdir(exist_ok=True)
    made = []
    for b in bookmarks:
        files = [Path(screens)/f"{b['id']}_{k}.png" for k, _ in PANELS]
        if not all(f.exists() for f in files):
            continue
        imgs = [Image.open(f).convert("RGB") for f in files]
        w, h = imgs[0].size
        top, bottom, gap = 92, 40, 6
        sheet = Image.new("RGB", (3*w+2*gap, top+h+bottom), (255, 255, 255))
        d = ImageDraw.Draw(sheet)
        r, e = b["roofer"], b["esri_lod20"]
        d.text((10, 6), b["title"], font=font(22, True), fill=(31, 35, 40))
        d.text((10, 36), f"{b['type']}, {b['footprint_m2']} m2, lidar roof cover {b['roof_cover_pct']}%   |   three-way hybrid uses {b['three_way_level']}",
               font=font(16), fill=(60, 66, 74))
        d.text((10, 60), f"roofer: {r['verdict']}{' (' + r['note'] + ')' if r['note'] else ''}, p95 {r['p95_m']} m, within 1 m {r['within_1_pct']}%   |   "
               f"Esri LOD2.0: {e['verdict']}{' (' + e['note'] + ')' if e['note'] else ''}, p95 {e['p95_m']} m, within 1 m {e['within_1_pct']}%   |   "
               f"Esri LOD1.2: p95 {b['esri_lod12']['p95_m']} m", font=font(16), fill=(60, 66, 74))
        for i, ((_, label), img) in enumerate(zip(PANELS, imgs)):
            x = i*(w+gap)
            sheet.paste(img, (x, top))
            d.rectangle([x+8, top+8, x+8+len(label)*9+14, top+36], fill=(255, 255, 255))
            d.text((x+14, top+11), label, font=font(17, True), fill=(31, 35, 40))
        x = 10
        for rgb, label in KEY:
            d.rectangle([x, top+h+12, x+16, top+h+28], fill=rgb, outline=(120, 120, 120))
            d.text((x+24, top+h+11), label, font=font(16), fill=(60, 66, 74))
            x += 24+len(label)*9+30
        d.text((x+10, top+h+11), "Unvalidated LiDAR planning estimates; flat ground, buildings lowered to it; edges drawn on roof facets.",
               font=font(15), fill=(120, 126, 134))
        path = out/f"{b['id']}.png"
        sheet.save(path)
        made.append(str(path))
    return made


if __name__ == "__main__":
    made = compose(sys.argv[1], json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))["bookmarks"])
    print(len(made), "composites")
