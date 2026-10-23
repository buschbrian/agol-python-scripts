r"""Public apps for the Millcreek LiDAR layers (October 23, 2026): three Sidebar Instant Apps on the web maps, a 3D Viewer
Instant App on the scene, and an ArcGIS StoryMap landing page that links them. All carry the planning-estimate warning.

    python reviews/2026-10-23/agol-apps/make_apps.py plan            what would be created (nothing is sent)
    python reviews/2026-10-23/agol-apps/make_apps.py create --go     create the five items, private, in the lidar folder
    python reviews/2026-10-23/agol-apps/make_apps.py check           read each back: private or public, settings, links

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
FOLDER = "Millcreek LiDAR 2023"
TAGS = ["Millcreek", "lidar", "2023", "planning estimate"]
TEMPLATES = {"sidebar": ("f6a143fb90c44d7b860f623f1a23c322", "sidebar", "instant_app_sidebar"),
             "3dviewer": ("888910da7fdc4b11ac32825ad2d87816", "3dviewer", "af151b76c68941d48f41b3031bf1110e")}
WARNING = ("<p><strong>Planning estimates.</strong> Everything here comes from the 2023 Salt Lake Valley QL1 lidar "
           "(flown October-November 2023) and the City of Millcreek's processing of it. These are unvalidated planning "
           "estimates, not surveyed or field-verified data. Do not use them for engineering, legal or property "
           "decisions.</p>")
WARNING_TEXT = ("Unvalidated planning estimates from the 2023 Salt Lake Valley QL1 lidar; not surveyed or field-verified "
                "data.")

APPS = {
    "terrain": {
        "template": "sidebar", "map": "177bfc592415451585ba72ab9207b3c6", "title": "Millcreek Terrain and Slope",
        "what": "Slope in six classes, 2 m contours and a hillshade, from the 0.5 m bare-earth lidar terrain. Zoom in to "
                "street scale for the contours and the detail of the slope classes.",
        "tags": ["slope", "terrain", "contours", "hillshade"]},
    "canopy": {
        "template": "sidebar", "map": "e5efa719691045849108553394448f35", "title": "Millcreek Tree Canopy",
        "what": "Tree canopy cover by ownership zone (25.59% of the city), estimated tree crowns and lidar treetops by "
                "height. Crowns and treetops appear as you zoom in. Treetops are lidar detections, not a tree census.",
        "tags": ["tree canopy", "urban forest", "trees"]},
    "buildings": {
        "template": "sidebar", "map": "504554bd5a9545559db06aa6098e8e49", "title": "Millcreek Building Heights",
        "what": "Salt Lake County building footprints coloured by their median roof height from the lidar. Select a "
                "building for its heights in metres and feet and how much of its roof the lidar saw.",
        "tags": ["buildings", "building height"]},
    "in3d": {
        "template": "3dviewer", "map": "5b5bdf4a63c9466fad5884039aa7357f", "title": "Millcreek in 3D",
        "what": "Millcreek's buildings standing on the city's own 0.5 m lidar terrain, with the hillshade draped over the "
                "ground. Use the slides for a tour, or drag to look around.",
        "tags": ["3D", "buildings", "terrain", "scene"]},
}


def splash(spec):
    return (f"<p>{spec['what']}</p>" + WARNING +
            "<p>More about the data, how it was made and its limits is in each layer's description.</p>")


def values(spec):
    common = {"splash": True, "splashTitle": spec["title"], "splashContent": splash(spec), "splashButtonText": "Open",
              "theme": "light", "home": True, "fullScreen": True, "share": True, "measure": True, "legend": True,
              "search": True, "popupHover": False}
    if spec["template"] == "sidebar":
        return {**common, "webmap": spec["map"], "title": spec["title"], "header": True, "titleLink": "",
                "splashOnStart": True, "legendOpenAtStart": True, "searchOpenAtStart": False, "mapZoom": True,
                "zoomControls": True, "scalebar": True, "locate": False, "basemapToggle": False, "exportToPDF": False,
                "keyboardShortcuts": True, "applyCustomTheme": False, "fullAppSettings": False,
                "mapA11yDesc": f"{spec['title']}: {spec['what']}"}
    return {**common, "type": "webscene", "webscene": spec["map"], "slides": True, "layerList": True,
            "layerListOpenAtStart": False, "daylight": True, "daylightOpenAtStart": False, "elevationProfile": False,
            "lineOfSight": False, "slice": False, "info": False, "customHeader": False, "applySharedTheme": False,
            "exportToPDF": False, "fullAppSettings": False}


def description(spec):
    return (f"<p>{spec['what']}</p>" + WARNING +
            f"<p>Built on the {spec['template'] == 'sidebar' and 'web map' or 'web scene'} "
            f"<a href='https://www.arcgis.com/home/item.html?id={spec['map']}'>{spec['map']}</a>. Records: "
            "canopy-toolbox/reviews/2026-10-23 in the City's agol-python-scripts repository.</p>")


def read_created():
    return json.loads(CREATED.read_text(encoding="utf-8")) if CREATED.exists() else {}


def plan():
    for key, spec in APPS.items():
        print(json.dumps({"key": key, "title": spec["title"], "template": TEMPLATES[spec["template"]][0],
                          "map": spec["map"], "values": values(spec)}, indent=1)[:1500])
    print("Landing page: an ArcGIS StoryMap, 'Millcreek LiDAR 2023', linking the four apps, private.")


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
        template_id, path, source_kw = TEMPLATES[spec["template"]]
        keywords = ["Configurable", "configurableApp", "instantApp", "JavaScript", "Map", "Mapping Site", "Online Map",
                    "Web Map", f"sourceId#{source_kw}"] + (["3Dscene"] if spec["template"] == "3dviewer" else [])
        data = {"source": template_id, "folderId": folder.properties["id"], "values": values(spec)}
        props = ItemProperties(title=spec["title"], item_type="Web Mapping Application", tags=TAGS + spec["tags"],
                               snippet=f"{spec['what'].split('. ')[0]}. {WARNING_TEXT}"[:250],
                               description=description(spec), type_keywords=keywords, license_info=WARNING_TEXT,
                               access_information="City of Millcreek GIS; 2023 Salt Lake Valley QL1 lidar (USGS 3DEP).")
        item = folder.add(item_properties=props, text=json.dumps(data)).result()
        url = f"{base}/apps/instant/{path}/index.html?appid={item.id}"
        item.update(item_properties={"url": url})
        created[key] = {"id": item.id, "url": url, "title": spec["title"]}
        CREATED.write_text(json.dumps(created, indent=1) + "\n", encoding="utf-8")
        print(f"{key}: {item.id} {url}")
    if "landing" not in created:
        created["landing"] = landing(gis, folder, created)
        CREATED.write_text(json.dumps(created, indent=1) + "\n", encoding="utf-8")
        print(f"landing: {created['landing']['id']} {created['landing']['url']}")


def landing(gis, folder, created):
    from arcgis.apps.storymap import StoryMap, Text, Button, Separator, TextStyles
    story = StoryMap(gis=gis)
    story.add(Text("Millcreek's 2023 lidar, mapped", style=TextStyles.HEADING))
    story.add(Text("In late 2023 a laser survey from the air measured Millcreek's ground, trees and buildings in "
                   "detail: more than a billion points across the city. These maps turn that survey into slope and "
                   "terrain, tree canopy and building heights, at half a metre on the ground."))
    story.add(Text(WARNING.replace("<p>", "").replace("</p>", "")))
    order = (("terrain", "Slope, contours and the shape of the land, from the valley floor to the east bench."),
             ("canopy", "How much of the city is under tree canopy, by ownership, with crowns and treetops."),
             ("buildings", "How tall each building is, from its roof in the lidar."),
             ("in3d", "The whole city in 3D, buildings standing on the lidar terrain."))
    for key, line in order:
        story.add(Separator())
        story.add(Text(created[key]["title"], style=TextStyles.SUBHEADING))
        story.add(Text(line))
        story.add(Button(link=created[key]["url"], text=f"Open {created[key]['title']}"))
    story.add(Separator())
    story.add(Text("About the data", style=TextStyles.SUBHEADING))
    story.add(Text("Each layer's item page describes how it was made, its fields and its limits. Coordinates use "
                   "NAD83(2011) taken to WGS84 with the ITRF08 transformation; elevations are NAVD88 metres. Lidar: "
                   "2023 Salt Lake Valley QL1 (USGS 3DEP). Building footprints and parcels: Salt Lake County."))
    try:
        item = story.save(title="Millcreek LiDAR 2023", tags=TAGS + ["story"], access="private", publish=True)
    except AttributeError:
        # With GIS("pro") the API's last publish step asks for a token the Pro sign-in does not expose; the story is
        # already saved and published by then (October 23), so take the item it made.
        item = next(i for i in gis.content.search(f'title:"Millcreek LiDAR 2023" AND owner:{gis.users.me.username} '
                                                  'AND type:"StoryMap"', max_items=5))
    try:
        item.move(folder)
    except Exception as error:  # moving is a convenience; the story works from any folder
        print("landing page left in the root folder:", error)
    item.update(item_properties={"snippet": "Maps of Millcreek's 2023 lidar: terrain and slope, tree canopy, building "
                                            "heights and the city in 3D. " + WARNING_TEXT})
    return {"id": item.id, "url": f"https://storymaps.arcgis.com/stories/{item.id}", "title": item.title}


def check():
    from arcgis.gis import GIS
    gis = GIS("pro")
    for key, rec in read_created().items():
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
    p.add_argument("step", choices=("plan", "create", "check"))
    p.add_argument("--go", action="store_true")
    a = p.parse_args(argv)
    if a.step == "plan" or (a.step == "create" and not a.go):
        plan()
    elif a.step == "create":
        create()
    else:
        check()


if __name__ == "__main__":
    main()
