# Citywide FRACTAL refinement of the Millcreek working LAS (October 19-20, 2026)

**Status: complete for all 61 tiles (October 20, 13:10).** 1,344,971,548 points, three FRACTAL passes each on the A4000, every
tile's passes agreeing evenly (largest pairwise spread 0.19 points). Refined copies exist for rules version 1
(`runs/refined-fractal-20261019`) and version 2 (`runs/refined-fractal-20261020`, the current one). Citywide summary of version 2:
[summary-v2-20261020.json](summary-v2-20261020.json); the October 19 pause snapshot is [status-20261019.json](status-20261019.json).

The refinement takes the October 8 working LAS (native building and height classes, `runs/city-count-20261008/prepared/points`),
runs the IGN FRACTAL model three times per tile with NAIP 2024 colour, and writes **provisional refined copies** in which a class
changes only where all three passes agree and contradict a toolbox-derived class (decided with Brian on October 19; rules version 2
on October 20). Originals and working files are never written. Every change is reversible from extra dimensions in the copy.

## Results, rules version 2 (all 61 tiles)
- **535,490,628 points changed (39.8%)**; 96.7% of points had unanimous passes.
- Vegetation to ground (code 7): 509.6 M, the bare surface the height classification had put in class 3 ("low vegetation"),
  since the vendor's ground class is sparse. Vegetation to building 6.5 M; building to vegetation 5.4 M; vegetation to other 9.7 M
  and to permanent structure 2.2 M; building to other 1.3 M and to permanent structure 0.8 M.
- Still only proposed: building called ground 18.7 M (rule 12), water or bridge 2.8 M, vendor-class contradictions 1.1 M.
- **Candidate treetops:** the top point of 102,527 of the 607,972 October 8 treetops (16.9%) left vegetation, mostly to building
  (70,013). **64% of them carry the October 15 SUSPECT flag, against 5.1% of the other treetops; the refinement reaches 72% of all
  SUSPECT treetops.** Two independent methods (FRACTAL on points and colour; fixed geometric rules) point at the same treetops,
  mostly roof edges. They are candidates for review, not removals: a rebuilt canopy surface decides that.
- **Against Brian's training labels on 12TVL2804** (533 labels, 408 comparable parts; evaluate_variants.py): baseline 300 agree
  (74%), version 1 322 (79%), version 2 384 (94%). These are training diagnostics on one tile, not an accuracy estimate.

## Where things are on the SSD
| What | Path under `lidar\2023-salt-lake-valley` |
|---|---|
| NAIP 2024 sheets (12, 242 MB, UGRC public bucket) | `naip\naip2024-sheets` |
| NAIP 2024 tile per lidar tile (61, with flight date) | `naip\naip2024-tiles\<tile>` |
| Colourised FRACTAL inputs (61) and `prepare.json` | `fractal\city-20261019\colorized` |
| Three passes, consensus and manifest per tile; `infer.json`, `infer.log` | `fractal\city-20261019\fractal\<tile>` |
| Refined copies and per-tile summaries; `refine.log` | `runs\refined-fractal-20261019\points` |

Folders named `<tile>.failed-*`, `<tile>.inconsistent-*` or `repeat-N.failed-*` are kept attempts, for diagnosis only.

## Rerunning (on whichever machine has the SSD and the Myria3D environment)
```
reviews\2026-10-19\fractal-city\city_fractal.bat infer          (skips the 22 completed tiles; about 8 min a tile on the A4000)
reviews\2026-10-19\fractal-city\city_fractal.bat refine --wait  (start alongside; refines each tile as its consensus lands)
reviews\2026-10-19\fractal-city\city_fractal.bat summarize <NEW_FOLDER>   (after all 61: city totals and the treetop impact)
```
Then the training-label check on 12TVL2804 (it was the next tile but two when the run paused):
```
<myria3d python> reviews\2026-10-19\fractal-city\label_check_refined.py <refined 12TVL2804.las> <...\packet-20260929> reviews\2026-09-29\packets\training-labels\labels-progress.csv <NEW.json>
```
Close Chrome, Teams and other heavy apps first (see "What went wrong"). 12TVL3302 is the evaluation holdout and 12TVL2203 the
external tile: their refined copies are products, never training data.

