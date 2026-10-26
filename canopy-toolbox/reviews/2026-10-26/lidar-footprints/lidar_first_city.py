r"""Roofer LoD2.2 on every LiDAR-first outline in Millcreek (October 26, 2026), after the Chambers Avenue pilot.

    python lidar_first_city.py prep    OUT     LiDAR outlines per tile (parts numbered FP_ID = LB number x 10 + part)
    python lidar_first_city.py run     OUT     roofer per tile, exactly as the October 24 v2 run (roofer_city.run)
    python lidar_first_city.py convert OUT     one CityJSON, one OBJ and one multipatch per building, LB_ID and roofer fields
    python lidar_first_city.py compose OUT     the candidate package: LiDAR-first models, plus today's model where trees hide
                                               a county building from the LiDAR

ArcGIS Pro Python with 3D Analyst (millcreek-py3; laspy; PYTHONNOUSERSITE=1). Read-only on every input; writes only OUT.
Nothing is uploaded. Same points (the citywide run's consensus roof and ground per tile), roofer 1.0.0 and
`--plane-detect-min-points 30` as v2; only the footprints change: runs\lidar-footprints-20261026\city\lidar.gdb\buildings,
each part given to the tile holding its inside point, with that tile's points plus every neighbour's points inside the
parts' extent plus 20 m (roofer_city._merge). Every stage resumes: finished tiles are skipped.
"""
import argparse
import datetime
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve()
LOD2 = HERE.parents[1].parent/"2026-10-23"/"lod2-check"
sys.path.insert(0, str(LOD2))
import roofer_city as rc  # noqa: E402

LIDAR = rc.RUNS/"lidar-footprints-20261026"/"city"/"lidar.gdb"
POINTS = rc.RUNS/"roofer-city-20261024"/"points"
V2 = rc.RUNS/"roofer-city-v2-20261024"
FLAGS = ["--plane-detect-min-points", "30"]


