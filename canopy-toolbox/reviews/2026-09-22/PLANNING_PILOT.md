# Millcreek LiDAR planning pilot — September 22, 2026

The expanded workflow completed on a **300 × 300 m Millcreek sample**, producing **25 rasters, building-height polygons, and contours** (27 planning datasets). Separate outputs contain tree candidates, crowns, review points, canopy-cover accounting, and a delivery-wide LAS index. All results remain **unvalidated planning estimates**.

[View the overview map](../../scratch/planning_20260922/planning-overview.png) · [Product catalog, methods, and next datasets](../../PLANNING_PRODUCTS.md) · [Preliminary imagery QA](IMAGERY_QA.md)

## Correction, added 2026-09-22 after the delivery metadata arrived

This report was written before the USGS and Aero-Graphics delivery documents were available.
Two inputs recorded below from recollection are wrong, and the results should be read with the
corrected values. Nothing in the processing, counts, or measurements changes.

- The lidar was collected **7 October to 5 November 2023**, not in 2024. The pilot tile 12TVL2804
  was flown 2023-11-02 and 2023-11-04.
- Nominal pulse spacing is **0.32 m**, not 0.5 m, with a measured first-return average of 18.2
  points per square metre. The 0.5 m figure is the raster cell size used here.
- Vertical accuracy is no longer unknown: tested point-cloud NVA RMSEz is **5.87 cm**.
- Because the collection is late-autumn, the canopy figures below are season-limited and are
  likely low for deciduous cover.

Full detail, per-tile flight dates, delivered classes, and coverage gaps are in
[delivery provenance](../../acquisitions/2023-salt-lake-valley/RECORD.md). The delivery indexer moved into the toolbox
as `canopy index-delivery` at the same time; the suite is now **74 tests, all passing in Pro
3.7.2** ([log](full-tests-after-provenance.txt)), up from the 62 recorded below.

## What changed since the previous task

The September 17 footprint review showed that the earlier commercial-roof pilot was in Taylorsville. It remains useful for that failure mode, but it is not a Millcreek canopy sample. This run uses a new area with 115 intersecting county footprints; all carry CITY = MILLCREEK.

A new canopy planning command builds the terrain, surface, drainage, and footprint-height bundle from a completed preparation. It preserves inputs, refuses existing output folders, records processing provenance, and reports incomplete observations. The existing tree algorithms and the root AGOL/GNSS utilities were retained.

This pilot uses the existing building classifier and height classes on a new LAS copy. Experimental low-slope roof-plane refinement from the commercial pilot was **not applied** to the new sample. Classification, especially roof edges and trees touching roofs, still needs independent review.

## Inputs and scope

