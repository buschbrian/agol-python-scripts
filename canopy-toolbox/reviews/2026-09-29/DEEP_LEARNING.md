# Esri deep-learning second opinion: status 2026-09-29

Short version: the deep-learning environment and both pretrained models are in place and load on the GPU.
The Classify Point Cloud Using Trained Model tool would not run, so there are no model predictions and no
confusion tables yet. The blocker is Pro's active-environment setting, which this task was told not to change.

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
- Pro's active environment was not changed: `conda env list` still marks `arcgispro-py3`, the HKLM
  `PythonCondaEnv` value is still `arcgispro-py3`, and there is no per-user override. `torch` is still not
  importable in the default env. `proswap` was not run.
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

## What blocked Part 3

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

## To finish (needs the user's decision)

1. `proswap -p "%LOCALAPPDATA%\ESRI\conda\envs\arcgispro-py3-dl"` in Pro's Python Command Prompt (per-user, no
   elevation). Note that this changes the runtime the canopy toolbox records; swap back afterwards with
   `proswap arcgispro-py3`. Close Pro first.
2. From the clone: `python dl_run.py building` and `python dl_run.py tree` in this folder. Batch size defaults to
   1 for 6 GB; the script samples `nvidia-smi` memory and writes timing to `work\run-<job>.json`. Use
   `--boundary 428250 4504250 428750 4504750` for a 500 m x 500 m area if the full tile is too slow or runs out of
   memory. Untested: full-tile runtime and whether 6 GB is enough.
3. `python dl_compare.py` applies the successful run's processing boundary automatically. An optional
   `--extent ...` must fit inside that boundary. It requires a complete inference manifest and checks SHA-256
   fingerprints of the baseline, prediction and model, the exact initial copy, point counts, scale, offsets,
   point order and binary class semantics before producing comparison tables. Unprocessed copies now fail
   with exit code 1 and no prediction headline. The earlier identity self-test is not inference evidence.

Open point for step 2: the script passes `output_classes` [0, target] with `EDIT_ALL`, so background predictions
should be written as 0 and the copy holds the pure model output. If the tool instead leaves background points at
their original codes, our class 6 and class 5 points called background by the model cannot be counted from
that copy. The comparator now rejects unexpected processed classes or modified excluded noise classes.
Any alternative normalization or classification-preservation strategy needs its own recorded input semantics
and comparator support; the current runner requires an exact baseline copy before inference.

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
version 1. The actual tool has not completed inference, so synthetic positive
tests and unchanged-copy integrity checks remain tests of the comparator only.

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

- `dl_run.py`: runner for the tool (not yet completed once).
- `dl_compare.py`: guarded comparison script; real untouched copies were rejected as expected on September 29.
- Model manifest: `H:\lidar\models\models.json`.

These would be model outputs, not accuracy: there are no reference labels for this tile.
