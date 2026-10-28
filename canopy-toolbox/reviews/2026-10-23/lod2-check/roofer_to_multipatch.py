r"""Roofer's CityJSON to a multipatch feature class and a scene layer package (October 24, 2026).

    python reviews/2026-10-23/lod2-check/roofer_to_multipatch.py ROOFER_DIR OUT [--cjio PATH_TO_CJIO.EXE]

ArcGIS Pro Python with 3D Analyst (PYTHONNOUSERSITE=1), plus cjio in its own virtual environment (ROOFER_DIR\tools\cjio-venv:
`uv venv`, then `uv pip install --python <venv python> cjio triangle`; nothing user-wide). Read-only on ROOFER_DIR\output;
writes only OUT (a new folder). Nothing is uploaded.
Route, each step checked:
  1. collect_cityjson.py: roofer's CityJSONSeq to one CityJSON.
  2. cjio: lod_filter 2.2, export obj (real-world UTM metres, one `o` object per BuildingPart).
  3. split_obj.py: one OBJ per part (Import 3D Files merges a file's objects into one feature).
  4. Import 3D Files (ONE_FILE_ONE_FEATURE, NAD83(2011) UTM 12N, Z up): one multipatch per part.
  5. FP_ID, roofer's attributes and the county footprint attributes added.
  6. Checks: each multipatch's extent against its vertices in the CityJSON; closed solids in the OBJ; the multipatches
     rasterized (Multipatch To Raster) against score_roofer.py's own rasterization of the CityJSON roof faces.
  7. make_slpk.py's packaging (WGS84, ITRF08 transformation named) and Validate Scene Layer Package.
"""
import argparse
import collections
import importlib.util
import json
from pathlib import Path
import subprocess

import numpy as np

HERE = Path(__file__).resolve()


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collect_mod = _load("collect_cityjson", HERE.parent/"collect_cityjson.py")
split_mod = _load("split_obj", HERE.parent/"split_obj.py")
lc = _load("lod2_check", HERE.parent/"lod2_check.py")
slpk_mod = _load("make_slpk", HERE.parents[2]/"2026-10-22"/"hosting"/"scene-layers"/"make_slpk.py")
WINDOW = (428000.0, 4504000.0, 429000.0, 4505000.0)
COUNTY = ("SOURCE_ID", "PARCEL_ID", "CITY", "FOOTPRINT_M2", "ROOF_COV_PCT", "ROOF_Z50_M", "GROUND_Z50_M", "HEIGHT_P50_M",
          "HEIGHT_P95_M", "HEIGHT_STATUS")
ROOFER = {"rf_roof_type": ("RF_ROOF_TYPE", "TEXT"), "rf_roof_planes": ("RF_ROOF_PLANES", "LONG"),
          "rf_ridgelines": ("RF_RIDGELINES", "LONG"), "rf_rmse_lod22": ("RF_RMSE_LOD22", "DOUBLE"),
          "rf_h_ground": ("RF_H_GROUND", "DOUBLE"), "rf_h_roof_max": ("RF_H_ROOF_MAX", "DOUBLE"),
          "rf_pt_density": ("RF_PT_DENSITY", "DOUBLE"), "rf_extrusion_mode": ("RF_EXTRUSION", "TEXT")}


def closed_solids(obj_path):
    """Open or non-manifold edges per OBJ object (vertices keyed by coordinates, so shared corners count once)."""
    verts, faces, current, objects = [], collections.defaultdict(list), None, []
    for line in Path(obj_path).read_text(encoding="utf-8").splitlines():
        if line.startswith("v "):
            verts.append(tuple(round(float(t), 3) for t in line.split()[1:4]))
        elif line.startswith("o "):
            current = line[2:].strip()
            objects.append(current)
        elif line.startswith("f "):
            faces[current].append([verts[int(t.split("/")[0])-1] for t in line.split()[1:]])
    bad = {}
    for name in objects:
        edges = collections.Counter()
        for f in faces[name]:
            for a, b in zip(f, f[1:]+f[:1]):
                if a != b:
                    edges[frozenset((a, b))] += 1
        n = sum(1 for c in edges.values() if c != 2)
        if n:
            bad[name] = n
    return {"objects": len(objects), "with_open_or_nonmanifold_edges": len(bad), "examples": dict(list(bad.items())[:5])}


def extents_vs_json(fc, city_json):
    """Each multipatch's extent against the min and max of its CityObject's vertices (metres)."""
    city = json.loads(Path(city_json).read_text(encoding="utf-8"))
    scale, translate = np.array(city["transform"]["scale"]), np.array(city["transform"]["translate"])
    verts = np.array(city["vertices"], float)*scale+translate

    def indices(b):
        return [b] if isinstance(b, int) else [i for part in b for i in indices(part)]
    worst = 0.0
    count = 0
    for name, shape in arcpy_rows(fc, ["PART", "SHAPE@"]):
        obj = city["CityObjects"][name]
        idx = sorted({i for g in obj["geometry"] if g["lod"] == "2.2" for i in indices(g["boundaries"])})
        lo, hi = verts[idx].min(0), verts[idx].max(0)
        e = shape.extent
        worst = max(worst, abs(e.XMin-lo[0]), abs(e.YMin-lo[1]), abs(e.ZMin-lo[2]),
                    abs(e.XMax-hi[0]), abs(e.YMax-hi[1]), abs(e.ZMax-hi[2]))
        count += 1
    return {"checked": count, "worst_extent_difference_m": round(worst, 4)}


