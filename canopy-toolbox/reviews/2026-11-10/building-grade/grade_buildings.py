"""Grade Brian's finished outlines2 answers into the November 9 decisions (November 10, 2026).

He answered the last 121 items (reshaped, small, tangles, the 42 reshaped one by one, the touching check). This adds his
answers to every item still waiting and sets the one rule they support:
- Tangles: 28 of 40 split into separate buildings (7 county, 2 units). The 142 waiting are split (rule-20261110).
- Touching pieces: 8 of 20 part of a building, 4 not a building, 3 unsure. The October 27 default (join) fails its
  check. Brian's call on the group: drop the 286 (DECISION DROP, BY Brian-20261110).
Everything else keeps its November 9 decision; his answers there already stood.

    python grade_buildings.py DATA RUN     DATA is the review page's data folder, RUN is runs\\lidar-footprints-20261109.
                                           Writes RUN/decisions-20261110.csv; the November 9 file is not changed.
"""
import collections
import csv
import hashlib
from pathlib import Path
import sys

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2]/"2026-10-26"/"lidar-footprints"))
from grade_regrade import decision, PREFIX, QUEUE  # noqa: E402

RULES = {"tangle_wait": "SPLIT_BUILDINGS"}
BY = "rule-20261110"
FAILED = {"touching_wait": "October 27 default (join) failed its check: 8 of 20 part of a building"}
CALLS = {"touching_wait": ("DROP", "Brian-20261110",   # his call on a whole group, after the check failed
                           "Brian, November 10: drop small pieces touching a building (join failed its check, 8 of 20)")}


def main(data, run):
    answers_csv = data/"answers"/"footprint-review-answers.csv"
    before = hashlib.sha256(answers_csv.read_bytes()).hexdigest()
    with answers_csv.open(encoding="utf-8") as fh:
        answered = {r["ITEM_ID"][len(PREFIX):]: r for r in csv.DictReader(fh) if r["QUEUE"] == QUEUE and r["ANSWER"]}
    with (run/"decisions.csv").open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    fields = list(rows[0])
    for r in rows:
        ans = answered.get(r["GROUP"])
        if ans and r["BY"] != "Brian":
            r.update(DECISION=decision(ans["ANSWER"], ans["NOTE"]), BY="Brian", ANSWER=ans["ANSWER"], NOTE=ans["NOTE"])
        elif r["BY"] == "waiting" and r["REVIEW_GROUP"] in RULES:
            r.update(DECISION=RULES[r["REVIEW_GROUP"]], BY=BY,
                     NOTE="Brian's tangle sample, November 10: 28 of 40 separate buildings")
        elif r["REVIEW_GROUP"] in CALLS and r["BY"] == "rule":
            dec, by, note = CALLS[r["REVIEW_GROUP"]]
            r.update(DECISION=dec, BY=by, NOTE=note)
        elif r["REVIEW_GROUP"] in FAILED and r["BY"] == "rule":
            r.update(DECISION="", BY="waiting", NOTE=FAILED[r["REVIEW_GROUP"]])
    out = run/"decisions-20261110.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fields)
        w.writeheader()
        w.writerows(rows)
    assert hashlib.sha256(answers_csv.read_bytes()).hexdigest() == before
    print("by:", dict(collections.Counter(r["BY"] for r in rows)))
    print("waiting:", dict(collections.Counter(r["REVIEW_GROUP"] for r in rows if r["BY"] == "waiting")))
    print("decisions:", dict(collections.Counter(r["DECISION"] or "(waiting)" for r in rows).most_common()))
    print("Brian's, by decision:", dict(collections.Counter(r["DECISION"] for r in rows if r["BY"] == "Brian").most_common()))
    print("wrote", out)


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
