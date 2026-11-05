# Workstation handoff - October 8, 2026

Close out on branch `canopy/classification-refinement`. The user deferred further
model inference and tile preprocessing until tomorrow. No new overnight run was
started; the workstation process check found no Python jobs running.

## Completed and verified

- Paired A4000 FRACTAL inference on full tile 12TVL2804: three passes each with
  NAIP 2021 and 2024, source dimensions/order and consensus checks passed.
  See [SSD_GPU.md](SSD_GPU.md), committed in `04bbf22`.
- Millcreek count: 607,972 candidate treetops at least 2 m tall inside/on the
  MunicipalBoundary; 75,176 public/government, 454,849 private, 59,212 without a
  parcel match, 18,735 uncertain owners. All detections remain UNVERIFIED.
  See [CITY_COUNT.md](CITY_COUNT.md), committed in `f257bc3`.
- All 61 working LAS files have native building and raster-ground height
  classification. Ground/noise and all non-classification bytes were preserved;
  originals remain unchanged. These are baseline height classes, not citywide
  FRACTAL model inference.
- The count run already contains 63 city-intersecting raster cores: CHM,
  vegetation DSM, building DSM, DTM, observed, vegetation support and building
  occlusion. Native building DSM values are roof elevations, not building heights.
- Closeout: 143 Python/toolbox files compile with both repo Python and ArcGIS
  Pro Python. The plain suite ran 454 tests successfully, with 88 ArcGIS-only
  skips; see [closeout-tests.log](closeout-tests.log). The first sandboxed attempt
  failed on temporary-folder permissions; the authorized rerun passed. Actual
  ArcGIS pilots and final city verification are recorded in CITY_COUNT.md.

## Data and environment

Data remain on the SSD, outside Git:

```text
D:\lidar\2023-salt-lake-valley\las                    original LAS (61)
D:\lidar\2023-salt-lake-valley\laz                    original LAZ (63)
D:\lidar\2023-salt-lake-valley\runs\city-count-20261008
  tree-count.gdb\city_treetops                       GIS points; no CSV conversion
  city-treetops.csv
  prepared\points                                   isolated classified LAS
  raster-ground-recovery\prepared-surface.lasd        completed working LAS index
  raster-ground-recovery\ground_mosaic.tif            cached terrain
  rasters\                                           63 completed raster cores
  inputs.gdb\municipal_boundary, parcels
  count.json, verification.json, inputs.json
D:\lidar\2023-salt-lake-valley\fractal\full-tile-20261008-a4000-chunked
```

Repo: `U:\agol-python-scripts`. Pro Python:
`C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe`.
Set `PYTHONNOUSERSITE=1` for Pro execution. CRS is EPSG 6341, projected metres;
LAS elevations are NAVD88/Geoid18 metres. Acquisition was October-November 2023.
No power-plan changes or keep-awake helpers remain active.

## Tomorrow's requested work

Build the remaining reusable tile products, particularly CHM and building
heights. Inventory completed products first and reuse verified preparation and
terrain. Compare the 63 LAZ names with the 61 LAS names before deciding whether
additional conversion/preparation is necessary; the city count already has full
header coverage and reports 99.25% observed grid coverage.

Existing modules: `canopy/rasters.py` builds supported CHM and direct building
DSM; `canopy/planning.py` builds planning surfaces and paired roof-minus-terrain
statistics by footprint. See [PLANNING_PRODUCTS.md](../../PLANNING_PRODUCTS.md).
The planning bundle still has a 4,000,000-cell AOI limit. Do not remove that limit
or append independent crowns and call them seamless. Citywide building summaries
and a complete raster library have not yet been produced.

Use fresh processes and intersecting-neighbor LAS datasets for native raster
jobs, as in `run_city_count.py` and `recover_city_ground.py`. Preserve completed
cores and inspect their manifests. Native point-ground classification failed;
the verified raster-ground recovery is the accepted preparation for this run.
For tile 12TVL3204, statistics refresh plus a nine-neighbor subset resolved the
ground failure. Preserve NoData and support evidence; no vegetation gap filling.

Before footprint height summaries, locate the authoritative/reference footprint
dataset and its unique stored ID, verify CRS and coverage, and retain footprint
attributes and QA flags. Report roof-minus-terrain estimates as unvalidated
planning measurements. No field accuracy or code-defined building height is
established by the current outputs. Original LAS, evaluation data and training
labels must remain immutable.
