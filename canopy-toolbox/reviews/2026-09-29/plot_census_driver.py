"""Create an independent plot packet; score completed censuses against run outputs.

No model predictions enter the packet. Original reference.gdb remains untouched.
"""
import argparse
import csv
import datetime
import json
import math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from canopy import evaluation_design as ed, plot_census as pc, validation_metrics as vm
from canopy.run_safeguards import fingerprint, verify_fingerprint

REVIEW_COLUMNS=['PLOT_ID','COMPLETE','POINTCLOUD_REVIEW','ALIGNMENT_QA','REVIEWER','REVIEW_DATE','IMAGERY_DATE','NOTES']
TREE_COLUMNS=['PLOT_ID','TREE_ID','X','Y','HEIGHT_M','REVIEWER','REVIEW_DATE','EVIDENCE']
CAUSE_COLUMNS=['RUN','PLOT_ID','TREE_ID','CAUSE','REVIEWER','REVIEW_DATE','EVIDENCE']
OMISSION_CAUSE_COLUMNS=['SAMPLE_ID','RUN','CAUSE','REVIEWER','REVIEW_DATE','EVIDENCE']


def write_csv(path,columns,rows=()):
    with path.open('x',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader();writer.writerows(rows)


def read_csv(path,columns):
    with Path(path).open(newline='',encoding='utf-8-sig') as f:
        reader=csv.DictReader(f)
        if reader.fieldnames!=columns: raise ValueError(f'Unexpected CSV schema: {path}')
        return list(reader)


def review_identity(row):
    if not row['REVIEWER'].strip(): raise ValueError('Completed reviews need a reviewer')
    datetime.date.fromisoformat(row['REVIEW_DATE'])


def create_packet(output,count,seed):
    output=Path(output)
    if output.exists(): raise FileExistsError('Choose a new plot packet directory')
    plots=pc.draw_plots(ed.TILES,count,seed)
    output.mkdir(parents=True)
    features=[]
    for p in plots:
        x,y,e,n=p['extent']
        features.append({'type':'Feature','properties':{'PLOT_ID':p['plot_id'],'TILE':p['tile']},
                         'geometry':{'type':'Polygon','coordinates':[[[x,y],[x,n],[e,n],[e,y],[x,y]]]}})
    # Esri JSON supports this projected metre CRS without abusing RFC7946 GeoJSON.
    esri={'geometryType':'esriGeometryPolygon','spatialReference':{'wkid':6341},
          'fields':[{'name':k,'type':'esriFieldTypeString','alias':k,'length':80} for k in ('PLOT_ID','TILE')],
          'features':[{'attributes':f['properties'],'geometry':{'rings':f['geometry']['coordinates']}} for f in features]}
    (output/'plots.esri.json').write_text(json.dumps(esri,indent=2))
    write_csv(output/'plot_reviews.csv',REVIEW_COLUMNS,
              ({'PLOT_ID':p['plot_id']} for p in plots))
    write_csv(output/'trees.csv',TREE_COLUMNS)
    write_csv(output/'causes.csv',CAUSE_COLUMNS)
    write_csv(output/'omission_causes.csv',OMISSION_CAUSE_COLUMNS)
    packet={'schema_version':1,'crs':6341,'seed':seed,'plots':plots,'truth_source':'INDEPENDENT_HUMAN_CENSUS',
            'plot_geometry':fingerprint(output/'plots.esri.json'),
            'tree_definition':'Every independently resolved woody tree >=2 m; XY is crown centre, not predicted apex.',
            'boundary':'Centre inside west/south inclusive, east/north exclusive plot; inspect 3 m context.',
            'holdout_tile':ed.HOLDOUT_TILE,'holdout_extent':ed.HOLDOUT_EXTENT,'holdout_note':ed.HOLDOUT_NOTE}
    (output/'packet.json').write_text(json.dumps(packet,indent=2))
    return {'packet':str(output),'plots':len(plots),'status':'READY_FOR_INDEPENDENT_REVIEW'}


def load_census(folder):
    folder=Path(folder); packet=json.loads((folder/'packet.json').read_text())
    verify_fingerprint(packet['plot_geometry'],folder/'plots.esri.json')
    if packet.get('truth_source')!='INDEPENDENT_HUMAN_CENSUS' or packet.get('crs')!=6341:
        raise ValueError('Independent census packet in EPSG:6341 required')
    plots={p['plot_id']:p for p in packet['plots']}
    counts={p['sampled_plots'] for p in packet['plots']}
    if len(counts)!=1 or packet['plots']!=pc.draw_plots(ed.TILES,counts.pop(),packet['seed']):
        raise ValueError('Plot design does not match the fixed seeded frame')
    reviews=read_csv(folder/'plot_reviews.csv',REVIEW_COLUMNS)
    if len(reviews)!=len(plots) or {r['PLOT_ID'] for r in reviews}!=set(plots):
        raise ValueError('Each fixed plot needs exactly one review row')
    complete={}
    for r in reviews:
        if r['COMPLETE'] in ('','NO'): continue
        if r['COMPLETE']!='YES' or r['POINTCLOUD_REVIEW']!='YES' or r['ALIGNMENT_QA']!='PASS':
            raise ValueError('Completed plots require class-hidden cross-section review and passing alignment QA')
        review_identity(r); datetime.date.fromisoformat(r['IMAGERY_DATE'])
        complete[r['PLOT_ID']]=plots[r['PLOT_ID']]
    trees={k:[] for k in complete}; ids=set()
    for r in read_csv(folder/'trees.csv',TREE_COLUMNS):
        if r['PLOT_ID'] not in complete: raise ValueError('Tree belongs to an incomplete or unknown plot')
        review_identity(r)
        x,y,height=(float(r[k]) for k in ('X','Y','HEIGHT_M'))
        if not all(math.isfinite(v) for v in (x,y,height)) or height<2:
            raise ValueError('Finite independent tree coordinates and height >=2 m required')
        if not pc.inside(x,y,plots[r['PLOT_ID']]['extent']): raise ValueError('Tree centre outside its plot')
        if not r['TREE_ID'].strip() or r['TREE_ID'] in ids or not r['EVIDENCE'].strip():
            raise ValueError('Unique tree ID and independent evidence required')
        ids.add(r['TREE_ID']);trees[r['PLOT_ID']].append({**r,'x':x,'y':y})
    causes={}
    for r in read_csv(folder/'causes.csv',CAUSE_COLUMNS):
        review_identity(r)
        key=(r['RUN'],r['PLOT_ID'],r['TREE_ID'])
        if r['TREE_ID'] not in ids or r['PLOT_ID'] not in trees or not any(t['TREE_ID']==r['TREE_ID'] for t in trees[r['PLOT_ID']]):
            raise ValueError('Cause does not identify a reviewed census tree')
        if r['CAUSE'] not in pc.CAUSES or key in causes or not r['EVIDENCE'].strip():
            raise ValueError('Valid unique cause and diagnostic evidence required')
        causes[key]=r['CAUSE']
    return packet,complete,trees,causes


def diagnose_omissions(folder,reference_gdb):
    """Validate optional diagnostic causes after blind labels are frozen."""
    from canopy import validation
    units,_=validation.read_reference(reference_gdb)
    truth={r['SAMPLE_ID']:r for r in units['omission'] if r.get('LABEL')=='TREE'}
    rows=read_csv(Path(folder)/'omission_causes.csv',OMISSION_CAUSE_COLUMNS)
    keys=set();counts={}
    for row in rows:
        review_identity(row);key=(row['RUN'],row['SAMPLE_ID'])
        if key in keys or row['SAMPLE_ID'] not in truth or not row['RUN'].strip():
            raise ValueError('Cause must uniquely identify a labelled TREE omission unit and run')
        if row['CAUSE'] not in pc.CAUSES or not row['EVIDENCE'].strip():
            raise ValueError('Valid cause and diagnostic evidence required')
        keys.add(key);counts.setdefault(row['RUN'],dict.fromkeys(pc.CAUSES,0))[row['CAUSE']]+=1
    return {'status':'DIAGNOSTIC_ONLY','labelled_tree_omission_units':len(truth),'diagnosed_units':len(rows),
            'causes_by_run':counts,'rows':rows,'warning':'Unweighted diagnostic counts; no change to labels or primary omission estimates.'}


def score_packet(folder,runs,radius,replicates):
    packet,plots,trees,causes=load_census(folder)
    if not plots: return {'status':'NO_LABELS','sampled_plots':len(packet['plots']),'complete_plots':0}
    from canopy import validation
    import arcpy
    rows=[]; manifests={}
    for tile,run in runs.items():
        outputs,_=validation.run_outputs(run)
        if arcpy.Describe(outputs['trees_review']).spatialReference.factoryCode!=packet['crs']:
            raise ValueError('Census and candidates must use EPSG:6341')
        candidates=list(arcpy.da.SearchCursor(outputs['trees_review'],['TREE_ID','SHAPE@X','SHAPE@Y']))
        if len({r[0] for r in candidates})!=len(candidates) or any(not r[0] for r in candidates):
            raise ValueError('Candidate frame needs unique nonblank TREE_IDs')
        manifests[tile]=fingerprint(Path(run)/'run.json')
        for plot_id,p in plots.items():
            if p['tile']!=tile: continue
            selected=[r for r in candidates if pc.inside(r[1],r[2],p['extent'])]
            reference=trees[plot_id]
            result=pc.score_objects([[r['x'],r['y']] for r in reference],[[r[1],r[2]] for r in selected],radius)
            counts=dict.fromkeys(pc.CAUSES,0)
            for i in result['missed_truth_indices']:
                cause=causes.get((str(Path(run).resolve()),plot_id,reference[i]['TREE_ID']),'UNKNOWN')
                counts[cause]+=1
            rows.append({'plot_id':plot_id,'tile':tile,**result,'missed_causes':counts})
    needed={p['tile'] for p in plots.values()}
    if not needed<=set(runs): raise ValueError('Supply a run for each tile with completed plots')
    scopes={}
    for scope,members in ed.scopes({p['tile'] for p in packet['plots']}):
        mine=[r for r in rows if r['tile'] in members]
        strata=[r['tile'] for r in mine]
        population={p['tile']:p['population_plots'] for p in packet['plots'] if p['tile'] in members}
        design=vm.Design(strata,population,{k:[r[k] for r in mine] for k in ('tp','fp','fn','duplicates')})
        def metric(t):
            a=t['s'];tp,fp,fn=a['tp'],a['fp'],a['fn']
            return {**a,'recall':tp/(tp+fn) if tp+fn else None,'precision':tp/(tp+fp) if tp+fp else None,
                    'false_detection_rate':fp/(tp+fp) if tp+fp else None,
                    'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None}
        scopes[scope]={'estimates':vm.estimate({'s':design},metric,replicates) if mine else {},
                       'status':'NO_LABELS' if not mine else 'PARTIAL' if design.missing() else 'OK',
                       'strata_without_labels':design.missing(),'population_coverage':design.coverage(),
                       'complete_plots':len(mine),'estimand':'COMPLETE_30M_GRID_PLOT_FRAME',
                       'review_assumption':'Completed plots must remain random within each tile; no selective completion.'}
    return {'status':'OK' if len(plots)==len(packet['plots']) else 'PARTIAL','plots':rows,'scopes':scopes,
            'run_manifests':manifests,'sampled_plots':len(packet['plots']),'complete_plots':len(plots),
            'reference_inputs':{name:fingerprint(Path(folder)/name) for name in ('packet.json','plot_reviews.csv','trees.csv','causes.csv')},
            'warning':'Product misses remain misses regardless of cause; diagnostic causes never erase false negatives.'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    create=sub.add_parser('create');create.add_argument('output',type=Path)
    create.add_argument('--plots-per-tile',type=int,default=4);create.add_argument('--seed',type=int,default=20260929)
    score=sub.add_parser('score');score.add_argument('packet',type=Path);score.add_argument('--run',action='append',required=True,help='TILE=completed run folder')
    score.add_argument('--output',type=Path,required=True);score.add_argument('--radius',type=float,default=1.5)
    score.add_argument('--replicates',type=int,default=2000)
    check=sub.add_parser('check-training');check.add_argument('--extent',type=float,nargs=4,action='append',required=True)
    diagnosis=sub.add_parser('diagnose-omissions');diagnosis.add_argument('packet',type=Path)
    diagnosis.add_argument('--reference-gdb',required=True);diagnosis.add_argument('--output',type=Path,required=True)
    args=p.parse_args(argv)
    if args.command=='create': result=create_packet(args.output,args.plots_per_tile,args.seed)
    elif args.command=='check-training': result={'allowed':ed.assert_training_extents(args.extent),'holdout_note':ed.HOLDOUT_NOTE}
    elif args.command=='diagnose-omissions':
        if args.output.exists(): raise FileExistsError('Choose a new diagnostic report')
        result=diagnose_omissions(args.packet,args.reference_gdb)
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2))
    else:
        if args.output.exists(): raise FileExistsError('Choose a new score output')
        pairs=[r.split('=',1) for r in args.run]
        if any(len(r)!=2 for r in pairs) or len({r[0] for r in pairs})!=len(pairs): raise ValueError('Unique TILE=run mappings required')
        result=score_packet(args.packet,dict(pairs),args.radius,args.replicates)
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
