"""Repoint the public buildings scene to the LiDAR-first layer, with pop-ups in metres and feet (October 26, 2026).

Brian: "repoint the public buildings scene to the LiDAR-first layer and make its pop-ups show metres and feet. Keep the old
layer for rollback and do it as one change." Same order as the October 25 release (reviews/2026-10-25/buildings-release):

    python release_lidar_first.py prepare           read-only: the plan (new layer text, pop-up, renderer, scene data)
    python release_lidar_first.py apply --go        protect the new layer and package, write the layer's text and drawing,
                                                    share the layer publicly, check it anonymously, then update the scene
    python release_lidar_first.py verify            read back as an anonymous viewer
    python release_lidar_first.py rollback --go     put the scene back as evidence/before-scene.json had it

ArcGIS Pro Python, PYTHONNOUSERSITE=1, signed in as GISMillcreek. Never uploads or deletes. The v2 layer, its package and
the Azure download stay as they are. The scene keeps its layer node id, camera, slides, terrain and other layers; only the
building node's item, URL, title, pop-up and renderer change. The pop-up reads the layer's own metres and feet fields
(no conversions in the pop-up); the renderer and legend use building height above ground with labels in both units.
"""
import argparse
import copy
import datetime
import gzip
import json
from pathlib import Path
import re
import urllib.request

HERE = Path(__file__).resolve().parent
EVIDENCE = HERE/"evidence"
IDS = {"new_layer": "de1adcb1da154620a1949181ab324747", "package": "e1df868f92034a409fb2d60123eec04d",
       "old_layer": "ce3617ac9b884bbcbee7c47a3e166999", "scene": "5b5bdf4a63c9466fad5884039aa7357f"}
PORTAL = "https://www.arcgis.com/sharing/rest"
KEYS = ("title", "snippet", "description", "tags", "accessInformation", "licenseInfo")
EXPECTED = {"count": 23593, "fp_sum": 2726488779, "outline": {"LiDAR-first outline (2023)": 23373,
                                                             "County footprint, roof hidden by trees": 220}}
LAYER_TITLE = "Buildings from LiDAR outlines (2023)"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def both(name, field_m, field_ft, unit_m, unit_ft, places=1, title=None, none="not modelled"):
    """An Arcade expression showing a metric field and its stored feet twin, e.g. '5.2 m (17.1 ft)'."""
    fmt = "#,##0" if places == 0 else "#,##0." + "0" * places
    return {"name": name, "title": title or name, "returnType": "string",
            "expression": f"var m = $feature.{field_m}; var f = $feature.{field_ft};\n"
                          f"if (IsEmpty(m) || IsEmpty(f)) {{ return '{none}'; }}\n"
                          f"return Text(m, '{fmt}') + ' {unit_m} (' + Text(f, '{fmt}') + ' {unit_ft})';"}


