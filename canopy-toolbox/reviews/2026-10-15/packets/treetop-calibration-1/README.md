# Treetop calibration sample 1 (350 treetops, blind)

These units measure how often each [treetop evidence](../../TREETOP_EVIDENCE.md) flag is right. They were drawn at
random (seed 20261015) from the October 8 city treetops, stratified by flag, at least 25 m + 1 m from every evaluation
unit and census plot, outside 12TVL3302 and 12TVL2203 with their halos, more than 3 m from any training unit a person has
already seen, and at least 2.5 m apart. **They only count if you label them without knowing their flags.**

- Do not open `sample.json`, the `treetop_evidence` layer or `treetop-evidence.csv` until every unit you intend to label
  is labelled. The blind layer below carries no flags.
- These are **calibration labels**: never evaluation answers, never training labels, never in `reference.gdb`.
- Once looked at, they are used up as a test: a rule changed in response cannot be measured on them.

## The question

For each point: **what is the highest object within 1 m (horizontally) of this point?** Pick one value of LABEL
(the same list as the training review):

| LABEL | Use when the top within 1 m is |
|---|---|
| TREE | a woody tree crown, branch or trunk (including a branch over a roof) |
| BUILDING_ROOF | a roof, its edge, eave, ridge or roof equipment |
| WIRE / POLE / WALL | an overhead wire, a pole or mast, a vertical face (facade, wall, solid fence) |
| OTHER_STRUCTURE | carport, shade sail, playground, tank, bridge |
| VEHICLE | car, truck, trailer |
| SHRUB_LOW_VEG / GROUND / WATER | as named |
| MIXED | two classes really share the top (e.g. a branch tip level with the eave) |
| UNSURE | you cannot tell |

MIXED and UNSURE are reported apart and are not counted either way, so use them honestly rather than guessing.

## Steps in ArcGIS Pro

1. In any project, add `H:\lidar\2023-salt-lake-valley\runs\treetop-evidence-20261015\calibration-treetop-calibration-1\calibration.gdb\calibration_units`
   and `...\calibration-treetop-calibration-1\delivery.lasd`, plus World Imagery as a basemap. **Add only these two.**
   The parent folder also holds `treetop-evidence.gdb` and `treetop-evidence.csv`, which carry every flag; leave them
   out of the project until you have finished.
2. Symbolise the LAS dataset by **elevation**, not class, and filter out classes 7 and 18 (noise). It is the original
   delivery, which only distinguishes ground from unclassified, so no class of ours can steer you.
3. Open the attribute table of `calibration_units`, sort by **REVIEW_ORDER** and work from 1 upwards. If you stop early,
   the units done so far are still a random subsample of every stratum, so label in order and do not skip.
4. For each row: zoom to it (about 1:300), look at the points around it in 3D or a profile view across it, then at the
   imagery. Judge from the points first; World Imagery is not from the October–November 2023 lidar dates. Hide the
   HEIGHT_M column, or at least decide before reading it: heights differ by stratum and could hint at one. Fill
   **LABEL**, **REVIEWER** (initials) and **REVIEW_DATE** (YYYY-MM-DD); NOTE is optional.
5. Save edits often. To copy the answers into the repo (do this at the end of each session):

```powershell
$env:PYTHONNOUSERSITE='1'; $env:CANOPY_LIDAR_ROOT='H:\lidar'
& "C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" reviews\2026-10-15\calibration_sample.py export-labels reviews\2026-10-15\packets\treetop-calibration-1
```

Then commit `labels.csv`.

## Score it

```powershell
python reviews\2026-10-15\calibration_sample.py score reviews\2026-10-15\packets\treetop-calibration-1 --out reviews\2026-10-15\packets\treetop-calibration-1\score.json
```

For each stratum it reports the label mix, the share that is not a tree with a two-sided 95% Clopper–Pearson interval,
and whether the stratum is MEASURED (at least 30 definite labels). Once all four suspect strata are measured, it also
projects the number of non-tree treetops among the 91,807 suspects. The projection assumes the sampled area represents
the city; 12TVL3302 holds 46,114 treetops and was excluded as the prospective holdout. With 50 units a stratum's interval is
roughly ±14 percentage points; ROOF_HEIGHT has 100 because it holds 94% of the suspects.

| Stratum (priority order) | Citywide | Eligible | Drawn |
|---|---:|---:|---:|
| WIRE (WIRE_HINT) | 2,413 | 2,363 | 50 |
| WALL (WALL_HINT, not wire) | 579 | 557 | 50 |
| FLAT_TOP (not wire or wall) | 4,875 | 4,716 | 50 |
| ROOF_HEIGHT (none of the above) | 83,940 | 79,998 | 100 |
| POLE_ONLY (POLE_HINT, not suspect) | 31,107 | 29,510 | 50 |
| UNFLAGGED | 485,058 | 433,630 | 50 |

The four suspect strata total 91,807. POLE_ONLY tests correction 1 (POLE_HINT left SUSPECT); UNFLAGGED gives the
rate of non-trees the flags miss. Because only 2,400 treetops carry two flags, each stratum's rate reads almost as its
flag's rate.