def arcpy_rows(fc, fields):
    import arcpy
    return list(arcpy.da.SearchCursor(fc, fields))


def raster_agreement(fc, out, reference):
    """Multipatch To Raster of the imported features against the CityJSON roof faces rasterized by score_roofer.py."""
    import arcpy
    arcpy.CheckOutExtension("3D")
    target = str(out/"roofer_lod22_z.tif")
    x0, y0, x1, y1 = WINDOW
    with arcpy.EnvManager(scratchWorkspace=str(out), extent=f"{x0} {y0} {x1} {y1}", snapRaster=str(lc.ROOF),
                          cellSize=str(lc.ROOF), outputCoordinateSystem=arcpy.SpatialReference(6341), compression="LZW"):
        arcpy.conversion.MultipatchToRaster(fc, target, 0.5, "MAXIMUM_HEIGHT")
    a, _ = lc._grid(target, ((x0, y0), (2000, 2000)))
    b = np.load(reference)
    both = np.isfinite(a) & np.isfinite(b)
    d = np.abs(a[both]-b[both])
    return {"cells_both": int(both.sum()), "only_multipatch": int((np.isfinite(a) & ~np.isfinite(b)).sum()),
            "only_cityjson": int((~np.isfinite(a) & np.isfinite(b)).sum()), "abs_diff_median_m": float(np.median(d)),
            "abs_diff_p99_m": float(np.percentile(d, 99)), "share_within_5cm": float((d <= 0.05).mean()),
            "share_within_25cm": float((d <= 0.25).mean()), "raster": target}


def main(argv=None):
    import arcpy
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("roofer_dir", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--cjio", type=Path)
    a = p.parse_args(argv)
    roofer_dir, out = a.roofer_dir.resolve(), a.out.resolve()
    cjio = a.cjio or roofer_dir/"tools"/"cjio-venv"/"Scripts"/"cjio.exe"
    out.mkdir(parents=True, exist_ok=False)
    arcpy.CheckOutExtension("3D")
    record = {"schema": "roofer-multipatch/1", "roofer_output": str(roofer_dir/"output")}
    city = out/"roofer.city.json"
    record["collect"] = collect_mod.collect(roofer_dir/"output", city)
    obj = out/"roofer_lod22.obj"
    log = subprocess.run([str(cjio), str(city), "lod_filter", "2.2", "export", "obj", str(obj)], capture_output=True,
                         text=True, check=True, cwd=str(out))
    record["cjio"] = {"version": subprocess.run([str(cjio), "--version"], capture_output=True, text=True).stdout.strip(),
                      "log": log.stdout.strip().splitlines()[-3:]}
    record["obj"] = split_mod.split(obj, out/"obj_parts")
    gdb = Path(arcpy.management.CreateFileGDB(str(out), "roofer.gdb")[0])
    raw = str(gdb/"import")
    arcpy.ddd.Import3DFiles(str(out/"obj_parts"), raw, "ONE_FILE_ONE_FEATURE", arcpy.SpatialReference(6341), "Z_IS_UP",
                            "Wavefront OBJ format (*.obj)")
    fc = str(gdb/"roofer_lod22")
    arcpy.management.CopyFeatures(raw, fc)
    arcpy.management.AddField(fc, "PART", "TEXT", field_length=20)
    arcpy.management.AddField(fc, "FP_ID", "LONG")
    for key, (name, kind) in ROOFER.items():
        arcpy.management.AddField(fc, name, kind, field_length=24 if kind == "TEXT" else None)
    cj = json.loads(city.read_text(encoding="utf-8"))
    with arcpy.da.UpdateCursor(fc, ["Name", "PART", "FP_ID"] + [v[0] for v in ROOFER.values()]) as cursor:
        for name, *_ in cursor:
            part = name[:-4]
            fid = int(part.split("-")[0])
            attrs = cj["CityObjects"][str(fid)]["attributes"]
            cursor.updateRow([name, part, fid] + [attrs.get(k) for k in ROOFER])
    county = str(lc.MASSING/"footprints")
    arcpy.management.JoinField(fc, "FP_ID", county, "FP_ID", list(COUNTY))
    record["features"] = int(arcpy.management.GetCount(fc)[0])
    ids = [r[0] for r in arcpy.da.SearchCursor(fc, ["FP_ID"])]
    record["unique_fp_ids"] = len(set(ids))
    record["feature_class"] = fc
    record["checks"] = {"extent_vs_cityjson": extents_vs_json(fc, city), "closed_solids_in_obj": closed_solids(obj),
                        "raster_vs_cityjson_roof": raster_agreement(fc, out, roofer_dir/"check"/"R22_z.npy")}
    slpk = str(out/"buildings_roofer_lod22.slpk")
    with arcpy.EnvManager(scratchWorkspace=str(out)):
        arcpy.management.Create3DObjectSceneLayerPackage(fc, slpk, arcpy.SpatialReference(4326), slpk_mod.TRANSFORM, "Desktop")
    report = str(out/"roofer-validation.json")
    arcpy.management.ValidateSceneLayerPackage(slpk, report)
    stats = slpk_mod.package_stats(slpk)
    record["slpk"] = {"path": slpk, "mb": round(Path(slpk).stat().st_size/2**20, 2), "package": stats,
                      "fp_id_stats_equal_source": (stats["fp_id_count"], stats["fp_id_sum"]) == (len(ids), sum(ids)),
                      "validation_messages": json.loads(Path(report).read_text(encoding="utf-8")).get("Messages")}
    (out/"roofer-multipatch.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps(record, indent=1))


if __name__ == "__main__":
    main()