def popup():
    exprs = [
        {"name": "title", "returnType": "string", "title": "Title",
         "expression": "IIf(IsEmpty($feature.LB_ID), 'County building ' + $feature.SOURCE_ID, 'Building ' + $feature.LB_ID)"},
        {"name": "compare", "returnType": "string", "title": "Against the county footprints",
         "expression": "var c = $feature.COMPARE_CLASS; var ids = DefaultValue($feature.COUNTY_IDS, '');\n"
                       "var words = Dictionary('MATCH', 'matches one county footprint', 'RESHAPED', 'the county outline is "
                       "offset or drawn differently', 'LIDAR_JOINS', 'one building where the county has several outlines', "
                       "'LIDAR_SPLITS', 'part of what the county draws as one outline', 'TANGLE', 'overlaps several county "
                       "outlines in a mixed way', 'LIDAR_ONLY', 'not in the county footprints', 'COUNTY_ONLY', 'county "
                       "footprint kept: its roof is hidden from the lidar by trees');\n"
                       "var t = IIf(HasKey(words, c), words[c], 'not compared');\n"
                       "return IIf(ids == '', t, t + ' (county building ' + Replace(ids, ';', ', ') + ')');"},
        both("bldg", "BLDG_HT_M", "BLDG_HT_FT", "m", "ft", title="Building height (ridge above ground)"),
        both("eave", "EAVE_HT_M", "EAVE_HT_FT", "m", "ft", title="Eave height above ground"),
        both("h50", "HEIGHT_P50_M", "HEIGHT_P50_FT", "m", "ft", title="Median roof height (county footprint)", none="—"),
        both("plan", "ROOF_PLAN_M2", "ROOF_PLAN_SQFT", "m²", "sq ft", 0, "Roof plan area"),
        both("roof", "ROOF_AREA_M2", "ROOF_AREA_SQFT", "m²", "sq ft", 0, "Roof surface (sloped)"),
        both("flat", "FLAT_AREA_M2", "FLAT_AREA_SQFT", "m²", "sq ft", 0, "Roof surface under 5 degrees"),
        both("south", "SOUTH_AREA_M2", "SOUTH_AREA_SQFT", "m²", "sq ft", 0, "South-facing roof surface"),
        both("east", "EAST_AREA_M2", "EAST_AREA_SQFT", "m²", "sq ft", 0, "East-facing roof surface"),
        both("west", "WEST_AREA_M2", "WEST_AREA_SQFT", "m²", "sq ft", 0, "West-facing roof surface"),
        both("north", "NORTH_AREA_M2", "NORTH_AREA_SQFT", "m²", "sq ft", 0, "North-facing roof surface"),
        both("volume", "RF_VOLUME_M3", "RF_VOLUME_CUFT", "m³", "cu ft", 0, "Modelled volume"),
        both("fit", "RF_RMSE_LOD22", "RF_RMSE_LOD22_FT", "m", "ft", 2, "Roof fit to the lidar (RMSE)", none="—"),
    ]
    rows = [("bldg", "Building height (ridge)"), ("eave", "Eave height"), ("h50", "Median roof height (county)"),
            ("plan", "Roof plan area"), ("roof", "Roof surface"), ("flat", "Flat roof (under 5°)"), ("south", "Facing south"),
            ("east", "Facing east"), ("west", "Facing west"), ("north", "Facing north"), ("volume", "Volume"),
            ("fit", "Roof fit (RMSE)")]
    field_infos = [{"fieldName": f"expression/{k}", "label": label, "visible": True, "isEditable": False} for k, label in rows]
    field_infos += [{"fieldName": "ROOF_PLANES", "label": "Roof planes (1 m² / 10.8 sq ft or more)", "visible": True,
                     "isEditable": False, "format": {"places": 0, "digitSeparator": True}},
                    {"fieldName": "ROOF_SLOPE_MEAN", "label": "Roof slope, area-weighted (degrees)", "visible": True,
                     "isEditable": False, "format": {"places": 1, "digitSeparator": True}},
                    {"fieldName": "ROOF_AZIMUTH_MAIN", "label": "Largest plane faces (bearing, degrees)", "visible": True,
                     "isEditable": False, "format": {"places": 0, "digitSeparator": True}}]
    return {"title": "{expression/title}", "expressionInfos": exprs,
            "popupElements": [
                {"type": "text", "text": "<p><b>Roof model:</b> {LEVEL}<br /><b>Outline:</b> {OUTLINE_SOURCE}<br />"
                                         "<b>Against the county footprints:</b> {expression/compare}</p>"},
                {"type": "fields", "fieldInfos": field_infos},
                {"type": "text", "text": "<p style='font-size:11px;color:#6b6b6b'>Heights and areas in metres with feet "
                                         "(international foot). Lidar outlines follow the roof edge, so they sit a little "
                                         "outside the walls. Facing areas cover slopes of 5 to 70 degrees; they are not a "
                                         "solar estimate. Unvalidated lidar planning estimate (2023 Salt Lake Valley QL1 "
                                         "lidar); not surveyed or field-verified.</p>"}],
            "fieldInfos": [{"fieldName": f, "visible": False, "isEditable": False}
                           for f in ("LB_ID", "SOURCE_ID", "LEVEL", "OUTLINE_SOURCE", "COMPARE_CLASS", "COUNTY_IDS")]
                          + field_infos}


def renderer(before):
    """The live renderer's breaks and colours, on building height above ground (ridge; the county median for kept county
    footprints without one), labelled in metres and feet."""
    r = copy.deepcopy(before)
    r.pop("field", None)
    r["valueExpression"] = "IIf(IsEmpty($feature.BLDG_HT_M), $feature.HEIGHT_P50_M, $feature.BLDG_HT_M)"
    r["valueExpressionTitle"] = "Building height above ground"
    r["defaultLabel"] = "No modelled height"
    lo = 0
    for c in r["classBreakInfos"]:
        hi = c["classMaxValue"]
        ft = lambda v: f"{v / 0.3048:.1f}"
        c["label"] = (f"Up to {hi} m ({ft(hi)} ft)" if lo == 0 else
                      f"Over {lo} m ({ft(lo)} ft)" if hi >= 60 else f"{lo} to {hi} m ({ft(lo)} to {ft(hi)} ft)")
        lo = hi
    return r


