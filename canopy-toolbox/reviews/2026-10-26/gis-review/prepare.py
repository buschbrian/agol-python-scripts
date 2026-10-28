"""Build new review copies; never edit LAS, footprints, models or human labels.

Run in Pro Python. --pilot limits trees to the first shard and uses a separate output folder.
No publishing. Source coordinates stay EPSG:6341; hosted copies use the proven ITRF08 transform.
"""
import argparse
import collections
import csv
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

import arcpy
import numpy as np
from shapely import from_wkb, MultiPoint, Point, STRtree, union_all

from review_rules import roof_queue, tree_queue, metres_to_feet, STATUS, ROOF_DECISIONS, TREE_DECISIONS

RUNS = Path(r'H:\lidar\2023-salt-lake-valley\runs')
SOURCE = RUNS/'millcreek-products-20261022/buildings.gdb/building_heights'
MASSING = RUNS/'massing-20261022/massing.gdb/footprints'
HYBRID = RUNS/'roofer-city-v2-20261024/v2/v2.gdb/buildings'
TRANSFORM = 'WGS_1984_(ITRF08)_To_NAD_1983_2011'


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n', encoding='utf8')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1<<20), b''):
            h.update(block)
    return h.hexdigest()


def indices(boundaries):
    if isinstance(boundaries, int):
        yield boundaries
    else:
        for value in boundaries:
            yield from indices(value)


def add_fields(fc, fields):
    for name, typ, length, alias in fields:
        arcpy.management.AddField(str(fc), name, typ, field_length=length, field_alias=alias)


COMMON = [
    ('PRIORITY','SHORT',None,'Review priority (1 first, 4 routine)'),
    ('REVIEW_FLAGS','TEXT',500,'Automated review cues; not findings'),
    ('REVIEW_STATUS','TEXT',24,'Review status'), ('REVIEW_DECISION','TEXT',32,'Your finding'),
    ('EVIDENCE_SOURCE','TEXT',500,'Evidence source / image or field visit'),
    ('EVIDENCE_DATE','TEXT',80,'Evidence capture date (or unknown)'),
    ('REVIEW_NOTES','TEXT',2000,'Review notes and proposed correction')]


def common(priority, flags):
    return [priority, flags, 'pending', 'uncertain', None, None, None]


def create_fc(gdb, name, geometry, fields):
    fc=gdb/name
    arcpy.management.CreateFeatureclass(str(gdb), name, geometry, spatial_reference=arcpy.SpatialReference(6341))
    add_fields(fc, fields+COMMON)
    return fc


def row_digest(rows):
    h=hashlib.sha256()
    for row in sorted(rows, key=lambda r:str(r[0])):
        h.update(json.dumps(row, default=str, separators=(',',':')).encode())
    return h.hexdigest()


