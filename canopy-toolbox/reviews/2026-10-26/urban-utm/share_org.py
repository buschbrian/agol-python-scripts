r"""Share the three Urban UTM layers with the organization only, delete-protect them and their packages, and read them back.

    python reviews/2026-10-26/urban-utm/share_org.py verify          read-only: sharing, protection, services against the sources
    python reviews/2026-10-26/urban-utm/share_org.py apply --go      layers to the organization, packages private, all six protected

ArcGIS Pro Python (PYTHONNOUSERSITE=1), signed in to Pro as GISMillcreek. Brian approved these items org-only on October 26:
never shared with everyone or with groups. The packages stay private (the October 25 precedent). Never deletes. Reads the
private services with the signed-in session; writes evidence/verification.json.
"""
import argparse
import datetime
import gzip
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[3]))
from canopy.lidar_root import lidar_root  # noqa: E402

RUN = lidar_root()/"2023-salt-lake-valley"/"runs"/"urban-utm-20261026"
LAYERS = {"urban_buildings": "b8e8ddaceac54876bd4c0cf3f31d92fd", "urban_footprints": "e74c2216aca54d7f8be2432768b64520",
          "urban_terrain": "83d1a892fd67408b9f8f9fcb754cd479"}
PACKAGES = {"urban_buildings": "c7702ec26f7843ad9572b797888557d6", "urban_footprints": "32ba9a96f01d43b690f8faa4ce4c6a15",
            "urban_terrain": "33b6ae61d34e4cd682c45fa42b229095"}
# Public items this work must not touch.
PUBLIC = {"scene_layer": "ce3617ac9b884bbcbee7c47a3e166999", "web_scene": "5b5bdf4a63c9466fad5884039aa7357f",
          "lod12_layer": "5082b5bd063a4a03847f2082dc3533d1"}
EXPECTED = {"count": 21561, "fp_id_sum": 237493394, "floors_sum": 32836, "floors_min": 1, "floors_max": 12,
            "levels": {"roofer LoD2.2": 20730, "Esri LOD2.0": 647, "Esri LOD1.2": 184}}
WKID = 6341


def sign_in():
    from arcgis.gis import GIS
    gis = GIS("pro")
    assert gis.users.me.username == "GISMillcreek", gis.users.me.username
    return gis


def get(gis, url, **params):
    response = gis.session.get(url, params={"f": "json", **params})
    response.raise_for_status()
    body = response.content
    # SceneServer serves precompressed I3S resources.
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    result = json.loads(body)
    assert "error" not in result, result
    return result


def sharing(item):
    shared = item.shared_with
    return {"access": item.access, "everyone": bool(shared.get("everyone")), "org": bool(shared.get("org")),
            "groups": [g.id for g in shared.get("groups", [])], "protected": item.protected}


def check_scene(gis, url):
    layer = get(gis, url + "/layers/0")
    stats = {s["name"]: get(gis, url + "/layers/0/" + s["href"].removeprefix("./"))["stats"]
             for s in layer["statisticsInfo"] if s["name"] in ("FP_ID", "FLOORS", "LEVEL")}
    levels = {v["value"]: v["count"] for v in stats["LEVEL"]["mostFrequentValues"]}
    out = {"layerType": layer["layerType"], "spatialReference": layer["spatialReference"],
           "heightModelInfo": layer.get("heightModelInfo"), "fields": [f["name"] for f in layer["fields"]],
           "fp_id": [stats["FP_ID"]["count"], stats["FP_ID"]["sum"]],
           "floors": [stats["FLOORS"]["sum"], stats["FLOORS"]["min"], stats["FLOORS"]["max"]], "levels": levels}
    out["ok"] = (layer["layerType"] == "3DObject" and layer["spatialReference"]["latestWkid"] == WKID
                 and out["fp_id"] == [EXPECTED["count"], EXPECTED["fp_id_sum"]]
                 and out["floors"] == [EXPECTED["floors_sum"], EXPECTED["floors_min"], EXPECTED["floors_max"]]
                 and levels == EXPECTED["levels"] and "FLOORS" in out["fields"])
    return out


def check_features(gis, url):
    layer = get(gis, url + "/0")
    stat = [{"statisticType": t, "onStatisticField": f, "outStatisticFieldName": n} for t, f, n in
            (("count", "FP_ID", "n"), ("sum", "FP_ID", "s"), ("sum", "FLOORS", "f"), ("min", "FLOORS", "fmin"),
             ("max", "FLOORS", "fmax"), ("sum", "Shape__Area", "area"))]
    a = get(gis, url + "/0/query", where="1=1", outStatistics=json.dumps(stat))["features"][0]["attributes"]
    levels = {f["attributes"]["LEVEL_"]: f["attributes"]["n"] for f in get(
        gis, url + "/0/query", where="1=1", groupByFieldsForStatistics="LEVEL_",
        outStatistics=json.dumps([{"statisticType": "count", "onStatisticField": "FP_ID", "outStatisticFieldName": "n"}]))["features"]}
    nulls = get(gis, url + "/0/query", where="FLOORS IS NULL", returnCountOnly="true")["count"]
    local = json.loads((RUN/"footprints"/"footprints.json").read_text(encoding="utf-8"))
    out = {"geometryType": layer["geometryType"], "spatialReference": layer["extent"]["spatialReference"],
           "fields": [(f["name"], f["type"]) for f in layer["fields"]], "fp_id": [a["n"], a["s"]],
           "floors": [a["f"], a["fmin"], a["fmax"]], "floors_null": nulls, "levels": levels,
           "area_m2": a["area"], "local_area_m2": local["area_m2"]}
    out["ok"] = (layer["extent"]["spatialReference"]["latestWkid"] == WKID and out["fp_id"] == [EXPECTED["count"], EXPECTED["fp_id_sum"]]
                 and out["floors"] == [EXPECTED["floors_sum"], EXPECTED["floors_min"], EXPECTED["floors_max"]]
                 and nulls == 0 and levels == EXPECTED["levels"] and abs(a["area"] - local["area_m2"]) < 1.0)
    return out


