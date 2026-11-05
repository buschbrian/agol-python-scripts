r"""Apply the Millcreek LiDAR styling to ArcGIS Online, or show what would change (October 23, 2026).

    python reviews/2026-10-23/agol-styling/apply_styling.py [STEP ...]          dry run: compares the repo JSON with what is online
    python reviews/2026-10-23/agol-styling/apply_styling.py [STEP ...] --go     send what differs, then read it back

    python reviews/2026-10-23/agol-styling/apply_styling.py thumbnails --thumbs DIR [--go]

STEP is any of styles, layers, maps (default all three), or thumbnails. ArcGIS Pro Python (PYTHONNOUSERSITE=1), ArcGIS API for Python
2.4; signs in with GIS("pro") and uses its session for every request. The JSON comes from build_definitions.py.
- styles: each vector tile item's resource styles/root.json (the style ArcGIS Online and the Maps SDK use when the
  item is added to a map; removing the resource restores the service's own style, kept in originals/).
- layers: the feature service item's data (drawing and pop-ups of both layers), each feature layer's service
  drawingInfo (updateDefinition with that key only), and the scene service item's data. Item text, tags and field
  descriptions are never sent (another session owns them).
- maps: the three web maps and the web scene, private in the "Millcreek LiDAR 2023" folder. Found by the IDs in
  created.json, else by title in your content; created only if missing, otherwise updated in place.
- thumbnails: each item in thumbnails.json gets DIR/<key>.png as its thumbnail (rendered by web/check.html?thumb=1 at
  the view recorded there; the PNGs carry basemap imagery, so they are not kept in the repo). Only the thumbnail is sent;
  a thumbnail it replaces is saved to DIR/replaced/ first. Entries with a "resource" are the web scene's slide
  pictures: DIR/<key>.jpg goes to that item resource, which the slide's thumbnail URL names.
Nothing is ever shared or deleted.
"""
import argparse
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_definitions import ITEMS, PORTAL  # noqa: E402

FOLDER = "Millcreek LiDAR 2023"
CREATED = HERE/"created.json"
STEPS = ("styles", "layers", "maps")
THUMBNAILS = HERE/"thumbnails.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class Portal:
    def __init__(self, go):
        from arcgis.gis import GIS
        self.gis = GIS("pro")
        self.session = self.gis.session
        self.user = self.gis.users.me.username
        self.go = go
        print(f"signed in as {self.user}; {'SENDING' if go else 'dry run, nothing is sent'}")

    def get(self, url, **params):
        r = self.session.get(url, params={"f": "json", **params})
        r.raise_for_status()
        return r.json() if r.text.strip() else None

    def post(self, url, **params):
        r = self.session.post(url, data={"f": "json", **params})
        r.raise_for_status()
        out = r.json()
        if "error" in out or out.get("success") is False:
            raise RuntimeError(f"{url}: {out}")
        return out

    def item(self, item_id):
        return self.get(f"{PORTAL}/content/items/{item_id}")

    def item_data(self, item_id):
        r = self.session.get(f"{PORTAL}/content/items/{item_id}/data", params={"f": "json"})
        return r.json() if r.status_code == 200 and r.text.strip() else None

    def update_item(self, item_id, **params):
        owner = self.item(item_id)["owner"]
        return self.post(f"{PORTAL}/content/users/{owner}/items/{item_id}/update", **params)


def report(label, current, wanted):
    if current == wanted:
        print(f"  {label}: unchanged")
        return False
    if isinstance(current, dict) and isinstance(wanted, dict):
        keys = sorted(k for k in set(current) | set(wanted) if current.get(k) != wanted.get(k))
        print(f"  {label}: differs in {keys}")
    else:
        print(f"  {label}: {'absent' if current is None else 'differs'}, would be {'sent' if current else 'created'}")
    return True


def styles(p):
    print("styles (item resource styles/root.json)")
    for name in ("slope", "contours", "treetops", "crowns"):
        item_id = ITEMS[name]["id"]
        wanted = load(HERE/"styles"/f"{name}.json")
        listed = p.get(f"{PORTAL}/content/users/{p.user}/items/{item_id}/resources").get("resources", [])
        exists = any(r["resource"] == "styles/root.json" for r in listed)
        url = f"{PORTAL}/content/items/{item_id}/resources/styles/root.json"
        current = p.get(url) if exists else None
        if report(f"{name} ({item_id})", current, wanted) and p.go:
            action = "updateResources" if exists else "addResources"
            p.post(f"{PORTAL}/content/users/{p.user}/items/{item_id}/{action}", fileName="root.json",
                   resourcesPrefix="styles", text=json.dumps(wanted))
            # A replaced resource can be served stale for a few seconds; ask again with a cache-busting parameter.
            for _ in range(6):
                back = p.get(url, _=str(time.time()))
                if back == wanted:
                    break
                time.sleep(5)
            print(f"    {action}; read back {'equal' if back == wanted else 'DIFFERENT'}")


