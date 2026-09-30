# Handoff: continue on the office GPU workstation (September 30, 2026)

Everything from the September 29–30 laptop session is committed on branch
`canopy/classification-refinement`. Large data is not in git; it lives on the H: USB disk
and the laptop's D: drive, listed below. Work stopped cleanly at 07:36 on September 30: no job
is running, and every completed run passed its integrity checks. The one exception is
12TVL3006; see step 4.

Verification at the stopping point: plain suite 360 tests OK (70 ArcPy skips); the full
ArcGIS Pro suite passed 360 tests (one expected skip) after the last code change to canopy/.

## 1. What to bring

| Data | Where | Size | Needed for |
|---|---|---:|---|
| Pilot runs: prepared tiles, baseline runs, validation `reference.gdb`, deep-learning outputs, HAG, training-review packet | `H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29\` | 69 GB | everything |
| Training-tile runs (12TVL3206, 3205, 3006) | `H:\lidar\2023-salt-lake-valley\runs\training-2026-09-30\` | 15 GB | training, 3006 rerun |
| USGS LAZ (source of record, 63 tiles) | `H:\lidar\2023-salt-lake-valley\laz\` | 5.5 GB | re-deriving LAS |
| Esri pretrained models (`.dlpk`, `models.json`) | `H:\lidar\models\` | 60 MB | inference |
| Uncompressed LAS used by `prepare` | **laptop** `D:\lidar\2023-salt-lake-valley\las\` | 42 GB | preparing new tiles only |

The D: LAS folder is **not** on the USB disk. Either copy it across before leaving
(`robocopy D:\lidar\2023-salt-lake-valley\las H:\lidar\2023-salt-lake-valley\las /E /J`,
H: has about 2 TB free), or re-create it at the office from the LAZ with ArcGIS Pro's
**Convert LAS** tool (compression "No Compression"), as the acquisition
[RECORD.md](../../acquisitions/2023-salt-lake-valley/RECORD.md) describes. If it moves, pass the
new folder to `prepare` or edit the `LAS` constant in `training_driver.py`, `select_training_tiles.py`
and `reviews/2026-09-29/pilot_driver.py`.

Small review packets that previously lived only on the laptop are now in the repo under
[reviews/2026-09-29/packets/](../2026-09-29/packets/). **The repo copies are the working
copies from now on**:
- `reference-review-batch1/labels.csv` is the evaluation worksheet.
- `independent-plot-census-v2/` is the census packet. The superseded `independent-plot-census` (v1) must not be used.
- `census-review-final-20260929/review.gdb` holds the census plots.

Older docs cite the laptop path
`C:\Users\Brian\.codex\visualizations\2026\09\29\01a0eed4-…`; read it as `packets\`.

Do not commit `canopy-toolbox\scratch\nearmap\` (it holds a key). Nothing else in scratch is needed.

## 2. Set up the office machine

1. **Drive letter.** Either give the USB disk the letter **H:** (Disk Management → Change Drive Letter),
   or, if H: is taken, set `CANOPY_LIDAR_ROOT` to the disk's `lidar` folder, for example
   `setx CANOPY_LIDAR_ROOT D:\lidar`, then open a new shell. The review scripts take their root from it
   (`canopy/lidar_root.py`), and recorded `X:\lidar\…` paths in the run manifests are translated to it when
   they are read back, so existing manifests still verify. Unset, nothing changes and the root is `H:\lidar`.
   The office workstation uses `D:\lidar` because H: is the network home share there.
2. **Power.** Stop sleep and USB selective suspend before any overnight job. The laptop's 12TVL3006
   row died when the machine slept and the USB disk dropped:
   `powercfg /change standby-timeout-ac 0`, `powercfg /change hibernate-timeout-ac 0`, and disable
   "USB selective suspend" in the active power plan's advanced settings.
3. **ArcGIS Pro 3.7.x** with 3D Analyst. Pro's Python 3.13 environments read the per-user
   `%APPDATA%\Python\Python313\site-packages`. Keep that folder empty, never `pip install --user`,
   and run every Pro Python script with `PYTHONNOUSERSITE=1`.
4. **Repo.** `git clone https://github.com/buschbrian/agol-python-scripts.git`,
   `git switch canopy/classification-refinement`, then
   `python -m venv .venv` and `.venv\Scripts\python -m pip install -r canopy-toolbox\requirements-dev.txt`.
5. **Deep-learning environment** (took about 1.5 h on the laptop; see
   [DEEP_LEARNING.md](../2026-09-29/DEEP_LEARNING.md)). From Pro's `bin\Python\Scripts`:
   `conda create --clone arcgispro-py3 -p %LOCALAPPDATA%\ESRI\conda\envs\arcgispro-py3-dl --pinned`, then
   `conda install -p %LOCALAPPDATA%\ESRI\conda\envs\arcgispro-py3-dl -c esri deep-learning-essentials`, then
   `proswap arcgispro-py3-dl`. **The tool fails with ERROR 002667 unless Pro's active
   environment is the DL clone.** Check it with
   `set PYTHONNOUSERSITE=1 && <clone>\python.exe -c "import torch, arcgis.learn; print(torch.cuda.is_available())"`.
