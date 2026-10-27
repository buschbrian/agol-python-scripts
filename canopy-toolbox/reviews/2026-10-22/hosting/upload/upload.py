r"""Upload the hosting packages to ArcGIS Online one item at a time, only when Brian says go (October 23, 2026).

    python reviews/2026-10-22/hosting/upload/upload.py list                 every item, its file and its upload status
    python reviews/2026-10-22/hosting/upload/upload.py ITEM                 dry run: checks the file, shows what would be sent
    python reviews/2026-10-22/hosting/upload/upload.py ITEM --go            upload and publish that one item

ArcGIS Pro Python (PYTHONNOUSERSITE=1), ArcGIS API for Python 2.4. Without --go nothing touches the portal. With --go the
script signs in (ArcGIS Pro's active portal by default, or --url and --username with a password prompt), refuses if an
item with the same title is already in your content or the log already records the item as published, adds the file to
the "Millcreek LiDAR 2023" folder and publishes it. It never shares, never deletes and never overwrites: every new item is
private to you. Retain each source package while its hosted layer depends on it (see README.md).
Each upload is logged to LOG (item IDs, URLs, file size and SHA-256).
"""
import argparse
import datetime
import getpass
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[4]))
from canopy.lidar_root import lidar_root  # noqa: E402

RUNS = lidar_root()/"2023-salt-lake-valley"/"runs"
LOG_DIR = RUNS/"hosting-uploads"
LOG = LOG_DIR/"uploads.json"
FOLDER = "Millcreek LiDAR 2023"
WARNING = ("Unvalidated LiDAR planning estimate from the 2023 Salt Lake Valley QL1 lidar (flown October-November 2023); "
           "not surveyed or field-verified data.")
DATUM = ("Coordinates: NAD83(2011) taken to WGS84 / Web Mercator with WGS_1984_(ITRF08)_To_NAD_1983_2011, the same as "
         "every layer in this set. Elevations NAVD88 (Geoid18) metres.")
TAGS = ["Millcreek", "lidar", "2023", "planning estimate"]
# Items with "datum": "utm" are not projected: their description says so instead of DATUM, and RECORDS_UTM names their records.
DATUM_UTM = ("Coordinates: NAD83(2011) / UTM zone 12N (EPSG 6341), metres, the lidar's own coordinate system; no datum "
             "transformation. For local scenes and a local ArcGIS Urban model in 6341. Elevations NAVD88 (Geoid18) metres.")
RECORDS = "Records: canopy-toolbox/reviews/2026-10-22 in buschbrian/agol-python-scripts (branch canopy/classification-refinement)."
RECORDS_UTM = ("Records: canopy-toolbox/reviews/2026-10-26/urban-utm in buschbrian/agol-python-scripts "
               "(branch claude/urban-utm-5e2a91).")

