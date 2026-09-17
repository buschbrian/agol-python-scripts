# Tree inventory scripting review — 2026-09-17

Implementation follow-up: [fixes, regression results, and real-data pilot](IMPLEMENTATION.md). This document preserves the original baseline findings.

Reviewed repository: U:\agol-python-scripts  
Baseline: main, commit 319f7b7; working tree clean before inspection.  
Conclusion: useful prototype, but not ready for an inventory production run. Both runtime blockers and incorrect analytical results were reproduced on this workstation.

## Repository map

There were 14 Python files and one Python toolbox at the review baseline.

| Item | Role and relevance |
|---|---|
| canopy-toolbox/CanopyTools.pyt | ArcGIS Pro entry point; five tools and their parameters. |
| canopy-toolbox/canopy/rasters.py | LAS audit, ground DTM, vegetation DSM, canopy height model (CHM). |
| canopy-toolbox/canopy/treetops.py | Smoothing, height-banded local maxima, plateau polygons, tree points. |
| canopy-toolbox/canopy/crowns.py | Inverted-CHM flow direction and watershed; crown geometry and height attributes. |
| canopy-toolbox/canopy/cover.py | Thresholded CHM summarized into canopy area and percent by polygon zone. |
| canopy-toolbox/canopy/bands.py | Pure-Python height bands, validation, and search radius conversion. |
| canopy-toolbox/canopy/tiling.py | Pure-Python tile extents, buffers, and point ownership; not connected to production execution. |
| canopy-toolbox/canopy/licensing.py | Advanced-license check and extension checkout/check-in. |
| canopy-toolbox/canopy/__init__.py | Package definition. |
| canopy-toolbox/tests/test_bands.py | Tests for band parsing, validation, and radii. |
| canopy-toolbox/tests/test_tiling.py | Tests for grid extents and point ownership. |
| canopy-toolbox/tests/__init__.py | Test package marker. |
| canopy-toolbox/README.md | Intended process, assumptions, validation guidance, and accuracy assertions. |
| canopy-toolbox/AGENTS.md | Development constraints, including keeping cover independent and preserving plateau collapse. |
| add_badelf_fields_to_agol.py | Hosted-layer GNSS metadata schema; potentially relevant to subsequent field verification. Does not collect or populate survey measurements. |
| sketch_layer_to_template_schema.py | Copies a production schema and loads an exported sketch layer; separate utility, not connected to tree outputs. |
| assign_polygon_colors.py | Polygon adjacency coloring; potential cartography helper, not part of detection. |
| README.md, LICENSE, .gitignore files | Repository overview, MIT license, and ignored generated assets. |

No LAS/LAZ/LASD inputs, ArcGIS projects, sample imagery, validation plots, production inventory schema, classification automation, batch runner, environment specification, or publishing workflow were found in the repository inventory. Some data formats are ignored by Git; the local file inventory was also checked.

## Existing process

~~~mermaid
flowchart TD
    A[LAS files] --> B[Manual classification with stock ArcGIS tools]
    B --> C[Tool 1: audit LAS dataset]
    C --> D[Tool 2: DTM and vegetation DSM]
    D --> E[CHM]
    E --> F[Tool 5: canopy cover by zone]
    E --> G[Tool 3: estimated treetop points]
    G --> H[Tool 4: crown polygons and attributes]
    E --> H
    I[Tile and ownership helpers] -. no production caller .-> G
~~~

Classification is described in the README, but is not implemented by this toolbox. The output is a canopy/detected-crown estimate. There is no implementation for species, stem locations, DBH, condition, maintenance records, field verification status, or persistent inventory identifiers.

## Workstation and verification

- ArcGIS Pro **3.7.2**, build 1901; Advanced license (ArcInfo); Named User.
- Pro Python **3.13.13**.
- 3D Analyst and Spatial Analyst both reported available and were successfully checked out for isolated tests.
- Standalone Python 3.14 was used for the existing pure-Python suite: **31/31 tests pass**.
- Syntax compilation succeeds for all **15 Python/toolbox source files**.
- Importing the toolbox succeeds and exposes all five tools.
- The LAS audit correctly reports the six classes in the generated 191-point LAS fixture.
- Both default interpolation strings execute successfully on Pro 3.7.2.
- Crown attribute calculation works independently with geodatabase inputs.
- Production datasets and hosted layers were not processed or edited. All synthetic data was generated in a unique temporary folder.

The passing unit tests do not exercise the ArcPy processing functions. The README's warning that those functions had never run was accurate for the original implementation; this review now supplies limited synthetic runtime evidence, not real-data validation.