def prepare_roofs(gdb):
    mass={str(s):int(fp) for s,fp in arcpy.da.SearchCursor(str(MASSING),['SOURCE_ID','FP_ID'])}
    hybrid_fields=['FP_ID','SOURCE_ID','LEVEL','CHECK_VERDICT','ROOFER_VERDICT','FALLBACK_REASON',
                   'RF_RMSE_LOD22','ROOF_SLOPE_MAIN','BLDG_HT_M']
    hybrid_rows=list(arcpy.da.SearchCursor(str(HYBRID),hybrid_fields))
    hybrid={str(r[1]):r for r in hybrid_rows}
    assert len(hybrid)==len(hybrid_rows)==21561
    fields=[('SOURCE_ID','TEXT',64,'County footprint ID'),('FP_ID','LONG',None,'Massing footprint ID'),
            ('ADDRESS','TEXT',250,'Source address (may be absent)'),('PARCEL_ID','TEXT',64,'Parcel ID'),
            ('MODEL_LEVEL','TEXT',40,'Hybrid model source'),('HEIGHT_STATUS','TEXT',150,'LiDAR roof-support status'),
            ('ROOF_COV_PCT','DOUBLE',None,'Footprint with roof support (%)'),
            ('HEIGHT_P50_FT','DOUBLE',None,'Median supported roof height (ft)'),
            ('HEIGHT_P95_FT','DOUBLE',None,'95th percentile roof height (ft)'),
            ('AREA_SQFT','DOUBLE',None,'County footprint area (sq ft)'),
            ('CHECK_VERDICT','TEXT',32,'Automated selected-model comparison'),
            ('ROOFER_VERDICT','TEXT',32,'Automated Roofer comparison'),
            ('FALLBACK_REASON','TEXT',200,'Why the hybrid used a fallback'),
            ('ROOF_RMSE_FT','DOUBLE',None,'Roofer model fit RMSE (ft; where available)'),
            ('ROOF_SLOPE_DEG','DOUBLE',None,'Main modeled roof slope (degrees)'),
            ('MODEL_HEIGHT_FT','DOUBLE',None,'Roofer model height (ft; where available)'),
            ('LIDAR_DATE','TEXT',64,'LiDAR acquisition period'),
            ('FOOTPRINT_DATE','TEXT',100,'County footprint vintage')]
    fc=create_fc(gdb,'roofs_review','POLYGON',fields)
    source_fields=['SOURCE_ID','ADDRESS','PARCEL_ID','HEIGHT_STATUS','ROOF_COV_PCT','HEIGHT_P50_M',
                   'HEIGHT_P95_M','FOOTPRINT_M2','SHAPE@','SHAPE@WKB']
    shapes=[]; source_ids=set(); fingerprint=[]; counts=collections.Counter(); examples=[]
    with arcpy.da.InsertCursor(str(fc),[f[0] for f in fields+COMMON]+['SHAPE@']) as dest:
        for sid,address,parcel,status,cov,h50,h95,area,shape,wkb in arcpy.da.SearchCursor(str(SOURCE),source_fields):
            sid=str(sid)
            assert sid not in source_ids
            source_ids.add(sid)
            r=hybrid.get(sid)
            level=r[2] if r else None
            priority,flags=roof_queue(level,status)
            vals=[sid,mass.get(sid),address,parcel,level or 'No hybrid model',status,cov,
                  metres_to_feet(h50),metres_to_feet(h95),area/.3048**2 if area is not None else None]
            vals += [r[3],r[4],r[5],metres_to_feet(r[6]),r[7],metres_to_feet(r[8])] if r else [None]*6
            vals += ['October-November 2023','Not established; source snapshot used October 2026']
            dest.insertRow(vals+common(priority,flags)+[shape])
            shp=from_wkb(bytes(wkb))
            assert shp.is_valid and not shp.is_empty
            shapes.append(shp)
            fingerprint.append([sid,hashlib.sha256(bytes(wkb)).hexdigest(),status,cov,h50,h95])
            counts[str(priority)]+=1
            if priority==1 and len(examples)<8:
                examples.append({'source_id':sid,'fp_id':mass.get(sid),'flags':flags,'x':shp.centroid.x,'y':shp.centroid.y})
    assert len(source_ids)==22042 and set(hybrid)<=source_ids
    missing=source_ids-set(hybrid)
    assert len(missing)==481
    return fc,shapes,{'count':len(source_ids),'missing_hybrid':len(missing),'priority_counts':dict(counts),
                     'source_fingerprint':row_digest(fingerprint),'hybrid_attributes_fingerprint':row_digest(hybrid_rows),
                     'examples':examples}


