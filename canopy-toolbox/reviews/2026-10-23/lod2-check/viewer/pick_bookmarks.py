r"""Bookmarks for the 3D viewer (October 24, 2026): the worst roofer failures and the best wins, from the per-building results.

    python reviews/2026-10-23/lod2-check/viewer/pick_bookmarks.py ROOFER_CITY_DIR OUT.json

ArcGIS Pro Python (arcpy, for the projection; PYTHONNOUSERSITE=1). Read-only. Each bookmark names a building (FP_ID), says why
it was picked (the numbers from the check), and gives its WGS84 position (NAD83(2011) to WGS84 with
WGS_1984_(ITRF08)_To_NAD_1983_2011, as the scene layer packages), its ground elevation and size, for the camera.
Categories, in order (counts in brackets):
  win-esri-defect  roofer passes, Esri LOD2.0 is broken or worse: largest Esri p95 minus roofer p95 [3]
  win-gable        steep-pitched, both pass: largest Esri p95 minus roofer p95, 120 to 600 m2 [2]
  win-commercial   multi-level or 600 m2 and up, both pass: largest Esri p95 minus roofer p95 [2]
  fail-invented    roofer top at least 1 m above the lidar's highest roof cell, Esri passes: largest overshoot, 100 m2 and up [3]
  fail-missing     roofer MISSING only, Esri passes: largest footprint [2]
  fail-worse       roofer worse than the flat baseline, Esri passes: largest p95 deficit [1]
  fail-both        roofer and Esri LOD2.0 both broken, 1,500 m2 and up: largest [1]
  typical          both better, 150 to 400 m2, pitched, roofer and Esri p95 close to the median [2]
"""
import csv
import json
from pathlib import Path
import sys

import numpy as np

TRANSFORM = "WGS_1984_(ITRF08)_To_NAD_1983_2011"
ESRI_CHECK = Path(r"H:\lidar\2023-salt-lake-valley\runs\lod2-check-filled-20261023\lod2-check.csv")
FOOTPRINTS = Path(r"H:\lidar\2023-salt-lake-valley\runs\massing-filled-20261023\massing.gdb\footprints")


def load(path):
    return {int(r["FP_ID"]): r for r in csv.DictReader(open(path, encoding="utf-8"))}


def num(r, k):
    v = r.get(k)
    return float(v) if v not in (None, "", "None") else np.nan


