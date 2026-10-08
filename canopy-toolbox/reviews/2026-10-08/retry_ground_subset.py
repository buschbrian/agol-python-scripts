"""Retry one native ground failure with only spatially relevant point files."""
import importlib.util
import json
from pathlib import Path
import sys
import arcpy
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from canopy import common,hag,las_records

root=Path(sys.argv[1]);tile=sys.argv[2]
work=root/'raster-ground-recovery'
core=hag.snap_out(las_records.header(root/'prepared/points'/f'{tile}.las')['extent'])
bounds=hag.snap_out([core[0]-50,core[1]-50,core[2]+50,core[3]+50])
files=[]
for path in sorted((root/'prepared/points').glob('*.las')):
    a,b,c,d=las_records.header(path)['extent']
    if a<=bounds[2] and c>=bounds[0] and b<=bounds[3] and d>=bounds[1]:files.append(str(path))
lasd=str(work/f'{tile}-neighbors.lasd')
if not arcpy.Exists(lasd):arcpy.management.CreateLasDataset(files,lasd,compute_stats='COMPUTE_STATS')
arcpy.management.LasDatasetStatistics(lasd,'OVERWRITE_EXISTING_STATS')
common.write_json(work/f'{tile}-neighbors.json',{'files':files,'bounds':bounds,'lasd':lasd})
spec=importlib.util.spec_from_file_location('recover',Path(__file__).with_name('recover_city_ground.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
row=module.build_ground(str(root/'prepared/points'/f'{tile}.las'),lasd,str(work/tile))
print(json.dumps(row,indent=2),flush=True)