# In the upload order of reviews/2026-10-23/PUBLISHING.md. Each publishes as `expect` (the new service item's type).
ITEMS = {
    "features": {
        "file": RUNS/"hosting-features-20261023"/"features.gdb", "type": "File Geodatabase", "expect": "Feature Service",
        "title": "Millcreek buildings and canopy cover zones (2023 lidar), planning estimate",
        "snippet": "County building footprints with lidar roof heights, and canopy cover by ownership zone. " + WARNING,
        "description": "Two layers. buildings: 22,042 county footprints with roof-height statistics from the October 22 "
                       "consensus roofs (HEIGHT_P50_M, HEIGHT_P95_M and in feet; HEIGHT_STATUS flags low support). "
                       "canopy_cover_zones: 13 ownership zones with canopy cover (canopy at least 2 m as a share of "
                       "observed cells; city 25.59%).",
        "tags": ["buildings", "building height", "canopy", "tree canopy"],
        "readme": "hosting/feature-layers/README.md"},
    "slope": {
        "file": RUNS/"slope-tiles-20261022"/"millcreek_slope_classes.vtpk", "type": "Vector Tile Package",
        "expect": "Vector Tile Service",
        "title": "Millcreek slope classes 0.5 m (2023 lidar), planning estimate",
        "snippet": "Slope in six classes (under 10%, 10-15, 15-20, 20-25, 25-30, 30% and over) from the 0.5 m lidar "
                   "terrain, 4 m2 minimum mapping unit. " + WARNING,
        "description": "129,352 polygons from slope_percent (3 m neighbourhood). Patches under 4 m2 joined their largest "
                       "neighbour; the areas steeper than each threshold hold within 0.54 points of the raw raster. No "
                       "attributes in the tiles (legend from the style).",
        "tags": ["slope", "terrain", "hillside"], "readme": "slope-tiles/README.md"},
    "contours": {
        "file": RUNS/"vector-tiles-20261022"/"millcreek_contours.vtpk", "type": "Vector Tile Package",
        "expect": "Vector Tile Service",
        "title": "Millcreek 2 m contours (2023 lidar), planning estimate",
        "snippet": "2 m contours of the 0.5 m lidar bare-earth terrain, 10 m index lines heavier. " + WARNING,
        "description": "15,149 lines, 3,260 index contours. Index lines from 1:288,895 inward, 2 m lines from 1:18,056. "
                       "At 0.5 m the 2 m lines follow curbs and berms.",
        "tags": ["contours", "terrain", "elevation"], "readme": "hosting/vector-tiles/README.md"},
    "hillshade": {
        "file": RUNS/"tiles-20261023"/"millcreek_hillshade_20261023.tpkx", "type": "Compact Tile Package",
        "expect": "Map Service",
        "title": "Millcreek hillshade 0.5 m (2023 lidar), planning estimate",
        "snippet": "Unvalidated LiDAR planning estimate. Hillshade (sun 315/45) of the 0.5 m bare-earth terrain from the "
                   "2023 Salt Lake Valley QL1 lidar, for display only; not a surveyed surface.",
        "description": "PNG32 tiles, levels 0-18 on the ArcGIS Online scheme, transparent outside the city.",
        "tags": ["hillshade", "terrain"], "readme": "hosting/tiles/README.md"},
    "treetops": {
        "file": RUNS/"vector-tiles-20261022"/"millcreek_treetops.vtpk", "type": "Vector Tile Package",
        "expect": "Vector Tile Service",
        "title": "Millcreek treetops (2023 lidar), planning estimate",
        "snippet": "527,140 lidar treetops at least 2 m tall, by height class. Detections, not a tree census. " + WARNING,
        "description": "From 1:18,056 inward. 32,986 treetops are flagged SUSPECT by geometric checks and not yet "
                       "reviewed. No attributes in the tiles.",
        "tags": ["trees", "treetops", "urban forest", "canopy"], "readme": "hosting/vector-tiles/README.md"},
    "crowns": {
        "file": RUNS/"vector-tiles-20261022"/"millcreek_crowns.vtpk", "type": "Vector Tile Package",
        "expect": "Vector Tile Service",
        "title": "Millcreek tree crowns (2023 lidar), planning estimate",
        "snippet": "400,063 estimated tree crowns, by treetop height class. Estimated canopy regions, not surveyed "
                   "crowns. " + WARNING,
        "description": "From 1:18,056 inward. A broad tree can hold several crowns and a clump of small trees can form "
                       "one. No attributes in the tiles.",
        "tags": ["trees", "crowns", "urban forest", "canopy"], "readme": "hosting/vector-tiles/README.md"},
    "buildings3d": {
        "file": RUNS/"scene-layers-20261022"/"buildings_lod12.slpk", "type": "Scene Package", "expect": "Scene Service",
        "title": "Millcreek 3D buildings LOD1.2 (2023 lidar), planning estimate",
        "snippet": "21,561 county footprints extruded from the lowest ground to the median lidar roof. " + WARNING,
        "description": "Flat blocks with the footprints' roof-height statistics for pop-ups. Heights NAVD88; the "
                       "package is labelled EGM96 but its heights were left in NAVD88 (see the scene-layers README).",
        "tags": ["buildings", "3D", "scene"], "readme": "hosting/scene-layers/README.md"},
    # October 24: the candidate to replace buildings3d (its LOD1.2 blocks include 598 that sit on the ground). A new item, never
    # an overwrite; the web scene is repointed afterwards. Built by reviews/2026-10-23/lod2-check/build_v2_package.py.
    "buildings3d_v2": {
        "file": RUNS/"roofer-city-v2-20261024"/"v2"/"buildings_hybrid_v2.slpk", "type": "Scene Package", "expect": "Scene Service",
        "title": "Millcreek 3D buildings with roof forms (2023 lidar), planning estimate",
        "snippet": "Unvalidated planning estimate: 21,561 buildings from 2023 lidar, with roofer LoD 2.2 roofs and "
                   "Esri LOD2.0/LOD1.2 fallbacks. Roof forms and heights are modelled, not surveyed or field-verified.",
        "description": "The LEVEL field says which model each building uses, and the roof attributes (planes, slopes, "
                       "azimuth, ridge and eave height, south-facing area) apply where LEVEL is roofer LoD2.2. Heights NAVD88; "
                       "the package is labelled EGM96 but its heights were left in NAVD88 (see the scene-layers README).",
        "tags": ["buildings", "3D", "scene", "roof forms"], "readme": "../2026-10-23/lod2-check/README.md"},
    # October 26: the LiDAR-first rebuild (Brian: the LiDAR is the truth for whole buildings). Roofer LoD2.2 on 23,327
    # building outlines drawn from the 2023 LiDAR alone, plus the v2 model where trees hide a county building. Metres kept
    # and feet added beside them in the same layer. A new item; repointing the public scene is a separate, approved step.
    # Built by reviews/2026-10-26/lidar-footprints/lidar_first_city.py.
    "buildings3d_lidar_first": {
        "file": RUNS/"lidar-footprints-20261026"/"roofer-city"/"buildings_lidar_first.slpk", "type": "Scene Package",
        "expect": "Scene Service",
        "title": "Millcreek 3D buildings from LiDAR outlines (2023 lidar), planning estimate",
        "snippet": "Unvalidated planning estimate: buildings outlined and modelled from the 2023 lidar alone (roofer LoD 2.2), "
                   "with county footprints only where trees hide a roof. Heights and areas in metres and feet.",
        "description": "OUTLINE_SOURCE says whether a building's outline comes from the LiDAR or, under trees, from the county "
                       "footprint; COMPARE_CLASS and COUNTY_IDS say how the LiDAR outline compares with the county layer. "
                       "Every metric field has a feet twin (_FT, _SQFT, _CUFT). LiDAR outlines follow the roof edge (eaves), "
                       "a median 0.39 m outside the county wall lines. Heights NAVD88 (see the scene-layers README).",
        "tags": ["buildings", "3D", "scene", "roof forms", "lidar outlines"],
        "readme": "../2026-10-26/lidar-footprints/README.md"},
    # October 26: copies in NAD83(2011) UTM 12N (6341) for a local ArcGIS Urban model, which needs its existing buildings and
    # elevation in the model's own coordinate system (the items above are WGS84 / Web Mercator for global scenes). Brian
    # approved them org-only; sharing and delete protection are reviews/2026-10-26/urban-utm/share_org.py's. Built by
    # reviews/2026-10-26/urban-utm/urban_utm.py.
    "urban_buildings": {
        "file": RUNS/"urban-utm-20261026"/"scene"/"buildings_three_way_utm.slpk", "type": "Scene Package",
        "expect": "Scene Service",
        "title": "Millcreek 3D buildings for ArcGIS Urban, UTM 12N (2023 lidar), planning estimate",
        "snippet": "Unvalidated planning estimate: the 21,561 three-way hybrid buildings (roofer LoD 2.2, Esri fallbacks) in "
                   "NAD83(2011) UTM 12N for a local ArcGIS Urban model, with an estimated floor count.",
        "description": "The same buildings as the public 3D buildings layer, packaged in UTM 12N instead of WGS84. FLOORS is "
                       "HEIGHT_P95_M divided by 3.5 m, rounded, at least 1: an estimate for Urban's Convert existing "
                       "buildings, not a count of storeys.",
        "tags": ["buildings", "3D", "scene", "ArcGIS Urban", "UTM"], "datum": "utm",
        "readme": "../2026-10-26/urban-utm/README.md"},
    "urban_footprints": {
        "file": RUNS/"urban-utm-20261026"/"footprints"/"urban_footprints.gdb", "type": "File Geodatabase",
        "expect": "Feature Service",
        "title": "Millcreek building footprints for ArcGIS Urban, UTM 12N (2023 lidar), planning estimate",
        "snippet": "Unvalidated planning estimate: one footprint per 3D building (21,561), with roof height, model level and "
                   "an estimated floor count, in NAD83(2011) UTM 12N for a local ArcGIS Urban model.",
        "description": "Footprints of the 3D buildings for ArcGIS Urban (Multipatch Footprint of each building, keyed by "
                       "FP_ID). FLOORS is HEIGHT_P95_M divided by 3.5 m, rounded, at least 1: an estimate, not a count of "
                       "storeys. No owner or address fields.",
        "tags": ["buildings", "building footprints", "ArcGIS Urban", "UTM"], "datum": "utm",
        "publish_parameters": {"name": "Millcreek_building_footprints_Urban_UTM12N", "targetSR": {"wkid": 6341},
                               "maxRecordCount": 2000},
        "readme": "../2026-10-26/urban-utm/README.md"},
    "urban_terrain": {
        "file": RUNS/"urban-utm-20261026"/"millcreek_terrain_utm_20261026.tpkx", "type": "Compact Tile Package",
        "expect": "Image Service",
        "title": "Millcreek bare-earth terrain for ArcGIS Urban, UTM 12N 0.5 m (2023 lidar), planning estimate",
        "snippet": "Unvalidated LiDAR planning estimate. Bare-earth elevation in metres, NAVD88, at 0.5 m on a NAD83(2011) UTM "
                   "12N tiling scheme, as the elevation layer of a local ArcGIS Urban model. Not a surveyed surface.",
        "description": "Elevation tiles (LERC 0.01 m), levels 0-14 halving from 8,192 m to 0.5 m pixels, on the UTM 12N "
                       "tiling scheme in the records. Urban needs its basemap on the same tiling scheme.",
        "tags": ["elevation", "ground", "terrain", "DEM", "ArcGIS Urban", "UTM"], "datum": "utm",
        "readme": "../2026-10-26/urban-utm/README.md"},
    # October 27: the same Urban buildings with FLOORS in WGS84, for a global (Web Mercator) Urban model alongside the local
    # one. Packaged as the public layer was (labelled EGM96, heights NAVD88). Brian approved org-only. Built by
    # reviews/2026-10-26/urban-utm/urban_utm.py slpk --wgs84.
    "urban_buildings_wgs84": {
        "file": RUNS/"urban-utm-20261026"/"scene-wgs84"/"buildings_three_way_wgs84.slpk", "type": "Scene Package",
        "expect": "Scene Service",
        "title": "Millcreek 3D buildings for ArcGIS Urban, Web Mercator (2023 lidar), planning estimate",
        "snippet": "Unvalidated planning estimate: the 21,561 three-way hybrid buildings (roofer LoD 2.2, Esri fallbacks) "
                   "for a global (Web Mercator) ArcGIS Urban model, with an estimated floor count.",
        "description": "The same buildings and FLOORS as the UTM 12N Urban layer, packaged in WGS84 for global scenes. "
                       "FLOORS is HEIGHT_P95_M divided by 3.5 m, rounded, at least 1: an estimate for Urban's Convert "
                       "existing buildings, not a count of storeys. Heights NAVD88; the package is labelled EGM96 as the "
                       "public 3D buildings layer is.",
        "tags": ["buildings", "3D", "scene", "ArcGIS Urban"], "records": RECORDS_UTM,
        "readme": "../2026-10-26/urban-utm/README.md"},
    # October 27: the basemap a local Urban model is created from, on the terrain's tiling scheme (Brian approved org-only).
    # Built by reviews/2026-10-26/urban-utm/basemap.py.
    "urban_basemap": {
        "file": RUNS/"urban-utm-20261026"/"basemap"/"millcreek_basemap_utm_20261027.tpkx", "type": "Compact Tile Package",
        "expect": "Map Service",
        "title": "Millcreek light basemap for ArcGIS Urban, UTM 12N (2023 lidar hillshade)",
        "snippet": "Light reference basemap in NAD83(2011) UTM 12N on the Millcreek Urban terrain's tiling scheme, so a local "
                   "ArcGIS Urban model can be created: lidar hillshade, parcel lines, street names, city boundary.",
        "description": "PNG tiles, levels 0-14 halving from 8,192 m to 0.5 m pixels, on exactly the tiling scheme of the "
                       "Millcreek bare-earth terrain for ArcGIS Urban (Urban requires the basemap and elevation to share "
                       "it). Hillshade of the unmasked 2023 lidar terrain; parcels, road centerlines and the municipal "
                       "boundary from Millcreek's hosted layers, projected from State Plane with no datum transformation. "
                       "For orientation only: not a survey or a parcel record.",
        "tags": ["basemap", "hillshade", "ArcGIS Urban", "UTM"], "datum": "utm",
        "credits": "Millcreek GIS; parcels, road centerlines and boundary: Millcreek; hillshade: 2023 Salt Lake Valley "
                   "QL1 lidar (USGS 3DEP).",
        "readme": "../2026-10-26/urban-utm/README.md"},
    "terrain": {
        "file": RUNS/"tiles-20261023"/"millcreek_terrain_20261023.tpkx", "type": "Compact Tile Package",
        "expect": "Image Service",
        "title": "Millcreek bare-earth terrain 0.5 m (2023 lidar), planning estimate",
        "snippet": "Unvalidated LiDAR planning estimate. Bare-earth elevation in metres, NAVD88 (Geoid18), interpolated at "
                   "0.5 m from class-2 ground returns of the 2023 Salt Lake Valley QL1 lidar; LERC error 0.01 m. For 3D "
                   "ground; not a surveyed surface.",
        "description": "Elevation tiles (LERC 0.01 m), levels 0-18 on the ArcGIS Online elevation scheme, covering the "
                       "whole lidar mosaic. Add to a web scene's Ground above World Elevation.",
        "tags": ["elevation", "ground", "terrain", "DEM"], "readme": "hosting/tiles/README.md"},
}


