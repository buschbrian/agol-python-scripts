r"""3D building massing from the October 22 consensus roofs (October 22, 2026): flat blocks (LOD1.2) and roof forms
(LOD2.0) for every county footprint with a roof height, by ArcGIS Extract LOD2 Buildings.

    python reviews/2026-10-22/massing/run_massing.py pilot OUT     footprints on 12TVL2804 only, to learn and time the tool
    python reviews/2026-10-22/massing/run_massing.py run OUT       every footprint with a roof height
    python reviews/2026-10-22/massing/run_massing.py clean OUT      drop the empty blocks the tool leaves; summarise again

ArcGIS Pro Python with 3D Analyst and Spatial Analyst (PYTHONNOUSERSITE=1). Read-only on the library; writes only under
OUT, which must be on a short path (ArcGIS raster saves fail with ERROR 2592 under the long scratch paths).
- Height source: a surface that is the consensus roof elevation where there is one (`roof_elevation_m.tif`) and the
  unmasked terrain elsewhere (`millcreek-products-20261019\terrain_context.tif`, equal to the city terrain on city cells).
- Footprints: the library's `buildings.gdb/building_heights` with ROOF_Z50_M not null (21,562 of 22,042), each tagged
  FP_ID = its OBJECTID there, so every block joins back to its height statistics.
- Each output block gets BASE_Z and TOP_Z (its multipatch's lowest and highest Z), TERRAIN_MIN_Z (lowest terrain cell
  under the footprint), and the differences TOP_Z - ROOF_Z50_M and BASE_Z - TERRAIN_MIN_Z, which `verify` summarises.
"""
import argparse
import datetime
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve()
TOOLBOX = HERE.parents[3]
sys.path.insert(0, str(TOOLBOX))
from canopy.lidar_root import lidar_root  # noqa: E402

VALLEY = lidar_root()/"2023-salt-lake-valley"
LIB = VALLEY/"runs"/"millcreek-products-20261022"
ROOF = LIB/"roof_elevation_m.tif"
TERRAIN = VALLEY/"runs"/"millcreek-products-20261019"/"terrain_context.tif"
FOOTPRINTS = LIB/"buildings.gdb"/"building_heights"
PILOT_TILE = (428000.0, 4504000.0, 429000.0, 4505000.0)        # 12TVL2804, the labelled tile
LEVELS = {"lod12": "LOD1.2", "lod20": "LOD2.0"}
KEEP = ("FP_ID", "ROOF_Z50_M", "GROUND_Z50_M", "HEIGHT_P50_M", "HEIGHT_P95_M", "ROOF_COV_PCT", "HEIGHT_STATUS")


def prepare(out, window=None):
    """The height surface and the footprints (FP_ID tagged) under OUT; window limits both to an extent."""
    import arcpy
    from arcpy.sa import Con, IsNull, Raster
    out.mkdir(parents=True, exist_ok=False)
    gdb = Path(arcpy.management.CreateFileGDB(str(out), "massing.gdb")[0])
    extent = " ".join(str(v) for v in window) if window else str(ROOF)
    dsm = str(out/"height_source.tif")
    with arcpy.EnvManager(scratchWorkspace=str(out), extent=extent, snapRaster=str(ROOF), cellSize=str(ROOF),
                          compression="LZW", parallelProcessingFactor="100%"):
        Con(IsNull(Raster(str(ROOF))), Raster(str(TERRAIN)), Raster(str(ROOF))).save(dsm)
    footprints = str(gdb/"footprints")
    layer = arcpy.management.MakeFeatureLayer(str(FOOTPRINTS), "fp", "ROOF_Z50_M IS NOT NULL").getOutput(0)
    if window:
        x0, y0, x1, y1 = window
        box = arcpy.Polygon(arcpy.Array([arcpy.Point(x0, y0), arcpy.Point(x1, y0), arcpy.Point(x1, y1),
                                         arcpy.Point(x0, y1)]), arcpy.Describe(str(FOOTPRINTS)).spatialReference)
        arcpy.management.SelectLayerByLocation(layer, "COMPLETELY_WITHIN", box)
    arcpy.management.CopyFeatures(layer, footprints)
    arcpy.management.AddField(footprints, "FP_ID", "LONG")
    oids = {}
    with arcpy.da.SearchCursor(str(FOOTPRINTS), ["OID@", "SOURCE_OID", "GlobalID"]) as cursor:
        for oid, source_oid, global_id in cursor:
            oids[global_id] = oid
    with arcpy.da.UpdateCursor(footprints, ["GlobalID", "FP_ID"]) as cursor:
        for global_id, _ in cursor:
            cursor.updateRow([global_id, oids[global_id]])
    return dsm, footprints, gdb


