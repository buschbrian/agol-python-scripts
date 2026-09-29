# Independent tree census and review prerequisites

Draw four 30 × 30 m plots per tile before consulting candidate maps. The fixed
seed is 20260929. The packet contains projected Esri JSON polygons (EPSG:6341),
blank plot-completion reviews, a tree-location worksheet and diagnostic cause
tables. It contains no predicted points, roof flags or LAS classes. Existing
reference samples and their labels are unchanged.

```powershell
python reviews/2026-09-29/plot_census_driver.py create NEW_PACKET
```

Use ArcGIS **JSON To Features** on `plots.esri.json` in a new review geodatabase.
Keep PLOT_ID. Draw each independent tree at its crown centre in a separate point
layer, then transfer its projected X/Y into `trees.csv`. Each independently
resolved woody tree at least 2 m tall gets one unique TREE_ID, measured height,
reviewer, review date and evidence. Inspect the full plot plus 3 m context. Include
centres on west/south edges; exclude east/north edges. Do not seed locations from
predicted treetops. Ambiguous merged crowns need further independent review;
leave the entire plot incomplete if its census cannot be resolved.

The probability frame is the complete 30 m grid, starting at each tile's southwest
corner. For these 1 km tiles it covers 990 × 990 m, leaving the 10 m north/east
strips out. Estimates refer to that frame, never the entire city. Plot totals are
expanded by grid-plot population/sample counts; plots are the sampling units,
not individual trees. Completed plots must remain a random subset within a tile.
Four plots are deliberately a small pilot; uncertainty may be wide or unavailable.

## Alignment and class-hidden point-cloud review

Before any labels, verify the actual imagery survey date and both horizontal
datums. At least four stable, well-spread building/ground corners per tile should
be identified independently in imagery and lidar. Record imagery X/Y, lidar X/Y,
offsets, mean offset, RMS and maximum offset in the review notes or an attached
corner table. Inspect a suspected uniform datum shift separately from object lean.
Use ground-level corners where possible; apparent roof edges in oblique standard
imagery are unsuitable control points. Set ALIGNMENT_QA to PASS only after the
alignment supports the intended 1.5 m matching radius and 0.5 m grid decisions;
otherwise resolve registration or record the plot as incomplete. Do not move
reference labels or fit a shift to improve a model's score.

In Pro, show **all** lidar returns with classification filters removed. Use
elevation or neutral symbology, hide class fields/legends, and make a cross-section
through each roof-edge ambiguity and tree. Measure ground-to-crown height directly
there; imagery alone cannot verify 2 m or an eave. Compare August 2023 imagery with
the tile's recorded November swath dates. Verify photo date at the location rather
than assuming a combined/latest WMS response has one date. The dated helper can
export an exact survey layer; its response still needs visible coverage review.

Only mark COMPLETE=YES after every tree has been reviewed, POINTCLOUD_REVIEW=YES,
ALIGNMENT_QA=PASS, reviewer/date and imagery date are recorded. Empty completed
plots are valid; blank reviews are not zero-tree observations.

## Scoring and diagnostic causes

```powershell
python reviews/2026-09-29/plot_census_driver.py score PACKET --run "12TVL2804=COMPLETED_RUN" --run "12TVL3302=COMPLETED_RUN" --run "12TVL2203=COMPLETED_RUN" --output NEW_SCORE.json
```

The primary radius is preregistered at 1.5 m. Every reference tree and detection
can join one pair, maximizing matched count before minimizing distance. Unmatched
trees are false negatives; unmatched candidates are false detections. Candidates
near already-matched trees are additionally flagged as duplicate detections.
Reports include detection rate (recall), false-detection rate, precision and F1,
plus analytic plot-design intervals and bootstrap cross-checks. Matching crown
centres to predicted apices is an operational spatial criterion, not biological
identity. Boundary displacement and dense crowns need review. Prespecified 1 m
and 3 m sensitivity runs may be reported alongside the primary result.

Freeze blind truth first. Then diagnose missed trees in `causes.csv` using the
absolute run folder as RUN, and the fixed PLOT_ID/TREE_ID. Allowed causes are
LEAF_OFF, EXCLUDED_UNCLASSIFIED, ROOF_CONFUSION, LOW_HEIGHT, SOURCE_GAP, DATE_CHANGE,
OTHER and UNKNOWN. Require reviewer/date and diagnostic evidence. A suspected
cause is UNKNOWN until supported by source returns or acquisition/date evidence.
Product misses remain misses: causes never erase false negatives or inflate
headline scores. They distinguish pipeline failures from what the November
acquisition could observe.

For already-labelled omission cells, fill `omission_causes.csv` after blind review:

```powershell
python reviews/2026-09-29/plot_census_driver.py diagnose-omissions PACKET --reference-gdb ORIGINAL_REFERENCE_GDB --output NEW_DIAGNOSTIC.json
```

This read-only command accepts only fixed omission SAMPLE_IDs independently
labelled TREE. It reports unweighted diagnostic counts and never modifies labels.

## Prospective holdout and domains

12TVL3302 plus its prepared 50 m context is reserved against future fine-tuning.
It has already been used for exploratory processing, so it is a **prospective**
training holdout, not a retrospectively untouched test set. Keep its imagery,
points, patches and rule-labelled LAS out of training, normalization, augmentation,
hyperparameter choice and early stopping. Check every training extraction:

```powershell
python reviews/2026-09-29/plot_census_driver.py check-training --extent XMIN YMIN XMAX YMAX
```

The guard rejects spatial overlap with 432950, 4501950, 434050, 4503050. A clean
future accuracy claim needs an additional area untouched by current development.
Codes 64–70 are footprint/rule-derived training hints, never scoring truth.
12TVL2203 is EXTERNAL_TRANSFER. MILLCREEK_PILOT_TILES includes only 2804/3302 and
does not imply exact municipal clipping or citywide representativeness. The
three-tile total is explicitly EXPLORATORY_COMBINED.
