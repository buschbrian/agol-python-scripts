"""Recover city working copies with raster-ground height classification.

Point-ground classification failed on 12TVL2503 and crashed on 12TVL2303.
Ground raster construction and SURFACE classification succeeded on 2503.
Build class-2 ground in parallel while LAS files are read-only, then classify
disjoint working files in fresh processes. Preserve all bytes except classification.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import time

import arcpy
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from canopy import common, hag, licensing, las_records


def build_ground(path, lasd, folder):
    info=las_records.header(path)
    core=hag.snap_out(info['extent'])
    bounds=hag.snap_out([core[0]-50,core[1]-50,core[2]+50,core[3]+50])
    folder=Path(folder)
    record_file=folder/'record.json'
    if record_file.exists():return json.loads(record_file.read_text())
    folder.mkdir(exist_ok=True)
    # A native crash may leave a partial TIFF. Keep it, but use a new attempt.
    attempt=folder/f'attempt-{len(list(folder.glob("attempt-*")))+1:03d}'
    with licensing.extensions('3D','Spatial'):
        ground=hag.raster_builder(lasd,6341)(attempt,bounds)
        core_path=str(folder/'core_ground.tif')
        with common.environment(ground.record['raster']['path']):
            arcpy.management.Clip(ground.record['raster']['path'],' '.join(map(str,core)),core_path,
                                  nodata_value='-9999',maintain_clipping_extent='NO_MAINTAIN_EXTENT')
    row={'tile':Path(path).stem,'ground':ground.record,'core':core,'core_ground':core_path}
    common.write_json(record_file,row)
    return row


def protected_hash(path):
    info=las_records.header(path)
    if info['format']!=6:raise ValueError('This recovery is validated only for point format 6')
    h=hashlib.sha256()
    with open(path,'rb') as handle:
        h.update(handle.read(info['offset']))
        left=info['points']
        while left:
            n=min(left,500000)
            block=np.frombuffer(handle.read(n*info['record_length']),dtype='uint8').copy().reshape(n,info['record_length'])
            block[:,16]=0
            h.update(block.tobytes());left-=n
        for block in iter(lambda:handle.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def fresh_ground(path, lasd, folder):
    record=Path(folder)/'record.json'
    if not record.exists():
        result=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--ground-worker',path,lasd,folder],
                              stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
        if result.returncode:
            raise RuntimeError(f'Ground worker {Path(path).stem} exited {result.returncode}: {result.stderr}')
    return json.loads(record.read_text())


def reset_partial_height(path, before, backup):
    if any(str(code) in before['classes'] for code in (3,4,5)):
        raise ValueError('Delivered vegetation must not be reset')
    points,scale,offset,modern,info=las_records.records(path,mode='r+')
    if not modern or info['format']!=6:raise ValueError('Expected validated modern class-byte layout')
    if not backup.exists():
        with open(backup,'wb') as handle:
            for start in range(0,len(points),1000000):
                handle.write(points['classification'][start:start+1000000].tobytes())
    elif backup.stat().st_size!=len(points):raise ValueError('Class backup point count differs')
    # A retry starts from the saved class bytes, then removes only provisional
    # height codes which were absent before the failed native height step.
    saved=np.memmap(backup,mode='r',dtype='uint8',shape=(len(points),))
    changed=0
    for start in range(0,len(points),1000000):
        old=np.array(saved[start:start+1000000])
        clear=np.isin(old,[3,4,5]);changed+=int(clear.sum());old[clear]=1
        points['classification'][start:start+len(old)]=old
    points.flush();del points,saved
    return changed


def height_job(job):
    path=Path(job['path']);work=Path(job['work']);start=time.time()
    before_hash=protected_hash(path)
    reset=reset_partial_height(path,job['before'],work/'classes-before-surface'/(path.stem+'.bin'))
    lasd=str(work/(path.stem+'.lasd'))
    with licensing.extensions('3D','Spatial'):
        if not arcpy.Exists(lasd):
            arcpy.management.CreateLasDataset([str(path)],lasd,compute_stats='COMPUTE_STATS')
        arcpy.ddd.ClassifyLasByHeight(lasd,'SURFACE',[[3,.5],[4,2],[5,80]],noise='NONE',
                                     compute_stats='COMPUTE_STATS',in_surface=job['ground'])
    after_hash=protected_hash(path)
    if before_hash!=after_hash:raise ValueError('Protected source bytes changed during height recovery')
    row={'tile':path.stem,'seconds':time.time()-start,'provisional_height_labels_reset':reset,
         'protected_sha256_before':before_hash,'protected_sha256_after':after_hash}
    common.write_json(work/'height-results'/(path.stem+'.json'),row)
    return row


def fresh_height(path, before, work, ground):
    job=Path(work)/'height-results'/(Path(path).stem+'.job.json')
    common.write_json(job,{'path':path,'before':before,'work':work,'ground':ground})
    result=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--height-job',str(job)],
                          stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
    if result.returncode:
        raise RuntimeError(f'Height worker {Path(path).stem} exited {result.returncode}: {result.stderr}')
    return json.loads(job.with_name(Path(path).stem+'.json').read_text())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path);parser.add_argument('--workers',type=int,choices=[1,2,3],default=2)
    args=parser.parse_args();root=args.root.resolve();prepared=root/'prepared'
    manifest=prepared/'preparation.json';state=json.loads(manifest.read_text())
    original=json.loads((prepared/'preparation.before-height-recovery.json').read_text())
    if 'ClassifyLasByHeight' not in original.get('error','') or state['status']=='complete':
        raise ValueError('Expected preserved native height failure')
    work=root/'raster-ground-recovery';work.mkdir(exist_ok=True)
    files=sorted((prepared/'points').glob('*.las'))
    if not files or any(prepared.resolve() not in p.resolve().parents for p in files):
        raise ValueError('Expected isolated working-copy files')
    recovery={'status':'building ground rasters','code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'grounds':{},'height':{},'thresholds':[[3,.5],[4,2],[5,80]],'noise':'NONE'}
    def save():common.write_json(work/'progress.json',recovery)
    state['status']='recovering height with raster ground';common.write_json(manifest,state);save()
    try:
        bootstrap=str(work/'ground-source.lasd')
        if not arcpy.Exists(bootstrap):
            arcpy.management.CreateLasDataset([str(p) for p in files],bootstrap,compute_stats='COMPUTE_STATS')
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures=[pool.submit(fresh_ground,str(p),bootstrap,str(work/p.stem)) for p in files]
            for future in as_completed(futures):
                row=future.result();recovery['grounds'][row['tile']]=row;save()
                print(f'Ground {len(recovery["grounds"])}/{len(files)} {row["tile"]}',flush=True)
        recovery['status']='classifying height from raster ground';save()
        backups=work/'classes-before-surface';backups.mkdir(exist_ok=True)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures=[pool.submit(fresh_height,str(path),state['before'][path.name],str(work),
                                 recovery['grounds'][path.stem]['ground']['raster']['path']) for path in files]
            for future in as_completed(futures):
                row=future.result();recovery['height'][row['tile']]=row;save()
                print(f'Height {len(recovery["height"])}/{len(files)} {row["tile"]}: {row["seconds"]:.1f}s',flush=True)
        sr=arcpy.Describe(bootstrap).spatialReference
        ground_mosaic=str(work/'ground_mosaic.tif')
        if not arcpy.Exists(ground_mosaic):
            arcpy.management.MosaicToNewRaster([recovery['grounds'][p.stem]['core_ground'] for p in files],
                                               str(work),'ground_mosaic.tif',sr,'32_BIT_FLOAT',.5,1,'FIRST','FIRST')
        refreshed=str(work/'prepared-surface.lasd')
        if not arcpy.Exists(refreshed):
            arcpy.management.CreateLasDataset([str(p) for p in files],refreshed,compute_stats='COMPUTE_STATS')
        state['after']={p.name:las_records.class_counts(p) for p in files}
        for row in state['sources']:
            stat=Path(row['path']).stat()
            if (stat.st_size,stat.st_mtime_ns)!=(row['bytes'],row['mtime_ns']):raise ValueError('Original source changed')
        state['source_id']=hashlib.sha256(json.dumps([(r['path'],r['bytes'],r['mtime_ns']) for r in state['sources']]).encode()).hexdigest()[:24]
        state['working_lasd']=refreshed;state['height_recovery']=recovery
        state['steps'].append('Height classified with native SURFACE mode from shared class-2 ground; protected bytes verified')
        state['quality_status']='PRELIMINARY_UNVALIDATED';state['status']='complete';state.pop('error',None)
        inputs=json.loads((root/'inputs.json').read_text());inputs['ground_mosaic']=ground_mosaic
        common.write_json(root/'inputs.json',inputs)
        recovery['status']='complete';save();common.write_json(manifest,state)
        print('Raster-ground height recovery complete',flush=True)
    except Exception as exc:
        recovery.update(status='failed',error=str(exc));save()
        state.update(status='failed',error=str(exc));common.write_json(manifest,state);raise


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--ground-worker':
        build_ground(*sys.argv[2:5])
    elif len(sys.argv)>1 and sys.argv[1]=='--height-job':
        height_job(json.loads(Path(sys.argv[2]).read_text()))
    else:main()
