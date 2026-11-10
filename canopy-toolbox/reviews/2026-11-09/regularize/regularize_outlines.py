"""Regularize the final LiDAR-first outlines (city2) after the lot-line cuts and tree fills. Run with the Pro Python (-I).

    regularize_outlines.py OUT

Writes OUT/regularized.gdb/buildings: every input outline, with its shape replaced by the regularized one unless that failed or
moved the shape too far (IoU with the input under MIN_IOU). Outlines the tool cannot regularize (tree fills leave slits and
spikes) get a second pass after a 0.5 m morphological close. Nothing is uploaded and no input is edited.
"""

import json
import sys
from collections import Counter
from pathlib import Path

import arcpy

INPUT = r"H:\lidar\2023-salt-lake-valley\runs\lidar-footprints-20261026\city2\buildings_filled.gpkg\main.buildings_filled"
SETTINGS = {"method": "RIGHT_ANGLES_AND_DIAGONALS", "tolerance": 0.75, "densification": 0.75, "precision": 0.25}
MIN_IOU = 0.85
CLOSE_M = 0.5


def iou(a, b):
    both = a.intersect(b, 4).area
    return both / (a.area + b.area - both) if both else 0.0


def regularize(source, target):
    arcpy.ddd.RegularizeBuildingFootprint(source, target, SETTINGS["method"], SETTINGS["tolerance"], SETTINGS["densification"], SETTINGS["precision"])
    return {row[0]: (row[1], row[2]) for row in arcpy.da.SearchCursor(target, ["LB_ID", "SHAPE@", "STATUS"])}


def invalid_oids(fc, gdb):
    report = str(gdb / "invalid")
    arcpy.management.CheckGeometry(fc, report, "OGC")
    return {row[0] for row in arcpy.da.SearchCursor(report, ["FEATURE_ID"])}


def restore_invalid(result, source, gdb):
    """Put the input shape back where the tool made an OGC-invalid polygon; roofer drops a whole tile on one such feature."""
    bad = invalid_oids(result, gdb)
    inputs = {row[0]: row[1] for row in arcpy.da.SearchCursor(source, ["LB_ID", "SHAPE@"])}
    fields = ["OID@", "LB_ID", "SHAPE@", "REG_STATUS", "REG_IOU", "REG_AREA_M2"]
    reverted = 0
    with arcpy.da.UpdateCursor(result, fields) as rows:
        for oid, lb, _, _, _, _ in rows:
            if oid in bad:
                rows.updateRow([oid, lb, inputs[lb], "KEPT_INPUT_INVALID", None, inputs[lb].area])
                reverted += 1
    remaining = invalid_oids(result, gdb)
    if remaining:
        arcpy.management.RepairGeometry(result, "KEEP_NULL", "OGC")
    left = invalid_oids(result, gdb)
    if left:
        raise SystemExit(f"{len(left)} features are still invalid")
    return reverted, len(remaining)


def main(out):
    out.mkdir(parents=True, exist_ok=True)
    arcpy.env.overwriteOutput = True
    gdb = out / "regularized.gdb"
    if not gdb.exists():
        arcpy.management.CreateFileGDB(str(out), gdb.name)
    source, result = str(gdb / "input"), str(gdb / "buildings")
    arcpy.conversion.ExportFeatures(INPUT, source)
    first = regularize(source, str(gdb / "tool_output"))

    failed = [lb for lb, (_, code) in first.items() if code != 0]
    cleaned = str(gdb / "cleaned")
    arcpy.conversion.ExportFeatures(source, cleaned, "LB_ID IN ({})".format(",".join(f"'{lb}'" for lb in failed)))
    with arcpy.da.UpdateCursor(cleaned, ["SHAPE@"]) as rows:
        for (shape,) in rows:
            rows.updateRow([shape.buffer(CLOSE_M).buffer(-CLOSE_M)])
    second = regularize(cleaned, str(gdb / "tool_output_cleaned"))

    arcpy.conversion.ExportFeatures(source, result)
    arcpy.management.AddFields(result, [["REG_STATUS", "TEXT", "", 28], ["REG_IOU", "DOUBLE"], ["REG_AREA_M2", "DOUBLE"]])
    tally, ious = Counter(), []
    with arcpy.da.UpdateCursor(result, ["LB_ID", "SHAPE@", "REG_STATUS", "REG_IOU", "REG_AREA_M2"]) as rows:
        for lb, shape, _, _, _ in rows:
            new, code = first[lb]
            label = "REGULARIZED"
            if code != 0:
                new, code = second.get(lb, (None, 1))
                label = "REGULARIZED_AFTER_CLOSE"
            if new is None or code != 0 or new.area == 0:
                state, value, final = "KEPT_INPUT_FAILED", None, shape
            else:
                value = iou(shape, new)
                ious.append(value)
                state, final = (label, new) if value >= MIN_IOU else ("KEPT_INPUT_LOW_IOU", shape)
            tally[state] += 1
            rows.updateRow([lb, final, state, value, final.area])
    reverted, repaired = restore_invalid(result, source, gdb)
    tally["KEPT_INPUT_INVALID"] = reverted
    ious.sort()
    summary = {"input": INPUT, "settings": SETTINGS, "min_iou": MIN_IOU, "close_m": CLOSE_M, "first_pass_failed": len(failed), "status": dict(tally),
               "invalid_reverted_to_input": reverted, "invalid_repaired_ogc": repaired,
               "iou_percentiles": {p: round(ious[int(len(ious) * p / 100)], 4) for p in (1, 5, 10, 25, 50)}}
    (out / "regularize.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
