r"""Apps for the Millcreek LiDAR layers (October 23, 2026): a Sidebar Instant App on the tree canopy web map and two 3D
Viewer Instant Apps, one on each web scene (terrain and slope, buildings). All carry the planning-estimate warning.

    python reviews/2026-10-23/agol-apps/make_apps.py plan            what would be created (nothing is sent)
    python reviews/2026-10-23/agol-apps/make_apps.py create --go     create any app not yet in created.json, private
    python reviews/2026-10-23/agol-apps/make_apps.py update [--go]   bring the existing apps in line with APPS (dry run
                                                                     without --go): title, text, template, settings
    python reviews/2026-10-23/agol-apps/make_apps.py delete [--go]   move the retired items in RETIRED to the recycle bin
    python reviews/2026-10-23/agol-apps/make_apps.py check           read each back: private or public, settings, links

History (October 23 evening, Brian's call): the terrain app was a Sidebar app on the 2D terrain web map and became a 3D
Viewer app on the new "Millcreek terrain and slope in 3D" scene, updated in place (same item and ID); the "Millcreek in 3D"
app became the buildings app; the Sidebar buildings app and the StoryMap landing page (which did not work) were retired to
the recycle bin. Item text follows the item-text session's house style (agol-metadata/_shared.md).

ArcGIS Pro Python (PYTHONNOUSERSITE=1), ArcGIS API for Python 2.4, signed in through ArcGIS Pro (GIS("pro")). Brian asked
to see each app before it is shared, so `create` makes them private and nothing here shares. The Instant Apps are items
of type Web Mapping Application whose data names Esri's English template (Sidebar f6a143fb..., 3D Viewer 888910da...)
and the settings ("values") the template reads; the settings follow public apps built on the same templates.
"""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve()
CREATED = HERE.parent/"created.json"
sys.path.insert(0, str(HERE.parents[1]/"agol-styling"))
from build_definitions import CREDITS, CREDITS_BUILDINGS, SNIPPET_END, TAGS as HOUSE_TAGS, terms  # noqa: E402
from reader_context import context
PORTAL = "https://www.arcgis.com/sharing/rest"
FOLDER = "Millcreek LiDAR 2023"
TAGS = HOUSE_TAGS + ["app"]
TEMPLATES = {"sidebar": ("f6a143fb90c44d7b860f623f1a23c322", "sidebar", "instant_app_sidebar"),
             "3dviewer": ("888910da7fdc4b11ac32825ad2d87816", "3dviewer", "af151b76c68941d48f41b3031bf1110e")}
WARNING = ("<p><strong>Planning estimates.</strong> Everything here comes from the 2023 Salt Lake Valley QL1 lidar "
           "(flown October-November 2023) and the City of Millcreek's processing of it. These are unvalidated planning "
           "estimates, not surveyed or field-verified data. Do not use them for engineering, legal or property "
           "decisions.</p>")

APPS = {
    "terrain": {
        "context": "terrain",
        "template": "3dviewer", "map": "71b680b486b245fd8ec17eb80387be94", "title": "Millcreek Terrain and Slope in 3D",
        "what": "Slope classes and contours at 6.56 ft intervals on Millcreek's lidar terrain, from the valley floor to "
                "the east bench. Use the slides for the hillside neighbourhoods, or drag to look around.",
        "tags": ["slope", "terrain", "contours", "hillshade", "3D"]},
    "canopy": {
        "context": "canopy",
        "template": "sidebar", "map": "e5efa719691045849108553394448f35", "title": "Millcreek Tree Canopy",
        "what": "Tree canopy cover by ownership zone (25.59% of the city), estimated tree crowns and lidar treetops by "
                "height. Crowns and treetops appear as you zoom in. Treetops are lidar detections, not a tree census.",
        "tags": ["tree canopy", "urban forest", "trees"]},
    "in3d": {
        "context": "in3d",
        "template": "3dviewer", "map": "5b5bdf4a63c9466fad5884039aa7357f", "title": "Millcreek Buildings in 3D",
        "what": "Millcreek's buildings with modelled lidar roof forms and measurements in feet, on the city's lidar "
                "terrain. Select a building for its model source, heights and available roof measurements. "
                "Use the slides for a tour, or drag to look around.",
        "tags": ["buildings", "building height", "3D"], "buildings": True},
}
# Retired on October 23 (Brian's call): deleted to the recycle bin, never permanently.
RETIRED = {"buildings": "370a1f38728545e4a0c57d29386143f4", "landing": "8d43f724a81e4c1d8ed91a9520cf0e29"}


def splash(spec):
    return (f"<p>{spec['what']}</p>" + WARNING +
            context(spec['context']))


