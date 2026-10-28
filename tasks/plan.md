# LiDAR review implementation

Implement the September 29 pasted review in dependency order. Preserve source LAS,
independent reference answers, historical run folders and existing worktree edits.
Use separate commits for the verified evaluation work and each integration slice.
Do not substitute footprints, rule labels or model predictions for truth.

1. Commit the already verified evaluation, reference-label and LAS-comparison work.
2. Integrate the footprint/building slice and document height field coverage.
3. Reproduce and fix roof-face extrapolation at the eave using a synthetic gable.
4. Consolidate binary LAS decoding in an ArcPy-free module; align physical roof
   context definitions without losing sampling-stratum distinctions.
5. Port only the September 23 class-0 observation policy, stale-statistics guard,
   building-method option and dated Nearmap helper. Retain today's sampling and QA.
6. Add a fixed plot-census frame, independent tree locations, one-to-one object
   scoring, omission causes, blinded cross-section review and alignment checks.
7. Add finite-population analytic stratified intervals as the primary interval;
   retain bootstrap results as a cross-check and report unsupported intervals.
8. Reserve spatial evaluation blocks before tuning; isolate external 12TVL2203
   results from Millcreek summaries and rule-derived training labels from scoring.
9. Prepare read-only/model experiment instructions for density, height normalization
   and pipeline variant scoring, with separate provenance for each experiment.
10. Implement the planned independent NAIP greenness review screen last.

The user explicitly chose to keep Pro's current environment and defer inference.
No proswap, environment package installation or actual inference is authorized
in this run. Independent manual labels/censuses must remain blank until reviewed.

Verification: pure unittest checks for sampling, matching, decoding and statistics;
actual ArcGIS synthetic fixtures for GP changes; read-only pilot evidence and new
scratch outputs for representative workflows; full repository unittest suite at
integration checkpoints. Source hashes and immutable original paths remain guarded.
