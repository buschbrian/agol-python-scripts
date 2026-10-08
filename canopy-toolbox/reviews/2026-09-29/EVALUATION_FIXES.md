# Evaluation and pilot safeguards — September 29, 2026

This slice corrects evaluation, report provenance and failure recovery. Roof
classification thresholds, original LAS files, reference labels, and Pro's active
Python environment were not changed. Changes remain uncommitted for review.

| Defect | Correction |
|---|---|
| One variant candidate retained multiple baseline candidates | Shared one-to-one matcher, used by validation and the local-roof candidate report. |
| Uniform small samples claimed exact confidence | Suppressed unsupported bootstrap intervals, explicit status, Wilson diagnostics and census handling. |
| Selectively changed crowns distorted stratum weights | Original respondent weights retained; reports identify the conditional crown scope. |
| Flag removal changed the baseline frame | Full baseline reloaded before scoring the filtered view. |
| Missing outputs or incompatible grids could enter evaluation | Dataset existence, grid/CRS, reference identity, count, population and label checks. |
| Untouched LAS copies appeared as model output | Successful inference manifests and content fingerprints required; boundaries and binary output semantics checked. |
| An existing LAS dataset might reference different input files | Inference reconstructs the dataset from the verified dedicated copy before classification. |
| Existing folders hid failed pilot steps | Complete preparation required; runs delegate reuse to signature-checked `--resume`. |
| Baseline driver searched its repository folder for external inventory | Explicit pilot root, configurable inventory/LAS/Python paths and import-safe main function. |
| Residential candidate report used the earlier plane refinement | Report regenerated against the local run; method/source provenance and manifest hashes recorded. |

The main checkout now contains the corrected validation modules, harness and
regressions copied from today's validation worktree. The matching/validation
corrections are mirrored there. The local-roof worktree retains its experimental
classifier and receives its corrected driver, candidate report and comparison
helpers. Its classifier has not been merged into the main CLI. The shared pipeline
preparation guard is mirrored across the existing experiment worktrees.

At the candidate-report radius of 1 m:

| Tile | Baseline | Local variant | Unmatched baseline | New variant |
|---|---:|---:|---:|---:|
| 12TVL2804 | 17,389 | 16,179 | 1,559 | 349 |
| 12TVL3302 | 44,285 | 43,813 | 733 | 261 |
| 12TVL2203 | 11,610 | 11,290 | 366 | 46 |
| Total | 73,284 | 71,282 | 2,658 | 656 |

These counts reconcile: baseline - unmatched + new = variant. Candidate-report
roof bands use the baseline class-6/ground points throughout. Removed counts now
include the no-ground category. The validation harness uses a different 1.5-m
radius, yielding 436 new variant candidates and 2,438 unmatched baseline candidates.
The net reduction is 2,002 either way; neither correspondence radius establishes
how many removed candidates were false roofs or true trees.

Corrected reports are in this task's artifact directory:

- `roof-local-candidates-corrected.json`: three tiles, corrected residential path,
  one-to-one counts and manifest SHA-256 fingerprints.
- `evaluation-corrected/score.json` and `comparison.md`: three baseline/local
  comparisons; `NO_LABELS` for all 1,468 sampled units.
- `dl-provenance-check.json`: current building/tree copies rejected because no
  successful inference manifests exist; no model headline produced.

Historical reports on H: were retained. Use the corrected artifacts for this
review. Their presence does not mean deep-learning inference was executed.

Verification used ArcGIS Pro Python. The repository suite ran 116 tests with 115
passing and one expected skip. The added evaluation modules ran 41 distinct tests
across the initial ArcGIS/pure run and subsequent pure additions, all passing. A
new actual ArcGIS incomplete-preparation case passed. Final driver/safeguard tests
also passed after the last edits. This covers 158 distinct tests: 157 passed and
one expected skip, run as the suite plus focused checks. Actual pilot scoring and
candidate-report generation succeeded without changing labels or LAS files.

Inference failure/setup, stale-dataset reconstruction, boundary enforcement,
fingerprint mismatch and input-copy rejection are regression-tested with
synthetic files and a mocked tool. Real pretrained inference remains unverified
because the configured active environment has not been changed. The existing
`DEEP_LEARNING.md` records the environment blocker and the prerequisites.

Code changes intentionally invalidate the pipeline's implementation signature.
If an existing run's code/input/parameter signature differs, use a fresh run
folder; do not remove the signature check or relabel the old run as current.
Failed preparations cannot be resumed in place: preserve them and choose a new
output folder. Partial preparations cannot be passed to the runner even when
the caller explicitly supplies source files.

Follow-up from the reference-label slice: a complete suite run found that the new
incomplete-preparation test left its failed manifest in the shared fixture root,
causing a later tiled-run test to fail. The fixture is now isolated in its own
directory; the production guard is unchanged. Both tests passed together, then
the complete expanded suite passed: 177 tests in 524.788 seconds, 176 passing and
one expected skip. See `REFERENCE_LABELS.md` for the validated label workflow.

The next LAS-comparison slice closes a separate inference-evidence gap: matching
XYZ and valid file fingerprints alone did not protect intensity, return/flag
bytes, other point attributes or classifications outside the processed area.
The comparator now checks the complete point records, protects legacy packed
flags and excluded noise, and validates binary output over the full inference
boundary. Processing and reporting extents are recorded separately. Synthetic
complete-command tests reproduced acceptance of changed intensity, point format
and boundary-external classifications before the fix; those outputs now fail
without disagreement counts. `DEEP_LEARNING.md` documents the contract and the
read-only checks of both real untouched copies. Successful inference remains
unverified; no environment switch or real classification was performed.