def layers(p):
    print("layers")
    for name, file in (("features", "features_item_data.json"), ("buildings3d", "buildings3d_item_data.json")):
        item_id = ITEMS[name]["id"]
        wanted = load(HERE/"layers"/file)
        if report(f"{name} item data ({item_id})", p.item_data(item_id), wanted) and p.go:
            p.update_item(item_id, text=json.dumps(wanted))
            print(f"    item data sent; read back {'equal' if p.item_data(item_id) == wanted else 'DIFFERENT'}")
    service = ITEMS["features"]["url"]
    admin = service.replace("/rest/services/", "/rest/admin/services/")
    for layer_id in (0, 1):
        wanted = load(HERE/"layers"/f"features_layer{layer_id}_drawingInfo.json")
        current = p.get(f"{service}/{layer_id}").get("drawingInfo")
        if report(f"feature layer {layer_id} service drawingInfo", current, wanted) and p.go:
            p.post(f"{admin}/{layer_id}/updateDefinition", updateDefinition=json.dumps({"drawingInfo": wanted}),
                   **{"async": "false"})
            back = p.get(f"{service}/{layer_id}").get("drawingInfo")
            print(f"    updateDefinition (drawingInfo only); read back {'equal' if back == wanted else 'DIFFERENT'}")


def find_map(p, key, item, created):
    if key in created:
        info = p.item(created[key]["id"])
        if info and info.get("id"):
            return info["id"]
    q = f'title:"{item["title"]}" AND owner:{p.user} AND type:"{item["type"]}"'
    hits = p.get(f"{PORTAL}/search", q=q, num=20).get("results", [])
    hits = [h for h in hits if h["title"] == item["title"] and h["type"] == item["type"]]
    if len(hits) > 1:
        raise RuntimeError(f"{len(hits)} items titled {item['title']!r}; record the right one in created.json")
    return hits[0]["id"] if hits else None


def item_params(item):
    params = {k: v for k, v in item.items() if k not in ("tags", "typeKeywords", "extent")}
    params["tags"] = ",".join(item["tags"])
    params["typeKeywords"] = ",".join(item["typeKeywords"])
    (x0, y0), (x1, y1) = item["extent"]
    params["extent"] = f"{x0},{y0},{x1},{y1}"
    return params


def maps(p):
    print("maps")
    created = load(CREATED) if CREATED.exists() else {}
    folders = p.get(f"{PORTAL}/content/users/{p.user}").get("folders", [])
    folder = next(f["id"] for f in folders if f["title"] == FOLDER)
    for path in sorted((HERE/"maps").glob("*.json")):
        key, spec = path.stem, load(path)
        item, data = spec["item"], spec["data"]
        item_id = find_map(p, key, item, created)
        if item_id is None:
            print(f"  {key}: no {item['type']} titled {item['title']!r}; would be created (private, {FOLDER})")
            if p.go:
                out = p.post(f"{PORTAL}/content/users/{p.user}/{folder}/addItem", text=json.dumps(data),
                             **item_params(item))
                item_id = out["id"]
                print(f"    created {item_id}")
        else:
            info = p.item(item_id)
            props_differ = any(info.get(k) != v for k, v in item.items() if k not in ("extent", "typeKeywords")) \
                or not set(item["typeKeywords"]) <= set(info.get("typeKeywords", []))
            changed = report(f"{key} ({item_id}) data", p.item_data(item_id), data)
            print(f"  {key}: item properties {'differ' if props_differ else 'unchanged'}")
            if (changed or props_differ) and p.go:
                p.update_item(item_id, text=json.dumps(data), **item_params(item))
                print("    updated")
        if item_id and p.go:
            info = p.item(item_id)
            back = p.item_data(item_id)
            print(f"    read back: data {'equal' if back == data else 'DIFFERENT'}, access {info['access']}, "
                  f"folder {'ok' if info.get('ownerFolder') == folder else info.get('ownerFolder')}")
            created[key] = {"id": item_id, "title": item["title"], "type": item["type"]}
    if p.go:
        CREATED.write_text(json.dumps(created, indent=1) + "\n")