def read_models(run, pilot):
    records=[]; seen=set(); shards=sorted((run/'tiles').glob('*/trees_*.city.json.gz'))
    if pilot:shards=shards[:1]
    for n,f in enumerate(shards):
        with gzip.open(f,'rt',encoding='utf8') as stream:d=json.load(stream)
        vertices=np.asarray(d['vertices'], dtype=np.float64)*d['transform']['scale']+d['transform']['translate']
        assert np.isfinite(vertices).all()
        for key,obj in d['CityObjects'].items():
            a=obj['attributes']; ident=a['gtid']
            assert key=='T_'+ident and ident not in seen
            seen.add(ident)
            crown=vertices[np.unique(list(indices(obj['geometry'][0]['boundaries'])))]
            trunk=vertices[np.unique(list(indices(obj['geometry'][1]['boundaries'])))]
            hull=MultiPoint(crown[:,:2]).convex_hull
            assert hull.geom_type=='Polygon' and hull.is_valid and hull.area>0
            center=Point((trunk[:,0].min()+trunk[:,0].max())/2,(trunk[:,1].min()+trunk[:,1].max())/2)
            records.append({'id':ident,'tile':a['tile_id'],'shape':hull,'center':center,'a':a,'seam':False})
        if (n+1)%25==0:print(f'Read {n+1}/{len(shards)} shards; {len(records):,} models',flush=True)
    assert pilot or (len(shards)==506 and len(records)==119410)
    return records


def prepare_trees(gdb, run, roof_shapes, pilot):
    records=read_models(run,pilot)
    crowns=[r['shape'] for r in records]; index=STRtree(crowns); roofs=STRtree(roof_shapes)
    pairs=0
    # Candidate only: different tiles with >=70% overlap of the smaller convex outline.
    # Highest-point ownership avoids identical IDs but does not establish seamless crown segmentation.
    for i,r in enumerate(records):
        if not r['a']['edge_review']:continue
        for j in index.query(r['shape'],predicate='intersects'):
            if j<=i or r['tile']==records[j]['tile'] or not records[j]['a']['edge_review']:continue
            if r['shape'].intersection(crowns[j]).area/min(r['shape'].area,crowns[j].area)>=.70:
                r['seam']=records[j]['seam']=True;pairs+=1
    fields=[('MODEL_ID','TEXT',40,'Stable CFTree model ID'),('TILE_ID','TEXT',16,'Processing tile'),
            ('HEIGHT_FT','DOUBLE',None,'Modeled total height (ft)'),
            ('CROWN_WIDTH_FT','DOUBLE',None,'Modeled crown width (ft)'),
            ('TRUNK_DIAM_FT','DOUBLE',None,'Inferred trunk diameter (ft; not measured DBH)'),
            ('SOURCE_POINTS','LONG',None,'Vegetation returns in segment'),
            ('EDGE_REVIEW','SHORT',None,'Within 328 ft of tile edge (1=yes)'),
            ('CORE_EDGE_FT','DOUBLE',None,'Highest return distance to core edge (ft)'),
            ('ROOF_OVERLAP_PCT','DOUBLE',None,'Convex crown outline over County footprints (%)'),
            ('ROOF_CENTER','SHORT',None,'Inferred trunk center inside County footprint (1=yes)'),
            ('SEAM_CANDIDATE','SHORT',None,'Cross-tile overlap candidate (1=yes)'),
            ('OUTLINE_METHOD','TEXT',150,'Review outline construction'),
            ('LIDAR_DATE','TEXT',64,'LiDAR acquisition period'),
            ('TRUNK_METHOD','TEXT',150,'Trunk model method')]
    fc=create_fc(gdb,'trees_review','POLYGON',fields)
    counts=collections.Counter(); flags_count=collections.Counter(); examples=[]
    with arcpy.da.InsertCursor(str(fc),[f[0] for f in fields+COMMON]+['SHAPE@']) as dest:
        for r in records:
            a=r['a']; hull=r['shape']; hits=roofs.query(hull,predicate='intersects')
            overlap=min(100.,100*hull.intersection(union_all([roof_shapes[j] for j in hits])).area/hull.area) if len(hits) else 0.
            center=bool(len(roofs.query(r['center'],predicate='intersects')))
            priority,flags=tree_queue(a['edge_review'],overlap,center,r['seam'])
            vals=[r['id'],r['tile'],a['height_ft'],a['crown_width_ft'],a['modelled_trunk_diameter_ft'],
                  a['source_points'],int(a['edge_review']),a['core_edge_distance_ft'],overlap,int(center),int(r['seam']),
                  'Convex XY hull of CFTree crown mesh; not a surveyed crown or the full 3D mesh',
                  'October-November 2023',a['trunk_method']]
            ring=arcpy.Array([arcpy.Point(x,y) for x,y in hull.exterior.coords])
            shape=arcpy.Polygon(ring, arcpy.SpatialReference(6341))
            dest.insertRow(vals+common(priority,flags)+[shape])
            counts[str(priority)]+=1;flags_count.update(flags.split(';'))
            if priority==2 and len(examples)<8:
                examples.append({'model_id':r['id'],'flags':flags,'x':r['center'].x,'y':r['center'].y})
    return fc,{'count':len(records),'priority_counts':dict(counts),'flag_counts':dict(flags_count),
               'cross_tile_overlap_pairs':pairs,'examples':examples}


