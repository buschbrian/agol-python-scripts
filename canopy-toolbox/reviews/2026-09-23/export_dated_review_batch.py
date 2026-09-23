"""Read fixed samples and render imagery-only triage sheets; never edit inputs."""
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import arcpy
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2] / "scratch" / "models"
OUT = ROOT / 'dated_review_20260923'
OUT.mkdir(exist_ok=False)
IMAGE_PATH = ROOT / 'nearmap_2023-08-31_aligned.jpg'
im = Image.open(IMAGE_PATH).convert('RGB')
assert im.size == (1200, 1200), im.size
report = json.loads((ROOT / 'model_imagery_sample.json').read_text())
fields = ['TREE_ID', 'PATTERN', 'FOOT_QA', 'SHAPE@XY']
candidates = [dict(zip(fields, row)) for row in arcpy.da.SearchCursor(report['candidate_sample'], fields)]
candidates.sort(key=lambda r: r['TREE_ID'])
groups = defaultdict(list)
for row in candidates:
    groups[(row['PATTERN'], row['FOOT_QA'])].append(row)
batch = []
for depth in range(12):
    for key in sorted(groups):
        if depth < len(groups[key]) and len(batch) < 24:
            batch.append(groups[key][depth])
fields = ['STRATUM', 'GRID_ROW', 'GRID_COL', 'STD_M2', 'TREE_M2', 'BOTH_M2', 'STD_TREES', 'TREE_TREES', 'BOTH_TREES']
plots = [dict(zip(fields, row)) for row in arcpy.da.SearchCursor(report['canopy_plots'], fields)]
plots.sort(key=lambda r: (r['GRID_ROW'], r['GRID_COL']))
assert len(candidates) == 206 and len(plots) == 24
for idx, row in enumerate(batch, 1):
    row['review_id'] = f'C{idx:02d}'
for row in plots:
    row['review_id'] = f"P{row['GRID_ROW']:02d}_{row['GRID_COL']:02d}"

def crop(x0, y0, x1, y1):
    return im.crop((round((x0-428100)*4), round((4504400-y1)*4),
                    round((x1-428100)*4), round((4504400-y0)*4))).resize((400,400))

def sheet(rows, kind, number):
    canvas = Image.new('RGB', (1260, 990), 'white')
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 19)
    draw.text((15, 8), 'Nearmap survey 2023-08-31 | AI visual triage only | November LiDAR', fill='black', font=font)
    for i, row in enumerate(rows):
        ox = 10 + (i % 3)*420
        oy = 45 + (i // 3)*470
        if kind == 'candidate':
            x,y = row['SHAPE@XY']
            tile = crop(x-7.5,y-7.5,x+7.5,y+7.5)
            td = ImageDraw.Draw(tile)
            # Open crosshair keeps the actual candidate cell visible.
            for a,b,c,d in [(181,200,193,200),(207,200,219,200),(200,181,200,193),(200,207,200,219)]:
                td.line((a,b,c,d), fill='#ff00ff', width=2)
            label = row['review_id'] + ' | 15 m window, candidate at center'
        else:
            x0=428100+row['GRID_COL']*10
            y1=4504400-row['GRID_ROW']*10
            tile=crop(x0-2,y1-12,x0+12,y1+2)
            td=ImageDraw.Draw(tile)
            td.rectangle((57,57,343,343), outline='#ff00ff', width=2)
            label = row['review_id'] + ' | magenta = fixed 10 m plot'
        canvas.paste(tile,(ox,oy+30))
        draw.text((ox,oy),label,fill='black',font=font)
    canvas.save(OUT / f'{kind}_sheet_{number:02d}.png')

for kind, rows in [('candidate',batch),('plot',plots)]:
    for start in range(0,len(rows),6):
        sheet(rows[start:start+6],kind,start//6+1)

state = {'status':'UNREVIEWED', 'survey_date':'2023-08-31',
         'local_photo_date_verified':False, 'reviewer_type':'AI_VISUAL_TRIAGE',
         'imagery_sha256':hashlib.sha256(IMAGE_PATH.read_bytes()).hexdigest(),
         'imagery_extent_epsg6341':[428100,4504100,428400,4504400],
         'imagery_grid_m':0.25, 'imagery_registration':'existing align_nearmap.py, not independently surveyed',
         'candidate_batch_selection':'round-robin over existing PATTERN/FOOT_QA groups; TREE_ID sorted within each group; first 24',
         'sample_source':report, 'candidate_batch':batch, 'all_candidates':candidates, 'plots':plots,
         'cautions':['Candidates are not stem identities.', 'Method labels omitted from review sheets.',
                     'Plots are purposive high-change/control locations; do not infer population accuracy.',
                     'Season and local image registration limit roof-edge labels.']}
(OUT/'review_manifest.json').write_text(json.dumps(state,indent=2))
print(json.dumps({'output':str(OUT),'candidates':len(batch),'plots':len(plots),'source_candidates':len(candidates)}))
