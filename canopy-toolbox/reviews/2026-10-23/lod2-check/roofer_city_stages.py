r"""The later stages of roofer_city.py: convert, score, hybrid (October 24, 2026). Not run on its own.

- convert: roofer's per-tile CityJSONSeq files into one CityJSON (vertices re-expressed on the first file's translate, so
  each is moved by at most 0.5 mm), cjio to OBJ, one OBJ per building, Import 3D Files, attributes, checks, a citywide raster.
- score: every building's roofer LoD2.2 put through lod2_check.py's measure with Esri's filled LOD1.2 as the flat baseline,
  so its verdicts use exactly the rules of the Esri check.
- hybrid: per building roofer where it passes, else Esri LOD2.0 where that passes, else Esri LOD1.2; one feature class,
  a scene layer package, its validation, and the pooled errors of the combination.
"""
import collections
import csv
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np

import roofer_city as rc
import roofer_to_multipatch as rm

lc = rm.lc
slpk_mod = rm.slpk_mod


def log(msg):
    rc.log(msg)


# ---------------------------------------------------------------- convert
def collect_city(output_dir, out_json, pattern="*/*.city.jsonl"):
    files = sorted(Path(output_dir).glob(pattern))
    head, scale, base = None, None, None
    objects, vertices, worst_shift, dropped = {}, [], 0.0, []
    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        h = json.loads(lines[0])
        if head is None:
            head, scale, base = h, np.array(h["transform"]["scale"]), np.array(h["transform"]["translate"])
        elif list(scale) != list(h["transform"]["scale"]):
            raise ValueError(f"{path}: another scale")
        move = (np.array(h["transform"]["translate"])-base)/scale
        shift = np.rint(move).astype(np.int64)
        worst_shift = max(worst_shift, float(np.abs((move-shift)*scale).max()))
        for line in lines[1:]:
            f = json.loads(line)
            first = len(vertices)
            vertices.extend((np.array(f["vertices"], np.int64)+shift).tolist())
            for key, obj in f["CityObjects"].items():
                if key in objects:
                    # a footprint with a degenerate extra part gets a second Building (extrusion mode skip, no children)
                    old = objects[key]
                    if old.get("children") and not obj.get("children"):
                        dropped.append({"id": key, "kept": old["attributes"].get("rf_extrusion_mode"),
                                        "dropped": obj["attributes"].get("rf_extrusion_mode")})
                        continue
                    if obj.get("children") and not old.get("children"):
                        dropped.append({"id": key, "kept": obj["attributes"].get("rf_extrusion_mode"),
                                        "dropped": old["attributes"].get("rf_extrusion_mode")})
                    else:
                        raise ValueError(f"duplicate CityObject {key} with geometry in both")
                for g in obj.get("geometry", []):
                    g["boundaries"] = rm.collect_mod._shift(g["boundaries"], first)
                objects[key] = obj
    city = {"type": "CityJSON", "version": head["version"],
            "transform": {"scale": head["transform"]["scale"], "translate": base.tolist()},
            "metadata": head.get("metadata", {}), "CityObjects": objects, "vertices": vertices}
    Path(out_json).write_text(json.dumps(city), encoding="utf-8")
    kinds = collections.Counter(o["type"] for o in objects.values())
    return {"files": len(files), "city_objects": dict(kinds), "vertices": len(vertices),
            "worst_vertex_move_m": round(worst_shift, 5),
            "duplicate_buildings_dropped": dropped}


