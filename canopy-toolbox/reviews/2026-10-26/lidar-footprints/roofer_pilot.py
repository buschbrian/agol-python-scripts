r"""Roofer LoD2.2 on the LiDAR-first outlines for one pilot block, packaged to compare with the current three-way hybrid
(October 26, 2026). Brian: "run roofer on the LiDAR-first outlines for a pilot block around Chambers Ave and show me
the 3D result next to the current hybrid".

    python roofer_pilot.py OUT [--centre X Y] [--half 250]

ArcGIS Pro Python with 3D Analyst (millcreek-py3; laspy, arcpy; PYTHONNOUSERSITE=1). Read-only on every input; writes
only OUT (a new folder). Nothing is uploaded. Same inputs and settings as the October 24 citywide run
(reviews/2026-10-23/lod2-check/roofer_city.py), only the footprints change:
- Footprints: the LiDAR-first outlines (runs\lidar-footprints-20261026\city) lying completely inside the block, with FP_ID
  the number of LB_ID. The county footprints are not used.
- Points: the citywide run's per-tile consensus points (class 6 roof where 2 of native, FRACTAL and Esri say building;
  class 2 native ground), merged from every tile touching the block plus 20 m.
- roofer 1.0.0: --lod22 --plane-detect-min-points 30, as the v2 run.
- Conversion: roofer_to_multipatch.py's route (one CityJSON, cjio OBJ of LoD2.2, one OBJ per part, Import 3D Files), then a
  scene layer package in WGS84 with the ITRF08 transformation, validated.
"""
import argparse
import datetime
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

import numpy as np

HERE = Path(__file__).resolve()
LOD2 = HERE.parents[1].parent/"2026-10-23"/"lod2-check"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(HERE.parents[3]))
from canopy.lidar_root import lidar_root  # noqa: E402

RUNS = lidar_root()/"2023-salt-lake-valley"/"runs"
LIDAR = RUNS/"lidar-footprints-20261026"/"city"/"lidar.gdb"
POINTS = RUNS/"roofer-city-20261024"/"points"
V2 = RUNS/"roofer-city-v2-20261024"
ROOFER = V2/"roofer-1.0.0"/"bin"/"roofer.exe"
CJIO = V2/"tools"/"cjio-venv"/"Scripts"/"cjio.exe"
FLAGS = ["--plane-detect-min-points", "30"]
CHAMBERS = (427930.0, 4505900.0)     # LB006200 (citywide run), the LiDAR building over LC01389, LC01423 and MD733329
BUFFER = 20.0
SRS = "EPSG:6341"
ROOFER_ATTRS = {"rf_roof_type": ("RF_ROOF_TYPE", "TEXT"), "rf_roof_planes": ("RF_ROOF_PLANES", "LONG"),
                "rf_rmse_lod22": ("RF_RMSE_LOD22", "DOUBLE"), "rf_h_ground": ("RF_H_GROUND", "DOUBLE"),
                "rf_h_roof_max": ("RF_H_ROOF_MAX", "DOUBLE"), "rf_extrusion_mode": ("RF_EXTRUSION", "TEXT")}


def footprints(out, box):
    import geopandas as gpd
    import shapely
    lidar = gpd.read_file(LIDAR, layer="buildings")
    sel = lidar[lidar.geometry.within(shapely.box(*box))].copy()
    multi = int(sel.geometry.apply(lambda g: len(getattr(g, "geoms", [g])) > 1).sum())
    # roofer builds each part of a multi-part outline as its own building under the same id, so number the parts:
    # FP_ID = LB number x 10 + part
    sel = sel.explode(index_parts=True).reset_index(level=1, names=["", "PART"]).reset_index(drop=True)
    sel["FP_ID"] = sel.LB_ID.str[2:].astype(int) * 10 + sel.PART
    sel[["FP_ID", "LB_ID", "ROOF_M2", "ROOF_H50_M", "AREA_M2", "geometry"]].to_file(out/"footprints.shp")
    return {"lidar_outlines_in_block": int(sel.LB_ID.nunique()), "multi_part_outlines": multi, "footprints": len(sel),
            "area_m2": round(float(sel.geometry.area.sum()), 1)}


def points(out, box):
    import laspy
    x0, y0, x1, y1 = box[0] - BUFFER, box[1] - BUFFER, box[2] + BUFFER, box[3] + BUFFER
    parts, header, used = [], None, []
    for f in sorted(POINTS.glob("*.las")):
        t = f.stem                                     # 12TVLxxyy: 1 km cells
        tx, ty = 400000 + int(t[5:7]) * 1000, 4500000 + int(t[7:9]) * 1000
        if tx >= x1 or tx + 1000 <= x0 or ty >= y1 or ty + 1000 <= y0:
            continue
        las = laspy.read(f)
        m = (las.x >= x0) & (las.x < x1) & (las.y >= y0) & (las.y < y1)
        if header is None:
            header = las.header
        parts.append(las.points[m])
        used.append(t)
    merged = laspy.LasData(laspy.LasHeader(point_format=header.point_format, version=header.version))
    merged.header.scales, merged.header.offsets = header.scales, header.offsets
    merged.points = laspy.ScaleAwarePointRecord(np.concatenate([p.array for p in parts]), header.point_format,
                                                header.scales, header.offsets)
    merged.write(out/"points.las")
    cls = np.asarray(merged.classification)
    return {"tiles": used, "points": int(len(cls)), "roof_class6": int((cls == 6).sum()), "ground_class2": int((cls == 2).sum())}


