"""Register the review package with the existing one-item, private-only uploader."""
import argparse
import importlib.util
from pathlib import Path
from types import SimpleNamespace

p=argparse.ArgumentParser()
p.add_argument('--gdb',type=Path,required=True)
p.add_argument('--go',action='store_true')
a=p.parse_args()
here=Path(__file__).resolve().parent
path=here.parents[1]/'2026-10-22/hosting/upload/upload.py'
spec=importlib.util.spec_from_file_location('hosting_upload',path)
uploader=importlib.util.module_from_spec(spec)
spec.loader.exec_module(uploader)
key='gis_review_20261026'
uploader.ITEMS[key]={
    'file':a.gdb.resolve(),'type':'File Geodatabase','expect':'Feature Service',
    'title':'Millcreek roofs and CFTree review - 20261026',
    'snippet':'Private review copies: County roof/footprint mismatches, draft CFTree crown outlines and reconstruction exclusions. Feet-based measurements; automated cues are not findings.',
    'description':'Three editable review layers: all 22,042 County footprints, 119,410 draft CFTree convex crown outlines '
        'from all 61 processing tiles, and 75 excluded reconstruction candidates. No model is not evidence of demolition. '
        'Record your finding, evidence capture date, source and notes. LiDAR flown October-November 2023; footprint vintage '
        'not established; imagery dates vary. Crown outlines are 2D convex XY hulls of local 3D meshes, not the full meshes. '
        'Trunk dimensions are inferred, not measured DBH. Review results are separate from training, calibration and reference labels. '
        'Coordinates Web Mercator, horizontal datum operation ITRF08; no elevation geometry. All dimensional review fields are feet or square feet.',
    'tags':['review','CFTree','roofs','trees','quality assurance','private'],
    'readme':'../../2026-10-26/gis-review/README.md'}
if a.go:
    uploader.go(key,SimpleNamespace(url=None,username=None,again=False,allow_duplicate=False))
else:
    import json
    print(json.dumps(uploader.describe(key),indent=2))
