# IGN FRACTAL model through Myria3D (an independent second opinion)

The model is `FRACTAL-LidarHD_7cl_randlanet` (IGN France, RandLA-Net; weights Etalab 2.0, dataset CC BY 4.0). It was trained on French
LiDAR HD with orthophoto colour, so on Millcreek its output is **an opinion to compare with triage and with human labels, not a label**.
Classes: other, ground, vegetation, building, water, bridge, permanent structure (the output uses codes 1, 2, 5, 6, 9, 64 and 65 for the ones the toy test produced).

## Running it
```
reviews\2026-09-30\colorize_las.py OUT.las --extent XMIN YMIN XMAX YMAX     (ArcGIS Pro Python; adds NAIP colour, sets class 1)
reviews\2026-09-30\fractal\predict.bat  OUT.las  RUN_FOLDER
```
The output LAS is a copy with `PredictedClassification`, `entropy` and per-class probabilities. Nothing reads or writes the review
geodatabase, and the source tile is never modified. The disk with the tile (`D:\lidar`) must be connected for a real run.

## Where things are (outside the repo, per machine; `predict.bat` reads `%FRACTAL_TOOLS%`, default `%USERPROFILE%\tools`)
- `tools\myria3d`: clone of https://github.com/IGNF/myria3d at commit c4f7f5e, with `myria3d-windows.patch` applied (below).
- `tools\envs\myria3d`: conda env, Python 3.12, PyTorch 2.4.1 CUDA 12.4 (rebuild recipe in [../../2026-10-01/NEXT_STEPS.md](../../2026-10-01/NEXT_STEPS.md)).
- `tools\models\FRACTAL-LidarHD_7cl_randlanet`: checkpoint (13.6 MB) and config from Hugging Face `IGNF/FRACTAL-LidarHD_7cl_randlanet`; both
  are also copied into `tools\myria3d\trained_model_assets\`, because `run.py predict` takes its config and checkpoint from there.

## Things learned (all needed to make it run on Windows)
1. **Absolute `predict.src_las`.** Hydra changes folder, so a relative path matches 0 files. `predict.bat` makes it absolute.
2. **`myria3d-windows.patch`** (4 lines in `pctl/datamodule/hdf5.py`): `predict_dataloader` hard-coded `num_workers=1`. Windows starts
   workers by pickling the transforms, and `TargetTransform` holds a local lambda, so it failed. The patch runs it in the main process.
   Re-apply with `git apply` after any update of the clone (the clone's files are CRLF; if needed `git apply --ignore-whitespace`).
3. **`pdal.exe` must be on PATH** (`<env>\Library\bin`); Myria3D shells out to `pdal info` after predicting.
4. **`datamodule.epsg=6341`**: the config default is 2154 (France).
5. **Colour is NAIP times 256** (Myria3D divides by 255 x 256 and asserts nothing is larger). It zeroes the colour of returns after the first itself.
6. **NAIP is leaf-off (2021-11-13)**, two years before the lidar, and the model expects contemporaneous colour. Expect weaker vegetation results.

## Smoke test
Myria3D's sample cloud (`tests\data\toy_dataset_src\862000_6652000.classified_toy_dataset.100mx100m.las`, 116,147 points) runs in 1.6 s on the
A4000: output has `PredictedClassification` (classes 1, 2, 5, 6, 9, 64, 65) and `entropy` (mean 0.34). That proves the pipeline, not accuracy.

## Repeat runner (October 7)

`repeat.py` runs three to five independent GPU passes, records input/model/code
hashes and logs, verifies every original LAS dimension by point index, and writes
a new `consensus.las`. It requires a colorized EPSG:6341 point-format-8 input,
the Myria3D environment and `PYTHONNOUSERSITE=1`. Choose a new output directory:

```bat
set PYTHONNOUSERSITE=1
%USERPROFILE%\tools\envs\myria3d\python.exe reviews\2026-09-30\fractal\repeat.py COLORIZED.las NEW_RUN_DIRECTORY --repeats 3
```

The consensus preserves the input Classification and adds `MajorityClassification`,
`RepeatAgreement`, `RepeatTie` and `StrictMajority`. A tied vote has code 0 and
`RepeatTie=1`; a unique plurality with less than half the votes is explicitly
distinguished from a strict majority. RepeatAgreement measures consistency, not
calibrated confidence or accuracy. Failed integrity checks leave a partial file
and a failed manifest, never a completed consensus. `predict.bat` now returns
nonzero for missing inputs/environments and preserves the inference exit code.

The first real local pilot used the existing 350 m 12TVL2804 prepared crop
(428075–428425 E, 4504075–4504425 N), colorized with NAIP 2024, without the SSD.
All 1,824,463 points passed the source-dimension and point-order checks across
three A4000 runs. Pairwise agreement was 98.92–98.95%; 1,795,941 points were
unanimous (98.44%), and 1,044 had three-way ties. Individual model calls took
about 14–15 seconds, excluding interpreter startup. This establishes execution
and repeat consistency for this crop, not classification accuracy or full-tile
performance. Outputs and manifests are in the October 7 chat's local artifact
folder, outside git. The source crop and colorized input were unchanged.

## Still to do

Run full tiles and the paired NAIP 2021/2024 experiment when the SSD returns.
Prespecify the class mapping before comparing consensus with
`triage-2/triage-proposals.csv` and human labels; the label packet is on the SSD.

## It is not deterministic (measured October 1)
Four runs of the toy cloud (three GPU, one CPU) agree on only **90.8% to 92.4%** of points, pair by pair, and CPU against GPU is no worse
than GPU against GPU, so the variation is run-to-run, not hardware. `myria3d/predict.py` never seeds (only `train.py` calls
`seed_everything`), and `MaximumNumNodes` subsamples any subtile over 40,000 points with an unseeded `torch.randperm`; RandLA-Net's own
random sampling adds more. The toy cloud is small and mixed, so the real tile may be steadier, but measure it before relying on any
single run. Treat FRACTAL like the tree model (about 0.88% of points change between runs): run it 3 to 5 times, keep the majority class
and the share of runs that agree as a per-point confidence, and report the agreement rate beside every comparison. Setting a seed would hide
the variation, not remove it.

`predict.bat` takes `FRACTAL_GPUS=0` to run on the CPU (tested; same output form), `[1]` for a second GPU, default `[0]`.
