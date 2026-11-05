# Candidate footprints from the LiDAR, with LiDAR heights (October 23, 2026)

Buildings the 2023 LiDAR sees that the county footprint layer lacks: clusters of consensus roof cells outside every county
footprint, outlined from the cells. Each carries the county footprints' roof-height statistics and empty review fields,
with a Web Mercator copy and LOD1.2 blocks ([lidar_candidates.py](lidar_candidates.py)). **These are unvalidated planning
estimates, not surveyed or field-verified data. Heights are roof minus terrain from 2023 LiDAR, not code-defined building
heights, and no candidate has been reviewed.** Nothing was uploaded or shared, and no county or city data was edited.

Brian decided on October 23 (as relayed by the Overture comparison session) to "detect and outline candidates from the LiDAR roof clusters outside county footprints, and
use the 1,264 Overture outlines only as a comparison afterwards, so the layer isn't ODbL-derived". The first version,
built from those Overture outlines, is kept as a review comparison only: [OVERTURE_VERSION.md](OVERTURE_VERSION.md).

Output: `H:\lidar\2023-salt-lake-valley\runs\footprint-candidates-lidar-20261023` (EPSG 6341 unless stated; elevations
NAVD88).

| File | Meaning |
|---|---|
| candidates.gdb/candidates | **6,213 candidate outlines** with roof statistics, nearest county footprint, parcel and empty review fields |
| web.gdb/candidates | The same in Web Mercator (EPSG 3857), with the REVIEW_STATUS domain, for a staff-only layer later |
| massing/massing.gdb/lod12 | 6,233 LOD1.2 blocks for the 6,213 candidates (FP_ID = the candidate's OBJECTID) |
| clusters.tif | Candidate number per 0.5 m cell (CAND_ID LC00001 = 1) |
| stage.tif | Every roof cell's fate: 1 on or within 1.5 m of a county footprint, 2 removed by the opening, 3 in a cluster under 10 m², 4 in a cluster with a median under 2 m, 5 candidate |
| witness.gdb (pairs, overture_missed), witness.json | The comparison with Overture, afterwards and apart from the layer |
| detect-pilot/, massing-pilot/, view0-2.png | The 12TVL2804 detection pilot, the 20-block massing pilot, and pilot maps |
| candidates.json, method-check.json, massing/massing.json | Run records; copies in [lidar/](lidar/) |

## Not derived from Overture
`detect` reads only the library's `roof_height_m.tif`, `observed.tif`, `roof_elevation_m.tif` and `terrain_m.tif`, the
county footprints (`buildings.gdb/building_heights`), the city boundary and, for context fields, the 2025-tax-year
parcels. Every threshold below was fixed from the county footprints and the LiDAR before the comparison ran, and none was
changed after it. Overture is read only by `witness`, which writes to its own `witness.gdb` and `witness.json`. The
candidate layer and its web copy hold no Overture geometry, id or attribute. The layer is built on County data (the
footprints and the 2023 LiDAR), whose own terms apply; those weren't reviewed here.

## Method
1. **Roof cells:** cells where `roof_height_m.tif` has a value (the 2-of-3 consensus roof) inside the city.
2. **Outside the county footprints:** cells whose centre is more than 1.5 m from every county footprint cell (footprints
   rasterized at cell centres, as building_heights counts them). The cut is set by the eave band seen in county data. Of
   the cells just outside the footprints, the share that is roof falls fast and then levels off (the cut removes everything up to and including 1.5 m):

   | Distance from a county footprint (cell centres) | 0.5-1 m | 1-1.5 m | 1.5-2 m | 2-2.5 m | 2.5-3 m | 5-7.5 m | over 10 m |
   |---|---:|---:|---:|---:|---:|---:|---:|
   | Cells that are roof | 62% | 23% | 8.3% | 4.9% | 3.6% | 2.0% | 1.2% |

3. **Opening and clusters:** a 3 × 3 opening removes strips narrower than 1.5 m (fence tops, eave remnants). Clusters are
   8-connected.
4. **Kept:** at least 40 cells (10 m²; the county footprints' 1st percentile is 12 m²) and a median roof height of at least
   2.0 m (the 1st percentile of county footprints under 40 m² is 2.2 m). Of 9,644 clusters, 3,404 are under 10 m² and 27
   too low.
5. **Outline:** the cluster's cell edges (Raster To Polygon, unsimplified), regularized by Regularize Building Footprint
   (right angles and diagonals, 0.75 m tolerance, 0.75 m densification, 0.25 m precision). 6,201 regularized; for 12 the
   tool failed and the cell outline is kept (OUTLINE = CELL_EDGES). Median outline-to-cluster area ratio 1.00 (5th-95th
   percentile 0.93-1.07).
6. **Heights and context:** the helpers in [footprint_candidates.py](footprint_candidates.py), shared with the Overture
   version. Roof statistics come from `summarize()` in the October 19
   [summarize_city_buildings.py](../../2026-10-19/summarize_city_buildings.py), the code that made `building_heights`, on
   the stored outlines: FOOTPRINT_M2, AOI_PCT, ROOF_COV_PCT, ROOF_Z50_M, GROUND_Z50_M, HEIGHT_P50_M, HEIGHT_P95_M,
   HEIGHT_MAX_M, GRID_CELLS, ROOF_CELLS, NEG_H_CELLS, PARTIAL_AOI, HEIGHT_STATUS. The context fields are
   NEAR_FP_SOURCE_ID, NEAR_FP_DIST_M, NEAR_FP_PARCEL_ID, PARCEL_ID, PARCEL_ADDRESS and SAME_PARCEL. The layer also carries
   CAND_ID, CLUSTER_CELLS, CLUSTER_M2, CLUSTER_H50_M, OUTLINE and SIZE_CLASS.
7. **Review fields** (empty): REVIEW_STATUS with the coded domain REVIEW_STATUS (ACCEPT, REJECT, UNSURE), REVIEW_NOTE,
   REVIEWER.
8. **Web copy and blocks:** `web()` and `massing()` from footprint_candidates.py: the October 22 feature-layer projection
   with its vertex check, and the October 22 massing method at LOD1.2 with its empty-block cleanup.

## Checks
- **Method check:** the zonal code reproduces `building_heights` exactly on all 13 fields for 2,000 random county
  footprints. The check ran once at 11:33 on the same code and rasters, and its record is reused here
  (`method-check.json`). The October 19 rasterization pilot also ran on 14 candidates: the NumPy cell-centre mask equals
  ArcGIS CELL_CENTER on all 14.
- **Pilot first:** detection on 12TVL2804 gave 138 candidates; [pilot-view-12TVL2804.png](lidar/pilot-view-12TVL2804.png)
  is one of the maps checked before the citywide run. The candidates are mostly detached backyard structures, some
  additions against houses, and a few eave or porch strips just past the 1.5 m cut.
- **Counts:** 6,213 clusters, 6,213 outlines, 6,213 projected, 6,213 with a block. Every candidate has a height (one has
  LOW_ROOF_SUPPORT, 9 NEGATIVE_HEIGHT, 2 PARTIAL_AOI).
- **No outline touches a county footprint**, regularization included.
- **Web copy:** no attribute differences or vertex-count mismatches. The largest distance from Esri's own ITRF08
  projection is 0.07 mm, against at least 1.58 m untransformed. The domain is in web.gdb and assigned to the field. The
  warning is in the metadata of both layers and the blocks.

## What the candidates are
The median outline is 24 m² and the median P95 height 3.1 m.

| Size | n | P95 under 3 m | 3-4.5 m | 4.5-6 m | 6-9 m | 9 m and over | Within 2 m of a county footprint | More than 5 m | Same parcel as nearest county building |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| under 20 m² | 2,357 | 1,161 | 997 | 139 | 48 | 12 | 1,727 | 424 | 1,746 |
| 20-40 m² | 2,019 | 760 | 1,070 | 114 | 59 | 16 | 1,250 | 467 | 1,394 |
| 40-80 m² | 807 | 278 | 369 | 85 | 64 | 11 | 453 | 194 | 520 |
| 80-150 m² | 431 | 194 | 97 | 73 | 51 | 16 | 169 | 157 | 257 |
| 150-300 m² | 359 | 169 | 52 | 27 | 78 | 33 | 105 | 156 | 161 |
| 300 m² and over | 240 | 48 | 30 | 21 | 61 | 80 | 71 | 131 | 72 |
| **All** | **6,213** | 2,610 | 2,615 | 459 | 361 | 168 | 3,775 | 1,529 | 4,150 |

- **Sheds, garages and carports: about 4,600.** 4,635 candidates are under 80 m² and under 4.5 m (P95), and most share a
  parcel with the nearest county building.
- **Against a house: 3,775 lie within 2 m of a county footprint.** These are additions, attached garages, covered
  patios and porches the county outline leaves out, plus some eave or porch strips just past the cut. They are the
  likeliest REJECTs, and filtering NEAR_FP_DIST_M > 2 leaves 2,438 detached candidates.
- **Large and tall: 252** are 150 m² or more with a P95 of at least 6 m, the buildings the county layer most likely lacks
  because they are newer. The largest is 7,220 m² and 23 m high.

## Witness: against the 1,264 Overture outlines (afterwards)
Found by both when the overlap is at least 30% of either outline (`witness.json`; pairs in `witness.gdb/pairs`).

| | n |
|---|---:|
| Overture outlines found by a LiDAR candidate | **1,242 of 1,264** (median IoU 0.76) |
| LiDAR candidates that match an Overture outline | 1,191 |
| LiDAR only | 5,022 |
| Overture only | 22 |

- **The LiDAR finds 98% of what Overture had.** The 22 it misses are all small (11-29 m², median 15 m²): 13 are roof
  within 1.5 m of a county footprint, 7 are clusters under 10 m², and 2 were removed by the opening
  (`witness.gdb/overture_missed`, with each one's share of cells at every stage).
- **The witness checks the method; it does not pick candidates.** Don't ACCEPT or REJECT a candidate because Overture
  has or lacks it: that would bring back the dependency this layer avoids. Review against imagery and the LiDAR.
- **49 LiDAR candidates each cover 2 to 6 Overture outlines:** touching structures merge into one roof cluster, such as
  townhouse rows and garages built wall to wall. Reviewers may want to split them.
- **5,022 candidates are LiDAR only.** 3,432 of them lie within 2 m of a county footprint (Overture rarely draws
  additions or porches separately), and 4,202 are under 40 m² (sheds Overture lacks). 1,022 are detached buildings more
  than 5 m from any county footprint that neither source has.

## Blocks (LOD1.2)
| | Pilot (20) | All (6,213) |
|---|---:|---:|
| Features from the tool | 20 | 6,240 |
| Empty features removed | 0 | 7 |
| Candidates without a block | 0 | 0 |
| Top minus median roof (m): p5 / median / p95 | -0.06 / -0.01 / 0.00 | -0.10 / -0.01 / 0.00 |
| Base minus lowest terrain (m): p5 / median / p95 | -0.72 / -0.08 / +0.03 | -0.77 / -0.09 / +0.02 |
| Bases more than 2 m above the lowest terrain | 0 | 0 |

The 20 extra blocks belong to 19 multipart outlines (25 candidates are multipart, mostly clusters joined only at a
corner), one block per part. Seven tops are more than 1 m below the median roof (listed in `massing.json`).

## Limits
- Anything at least 10 m² and 2 m high that the consensus calls roof is a candidate. That includes trailers, RVs, box
  trucks and the occasional tree the consensus mistakes for roof (2.8% of non-roof parts were called roof on the
  labelled tile). Review decides.
- Buildings built after the October-November 2023 flight aren't there, and ones removed since still are.
- Regularized outlines are LiDAR estimates of the roof edge (eaves included), not wall lines.
- The thresholds are a first setting from county data. A 2 m attached-cut or a larger minimum area would shrink the
  review load, but that is Brian's call: it wasn't tuned against Overture, and it shouldn't be.

## Licences
The layer, its web copy and its blocks contain no Overture data, so ODbL doesn't attach to them. Publishing them is a
question of the County's terms for the footprints and LiDAR. `witness.gdb` and `witness.json` hold Overture ids and
measures and belong with the ODbL comparison material: keep them out of anything published. The Overture-based version and
its terms are in [OVERTURE_VERSION.md](OVERTURE_VERSION.md) and `Z:\GIS\overture\2026-10-21.0\millcreek\LICENSES.md`.

## Next
- Field Maps review: publish web.gdb/candidates as a **staff-only** hosted feature layer, editing limited to the three
  review fields, only on Brian's word, through `reviews/2026-10-22/hosting/upload/upload.py` (one item, `--go`). Detached
  candidates and the 252 large tall ones first.
- After review, ACCEPT outlines can go to the County as missing buildings, drawn from the LiDAR.
- A scene layer package of the blocks would follow the [scene-layers](../../2026-10-22/hosting/scene-layers/README.md)
  steps.

## Rerun
From `canopy-toolbox`, with ArcGIS Pro's `millcreek-py3` env, `PYTHONNOUSERSITE=1` and `-I`:

```
python -I reviews/2026-10-23/footprint-candidates/lidar_candidates.py detect OUT --pilot
python -I reviews/2026-10-23/footprint-candidates/lidar_candidates.py detect OUT
python -I reviews/2026-10-23/footprint-candidates/lidar_candidates.py web OUT
python -I reviews/2026-10-23/footprint-candidates/lidar_candidates.py pilot OUT
python -I reviews/2026-10-23/footprint-candidates/lidar_candidates.py massing OUT
python -I reviews/2026-10-23/footprint-candidates/lidar_candidates.py witness OUT
```

`detect` reuses OUT\method-check.json when present (otherwise it runs the check) and refuses to compute anything if the
check is not exact.
