# Training tiles (September 30, 2026)

**Status (2026-09-30 07:40 MDT):** the CPU phase is complete for all three tiles. Tree and building
inference is complete and verified for 12TVL3206 and 12TVL3205. For **12TVL3006, both GPU rows are
still to do**:

- The tree row's `dl_run` failed. At 04:05 the machine went into Modern Standby, and at 04:07 the
  H: USB disk was surprise-removed. When the machine resumed at 07:31, the run failed.
- The building row was never started. The queue process died at that same moment, and 07:30 had
  already passed.

Three more Millcreek tiles were prepared and run for the **TRAINING domain**, to grow the data
available for fine-tuning point-cloud models. They are **12TVL3206, 12TVL3205 and 12TVL3006**. Before
tonight, only 12TVL2804 could be used for training. These tiles join it in the training domain.
**12TVL3302** and its halo remain the prospective holdout, and **12TVL2203** remains external
transfer. Neither is ever used for training.

Training labels for these tiles will come from the training-review workflow
([TRAINING_REVIEW.md](../2026-09-29/TRAINING_REVIEW.md), `canopy/training_review.py`). That packet
currently draws units only from 12TVL2804. Extending it to these tiles is a separate step. Nothing on
this page is a label or an accuracy figure.

Files in this folder:

| File | Role |
|---|---|
| [select_training_tiles.py](select_training_tiles.py) | Seeded candidate rules and the draw (ArcGIS Pro Python; reads reference.gdb read-only) |
| [training-tiles.json](training-tiles.json) | The draw record: rules, the full 61-tile universe with the reason each tile was excluded, the candidates and the draw |
| [training_driver.py](training_driver.py) | CPU phase: prepare and baseline run, one tile at a time at below-normal priority |
| [run_training_gpu.ps1](run_training_gpu.ps1) | GPU phase: waits for the GPU to be free, then runs tree and building inference one row at a time |
| [summarize_training.py](summarize_training.py) → [training-results.json](training-results.json) | Collects the run records into one file |

