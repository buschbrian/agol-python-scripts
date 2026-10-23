# LiDAR and classification review — September 29, 2026

The local roof-surface work is a useful improvement over the original flat-roof method. The saved runs show fewer candidates and less roof-like canopy, with a recorded classification-byte integrity audit. Classification accuracy is still unknown. Evaluation and provenance defects should be corrected before using these results to select thresholds or train a model.

This was a review, not an implementation pass. Source code, LAS data, Git branches/worktrees, and the active ArcGIS Python environment were left unchanged. Tests created temporary synthetic fixtures. This report is saved outside the repository.

## Scope and state

Main checkout: `V:\Developer\agol-python-scripts`, branch `canopy/classification-refinement`, HEAD `1b0123d`. There is one commit dated September 29 across the available Git branches: the full-tile classification review, 13 files and 1,028 added lines. The main checkout also has untracked `DEEP_LEARNING.md`, `dl_run.py`, and `dl_compare.py`.

Three existing Claude worktrees contain additional uncommitted work, despite the expectation that worktrees would be paused:

| Worktree suffix | Work reviewed |
|---|---|
| `agent-ad0b239c493c87050` | Local roof surface, roof classification, CLI changes, synthetic tests, pilot/evidence/integrity/remaining-candidate scripts |
| `agent-a985a6c0c85999dc1` | Footprint acquisition, building reconciliation, classification rules, CLI changes, synthetic tests, pilot driver |
| `agent-a029d17a7780b32bd` | Stratified reference sampling, weighted accuracy metrics, review layers/chips, comparison harness, synthetic tests |

The review also traced the baseline acquisition record, LAS readers, preparation, raster support/occlusion, tiling/resume, treetops/crowns, and relevant tests. Saved manifests and diagnostics were inspected under `H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29`; installed deep-learning package metadata and model metadata were checked read-only. Full city processing, inference, new footprint requests, and new imagery requests were not run.

## Findings requiring correction

### 1. [P1] Candidate matching can reuse one prediction for several baseline candidates

[validation.py:429](V:/Developer/agol-python-scripts/.claude/worktrees/agent-a029d17a7780b32bd/canopy-toolbox/canopy/validation.py:429) uses independent nearest-neighbour presence within 1.5 m. The reverse check for new candidates is independent too. There is no one-to-one assignment.

Reproduced with baseline candidates at `(0,0)` and `(1,0)` and a single variant candidate at `(0,0)`: both baseline candidates are marked retained. With one TREE label and one ROOF_OR_BUILDING label, `score_treetops` estimates two kept candidates and zero false candidates removed although the variant contains one candidate. This distorts precision and removal estimates when nearby peaks merge or shift. The local-roof candidate diagnostic has the same limitation at a 1 m radius.

Use an explicit one-to-one assignment within the radius, preserving TREE_ID matches first where appropriate. Report ambiguous matches, shifts, and new candidates separately. Test a real peak beside a roof peak and a two-to-one merger.

### 2. [P1] Bootstrap intervals can imply certainty from a tiny sample

[validation_metrics.py:222](V:/Developer/agol-python-scripts/.claude/worktrees/agent-a029d17a7780b32bd/canopy-toolbox/canopy/validation_metrics.py:222) resamples only the observed values. A homogeneous labelled sample therefore produces homogeneous bootstrap draws.

Reproduced with five TREE labels in a stratum of 10,000 candidates: headline precision is 1.0 with interval `[1.0, 1.0]`. The same function's per-stratum Wilson interval correctly retains uncertainty, approximately `[0.566, 1.0]`. The zero-width headline interval is misleading for an accuracy report and can occur with all false labels too.

Use an interval method that handles zero/all successes for weighted proportions, or suppress degenerate headline intervals and explicitly show unresolved uncertainty. Preserve the distinction between a sample and a complete stratum census. Test homogeneous small samples as well as mixed samples.

### 3. [P1] Deep-learning comparison accepts failed or unprocessed copies as predictions

[dl_compare.py:74](V:/Developer/agol-python-scripts/canopy-toolbox/reviews/2026-09-29/dl_compare.py:74) validates point identity, then computes prediction tables without requiring a successful inference record. Identity is necessary for pairing points, but unchanged copies also pass it. [dl_run.py:87](V:/Developer/agol-python-scripts/canopy-toolbox/reviews/2026-09-29/dl_run.py:87) writes timing/messages in `finally` without an explicit success status; the comparator never reads that record.

Consequently a failed run, an untouched copy, or a boundary run compared without its extent can be presented as model agreement/disagreement. The current identity self-test proves pairing only. The existing deep-learning notes correctly say that no inference completed, but the scripts do not enforce that distinction.

