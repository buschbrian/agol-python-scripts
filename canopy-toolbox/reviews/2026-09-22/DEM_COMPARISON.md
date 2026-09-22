# Toolbox DTM against the delivery-derived DEM — September 22, 2026

The first external check on the toolbox terrain surface. Over the 300 × 300 m Millcreek pilot the
two surfaces agree to a **median of −0.031 m with an RMSE of 0.098 m**, and where the toolbox has
direct ground support the RMSE falls to **0.030 m**. The disagreement is systematic, has an
identified cause in the toolbox's own interpolation setting, and scales cleanly with distance from
measured ground.

[Difference map and histogram](../../scratch/planning_20260922/dem_comparison/dem-comparison.png) ·
[full statistics](dem-comparison.json)

## This is not an accuracy assessment

Both surfaces are interpolations of the **same 2023 classified point cloud**. Agreement therefore
measures how closely the toolbox reproduces a reviewed bare-earth surface built from identical
returns; it does not establish the vertical accuracy of either one against ground truth. The
delivery's tested accuracy (5.97 cm DEM NVA RMSEz) belongs to the vendor product, and this
comparison does not transfer it to the toolbox.

The reference is `G:\GIS\Data\millcreek_dem_half_meter.tif`: 26000 × 14000 cells at 0.5 m,
EPSG 6341 with NAVD88 height / Geoid18 in metres, spanning 422000–435000 E and 4501000–4508000 N.

The file carries no lineage statement, so its origin was established by test rather than by record:

- **It holds data where no local point cloud exists.** Tiles 12TVL2902, 2903, 3003 and 3103 are
  absent from the 52-tile LAS extract, and the mosaic is 100% valid across all four. It cannot
  have been derived from the point cloud on this network, so it came from delivered or published
  raster tiles.
- **It is bare earth.** Against `millcreek_dsm_half_meter.tif` over the pilot AOI the median
  difference is 0.000 m, rising to +11.26 m at the 95th percentile and +27.37 m maximum, with only
  0.27% of cells below zero. That is the signature of a terrain model under a surface model, not a
  surface model itself.
- **The file itself was written locally**, by ArcGIS Pro 3.4's bundled GDAL 3.10.2 on 2025-09-29,
  LZW compressed in 128 × 128 blocks. Its 0.5 m cell size, horizontal and vertical references all
  match the delivery specification.

Taken together: the published hydro-flattened bare-earth DEM, clipped and mosaicked locally to a
Millcreek rectangle. Which published copy — the Aero-Graphics delivery tiles or UGRC's
republication of them — is not recoverable from the file, but they are the same product. The
mosaic's holes do not follow the QL1 data product area, which contains the whole rectangle, and
they are not a tight city clip either: the mosaic is fully valid over tiles containing no Millcreek
at all. Whatever boundary was used to clip it is not recorded.

This is a stronger reference than a locally re-derived surface would have been: it is the vendor's
manually reviewed bare earth, produced independently of anything in this toolbox.

Grids align without resampling: the pilot AOI origin sits an integer number of cells from the
mosaic origin, so every comparison is cell-to-cell on a shared grid.

## Coverage

All **360,000** cells are valid in both surfaces. Neither has a void anywhere in the AOI, so no
part of the comparison is inferred across missing data.

| Surface | Range over the AOI |
|---|---|
| Toolbox DTM | 1320.925 – 1328.667 m |
| Delivery DEM | 1320.930 – 1328.775 m |

## Differences, toolbox minus delivery

| Subset | Cells | Median | Mean | RMSE | MAE | ≤5 cm | ≤10 cm |
|---|---:|---:|---:|---:|---:|---:|---:|
| All compared cells | 360,000 | −0.031 | −0.043 | 0.098 | 0.051 | 71.8% | 90.6% |
| With a direct class-2 return | 152,489 | −0.019 | −0.021 | **0.030** | 0.023 | 93.8% | 99.4% |
| With no direct ground return | 207,511 | −0.044 | −0.059 | 0.127 | 0.072 | 55.6% | 84.2% |
| Under a measured roof | 76,137 | −0.043 | −0.058 | 0.160 | 0.087 | 53.2% | 78.3% |
| Not under a roof | 283,863 | −0.029 | −0.039 | 0.073 | 0.042 | 76.7% | 93.9% |

