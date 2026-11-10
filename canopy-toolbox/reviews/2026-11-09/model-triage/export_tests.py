"""Blind sheets and batches for the two simple-question tests. Run with the Pro Python.

    export_tests.py OUT

OUT/batches and OUT/sheets go to the model. OUT/key/key.csv maps sheet numbers to items and stays with the grader.
"""

import base64
import csv
import io
import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pyproj import Transformer

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "model-assist"))
import export_sheets as base  # noqa: E402

SEED = 20261110
BATCHES = 6
SMALL_FACTS = ("LiDAR area", "LiDAR roof height (median)")
TREE_FACTS = ("Height", "Crown width", "Crown outline area", "LiDAR points in the model", "October 22 treetops inside",
              "Trunk inside a county footprint", "Outline over county footprints")
OPTIONS = {
    "small": [["REAL_STRUCTURE", "A real structure: shed, outbuilding, garage, addition, porch or separate building"],
              ["NOT_STRUCTURE", "Not a structure: vehicle, trailer, RV, tree, or nothing"], ["UNSURE", "The sheet does not settle it"]],
    "tree": [["ONE_TREE", "The red points are one complete, well-shaped tree"],
             ["PROBLEM", "Shrubs or brush, several trees joined, part of a tree, not a tree, wrong shape, or takes in a roof or shed"],
             ["UNSURE", "The sheet does not settle it"]],
}
BRIEF = """# Blind visual review of LiDAR objects, Millcreek, Utah

Answer only from the sheet images and the facts in your batch file. Read only your batch file and the sheets it lists.

Every sheet has a LiDAR panel and an imagery panel covering the same extent.
- LiDAR surface, autumn 2023: grey hillshade is ground, green is tree canopy 2 m or taller, yellow through orange to magenta
  is a roof from 0 m to 12 m or taller.
- NAIP imagery, July 2024: newer than the LiDAR and can sit up to about 2 m off it.
- RED outline: the object in question. WHITE: county footprint. CYAN: another LiDAR outline.

Task small: what is this small red outline? Task tree: the red outline is an automatic tree model. Its sheet also has two side
views underneath, looking north and looking west, at equal scale. Red points are this model above 2 m, orange are its points
under 2 m, magenta and pale pink are other tree models, grey is other vegetation nearby, the brown line is the ground, and the
dashed green line is 2 m above the ground.

Pick one code from the task's options. Use UNSURE when the sheet does not settle it. Confidence: high only when the sheet
clearly settles it, medium for a likely reading, low otherwise.

Write one JSON object per line and nothing else, one per item, in batch order:
{"id":"S001","answer":"CODE","confidence":"high|medium|low","note":"under 15 words on what you saw"}
"""


def data_uri_image(uri):
    return Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))).convert("RGB")


def add_profile(path, item):
    top = Image.open(path).convert("RGB")
    profile = data_uri_image(item["profile"])
    width = top.width
    height = round(profile.height * width / profile.width)
    profile = profile.resize((width, height), Image.BICUBIC)
    out = Image.new("RGB", (width, top.height + height + 34), (245, 245, 245))
    out.paste(top, (0, 0))
    ImageDraw.Draw(out).text((6, top.height + 7), "Side views: looking north (left), looking west (right)", fill=(0, 0, 0),
                             font=ImageFont.truetype("arial.ttf", 18))
    out.paste(profile, (0, top.height + 34))
    out.save(path, optimize=True)


def main():
    out = Path(sys.argv[1])
    with open(base.REVIEW / "answers" / "footprint-review-answers.csv", encoding="utf-8-sig", newline="") as f:
        answered = {(r["QUEUE"], r["ITEM_ID"]) for r in csv.DictReader(f)}
    index = json.loads((base.DATA / "index.json").read_text(encoding="utf-8"))["items"]
    chosen = []
    for entry in index:
        key = (entry["queue"], entry["id"])
        if key not in answered:
            continue
        if entry["queue"] == "outlines" and entry["group"] in ("decide_small", "auto_vehicles"):
            chosen.append((entry, "small", "A"))
        elif entry["queue"] == "outlines2" and entry["group"] in ("decide_small", "check_touching"):
            chosen.append((entry, "small", "A-secondary"))
        elif entry["queue"] == "trees" and entry["group"] == "sample":
            chosen.append((entry, "tree", "B"))
    random.Random(SEED).shuffle(chosen)
    print(len(chosen), "items")

    for folder in ("batches", "sheets", "key"):
        (out / folder).mkdir(parents=True, exist_ok=True)
    naip, to_utm, offset = base.Naip(), Transformer.from_crs(4326, 6341, always_xy=True), base.datum_offset()
    bundles, rows, key_rows = {}, [], []
    for n, (entry, task, test) in enumerate(chosen, 1):
        bundle = bundles.setdefault(entry["bundle"], json.loads((base.DATA / "bundles" / entry["bundle"]).read_text(encoding="utf-8")))
        item = bundle[entry["id"]]
        sid = f"S{n:03d}"
        path = out / "sheets" / f"{sid}.png"
        base.sheet(item, naip, to_utm, offset, path)
        if task == "tree":
            add_profile(path, item)
        allowed = TREE_FACTS if task == "tree" else SMALL_FACTS
        rows.append({"id": sid, "task": task, "facts": {k: item["facts"][k] for k in allowed if k in item["facts"]}, "sheet": str(path)})
        key_rows.append({"SHEET": sid, "ITEM_ID": entry["id"], "QUEUE": entry["queue"], "TEST": test, "TASK": task})

    with open(out / "key" / "key.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(key_rows[0]))
        writer.writeheader()
        writer.writerows(key_rows)
    (out / "batches" / "BRIEF.md").write_text(BRIEF, encoding="utf-8")
    size = len(rows) // BATCHES + 1
    for n in range(BATCHES):
        part = rows[n * size:(n + 1) * size]
        (out / "batches" / f"batch_{n + 1:02d}.json").write_text(
            json.dumps({"options": OPTIONS, "items": part}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("tests", {t: sum(r["TEST"] == t for r in key_rows) for t in ("A", "A-secondary", "B")})


if __name__ == "__main__":
    main()