def values(spec):
    common = {"splash": True, "splashTitle": spec["title"], "splashContent": splash(spec), "splashButtonText": "Open",
              "theme": "light", "home": True, "fullScreen": True, "share": True, "measure": True, "legend": True,
              "search": True, "popupHover": False, "units": "imperial", "info": True,
              "measureLinearUnit": "feet", "measureAreaUnit": "square-feet",
              "detailsOpenAtStart": False, "detailsContent": splash(spec)}
    if spec["template"] == "sidebar":
        return {**common, "webmap": spec["map"], "title": spec["title"], "header": True, "titleLink": "",
                "splashOnStart": True, "legendOpenAtStart": True, "searchOpenAtStart": False, "mapZoom": True,
                "zoomControls": True, "scalebar": True, "locate": False, "basemapToggle": False, "exportToPDF": False,
                "keyboardShortcuts": True, "applyCustomTheme": False, "fullAppSettings": False,
                "mapA11yDesc": f"{spec['title']}: {spec['what']}"}
    return {**common, "type": "webscene", "webscene": spec["map"], "slides": True, "layerList": True,
            "layerListOpenAtStart": False, "daylight": True, "daylightOpenAtStart": False,
            "elevationProfile": spec['context'] == 'terrain', "elevationProfileUnits": "imperial",
            "elevationProfileOpenAtStart": False,
            "lineOfSight": False, "slice": False, "customHeader": False, "applySharedTheme": False,
            "exportToPDF": False, "fullAppSettings": False}


def description(spec):
    kind = "web map" if spec["template"] == "sidebar" else "web scene"
    return (WARNING + f"<p>{spec['what']}</p>" + context(spec['context']) +
            # rel as ArcGIS Online stores it, so the read-back compares equal
            f"<p>Built on the {kind} <a href='https://www.arcgis.com/home/item.html?id={spec['map']}' "
            f"rel='nofollow ugc'>{spec['map']}</a>; "
            "each layer's own page describes how it was made, its fields and its limits.</p>"
            "<p><b>Questions or corrections:</b> City of Millcreek GIS.</p>")


def keywords(spec):
    source_kw = TEMPLATES[spec["template"]][2]
    return (["Configurable", "configurableApp", "instantApp", "JavaScript", "Map", "Mapping Site", "Online Map",
             "Web Map", f"sourceId#{source_kw}"] + (["3Dscene"] if spec["template"] == "3dviewer" else []))


def properties(spec, folder_id):
    """Everything the app item carries, in the form the portal's update call takes."""
    snippet = f"{spec['what'].split('. ')[0]}. {SNIPPET_END}"
    if len(snippet) > 250:
        raise ValueError(f"{spec['title']}: summary over 250 characters")
    return {"title": spec["title"], "snippet": snippet, "description": description(spec),
            "tags": TAGS + spec["tags"], "typeKeywords": keywords(spec), "licenseInfo": terms(spec.get("buildings")),
            "accessInformation": CREDITS_BUILDINGS if spec.get("buildings") else CREDITS,
            "text": {"source": TEMPLATES[spec["template"]][0], "folderId": folder_id, "values": values(spec)}}


def app_url(base, spec, item_id):
    return f"{base}/apps/instant/{TEMPLATES[spec['template']][1]}/index.html?appid={item_id}"


def read_created():
    return json.loads(CREATED.read_text(encoding="utf-8")) if CREATED.exists() else {}


def plan():
    for key, spec in APPS.items():
        print(json.dumps({"key": key, "title": spec["title"], "template": TEMPLATES[spec["template"]][0],
                          "map": spec["map"], "values": values(spec)}, indent=1)[:1500])


def create():
    from arcgis.gis import GIS, ItemProperties
    gis = GIS("pro")
    me = gis.users.me
    print(f"Signed in to {gis.url} as {me.username}")
    base = f"https://{gis.properties.urlKey}.{gis.properties.customBaseUrl}"
    folder = gis.content.folders.get(FOLDER)
    created = read_created()
    for key, spec in APPS.items():
        if key in created:
            print(f"{key}: already created ({created[key]['id']}); skipping")
            continue
        want = properties(spec, folder.properties["id"])
        props = ItemProperties(title=want["title"], item_type="Web Mapping Application", tags=want["tags"],
                               snippet=want["snippet"], description=want["description"],
                               type_keywords=want["typeKeywords"], license_info=want["licenseInfo"],
                               access_information=want["accessInformation"])
        item = folder.add(item_properties=props, text=json.dumps(want["text"])).result()
        url = app_url(base, spec, item.id)
        item.update(item_properties={"url": url})
        created[key] = {"id": item.id, "url": url, "title": spec["title"]}
        CREATED.write_text(json.dumps(created, indent=1) + "\n", encoding="utf-8")
        print(f"{key}: {item.id} {url}")