## The rule (refine_city.py)
Applied only to unanimous, non-withheld points whose October 8 class came from the toolbox:
codes 1 to 3 move height vegetation (3/4/5) to building, permanent structure (64) or other (1); codes 4 to 6 move building (6) to
vegetation (banded 3/4/5 by height above the run's ground mosaic), permanent structure or other. Proposed only, class unchanged:
11 vegetation called ground, 12 building called ground, 13 a vendor class contradicted, 14 building called vegetation without a
usable height, 15 water or bridge, 16 a baseline class-1 point called vegetation, building or structure.
Extra dimensions in each copy: `BASE_CLASS`, `FRACTAL_CLASS`, `FRACTAL_VOTES`, `REFINE_RULE`.

## Results so far (22 tiles, 489,348,912 points; not yet a city total)
- **13,101,902 points changed (2.68%)**; 97.0% of points had unanimous passes.
- Largest moves: 0.5 to 2 m vegetation to other, 5.07 M (vehicles, fences, walls are the likely objects); high vegetation to building,
  2.53 M; building to vegetation, 1.26 M (overhanging canopy); building to other, 1.06 M; high vegetation to other, 0.95 M; high
  vegetation to permanent structure, 0.74 M.
- **Proposed, not applied: 207 M vegetation points that FRACTAL calls ground (rule 11).** The vendor's ground class is sparse (12TVL2804:
  2.66 M of 27 M points), and the October 8 height classification put the rest of the bare surface (pavement, lawns) into class 3,
  "low vegetation". Class 3 is therefore mostly ground, which matters for anything that uses it as vegetation. Making it ground would
  change terrain inputs, so it is left for a decision.
- Also proposed: 9.6 M building points called ground (rule 12), worth a look; 1.2 M water or bridge (rule 15); 0.36 M vendor-class
  contradictions (rule 13).
- Treetop impact and the training-label check are not run yet (they need all tiles and 12TVL2804).

These are model-driven proposals, not validated labels: FRACTAL was trained in France with other imagery, and agreement between
three passes removes its run-to-run noise, not its systematic errors.

## What went wrong, and the guards it produced
- **Memory commit limit.** The workstation (32 GB RAM, system-managed page file) was at its commit limit with desktop apps open
  (about 38 GB committed by processes). Passes then crashed at start-up (`0xC0000005`) or while loading PyTorch's CUDA libraries
  (`WinError 1114`). `infer_city.py` now waits for 6 GB of headroom before a tile; closing Chrome and Teams raised headroom from
  about 2 to 9 GB. A larger page file is a question for IT.
- **Native crashes inside a pass** (PDAL and start-up). `repeat.py --pass-retries` (default 0, so October 8 behaviour is unchanged)
  reruns only the crashed pass, keeping its folder as `repeat-N.failed-k`; the city driver uses 2, and tries a tile up to three times.
- **A silently corrupt pass.** One pass of 12TVL2702 agreed with the other two on 51% of points while they agreed on 98%, although every
  point-order and source check passed. A tile whose pairwise pass agreements spread by more than 2 points is now rejected and rerun
  (`infer_city.py`) and never refined (`refine_city.py`). Healthy tiles spread by at most 0.2 points; the rerun of 12TVL2702 was 97.5%
  unanimous. Because the refinement needs all three passes to agree, a corrupt pass mostly blocks changes rather than adding wrong
  ones, but it leaves the tile's consensus and vote counts wrong.
- Eight attempts failed across seven tiles (seven crashes, one corrupt pass); all seven tiles completed on retry.
- One tile (12TVL2502) needed more than the card's 16 GB at batch 10 and ran 4.5 times slower through shared memory; same results.
