"""Citywide count-only estimate: canonical CHM, global peaks, parcel ownership.

Run with Pro Python and PYTHONNOUSERSITE=1. Requires a completed isolated
preparation and inputs.json containing projected boundary/parcel snapshots.
Never calls crown segmentation or changes its 4-million-cell limit.
"""
import argparse
import collections
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
import subprocess
import time
import uuid

import arcpy
import numpy as np
import shapely
from shapely.strtree import STRtree

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from canopy import bands, common, count_peaks, las_records, licensing, parcel_ownership, rasters
from canopy.tiling import Extent, Tile, snap_extent, tile_grid


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def raster_core(lasd, tile, folder, source_id, ground_raster):
    folder=Path(folder);folder.mkdir(parents=True)
    start=time.time()
    with licensing.extensions('3D','Spatial'):
        # This native tool failed for one ground tile with the full-city index.
        # Include every working file whose header intersects the requested halo.
        # No point inside the raster extent can be excluded by this selection.
        selected=[]
        for path in sorted((Path(lasd).parent.parent/'prepared/points').glob('*.las')):
            a,b,c,d=las_records.header(path)['extent']
            if a<=tile.buffered.xmax and c>=tile.buffered.xmin and b<=tile.buffered.ymax and d>=tile.buffered.ymin:
                selected.append(str(path))
        if not selected:raise ValueError('No point files cover raster tile')
        subset=str(folder/'source.lasd')
        arcpy.management.CreateLasDataset(selected,subset,compute_stats='COMPUTE_STATS')
        common.write_json(folder/'source-files.json',selected)
        products=rasters.build_chm(subset,str(folder),.5,tile.buffered.as_arcpy_string(),
                                  source_id=source_id,ground_raster=ground_raster)
        core_path=str(folder/'core_chm.tif')
        with common.environment(products['chm']):
            arcpy.management.Clip(products['chm'],tile.core.as_arcpy_string(),core_path,
                                  nodata_value='-9999',maintain_clipping_extent='NO_MAINTAIN_EXTENT')
    return tile,core_path,time.time()-start


