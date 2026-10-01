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

## Where things are (outside the repo, per machine)
- `C:\Users\bbusch\tools\myria3d`: clone of Myria3D, with `myria3d-windows.patch` applied (below).
- `C:\Users\bbusch\tools\envs\myria3d`: conda env (conda-forge: python 3.11, pytorch 2.4 cu124, pdal, laspy; torch-geometric and the
  scatter/cluster/sparse/spline wheels from `https://data.pyg.org/whl/torch-2.4.0%2Bcu124.html`, because the conda `pyg` channel is
  unreachable). Building from the full `environment.yml` hangs on Windows; use the short list of channels.
- `C:\Users\bbusch\tools\models\FRACTAL-LidarHD_7cl_randlanet`: checkpoint and config.

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

## Not done yet
Run on the colourised crop/tile of 12TVL2804 (needs the SSD), then cross-tab against `triage-2/triage-proposals.csv` and the human labels.
