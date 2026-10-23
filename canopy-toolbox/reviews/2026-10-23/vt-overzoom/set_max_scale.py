r"""Let the four hosted vector tile layers draw past 1:2,257 by clearing their service's maxScale (October 23, 2026).

    python reviews/2026-10-23/vt-overzoom/set_max_scale.py list               each service's maxScale and style resource
    python reviews/2026-10-23/vt-overzoom/set_max_scale.py ITEM               dry run: what would be sent for that item
    python reviews/2026-10-23/vt-overzoom/set_max_scale.py ITEM --go          send it, then read the service back
    python reviews/2026-10-23/vt-overzoom/set_max_scale.py ITEM --restore --go   put the original maxScale back

ArcGIS Pro Python (PYTHONNOUSERSITE=1), signed in through ArcGIS Pro (GIS("pro")). The ArcGIS Maps SDK, and so Map
Viewer and the apps, suspends a vector tile layer at scales larger than its VectorTileServer's `maxScale` (1:2,257, the
last level of the packages), whatever the layer's own maxScale in a web map says; see README.md. This posts
`serviceDefinition = {"maxScale": VALUE}` to the service's admin `edit` operation (what the API's
VectorTileLayerManager.edit_tile_service sends, which skips a 0). Nothing else in the service changes: no tiles, no
levels, no style. The item ID, item text and the item resource `styles/root.json` are untouched. The service JSON is
saved to `originals/` before the first change; `--restore` sends its maxScale back. Never shares or deletes.
"""
import argparse
import datetime
import json
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
ORIGINALS = HERE/"originals"
LOG = HERE/"applied.json"
ITEMS = {
    "slope": "3b5b1a9110f14e93af68752be89e0df2",
    "contours": "50573eeba93f405a869a1d78a08d68e8",
    "treetops": "924b993cb23046cb87641253bcf786de",
    "crowns": "d9388dc83f894edbb63e0510a8c62fa8",
}


def sign_in():
    from arcgis.gis import GIS
    gis = GIS("pro")
    print(f"signed in as {gis.users.me.username} on {gis.url}")
    return gis


def admin_url(service_url):
    return service_url.replace("/rest/services/", "/rest/admin/services/")


def state(gis, key):
    item = gis.content.get(ITEMS[key])
    public = gis.session.get(item.url, params={"f": "json"}).json()
    admin = gis.session.get(admin_url(item.url), params={"f": "json"}).json()
    resources = [r["resource"] for r in item.resources.list()]
    return item, public, admin, resources


def summary(key, item, public, admin, resources):
    lods = public.get("tileInfo", {}).get("lods", [])
    return {"item": key, "id": item.id, "title": item.title, "service maxScale": public.get("maxScale"),
            "admin maxScale": admin.get("maxScale"), "minScale": public.get("minScale"),
            "levels": f"{lods[0]['level']}-{lods[-1]['level']}" if lods else None, "maxLOD": public.get("maxLOD"),
            "styles/root.json": "styles/root.json" in resources}


def go(gis, key, value):
    item, public, admin, resources = state(gis, key)
    before = summary(key, item, public, admin, resources)
    ORIGINALS.mkdir(exist_ok=True)
    original = ORIGINALS/f"{key}_service.json"
    if not original.exists():
        original.write_text(json.dumps({"service": public, "admin": admin}, indent=1) + "\n", encoding="utf-8")
    data = {"f": "json", "serviceDefinition": json.dumps({"maxScale": value})}
    resp = gis.session.post(admin_url(item.url) + "/edit", data=data)
    resp.raise_for_status()
    answer = resp.json()
    print("edit:", answer)
    if "error" in answer or answer.get("success") is False:
        raise SystemExit(f"{key}: ArcGIS Online refused the edit; nothing else was sent")
    for wait in (0, 5, 15, 30, 60):  # the public JSON can be served stale for a short while
        time.sleep(wait)
        item, public, admin, resources = state(gis, key)
        if public.get("maxScale") == value and admin.get("maxScale") == value:
            break
    after = summary(key, item, public, admin, resources)
    print(json.dumps({"before": before, "after": after}, indent=1))
    log = json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}
    log.setdefault(key, []).append({"when": datetime.datetime.now().isoformat(timespec="seconds"), "sent": value,
                                    "answer": answer, "before": before, "after": after})
    LOG.write_text(json.dumps(log, indent=1) + "\n", encoding="utf-8")
    if after["service maxScale"] != value:
        raise SystemExit(f"{key}: the service still reads maxScale {after['service maxScale']}; check again later")
    if not after["styles/root.json"]:
        raise SystemExit(f"{key}: the item resource styles/root.json is no longer listed")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("item", choices=["list"] + list(ITEMS))
    p.add_argument("--value", type=float, default=0, help="maxScale to send (default 0, no limit)")
    p.add_argument("--restore", action="store_true", help="send the original maxScale saved in originals/")
    p.add_argument("--go", action="store_true", help="actually send it, for this one item")
    a = p.parse_args(argv)
    gis = sign_in()
    if a.item == "list":
        for key in ITEMS:
            print(json.dumps(summary(key, *state(gis, key))))
        return
    value = a.value
    if a.restore:
        original = ORIGINALS/f"{a.item}_service.json"
        if not original.exists():
            raise SystemExit(f"{a.item}: no saved original in {original}")
        value = json.loads(original.read_text(encoding="utf-8"))["service"]["maxScale"]
    item, public, admin, resources = state(gis, a.item)
    print(json.dumps(summary(a.item, item, public, admin, resources), indent=1))
    print(f"would POST {admin_url(item.url)}/edit with serviceDefinition {json.dumps({'maxScale': value})}")
    if not a.go:
        print("dry run: nothing sent (add --go)")
        return
    go(gis, a.item, value)


if __name__ == "__main__":
    main()
