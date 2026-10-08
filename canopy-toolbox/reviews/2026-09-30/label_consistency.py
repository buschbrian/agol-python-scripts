"""Flag training labels that the points inside their own unit patch cannot support. Read-only.

    python reviews/2026-09-30/label_consistency.py NEW_OUTPUT_DIR [--labels labels-progress.csv]

Protocol (decided September 30, 2026): a label says what the returns inside the unit's 1 m patch and height slab are. For
every labelled unit this measures the height above ground of exactly those points and flags a label that names something
they cannot be (a VEHICLE whose patch tops out at 0.3 m, a BUILDING_ROOF that is 1 m off the ground, ...). See
canopy/label_check.py for the rules. A flag asks a person to look again; nothing is changed, and unflagged does not mean
correct. Reads the repo label backup (run training_labels.bat backup first), the packet and the prepared tile's points.
"""
import argparse
import csv
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from canopy import label_check, las_records  # noqa: E402
from canopy.lidar_root import lidar_root, live  # noqa: E402

PILOT = lidar_root()/"2023-salt-lake-valley"/"runs"/"pilot-2026-09-29"
PACKET = PILOT/"training-review"/"packet-20260929"/"packet.json"
LAS = PILOT/"12TVL2804"/"prepared"/"points"/"12TVL2804.las"
LABELS = Path(__file__).resolve().parents[1]/"2026-09-29"/"packets"/"training-labels"/"labels-progress.csv"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path)
    parser.add_argument("--labels", type=Path, default=LABELS)
    args = parser.parse_args(argv)
    if args.out.exists():
        raise FileExistsError(f"Choose a new output folder: {args.out}")
    units = {u["UNIT_ID"]: u for u in json.loads(live(PACKET).read_text(encoding="utf-8"))["units"]}
    with open(args.labels, encoding="utf-8", newline="") as handle:
        labelled = [r for r in csv.DictReader(handle) if r.get("LABEL")]
    block, scale, offset, modern, info = las_records.records(live(LAS))
    x = block["x"]*scale[0]+offset[0]
    y = block["y"]*scale[1]+offset[1]
    z = block["z"]*scale[2]+offset[2]
    rows = []
    for record in labelled:
        unit = units[record["UNIT_ID"]]
        near = np.flatnonzero((np.abs(x-unit["X"]) <= 1.5) & (np.abs(y-unit["Y"]) <= 1.5))
        stats = label_check.patch_stats(unit, x[near], y[near], z[near], unit["GROUND_Z"])
        reasons = label_check.check_label(record["LABEL"], stats)
        rows.append({"UNIT_ID": record["UNIT_ID"], "QUEUE": unit["QUEUE"], "LABEL": record["LABEL"],
                     "REVIEWER": record.get("REVIEWER", ""), "patch_points": stats["n"],
                     "min_hag": round(stats["min"], 2), "mean_hag": round(stats["mean"], 2),
                     "max_hag": round(stats["max"], 2), "FLAG": "FLAG" if reasons else "",
                     "REASON": "; ".join(reasons)})
    args.out.mkdir(parents=True)
    with open(args.out/"consistency.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    flagged = [r for r in rows if r["FLAG"]]
    by_label = {}
    for r in rows:
        entry = by_label.setdefault(r["LABEL"], {"labelled": 0, "flagged": 0})
        entry["labelled"] += 1
        entry["flagged"] += bool(r["FLAG"])
    print(f"{len(rows)} labelled units; {len(flagged)} flagged for a second look")
    print("by label:", json.dumps(dict(sorted(by_label.items()))))
    for r in flagged:
        print(f"  {r['UNIT_ID']:8s} {r['LABEL']:16s} {r['REASON']}")
    if flagged:
        quoted = ",".join(f"'{r['UNIT_ID']}'" for r in flagged)
        (args.out/"recheck-select.txt").write_text(f"UNIT_ID IN ({quoted})\n", encoding="utf-8")
        print("To re-look in Pro: set the Training units layer's definition query to 'Labelled (check answers)' "
              "(labelled units are hidden by default), then Select By Attributes with recheck-select.txt. To change a "
              "label, run Label Training Unit with Replace ticked.")
    print(f"Wrote {args.out/'consistency.csv'}")


if __name__ == "__main__":
    main()