def fresh_raster(lasd, tile, folder, source_id, ground_raster):
    folder=Path(folder)
    job=folder.with_name(folder.name+'.job.json')
    common.write_json(job,{'lasd':lasd,'tile':list(tile),'folder':str(folder),
                          'source_id':source_id,'ground_raster':ground_raster})
    result=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--raster-worker',str(job)],
                          stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    if result.returncode:
        raise RuntimeError(f'Raster worker {tile.name} exited {result.returncode}: {result.stderr}')
    record=json.loads((folder/'result.json').read_text())
    return tile,record['core_path'],record['seconds']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('--wait-for-preparation',action='store_true')
    parser.add_argument('--workers',type=int,choices=[1,2,3],default=2)
    args=parser.parse_args()
    root=args.root.resolve()
    manifest=root/'count.json'
    if manifest.exists(): raise FileExistsError('Use a new count run')
    state={'status':'waiting for preparation','started':time.time(),
           'interpretation':'Estimated treetops >=2 m, not a field-verified stem census',
           'parameters':{'cell_m':.5,'raster_core_m':950,'raster_halo_m':20,'smooth_cells':1,
                         'bands':bands.DEFAULT_SPEC,'ownership_location':'Detected treetop cell centre',
                         'crowns':False},'tiles':{},'code_sha256':{}}
    for file in [Path(__file__),Path(count_peaks.__file__),Path(parcel_ownership.__file__),
                 Path(rasters.__file__),Path(bands.__file__)]:
        state['code_sha256'][file.name]=digest(file)
    def save(): common.write_json(manifest,state)
    save()
    try:
        preparation=root/'prepared'/'preparation.json'
        while True:
            prep=json.loads(preparation.read_text())
            if prep['status']=='complete': break
            if prep['status']=='failed': raise RuntimeError(prep.get('error','Preparation failed'))
            if not args.wait_for_preparation: raise ValueError('Preparation not complete')
            if time.time()-state['started']>21600: raise TimeoutError('Preparation did not complete in six hours')
            time.sleep(10)
        inputs=json.loads((root/'inputs.json').read_text())
        state['inputs_sha256']=digest(root/'inputs.json')
        state['preparation_sha256']=digest(preparation)
        state['source_id']=prep['source_id']
        state['input_files']=[{'path':str(p),'bytes':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns}
                              for p in sorted((root/'prepared'/'points').glob('*.las'))]
        city_parts=[shapely.from_wkb(bytes(wkb)) for wkb, in arcpy.da.SearchCursor(inputs['boundary'],['SHAPE@WKB'])]
        city=shapely.union_all(city_parts)
        if not shapely.is_valid(city): raise ValueError('City boundary geometry is invalid')
        shapely.prepare(city)
        extent=snap_extent(Extent(*inputs['extent']).buffered(20),.5)
        shape=(round(extent.height/.5),round(extent.width/.5))
        state.update(status='rasterizing',extent=list(extent),shape=list(shape))
        save()
        array=np.memmap(root/'canonical-chm.bin',mode='w+',dtype='float32',shape=shape)
        array[:]=np.nan
        context=shapely.buffer(city,20)
        planned=[t for t in tile_grid(extent,950,20,.5) if shapely.intersects(context,shapely.box(*t.core))]
        state['raster_tiles_planned']=len(planned);save()
        state['ground_raster']=inputs.get('ground_mosaic')
        state['raster_workers']=args.workers;save()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures=[pool.submit(fresh_raster,prep['working_lasd'],tile,str(root/'rasters'/tile.name),
                                 prep['source_id'],inputs.get('ground_mosaic')) for tile in planned]
            for number,future in enumerate(as_completed(futures),1):
                tile,core_path,seconds=future.result()
                raster=arcpy.Raster(core_path)
                rr=round((extent.ymax-raster.extent.YMax)/.5)
                cc=round((raster.extent.XMin-extent.xmin)/.5)
                core=arcpy.RasterToNumPyArray(raster,nodata_to_value=np.nan)
                expected=(round(tile.core.height/.5),round(tile.core.width/.5))
                if core.shape!=expected or not math.isclose(raster.meanCellWidth,.5):
                    raise ValueError('Raster core grid differs')
                if (abs(extent.xmin+cc*.5-raster.extent.XMin)>1e-6 or
                        abs(extent.ymax-rr*.5-raster.extent.YMax)>1e-6):
                    raise ValueError('Raster core is not on the canonical grid')
                array[rr:rr+core.shape[0],cc:cc+core.shape[1]]=core
                state['tiles'][tile.name]={'core':list(tile.core),'chm':core_path,
                                           'seconds':seconds,'grid_offset':[rr,cc],
                                           'shape':list(core.shape)}
                save();print(f'CHM {number}/{len(planned)} {tile.name}: {seconds:.1f}s',flush=True)
        array.flush()
        state['status']='detecting globally reconciled peaks';save()
        last=[0.]
        def progress(stage,row,col):
            if time.time()-last[0]>30:
                state['detection_progress']={'stage':stage,'row':row,'col':col};save()
                print('Detection:',stage,row,col,flush=True);last[0]=time.time()
        peaks=count_peaks.detect(array,bands.DEFAULT_BANDS,.5,root/'peak-work',progress=progress)
        xy=np.array([(extent.xmin+(c+.5)*.5,extent.ymax-(r+.5)*.5) for r,c,h in peaks]).reshape(-1,2)
        inside=shapely.intersects_xy(city,xy[:,0],xy[:,1])
        state['peaks_before_city_clip']=len(peaks)
        peaks=[peak for peak,keep in zip(peaks,inside) if keep];xy=xy[inside]
        state.update(status='assigning parcel ownership',city_treetops=len(peaks));save()
        parcel_geometries=[];parcel_categories=[];parcel_groups=[];public=collections.Counter()
        for oid,owner,wkb in arcpy.da.SearchCursor(inputs['parcels'],['OID@','own_name','SHAPE@WKB']):
            if wkb is None: raise ValueError(f'Parcel {oid} has no geometry')
            geom=shapely.from_wkb(bytes(wkb))
            if not shapely.is_valid(geom): raise ValueError(f'Parcel {oid} geometry is invalid; repair the snapshot explicitly')
            category,group=parcel_ownership.classify(owner)
            parcel_geometries.append(geom);parcel_categories.append(category);parcel_groups.append(group)
            if category!='PRIVATE': public[(str(owner),category,group)]+=1
        with open(root/'owner-classification-review.csv','w',encoding='utf-8',newline='') as handle:
            writer=csv.writer(handle);writer.writerow(['OWNER_OF_RECORD','CATEGORY','BASIS','PARCELS'])
            writer.writerows((*key,n) for key,n in sorted(public.items()))
        tree=STRtree(parcel_geometries)
        assigned=[]
        for offset in range(0,len(xy),10000):
            batch=xy[offset:offset+10000]
            matches=tree.query(shapely.points(batch),predicate='intersects')
            hits=collections.defaultdict(list)
            for point,parcel in zip(*matches): hits[int(point)].append(int(parcel))
            for i in range(len(batch)):
                ids=hits[i]
                category=parcel_ownership.resolve(parcel_categories[j] for j in ids)
                groups=sorted(set(parcel_groups[j] for j in ids))
                group=groups[0] if len(groups)==1 else ('MULTIPLE_PUBLIC_PARCELS' if category=='PUBLIC_GOVERNMENT' else '')
                assigned.append((category,group,len(ids)))
        totals=collections.Counter(row[0] for row in assigned)
        if sum(totals.values())!=len(peaks): raise RuntimeError('Ownership totals do not sum to unique city peaks')
        gdb=str(root/'tree-count.gdb');arcpy.management.CreateFileGDB(str(root),'tree-count.gdb')
        tops=common.create_points(gdb,'city_treetops',arcpy.SpatialReference(6341))
        common.add_fields(tops,[('OWNERSHIP','TEXT',32),('OWNER_GROUP','TEXT',80),('PARCEL_MATCHES','LONG',None)])
        fields=['SHAPE@XY','TREE_ID','HEIGHT_M','MIN_HEIGHT','SMOOTH','SOURCE_ID','REVIEW_STATUS',
                'OWNERSHIP','OWNER_GROUP','PARCEL_MATCHES']
        with arcpy.da.InsertCursor(tops,fields) as cursor, open(root/'city-treetops.csv','w',encoding='utf-8',newline='') as handle:
            writer=csv.writer(handle);writer.writerow(['TREE_ID','X','Y','HEIGHT_M','OWNERSHIP','OWNER_GROUP','PARCEL_MATCHES'])
            for (r,c,h),(x,y),(category,group,matches) in zip(peaks,xy,assigned):
                tree_id=str(uuid.uuid5(uuid.NAMESPACE_URL,f'{prep["source_id"]}|6341|{x:.6f}|{y:.6f}'))
                cursor.insertRow([(x,y),tree_id,h,2.,1,prep['source_id'],'UNVERIFIED',category,group,matches])
                writer.writerow([tree_id,x,y,h,category,group,matches])
        common.metadata(tops,'Citywide count-only detection on one canonical CHM with globally reconciled plateaus. '
                        'Ownership uses detected apex location and 2025-tax-year parcel snapshot, not surveyed stems. '
                        'Unknown and conflicting ownership are separate; tax exemption does not establish public ownership.')
        state['status']='checking city observation coverage';save()
        cell_total=observed=canopy=0
        for r0,c0,r1,c1 in count_peaks.blocks(shape,1000):
            xs=extent.xmin+(np.arange(c0,c1)+.5)*.5
            ys=extent.ymax-(np.arange(r0,r1)+.5)*.5
            mask=shapely.intersects_xy(city,xs[None,:],ys[:,None])
            chunk=np.asarray(array[r0:r1,c0:c1])
            cell_total+=int(mask.sum());observed+=int((mask&np.isfinite(chunk)).sum())
            canopy+=int((mask&(chunk>=2)).sum())
        for row in state['input_files']:
            stat=Path(row['path']).stat()
            if (stat.st_size,stat.st_mtime_ns)!=(row['bytes'],row['mtime_ns']):
                raise RuntimeError('Prepared LAS changed during count')
        state.update(status='complete',finished=time.time(),ownership_totals=dict(totals),
                     observation={'city_grid_cells':cell_total,'observed_cells':observed,'missing_cells':cell_total-observed,
                                  'observed_pct':observed/cell_total*100,'canopy_ge_2m_cells':canopy},
                     outputs={'treetops':tops,'csv':str(root/'city-treetops.csv')},
                     quality_status='PRELIMINARY_UNVALIDATED; known classification and detection errors remain',
                     parcel_tax_years=inputs['parcel_attributes']['tax_year'],
                     public_breakdown=dict(collections.Counter(group for category,group,n in assigned if category=='PUBLIC_GOVERNMENT')),
                     multiple_parcel_matches=sum(n>1 for category,group,n in assigned))
        state['seconds']=state['finished']-state['started'];save()
        print(json.dumps({k:state[k] for k in ['status','city_treetops','ownership_totals','observation','outputs','seconds']},indent=2),flush=True)
    except Exception as exc:
        state.update(status='failed',error=str(exc),finished=time.time());save();raise


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--raster-worker':
        job=json.loads(Path(sys.argv[2]).read_text())
        r,c,core,buffered=job['tile'];tile=Tile(r,c,Extent(*core),Extent(*buffered))
        _,core_path,seconds=raster_core(job['lasd'],tile,job['folder'],job['source_id'],job['ground_raster'])
        common.write_json(Path(job['folder'])/'result.json',{'core_path':core_path,'seconds':seconds})
    else:main()
