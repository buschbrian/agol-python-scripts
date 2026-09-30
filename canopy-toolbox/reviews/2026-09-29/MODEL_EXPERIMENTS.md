# Density and height experiments

**Decision reversed on September 29, 2026.** The earlier decision (keep the
environment, defer inference) was replaced when the user authorized inference.
Pro's per-user active environment is now the deep-learning clone; see
[DEEP_LEARNING.md](DEEP_LEARNING.md) for the switch and the runtime isolation.
The four rows below ran on 12TVL2804 the same evening. Their numbers are model
outputs and disagreement counts, **not accuracy**: there are no independent
labels in these tables, and the baseline classes are not truth.

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
paths, so it is not a reusable script. Runtime depends on blocks more than on points. The thinned row had 11%
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
  **not tested**. Testing it would need a new row whose baseline has Z rewritten to height above ground. That
  is a different baseline with changed protected bytes, and it was not done. Incidentally, the identical outputs
  show the building inference was reproducible for identical input on this machine.

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
```

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

The September 23 G: run (~15 returns/m²) and current USGS input (~27 returns/m²)
are different source/processing realizations. Compare the paired variants on
one source first. Leaf-off, photo-date mismatch and source omissions remain
separate diagnostic limitations. Preserve 12TVL2203 as external transfer and
exclude 12TVL3302 plus its halo from all future fine-tuning.
