"""Park the open trees in the merged and over_roof queues (Brian, November 10). Run with the Pro Python, server stopped.

    park_tree_queues.py DATA

Backs up index.json, then removes every merged or over_roof tree with no answer and no note, and appends them to
parked-items.csv. Undo: copy index.before-park-20261110.json over index.json.
"""

import csv
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
GROUPS = ("merged", "over_roof")
REASON = "tree queue parked: the random sample already checked these cues (test C)"


def main(data):
    if (data / "index.before-park-20261110.json").exists():
        raise SystemExit("already parked")
    built = json.loads((data / "index.json").read_text(encoding="utf-8"))
    with open(data / "answers" / "footprint-review-answers.csv", encoding="utf-8", newline="") as f:
        touched = {r["ITEM_ID"] for r in csv.DictReader(f)}
    parked = [i for i in built["items"] if i["queue"] == "trees" and i["group"] in GROUPS and i["id"] not in touched]
    kept = sum(1 for i in built["items"] if i["queue"] == "trees" and i["group"] in GROUPS and i["id"] in touched)
    gone = {i["id"] for i in parked}
    shutil.copy2(data / "index.json", data / "index.before-park-20261110.json")
    items = [i for i in built["items"] if i["id"] not in gone]
    counts = {}
    for item in items:
        counts.setdefault(item["queue"], {}).setdefault(item["group"], 0)
        counts[item["queue"]][item["group"]] += 1
    built.update(counts=counts, items=items, parked_20261110=len(gone))
    partial = data / "index.partial"
    partial.write_text(json.dumps(built, separators=(",", ":")), encoding="utf-8")
    os.replace(partial, data / "index.json")
    with open(HERE / "parked-items.csv", "a", encoding="utf-8", newline="") as f:
        csv.writer(f, lineterminator="\n").writerows([i["id"], i["queue"], i["group"], REASON] for i in parked)
    print(len(gone), "parked", dict(Counter(i["group"] for i in parked)), "kept with an answer or note:", kept)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
