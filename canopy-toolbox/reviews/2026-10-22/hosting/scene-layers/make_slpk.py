r"""Scene layer packages of the 3D building massing (hosting plan step 3, October 22, 2026).

    python reviews/2026-10-22/hosting/scene-layers/make_slpk.py MASSING_DIR OUT

ArcGIS Pro Python (PYTHONNOUSERSITE=1). Read-only on the massing run (reviews/2026-10-22/massing); writes OUT\*.slpk, the
validation reports and OUT\slpk.json. Nothing is uploaded: sharing the packages is Brian's step.
- One package per level: buildings_lod12.slpk (flat blocks) and buildings_lod20.slpk (roof forms), each feature carrying
  the footprint's attributes and roof-height statistics.
- WGS84 output for ArcGIS Online global scenes, with the NAD83(2011) to WGS84 transformation named explicitly. Heights stay
  NAVD88 (Geoid18) metres, as the terrain and the elevation package are.
- Checks: Validate Scene Layer Package on each; the package opened as a scene layer has as many features as its multipatch
  feature class.
"""
import argparse
import datetime
import json
from pathlib import Path

LEVELS = {"lod12": "buildings_lod12.slpk", "lod20": "buildings_lod20.slpk"}
TRANSFORM = "WGS_1984_(ITRF08)_To_NAD_1983_2011"


def package_stats(slpk):
    """From the package itself (a zip): the FP_ID statistics (count and sum of the footprint IDs it holds), the layer's
    spatial reference and the vertical span of its node boxes. Pro cannot count features on a scene layer."""
    import gzip
    import zipfile
    with zipfile.ZipFile(slpk) as z:
        layer = json.loads(gzip.decompress(z.read("3dSceneLayer.json.gz")))
        key = next(s["key"] for s in layer["statisticsInfo"] if s["name"] == "FP_ID")
        stats = json.loads(gzip.decompress(z.read(f"statistics/{key}/0.json.gz")))["stats"]
        nodes = [n for name in z.namelist() if name.startswith("nodepages/")
                 for n in json.loads(gzip.decompress(z.read(name)))["nodes"]]
    z_centres = [n["obb"]["center"][2] for n in nodes]
    return {"fp_id_count": int(stats["count"]), "fp_id_sum": int(stats["sum"]), "nodes": len(nodes),
            "spatial_reference": layer["spatialReference"], "node_centre_z_range": [min(z_centres), max(z_centres)]}


def main(argv=None):
    import arcpy
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("massing", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args(argv)
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    gdb = a.massing.resolve()/"massing.gdb"
    record = {"schema": "hosting-slpk/1", "created": datetime.datetime.now().isoformat(timespec="seconds"),
              "massing": str(a.massing.resolve()), "coordinate_system": "WGS84 (4326)", "transformation": TRANSFORM,
              "packages": {}}
    for key, name in LEVELS.items():
        source = str(gdb/key)
        slpk = str(out/name)
        started = datetime.datetime.now()
        with arcpy.EnvManager(scratchWorkspace=str(out)):
            arcpy.management.Create3DObjectSceneLayerPackage(source, slpk, arcpy.SpatialReference(4326), TRANSFORM,
                                                             "Desktop")
        seconds = round((datetime.datetime.now()-started).total_seconds())
        report = str(out/f"{key}-validation.json")
        arcpy.management.ValidateSceneLayerPackage(slpk, report)
        ids = [r[0] for r in arcpy.da.SearchCursor(source, ["FP_ID"])]
        record["packages"][key] = {
            "slpk": slpk, "seconds": seconds, "mb": round(Path(slpk).stat().st_size/2**20, 1),
            "source_features": len(ids), "source_fp_id_sum": sum(ids),
            "package": package_stats(slpk), "validation_report": report,
            "validation_messages": json.loads(Path(report).read_text(encoding="utf-8")).get("Messages"),
        }
        pkg = record["packages"][key]["package"]
        record["packages"][key]["all_features_in_package"] = (pkg["fp_id_count"], pkg["fp_id_sum"]) == (len(ids), sum(ids))
        print(key, json.dumps(record["packages"][key]), flush=True)
    (out/"slpk.json").write_text(json.dumps(record, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
