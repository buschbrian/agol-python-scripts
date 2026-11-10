"""Roofer LoD2.2 on the regularized outlines, as a cross-check. Run with millcreek-py3 and PYTHONNOUSERSITE=1.

    lod22_check.py run OUT       prep and roofer per tile, the same points and settings as lidar_first_city.py
    lod22_check.py flags OUT     one row per outline: model or not, fit error, and a review flag

An outline is flagged when any part has no LoD2.2 model or the fit error exceeds RMSE_FLAG_M.
"""

import csv
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2] / "2026-10-26" / "lidar-footprints"))
RMSE_FLAG_M = 0.5


def run(out):
    import lidar_first_city as lfc
    lfc.LIDAR = out.parent / "regularized.gdb"
    lfc.prep(out)
    lfc.run(out)


def flags(out):
    models = {}
    for path in (out / "output").glob("*/*.city.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            feature = json.loads(line)
            for key, item in feature.get("CityObjects", {}).items():
                if item.get("type") == "Building" and item.get("children") and item.get("attributes", {}).get("rf_success"):
                    models[int(key)] = item["attributes"]
    parts = json.loads((out / "prep.json").read_text(encoding="utf-8"))
    import geopandas as gpd
    by_outline = {}
    for shp in sorted((out / "footprints").glob("*.shp")):
        table = gpd.read_file(shp, ignore_geometry=True)
        for fid, lb, area in zip(table.FP_ID, table.LB_ID, table.AREA_M2):
            by_outline.setdefault(lb, []).append((int(fid), area))
    rows, tally = [], Counter()
    for lb, members in sorted(by_outline.items()):
        found = [models[f] for f, _ in members if f in models]
        fits = [a.get("rf_rmse_lod22") for a in found if a.get("rf_rmse_lod22") is not None]
        worst = max(fits) if fits else None
        flag = "NO_MODEL" if len(found) < len(members) else ("HIGH_RMSE" if worst is not None and worst > RMSE_FLAG_M else "OK")
        tally[flag] += 1
        rows.append({"LB_ID": lb, "PARTS": len(members), "MODELS": len(found), "RMSE_MAX_M": worst, "FLAG": flag})
    with open(out / "lod22-flags.csv", "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"outlines": len(rows), "parts": parts["parts"], "flags": dict(tally)}, indent=1))


if __name__ == "__main__":
    {"run": run, "flags": flags}[sys.argv[1]](Path(sys.argv[2]))
