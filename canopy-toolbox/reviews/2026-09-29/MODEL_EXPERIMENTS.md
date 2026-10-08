# Density and height experiments

**Decision reversed on September 29, 2026.** The earlier decision (keep the
environment, defer inference) was replaced when the user authorized inference.
Pro's per-user active environment is now the deep-learning clone; see
[DEEP_LEARNING.md](DEEP_LEARNING.md) for the switch and the runtime isolation.
The four rows below ran on 12TVL2804 the same evening. Their numbers are model
outputs and disagreement counts, **not accuracy**: there are no independent
labels in these tables, and the baseline classes are not truth. Overnight into
September 30, a second queue inferred the 12TVL2804 halos, 12TVL3302 (prospective
holdout) and 12TVL2203 (external transfer), plus a height-above-ground Z row. It then
produced full-tile product runs under three conflict policies that the harness can
grid-match ([September 30 queue](#september-30-queue-halos-holdout-transfer-overnight-2026-092930),
[product runs](#september-30-conflict-policies-and-full-tile-product-runs-12tvl2804)).

## Results on 12TVL2804 (September 29, 2026)

Common settings: boundary = tile core `428000 4504000 429000 4505000` (inclusive
rectangle, EPSG:6341), batch 1, EDIT_ALL, noise 7/18 excluded, output classes
0/target. Each row used a fresh exact copy in its own root under
`H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29\deep-learning\experiments-20260929\<row>\`
(`<row>\<job>\` holds the classified copy, `<row>\work\` the manifest, logs and
comparison). The full-density baseline MD5 was `82787095336690d2909344206f9a80fc`
before and after every run. The earlier copies under `deep-learning\12TVL2804\`
were not touched. Model hashes: tree `.dlpk` and building `.dlpk` as recorded in
each `run-<job>.json`, identical across rows of the same model.

GPU memory is whole-device `nvidia-smi` usage sampled once a second, including
ArcGIS Pro, which the user had open; the "before" column is the first sample.

| Row | Model | Row baseline | Status | Tool time | dl_run elapsed | GPU MiB before / peak | Integrity | Output SHA-256 |
|---|---|---|---|---|---|---|---|---|
| tree-full | Tree PointCNN | full density, 26,982,464 points | complete | 1 h 29 min 51 s | 5,402.3 s | 1,970 / 4,187 | verified | `f165dba25fb418f3…` |
| tree-thin3 | Tree PointCNN | new thinned copy, 3,003,367 points | complete | 44 min 54 s | 2,701.8 s | 2,520 / 3,592 | verified | `aae4fc0fa8fc34d0…` |
| building-abs | Building RandLANet | full density, absolute Z | complete | 19 min 52 s | 1,213.7 s | 2,577 / 3,051 | verified | `08cd9070ca0ecaa0…` |
| building-hag | Building RandLANet | as building-abs + `--reference-height` | complete | 17 min 13 s | 1,047.5 s | 1,415 / 2,086 | verified | `08cd9070ca0ecaa0…` (identical to building-abs) |

Full hashes, package provenance and tool messages are in
[dl-experiments-20260929/](dl-experiments-20260929/) (`run-<row>.json`, `compare-<row>.json`, `row-<row>.log`).
[`run_row.ps1`](dl-experiments-20260929/run_row.ps1) is a record of what ran: it hard-codes this worktree's
paths, so it is not a reusable script. The generalized runner is
[dl-experiments-20260930/run_row.ps1](dl-experiments-20260930/run_row.ps1). Runtime depends on blocks more than on points. The thinned row had 11%
of the points and took half as long as tree-full. The full tree row took 90 min, beyond the 30–60 min estimate.

"Integrity" means `dl_compare.py` verified, over every record, that all
non-classification bytes match the row's own baseline, noise 7/18 is unchanged,
nothing outside the boundary changed, and every processed non-noise point is 0 or
the target class. Only then are the counts below reported.

### Disagreement with baseline classes, inside the boundary

Share of each baseline class the model labelled as its target class. The
thinned row is compared with its own thinned baseline, so its counts are about
one ninth of the full-density counts; compare shares, not counts.

| Baseline class | tree-full: called tree (5) | tree-thin3: called tree (5) | building-abs: called building (6) | building-hag: called building (6) |
|---|---|---|---|---|
| 1 unclassified | 0.008% (35 of 455,565) | 0.012% (6 of 50,976) | 0.039% (176) | identical to building-abs |
| 2 ground | 0.015% (402 of 2,658,030) | 0.021% (61 of 295,255) | 0.058% (1,541) | identical |
| 3 low veg | 0.008% (728 of 9,589,034) | 0.008% (89 of 1,068,229) | 0.021% (2,033) | identical |
| 4 medium veg | 4.58% (48,784 of 1,065,061) | 5.57% (6,596 of 118,333) | 0.97% (10,318) | identical |
| 5 high veg | 98.83% (8,715,316 of 8,818,572) | 98.90% (970,275 of 981,025) | 1.48% (130,226) | identical |
| 6 building | 11.48% (496,598 of 4,325,602) | 17.58% (84,656 of 481,571) | 82.64% (3,574,487) | identical |
| 7 / 18 noise | 0 (excluded) | 0 (excluded) | 0 (excluded) | identical |

All other processed non-noise points were set to 0. Headline disagreement: the tree model calls 103,256
baseline class-5 points background and 496,598 baseline class-6 points tree (full density). The building model
calls 751,115 baseline class-6 points background and 142,577 baseline class-3/4/5 points building.

These are counts of agreement and disagreement between two classifiers. Neither
the baseline pipeline nor the pretrained models were checked against independent
labels here, so no row shows which is right.

### Thinned baseline (tree-thin3)

- Tool: [dl_thin.py](dl_thin.py); record `tree-thin3\baseline\12TVL2804-thin3.thinning.json`.
- Method: whole-pulse Bernoulli selection. Pulse key = (GPS time, point source ID,
  scanner channel). Each pulse was kept with p = 3 × 1,000,000 / 26,982,464 =
  0.111183, using `numpy.random.default_rng(20260929)` over pulses in sorted key order.
- Point-versus-pulse policy: pulses kept or dropped whole, so Number of Returns
  and return numbers are unchanged and consistent with the retained records.
  Source structure check: 24,430,510 pulses; none had inconsistent Number of Returns,
  duplicate return numbers or more records than Number of Returns; 16,032,305
  (65.6%) were complete (the rest are missing returns in the source, for example
  edge-clipped, and were not repaired). Thinned: 2,718,840 pulses kept, all with the
  same properties (1,784,369 complete).
- Retained attributes: every byte of each retained record, in original order
  (verified by byte comparison). Header changes: 1.4 point count, points by return,
  XYZ bounds. VLRs copied.
- Result: 3,003,367 points, 90,102,506 bytes, SHA-256
  `2992199b48822d7c5e4fbcaf8a70ba2e084ca545a7784f9708e7b6c32c35febc`.
- Density in the 400 tile-aligned 50 m blocks (points/m², all points):

  | | min | p05 | p25 | median | mean | p75 | p95 | max |
  |---|---|---|---|---|---|---|---|---|
  | full baseline | 11.01 | 12.04 | 13.98 | 16.87 | 26.98 | 40.08 | 57.01 | 88.42 |
  | thinned | 1.23 | 1.34 | 1.56 | 1.87 | 3.00 | 4.42 | 6.38 | 9.87 |

  Non-noise density is within 0.1 points/m² of these values. The source density is
  strongly banded by flight-line overlap, so "about 3 points/m²" holds for the mean;
  half the blocks are under 1.9.

### Reference height (building-hag)

- Tool: [dl_reference_height.py](dl_reference_height.py); record
  `building-hag\reference\reference-height.json`.
- No single pipeline DTM covers the tile: `12TVL2804\run\` has 25 per-tile
  `dtm.tif` files (230 m each) and no mosaic, so a new raster was derived.
- Inputs: the baseline tile plus its seven neighbouring 50 m halo files from the
  same `prepared\points` folder, **copied** into `building-hag\reference\points\`
  (SHA-256 of every copy matched its source). Class-2 ground only, withheld,
  overlap and synthetic points excluded, with the pipeline's
  `TRIANGULATION NATURAL_NEIGHBOR WINDOW_SIZE MINIMUM 1`, 0.5 m cells.
- Raster: `building-hag\reference\ground.tif`, extent 427950–429050 E,
  4503950–4505050 N, EPSG:6341 metres, NAVD88 height (Geoid18) metres, ground
  1318.83–1371.70 m. No NoData inside the boundary; complete coverage extends
  24.5 m beyond it on every side (5,235 NoData cells lie in the outer rim only).
  Statistics were calculated before fingerprinting and the file was set read-only.
- SHA-256 `808b0591ff7e46b5a4b77981f90052f57005fe7689078b2911b88da2c14a6654`,
  unchanged after the run (rechecked by `dl_run.py`, `dl_compare.py` and the row runner).
- **Result: a null control.** The building-hag output is byte-identical to building-abs, so the reference raster
  changed no prediction. The building EMD's `features_to_keep` is `xyz` only and records no relative-height
  attribute. Our inference from that and the identical output is that this model does not use relative height
  through this tool, and the raster acted only as a coverage mask. Coverage was complete, so no point was
  omitted. This is an inference, not documented tool behaviour. The absolute-versus-HAG question was therefore
  **not tested** by this row. Testing it would need a new row whose baseline has Z rewritten to height above ground. That
  is a different baseline with changed protected bytes. It was done on September 30 as row d (below): HAG Z changes
  building predictions for 108,210 points. Incidentally, the identical outputs here show the building inference
  was reproducible for identical input on this machine.

## September 30 queue: halos, holdout, transfer (overnight 2026-09-29/30)

Authorized by the user to run more tiles on this machine. Root:
`H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29\deep-learning\experiments-20260930\`, one folder per
row (`<row>\<job>\` holds the classified copies and `<job>.lasd`; `<row>\work\` holds the row manifest, one
schema-1 manifest per file, `row.json` with MD5s, logs and the comparison). Settings as on September 29:
EDIT_ALL, noise 7/18 excluded, output classes 0/target, batch 1, clone python with `PYTHONNOUSERSITE=1`. The
difference is that each row is **one LAS dataset over several files with no boundary**, so every non-noise
point of every file was classified. Runner:
[run_queue.ps1](dl-experiments-20260930/run_queue.ps1) → [run_row.ps1](dl-experiments-20260930/run_row.ps1)
(generalized from the September 29 record; toolbox path is the main checkout). One GPU job at a time.

Every source file's MD5 was recorded before copying. Each copy matched it, and every source was unchanged
after its row. The 12TVL2804 core baseline (`82787095…`) was also re-hashed around every row and did not
change. Per-file MD5s are in each `work\row.json`. The core-file MD5s are 12TVL3302 `36ac0563d3dd7e39d3f1b2abcac7d4f3` and
12TVL2203 `3056d908f5284daab3ba776f3e599874`. Every row passed the binary integrity gate **file by file**
(`dl_compare.py --row-manifest`): all non-classification bytes matched each file's own baseline, noise was
unchanged, and every non-noise point was 0 or the target.

GPU MiB below is whole-device `nvidia-smi` usage sampled once a second (about 1.4 GB of that is the desktop
before inference), not model memory alone.

**Halo class 0 check (before row a):** a full scan of every prepared file for the three tiles found **no class-0
point in any file**, core or halo. Classes present in the 12TVL2804 halos: 1, 2, 3, 4, 5, 6, 7, 18. The baseline
run's "Unclassified points are excluded" warning comes from class 1. 12TVL2203 and its halos also hold 9
(water), 17 (bridge deck) and 20. EDIT_ALL reassigned those to 0 or the target like every other non-noise class.

| Row | Label | Files / points | Tool time | GPU MiB first / peak | Integrity |
|---|---|---|---|---|---|
| a. 12TVL2804-halo-tree | halo files only (core inferred Sept 29) | 7 / 5,570,591 | 11 min 13 s | 1,475 / 2,363 | verified, all 7 |
| a. 12TVL2804-halo-building | same | 7 / 5,570,591 | 4 min 36 s | 1,450 / 1,913 | verified, all 7 |
| b. 12TVL3302-…-tree | prospective holdout -- inference only, never training | 8 / 40,330,316 | 1 h 8 min 19 s | 1,384 / 2,629 | verified, all 8 |
| b. 12TVL3302-…-building | same | 8 / 40,330,316 | 26 min 15 s | 1,630 / 2,139 | verified, all 8 |
| c. 12TVL2203-external-transfer-tree | external transfer -- outside Millcreek estimate | 4 / 22,291,107 | 30 min 19 s | 1,722 / 2,590 | verified, all 4 |
| c. 12TVL2203-external-transfer-building | same | 4 / 22,291,107 | 13 min 30 s | 1,491 / 1,930 | verified, all 4 |

The 12TVL3302 folders, manifests (`data_use_label`) and `LABEL.txt` say "prospective holdout -- inference only,
never training". The 12TVL2203 ones say "external transfer -- outside Millcreek estimate". When the queue
started (21:33), no ArcGIS Pro process was running; later on it was not checked. Tree inference ran faster per
point than the September 29 tree-full row (90 min for 27 M points, with Pro open). The cause was not tested.

### Disagreement with baseline classes (all files of each row)

Share of each baseline class labelled as the model's target. Per-file tables are in
`<row>\work\compare-<row>.json` (copied to [dl-experiments-20260930/](dl-experiments-20260930/)).

| Baseline class | 2804 halos tree | 2804 halos building | 3302 tree | 3302 building | 2203 tree | 2203 building |
|---|---|---|---|---|---|---|
| 1 unclassified | 0.40% (249) | 0.003% (2) | 0.099% (528) | 0.040% (216) | 0.061% (318) | 0.0004% (2) |
| 2 ground | 0.033% (201) | 0.0002% (1) | 0.071% (2,081) | 0.085% (2,492) | 0.001% (21) | 0 |
| 3 low veg | 0.006% (110) | 0.0003% (5) | 0.017% (1,864) | 0.011% (1,189) | 0.001% (86) | 0.00003% (3) |
| 4 medium veg | 2.89% (6,054) | 0.76% (1,597) | 3.85% (194,522) | 0.076% (3,839) | 3.14% (33,851) | 0.072% (772) |
| 5 high veg | 98.93% (1,867,805 of 1,888,060) | 1.46% (27,576) | 97.19% (17,595,547 of 18,105,266) | 0.34% (61,700) | 97.15% (4,503,438 of 4,635,738) | 0.46% (21,466) |
| 6 building | 10.94% (94,672 of 865,044) | 78.69% (680,701) | 10.75% (296,162 of 2,754,231) | 81.01% (2,231,054) | 8.66% (109,911 of 1,269,117) | 70.41% (893,622) |
| 9 water | – | – | – | – | 0 of 52,066 | 0 |
| 17 bridge deck | – | – | – | – | 41.4% (224 of 541) | 0 |
| 20 | – | – | – | – | 0 of 3,157 | 0 |
| 7 / 18 noise | excluded | excluded | excluded | excluded | excluded | excluded |

The pattern repeats on all three tiles. The tree model calls 97–99% of baseline 5 tree and 9–11% of baseline 6
tree. The building model calls 70–81% of baseline 6 building and under 1.5% of baseline 5 building. The two
12TVL3302 halo files with no baseline building (3201, 3301) got no building prediction. **These are disagreement
counts between two classifiers, not accuracy.** 12TVL3302 results are exploratory use of a prospective holdout;
it must stay out of any training. 12TVL2203 is external transfer and never part of a Millcreek estimate.

### Row d: height-above-ground Z (tree-hag-z, building-hag-z)

Input: the z-mode HAG copy of the 12TVL2804 core written by another agent's `python -m canopy hag`
(`hag-20260929\12TVL2804\manifest.json`, status complete, `EXPERIMENTAL_UNVALIDATED`). File
`points\12TVL2804.las`, MD5 `ee8ad65ec93942740b823f3097c8d288`, unchanged after both rows. Four halo files
were refused by the HAG writer because they have uncovered points, so row d is **core only**. That is
the same scope as the September 29 tree-full/building-abs rows, whose core boundary contained the whole core
file. Each row treated the HAG LAS as its own baseline and was compared by index with it only.

- **Non-Z bytes equal the absolute baseline (verified)** by [dl_hag_check.py](dl_hag_check.py) over all
  26,982,464 records: every record byte except Z, every header/VLR byte except the Z offset and max/min Z
  fields, and all trailing bytes are identical. Z differs in every record. Header Z: absolute
  1232.64–1471.07 m, HAG −128.05–119.34 m. The extremes are noise: all 317 points below −10 m are class 7 and
  the maximum is class 18, and both classes are excluded from inference. 8,778 points lie below −1 m (3,558
  class 1, 4,024 class 6, 1,024 class 7, 133 class 2, 39 class 3).
- The first attempt failed: tree-hag-z **failed after 31 min 10 s of tool time** with
  `ERROR 999999 … Failed to open file for editing - the file may be read only or write protected.` The HAG
  writer marks its output read-only and `Copy-Item` kept that attribute on the copy. The queued
  building-hag-z attempt was stopped by the operator a few minutes in. Both folders are kept as
  `*-attempt1-readonly` with a note and are not evidence. Fixes: the runner now clears the attribute on each
  fresh copy (not content, so the MD5 is unaffected), and `dl_run.py` refuses a read-only copy before any record
  or tool call.
- Rerun results:

| Row | Tool time | GPU MiB first / peak | Integrity | Called target (vs. September 29 absolute-Z row) |
|---|---|---|---|---|
| tree-hag-z | 32 min 10 s | 1,528 / 2,470 | verified | baseline 5: 99.05% (tree-full 98.83%); baseline 6: 11.43% (11.48%); baseline 4: 2.54% (4.58%) |
| building-hag-z | 16 min 36 s | 1,507 / 1,987 | verified | baseline 6: 83.40% (building-abs 82.64%); baseline 5: 1.50% (1.48%); baseline 4: 0.95% (0.97%) |

- **Paired by point index with the absolute-Z outputs** (valid because non-Z bytes and order are identical):

| Model | Target in both | Absolute-Z only | HAG-Z only | Points changed |
|---|---|---|---|---|
| tree (5) | 9,125,277 | 136,586 | 130,487 | 267,073 (0.99% of the tile) |
| building (6) | 3,680,379 | 38,402 | 69,808 | 108,210 (0.40%) |

  **HAG input changes predictions.** For the building model the change is attributable to Z: on September 29
  two identical absolute-Z inputs gave byte-identical building outputs. For the tree model, run-to-run
  reproducibility had not been measured when this row ran. The later [step b repeat](#step-b-tree-reproducibility)
  shows that most of the 267,073 tree changes appear with no change to the input, so they cannot be attributed to
  Z. As everywhere else, neither version is shown
  to be more accurate. The paired record is `hag-z-check\hag-vs-absolute-paired.json`.

### Step b: tree reproducibility

The September 30 handoff asked for a repeat of the absolute-Z tree row, because row d's 267,073 changed tree
points could not be attributed to Z without it. Two repeats ran on the A4000 office workstation (i9-13900K,
RTX A4000 16 GB, driver 616.92, Pro 3.7 deep-learning clone, PyTorch 2.9.1 CUDA 12.9), each alone on the GPU at
batch 1: `tree-abs-repeat` (1,310.5 s of tool time) and `tree-abs-repeat2` (1,354.7 s). Both used the same file
as the September 29 `tree-full` row (the absolute 12TVL2804 core, MD5 `82787095…80FC`), the same boundary
(`428000 4504000 429000 4505000`) and the same tree model. Both passed integrity and left the baseline and watch
file hashes unchanged. Queue and comparer: [queue_tree_repeat.ps1](../2026-09-30/queue_tree_repeat.ps1),
[repeat_compare.py](../2026-09-30/repeat_compare.py). The pairing uses the same `paired_predictions` as the HAG-Z
pairing and reproduced that pairing's published counts exactly when checked on the `tree-full` and `tree-hag-z`
outputs. Every pairing is by point index over all 26,982,464 points (valid because the non-Z bytes and order are
identical), target class 5.

| Runs compared | Machines | Tree in both | First only | Second only | Points changed |
|---|---|---:|---:|---:|---:|
| `tree-full` vs `tree-abs-repeat` | laptop / workstation | 9,143,073 | 118,790 | 119,063 | **237,853** (0.88%) |
| `tree-full` vs `tree-abs-repeat2` | laptop / workstation | 9,142,347 | 119,516 | 118,038 | **237,554** (0.88%) |
| `tree-abs-repeat` vs `tree-abs-repeat2` | workstation / workstation | 9,142,706 | 119,430 | 117,679 | **237,109** (0.88%) |
| `tree-hag-z` vs `tree-full` | laptop / laptop | 9,125,277 | 136,586 | 130,487 | 267,073 (0.99%) |
| `tree-hag-z` vs `tree-abs-repeat` | laptop / workstation | 9,125,670 | 130,094 | 136,466 | 266,560 (0.99%) |
| `tree-hag-z` vs `tree-abs-repeat2` | laptop / workstation | 9,124,543 | 131,221 | 135,842 | 267,063 (0.99%) |

(`tree-hag-z` is the first column in its last two rows, so "first only" there is the HAG-Z output.)

- **The tree model is not reproducible.** Identical input gives different output every time: no two of the three
  absolute-Z runs are byte-identical, and each pair differs by about 237,100 to 237,900 points (0.88% of the tile).
- **The noise does not depend on the machine.** The two cross-machine pairs (237,853 and 237,554) match the
  same-machine pair (237,109) to within about 0.3%. Nothing here shows any effect of the laptop's versus the workstation's
  GPU, driver or libraries on the tree output. The three noise pairs spread by only about ±0.16%.
- **Most of row d's tree difference is noise.** The three HAG-Z pairings give 266,560 to 267,073 (mean about
  266,900). The absolute-Z noise is about 237,500, so HAG-Z adds about **29,400 more changed points (0.11% of the
  tile)**, about 11% of the difference that was measured. The excess is the same in all three HAG-Z pairings. It is
  the only input difference, so a small Z effect is the natural reading, but it is small compared with the noise.
- **Direction of the excess.** In the HAG-Z pairings the absolute-Z runs call 4,600 to 6,400 more points tree than
  HAG-Z does. Between absolute-Z runs the two directions differ by only 300 to 1,800. So HAG-Z calls slightly fewer
  points tree.
- **The building model is different.** It was byte-reproducible on identical input, so its 108,210 changed points
  are a Z effect, not noise.
- Nothing here says which tree output is more accurate; no labels exist yet. With three runs this is a measurement
  of the noise level, not a significance test.

Result records: [tree-repeat/](../2026-09-30/tree-repeat/) holds five of the six pairing files; the sixth,
`tree-hag-z` vs `tree-full`, is the row-d record `hag-z-check\hag-vs-absolute-paired.json` on the lidar disk. Paths
inside the files are the workstation's `D:` paths. The outputs are on the lidar disk under
`experiments-20260930\tree-abs-repeat` and `tree-abs-repeat2`.

### Step d: batch size

The first `tree-abs-batch8` attempt failed after 57 s with an intermittent `SyntaxError` while the tool's worker
imported `sympy` during model load, before batch size could matter (GPU peak 1,801 MiB; the same import passed 4 of 4
times afterwards and the `sympy` file is identical to Pro's). It is kept as `tree-abs-batch8-attempt1-import-error`
and is not evidence. The row was rerun (`tree-abs-batch8`, batch 8, otherwise identical to the batch-1 repeats:
same file, boundary and model, alone on the GPU, same workstation). It passed integrity and left the baseline
and watch hashes unchanged.

| | Batch 1 (`tree-abs-repeat`, `-repeat2`) | Batch 8 (`tree-abs-batch8`) |
|---|---:|---:|
| Tool time | 1,310.5 s and 1,354.7 s | **698.7 s** (1.9 times faster) |
| GPU memory, first / peak | 1,487 / 2,565 and 1,300 / 2,792 MiB | 1,417 / **6,712 MiB** (of 16,376) |
| Points changed vs `tree-abs-repeat2` | 237,109 (repeat vs repeat2) | **237,506** (0.88%) |
| Tree in both / batch-1 only / batch-8 only | | 9,142,206 / 118,179 / 119,327 |

- **No batch-size effect is detectable.** The batch-8 output differs from a batch-1 run by 237,506 points, inside
  the 237,109 to 237,853 range that two batch-1 runs differ by. The direction is symmetric too: the batch-1 and
  batch-8 exclusive counts differ by 1,148, within the 300 to 1,800 seen between batch-1 runs.
- **Limits.** One batch-8 run, and only the tree model; the building model was not tried above batch 1. The
  comparison can only show that batch 8 is not distinguishable from noise, not that it is identical (nothing is).
  Batch 16 was not tried; memory peaked at 6.7 GB, so it may fit.
- **What it means for speed.** On this workstation a batch of 8 roughly halves tree inference time with no
  detectable change in the predictions. The manifests record `batch_size`, so rows stay comparable. The handoff's
  "batch 1 for every comparison row" rule is the user's to keep or relax.

Result record: [tree-repeat/batch8-vs-repeat2.json](../2026-09-30/tree-repeat/batch8-vs-repeat2.json).

## Fixed experiment matrix (original plan)

Use the same frozen boundary and independent labels for all rows. Start on
12TVL2804, outside the prospective fine-tuning holdout. Keep batch=1, model hash,
return/flag policy and class mapping fixed.

| Model | Input | Control |
|---|---|---|
| Tree PointCNN | full USGS density | no reference-height raster |
| Tree PointCNN | new approximately 3 points/m² copy | same boundary and settings |
| Building RandLANet | full-density block | absolute elevations |
| Building RandLANet | identical full-density block | same ground raster as reference_height |

The downloaded tree EMD declares 50 × 50 m blocks and 8,192 sampled points.
8,192 / 2,500 = 3.28 points/m² is the model block's nominal point budget; it is
**not proof of training acquisition density**, and inference may subdivide or
resample dense inputs. About 3 points/m² is a sensitivity target. Record the
thinning method, point-versus-pulse policy, seed, retained return attributes,
actual per-block density distribution and SHA-256 of each new baseline. Do not
compare thinned input directly with full input index-by-index: each density
experiment compares its predictions with its own exact pre-inference baseline.

The building EMD records training XYZ Z minima/maxima -168.48/232.96 m. The pilot's
absolute elevations differ. That motivates a controlled HAG test but does not
prove failed normalization; model preprocessing may use relative coordinates.
The installed tool exposes `reference_height`: points outside that raster are
omitted. Require complete valid ground coverage of the processing boundary and
context, correct metre horizontal/vertical units and unchanged raster bytes.
The runner records and rechecks its fingerprint; the comparator verifies it too.

[Esri's tree model](https://doc.arcgis.com/en/pretrained-models/latest/point-cloud/introduction-to-tree-point-classification.htm)
requires XYZ and Number of Returns and maps outputs to 0/5.
[The building model](https://doc.arcgis.com/en/pretrained-models/latest/point-cloud/introduction-to-building-point-classification.htm)
uses XYZ and maps outputs to 0/6. Published validation scores are not local pilot
accuracy. Detailed limits here come from the downloaded EMDs in `H:\lidar\models`.

Command pattern (the September 29 rows used it with PYTHONNOUSERSITE=1 and the clone's python;
dl_run refuses to start while per-user site-packages are enabled). Always use a **fresh exact copy** under ROOT/JOB:

```powershell
python reviews/2026-09-29/dl_run.py tree --source BASELINE.las --copy ROOT/tree/EXACT_COPY.las --output-root ROOT --boundary XMIN YMIN XMAX YMAX
python reviews/2026-09-29/dl_run.py building --source BASELINE.las --copy ROOT/building/EXACT_COPY.las --output-root ROOT --reference-height GROUND.tif --boundary XMIN YMIN XMAX YMAX
python reviews/2026-09-29/dl_compare.py --original BASELINE.las --manifest tree=ROOT/work/run-tree.json --out NEW_COMPARISON.json
# multi-file row (core + halos, one LAS dataset, no boundary); one --copy per --source, same order:
python reviews/2026-09-29/dl_run.py tree --source A.las --copy ROOT/tree/A.las --source B.las --copy ROOT/tree/B.las --output-root ROOT --label "TEXT"
python reviews/2026-09-29/dl_compare.py --row-manifest tree=ROOT/work/run-tree.json --out NEW_COMPARISON.json
# product per file, then a full-tile canopy run on the baseline grid:
python reviews/2026-09-29/dl_product.py --baseline B.las --tree-manifest ROOT/work/run-tree-B.json --tree-compare CMP.json --building-manifest ... --building-compare ... --policy conflict-class --out NEW.las
python reviews/2026-09-29/dl_product_tile.py --policy tree-wins building-wins conflict-class
```

`dl-experiments-20260930/run_row.ps1` does the copy/MD5/dl_run/dl_compare sequence for one row. It clears a
read-only attribute on fresh copies. `dl_run.py` refuses read-only copies before starting.

Noise 7/18 remains excluded. The raw prediction remains binary; do not overwrite
it while assembling pipeline inputs. Complete manifests and binary integrity are
necessary before any disagreement counts are reported.

## Product scoring after inference

Raw EDIT_ALL inference can replace ground with background 0, so a binary model
LAS alone is not a usable CHM ground source. Create a separate documented product
copy after binary validation: retain baseline class-2 ground/noise for the DTM,
use tree predictions as class 5, and use verified model background only within
the fully processed area. Combine building/vegetation predictions only under a
declared conflict policy; a building-only output has no vegetation prediction.
Record every restoration/merge and maintain hashes of raw outputs. Do not call
this postprocessed copy the raw model output or use it in the raw comparator.

Refresh statistics on that new copy. Run the normal bounded `canopy run` with
`--classified-background-zero` only where class 0 is entirely verified model
background; mixed unprocessed class 0 requires an isolated processed extraction.
Score its standard run.json through the fixed-reference harness and plot census.
Report candidate precision, complete-plot recall/duplicates/F1, canopy error and
cause diagnostics. Baseline/model classes and rules 64–70 never become truth.

### September 29 product run (tree-full)

- Product: [dl_product.py](dl_product.py) wrote a new file,
  `experiments-20260929\product-tree-full\12TVL2804\points\12TVL2804.las`
  (record [product-tree-full.json](dl-experiments-20260929/product-tree-full.json)).
  It starts from the verified tree-full output and is combined with the verified building-abs output.
- Declared policy, per point in order: baseline noise 7/18 kept (70,600); baseline ground 2 restored
  (2,658,030, of which 402 had been called tree and 1,541 building); tree prediction 5 → 5 (9,261,461);
  building prediction 6 → 6 only where the tree model said background (3,311,370); everything else → 0
  (11,681,003). **Conflicts resolve to tree.** 405,870 points were called target by both models and became 5.
  That keeps the tree prediction as the variable under test, but it puts model-tree points on baseline roofs
  (the tree model called 496,598 baseline-6 points tree) and reduces building occlusion accordingly.
- Raw outputs and the baseline were only read. Their SHA-256 matched before and after, and the baseline MD5 was
  unchanged. This product is not a raw model output and never enters `dl_compare.py`.
- Largest semantic difference from the baseline run: baseline classes 3 and 4 (about 10.65 million points)
  have no counterpart. They became 0 or 5, so the product's vegetation is tree-model class 5 only.
- A new LAS dataset with statistics was built on the product (`product.lasd`; audit in
  `product-lasd-audit.json`). The class list shows 0, 2, 5 and 6. The noise points carry the withheld flag and are
  not listed.
- `python -m canopy run product.lasd run --extent 428250 4504250 428500 4504500 --source-files … --classified-background-zero`
  completed in 40.3 s (4 tiles; warning "134.75 m2 of canopy has no treetop seed"). It produced 929 treetops and
  572 crowns, and run.json reports `quality_status: UNVALIDATED`. The flag is justified here because the whole tile
  was processed and every class 0 is verified model background. The 250 m extent and its halo lie inside the tile.
- Scoring: `validation_harness.py score --run dl-tree-full-product=…\product-tree-full\{tile}\run` **refused**
  with `ValueError: Run grid differs from reference baseline for 12TVL2804`. The harness requires the full-tile
  baseline run's CHM grid, so no bounded run can be scored with it as written. For the label status, a
  baseline-only score call printed: "No labels yet: 0 of 1468 reference units are labelled (treetop 0/628,
  omission 0/300, cell 0/360, crown 0/180)". No completed plot-census packet exists, so census scoring was not
  run. **No accuracy figure exists for this product.** The candidate counts above are not precision or recall.
- Options for the user: a supplementary full-tile product run on the baseline grid (minutes of CPU; its edge
  tiles would lack the neighbour halos the baseline run had), or a bounded-extent scoring mode in the harness.
  **Done on September 30 (next section): full-tile product runs on the baseline grid, with the halos inferred.**

### September 30: conflict policies and full-tile product runs (12TVL2804)

**Policies** ([dl_product.py](dl_product.py) `--policy`). They apply to points that both models claim (tree
5 and building 6). Ground and noise restoration are unchanged.

| Policy | Conflict points become | Effect in `canopy run` |
|---|---|---|
| `tree-wins` (September 29 default) | 5 | vegetation: canopy height; not occluded |
| `building-wins` | 6 | non-canopy and building occlusion (a class-6 first return > 0.35 m above the vegetation return masks that cell) |
| `conflict-class` | user-definable 64–255, default 65 | **none**: class 65 is not in `VEG_CLASSES` (3;4;5), `NON_CANOPY_CLASSES` (2;6;9;10;11;13–17;20[;0]) or the building layer (6), so these points add no canopy height, no occlusion and **no observation**. A cell whose only first/single returns are conflict points is NoData (unknown), not 0. `canopy run` emits no warning for it (it warns only for 1, or 0 without the flag); `chm.json` lists 65 among the input class codes. No `canopy/` change was needed for this. |

**Inputs:** core = the verified September 29 tree-full and building-abs outputs (core boundary, which contains
the whole core file). Halos = the verified September 30 halo rows (no boundary). So every point of all 8 files
went through model inference. `--classified-background-zero` is justified: every class 0 is verified model
background. The driver is [dl_product_tile.py](dl_product_tile.py) (default Pro python, `PYTHONNOUSERSITE=1`).
It reads the baseline `run\run.json` parameters and passes them explicitly (extent, tile 200, overlap 15,
cell 0.5, bands, smoothing 1, min crown 3, clearance 0.35, `z_unit` null). The product `run.json` differs
from the baseline only in `source_id` (not passed: it names the input points and seeds TREE_IDs; the harness
matches variant candidates by location) and `classified_background_zero: true`. All 8 prepared baseline files and
all 16 raw outputs had the same MD5 before and after. Every run's CHM grid equals the baseline grid
(2000 × 2000, 0.5 m, xmin 428000, ymax 4505000).

Point counts (all 8 files; core alone in brackets). Noise kept 77,809, ground restored 3,259,125, background 0
14,043,266 in every policy:

| Policy | class 5 | class 6 | class 65 | conflicts |
|---|---|---|---|---|
| tree-wins | 11,230,351 [9,261,461] | 3,942,504 [3,311,370] | – | 484,617 [405,870] → 5 |
| building-wins | 10,745,734 [8,855,591] | 4,427,121 [3,717,240] | – | 484,617 → 6 |
| conflict-class | 10,745,734 [8,855,591] | 3,942,504 [3,311,370] | 484,617 [405,870] | 484,617 → 65 |

The core tree-wins counts reproduce the September 29 product exactly.

| Run (full tile) | Treetops | within 15 m of tile edge | Crowns | CHM cells ≥ 2 m (m²) | NoData cells | Assemble / LASD stats / `canopy run` |
|---|---|---|---|---|---|---|
| baseline (Sept 29 pilot) | 17,389 | 1,127 | 11,661 | 1,170,839 (292,710) | 33,088 | – / – / 4.67 min (pilot timing) |
| dl tree-wins | 17,728 | 1,148 | 12,790 | 1,239,039 (309,760) | 28,331 | 16.5 s / 2.7 s / 152.7 s |
| dl building-wins | 14,488 | 979 | 11,311 | 1,160,612 (290,153) | 28,331 | 15.9 s / 2.7 s / 168.8 s |
| dl conflict-class (65) | 14,697 | 986 | 11,358 | 1,162,474 (290,619) | 50,275 | 16.8 s / 2.3 s / 154.4 s |
| dl tree-wins, **baseline halos** | 17,728 | 1,148 | 12,790 | 1,239,039 | 28,331 | 14.3 s / 2.4 s / 154.4 s |

Conflict-class leaves 21,944 more cells (5,486 m²) unknown than the other policies. Compared with tree-wins,
building-wins changes 81,048 cells by more than 0.1 m, and conflict-class changes 59,104 cells plus 21,944
NoData changes (`chm-differences.txt`). These are product differences, **not accuracy**.

**Harness** (`validation_harness.py score` with `baseline` and the four product runs as `--run` variants,
30 s): **the grid check passed for every product run.** Its verbatim headline: "No labels yet: 0 of 1468
reference units are labelled (treetop 0/628, omission 0/300, cell 0/360, crown 0/180). Label the samples in
ArcGIS Pro, then score again." Every metric cell reads "no labels yet". Its structural counts for 12TVL2804:
of the 210 sampled baseline treetop candidates, tree-wins keeps 156, building-wins 150 and conflict-class 151.
Candidates outside the sampling frame (no baseline candidate nearby) number 3,413, 1,199 and 1,301. Sampled
crowns changed: 9, 6 and 7. The baseline-halo variant is identical to tree-wins. Report
`validation\scores\20260930-015037`. **No accuracy figure exists for any product.**

### Scoring approaches compared (measured facts, 12TVL2804)

1. **Full tile, inferred halos (recommended, done).** Same grid as the baseline, so the fixed reference and the
   harness apply unchanged, and every point has model semantics. Cost: 16 min of GPU for the 7 halo files and
   about 3 min of CPU per policy.
2. **Full tile, baseline halos (measured).** The CHM is **identical cell for cell** to option 1: 0 of 4,000,000
   cells changed, in every edge band (0–15, 15–30, 30–50 m and interior). Treetop and crown counts are also
   identical. The reason is structural. `canopy run` builds each 200 m tile over its 15 m buffer but keeps only
   the core cells, and every class-dependent surface (vegetation DSM, non-canopy, building occlusion) is binned
   per cell. Halo points therefore reach the core CHM only through the class-2 ground TIN, and the product
   restores ground from the baseline in both variants. So for the *CHM product* halo inference changes nothing. It
   would matter if the ground source or the DSM interpolation changed. `--classified-background-zero` was valid here
   only because no halo file holds class 0 (checked). The halos also mix semantics: baseline 1/3/4/5/6 next to model
   0/5/6.
3. **Bounded-extent scorer (not built; would need a `canopy/validation.py` change).** `run_units` rejects any
   grid other than the baseline's (lines 584–589). A bounded mode would have to window the baseline grid and
   restrict every sample to the window. The design is stratified per tile, with populations counted over the
   whole tile, so a window is a **domain** with unknown per-stratum populations and very few units. The
   September 29 250 m extent (6.25% of the tile) holds 34 of the tile's 490 reference units: treetop 19,
   omission 6, cell 5, crown 4 (`reference-units-12TVL2804.json`). That is too few for stratified estimates, and
   the result would describe the window, not the tile. Edge effects add to this. A bounded `canopy run` recomputes
   its own 15 m halos inside the tile, and subregion-only inference cuts model blocks at the subregion boundary.
   43 of the tile's units lie within 15 m of the tile edge.

**Untested edge effect in the inference itself.** The core (September 29) was inferred in a dataset holding
only the core file, and the halos (September 30) in one holding only the halos. Blocks on both sides of the
428000/429000 E and 4504000/4505000 N seams therefore lacked cross-seam context. Option 2 shows that halo predictions do not reach the CHM.
Core predictions near the tile edge do, and a core + halo joint inference (as done for 12TVL3302 and
12TVL2203) would be needed to measure that. This was not done for 12TVL2804.

The September 23 G: run (~15 returns/m²) and current USGS input (~27 returns/m²)
are different source/processing realizations. Compare the paired variants on
one source first. Leaf-off, photo-date mismatch and source omissions remain
separate diagnostic limitations. Preserve 12TVL2203 as external transfer and
exclude 12TVL3302 plus its halo from all future fine-tuning.