def prep(out):
    import geopandas as gpd
    out.mkdir(parents=True, exist_ok=True)
    lidar = gpd.read_file(LIDAR, layer="buildings")
    parts = lidar.explode(index_parts=True).reset_index(level=1, names=["", "PART"]).reset_index(drop=True)
    parts["FP_ID"] = parts.LB_ID.str[2:].astype(int) * 10 + parts.PART
    assert parts.FP_ID.is_unique
    inside = parts.geometry.representative_point()
    cells = {(int(b[0] // 1000), int(b[1] // 1000)): t for t, b in rc.tiles().items()}
    parts["TILE"] = [cells.get((int(p.x // 1000), int(p.y // 1000)), "NONE") for p in inside]
    (out/"footprints").mkdir(exist_ok=True)
    info = {}
    for tile, g in parts.groupby("TILE"):
        x0, y0, x1, y1 = g.total_bounds
        info[tile] = {"n": len(g), "xmin": x0, "ymin": y0, "xmax": x1, "ymax": y1}
        if tile != "NONE":
            g[["FP_ID", "LB_ID", "AREA_M2", "geometry"]].to_file(out/"footprints"/f"{tile}.shp")
    record = {"schema": "lidar-first-city-prep/1", "created": datetime.datetime.now().isoformat(timespec="seconds"),
              "outlines": int(lidar.LB_ID.nunique()), "parts": len(parts), "tiles_with_footprints": len([t for t in info if t != "NONE"]),
              "outside_every_tile": info.get("NONE", {}).get("n", 0), "tiles": info}
    (out/"prep.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(f"prep: {record['outlines']} outlines, {record['parts']} parts, {record['tiles_with_footprints']} tiles, "
          f"{record['outside_every_tile']} outside every tile", flush=True)


def run(out):
    if not (out/"roofer-1.0.0").exists():
        shutil.copytree(V2/"roofer-1.0.0", out/"roofer-1.0.0")
    rc.run(out, flags=FLAGS, points_from=str(POINTS))


def convert(out):
    import arcpy
    import roofer_city_stages as st
    arcpy.CheckOutExtension("3D")
    conv = out/"convert"
    conv.mkdir(exist_ok=True)
    record = {"schema": "lidar-first-city-convert/1", "started": datetime.datetime.now().isoformat(timespec="seconds")}
    city = conv/"roofer.city.json"
    if not city.exists():
        record["collect"] = st.collect_city(out/"output", city)
    if not (out/"tools").exists():
        shutil.copytree(V2/"tools", out/"tools")
    cjio = st.ensure_cjio(out)
    parts = conv/"obj_buildings"
    if not parts.exists():
        import os
        env = {**os.environ, "PYTHONNOUSERSITE": "1"}
        work = conv/"cjio-work"
        work.mkdir(exist_ok=True)
        stats = {"triangle": 0, "earcut": [], "crashed_calls": []}
        total = 0
        for d in sorted((out/"output").iterdir()):
            tile_json = work/f"{d.name}.city.json"
            st.collect_city(d, tile_json, "*.city.jsonl")
            cj = json.loads(tile_json.read_text(encoding="utf-8"))
            ids = [k for k, o in cj["CityObjects"].items() if o["type"] == "Building" and o.get("children")]
            for obj in st._export(cjio, cj, ids, work, d.name + "_t", env, stats):
                total += st.split_by_building(obj, parts)["buildings"]
            print(f"obj {d.name}: {len(ids)} buildings", flush=True)
        record["obj"] = {"buildings": total, **stats}
        shutil.rmtree(work)
    gdb = conv/"lidar_first.gdb"
    if not arcpy.Exists(str(gdb)):
        arcpy.management.CreateFileGDB(str(conv), gdb.name)
    raw, fc = str(gdb/"import"), str(gdb/"lidar_first_lod22")
    if not arcpy.Exists(fc):
        arcpy.ddd.Import3DFiles(str(parts), raw, "ONE_FILE_ONE_FEATURE", arcpy.SpatialReference(6341), "Z_IS_UP",
                                "Wavefront OBJ format (*.obj)")
        arcpy.management.CopyFeatures(raw, fc)
        arcpy.management.AddField(fc, "FP_ID", "LONG")
        arcpy.management.AddField(fc, "LB_ID", "TEXT", field_length=12)
        arcpy.management.AddField(fc, "PARTS", "LONG")
        for name, kind in st.rm.ROOFER.values():
            arcpy.management.AddField(fc, name, kind, field_length=24 if kind == "TEXT" else None)
        cj = json.loads(city.read_text(encoding="utf-8"))
        with arcpy.da.UpdateCursor(fc, ["Name", "FP_ID", "LB_ID", "PARTS"] + [v[0] for v in st.rm.ROOFER.values()]) as cursor:
            for name, *_ in cursor:
                fid = int(name[:-4])
                b = cj["CityObjects"][str(fid)]
                cursor.updateRow([name, fid, f"LB{fid // 10:06d}", len(b.get("children", []))] +
                                 [b["attributes"].get(k) for k in st.rm.ROOFER])
    ids = [r[0] for r in arcpy.da.SearchCursor(fc, ["FP_ID"])]
    prep_info = json.loads((out/"prep.json").read_text(encoding="utf-8"))
    record.update(features=len(ids), unique_fp_ids=len(set(ids)), parts_given=prep_info["parts"],
                  checks={"extent_vs_cityjson": st.building_extents(fc, city), "closed_solids_in_obj": st.closed_solids_dir(parts)},
                  feature_class=fc, finished=datetime.datetime.now().isoformat(timespec="seconds"))
    (conv/"convert.json").write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: record[k] for k in ("features", "unique_fp_ids", "parts_given", "checks")}, indent=1, default=str))


HIDDEN_CANOPY_PCT = 30


def compose(out):
    """The candidate: every LiDAR-first roofer model, plus today's v2 model for each county footprint with no 2023 roof
    and 30% or more canopy over it (the LiDAR is blind there; compare.csv's COUNTY_ONLY groups). Packaged and validated."""
    import csv
    import importlib.util
    import arcpy
    spec = importlib.util.spec_from_file_location("make_slpk", LOD2.parents[1]/"2026-10-22"/"hosting"/"scene-layers"/"make_slpk.py")
    slpk_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(slpk_mod)
    arcpy.CheckOutExtension("3D")
    lidar_fc = str(out/"convert"/"lidar_first.gdb"/"lidar_first_lod22")
    hidden = set()
    with open(rc.RUNS/"lidar-footprints-20261026"/"city"/"compare.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["CLASS"] == "COUNTY_ONLY" and r["COUNTY_CANOPY_PCT"] and float(r["COUNTY_CANOPY_PCT"]) >= HIDDEN_CANOPY_PCT:
                hidden.add(r["COUNTY_IDS"])
    gdb = out/"candidate.gdb"
    if not arcpy.Exists(str(gdb)):
        arcpy.management.CreateFileGDB(str(out), gdb.name)
    county_layer = arcpy.management.MakeFeatureLayer(str(V2/"v2"/"v2.gdb"/"buildings"), "hidden_county",
                                                     "SOURCE_ID IN ({})".format(",".join(f"'{s}'" for s in sorted(hidden))))[0]
    kept_county = int(arcpy.management.GetCount(county_layer)[0])
    target = str(gdb/"buildings")
    if arcpy.Exists(target):
        arcpy.management.Delete(target)
    arcpy.management.Merge([lidar_fc, county_layer], target)
    arcpy.management.AddField(target, "OUTLINE_SOURCE", "TEXT", field_length=60)
    with arcpy.da.UpdateCursor(target, ["LB_ID", "LEVEL", "OUTLINE_SOURCE"]) as cursor:
        for lb, level, _ in cursor:
            if lb:
                cursor.updateRow([lb, "roofer LoD2.2", "LiDAR-first outline (2023)"])
            else:
                cursor.updateRow([lb, level, "County footprint, roof hidden by trees"])
    slpk = str(out/"buildings_lidar_first.slpk")
    Path(slpk).unlink(missing_ok=True)
    with arcpy.EnvManager(scratchWorkspace=str(out)):
        arcpy.management.Create3DObjectSceneLayerPackage(target, slpk, arcpy.SpatialReference(4326), slpk_mod.TRANSFORM, "Desktop")
    report = str(out/"candidate-validation.json")
    arcpy.management.ValidateSceneLayerPackage(slpk, report)
    prep_info = json.loads((out/"prep.json").read_text(encoding="utf-8"))
    lidar_models = int(arcpy.management.GetCount(lidar_fc)[0])
    record = {"schema": "lidar-first-candidate/1", "created": datetime.datetime.now().isoformat(timespec="seconds"),
              "lidar_outline_parts": prep_info["parts"], "lidar_models": lidar_models,
              "lidar_parts_without_a_model": prep_info["parts"] - lidar_models,
              "county_footprints_hidden_by_trees": len(hidden), "of_them_with_a_v2_model": kept_county,
              "features": int(arcpy.management.GetCount(target)[0]), "feature_class": target,
              "slpk": {"path": slpk, "mb": round(Path(slpk).stat().st_size / 2**20, 1),
                       "validation_messages": json.loads(Path(report).read_text(encoding="utf-8")).get("Messages")}}
    (out/"candidate.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps(record, indent=1))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stage", choices=("prep", "run", "convert", "compose"))
    p.add_argument("out", type=Path)
    a = p.parse_args(argv)
    {"prep": prep, "run": run, "convert": convert, "compose": compose}[a.stage](a.out.resolve())


if __name__ == "__main__":
    main()
