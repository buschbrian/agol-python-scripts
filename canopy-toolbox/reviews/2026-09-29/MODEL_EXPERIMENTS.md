# Deferred density and height experiments

Decision: keep the current ArcGIS Pro environment; **inference is deferred**.
The runner now accepts independent source/copy/output-root inputs and optional
`--reference-height`, so future paired experiments need no edits to hard-coded
paths. Tests use synthetic files and mocked inference. No model result is claimed.

## Fixed experiment matrix

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

After future inference is authorized, with a **fresh exact copy** under ROOT/JOB:

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
Product assembly and inference remain deferred; their future outputs need actual
runtime verification before use.

The September 23 G: run (~15 returns/m²) and current USGS input (~27 returns/m²)
are different source/processing realizations. Compare the paired variants on
one source first. Leaf-off, photo-date mismatch and source omissions remain
separate diagnostic limitations. Preserve 12TVL2203 as external transfer and
exclude 12TVL3302 plus its halo from all future fine-tuning.
