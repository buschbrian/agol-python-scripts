"""Resumable CFTree city run: immutable inputs, per-tree SQLite checkpoints, local draft outputs.

prepare makes a frozen 61-tile plan. run stages filtered vegetation and processes ready tiles in one
worker while remaining inputs stage. No ArcPy, uploads, publishing or source classification edits.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import uuid

HERE=Path(__file__).resolve().parent
UPSTREAM='13be34b412a2f83f3ec1c89487665120348bb9d9'


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def atomic(p,value):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        tmp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        # A short-lived Windows reader can deny rename while the coordinator reads this status.
        for attempt in range(8):
            try:
                os.replace(tmp,p)
                return
            except PermissionError:
                if attempt==7: raise
                time.sleep(.05*(attempt+1))
    finally:
        tmp.unlink(missing_ok=True)


def setup(c):
    sys.path[:0]=[c['python_deps'],c['repository'],str(HERE.parent/'cftree-pilot')]
    for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
        os.environ[name]='1'


def tile_neighbors(tile,tiles,halo):
    x0,y0,x1,y1=tile['core']
    return [t['id'] for t in tiles if t['core'][0]<x1+halo and t['core'][2]>x0-halo
            and t['core'][1]<y1+halo and t['core'][3]>y0-halo]


def owns(core,point):
    return core[0]<=point[0]<core[2] and core[1]<=point[1]<core[3]


def model_id(point):
    return str(uuid.uuid5(uuid.NAMESPACE_URL,'millcreek-cftree-v1:6341:'+':'.join(f'{float(v):.3f}' for v in point)))


def can_start(active,workers,available,free_disk,min_available,min_disk):
    return active<workers and available>=min_available and free_disk>=min_disk


def prepare(a):
    sys.path.insert(0,a.python_deps)
    import laspy
    tiles=[]
    files=sorted(Path(a.points).glob('*.las'))
    if len(files)!=61:
        raise ValueError(f'Expected 61 refined LAS files, found {len(files)}')
    for f in files:
        with laspy.open(f) as reader:
            h=reader.header
            crs=h.parse_crs(); horizontal=crs.sub_crs_list[0] if crs.is_compound else crs
            assert horizontal.to_epsg()==6341
            x0=400000+int(f.stem[-4:-2])*1000
            y0=4500000+int(f.stem[-2:])*1000
            assert h.mins[0]>=x0-.02 and h.maxs[0]<=x0+1000.02
            assert h.mins[1]>=y0-.02 and h.maxs[1]<=y0+1000.02
            stat=f.stat()
            tiles.append(dict(id=f.stem,path=str(f),bytes=stat.st_size,mtime_ns=stat.st_mtime_ns,
                              point_count=h.point_count,core=[x0,y0,x0+1000,y0+1000]))
    repo=Path(a.repository)
    assert subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()==UPSTREAM
    c=dict(created_utc=now(),repository=str(repo),upstream_commit=UPSTREAM,python_deps=a.python_deps,
           terrain=a.terrain,run_dir=str(a.run_dir),outputs=a.outputs,tiles=tiles,halo_m=100.,
           min_height_m=2.,min_points=50,segmentation=[2.5,1.5,3],wrap=[15,50],workers=1,
           minimum_available_gb=7.,minimum_disk_gb=15.,metrics_mode='geometry',
           source_filter='refined classes 3/4/5; excludes withheld, synthetic and overlap',
           status='draft; seam validation and review pending; no publication')
    c['config_hash']=hashlib.sha256(json.dumps(c,sort_keys=True).encode()).hexdigest()
    a.run_dir.mkdir(parents=True,exist_ok=False)
    atomic(a.run_dir/'config.json',c)
    atomic(a.run_dir/'job.json',dict(status='prepared',tiles=61,staged=0,completed=0,updated_utc=now()))
    print('Prepared 61 tiles,',sum(t['point_count'] for t in tiles),'points; outputs',a.run_dir,flush=True)


def stage(c,t):
    import numpy as np
    import laspy
    import rasterio
    from rasterio.windows import from_bounds
    root=Path(c['run_dir'])/'staged'; root.mkdir(exist_ok=True)
    done=root/(t['id']+'.json'); output=root/(t['id']+'.npy')
    if done.exists() and output.exists():
        rec=read(done)
        assert rec['config_hash']==c['config_hash'] and output.stat().st_size==rec['npy_bytes']
        return
    f=Path(t['path']); stat=f.stat()
    assert (stat.st_size,stat.st_mtime_ns)==(t['bytes'],t['mtime_ns']), 'Input changed since plan'
    with rasterio.open(c['terrain']) as src:
        assert src.crs.to_epsg()==6341
        w=from_bounds(*t['core'],src.transform).round_offsets().round_lengths()
        dem=src.read(1,window=w,boundless=True,masked=True)
        transform=src.window_transform(w)
    arrays=[]; seen=0; missing_ground=0
    with laspy.open(f) as reader:
        for chunk in reader.chunk_iterator(500_000):
            seen+=len(chunk)
            x,y,z=np.asarray(chunk.x),np.asarray(chunk.y),np.asarray(chunk.z)
            keep=np.isin(np.asarray(chunk.classification),[3,4,5])
            keep &= ~np.asarray(chunk.withheld,dtype=bool)&~np.asarray(chunk.overlap,dtype=bool)&~np.asarray(chunk.synthetic,dtype=bool)
            indices=np.flatnonzero(keep)
            rr,cc=rasterio.transform.rowcol(transform,x[indices],y[indices]); rr,cc=np.asarray(rr),np.asarray(cc)
            valid=(rr>=0)&(rr<dem.shape[0])&(cc>=0)&(cc<dem.shape[1])
            indices,rr,cc=indices[valid],rr[valid],cc[valid]
            ground=dem[rr,cc]
            known=~np.ma.getmaskarray(ground)&np.isfinite(ground.data)
            missing_ground+=int((~known).sum())
            indices=indices[known&(z[indices]-ground.data>=c['min_height_m'])]
            if len(indices): arrays.append(np.column_stack((x[indices],y[indices],z[indices])))
    assert seen==t['point_count']
    points=np.concatenate(arrays) if arrays else np.empty((0,3),dtype='float64')
    assert np.isfinite(points).all()
    temp=output.with_suffix('.npy.tmp')
    with temp.open('wb') as stream: np.save(stream,points,allow_pickle=False)
    os.replace(temp,output)
    atomic(done,dict(tile=t['id'],source_points=seen,vegetation_points=len(points),unknown_ground_points=missing_ground,
        config_hash=c['config_hash'],npy_bytes=output.stat().st_size,
        selected_xyz_sha256=hashlib.sha256(points.tobytes()).hexdigest(),completed_utc=now()))


def process_tile(c,t):
    setup(c)
    import numpy as np
    import rasterio
    from rasterio.windows import from_bounds
    import trimesh
    from pilot import binary,wsl_path,geometry_metrics
    from src.reconstruction.construct_geometry import construct_lod3
    from src.reconstruction.write_cityjson import init_cityjson,add_tree,finalize_cityjson
    run=Path(c['run_dir']); out=run/'tiles'/t['id']; out.mkdir(parents=True,exist_ok=True)
    status_path=out/'status.json'
    def status(state,**kw):
        atomic(status_path,dict(tile=t['id'],state=state,updated_utc=now(),config_hash=c['config_hash'],**kw))
    status('assembling_halo')
    h=c['halo_m']; x0,y0,x1,y1=t['core']; bounds=[x0-h,y0-h,x1+h,y1+h]
    dtm=out/'terrain_m.tif'
    if not dtm.exists():
        with rasterio.open(c['terrain']) as src:
            w=from_bounds(*bounds,src.transform).round_offsets().round_lengths()
            dem=src.read(1,window=w,boundless=True,masked=True)
            profile=src.profile.copy(); profile.update(width=dem.shape[1],height=dem.shape[0],transform=src.window_transform(w),compress='deflate')
            with rasterio.open(dtm,'w',**profile) as dst: dst.write(dem.filled(src.nodata),1)
    seg=out/'segmentation.xyz'
    if not seg.exists():
        parts=[]
        for neighbor in t['neighbors']:
            points=np.load(run/'staged'/(neighbor+'.npy'),mmap_mode='r')
            keep=(points[:,0]>=bounds[0])&(points[:,0]<bounds[2])&(points[:,1]>=bounds[1])&(points[:,1]<bounds[3])
            parts.append(np.asarray(points[keep]))
        points=np.concatenate(parts)
        if len(points)<c['min_points']:
            status('complete',models=0,rejected=0,reason='insufficient vegetation points'); return
        xyz=out/'vegetation.xyz'; np.savetxt(xyz,points,fmt='%.6f')
        status('segmenting',input_points=len(points))
        temp=out/'segmentation.xyz.tmp'
        binary(Path(c['repository'])/'src/segmentation/TreeSeparation/build/segmentation',
            [wsl_path(xyz),wsl_path(temp),*[str(v) for v in c['segmentation']]],out/'segmentation.log',7200)
        os.replace(temp,seg)
        del points,parts
    status('reading_segments')
    rows=np.loadtxt(seg,ndmin=2)
    assert rows.shape[1]==4 and np.isfinite(rows).all()
    order=np.argsort(rows[:,0],kind='stable'); rows=rows[order]
    ids,starts,counts=np.unique(rows[:,0].astype('int64'),return_index=True,return_counts=True)
    db=sqlite3.connect(out/'models.sqlite',timeout=60)
    db.execute('CREATE TABLE IF NOT EXISTS models (id TEXT PRIMARY KEY, segment INTEGER, payload BLOB, status TEXT, reason TEXT)')
    db.commit()
    finished={r[0] for r in db.execute('SELECT id FROM models')}
    completed=sum(1 for _ in db.execute("SELECT 1 FROM models WHERE status='ok'"))
    rejected=sum(1 for _ in db.execute("SELECT 1 FROM models WHERE status='rejected'"))
    seen=0; started=time.monotonic(); last_report=0
    for tid,index,count in zip(ids,starts,counts):
        if count<c['min_points']: continue
        pts=rows[index:index+count,1:]
        # Deterministic highest return, with XY tie breaking; no ownership claim from a finite halo.
        top=pts[np.lexsort((pts[:,0],pts[:,1],-pts[:,2]))[0]]
        if not owns(t['core'],top): continue
        ident=model_id(top); seen+=1
        if ident in finished: continue
        try:
            offset=pts.mean(axis=0); local=pts-offset
            xyz=out/'current_tree.xyz'; ply=out/'current_crown.ply'
            np.savetxt(xyz,local,fmt='%.6f')
            binary(Path(c['repository'])/'src/reconstruction/AlphaWrap/build/awrap_points',
                [wsl_path(xyz),*[str(v) for v in c['wrap']],wsl_path(ply)],out/'current_wrap.log',120)
            mesh=trimesh.load(str(ply),force='mesh')
            if not mesh.is_watertight or not np.isfinite(mesh.vertices).all(): raise ValueError('Crown is not finite and closed')
            metrics=geometry_metrics(mesh,dtm,offset)
            geometry=construct_lod3(mesh,metrics,offset,gtid=ident,tile_id=t['id'])
            if len(geometry['components'])!=2: raise ValueError('Crown and inferred trunk required')
            for comp in geometry['components']:
                comp['lod']='3'
                m=trimesh.Trimesh(comp['vertices_local'],comp['faces'],process=False)
                if not m.is_watertight or not np.isfinite(m.vertices).all(): raise ValueError('Component is not finite and closed')
            edge=min(top[0]-x0,x1-top[0],top[1]-y0,y1-top[1])
            attrs=geometry['attributes']
            attrs.update(model='CFTree',validation='unvalidated planning estimate',
                height_ft=float((top[2]-metrics['trunk']['base_xyz'][2])/.3048),crown_width_ft=float(metrics['crown']['CW_m']/.3048),
                modelled_trunk_diameter_ft=float(metrics['trunk']['DBH_m']/.3048),source_points=int(count),
                edge_review=bool(edge<h),core_edge_distance_ft=float(edge/.3048),
                trunk_method='allometry and terrain; inferred, not measured')
            city=init_cityjson(); add_tree(city,ident,geometry['components'],offset,attrs)
            encoded=json.dumps(city,allow_nan=False,separators=(',',':')).encode()
            db.execute('INSERT INTO models VALUES (?,?,?,?,?)',(ident,int(tid),gzip.compress(encoded),'ok',''))
            completed+=1
        except Exception as exc:
            reason=f'{type(exc).__name__}: {exc}'[:1000]
            db.execute('INSERT INTO models VALUES (?,?,?,?,?)',(ident,int(tid),None,'rejected',reason))
            rejected+=1
        db.commit()
        finished.add(ident)
        if time.monotonic()-last_report>10:
            status('reconstructing',models=completed,rejected=rejected,core_candidates_seen=seen,total_segments=len(ids),elapsed_seconds=round(time.monotonic()-started))
            last_report=time.monotonic()
    status('exporting',models=completed,rejected=rejected)
    shard=init_cityjson(); shard_number=0; shard_count=0
    def save_shard():
        nonlocal shard,shard_number,shard_count
        if not shard_count: return
        final=finalize_cityjson(shard,crs='EPSG:6341')
        final['metadata'].pop('presentLoDs',None)
        final['metadata']['title']='Millcreek CFTree draft '+t['id']
        final['metadata']['abstract']='Planning estimate. XY EPSG6341; Z NAVD88 Geoid18 meters. Trunks inferred. Seam review pending.'
        dest=out/f'trees_{shard_number:04d}.city.json.gz'; tmp=dest.with_suffix('.gz.tmp')
        with gzip.open(tmp,'wt',encoding='utf8') as stream: json.dump(final,stream,allow_nan=False,separators=(',',':'))
        os.replace(tmp,dest); shard_number+=1; shard_count=0; shard=init_cityjson()
    for ident,payload in db.execute("SELECT id,payload FROM models WHERE status='ok' ORDER BY id"):
        one=json.loads(gzip.decompress(payload)); base=len(shard['vertices'])
        obj=one['CityObjects']['T_'+ident]
        for geom in obj['geometry']:
            for shell in geom['boundaries']:
                for face in shell:
                    for ring in face:
                        for i in range(len(ring)): ring[i]+=base
        shard['vertices'].extend(one['vertices']); shard['CityObjects']['T_'+ident]=obj; shard_count+=1
        if shard_count>=250: save_shard()
    save_shard(); db.close()
    status('complete_with_rejections' if rejected else 'complete',models=completed,rejected=rejected,
           cityjson_shards=shard_number,seam_review='pending',completed_utc=now())


def progress(c,phase):
    run=Path(c['run_dir']); statuses={}
    for t in c['tiles']:
        path=run/'tiles'/t['id']/'status.json'
        statuses[t['id']]=read(path) if path.exists() else dict(state='queued')
    value=dict(updated_utc=now(),phase=phase,tiles=61,staged=len(list((run/'staged').glob('*.json'))) if (run/'staged').exists() else 0,
               completed=sum(v['state'] in ('complete','complete_with_rejections') for v in statuses.values()),
               failed=sum(v['state']=='failed' for v in statuses.values()),models=sum(v.get('models',0) for v in statuses.values()),
               rejected=sum(v.get('rejected',0) for v in statuses.values()),tile_status=statuses,run_dir=str(run),
               metrics_mode='geometry',halo_m=c['halo_m'],execution=c.get('execution'),
               publication='local draft; seam reconciliation and review pending')
    atomic(run/'job.json',value); atomic(Path(c['outputs'])/'cftree-city-progress.json',value)


def run(a):
    c=read(a.run_dir/'config.json'); setup(c)
    import psutil
    import shutil
    lock=a.run_dir/'runner.lock'
    if lock.exists():
        old=read(lock)
        if psutil.pid_exists(old['pid']): raise RuntimeError('Run is already active')
        lock.unlink()
    with lock.open('x') as stream: json.dump(dict(pid=os.getpid(),started_utc=now()),stream)
    awake=False
    if a.keep_awake:
        import ctypes
        awake=bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000001))
        if not awake:
            lock.unlink()
            raise OSError('Could not keep the system awake for the overnight run')
    c['execution']=dict(workers=a.workers,keep_awake=awake,pid=os.getpid(),started_utc=now(),
        config_hash=c['config_hash'],driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    atomic(a.run_dir/'execution.json',c['execution'])
    tiles=c['tiles']; byid={t['id']:t for t in tiles}
    for t in tiles: t['neighbors']=tile_neighbors(t,tiles,c['halo_m'])
    # Pilot neighborhood and neighbors first; then every remaining LAS tile exactly once.
    priority=tile_neighbors(byid['12TVL2804'],tiles,c['halo_m'])
    ordered=sorted(tiles,key=lambda t:(t['id'] not in priority,t['id']))
    futures={}; submitted=set()
    def reap():
        for fut,t in list(futures.items()):
            if not fut.done(): continue
            try: fut.result()
            except Exception as exc:
                atomic(a.run_dir/'tiles'/t['id']/'status.json',dict(tile=t['id'],state='failed',reason=f'{type(exc).__name__}: {exc}',updated_utc=now()))
            del futures[fut]
    def schedule(pool):
        reap()
        if not can_start(len(futures),a.workers,psutil.virtual_memory().available,
                         shutil.disk_usage(a.run_dir).free,c['minimum_available_gb']*1e9,
                         c['minimum_disk_gb']*1e9): return
        for t in ordered:
            if t['id'] in submitted: continue
            status=a.run_dir/'tiles'/t['id']/'status.json'
            if status.exists() and read(status)['state'] in ('complete','complete_with_rejections'):
                submitted.add(t['id']); continue
            if all((a.run_dir/'staged'/(n+'.json')).exists() for n in t['neighbors']):
                futures[pool.submit(process_tile,c,t)]=t; submitted.add(t['id']); break
    try:
        with ProcessPoolExecutor(max_workers=a.workers) as pool:
            for t in ordered:
                stage_done=a.run_dir/'staged'/(t['id']+'.json')
                if stage_done.exists():
                    stage(c,t); schedule(pool); continue
                while psutil.virtual_memory().available<4e9 or shutil.disk_usage(a.run_dir).free<c['minimum_disk_gb']*1e9:
                    reap(); progress(c,'waiting_for_resources'); time.sleep(15)
                progress(c,'staging '+t['id']); stage(c,t); schedule(pool)
            while len(submitted)<61 or futures:
                schedule(pool); progress(c,'processing'); time.sleep(10)
        progress(c,'processing finished; seam reconciliation and review pending')
    except Exception as exc:
        progress(c,'stopped_on_error')
        record=read(a.run_dir/'job.json'); record['coordinator_error']=f'{type(exc).__name__}: {exc}'
        atomic(a.run_dir/'job.json',record); atomic(Path(c['outputs'])/'cftree-city-progress.json',record)
        raise
    finally:
        if awake:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        lock.unlink(missing_ok=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('step',choices=['prepare','run'])
    p.add_argument('--run-dir',type=Path,required=True)
    p.add_argument('--repository')
    p.add_argument('--python-deps')
    p.add_argument('--points')
    p.add_argument('--terrain')
    p.add_argument('--outputs')
    p.add_argument('--workers',type=int,choices=range(1,5),default=1,
                   help='Concurrent tiles; input/method configuration and checkpoints remain unchanged')
    p.add_argument('--keep-awake',action='store_true',help='Keep Windows awake for this process lifetime')
    a=p.parse_args()
    prepare(a) if a.step=='prepare' else run(a)
