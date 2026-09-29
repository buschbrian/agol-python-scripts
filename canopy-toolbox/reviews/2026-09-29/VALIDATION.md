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

Analytic stratified intervals are now the main bounds. For each total, variance
is the sum of `N_h² (1 - n_h/N_h) s_h² / n_h`. Ratios and combined statistics
use Taylor linearization of their joint totals, preserving covariance between
outcomes on the same sampled unit. Independent sample designs add variances.
A Satterthwaite t critical value uses the stratum variance contributions. Output
includes variance, standard error and degrees of freedom. The original seeded
percentile bootstrap appears under `bootstrap` as a cross-check; its with-replacement
resampling does not include the analytic finite-population correction.

The formulas follow [Penn State's stratified sampling notes](https://online.stat.psu.edu/stat506/Lesson06);
Taylor linearization is described in [CDC's variance estimation guidance](https://wwwn.cdc.gov/nchs/nhanes/tutorials/varianceestimation.aspx).
These are approximate intervals, not guaranteed small-sample coverage. Ratio
intervals can extend beyond natural bounds; do not interpret those limits as
possible probabilities. Homogeneous non-census strata, singleton respondents and
degenerate linearization do not produce a falsely precise headline interval.
A fully labelled census has exact bounds. Missing strata are excluded from the
covered-strata estimand and explicitly reported. Neither method repairs selective
UNSURE/nonresponse, imagery misregistration, systematic label error or date mismatch.

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
