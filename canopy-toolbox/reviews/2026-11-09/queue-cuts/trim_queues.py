"""Take unanswered items off the footprint review page (Brian, November 9). Run with the Pro Python, server stopped.

    trim_queues.py DATA

Removes open tree_rejects items, and open tree-sample items past 30 answered-or-kept per band for 8 m and up. Backs up index.json
first and writes parked-items.csv beside this file. Items with an answer or a note are never removed. Answers are not touched.
Undo: copy index.before-trim-20261109.json over index.json.
"""

import csv
import json
import os
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = 30
TALL = ((8, 12, "8-12"), (12, 20, "12-20"), (20, 1e9, "20+"))


def band_of(height):
    return next((name for low, high, name in TALL if low <= height < high), None)


def main(data):
    if (data / "index.before-trim-20261109.json").exists():
        raise SystemExit("already trimmed")
    built = json.loads((data / "index.json").read_text(encoding="utf-8"))
    with open(data / "answers" / "footprint-review-answers.csv", encoding="utf-8", newline="") as f:
        rows = {r["ITEM_ID"]: r for r in csv.DictReader(f)}
    answered = lambda i: bool(rows.get(i["id"], {}).get("ANSWER", "").strip())
    touched = lambda i: i["id"] in rows

    parked = []
    for item in built["items"]:
        if item["queue"] == "tree_rejects" and not touched(item):
            parked.append((item, "exclusion stands: 36 of 43 answered were not a tree, none a missed tree"))

    bundles = {}
    bands = {}
    for item in (i for i in built["items"] if i["queue"] == "trees" and i["group"] == "sample"):
        bundle = bundles.setdefault(item["bundle"], json.loads((data / "bundles" / item["bundle"]).read_text(encoding="utf-8")))
        name = band_of(float(re.match(r"[\d.]+", bundle[item["id"]]["facts"]["Height"]).group()))
        if name:
            bands.setdefault(name, []).append(item)
    for name, items in bands.items():
        keep = sum(answered(i) or touched(i) for i in items)
        for item in sorted((i for i in items if not touched(i)), key=lambda i: i["order"]):
            keep += 1
            if keep > TARGET:
                parked.append((item, f"tree sample: 30 per band is enough for {name} m"))

    gone = {i["id"] for i, _ in parked}
    if any(i in rows for i in gone):
        raise SystemExit("an item with an answer or note was selected")
    shutil.copy2(data / "index.json", data / "index.before-trim-20261109.json")
    items = [i for i in built["items"] if i["id"] not in gone]
    counts = {}
    for item in items:
        counts.setdefault(item["queue"], {}).setdefault(item["group"], 0)
        counts[item["queue"]][item["group"]] += 1
    built.update(counts=counts, items=items, trimmed_20261109=len(gone))
    partial = data / "index.partial"
    partial.write_text(json.dumps(built, separators=(",", ":")), encoding="utf-8")
    os.replace(partial, data / "index.json")

    with open(HERE / "parked-items.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["ITEM_ID", "QUEUE", "GROUP", "REASON"])
        writer.writerows([i["id"], i["queue"], i["group"], why] for i, why in parked)
    print(len(gone), "parked", sorted(Counter((i["queue"], i["group"]) for i, _ in parked).items()))
    print("left in tree sample by band", {n: (len(v) - sum(i["id"] in gone for i in v), sum(not touched(i) and i["id"] not in gone for i in v)) for n, v in bands.items()})


if __name__ == "__main__":
    main(Path(sys.argv[1]))
