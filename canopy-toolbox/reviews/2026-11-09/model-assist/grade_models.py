"""Grade the model pass against Brian's committed answers and list what still needs him.

    grade_models.py OUT DEST

OUT is the export_sheets.py folder holding result_*.jsonl; DEST receives the CSVs and summary.json.
"""

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANSWERS = HERE.parents[1] / "2026-10-23" / "footprint-review" / "answers" / "footprint-review-answers.csv"
QUEUE = Path(r"C:\Users\Brian\Documents\Codex\2026-10-24\go-x20\outputs\lidar-human-review-queue.csv")
INDEX = Path(r"H:\lidar\2023-salt-lake-valley\runs\footprint-review-20261023\data\index.json")
MIN_AGREE, MIN_ITEMS = 0.85, 10
OPEN_TASKS = ("reshaped", "small", "tangle")
HOLD = {"UNSURE", "NEEDS_EDIT"}


def results(folder):
    rows = {}
    for path in sorted(folder.glob("result_*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row["id"] in rows:
                    raise SystemExit(f"duplicate {row['id']} in {path}")
                rows[row["id"]] = row
    return rows


def write(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def footprints(out, dest):
    items = {}
    for path in sorted((out / "footprints").glob("batch_*.json")):
        batch = json.loads(path.read_text(encoding="utf-8"))
        for item in batch["items"]:
            items[item["id"]] = (item["task"], {c for c, _ in batch["tasks"][item["task"]]})
    got = results(out / "footprints")
    if set(got) != set(items):
        raise SystemExit(f"missing {sorted(set(items) - set(got))[:10]}, extra {sorted(set(got) - set(items))[:10]}")
    for key, row in got.items():
        if row["answer"] not in items[key][1]:
            raise SystemExit(f"{key}: {row['answer']} is not an option")
    with open(ANSWERS, encoding="utf-8-sig", newline="") as f:
        key = {r["ITEM_ID"]: r["ANSWER"] for r in csv.DictReader(f) if r["QUEUE"] == "outlines2"}
    groups = {i["id"]: i["group"] for i in json.loads(INDEX.read_text(encoding="utf-8"))["items"] if i["queue"] == "outlines2"}
    tally = defaultdict(Counter)
    confusion = Counter()
    for item, row in got.items():
        if item in key:
            task, hit = items[item][0], row["answer"] == key[item]
            tally[task]["all"] += 1
            tally[task]["all_hit"] += hit
            if row["confidence"] == "high":
                tally[task]["high"] += 1
                tally[task]["high_hit"] += hit
            if not hit:
                confusion[(task, key[item], row["answer"])] += 1
    passed = {t: tally[t]["high"] >= MIN_ITEMS and tally[t]["high_hit"] / tally[t]["high"] >= MIN_AGREE for t in OPEN_TASKS}
    rows = []
    for item, row in got.items():
        task = items[item][0]
        if item in key:
            status = "test"
        elif passed[task] and row["confidence"] == "high" and row["answer"] not in HOLD:
            status = "settled_provisionally"
        else:
            status = "needs_brian"
        rows.append({"ITEM_ID": item, "GROUP": groups[item], "TASK": task, "MODEL_ANSWER": row["answer"], "CONFIDENCE": row["confidence"],
                     "NOTE": row.get("note", ""), "STATUS": status, "BRIAN_ANSWER": key.get(item, "")})
    write(dest / "model-footprint-answers.csv", sorted(rows, key=lambda r: (r["STATUS"], r["GROUP"], r["ITEM_ID"])))
    return {"tasks": {t: dict(tally[t]) for t in tally}, "passed": passed,
            "open": dict(Counter(r["STATUS"] for r in rows)),
            "needs_brian_by_group": dict(Counter(r["GROUP"] for r in rows if r["STATUS"] == "needs_brian")),
            "top_misses": [[*k, v] for k, v in confusion.most_common(12)]}


def examples(out, dest):
    got = results(out / "examples")
    with open(QUEUE, encoding="utf-8-sig", newline="") as f:
        first = list(csv.DictReader(f))
    if {r["unit_id"] for r in first} != set(got):
        raise SystemExit("example ids do not match the queue")
    rows = []
    for row in first:
        second = got[row["unit_id"]]
        agree = row["assistant_label"] == second["answer"]
        unsure = "UNSURE" in (row["assistant_label"], second["answer"])
        rows.append({"NUMBER": row["number"], "PACKET": row["packet"], "UNIT_ID": row["unit_id"], "FIRST_LABEL": row["assistant_label"],
                     "FIRST_CONFIDENCE": row["assistant_confidence"], "SECOND_LABEL": second["answer"], "SECOND_CONFIDENCE": second["confidence"],
                     "SECOND_NOTE": second.get("note", ""), "STATUS": "needs_brian" if unsure or not agree else "two_reads_agree",
                     "SHEET": row["evidence_sheet"]})
    write(dest / "model-example-second-read.csv", rows)
    return {"counts": dict(Counter(r["STATUS"] for r in rows)),
            "needs_brian_by_packet": dict(Counter(r["PACKET"] for r in rows if r["STATUS"] == "needs_brian"))}


if __name__ == "__main__":
    source, target = Path(sys.argv[1]), Path(sys.argv[2])
    target.mkdir(parents=True, exist_ok=True)
    summary = {"footprints": footprints(source, target), "examples": examples(source, target)}
    (target / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