def update(go):
    """Bring each existing app (by its ID in created.json) in line with APPS: only what differs is sent, then read back."""
    from arcgis.gis import GIS
    gis = GIS("pro")
    s, me = gis.session, gis.users.me.username
    base = f"https://{gis.properties.urlKey}.{gis.properties.customBaseUrl}"
    folder_id = gis.content.folders.get(FOLDER).properties["id"]
    created = read_created()
    print(f"Signed in as {me}; {'SENDING' if go else 'dry run, nothing is sent'}")
    for key, spec in APPS.items():
        if key not in created:
            print(f"{key}: not created yet (run create)")
            continue
        item_id = created[key]["id"]
        want = {**properties(spec, folder_id), "url": app_url(base, spec, item_id)}
        info = s.get(f"{PORTAL}/content/items/{item_id}", params={"f": "json"}).json()
        now = {k: info.get(k) for k in want if k != "text"}
        now["text"] = s.get(f"{PORTAL}/content/items/{item_id}/data", params={"f": "json"}).json()
        differ = [k for k in want
                  if (set(now[k] or []) != set(want[k]) if k in ("tags", "typeKeywords") else now[k] != want[k])]
        print(f"{key} ({item_id}): {'differs in ' + ', '.join(differ) if differ else 'unchanged'}")
        if go and differ:
            params = {k: (",".join(want[k]) if k in ("tags", "typeKeywords") else
                          json.dumps(want[k]) if k == "text" else want[k]) for k in differ}
            r = s.post(f"{PORTAL}/content/users/{me}/items/{item_id}/update", data={"f": "json", **params}).json()
            if not r.get("success"):
                raise RuntimeError(f"{key}: {r}")
            back = s.get(f"{PORTAL}/content/items/{item_id}/data", params={"f": "json"}).json()
            info = s.get(f"{PORTAL}/content/items/{item_id}", params={"f": "json"}).json()
            print(f"  sent; read back: settings {'equal' if back == want['text'] else 'DIFFERENT'}, "
                  f"title {info['title']!r}, url {info['url']}, access {info['access']}")
        created[key] = {"id": item_id, "url": want["url"], "title": spec["title"]}
    if go:
        CREATED.write_text(json.dumps(created, indent=1) + "\n", encoding="utf-8")


def delete(go):
    """Move each retired item to the recycle bin (permanentDelete false), confirm it left the content, and record it."""
    from arcgis.gis import GIS
    gis = GIS("pro")
    s, me = gis.session, gis.users.me.username
    created = read_created()
    retired = created.setdefault("retired", {})
    print(f"Signed in as {me}; {'SENDING' if go else 'dry run, nothing is sent'}")
    for key, item_id in RETIRED.items():
        info = s.get(f"{PORTAL}/content/items/{item_id}", params={"f": "json"}).json()
        if "error" in info:
            print(f"{key} ({item_id}): not in your content ({info['error'].get('message')})")
            continue
        print(f"{key} ({item_id}): {info['type']} {info['title']!r}, {info['access']}, protected {info.get('protected')}"
              f"{'' if go else '; would go to the recycle bin'}")
        if go:
            r = s.post(f"{PORTAL}/content/users/{me}/items/{item_id}/delete",
                       data={"f": "json", "permanentDelete": "false"}).json()
            if not r.get("success"):
                raise RuntimeError(f"{key}: {r}")
            gone = "error" in s.get(f"{PORTAL}/content/items/{item_id}", params={"f": "json"}).json()
            print(f"  deleted to the recycle bin; item page gone: {gone}")
            retired[key] = {"id": item_id, "type": info["type"], "title": info["title"],
                            "deleted": "2026-10-23, to the recycle bin (restore from Content > Recycle bin)"}
            created.pop(key, None)
    if go:
        CREATED.write_text(json.dumps(created, indent=1) + "\n", encoding="utf-8")


def check():
    from arcgis.gis import GIS
    gis = GIS("pro")
    for key, rec in read_created().items():
        if key == "retired":
            continue
        item = gis.content.get(rec["id"])
        out = {"key": key, "title": item.title, "type": item.type, "access": item.access, "url": item.url}
        if key in APPS:
            data = item.get_data()
            v = data.get("values", {})
            target = v.get("webmap") or v.get("webscene")
            out.update(source=data.get("source"), map=target, map_ok=target == APPS[key]["map"],
                       splash_warning="planning estimates" in v.get("splashContent", "").lower(),
                       map_access=gis.content.get(target).access)
        print(json.dumps(out))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("step", choices=("plan", "create", "update", "delete", "check"))
    p.add_argument("--go", action="store_true")
    a = p.parse_args(argv)
    if a.step == "plan" or (a.step == "create" and not a.go):
        plan()
    elif a.step == "create":
        create()
    elif a.step == "update":
        update(a.go)
    elif a.step == "delete":
        delete(a.go)
    else:
        check()


if __name__ == "__main__":
    main()
