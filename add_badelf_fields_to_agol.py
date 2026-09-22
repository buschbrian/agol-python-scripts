"""
add_badelf_fields_to_agol.py

Adds the Bad Elf Flex (2025) GNSS metadata fields and their coded-value
domains to an ArcGIS Online hosted feature layer, so points collected with a
Bad Elf receiver keep their correction type, geoid model, antenna height, and
final heights alongside the geometry.

Existing fields are checked for compatible types, lengths, and domains before
any schema changes. Use --dry-run to inspect the proposed additions.

Usage:
    python add_badelf_fields_to_agol.py --url https://<org>.maps.arcgis.com \
        --item <hosted-feature-layer-item-id> --username <agol-user>

    The password is prompted for (not echoed). Pass --password only in
    automation where a prompt is impossible. --layer picks a sublayer index
    when the item has more than one (default 0).

Requires the ArcGIS API for Python (`arcgis`).
"""

import argparse
import getpass
import json
import sys

from arcgis.features import FeatureLayerCollection
from arcgis.gis import GIS

# ---------------------------- Domain Definitions ---------------------------- #
BADELF_CORR_TYPE_DOMAIN = {
    "name": "BADELF_CORR_TYPE_D",
    "type": "codedValue",
    "codedValues": [
        {"name": "NONE", "code": 0},
        {"name": "SBAS", "code": 1},
        {"name": "RTCM", "code": 2},
        {"name": "ATLAS", "code": 3},
    ],
}

BADELF_ORTHO_MODEL_DOMAIN = {
    "name": "BADELF_ORTHO_MODEL_D",
    "type": "codedValue",
    "codedValues": [
        {"name": "GEOID18", "code": "GEOID18"},
        {"name": "GEOID12B", "code": "GEOID12B"},
        {"name": "USGG2012", "code": "USGG2012"},
        {"name": "EGM2008", "code": "EGM2008"},
        {"name": "CGG2013", "code": "CGG2013"},
    ],
}

# ---------------------------- Field Definitions ---------------------------- #
NEW_FIELDS = [
    {"name": "BADELF_LATITUDE",            "type": "esriFieldTypeDouble",       "alias": "Bad Elf Latitude"},
    {"name": "BADELF_LONGITUDE",           "type": "esriFieldTypeDouble",       "alias": "Bad Elf Longitude"},
    {"name": "BADELF_ELLIPSOIDAL_M",       "type": "esriFieldTypeDouble",       "alias": "Ellipsoidal height (m)"},
    {"name": "BADELF_DATUM",               "type": "esriFieldTypeString",       "alias": "Datum",                  "length": 25},
    {"name": "BADELF_NTRIP_MOUNT",         "type": "esriFieldTypeString",       "alias": "NTRIP mount point",      "length": 30},
    {"name": "BADELF_CORR_TYPE",           "type": "esriFieldTypeSmallInteger", "alias": "Correction type",        "domain": BADELF_CORR_TYPE_DOMAIN},
    {"name": "BADELF_CORR_DISTANCE_KM",    "type": "esriFieldTypeDouble",       "alias": "Correction distance (km)"},
    {"name": "BADELF_POINT_NAME",          "type": "esriFieldTypeString",       "alias": "Point name",             "length": 50},
    {"name": "BADELF_NOTE",                "type": "esriFieldTypeString",       "alias": "Note",                   "length": 255},
    {"name": "BADELF_FINAL_ORTHO_HEIGHT_M", "type": "esriFieldTypeDouble",      "alias": "Final ortho height (m)"},
    {"name": "BADELF_FINAL_ELLIPSOIDAL_M", "type": "esriFieldTypeDouble",       "alias": "Final ellipsoidal (m)"},
    {"name": "BADELF_ORTHO_GEOID_M",       "type": "esriFieldTypeDouble",       "alias": "Geoid offset (m)"},
    {"name": "BADELF_ORTHO_MODEL",         "type": "esriFieldTypeString",       "alias": "Geoid model",            "length": 25, "domain": BADELF_ORTHO_MODEL_DOMAIN},
    {"name": "BADELF_ANTENNA_HEIGHT_M",    "type": "esriFieldTypeDouble",       "alias": "Antenna height (m)"},
]


