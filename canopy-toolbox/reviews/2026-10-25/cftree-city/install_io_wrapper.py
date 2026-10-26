"""Install a local I/O adapter around the unchanged compiled segmentation binary."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('repository',type=Path)
p.add_argument('audit',type=Path)
p.add_argument('--tool',choices=['segmentation','alpha'],default='segmentation')
a=p.parse_args()
repo=a.repository.resolve()
build=repo/('src/segmentation/TreeSeparation/build' if a.tool=='segmentation' else 'src/reconstruction/AlphaWrap/build')
name='segmentation' if a.tool=='segmentation' else 'awrap_points'
target=build/name; native=build/(name+'.native')
assert repo.drive.upper()=='C:' and build.resolve().is_relative_to(repo)
def linux(path):return '/mnt/c/'+path.as_posix()[3:]
if not native.exists():
    assert target.read_bytes()[:4]==b'\x7fELF'
    subprocess.run(['wsl','-d','Ubuntu','--','mv','--',linux(target),linux(native)],check=True)
else:
    assert b'Millcreek CFTree I/O adapter' in target.read_bytes()
source=Path(__file__).with_name('segmentation_io.sh' if a.tool=='segmentation' else 'alpha_io.sh')
target.write_text(source.read_text(),encoding='utf8',newline='\n')
subprocess.run(['wsl','-d','Ubuntu','--','chmod','+x',linux(target)],check=True)
record=dict(native_sha256=hashlib.sha256(native.read_bytes()).hexdigest(),
            wrapper_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
            native_binary=str(native),wrapper=str(target),algorithm_changed=False,
            operation='Same input and parameters; bulk copy into Linux scratch, run, bulk copy output back')
a.audit.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record))
