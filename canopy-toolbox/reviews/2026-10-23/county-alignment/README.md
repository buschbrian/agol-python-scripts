# County footprints against the 2023 LiDAR: misalignment (October 23, 2026)

Brian asked to "first measure the county layer's misalignment against the LiDAR and separate systematic shifts from
real offsets, before I review those queues" ([align_county.py](align_county.py)). **The figures are unvalidated
planning estimates from the 2023 LiDAR consensus roof.** The County's data was not edited: the shifted outlines are a
derived layer. Nothing was uploaded.

Output: `H:\lidar\2023-salt-lake-valley\runs\county-alignment-20261023`. The repo copies are the JSON records and the
three maps.

| File | Meaning |
|---|---|
| county-alignment.gpkg / footprints_as_county | The 22,042 county footprints as stored, with their fit, local shift and CLASS |
| … / footprints_best_fit | The same, SYSTEMATIC moved by the local shift and REAL_OFFSET by their own fit (a derived layer) |
| … / footprints_local_shift | Every footprint moved by its neighbourhood's shift (a derived layer) |
| … / shift_field_250m | The median shift of reliable fits per 250 m cell (points with DX, DY) |
| fit.csv, field.csv, classes.csv, candidates-explained.csv | Per-footprint fit, local field, class; per-candidate result |
| fit.json, field.json, classify.json | Summaries (copies here) |
| shift-field.png, pilot-shifts.png, real-offset-examples.png | Maps (copies here) |

## Answer: there is no systematic shift
- **Each building's own shift is small.** The 17,141 footprints with a reliable fit need a median shift of **0.36 m**
  (0.77 m at the 90th percentile). That is within one LiDAR cell plus the eaves: a 0.5 m raster can't place an outline
  much better.
- **Neighbours don't share a shift.** The median shift of the reliable fits within 150 m is 0.15 m (0.27 m at the 90th
  percentile), smaller than the scatter among those neighbours (0.32 m). Taking it off barely changes the residual
  (0.33 m, from 0.36). Only 15 footprints have a local shift of 0.5 m or more, and only 7 (0.04%) are explained by it.
  No 500 m cell is off by 0.5 m, and only one of 459 250 m cells is (0.53 m).
- **The whole city leans about 0.1 m west.** The citywide median is dx -0.13 m, dy +0.02 m, under half a LiDAR cell
  and below what this method resolves.
- **It isn't the datum.** The footprints came from the County's EPSG 3566 via
  `WGS_1984_(ITRF00)_To_NAD_1983 + WGS_1984_(ITRF08)_To_NAD_1983_2011`, which is a null shift here (6 mm). The
  alternative HARN path would move them (-0.17, +0.36) m, and the fit finds no such shift.
- **There is no vintage to split by.** The county layer is one edit (one creator; created and edited in 2019) with no
  source, year-built or build-type values beyond a handful, so there is no subdivision or survey structure to test.
  By jurisdiction the shifts are the same.

`shift-field.png` maps the 250 m medians (arrows ×1000) beside the histograms of own and local shifts.
`pilot-shifts.png` is the two-tile pilot (12TVL2804 and 12TVL2603), checked before the citywide run. On both, the
reliable arrows point every way.

## Method
- **Fit:** for every county footprint, the shift within ±3 m at 0.25 m steps that puts the most consensus roof cells
  inside the outline. The outline is rasterized at 0.25 m cell centres and the 0.5 m roof read at 0.25 m, and an FFT
  cross-correlation scores every shift at once. Roofs overhang their footprints, so several shifts often tie; the
  centre of the tied plateau (every shift within 1% of the best) is taken, which centres the outline under its roof.
- **Fit quality:** sharpness (best minus the mean 0.5-0.75 m beyond the plateau), the margin over any shift 1 m or more
  away (a second peak means an ambiguous fit), whether the plateau reaches the search edge, and the share of the outline
  under canopy of 2 m or more without roof.
- **Reliable fit:** at least 40 m², at least 85% roof at the best shift, sharpness and margin at least 0.02, not on
  the edge, and at most 20% under trees.
