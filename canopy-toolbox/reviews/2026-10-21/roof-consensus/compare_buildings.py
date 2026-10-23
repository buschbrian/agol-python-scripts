"""Compare the consensus building heights with October 19's, footprint by footprint (October 21, 2026).

    python reviews/2026-10-21/roof-consensus/compare_buildings.py ROOT

Run with any Python 3 after summarize_city_buildings.py has written ROOT/buildings/building-heights.csv. Read-only on both
CSVs; writes ROOT/buildings/comparison.json and ROOT/buildings/height-changes.csv (every footprint whose median height moved by
more than 0.5 m or whose roof support status changed, largest change first), for review in Pro beside the two layers.
Both runs use the same footprints, terrain and summary code, so every difference comes from the roofs.
"""
import argparse
import csv
import json
from pathlib import Path
import statistics

OCT19 = Path(r"D:\lidar\2023-salt-lake-valley\runs\millcreek-products-20261019\building-heights.csv")
MOVE_M = 0.5
NUMBERS = ("HEIGHT_P50_M", "HEIGHT_P95_M", "HEIGHT_MAX_M", "ROOF_COV_PCT")


def read(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return {row["SOURCE_ID"]: row for row in csv.DictReader(handle)}


def number(value):
    return None if value in (None, "", "None") else float(value)


def flags(row):
    return set(filter(None, row["HEIGHT_STATUS"].split(";")))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", type=Path)
    args = parser.parse_args(argv)
    folder = args.root/"buildings"
    old, new = read(OCT19), read(folder/"building-heights.csv")
    if set(old) != set(new):
        raise ValueError("The two runs hold different footprints")
    report = {"footprints": len(new), "status_counts": {}, "moved": {}, "medians": {}}
    for name, rows in (("oct19", old), ("consensus", new)):
        counts = {}
        for row in rows.values():
            for flag in flags(row):
                counts[flag] = counts.get(flag, 0)+1
        counts["with_height"] = sum(number(r["HEIGHT_P50_M"]) is not None for r in rows.values())
        report["status_counts"][name] = dict(sorted(counts.items()))
    changes, deltas = [], {k: [] for k in NUMBERS}
    for key, a in old.items():
        b = new[key]
        row = {"SOURCE_ID": key}
        for field in NUMBERS:
            x, y = number(a[field]), number(b[field])
            row[f"{field}_OCT19"], row[f"{field}_CONSENSUS"] = x, y
            row[f"{field}_DELTA"] = None if x is None or y is None else round(y-x, 3)
            if row[f"{field}_DELTA"] is not None:
                deltas[field].append(row[f"{field}_DELTA"])
        support = ("NO_ROOF_SUPPORT", "LOW_ROOF_SUPPORT")
        row["SUPPORT_OCT19"] = ";".join(f for f in support if f in flags(a)) or "OK"
        row["SUPPORT_CONSENSUS"] = ";".join(f for f in support if f in flags(b)) or "OK"
        moved = row["HEIGHT_P50_M_DELTA"] is not None and abs(row["HEIGHT_P50_M_DELTA"]) > MOVE_M
        if moved or row["SUPPORT_OCT19"] != row["SUPPORT_CONSENSUS"] or (row["HEIGHT_P50_M_OCT19"] is None) != (row["HEIGHT_P50_M_CONSENSUS"] is None):
            changes.append(row)
    for field, values in deltas.items():
        report["medians"][field] = {"compared": len(values), "unchanged": sum(v == 0 for v in values),
                                    "median_delta": statistics.median(values) if values else None,
                                    "moved_over_0.5": sum(abs(v) > MOVE_M for v in values) if "HEIGHT" in field else None}
    pairs = {}
    for row in changes:
        k = f'{row["SUPPORT_OCT19"]} -> {row["SUPPORT_CONSENSUS"]}'
        pairs[k] = pairs.get(k, 0)+1
    report["support_transitions_among_changes"] = dict(sorted(pairs.items(), key=lambda kv: -kv[1]))
    report["review_rows"] = len(changes)
    changes.sort(key=lambda r: -abs(r["HEIGHT_P50_M_DELTA"] or 0))
    with open(folder/"height-changes.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(changes[0]) if changes else ["SOURCE_ID"])
        writer.writeheader()
        writer.writerows(changes)
    (folder/"comparison.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
