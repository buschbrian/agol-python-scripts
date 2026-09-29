# Validation harness and evaluation corrections

The corrected harness is available in the main checkout through
`python reviews/2026-09-29/validation_harness.py`. The existing validation worktree
also contains the corrections. The sample is fixed to the baseline; scoring reads
its geodatabase without changing reference labels or source LAS files.

From `canopy-toolbox`, in ArcGIS Pro Python:

```powershell
python reviews/2026-09-29/validation_harness.py score
python -m unittest tests.test_evaluation_safeguards tests.test_validation_metrics tests.test_validation_arcpy -v
```

Global `--root` and `--out` arguments precede `score`. `--out` is the existing
validation directory containing `reference.gdb`; reports are written in a new
timestamped `scores` subdirectory. Do not invoke `sample` to refresh a labelled
reference: choose a separate directory when a new sampling frame is required.

Treetops are matched across the entire baseline and variant candidate frames
before sampled locations receive answers. Each candidate can participate in one
pair. Maximum cardinality takes precedence over minimum total distance, within
the inclusive 1.5-m radius. Stable IDs take precedence only for the same run,
including flag-removal experiments. Cross-run matches use coordinates. New
candidates are the unmatched variant candidates, and their tree share is unknown;
the comparison table includes sensitivity estimates treating them all as false or
all as true. This is spatial correspondence, not proof of biological tree identity.
Spatial ambiguity counts describe candidates with multiple neighbors before
identity prioritization. Dense assignment components fail rather than allocate
unbounded matrices.

Bootstrap intervals are suppressed when a non-census stratum has identical
observed outcome vectors, or when the empirical interval degenerates. The point
estimate remains available, with `interval_status` and null bounds, and the table
marks the interval unavailable. Per-stratum Wilson intervals remain available.
A fully labelled census can have an exact zero-width interval. These intervals
assume usable labels are a random subsample in each stratum; selective skipping,
UNSURE responses, imagery misregistration and label error are not corrected by
resampling. Missing strata and population coverage are reported explicitly.

Crown labels transfer only at IoU >= 0.8. Quality shares describe unchanged,
matched baseline crowns. Changed crowns require fresh labels and are counted
separately. Each labelled respondent keeps its original N/n weight; a changed
crown contributes zero to the transferable-label denominator rather than having
its weight reassigned to unchanged crowns in its stratum. These shares do not
describe every crown in the variant.

Scoring rejects mismatched CRS, shifted grids, nonsquare cells, missing completed
outputs, moved reference treetops, inconsistent cell areas, impossible candidate
counts, invalid populations and unknown labels. Existing nonempty score folders
are refused. New samples record baseline manifest SHA-256 fingerprints; scoring
checks those manifests and records the scored manifests. The current pilot's
older sample has no such fingerprints and is marked
`LEGACY_SAMPLE_WITHOUT_MANIFEST_FINGERPRINTS`. A manifest fingerprint does not
prove that someone has not edited a dataset in place without updating its manifest.

The current pilot has 1,468 sampled units and zero reference labels. Its corrected
score therefore reports `NO_LABELS`, with no accuracy claim. County, OSM and
Microsoft footprints, retained vegetation classes, and pretrained-model agreement
are contextual evidence; they are not independent tree/roof reference labels.

## Reference-label exchange

The next slice adds `export-labels` and `import-labels`. The fixed sample is not
redrawn. Exported worksheets preserve REVIEW_ORDER and hide strata, coordinates,
roof/canopy metrics, and model predictions. Use SAMPLE_ID to find the feature in
the existing ArcGIS review layers. See [the label workflow](REFERENCE_LABELS.md)
for the ready-to-review first batch and exact commands.

Imports preview by default. Applying requires `--apply` and a fresh audit directory.
The full worksheet is checked against the exported reference frame, sample IDs,
geometry, review order, label domains and field lengths before an edit session
begins. Reviewer and ISO review date are required for nonblank labels. Blank labels
do not clear existing answers, and identical answers preserve prior reviewer
metadata. Conflicting existing answers require `--replace-existing`.

All updates affect review fields only and share one ArcGIS edit transaction.
Each application archives the submitted CSV plus before/after values and status.
A runtime failure rolls the edits back. Scoring remains a separate command after
labels are applied, so the evaluator cannot manufacture reference answers.
