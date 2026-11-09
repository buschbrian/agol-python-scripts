"""Blind review sheets and batches for a first model pass. Run with the Pro Python (-I).

    export_sheets.py OUT

Footprints: every answered outlines2 item (the test) and every open item in the five review groups, shuffled together.
Each sheet is the page's LiDAR chip beside local NAIP 2024, nothing else. Answers, groups and rule proposals stay out.
Examples: the 222 from the October 25 human queue; assistant labels stay out.
"""

import base64
import csv
import io
import json
import random
import shutil
import sys
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image, ImageDraw, ImageFont
from pyproj import Transformer
from rasterio.merge import merge

SEED = 20261109
HERE = Path(__file__).resolve().parent
REVIEW = HERE.parents[1] / "2026-10-23" / "footprint-review"
DATA = Path(r"H:\lidar\2023-salt-lake-valley\runs\footprint-review-20261023\data")
NAIP = Path(r"H:\lidar\2023-salt-lake-valley\naip\naip2024-tiles")
OUTPUTS = Path(r"C:\Users\Brian\Documents\Codex\2026-10-24\go-x20\outputs")
PANEL = 560
OPEN_GROUPS = {"decide_reshaped", "answer_reshaped", "decide_small", "check_touching", "decide_tangle"}
TASK_OF = {"decide_joins": "joins", "check_county_kept": "kept", "decide_reshaped": "reshaped", "answer_reshaped": "reshaped",
           "decide_tangle": "tangle", "decide_small": "small", "check_touching": "small"}

RESHAPED = [["UNDER_TREES", "LiDAR covered by trees: keep the county outline"],
            ["LIDAR_RIGHT", "Redraw it from the LiDAR outline"],
            ["SHIFT_COUNTY", "County shape is right but offset: shift it onto the LiDAR"],
            ["ADD_TO_COUNTY", "County is right for part: add the extra roof (addition, garage, porch) from the LiDAR"],
            ["SPLIT_BUILDINGS", "Several buildings inside one outline: split them"],
            ["COUNTY_RIGHT", "The county outline is right as it is"],
            ["NEEDS_EDIT", "Needs redrawing by hand"], ["NOT_A_BUILDING", "Not a building"], ["UNSURE", "Unsure"]]
TASKS = {
    "reshaped": RESHAPED,
    "tangle": RESHAPED + [["KEEP_UNITS", "Units: keep the county lines inside the LiDAR shape"]],
    "small": [["SHED", "A shed or outbuilding"],
              ["PART_OF_BUILDING", "Part of a house or garage (addition, porch, attached garage): join it"],
              ["OFFSET_SHED", "A shed whose county outline sits offset nearby"], ["VEHICLE", "A vehicle, trailer or RV"],
              ["NOT_A_BUILDING", "Not a building (tree or other)"], ["LIDAR_RIGHT", "A separate building to add"],
              ["NEEDS_EDIT", "Needs editing"], ["UNSURE", "Unsure"]],
    "kept": [["UNDER_TREES", "Still there, hidden by trees: keep the county outline"], ["GONE", "Gone"],
             ["SHIFT_COUNTY", "There, but the county outline is offset"],
             ["SHED", "A small shed or outbuilding the LiDAR missed"], ["NOT_A_BUILDING", "Not a building"], ["UNSURE", "Unsure"]],
    "joins": [["LIDAR_RIGHT", "The LiDAR outline is right: replace the county outline(s)"],
              ["KEEP_UNITS", "LiDAR outer shape is right; keep the county lines inside it (townhouses, units)"],
              ["COUNTY_RIGHT", "The county outline is right"], ["GONE", "The county building is gone; nothing replaces it"],
              ["UNDER_TREES", "Hidden under trees: keep the county outline"],
              ["NOT_A_BUILDING", "The red outline is not a building (vehicle, tree, other)"],
              ["NEEDS_EDIT", "Several problems: needs hand editing"], ["SHED", "A shed or small outbuilding"],
              ["SPLIT_BUILDINGS", "Separate buildings: split the LiDAR outline"], ["UNSURE", "Unsure"]],
}
LABELS = {"TREE": "Woody tree crown, branches or trunk (any height; includes overhanging branches)",
          "BUILDING_ROOF": "Roof of a building, including roof-mounted equipment",
          "WALL": "Building facade only (fences and freestanding walls are OTHER_STRUCTURE)",
          "WIRE": "Overhead wire or cable", "POLE": "Pole or mast: utility, light, sign or flag pole",
          "OTHER_STRUCTURE": "Fence, freestanding wall, carport, shade sail, playground, bridge, tank",
          "SHRUB_LOW_VEG": "Shrub, clipped hedge, garden bed, tall grass (not mown lawn)",
          "GROUND": "Bare ground, pavement, gravel, low hardscape or mown lawn", "VEHICLE": "Car, truck, trailer or other vehicle",
          "WATER": "Water surface", "MIXED": "The patch clearly holds two or more classes", "UNSURE": "Cannot tell"}


def datum_offset():
    import arcpy
    lon, lat = -111.84, 40.68
    point = arcpy.PointGeometry(arcpy.Point(lon, lat), arcpy.SpatialReference(4326))
    right = point.projectAs(arcpy.SpatialReference(6341), "WGS_1984_(ITRF08)_To_NAD_1983_2011").firstPoint
    x, y = Transformer.from_crs(4326, 6341, always_xy=True).transform(lon, lat)
    return right.X - x, right.Y - y


