# Training-label review (12TVL2804) — September 29, 2026

This packet collects **training labels** for fine-tuning point-cloud models (Esri
PointCNN / RandLA-Net / SQN / Point Transformer V3 in Pro) and imagery models. It is
separate from evaluation. It is not the [reference worksheet](REFERENCE_LABELS.md) or
the [plot census](PLOT_CENSUS.md). Training labels never enter `reference.gdb`. They are
never drawn on or near evaluation units. They never produce an accuracy figure.

Code: [canopy/training_review.py](../../canopy/training_review.py) (no ArcPy),
[canopy/training_review_arcpy.py](../../canopy/training_review_arcpy.py),
[training_review_driver.py](training_review_driver.py) (CLI) and
[TrainingReview.pyt](../../TrainingReview.pyt) (the Pro step-through tools). Tests:
`tests/test_training_review.py` (plain) and `tests/test_training_review_arcpy.py` (ArcGIS).

## The packet

`H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29\training-review\packet-20260929\`

| File | What it is |
|---|---|
| `training_review.aprx` | New review project (a copy of Pro's `Blank.aprx`; no existing project was opened or changed) |
| `training_review.gdb` | `training_units` (points, answer fields with domains), `training_patches`, `training_domain`, `excluded_evaluation_areas` |
| `layers\*.lyrx` | The same layers, for adding to any other map |
| `packet.json` | Frozen units, evaluation-exclusion frame and digest, parameters, source hashes, areas, queue counts |
| `review_session.json` | Created by the Label tool; remembers the reviewer name |

A first build is kept in `training-review\superseded\`; do not label it. It was not
split by class in Q3, so only 9 of its 187 Q3 units were on baseline class 5.

The template the brief suggested (`validation\review\validation_review.aprx`) does not
exist on disk: `validation\` holds only `reference.gdb`. The project is therefore
built from the install's `Blank.aprx`, as `validation.review_layers` does.

### Queues (built September 29, 189.5 s, CPU only, below-normal priority)

1,065 units. The cap is 200 per queue. Half of each cap is the highest-priority
clusters (TOP) and half is a seeded random sample of the rest (RANDOM). Assembly then
drops units that are too close to an earlier unit (spacing) or outside the domain.

| Queue | Source evidence (baseline 12TVL2804, tile core, training domain only) | Candidate clusters | Units |
|---|---|---:|---:|
| Q1_TREE_ON_ROOF | tree-full called 5 on baseline 6 (176,836 points) | 1,261 | 170 |
| Q2_BLDG_BACKGROUND | building-abs called 0 on baseline 6 (281,428 points) | 1,681 | 173 |
| Q3_VEG_BACKGROUND | tree-full called 0 on baseline 4/5 (362,757 points); cap split by baseline class | 702 (class 5) / 2,750 (class 4) | 182 (89 / 93) |
| Q4_SHAPE | shape-gate wall_like / wire / pole on baseline 4/5 (267,230 points); cap split in thirds | 355 / 1,871 / 271 | 165 (57 / 60 / 48) |
| Q5_ROOF_CANDIDATE | baseline treetops flagged ROOF_EDGE or ON_ROOF (`buildings\12TVL2804\review.gdb\candidate_flags`) | 1,289 | 182 |
| Q6_RANDOM | area-uniform random locations in the training domain | 400 drawn | 193 |

- **Clustering:** evidence points are binned into 1 m cells and joined through 8-connected
  cells into objects. Each object is split on a 15 m grid, so one unit stays roughly one
  object; pieces under 10 points (5 for shape groups) are dropped. The unit is the
  evidence point nearest the cluster's median position.
- **Priority:** cluster size, or candidate height for Q5.
- **Shape-gate runs:** REVIEW runs of the committed `shape_gate.py` (SHA-256 `09fcc555…`)
  on four 500 m quadrants, in `training-review\shape-gate\q-*`. Peak memory was
  1.11–1.25 GB, and each run took 53–104 s. Records are in `packet.json`
  (`shape_gate_runs`, `shape_gate_py_sha256_note`).
- **Integrity:** the baseline and both model outputs were checked to hold identical XYZ
  in the same order. Their SHA-256 matched before and after the build.

## Keeping training away from evaluation

Enforced when the packet is built, whenever a label is written by the Label tool, and on
every snapshot or export. A refused label is reported with its reason.

- **12TVL3302** plus its 50 m prepared halo (`432950 4501950 434050 4503050`, the
  existing `check-training` guard) and **12TVL2203** plus a 50 m halo are excluded
  entirely. Training units are drawn only from the 12TVL2804 tile core.
- On 12TVL2804, a patch must lie at least **25 m**, edge to edge, from every evaluation
  sample unit and every census plot. The frame holds all 1,468 reference units
  (treetop, omission, cell and crown outline) and all 12 plots, from every tile. Their
  identity and geometry come from `reference.gdb` and `plots.esri.json`. The plots are
  cross-checked against `census-review-final-20260929\review.gdb\plots`. No labels are
  read. Of those features, 494 are on 12TVL2804: 490 sample units and 4 plots.
- **Why 25 m:** it adds the 1.5 m preregistered matching radius, 22.6 m and the 1 m patch
  radius. The 22.6 m is the 99th percentile of the baseline crown bounding-box
  diagonal (11,661 crowns on 12TVL2804; maximum 36.2 m). A labelled patch therefore
  cannot share a typical crown, even a large one, with an evaluation treetop, cell,
  omission point, crown outline or plot.
- The frame digest is stored in `packet.json`. A snapshot or export first rebuilds the frame from
  the live `reference.gdb` and plots (geometry and IDs only, so evaluation labelling can
  continue). It refuses to run if the frame changed.

### Training area on 12TVL2804 (1 km² tile core, 0.5 m raster, exact distances enforced per unit)

| Rule | Allowed | Excluded |
|---|---:|---:|
| Patch centres ≥ 26 m (25 m buffer + 1 m patch) from all evaluation features, inside the tile | **0.361 km² (36.1 %)** | 0.639 km² |
| Points ≥ 50 m from evaluation features (the model's block size) | 0.024 km² (2.4 %) | 0.976 km² |
| Tile-aligned 50 m blocks wholly ≥ 50 m from evaluation features | **0** of 400 | — |
| Tile-aligned 100 m blocks wholly ≥ 50 m from evaluation features | **0** of 100 | — |

The sparse-patch domain, about a third of the tile, is enough for the patch queues
above. Fully labelled training blocks, however, are **not possible on 12TVL2804**
without touching the evaluation frame. The Pro architectures other than SQN need
such blocks (below). **Recommendation:** prepare one or more additional
non-holdout tiles purely for training. 12TVL2204 already has a pilot folder. That tile
must not be 12TVL3302, 12TVL2203 or their halos, and it should carry no evaluation
units. This packet does not prepare it.

## What a unit asks

Each unit is a point with a **patch**: a vertical cylinder of radius 1 m, cut to the
height slab `Z_LOW..Z_HIGH`. `HAG_LOW..HAG_HIGH` gives the same slab above ground, from
the ground raster in `building-hag\reference`. The label says what **every return in
that slab** is.

- **Radius 1 m:** at about 27 returns/m², a 1 m circle holds about 85 returns in plan
  view. That is enough to judge, and small enough that a roof edge, a wire span or
  one part of a crown stays homogeneous.
- **Disagreement and shape queues:** the slab is the evidence cluster's height range
  near the point, plus 1 m.
- **Roof candidates and random units:** the slab is the top 2 m of returns.
- Units are at least 2.5 m apart, so patches never overlap and labels never conflict.

| Label | Meaning | LAS training code |
|---|---|---:|
| TREE | Woody tree crown, branches or trunk (includes branches over roofs) | 5 |
| BUILDING_ROOF | Roof of a building, including roof-mounted equipment | 6 |
| WALL | Vertical face: facade, retaining/garden wall, solid fence | 72 |
| WIRE | Overhead wire or cable | 14 |
| POLE | Utility, light, sign or flag pole | 73 |
| OTHER_STRUCTURE | Carport, shade sail, playground, bridge, tank | 74 |
| SHRUB_LOW_VEG | Non-tree vegetation: shrub, clipped hedge, lawn, garden | 3 |
| GROUND | Bare ground, pavement, gravel, low hardscape | 2 |
| VEHICLE | Car, truck, trailer | 75 |
| WATER | Pool, pond, stream | 9 |
| MIXED | The slab clearly holds two or more classes (e.g. a branch over a roof edge) | not exported |
| UNSURE | Cannot tell from cross-sections and imagery | not exported |

**MIXED** was added to the requested list. Roof-edge and overhang patches often contain
two classes, and forcing one label there would mislabel points. Use MIXED only when the
slab really holds two classes; a single uncertain class is UNSURE.

Codes 72–75 are LAS user-definable codes. They avoid 64–71, which the shape gate and
the footprint review copies already use with other meanings. Pro's `class_remap` can
merge codes at training time, for example WALL into 6 or SHRUB_LOW_VEG into 1.

`IMAGERY_USABLE` answers one question: is the object visible and correctly
identifiable in the imagery at that point? YES exports the patch to imagery training.
NO or blank excludes it (walls, wires under canopy, shadows).

## Step by step in ArcGIS Pro

1. Open `training_review.aprx`. The map shows:
   - **Esri World Imagery**, for visual reference only;
   - the 12TVL2804 prepared LAS dataset with **all returns**, elevation stretch
     symbology and classes hidden;
   - the red **excluded** buffers (never label inside them);
   - yellow patch circles;
   - cyan **Training units**, labelled with UNIT_ID.

   Read the imagery capture date at your location from the World Imagery citation
   or Wayback, as the plot census requires. The World Imagery service adds its own
   *Citations* sublayer. Pro may warn about a missing `Blank.atbx` default toolbox: that
   reference is inherited from the Blank template and is harmless.
2. The **Training Review** toolbox (`TrainingReview.pyt`) is attached to the project. If
   it is missing, use Catalog > Toolboxes > Add Toolbox and choose
   `canopy-toolbox\TrainingReview.pyt`.
3. Run **Next Training Unit**. It selects the lowest-REVIEW_ORDER unit with a blank LABEL
   and zooms to a 30 m view. The optional *queue* parameter restricts it to one queue.
   The message gives the slab heights.
4. Inspect the unit in a **cross-section**. With the LAS layer selected, open
   *LAS Dataset Layer > Classification > Profile View*. This is the Pro 3.x ribbon location; it
   was not clicked through in this session. Draw a short line through the
   unit, about 2 m wide, and read the returns between Z_LOW and Z_HIGH. Imagery alone
   cannot verify height, eaves or overhanging branches. Check the imagery date against
   the November lidar: leaf-off trees and changed buildings are common.
5. Open **Label Training Unit** in the Geoprocessing pane. Pick LABEL and IMAGERY_USABLE
   from the dropdowns. The LABEL list is read from the geodatabase domain. Add NOTES if
   useful. REVIEWER is remembered after the first run. Press **Run**. The tool:
   - writes LABEL, IMAGERY_USABLE, NOTES, REVIEWER and today's REVIEW_DATE to the
     **one** selected unit;
   - refuses if zero or several units are selected, if the label is outside the
     domain, or if the unit is in the excluded evaluation domain;
   - refuses to replace a different existing label unless *Replace an existing
     different label* is ticked;
   - then selects and zooms to the next unit.

   The just-labelled point disappears from the map because the default definition
   query is `LABEL IS NULL`. Use *Labelled (check answers)* to see it. The tool re-checks
   the exclusion against the frame frozen in `packet.json`. A snapshot or export re-reads
   the live `reference.gdb` and plots as well.

   Repeat steps 4–5.
6. **Pro keeps the last dialog values after Run.** Change LABEL every time; the
   previous answer is still selected. If you edit in the Attributes pane or the
   attribute table instead, save those edits before running the tools again. The
   Attributes pane shows the same domain dropdowns.
7. For other views, use the *Training units* layer's definition queries:
   - Layer Properties > Definition Query: *Unlabelled (all queues)* (default), one
     query per queue, *All units*, or *Labelled (check answers)*;
   - for manual stepping, sort the attribute table by REVIEW_ORDER and use
     *Zoom To Selection*.

   Evidence fields (model classes, shape group, cluster sizes) are hidden in the
   default layer. `layers\training_units_evidence.lyrx` shows them, but it may bias
   your answers.
8. REVIEW_ORDER interleaves the six queues, so a short session still covers every
   queue. Within a queue the order is seeded and random, and it mixes top-priority
   clusters with a random background. Skipping units is fine for training, unlike the
   evaluation worksheet. Prefer UNSURE or MIXED over leaving hard cases blank.

**Not verified yet:** the zoom and selection behaviour of both tools
(`ArcGISProject("CURRENT")`, active map view camera) needs a live Pro session to
verify. The fixtures test the next-unit choice, validation, domain refusal and writing,
but they run outside Pro. Bookmarks are not generated: arcpy.mp in Pro 3.7 has no
bookmark-creation method, only import from a `.bkmx` file. **No ModelBuilder model is
shipped.** A model cannot be authored from arcpy, and it would only rerun the same tool.
The *Label Training Unit* dialog already is the loop: pick, Run, repeat.

## Snapshot, validation and audit

Direct editing is allowed, but nothing trains from the live table. First take a strict
snapshot, in ArcGIS Pro Python with `PYTHONNOUSERSITE=1`, from `canopy-toolbox`:

```powershell
$py = 'C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe'
$pk = 'H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29\training-review\packet-20260929'
& $py -B reviews/2026-09-29/training_review_driver.py status $pk
& $py -B reviews/2026-09-29/training_review_driver.py snapshot $pk NEW_SNAPSHOT_DIR
```

The snapshot refuses the **whole** table if any of these is wrong:

- a unit is missing, duplicated or unknown;
- an identity field changed (ID, queue, order, X/Y, slab, radius);
- a label is outside the domain;
- IMAGERY_USABLE is set without a label;
- a reviewer is missing, a date is not valid YYYY-MM-DD, or notes are too long;
- the evaluation frame changed;
- a labelled patch is inside the excluded domain.

It writes `labels.csv` and `snapshot.json`: the counts, the reviewers, the packet and
frame digests, and the SHA-256 of `labels.csv`. Exports re-verify that hash and every
unit token, so an edited snapshot is refused.

## Saving labels to the repo (backup and restore)

The geodatabase on the lidar disk is the working master, and `snapshot` is strict and writes to the same disk. So
the repo holds no labels until you back them up. `backup` copies every answered unit into
[packets/training-labels](packets/training-labels/) (`labels-progress.csv` and `progress.json`, stored byte-for-byte
by `.gitattributes`). It is lenient: a row that would fail the snapshot rules is still saved, with the reason in
`CHECK`, and the command exits 3. The output is deterministic, so unchanged work makes no git diff.
`restore` previews, then with `--apply` writes the repo copy back into blank units; a different live label is a
conflict, skipped unless `--replace`, and every written unit is read back. `restore` applies the same domain and
evaluation-frame checks as the Label tool.

```powershell
training_review_driver.py backup [--packet PACKET] [--out DIR]
training_review_driver.py restore [--packet PACKET] [--csv FILE] [--apply] [--replace]
```

[reviews/2026-09-30/training_labels.bat](../2026-09-30/training_labels.bat) wraps these for the reviewer
(`status`, `backup`, `save` = backup and commit, `restore`) and needs no PowerShell script. The reviewer's steps are in
[LABELLING_CHECKLIST.md](../2026-09-30/LABELLING_CHECKLIST.md). The driver reads the review GDB beside `packet.json`,
not the path recorded inside it, so it works when the disk has a different drive letter.

The project file stores the toolbox by absolute path (and the review layers by relative path, so they survive a
change of drive letter). A project built on one machine therefore shows the Training Review toolbox broken on another.
`training_review_driver.py repair-project` (or `training_labels.bat repair`, with Pro closed) adds this machine's
`TrainingReview.pyt` and keeps a dated copy of the project. arcpy can only add toolbox entries, not remove them, so the
stale entry stays until it is removed in Pro (Catalog > Toolboxes > right-click > Remove).

## Point-cloud training export (what Pro supports)

```powershell
& $py -B reviews/2026-09-29/training_review_driver.py export-pointcloud $pk SNAPSHOT NEW_EXPORT_DIR [--prepare]
```

The export writes a **new** LAS copy of the baseline 12TVL2804 file. The source is only
read, and its SHA-256 is checked before and after.

- Labelled slabs get their training code.
- Noise 7/18 is kept.
- **Every other point gets code 250.**
- The script then verifies that only classification bytes changed.
- It builds a LAS dataset and a spatial train/validation split by 50 m blocks (20 %
  of labelled blocks for validation).
- It writes `boundaries.gdb` and the recommended *Prepare Point Cloud Training Data*
  parameters: `excluded_class_codes = 250, 7, 18` and a 50 m block.
- `--prepare` runs that preparation. It prepares data only; it never trains.

What the installed tools support, checked on this machine (Pro 3.7.2, arcgis 2.4.3):

- **Prepare Point Cloud Training Data** has `excluded_class_codes` ("the class codes that
  will be excluded from the training data"), `class_codes_of_interest`,
  `training_boundary` and `validation_boundary`
  ([docs](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/3d-analyst/prepare-point-cloud-training-data.html)).
- **Train Point Cloud Classification Model** offers `architecture` PointCNN, RandLA-Net,
  Semantic Query Network and Point Transformer V3 (the default), plus `class_remap`,
  `target_classes` and `background_class`. Its documentation says "SQN does not require a
  comprehensive classification of the training data as the other neural network
  architectures do"
  ([docs](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/3d-analyst/train-point-cloud-classification-model.html)).
- **No ignore-label exists.** In the clone's `arcgis/learn`:
  - `models/_pointcnn_utils.py` `CrossEntropyPC` calls `F.cross_entropy(inp, target)`
    with no `ignore_index`; no point-cloud model sets one;
  - `models/_sqn_utils.py` queries all original block points
    (`xyz_query = end_points["xyz"][0]`);
  - `target_classes`/`background_class` remap unlisted codes to a background class
    that is still trained.
- **Empirical check** (synthetic, preparation only; record
  `training-review\prepare-probe-20260929.json`). With 250 excluded, the stored
  `.pctd` blocks held only the labelled points (classes 2 and 5; 132 train / 96
  validation stored records; overlapping blocks store a point more than once, so these exceed the 54 labelled input points). Without exclusion they held 36,796 / 36,192 points of
  class 250 as an ordinary class. **Excluded points are removed.** The model sees
  neither their label nor their coordinates, so unlabelled points are not "ignored with
  context".

So the export is implemented as far as Pro supports it. Sparse patches become
**islands** of labelled points, which only SQN is documented to tolerate. Whether
island training transfers to full-density inference is untested. PointCNN, RandLA-Net
and PTv3 need **fully labelled blocks**: every non-noise point in a 50 m (tree) or
100 m (building) block labelled, for example by correcting a copy of the baseline
classes in Pro's interactive LAS classification editing. Such blocks must lie 50 m or
more from evaluation units, and that domain on 12TVL2804 is almost empty (see the areas
above).

## Imagery training export (NAIP only)

```powershell
& $py -B reviews/2026-09-29/training_review_driver.py export-imagery $pk SNAPSHOT NEW_EXPORT_DIR --raster FOUR_BAND_NAIP.tif [--chips]
```

- The export writes `imagery_training_patches`: 1 m patch circles with a Short
  `CLASSVALUE` (1–10 in label order, 0 = unlabelled), for units whose label is
  exportable and whose IMAGERY_USABLE is YES.
- The raster must be the verified four-band NAIP in EPSG:6341 and must cover every
  patch; otherwise the export refuses.
- `--chips` runs *Export Training Data For Deep Learning*, Classified Tiles format, using
  the Spatial Analyst copy of the tool; Image Analyst is not licensed here.
- The only local NAIP is the 250 m pilot patch (`scratch\naip-review-20260929`). A
  tile-wide four-band NAIP export is needed before a real imagery export.

**Licensing flag.**

- NAIP (USGS, public domain) is the training raster.
- **Esri World Imagery is used only for visual review. It is not exported.** Its terms
  may restrict use as machine-learning training data; that decision is the user's.
- NAIP is 2021 and the lidar is November 2023. Changed buildings and trees make some
  lidar-judged labels wrong on NAIP. IMAGERY_USABLE is judged on the imagery you
  viewed, which may not be the NAIP date.

## Verification

- **Plain tests** (`tests/test_training_review.py`, 20 tests) cover:
  - edge-to-edge buffers for points, polygons and plots;
  - holdout-tile and tile-edge refusal; frame tamper refusal;
  - domain areas and clear blocks;
  - clustering and splitting; seeded top/random selection;
  - area-uniform random draws;
  - round-robin REVIEW_ORDER with spacing and domain drops, deterministic;
  - next-unit choice; answer validation (domain, reviewer, date, future date, notes);
  - label refusal in the excluded domain;
  - strict snapshot planning; snapshot tamper detection;
  - the LAS export: slab codes, noise kept, 250 elsewhere, source unchanged, only
    classification bytes changed, legacy/overlap/excluded refusals;
  - the block split, and label codes clear of 64–71.
- **ArcGIS fixtures** (`tests/test_training_review_arcpy.py`, 4 tests) cover:
  - GDB, coded-value domains and field domains;
  - patches, excluded areas and domain polygons;
  - the new `.aprx` with layers, definition queries and the attached toolbox;
  - the Label tool core: 0 / 2 selected, out-of-domain label, replace guard, advance,
    and excluded-domain refusal;
  - snapshot, then point-cloud export with a real *Prepare Point Cloud Training Data*
    run (preparation only), then imagery polygons and chips on a synthetic four-band
    raster;
  - refusal of a tampered snapshot.
- **Real packet:** built as above. A real `status`, and a real `snapshot` into
  `training-review\snapshot-20260929-empty`, re-checked the live evaluation frame and
  reported 1,065 units, 0 labelled. No real export exists yet, because there are no
  labels.
- **Pro-only behaviour:** zoom and selection inside a live Pro session are **not
  verified**.
- **Full suites:**
  - The complete ArcGIS Pro Python suite (`PYTHONNOUSERSITE=1`, default
    `arcgispro-py3`) ran 358 tests in 689.3 s: all passed, with 1 expected skip
    (`training-review\arcgis-suite-20260929-final.log`).
  - An earlier full run had shown that other suites leave `arcpy.env` workspaces
    pointing at deleted folders. The fixtures and `_domain_polygons` now pin their own
    workspaces.
  - Plain Python ran 358 tests: all passed, with 70 skipped.

## Decisions for the user

1. **Buffer.** The object-level buffer is 25 m. A stricter 50 m block-level buffer
   would leave 2.4 % of the tile and no whole blocks. Confirm 25 m, or choose a larger
   value and rebuild.
2. **Additional training tiles.** Fully labelled blocks for PointCNN, RandLA-Net or
   PTv3 need a training-only tile. Choose and prepare it; 12TVL2204 is a candidate.
3. **Sparse-label route.** SQN on labelled islands (with `excluded_class_codes`) is the
   only sparse path Pro offers. Try it first, or invest in fully labelled blocks?
4. **Esri World Imagery as training data.** Check its terms before any ML use. The
   exports use NAIP only.
5. **Label set.** MIXED was added. WALL/POLE/OTHER_STRUCTURE/VEHICLE use user codes
   72–75, and SHRUB_LOW_VEG maps to 3. Adjust, or plan `class_remap`.
6. **Tile-wide NAIP.** Fetch a verified four-band NAIP export of 12TVL2804 before any
   imagery training export.

## Decision recorded September 30, 2026: a label covers only the returns in the unit's patch

The training export gives a unit's label to every point inside its 1 m patch and height slab. A blind audit of the triage
(TRIAGE.md in `reviews/2026-09-30`) found labels that named something beside the patch or in the imagery (two VEHICLE labels
with no vehicle in the lidar within 3 m, a POLE and a WALL that lie outside the slab). Decision by the project owner: **label only
the returns in the patch**; where the interesting object is beside the patch, label what is in the patch or use UNSURE or MIXED.
Object-level labels (which would need a segmentation step) were not chosen.

- The checklist states the rule. `reviews/2026-09-30/label_consistency.py` flags labels the patch's own points cannot support
  (a VEHICLE whose patch reaches 0.3 m, a roof 1 m off the ground). The first run flagged 7 of the 58 labels then saved
  (Q3-0002, Q6-0008, Q6-0019, Q2-0060, Q6-0119, Q6-0147, Q6-0148) for a second look, and none of the 23 roofs or 11 grounds.
- Labels made before this decision are not assumed wrong; the flags ask a person to look again.
