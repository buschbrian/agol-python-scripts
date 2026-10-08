"""Copy tree candidates and flag proximity to building footprints for review.

Footprint contact is an inspection priority, not a tree/non-tree classifier.
"""
from collections import Counter
from pathlib import Path

import arcpy

from . import common


def flag_footprint_contact(candidates, footprints, output_gdb, distance=2.0,
                           name="trees_footprint_review"):
    distance = common.positive(distance, "Footprint review distance")
    if not name:
        raise ValueError("Output feature class name is required")
    common.prefix_name(name)
    point_info = arcpy.Describe(candidates)
    polygon_info = arcpy.Describe(footprints)
    if point_info.shapeType != "Point" or polygon_info.shapeType != "Polygon":
        raise ValueError("Candidates must be points and footprints must be polygons")
    point_sr = common.metric_reference(point_info.spatialReference)
    if not common.same_xy_reference(point_sr, polygon_info.spatialReference):
        raise ValueError("Candidates and footprints must use the same horizontal CRS")
    field_names = {field.name.upper() for field in arcpy.ListFields(candidates)}
    if "TREE_ID" not in field_names:
        raise ValueError("Use a tree candidate layer with TREE_ID")
    if field_names & {"NEAR_FID", "NEAR_DIST", "FOOT_QA"}:
        raise ValueError("Input already contains footprint-review fields; use the original candidates")
    target = common.output(common.geodatabase(output_gdb), name)
    arcpy.management.CopyFeatures(candidates, target)
    counts = Counter()
    by_status = Counter()
    has_crown_status = "CROWN_STATUS" in field_names
    fields = ["NEAR_DIST", "FOOT_QA"] + (["CROWN_STATUS"] if has_crown_status else [])
    try:
        arcpy.analysis.Near(target, footprints, f"{distance} Meters", method="PLANAR")
        arcpy.management.AddField(target, "FOOT_QA", "TEXT", field_length=35)
        with arcpy.da.UpdateCursor(target, fields) as cursor:
            for row in cursor:
                near = row[0]
                label = ("ON_FOOTPRINT" if near == 0 else
                         "NEAR_FOOTPRINT" if near > 0 else "OTHER")
                row[1] = label
                cursor.updateRow(row)
                counts[label] += 1
                if has_crown_status:
                    by_status[(label, row[2])] += 1
        common.metadata(target,
            f"Point-to-footprint planar Near within {distance} m. FOOT_QA flags review priority. "
            "ON_FOOTPRINT may be a real tree overhanging a roof; inspect imagery and point classes. "
            "NEAR_FID is the input footprint ObjectID and is not a stable building identifier.")
    except Exception:
        arcpy.management.Delete(target)
        raise
    return {
        "output": str(Path(target).resolve()),
        "distance_m": distance,
        "counts": dict(counts),
        "counts_by_crown_status": [
            {"foot_qa": qa, "crown_status": status, "count": count}
            for (qa, status), count in sorted(by_status.items())
        ],
        "warning": "Footprint contact is a review flag, not measured false-detection accuracy.",
    }