def prepare_rejects(gdb,run,pilot):
    fields=[('MODEL_ID','TEXT',40,'Rejected model candidate ID'),('TILE_ID','TEXT',16,'Processing tile'),
            ('SEGMENT_ID','LONG',None,'CFTree segment ID'),('REJECT_REASON','TEXT',250,'Reconstruction exclusion reason'),
            ('LOC_METHOD','TEXT',150,'Review point method'),('LIDAR_DATE','TEXT',64,'LiDAR acquisition period')]
    fc=create_fc(gdb,'tree_exceptions_review','POINT',fields)
    count=0; reasons=collections.Counter()
    with arcpy.da.InsertCursor(str(fc),[f[0] for f in fields+COMMON]+['SHAPE@XY']) as dest:
        for db_path in sorted((run/'tiles').glob('*/models.sqlite')):
            with sqlite3.connect(f'{db_path.as_uri()}?mode=ro', uri=True) as db:
                rejected={int(s):(ident,reason) for ident,s,reason in db.execute("SELECT id,segment,reason FROM models WHERE status='rejected'")}
            if not rejected:continue
            # Streaming scan of only rejected segments; segmentation.xyz is segment_id x y z.
            peaks={}
            with (db_path.parent/'segmentation.xyz').open() as stream:
                for line in stream:
                    values=line.split();seg=int(values[0])
                    if seg in rejected:
                        x,y,z=map(float,values[1:4])
                        if seg not in peaks or z>peaks[seg][2]:peaks[seg]=(x,y,z)
            assert set(peaks)==set(rejected)
            for seg,(ident,reason) in rejected.items():
                vals=[ident,db_path.parent.name,seg,reason,'Highest vegetation return of excluded segment; not a measured stem',
                      'October-November 2023']
                dest.insertRow(vals+common(1,'RECONSTRUCTION_EXCLUDED')+[peaks[seg][:2]])
                count+=1;reasons[reason]+=1
            print(f'Located {count}/75 exclusions',flush=True)
            if pilot:break
    assert pilot or count==75
    return fc,{'count':count,'reasons':dict(reasons)}


