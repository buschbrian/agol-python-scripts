# Millcreek canopy terrain and building height products

Millcreek now has seven city-clipped GIS rasters at 0.5 m resolution and a county
footprint layer with roof-height statistics. All outputs passed the saved
verification. They reuse the October 8 native classification and terrain;
no model inference or source LAS classification ran in this batch.

The SSD is mounted at D:. Its current inventory contains 61 LAS and 61 LAZ files
with matching normalized tile names. The older handoff's 63-LAZ count does not
describe this inventory. The repository was resumed from `49c03e0` on
`canopy/classification-refinement`.

## Open the GIS products

Output folder:
`D:\lidar\2023-salt-lake-valley\runs\millcreek-products-20261019`.

| Dataset | Meaning |
|---|---|
| chm_m.tif | Supported canopy height above terrain; unknown cells remain NoData |
| terrain_m.tif | Interpolated bare-earth elevation |
| roof_elevation_m.tif | Direct class-6 first/single-return elevation |
| roof_height_m.tif | Paired roof elevation minus terrain; negative values retained |
| observed.tif | Canopy observation mask: 1 observed, 0 unknown, NoData outside city |
| vegetation_support.tif | Direct visible vegetation support after same-cell roof occlusion |
| building_occlusion.tif | Existing evidence that a higher roof occludes lower vegetation |
| buildings.gdb/building_heights | County footprints with paired roof-height statistics and QA flags |
| building-heights.csv | Matching attributes keyed by SOURCE_ID; the GIS layer needs no CSV conversion |

Use `HEIGHT_P50_M`, `HEIGHT_P95_M` and `HEIGHT_MAX_M` for the new building
measurements. The county's original `BLDGHEIGHT` attribute is preserved and was
not used in their calculation. `ROOF_COV_PCT`, `HEIGHT_STATUS` and `AOI_PCT`
describe support and city-boundary clipping. Footprint geometry stays whole;
height cells come from its intersection with the municipal boundary.

Coordinates are NAD83(2011) / UTM zone 12N, EPSG 6341, metres. Absolute terrain
and roof elevations inherit NAVD88/Geoid18 metre elevations from the lidar.
CHM and roof-height values are relative to terrain. Collection was
October-November 2023; the county footprint snapshot was downloaded October 19,
2026. These are unvalidated planning estimates, not surveyed or code-defined
building heights.

## Building coverage and review flags

| Result | Footprints |
|---|---:|
| Intersecting the city | 22,042 |
| With height estimates | 21,415 |
| No paired roof support | 624 |
| No raster cell centres | 3 |
| Low roof support below the 80 percent review threshold | 1,848 |
| Containing at least one negative height cell | 633 |
| Partially outside the city | 27 |
| Copied geometry repaired and flagged | 5 |

Flags overlap. All 22,042 records are UNVALIDATED. Overlapping or duplicate
footprint geometries are processed independently by their stored county ID;
22,042 is a footprint-record count, not a verified count of distinct buildings.
Negative cells remain available for review; no footprint has a negative median
height in this run.

The [public county footprint service](https://services1.arcgis.com/DJP723NX3ukQ2LtF/arcgis/rest/services/SLCo_BuildingFootprints/FeatureServer/0)
returned 48,957 records in the native query envelope, checked against its ID/count
response. Local projection and intersection retained 22,042. The native response,
native feature class, attributes and projection provenance are retained under
`footprints/`. Five OGC non-simple copied geometries were backed up before
repair; IDs and attributes were unchanged, and area changes were below
0.000000001 m². The originals are in `geometry-before-repair.json` and
`footprints.gdb/invalid_before_repair`.

## Methods and verification

The 63 previously completed raster cores supply the same canopy, terrain and
roof evidence used by the [October 8 count](../2026-10-08/CITY_COUNT.md). Native
jobs crop buffered products to nonoverlapping cores before assembly and city
masking. Every core passed grid, support and paired-height checks. Original LAS,
working LAS and source raster size/mtime fingerprints were unchanged.

The assembled rasters preserve exactly 133,813,488 city grid cells: 132,810,424
observed and 1,003,064 unknown, or 99.2504 percent canopy observation coverage.
There are 34,748,843 observed canopy cells at least 2 m tall. These four counts
exactly match the count run. No missing canopy was interpolated or extrapolated.

Building statistics reuse `planning_metrics.height_summary` on independent
footprint windows of at most 4,000,000 cells. Disk-backed raster caches avoid
loading the whole city into memory. Twelve real pilot footprints and a separate
20-footprint city sample matched actual ArcGIS CELL_CENTER rasterization; the
city sample also matched cached values against the source rasters exactly.
An exact-boundary-cell fallback uses ArcGIS rasterization; it was needed for
zero city footprints. Existing crown and planning-bundle limits are unchanged.

Final independent verification checked all 23,238,732 paired city roof cells for
exact subtraction and NoData preservation, including 13,793 negative cells.
It also checked all 22,042 feature IDs, CSV values, support counts, percentile
ordering, flags and finite numeric values. Output footprints preserve their
input geometry and attributes after the recorded five-copy repair.

Run manifests and proofs are on the SSD: `products.json`, `building-heights.json`,
`building-method-pilot.json`, `footprints/footprints.json` and `verification.json`.
Small verification copies accompany this report. Runtime was ArcGIS Pro 3.7.3,
Python 3.13.13. All five new workflow scripts compile in Pro Python.

## Continue from this library

Use the city rasters and `buildings.gdb/building_heights` for mapping and review.
Preserve the October 8 tree count and October 15 treetop-evidence outputs; this
batch does not replace them. The full extent of all 61 original tiles remains
outside today's agreed scope.

The runnable scripts alongside this report assemble products, fetch county
footprints, repair copied geometry, summarize buildings and verify outputs.
They refuse existing completed output datasets. A fresh raster assembly requires
a new output directory; do not rerun classification to recreate these products.
Slope, contours, drainage and roof planes are separate products and were not
generated in this batch. The [planning catalog](../../PLANNING_PRODUCTS.md)
records their methods and limits.