def get_json(gis, url):
    b = gis.session.get(url, params={"f": "json"}).content
    return json.loads(gzip.decompress(b) if b.startswith(b"\x1f\x8b") else b)


def anon(url):
    with urllib.request.urlopen(url + ("&" if "?" in url else "?") + "f=json", timeout=60) as response:
        b = response.read()
    result = json.loads(gzip.decompress(b) if b.startswith(b"\x1f\x8b") else b)
    assert "error" not in result, result
    return result


def referenced(obj):
    s = json.dumps(obj)
    names = set(re.findall(r"\$feature\.([A-Za-z_][A-Za-z_0-9]*)", s)) | set(re.findall(r"\{([A-Z][A-Z_0-9]*)\}", s))
    names |= {f["fieldName"] for f in obj.get("fieldInfos", []) if not f["fieldName"].startswith("expression/")}
    return names


def prepare(gis):
    scene_before, old, new = (read(EVIDENCE/f"before-{k}.json") for k in ("scene", "v2-layer", "new-layer"))
    layer_url = new["url"] + "/layers/0"
    layer = get_json(gis, layer_url)
    fields = {f["name"] for f in layer["fields"]}
    pop = popup()
    scene = copy.deepcopy(scene_before["data"])
    nodes = [n for n in scene["operationalLayers"] if n.get("itemId") == IDS["old_layer"]]
    assert len(nodes) == 1
    node = nodes[0]
    rend = renderer(node["layerDefinition"]["drawingInfo"]["renderer"])
    missing = (referenced(pop) | referenced(rend)) - fields
    assert not missing, f"pop-up or renderer refers to fields the new layer lacks: {sorted(missing)}"
    node.update(itemId=IDS["new_layer"], url=layer_url, title=LAYER_TITLE, popupInfo=pop)
    node["layerDefinition"]["drawingInfo"]["renderer"] = rend
    props = {
        "title": new["title"],
        "snippet": "Unvalidated planning estimate: 3D buildings outlined and modelled from the 2023 lidar (roofer LoD 2.2), "
                   "county footprints only where trees hide a roof. Heights and areas in metres and feet.",
        "description": "<p>23,593 buildings: 23,373 outlined from the 2023 lidar itself and modelled with roofer LoD 2.2, "
                       "and 220 county footprints whose roofs the lidar cannot see under trees (their October 25 models). "
                       "OUTLINE_SOURCE says which; COMPARE_CLASS and COUNTY_IDS say how each lidar outline compares with "
                       "the county footprints.</p><p>Every metric field has a feet twin beside it in the same layer: _FT "
                       "for lengths and heights, _SQFT for areas, _CUFT for volume (international foot). Lidar outlines "
                       "follow the roof edge, a median 0.39 m (1.3 ft) outside the county wall lines. Heights NAVD88.</p>"
                       "<p>Replaces the three-way hybrid on county footprints (" + IDS["old_layer"] + "), which is kept "
                       "for rollback.</p>",
        "tags": new["tags"],
        "accessInformation": "City of Millcreek GIS. Lidar: 2023 Salt Lake Valley QL1 lidar (USGS 3DEP, project "
                             "UT_2023SaltLakeCo_C24). Building outlines: from the lidar; county footprints (Salt Lake "
                             "County Assessor and Surveyor, downloaded October 19, 2026) only where trees hide a roof. "
                             "Roof models: roofer 1.0.0 (3DGI / TU Delft).",
        "licenseInfo": old["licenseInfo"]}
    assert len(props["snippet"]) <= 250 and "planning estimate" in props["snippet"].lower()
    layer_data = {"layers": [{"id": 0, "popupInfo": pop, "layerDefinition": {"drawingInfo": {"renderer": rend}}}]}
    plan = {"created": datetime.datetime.now().isoformat(timespec="seconds"), "new_layer": {"props": props, "data": layer_data},
            "scene": {"data": scene}, "layer_fields": len(fields)}
    write(EVIDENCE/"release-plan.json", plan)
    print(f"Prepared: {len(fields)} layer fields, pop-up and renderer refer only to existing fields; "
          f"scene node {node['id']} repointed in the plan; nothing sent.")
    return plan