## Findings requiring correction before production

### 1. P1 — Tools 3 and 4 cannot complete with either ordinary output workspace type

**Locations:** treetops.py:62–74; crowns.py:35–47; CanopyTools.pyt:136 and 193.

The UI accepts a generic workspace, but the implementations mix TIFF paths with geodatabase-only assumptions:

- File geodatabase: saving plateaus.tif or crowns.tif inside the .gdb fails with ERROR 010240.
- Folder: treetops become shapefiles; calculating TREE_ID from !OBJECTID! fails with ERROR 000539 because the actual OID field is FID.
- Folder: crowns fail when AlterField tries to rename the shapefile gridcode field, with ERROR 000664.
- The later Shape_Area selection and long attribute names also assume geodatabase behavior.

**Action:** define one supported output contract: geodatabase feature classes/tables with valid geodatabase raster names, or a separate raster folder. Use Describe(...).OIDFieldName where needed. Validate the contract in the toolbox UI.

### 2. P1 — Crown watershed does not recover even a simple synthetic crown

**Locations:** crowns.py:27–36; treetops.py:39–45 and 70–75.

To inspect the algorithm beyond finding 1, diagnostic function copies were compiled in memory with only the two invalid TIFF names changed. The repository source files were untouched. Minimum crown area was set to zero so the result could be inspected.

A symmetric, 12 m tall synthetic cone contained **137 cells above the 2 m threshold**, at 1 m resolution:

- Detection produced one point at the peak.
- Watershed produced **one crown cell**, or **1 m²**.
- The normal 3 m² minimum-area filter would delete that crown.

An independent rerun with explicitly matched extent, cell size, snap raster, and an explicitly rasterized peak reproduced the same one-cell watershed. This rules out simple seed-grid alignment as the explanation for this fixture. Flow-direction values around the peak included undefined, multi-direction sink codes.

ArcGIS Flow Direction handles one-cell sinks internally and can assign undefined flow directions to sinks. Consequently, omitting Fill does not by itself guarantee that a single treetop point represents an entire drainage basin. See [Flow Direction documentation](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/spatial-analyst/flow-direction.html).

A cone with an offset peak produced only 30 crown cells out of 137; the detected point sampled 10.5 m while the raw maximum was 15 m. Detection uses a smoothed surface, but delineation uses the raw surface, so their extrema need not coincide.

**Action:** revisit the segmentation/seed representation, with tests for simple cones, flat tops, adjacent trees, and uneven crowns. Investigate sink-region seeds or a suitable marker-based segmentation method. Keep the no-Fill requirement; adding Fill indiscriminately is not a correction. Define acceptance checks for seeded canopy coverage and tree-to-crown correspondence.

### 3. P1 — Vegetation DSM interpolation invents canopy across open gaps

**Locations:** rasters.py:21 and 95–100.

The DSM is built only from selected above-ground returns and uses NATURAL_NEIGHBOR to fill empty cells. A cell lacking a vegetation return can therefore receive an interpolated canopy elevation from surrounding trees.

In the synthetic LAS fixture, ground was at 100 m and vegetation strips were at 110 m, separated by a bare-ground gap:

- Default processing gave a test gap location **11.76 m CHM height** because the unclassified point also influenced interpolation.
- A second diagnostic run excluded class 1 and used only classes 3/4/5; the same gap still received **10 m CHM height**.
- A test zone containing part of the gap was consequently reported as 100% canopy.

This is an analytical error independent of the class-1 problem below. Esri documents natural-neighbor void filling as interpolation of cells with no points: [LAS Dataset To Raster](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/conversion/las-dataset-to-raster.html).

**Action:** define a measured vegetation-support mask and a policy for small sampling holes versus observed non-canopy versus missing coverage. Constrain any interpolation accordingly. A vegetation-only interpolated surface alone is not an adequate canopy occupancy model.

### 4. P1 — The vegetation filter includes unclassified points

**Location:** rasters.py:15.

VEG_CLASSES is "1;3;4;5". Class 1 is unclassified, so unclassified roofs, wires, or other objects can enter a surface advertised as vegetation-only.

A synthetic class-1 point 15 m above ground appeared as **15 m CHM height**. Class-6 building returns themselves were excluded, but interpolation still assigned canopy height at a building location.

**Action:** default to validated vegetation classes, quantify residual unclassified points, and make any exception an explicit, documented choice. Building exclusion also needs to account for canopy interpolation across roofs.

### 5. P1 — Canopy percent silently excludes missing area from its denominator

