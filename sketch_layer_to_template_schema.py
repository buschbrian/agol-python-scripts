"""
sketch_layer_to_template_schema.py

Turns an ArcGIS Online Map Viewer sketch layer into a feature class that
carries a production dataset's full schema — fields, domains, subtypes,
GlobalIDs and attribute rules — instead of the title/description stub a
sketch export gives you.

A sketch layer is a client-side feature collection stored in the web map's
JSON. It has no service endpoint and ArcGIS Online offers no export, so the
geometry has to come down through Pro first:

    1. Web map item page > More options > Open in ArcGIS Pro (an .pitemx).
    2. Contents pane, right-click the sketch layer > Data > Export Features.
    3. Point SKETCH_FC below at that export.

The script then copies TEMPLATE_FC (schema and rules together), empties it,
reprojects the sketch with an explicit datum transformation, and appends.
Attribute rules are disabled during the load so an immediate constraint rule
cannot leave a half-filled feature class behind, then re-enabled.

Set the paths below and run once with DRY_RUN = True to read the report.

Runs in ArcGIS Pro's Python (`arcpy`).
"""

import csv
import os
import arcpy

# ---------------------------------------------------------------- config
SKETCH_FC   = r"C:\work\sketch.gdb\planner_sketch"   # sketch export, usually WGS 1984
TEMPLATE_FC = r"C:\work\flu.gdb\FutureLandUse"       # schema + rules donor
TARGET_FC   = r"C:\work\flu.gdb\FLU_from_sketch"     # created by this script
RULES_CSV   = r"C:\work\attribute_rules.csv"         # audit artifact + fallback

# Target field -> sketch field. Everything unlisted is left null. Sketch
# layers only carry title/description-style fields, so expect this to be short.
FIELD_MAP = {
    # "LANDUSE_DESC": "description",
    # "LABEL":        "title",
}

# Target field -> literal expression, stamped after the append.
CONSTANTS = {
    # "DATA_SOURCE": "'Planner web map sketch'",
}

# Leave None to auto-pick from ListTransformations and print the choice.
# Utah WGS84 -> NAD83 is normally WGS_1984_(ITRF00)_To_NAD_1983.
TRANSFORMATION = None

EVALUATE_BATCH_RULES = False   # batch/validation rules only; safe to leave off
DRY_RUN = True

arcpy.env.overwriteOutput = False


def rule_names(fc):
    """Read rule names without writing an export during a dry run."""
    return [rule.name for rule in getattr(arcpy.Describe(fc), "attributeRules", [])]


def enabled_rule_names(fc):
    return [rule.name for rule in getattr(arcpy.Describe(fc), "attributeRules", [])
            if getattr(rule, "isEnabled", True)]


def main():
    for path in (SKETCH_FC, TEMPLATE_FC):
        if not arcpy.Exists(path):
            raise SystemExit("missing input: {}".format(path))
    if arcpy.Exists(TARGET_FC):
        raise SystemExit("target already exists, delete it first: {}".format(TARGET_FC))

    src_sr = arcpy.Describe(SKETCH_FC).spatialReference
    tgt_sr = arcpy.Describe(TEMPLATE_FC).spatialReference
    sketch_n = int(arcpy.management.GetCount(SKETCH_FC)[0])

    transform = TRANSFORMATION
    if src_sr.GCS.name != tgt_sr.GCS.name and not transform:
        options = arcpy.ListTransformations(src_sr, tgt_sr, arcpy.Describe(SKETCH_FC).extent)
        if not options:
            raise SystemExit("no datum transformation found; set TRANSFORMATION manually")
        transform = options[0]

    template_rules = rule_names(TEMPLATE_FC)

    print("sketch      : {} ({} features, {})".format(SKETCH_FC, sketch_n, src_sr.name))
    print("target SR   : {}".format(tgt_sr.name))
    print("transform   : {}".format(transform or "none needed"))
    print("rules       : {}".format(len(template_rules)))
    print("rules CSV   : {}".format(RULES_CSV))
    print("mapped      : {}".format(FIELD_MAP or "none - all attributes land null"))
    if DRY_RUN:
        print("\nDRY_RUN - nothing written. Review this report, then set DRY_RUN = False.")
        return

    arcpy.management.ExportAttributeRules(TEMPLATE_FC, RULES_CSV)

    # Copy carries fields, domains, subtypes, GlobalIDs and the rules together,
    # which avoids Import Attribute Rules failing on fields that don't exist yet.
    arcpy.management.Copy(TEMPLATE_FC, TARGET_FC)
    copied = rule_names(TARGET_FC)
    if len(copied) != len(template_rules):
        print("Copy dropped rules ({} of {}); importing from CSV".format(
            len(copied), len(template_rules)))
        arcpy.management.ImportAttributeRules(TARGET_FC, RULES_CSV)
        copied = rule_names(TARGET_FC)

    # Restore only rules that were enabled before the load, including on failure.
    originally_enabled = enabled_rule_names(TARGET_FC)
    if originally_enabled:
        arcpy.management.DisableAttributeRules(TARGET_FC, originally_enabled)
    try:
        arcpy.management.DeleteRows(TARGET_FC)

        # Explicit, not on-the-fly in Append, so the datum transformation is a choice.
        staged = SKETCH_FC
        if src_sr.exportToString().split(";")[0] != tgt_sr.exportToString().split(";")[0]:
            staged = os.path.join(arcpy.env.scratchGDB, "sketch_projected")
            if arcpy.Exists(staged):
                arcpy.management.Delete(staged)
            arcpy.management.Project(SKETCH_FC, staged, tgt_sr, transform, src_sr)

        fms = arcpy.FieldMappings()
        fms.addTable(TARGET_FC)
        for tgt_field, src_field in FIELD_MAP.items():
            idx = fms.findFieldMapIndex(tgt_field)
            if idx == -1:
                raise SystemExit("no field '{}' on {}".format(tgt_field, TARGET_FC))
            fm = fms.getFieldMap(idx)
            fm.addInputField(staged, src_field)
            fms.replaceFieldMap(idx, fm)

        arcpy.management.Append(staged, TARGET_FC, "NO_TEST", fms)

        for field, expr in CONSTANTS.items():
            arcpy.management.CalculateField(TARGET_FC, field, expr, "PYTHON3")

    finally:
        if originally_enabled:
            arcpy.management.EnableAttributeRules(TARGET_FC, originally_enabled)
    if EVALUATE_BATCH_RULES:
        arcpy.management.EvaluateRules(os.path.dirname(TARGET_FC),
                                       "VALIDATION_RULES;BATCH_CALCULATION_RULES")

    out_n = int(arcpy.management.GetCount(TARGET_FC)[0])
    print("\n{} -> {} features, {} rules enabled".format(TARGET_FC, out_n, len(copied)))
    if out_n != sketch_n:
        print("WARNING: expected {} features".format(sketch_n))


if __name__ == "__main__":
    main()
