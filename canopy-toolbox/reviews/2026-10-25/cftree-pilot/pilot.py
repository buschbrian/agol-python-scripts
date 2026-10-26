"""Bounded CFTree feasibility pilot on classified Millcreek ALS, using unmodified upstream modules.

Runs C++ tools through WSL and Python geometry/metrics in the existing Pro environment.
Only writes beneath --output (which must be new). No uploads, source edits or full-city run.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

REVISION = '13be34b412a2f83f3ec1c89487665120348bb9d9'
CORE = [428100., 4504100., 428300., 4504300.]
HALO_M = 20.


def wsl_path(path):
    p = Path(path).resolve()
    if p.drive.upper() != 'C:':
        raise ValueError('Pilot WSL inputs must be staged in the C: workspace')
    return '/mnt/c/' + p.as_posix()[3:]


def binary(tool, arguments, logfile, timeout):
    result = subprocess.run(['wsl', '-d', 'Ubuntu', '--', wsl_path(tool), *arguments],
                            capture_output=True, timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
    logfile.write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f'{tool.name} failed; see {logfile}')


def geometry_metrics(mesh, dtm, offset):
    """Use upstream crown/trunk calculations; skip CFD-only voxel/ray calculations for visualization."""
    from src.reconstruction.extract_tree_metrics import (
        _compute_crown_metrics, compute_trunk_base_from_dtm, estimate_trunk_dimensions)
    width, local_median = _compute_crown_metrics(mesh)
    median = local_median + offset[2]
    base = compute_trunk_base_from_dtm(mesh, dtm, offset)
    if base is None:
        raise ValueError('No terrain support beneath the crown')
    height, diameter, radius = estimate_trunk_dimensions(width, median, base[2])
    return {'status':'ok', 'crown':{'CW_m':width,'median_z':median,'r50_m':None,'porosity':None},
            'trunk':{'H_m':height,'DBH_m':diameter,'r_trunk':radius,'base_xyz':base.tolist()}}


def run(a):
    if a.python_deps:
        sys.path.insert(0,str(a.python_deps))
    import laspy
    import numpy as np
    import rasterio
    from rasterio.windows import from_bounds
    import trimesh
    assert subprocess.check_output(['git', '-C', str(a.repository), 'rev-parse', 'HEAD'], text=True).strip() == REVISION
    sys.path.insert(0, str(a.repository))
    from src.reconstruction.extract_tree_metrics import compute_tree_metrics
    from src.reconstruction.construct_geometry import construct_lod3
    from src.reconstruction.write_cityjson import init_cityjson, add_tree, finalize_cityjson
    a.output.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    xmin, ymin, xmax, ymax = CORE
    bounds = [xmin-HALO_M, ymin-HALO_M, xmax+HALO_M, ymax+HALO_M]
    staged_dtm = a.output/'terrain_m.tif'
    with rasterio.open(a.terrain) as src:
        assert src.crs.to_epsg() == 6341
        window = from_bounds(*bounds, src.transform).round_offsets().round_lengths()
        dem = src.read(1, window=window, masked=True)
        transform = src.window_transform(window)
        profile = src.profile.copy()
        profile.update(width=dem.shape[1], height=dem.shape[0], transform=transform, compress='deflate')
        with rasterio.open(staged_dtm, 'w', **profile) as dst:
            dst.write(dem.filled(src.nodata), 1)
    kept = []
    edge_points_excluded = 0
    with laspy.open(a.las) as las:
        crs = las.header.parse_crs()
        horizontal = crs.sub_crs_list[0] if crs.is_compound else crs
        assert horizontal.to_epsg() == 6341
        for chunk in las.chunk_iterator(1_000_000):
            x, y, z = np.asarray(chunk.x), np.asarray(chunk.y), np.asarray(chunk.z)
            mask = np.isin(np.asarray(chunk.classification), [3,4,5])
            mask &= ~np.asarray(chunk.withheld,dtype=bool) & ~np.asarray(chunk.synthetic,dtype=bool) & ~np.asarray(chunk.overlap,dtype=bool)
            mask &= (x>=bounds[0]) & (x<bounds[2]) & (y>=bounds[1]) & (y<bounds[3])
            indices = np.flatnonzero(mask)
            rr, cc = rasterio.transform.rowcol(transform, x[indices], y[indices])
            rr, cc = np.asarray(rr), np.asarray(cc)
            within = (rr>=0) & (rr<dem.shape[0]) & (cc>=0) & (cc<dem.shape[1])
            edge_points_excluded += int((~within).sum())
            indices, rr, cc = indices[within], rr[within], cc[within]
            ground = dem[rr, cc]
            good = ~np.ma.getmaskarray(ground) & (z[indices]-ground.data>=2.0)
            indices = indices[good]
            if len(indices):
                kept.append(np.column_stack((x[indices],y[indices],z[indices])))
    points = np.concatenate(kept)
    assert np.isfinite(points).all() and len(points)>50
    xyz = a.output/'vegetation.xyz'
    np.savetxt(xyz, points, fmt='%.6f')
    seg = a.output/'segmentation.xyz'
    binary(a.repository/'src/segmentation/TreeSeparation/build/segmentation',
           [wsl_path(xyz),wsl_path(seg),'2.5','1.5','3'],a.output/'segmentation.log',180)
    segments = np.loadtxt(seg)
    assert segments.ndim == 2 and segments.shape[1] == 4 and np.isfinite(segments).all()
    ids, counts = np.unique(segments[:,0].astype(int),return_counts=True)
    candidates = []
    for tid, count in zip(ids,counts):
        if count<50:
            continue
        pts = segments[segments[:,0]==tid,1:]
        top = pts[np.argmax(pts[:,2])]
        if xmin<=top[0]<xmax and ymin<=top[1]<ymax:
            candidates.append((int(tid),pts))
    # First IDs in deterministic segmentation order; limited for a bounded feasibility trial.
    selected = candidates[:a.max_trees]
    city = init_cityjson()
    results = []
    for tid, pts in selected:
        begin = time.monotonic()
        offset = pts.mean(axis=0)
        local = pts-offset
        tree_dir = a.output/f'tree_{tid}'
        tree_dir.mkdir()
        tree_xyz = tree_dir/'points.xyz'
        np.savetxt(tree_xyz,local,fmt='%.6f')
        ply = tree_dir/'crown.ply'
        binary(a.repository/'src/reconstruction/AlphaWrap/build/awrap_points',
               [wsl_path(tree_xyz),'15','50',wsl_path(ply)],tree_dir/'alpha-wrap.log',120)
        mesh = trimesh.load(str(ply),force='mesh')
        assert np.isfinite(mesh.vertices).all() and mesh.is_watertight and len(mesh.faces)>0
        metrics = compute_tree_metrics(mesh,local,staged_dtm,offset) if a.cfd_metrics else geometry_metrics(mesh,staged_dtm,offset)
        assert metrics['status']=='ok'
        gtid = 280400000+tid
        geometry = construct_lod3(mesh,metrics,offset,gtid=gtid,tile_id='12TVL2804-pilot')
        assert len(geometry['components']) == 2, 'Crown and trunk required for pilot output'
        ground_z = metrics['trunk']['base_xyz'][2]
        height_m = float(pts[:,2].max()-ground_z)
        attributes = geometry['attributes']
        attributes.update(height_ft=height_m/.3048, crown_width_ft=metrics['crown']['CW_m']/.3048,
                          modelled_trunk_diameter_ft=metrics['trunk']['DBH_m']/.3048,
                          model='CFTree', validation='unvalidated planning estimate',
                          trunk_method='allometry and terrain; not measured', source_points=len(pts))
        for comp in geometry['components']:
            comp['lod']='3'
            model = trimesh.Trimesh(comp['vertices_local'],comp['faces'],process=False)
            assert model.is_watertight and np.isfinite(model.vertices).all()
            model.export(str(tree_dir/(comp['role']+'_meters.obj')))
            model.apply_scale(1/.3048)
            model.export(str(tree_dir/(comp['role']+'_feet.obj')))
        add_tree(city,gtid,geometry['components'],offset,attributes)
        result = dict(segment_id=tid,gtid=gtid,source_points=len(pts),height_ft=height_m/.3048,
                      crown_width_ft=metrics['crown']['CW_m']/.3048,crown_faces=len(mesh.faces),
                      crown_vertices=len(mesh.vertices),watertight=True,origin_m=offset.tolist(),
                      seconds=round(time.monotonic()-begin,2))
        results.append(result)
        print(json.dumps(result),flush=True)
    assert len(results)==len(selected)>0
    final = finalize_cityjson(city,crs='EPSG:6341')
    final['metadata']['title']='Millcreek CFTree neighborhood feasibility pilot'
    final['metadata']['abstract']='Unvalidated planning estimates. XY NAD83(2011)/UTM12N; Z NAVD88 Geoid18 in meters. Trunks are modelled, not measured.'
    final['metadata'].pop('presentLoDs',None)
    decoded = np.asarray(final['vertices'])*final['transform']['scale']+final['transform']['translate']
    assert np.isfinite(decoded).all()
    for obj in final['CityObjects'].values():
        for geom in obj['geometry']:
            assert geom['lod']=='3'
            for shell in geom['boundaries']:
                for face in shell:
                    for ring in face:
                        assert len(ring)==3 and min(ring)>=0 and max(ring)<len(decoded)
    citypath = a.output/'millcreek_cftree_pilot.city.json'
    citypath.write_text(json.dumps(final,allow_nan=False,separators=(',',':')),encoding='utf-8')
    manifest = dict(upstream_repository='https://github.com/NoahAlting/CFTree',upstream_commit=REVISION,
        source_las=str(a.las),source_terrain=str(a.terrain),core_bounds_m=CORE,halo_m=HALO_M,
        input_points=len(points),cropped_terrain_edge_points_excluded=edge_points_excluded,
        segmented_points=len(segments),segments=len(ids),eligible_core_segments=len(candidates),
        reconstructed=len(results),trees=results,seconds=round(time.monotonic()-start,2),
        segmentation_parameters=dict(radius_m=2.5,vertical_resolution_m=1.5,min_points_per_cluster=3),
        wrapping_parameters=dict(ralpha=15,roffset=50),metrics_mode='cfd' if a.cfd_metrics else 'geometry',
        adaptation='Existing refined classes 3/4/5 and HAG >=2 m replace AHN acquisition and HOMED. CFTree segmentation, wrapping, metrics and geometry retained.',
        limitations=['Bounded pilot, not a full city run or tree census','20 m halo is not seam validation',
                     'Trunk locations and diameters are inferred','No field accuracy assessment',
                     'CityJSON finite coordinates, references, LoD strings and closed meshes checked; full schema validation pending'],
        cityjson_sha256=hashlib.sha256(citypath.read_bytes()).hexdigest())
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False)+'\n')
    print('Completed',len(results),'CFTree trees; manifest saved.',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repository',type=Path,required=True)
    p.add_argument('--python-deps',type=Path,help='Isolated trimesh dependency directory; does not modify Pro')
    p.add_argument('--las',type=Path,required=True)
    p.add_argument('--terrain',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--max-trees',type=int,default=12)
    p.add_argument('--cfd-metrics',action='store_true',help='Also compute costly porosity/r50 metrics; omitted for visualization')
    run(p.parse_args())
