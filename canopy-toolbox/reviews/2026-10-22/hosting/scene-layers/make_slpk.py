r"""Scene layer packages of the 3D building massing (hosting plan step 3, October 22, 2026).

    python reviews/2026-10-22/hosting/scene-layers/make_slpk.py MASSING_DIR OUT
    python reviews/2026-10-22/hosting/scene-layers/make_slpk.py FEATURE_CLASS OUT --name NAME --wkid 6341

ArcGIS Pro Python (PYTHONNOUSERSITE=1). Read-only on the massing run (reviews/2026-10-22/massing) or the feature class;
writes OUT\*.slpk, the validation reports and OUT\slpk.json. Nothing is uploaded: sharing the packages is Brian's step.
- From a massing run, one package per level: buildings_lod12.slpk (flat blocks) and buildings_lod20.slpk (roof forms), each
  feature carrying the footprint's attributes and roof-height statistics. Given a multipatch feature class instead, one
  package, OUT\NAME.slpk.
- WGS84 output for ArcGIS Online global scenes by default, with the NAD83(2011) to WGS84 transformation named explicitly.
  --wkid packages in another coordinate system (October 26: 6341, NAD83(2011) UTM 12N, for a local ArcGIS Urban model, with
  no transformation since the sources are already in it); --vcs adds a vertical coordinate system. Heights stay NAVD88
  (Geoid18) metres, as the terrain and the elevation package are.
- Checks: Validate Scene Layer Package on each; the package opened as a scene layer has as many features as its multipatch
  feature class.
"""
import argparse
import datetime
import json
from pathlib import Path

LEVELS = {"lod12": "buildings_lod12.slpk", "lod20": "buildings_lod20.slpk"}
TRANSFORM = "WGS_1984_(ITRF08)_To_NAD_1983_2011"
WGS84 = 4326


def package_stats(slpk):
    """From the package itself (a zip): the FP_ID statistics (count and sum of the footprint IDs it holds), the layer's
    spatial reference and height model and the vertical span of its node boxes. Pro cannot count features on a scene layer."""
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
            "spatial_reference": layer["spatialReference"], "height_model": layer.get("heightModelInfo"),
            "node_centre_z_range": [min(z_centres), max(z_centres)]}


def spatial_reference(wkid=WGS84, vcs=None):
    import arcpy
    return arcpy.SpatialReference(wkid, vcs) if vcs else arcpy.SpatialReference(wkid)


def package(source, slpk, report, wkid=WGS84, vcs=None, transformation=None):
    """Package one multipatch feature class, validate it and compare the package's FP_IDs with the source's.
    The transformation defaults to TRANSFORM for WGS84 and to none for any other coordinate system."""
    import arcpy
    if transformation is None:
        transformation = TRANSFORM if wkid == WGS84 else ""
    started = datetime.datetime.now()
    with arcpy.EnvManager(scratchWorkspace=str(Path(slpk).parent)):
        arcpy.management.Create3DObjectSceneLayerPackage(str(source), str(slpk), spatial_reference(wkid, vcs),
                                                         transformation, "Desktop")
    seconds = round((datetime.datetime.now()-started).total_seconds())
    arcpy.management.ValidateSceneLayerPackage(str(slpk), str(report))
    ids = [r[0] for r in arcpy.da.SearchCursor(str(source), ["FP_ID"])]
    entry = {
        "slpk": str(slpk), "seconds": seconds, "mb": round(Path(slpk).stat().st_size/2**20, 1),
        "source_features": len(ids), "source_fp_id_sum": sum(ids),
        "package": package_stats(str(slpk)), "validation_report": str(report),
        "validation_messages": json.loads(Path(report).read_text(encoding="utf-8")).get("Messages"),
    }
    entry["all_features_in_package"] = (entry["package"]["fp_id_count"], entry["package"]["fp_id_sum"]) == (len(ids), sum(ids))
    return entry


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("source", type=Path, help="a massing run folder (holding massing.gdb) or a multipatch feature class")
    p.add_argument("out", type=Path)
    p.add_argument("--name", help="package name for a feature class source (default: the feature class name)")
    p.add_argument("--wkid", type=int, default=WGS84, help="output coordinate system (default 4326, WGS84)")
    p.add_argument("--vcs", type=int, help="output vertical coordinate system, e.g. 5703 for NAVD88 height (default none)")
    p.add_argument("--transformation", help=f"default {TRANSFORM} for WGS84, none otherwise; '' for none")
    a = p.parse_args(argv)
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    transformation = a.transformation if a.transformation is not None else (TRANSFORM if a.wkid == WGS84 else "")
    massing = (a.source/"massing.gdb").is_dir()
    sources = ({key: (a.source.resolve()/"massing.gdb"/key, name) for key, name in LEVELS.items()} if massing else
               {(a.name or a.source.name): (a.source.resolve(), f"{a.name or a.source.name}.slpk")})
    sr = spatial_reference(a.wkid, a.vcs)
    record = {"schema": "hosting-slpk/1", "created": datetime.datetime.now().isoformat(timespec="seconds"),
              "massing" if massing else "source": str(a.source.resolve()),
              "coordinate_system": f"{sr.name} ({a.wkid})" + (f" + {sr.VCS.name} ({a.vcs})" if a.vcs else ""),
              "transformation": transformation, "packages": {}}
    for key, (source, name) in sources.items():
        record["packages"][key] = package(source, out/name, out/f"{key}-validation.json", a.wkid, a.vcs, transformation)
        print(key, json.dumps(record["packages"][key]), flush=True)
    (out/"slpk.json").write_text(json.dumps(record, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
