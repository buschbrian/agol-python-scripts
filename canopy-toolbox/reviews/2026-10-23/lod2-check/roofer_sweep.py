r"""Roofer settings against its snags, on the pilot tile 12TVL2804 (October 24, 2026).

    python reviews/2026-10-23/lod2-check/roofer_sweep.py SWEEP_DIR [--only NAME ...]

ArcGIS Pro Python or the deep-learning clone (arcpy, numpy, Pillow; PYTHONNOUSERSITE=1). Runs roofer (the pilot's copy) on the
pilot's input with each configuration, then measures two things per configuration:
- Snags, counted from roofer's CityJSON (LoD 2.2 roof faces of each building):
    tiny faces      roof faces under 0.5 m2 in plan
    slivers         roof faces whose width, estimated as 2 x plan area / perimeter, is under 0.4 m
    steep faces     roof faces steeper than 75 degrees (walls called roof)
    faces per roof  roof faces per building (fewer is simpler)
    outline excess  vertices of the model's outline (GroundSurface) beyond those of the county footprint
    plan ratio      roof plan area over footprint area
- Fit, as score_roofer.py (same compared cells and rules, Esri filled LOD1.2 as the flat baseline): pooled share within
  0.5 m and 1 m, median p95, buildings broken (strict, and without the MISSING flag), buildings with no solid.
Configurations are roofer command-line options; the run, its log and its CityJSONSeq stay under SWEEP_DIR\<name>.
"""
import argparse
import csv
import datetime
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

HERE = Path(__file__).resolve()
PILOT = Path(r"H:\lidar\2023-salt-lake-valley\runs\roofer-20261024")
CHECK_FILLED = Path(r"H:\lidar\2023-salt-lake-valley\runs\lod2-check-filled-20261023")
EXE = PILOT/"roofer-1.0.0"/"bin"/"roofer.exe"

CONFIGS = {
    "base": [],
    "noclip": ["--no-clip-terrain"],
    "cx70": ["--complexity-factor", "0.7"],
    "cx50": ["--complexity-factor", "0.5"],
    "eps40": ["--plane-detect-epsilon", "0.4"],
    "eps50": ["--plane-detect-epsilon", "0.5"],
    "minpts30": ["--plane-detect-min-points", "30"],
    "noclip_cx70": ["--no-clip-terrain", "--complexity-factor", "0.7"],
    "eps40_mp30_cx80": ["--plane-detect-epsilon", "0.4", "--plane-detect-min-points", "30", "--complexity-factor", "0.8"],
    "minpts50": ["--plane-detect-min-points", "50"],
    "minpts80": ["--plane-detect-min-points", "80"],
    "minpts50_k25": ["--plane-detect-min-points", "50", "--plane-detect-k", "25"],
}


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE.parent/f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_roofer(name, flags, folder):
    out = folder/name/"output"
    if out.exists() and list(out.glob("*.city.jsonl")):
        return json.loads((folder/name/"run.json").read_text(encoding="utf-8")) if (folder/name/"run.json").exists() else {}
    (folder/name/"input").mkdir(parents=True, exist_ok=True)
    (folder/name/"input"/"roofer-input.json").write_text((PILOT/"input"/"roofer-input.json").read_text(encoding="utf-8"), encoding="utf-8")
    out.mkdir(parents=True, exist_ok=True)
    work = folder/name/"work"
    work.mkdir(exist_ok=True)
    cmd = [str(EXE), "--lod12", "--lod22", "--id-attribute", "FP_ID", "--srs", "EPSG:6341", "--jobs", "12", *flags,
           str(PILOT/"input"/"12TVL2804.las"), str(PILOT/"input"/"footprints.shp"), str(out)]
    started = datetime.datetime.now()
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(work))
    (folder/name/"roofer.log").write_text(p.stdout+p.stderr, encoding="utf-8")
    record = {"flags": flags, "returncode": p.returncode, "seconds": round((datetime.datetime.now()-started).total_seconds(), 1)}
    (folder/name/"run.json").write_text(json.dumps(record), encoding="utf-8")
    return record


def ring_area(ring):
    x, y = ring[:, 0], ring[:, 1]
    return 0.5*(np.dot(x, np.roll(y, -1))-np.dot(y, np.roll(x, -1)))