def sha256(path):
    """SHA-256 of a file, or of a folder's files in name order (a file geodatabase)."""
    h = hashlib.sha256()
    files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
    for f in files:
        if path.is_dir():
            h.update(f.relative_to(path).as_posix().encode())
        with open(f, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
    return h.hexdigest()


def size(path):
    return path.stat().st_size if path.is_file() else sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def read_log():
    return json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else {}


def describe(key):
    spec = ITEMS[key]
    path = Path(spec["file"])
    if not path.exists():
        raise SystemExit(f"{key}: {path} does not exist")
    if spec["type"] == "File Geodatabase" and any(path.glob("*.lock")):
        raise SystemExit(f"{key}: {path} has lock files; close ArcGIS Pro's hold on it first")
    return {"item": key, "file": str(path), "bytes": size(path), "sha256": sha256(path), "item_type": spec["type"],
            "expect": spec["expect"], "title": spec["title"], "folder": FOLDER, "tags": TAGS + spec["tags"],
            "snippet": spec["snippet"], "coordinates": DATUM_UTM if spec.get("datum") == "utm" else DATUM,
            "publish_parameters": spec.get("publish_parameters"), "sharing": "private (not shared)"}


def properties(key):
    from arcgis.gis import ItemProperties
    spec = ITEMS[key]
    utm = spec.get("datum") == "utm"
    return ItemProperties(title=spec["title"], item_type=spec["type"], tags=TAGS + spec["tags"], snippet=spec["snippet"],
                          description="<p>" + spec["description"] + "</p><p>" + WARNING + "</p><p>"
                                      + (DATUM_UTM if utm else DATUM) + "</p><p>"
                                      + spec.get("records", RECORDS_UTM if utm else RECORDS) + " See " + spec["readme"]
                                      + ".</p>",
                          access_information=spec.get("credits",
                                                      "Millcreek GIS; lidar: 2023 Salt Lake Valley QL1 (USGS 3DEP)."),
                          license_info=WARNING)


def upload_file(key):
    """The file to send: a file geodatabase goes as a zip of the .gdb folder (its lock files left out)."""
    path = Path(ITEMS[key]["file"])
    if path.is_file():
        return path
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    target = LOG_DIR/(path.name + ".zip")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(path.rglob("*")):
            if f.is_file() and not f.name.endswith(".lock"):
                z.write(f, Path(path.name)/f.relative_to(path))
    return target


def trace_unverified_https():
    """Log where any HTTPS request without certificate verification comes from. The hillshade publish (October 23) made
    four to www.arcgis.com from inside the ArcGIS API although the session verifies certificates; this records the
    call stack of each so the source can be found and reported."""
    import traceback
    import warnings
    shown = warnings.showwarning

    def show(message, category, filename, lineno, file=None, line=None):
        if category.__name__ == "InsecureRequestWarning":
            stack = "".join(traceback.format_stack(limit=14)[:-1])
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(LOG_DIR/"unverified-https.log", "a", encoding="utf-8") as fh:
                fh.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {message}\n{stack}\n")
            print("WARNING: an unverified HTTPS request was made; call stack in", LOG_DIR/"unverified-https.log")
        else:
            shown(message, category, filename, lineno, file, line)
    warnings.showwarning = show


def sign_in(args):
    from arcgis.gis import GIS
    if args.url:
        password = getpass.getpass(f"Password for {args.username}: ")
        return GIS(args.url, args.username, password)
    return GIS("pro")


def go(key, args):
    from arcgis.gis import GIS  # noqa: F401  (fail before signing in if the API is missing)
    trace_unverified_https()
    record = describe(key)
    log = read_log()
    if log.get(key, {}).get("published_id") and not args.again:
        raise SystemExit(f"{key}: the log already records it as published ({log[key]['published_id']}); "
                         "pass --again only if that layer was deleted")
    gis = sign_in(args)
    me = gis.users.me
    print(f"Signed in to {gis.url} as {me.username}")
    title = ITEMS[key]["title"]
    existing = [i for i in gis.content.search(f'title:"{title}" AND owner:{me.username}', max_items=50)
                if i.title == title]
    if existing and not args.allow_duplicate:
        raise SystemExit(f"{key}: already in your content: " + ", ".join(f"{i.type} {i.id}" for i in existing))
    folder = gis.content.folders.get(FOLDER) or gis.content.folders.create(FOLDER)
    path = upload_file(key)
    print(f"Adding {path} ({size(path):,} bytes) to '{FOLDER}' ...", flush=True)
    package = folder.add(item_properties=properties(key), file=str(path)).result()
    print(f"Added {package.type} {package.id}; publishing ...", flush=True)
    name = re.sub(r"[\W_]+", "_", title).strip("_")[:80]
    if ITEMS[key]["type"] == "Compact Tile Package":
        layer = package.publish(publish_parameters={"name": name, "maxRecordCount": 2000}, build_initial_cache=True)
    elif "publish_parameters" in ITEMS[key]:
        layer = package.publish(publish_parameters=ITEMS[key]["publish_parameters"])
    else:
        layer = package.publish()
    entry = dict(record, uploaded=datetime.datetime.now().isoformat(timespec="seconds"), portal=gis.url,
                 owner=me.username, sent_file=str(path), package_id=package.id, published_id=layer.id,
                 published_type=layer.type, published_url=layer.url, item_page=layer.homepage,
                 type_as_expected=layer.type == ITEMS[key]["expect"])
    log[key] = entry
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(log, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: entry[k] for k in ("package_id", "published_id", "published_type", "item_page")}, indent=1))
    if not entry["type_as_expected"]:
        print(f"NOTE: expected a {ITEMS[key]['expect']}, got {layer.type}. Check the item before using it.")
    print("Not shared. Next: open the item page and check it draws (README.md lists what to look for). "
          f"Retain source package {package.id} while the hosted layer depends on it.")


def show_list():
    log = read_log()
    for key, spec in ITEMS.items():
        path = Path(spec["file"])
        status = log.get(key, {}).get("published_id")
        state = f"published {status}" if status else "not uploaded"
        exists = f"{size(path)/1e6:,.1f} MB" if path.exists() else "MISSING"
        print(f"{key:12} {exists:>10}  {state:40}  {path}")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("item", choices=["list"] + list(ITEMS))
    p.add_argument("--go", action="store_true", help="actually upload and publish this one item")
    p.add_argument("--url", help="portal URL instead of ArcGIS Pro's active portal (with --username)")
    p.add_argument("--username")
    p.add_argument("--allow-duplicate", action="store_true", help="upload although an item with this title exists")
    p.add_argument("--again", action="store_true", help="upload although the log records this item as published")
    a = p.parse_args(argv)
    if bool(a.url) != bool(a.username):
        p.error("--url and --username go together")
    if a.item == "list":
        show_list()
    elif a.go:
        go(a.item, a)
    else:
        print(json.dumps(describe(a.item), indent=1))
        print("Dry run: nothing was sent. Add --go to upload and publish this item.")


if __name__ == "__main__":
    main()
