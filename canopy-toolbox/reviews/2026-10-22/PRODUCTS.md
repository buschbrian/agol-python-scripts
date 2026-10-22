# Millcreek canopy, building and tree products, October 22, 2026

The current version of every Millcreek lidar product, rebuilt from a better classification. Brian asked on October 22 to
"keep rebuilding items with the better data". The [October 19 library](../2026-10-19/PRODUCTS.md) and the
[October 8 count](../2026-10-08/CITY_COUNT.md) stay on the SSD unchanged for comparison.

Output folder: `D:\lidar\2023-salt-lake-valley\runs\millcreek-products-20261022` (`library.json` lists each file's source
and SHA-256). Coordinates NAD83(2011) / UTM 12N, EPSG 6341, metres; elevations NAVD88 (Geoid18). Lidar collected
October-November 2023. **These are unvalidated planning estimates, not surveyed or field-verified data.**

## What changed from October 8 and 19
The October products used one classification of the lidar points, the October 8 native height and building classes. This
library uses a combined classification:
- **Buildings:** a point is roof when at least two of three independent sources call it building: the October 8 native
  class, the IGN FRACTAL model (three-pass majority) and Esri's pretrained building model
  ([roof-consensus](../2026-10-21/roof-consensus/README.md)).
- **Everything else:** the FRACTAL refinement rules v2 ([fractal-city](../2026-10-19/fractal-city/README.md)), which moved
  bare ground out of "low vegetation" and corrected vegetation, building, structure and other where all three FRACTAL
  passes agreed. Points classed other (1) or permanent structure (64) count as observed non-canopy.
- **Terrain is unchanged** (ground was not reclassified), so heights are measured from the same surface as before.

Every rebuild used the October method and was first proven on the old classes. The native version of the canopy rasters
equals October 19's on every one of 133,813,488 city cells; the native roofs equal October 19's on all 23,238,732 roof cells;
the native canonical canopy equals October 8's count input on every cell. So each difference below comes from the
classification, not the method.

