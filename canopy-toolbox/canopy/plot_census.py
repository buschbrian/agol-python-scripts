"""Independent fixed 30 m plots and one-to-one tree census scoring; no ArcPy."""
import hashlib
import math
import numpy as np
from scipy.spatial import cKDTree
from .matching import match_candidates

CAUSES=('LEAF_OFF','EXCLUDED_UNCLASSIFIED','ROOF_CONFUSION','LOW_HEIGHT',
        'SOURCE_GAP','DATE_CHANGE','OTHER','UNKNOWN')
PLOT_M=30.


def draw_plots(tiles, count=4, seed=20260929):
    if isinstance(count,bool) or int(count)!=count or count < 1:
        raise ValueError('Plot count must be a positive integer')
    plots=[]
    for tile,bounds in sorted(tiles.items()):
        if len(bounds)!=4 or not all(math.isfinite(v) for v in bounds):
            raise ValueError('Finite tile bounds required')
        west,south,east,north=bounds
        cols,rows=int((east-west)//PLOT_M),int((north-south)//PLOT_M)
        population=cols*rows
        if cols<1 or rows<1 or count>population:
            raise ValueError('Not enough complete 30 m plots in tile')
        tile_seed=int.from_bytes(hashlib.sha256(f'{seed}:{tile}'.encode()).digest()[:8],'big')
        rng=np.random.default_rng(tile_seed)
        for order,cell in enumerate(rng.choice(population,count,replace=False),1):
            row,col=divmod(int(cell),cols)
            x,y=west+col*PLOT_M,south+row*PLOT_M
            plots.append({'plot_id':f'{tile}_{row:03d}_{col:03d}', 'tile':tile,
                          'extent':[x,y,x+PLOT_M,y+PLOT_M], 'review_order':order,
                          'population_plots':population,'sampled_plots':count,
                          'frame_extent':[west,south,west+cols*PLOT_M,south+rows*PLOT_M]})
    return plots


def inside(x,y,bounds):
    return bounds[0]<=x<bounds[2] and bounds[1]<=y<bounds[3]


def score_objects(truth, candidates, radius=1.5):
    truth=np.asarray(truth,dtype=float).reshape(-1,2)
    candidates=np.asarray(candidates,dtype=float).reshape(-1,2)
    matches=match_candidates(truth,candidates,radius)
    forward,reverse=matches['baseline_to_variant'],matches['variant_to_baseline']
    tp=int((forward>=0).sum()); fp=int((reverse<0).sum()); fn=int((forward<0).sum())
    unmatched=np.flatnonzero(reverse<0)
    matched_truth=truth[forward>=0]
    duplicates=(int(np.count_nonzero(cKDTree(matched_truth).query(candidates[unmatched],k=1)[0]<=radius))
                if len(matched_truth) and len(unmatched) else 0)
    return {'tp':tp,'fp':fp,'fn':fn,'duplicates':duplicates,
            'precision':tp/(tp+fp) if tp+fp else None,
            'recall':tp/(tp+fn) if tp+fn else None,
            'false_detection_rate':fp/(tp+fp) if tp+fp else None,
            'f1':2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
            'missed_truth_indices':np.flatnonzero(forward<0).tolist(),
            'false_candidate_indices':unmatched.tolist(),
            'ambiguous_truth':matches['ambiguous_baseline'],'ambiguous_candidates':matches['ambiguous_variant'],
            'matching':'ONE_TO_ONE_MAX_CARDINALITY_MIN_DISTANCE','radius_m':radius}