def main(folder, out):
    import arcpy
    folder = Path(folder)
    roofer = load(folder/"check"/"lod2-check.csv")
    esri = load(ESRI_CHECK)
    level = {int(r["FP_ID"]): r for r in csv.DictReader(open(folder/"three-way.csv", encoding="utf-8"))}
    ids = [i for i in roofer if num(roofer[i], "LOD20_CELLS") > 0 and roofer[i]["VERDICT"] != "too-few"]
    ok = lambda r: r["VERDICT"] in ("better", "same")
    d = {i: num(esri[i], "LOD20_ABS_P95_M")-num(roofer[i], "LOD20_ABS_P95_M") for i in ids}   # positive: roofer closer
    area = {i: num(roofer[i], "FOOTPRINT_M2") for i in ids}
    picks = []

    def take(category, candidates, key, n, reverse=True):
        chosen = sorted(candidates, key=key, reverse=reverse)[:n]
        picks.extend((category, i) for i in chosen)

    take("win-esri-defect", [i for i in ids if ok(roofer[i]) and esri[i]["VERDICT"] in ("broken", "worse") and area[i] >= 150],
         lambda i: d[i], 3)
    take("win-gable", [i for i in ids if roofer[i]["ROOF_TYPE"] == "steep-pitched" and ok(roofer[i]) and ok(esri[i])
                       and 120 <= area[i] <= 600], lambda i: d[i], 2)
    take("win-commercial", [i for i in ids if (roofer[i]["ROOF_TYPE"] == "multi-level" or area[i] >= 600) and ok(roofer[i])
                            and ok(esri[i]) and area[i] <= 4000], lambda i: d[i], 2)
    take("fail-invented", [i for i in ids if roofer[i]["VERDICT"] == "broken" and "TOP_ABOVE_LIDAR" in roofer[i]["NOTE"]
                           and ok(esri[i]) and area[i] >= 100],
         lambda i: num(roofer[i], "LOD20_TOP_MINUS_LIDAR_MAX_M"), 3)
    take("fail-missing", [i for i in ids if roofer[i]["VERDICT"] == "broken" and roofer[i]["NOTE"] == "MISSING"
                          and ok(esri[i]) and area[i] <= 4000], lambda i: area[i], 2)
    take("fail-worse", [i for i in ids if roofer[i]["VERDICT"] == "worse" and ok(esri[i])], lambda i: -d[i], 1)
    take("fail-both", [i for i in ids if roofer[i]["VERDICT"] == "broken" and esri[i]["VERDICT"] == "broken" and area[i] >= 1500],
         lambda i: area[i], 1)
    med_r = np.nanmedian([num(roofer[i], "LOD20_ABS_P95_M") for i in ids])
    take("typical", [i for i in ids if roofer[i]["VERDICT"] == "better" and esri[i]["VERDICT"] == "better"
                     and roofer[i]["ROOF_TYPE"] == "pitched" and 150 <= area[i] <= 400],
         lambda i: abs(num(roofer[i], "LOD20_ABS_P95_M")-med_r), 2, reverse=False)
    seen, unique = set(), []
    for c, i in picks:
        if i not in seen:
            seen.add(i)
            unique.append((c, i))
    wanted = {i for _, i in unique}
    sr4326 = arcpy.SpatialReference(4326)
    info = {}
    for fid, shape, ground in arcpy.da.SearchCursor(str(FOOTPRINTS), ["FP_ID", "SHAPE@", "GROUND_Z50_M"]):
        if fid in wanted:
            p = arcpy.PointGeometry(shape.labelPoint, shape.spatialReference).projectAs(sr4326, TRANSFORM)
            e = shape.extent
            info[fid] = {"lon": p.firstPoint.X, "lat": p.firstPoint.Y, "ground_z": ground,
                         "size_m": float(np.hypot(e.XMax-e.XMin, e.YMax-e.YMin))}
    titles = {"win-esri-defect": "Win: Esri LOD2.0 has a defect, roofer does not", "win-gable": "Win: steep gable",
              "win-commercial": "Win: large or multi-level roof", "fail-invented": "Failure: roofer invents roof",
              "fail-missing": "Failure: roofer misses roof", "fail-worse": "Failure: roofer worse than the flat block",
              "fail-both": "Both fail", "typical": "Typical"}
    out_list = []
    for n, (c, i) in enumerate(unique, 1):
        r, e = roofer[i], esri[i]
        out_list.append({
            "id": f"b{n:02d}", "fp_id": i, "category": c, "title": f"{titles[c]} (FP {i})", "type": r["ROOF_TYPE"],
            "footprint_m2": round(area[i]), "roof_cover_pct": round(num(r, "ROOF_COV_PCT")),
            "roofer": {"verdict": r["VERDICT"], "note": r["NOTE"], "p95_m": round(num(r, "LOD20_ABS_P95_M"), 2),
                       "within_1_pct": round(num(r, "LOD20_WITHIN_1_PCT"), 1),
                       "top_minus_lidar_m": round(num(r, "LOD20_TOP_MINUS_LIDAR_MAX_M"), 1)},
            "esri_lod20": {"verdict": e["VERDICT"], "note": e["NOTE"], "p95_m": round(num(e, "LOD20_ABS_P95_M"), 2),
                           "within_1_pct": round(num(e, "LOD20_WITHIN_1_PCT"), 1)},
            "esri_lod12": {"p95_m": round(num(e, "LOD12_ABS_P95_M"), 2), "within_1_pct": round(num(e, "LOD12_WITHIN_1_PCT"), 1)},
            "three_way_level": level[i]["LEVEL"], **info[i]})
    Path(out).write_text(json.dumps({"bookmarks": out_list}, indent=1), encoding="utf-8")
    for b in out_list:
        print(b["id"], b["category"], b["fp_id"], b["type"], b["footprint_m2"], b["roofer"]["verdict"], b["roofer"]["p95_m"],
              b["esri_lod20"]["verdict"], b["esri_lod20"]["p95_m"], b["three_way_level"])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
