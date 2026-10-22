# Treetop calibration sample 2 (350 treetops, blind)

These units measure how often each October 22 [treetop evidence](../../treetop-evidence/README.md) flag is right, on the
October 22 city treetops (the count rebuilt from the combined classification). They were drawn at random (seed 20261022)
from `runs\treetop-evidence-20261022\treetop-evidence.csv`, stratified by flag, at least 25 m + 1 m from every
evaluation unit and census plot, outside 12TVL3302 and 12TVL2203 with their halos, more than 3 m from any training unit a
person has already seen (all 1,389 as of October 22: the original packet with audit 2, the refined cylinders and the rare
classes), and at least 2.5 m apart. **They only count if you label them without knowing their flags.**

It replaces [calibration sample 1](../../../2026-10-15/packets/treetop-calibration-1/README.md), which was drawn from the
October 8 treetops and never labelled: only 157 of its 350 points are still treetops on October 22, and the flags of those
that are were computed against different roofs. Six of these points lie within 2.5 m of a sample 1 point (three at the same
spot); that does not matter while sample 1 stays unlabelled.

- Do not open `sample.json`, the evidence CSV or any layer made from it until every unit you intend to label is labelled.
  The blind layer below carries no flags.
- These are **calibration labels**: never evaluation answers, never training labels, never in `reference.gdb`.
- Once looked at, they are used up as a test: a rule changed in response cannot be measured on them.

## The question

For each point: **what is the highest object within 1 m (horizontally) of this point?** Pick one value of LABEL
(the same list as the training review):

| LABEL | Use when the top within 1 m is |
|---|---|
| TREE | a woody tree crown, branch or trunk (including a branch over a roof) |
| BUILDING_ROOF | a roof, its edge, eave, ridge or roof equipment |
| WIRE / POLE / WALL | an overhead wire, a pole or mast, a building facade |
| OTHER_STRUCTURE | carport, shade sail, playground, tank, bridge, fence or freestanding wall |
| VEHICLE | car, truck, trailer |
| SHRUB_LOW_VEG / GROUND / WATER | as named (lawn is GROUND) |
| MIXED | two classes really share the top (e.g. a branch tip level with the eave) |
| UNSURE | you cannot tell |

WALL and OTHER_STRUCTURE follow the October 20 decision: fences and garden or retaining walls are OTHER_STRUCTURE.
MIXED and UNSURE are reported apart and are not counted either way, so use them honestly rather than guessing.

## Label it on the page (recommended)

From the repo root, `canopy-toolbox\reviews\2026-10-20\label-page\label_page.bat serve-calibration` opens
http://127.0.0.1:8768 ([label page, calibration mode](../../../2026-10-20/label-page/README.md#treetop-calibration-mode-october-22)).
Each point shows its 12 m of delivery points in 3D, two side sections, NAIP 2024 and the imagery map; the red column is
everything within 1 m. Press 1 to 0, M or U for the label; it moves to the next unlabelled point in review order. The page
shows no heights, flags or strata. At the end of each session copy the answers into this folder and commit:

```
canopy-toolbox\reviews\2026-10-20\label-page\label_page.bat import-calibration           (preview)
canopy-toolbox\reviews\2026-10-20\label-page\label_page.bat import-calibration --apply
```

Use one route, the page or Pro, not both: the Pro layer is not updated by the page.

## Steps in ArcGIS Pro (the alternative)

1. In any project, add `H:\lidar\2023-salt-lake-valley\runs\treetop-evidence-20261022\calibration-treetop-calibration-2\calibration.gdb\calibration_units`
   and `...\calibration-treetop-calibration-2\delivery.lasd`, plus World Imagery as a basemap. **Add only these two.**
   The parent folder also holds `treetop-evidence.csv`, which carries every flag, and the product library holds the same
   flags; leave both out of the project until you have finished.
2. Symbolise the LAS dataset by **elevation**, not class, and filter out classes 7 and 18 (noise). It is the original
   delivery, which only distinguishes ground from unclassified, so no class of ours can steer you.
3. Open the attribute table of `calibration_units`, sort by **REVIEW_ORDER** and work from 1 upwards. If you stop early,
   the units done so far are still a random subsample of every stratum, so label in order and do not skip.
4. For each row: zoom to it (about 1:300), look at the points around it in 3D or a profile view across it, then at the
   imagery. Judge from the points first; World Imagery is not from the October–November 2023 lidar dates. Hide the
   HEIGHT_M column, or at least decide before reading it: heights differ by stratum and could hint at one. Fill
   **LABEL**, **REVIEWER** (initials) and **REVIEW_DATE** (YYYY-MM-DD); NOTE is optional.
5. Save edits often. To copy the answers into the repo (do this at the end of each session), from `canopy-toolbox`:

```powershell
$env:PYTHONNOUSERSITE='1'; $env:CANOPY_LIDAR_ROOT='H:\lidar'
& "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" reviews\2026-10-15\calibration_sample.py export-labels reviews\2026-10-22\packets\treetop-calibration-2
```

Then commit `labels.csv`. On the A4000 the SSD is D:, so set `CANOPY_LIDAR_ROOT='D:\lidar'` there.

## Score it

```powershell
python reviews\2026-10-15\calibration_sample.py score reviews\2026-10-22\packets\treetop-calibration-2 --out reviews\2026-10-22\packets\treetop-calibration-2\score.json
```

For each stratum it reports the label mix, the share that is not a tree with a two-sided 95% Clopper–Pearson interval,
and whether the stratum is MEASURED (at least 30 definite labels). Once all four suspect strata are measured, it also
projects the number of non-tree treetops among the 32,986 suspects. The projection assumes the sampled area represents
the city; 12TVL3302 holds 44,845 October 22 treetops and was excluded as the prospective holdout. With 50 units a
stratum's interval is roughly ±14 percentage points; ROOF_HEIGHT has 100 because it holds 87% of the suspects.

| Stratum (priority order) | Citywide | Eligible | Drawn |
|---|---:|---:|---:|
| WIRE (WIRE_HINT) | 1,098 | 1,067 | 50 |
| WALL (WALL_HINT, not wire) | 404 | 382 | 50 |
| FLAT_TOP (not wire or wall) | 2,692 | 2,591 | 50 |
| ROOF_HEIGHT (none of the above) | 28,792 | 27,180 | 100 |
| POLE_ONLY (POLE_HINT, not suspect) | 24,445 | 23,185 | 50 |
| UNFLAGGED | 469,709 | 418,233 | 50 |

The four suspect strata total 32,986. POLE_ONLY tests whether leaving POLE_HINT out of SUSPECT was right; UNFLAGGED gives
the rate of non-trees the flags miss. Only 1,207 treetops carry two or more of the four suspect flags, so each stratum's
rate reads almost as its flag's rate.

Drawn with `calibration_sample.py draw ... --seed 20261022 --evidence <SSD>\lidar\2023-salt-lake-valley\runs\treetop-evidence-20261022 --prefix C2`;
the blind layer was built with `build-gdb` (350 features, the 61 delivery LAS files unchanged: `build.json` beside it).
