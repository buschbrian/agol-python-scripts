# LOD2.0 roof forms against the lidar roof (October 23, 2026)

Can the experimental LOD2.0 roofs from the [October 22 massing](../../2026-10-22/massing/README.md) replace the flat LOD1.2
blocks as the existing-buildings layer for small area plans (ArcGIS Urban)? For every building this check measures how far
each level's roof is from the consensus lidar roof ([roof-consensus](../../2026-10-21/roof-consensus/README.md)), sorts the
buildings into LOD2.0 better, about the same, or worse/broken, and looks at the worst cases by roof type.
Nothing was uploaded or shared.

**Recommendation: publish the hybrid built from the filled rerun.** The filled citywide LOD2.0 is good enough to carry
the existing-buildings layer, and the check supplies the per-building rule for the few that are not.
- **Use LOD2.0 for 21,293 of 21,561 buildings (98.8%; 4.69 of 4.74 km² of footprint)** and LOD1.2 for the other 268:
  the 159 with too little lidar roof to judge, and 109 whose LOD2.0 has a pit or spike. The rule: LOD2.0 where the
  verdict is better or same and under 10% of the footprint is at ground level.
- **On the compared roof cells the hybrid is within 0.5 m on 94.4% and within 1 m on 97.7%.** LOD1.2 alone manages
  56.9% and 80.4%, and all-LOD2.0 94.6% and 97.8%.
- **The October 22 LOD2.0 should not be used as it is.** Its main fault was one mistake in run_massing.py. Inside a
  footprint, every cell the lidar did not see as roof (tree overhang, lidar voids on dark or wet flat roofs, edges)
  was filled with *terrain*, so the tool modelled those parts of the building at ground level.
  - October 22 LOD2.0: 721 buildings are worse or broken, and 2,827 more pass but have 10% or more of the footprint at
    ground level.
  - October 22 LOD1.2: 598 blocks, **including blocks in the public LOD1.2 scene layer**, are slabs within 1 m of the
    ground, almost all on footprints with low roof support.
- **The rerun fixes that.** The height source takes each footprint's missing roof cells from the nearest roof cell of the
  same footprint (`fill_trial.py --city`). In the rerun: worse 293 to 20, broken 428 to 79, LOD2.0 buildings with 10% or
  more of the footprint at ground level 3,614 to 21, LOD1.2 ground slabs 598 to 3. The public LOD1.2 scene layer would
  need replacing with the rerun's.
- **What is still wrong in the 109:** the tool sometimes drops a wedge or wing to ground even on a fully covered roof;
  ridge spikes at towers; and cross gables flattened to one plane. On those 109, LOD2.0 is within 1 m on 92.1% of
  cells and LOD1.2 on 74.3%, so the fallback trades some accuracy for removing the pit or spike. Publishing LOD2.0 for
  everything instead costs 0.1 point of overall within-1 m share (hybrid 97.7%, all-LOD2.0 97.8%) and leaves those
  defects in.
- **Still unchecked:** nothing was viewed in 3D or against imagery, and the check measures fidelity to the lidar, not
  independent accuracy (see the end).
- **Update, October 24: roofer on the whole city beats this by the same check.** A three-way hybrid (roofer where it
  passes, else Esri LOD2.0, else LOD1.2) is within 0.5 m on 96.8% and within 1 m on 98.2% of compared cells, against
  94.4% and 97.7% for the Esri-only hybrid. See "Roofer on the whole city" below. It has not been viewed in 3D either.
- **Later on October 24: the candidate is the v2 three-way hybrid** (roofer with `--plane-detect-min-points 30`, plus roof attributes), 20.2 MB,
  validated. See "Clean-up, imagery check and roof attributes". The plan for replacing the public LOD1.2 layer is [PUBLISH_PLAN.md](PUBLISH_PLAN.md);
  nothing has been uploaded.

## Method ([lod2_check.py](lod2_check.py))
- **Reference:** `roof_elevation_m.tif` in the library, the consensus roof: the highest first or single return per
  0.5 m cell, called building by 2 of 3 classifiers. **The massing was fitted to this same surface**, so the check
  measures how faithfully each level represents the lidar roof, not accuracy against an independent truth.
- **Models:** `massing-20261022\massing.gdb` `lod12` and `lod20` (21,561 blocks each) were turned into rasters on the
  same grid by Multipatch To Raster (highest Z on a vertical line through each cell centre). The footprints were
  rasterized by Polygon To Raster (cell centre, FP_ID). Both took seconds. Cell-centre sampling against the lidar's
  in-cell maximum should read a pitched roof slightly low. The median LOD2.0 bias is only -0.02 m on steep roofs and
  -0.01 m on flat ones, so this effect is small.
- **Compared cells:** inside the footprint, where the lidar has roof. For each level and building: median signed error,
  |error| p50 and p95, and the share of compared cells within 0.5 m and 1 m.
- Over the *whole* footprint, lidar roof or not, the check also records **GROUND_PCT**: the share of cells where the
  level sits within 1 m of the footprint's median ground. A roof modelled at ground level shows as a pit whatever the
  lidar saw there.
- **Verdict** (rules written before the citywide results were read; `VERDICT_RULES` in the script; margins of 10
  points of within-1 m share or 0.5 m of |error| p95):
  - *too-few*: fewer than 20 compared cells.
  - *broken*: any of four flags on LOD2.0:
    - TOP_ABOVE_LIDAR: its top more than 1 m above the highest lidar roof cell.
    - ABOVE_1M: 10% or more of compared cells more than 1 m above the lidar.
    - DROPPED: 10% or more of compared cells within 1 m of ground where the lidar roof is 2 m or more up. This flag was
      added after the pilot showed the failure.
    - MISSING: no LOD2.0 surface on 5% or more of compared cells.
  - *better*: LOD2.0 ahead by a margin on at least one measure and behind on neither.
  - *worse*: the reverse.
  - *same*: the rest. 93 of them are mixed (ahead on one measure, behind on the other).
- **Roof type** was inferred from the lidar, because county BuildType is empty on 21,408 footprints (`TYPE_RULES`).
  Rules are taken in order, first match wins:
  - multi-level: footprint at least 400 m², slope under 12°, relief at least 2 m, 15% or more of cells over 1.5 m from
    the median.
  - flat: median slope under 8° and relief under 1.5 m. Flat-parapet is a flat roof whose edge ring is 0.3 m or more
    above the interior.
  - steep-pitched: median slope 25° or more (about 6/12).
  - pitched: median slope 8° or more.
  - other: the rest.
- A use hint (residential or commercial) comes from Overture buildings and land use at each footprint's inside point.
  It is projected with WGS_1984_(ITRF08)_To_NAD_1983_2011. The hint is coarse: Overture residential land use covers
  most of the city.
- Worst cases were drawn with `figures`: lidar, LOD2.0, LOD1.2, LOD2.0 minus lidar, and a profile. This visual check is
  on rasters; nothing was inspected in a 3D scene.

## Results: the October 22 LOD2.0, before the fill (21,561 buildings, 21,402 judged)
Cells with "a / b" give LOD2.0 / LOD1.2. The error columns are medians over buildings. Hybrid is the number of
buildings the interim hybrid rule gives to LOD2.0.