Extremes span −1.19 m to +1.84 m. Only 42.4% of cells carry a direct ground return at 0.5 m, so
most of the AOI is interpolated on both sides.

## The low bias is a deliberate setting, not drift

Every subset has a negative median: the toolbox terrain sits consistently **below** the delivery
surface, by about 2 cm even where ground is directly measured. The cause is in the toolbox itself.
`rasters.DTM_INTERPOLATION` is `TRIANGULATION NATURAL_NEIGHBOR WINDOW_SIZE MINIMUM 1`, which thins
each cell to its **lowest** ground return before triangulating. A surface built from cell minima is
expected to sit under one built from the points as delivered.

That is a defensible conservative choice for canopy height — it will not inflate heights above
terrain — but it should be named as a known bias rather than read as error, and anyone comparing
toolbox terrain to an external DEM should expect this offset. It is not evidence of a datum,
geoid, or registration problem: the offset is far too small and too uniform for that, and both
surfaces declare the same vertical reference.

## Disagreement tracks ground support

| Distance to nearest direct ground return | Cells | Median | RMSE | ≤5 cm |
|---|---:|---:|---:|---:|
| 0 – 0.5 m | 152,489 | −0.019 | 0.030 | 93.8% |
| 0.5 – 1 m | 129,862 | −0.042 | 0.078 | 62.0% |
| 1 – 2 m | 38,335 | −0.055 | 0.160 | 43.8% |
| 2 – 4 m | 27,576 | −0.047 | 0.185 | 48.6% |
| 4 – 8 m | 11,100 | −0.056 | 0.231 | 40.5% |
| 8 m and beyond | 638 | −0.073 | 0.232 | 31.0% |

RMSE rises monotonically with distance from measured ground, from 3 cm to 23 cm. This is the useful
result for downstream work: **`ground_distance_m` predicts where the toolbox DTM is least
trustworthy**, so it can be published as a confidence layer rather than a diagnostic. The same
relationship explains the under-roof figures, since building interiors are exactly where ground is
furthest away.

## Worst cluster

The ten largest disagreements are one patch near 428219–428234 E, 4504393–4504399 N, at the
northern AOI boundary, where the toolbox reads 1.6–1.8 m **higher** than the delivery. Two county
footprints sit within 12 m — COUNTY_ID 733551 and 735811, both flagged `PARTIAL_AOI` because they
cross the analysis edge.

The surrounding terrain is near 1323.6 m and the delivery DEM holds that level; the toolbox carries
a bump to 1325.4 m. The most likely reading is a ground-classified return on or beside the
structure that the toolbox TIN honours and the vendor's **manually reviewed** bare earth removed.
The delivery's processing includes human review and correction of class 2; the toolbox has none.
This patch should be inspected in Pro before the pattern is generalized — it is one location, and a
single cluster is not a characterized failure mode.

## What this does and does not settle

Settled: the toolbox DTM is not grossly wrong, carries no voids here, has a small and explained
systematic offset, and degrades predictably away from measured ground.

Not settled: absolute vertical accuracy, behaviour on slopes (this AOI spans under 8 m of relief
and a 2.59% median slope), behaviour in the foothills or in parks, and whether the edge cluster
above represents a general weakness around buildings. The building-height products inherit terrain
error directly, so the under-roof RMSE of 0.160 m is the floor on their height uncertainty in this
sample — separate from classification error, and still not validated against measured buildings.

## Correction to the coverage recommendation

Delivery provenance originally recommended requesting the six interior tiles missing from the
extract. Two later findings narrow that. This mosaic already covers all six at full density, so
terrain work over them needs no new data. And four of the six contain no Millcreek at all; against
the city boundary, the tiles actually missing are nine edge slivers holding 1.25% of the city.
[Delivery provenance](../../DELIVERY_PROVENANCE.md#coverage-of-millcreek) now lists them.

## Reproducing

Run [compare_dem.py](compare_dem.py) with ArcGIS Pro Python; it reads both surfaces on the shared
grid and writes the JSON and figure to `scratch/planning_20260922/dem_comparison/`. Its input paths
are hard-coded to this pilot. The script is a review record, not part of the toolbox, and has no
tests; the figure stays in ignored scratch like the pilot's overview map.