def run_roofer(out):
    dest = out/"output"
    dest.mkdir()
    cmd = [str(ROOFER), "--lod22", "--id-attribute", "FP_ID", "--srs", SRS, *FLAGS, str(out/"points.las"),
           str(out/"footprints.shp"), str(dest)]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(out))
    (out/"roofer.log").write_text(proc.stdout + proc.stderr, encoding="utf-8")
    wrote = re.search(r"wrote (\d+) buildings in", proc.stdout)
    if proc.returncode != 0 or not wrote:
        raise RuntimeError(f"roofer failed, see {out/'roofer.log'}")
    return {"command": " ".join(cmd[1:4] + FLAGS), "buildings_written": int(wrote.group(1))}


def convert(out):
    import arcpy
    collect = _load("collect_cityjson", LOD2/"collect_cityjson.py")
    split = _load("split_obj", LOD2/"split_obj.py")
    slpk_mod = _load("make_slpk", LOD2.parents[1]/"2026-10-22"/"hosting"/"scene-layers"/"make_slpk.py")
    arcpy.CheckOutExtension("3D")
    record = {}
    city = out/"roofer.city.json"
    record["collect"] = collect.collect(out/"output", city)
    obj = out/"roofer_lod22.obj"
    subprocess.run([str(CJIO), str(city), "lod_filter", "2.2", "export", "obj", str(obj)], capture_output=True, text=True,
                   check=True, cwd=str(out))
    record["obj"] = split.split(obj, out/"obj_parts")
    gdb = Path(arcpy.management.CreateFileGDB(str(out), "pilot.gdb")[0])
    raw = str(gdb/"import")
    arcpy.ddd.Import3DFiles(str(out/"obj_parts"), raw, "ONE_FILE_ONE_FEATURE", arcpy.SpatialReference(6341), "Z_IS_UP",
                            "Wavefront OBJ format (*.obj)")
    fc = str(gdb/"lidar_first_lod22")
    arcpy.management.CopyFeatures(raw, fc)
    arcpy.management.AddField(fc, "FP_ID", "LONG")
    arcpy.management.AddField(fc, "LB_ID", "TEXT", field_length=12)
    arcpy.management.AddField(fc, "LEVEL", "TEXT", field_length=40)
    for name, kind in ROOFER_ATTRS.values():
        arcpy.management.AddField(fc, name, kind, field_length=24 if kind == "TEXT" else None)
    cj = json.loads(city.read_text(encoding="utf-8"))
    with arcpy.da.UpdateCursor(fc, ["Name", "FP_ID", "LB_ID", "LEVEL"] + [v[0] for v in ROOFER_ATTRS.values()]) as cursor:
        for name, *_ in cursor:
            fid = int(name[:-4].split("-")[0])
            attrs = cj["CityObjects"][str(fid)]["attributes"]
            cursor.updateRow([name, fid, f"LB{fid // 10:06d}", "roofer LoD2.2 on the LiDAR outline"] +
                             [attrs.get(k) for k in ROOFER_ATTRS])
    record["features"] = int(arcpy.management.GetCount(fc)[0])
    record["buildings"] = len({r[0] for r in arcpy.da.SearchCursor(fc, ["FP_ID"])})
    slpk = str(out/"lidar_first_pilot.slpk")
    with arcpy.EnvManager(scratchWorkspace=str(out)):
        arcpy.management.Create3DObjectSceneLayerPackage(fc, slpk, arcpy.SpatialReference(4326), slpk_mod.TRANSFORM, "Desktop")
    report = str(out/"pilot-validation.json")
    arcpy.management.ValidateSceneLayerPackage(slpk, report)
    record["slpk"] = {"path": slpk, "mb": round(Path(slpk).stat().st_size / 2**20, 2),
                      "validation_messages": json.loads(Path(report).read_text(encoding="utf-8")).get("Messages")}
    return record


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out", type=Path)
    p.add_argument("--centre", type=float, nargs=2, default=CHAMBERS)
    p.add_argument("--half", type=float, default=250.0)
    a = p.parse_args(argv)
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    cx, cy = a.centre
    box = (cx - a.half, cy - a.half, cx + a.half, cy + a.half)
    record = {"schema": "lidar-first-roofer-pilot/1", "created": datetime.datetime.now().isoformat(timespec="seconds"),
              "box": box, "roofer": str(ROOFER), "flags": FLAGS}
    record["footprints"] = footprints(out, box)
    print(record["footprints"], flush=True)
    record["points"] = points(out, box)
    print(record["points"], flush=True)
    record["run"] = run_roofer(out)
    print(record["run"], flush=True)
    record["convert"] = convert(out)
    (out/"pilot.json").write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
    print(json.dumps(record["convert"], indent=1, default=str))


if __name__ == "__main__":
    main()