def terrain_min(footprints, gdb, out):
    """Lowest terrain cell under each footprint (zonal MIN; overlapping footprints are handled one by one)."""
    import arcpy
    table = str(gdb/"terrain_min")
    with arcpy.EnvManager(scratchWorkspace=str(out), snapRaster=str(TERRAIN), cellSize=str(TERRAIN)):
        arcpy.sa.ZonalStatisticsAsTable(footprints, "FP_ID", str(TERRAIN), table, "DATA", "MINIMUM")
    return {fp: z for fp, z in arcpy.da.SearchCursor(table, ["FP_ID", "MIN"])}


def extract(dsm, footprints, gdb, out):
    import arcpy
    paths = {}
    for key, level in LEVELS.items():
        target = str(gdb/key)
        started = datetime.datetime.now()
        with arcpy.EnvManager(scratchWorkspace=str(out)):
            arcpy.ddd.ExtractLOD2Buildings(dsm, footprints, target, level)
        paths[key] = {"path": target, "seconds": round((datetime.datetime.now()-started).total_seconds())}
        print(f"  {level}: {arcpy.management.GetCount(target)[0]} blocks, {paths[key]['seconds']} s", flush=True)
    return paths


def annotate(path, tmin):
    """BASE_Z, TOP_Z, TERRAIN_MIN_Z and the two differences on every block."""
    import arcpy
    for name in ("BASE_Z", "TOP_Z", "TERRAIN_MIN_Z", "TOP_MINUS_ROOF50", "BASE_MINUS_TMIN"):
        arcpy.management.AddField(path, name, "DOUBLE")
    with arcpy.da.UpdateCursor(path, ["SHAPE@", "FP_ID", "ROOF_Z50_M", "BASE_Z", "TOP_Z", "TERRAIN_MIN_Z",
                                      "TOP_MINUS_ROOF50", "BASE_MINUS_TMIN"]) as cursor:
        for shape, fp, roof50, *_ in cursor:
            base, top, t = (shape.extent.ZMin, shape.extent.ZMax, tmin.get(fp)) if shape else (None, None, tmin.get(fp))
            cursor.updateRow([shape, fp, roof50, base, top, t,
                              None if top is None or roof50 is None else top-roof50,
                              None if base is None or t is None else base-t])


def summary(path):
    """Distributions of the two differences, overall and by roof coverage and status."""
    import arcpy
    rows = [r for r in arcpy.da.SearchCursor(path, ["TOP_MINUS_ROOF50", "BASE_MINUS_TMIN", "ROOF_COV_PCT",
                                                     "HEIGHT_STATUS", "BASE_Z"])]

    def stats(values):
        v = np.array([x for x in values if x is not None], float)
        if not len(v):
            return {"n": 0}
        return {"n": int(len(v)), "p05": round(float(np.percentile(v, 5)), 3), "p50": round(float(np.median(v)), 3),
                "p95": round(float(np.percentile(v, 95)), 3), "min": round(float(v.min()), 3),
                "max": round(float(v.max()), 3), "beyond_0.25m": int((np.abs(v) > 0.25).sum()),
                "beyond_1m": int((np.abs(v) > 1).sum())}
    out = {"blocks": len(rows), "empty_geometry": sum(1 for r in rows if r[4] is None),
           "top_minus_roof50": stats(r[0] for r in rows), "base_minus_terrain_min": stats(r[1] for r in rows),
           "by_roof_coverage": {}, "by_status": {}}
    for name, lo, hi in (("under 80%", 0, 80), ("80-95%", 80, 95), ("95% and over", 95, 1000)):
        part = [r for r in rows if r[2] is not None and lo <= r[2] < hi]
        out["by_roof_coverage"][name] = {"top": stats(r[0] for r in part), "base": stats(r[1] for r in part)}
    for status in sorted({r[3] for r in rows}):
        part = [r for r in rows if r[3] == status]
        out["by_status"][status] = {"top": stats(r[0] for r in part), "base": stats(r[1] for r in part)}
    return out


