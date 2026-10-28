r"""An ArcGIS Pro project to look at the three scene layer packages (October 24, 2026).

    python reviews/2026-10-23/lod2-check/viewer/build_pro_project.py OUT_DIR web/bookmarks.json

ArcGIS Pro Python (PYTHONNOUSERSITE=1). Read-only on the packages; writes OUT_DIR\\Millcreek_buildings_3D.aprx from a copy of the
install's Blank.aprx (as the vector tile packages were made). Three global scenes, each with one package, the same bookmarks in
each, so linking two views (View > Link Views) gives the side-by-side of the web viewer:
  Esri LOD2.0 hybrid   buildings_hybrid.slpk        (scene-layers-hybrid-20261023)
  roofer only          buildings_roofer_only.slpk   (roofer-city-20261024)
  three-way hybrid     buildings_three_way.slpk     (roofer-city-20261024)
Pro's scene ground is its default online elevation (it needs a connection); the packages' heights are NAVD88 metres.
The bookmarks are made from a map frame's camera on a throwaway layout: looking at the building from 1.6 x its size away
(plus 60 m), 32 degrees below horizontal, heading from the FP_ID as in the web viewer. Nothing is uploaded.
"""
import json
import math
from pathlib import Path
import shutil
import sys

RUNS = Path(r"H:\lidar\2023-salt-lake-valley\runs")
PACKAGES = [("Esri LOD2.0 hybrid", RUNS/"scene-layers-hybrid-20261023"/"buildings_hybrid.slpk"),
            ("roofer only", RUNS/"roofer-city-20261024"/"buildings_roofer_only.slpk"),
            ("three-way hybrid", RUNS/"roofer-city-20261024"/"buildings_three_way.slpk")]


def main(out_dir, bookmarks_json):
    import arcpy
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    template = Path(arcpy.GetInstallInfo()["InstallDir"])/r"Resources\ArcToolBox\Services\routingservices\data\Blank.aprx"
    path = out/"Millcreek_buildings_3D.aprx"
    shutil.copy(template, path)
    aprx = arcpy.mp.ArcGISProject(str(path))
    for m in list(aprx.listMaps()):
        aprx.deleteItem(m)
    bookmarks = json.loads(Path(bookmarks_json).read_text(encoding="utf-8"))["bookmarks"]
    report = {"project": str(path), "scenes": [], "bookmarks": len(bookmarks), "bookmark_errors": []}
    for title, slpk in PACKAGES:
        scene = aprx.createMap(title, "SCENE")
        scene.addDataFromPath(str(slpk))
        layout = aprx.createLayout(11, 8.5, "INCH", f"tmp {title}")
        frame = layout.createMapFrame(arcpy.Extent(0.25, 0.25, 10.75, 8.25), scene, "frame")
        made = 0
        for b in bookmarks:
            try:
                heading = (b["fp_id"]*37) % 360
                dist = 1.6*b["size_m"]+60
                horizontal = dist*math.cos(math.radians(32))
                cam = frame.camera
                cam.X = b["lon"]-horizontal*math.sin(math.radians(heading))/(111320*math.cos(math.radians(b["lat"])))
                cam.Y = b["lat"]-horizontal*math.cos(math.radians(heading))/110574
                cam.Z = b["ground_z"]+dist*math.sin(math.radians(32))+5
                cam.heading, cam.pitch, cam.roll = heading, -32, 0
                frame.camera = cam
                frame.createBookmark(f"{b['id']} {b['title']}", f"{b['type']}, {b['footprint_m2']} m2; roofer {b['roofer']['verdict']} "
                                     f"p95 {b['roofer']['p95_m']} m; Esri LOD2.0 {b['esri_lod20']['verdict']} p95 {b['esri_lod20']['p95_m']} m")
                made += 1
            except Exception as e:      # reported, not hidden
                report["bookmark_errors"].append(f"{title} {b['id']}: {e}")
        aprx.deleteItem(layout)
        report["scenes"].append({"name": title, "layers": [l.name for l in scene.listLayers()],
                                 "bookmarks": [bm.name for bm in scene.listBookmarks()][:3], "bookmark_count": len(scene.listBookmarks()),
                                 "made": made})
    aprx.save()
    (out/"project.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
