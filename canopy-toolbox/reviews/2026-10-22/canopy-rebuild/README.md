# Canopy rebuilt from the combined classification (October 22, 2026)

Brian's order on October 21 was roofs first, then canopy; on October 22 he said go ahead, with points classed 1 (other) and 64
(permanent structure) counting as observed non-canopy. Nothing here replaces an October product: the outputs sit beside
October 19's for review. Treetops and crowns are not re-detected until Brian has reviewed this comparison.

## The combined class (canopy_rebuild.py)
Per point of the October 8 working LAS: **building** where the roof consensus says so (2 of 3: native, FRACTAL's three-pass
majority, Esri; [../../2026-10-21/roof-consensus](../../2026-10-21/roof-consensus/README.md)); otherwise the **rules-v2 class**
(`runs\refined-fractal-20261020\points`), except where rules v2 says building and the consensus does not, where the native
class (or FRACTAL's majority if the native class is the building) is used. Saved per tile as `classes\<tile>.npy` (uint8, in
working-LAS point order) for LAS copies later.

## Method and its proof
`canopy.rasters.build_chm` as the October 8 count ran it (building clearance 0.35 m, classified background off), from first
and single returns without withheld, overlap or synthetic points, on the October 19 city grid with the ArcGIS edge rule,
against the October 19 terrain (not rebuilt). The same pass builds a "native" version from the October 8 classes:
**it reproduces October 19's chm_m.tif, observed.tif, vegetation_support.tif and building_occlusion.tif on all 133,813,488
city cells, with no difference**, and gives the October 8 count's 34,748,843 canopy cells. Only then is the combined version
trusted.