def slide_resource(p, key, item_id, resource, image):
    """A web scene slide's picture, kept as an item resource (the slide's thumbnail URL in maps/in-3d.json)."""
    prefix, name = resource.rsplit("/", 1)
    url = f"{PORTAL}/content/items/{item_id}/resources/{resource}"

    def current():
        r = p.session.get(url, params={"_": str(time.time())})
        return r.content if r.status_code == 200 else None

    before = current()
    if before == image:
        print(f"  {key} ({item_id} resource {resource}): unchanged")
        return
    print(f"  {key} ({item_id} resource {resource}): {'replaced' if before else 'new'}, {len(image):,} bytes")
    if p.go:
        action = "updateResources" if before is not None else "addResources"
        r = p.session.post(f"{PORTAL}/content/users/{p.item(item_id)['owner']}/items/{item_id}/{action}",
                           data={"f": "json", "resourcesPrefix": prefix, "fileName": name},
                           files={"file": (name, image, "image/jpeg")})
        r.raise_for_status()
        if "error" in r.json() or r.json().get("success") is False:
            raise RuntimeError(f"{key}: {r.json()}")
        for _ in range(6):   # a replaced resource can be served stale for a few seconds
            back = current()
            if back == image:
                break
            time.sleep(5)
        print(f"    {action}; read back {'equal' if back == image else 'DIFFERENT'}")


def thumbnails(p, folder):
    print("thumbnails")
    for key, entry in load(THUMBNAILS).items():
        if key.startswith("_"):
            continue
        # Only the pictures present in DIR are sent, so a folder of a few new renders leaves the others alone.
        image = Path(folder)/f"{key}.{'jpg' if 'resource' in entry else 'png'}"
        if not image.exists():
            print(f"  {key}: no {image.name} in DIR, left as it is")
            continue
        if "resource" in entry:
            slide_resource(p, key, entry["item"], entry["resource"], image.read_bytes())
            continue
        item_id, png = entry["item"], image.read_bytes()
        info = p.item(item_id)

        def current():
            name = p.item(item_id).get("thumbnail")
            # Plain requests get a 200-pixel copy; w=800 returns the stored original, byte for byte.
            r = (p.session.get(f"{PORTAL}/content/items/{item_id}/info/{name}", params={"w": 800, "_": str(time.time())})
                 if name else None)
            return r.content if r is not None and r.status_code == 200 else None

        before = current()
        if before == png:
            print(f"  {key} ({item_id}): unchanged")
            continue
        print(f"  {key} ({item_id}): {'replaces ' + info['thumbnail'] if info.get('thumbnail') else 'new'}, {len(png):,} bytes")
        if p.go:
            if before is not None:   # keep the thumbnail being replaced, beside the new ones
                kept = Path(folder)/"replaced"/f"{key}_{Path(info['thumbnail']).name}"
                kept.parent.mkdir(exist_ok=True)
                kept.write_bytes(before)
            r = p.session.post(f"{PORTAL}/content/users/{info['owner']}/items/{item_id}/update", data={"f": "json"},
                               files={"thumbnail": (f"{key}.png", png, "image/png")})
            r.raise_for_status()
            if "error" in r.json() or r.json().get("success") is False:
                raise RuntimeError(f"{key}: {r.json()}")
            print(f"    sent; read back {'equal' if current() == png else 'DIFFERENT'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("steps", nargs="*", metavar="STEP", help=f"any of {', '.join(STEPS)} (default all)")
    parser.add_argument("--go", action="store_true", help="send the changes (default: dry run)")
    parser.add_argument("--thumbs", help="folder of <key>.png thumbnails, for the thumbnails step")
    args = parser.parse_args()
    unknown = set(args.steps) - set(STEPS) - {"thumbnails"}
    if unknown:
        parser.error(f"unknown steps {sorted(unknown)}")
    p = Portal(args.go)
    for step in args.steps or STEPS:
        if step == "thumbnails":
            if not args.thumbs:
                parser.error("thumbnails needs --thumbs DIR")
            thumbnails(p, args.thumbs)
        else:
            globals()[step](p)


if __name__ == "__main__":
    main()