def nonnegative_index(value):
    index = int(value)
    if index < 0:
        raise argparse.ArgumentTypeError("layer index must be non-negative")
    return index


def schema_conflicts(existing_fields):
    existing = {field["name"].upper(): field for field in existing_fields}
    conflicts = []
    for expected in NEW_FIELDS:
        actual = existing.get(expected["name"])
        if actual is None:
            continue
        if actual["type"] != expected["type"]:
            conflicts.append(expected["name"] + ": field type differs")
        if "length" in expected and (actual.get("length") or 0) < expected["length"]:
            conflicts.append(expected["name"] + ": field length is too short")
        if "domain" in expected:
            domain = actual.get("domain") or {}
            wanted = {(str(v["code"]), v["name"]) for v in expected["domain"]["codedValues"]}
            found = {(str(v["code"]), v["name"]) for v in domain.get("codedValues", [])}
            if domain.get("type") != "codedValue" or not wanted <= found:
                conflicts.append(expected["name"] + ": domain is missing or incompatible")
    return conflicts


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Add Bad Elf Flex metadata fields to an AGOL hosted feature layer.")
    p.add_argument("--url", required=True, help="Portal URL, e.g. https://myorg.maps.arcgis.com")
    p.add_argument("--item", required=True, help="Item ID of the hosted feature layer")
    p.add_argument("--username", required=True, help="ArcGIS Online username")
    p.add_argument("--password", help="Password (prompted if omitted; prefer the prompt)")
    p.add_argument("--layer", type=nonnegative_index, default=0, help="Sublayer index within the item (default 0)")
    p.add_argument("--dry-run", action="store_true", help="Validate and report additions without changing the layer")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    password = args.password or getpass.getpass(f"Password for {args.username}: ")

    gis = GIS(args.url, args.username, password)

    item = gis.content.get(args.item)
    if not item:
        sys.exit(f"Item ID {args.item} not found or access denied.")

    flc = FeatureLayerCollection.fromitem(item)
    try:
        layer = flc.layers[args.layer]
    except IndexError:
        sys.exit(f"Item has {len(flc.layers)} layer(s); --layer {args.layer} is out of range.")

    print(f"\nConnected to layer: {layer.properties.name}")

    # ---------------------------- Filter Existing Fields ---------------------------- #
    conflicts = schema_conflicts(layer.properties.fields)
    if conflicts:
        print("Existing schema requires review; no changes made:\n" + "\n".join(conflicts))
        return 1
    existing_fields = {f["name"].upper() for f in layer.properties.fields}
    fields_to_add = []
    for fld in NEW_FIELDS:
        if fld["name"] in existing_fields:
            continue
        field_def = {"name": fld["name"], "type": fld["type"], "alias": fld["alias"]}
        if "length" in fld:
            field_def["length"] = fld["length"]
        if "domain" in fld:
            field_def["domain"] = fld["domain"]
        fields_to_add.append(field_def)

    # ---------------------------- Commit Schema Changes ---------------------------- #
    if not fields_to_add:
        print("All Bad Elf fields already exist. No changes needed.")
        return 0

    if args.dry_run:
        print("DRY_RUN: would add " + ", ".join(f["name"] for f in fields_to_add))
        return 0
    print(f"Adding {len(fields_to_add)} new fields to the layer...")
    response = layer.manager.add_to_definition({"fields": fields_to_add})
    if response.get("success", False):
        print("Fields and domains added successfully.")
        return 0

    print("Failed to update the layer definition.")
    print(json.dumps(response, indent=2))
    return 1


if __name__ == "__main__":
    sys.exit(main())