Outputs are in `H:\lidar\2023-salt-lake-valley\runs\training-2026-09-30\`: `<TILE>\prepared`,
`<TILE>\run`, `<TILE>\cpu-record.json`, `training-timings.csv`, `driver.log` and `logs\`. The GPU rows
go in `deep-learning\<TILE>-<model>\`, with `deep-learning\gpu-queue.log` and `gpu-status.json`.

## Selection

The draw is `random.Random(20260930).sample(sorted(candidates), 3)`. It picked
**12TVL3206, 12TVL3205, 12TVL3006**, in that order. The rules were fixed before the draw was run.
`training-tiles.json` gives the reason for every excluded tile.

The universe is the 61 USGS tiles that touch Millcreek (`usgs-laz-millcreek.csv`). A tile is a
candidate only if it passes all of these rules:

1. **Full neighbourhood.** LAZ is on H: and the converted LAS is on D: for the tile and all eight of
   its 1 km neighbours, with LAS header point counts equal to the USGS manifest. This ensures the
   prepared 50 m halo is complete on every side. 12TVL2804 fails this rule itself because it has no
   12TVL2903. Most edge tiles fail it too.
2. **Not 12TVL2804.**
3. **Clear of the protected tiles.** Neither the tile's core nor its prepared extent (core ± 50 m)
   may intersect the 12TVL3302 holdout frame `432950 4501950 434050 4503050`
   (`evaluation_design.HOLDOUT_EXTENT`). The same applies to 12TVL2203 ± 50 m
   (`421950 4502950 423050 4504050`).
4. **No evaluation units.** No evaluation feature may lie within the tile's prepared extent. The
   evaluation features are the 1,468 reference sample units in `validation\reference.gdb`
   (treetop, omission, cell and crown) and the 12 census plots in `plots.esri.json`: 1,480 in all,
   of which 494 are on 2804, 494 on 3302 and 492 on 2203. The test compares bounding boxes. A point
   sitting exactly on an extent edge would not count as intersecting. No feature is that close to
   any candidate. This rule applies TRAINING_REVIEW.md's requirement that a training tile carry no
   evaluation units. It alone removes 2704, 2705, 2805 and 2905. 2803 and 2904 also carry 2804
   units, but they already fail rule 1. 12TVL2703 survives, since no 2804 evaluation feature lies
   within 50 m of its extent, but it was not drawn.

That leaves **10 candidates**: 2603, 2703, 3005, 3006, 3105, 3106, 3205, 3206, 3304 and 3305. As a
further check, `evaluation_design.assert_training_extents` passed for each selected core and
prepared extent.

**No stratification.** The task preferred a stratified draw. But the delivered classes are only
1, 2, 7 and 18, with no class 6, and `acquisition-facts.md` has no land-use or building-density
field. There was no usable proxy before processing, so the draw is simple random. The JSON also
records each tile's class-2 share from an 8,192-point inventory sample. That share is descriptive
only.

**The draw is spatially clustered.** 12TVL3206 and 12TVL3205 are adjacent: their halos overlap and
each is in the other's halo. 12TVL3006 is two tiles west of them, and its halo includes 3105/3106
(the same halo files as 3205/3206). All three are in the north-east of the city. They add training
data, but they do not represent Millcreek as a whole.

**Prepare source.** Following the September 29 pilot, the source is the converted LAS in
`D:\lidar\2023-salt-lake-valley\las`, not the LAZ in `H:\lidar\2023-salt-lake-valley\laz` (which
`prepare` cannot read). Header point counts match the USGS LAZ manifest for all 61 tiles.

## CPU phase: prepare and baseline run

`training_driver.py` runs the pilot's commands, from `reviews/2026-09-29/pilot_driver.py`, with no
extra options:

- `prepare D:\...\las <TILE>\prepared --extent core±50m`
- `run <TILE>\prepared\prepared.lasd <TILE>\run --extent core`

It runs one tile at a time at BELOW_NORMAL priority, with PYTHONNOUSERSITE=1. Before each step it
checks the other Python processes' command lines for another agent's whole-tile canopy CPU job. It
found none, so it never waited. The only other heavy process was the September 30 GPU queue's
12TVL3302 tree row, and GPU work is allowed to overlap.

| Tile | Prepare (min) | Peak RSS (GB) | Prepared (GB) | Run (min) | Peak RSS (GB) | Status |
|---|---:|---:|---:|---:|---:|---|
| 12TVL3206 | 1.44 | 2.48 | 0.86 | 3.75 | 0.69 | both `complete` |
| 12TVL3205 | 1.16 | 2.34 | 0.83 | 3.47 | 0.66 | both `complete` |
| 12TVL3006 | 1.94 | 2.75 | 0.93 | 3.57 | 0.67 | both `complete` |
| *12TVL2804 (pilot, 29 Sep)* | *2.02* | *2.28* | *0.98* | *4.67* | *0.68* | |

Each run logged the pipeline's usual warnings: unclassified points excluded, and canopy area with no
treetop seed. These were the same kinds of warning as the pilot's.

Each prepared extent contains 9 files: the core and 8 halo extracts.

- 3206: 3105–3107, 3205–3207, 3305–3307
- 3205: 3104–3106, 3204–3206, 3304–3306
- 3006: 2905–2907, 3005–3007, 3105–3107

Core class shares after prepare:

| Tile | 1 | 2 | 3 | 4 | 5 | 6 | 18 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 12TVL3206 | 2.8 % | 12.0 % | 42.6 % | 6.9 % | 25.7 % | 9.9 % | 0.12 % |
| 12TVL3205 | 2.0 % | 11.1 % | 42.2 % | 4.0 % | 24.9 % | 15.6 % | 0.17 % |
| 12TVL3006 | 1.6 % | 9.8 % | 38.2 % | 4.2 % | 28.4 % | 17.6 % | 0.29 % |

These are rule-based baseline classes, not truth.

**Same parameters as the 12TVL2804 pilot.** The manifests are not byte-identical. The new
`preparation.json` records `building_method: STANDARD`, and the new `run.json` records
`classified_background_zero: false`. Both keys were added on 29 Sep at 16:32 (a6e3c85), after the
pilot ran. Their values are the behaviour the pilot's code had hard-coded: `ClassifyLasBuilding` used
`method="STANDARD"`, and there was no class-0 background option. Every other parameter is equal,
apart from the extent and source ID.

**Code is not the same.** The runs used HEAD `83b359c` plus other agents' uncommitted edits to
`canopy/__main__.py` (new `hag` and `shape-gate` options) and `canopy/shape_gate.py`. None of those
edits touch `prepare` or `run`. Five commits since the pilot changed `preparation.py`, `pipeline.py`,
`rasters.py` or `las_records.py`, so the run signatures differ from 12TVL2804's. The per-file SHA-256
of `canopy/*.py` at launch is in each `cpu-record.json`.

## GPU phase: Esri pretrained tree and building models

`run_training_gpu.ps1` was started detached at 22:12 (pid 4612) and did the following:

1. Poll the September 30 experiment `queue.log` every 5 min for the literal `GPU QUEUE DONE`.
2. Then require 5 consecutive 1-minute polls with no compute-only GPU process. On this WDDM driver,
   `nvidia-smi --query-compute-apps` lists every desktop app that uses the GPU (explorer, browsers,
   Discord and so on, all type `C+G`), so it is never empty. The idle test therefore counts only type
   `C` rows in the `nvidia-smi` process table, plus any python/pythonw process in the compute-apps
   list.
3. Run one row at a time, tile by tile, tree before building, for 3206, then 3205, then 3006. Each
   row goes through the other agent's generalized runner
   `reviews/2026-09-29/dl-experiments-20260930/run_row.ps1`, reused read-only; its SHA-256 and
   `dl_run.py`/`dl_compare.py`'s are recorded per row. The runner makes fresh exact copies of the
   9 prepared files and checks MD5 before and after, with the core also watched. Settings are
   EDIT_ALL, classes 7/18 excluded and batch 1. `dl_compare` then produces the integrity check and
   disagreement tables.
4. Not start any row at or after 07:30 local time.

**What happened.** The other agent's queue logged `GPU QUEUE DONE` at 01:36:27, after its HAG rows.
The waiter found the marker at 01:37:15 and then counted five idle polls from 01:37 to 01:41. The
first row started at 01:41:16.

| Row | Files | Points | Row wall (min) | Tool (min) | GPU peak (MiB) | MD5 source = copy = source after | Watched core unchanged | dl_compare |
|---|---:|---:|---:|---:|---:|---|---|---|
| 12TVL3206-tree | 9 | 28,761,459 | 36.1 | 35.8 | 2,585 | yes (9/9) | yes | `verified_inference` |
| 12TVL3206-building | 9 | 28,761,459 | 18.1 | 17.9 | 1,981 | yes (9/9) | yes | `verified_inference` |
| 12TVL3205-tree | 9 | 27,618,004 | 33.8 | 33.5 | 2,434 | yes (9/9) | yes | `verified_inference` |
| 12TVL3205-building | 9 | 27,618,004 | 19.4 | 19.2 | 1,953 | yes (9/9) | yes | `verified_inference` |
| 12TVL3006-tree | 9 | — | 243.3 | — | 2,432 | before and copy yes; checked after by hand, see below | — | **not run: dl_run failed** |
| 12TVL3006-building | — | — | — | — | — | — | — | **not started** |

The rows ran much faster than the 90–110 min (tree) and 25 min (building) the task anticipated.

Every verified row matched its manifest:

- `status: complete`, EDIT_ALL, output classes `[0, 5]` for tree and `[0, 6]` for building
- classes 7/18 excluded, batch 1, PYTHONNOUSERSITE=1
- model SHA-256 `3da91365…` (tree) and `854bd59e…` (building), matching the September 29 rows

`dl_compare` found, for every file, identical coordinates and identical non-classification bytes
between each copy and its baseline.

**12TVL3006 failure, verbatim.** The ArcGIS tool itself reported `Succeeded at Wednesday,
September 30, 2026 4:05:21 AM (Elapsed Time: 36 minutes 28 seconds)`, and output fingerprints were
recorded for all 9 files. Then the System log shows:

- 04:05:27: `The system session has transitioned from 4 to 5`
- 04:07:52: `Disk 3 has been surprise removed`
- 07:31:56: `The system is exiting Modern Standby`

When the machine resumed, `dl_run.py` recorded `"status": "failed"`, `"error": "[Errno 22] Invalid
argument"` in `work\run-tree.json`. The runner logged `Program 'python.exe' failed to run: The volume
for a file has been externally altered so that the opened file is no longer valid. :
'...\12TVL3006-tree\work\dl_run.log'`. The runner stopped before its own after-MD5 step. I re-hashed
all 9 12TVL3006 prepared sources at 07:33, and each still matches its pre-run MD5.
`training-results.json` shows `md5_source_copy_after_all_equal: false` for this row. That is only
because the after-hash fields were never written, not because any hash differed.

The classified copies in `12TVL3006-tree\tree\` are **unverified**. Do not use them: their manifest
says `failed`, and `dl_compare` refuses failed manifests. The queue process also died at resume,
since its stdout handle was on the removed disk. Its last log line is the 3006 tree exit. Its
`gpu-status.json` still says `running rows`, with `12TVL3006-building` remaining. No row was started
after 07:30.

This failure is environmental (sleep plus a USB disk dropping out), not specific to the tile. To
redo 12TVL3006, move or rename `deep-learning\12TVL3006-tree` (the runner refuses an existing copy
folder), keep the machine awake, and run
`pwsh -File run_training_gpu.ps1 -Tiles 12TVL3006 -Cutoff 11:59`. The marker is already present.
Before noon, pass a `-Cutoff` later than the start time, because the default 07:30 would stop it at
once. The rerun should take about 55 min.

### Disagreement with the baseline classes (core + halo, all 9 files)

These tables show **class disagreement with pretrained models, not accuracy**. Neither the baseline
classes nor the model outputs are labels.

Share of each baseline class that the model called its target class:

| Baseline class | 3206 tree→5 | 3205 tree→5 | 3206 building→6 | 3205 building→6 |
|---|---:|---:|---:|---:|
| 1 unclassified | 0.80 % | 0.06 % | 0.24 % | 0.02 % |
| 2 ground | 0.53 % | 0.05 % | 0.42 % | 0.10 % |
| 3 low veg | 0.14 % | 0.01 % | 0.34 % | 0.04 % |
| 4 medium veg | 5.10 % | 3.45 % | 0.34 % | 0.75 % |
| 5 high veg | 97.81 % | 98.55 % | 1.05 % | 1.25 % |
| 6 building | 10.73 % | 8.53 % | 79.79 % | 78.26 % |
| 17 bridge deck | 32.1 % (of 10,161) | 7.7 % (of 11,508) | 9.7 % | 3.0 % |
| 7 / 18 noise | 0 (excluded) | 0 (excluded) | 0 | 0 |

Key disagreement counts:

| | 12TVL3206 | 12TVL3205 | *12TVL2804 core only (29 Sep)* |
|---|---:|---:|---:|
| Our 5 the tree model calls background | 156,998 of 7,163,757 (2.19 %) | 101,140 of 6,972,387 (1.45 %) | *103,256 of 8,818,572 (1.17 %)* |
| Our 6 the tree model calls tree | 297,909 of 2,776,890 (10.73 %) | 350,118 of 4,105,908 (8.53 %) | *496,598 of 4,325,602 (11.48 %)* |
| Our 6 the building model calls background | 561,292 of 2,776,890 (20.21 %) | 892,826 of 4,105,908 (21.74 %) | *751,115 of 4,325,602 (17.36 %)* |
| Our 3/4/5 the building model calls building | 123,783 (42,264 / 6,543 / 74,976) | 100,489 (4,945 / 8,202 / 87,342) | *142,577* |

The 12TVL2804 column is the core only, so it is not strictly comparable with the core-plus-halo rows.

The pattern is the one seen on 12TVL2804. The main disagreements are:

- About a tenth of baseline class 6 is called tree by the tree model.
- About a fifth of class 6 is called background by the building model.
- About 1 % of class 5 is called building.

12TVL3206 has many more baseline class 2 and 3 points that the tree model calls tree than 12TVL3205
does: 19,332 and 17,353, against 1,462 and 1,039. Its class-17 bridge-deck points are also often called tree (32 %).
These are candidate review queues, not errors established by either side.

Per-file tables are in `deep-learning\<row>\work\compare-<row>.json`. The combined figures are in
[training-results.json](training-results.json).

## Training domain and next steps

- 12TVL3206, 12TVL3205 and 12TVL3006 (each core + 50 m halo) are **TRAINING-domain tiles**, along
  with 12TVL2804. They contain no evaluation units or plots. None of them may be used as held-out
  evaluation for a model trained on them.
- 12TVL3302 plus its halo stays the prospective holdout. 12TVL2203 stays external transfer.
- Labels will come from the training-review workflow
  ([TRAINING_REVIEW.md](../2026-09-29/TRAINING_REVIEW.md)). That workflow currently draws units only
  on 12TVL2804. Pointing it at these tiles, including fully labelled 50 m or 100 m blocks, which
  2804 cannot provide, is a separate change.
- Still to do: the 12TVL3006 tree and building rows (see above).