6. **Path overrides** if the office layout differs. The GPU runners read `CANOPY_DL_PYTHON`
   (default `%LOCALAPPDATA%\ESRI\conda\envs\arcgispro-py3-dl\python.exe`), `CANOPY_TOOLBOX`
   (default: the repo's `canopy-toolbox`) and `CANOPY_VENV_PYTHON` (default: the repo `.venv`).
7. **Smoke test.** Run the plain suite in the venv. Then run the full suite with Pro Python:
   `set PYTHONNOUSERSITE=1` and, from `canopy-toolbox`,
   `"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" -m unittest discover -s tests -t .`
   (about 9 minutes, 360 tests, one expected skip).

## 3. Where things stand

| Area | State | Record |
|---|---|---|
| Evaluation reference (1,468 units) | **0 labelled.** Batch 1 = 743 blank rows. | [REFERENCE_LABELS.md](../2026-09-29/REFERENCE_LABELS.md) |
| Independent census (12 plots) | Blank; alignment QA and cross-sections still to do | [PLOT_CENSUS.md](../2026-09-29/PLOT_CENSUS.md) |
| Training-label review | 1,065 units on 12TVL2804, 0 labelled; `H:\…\pilot-2026-09-29\training-review\packet-20260929\training_review.aprx` | [TRAINING_REVIEW.md](../2026-09-29/TRAINING_REVIEW.md) |
| Pretrained inference | 12TVL2804 (core, halos, thinned, HAG-Z), 12TVL3302 (holdout, inference only), 12TVL2203 (external), 12TVL3206, 12TVL3205 | [DEEP_LEARNING.md](../2026-09-29/DEEP_LEARNING.md), [MODEL_EXPERIMENTS.md](../2026-09-29/MODEL_EXPERIMENTS.md) |
| Product scoring | Three conflict policies ran full-tile on the baseline grid; the harness accepts them; nothing to score until labels exist | MODEL_EXPERIMENTS.md |
| Height above ground | `canopy hag`; datasets for 2804 and 3302 complete; the 2203 core is refused in Z mode | [HAG.md](../2026-09-29/HAG.md) |
| Walls/poles/wires | `canopy shape-gate`; wall needs 0.7 m HAG; `--apply` changes 0 points on the pilot | [SHAPE_GATE.md](../2026-09-29/SHAPE_GATE.md) |
| Training tiles | 3206/3205 done; **3006 GPU unfinished** | [TRAINING_TILES.md](TRAINING_TILES.md) |

Domain rules (never relax them without a recorded decision):
- 12TVL3302 plus its halo is a prospective holdout: inference only, never training.
- 12TVL2203 is external transfer, outside any Millcreek estimate.
- Training labels stay 25 m from every reference unit and census plot. Model output, baseline classes and rule codes are never truth.

## 4. GPU work for today, in order

Each row copies fresh inputs, hashes them before and after, and runs `dl_compare`. Keep
batch 1 for every comparison row. On a bigger GPU, test batch size as its own experiment
(step d) before using it anywhere else.

a. **Rerun 12TVL3006** (about 55 min on the laptop). Rename
   `H:\…\training-2026-09-30\deep-learning\12TVL3006-tree` to `12TVL3006-tree-attempt1-sleep` (the
   classified copies inside are unverified), then from `canopy-toolbox\reviews\2026-09-30`:
   `pwsh -File run_training_gpu.ps1 -Tiles 12TVL3006 -Cutoff 23:59`. Pass a cutoff later than the start time, or it stops immediately.

b. **Tree reproducibility.** Repeat the absolute-Z tree row on the 12TVL2804 core (about 32 min).
   Without it, the 267k tree-point differences between HAG-Z and absolute Z can't be
   attributed to Z. Building outputs are already known to be deterministic.

c. **Remaining training candidates.** 2603, 2703, 3005, 3105, 3106, 3304 and 3305 passed the
   selection rules. CPU prepare and run take about 6 min per tile; then tree and building inference.
   `training-tiles.json` records the September 30 draw. A new draw needs a new seed and its own
   record. The current draw is clustered in the north-east.

d. **Batch size.** One 12TVL2804 tree row at batch 4 or 8, compared with batch 1, to learn
   whether larger batches change predictions before using them for speed.

e. **Optional seam test.** Joint core+halo inference for 12TVL2804, to measure how edge effects reach the core.

## 5. After labels exist

1. Evaluation. Preview first:
   `validation_harness.py import-labels packets\reference-review-batch1\labels.csv`.
   Apply only after checking the preview: `--apply --audit-dir …`.
   Then run `validation_harness.py score` with the baseline and the three product runs.
   The conflict-policy choice waits for this score.
2. Training export: `training_review_driver.py snapshot`, then `export-pointcloud`. Unlabelled points
   get code 250, which Prepare Point Cloud Training Data excludes. Only **SQN** claims to train
   on sparse labels, so try SQN fine-tuning first. The other architectures need fully labelled
   50–100 m blocks, which will come from the training tiles, not 2804.
3. Imagery training needs a tile-wide four-band NAIP export (public domain). Esri World Imagery
   is for viewing only unless its terms are confirmed for training.

## 6. Open decisions for the user

1. **Conflict policy:** tree wins, building wins, or a separate conflict class. Decide after scoring.
2. **Halo inference:** it changes nothing in the CHM under the clip-to-core pipeline. Keep it only for uniform semantics.
3. **HAG uncovered points:** refuse the whole file (current), or write a subset copy.
4. **Shape gate:**
   - should the 0.7 m minimum also apply to wires and poles?
   - should walls over missing ground get their own code?
   - calibration needs a separate sample, never batch 1.
5. **Training buffer:** 25 m (current) or larger. At 50 m, almost nothing on 2804 is usable.
6. **Training tiles:** accept the clustered draw, or redraw with a spatial-spread rule.
7. **World Imagery as training data:** yes or no.