**Locations:** cover.py:26–28 and 35–46.

Con preserves CHM NoData, and ZonalStatisticsAsTable(..., "DATA", ...) ignores it. COUNT therefore represents valid value cells, not the full zone.

A **16 m²** zone with **8 m² of observed canopy and 8 m² of NoData** produced:

- CANOPY_M2 = 8
- ZONE_M2 = 8
- CANOPY_PCT = 100

That is 100% of observed cells, mislabeled as a complete zone result. The actual full-zone canopy proportion is unknown in this fixture; if the missing cells were independently established as bare ground, it would be 50%. NoData must not automatically be treated as zero canopy.

**Action:** report total zone area, observed area, missing area, and coverage fraction separately. Flag incomplete zones or use an explicitly documented observed-area denominator. Preserve zone records even when they have no observations. See [Zonal Statistics as Table](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/spatial-analyst/zonal-statistics-as-table.html).

### 6. P1 — Units and pixel size are assumed rather than validated

**Locations:** cover.py:30; rasters.py:65; treetops.py:49; crowns.py:47 and 74–79; toolbox cell-size parameters.

The tools independently accept a cell size, defaulting to 0.5, rather than deriving it from the CHM. Neither horizontal nor vertical units are enforced as metres.

For the 1 m raster above, leaving cover's default cell size at 0.5 reported **2 m² instead of 8 m²**. Geographic or feet-based inputs would also invalidate metre-labelled thresholds, heights, and areas.

**Action:** derive cell width/height from the raster, validate a projected CRS, explicitly handle horizontal and vertical units, and reject inconsistent inputs. Set consistent processing environments for tools 3–5; ambient Pro settings must not silently change analysis.

### 7. P2 — Tiling and seam handling exist only as helpers

**Locations:** tiling.py:91–138; treetops.py:73–74; CanopyTools.pyt.

No production function or toolbox tool calls tile_grid, recommended_overlap, owning_tile, or dedupe_by_core. There is no tiled execution, merge, restart, or crown reconciliation workflow.

TREE_ID is copied from a local ObjectID, so independently produced tile outputs will collide if simply appended. Prefixes change filenames, not tree identifiers.

The helper also accepts a tile size and overlap that are not multiples of cell size. A 4.1 m tile with a 0.3 m overlap at 0.5 m resolution produced unsnapped internal boundaries, despite the documented snapped-grid contract.

**Action:** add an explicit batch coordinator with a shared grid, tile IDs, globally unique detection IDs, ownership filtering, crown handling, progress logs, and restart behavior. Quantize or validate tile dimensions. Validate seam equivalence against untiled results; different local detections are not resolved merely by assigning coordinate ownership.

### 8. P2 — Repeatability and boundary cases are not covered

**Locations:** cover.py:24–26; rasters.py:87–100; treetops.py:58–75; bands.py:54–71.

- Every cover call writes the same canopy_binary intermediate. A second call with a different output table failed with ERROR 000872 when overwrite was disabled.
- Several other intermediate names and layer names are fixed, with no cleanup on error.
- NaN and infinity are not explicitly rejected in numeric parameters; parse_bands("2-:nan") was accepted.
- Two diagonally touching tied maxima became two point features despite belonging to one eight-connected RegionGroup. RasterToPolygon's default separate polygon parts bypasses the intended one-point-per-region collapse.
- The no-tree, all-NoData, partly covered zone, duplicate zone-ID, overlapping zone, feet-based CRS, non-square pixel, and repeat-run cases lack integration coverage.

**Action:** give intermediates unique scratch names with cleanup, validate finite positive parameters, preserve region identity during plateau collapse, and add targeted regression fixtures for these observed failures.

## Process and documentation gaps

- Audit currently reports dataset-wide presence of classes, not per-file counts, proportions, or classification quality. It does not validate coverage, point density, ground support, acquisition date, units, or return/flag distributions.
- has_building is computed but does not generate a missing-building warning. Lack of noise-class points does not prove noise screening was skipped; a clean delivery may contain none.
- Build CHM does not enforce successful preflight checks before processing.
- Height classification assigns labels by height. It does not prove an object is a tree. Ground, buildings, other structures, noise, and vegetation require appropriate review.
- Tree height threshold, band minimum height, and canopy/crown thresholds are independently editable and can diverge.
- Crowns smaller than the cutoff are removed without removing or flagging their treetop records; detected-point and accepted-crown counts can differ.
- Crown processing mutates the supplied treetop feature class by adding crown attributes. The UI does not make that side effect explicit or provide a derived updated-point output.
- Existing numeric detection-rate and plateau-reduction claims have no cited experiment or local validation artifacts. They are not established performance guarantees. Bias can include false positives as well as missed trees.
- The acquisition-date statement in the README is not proof of the date or leaf condition of the datasets that will be supplied.
- No uncertainty calculation, validation sampling implementation, run manifest, output metadata warning, production inventory schema, or deployment process is present. The estimate warning is a geoprocessing message, not persistent dataset metadata.