class Naip:
    def __init__(self):
        self.tiles = []
        for path in sorted(NAIP.glob("*/naip_*.tif")):
            with rasterio.open(path) as src:
                self.tiles.append((path, src.bounds))

    def crop(self, left, bottom, right, top):
        hits = [p for p, b in self.tiles if b.left < right and b.right > left and b.bottom < top and b.top > bottom]
        if not hits:
            return None
        sources = [rasterio.open(p) for p in hits]
        try:
            array, _ = merge(sources, bounds=(left, bottom, right, top), res=0.5, indexes=[1, 2, 3])
        finally:
            for src in sources:
                src.close()
        return Image.fromarray(np.moveaxis(array, 0, -1).astype("uint8"), "RGB")


def overlay(panel, item, scale):
    draw = ImageDraw.Draw(panel)
    def rings(key, colour, width):
        for ring in item.get(key) or []:
            draw.line([(x * scale, y * scale) for x, y in ring], fill=colour, width=width)
    rings("county_px", (255, 255, 255), 2)
    rings("cand_px", (0, 213, 255), 2)
    rings("focus_px", (255, 61, 245), 3)
    rings("outline_px", (255, 42, 42), 3)


def sheet(item, naip, to_utm, offset, path):
    chip = item["chip"]
    size, metres = chip["size"], chip["metres"]
    cell = metres / size
    xs, ys = [], []
    for key_px, key_ll in (("outline_px", "outline_ll"), ("county_px", "county_ll")):
        for ring_px, ring_ll in zip(item.get(key_px) or [], item.get(key_ll) or []):
            for (px, py), (lat, lon) in zip(ring_px, ring_ll):
                x, y = to_utm.transform(lon, lat)
                xs.append(x + offset[0] - cell * px)
                ys.append(y + offset[1] + cell * py)
    left, top = float(np.mean(xs)), float(np.mean(ys))
    lidar = Image.open(io.BytesIO(base64.b64decode(chip["uri"].split(",", 1)[1]))).convert("RGB").resize((PANEL, PANEL), Image.BICUBIC)
    photo = naip.crop(left, top - metres, left + metres, top)
    photo = photo.resize((PANEL, PANEL), Image.BICUBIC) if photo else Image.new("RGB", (PANEL, PANEL), (120, 120, 120))
    scale = PANEL / size
    overlay(lidar, item, scale)
    overlay(photo, item, scale)
    out = Image.new("RGB", (PANEL * 2 + 20, PANEL + 34), (245, 245, 245))
    font = ImageFont.truetype("arial.ttf", 18)
    draw = ImageDraw.Draw(out)
    draw.text((6, 7), f"LiDAR surface, autumn 2023 ({metres:.0f} m across)", fill=(0, 0, 0), font=font)
    draw.text((PANEL + 26, 7), "NAIP imagery, July 2024 (same extent)", fill=(0, 0, 0), font=font)
    out.paste(lidar, (0, 34))
    out.paste(photo, (PANEL + 20, 34))
    out.save(path, optimize=True)


def footprints(out):
    index = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
    with open(REVIEW / "answers" / "footprint-review-answers.csv", encoding="utf-8-sig", newline="") as f:
        answered = {r["ITEM_ID"] for r in csv.DictReader(f) if r["QUEUE"] == "outlines2"}
    chosen = [i for i in index["items"] if i["queue"] == "outlines2" and i["group"] in TASK_OF
              and (i["id"] in answered or i["group"] in OPEN_GROUPS)]
    test = sum(i["id"] in answered for i in chosen)
    print(f"{len(chosen)} items: {test} test, {len(chosen) - test} open")
    naip, to_utm, offset = Naip(), Transformer.from_crs(4326, 6341, always_xy=True), datum_offset()
    print("datum offset", offset)
    sheets = out / "footprints" / "sheets"
    sheets.mkdir(parents=True, exist_ok=True)
    random.Random(SEED).shuffle(chosen)
    bundles, rows = {}, []
    for entry in chosen:
        bundle = bundles.setdefault(entry["bundle"], json.loads((DATA / "bundles" / entry["bundle"]).read_text(encoding="utf-8")))
        item = bundle[entry["id"]]
        path = sheets / f"{entry['id']}.png"
        sheet(item, naip, to_utm, offset, path)
        facts = {k: v for k, v in item["facts"].items() if k not in ("Address (county)", "Parcel")}
        rows.append({"id": entry["id"], "task": TASK_OF[entry["group"]], "facts": facts, "sheet": str(path)})
    size = len(rows) // 6 + 1
    for n in range(6):
        (out / "footprints" / f"batch_{n + 1:02d}.json").write_text(
            json.dumps({"tasks": TASKS, "items": rows[n * size:(n + 1) * size]}, ensure_ascii=False, indent=1), encoding="utf-8")


def examples(out):
    with open(OUTPUTS / "lidar-human-review-queue.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    sheets = out / "examples" / "sheets"
    sheets.mkdir(parents=True, exist_ok=True)
    by_sheet = {}
    for row in rows:
        by_sheet.setdefault(row["evidence_sheet"], []).append(
            {"id": row["unit_id"], "number": int(row["number"]), "packet": row["packet"], "question": row["target_rule"]})
    names = sorted(by_sheet)
    for name in names:
        shutil.copy2(OUTPUTS / name, sheets / Path(name).name)
    size = len(names) // 5 + 1
    for n in range(5):
        part = [{"sheet": str(sheets / Path(name).name), "units": by_sheet[name]} for name in names[n * size:(n + 1) * size]]
        (out / "examples" / f"batch_{n + 1:02d}.json").write_text(json.dumps({"labels": LABELS, "sheets": part}, indent=1), encoding="utf-8")
    print(f"{len(rows)} examples on {len(names)} sheets")


if __name__ == "__main__":
    target = Path(sys.argv[1])
    footprints(target)
    examples(target)