def check_terrain(gis, url):
    """The service's tiling scheme against the local scheme, and level 14 tiles against the package's own bytes."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("urban_utm", HERE.parent/"urban_utm.py")
    uu = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(uu)
    pt = uu._load("package_tiles", uu.REVIEWS/"2026-10-22"/"hosting"/"tiles"/"package_tiles.py")
    service = get(gis, url)
    info = service.get("tileInfo", {})
    scheme = uu.read_scheme(RUN/"elevation"/"scheme.xml")
    lods = [(lod["level"], lod["resolution"]) for lod in info.get("lods", [])]
    tpkx = RUN/"millcreek_terrain_utm_20261026.tpkx"
    local = {(r, c): d for r, c, d in pt.package_tiles(tpkx, 14)}
    picks = sorted(k for k, d in local.items() if pt.decode("terrain", d)[1].all())[::400]
    tiles = []
    for r, c in picks:
        response = gis.session.get(f"{url}/tile/14/{r}/{c}")
        hosted = response.content if response.status_code == 200 else b""
        same = hosted == local[(r, c)]
        diff = None
        if hosted and not same:
            import numpy as np
            diff = float(np.abs(pt.decode("terrain", hosted)[0] - pt.decode("terrain", local[(r, c)])[0]).max())
        tiles.append({"tile": [14, r, c], "status": response.status_code, "bytes_equal": same, "max_abs_diff_m": diff})
    out = {"serviceDataType": service.get("serviceDataType"), "spatialReference": service.get("spatialReference"),
           "tile_format": info.get("format"), "tile_size": [info.get("rows"), info.get("cols")],
           "origin": info.get("origin"), "lods": lods, "cacheType": service.get("cacheType"),
           "scheme_origin": scheme["origin"], "tiles": tiles}
    out["ok"] = (service.get("spatialReference", {}).get("latestWkid") == WKID
                 and [info["origin"]["x"], info["origin"]["y"]] == scheme["origin"]
                 and [round(res, 9) for _, res in lods] == [round(lod["resolution"], 9) for lod in scheme["lods"]]
                 and all(t["bytes_equal"] or (t["max_abs_diff_m"] is not None and t["max_abs_diff_m"] <= 0.01) for t in tiles))
    return out


def verify(gis):
    record = {"verified_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "items": {}}
    for key, item_id in LAYERS.items():
        layer, package = gis.content.get(item_id), gis.content.get(PACKAGES[key])
        record["items"][key] = {"layer": {"id": item_id, "type": layer.type, "url": layer.url, **sharing(layer)},
                                "package": {"id": package.id, "type": package.type, "size": package.size, **sharing(package)}}
    record["items"]["urban_buildings"]["service"] = check_scene(gis, record["items"]["urban_buildings"]["layer"]["url"])
    record["items"]["urban_footprints"]["service"] = check_features(gis, record["items"]["urban_footprints"]["layer"]["url"])
    record["items"]["urban_terrain"]["service"] = check_terrain(gis, record["items"]["urban_terrain"]["layer"]["url"])
    record["public_items_untouched"] = {k: {"id": v, "access": gis.content.get(v).access,
                                            "modified": gis.content.get(v).modified} for k, v in PUBLIC.items()}
    sharing_ok = all(i["layer"]["access"] == "org" and not i["layer"]["everyone"] and not i["layer"]["groups"]
                     and i["layer"]["protected"] and i["package"]["access"] == "private" and i["package"]["protected"]
                     for i in record["items"].values())
    record["sharing_ok"] = sharing_ok
    record["services_ok"] = all(i["service"]["ok"] for i in record["items"].values())
    out = HERE.parent/"evidence"
    out.mkdir(exist_ok=True)
    (out/"verification.json").write_text(json.dumps(record, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(record, default=str))
    return record


def apply(gis):
    for key, item_id in LAYERS.items():
        layer, package = gis.content.get(item_id), gis.content.get(PACKAGES[key])
        assert layer.access in ("private", "org") and package.access == "private", (key, layer.access, package.access)
        assert layer.protect(enable=True) and package.protect(enable=True), key
        layer.sharing.sharing_level = "ORGANIZATION"
        print(key, "layer shared with the organization; layer and package delete-protected", flush=True)
    verify(gis)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("verify", "apply"))
    p.add_argument("--go", action="store_true")
    a = p.parse_args()
    if a.step == "apply" and not a.go:
        p.error("apply changes sharing and protection; add --go")
    gis = sign_in()
    apply(gis) if a.step == "apply" else verify(gis)


if __name__ == "__main__":
    main()
