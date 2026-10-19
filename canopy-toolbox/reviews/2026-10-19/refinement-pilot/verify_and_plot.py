"""Verify the frozen pilot and plot comparable CHMs on one shared height scale."""
import hashlib
import json
from pathlib import Path
import sys

import arcpy
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from canopy import common, las_records, training_review
from canopy.training_review import verify_only_classes_changed


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    value=hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda:handle.read(8*1024*1024),b""):value.update(block)
    return value.hexdigest()


def main(root):
    root=Path(root).resolve()
    state=read(root/"experiment.json")
    assert state["status"].startswith("complete") and state["evaluation_status"]=="NO_LABELS"
    base=root/"baseline/points/12TVL2804.las"
    reference,_,_,modern,_=las_records.records(base)
    assert modern
    checks={}
    for variant in ("local_roofs","fractal_unanimous"):
        source=root/variant/"points/12TVL2804.las"
        proof=verify_only_classes_changed(base,source)
        points,_,_,_,_=las_records.records(source)
        actual=np.flatnonzero(reference["classification"]!=points["classification"])
        audit=np.load(root/variant/("changes/12TVL2804.npz" if variant=="local_roofs" else "changes.npz"))
        assert np.array_equal(actual,audit["point_index"])
        assert np.array_equal(reference["classification"][actual],audit["previous_class_byte"])
        assert las_records.clean_flags(reference["flags"][actual],True).all()
        if variant=="local_roofs":
            assert np.isin(reference["classification"][actual],[4,5]).all()
            assert (points["classification"][actual]==6).all() and (audit["votes"]>=3).all()
        else:
            assert np.array_equal(points["classification"][actual],audit["new_class"])
            assert np.isin(reference["classification"][actual],[3,4,5,6]).all()
        checks[variant]={**proof,"audit_exact_match":True,"all_excluded_flags_protected":True}
        del points
    del reference
    colours=LinearSegmentedColormap.from_list("height",["#f5f5f0","#b4d79d","#51a161","#006837","#003e30"])
    colours.set_bad("#909090")
    fig,axes=plt.subplots(3,3,figsize=(12,11),layout="constrained")
    variants=("baseline","local_roofs","fractal_unanimous")
    frame=read(Path("D:/lidar/2023-salt-lake-valley/runs/pilot-2026-09-29/training-review/packet-20260929/packet.json"))["frame"]
    comparisons=[]
    for row,site in enumerate(state["sites"]):
        previous=None
        x0,y0,x1,y1=site["core"]
        xs,ys=np.meshgrid(x0+(np.arange(300)+.5)*.5,y0+(300-np.arange(300)-.5)*.5)
        develop=training_review.patch_status(xs.ravel(),ys.ravel(),frame,radius=0).reshape((300,300))==""
        base_chm=None
        for col,variant in enumerate(variants):
            result=read(root/"products"/site["name"]/variant/"result.json")
            arrays={}
            for key in ("chm","dtm"):
                arrays[key]=arcpy.RasterToNumPyArray(result["rasters"][key],arcpy.Point(x0,y0),300,300,-9999)
                r,cell=common.grid(result["rasters"][key],.5,4_000_000)
                assert (r.width,r.height)==(380,380)
            if previous is not None:assert np.array_equal(arrays["dtm"],previous)
            previous=arrays["dtm"]
            chm=arrays["chm"].astype(float);chm[chm==-9999]=np.nan
            if base_chm is None:base_chm=chm.copy()
            ax=axes[row,col]
            plotted=ax.imshow(np.ma.masked_invalid(chm),extent=(0,150,0,150),vmin=0,vmax=40,cmap=colours,origin="upper")
            points=list(arcpy.da.SearchCursor(result["treetops"],["SHAPE@X","SHAPE@Y"],where_clause="DEVELOPMENT = 1"))
            if points:
                xy=np.asarray(points)
                ax.scatter(xy[:,0]-x0,xy[:,1]-y0,s=3,color="#f16b22",alpha=.8,linewidths=0)
            metric=next(r for r in state["comparison"] if r["site"]==site["name"] and r["variant"]==variant)
            assert len(points)==metric["treetops_development"]
            observed=np.isfinite(chm)&develop
            canopy=(chm>=2)&develop
            unknown=develop&~np.isfinite(chm)
            removed=(base_chm>=2)&develop&~(chm>=2)
            removed_unknown=removed&~np.isfinite(chm)
            removed_known=removed&np.isfinite(chm)
            assert (removed_unknown.sum()+removed_known.sum())*.25==metric["canopy_removed_m2"]
            assert observed.sum()*.25==metric["observed_m2_development"]
            assert canopy.sum()*.25==metric["canopy_m2_development"]
            comparisons.append({"site":site["name"],"variant":variant,
                "coverage_pct":float(100*observed.sum()/develop.sum()),
                "canopy_lower_bound_pct":float(100*canopy.sum()/develop.sum()),
                "canopy_upper_bound_pct":float(100*(canopy.sum()+unknown.sum())/develop.sum()),
                "baseline_canopy_now_observed_below_2m_m2":float(removed_known.sum()*.25),
                "baseline_canopy_now_unknown_m2":float(removed_unknown.sum()*.25)})
            ax.set_title(f"{variant.replace('_',' ')}\n{metric['treetops_development']} development candidates",fontsize=10)
            if col==0:ax.set_ylabel(site["name"].replace("_"," ")+"\nNorthing within core (m)")
            if row==2:ax.set_xlabel("Easting within core (m)")
            ax.set_aspect("equal")
    fig.colorbar(plotted,ax=axes,shrink=.65,label="Canopy height above terrain (m); grey = NoData")
    fig.suptitle("Fixed-parameter development comparison | orange dots are unverified candidates\n150 m cores; candidate counts exclude reference/census buffers",fontsize=13)
    fig.savefig(root/"comparison.png",dpi=155)
    plt.close(fig)
    assert state["reference_unchanged"] and state["source_unchanged"] and state["consensus_unchanged"]
    original=Path(__file__).resolve().parents[2]/"2026-09-29/packets/reference-review-batch1/labels.csv"
    # parents[2] is reviews for this script's location.
    assert sha(root/"independent-review/labels.csv")==sha(original)
    for fc,expected in state["reference_before"].items():
        label="CROWN_LABEL" if fc=="crown_sample" else "LABEL"
        rows=sorted((key,bytes(wkb).hex(),answer or "") for key,wkb,answer in arcpy.da.SearchCursor(
            str(root/"independent-review/reference.gdb"/fc),["SAMPLE_ID","SHAPE@WKB",label]))
        assert hashlib.sha256(json.dumps(rows).encode()).hexdigest()==expected["geometry_labels_sha256"]
    proof={"status":"passed","variants":checks,"site_raster_pairs":9,"all_site_grids_match":True,
        "same_ground_all_variants":True,"reference_unchanged":True,"raw_consensus_unchanged":True,
        "blind_worksheet_unchanged":True,"blind_reference_geometry_labels_match":True,
        "evaluation_status":"NO_LABELS","figure":str(root/"comparison.png")}
    proof["development_comparison"]=comparisons
    common.write_json(root/"verification.json",proof)
    print(json.dumps(proof,indent=2))


if __name__=="__main__":main(sys.argv[1])
