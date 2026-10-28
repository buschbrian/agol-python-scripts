"""Treetop, height and crown figures behind the RFP answers (October 23, 2026).

Reads the October 22 product library (crowns.gdb/trees_review and treetop-evidence.csv) and writes counts.json beside
this script. Read only; nothing in the library changes. Run with ArcGIS Pro Python:

    $env:PYTHONNOUSERSITE='1'; $env:CANOPY_LIDAR_ROOT='H:\\lidar'
    & "C:\\Program Files\\ArcGIS\\Pro\\bin\\Python\\envs\\arcgispro-py3\\python.exe" reviews\\2026-10-23\\rfp-tree-questions\\counts.py
"""
import json
import os
from pathlib import Path

import arcpy
import numpy as np
import pandas as pd

LIBRARY = Path(os.environ.get("CANOPY_LIDAR_ROOT", r"H:\lidar")) / "2023-salt-lake-valley/runs/millcreek-products-20261022"
FIELDS = ["TREE_ID", "HEIGHT_M", "OWNERSHIP", "OWNER_GROUP", "CROWN_STATUS", "CROWN_DIAM_M"]
LARGE_HEIGHT_M, LARGE_CROWN_M = 20, 12   # screening thresholds for the heritage/specimen candidate list


def load():
    rows = arcpy.da.TableToNumPyArray(str(LIBRARY / "crowns.gdb/trees_review"), FIELDS,
                                      null_value={"OWNER_GROUP": "", "CROWN_STATUS": "", "CROWN_DIAM_M": -1})
    trees = pd.DataFrame(rows).merge(pd.read_csv(LIBRARY / "treetop-evidence.csv", usecols=["TREE_ID", "SUSPECT"]),
                                     on="TREE_ID", how="left", validate="1:1")
    assert trees.SUSPECT.notna().all()
    trees["GROUP"] = np.where(trees.OWNERSHIP == "PUBLIC_GOVERNMENT", "PUBLIC:" + trees.OWNER_GROUP, trees.OWNERSHIP)
    trees["CROWN"] = trees.CROWN_STATUS == "ESTIMATED"
    return trees


def summary(d):
    kept = d[d.SUSPECT == 0]
    crowns = kept[kept.CROWN]
    return {"treetops": len(d), "suspect": int(d.SUSPECT.sum()), "not_suspect": len(kept),
            "not_suspect_ge_4m": int((kept.HEIGHT_M >= 4).sum()), "not_suspect_ge_6m": int((kept.HEIGHT_M >= 6).sum()),
            "not_suspect_crown_ge_3m2": len(crowns),
            "median_height_m": round(float(kept.HEIGHT_M.median()), 2),
            "median_crown_diam_m": round(float(crowns.CROWN_DIAM_M.median()), 2) if len(crowns) else None,
            "large_candidates": int((crowns.HEIGHT_M.ge(LARGE_HEIGHT_M) & crowns.CROWN_DIAM_M.ge(LARGE_CROWN_M)).sum())}


def main():
    trees = load()
    scopes = {"city": trees,
              "no_parcel": trees[trees.OWNERSHIP == "NO_PARCEL"],
              "millcreek_owned": trees[trees.GROUP == "PUBLIC:MILLCREEK"],
              "no_parcel_and_millcreek_owned": trees[(trees.OWNERSHIP == "NO_PARCEL") | (trees.GROUP == "PUBLIC:MILLCREEK")],
              "public_other_than_county": trees[(trees.OWNERSHIP == "PUBLIC_GOVERNMENT")
                                                & (trees.OWNER_GROUP != "SALT_LAKE_COUNTY")],
              "public_all": trees[trees.OWNERSHIP == "PUBLIC_GOVERNMENT"]}
    result = {"library": str(LIBRARY), "large_candidate_rule": f"not SUSPECT, crown estimated (at least 3 m2), height at "
              f"least {LARGE_HEIGHT_M} m and crown diameter at least {LARGE_CROWN_M} m",
              "scopes": {name: summary(d) for name, d in scopes.items()},
              "groups": {name: summary(d) for name, d in trees.groupby("GROUP")}}
    out = Path(__file__).with_name("counts.json")
    out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf8")
    for name, figures in result["scopes"].items():
        print(name, figures)


if __name__ == "__main__":
    main()