Outputs in `D:\lidar\2023-salt-lake-valley\runs\canopy-rebuild-20261022`: `chm_m.tif`, `observed.tif`,
`vegetation_support.tif`, `building_occlusion.tif` (October 19 encodings), `classes\`, `canopy_change.tif`,
`treetops-canopy.csv`, `manifest.json`, `comparison.json`. `work\` (about 5 GB of working arrays) can be deleted.

## Comparison (compare_canopy.py; [comparison.json](comparison.json))
| City cells | October 19 | Rebuilt |
|---|---:|---:|
| Observed | 132,810,424 | 133,058,292 |
| Canopy at least 2 m | 34,748,843 | **34,044,344** (-2.0%) |
| Building occludes vegetation | 390,491 | 315,073 |
| Vegetation support (any height) | 103,427,084 | 43,952,772 |

Canopy at least 2 m: 33,679,482 cells in both, 1,069,361 lost, 364,862 gained (`canopy_change.tif`: 1 both, 2 lost, 3
gained). Gains are mostly branches over roofs that the native class had called roof. Vegetation support falls by more than
half because rules v2 moves the bare surface the October 8 height classification had put in "low vegetation" to ground; that
is below 2 m and does not change canopy.

**October 8 treetops** (607,972; `treetops-canopy.csv`):

| In the rebuilt canopy | Treetops | Flagged SUSPECT on October 15 |
|---|---:|---:|
| KEPT (CHM at least 2 m) | 520,225 | 32,459 (6.2%) |
| BUILDING (a consensus roof occludes the cell) | 11,440 | 10,919 (95%) |
| NO_VEGETATION (no vegetation point left in the cell) | 74,037 | 48,131 (65%) |
| LOWER (vegetation under 2 m) | 2,270 | 298 (13%) |

87,747 treetops (14.4%) would no longer stand; 67.6% of them carry the independent October 15 SUSPECT flag, against 6.2% of
those kept. These are candidates, not removals: the count changes only when treetops are re-detected on the new canopy.

**Labels on 12TVL2804** (a part is vegetation when most of its clean points are class 3, 4 or 5):

| | Native (October 8) | Rules v2 | Combined |
|---|---:|---:|---:|
| Tree parts called vegetation (270) | 240 (88.9%) | 257 (95.2%) | **259 (95.9%)** |
| Shrub parts (85) | 73 (85.9%) | 64 (75.3%) | 65 (76.5%) |
| Other parts called vegetation (862) | 355 (41.2%) | 82 (9.5%) | 92 (10.7%) |

Trees improve; "other" called vegetation falls from 41% (mostly ground in class 3) to 11%. Shrubs get worse: rules v2 moves
some shrub points to ground. That hardly touches canopy at 2 m but matters if low vegetation is ever reported.

## Treetop count on the rebuilt canopy (count_rebuilt.py; [count-summary.json](count-summary.json))
Brian said go ahead on October 22. The October 8 method exactly: one canonical CHM of the city and a 20 m margin on its 63
planned 950 m raster cores, `count_peaks.detect` with the default bands (2-6 m: 1 m radius; 6-12: 1.5; 12-20: 2; 20+: 2.5;
smoothing one cell), peaks clipped to the municipal boundary, ownership from the same 2025-tax-year parcel snapshot. The
detector, bands, ownership and raster code are unchanged since October 8 (SHA-256 checked), and **the native canonical CHM
equals October 8's canonical-chm.bin on every cell** (a first attempt without the core footprint differed in 10.15 M cells,
all outside the cores; kept as `city-count-20261022.failed-1`). Outputs in `runs\city-count-20261022`: `tree-count.gdb\city_treetops`
and `city-treetops.csv` (OCT8 = SAME_CELL or NEW; a same-cell treetop keeps its October 8 TREE_ID), `treetop-changes.csv`.

| | October 8 | Rebuilt |
|---|---:|---:|
| **Treetops in the city** | 607,972 | **527,140** (-13.3%) |
| Private | 454,849 | 387,414 |
| Public / government | 75,176 | 72,828 (Salt Lake County 61,295; Salt Lake City 4,805; schools 3,688; Millcreek 1,593) |
| No matching parcel | 59,212 | 48,697 |
| Uncertain owner | 18,735 | 18,201 |

490,333 treetops are at the same cell. Of the 117,639 removed, 24,971 have a new treetop within 1.5 m (the same tree, its top
cell moved) and 92,668 have none; **68.0% of those 92,668 carry the October 15 SUSPECT flag** (6% of treetops overall).
12,384 added treetops have no removed one within 1.5 m (mostly canopy over roofs that the native class had masked).
Checked: 527,140 unique TREE_IDs, all at least 2 m, CSV and feature class equal.

## Crown pilot on 12TVL2804 (crowns_pilot.py; [crowns-pilot-12TVL2804.json](crowns-pilot-12TVL2804.json))
Crown delineation is bounded to 4,000,000 cells (AGENTS.md), so it is not run citywide: that needs a new tiled method,
validated first. One 1 km tile is exactly 4,000,000 cells. `canopy.crowns.delineate` (minimum height 2 m, minimum crown
3 m2) on 12TVL2804 for both canopies, in `runs\crowns-pilot-20261022\crowns.gdb` (oct8_ and rebuilt_ crowns, trees_review,
treetops); crowns at the tile edge are partial.

| 12TVL2804 | October 8 | Rebuilt |
|---|---:|---:|
| Treetops | 14,578 | 11,701 |
| Crowns (at least 3 m2) | 9,719 | 9,083 |
| Treetops whose crown is under 3 m2 | 4,859 | 2,618 |
| Crown area | 234,600 m2 | 232,180 m2 |
| Median crown | 14.0 m2 | 15.5 m2 |

Most of the drop is treetops with too small a crown (-46%); estimated crowns fall 6.5% and crown area 1%. The rebuild
removes mostly spurious peaks (roof edges, structures), not canopy.

## Next
1. Brian reviews in Pro: the new `city_treetops` beside October 8's (OCT8 field), `treetop-changes.csv`, `canopy_change.tif`
   and the 12TVL2804 crowns.
2. His decisions: whether the rebuilt count (527,140) and the consensus building layer replace the October products; whether
   to build and validate a tiled crown method for citywide crowns; cover by zone on the rebuilt canopy (canopy/cover.py).
