"""Blind spot-check of the model's confident ONE_TREE calls on the open tall trees, by the rule in README.md.

    spot_check.py add DATA OUT      put the spot-check group on the review page (server stopped); OUT holds key/ and results/
    spot_check.py score DATA OUT    score Brian's spot-check answers and list what a pass would settle

The page shows no model call. The group mixes the sampled ONE_TREE calls with other trees, in random order.
"""

import csv
import json
import os
import random
import shutil
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEED = 20261110
CHECK, FILLER, GROUP = 30, 15, "spot_check"
MIN_SCORED, MIN_MATCH = 20, 0.85


def calls(out):
    with open(out / "key" / "key.csv", encoding="utf-8-sig", newline="") as f:
        key = {r["SHEET"]: r for r in csv.DictReader(f)}
    rows = {}
    for path in sorted((out / "results").glob("result_*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows[key[r["id"]]["ITEM_ID"]] = {**r, "GROUP": key[r["id"]]["TEST"]}
    if len(rows) != len(key):
        raise SystemExit(f"{len(key) - len(rows)} sheets have no answer")
    return rows


def confident(r):
    return r["answer"] == "ONE_TREE" and r["confidence"] == "high"


def add(data, out):
    if (data / "index.before-spotcheck-20261110.json").exists():
        raise SystemExit("spot-check already added")
    model = calls(out)
    yes = sorted(i for i, r in model.items() if confident(r))
    rest = sorted(i for i, r in model.items() if not confident(r))
    rng = random.Random(SEED)
    picked = rng.sample(yes, min(CHECK, len(yes)))
    filler = rng.sample(rest, min(FILLER, len(rest)))
    mixed = picked + filler
    rng.shuffle(mixed)
    built = json.loads((data / "index.json").read_text(encoding="utf-8"))
    by_id = {i["id"]: i for i in built["items"]}
    with open(data / "answers" / "footprint-review-answers.csv", encoding="utf-8", newline="") as f:
        if any(r["ITEM_ID"] in by_id and r["ITEM_ID"] in set(mixed) for r in csv.DictReader(f)):
            raise SystemExit("a picked tree already has an answer or note")
    shutil.copy2(data / "index.json", data / "index.before-spotcheck-20261110.json")
    moved = [dict(by_id[i], group=GROUP, from_group=by_id[i]["group"]) for i in mixed]
    first = next(n for n, i in enumerate(built["items"]) if i["queue"] == "trees")
    items = [i for i in built["items"] if i["id"] not in set(mixed)]
    items[first:first] = moved
    counts = {}
    for item in items:
        counts.setdefault(item["queue"], {}).setdefault(item["group"], 0)
        counts[item["queue"]][item["group"]] += 1
    built.update(counts=counts, items=items)
    partial = data / "index.partial"
    partial.write_text(json.dumps(built, separators=(",", ":")), encoding="utf-8")
    os.replace(partial, data / "index.json")
    with open(HERE / "spot-check-items.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["ITEM_ID", "FROM_GROUP", "ROLE"])
        writer.writerows([i, by_id[i]["group"], "check" if i in picked else "filler"] for i in mixed)
    print(f"{len(yes)} confident ONE_TREE calls of {len(model)}; spot-check group: {len(picked)} checks + {len(filler)} filler")


def score(data, out):
    model = calls(out)
    with open(HERE / "spot-check-items.csv", encoding="utf-8-sig", newline="") as f:
        roles = {r["ITEM_ID"]: r["ROLE"] for r in csv.DictReader(f)}
    with open(data / "answers" / "footprint-review-answers.csv", encoding="utf-8", newline="") as f:
        answers = {r["ITEM_ID"]: r["ANSWER"] for r in csv.DictReader(f) if r["ANSWER"].strip()}
    checks = [i for i, role in roles.items() if role == "check" and i in answers]
    scored = [i for i in checks if answers[i] != "UNSURE"]
    match = sum(answers[i] == "ONE_TREE" for i in scored)
    passed = len(scored) >= MIN_SCORED and match / len(scored) >= MIN_MATCH if scored else False
    settle = sorted(i for i, r in model.items() if confident(r) and i not in roles)
    result = {"checks_answered": len(checks), "scored": len(scored), "one_tree": match,
              "rate": round(match / len(scored), 3) if scored else None, "passes": passed,
              "his_answers_on_checks": dict(Counter(answers[i] for i in checks)),
              "would_settle": len(settle), "would_settle_by_group": dict(Counter(model[i]["GROUP"] for i in settle))}
    (HERE / "spot-check-score.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    {"add": add, "score": score}[sys.argv[1]](Path(sys.argv[2]), Path(sys.argv[3]))