## Practical processing sequence for the actual LAS delivery

1. **Inventory the delivery first:** file paths, source/producer, actual lidar versus photogrammetry, extent, acquisition date, point spacing/density, horizontal and vertical reference systems and units, class counts, return distributions, and flags. Match this to the study boundary and intended deliverables.
2. **Create a working copy for classification.** ArcGIS classification tools edit referenced point files; a new .lasd referencing the same originals is not a copy of those points.
3. **Choose a pilot area** containing known trees, pavement, buildings, open gaps, slopes, and dense canopy. Establish the tree-height definition and validation reference.
4. **Screen noise using a method appropriate to density.** Isolation or absolute-height screening can precede ground classification; relative-height noise screening requires a ground surface. Preview questionable classifications before committing them to working data. [Classify LAS Noise](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/3d-analyst/classify-las-noise.html)
5. **Classify and inspect ground**, then classify buildings/structures before assigning remaining class-0/1 points to height-based classes. Buildings require prior ground classification. Height bins must be checked on the pilot; class boundaries are not a substitute for vegetation validation. [Classify LAS Building](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/3d-analyst/classify-las-building.html), [Classify LAS By Height](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/3d-analyst/classify-las-by-height.html)
6. **Refresh statistics and audit each file/tile**, including unclassified leftovers and classification errors.
7. **Build a validated ground model, vegetation support/coverage masks, and CHM** on one documented grid. Examine roofs, gaps, edges, and hill slopes before calculating canopy.
8. **Validate canopy cover first**, including zone denominators and missing coverage. Keep this independent of individual-tree detection.
9. **Calibrate and validate detection/segmentation**, then implement tiled scaling. Compare estimated crowns to imagery and field observations across distinct settings.
10. **Create a field-review inventory layer** with persistent IDs, source date, method, confidence/review status, and operational fields. Report measured validation results and uncertainty before publishing counts.

No classification thresholds, tile size, coordinate conversion, or final accuracy claim should be selected solely from this repository's defaults.

## Separate utility notes

These scripts are not invoked by the canopy toolbox:

- **Bad Elf schema helper:** useful for a future hosted field-verification layer; adds missing fields only. It does not validate the types/domains of existing fields, populate GNSS values, or create the tree-inventory schema. A negative --layer index also selects from the end rather than being rejected.
- **Sketch schema helper:** DRY_RUN still exports RULES_CSV before it returns, contrary to its "nothing written" message. Attribute rules are disabled without a finally block, so a failed load can leave them disabled on the new target. It should not be treated as a ready-made tree loading workflow.
- **Polygon coloring:** uses a fixed nine-color greedy assignment and silently defaults unmatched features to 1. There is no explicit failure if all available colors are used. Its actual field is Color_ID, while the root README calls it colorID.

These utilities received source inspection and syntax checks; their data-editing operations were not run.

## Fix order and acceptance gates

1. Correct output workspaces, raster names, and OID handling.
2. Correct vegetation support/class filtering, cover coverage accounting, and unit/grid validation.
3. Replace or correct crown seed/segmentation behavior until simple synthetic trees yield sensible complete crowns.
4. Add repeatable ArcGIS regression checks covering the failures above.
5. Implement and verify classification/preflight and one real pilot tile.
6. Connect tiling, IDs, merge/restart behavior, run manifests, and field-review output.
7. Calibrate against independent observations before any production count or percentage is published.

The current code should not be run across the full LAS delivery simply because the 31 existing tests pass.

## Evidence and scope

[runtime-evidence.json](runtime-evidence.json) records the synthetic results, exceptions, and exact diagnostic source used. Baseline scripts were not edited. The follow-up vegetation experiment changed only an in-memory module constant, and the seed experiment changed only raster output names in in-memory function copies; neither is a production fix.

Temporary diagnostic folder:
C:\Users\bbusch\AppData\Local\Temp\canopy-review-624d3728add548feb88c10b0b12e2052

Tests operated on small synthetic fixtures. Actual LAS quality, classification performance, acquisition metadata, local tree accuracy, city-scale performance, and final inventory requirements remain unverified until the delivery and study context are supplied.