def finish_layer(fc, hosted, decisions):
    arcpy.management.Project(str(fc),str(hosted),arcpy.SpatialReference(3857),TRANSFORM)
    gdb=hosted.parent
    for name,codes in [('review_status',STATUS),(hosted.name+'_decision',decisions)]:
        existing={d.name for d in arcpy.da.ListDomains(str(gdb))}
        if name not in existing:
            arcpy.management.CreateDomain(str(gdb),name,name,'TEXT','CODED')
            for code,label in codes:arcpy.management.AddCodedValueToDomain(str(gdb),name,code,label)
    arcpy.management.AssignDomainToField(str(hosted),'REVIEW_STATUS','review_status')
    arcpy.management.AssignDomainToField(str(hosted),'REVIEW_DECISION',hosted.name+'_decision')
    arcpy.management.AssignDefaultToField(str(hosted),'REVIEW_STATUS','pending')
    arcpy.management.AssignDefaultToField(str(hosted),'REVIEW_DECISION','uncertain')
    arcpy.management.AddGlobalIDs(str(hosted))
    arcpy.management.EnableAttachments(str(hosted))
    arcpy.management.EnableEditorTracking(str(hosted),'created_user','created_date','last_edited_user','last_edited_date',
                                         'ADD_FIELDS','UTC')
    arcpy.management.AddIndex(str(hosted),'REVIEW_STATUS','review_status_idx')
    arcpy.management.AddIndex(str(hosted),'PRIORITY','priority_idx')
    expected=int(arcpy.management.GetCount(str(fc))[0]);actual=int(arcpy.management.GetCount(str(hosted))[0])
    assert expected==actual
    bad=[]
    for oid,shape in arcpy.da.SearchCursor(str(hosted),['OID@','SHAPE@']):
        if shape is None or not shape.pointCount:bad.append(oid)
    assert not bad,bad[:5]
    # Verify a representative source coordinate with the explicit datum operation used by this library.
    src=next(iter(arcpy.da.SearchCursor(str(fc),['SHAPE@'])))[0]
    dst=next(iter(arcpy.da.SearchCursor(str(hosted),['SHAPE@'])))[0]
    expected_center=src.projectAs(arcpy.SpatialReference(3857),TRANSFORM).centroid
    assert abs(expected_center.X-dst.centroid.X)<.01 and abs(expected_center.Y-dst.centroid.Y)<.01
    return {'count':actual,'empty_geometries':0,'spatial_reference':3857,'datum_transform':TRANSFORM,
            'domains':True,'attachments':True,'editor_tracking':True,'sample_projection_error_ft':'<0.033'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--pilot',action='store_true');a=p.parse_args()
    a.run=a.run.resolve();a.output=a.output.resolve()
    if a.output.exists():raise SystemExit('Output already exists; preserve any review edits. Use a new folder.')
    a.output.mkdir(parents=True)
    started=time.monotonic()
    arcpy.env.overwriteOutput=False
    for name in ['source.gdb','gis_review.gdb']:arcpy.management.CreateFileGDB(str(a.output),name)
    source=a.output/'source.gdb';hosted=a.output/'gis_review.gdb'
    roof_fc,roofs,roof_report=prepare_roofs(source)
    print(f'Prepared {len(roofs):,} roof footprints',flush=True)
    tree_fc,tree_report=prepare_trees(source,a.run,roofs,a.pilot)
    print(f'Prepared {tree_report["count"]:,} tree outlines',flush=True)
    reject_fc,reject_report=prepare_rejects(source,a.run,a.pilot)
    verification={}
    for fc,decisions in [(roof_fc,ROOF_DECISIONS),(tree_fc,TREE_DECISIONS),(reject_fc,TREE_DECISIONS)]:
        verification[fc.name]=finish_layer(fc,hosted/fc.name,decisions)
        print('Projected and verified',fc.name,flush=True)
    report={'generated_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'pilot':a.pilot,'source_paths':
            {'footprints':str(SOURCE),'massing':str(MASSING),'hybrid':str(HYBRID),'cftree':str(a.run)},
            'config_sha256':digest(a.run/'config.json'),'roofs':roof_report,'trees':tree_report,'exceptions':reject_report,
            'layers':verification,'elapsed_seconds':round(time.monotonic()-started,1),
            'limitations':['Automated cues are not findings or human labels.',
            'No roof model does not establish demolition. Check coverage, classification, dates and alignment.',
            'Tree outlines are convex XY hulls of draft meshes, not full 3D meshes or surveyed crown extents.',
            'Roof overlap can be real overhang; cross-tile overlap can be separate trees.',
            'All trunk positions and diameters are inferred; not an inventory or measured DBH.']}
    dump(a.output/'manifest.json',report)
    arcpy.management.ClearWorkspaceCache()
    print(json.dumps({k:report[k] for k in ['roofs','trees','exceptions','elapsed_seconds']},indent=2))


if __name__=='__main__':main()
