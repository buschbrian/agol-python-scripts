r"""Share the published Millcreek LiDAR items publicly, then check them as an anonymous viewer (October 23, 2026).

    python reviews/2026-10-22/hosting/upload/share.py check          sharing level of each item, and the anonymous check
    python reviews/2026-10-22/hosting/upload/share.py share --go     share every item with everyone, then check

ArcGIS Pro Python (PYTHONNOUSERSITE=1). Brian decided on October 23 that all eight layers go public, treetops and crowns
included, with the three web maps and the 3D scene built on them. Without --go nothing changes. The anonymous check uses
plain HTTPS requests with no token: each item's description must say "public"; each service must answer; each tile
layer must serve a tile; each web map and the scene must reference only items an anonymous viewer can open.
"""
import argparse
import json
from pathlib import Path
import sys

import requests

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[4]))
from canopy.lidar_root import lidar_root  # noqa: E402

PORTAL = "https://www.arcgis.com/sharing/rest"
# Level 14 tile over the middle of Millcreek (-111.84, 40.69): row 6159, column 3102, in both tiling schemes.
TILE_14 = "14/6159/3102"
LAYERS = {
    "features": "d5effaee6c66497eaeb64e4c2e0f496e", "slope": "3b5b1a9110f14e93af68752be89e0df2",
    "contours": "50573eeba93f405a869a1d78a08d68e8", "hillshade": "cab8824e44384d479e1f302cdf34daf9",
    "treetops": "924b993cb23046cb87641253bcf786de", "crowns": "d9388dc83f894edbb63e0510a8c62fa8",
    "buildings3d": "5082b5bd063a4a03847f2082dc3533d1", "terrain": "ce1680a5196e458ebfb60ead5150b946",
}
MAPS = {
    "map_terrain_slope": "177bfc592415451585ba72ab9207b3c6", "map_tree_canopy": "e5efa719691045849108553394448f35",
    "map_buildings": "504554bd5a9545559db06aa6098e8e49", "scene_3d": "5b5bdf4a63c9466fad5884039aa7357f",
}
LOG = lidar_root()/"2023-salt-lake-valley"/"runs"/"hosting-uploads"/"sharing.json"


def anon(url, **params):
    """A request with no token and no session, as a member of the public would make it."""
    return requests.get(url, params=params, timeout=60)


def item_items(data):
    """Item IDs a web map or scene references: operational layers (and their sublayers), ground layers, basemaps."""
    ids = set()

    def walk(layers):
        for lyr in layers or []:
            if lyr.get("itemId"):
                ids.add(lyr["itemId"])
            walk(lyr.get("layers"))
    walk(data.get("operationalLayers"))
    walk((data.get("ground") or {}).get("layers"))
    walk((data.get("baseMap") or {}).get("baseMapLayers"))
    return ids


def package_tile(key):
    """The first level-14 tile (else the deepest level's first) stored in the item's own .vtpk."""
    sys.path.insert(0, str(HERE.parent))
    sys.path.insert(0, str(HERE.parents[1]/"vector-tiles"))
    from upload import ITEMS
    from build_vector_tiles import _tiles
    tiles = [(lvl, r, c) for lvl, r, c, _ in _tiles(ITEMS[key]["file"])]
    lvl, r, c = next((x for x in tiles if x[0] == 14), max(tiles))
    return f"{lvl}/{r}/{c}"


def check_item(key, item_id):
    out = {"key": key, "id": item_id}
    meta = anon(f"{PORTAL}/content/items/{item_id}", f="json").json()
    out["access"] = meta.get("access", meta.get("error", {}).get("message"))
    out["type"] = meta.get("type")
    url = meta.get("url")
    if url:
        svc = anon(url, f="json")
        body = svc.json() if "json" in svc.headers.get("content-type", "") else {}
        out["service"] = "ok" if svc.status_code == 200 and "error" not in body else f"{svc.status_code} {body.get('error')}"
        if url.endswith("VectorTileServer"):
            style = anon(url + "/resources/styles/root.json")
            out["style"] = style.status_code
            # Indexed packages keep sparse areas at a shallower level, so ask for a tile the package itself holds.
            path = package_tile(key)
            out["tile_14"], out["tile_checked"] = anon(url + f"/tile/{path}.pbf").status_code, path
        elif url.endswith("MapServer") or url.endswith("ImageServer"):
            tile = anon(url + f"/tile/{TILE_14}")
            out["tile_14"] = tile.status_code
        elif url.endswith("FeatureServer"):
            q = anon(url + "/0/query", where="1=1", returnCountOnly="true", f="json").json()
            out["features_layer0"] = q.get("count", q.get("error"))
        elif url.endswith("SceneServer"):
            lyr = anon(url + "/layers/0", f="json").json()
            out["scene_layer"] = lyr.get("layerType", lyr.get("error"))
    if key.startswith(("map_", "scene_")):
        data = anon(f"{PORTAL}/content/items/{item_id}/data", f="json").json()
        refs = item_items(data)
        blocked = []
        for ref in sorted(refs):
            r = anon(f"{PORTAL}/content/items/{ref}", f="json").json()
            if r.get("access") != "public":
                blocked.append(ref)
        out["references"] = len(refs)
        out["references_not_public"] = blocked
    out["ok"] = out["access"] == "public" and out.get("service", "ok") == "ok" and not out.get("references_not_public") \
        and out.get("tile_14", 200) == 200 and out.get("style", 200) == 200
    return out


def check():
    results = [check_item(k, v) for k, v in {**LAYERS, **MAPS}.items()]
    for r in results:
        print(json.dumps(r))
    return results


def share():
    from arcgis.gis import GIS
    gis = GIS("pro")
    print(f"Signed in to {gis.url} as {gis.users.me.username}")
    shared = {}
    for key, item_id in {**LAYERS, **MAPS}.items():
        item = gis.content.get(item_id)
        before = item.access
        if before != "public":
            item.sharing.sharing_level = "EVERYONE"
        after = gis.content.get(item_id).access
        shared[key] = {"id": item_id, "title": item.title, "before": before, "after": after}
        print(f"{key:18} {before:8} -> {after:8} {item.title}")
    return shared


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("check", "share"))
    p.add_argument("--go", action="store_true")
    a = p.parse_args(argv)
    record = {}
    if a.step == "share":
        if not a.go:
            print("Dry run: would share with everyone:", ", ".join({**LAYERS, **MAPS}))
            return
        record["shared"] = share()
    record["anonymous_check"] = check()
    if a.step == "share":
        LOG.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
        print("Logged to", LOG)
    bad = [r["key"] for r in record["anonymous_check"] if not r["ok"]]
    print("All public and loading anonymously." if not bad else "NOT OK: " + ", ".join(bad))


if __name__ == "__main__":
    main()
