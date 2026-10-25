r"""Hybrid building massing and its scene layer package (October 23, 2026): LOD2.0 where it passed the check, else LOD1.2.

    python reviews/2026-10-23/lod2-check/build_hybrid.py MASSING_DIR CHECK_DIR OUT

ArcGIS Pro Python with 3D Analyst (PYTHONNOUSERSITE=1). Read-only on both inputs; writes OUT\hybrid.gdb, OUT\buildings_hybrid.slpk,
the validation report and OUT\hybrid.json. Nothing is uploaded.
- MASSING_DIR: a massing run with massing.gdb (lod12, lod20), here massing-filled-20261023.
- CHECK_DIR: the lod2_check.py run on it (lod2-check.csv), here lod2-check-filled-20261023.
- Rule: a building takes its LOD2.0 block when VERDICT is better or same and LOD20_GROUND_PCT is under 10 (a missing
  GROUND_PCT counts as under 10); every other building takes its LOD1.2 block. One feature per FP_ID.
- Added fields: LEVEL ("LOD2.0" or "LOD1.2"), CHECK_VERDICT, LOD20_GROUND_PCT (as measured, for every building) and
  FALLBACK_REASON (too-few, worse-or-broken, ground-level; empty for LOD2.0).
- Packaged and validated as make_slpk.py does (WGS84, the ITRF08 transformation named, Desktop profile).
"""
import argparse
import csv
import datetime
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve()
SLPK_SCRIPT = HERE.parents[2]/"2026-10-22"/"hosting"/"scene-layers"/"make_slpk.py"
GROUND_LIMIT = 10.0


def _slpk_module():
    spec = importlib.util.spec_from_file_location("make_slpk", SLPK_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def decide(csv_path):
    """FP_ID -> (level, verdict, ground_pct, reason) from the check's per-building CSV."""
    out = {}
    for r in csv.DictReader(open(csv_path, encoding="utf-8")):
        fid, verdict = int(r["FP_ID"]), r["VERDICT"]
        ground = float(r["LOD20_GROUND_PCT"]) if r["LOD20_GROUND_PCT"] not in ("", "None") else None
        if verdict == "too-few":
            level, reason = "LOD1.2", "too-few"
        elif verdict in ("worse", "broken"):
            level, reason = "LOD1.2", "worse-or-broken"
        elif ground is not None and ground >= GROUND_LIMIT:
            level, reason = "LOD1.2", "ground-level"
        else:
            level, reason = "LOD2.0", ""
        out[fid] = (level, verdict, ground, reason)
    return out


def main(argv=None):
    import arcpy
    arcpy.CheckOutExtension("3D")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("massing", type=Path)
    p.add_argument("check", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args(argv)
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    src = a.massing.resolve()/"massing.gdb"
    choice = decide(a.check.resolve()/"lod2-check.csv")
    gdb = Path(arcpy.management.CreateFileGDB(str(out), "hybrid.gdb")[0])
    hybrid = str(gdb/"buildings_hybrid")
    arcpy.management.CopyFeatures(str(src/"lod20"), hybrid)
    ids20 = set()
    with arcpy.da.UpdateCursor(hybrid, ["FP_ID"]) as cursor:
        for (fid,) in cursor:
            if choice.get(fid, ("LOD1.2",))[0] == "LOD2.0":
                ids20.add(fid)
            else:
                cursor.deleteRow()
    # the LOD1.2 blocks of the fallback buildings: a copy trimmed to them, appended (an insert cursor cannot write multipatches)
    fallback = str(gdb/"lod12_fallback")
    arcpy.management.CopyFeatures(str(src/"lod12"), fallback)
    inserted = 0
    with arcpy.da.UpdateCursor(fallback, ["FP_ID"]) as cursor:
        for (fid,) in cursor:
            if choice.get(fid, ("LOD1.2",))[0] == "LOD1.2" and fid not in ids20:
                inserted += 1
            else:
                cursor.deleteRow()
    arcpy.management.Append(fallback, hybrid, "NO_TEST")
    for name, kind, length in (("LEVEL", "TEXT", 8), ("CHECK_VERDICT", "TEXT", 10), ("LOD20_GROUND_PCT", "DOUBLE", None),
                               ("FALLBACK_REASON", "TEXT", 20)):
        arcpy.management.AddField(hybrid, name, kind, field_length=length)
    counts = {}
    with arcpy.da.UpdateCursor(hybrid, ["FP_ID", "LOD", "LEVEL", "CHECK_VERDICT", "LOD20_GROUND_PCT",
                                        "FALLBACK_REASON"]) as cursor:
        for fid, lod, *_ in cursor:
            level, verdict, ground, reason = choice[fid]
            assert (level == "LOD2.0") == (abs(lod-2.0) < 1e-6), (fid, level, lod)
            cursor.updateRow([fid, lod, level, verdict, ground, reason])
            counts[(level, reason)] = counts.get((level, reason), 0)+1
    ids = [r[0] for r in arcpy.da.SearchCursor(hybrid, ["FP_ID"])]
    assert len(ids) == len(set(ids)), "an FP_ID appears twice"
    slpk_tools = _slpk_module()
    slpk = str(out/"buildings_hybrid.slpk")
    started = datetime.datetime.now()
    with arcpy.EnvManager(scratchWorkspace=str(out)):
        arcpy.management.Create3DObjectSceneLayerPackage(hybrid, slpk, arcpy.SpatialReference(4326),
                                                         slpk_tools.TRANSFORM, "Desktop")
    seconds = round((datetime.datetime.now()-started).total_seconds())
    report = str(out/"hybrid-validation.json")
    arcpy.management.ValidateSceneLayerPackage(slpk, report)
    package = slpk_tools.package_stats(slpk)
    record = {"schema": "hybrid-slpk/1", "created": datetime.datetime.now().isoformat(timespec="seconds"),
              "massing": str(a.massing.resolve()), "check": str(a.check.resolve()),
              "rule": "LOD2.0 where VERDICT is better or same and LOD20_GROUND_PCT < 10; LOD1.2 otherwise",
              "buildings": len(ids), "lod12_blocks_appended": inserted,
              "by_level_and_reason": {f"{k[0]} {k[1]}".strip(): v for k, v in sorted(counts.items())},
              "slpk": slpk, "seconds": seconds, "mb": round(Path(slpk).stat().st_size/2**20, 1),
              "source_fp_id_sum": sum(ids), "package": package,
              "all_features_in_package": (package["fp_id_count"], package["fp_id_sum"]) == (len(ids), sum(ids)),
              "validation_report": report,
              "validation_messages": json.loads(Path(report).read_text(encoding="utf-8")).get("Messages")}
    (out/"hybrid.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    print(json.dumps(record, indent=1))


if __name__ == "__main__":
    main()