Require a completed manifest containing model/input identity, processing boundary, editable/excluded classes, and verified output class semantics. Derive the evaluation mask from that manifest. For these binary models, reject unexpected classes among processed eligible points instead of counting every non-target class as model background. Preserve pairing checks and distinguish self-tests from prediction reports.

### 4. [P2] Saved residential candidate diagnostics compare the wrong refinement

[roof-local/candidates.json](H:/lidar/2023-salt-lake-valley/runs/pilot-2026-09-29/roof-local/candidates.json) points the residential tile to `12TVL2804\run-refined`, the original plane method. It records 17,285 candidates. [The local comparison](H:/lidar/2023-salt-lake-valley/runs/pilot-2026-09-29/roof-local/12TVL2804/comparison.json) records 16,179 candidates from `roof-local\12TVL2804\run`.

The other two tiles match their local comparisons. This mixed file cannot support a three-tile statement about local roof-level removals or overhang losses. Regenerate the residential entry using the local run, and validate exact run paths/signatures and counts against each comparison manifest. The raw candidate totals in the table below come from the consistent per-tile comparison files.

### 5. [P2] Pilot drivers mistake folder existence for successful completion

[pilot_driver.py:52](V:/Developer/agol-python-scripts/canopy-toolbox/reviews/2026-09-29/pilot_driver.py:52) and [roof_local_driver.py:56](V:/Developer/agol-python-scripts/.claude/worktrees/agent-ad0b239c493c87050/canopy-toolbox/reviews/2026-09-29/roof_local_driver.py:56) skip existing preparation/run folders. The underlying tools create folders before processing completes, so rerunning after an interruption or failure can silently skip the failed step. An incomplete run may never be resumed; a failed preparation may be passed downstream.

Check completed manifests and expected outputs. For incomplete canopy runs, use the existing signature-checked `--resume` path. Failed preparation/refinement needs an explicit new attempt directory or a supported recovery procedure. Do not treat an existing folder as an `ok` result.

### 6. [P2] The committed baseline pilot driver is not reproducible from its repository location

[pilot_driver.py:13](V:/Developer/agol-python-scripts/canopy-toolbox/reviews/2026-09-29/pilot_driver.py:13) sets ROOT to its own directory and reads `ROOT/las-inventory.json`. That file is absent from the repository review directory; the inventory actually used is in the external H: run root. Executing the checked-in script therefore fails before processing. Copying the script to H: changes its meaning and is an undocumented prerequisite. If an inventory is placed beside the repository script, large generated outputs go into the review directory.

Expose `--root`, `--inventory`, and the input LAS folder, with documented defaults outside the repository. Record the exact invocation in the timing/run evidence.

## What the classification evidence establishes

The delivered data has ground/noise and other minimum delivery classes; it has no delivered building or vegetation classification. `prepare` runs building classification first, then assigns remaining unclassified points to height classes 3/4/5. Height is not an object label: missed roof faces/edges, walls, wires, poles, vehicles, and structures can become apparent vegetation.

The CHM uses vegetation-class first/single returns without filling vegetation gaps. Building occlusion only acts where a higher measured building return occupies the same raster cell. It cannot remove an adjacent missed roof edge or a completely missed building. Altering crown size or maxima radius can hide some symptoms but does not correct canopy area.

The original refinement accepted only 70 of 805 residential roof regions and reduced residential candidates by 104. Its single low-slope plane is deliberately unsuitable for many gabled/hipped roofs. The local method fits nearby roof faces, uses unchanged class-6 support, and applies a narrower default band: 0.35 m below to 0.5 m above. Classes 4/5 are eligible by default; flags are preserved and synthetic/withheld/overlap points are excluded.

| Tile | Baseline candidates | Local-surface candidates | Net reduction | Canopy area removed |
|---|---:|---:|---:|---:|
| 12TVL2804 | 17,389 | 16,179 | 1,210 | 4,651.75 m² |
| 12TVL3302 | 44,285 | 43,813 | 472 | 2,683.25 m² |
| 12TVL2203 | 11,610 | 11,290 | 320 | 626.00 m² |
| Total | 73,284 | 71,282 | 2,002 | 7,961.00 m² |

These are net counts and mapped areas, not verified false-positive removals. Saved comparisons report no added canopy, no increased CHM heights, and no NoData-mask changes. Saved integrity checks pass for all three refinements, including unchanged non-classification bytes and matching per-point audit logs. This review inspected those saved checks; it did not independently reread every LAS byte.