Checked against 1,217 labelled parts on 12TVL2804 (Brian's training labels; a hard sample, not a city accuracy):

| | October 8 / 19 | October 22 |
|---|---:|---:|
| Roofs found | 89.2% | **92.8%** |
| Non-roofs called roof | 14.0% | **2.8%** |
| Trees called vegetation | 88.9% | **95.9%** |
| Non-vegetation called vegetation | 41.2% | **10.7%** |
| Shrubs called vegetation | 85.9% | 76.5% (rules v2 moves some shrub to ground) |

## Products
| File | Meaning |
|---|---|
| chm_m.tif | Canopy height (m); NoData = unknown or outside the city |
| observed.tif | 1 observed, 0 unknown, 3 outside the city |
| vegetation_support.tif | 1 where a vegetation return supports the cell |
| building_occlusion.tif | 1 where a roof occludes lower vegetation |
| terrain_m.tif | Bare-earth elevation (m), as October 19 |
| roof_elevation_m.tif, roof_height_m.tif | Consensus roof elevation and height above terrain (m); negatives kept |
| building_sources.tif | Which sources saw roof in the cell: 1 native + 2 FRACTAL + 4 Esri |
| buildings.gdb/building_heights, building-heights.csv | 22,042 county footprints with roof height statistics and flags |
| tree-count.gdb/city_treetops, city-treetops.csv | 527,140 treetops at least 2 m, with parcel ownership; OCT8 = SAME_CELL or NEW |
| treetop-evidence.csv | Review evidence per treetop (roof edge, flat top, wire, pole, wall hints); 32,986 SUSPECT |
| crowns.gdb/crowns, crowns.gdb/trees_review | 400,063 estimated crowns (TREE_ID, HEIGHT_M, CROWN_AREA_M2, CROWN_DIAM_M); treetops with crown status |
| cover.gdb (zones, cover_rebuilt, cover_oct19), cover-comparison.csv | Canopy cover by zone, both canopies |
| review/canopy_change.tif | Canopy at least 2 m since October 19: 1 both, 2 lost, 3 gained |
| review/treetop-changes.csv | Treetops removed and added since October 8 |
| review/height-changes.csv | Footprints whose height or roof support changed |

## Key figures
| | October 8 / 19 | October 22 |
|---|---:|---:|
| City cells observed | 132,810,424 (99.25%) | 133,058,292 |
| Canopy at least 2 m (cells) | 34,748,843 | 34,044,344 (-2.0%) |
| Treetops in the city | 607,972 | **527,140** (-13.3%) |
| Treetops on private / public / no parcel / uncertain | 454,849 / 75,176 / 59,212 / 18,735 | 387,414 / 72,828 / 48,697 / 18,201 |
| Crowns (at least 3 m2) | not produced | **400,063** (826 ha; median 12.25 m2) |
| Footprints with a roof height | 21,415 | 21,562 |
| Footprints with a roof cell below terrain | 633 | 35 |
| Footprints with low roof support (< 80%) | 1,848 | 2,380 |

Treetops removed with no replacement nearby (92,668): 68% were flagged SUSPECT by the independent October 15 geometric
checks, against 6% of all treetops. 24,971 others moved by 1.5 m or less (the same tree). Building median heights hardly
change (86 footprints move more than 0.5 m); low-roof coverage is the cost, on footprints whose lower roofs only the native
classification saw. Details: [canopy-rebuild](canopy-rebuild/README.md), [roof-consensus](../2026-10-21/roof-consensus/README.md).

## Canopy cover by zone (cover.gdb, cover-comparison.csv)
`canopy.cover.summarize`, unchanged, on both canopies: canopy where the CHM is at least 2 m, as a share of observed cells;
the low and high bounds count unobserved cells as no canopy or as all canopy. Every zone is about 99.4% observed, so all are
PARTIAL and the observed share is the figure to use. Zones come from the 2025-tax-year parcel snapshot and the treetop
count's ownership rules; "No parcel" is the city outside every parcel, mostly streets.

| Zone | Acres | October 19 | **October 22** | Bounds | Canopy acres |
|---|---:|---:|---:|---:|---:|
| **Millcreek** | 8,266.5 | 26.16% | **25.59%** | 25.44-26.01% | 2,146.7 to 2,103.1 |
| Private parcels | 5,751.0 | 29.73% | 29.10% | 28.91-29.55% | 1,695.8 to 1,662.5 |
| Public / government | 838.9 | 25.24% | 24.91% | 24.82-25.20% | 210.4 to 208.2 |
| Uncertain owner | 206.3 | 19.94% | 19.59% | 19.51-19.89% | 40.8 to 40.3 |
| No parcel (streets, rights-of-way) | 1,470.4 | 13.66% | 13.12% | 13.07-13.46% | 199.7 to 192.1 |
| Salt Lake County | 536.1 | 29.31% | 29.08% | 28.97-29.33% | 156.0 to 155.3 |
| Public schools | 162.6 | 8.63% | 8.06% | 8.04-8.28% | 14.0 to 13.1 |
| Salt Lake City | 53.3 | 50.70% | 50.53% | 50.06-51.00% | 26.7 to 26.7 |
| Millcreek (city-owned) | 32.6 | 27.11% | 26.43% | 26.30-26.81% | 8.8 to 8.6 |
| Public districts | 31.2 | 7.07% | 6.87% | 6.85-7.12% | 2.2 to 2.1 |
| State of Utah | 13.8 | 12.61% | 11.48% | 11.42-11.89% | 1.7 to 1.6 |
| Public housing | 5.4 | 9.48% | 8.64% | 8.59-9.15% | 0.5 to 0.5 |
| Federal | 3.9 | 11.74% | 10.00% | 9.96-10.41% | 0.5 to 0.4 |

Cover falls by 0.2 to 1.7 points everywhere, as roof edges and structures leave the canopy; the city total is 0.58 points
lower. The first cover run crashed in ArcGIS's geometry engine (a Python union of 21,743 parcels); zones are now built with
the pairwise dissolve, clip and erase tools, and a second native crash was resumed cleanly (`--resume`).

## Limits
- Crowns come from a tiled version of the toolbox's crown method (`canopy.crowns.segment` in 950 m tiles with a 40 m halo,
  seeded by every detected peak), validated against the single-window method on three tiles including the densest (exact
  from a 20 m halo) and stable when rerun with an 80 m halo ([tiled-crowns](tiled-crowns/README.md)). They are estimated
  canopy regions, not surveyed crowns: a broad tree can hold several, a clump of small trees can form one; 127,077 treetops
  have a crown under 3 m2 (CROWN_TOO_SMALL in trees_review).
- Treetop evidence: the October 15 script was missing, so it was rebuilt from its manifest as `canopy/treetop_evidence.py`
  and proven to reproduce all 607,972 October 15 rows byte for byte, then run on the new treetops: 32,986 SUSPECT (6.3%,
  October 15: 15.1%) ([treetop-evidence](treetop-evidence/README.md)). Evidence for review, never labels.
- Treetops are lidar detections, not a stem census: low or suppressed trees can be missed, broad trees can have several
  peaks, and ownership uses the treetop cell and the 2025-tax-year parcel snapshot.
- The combined classification is model-assisted and provisional; the label figures above are training diagnostics on one
  tile. The workstation showed native crashes and one likely memory fault during this work; every result here completed and
  passed its checks on a clean run.