def snags(jsonl, footprint_vertices):
    """Per building snag counts from the LoD 2.2 solids of a roofer CityJSONSeq file."""
    lines = Path(jsonl).read_text(encoding="utf-8").splitlines()
    head = json.loads(lines[0])
    scale, translate = np.array(head["transform"]["scale"]), np.array(head["transform"]["translate"])
    rows = {}
    for line in lines[1:]:
        f = json.loads(line)
        v = np.array(f["vertices"], float)*scale+translate
        for key, o in f["CityObjects"].items():
            if o["type"] != "BuildingPart":
                continue
            fid = int(key.split("-")[0])
            row = rows.setdefault(fid, {"faces": 0, "tiny": 0, "sliver": 0, "steep": 0, "plan_area": 0.0, "outline": 0})
            for g in o["geometry"]:
                if g["lod"] != "2.2" or g["type"] != "Solid":
                    continue
                kinds = [s["type"] for s in g["semantics"]["surfaces"]]
                for shell, labels in zip(g["boundaries"], g["semantics"]["values"]):
                    for face, label in zip(shell, labels):
                        ring = v[face[0]]
                        if kinds[label] == "GroundSurface":
                            row["outline"] += len(ring)
                        if kinds[label] != "RoofSurface":
                            continue
                        plan = abs(ring_area(ring))
                        for hole in face[1:]:
                            plan -= abs(ring_area(v[hole]))
                        perimeter = np.linalg.norm(np.diff(np.vstack([ring, ring[:1]]), axis=0), axis=1).sum()
                        # the vector area of the whole outline: a normal from three vertices is unreliable when they are nearly
                        # collinear (the first version of this metric used them and counted 55 "steep" faces that are not)
                        n = np.zeros(3)
                        for p1, p2 in zip(ring[1:-1], ring[2:]):
                            n += np.cross(p1-ring[0], p2-ring[0])
                        norm = np.linalg.norm(n)
                        slope = np.degrees(np.arccos(min(1.0, abs(n[2])/norm))) if norm > 0 else 0.0
                        row["faces"] += 1
                        row["plan_area"] += plan
                        row["tiny"] += plan < 0.5
                        row["sliver"] += (2*plan/perimeter if perimeter > 0 else 0) < 0.4
                        row["steep"] += slope > 75
    for fid, row in rows.items():
        row["outline_excess"] = row["outline"]-footprint_vertices.get(fid, row["outline"])
    return rows


def footprint_vertex_counts():
    import arcpy
    return {fid: (s.pointCount-s.partCount) for fid, s in arcpy.da.SearchCursor(str(PILOT/"input"/"footprints.shp"), ["FP_ID", "SHAPE@"])}


def measure(name, folder, sr, fpv, areas):
    d = folder/name
    rows = snags(next((d/"output").glob("*.city.jsonl")), fpv)
    out = d/"check"
    if not out.exists():
        sr.score(d, CHECK_FILLED, out)
    check = json.loads((out/"roofer-check.json").read_text(encoding="utf-8"))
    csvrows = list(csv.DictReader(open(out/"roofer-check.csv", encoding="utf-8")))
    judged = [r for r in csvrows if r["VERDICT_R22"] not in ("too-few", "no-model")]
    broken = [r for r in judged if r["VERDICT_R22"] == "broken"]
    f = np.array

    def share(key):
        return round(100*sum(1 for r in rows.values() if r[key] > 0)/max(1, len(rows)), 1)
    plan_ratio = [r["plan_area"]/areas[fid] for fid, r in rows.items() if fid in areas and areas[fid] > 0]
    return {"name": name, "buildings_with_solid": len(rows), "roof_faces": int(sum(r["faces"] for r in rows.values())),
            "faces_per_roof_median": float(np.median([r["faces"] for r in rows.values()])),
            "faces_per_roof_mean": round(float(np.mean([r["faces"] for r in rows.values()])), 2),
            "tiny_faces": int(sum(r["tiny"] for r in rows.values())), "buildings_with_tiny_pct": share("tiny"),
            "slivers": int(sum(r["sliver"] for r in rows.values())), "buildings_with_sliver_pct": share("sliver"),
            "steep_faces": int(sum(r["steep"] for r in rows.values())), "buildings_with_steep_pct": share("steep"),
            "outline_excess_median": float(np.median([r["outline_excess"] for r in rows.values()])),
            "outline_excess_p90": float(np.percentile([r["outline_excess"] for r in rows.values()], 90)),
            "plan_ratio_median": round(float(np.median(plan_ratio)), 3),
            "within_05_pct": check["pooled"]["R22"]["within_05_pct"], "within_1_pct": check["pooled"]["R22"]["within_1_pct"],
            "p95_median_m": check["median"]["R22"]["ABS_P95_M"], "judged": len(judged), "broken": len(broken),
            "broken_without_missing": sum(1 for r in broken if [x for x in r["NOTE_R22"].split(";") if x not in ("MISSING", "")]),
            "better": sum(r["VERDICT_R22"] == "better" for r in judged), "worse": sum(r["VERDICT_R22"] == "worse" for r in judged)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("folder", type=Path)
    p.add_argument("--only", nargs="*")
    a = p.parse_args(argv)
    a.folder.mkdir(parents=True, exist_ok=True)
    sr = _load("score_roofer")
    fpv = footprint_vertex_counts()
    import arcpy
    areas = {fid: s.area for fid, s in arcpy.da.SearchCursor(str(PILOT/"input"/"footprints.shp"), ["FP_ID", "SHAPE@"])}
    results = []
    for name, flags in CONFIGS.items():
        if a.only and name not in a.only:
            continue
        run = run_roofer(name, flags, a.folder)
        m = measure(name, a.folder, sr, fpv, areas)
        m["seconds"], m["flags"] = run.get("seconds"), " ".join(flags)
        results.append(m)
        print(json.dumps(m), flush=True)
    path = a.folder/"sweep.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    merged = {r["name"]: r for r in old}
    merged.update({r["name"]: r for r in results})
    path.write_text(json.dumps(list(merged.values()), indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
