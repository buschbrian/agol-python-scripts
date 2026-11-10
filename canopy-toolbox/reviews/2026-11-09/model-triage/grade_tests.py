"""Grade the two simple-question tests against Brian's committed answers, by the rule in README.md.

    grade_tests.py OUT DEST

OUT holds key/key.csv and results/result_*.jsonl. DEST receives answers.csv and summary.json.
"""

import csv
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ANSWERS = HERE.parents[1] / "2026-10-23" / "footprint-review" / "answers" / "footprint-review-answers.csv"
MIN_ITEMS, MIN_MATCH = 10, 0.85
TRUTH = {
    "small": {"SHED": "REAL_STRUCTURE", "PART_OF_BUILDING": "REAL_STRUCTURE", "OFFSET_SHED": "REAL_STRUCTURE", "LIDAR_RIGHT": "REAL_STRUCTURE",
              "NOT_A_BUILDING": "NOT_STRUCTURE", "VEHICLE": "NOT_STRUCTURE"},
    "tree": {"ONE_TREE": "ONE_TREE", **{c: "PROBLEM" for c in ("SHRUBS", "BRUSH", "MERGED", "PART_OF_TREE", "NOT_A_TREE", "SHAPE_WRONG", "TREE_WITH_ROOF")}},
}
VALID = {"small": {"REAL_STRUCTURE", "NOT_STRUCTURE", "UNSURE"}, "tree": {"ONE_TREE", "PROBLEM", "UNSURE"}}


def main():
    out, dest = Path(sys.argv[1]), Path(sys.argv[2])
    with open(out / "key" / "key.csv", encoding="utf-8-sig", newline="") as f:
        key = {r["SHEET"]: r for r in csv.DictReader(f)}
    with open(ANSWERS, encoding="utf-8-sig", newline="") as f:
        answers = {(r["QUEUE"], r["ITEM_ID"]): r["ANSWER"] for r in csv.DictReader(f)}
    got = {}
    for path in sorted((out / "results").glob("result_*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if row["id"] in got:
                    raise SystemExit(f"duplicate {row['id']}")
                got[row["id"]] = row
    if set(got) != set(key):
        raise SystemExit(f"missing {sorted(set(key) - set(got))[:10]}, extra {sorted(set(got) - set(key))[:10]}")

    rows = []
    for sid, k in sorted(key.items()):
        row = got[sid]
        if row["answer"] not in VALID[k["TASK"]] or row["confidence"] not in ("high", "medium", "low"):
            raise SystemExit(f"{sid}: bad answer {row['answer']} / {row['confidence']}")
        brian = answers[(k["QUEUE"], k["ITEM_ID"])]
        rows.append({"SHEET": sid, "ITEM_ID": k["ITEM_ID"], "TEST": k["TEST"], "TASK": k["TASK"], "MODEL_ANSWER": row["answer"], "CONFIDENCE": row["confidence"],
                     "NOTE": row.get("note", ""), "BRIAN_ANSWER": brian, "BRIAN_SIMPLE": TRUTH[k["TASK"]].get(brian, "")})

    summary = {}
    for test in sorted({r["TEST"] for r in rows}):
        part = [r for r in rows if r["TEST"] == test]
        scored = [r for r in part if r["BRIAN_SIMPLE"]]
        answered = [r for r in scored if r["MODEL_ANSWER"] != "UNSURE"]
        entry = {"items": len(part), "scored": len(scored), "truth": dict(Counter(r["BRIAN_SIMPLE"] for r in scored)),
                 "model_unsure": sum(r["MODEL_ANSWER"] == "UNSURE" for r in scored), "answered_match": sum(r["MODEL_ANSWER"] == r["BRIAN_SIMPLE"] for r in answered),
                 "answered": len(answered), "directions": {}}
        for code in sorted({v for v in TRUTH[part[0]["TASK"]].values()}):
            calls = [r for r in scored if r["MODEL_ANSWER"] == code and r["CONFIDENCE"] == "high"]
            hits = sum(r["BRIAN_SIMPLE"] == code for r in calls)
            majority = max(Counter(r["BRIAN_SIMPLE"] for r in calls).values(), default=0) / len(calls) if calls else 0
            rate = hits / len(calls) if calls else 0
            overall = max(Counter(r["BRIAN_SIMPLE"] for r in scored).values()) / len(scored)
            entry["directions"][code] = {"high_calls": len(calls), "match": hits, "rate": round(rate, 3), "share_of_majority_answer_in_scored": round(overall, 3),
                                         "passes": test in ("A", "B", "C-8plus") and len(calls) >= MIN_ITEMS and rate >= MIN_MATCH and rate > overall}
            entry["directions"][code]["majority_among_calls"] = round(majority, 3)
        summary[test] = entry

    dest.mkdir(parents=True, exist_ok=True)
    with open(dest / "answers.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (dest / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