def build(out, window):
    import arcpy
    from canopy import planning
    arcpy.CheckOutExtension("3D")
    arcpy.CheckOutExtension("Spatial")
    out = Path(out).resolve()
    started = datetime.datetime.now().isoformat(timespec="seconds")
    print("height source and footprints", flush=True)
    dsm, footprints, gdb = prepare(out, window)
    n = int(arcpy.management.GetCount(footprints)[0])
    print(f"  {n} footprints", flush=True)
    tmin = terrain_min(footprints, gdb, out)
    print("Extract LOD2 Buildings", flush=True)
    paths = extract(dsm, footprints, gdb, out)
    result = {"schema": "massing/1", "started": started, "window": window, "footprints": n,
              "height_source": {"roof": str(ROOF), "terrain": str(TERRAIN), "path": dsm},
              "tool": "arcpy.ddd.ExtractLOD2Buildings(height_source, footprints, out, level), defaults otherwise",
              "outputs": {}, "warning": planning.WARNING}
    for key, item in paths.items():
        annotate(item["path"], tmin)
        planning._metadata(item["path"], f"3D building massing, {LEVELS[key]}, from the consensus roof surface and "
                                         "county footprints (Extract LOD2 Buildings). Heights are roof-minus-terrain "
                                         "estimates, not code-defined building heights.")
        result["outputs"][key] = {**item, "summary": summary(item["path"])}
    result["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
    (out/"massing.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps({k: {"seconds": v["seconds"], **v["summary"]} for k, v in result["outputs"].items()}, indent=1))


def clean(out):
    """Delete the empty blocks Extract LOD2 Buildings leaves (zero area, all Z = 0: on October 22, a spare beside the real
    block for 7 footprints and the only output for one 0.5 m2 sliver), list the blocks whose base sits more than 2 m above
    the lowest terrain under the footprint, and summarise again."""
    import arcpy
    out = Path(out).resolve()
    record = json.loads((out/"massing.json").read_text(encoding="utf-8"))
    cleaned = {}
    for key in LEVELS:
        path = str(out/"massing.gdb"/key)
        removed = []
        with arcpy.da.UpdateCursor(path, ["SHAPE@", "FP_ID"]) as cursor:
            for shape, fp in cursor:
                if shape is None or shape.area == 0 or shape.extent.ZMax == 0:
                    removed.append(fp)
                    cursor.deleteRow()
        ids = [r[0] for r in arcpy.da.SearchCursor(path, ["FP_ID"])]
        high = [{"FP_ID": fp, "base_minus_terrain_min": round(d, 2), "block_height": round(t-b, 2)}
                for fp, d, b, t in arcpy.da.SearchCursor(path, ["FP_ID", "BASE_MINUS_TMIN", "BASE_Z", "TOP_Z"])
                if d is not None and d > 2]
        cleaned[key] = {"removed_empty": sorted(removed), "blocks": len(ids), "footprints_with_a_block": len(set(ids)),
                        "footprints_with_two_blocks": len(ids)-len(set(ids)),
                        "footprints_without_a_block": sorted(set(removed)-set(ids)),
                        "base_over_2m_above_terrain_min": high, "summary": summary(path)}
        print(key, json.dumps({k: v for k, v in cleaned[key].items() if k != "summary"}), flush=True)
    record["cleaned"] = cleaned
    (out/"massing.json").write_text(json.dumps(record, indent=1), encoding="utf-8")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("pilot", "run", "clean"))
    p.add_argument("out", type=Path)
    a = p.parse_args(argv)
    if a.step == "clean":
        clean(a.out)
    else:
        build(a.out, PILOT_TILE if a.step == "pilot" else None)


if __name__ == "__main__":
    main()
