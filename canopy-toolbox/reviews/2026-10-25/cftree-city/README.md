# CFTree city run — October 25, 2026

Brian requested CFTree on all 61 tiles and clarified that the other unfinished work meant review
examples. The separate [assistant review](../assistant-review/README.md) does not modify training or
calibration answers. The earlier [12-model pilot](../cftree-pilot/README.md) established the runtime.

## Running job

The coordinator started at 19:59 MDT October 25, 2026 in a hidden background Pro Python process.
All 61 refined LAS inputs have been staged. Their headers total **1,344,971,548 source points**.
The frozen configuration hash is `6fd0054860f04a3b4f175691b69dbca0b3d93225ade17e378ac1d6c233a720df`.

Run directory:
`C:\Users\Brian\Documents\Codex\2026-10-24\go-x20\work\cftree-city-20261025`.
Its `job.json` is authoritative; the chat's `outputs/cftree-city-progress.json` is refreshed as it runs.
`launch.json` records the initial PID, `runner.lock` prevents a duplicate coordinator, and the two
`runner.*.log` files capture exceptions. Do not start a second coordinator while the lock's process lives.

The first full tile, 12TVL2804, completed at 20:49 MDT: **3,186 models, zero rejections, 13 CityJSON
shards**. Export verification checked all 2,010,726 triangle faces: finite coordinates, valid indices,
closed edge incidence and no zero-area triangles after coordinate quantization. Feet attributes reverse
to metric crown width and inferred trunk diameter within 1e-8 m. This is a structural check, not full
solid topology, seam, schema or field validation. The pilot separately passed the official CityJSON schema.
The remaining tiles continue automatically; the evidence snapshot is historical, not a completion claim.

At Brian's request to use the machine overnight, the job resumed at 21:42 MDT with **two concurrent
CPU tile workers** and a process-scoped Windows keep-awake request. The frozen source/method
configuration and all checkpoints were preserved, including 1,165 completed models in the in-progress
tile. `execution.json` and `launch-overnight.json` record the current runtime; `handoff-complete.json`
proves no committed rows were lost. The initial serial PID in `launch.json` is historical.
This adaptation runs CFTree's CPU TreeSeparation/CGAL tools; it does not use CUDA. The available GPU
does not accelerate these stages. A new worker starts only with a free worker slot, at least 7 GB
available RAM and 15 GB free disk. The keep-awake request is released when the coordinator exits;
it does not change Windows' saved power settings or prevent display sleep.

## Inputs and method

- Immutable refined LAS: `H:\lidar\2023-salt-lake-valley\runs\refined-fractal-20261020\points`.
- Ground: `H:\lidar\2023-salt-lake-valley\runs\millcreek-products-20261022\terrain_m.tif`.
- Pinned CFTree commit `13be34b412a2f83f3ec1c89487665120348bb9d9`; isolated trimesh 5.2.0.
- Select classes 3/4/5, valid ground and height >=2 m (6.56 ft); exclude synthetic, withheld and overlap
  returns. Source size, timestamp, CRS and point count are checked during staging. Stage manifests retain
  selected-point checksums. Resume checks the frozen configuration and staged file size.
- Each 1 km core uses a trial 100 m neighbor margin. TreeSeparation defaults are 2.5 m radius, 1.5 m
  vertical resolution and 3 minimum points; reconstruction requires at least 50 points. AlphaWrap uses
  ralpha 15 and roffset 50. Geometry-only metrics omit CFD porosity/r50, which remain null.
- Highest-return core ownership is half-open at borders, with deterministic XY tie-breaking. UUID5 IDs
  derive from the highest source XYZ. This prevents duplicate ownership of an identical highest point;
  a finite margin does **not** prove identical segmentation or exact seams between tiles.
- The overnight run has two heavy worker slots. Scheduling requires 7 GB available RAM and 15 GB
  free disk before each launch; staging waits for 4 GB RAM
  and 15 GB free disk. A completed tree is committed to SQLite before the next starts. Rejections retain
  the exception reason. CityJSON exports in batches of at most 250 models per compressed shard.

Every crown and inferred trunk must have finite coordinates and a closed mesh before checkpointing.
CityJSON keeps XY EPSG6341 and original NAVD88 Geoid18 Z in meters, with its scale/translate transform.
Display attributes use international feet. Trunk positions and diameters are allometric estimates, not
observed stems or measured DBH. All products remain local drafts and unvalidated planning estimates.

## I/O adaptation and verification

The unchanged native C++ programs used tiny reads/writes across the Windows/WSL filesystem boundary.
`install_io_wrapper.py` retains each original ELF as `.native` and installs the corresponding shell
adapter. The adapters bulk-copy input into a unique Linux temporary directory, execute the same binary
and parameters, and copy output back. Cleanup names only their own known temporary files.

Segmentation and AlphaWrap outputs matched the pilot **byte for byte**; checksums and native-binary
hashes are retained in `evidence/`. No segmentation or reconstruction algorithm was changed. Both
adapters are in use for subsequent tiles.

Four actual Pro-runtime tests pass: border ownership/stable IDs, neighbor selection, concurrent-worker
RAM/disk/slot guards, and synthetic
LAS/terrain class/flag/ground filtering with unchanged source bytes and resumable staging. Changing the
east ownership test from `<` to `<=` in an isolated source copy caused the border test to fail as expected;
the live worker's source was unchanged. Export verification also passed on the completed full tile.

## Resume and inspect

Use Pro Python with `PYTHONNOUSERSITE=1` and `PYTHONDONTWRITEBYTECODE=1`. Resume with:

```powershell
& 'C:\Users\Brian\AppData\Local\ESRI\conda\envs\arcgispro-py3-dl\python.exe' `
  'C:\Users\Brian\Documents\Codex\2026-10-24\go-x20\work\lidar-wrapup\canopy-toolbox\reviews\2026-10-25\cftree-city\run_city.py' `
  run --run-dir 'C:\Users\Brian\Documents\Codex\2026-10-24\go-x20\work\cftree-city-20261025' `
  --workers 2 --keep-awake
```

The coordinator skips completed tiles, reuses segmentation, and skips already checkpointed models.
Do not rerun `prepare` on this directory. A rejected model is recorded as finished; investigate its reason
before deliberately resetting that row. Tile-level failures can be retried by resuming after fixing the cause.

`verify_tile.py TILE_DIRECTORY REPORT_JSON MEASUREMENTS_CSV` checks a completed tile and exports feet
measurements without modifying the tile. The first tile's draft archive, feet CSV and verification are in
the chat's outputs directory. Run manifests and data stay outside Git; only code and bounded verification
evidence are versioned.

## Before publishing trees

Reconcile neighboring tiles for split/duplicate/merged crowns; 1,218 first-tile models are flagged within
100 m of a core edge for review. Inspect dense vegetation, isolated trees, sparse returns and building
contamination. Review inferred trunk allometry for Utah trees. Compare against source points and field
samples before making accuracy claims. Packaging for ArcGIS/Azure and publishing the tree layer remain
separate steps; the existing public building release is unchanged.