| Inferred roof type | Buildings | Better | Same | Worse | Broken | \|e\| p50 (m) | \|e\| p95 (m) | Within 0.5 m (%) | Within 1 m (%) | Hybrid |
|---|---:|---:|---:|---:|---:|---|---|---|---|---:|
| multi-level | 107 | 105 | 0 | 0 | 2 | 0.07 / 0.58 | 0.76 / 3.10 | 92 / 49 | 97 / 58 | 91 |
| steep-pitched | 4,663 | 4,132 | 404 | 21 | 106 | 0.09 / 0.70 | 0.65 / 1.68 | 93 / 37 | 97 / 68 | 3,969 |
| pitched | 13,876 | 8,110 | 5,316 | 207 | 243 | 0.07 / 0.40 | 0.39 / 0.96 | 96 / 62 | 99 / 96 | 11,589 |
| flat-parapet | 158 | 38 | 117 | 1 | 2 | 0.07 / 0.14 | 0.56 / 0.87 | 94 / 84 | 98 / 97 | 138 |
| flat | 2,124 | 142 | 1,863 | 62 | 57 | 0.05 / 0.08 | 0.24 / 0.28 | 98 / 98 | 99 / 100 | 1,688 |
| other | 474 | 372 | 82 | 2 | 18 | 0.07 / 0.26 | 0.61 / 1.59 | 93 / 62 | 97 / 79 | 379 |
| too few cells | 159 | | | | | | | | | 0 |
| **all** | **21,561** | **12,899** | **7,782** | **293** | **428** | 0.07 / 0.42 | 0.42 / 1.04 | 96 / 59 | 98 / 94 | **17,854** |

| Lidar roof cover of the footprint | Buildings | Better | Same | Worse | Broken | Too few | LOD2.0 ≥10% at ground | LOD1.2 slab at ground |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| under 80% | 2,380 | 928 | 695 | 232 | 381 | 144 | 2,289 | 591 |
| 80-95% | 4,958 | 2,822 | 2,070 | 53 | 11 | 2 | 1,312 | 3 |
| 95% and over | 14,223 | 9,149 | 5,017 | 8 | 36 | 13 | 13 | 4 |

- **Broken flags** (a building can carry more than one): DROPPED 356, TOP_ABOVE_LIDAR 48, ABOVE_1M 42, MISSING 3.
- **The failures follow lidar support.** 613 of the 721 worse or broken buildings have under 80% lidar roof cover, and
  658 have dropped cells or a footprint at least 10% at ground level. Footprint area by verdict: 3.26 km² better,
  1.37 same, 0.03 worse, 0.07 broken.
- **Predictability:**
  - Roof cover separates bad from passing buildings with an AUC of 0.93 (0.065 as a raw score, since low cover
    predicts bad).
  - The tool's own RMSE on the block has an AUC of 0.85.
  - Footprint area, relief and slope separate them barely or not at all.
  - So the failures are predictable. With the per-building verdict at hand, the hybrid needs no proxy.
- **By use hint:**

  | Use hint | Buildings | Better | Same | Worse | Broken |
  |---|---:|---:|---:|---:|---:|
  | commercial | 664 | 42.0% | 53.2% | 1.2% | 3.6% |
  | residential | 17,848 | 60.9% | 35.9% | 1.4% | 1.8% |

## Worst cases by type (figures in the run folder)
**Multi-level commercial** (107 inferred; 105 better, 2 broken). LOD2.0 follows the roof levels closely; LOD1.2 puts one
block at the median and misses each level by metres.
- **FP 11793** (pilot): a three-level roof. LOD2.0 has a median |error| of 0.08 m, against 1.43 m for LOD1.2.
- **FP 19889** (9,294 m², lidar roof on 32%): the lidar barely sees this roof. LOD2.0 drops large parts of it to
  ground. LOD1.2 is no better: none of its compared cells are within 1 m.
- **FP 17042** (3,944 m², 49% cover; typed "other", commercial hint): a lidar void in the middle of a flat roof. LOD2.0
  turns the void into a ground-level crater, and **the LOD1.2 block is a slab on the ground.**
- **FP 18810** (flat, commercial): the same kind of crater.
- **FP 12572** ("better"): still has ground-level pits where its roof has lidar gaps. These pits are visible but sit
  outside the compared cells, which is why GROUND_PCT is reported.
- **FP 21803**, a church: flagged only for a ridge 1 m above the lidar. It fits well otherwise.

**Steep residential gables** (4,663; 4,132 better). The class where LOD2.0 gains the most: median |error| p95 0.65 m
against LOD1.2's 1.68 m.
- **FP 5651**: typical. LOD2.0 follows ridge and hips with a median |error| of 0.07 m; LOD1.2's is 1.08 m.
- **FP 3549** (100% roof cover): the tool set a whole 10 m wing at ground level although the lidar roof is complete.
  This is not the terrain fill. 9 buildings with at least 95% cover and dropped cells look like this, and the hybrid
  must catch them.
- **FP 3101**: one corner dropped the same way.
- **FP 21389**: a townhouse row with cross gables, reduced to one sloping plane (ABOVE_1M). LOD1.2 is no better.
- **FP 1345**, a church: a 2 m spike at the tower flags it, otherwise within 0.35 m.
- **FP 7169, 9215, 8736, 18722**: a random sample of passing buildings with 10% or more at ground level. Each has a
  corner or wing at ground level exactly where the lidar has no roof (tree overhang). The terrain fill explains them.

**Flat roofs with parapets** (158 inferred; 38 better, 117 same). Neither level models a parapet: LOD2.0 follows the roof
deck (**FP 3666**: deck within 0.05 m, |error| p95 1.36 m for LOD2.0 and 1.07 m for LOD1.2, from the parapet cells).
- **FP 15521**: has dropped parts.
- **FP 21011**: a large parapeted roof the rule typed steep-pitched. LOD2.0 has strips at ground level along interior
  walls. The parapet detector is weak, so read this class as indicative.
- **Plain flat roofs** (2,124): 88% "same". LOD2.0 adds nothing there and only fails through craters and edge notches
  (FP 5629, 18810).

## Fill trial on 12TVL2804 ([fill_trial.py](fill_trial.py), [report_fill.py](report_fill.py)); the citywide rerun follows
The height source was rebuilt with each footprint's missing roof cells (45,378 of 691,415 footprint cells) taken from the
nearest roof cell of the same footprint; terrain was kept outside footprints and under footprints with no roof cell. The
tool was then run as on October 22, on the 639 footprints touching the tile (LOD2.0 in 92 s). The results below cover
the 629 buildings judged in both runs on the same compared cells.

| | October 22 | Filled |
|---|---:|---:|
| better / same / worse / broken | 374 / 228 / 10 / 17 | 381 / 241 / 0 / 7 |
| LOD2.0 within 0.5 m / 1 m, all compared cells | 92.7% / 96.7% | 93.4% / 97.4% |
| LOD2.0 with 10% or more of footprint at ground level | 126 | 2 |
| LOD1.2 slabs at ground level (50% or more) | 11 | 1 |
| Under 80% roof cover (75): worse or broken | 19 | 0 |

- **FP 10567 and 3905** go from broken (whole wings at ground level) to a full gabled roof.
- Of the 7 left broken:
  - 5 carried TOP_ABOVE_LIDAR before the fill too. At least one, FP 2982, is an artefact of the tile edge cutting the
    footprint.
  - FP 19150 is a 1 m ridge overshoot on an otherwise close fit.
  - FP 19839's LOD2.0 shell does not cover the east end of its footprint (MISSING).
