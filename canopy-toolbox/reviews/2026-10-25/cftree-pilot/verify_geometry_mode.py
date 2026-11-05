"""Compare geometry-only metrics against the full CFD pilot, using the same finished crowns."""
import argparse
import json
import math
from pathlib import Path
import sys
import time

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--pilot',type=Path,required=True)
p.add_argument('--repository',type=Path,required=True)
p.add_argument('--python-deps',type=Path,required=True)
a=p.parse_args()
sys.path[:0]=[str(a.python_deps),str(a.repository)]
import numpy as np
import trimesh
from pilot import geometry_metrics
from src.reconstruction.construct_geometry import construct_lod3

manifest=json.loads((a.pilot/'manifest.json').read_text())
city=json.loads((a.pilot/'millcreek_cftree_pilot.city.json').read_text())
started=time.monotonic()
checked=[]
for tree in manifest['trees']:
    mesh=trimesh.load(str(a.pilot/f'tree_{tree["segment_id"]}'/'crown.ply'),force='mesh')
    offset=np.asarray(tree['origin_m'])
    metrics=geometry_metrics(mesh,a.pilot/'terrain_m.tif',offset)
    geometry=construct_lod3(mesh,metrics,offset,gtid=tree['gtid'],tile_id='12TVL2804-pilot')
    expected=city['CityObjects'][f'T_{tree["gtid"]}']['attributes']
    keys=['crown_width_m','crown_median_z','trunk_H_m','trunk_DBH_m','trunk_radius_m','trunk_base_height_m']
    for name in keys:
        assert math.isclose(geometry['attributes'][name],expected[name],rel_tol=0,abs_tol=1e-8),(tree['gtid'],name)
    assert geometry['attributes']['crown_porosity'] is None and geometry['attributes']['crown_r50_m'] is None
    assert len(geometry['components'])==2
    checked.append(tree['gtid'])
result=dict(trees=len(checked),core_metrics_match_full_cfd=True,absolute_tolerance_m=1e-8,
            geometry_metrics_seconds=round(time.monotonic()-started,3),
            comparison='Recalculation on finished crowns; excludes segmentation and alpha wrapping',
            omitted_fields=['crown_porosity','crown_r50_m'],trimesh_version=trimesh.__version__)
(a.pilot/'geometry-mode-verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