def split_by_building(obj_path, out):
    """One OBJ per building (all its parts), named <FP_ID>.obj."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    vertices, objects, current = [], collections.defaultdict(list), None
    for line in Path(obj_path).read_text(encoding="utf-8").splitlines():
        if line.startswith("v "):
            vertices.append(line)
        elif line.startswith("o "):
            current = line[2:].strip().split("-")[0]
        elif line.startswith("f ") and current is not None:
            objects[current].append([int(t.split("/")[0]) for t in line.split()[1:]])
    for name, faces in objects.items():
        used = sorted({i for f in faces for i in f})
        remap = {old: new for new, old in enumerate(used, 1)}
        lines = [f"o {name}"] + [vertices[i-1] for i in used] + ["f " + " ".join(str(remap[i]) for i in f) for f in faces]
        (out/f"{name}.obj").write_text("\n".join(lines)+"\n", encoding="utf-8")
    return {"buildings": len(objects), "faces": sum(len(f) for f in objects.values())}


def ensure_cjio(out):
    venv = out/"tools"/"cjio-venv"
    cjio = venv/"Scripts"/"cjio.exe"
    if cjio.exists():
        return cjio
    env = {**os.environ, "PYTHONNOUSERSITE": "1", "UV_LINK_MODE": "copy"}
    (out/"tools").mkdir(exist_ok=True)
    subprocess.run(["uv", "venv", str(venv), "--python", "C:/Python313/python.exe"], check=True, env=env)
    subprocess.run(["uv", "pip", "install", "--python", str(venv/"Scripts"/"python.exe"), "cjio", "triangle"],
                   check=True, env=env)
    return cjio


def venv_python(cjio):
    return Path(cjio).parent/"python.exe"


def _subset(cj, ids):
    objs = {}
    for i in ids:
        objs[i] = cj["CityObjects"][i]
        for c in cj["CityObjects"][i].get("children", []):
            objs[c] = cj["CityObjects"][c]
    return {**cj, "CityObjects": objs}


EXPORT_TIMEOUT_S = (30, 0.2)   # seconds: base plus per building; a normal tile of 565 buildings exports in about 4 s


def _export(cjio, cj, ids, work, tag, env, stats):
    """OBJ files for these buildings. cjio's default triangulator (`triangle`) can crash the process on one bad face; then the
    buildings are halved until the one that crashes is alone, and only that building is triangulated by earcut (--sloppy)."""
    if not ids:
        return []
    sub, obj = work/f"{tag}.city.json", work/f"{tag}.obj"
    sub.write_text(json.dumps(_subset(cj, ids)), encoding="utf-8")
    obj.unlink(missing_ok=True)
    try:
        p = subprocess.run([str(cjio), str(sub), "lod_filter", "2.2", "export", "obj", str(obj)], capture_output=True,
                           text=True, env=env, cwd=str(work), timeout=EXPORT_TIMEOUT_S[0] + EXPORT_TIMEOUT_S[1] * len(ids))
        code = p.returncode
    except subprocess.TimeoutExpired:   # October 26: triangle can also hang on a bad face; treat it as a crash
        code = "timeout"
    if code == 0 and obj.exists():
        stats["triangle"] += len(ids)
        return [obj]
    stats["crashed_calls"].append({"tag": tag, "buildings": len(ids), "returncode": code})
    if len(ids) == 1:
        obj.unlink(missing_ok=True)
        subprocess.run([str(cjio), str(sub), "lod_filter", "2.2", "export", "--sloppy", "obj", str(obj)], capture_output=True,
                       text=True, check=True, env=env, cwd=str(work))
        stats["earcut"].append(ids[0])
        return [obj]
    mid = len(ids)//2
    return (_export(cjio, cj, ids[:mid], work, tag+"a", env, stats) +
            _export(cjio, cj, ids[mid:], work, tag+"b", env, stats))


def closed_solids_dir(folder):
    """Buildings whose OBJ has an edge not shared by exactly two triangles (vertices keyed by coordinates)."""
    n = bad = 0
    examples = []
    for path in sorted(Path(folder).glob("*.obj")):
        r = rm.closed_solids(path)
        n += r["objects"]
        if r["with_open_or_nonmanifold_edges"]:
            bad += r["with_open_or_nonmanifold_edges"]
            if len(examples) < 5:
                examples.append(path.stem)
    return {"buildings": n, "with_open_or_nonmanifold_edges": bad, "examples": examples}


def building_extents(fc, city_json):
    """Each building multipatch's extent against its parts' LoD2.2 vertices in the CityJSON."""
    import arcpy
    city = json.loads(Path(city_json).read_text(encoding="utf-8"))
    verts = np.array(city["vertices"], float)*np.array(city["transform"]["scale"])+np.array(city["transform"]["translate"])

    def idx(b):
        return [b] if isinstance(b, int) else [i for p in b for i in idx(p)]
    worst, n, over = 0.0, 0, []
    for fid, shape in arcpy.da.SearchCursor(fc, ["FP_ID", "SHAPE@"]):
        parts = city["CityObjects"][str(fid)].get("children", [])
        ii = sorted({i for p in parts for g in city["CityObjects"][p]["geometry"] if g["lod"] == "2.2" for i in idx(g["boundaries"])})
        lo, hi = verts[ii].min(0), verts[ii].max(0)
        e = shape.extent
        d = max(abs(e.XMin-lo[0]), abs(e.YMin-lo[1]), abs(e.ZMin-lo[2]), abs(e.XMax-hi[0]), abs(e.YMax-hi[1]), abs(e.ZMax-hi[2]))
        worst = max(worst, d)
        n += 1
        if d > 0.002:
            over.append(fid)
    return {"checked": n, "worst_extent_difference_m": round(worst, 4), "over_2mm": len(over), "examples": over[:5]}


def convert(out):
    import arcpy
    arcpy.CheckOutExtension("3D")
    conv = out/"convert"
    conv.mkdir(exist_ok=True)
    record = {"schema": "roofer-city-convert/1", "started": datetime.datetime.now().isoformat(timespec="seconds")}
    city = conv/"roofer.city.json"
    if not city.exists():
        record["collect"] = collect_city(out/"output", city)
        log(f"collect: {record['collect']}")
    cjio = ensure_cjio(out)
    parts = conv/"obj_buildings"
    if not parts.exists():
        env = {**os.environ, "PYTHONNOUSERSITE": "1"}
        work = conv/"cjio-work"
        work.mkdir(exist_ok=True)
        stats = {"triangle": 0, "earcut": [], "crashed_calls": []}
        total = 0
        for d in sorted((out/"output").iterdir()):
            tile_json = work/f"{d.name}.city.json"
            collect_city(d, tile_json, "*.city.jsonl")
            cj = json.loads(tile_json.read_text(encoding="utf-8"))
            ids = [k for k, o in cj["CityObjects"].items() if o["type"] == "Building" and o.get("children")]
            for obj in _export(cjio, cj, ids, work, d.name+"_t", env, stats):
                total += split_by_building(obj, parts)["buildings"]
            log(f"obj {d.name}: {len(ids)} buildings (earcut so far {len(stats['earcut'])})")
        record["obj"] = {"buildings": total, **stats}
        shutil.rmtree(work)
    record["obj_triangulation"] = record.get("obj")
    gdb = conv/"roofer.gdb"
    if not arcpy.Exists(str(gdb)):
        arcpy.management.CreateFileGDB(str(conv), gdb.name)
    raw, fc = str(gdb/"import"), str(gdb/"roofer_lod22")
    if not arcpy.Exists(fc):
        arcpy.ddd.Import3DFiles(str(parts), raw, "ONE_FILE_ONE_FEATURE", arcpy.SpatialReference(6341), "Z_IS_UP",
                                "Wavefront OBJ format (*.obj)")
        arcpy.management.CopyFeatures(raw, fc)
        arcpy.management.AddField(fc, "FP_ID", "LONG")
        arcpy.management.AddField(fc, "PARTS", "LONG")
        for key, (name, kind) in rm.ROOFER.items():
            arcpy.management.AddField(fc, name, kind, field_length=24 if kind == "TEXT" else None)
        cj = json.loads(city.read_text(encoding="utf-8"))
        with arcpy.da.UpdateCursor(fc, ["Name", "FP_ID", "PARTS"] + [v[0] for v in rm.ROOFER.values()]) as cursor:
            for name, *_ in cursor:
                fid = int(name[:-4])
                b = cj["CityObjects"][str(fid)]
                cursor.updateRow([name, fid, len(b.get("children", []))] + [b["attributes"].get(k) for k in rm.ROOFER])
        arcpy.management.JoinField(fc, "FP_ID", str(rc.FILLED/"massing.gdb"/"footprints"), "FP_ID", list(rm.COUNTY))
    ids = [r[0] for r in arcpy.da.SearchCursor(fc, ["FP_ID"])]
    record["features"] = len(ids)
    record["unique_fp_ids"] = len(set(ids))
    record["multi_part_buildings"] = sum(1 for r in arcpy.da.SearchCursor(fc, ["PARTS"]) if r[0] and r[0] > 1)
    record["checks"] = {"extent_vs_cityjson": building_extents(fc, city), "closed_solids_in_obj": closed_solids_dir(parts)}
    log(f"checks: {record['checks']}")
    target = str(conv/"roofer_lod22_z.tif")
    if not arcpy.Exists(target):
        with arcpy.EnvManager(scratchWorkspace=str(conv), extent=str(lc.ROOF), snapRaster=str(lc.ROOF),
                              cellSize=str(lc.ROOF), outputCoordinateSystem=arcpy.SpatialReference(6341), compression="LZW"):
            arcpy.conversion.MultipatchToRaster(fc, target, 0.5, "MAXIMUM_HEIGHT")
    record["raster"] = target
    record["feature_class"] = fc
    record["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
    (conv/"convert.json").write_text(json.dumps(record, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- score
def _link(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def score(out):
    import arcpy
    conv, check = out/"convert", out/"check"
    check.mkdir(exist_ok=True)
    fc = str(conv/"roofer.gdb"/"roofer_lod22")
    for name in ("fp_id.tif", "lod12_z.tif"):
        if not (check/name).exists():
            _link(rc.CHECK_FILLED/name, check/name)
    if not (check/"lod20_z.tif").exists():
        _link(conv/"roofer_lod22_z.tif", check/"lod20_z.tif")
    gdb = out/"score.gdb"
    if not arcpy.Exists(str(gdb)):
        arcpy.management.CreateFileGDB(str(out), gdb.name)
        arcpy.management.CopyFeatures(str(rc.FILLED/"massing.gdb"/"footprints"), str(gdb/"footprints"))
        arcpy.management.CopyRows(str(rc.FILLED/"massing.gdb"/"lod12"), str(gdb/"lod12"))
        arcpy.management.CopyRows(fc, str(gdb/"lod20"))
        table = str(gdb/"lod20")
        for name in ("TOP_Z", "RMSE", "PCT_HI_ERR"):
            arcpy.management.AddField(table, name, "DOUBLE")
        top = {fid: s.extent.ZMax for fid, s in arcpy.da.SearchCursor(fc, ["FP_ID", "SHAPE@"])}
        with arcpy.da.UpdateCursor(table, ["FP_ID", "TOP_Z", "RMSE", "RF_RMSE_LOD22"]) as cursor:
            for fid, _, _, rmse in cursor:
                cursor.updateRow([fid, top.get(fid), rmse, rmse])
    lc.MASSING = gdb
    log("measure: every building, roofer LoD2.2 in the LOD2.0 slot, Esri filled LOD1.2 as the baseline")
    lc.measure(check)


# ---------------------------------------------------------------- hybrid
def _num(r, k):
    v = r.get(k)
    return float(v) if v not in (None, "", "None") else np.nan


def load(path):
    return {int(r["FP_ID"]): r for r in csv.DictReader(open(path, encoding="utf-8"))}


def decide(roofer, esri):
    """FP_ID -> (level, reason, verdicts)."""
    choice = {}
    for fid, e in esri.items():
        r = roofer.get(fid)
        r_ok = (r is not None and _num(r, "LOD20_CELLS") > 0 and r["VERDICT"] in ("better", "same")
                and not _num(r, "LOD20_GROUND_PCT") >= 10)
        e_ok = e["VERDICT"] in ("better", "same") and not _num(e, "LOD20_GROUND_PCT") >= 10
        if r_ok:
            level, reason = "roofer LoD2.2", ""
        elif e_ok:
            level, reason = "Esri LOD2.0", "roofer " + _why(r)
        else:
            level, reason = "Esri LOD1.2", f"roofer {_why(r)}; Esri LOD2.0 {_why(e, esri=True)}"
        choice[fid] = (level, reason, r["VERDICT"] if r is not None and _num(r, "LOD20_CELLS") > 0 else "no-model",
                       e["VERDICT"])
    return choice


def _why(r, esri=False):
    if r is None or (not esri and _num(r, "LOD20_CELLS") == 0):
        return "no-geometry"
    if r["VERDICT"] in ("too-few", "worse", "broken"):
        return r["VERDICT"]
    return "ground-level"


def pooled(rows, pick, key_cells="CELLS"):
    cells = w5 = w1 = 0.0
    for fid, e in rows.items():
        src = pick(fid)
        if src is None:
            continue
        r, k = src
        n = _num(r, f"{k}_CELLS")
        if not n or n != n or r.get(f"{k}_WITHIN_1_PCT") in (None, "", "None"):
            continue
        cells += n
        w5 += n*_num(r, f"{k}_WITHIN_05_PCT")
        w1 += n*_num(r, f"{k}_WITHIN_1_PCT")
    return {"cells": int(cells), "within_05_pct": round(w5/cells, 2), "within_1_pct": round(w1/cells, 2)}


def hybrid(out):
    import arcpy
    arcpy.CheckOutExtension("3D")
    check = out/"check"
    roofer = load(check/"lod2-check.csv")
    esri = load(rc.CHECK_FILLED/"lod2-check.csv")
    choice = decide(roofer, esri)
    counts = collections.Counter(c[0] for c in choice.values())
    judged = {fid for fid, e in esri.items() if e["VERDICT"] != "too-few"}
    summary = {"buildings": len(choice), "levels": dict(counts),
               "reasons": {f"{k[0]} | {k[1]}": n for k, n in
                           collections.Counter((c[0], c[1]) for c in choice.values() if c[1]).most_common(12)}}
    mix = lambda fid: ((roofer[fid], "LOD20") if choice[fid][0] == "roofer LoD2.2" else
                       (esri[fid], "LOD20") if choice[fid][0] == "Esri LOD2.0" else (esri[fid], "LOD12"))
    in_judged = {f: None for f in judged}
    summary["pooled_within"] = {
        "all roofer LoD2.2 (where it has geometry)": pooled(in_judged, lambda f: (roofer[f], "LOD20") if f in roofer else None),
        "all Esri LOD2.0": pooled(in_judged, lambda f: (esri[f], "LOD20")),
        "all Esri LOD1.2": pooled(in_judged, lambda f: (esri[f], "LOD12")),
        "Esri-only hybrid (LOD2.0 else LOD1.2)": pooled(
            in_judged, lambda f: (esri[f], "LOD20") if (esri[f]["VERDICT"] in ("better", "same")
                                                           and not _num(esri[f], "LOD20_GROUND_PCT") >= 10) else (esri[f], "LOD12")),
        "three-way hybrid": pooled(in_judged, mix)}
    summary["by_type"] = {}
    for t in sorted({e["ROOF_TYPE"] for e in esri.values()}):
        ids = [f for f, e in esri.items() if e["ROOF_TYPE"] == t]
        summary["by_type"][t] = {"buildings": len(ids), **dict(collections.Counter(choice[f][0] for f in ids))}
    summary["verdict_matrix"] = {f"roofer {a} / Esri {b}": n for (a, b), n in sorted(
        collections.Counter((c[2], c[3]) for c in choice.values()).items(), key=lambda x: -x[1])[:12]}
    # feature class: roofer rows, Esri LOD2.0 rows, Esri LOD1.2 rows, one per FP_ID
    gdb = out/"hybrid.gdb"
    if arcpy.Exists(str(gdb)):
        arcpy.management.Delete(str(gdb))
    arcpy.management.CreateFileGDB(str(out), gdb.name)
    final = str(gdb/"buildings_three_way")
    arcpy.management.CopyFeatures(str(out/"convert"/"roofer.gdb"/"roofer_lod22"), final)
    for level, source in (("Esri LOD2.0", str(rc.FILLED/"massing.gdb"/"lod20")),
                          ("Esri LOD1.2", str(rc.FILLED/"massing.gdb"/"lod12"))):
        want = {fid for fid, c in choice.items() if c[0] == level}
        part = str(gdb/("part_"+level.split()[1].replace(".", "")))
        arcpy.management.CopyFeatures(source, part)
        with arcpy.da.UpdateCursor(part, ["FP_ID"]) as cursor:
            for (fid,) in cursor:
                if fid not in want:
                    cursor.deleteRow()
        arcpy.management.Append(part, final, "NO_TEST")
    want_roofer = {fid for fid, c in choice.items() if c[0] == "roofer LoD2.2"}
    # remove roofer rows that were not chosen: they are the first rows (before the appended Esri parts)
    n_roofer_rows = int(arcpy.management.GetCount(str(out/"convert"/"roofer.gdb"/"roofer_lod22"))[0])
    with arcpy.da.UpdateCursor(final, ["OID@", "FP_ID"]) as cursor:
        for oid, fid in cursor:
            if oid <= n_roofer_rows and fid not in want_roofer:
                cursor.deleteRow()
    for name, kind, length in (("LEVEL", "TEXT", 16), ("CHECK_VERDICT", "TEXT", 10), ("ROOFER_VERDICT", "TEXT", 10),
                               ("ESRI_VERDICT", "TEXT", 10), ("FALLBACK_REASON", "TEXT", 60)):
        arcpy.management.AddField(final, name, kind, field_length=length)
    seen = collections.Counter()
    with arcpy.da.UpdateCursor(final, ["FP_ID", "LEVEL", "CHECK_VERDICT", "ROOFER_VERDICT", "ESRI_VERDICT",
                                       "FALLBACK_REASON"]) as cursor:
        for fid, *_ in cursor:
            level, reason, rv, ev = choice[fid]
            verdict = roofer[fid]["VERDICT"] if level == "roofer LoD2.2" else esri[fid]["VERDICT"]
            cursor.updateRow([fid, level, verdict, rv, ev, reason])
            seen[fid] += 1
    summary["features"] = sum(seen.values())
    summary["fp_ids_once"] = all(v == 1 for v in seen.values()) and len(seen) == len(choice)
    slpk = str(out/"buildings_three_way.slpk")
    Path(slpk).unlink(missing_ok=True)
    Path(out/"three-way-validation.json").unlink(missing_ok=True)
    with arcpy.EnvManager(scratchWorkspace=str(out)):
        arcpy.management.Create3DObjectSceneLayerPackage(final, slpk, arcpy.SpatialReference(4326), slpk_mod.TRANSFORM,
                                                         "Desktop")
    report = str(out/"three-way-validation.json")
    arcpy.management.ValidateSceneLayerPackage(slpk, report)
    stats = slpk_mod.package_stats(slpk)
    ids = [r[0] for r in arcpy.da.SearchCursor(final, ["FP_ID"])]
    summary["slpk"] = {"path": slpk, "mb": round(Path(slpk).stat().st_size/2**20, 1), "package": stats,
                       "fp_id_stats_equal_source": (stats["fp_id_count"], stats["fp_id_sum"]) == (len(ids), sum(ids)),
                       "validation_messages": json.loads(Path(report).read_text(encoding="utf-8")).get("Messages")}
    with open(out/"three-way.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["FP_ID", "LEVEL", "ROOFER_VERDICT", "ESRI_VERDICT", "FALLBACK_REASON"])
        for fid in sorted(choice):
            w.writerow([fid, choice[fid][0], choice[fid][2], choice[fid][3], choice[fid][1]])
    (out/"three-way.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
