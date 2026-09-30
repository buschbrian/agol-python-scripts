# Esri deep-learning second opinion: status 2026-09-29

Update, September 30: an overnight queue added the 12TVL2804 halos, 12TVL3302 and 12TVL2203 (core + halos),
and a HAG-Z row. Every row verified. Full-tile product runs for three conflict policies were scored by the harness,
which reports no labels yet. See [September 30 queue](#september-30-queue-overnight).

Short version (updated late on September 29): the user authorized inference, reversing the earlier
"keep the environment, defer inference" decision. After Pro's per-user active environment was switched to the
deep-learning clone, Classify Point Cloud Using Trained Model ran. All four rows of the
[fixed experiment matrix](MODEL_EXPERIMENTS.md) completed on 12TVL2804 and passed the binary integrity gate.
The results are model outputs and **disagreement counts with the baseline classes, not accuracy**. There are no
independent labels in them. The sections below keep the earlier history.

## Environment (done)

- Clone: `C:\Users\Brian\AppData\Local\ESRI\conda\envs\arcgispro-py3-dl`, made with
  `conda create --clone arcgispro-py3 -p <path> --pinned` (conda 24.7.1 from Pro's `Scripts`).
- Installed: `conda install -p <clone> deep-learning-essentials` from the `esri` channel (the README's developer
  install path). The dry run showed one change to an existing package, certifi 2026.4.22 to 2026.7.22.
- Versions in the clone: deep-learning-essentials 3.7 (build cuda129_torch291_py313_9), Python 3.13.13,
  PyTorch 2.9.1 (cuda129, cuDNN 9.10), CUDA runtime 12.9, arcgis 2.4.3, arcgis-dlpk 3.7, arcpy 3.7 (Pro 3.7.2),
  numpy 2.3.5, spconv 2.3.8, torch-geometric/-cluster/-scatter/-sparse, fastai 1.0.63.
- `import torch, arcgis, arcgis.learn` works; `torch.cuda.is_available()` is True, device NVIDIA GeForce RTX 3060
  Laptop GPU (driver 616.64, 6144 MiB). `import arcpy` works; the 3D Analyst extension checks out as Available.
- During the first attempt, Pro's active environment was not changed: `conda env list` marked
  `arcgispro-py3`, the HKLM `PythonCondaEnv` value was `arcgispro-py3`, and there was no per-user override.
  Later on September 29 the main session switched the **per-user** active environment to the clone with
  `proswap` (see below). `arcgispro-py3` itself is unchanged and still has no `torch`.
- The install took roughly 1.5 hours, mostly download and linking.

## Models (done)

Downloaded anonymously with `item.download` to `H:\lidar\models\`; item details are in `models.json` there and
the `.emd` files are extracted under `H:\lidar\models\extracted\`. Both items are owned by `esri_analytics`,
tagged "Requires Subscription", and licensed under the Esri Master License Agreement.

| | Tree Point Classification | Building Point Classification |
|---|---|---|
| Item ID | `58d77b24469d4f30b5f68973deb65599` | `a64fa0b01aef406c8a0b2feaa1feee76` |
| File | `Tree_point_classification.dlpk` (14.5 MB) | `building_point_classification.dlpk` (6.1 MB) |
| Architecture | PointCNN | RandLA-Net |
| .emd version | 2021.12.09 | 2024.07.31 (arcgis.learn 2.3.0) |
| Classes | 0 background, 5 tree | 0 background, 6 building |
| Input attributes | X, Y, Z, number of returns (extra_features `num_returns`, 1 to 5) | X, Y, Z only |
| Block size | 50 m x 50 m (third value 314.22 is the training Z range) | 100 m, circular blocks |
| Max points per block | 8192 | 30000 |
| Reported accuracy | .emd 0.9896; item page: tree precision 0.975, recall 0.966, F1 0.971 (validation) | .emd 98.0; no per-class table |
| Training data | UK Environment Agency airborne lidar | Canada and Netherlands airborne lidar |
| Training point spacing | 0.6 +/- 0.3 m | 0.1 to 0.6 m |
| Units | metric X, Y, Z, projected CRS | metric, Z range -168 to 233 m |

Notes from the item pages and `.emd` files:

- Both were trained on the full point set (all classes present), so Esri says to give the network every point and to
  control results with target classification and class preservation. The tree item says it expects
  unclassified input; the building item says it was trained without high or low noise.
- Our tile is about 27 points per square metre (26,982,464 points in 1 km2, roughly 0.19 m spacing). That is
  denser than the tree model's training data (0.6 m spacing, about 3 points per m2) and at or beyond the fine end
  of the building model's (0.1 to 0.6 m). Density mismatch may affect either model; how much is not known.
- The tile's Z values are 1232 to 1471 m. That is inside the tree model's stated Z range and outside the building
  model's stated Z range of -168 to 233 m (stored as normalisation limits in the `.emd`). Inspection of the
  installed `arcgis.learn` point-cloud loader shows per-block recentering, including subtraction of the block's
  minimum Z. Absolute terrain elevation alone therefore does not establish an invalid input distribution.
  Compatibility of the actual geoprocessing inference path remains untested.
- The tree item says it is not expected to work well in mountainous regions. Millcreek is on the foothills, so
  treat tree results on steep parts of the tile with caution.
- Building limitations listed by Esri: skyscrapers and very large warehouses are less precise.

## Data copies (done, untouched by any model)

Copies of `prepared\points\12TVL2804.las` (809,475,416 bytes, MD5 `82787095336690d2909344206f9a80fc`) are in
`H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29\deep-learning\12TVL2804\building\` and `...\tree\`, each with
a `12TVL2804.lasd` and `.lasx` built by Create LAS Dataset (EPSG:6341). Both copies still match the original
MD5. The original and the other agents' folders were not touched. The tile profile (from the original):
class 1 455,565; 2 2,658,030; 3 9,589,034; 4 1,065,061; 5 8,818,572; 6 4,325,602; 7 1,559; 18 69,041.

## What blocked the first attempt (resolved)

Running `arcpy.ddd.ClassifyPointCloudUsingTrainedModel` from the clone's python (parameters were accepted; tried
on a scratch copy with a 250 m x 250 m boundary polygon, which I have since deleted) fails after about 0.4 s with:

    ERROR 002667: Cannot load python module. Make sure you have the right Deep Learning Python API
    (CNTK, TensorFlow, ...) installed.

What was checked:

- All imports the tool needs succeed in the clone, in either order: `arcpy`, `torch`, `arcgis.learn`
  (RandLANet, PointCNN), `fastai.callback`. Both `.dlpk` models also load onto the GPU through
  `arcgis.learn.<Architecture>.from_model`. The `.emd` path gave the same error as the `.dlpk`.
- The tool does not use the calling interpreter. No import failure occurred inside the calling process, and
  no `sys.path` change. Strings in Pro's `GpTinFunctions.dll` show the tool runs its own dependency check
  (`arcgis`, `torch`, `fastai.callback`) in a subprocess started from the embedded interpreter's `sys.prefix`.
  Setting `CONDA_PREFIX`, `CONDA_DEFAULT_ENV`, `PYTHONHOME` and `PATH` for the process changed nothing.
- The active-environment value lives in the registry (`PythonCondaEnv`, with `proswap` writing a per-user value
  unless `--all-users` is given). This is the most likely cause, but it is an inference from the error and
  the registry layout, not something I could confirm without changing it.

I stopped there. Changing the active environment was ruled out for this task, and I did not write the registry
value by other means. I also did not substitute a different inference path (for example `predict_las` in
arcgis.learn), because it would not be the tool that was asked for and the results would need separate
validation against it.

## Decision reversed: inference authorized (September 29, 2026)

Earlier on September 29 the user chose to keep the environment and defer inference. Later that day the user
authorized inference. The main session ran `proswap` to set Pro's per-user active environment to
`arcgispro-py3-dl`. No other registry edit and no package installation were made for the runs below. The earlier
copies under `deep-learning\12TVL2804\` were left untouched and are still not model outputs.

**The proswap fix is confirmed.** A 250 m building smoke test
(`deep-learning\smoke-20260929\`, boundary 428250 4504250 428500 4504500) succeeded in 154 s of tool time,
with whole-GPU memory peaking at 2,444 MiB. ERROR 002667 therefore came from the active-environment setting, as
suspected. The smoke run is **not** used as evidence. It ran without `PYTHONNOUSERSITE`, so the calling
interpreter loaded a stray numpy 2.5.3 and scipy 1.18.1 from
`C:\Users\Brian\AppData\Roaming\Python\Python313\site-packages` instead of the clone's numpy 2.3.5.

### Runtime isolation

Pro's Python 3.13 environments read the per-user site-packages unless `PYTHONNOUSERSITE=1` is set. Every matrix
run set it. `dl_run.py` now:

- **refuses to start** while `site.ENABLE_USER_SITE` is true, before writing any manifest, unless
  `--allow-user-site` is given; the override is recorded;
- records `PYTHONNOUSERSITE`, `site.ENABLE_USER_SITE`, `sys.prefix` and, for torch, arcgis, numpy and scipy, the
  version, module file, distribution location and whether the file is under `sys.prefix`, before and after the tool
  runs (`runtime_isolation`, `package_provenance`, `package_provenance_after`).

All four matrix manifests show `PYTHONNOUSERSITE=1`, `ENABLE_USER_SITE` false, and numpy 2.3.5, scipy 1.16.3,
torch 2.9.1 and arcgis 2.4.3, all resolving inside the clone. These records cover the calling interpreter.
The tool runs inference in a child `pythonw.exe` from the clone, which inherits the environment variable. For
tree-full, a snapshot of that worker's loaded modules
([worker-modules-tree-full.json](dl-experiments-20260929/worker-modules-tree-full.json)) lists the clone's numpy,
scipy and torch binaries and no module from the Roaming user site. The other rows' workers were not inspected.

### Matrix results (12TVL2804, tile-core boundary)

| Row | Tool time | GPU MiB before / peak (whole device) | Integrity | Main disagreement (inside boundary) |
|---|---|---|---|---|
| tree-full | 1 h 29 min 51 s | 1,970 / 4,187 | verified | 98.83% of baseline 5 and 11.48% of baseline 6 called tree |
| tree-thin3 (new 3 pts/m² baseline) | 44 min 54 s | 2,520 / 3,592 | verified | 98.90% of baseline 5 and 17.58% of baseline 6 called tree |
| building-abs | 19 min 52 s | 2,577 / 3,051 | verified | 82.64% of baseline 6 and 1.48% of baseline 5 called building |
| building-hag | 17 min 13 s | 1,415 / 2,086 | verified | output byte-identical to building-abs (null control) |

The full-density baseline MD5 matched `82787095336690d2909344206f9a80fc` before and after every row, and the
reference raster was unchanged. **Disagreement counts are not accuracy.** They compare two classifiers, and
neither has been checked against independent labels. The HAG row shows the reference raster changed nothing.
The building EMD uses XYZ only, so the absolute-versus-HAG question remains untested. Row details, the thinning
record, the reference-height raster and per-class tables are in [MODEL_EXPERIMENTS.md](MODEL_EXPERIMENTS.md).
Manifests, comparisons and row logs are copied into [dl-experiments-20260929/](dl-experiments-20260929/).

### Product scoring (tree-full)

A separate product copy (tree 5, restored baseline ground and noise, building-abs 6 where the tree model said
background, conflicts to tree) completed a bounded `canopy run` on 428250 4504250 428500 4504500 with
`--classified-background-zero`. It produced 929 treetops and 572 crowns and is UNVALIDATED. The validation
harness refused to score it ("Run grid differs from reference baseline for 12TVL2804"): it requires the
full-tile baseline grid. The reference sample has **no labels yet (0 of 1468 units)**. No accuracy figure exists.
Details and options are in [MODEL_EXPERIMENTS.md](MODEL_EXPERIMENTS.md#september-29-product-run-tree-full).

### September 30 queue (overnight)

With inference authorized for more tiles, a sequential queue ran on this machine (one GPU job at a time, clone
python with `PYTHONNOUSERSITE=1`, fresh exact copies, per-file MD5 before and after). Every row used one LAS
dataset over several files and no boundary. Every row passed the integrity gate file by file. Details and
tables are in [MODEL_EXPERIMENTS.md](MODEL_EXPERIMENTS.md#september-30-queue-halos-holdout-transfer-overnight-2026-092930).

| Row | Files / points | Tool time (tree / building) | GPU peak MiB (tree / building) | Headline disagreement |
|---|---|---|---|---|
| a. 12TVL2804 halos | 7 / 5.57 M | 11 min 13 s / 4 min 36 s | 2,363 / 1,913 | tree: 98.9% of b5, 10.9% of b6; building: 78.7% of b6 |
| b. 12TVL3302, prospective holdout -- inference only, never training | 8 / 40.3 M | 1 h 8 min 19 s / 26 min 15 s | 2,629 / 2,139 | tree: 97.2% of b5, 10.8% of b6; building: 81.0% of b6 |
| c. 12TVL2203, external transfer -- outside Millcreek estimate | 4 / 22.3 M | 30 min 19 s / 13 min 30 s | 2,590 / 1,930 | tree: 97.1% of b5, 8.7% of b6; building: 70.4% of b6 |
| d. 12TVL2804 core, HAG Z (own baseline) | 1 / 27.0 M | 32 min 10 s / 16 min 36 s | 2,470 / 1,987 | vs absolute Z by index: tree 267,073 points changed, building 108,210 |

- No class-0 point exists in any prepared file (core or halo) of the three tiles; checked by full scan.
- Row d's HAG baseline differs from the absolute baseline only in Z (verified over every byte). The first row d
  attempt failed with "Failed to open file for editing - the file may be read only or write protected" because
  the copy kept the HAG file's read-only attribute. That attempt is kept and labelled. The runner and `dl_run.py`
  now handle and refuse this case.
- Building predictions change with HAG Z. Building inference had been byte-reproducible for identical input, so
  this is a Z effect. The tree model is not reproducible: identical input changes about 237,500 points (0.88%)
  run to run, on either machine, so about 89% of the 267,073 tree changes are noise and a Z effect is at most
  about 29,000 points ([step b](MODEL_EXPERIMENTS.md#step-b-tree-reproducibility)).
- Full-tile product runs for three conflict policies (tree-wins, building-wins, conflict class 65) are on the
  baseline grid, and the harness accepted them. It reports 0 of 1468 units labelled, so **no accuracy
  exists**. The halo classes proved irrelevant to the CHM: baseline-halo and inferred-halo products are cell-for-cell
  identical.

### Point-record integrity gate

The comparator checks every point-record byte in bounded chunks, including return
numbers, intensity, GPS time, RGB/waveform fields when present, and opaque Extra
Bytes. All non-classification bytes must match the baseline. For legacy formats
0–5, classification occupies only the low five bits of its packed byte; the three
flag bits must remain identical. For formats 6–10, the separate classification
flags byte is among the protected bytes. This follows the existing binary reader's
LAS encoding; modern offsets are also documented in the
[ASPRS point-record definition](https://lasformat.org/latest/02.00_definition.html#point-data-record-format-6).

Noise classes 7/18 must remain unchanged everywhere, and all classifications
outside the recorded inference boundary must remain unchanged. Binary output
classes are checked across the entire processed area, including points outside a
smaller requested reporting extent. A changed point format, record length, count,
scale, offset, truncated prediction, or changed protected point byte rejects that
job before its disagreement counts are reported. Coincident XYZ coordinates alone
do not establish preserved point order when other point attributes differ.

`processed_extent` now describes the manifest's inference boundary;
`comparison_extent` describes the effective reporting rectangle. Both are null
for full-tile inference/reporting. Existing successful manifests still use schema
version 1. On September 29 the gate passed for all four real matrix outputs (above). The paragraphs below
describe the earlier checks of the unclassified copies.

The read-only pilot integrity check scanned all 26,982,464 records in each
existing copy. Both passed; source and copy SHA-256 fingerprints were identical
before and after. The scan took 2.619 seconds for the building copy and 2.098
seconds for the tree copy. The complete comparison command then rejected both
copies because their successful inference manifests are absent, producing no
model disagreement headline. The task artifacts `dl-point-integrity-check.json`
and `dl-integrity-provenance-check.json` record those separate results.

The final ArcGIS Pro Python suite ran 194 tests in 613.758 seconds: 193 passed,
with one expected delivery mock skip covered by the real ArcPy fixtures. The 17
new comparison tests include byte-by-byte corruption cases for legacy/modern
records and complete-command cases with synthetic LAS and provenance manifests.
The production script and new tests also passed Python compilation and the
repository whitespace check.

## Files

- `dl_run.py`: runner for the tool, with runtime-isolation checks and provenance. It handles multi-file rows
  (row manifest plus per-file schema-1 manifests) and `--label`, and refuses read-only copies.
- `dl_compare.py`: guarded comparison script; `--row-manifest` compares every file of a row with its own baseline.
- `dl_thin.py`: whole-pulse thinning into a new baseline. `dl_reference_height.py`: class-2 ground raster built
  from copies.
- `dl_product.py`: documented product copy from verified outputs (never a raw output), with conflict policies
  `tree-wins`, `building-wins` and `conflict-class`. `dl_product_tile.py`: full-tile product runs on the baseline grid.
- `dl_hag_check.py`: verifies that a HAG baseline differs from its absolute baseline only in Z, and pairs predictions by index.
- `dl-experiments-20260929/`, `dl-experiments-20260930/`: manifests, comparisons, logs and the row runners.
- Model manifest: `H:\lidar\models\models.json`.

These are model outputs, not accuracy. Disagreement with the baseline classes is not error, because the
baseline is not truth either.