- **TOP_ABOVE_LIDAR is over-sensitive.** Most of the flagged buildings that were drawn look fine apart from a spike.
  Keeping them in LOD1.2 costs little.

## Citywide rerun with the filled height source (`fill_trial.py --city`, `report_city.py`)
- **Height source:** 1,257,310 of 18,939,348 footprint cells (6.6%) were filled from the nearest roof cell of their own
  footprint; terrain stays outside footprints and under footprints with no roof cell. Footprints, tool and settings
  are as on October 22. LOD1.2 took 125 s and LOD2.0 48 minutes.
- **One repair:** the citywide LOD1.2 pass returned 21,306 blocks, 255 short of the 21,561 of October 22 (LOD2.0 returned
  all 21,561). Run alone on those 255 footprints with the same height source, the tool builds all of them, so they
  were appended from that run (`fill-trial-city.json`, `patched_lod12`). The cause of the loss in the full pass is not
  known.
- Every building was measured again with the same rules.

| | October 22 | Filled rerun |
|---|---:|---:|
| Better | 12,899 | 13,311 |
| Same | 7,782 | 7,992 |
| Worse | 293 | 20 |
| Broken | 428 | 79 |
| Too few cells | 159 | 159 |
| LOD2.0 within 0.5 m / 1 m of the lidar | 93.9% / 97.3% | 94.6% / 97.8% |
| LOD1.2 within 0.5 m / 1 m | 56.3% / 79.7% | 56.9% / 80.4% |
| LOD2.0 with 10% or more of footprint at ground level | 3,614 | 21 |
| LOD1.2 slabs at ground level | 598 | 3 |
| Hybrid rule: buildings given LOD2.0 | 17,854 | **21,293** |
| Hybrid within 0.5 m / 1 m | 89.5% / 94.9% | **94.4% / 97.7%** |

| Inferred roof type | Buildings | Better | Same | Worse | Broken | Hybrid LOD2.0 |
|---|---:|---:|---:|---:|---:|---:|
| multi-level | 107 | 105 | 0 | 0 | 2 | 103 |
| steep-pitched | 4,663 | 4,232 | 397 | 4 | 30 | 4,628 |
| pitched | 13,876 | 8,413 | 5,415 | 16 | 32 | 13,825 |
| flat-parapet | 158 | 40 | 116 | 0 | 2 | 156 |
| flat | 2,124 | 130 | 1,990 | 0 | 4 | 2,117 |
| other | 474 | 391 | 74 | 0 | 9 | 464 |
| too few cells | 159 | | | | | 0 |

- **Remaining flags** (79 broken): TOP_ABOVE_LIDAR 33, ABOVE_1M 33, DROPPED 9, MISSING 4 (a building can carry more than
  one). Of the 99 worse or broken, 32 have under 80% roof cover and 3 have 95% or more cover and dropped parts.
- **Worse (20):** 16 pitched and 4 steep-pitched, all small (the largest is 154 m²). FP 12936 has a diagonal wedge
  dropped to ground on a covered roof, a fault of the tool.
- **Broken, large cases:**
  - FP 4680 (5,829 m², flat-parapet): flagged only for a 1.8 m spike in one corner; otherwise a median error of 0.14 m
    and LOD1.2 is no better.
  - FP 9451 (4,566 m², a parking structure): the lidar has a sunken roof area that both levels flatten.
  - FP 1345 (church): the same tower spike as before.
- **The earlier worst cases are repaired.** FP 17042 (3,944 m², lidar void) went from a ground-level crater with a
  ground slab for LOD1.2 to "same": LOD2.0 within 1 m on 98.3%, LOD1.2 on 92.9%. FP 3549 (steep gable wing at ground
  level) is "better": LOD2.0 within 1 m on 99.1%, LOD1.2 on 41.6%.