- **Local field:** the median dx and dy of the reliable fits within 150 m (at least 5, the footprint itself left out).
- **Classes:**
  - **ALIGNED:** at least 85% roof where it is, and no shift gains 5 points.
  - **SYSTEMATIC:** at least 85% roof once the local shift (0.25 m or more) is applied, gaining at least 5 points.
  - **REAL_OFFSET:** a trustworthy fit of its own, at least 85% roof, a gain of at least 5 points, a shift of 0.5 m or
    more, and 0.5 m or more from the local shift.
  - **REBUILT_OR_GONE:** under 50% roof under any shift, and not under trees (canopy under 30%).
  - **UNCERTAIN:** the rest.

| Class | Footprints | Median area | Median shift | Roof as stored → at best shift |
|---|---:|---:|---:|---:|
| ALIGNED | 17,928 (81%) | 182 m² | 0.36 m | 99% → 99% |
| UNCERTAIN | 3,348 | 100 m² | — | 71% → 77% |
| REAL_OFFSET | 507 | 60 m² | 1.06 m | 85% → 93% |
| REBUILT_OR_GONE | 254 | 96 m² | — | 0% → 0% |
| SYSTEMATIC | 5 | 26 m² | 0.79 m | 89% → 99% |

UNCERTAIN breaks down as 1,345 with trees over 30% or more of the outline, 1,412 only part roofed under any shift (an
addition removed, a partial rebuild, or a roof the consensus misses), and 591 with an ambiguous fit.
REAL_OFFSET is mostly small outbuildings whose county outline sits 0.5 to 1.9 m off their roof;
`real-offset-examples.png` shows six, the county outline in blue and its best fit dashed red.

## What it does to the review queues
Candidates were re-tested against each derived layer. A candidate counts as explained when at least 80% of its cells
fall on or within 1.5 m of a moved outline, the rule that excluded roof near county footprints in the first place. A
pair counts as explained when its county outline reaches 85% roof and all its candidates are explained.

| Queue | Before | After the local shift | After the best fit |
|---|---:|---:|---:|
| LiDAR candidates (all) | 6,213 | 6,213 | 6,209 |
| … against a county building (other, lower roof, corner of a roof) | 3,675 | 3,675 | 3,671 |
| Offset or rebuilt (county + LiDAR) | 458 | 458 | 456 |

**Realignment explains almost nothing, because the queues aren't misregistration.** The pieces against county
buildings are roof the county outline doesn't include: a missing corner, an addition, a porch, a carport, or eaves
past 1.5 m. No translation of the outline removes them. Only 56 candidates gain any cells from a best-fit outline, 33
gain a quarter of their cells and 15 gain half. Brian's own example, PR724355, shows it: its 52% roof is trees over
half the house, and the corner beyond the outline is the same roof, a shape difference. The "Corner or edge of a
county roof" group (406) and the guess on 24 pairs already handle that.

On the review page:
- **Explained items** (LC02157, LC04399, LC04639, LC04792; PR725966, PR733201) move to a last group, "Explained by
  realigning the county outline".
- **New fact:** every candidate ("That county outline vs the LiDAR"), pair and county item ("County outline vs the
  LiDAR") says how its county outline sits on the LiDAR: aligned, offset with distance and direction, trees over it,
  part roofed, or rebuilt or gone. Among the 458 pairs: 409 uncertain (mostly trees or part roofed), 32 rebuilt or
  gone, 16 offset, 1 systematic.
- **Applied in place** by `footprint_review.bat facts`, which reads this folder's classes.csv when present. Brian's 28
  answers are untouched.

## Rerun
From `canopy-toolbox`, ArcGIS Pro env `millcreek-py3`, `PYTHONNOUSERSITE=1`:
```
python -I reviews/2026-10-23/county-alignment/align_county.py fit OUT --pilot
python -I reviews/2026-10-23/county-alignment/align_county.py fit OUT        (about 1.5 minutes)
python -I reviews/2026-10-23/county-alignment/align_county.py field OUT
python -I reviews/2026-10-23/county-alignment/align_county.py classify OUT
```
