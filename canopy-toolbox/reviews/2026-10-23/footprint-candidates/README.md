# Candidate footprints from Overture, with LiDAR heights (October 23, 2026)

Overture Maps buildings that sit on a 2023 LiDAR roof but match no county footprint, made into a reviewable layer with the
county footprints' roof-height statistics, a Web Mercator copy and LOD1.2 blocks
([footprint_candidates.py](footprint_candidates.py)). Brian approved the layer on October 23 after the Overture vs LiDAR
comparison (`Z:\GIS\overture\2026-10-21.0\millcreek\lidar-compare\README.md`). **These are unvalidated planning estimates, not surveyed or
field-verified data. Heights are roof minus terrain from 2023 LiDAR, not code-defined building heights, and none of these
outlines has been reviewed.** Nothing was uploaded or shared, and no county or city data was edited.

Output: `H:\lidar\2023-salt-lake-valley\runs\footprint-candidates-20261023` (EPSG 6341 unless stated; elevations NAVD88).

| File | Meaning |
|---|---|
| candidates.gdb/candidates | **1,264 candidate outlines** with roof statistics, nearest county footprint, parcel and empty review fields |
| web.gdb/candidates | The same in Web Mercator (EPSG 3857), with the REVIEW_STATUS domain, for a staff-only layer later |
| massing/massing.gdb/lod12 | 1,265 LOD1.2 blocks for the 1,264 candidates (FP_ID = the candidate's OBJECTID) |
| massing-pilot/ | The 20-candidate pilot |
| candidates.json, method-check.json, massing/massing.json | Run records; copies here, with massing-pilot.json |
| superseded/ | Two earlier passes of this run (see Method); not for use |

## 1,264, not 1,219
The comparison was rerun at 11:31 the same day. Its first run projected Overture's WGS84 outlines with GeoPandas, whose
default for this pair is a null transformation, leaving every outline 1.2 m west-northwest of the LiDAR and the county
footprints. Projected with `WGS_1984_(ITRF08)_To_NAD_1983_2011`, as the county footprints and every hosted package are,
1,264 Overture-only buildings sit on a LiDAR roof. The comparison's README says to use only the rerun's files, so this
layer is the 1,264. Its outlines are projected here the same way from `buildings.parquet`, and they equal the comparison's
outlines exactly (Hausdorff distance 0 on all 1,264).

## Method
- **Selection:** `overture_vs_lidar.gpkg / overture_buildings` where MATCH = OVERTURE_ONLY (no county footprint covers
  10% of the outline) and LIDAR = ROOF (at least 50% of the outline's cells are consensus roof), by Overture id.
- **Roof statistics:** `summarize()` from [summarize_city_buildings.py](../../2026-10-19/summarize_city_buildings.py), the
  code that made `buildings.gdb/building_heights`, run unchanged on the library's `roof_elevation_m.tif` and
  `terrain_m.tif` and clipped to the same municipal boundary. Every candidate carries the full `building_heights` set:
  FOOTPRINT_M2, AOI_PCT, ROOF_COV_PCT, ROOF_Z50_M, GROUND_Z50_M, HEIGHT_P50_M, HEIGHT_P95_M, HEIGHT_MAX_M, GRID_CELLS,
  ROOF_CELLS, NEG_H_CELLS, PARTIAL_AOI, HEIGHT_STATUS.
- **Overture fields:** OVERTURE_ID, SOURCES (OSM, Microsoft ML, OSM + Microsoft ML; Esri Community Maps would be its own
  value, but none of the 1,264 are Esri), SOURCE_DATASETS (Overture's own string), OSM_RECORD (the OSM way or relation),
  OV_CLASS, OV_SUBTYPE, OV_HEIGHT_M (Microsoft's ML estimate; the comparison found it unreliable above one storey), and
  SIZE_CLASS.
- **Context:** NEAR_FP_SOURCE_ID, NEAR_FP_DIST_M and NEAR_FP_PARCEL_ID are the nearest county footprint (planar, edge to
  edge). PARCEL_ID and PARCEL_ADDRESS are the parcel holding most of the outline, from the 2025-tax-year snapshot
  `city-count-20261008\inputs.gdb\parcels`. That snapshot was projected with the ITRF00 transformation, not ITRF08, a
  difference of 6 mm here. Owner names are left out. SAME_PARCEL says whether the parcel matches the nearest
  county footprint's. The county ADDRESS field is filled on only 82 footprints, so the parcel address is used instead.
- **Review fields** (empty): REVIEW_STATUS with the coded domain REVIEW_STATUS (ACCEPT, REJECT, UNSURE), REVIEW_NOTE
  (500 characters), REVIEWER.
- **Web copy:** `project()` and `projection_check()` from the October 22
  [prepare_features.py](../../2026-10-22/hosting/feature-layers/prepare_features.py), imported unchanged.
- **Blocks:** the October 22 [massing method](../../2026-10-22/massing/README.md): Extract LOD2 Buildings at LOD1.2 on the
  consensus roof elevation, with the unmasked terrain elsewhere. Its helpers (`terrain_min`, `annotate`, `summary`) are
  imported from run_massing.py, and its empty-block cleanup is repeated. The height source covers only the candidates'
  extent plus 50 m.

The statistics are computed on the outlines as stored in the geodatabase, as `building_heights` was. A first pass used the
unsnapped in-memory shapes: their clip to the city boundary differed by a sliver, and 402 were flagged PARTIAL_AOI
against 1 now (`superseded/candidates-unsnapped.*`). A second pass is kept in `superseded/first-pass`. It was identical
apart from carrying the empty county ADDRESS instead of the parcel address.

## Checks
- **Method check (before any candidate figure):** the zonal code was rerun on 2,000 random county footprints (seed 1).
  All 13 fields equal `building_heights` exactly on every one, GRID_CELLS included, and ROOF_Z50_M and GROUND_Z50_M on
  the 1,945 with a roof (`method-check.json`). Two of the sample cross the city boundary (PARTIAL_AOI). The comparison's
  own rasterio check could not show this: it missed GRID_CELLS on 3 of 2,000 and has no elevation medians.
- **Rasterization pilot:** the October 19 script's own pilot ran on 13 candidates (12 spread by size, plus the one that
  crosses the boundary). Its NumPy cell-centre mask equals ArcGIS PolygonToRaster CELL_CENTER on all 13.
- **Cross-check with the comparison:** ROOF_COV_PCT here equals the comparison's L_ROOF_COV_PCT on all 1,264 (largest
  difference 0.0 points).
- **Counts:** 1,264 selected, 1,264 written, 1,264 projected, 1,264 with a block.
- **Boundary:** county footprints were kept when they touch the city, so only a candidate crossing the boundary could hide
  a county footprint that lies wholly outside the city. One candidate crosses (89.8% inside), and none of the county's
  26,915 footprints outside the city overlaps it.
- **Web copy:** 1,264 features, no attribute differences, no vertex-count mismatches. The largest vertex distance from
  Esri's own projection of the source with the ITRF08 transformation is 0.07 mm, against at least 1.58 m from the
  untransformed projection. The REVIEW_STATUS domain is in web.gdb and assigned to the field. The warning is in the
  metadata of both layers and of the blocks.

## What the candidates are
Every candidate has a height: none falls below 50% roof cover, and 155 are below 80% (LOW_ROOF_SUPPORT). The median
outline is 90 m² and the median P95 height 3.2 m. 540 come from Microsoft ML only, 437 from OSM and Microsoft together,
and 287 from OSM only.

Overture classes only 186 of them, so size and LiDAR height are the better guide:

| Size | n | P95 under 3 m | 3-4.5 m | 4.5-6 m | 6-9 m | 9 m and over | Same parcel as nearest county building |
|---|---:|---:|---:|---:|---:|---:|---:|
| under 20 m² | 55 | 24 | 25 | 4 | 1 | 1 | 43 |
| 20-40 m² | 176 | 70 | 96 | 7 | 2 | 1 | 116 |
| 40-80 m² | 326 | 140 | 134 | 42 | 3 | 7 | 175 |
| 80-150 m² | 321 | 144 | 44 | 29 | 62 | 42 | 153 |
| 150-300 m² | 249 | 133 | 33 | 15 | 49 | 19 | 104 |
| 300 m² and over | 137 | 37 | 8 | 12 | 29 | 51 | 33 |
| **All** | **1,264** | 548 | 340 | 109 | 146 | 121 | 624 (627 not, 13 unknown) |

- **Sheds, garages and carports: about 490.** 489 candidates are under 80 m² and under 4.5 m (P95). Of the 557 under
  80 m², 334 share a parcel with the nearest county building, as an outbuilding would. The 548 under 3 m include low
  carports and shade structures at every size.
- **Overture's own classes** agree where they exist: 38 carports (34 under 3 m), 9 parking (covered parking, all under
  3 m), 4 garages, 1 shed, 5 roofs and 4 shelters; 53 more carry the subtype outbuilding.
- **Not outbuildings: 148 large, tall buildings** (150 m² or more and P95 at least 6 m), mostly OSM + Microsoft (128).
  Overture classes 43 of them: 24 terraces (townhouse rows), 9 detached, 4 apartments, 2 houses, a sports centre and
  others. The largest is a 6,403 m² apartment building 23 m high, 4.5 m from the nearest county footprint. These are
  most likely buildings newer than the county layer, or places where it is incomplete. **They are the ones to review
  first.** Another 104 are house-sized (80-150 m²) and at least 6 m tall, two storeys rather than a shed; Overture's 27
  semidetached houses (all 80-150 m² and 6-9 m) are among them.
- Distance to the nearest county footprint: median 4.6 m; 113 touch one (under 0.5 m) and 248 are more than 10 m away.

## Blocks (LOD1.2)
| | Pilot (20) | All (1,264) |
|---|---:|---:|
| Features from the tool | 20 | 1,265 |
| Empty features removed | 0 | 0 |
| Candidates without a block | 0 | 0 |
| Top minus median roof (m): p5 / median / p95 | -0.14 / -0.02 / 0.00 | -0.25 / -0.01 / 0.00 |
| Base minus lowest terrain (m): p5 / median / p95 | -0.37 / -0.09 / +0.01 | -0.60 / -0.09 / +0.02 |
| Bases more than 2 m above the lowest terrain | 0 | 0 |

These match the county blocks of October 22: tops follow the median roof, and bases sit just below the ground.
- Candidate 564 (714 m², OSM + Microsoft) is a two-part outline and gets one block per part, which is correct.
- Four tops are more than 1 m below the median roof: FP_ID 333, 566 and 594 have 52-70% roof support, and FP_ID 383 has
  98%. Of the 761 candidates with 95% or more support, only 383 is off by more than 1 m.

## Licences: what this means for publishing
From `Z:\GIS\overture\2026-10-21.0\millcreek\LICENSES.md` (written the same day; a working summary, not legal advice).
- **Every outline here is ODbL.** The Overture buildings theme is ODbL, and so are both sources these candidates come
  from: OpenStreetMap and Microsoft ML Buildings. The share-alike terms therefore cover all 1,264, not only the
  OSM-derived ones. The LiDAR figures attached to them are the County's measurements, not Overture's.
- **A staff-only review layer** is not public use, so ODbL's share-alike terms aren't triggered. Credit
  "© OpenStreetMap contributors, Overture Maps Foundation" on it anyway.
- **A public map, image or scene of them** is a Produced Work: the attribution line plus a notice that the data is ODbL.
- **A public queryable or downloadable layer** of the candidates, or of the blocks massed from them, is a database
  derived from ODbL data. It would have to be offered under ODbL.
- **Accepted candidates going into a City or County footprint layer:** copying the Overture outline makes that layer, or
  that part of it, a Derivative Database if it is published as data. Redrawing the building from imagery or the LiDAR
  roof, with Overture used only to find it, does not. Anything published as data should go to the City Attorney first,
  as LICENSES.md says.

## Next
- Field Maps review: publish web.gdb/candidates as a **staff-only** hosted feature layer with editing limited to the three
  review fields, only on Brian's word, through `reviews/2026-10-22/hosting/upload/upload.py` (one item, `--go`).
- After review, ACCEPT outlines can be passed to the County as missing buildings. How they are drawn decides the licence
  (see above).
- A scene layer package of the blocks would follow the [scene-layers](../../2026-10-22/hosting/scene-layers/README.md)
  steps. Under the same licence terms, keep it staff-only unless the City Attorney agrees otherwise.

## Rerun
From `canopy-toolbox`, with ArcGIS Pro's `millcreek-py3` env, `PYTHONNOUSERSITE=1` and `-I`:

```
python -I reviews/2026-10-23/footprint-candidates/footprint_candidates.py check OUT
python -I reviews/2026-10-23/footprint-candidates/footprint_candidates.py build OUT
python -I reviews/2026-10-23/footprint-candidates/footprint_candidates.py web OUT
python -I reviews/2026-10-23/footprint-candidates/footprint_candidates.py pilot OUT
python -I reviews/2026-10-23/footprint-candidates/footprint_candidates.py massing OUT
```

`build` reuses OUT\method-check.json when present and refuses to compute anything if it is not exact.