The remaining-candidate diagnostic reports 3,767 roof-level suspects, of which 2,849 lack enough usable local faces. This suggests improving support/face estimation or footprint-guided review before widening the height band. Roof-level real branches remain intrinsically ambiguous. The local method cannot recover roofs with no class-6 support at all.

Footprint reconciliation now addresses that second failure mode. County screens report 15 LIDAR_MISSED footprints across the three tiles; the lidar-region screens report 100 regions without a matching footprint. These are review cases, not error counts. Source currency and coverage differ; county extracts are related sources, and OSM sources can share imported geometry. The label LAS uses the union of reference footprints, not agreement between two independent sources. Its “confident” non-building codes retain existing vegetation height classes, so they still include non-tree objects. Treat these as proposed labels for adjudication, not independent ground truth or ready-made tree-training labels.

## Deep-learning status and dependencies

The installed clone metadata confirms Python 3.13.13, `deep-learning-essentials` 3.7, PyTorch 2.9.1/CUDA 12.9, ArcGIS API 2.4.3, `arcgis-dlpk` 3.7, NumPy 2.3.5, SciPy 1.16.3, and python-pdal 3.5.3 from Esri. GPU inspection confirms an RTX 3060 Laptop with 6,144 MiB. The base toolbox uses ArcPy/NumPy/SciPy; the point-shape diagnostic additionally uses PDAL and SciPy cKDTree; monitoring uses psutil. There is no checked-in environment export that reproduces the clone's full package set.

The downloaded models are Building Point Classification/RandLA-Net and Tree Point Classification/PointCNN. Building uses XYZ and predicts 0/6; tree also uses Number of Returns and predicts 0/5. Both recommend 8 GB VRAM, so batch size 1 and a small copy are sensible experiments on this machine, not proof that inference will fit. [Esri building model](https://doc.arcgis.com/en/pretrained-models/latest/point-cloud/introduction-to-building-point-classification.htm), [Esri tree model](https://doc.arcgis.com/en/pretrained-models/latest/point-cloud/introduction-to-tree-point-classification.htm).

`DEEP_LEARNING.md` records successful imports/model loading but tool failure ERROR 002667. The active-environment explanation remains an inference, not a verified fix. No prediction evidence was found. Do not interpret downloaded models or GPU loading as successful classification. Esri also specifies matching model attributes and reasonably similar density/distribution. [Inference tool documentation](https://pro.arcgis.com/en/pro-app/latest/tool-reference/3d-analyst/classify-point-cloud-using-trained-model.htm).

The absolute-Z mismatch discussed in the notes is unresolved for the geoprocessing tool. Installed `arcgis.learn` data-loading code does recenter XYZ, so raw elevation limits alone are insufficient to conclude the building model is invalid here. Verify the actual inference normalization path before changing elevations. Preserve ground/noise for any eventual production integration: a pure 0/5 or 0/6 comparison copy is not directly ready for the canopy pipeline.

## Verification and remaining work

- Full main-checkout ArcGIS suite: 104 tests, 103 passed and one intentional skip; 207.3 seconds.
- Targeted local roof suite: 17 tests passed, including legacy/modern LAS byte preservation.
- Targeted building suite: 28 tests passed, including an ArcGIS reconciliation fixture.
- Targeted validation suite: 20 tests passed, including synthetic run/reference scoring.
- Syntax-only compilation: 56 baseline/review/worktree Python/toolbox files passed.
- Two evaluation defects reproduced in memory; saved run identity/count mismatch independently checked.

Initial sandbox runs failed because ArcGIS licensing and temporary fixtures were inaccessible; approved execution outside the sandbox resolved those environmental failures. Existing passing tests do not cover the defects above.

The saved validation set contains 1,468 units: 628 treetop, 300 omission, 360 cell, and 180 crown samples. Its score report explicitly says NO_LABELS, with zero labelled units. Independent human reference labels are the immediate missing evidence. Candidate precision is not a tree census; crown labels transferred only to substantially unchanged polygons are not overall variant crown accuracy. UNSURE/nonresponse may be systematic around roofs and canopy, so dropping them must be reported and examined.

Recommended sequence: correct matching/intervals and report provenance; finish a blind labelled sample across roofs, overhangs, true canopy, non-tree structures, omissions, and seams; then compare baseline, local refinement, and footprint flags on the same labels. Address weak local roof support and wholly missed buildings separately. Keep wall/wire shape features as review evidence until calibrated. Evaluate pretrained models as a later second opinion on a small copy, with a completed prediction manifest and a reproducible environment. Integrate the two worktrees' overlapping CLI changes together and rerun the full suite. Retain the 4,000,000-cell whole-AOI crown limit: a larger roof-prefilter limit does not validate seamless citywide crowns.