def update(gis, item_id, props=None, data=None):
    item = gis.content.get(item_id)
    payload = {"f": "json", **(props or {})}
    if isinstance(payload.get("tags"), list):
        payload["tags"] = ",".join(payload["tags"])
    if data is not None:
        payload["text"] = json.dumps(data)
    r = gis.session.post(f"{PORTAL}/content/users/{item.owner}/items/{item_id}/update", data=payload)
    r.raise_for_status()
    assert r.json().get("success") is True, r.json()


def verify(gis, plan):
    out = {"verified_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    assert anon(f"{PORTAL}/content/items/{IDS['new_layer']}")["access"] == "public"
    assert anon(f"{PORTAL}/content/items/{IDS['old_layer']}")["access"] == "public"   # kept for rollback
    assert gis.content.get(IDS["package"]).access == "private"
    for key in ("new_layer", "package"):
        assert gis.content.get(IDS[key]).protected, key
    assert anon(f"{PORTAL}/content/items/{IDS['scene']}/data") == plan["scene"]["data"]
    assert anon(f"{PORTAL}/content/items/{IDS['new_layer']}/data") == plan["new_layer"]["data"]
    url = gis.content.get(IDS["new_layer"]).url + "/layers/0"
    layer = anon(url)
    stats = {i["name"]: anon(url + "/" + i["href"].removeprefix("./"))["stats"] for i in layer["statisticsInfo"]
             if i["name"] in ("FP_ID", "OUTLINE_SOURCE")}
    assert stats["FP_ID"]["sum"] == EXPECTED["fp_sum"]
    assert {v["value"]: v["count"] for v in stats["OUTLINE_SOURCE"]["mostFrequentValues"]} == EXPECTED["outline"]
    out.update(new_layer_public=True, old_layer_public=True, package_private=True, delete_protected=True,
               scene_matches_plan=True, layer_data_matches_plan=True, anonymous_statistics_match=True, layer_url=url)
    write(EVIDENCE/"release-verification.json", out)
    print(json.dumps(out, indent=1))


def apply(gis, plan):
    before = read(EVIDENCE/"before-scene.json")
    scene = gis.content.get(IDS["scene"])
    current = scene.get_data()
    applied = [read(f)["scene"]["data"] for f in sorted(EVIDENCE.glob("release-plan-applied-*.json"))]   # earlier revisions
    assert current in (before["data"], plan["scene"]["data"], *applied), "the scene changed since the snapshot; snapshot again"
    for key in ("new_layer", "package"):
        assert gis.content.get(IDS[key]).protect(enable=True), key
    update(gis, IDS["new_layer"], plan["new_layer"]["props"], plan["new_layer"]["data"])
    print("New layer text, pop-up and renderer saved; layer and package delete-protected.", flush=True)
    gis.content.get(IDS["new_layer"]).sharing.sharing_level = "EVERYONE"
    url = gis.content.get(IDS["new_layer"]).url + "/layers/0"
    assert anon(f"{PORTAL}/content/items/{IDS['new_layer']}")["access"] == "public"
    assert anon(url)["layerType"] == "3DObject"
    print("New layer is publicly readable. Repointing the scene.", flush=True)
    update(gis, IDS["scene"], data=plan["scene"]["data"])
    verify(gis, plan)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("prepare", "apply", "verify", "rollback"))
    p.add_argument("--go", action="store_true")
    a = p.parse_args()
    if a.step in ("apply", "rollback") and not a.go:
        p.error("Changes need --go; run prepare first.")
    from arcgis.gis import GIS
    gis = GIS("pro")
    assert gis.users.me.username == "GISMillcreek"
    if a.step == "prepare":
        prepare(gis)
        return
    plan = read(EVIDENCE/"release-plan.json")
    if a.step == "apply":
        apply(gis, plan)
    elif a.step == "verify":
        verify(gis, plan)
    else:
        before = read(EVIDENCE/"before-scene.json")
        assert gis.content.get(IDS["scene"]).get_data() == plan["scene"]["data"], "scene changed after release; review first"
        update(gis, IDS["scene"], data=before["data"])
        assert gis.content.get(IDS["scene"]).get_data() == before["data"]
        print("Scene restored to the v2 layer; the new layer stays public and protected (unshare it by hand if wanted).")


if __name__ == "__main__":
    main()
