# Independent review prompt for Opus or Fable

You are an independent senior reviewer of a Python/ArcGIS Pro canopy and planning toolbox. Review all accumulated work in this repository, not only the newest diff. Find actionable correctness, data-integrity, scientific-validity, reproducibility, security, and usability problems. Do not endorse results merely because tests pass. Do not invent defects to fill a quota.

## Repository and review boundary

Local repository: `U:\agol-python-scripts`; primary component: `canopy-toolbox`.

The implementation commit containing this prompt collects the previously uncommitted canopy/planning/model-validation work. Its baseline parent is `3777e12` (resolve the full hash locally). Start with `git status --short`, `git log -8 --oneline`, and `git diff 3777e12 <implementation-commit> -- canopy-toolbox`. Also inspect relevant earlier implementation/history and the current pipeline end to end. Later unrelated commits are not automatically part of this review.

Read `canopy-toolbox/AGENTS.md`, `README.md`, `DELIVERY_PROVENANCE.md`, `PLANNING_PRODUCTS.md`, the September 17 implementation/roof-edge reports, and the September 22/23 planning, classification, deep-learning and imagery reports. Treat their claims as evidence to check, not authority.

Work read-only initially. Do not classify original or prepared source LAS, edit production code, overwrite review labels, rerun GPU inference, publish ArcGIS data, push commits, or modify machine security settings. Return a review before fixes. Do not delegate. Check your own account usage first and retain a reasonable reserve; another provider's allowance is not visible from Codex.

## What changed and what to examine

1. Preparation and classification: copied-input isolation; preserved ground/noise/building classes; CONSERVATIVE/STANDARD/AGGRESSIVE building-method selection; metadata and default compatibility; model stage parameter semantics and stale LAS statistics.
2. CHM and observation: measured vegetation support; first/single returns and flags; same-cell building occlusion; ordinary class 0 remaining unknown; explicit model-background class 0 becoming observed non-canopy; whether that declaration is sufficiently constrained and reproducible.
3. Grids and spatial analysis: CRS/vertical units, extent, snap/origin, nodata, array orientation, cell area, tiled-core assembly, bounded whole-AOI segmentation, plateau seeds, crown seams, resume signatures and source provenance. Inspect existing code as well as new changes.
4. Cover and planning products: independent cover denominators and missing-area bounds; footprint-window height-summary optimization; overlaps, tiny/outside/partial polygons; terrain/drainage limitations and advertised output meaning.
5. Footprint review: copy-before-edit behavior, distances/CRS, output cleanup, preservation of source candidates and stable IDs. Roof overlap is a review priority, not a false-positive label.
6. Historical Nearmap WMS helper: exact-date versus combined/latest layers, inherited SRS, axis order and bounding boxes, credentials in URLs/errors/redirects, output overwrite/partial failure, image dimensions/georeferencing and metadata, and missing offline tests. Do not make paid network requests or retrieve new imagery for this review.
7. Documentation and evidence: distinguish working behavior, sensitivity metrics, qualitative AI triage and independently measured accuracy; identify stale or contradictory claims and broken reproducibility paths.

## Established context to verify

The delivery is 2023 LiDAR, not 2024, with reported nominal pulse spacing 0.32 m; this differs from the chosen 0.5 m raster grid. The Millcreek pilot is a 300 m square, EPSG:6341 extent 428100,4504100,428400,4504400. Do not confuse it with the earlier Taylorsville demo tile.

Standard, tree-only and building-then-tree outputs reportedly have canopy areas 20,962.75 / 20,308.25 / 20,435.50 m² and 1,530 / 1,345 / 1,299 candidates. These are sensitivity differences, not accuracy rankings.

The September 23 roof check reproduced a 55-cell / 13.75 m² connected addition within the current OSM roof mask and 89 class-6-to-class-5 transitions in a 300-point window. Across the pilot there are 782 added roof-mask cells. Building-stage class-6 count drops from 346,212 to 310,538, then holds during the tree stage. Exact intermediate point classes cannot be inspected because an after-building LAS was not retained. Check whether causal claims exceed that evidence.

All three compared LAS copies have 1,824,463 points; the recorded validation found matching ordered XYZ, returns and flags and unchanged before/after hashes. Review whether the script adequately checks coordinate scales/offsets, CRS, full point identity, raster transforms/masks and any hardcoded spatial assumptions. Do not regard a summary JSON as an executable assertion.

Imagery is from the Nearmap survey layer dated August 31, 2023, versus LiDAR acquired November 2/4, 2023. Local photo date and positional accuracy remain unverified. OSM footprints were retrieved in September 2026. Changes in season/date, overhangs and image displacement matter.

The existing sample comprises 206 candidate peaks and 24 deliberately selected 10 m plots. The September 23 exporter prepared 24 candidate and 24 plot views; only six of each received qualitative AI triage. No independent reference labels, measured canopy-area labels, omission counts, or production accuracy scores were completed. Assess stratification, selection bias, weighting, dependence, stem-versus-peak identity, and how missed trees should be evaluated. Keep learned alternatives experimental unless evidence warrants otherwise.

## Tests and available evidence

From `canopy-toolbox`, the full suite was run using:

```powershell
& 'C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe' -m unittest discover -s tests -t . -v
```

Result: **80 tests passed in 269.636 seconds**, with no skipped cases in the saved run. Evidence: `reviews/2026-09-23/regression-tests.txt`. Passing tests do not establish real-world classification accuracy. Run focused checks only where they resolve a finding; avoid repeating the full suite without a reason. Plain system Python lacked NumPy for one test module, and ArcPy licensing required individually approved execution outside the Codex sandbox.

Small committed evidence: `reviews/2026-09-23/roof-case-validation.json`, `validate_roof_case.py`, `export_dated_review_batch.py`, and `reviews/2026-09-22/TODAY_2026-09-23.md`. The roof script prints detailed results to stdout; the JSON is a summarized checkpoint. Both scripts locate data beneath `canopy-toolbox/scratch/models`; the exporter refuses an existing output folder.

Large inputs, DLPKs, LAS copies, geodatabases, imagery and contact sheets are intentionally ignored under `scratch/`. The review manifest is `scratch/models/dated_review_20260923/review_manifest.json`; successful sequential trial is `scratch/models/millcreek_building_tree_trial_v2`. A Git-only checkout cannot reproduce those real-data checks. If unavailable, identify the exact evidence gap and continue with code/tests; never fabricate inspection or request credentials.

## Required review output

Lead with findings ordered by severity (P0–P3), each containing an exact file/line, concrete trigger, consequence, supporting evidence or minimal reproduction, and a narrowly scoped proposed fix. Separate confirmed bugs from scientific validation gaps and hypotheses. Flag tests that skip, cannot run, or only mirror implementation. State explicitly if there are no actionable code findings.

Then provide: (1) tests/checks actually performed, (2) claims supported versus unsupported, (3) the minimum next validation experiment, and (4) a prioritized short fix list. Explain whether current outputs are suitable for exploratory use, independent validation, or production—and why. No modifications or deployment without a follow-up instruction.
