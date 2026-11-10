r"""Citywide roofer-only scene layer package (October 24, 2026), for looking at roofer's failures before the fallback replaces them.

    python reviews/2026-10-23/lod2-check/package_roofer_only.py ROOFER_CITY_DIR

ArcGIS Pro Python with 3D Analyst (PYTHONNOUSERSITE=1). Read-only on ROOFER_CITY_DIR\convert\roofer.gdb; writes
ROOFER_CITY_DIR\buildings_roofer_only.slpk and its validation report. Packaged as make_slpk.py does (WGS84, ITRF08 named).
Nothing is uploaded.
"""
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve()
spec = importlib.util.spec_from_file_location("make_slpk", HERE.parents[2]/"2026-10-22"/"hosting"/"scene-layers"/"make_slpk.py")
slpk_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(slpk_mod)


def main(folder):
    import arcpy
    arcpy.CheckOutExtension("3D")
    folder = Path(folder)
    fc = str(folder/"convert"/"roofer.gdb"/"roofer_lod22")
    slpk = folder/"buildings_roofer_only.slpk"
    slpk.unlink(missing_ok=True)
    with arcpy.EnvManager(scratchWorkspace=str(folder)):
        arcpy.management.Create3DObjectSceneLayerPackage(fc, str(slpk), arcpy.SpatialReference(4326), slpk_mod.TRANSFORM,
                                                         "Desktop")
    report = folder/"roofer-only-validation.json"
    arcpy.management.ValidateSceneLayerPackage(str(slpk), str(report))
    ids = [r[0] for r in arcpy.da.SearchCursor(fc, ["FP_ID"])]
    stats = slpk_mod.package_stats(str(slpk))
    record = {"slpk": str(slpk), "mb": round(slpk.stat().st_size/2**20, 1), "package": stats,
              "fp_id_stats_equal_source": (stats["fp_id_count"], stats["fp_id_sum"]) == (len(ids), sum(ids)),
              "validation_messages": json.loads(report.read_text(encoding="utf-8")).get("Messages")}
    (folder/"roofer-only.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps(record, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
