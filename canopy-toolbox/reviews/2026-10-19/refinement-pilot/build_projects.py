"""Create separate diagnostic and blind-reference ArcGIS Pro projects."""
import json
from pathlib import Path
import sys

import arcpy

TOOLBOX = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(TOOLBOX))
from canopy import common
from canopy.lidar_root import live


def add_group(map_,group,layer):
    map_.addLayerToGroup(group,layer,"BOTTOM")
    map_.removeLayer(layer)


def main(root):
    root = Path(root).resolve()
    state = json.loads((root/"experiment.json").read_text(encoding="utf-8"))
    assert state["status"].startswith("complete")
    source = Path("D:/lidar/2023-salt-lake-valley/runs/pilot-2026-09-29/validation/review/validation_review.aprx")
    project = arcpy.mp.ArcGISProject(str(source))
    for map_ in project.listMaps():
        project.deleteItem(map_)
    for site in state["sites"]:
        map_ = project.createMap(site["name"],"MAP")
        map_.spatialReference = arcpy.SpatialReference(6341)
        for variant in ("baseline","local_roofs","fractal_unanimous"):
            result = json.loads((root/"products"/site["name"]/variant/"result.json").read_text(encoding="utf-8"))
            group = map_.createGroupLayer(variant)
            group.visible = variant == "baseline"
            chm = map_.addDataFromPath(result["rasters"]["chm"])
            chm.name = "CHM in metres"
            sym = chm.symbology
            sym.updateColorizer("RasterClassifyColorizer")
            sym.colorizer.breakCount = 6
            sym.colorizer.classificationMethod = "ManualInterval"
            colours = [[220,220,220,100],[189,221,142,100],[120,198,121,100],
                       [49,163,84,100],[0,104,55,100],[0,60,48,100]]
            for band,upper,colour in zip(sym.colorizer.classBreaks,(2,6,12,20,40,80),colours):
                band.upperBound = upper
                band.label = f"Height <= {upper} m"
                band.color = {"RGB":colour}
            chm.symbology = sym
            add_group(map_,group,chm)
            tops = map_.addDataFromPath(result["treetops"])
            tops.name = "Unverified candidates in development domain"
            tops.definitionQuery = "DEVELOPMENT = 1"
            sym = tops.symbology
            sym.renderer.symbol.color = {"RGB":[255,60,20,100]}
            sym.renderer.symbol.size = 4
            tops.symbology = sym
            add_group(map_,group,tops)
            points = map_.addDataFromPath(str(root/variant/"prepared.lasd"))
            points.name = "Classified point cloud for diagnostic cross sections"
            points.visible = False
            add_group(map_,group,points)
        a,b,c,d = site["core"]
        map_.defaultCamera.setExtent(arcpy.Extent(a-15,b-15,c+15,d+15))
    output = root/"classification_comparison.aprx"
    project.saveACopy(str(output))
    independent = arcpy.mp.ArcGISProject(str(source))
    review = root/"independent-review"
    rebound = []
    for map_ in independent.listMaps():
        for layer in map_.listLayers():
            if not layer.supports("CONNECTIONPROPERTIES"):
                continue
            connection = layer.connectionProperties
            database = connection.get("connection_info",{}).get("database","")
            if database:
                update = json.loads(json.dumps(connection))
                update["connection_info"]["database"] = str(review/"reference.gdb") if "reference.gdb" in database else str(live(database))
                layer.updateConnectionProperties(connection,update,validate=True)
            if "reference.gdb" in database:
                layer.visible = True
                rebound.append(layer.name)
            elif not layer.isGroupLayer and not layer.isBasemapLayer:
                layer.visible = False
    blind = review/"blind_reference_review.aprx"
    independent.saveACopy(str(blind))
    assert len(rebound) >= 4
    check = arcpy.mp.ArcGISProject(str(output))
    broken = [(m.name,l.name) for m in check.listMaps() for l in m.listLayers() if l.isBroken]
    check_blind = arcpy.mp.ArcGISProject(str(blind))
    broken_reference = [(m.name,l.name) for m in check_blind.listMaps() for l in m.listLayers()
                        if l.supports("DATASOURCE") and "reference.gdb" in l.dataSource and l.isBroken]
    assert not broken and not broken_reference,(broken,broken_reference)
    common.write_json(root/"projects.json",{"status":"passed","comparison_project":str(output),
        "blind_review_project":str(blind),"rebound_review_layers":rebound,"broken_comparison_layers":broken,
        "broken_reference_layers":broken_reference,"comparison_chm_breaks_m":[2,6,12,20,40,80],
        "review_instructions":"Use the blind project and CSV for independent answers. Diagnostic comparisons must remain closed while labelling. Inspect elevation-coloured lidar cross sections and verify imagery date/alignment; never infer reference truth from class colours."})
    print(str(output));print(str(blind))


if __name__=="__main__":main(sys.argv[1])