- Original delivery: G:\GIS\2024 Lidar for tower extract.
- **52 LAS files; 1,269,149,276 points; 38.07 GB** in decimal units.
- Source header bounds: 422000–434999.99 E, 4501000–4507999.99 N. Their bounding rectangle does not imply uninterrupted delivery coverage.
- Capture year **2024** and nominal point spacing **0.5 m** were confirmed by the user. Exact flight date/season and validated vertical accuracy remain unknown here. **Superseded — see the correction above.**
- Source coordinate reference: NAD83(2011) / UTM zone 12N, with NAVD88 height / Geoid18, metres, as declared in the LAS.
- New prepared copy: one source tile, 12TVL2804, clipped to 428075 4504075 428425 4504425 (350 m square).
- Analysis grid: **428100 4504100 428400 4504400**, 600 × 600 cells at 0.5 m (9 hectares / 22.24 acres).
- County footprints: [SLCo BuildingFootprints](https://services1.arcgis.com/DJP723NX3ukQ2LtF/arcgis/rest/services/SLCo_BuildingFootprints/FeatureServer/0), downloaded by IDs in bounded batches with completeness checks, projected by the service to EPSG:6341, and preserved locally.
- No matched-date imagery, independent building heights, or field-tree reference sample was used to establish accuracy.

The copied LAS contains 1,824,463 points: 285,194 ground, 346,212 building, 1,178,423 combined height-based vegetation classes, 13,904 unclassified, and 730 noise points. Height-based vegetation labels are candidate classes, not verified botanical classifications. Preparation verified source file size/mtime remained unchanged.

## Building heights

All **115** footprints received paired class-6 roof/terrain height statistics. Footprint geometry and original identifiers are preserved.

| Result | Count / value |
|---|---:|
| Footprints with a height estimate | 115 |
| Partial footprints crossing the analysis boundary | 20 |
| Roof support below the 80% review threshold | 13 |
| Footprints containing negative roof-minus-ground cells | 2 |
| Range of per-building 95th-percentile heights | 2.50–10.25 m |

Flags overlap. Every record remains UNVALIDATED. Percentiles describe roof-cell maxima minus interpolated ground at the same cell centers, not a legal building height.

The two negative-height cases are COUNTY_ID **721824** (4 cells, also partial) and **737222** (1 cell). Their median heights are positive (8.66 m and 3.13 m); inspect the small inconsistent areas rather than silently clamping them. Roof support can be high while individual cells are wrong.

## Trees and canopy

| Result | Value |
|---|---:|
| Candidate treetops | 1,530 |
| Crowns passing the 3 m² minimum-area rule | 1,004 |
| Observed canopy at least 2 m high | 20,962.75 m² / 5.18 acres |
| Raster area with observation support | 99.469% |
| Unknown area | 477.75 m² / 0.531% |
| Canopy share of observed area | 23.416% |
| Full-grid bounds from missing coverage alone | 23.292–23.823% |

These are algorithm outputs, not verified tree counts. A crown passing the area rule is not independently accepted as a tree. The full-grid CANOPY_PCT field is correctly null because coverage is incomplete. The bounds only account for missing cells; they do not include classification or tree-detection error.

## Terrain and drainage

- DTM elevation range: **1320.92–1328.67 m**.
- Median terrain slope: **2.59%**; 95th percentile **7.10%**, using a 3 m neighborhood radius.
- Ground-support distance: median **0.5 m**, 95th percentile **3.16 m**, maximum **12.54 m**. These measure interpolation support, not accuracy.
- Maximum depression-fill depth: **0.329 m**. There are 988 cells (247 m²) deeper than 0.1 m in this diagnostic.
- **12,751 cells** are downstream of an AOI boundary or NoData neighbor in the D8 boundary-influence screen.

Drainage routes use a 1,000 m² contributing-area threshold. They are preliminary terrain routes, not a storm-drain model, delineated legal waters, or a flood map. Continuous flow runs on the original DTM; the independent fill-depth diagnostic does not feed routing. Catchment work requires a larger contributing extent and review of culverts, storm drains, bridges, and real depressions.

## Open the results in ArcGIS Pro

Everything below is relative to canopy-toolbox/scratch/planning_20260922:

| Location | Contents |
|---|---|
| layers/building_heights.lyrx | County polygons symbolized by 95th-percentile height |
| layers/tree_candidates.lyrx, layers/crowns.lyrx | Tree review points and crown polygons |
| layers/dtm.lyrx, layers/slope_percent.lyrx, layers/chm.lyrx | Terrain, slope, canopy review layers |
| layers/contributing_area_m2.lyrx, layers/flow_boundary_influence.lyrx | Drainage area and boundary influence |
| layers/depression_fill_depth_m.lyrx, layers/contours.lyrx | Depression-depth diagnostic and contours |
| millcreek_products/surfaces | Terrain, roof, canopy, all-object surface, support and height TIFFs |
| millcreek_products/terrain | Terrain/drainage TIFFs and terrain.gdb/contours |
| millcreek_products/planning.gdb/building_heights | Building-height feature class |
| millcreek_trees.gdb | Candidate points, review points, crowns, AOI, and canopy-cover table |
| delivery-index.lyrx | Header bounds for all 52 LAS tiles |
| delivery_index.gdb/las_tile_bounds | Tile paths, points, size, elevation bounds, and returns per bounding area |
| planning-overview.png | Four-panel map inspected after rendering |
| pilot-summary.json, tree-summary.json | Counts, coverage, and numerical QA |
| millcreek_products/planning.json | Complete run status, provenance, parameters, output catalog |
| county-footprints.json | Cached public query, timestamp, and features |

The delivery index describes rectangular header bounds, not a verified point-support boundary. Returns per square metre are not nominal pulse density.

## Verification and remaining work

**62 tests passed in ArcGIS Pro 3.7.2**, including seven new tests. They cover paired heights, missing data, negative values, overlapping/tiny/outside/partial footprints, D8 boundary propagation, an analytical slope, a synthetic depression, area units, source-raster preservation, output refusal, and an end-to-end LAS bundle. The full log is [full-tests.txt](full-tests.txt). Syntax checks and CLI help also passed.

The real-data run completed and its overview map was visually inspected. Roof heights, slopes, canopy structure, and coverage masks have plausible ranges; that is not an independent accuracy assessment. The all-object height raster deliberately retains negative values (minimum -1.65 m) for QA.

Footprint-by-footprint ArcGIS rasterization took several minutes for 115 buildings. It preserves overlap accounting but needs profiling/optimization before citywide use. Planning rasters and crown processing remain limited to 4 million cells per AOI; no citywide seamless crown reconciliation or catchment mosaic is claimed.

A follow-up changed building-height rasterization to use each footprint's grid-aligned bounding window. The ArcGIS regression covers an offset footprint, overlaps, tiny polygons, missing roofs, and partial/outside footprints. A fresh run over all 115 pilot footprints matched every saved summary field, including status flags, within 1e-6 for numeric values. That run took 539 seconds. It reduces the size of per-footprint masks and array calculations, but per-feature ArcGIS operations still dominate; no speedup is claimed without a same-machine baseline.

Recommended next work:
1. Compare the delivery-index footprint with the city and hydrologic study extents.
2. Review the flagged buildings and canopy/eave contact in this sample, then add park and foothill samples.
3. Establish citywide terrain and support mosaics; extend footprint-height processing with bounded windows or independently tested faster masks.
4. Add parcel/ROW/park canopy summaries and a larger drainage pilot with culverts and storm-drain context.
5. Reuse the reviewed surfaces for shade, solar, visibility, building massing, and planting opportunities as described in the product catalog.

