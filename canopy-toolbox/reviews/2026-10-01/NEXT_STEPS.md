# Next steps and how to pick this up on another machine (October 1, 2026)

**October 8 update:** the SSD is attached, the A4000 completed three verified
full-tile passes per imagery year, and the training comparison is saved.
Read [SSD_GPU.md](../2026-10-08/SSD_GPU.md) for the accepted outputs, Windows
reader/writer fixes and remaining manual review. The sections below retain
the October 1 state; the old SSD and first-run blockers are resolved.

Branch `canopy/classification-refinement`. Read [HANDOFF.md](../2026-09-30/HANDOFF.md) first (sections 1 to 3 for the data layout);
this page is what changed since and what comes next. Nothing here writes to live GIS data, and none of it should.

## 1. What exists now (all committed)
| Piece | Where | State |
|---|---|---|
| Label-only-the-patch protocol, patch height and warnings, bulk labelling, 3D scene | `canopy/training_review_arcpy.py`, `TrainingReview.pyt` | Built and unit-tested; **not yet confirmed live in Pro** (map and scene following, bulk tool, warnings) |
| Triage v2 (independent evidence) | `canopy/triage.py`, `2026-09-30/triage-2/` | 99 of 1,065 units are AUTO candidates; nothing is auto-accepted until audit 2 is scored |
| Audit 2 (40 units, blind) | `2026-09-30/audit-2/README.md` | **Waiting for you to label it** |
| FRACTAL model through Myria3D | `2026-09-30/fractal/` (`predict.bat`, README, patch) | Runs on the toy cloud on GPU and CPU; **not yet run on a Millcreek tile** |
| Colourised LAS for FRACTAL | `2026-09-30/colorize_las.py` | Written and tested; one crop was made on the SSD (`D:\lidar\...\fractal\crop-centre\colorized.las`, with a `.json` giving its extent) |
| NAIP 2021 tile (USGS service) | `2026-09-30/naip_fetch.py` | On the SSD (`...\naip\12TVL2804\`); flown 2021-11-13 |
| NAIP 2024 tile (UGRC sheets) | `2026-10-01/naip_ugrc_download.py`, `naip_local_tile.py`, [NAIP_2024.md](NAIP_2024.md) | Built on the workstation only; flown 2024-07-07 |

## 2. Setting up another machine
1. `git fetch`, then `git switch canopy/classification-refinement`. Run everything in the repo with ArcGIS Pro's Python
   (`C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe`) and set `PYTHONNOUSERSITE=1`.
   Call `.bat` files, not `.ps1` (execution policy is AllSigned on the City machines).
2. **The SSD** carries `lidar\` (tiles, `runs\pilot-2026-09-29`, `training_review.gdb`, NAIP 2021). Plug it in, or set `CANOPY_LIDAR_ROOT`
   to its `lidar` folder; `training_labels.bat` finds `D:\lidar` or `H:\lidar` itself. Back up labels first: `training_labels.bat save`.
3. **NAIP 2024 (needs no SSD).** From the repo's `canopy-toolbox` folder:
   ```
   python reviews\2026-10-01\naip_ugrc_download.py %USERPROFILE%\tools\naip-2024
   python reviews\2026-10-01\naip_local_tile.py 12TVL2804 428000 4504000 429000 4505000 %USERPROFILE%\tools\naip-2024\tile-12TVL2804 --sheets %USERPROFILE%\tools\naip-2024 --flight-date 2024-07-07
   ```
   The first is a plain public download of about 86 MB (add `--check` to only list sizes); the second makes the 4-band 0.5 m tile and
   checks it. The tile is 16 MB; copying it from the workstation (`C:\Users\bbusch\tools\naip-2024\tile-12TVL2804\`) works too.
   Imagery stays out of git.
4. **FRACTAL stack** (only where you want to run the model; a CUDA GPU is optional, `FRACTAL_GPUS=0` runs on the CPU, slowly). Under
   `%USERPROFILE%\tools` (override with `FRACTAL_TOOLS`):
   ```
   "C:\Program Files\ArcGIS\Pro\bin\Python\Scripts\conda.exe" create -p %USERPROFILE%\tools\envs\myria3d --override-channels -c pytorch -c nvidia -c conda-forge python=3.12 pip pytorch==2.4.1 pytorch-cuda=12.4 torchvision=0.19.1 lightning torchmetrics numpy h5py pdal=2.10 python-pdal gdal pyproj laspy "urllib3<2" pandas matplotlib seaborn hydra-core hydra-colorlog python-dotenv rich tqdm -y
   %USERPROFILE%\tools\envs\myria3d\python.exe -m pip install torch_scatter torch_sparse torch_cluster -f https://data.pyg.org/whl/torch-2.4.0+cu124.html
   %USERPROFILE%\tools\envs\myria3d\python.exe -m pip install torch-geometric==2.6.1 ign-pdal-tools lazrs
   git clone https://github.com/IGNF/myria3d %USERPROFILE%\tools\myria3d
   cd %USERPROFILE%\tools\myria3d
   git checkout c4f7f5e
   git apply --ignore-whitespace <repo>\canopy-toolbox\reviews\2026-09-30\fractal\myria3d-windows.patch
   ```
   Then download `FRACTAL-LidarHD_7cl_randlanet.ckpt` and `FRACTAL-LidarHD_7cl_randlanet-inference-Myria3DV3.8.yaml` from the Hugging Face model
   `IGNF/FRACTAL-LidarHD_7cl_randlanet` into `%USERPROFILE%\tools\models\FRACTAL-LidarHD_7cl_randlanet\` **and copy both into
   `myria3d\trained_model_assets\`** (`run.py predict` reads its config and checkpoint from there).
   Versions in the working environment: torch 2.4.1, torch-geometric 2.6.1, torch_scatter 2.1.2, torch_sparse 0.6.18, torch_cluster 1.6.3
   (the three +pt24cu124), pdal 3.5.5 (python), lightning 2.6.6, laspy 2.7.0, hydra-core 1.3.6, ign-pdal-tools 1.16.0.
   The pip lines are reconstructed from that list, not replayed: if the first run names a missing package, `pip install` it.
   The conda `pyg` channel is unreachable from the City network, which is why PyG comes from pip wheels. Myria3D's own
   `environment.yml` hangs the solver on Windows; do not use it.
   Check the install with the toy cloud:
   ```
   reviews\2026-09-30\fractal\predict.bat %USERPROFILE%\tools\myria3d\tests\data\toy_dataset_src\862000_6652000.classified_toy_dataset.100mx100m.las %USERPROFILE%\tools\runs\smoke
   ```
   It should end in "Runtime of predict" and leave a LAS with `PredictedClassification` and `entropy`.

## 3. Next steps, in order
Items 1 to 4 need a person and the SSD; 5 to 7 need the GPU machine (or a patient CPU).

1. **Label audit 2, blind** ([README](../2026-09-30/audit-2/README.md)): do not open `triage-2/triage-proposals.csv` or `audit-sample.json` until all
   40 are done. Then `training_labels.bat save` and score with the command in that README. Audit 1 is used up; do not tune rules on it.
2. **Re-look at the 7 flagged labels**: `label-consistency-1/recheck-select.txt`. Refresh the toolbox in Pro first.
3. **Confirm the Pro project live**: `training_labels.bat patch-stats`, then with Pro closed `training_labels.bat add-scene`, then open it and
   check that the map and scene follow the unit, the bulk tool works, and the warnings show. Report anything that fails.
4. **Register the NAIP against the lidar**: the sheets are NAD83 labelled 26912 and used as 6341 with no shift, and UGRC states
   1.07 m and 2.6 m accuracy. Measure the offset on roof edges or footprints before any sub-metre overlay.
5. **Run FRACTAL on a crop, with each year of imagery**: colourise the same extent with the 2021 and the 2024 tile
   (`python reviews\2026-09-30\colorize_las.py OUT.las --extent XMIN YMIN XMAX YMAX --naip <naip tif>`; each output must be a **new** file), then
   `predict.bat OUT.las RUN_FOLDER` for each. **Run each three to five times**: FRACTAL is not deterministic
   (about 91% agreement between identical runs on the toy cloud; see its README). Keep the majority class and the share of runs that agree.
6. **Write the comparison before looking at it.** There is no FRACTAL-versus-labels script yet. Decide and record the class mapping first
   (FRACTAL 1 other, 2 ground, 5 vegetation, 6 building, 9 water, 17 bridge, 64 permanent structure, to our labels), then for each unit's
   patch compare the majority FRACTAL class with the human label and the triage proposal. Report agreement per class with the run-to-run
   agreement beside it, and the 2021 against 2024 difference. It is a second opinion, not truth: it was trained on French LiDAR HD with
   contemporaneous colour (published mIoU 77.5 on its own validation set, 60.8 on its hidden test set).
7. **Only then** decide whether FRACTAL becomes a cue in triage, and whether the 15 cm Hexagon imagery is needed for visual review
   (you have Discover access; ask UGRC, ugrc@utah.gov, to confirm in writing that local processing is allowed, since the licence pages are silent on ML).

## 4. Where other tiles come from (researched October 1)
- **UGRC publishes only the 0.5 m DEM and first-return DSM** for the 2023 Salt Lake County lidar (raster.utah.gov), **no point clouds**.
- **USGS rockyweb has the LAZ**, all 61 Millcreek tiles, listed in `../../acquisitions/2023-salt-lake-valley/usgs-laz-millcreek.csv` and fetched with
  `canopy fetch` (about 140 KB/s per connection, 72 MB a tile). The USGS public AWS bucket (`usgs-lidar-public`) does **not** hold this project.
- **No aerial collection matches the lidar window** (2023-10-07 to 2023-11-05): NAIP is 2021 (flown 2021-11-13) and 2024 (2024-07-07), Hexagon 15 cm is the
  2024 flight only (flights 2024-07-07 and 2024-08-16 over Millcreek), and UGRC's NAIP page lists no 2023 collection.
  Hexagon is 15 cm (about 6 inch), RGB only and licensed; attribute it "(c) 2024 HxGN Content Program, Hexagon" if shown.
- UGRC's aerial tile index (`Aerial_Photography` feature service, AGOL item 747a5deabc6e46e9bec5594ce0993612) lists every sheet and its public download URL.

## 5. Still open
- **Which tiles next?** Wait for the SSD and use the training tiles already fetched (12TVL3006, 3205, 3206 and their neighbours), or fetch more
  from USGS (the 9 city-edge tiles are about 6.6 GB). Decide once FRACTAL has shown whether more data would help.
- **Decision-log location** (the decision-log skill asked where to keep decisions; not answered, no `docs/decisions.md` created).
- **Workstation instability** (WHEA and unexpected shutdowns, [HANDOFF.md](../2026-09-30/HANDOFF.md) section 7): a memory test, BIOS and GPU reseat are for IT/HP.
  Back up labels often (`training_labels.bat save`) and push.
- Licences to carry into any write-up: FRACTAL weights Etalab 2.0, FRACTAL dataset CC BY 4.0 (attribute IGN); NAIP is public domain.
