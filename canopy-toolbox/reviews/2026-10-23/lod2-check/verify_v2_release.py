"""Read existing source/package and portal items; only write local audit outputs."""
import collections
import csv
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import arcpy

repo, out = map(Path, sys.argv[1:3])
out.mkdir(parents=True, exist_ok=True)
run = Path(r"H:\lidar\2023-salt-lake-valley\runs\roofer-city-v2-20261024\v2")
slpk = run / "buildings_hybrid_v2.slpk"
spec = importlib.util.spec_from_file_location("build_v2", repo / "reviews/2026-10-23/lod2-check/build_v2_package.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)
names = [f[0] for f in build.FIELDS]
source = str(run / "v2.gdb/buildings")
records = list(arcpy.da.SearchCursor(source, ["FP_ID", "LEVEL"] + names))
ids = [r[0] for r in records]
levels = collections.Counter(r[1] for r in records)
selected = {r[0] for r in records if r[1] == "roofer LoD2.2"}
rows = {int(r["FP_ID"]): r for r in csv.DictReader((run / "roof/building_roofs.csv").open(encoding="utf-8"))}
summary = build.summarize_packaged_roofs(rows, selected)
stats = build.slpk_mod.package_stats(slpk)
actual_fields = {f.name for f in arcpy.ListFields(source)}
checks = {
    "source_ids_unique": len(ids) == len(set(ids)),
    "expected_feature_count": len(ids) == 21561,
    "model_counts": dict(levels) == {"roofer LoD2.2": 20730, "Esri LOD2.0": 647, "Esri LOD1.2": 184},
    "package_id_statistics_match_source": (stats["fp_id_count"], stats["fp_id_sum"]) == (len(ids), sum(ids)),
    "fallback_roof_attributes_null": all(all(v is None for v in r[2:]) for r in records if r[1] != "roofer LoD2.2"),
    "roofer_roof_area_present": all(r[2 + names.index("ROOF_AREA_M2")] is not None for r in records if r[1] == "roofer LoD2.2"),
}
import zipfile
with zipfile.ZipFile(slpk) as z:
    layer = json.loads(gzip.decompress(z.read("3dSceneLayer.json.gz")))
    checks["package_fields_match_source"] = {f["name"] for f in layer["fields"]} == actual_fields - {"Shape"}
    package_totals = {}
    for name in ("ROOF_AREA_M2", "FLAT_AREA_M2", "SOUTH_AREA_M2", "EAST_AREA_M2", "WEST_AREA_M2", "NORTH_AREA_M2"):
        key = next(s["key"] for s in layer["statisticsInfo"] if s["name"] == name)
        st = json.loads(gzip.decompress(z.read(f"statistics/{key}/0.json.gz")))["stats"]
        source_sum = sum(r[2 + names.index(name)] or 0 for r in records)
        checks[f"{name}_matches_source"] = st["count"] == len(selected) and abs(st["sum"] - source_sum) < .01
        package_totals[name] = {"count": st["count"], "sum": round(st["sum"], 1)}
    field_definitions = layer["fields"]
report = out / "package-validation.json"
arcpy.management.ValidateSceneLayerPackage(str(slpk), str(report))
messages = json.loads(report.read_text(encoding="utf-8"))["Messages"]
checks["fresh_validation_no_warnings_or_errors"] = bool(messages) and all(m.startswith("Information") for m in messages)
audit = {"package": str(slpk), "sha256": hashlib.sha256(slpk.read_bytes()).hexdigest(),
         "source_count": len(ids), "source_unique_ids": len(set(ids)), "source_fp_id_sum": sum(ids),
         "model_counts": dict(levels), "packaged_roof_attributes": summary, "package_attribute_totals": package_totals,
         "package_stats": stats, "checks": checks, "validation_messages": messages,
         "field_names": [f["name"] for f in field_definitions],
         "limitations": ["ID check compares count, uniqueness in source and package sum; it is not a bytewise ID-list comparison.",
                         "No new field or City imagery validation; measurements are fitted to the source lidar."]}
(out / "release-audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"checks": checks, "totals": summary}, indent=2), flush=True)
assert all(checks.values()), "See release-audit.json for failed checks"
