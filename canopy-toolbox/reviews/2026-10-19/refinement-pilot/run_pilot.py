"""Frozen-parameter development comparison: baseline, local roofs, FRACTAL consensus.

Use Pro Python, PYTHONNOUSERSITE=1, CANOPY_LIDAR_ROOT=D:\\lidar.
No inference, model training, label writes, or city-product replacement.
"""
import argparse
from collections import Counter
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import arcpy
import laspy
import numpy as np
import shapely
from scipy import ndimage

TOOLBOX = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(TOOLBOX))
from canopy import bands, common, fractal_compare, las_records, licensing, rasters, roofs, training_review, treetops
from canopy.training_review import verify_only_classes_changed

LIDAR = Path("D:/lidar/2023-salt-lake-valley")
CITY = LIDAR/"runs/city-count-20261008"
PRODUCTS = LIDAR/"runs/millcreek-products-20261019"
PILOT = LIDAR/"runs/pilot-2026-09-29"
PACKET = PILOT/"training-review/packet-20260929/packet.json"
CONSENSUS = LIDAR/"fractal/full-tile-20261008-a4000-chunked/naip2024/consensus.las"
GROUND = CITY/"raster-ground-recovery/ground_mosaic.tif"
VARIANTS = ("baseline", "local_roofs", "fractal_unanimous")
SIDE = 150
HALO = 20
WARNING = "Unvalidated development comparison; candidate counts and model agreement are not accuracy measurements."


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(8*1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def rectangle(bounds):
    a,b,c,d = bounds
    return arcpy.Polygon(arcpy.Array([arcpy.Point(x,y) for x,y in [(a,b),(a,d),(c,d),(c,b),(a,b)]]),arcpy.SpatialReference(6341))


def reference_state():
    result = {}
    gdb = PILOT/"validation/reference.gdb"
    for fc in ("treetop_sample","omission_sample","cell_sample","crown_sample"):
        label = "CROWN_LABEL" if fc == "crown_sample" else "LABEL"
        rows = sorted((key, bytes(wkb).hex(), answer or "") for key,wkb,answer in
                      arcpy.da.SearchCursor(str(gdb/fc),["SAMPLE_ID","SHAPE@WKB",label]))
        result[fc] = {"counts":dict(Counter(r[2] for r in rows)),
                      "geometry_labels_sha256":hashlib.sha256(json.dumps(rows).encode()).hexdigest()}
    return result


def prepare(root):
    root.mkdir(parents=True,exist_ok=False)
    frame = read(PACKET)["frame"]
    training_review.check_frame(frame)
    consensus_manifest = read(CONSENSUS.parent/"manifest.json")
    assert consensus_manifest["status"].startswith("complete") and consensus_manifest["repeats"] == 3
    assert sha(CONSENSUS) == consensus_manifest["consensus_sha256"]
    source = CITY/"prepared/points/12TVL2804.las"
    record = {"status":"preparing", "started":time.time(), "warning":WARNING,
        "tile":"12TVL2804", "frame_digest":frame["digest"], "runtime":common.runtime(),
        "code_sha256":sha(Path(__file__)),
        "reference_before":reference_state(), "source_sha256":sha(source),
        "consensus_sha256":consensus_manifest["consensus_sha256"], "packet_sha256":sha(PACKET),
        "parameters":{"cell_m":.5,"core_m":SIDE,"halo_m":HALO,"bands":bands.DEFAULT_SPEC,"smooth_cells":1,
            "local_roofs":"existing defaults; no threshold tuning",
            "model_policy":"existing refine_city.rules; three unanimous votes; all excluded flags protected",
            "ground":"same October 8 cached terrain for every variant",
            "development_metric_domain":"core outside fixed reference/census 25 m buffers",
            "selection":"largest roofs, greatest footprint count, highest baseline canopy among remaining cores"},
        "evaluation_status":"NO_LABELS"}
    common.write_json(root/"experiment.json",record)
    city = shapely.union_all([shapely.from_wkb(bytes(w)) for (w,) in arcpy.da.SearchCursor(str(CITY/"inputs.gdb/municipal_boundary"),["SHAPE@WKB"])])
    footprints = [shapely.from_wkb(bytes(w)) for (w,) in arcpy.da.SearchCursor(str(PRODUCTS/"buildings.gdb/building_heights"),["SHAPE@WKB"],spatial_filter=rectangle([428000,4504000,429000,4505000]),spatial_relationship="INTERSECTS")]
    candidates = []
    for y in range(4504050,4504801,175):
        for x in range(428050,428801,175):
            bounds = [x,y,x+SIDE,y+SIDE]
            box = shapely.box(*bounds)
            if not shapely.covers(city,box):
                continue
            xgrid,ygrid = np.meshgrid(x+(np.arange(300)+.5)*.5, y+(300-np.arange(300)-.5)*.5)
            allowed = training_review.patch_status(xgrid.ravel(),ygrid.ravel(),frame,radius=0).reshape((300,300)) == ""
            if allowed.mean() < .15:
                continue
            canopy = arcpy.RasterToNumPyArray(str(PRODUCTS/"chm_m.tif"),arcpy.Point(x,y),300,300,-9999)
            areas = [g.intersection(box).area for g in footprints if shapely.intersects(g,box)]
            candidates.append({"core":bounds,"footprints":len(areas),"roof_area_m2":sum(areas),
                "largest_roof_m2":max(areas,default=0),"baseline_canopy_m2":int((canopy>=2).sum())*.25,
                "development_cells":int(allowed.sum())})
    selected = []
    for name, key in (("large_roofs","largest_roof_m2"),("small_roofs","footprints"),("canopy_open","baseline_canopy_m2")):
        options = [c for c in candidates if all(not shapely.intersects(shapely.box(*c["core"]),shapely.box(*s["core"]).buffer(5)) for s in selected)]
        assert options, "Not enough nonoverlapping development cores"
        chosen = dict(max(options,key=lambda c:(c[key],c["development_cells"])))
        chosen["name"] = name
        chosen["buffered"] = [chosen["core"][0]-HALO,chosen["core"][1]-HALO,chosen["core"][2]+HALO,chosen["core"][3]+HALO]
        selected.append(chosen)
    record.update(sites=selected,selection_candidates=candidates)
    common.write_json(root/"experiment.json",record)
    base = root/"baseline"
    (base/"points").mkdir(parents=True)
    target = base/"points/12TVL2804.las"
    shutil.copy2(source,target)
    assert sha(target) == record["source_sha256"]
    lasd = str(base/"prepared.lasd")
    arcpy.management.CreateLasDataset([str(target)],lasd,compute_stats="COMPUTE_STATS")
    common.write_json(base/"preparation.json",{"status":"complete","working_lasd":lasd,
        "extent":[428000,4504000,429000,4505000],"source_id":"classification-pilot-20261019",
        "sources":[str(source)],"quality_status":"BASELINE_UNVALIDATED"})
    record["status"] = "baseline ready"
    common.write_json(root/"experiment.json",record)
    print(json.dumps({"sites":selected,"reference":record["reference_before"]},indent=2),flush=True)


def model(root):
    spec = importlib.util.spec_from_file_location("city_refine_rules",TOOLBOX/"reviews/2026-10-19/fractal-city/refine_city.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base = root/"baseline/points/12TVL2804.las"
    folder = root/"fractal_unanimous"
    (folder/"points").mkdir(parents=True,exist_ok=False)
    out = folder/"points/12TVL2804.las"
    shutil.copy2(base,out)
    header = las_records.header(out)
    mapped = np.memmap(out,dtype=np.uint8,offset=header["offset"],mode="r+",shape=(header["points"],header["record_length"]))
    ground = arcpy.RasterToNumPyArray(str(GROUND),arcpy.Point(428000,4504000),2000,2000,-9999)
    audit = {"point_index":[],"previous_class_byte":[],"new_class":[],"rule":[]}
    proposals = Counter()
    with laspy.open(base) as b, laspy.open(CONSENSUS) as c:
        assert b.header.point_count == c.header.point_count == header["points"]
        offset = 0
        for block in b.chunk_iterator(500_000):
            other = c.read_points(len(block))
            for dim in b.header.point_format.dimension_names:
                if dim != "classification":
                    assert np.array_equal(np.asarray(block[dim]),np.asarray(other[dim])),f"Consensus alignment: {dim}"
            codes,agreement,tied,strict = [np.asarray(other[k]) for k in ("MajorityClassification","RepeatAgreement","RepeatTie","StrictMajority")]
            fractal_compare.validate_consensus(codes,agreement,tied,strict,3)
            x,y,z = [np.asarray(v) for v in (block.x,block.y,block.z)]
            col = np.floor((x-428000)/.5).astype(int)
            row = np.floor((4505000-y)/.5).astype(int)
            inside = (col>=0)&(col<2000)&(row>=0)&(row<2000)
            hag = np.full(len(block),np.nan)
            g = ground[row[inside],col[inside]].astype(float)
            g[g == -9999] = np.nan
            hag[inside] = z[inside]-g
            old = np.asarray(block.classification).astype(np.uint8)
            skip = np.asarray(block.withheld,bool)|np.asarray(block.synthetic,bool)|np.asarray(block.overlap,bool)
            new,rules = module.rules(old,codes,np.isclose(agreement,1,atol=1e-6),skip,hag)
            changed = new != old
            assert np.all(~skip[changed]) and np.isin(old[changed],[3,4,5,6]).all()
            mapped[offset:offset+len(block),16] = new
            indexes = np.flatnonzero(changed)
            for key,value in (("point_index",indexes+offset),("previous_class_byte",old[changed]),("new_class",new[changed]),("rule",rules[changed])):
                audit[key].append(value)
            proposals.update(dict(zip(*[a.tolist() for a in np.unique(rules[rules>=11],return_counts=True)])))
            offset += len(block)
    mapped.flush()
    del mapped
    np.savez_compressed(folder/"changes.npz",**{k:np.concatenate(v) for k,v in audit.items()})
    proof = verify_only_classes_changed(base,out)
    lasd = str(folder/"prepared.lasd")
    arcpy.management.CreateLasDataset([str(out)],lasd,compute_stats="COMPUTE_STATS")
    state = read(root/"baseline/preparation.json")
    state.update(working_lasd=lasd,quality_status="EXPERIMENTAL_UNVALIDATED",consensus=str(CONSENSUS),
                 integrity=proof,proposed_only=dict(proposals),rule_code_sha256=sha(Path(module.__file__)))
    common.write_json(folder/"preparation.json",state)
    print(json.dumps(proof),flush=True)


def local(root):
    with licensing.extensions("3D","Spatial"):
        state = roofs.refine_local(str(root/"baseline/prepared.lasd"),str(root/"local_roofs"))
    proof = verify_only_classes_changed(root/"baseline/points/12TVL2804.las",root/"local_roofs/points/12TVL2804.las")
    common.write_json(root/"local_roofs/integrity.json",proof)
    print(json.dumps(proof),flush=True)


def raster(root,site_name,variant):
    state = read(root/"experiment.json")
    site = next(s for s in state["sites"] if s["name"]==site_name)
    folder = root/"products"/site_name/variant
    folder.mkdir(parents=True,exist_ok=False)
    with licensing.extensions("3D","Spatial"):
        products = rasters.build_chm(str(root/variant/"prepared.lasd"),str(folder),.5,
            " ".join(map(str,site["buffered"])),source_id="classification-pilot-20261019",ground_raster=str(GROUND))
        gdb = str(folder/"review.gdb")
        arcpy.management.CreateFileGDB(str(folder),"review.gdb")
        points = treetops.detect(products["chm"],gdb,bands.parse_bands(bands.DEFAULT_SPEC),smooth_cells=1,
                                  source_id="classification-pilot-20261019")
        common.add_fields(points,[("IN_CORE","SHORT",None),("DEVELOPMENT","SHORT",None)])
        frame = read(PACKET)["frame"]
        bounds = site["core"]
        with arcpy.da.UpdateCursor(points,["SHAPE@X","SHAPE@Y","IN_CORE","DEVELOPMENT"]) as cursor:
            for row in cursor:
                row[2] = int(bounds[0]<=row[0]<bounds[2] and bounds[1]<=row[1]<bounds[3])
                row[3] = int(bool(row[2]) and training_review.patch_status([row[0]],[row[1]],frame,radius=0)[0]=="")
                cursor.updateRow(row)
    common.write_json(folder/"result.json",{"status":"complete","rasters":products,"treetops":points})
    print(site_name,variant,"ready",flush=True)


def finish(root):
    state = read(root/"experiment.json")
    frame = read(PACKET)["frame"]
    summaries, building_rows = [], []
    spec = importlib.util.spec_from_file_location("building_windows",TOOLBOX/"reviews/2026-10-19/summarize_city_buildings.py")
    bm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bm)
    for site in state["sites"]:
        bounds = site["core"]
        x,y = np.meshgrid(bounds[0]+(np.arange(300)+.5)*.5,bounds[1]+(300-np.arange(300)-.5)*.5)
        develop = training_review.patch_status(x.ravel(),y.ravel(),frame,radius=0).reshape((300,300))==""
        previous = None
        for variant in VARIANTS:
            result = read(root/"products"/site["name"]/variant/"result.json")
            arrays = {}
            for key in ("chm","dtm","building","dsm"):
                arrays[key] = arcpy.RasterToNumPyArray(result["rasters"][key],arcpy.Point(bounds[0],bounds[1]),300,300,-9999).astype(float)
                arrays[key][arrays[key]==-9999] = np.nan
            if previous is None:
                previous = arrays
            assert np.array_equal(previous["dtm"],arrays["dtm"],equal_nan=True)
            observed, canopy = np.isfinite(arrays["chm"]), arrays["chm"]>=2
            base_observed, base_canopy = np.isfinite(previous["chm"]), previous["chm"]>=2
            count = list(arcpy.da.SearchCursor(result["treetops"],["IN_CORE","DEVELOPMENT"]))
            row = {"site":site["name"],"variant":variant,"core_m2":SIDE**2,"development_m2":float(develop.sum()*.25),
                "treetops_core":sum(r[0] for r in count),"treetops_development":sum(r[1] for r in count),
                "canopy_m2_core":float(canopy.sum()*.25),"canopy_m2_development":float((canopy&develop).sum()*.25),
                "observed_m2_development":float((observed&develop).sum()*.25),
                "observation_lost_m2":float((base_observed&~observed&develop).sum()*.25),
                "observation_gained_m2":float((~base_observed&observed&develop).sum()*.25),
                "canopy_removed_m2":float((base_canopy&~canopy&develop).sum()*.25),
                "canopy_added_m2":float((~base_canopy&canopy&develop).sum()*.25),"accuracy_status":"NO_LABELS"}
            summaries.append(row)
            windows = bm.Windows({"terrain":result["rasters"]["dtm"],"roof_elevation":result["rasters"]["building"]})
            with common.scratch() as (_,scratch):
                for key,geom in arcpy.da.SearchCursor(str(PRODUCTS/"buildings.gdb/building_heights"),["SOURCE_ID","SHAPE@"],
                    spatial_filter=rectangle(bounds),spatial_relationship="INTERSECTS"):
                    metrics,_ = bm.summarize(geom,rectangle(bounds),windows,scratch)
                    building_rows.append({"site":site["name"],"variant":variant,"SOURCE_ID":key,**metrics})
    with (root/"comparison.csv").open("w",newline="",encoding="utf-8") as handle:
        writer = csv.DictWriter(handle,fieldnames=list(summaries[0]));writer.writeheader();writer.writerows(summaries)
    with (root/"building-comparison.csv").open("w",newline="",encoding="utf-8") as handle:
        writer = csv.DictWriter(handle,fieldnames=list(building_rows[0]));writer.writeheader();writer.writerows(building_rows)
    assert reference_state() == state["reference_before"]
    assert sha(CITY/"prepared/points/12TVL2804.las") == state["source_sha256"]
    assert sha(CONSENSUS) == state["consensus_sha256"] and sha(PACKET)==state["packet_sha256"]
    review = root/"independent-review"
    review.mkdir()
    packet_source = TOOLBOX/"reviews/2026-09-29/packets/reference-review-batch1"
    for filename in ("labels.csv","packet.json","REVIEW.md"):
        shutil.copy2(packet_source/filename,review/filename)
    arcpy.management.Copy(str(PILOT/"validation/reference.gdb"),str(review/"reference.gdb"))
    source_project = PILOT/"validation/review/validation_review.aprx"
    if source_project.exists():
        project = arcpy.mp.ArcGISProject(str(source_project))
        for map_ in project.listMaps():
            for layer in map_.listLayers():
                if not layer.supports("CONNECTIONPROPERTIES"):
                    continue
                connection = layer.connectionProperties
                old_database = connection.get("connection_info",{}).get("database","")
                if "reference.gdb" in old_database:
                    updated = json.loads(json.dumps(connection))
                    updated["connection_info"]["database"] = str(review/"reference.gdb")
                    layer.updateConnectionProperties(connection,updated,validate=True)
                elif not layer.isGroupLayer:
                    layer.visible = False
        project.saveACopy(str(review/"independent_review.aprx"))
    state.update(status="complete; comparisons ready, independent labels required",finished=time.time(),
        comparison=summaries,building_rows=len(building_rows),reference_unchanged=True,source_unchanged=True,
        consensus_unchanged=True,independent_review=str(review),evaluation_status="NO_LABELS",
        independent_review_note="Exact copy of existing fixed sample, not a new draw. Labels remain blank; no reference answers synthesized.")
    common.write_json(root/"experiment.json",state)
    print(json.dumps(summaries,indent=2),flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root",type=Path)
    parser.add_argument("--step",choices=("prepare","model","local","raster","finish"))
    parser.add_argument("--site")
    parser.add_argument("--variant",choices=VARIANTS)
    args = parser.parse_args()
    if args.step:
        if args.step=="raster":raster(args.root,args.site,args.variant)
        else:globals()[args.step](args.root)
        return
    if args.root.exists():raise FileExistsError("Use a fresh pilot root")
    logs = args.root.parent/(args.root.name+"-logs")
    logs.mkdir(exist_ok=False)
    jobs = [("prepare",[]),("model",[]),("local",[])]
    for step,extra in jobs:
        with (logs/(step+".log")).open("w",encoding="utf-8") as log:
            done=subprocess.run([sys.executable,"-B",str(Path(__file__).resolve()),str(args.root),"--step",step,*extra],stdout=log,stderr=subprocess.STDOUT)
        if done.returncode:raise RuntimeError(f"{step} failed; inspect {logs/(step+'.log')}")
        print(step,"complete",flush=True)
    for site in read(args.root/"experiment.json")["sites"]:
        for variant in VARIANTS:
            name=site["name"]+"-"+variant
            with (logs/(name+".log")).open("w",encoding="utf-8") as log:
                done=subprocess.run([sys.executable,"-B",str(Path(__file__).resolve()),str(args.root),"--step","raster","--site",site["name"],"--variant",variant],stdout=log,stderr=subprocess.STDOUT)
            if done.returncode:raise RuntimeError(f"{name} failed; inspect its log")
            print(name,"complete",flush=True)
    with (logs/"finish.log").open("w",encoding="utf-8") as log:
        done=subprocess.run([sys.executable,"-B",str(Path(__file__).resolve()),str(args.root),"--step","finish"],stdout=log,stderr=subprocess.STDOUT)
    if done.returncode:raise RuntimeError("Final comparison failed; inspect finish.log")
    print("Comparison complete; independent accuracy remains NO_LABELS",flush=True)


if __name__=="__main__":main()