- **New flags:** 31 buildings that were "better" before are "broken" now. I did not look into those 31 individually (the
  tool's roof fit shifts when its input changes). Other moves: 1,011 same to better, 742 better to same, 258 broken
  to same, 139 broken to better, 243 worse to same.
- **TOP_ABOVE_LIDAR is over-sensitive**, as the pilot also showed: a 1 to 2 m spike in one corner of an otherwise close
  roof is enough. The hybrid sends them to LOD1.2 anyway, which costs little accuracy on those.
- Footprint area by verdict: better 3.36 km², same 1.33, worse 0.001, broken 0.033, too few 0.010.

## Scene layer packages from the filled massing (not uploaded)
[make_slpk.py](../../2026-10-22/hosting/scene-layers/make_slpk.py), unchanged, on `massing-filled-20261023`, into
`H:\lidar3-salt-lake-valley
uns\scene-layers-filled-20261023\` (record `slpk-filled.json`, copied here).

| Package | Buildings | Size | Validate Scene Layer Package |
|---|---:|---:|---|
| buildings_lod12.slpk | 21,561 | 9.0 MB | passes; the usual "vertex normals may be required" warning only |
| buildings_lod20.slpk | 21,561 | 14.6 MB | the same |

- Each package's own FP_ID statistics (count 21,561, sum 237,493,394) equal its source feature class's, so every building
  is in each package. Both are labelled WGS84 with the EGM96 vertical label, with heights still NAVD88, as on October 22
  ([scene-layers README](../../2026-10-22/hosting/scene-layers/README.md)).
- **These are the two plain levels, not the hybrid** (next section).
- The October 22 packages and the public LOD1.2 scene layer are untouched.

## Hybrid scene layer package (not uploaded)
[build_hybrid.py](build_hybrid.py) on `massing-filled-20261023` and `lod2-check-filled-20261023`, into
`H:\lidar\2023-salt-lake-valley\runs\scene-layers-hybrid-20261023\` (`buildings_hybrid.slpk`, 13.9 MB; `hybrid.gdb`; the
validation report; record `hybrid.json`, copied here). One feature per FP_ID, 21,561 in all.

| LEVEL | FALLBACK_REASON | Buildings |
|---|---|---:|
| LOD2.0 | | 21,293 |
| LOD1.2 | too-few (under 20 compared cells) | 159 |
| LOD1.2 | worse-or-broken | 99 |
| LOD1.2 | ground-level (passes, but LOD2.0 has 10% or more of the footprint at ground level) | 10 |

- **Rule:** LOD2.0 where the verdict is better or same and LOD20_GROUND_PCT is under 10; LOD1.2 otherwise. The counts
  equal the hybrid counts above.
- **Added fields:** LEVEL, CHECK_VERDICT, LOD20_GROUND_PCT (measured for every building) and FALLBACK_REASON, besides the
  tool's own LOD (1.2 or 2.0) and the footprint attributes of the other packages.
- **Checks:** Validate Scene Layer Package passes, with only the vertex-normals warning. The package's FP_ID statistics
  (count 21,561, sum 237,493,394) equal the hybrid feature class's. The script checks that LEVEL agrees with the tool's
  LOD field on every feature and that no FP_ID appears twice.
- It carries the check's verdicts, which the plain packages do not. The fallback blocks are the filled run's LOD1.2.

## Trial: roofer LoD2.2 on 12TVL2804 (October 24)
Roofer ([3DBAG/roofer](https://github.com/3DBAG/roofer), the 3D BAG's reconstruction tool) was installed, run on the pilot
tile, converted to multipatch and a scene layer package, and scored. Details in [TOOLS.md](TOOLS.md).
**One tile, 587 judged buildings, roofer's default parameters.**
- **Install:** the official `roofer-windows-x86_64-v1.0.0.zip` (12 MB, SHA-256 `143413f1…ae7f`, no checksum published to compare)
  from the project's GitHub releases, unzipped into its own folder `runs\roofer-20261024\roofer-1.0.0` on the SSD. No PATH,
  user-site or pip changes; it ran at once (`roofer 1.0.0`).
- **Input** ([roofer_input.py](roofer_input.py)): the tile's working LAS reduced to the consensus roof points (class 6: 3.72 M
  first or single returns that at least two of native, FRACTAL and Esri call building) and native ground (class 2: 2.66 M),
  plus the 591 county footprints lying completely within the tile (FP_ID kept). Roofer reads both directly.
- **Run:** `roofer --lod12 --lod22 --id-attribute FP_ID --srs EPSG:6341 --jobs 12`: **23 seconds** for 591 buildings
  (Esri's tool took 92 s for LOD2.0 on 639 footprints of the same tile, and 48 min citywide). Output is CityJSONSeq with its
  own RMSE, planes and roof type per building. 587 buildings got solids; 3 were skipped as "point cloud unusable" (all too
  few cells to judge here anyway) and 1 came out with no geometry.

### Route to a multipatch and a scene layer ([roofer_to_multipatch.py](roofer_to_multipatch.py))
1. [collect_cityjson.py](collect_cityjson.py): the CityJSONSeq into one CityJSON (1,178 objects: 591 buildings, 587 parts).
2. **cjio 0.10.1** (`lod_filter 2.2`, `export obj`): installed with uv into its own virtual environment
   `roofer-20261024\tools\cjio-venv` (cjio, click, numpy and `triangle`, which cjio needs to triangulate; from PyPI, nothing
   user-wide). The OBJ keeps real UTM metres: 587 objects, 30,513 vertices, 58,738 triangles.
3. [split_obj.py](split_obj.py): one OBJ per part. **Import 3D Files merges everything in a file into one feature**, in both
   of its modes (the first try gave 1 multipatch for all 587).
4. **Import 3D Files** (`ONE_FILE_ONE_FEATURE`, NAD83(2011) UTM 12N, Z up): 587 multipatches, one per part, in
   `multipatch\roofer.gdb\roofer_lod22`, with FP_ID, roofer's attributes (roof type, planes, ridgelines, RMSE, ground and
   roof heights, point density, extrusion mode) and the county footprint attributes (heights, roof cover, status). No county
   attribute is empty.
5. **Scene layer package** by make_slpk.py's method (WGS84, ITRF08 transformation named): `buildings_roofer_lod22.slpk`, 0.44 MB.
   Validate Scene Layer Package passes with **no warnings**, and the package's FP_ID statistics (587, sum 6,521,683) equal the
   feature class's.

| Check on the route | Result |
|---|---|
| Each multipatch's extent against its vertices in the CityJSON | all 587 within 0.3 mm in X, Y and Z |
| Imported geometry as ArcGIS rasterizes it against score_roofer.py's own rasterization of the CityJSON roof faces | 614,862 shared cells; median difference 0.1 mm; 95.7% within 5 cm, 97.5% within 25 cm; 38,621 cells only in mine, 6,841 only in the multipatch raster |
| Closed solids in the OBJ (every edge in two triangles) | 7 of 587 parts are not (4709-0, 9244-0, 11428-0, 11755-0, 11793-0 and two more); whether roofer's solid or cjio's triangulation is at fault was not checked |
| `cjio validate` | **not run**: it needs the compiled `cjvalpy`, which was not installed |

The two rasterizations differ most where the multipatch raster is lower (13,405 of the 15,254 cells that differ by more than
25 cm, spread over 460 buildings; 16% of the differences are within 2 cells of a roof edge). That was not explained, so
roofer was scored from the ArcGIS raster, which is how Esri's blocks are measured.

### Scoring ([score_roofer.py](score_roofer.py))
Roofer's LoD2.2 was put through the same per-building rules as the check, beside Esri's LOD1.2 and LOD2.0 *from the filled
run*; roofer's LoD1.2 is scored too (rasterized by the script). The first pass used the script's own rasterization of
roofer's roof faces (below as "first pass"); the main figures use Multipatch To Raster of the imported features.

| Pooled over compared cells (587 buildings for Esri, 586 for roofer) | Esri LOD1.2 | Esri LOD2.0 | roofer LoD1.2 | roofer LoD2.2 |
|---|---:|---:|---:|---:|
| within 0.5 m of the lidar | 54.7% | 93.4% | 51.8% | **96.8%** |
| within 1 m | 77.0% | 97.4% | 74.6% | **98.1%** |
| median building: \|e\| p95 | 1.02 m | 0.42 m | 1.13 m | **0.25 m** |

| Verdict against Esri LOD1.2 as the flat baseline | Better | Same | Worse | Broken | Too few |
|---|---:|---:|---:|---:|---:|
| Esri LOD2.0 (filled) | 358 | 228 | 0 | 1 | 4 |
| roofer LoD2.2 | 387 | 181 | 1 | **17** | 4 (+1 no geometry) |
| roofer LoD2.2, first pass | 374 | 181 | 1 | 30 | 4 (+1 no geometry) |

- **Roofer is tighter where it works.** Its median building has a p95 error of 0.25 m against Esri's 0.42 m, and it is closer
  on p95 for 406 of 586 buildings. Median p95 by type (Esri LOD2.0 / roofer LoD2.2): steep-pitched 0.62 / 0.32 m, pitched
  0.39 / 0.25 m, multi-level 0.73 / 0.33 m (5 buildings), flat-parapet 0.57 / 0.38 m (5), flat 0.21 / 0.12 m, other
  0.57 / 0.58 m. Within 1 m the two are level. Both pass on 567 of Esri's 585 passes.
- **No ground-level pits** for either: neither has a building with 10% or more of the footprint at ground level. Roofer builds
  roofs from the roof points only, so the October 22 terrain-fill fault cannot occur.
- **The 17 broken:** 11 are TOP_ABOVE_LIDAR (one also ABOVE_1M): roofer fitted a roof plane into cells where the lidar saw
  no roof, for example FP 9793 (420 m²) and FP 19424 (411 m²). 6 are MISSING (a solid that does not reach 5% or more of the lidar
  roof cells; the largest are FP 5629 and FP 1165, about 570 to 580 m²). 13 of the 17 have under 80% roof cover and Esri's
  LOD2.0 passes on all 17.
- **By lidar roof cover** (roofer / Esri LOD2.0 broken): under 80%: 13 of 69 / 0; 80 to 95%: 4 of 151 / 1; 95% and over: 0 of 366 / 0.
- **Nothing here says roofer is better than the other tool at what matters for Urban:** the check measures fidelity to the
  lidar, which both were fed (roofer the consensus points, Esri the consensus raster). Roofer's lead is in tight tolerance
  (0.5 m) and p95; at 1 m they are level. Roofer's output is tile-bound and was made with its default parameters.
- **Not done:** nothing was viewed in 3D or against imagery, one tile only, no citywide run, no upload. Whether this LoD2.2 is
  what the European municipalities' LOD 2.2 looks like was not checked.
- Files in `roofer-20261024\`: `input\` (LAS, shapefile, `roofer-input.json`), `output\*.city.jsonl`, `multipatch\`
  (CityJSON, OBJ parts, `roofer.gdb`, the raster, the package and its validation report, `roofer-multipatch.json`),
  `check\` (first pass) and `check-multipatch\` (main scoring, with `figures\` from the first pass), `roofer-run.log`, `tools\`.
  Copies of the JSONs and the log are beside this README.

## Roofer on the whole city, and a three-way hybrid (October 24)
[roofer_city.py](roofer_city.py) and [roofer_city_stages.py](roofer_city_stages.py) ran the trial above on all 21,562 footprints,
and scored every building with the same rules as the Esri check. Run folder:
`H:\lidar\2023-salt-lake-valley\runs\roofer-city-20261024\` (results copied to [roofer-city](roofer-city)). Nothing uploaded.
**Default roofer parameters; the same lidar roof is both the input and the reference.**

**Run:**
- **Points:** the consensus roof and ground points of all 61 tiles, 8.9 GB, built in 4 minutes with 4 workers.
- **Footprints:** each footprint goes to the tile that holds its inside point. All 21,562 are assigned, to 52 tiles.
- **Edges:** for each tile, roofer got the tile's own points plus every neighbour's points inside the extent of its
  footprints plus 20 m, merged into one LAS. Roofer would otherwise pick one point cloud per building. 27.2 million
  neighbour points were added across the city.
- **Roofer:** 52 tiles, no failures, 18 minutes including the merges. It wrote 21,569 buildings from 21,562 footprints. The 7
  extra are a second, degenerate "skip" building for 7 multi-part footprints (the same 7 that got a spare empty block from
  Esri's tool on October 22); they were dropped.
- **Result:** 21,436 buildings have solids. 126 have none ("point cloud unusable" or skipped); 134 have no compared cells.

**Conversion** (the route proven on the pilot, per tile):
- **Triangulation:** cjio's default triangulator `triangle` crashed (native access violation) on the whole-city file and,
  tile by tile, on 3 tiles (12TVL2204, 12TVL2504, 12TVL3104) given all their buildings at once; each passed when
  halved. All 21,436 buildings were triangulated by `triangle`; none needed the fallback.
- **Earcut rejected:** cjio's `--sloppy` earcut triangulator also finished the city file, but left 3,581 of 21,474 parts with
  open edges (17%) against 180 of 21,436 buildings (0.8%) with `triangle`. On the pilot tile it left 121 of 587 against 7.
  The first citywide conversion with earcut was discarded.
- **Checks:** every building multipatch's extent matches its CityJSON vertices to within 0.9 mm (the merge moves vertices by
  at most 0.5 mm). 26 buildings have more than one part. The citywide raster is Multipatch To Raster on the roof grid.

**Scoring, every building** (roofer LoD2.2 in the "LOD2.0" slot of `lod2_check.py measure`, Esri's filled LOD1.2 as the flat
baseline; Esri's own figures are the filled run's):

| Pooled over compared cells | Esri LOD1.2 | Esri LOD2.0 | roofer LoD2.2 |
|---|---:|---:|---:|
| within 0.5 m of the lidar | 56.9% | 94.6% | **96.9%** |
| within 1 m | 80.4% | 97.8% | **98.2%** |
| median building: \|e\| p95 | | 0.37 m | **0.24 m** |
| buildings worse or broken (of 21,383 with roofer geometry) | | 98 | 583 |

- **Roofer is closer on p95 for 14,500 of 21,383 buildings (68%).** Median p95 (Esri LOD2.0 / roofer) and worse or broken
  buildings (Esri / roofer) by inferred type: steep-pitched 0.55 / 0.29 m, 33 / 164; pitched 0.34 / 0.23 m, 48 / 359;
  multi-level 0.68 / 0.37 m, 2 / 4; flat-parapet 0.48 / 0.29 m, 2 / 2; flat 0.21 / 0.16 m, 4 / 32; other 0.55 / 0.28 m, 9 / 22.
- **Roofer fails more often, and on weak lidar.** Of its 583 worse or broken buildings, 476 have under 80% lidar roof cover
  (21% of those 2,218 buildings), 84 have 80 to 95% (1.7% of 4,955) and 23 have 95% or more (0.16% of 14,210).
  Flags (a building can carry more than one): TOP_ABOVE_LIDAR 329, MISSING 230, ABOVE_1M 34. The largest are big
  footprints where the lidar saw little roof (FP 19889, 10363, 9661, 18825, 576, 11923), which Esri's tool also struggles with.
- **Where they agree:** both pass on 20,712 buildings; roofer passes and Esri's LOD2.0 is broken on 70; Esri passes and roofer is
  broken on 555.

**Three-way hybrid.** Per building: roofer LoD2.2 if its verdict is better or same and under 10% of its footprint is at ground
level; else Esri LOD2.0 if that passes the same test; else Esri LOD1.2. One feature per building,
`hybrid.gdb\buildings_three_way`, scene layer package `buildings_three_way.slpk` (19.1 MB), with LEVEL, CHECK_VERDICT,
ROOFER_VERDICT, ESRI_VERDICT and FALLBACK_REASON added; per-building choices in `three-way.csv`.

| LEVEL | Buildings | Footprint area | Why the others fall back |
|---|---:|---:|---|
| roofer LoD2.2 | 20,790 (96.4%) | 4.62 km² | |
| Esri LOD2.0 | 593 | 0.10 km² | roofer broken 552, worse 18, no geometry 18, ground-level 5 |
| Esri LOD1.2 | 178 | 0.02 km² | too few lidar cells 159, otherwise neither passes |

| Pooled within 0.5 m / 1 m | |
|---|---:|
| Esri LOD2.0 alone | 94.6% / 97.8% |
| Esri-only hybrid (LOD2.0 else LOD1.2) | 94.4% / 97.7% |
| roofer alone (where it has geometry) | 96.9% / 98.2% |
| **three-way hybrid** | **96.8% / 98.2%** |

- **Validation:** Validate Scene Layer Package passes with no warnings. The package's FP_ID statistics (21,561, sum 237,493,394) equal
  the feature class's, and each FP_ID appears once.
- **The three-way hybrid is about as accurate as roofer alone on this measure.** The fallback removes 583 buildings
  that the check flags (invented roof planes, missing roof), but those barely move a pooled within-1 m figure. Its value is
  in the defects, not in the pooled number. The selection uses the same lidar as the scoring, so the pooled figure for the
  mix is a little optimistic.
- **Not viewed in 3D**, and not compared with imagery. One thing this check cannot see is how a roof looks: pitch,
  eaves and ridge form. The European LOD 2.2 you described is judged by eye.

## Looking at it in 3D (October 24)
A local web viewer and an ArcGIS Pro project, in [viewer](viewer). Nothing uploaded; everything is read from the `.slpk` files.
Run folder: `H:\lidar\2023-salt-lake-valley\runs\viewer-20261024\`.

**Web viewer** (`viewer\start_viewer.bat`, then http://127.0.0.1:8801/): three synchronized scenes of the same place:
the Esri LOD2.0 hybrid (October 23 package), roofer LoD2.2 alone (`buildings_roofer_only.slpk`, new, 17.3 MB, 21,436 buildings,
validated) and the three-way hybrid. Drag in one and the others follow. A drop-down jumps to the 15 bookmarks below; the
caption gives the numbers. Roof edges can be switched off. **Colour tells the model:** light grey roofer, blue Esri LOD2.0,
orange Esri LOD1.2 (so the three-way view shows where the fallback happened).
- [serve_scene.py](viewer/serve_scene.py) serves the page and the packages on 127.0.0.1 only. An `.slpk` is a zip of the resources
  an I3S REST scene layer serves, so the server maps requests to entries (layer, node pages, geometries, attributes) and passes the
  gzipped entries through. **The ArcGIS Maps SDK for JavaScript 5.1.27 reads the three packages this way and draws them**, so this
  also tests the packages in the web client they are meant for. The page loads the SDK from Esri's CDN (`js.arcgis.com`); no data goes there.
- It is a **global scene** (WGS84): the packages are WGS84, a UTM local scene refuses them, and a Web Mercator one would stretch
  east-west by 1.3 here.
- **There is no terrain.** The ground is the globe's surface; for each bookmark the layers are lowered by that building's ground
  elevation so it stands on the ground. Neighbours on a slope float or sink a little. It also means no imagery or street context.
- The browser pane built into this app is throttled (about 1 frame a second) when it is hidden, which starved the 3D view, so the
  screenshots were taken with the Playwright browser. WebGL there is software-rendered and lost its context at 1000 px wide;
  800 px worked, and the page reloads and retries a bookmark once if a screenshot hangs (no retries were needed).

**Screenshots:** `viewer-20261024\screens\<id>_<esri|roofer|threeway>.png` (45) and `screens\composite\<id>.png` (15, the three
side by side with the numbers). They are kept on the SSD, not in the repo. [compose.py](viewer/compose.py) makes the composites.

**Bookmarks** ([pick_bookmarks.py](viewer/pick_bookmarks.py), [bookmarks.json](viewer/web/bookmarks.json)): picked from the per-building
results by rule before any was looked at, not by eye.

| ID | Category | FP_ID | Type, m² | Roofer (p95) | Esri LOD2.0 (p95) | Three-way uses |
|---|---|---:|---|---|---|---|
| b01 | win-esri-defect | 7226 | pitched, 284 | better (1.1 m) | broken (DROPPED) (9.63 m) | roofer LoD2.2 |
| b02 | win-esri-defect | 4533 | pitched, 388 | better (0.2 m) | broken (DROPPED) (7.6 m) | roofer LoD2.2 |
| b03 | win-esri-defect | 14920 | pitched, 199 | same (0.4 m) | broken (DROPPED) (7.04 m) | roofer LoD2.2 |
| b04 | win-gable | 15339 | steep-pitched, 371 | better (1.16 m) | same, MIXED (9.94 m) | roofer LoD2.2 |
| b05 | win-gable | 22001 | steep-pitched, 253 | better (0.41 m) | better (1.96 m) | roofer LoD2.2 |
| b06 | win-commercial | 12234 | steep-pitched, 823 | better (0.53 m) | better (2.04 m) | roofer LoD2.2 |
| b07 | win-commercial | 20802 | steep-pitched, 656 | better (0.73 m) | better (2.13 m) | roofer LoD2.2 |
| b08 | fail-invented | 16729 | steep-pitched, 105 | broken, TOP_ABOVE_LIDAR (2.34 m) | better (0.23 m) | Esri LOD2.0 |
| b09 | fail-invented | 3587 | steep-pitched, 134 | broken, TOP_ABOVE_LIDAR (0.33 m) | better (0.89 m) | Esri LOD2.0 |
| b10 | fail-invented | 16382 | pitched, 281 | broken, TOP_ABOVE_LIDAR (0.49 m) | better (0.25 m) | Esri LOD2.0 |
| b11 | fail-missing | 9661 | steep-pitched, 3,441 | broken, MISSING (1.04 m) | better (0.95 m) | Esri LOD2.0 |
| b12 | fail-missing | 18825 | other, 3,274 | broken, MISSING (0.24 m) | better (0.67 m) | Esri LOD2.0 |
| b13 | fail-worse | 19047 | flat, 106 | worse (6.01 m) | same (0.27 m) | Esri LOD2.0 |
| b14 | typical | 405 | pitched, 220 | better (0.24 m) | better (0.3 m) | roofer LoD2.2 |
| b15 | typical | 1902 | pitched, 178 | better (0.24 m) | better (0.21 m) | roofer LoD2.2 |

No building met the "both fail, 1,500 m² or more" rule, so there is no bookmark for it.

**What the five composites I looked at show** (b01, b04, b08, b11, b13; the other ten were not examined by eye):
- **b01 (FP 7226), a clear win.** Esri's own hybrid draws this L-shaped house as an orange flat block (its LOD2.0 had dropped parts, so the
  hybrid fell back to LOD1.2). Roofer's version has the real roof forms, and the three-way hybrid uses it.
- **b04 (FP 15339), a clear win.** Esri's LOD2.0 has an open hole through the middle of the roof; roofer's has a complete roof with a dormer.
- **b08 (FP 16729), a clear failure, caught.** Only 17% of the footprint has lidar roof. Roofer builds a tall wedge-shaped volume that does
  not look like a house; Esri's pitched L-shaped roof is plausible, and the three-way hybrid uses Esri's.
- **b11 (FP 9661), unclear.** A 3,441 m² complex. Roofer builds separate wings with gaps between them; Esri's is one fused roof slab
  bridging the gaps with odd creases. The check calls roofer broken (MISSING) because lidar roof cells in those gaps are uncovered, but
  roofer's separate wings may be the more faithful reading. This one needs a person's judgement.
- **b13 (FP 19047), subtle.** In this view the roofer and Esri versions of the flat building look alike at a glance; the 6 m p95 error is not obvious.
- **So the metric and the eye do not always agree**, in both directions. The viewer exists so you can decide.

**Pro project** ([build_pro_project.py](viewer/build_pro_project.py), `viewer-20261024\pro\Millcreek_buildings_3D.aprx`): three scenes, one per package,
with the same 15 bookmarks in each, so linking two views (View > Link Views) gives the same side-by-side. **Not checked in Pro:** a scene
cannot be rendered or exported from a script (a layout with a scene frame exported blank), so the project was built and its bookmarks
read back (15 in each scene) but never opened. Bookmark cameras look from 1.6 x the building size away, 32 degrees below horizontal; the
scene's ground is Pro's default online elevation, so open it with a connection, and check the first bookmark before trusting the rest.

## Clean-up, imagery check and roof attributes (October 24, later)
Brian looked at the three-way hybrid and asked for the edges and "little snags" to be cleaned up, an independent check, the public layer's
replacement prepared, and roof attributes for planning. Nothing was uploaded or shared.

### What the snags are, and what roofer's settings can do ([roofer_sweep.py](roofer_sweep.py), [roofer-sweep.json](roofer-sweep.json))
On the pilot tile (587 buildings, 3,131 roof faces with roofer's defaults) the countable snags are few: 9 faces under 0.5 m² in plan, 20 slivers
narrower than 0.4 m. (The first sweep also reported 55 "steep" faces; that count took a face's orientation from its first three vertices,
which is unreliable when they are nearly collinear. With the vector-area normal there are none, in any configuration or citywide.) Twelve settings were run
on the pilot, 22 s each, and scored with the same rules as the Esri check:

| Setting | Roof faces | Tiny | Slivers | Within 0.5 m / 1 m | Median p95 | Broken |
|---|---:|---:|---:|---|---:|---:|
| defaults | 3,131 | 9 | 20 | 96.5% / 98.0% | 0.284 m | 30 |
| `--plane-detect-min-points 30` | 3,023 | 4 | 7 | 96.4% / 98.0% | 0.287 m | 30 |
| min-points 50 | 2,831 | 3 | 3 | 96.2% / 97.8% | 0.302 m | 34 |
| min-points 80 | 2,579 | 1 | 2 | 95.6% / 97.5% | 0.338 m | 36 |
| `--complexity-factor 0.7` | 2,350 | 2 | 2 | 94.5% / 97.4% | 0.432 m | 34 |
| complexity 0.5 | 1,697 | 0 | 0 | 89.8% / 95.5% | 0.759 m | 54 |
| `--plane-detect-epsilon 0.5` | 2,620 | 5 | 16 | 95.1% / 98.0% | 0.460 m | 33 |
| `--no-clip-terrain` | 3,107 | 6 | 14 | 96.5% / 98.0% | 0.284 m | 24 |

- **Fewer snags cost detail, except one setting.** Lower complexity and a looser plane tolerance remove snags by removing roof detail (the
  median error rises from 0.28 m to 0.43 m at complexity 0.7). **`--plane-detect-min-points 30` cut slivers by 65% and tiny faces by 56% on the pilot
  with no change in fit**, so it was chosen.
- **The ragged edges are roofer's terrain clipping, not tiny faces.** By default roofer cuts out of the roofprint every patch where it sees ground
  points. Where the county footprint is larger than the roof, that is right; where the lidar sees ground *through* a glass roof or loses a white
  roof, it takes real roof away and leaves ragged or half-missing outlines. In eight pilot buildings the clipped result covers 16 to 79% less
  of the footprint than the unclipped one ([roofer_inspect.py](roofer_inspect.py)). On aerial imagery ([imagery_compare.py](imagery_compare.py)) the clipping removed real
  roof on the white-roofed FP 19897 and 2663 and the glass-and-solar roof FP 10567, and was right on FP 16951, where the footprint is bigger than the
  building; four more were unclear (trees, a sliver footprint). The class-2 points inside these footprints sit at ground level (about 0 m above ground), so the lidar
  does see ground there. **So clipping is faithful to the lidar and the county footprint is what is wrong in some places; neither setting is right
  everywhere**, and `--no-clip-terrain` was not adopted.
- **What is not cleaned up:** roofer breaks complex roofs into many small facets (10 of 97 sampled buildings, below), and clipped outlines stay
  as the lidar left them. Fixing either needs editing the geometry (merging near-coplanar neighbours, regularising outlines), not another setting.

### v2: the citywide rerun with min-points 30 ([roofer_city.py](roofer_city.py); run folder `roofer-city-v2-20261024`)
The same pipeline as above, about 30 minutes end to end (roofer 15 minutes, no failures; conversion with `triangle` on every building; it crashed again on three whole
tiles, 12TVL2204, 2503 and 2803, each passing when halved, none by earcut), reusing v1's points.

| | v1 (defaults) | v2 (min-points 30) |
|---|---:|---:|
| Roof faces / per building | 99,026 / 4.62 | 96,187 / 4.49 |
| Tiny faces (buildings with one) | 202 (0.9%) | **126 (0.6%)** |
| Slivers (buildings with one) | 559 (2.3%) | **305 (1.2%)** |
| Buildings with a roofer solid | 21,436 | 21,407 |
| Roofer worse or broken, of those judged | 583 | 639 |
| Roofer pooled within 0.5 m / 1 m | 96.87% / 98.18% | 96.79% / 98.14% |
| **Three-way: roofer / Esri LOD2.0 / Esri LOD1.2** | 20,790 / 593 / 178 | 20,730 / 647 / 184 |
| **Three-way pooled within 0.5 m / 1 m** | 96.82% / 98.17% | 96.74% / 98.13% |

The setting trades a little accuracy for tidiness citywide: 38% fewer tiny faces and 45% fewer slivers, 0.04 points less of the roof within 1 m, 56 more
buildings sent to the fallback. Both are small; v2 is the one packaged.

### Independent check on imagery ([imagery_check.py](imagery_check.py), run folder `imagery-check-20261024`)
The scoring compares models with the lidar both were built from. This puts roofer's roofs next to something else: Esri World Imagery (a public export service;
the only network use, one request per building, bounding box only). **A seeded random sample of 109 buildings** (seed 20261024): 97 where the
three-way hybrid uses roofer, stratified by inferred roof type, 60 to 1,500 m², plus 12 that fell back to Esri LOD2.0 because roofer was flagged.
Each cell shows the imagery and the same imagery with roofer's roof planes drawn (coloured by the compass direction each faces; flat planes grey) and the
county footprint dashed yellow. Imagery has its own position error and no true-ortho correction, so each overlay is shifted to the strongest image edges
(median 0.66 m; 25 of 109 needed more than 3 m, mostly on taller roofs). 14 sheets of 8 are in `sheets\`.

**Ratings were made by the assistant reading these crops (340 pixels a building), not by a City reviewer.** G: the roof form matches the imagery;
P: partly, the right idea with wrong detail; B: poor; U: cannot tell (trees, shade, a footprint that is not a building). A blank rating file is in the run folder
for a second opinion; plain-view overlays cannot show chimneys, which were judged in 3D only.

| Roofer buildings (97) | G | P | B | U |
|---|---:|---:|---:|---:|
| all | **61 (63%)** | 28 (29%) | **0** | 8 (8%) |
| flat (11) | 10 | 1 | 0 | 0 |
| steep-pitched (32) | 17 | 12 | 0 | 3 |
| pitched (39) | 24 | 11 | 0 | 4 |
| other, flat-parapet, multi-level (15) | 10 | 4 | 0 | 1 |

- **What matches well:** hip roofs with all their planes (FP 7167, 4944, 12942, 8777), gables with the right ridge direction, stepped flat roofs with a
  pitched section separated from the flat (FP 20434, 14025), townhouse rows with dormers (FP 1916).
- **What is "partly":** 10 of the 28 are roofer **fragmenting a complex roof** into many facets where one or two planes are real (FP 11100, 5448, 5893,
  1096, 12961, 10419), one has thin spurious strips along two edges (13765), and the rest are low-slope roofs drawn pitched or the reverse. This is the
  snag Brian saw, and no setting removed it.
- **The fallback was right in 3 of the 12, wrong in 3, unclear in 6.** Roofer looked right for FP 5842, 3756 and **18536**, where the county footprint is a
  demolished building on a dirt lot and roofer modelled only what stands; the check flagged it and the hybrid replaced it with Esri's full-footprint roof.
  For FP 17644, 15336 and 8007 roofer's single big plane misses a hip or a complex roof and the fallback was right. So the "broken" rule is a
  blunt tool: it protects against roofer's real failures and also replaces some good models.

### Roof attributes ([roof_attributes.py](roof_attributes.py))
From roofer's roof faces (not the fallbacks): per plane, in `roof_planes.csv` (96,187 rows), and per building, in `building_roofs.csv` (21,407): plane count,
roof plan and true area, slopes, the main plane's azimuth, ridge, eave and building height above ground, flat area and south, east, west and
north-facing area (planes of 5 to 70 degrees), snag counts. All are in the v2 package where LEVEL is roofer LoD2.2, with descriptions in `fields.md`.
**Across the 21,407 buildings: 4.95 km² of roof surface, 1.25 km² of it flat; usable sloped area 0.96 km² south, 0.95 km² north, 0.90 km² east, 0.88 km² west; the
median plane slope by area is 17°.** Sanity check on a known gable (FP 5651): two planes of 33.3° facing 91° and 271° (a north-south ridge) and a cross gable at 1° and 181°. They are
geometry, **not a solar production estimate**: no shading, panels or weather.

### The v2 package and the public layer ([build_v2_package.py](build_v2_package.py), [PUBLISH_PLAN.md](PUBLISH_PLAN.md))
`roofer-city-v2-20261024\v2\buildings_hybrid_v2.slpk`: 20.2 MB, 21,561 buildings, 20,730 with roof attributes, validated with no warnings, FP_ID statistics equal the
source's, drawn correctly by the ArcGIS Maps SDK 5.1 (`viewer\start_viewer_v2.bat`). The live public LOD1.2 layer has **598 blocks on the ground**
([ground-slab-fp-ids.csv](ground-slab-fp-ids.csv)); the plan swaps it for v2 by a new item and a repointed scene, each step on Brian's go-ahead, with the decisions that are
his (roof forms were staff-only on October 23; the wording; a licence line for roofer) and an interim fix. An `upload.py` entry `buildings3d_v2` was added; its dry run was
refused in the Claude session; it passed in the October 24 wrap-up (no upload). Draft item text: [draft-metadata/buildings3d_v2.md](draft-metadata/buildings3d_v2.md).

## What was not checked
- No independent roof truth: the lidar is the surface the massing was fitted to, and no surveyed roof was used.
- The original Esri-only check did not include a visual review. Later sections record the 3D comparison viewer and assistant imagery checks. No City-rated or surveyed roof validation is complete.
- Roof types and use hints are inferred, and the parapet rule misses some parapets.
- The tool's roof fit is not stable: 31 buildings changed from better to broken when its input changed. A published version should be rechecked as published.
- The 109 fallback buildings use LOD1.2 as it is; those blocks were measured, not inspected.
- The lidar is from 2023; buildings built or demolished since are whatever the footprints say.

## Outputs
On the SSD, `H:\lidar\2023-salt-lake-valley\runs\`:
- `lod2-check-20261023\`:
  - `lod2-check.csv`: one row per building. It holds both levels' errors, GROUND_PCT, DROPPED_PCT, type, use hint,
    verdict and flags.
  - `lod2-check.gdb`: the same data as table `results`, and joined onto `footprints` for review in Pro.
  - `lod2-check.json`: the summary and the rules, also copied here.
  - The three rasters and `figures\fp<FP_ID>.png`.
- `lod2-check-pilot-20261023\`: the pilot, the same outputs on 12TVL2804.
- `fill-trial-20261023\` and `lod2-check-fill-trial-20261023\`: the filled height source for 12TVL2804, its massing and this check on it.
- **`massing-filled-20261023\`: the citywide filled rerun.** `massing.gdb` holds `lod12`, `lod20` and `footprints`; also the
  filled `height_source_filled.tif` and `fill-trial.json` (copied here as `fill-trial-city.json`). The log is
  `massing-filled-20261023.log` beside it.
- **`lod2-check-filled-20261023\`: this check on the rerun**, the same files as `lod2-check-20261023\` (the per-building CSV
  and gdb for the proposed layer; `lod2-check-filled.json` is copied here).
- `lod2-probe-20261023\`: the 255 blocks of the LOD1.2 repair.
- `scene-layers-filled-20261023\`: the two scene layer packages and their validation reports.
- `scene-layers-hybrid-20261023\`: the hybrid package, its `hybrid.gdb` and validation report.
- `roofer-20261024\`: the roofer trial (above).
- `viewer-20261024\`: the viewer's screenshots, the Pro project and the server log.
- `roofer-sweep-20261024\` (12 settings on the pilot), `roofer-city-v2-20261024\` (the v2 run, `v2\` the package), `imagery-check-20261024\` (sample, sheets, ratings).
- `roofer-city-20261024\`: the citywide roofer run (above): per-tile points and footprints, `output\<tile>` roofer results, `convert\` (CityJSON, per-building OBJ, `roofer.gdb`, raster), `check\` (the per-building scoring), `hybrid.gdb`, `buildings_three_way.slpk` and its validation report.

Tables come from [report_city.py](report_city.py) (give it a run folder; Pro Python, for the AUCs) and [report_fill.py](report_fill.py).

```
python reviews/2026-10-23/lod2-check/lod2_check.py rasterize H:\lidar\2023-salt-lake-valley\runs\lod2-check-20261023
python reviews/2026-10-23/lod2-check/lod2_check.py measure H:\lidar\2023-salt-lake-valley\runs\lod2-check-20261023
python reviews/2026-10-23/lod2-check/lod2_check.py figures H:\lidar\2023-salt-lake-valley\runs\lod2-check-20261023 3549 17042

python reviews/2026-10-23/lod2-check/fill_trial.py H:\lidar\2023-salt-lake-valley\runs\massing-filled-20261023 --city
python reviews/2026-10-23/lod2-check/lod2_check.py rasterize H:\lidar\2023-salt-lake-valley\runs\lod2-check-filled-20261023 --massing H:\lidar\2023-salt-lake-valley\runs\massing-filled-20261023\massing.gdb
```
(`measure` and `figures` take the same `--massing`.)


## October 24 wrap-up corrections

The local v2 package was freshly checked with ArcGIS Pro: 21,561 unique source FP_IDs, matching package ID count and sum; 20,730 roofer, 647 Esri LOD2.0 and 184 Esri LOD1.2 buildings. All 831 fallback buildings have null roof attributes. Package validation has no warnings.

The 4.95 km² roof / 1.25 km² flat totals above describe all 21,407 roofer reconstructions before fallback selection. **The retained 20,730 in the package contain 4.8554083 km² of roof, including 1.2305598 km² flat.** `build_v2_package.py` now records the selected subset separately from the all-roofer summary. The existing SLPK geometry and values are unchanged.

The v2 launcher formerly used v1 bookmark captions; seven of those p95 errors had changed. `viewer/web/bookmarks-v2.json` is generated from the v2 scoring and selection, and `start_viewer_v2.bat` explicitly selects it. The v1 launcher retains its original bookmarks.

Release checks, current online status and remaining decisions: [October 24 wrap-up](../WRAPUP-2026-10-25.md). The draft field dictionary lists all 45 actual packaged fields, excludes the absent LOD20_GROUND_PCT field, and describes roof shapes as modelled rather than verified real shapes.
