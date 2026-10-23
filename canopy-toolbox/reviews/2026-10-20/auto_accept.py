"""Write the triage's roof and tree AUTO candidates as training answers, for the units still unlabelled. Writes one CSV.

    python reviews/2026-10-20/auto_accept.py NEW_CSV [--packet PACKET_DIR] [--triage triage-proposals.csv] [--labels backup.csv]
    training_labels.bat restore --csv NEW_CSV            (preview)
    training_labels.bat restore --csv NEW_CSV --apply

Decided with Brian on October 20, 2026, after the blind audit 2 of triage v2: roofs 23 of 23 (or 22 of 23, depending on one
unit later removed as ambiguous), trees 14 of 15 (the miss a MIXED answer), walls 0 of 2. So only BUILDING_ROOF and TREE
AUTO_CANDIDATEs are accepted, never walls or anything else. Every answer has REVIEWER "triage-v2" and a note, so auto answers can
always be told apart from human labels and removed. Left out: units already labelled, the audit units (they test the triage, so
the triage must never answer them), units a person removed as ambiguous (--skip) and units answered on the label page but not
yet imported. The CSV is in the training-label backup
format; the review geodatabase changes only through restore, which checks every row and never overwrites a label.
"""
import argparse
import csv
import datetime
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[2]
sys.path.insert(0, str(TOOLBOX))
from canopy import training_review as tr  # noqa: E402
from canopy.lidar_root import lidar_root  # noqa: E402

PACKET = lidar_root()/"2023-salt-lake-valley"/"runs"/"pilot-2026-09-29"/"training-review"/"packet-20260929"
TRIAGE = TOOLBOX/"reviews"/"2026-09-30"/"triage-2"/"triage-proposals.csv"
LABELS = TOOLBOX/"reviews"/"2026-09-29"/"packets"/"training-labels"/"labels-progress.csv"
AUDITS = [TOOLBOX/"reviews"/"2026-09-30"/name/"audit-units.txt" for name in ("audit-1", "audit-2")]
ACCEPTED = ("BUILDING_ROOF", "TREE")
REVIEWER = "triage-v2"
NOTE = "Auto-accepted triage v2 AUTO_CANDIDATE (blind audit 2: roofs 23/23, trees 14/15; walls never). Not a human label."
REMOVED_AS_AMBIGUOUS = ("Q1-0114", "Q2-0010")         # cleared by Brian on October 20; a person decides these


def choose(units, proposals, labelled, excluded):
    """(unit, label) pairs to auto-accept, in review order."""
    out = []
    for unit in sorted(units, key=lambda u: (int(u["REVIEW_ORDER"]), u["UNIT_ID"])):
        uid = unit["UNIT_ID"]
        p = proposals.get(uid)
        if uid in labelled or uid in excluded or p is None:
            continue
        if p.get("TIER") == "AUTO_CANDIDATE" and p.get("PROPOSED") in ACCEPTED:
            out.append((unit, p["PROPOSED"]))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path)
    parser.add_argument("--packet", type=Path, default=PACKET)
    parser.add_argument("--triage", type=Path, default=TRIAGE)
    parser.add_argument("--labels", type=Path, default=LABELS)
    parser.add_argument("--skip", nargs="*", default=list(REMOVED_AS_AMBIGUOUS))
    parser.add_argument("--page-answers", type=Path, help="label page answers (default <packet>/label-page/answers/...); "
                                                          "units answered there are left to the person")
    args = parser.parse_args(argv)
    if args.out.exists():
        raise FileExistsError(args.out)
    packet = json.loads((args.packet/"packet.json").read_text(encoding="utf-8"))
    if packet.get("schema") != tr.SCHEMA or tr.units_digest(packet["units"]) != packet["units_digest"]:
        raise ValueError("Not an unaltered training review packet")
    frame = tr.check_frame(packet["frame"])
    proposals = {r["UNIT_ID"]: r for r in csv.DictReader(open(args.triage, encoding="utf-8"))}
    labelled = {r["UNIT_ID"] for r in tr.read_backup(args.labels) if r["LABEL"]}
    page = args.page_answers or args.packet/"label-page"/"answers"/"label-page-answers.csv"
    if page.exists():
        labelled |= {r["UNIT_ID"] for r in tr.read_backup(page) if r["LABEL"]}      # a person's answer always wins
    audited = set()
    for path in AUDITS:
        if path.exists():
            audited |= set(path.read_text(encoding="utf-8").split())
    excluded = audited | set(args.skip)
    today = datetime.date.today().isoformat()
    rows = []
    for unit, label in choose(packet["units"], proposals, labelled, excluded):
        answer = tr.normalize_answer(unit, {"LABEL": label, "REVIEWER": REVIEWER, "REVIEW_DATE": today, "NOTES": NOTE}, frame)
        rows.append({"UNIT_ID": unit["UNIT_ID"], "QUEUE": unit["QUEUE"], "REVIEW_ORDER": unit["REVIEW_ORDER"],
                     "UNIT_TOKEN": tr.unit_token(frame["digest"], unit), **answer, "CHECK": "OK"})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(tr.backup_csv(rows), encoding="utf-8")
    unlabelled = len(packet["units"])-len(labelled)
    counts = {}
    for r in rows:
        counts[r["LABEL"]] = counts.get(r["LABEL"], 0)+1
    print(f"{len(rows)} of {unlabelled} unlabelled units auto-accepted: {counts}; left out {len(excluded & {u['UNIT_ID'] for u in packet['units']} - labelled)} "
          f"audit or removed units -> {args.out}")


if __name__ == "__main__":
    main()
