# Canopy Tools for ArcGIS Pro

Classified LAS to an observed canopy-height model, canopy cover by zone, estimated treetops, and crown polygons. The toolbox also provides a field-review layer. These are candidate trees and estimated crowns, not a stem census.

The [original review](reviews/2026-09-17/README.md) records the baseline failures. The [implementation report](reviews/2026-09-17/IMPLEMENTATION.md) records the core fixes; the [roof-edge follow-up](reviews/2026-09-17/ROOF_EDGES.md) contains the latest 55-test validation, imagery comparison, and current pilot layers.

## Terrain, buildings, and other planning products

The new **planning** CLI command creates terrain/slope/contour rasters, surface heights, drainage-screening layers, and optional county-footprint height summaries on a prepared LAS copy. See the [product catalog and expansion roadmap](PLANNING_PRODUCTS.md) for output definitions, QA flags, limits, and the runnable example. The [September 22 Millcreek pilot report](reviews/2026-09-22/PLANNING_PILOT.md) records the real-data results.

## Environment

Use ArcGIS Pro Python with arcpy, NumPy, and SciPy. The workstation pilot uses Pro 3.7.2, Python 3.13.13, and the bundled scientific packages. LAS preparation and raster construction require 3D Analyst; canopy raster analysis requires Spatial Analyst. The removed Feature To Point operation no longer imposes an Advanced-license check; verification was performed on this workstation's Advanced license, not on Basic or Standard.

Horizontal coordinates must be projected metres. A supplied vertical CRS must also use metres. For LAS without a vertical CRS, explicitly verify metre heights and use the toolbox checkbox or CLI --z-metres. This declaration does not convert coordinates or elevations. Zones and treetops must use the CHM's horizontal CRS.

## ArcGIS Pro toolbox

Add CanopyTools.pyt to a Pro project. Tools 3 and 4 require an existing file geodatabase. Tool 2 writes rasters to an ordinary folder; tool 5 writes a table inside an existing file geodatabase. Existing outputs are refused: choose a new prefix or run folder.

| Tool | Inputs and outputs |
|---|---|
| 1. Audit LAS Dataset | Reads CRS, point count, available classes, and statistics status. Presence of a class does not establish classification quality. |
| 2. Build Canopy Height Model | Ground DTM; unfilled vegetation/building DSMs; vegetation-support, building-occlusion and observation masks; CHM; JSON provenance. |
| 3. Detect Treetops | Height-banded local maxima, one actual raster cell per connected plateau, stable source/coordinate UUIDs. |
| 4. Delineate Crowns | Marker watershed constrained to measured canopy. Writes crowns and a separate trees_review feature class; input detections are unchanged. |
| 5. Summarize Canopy Cover | Independent CHM thresholding by polygon zone, including observation coverage and missing-area bounds. No detection input required. |

Optional cell-size parameters on tools 3–5 verify the raster resolution. Area is always calculated from the actual cells. Crown minimum height must match the detection threshold stored in the treetops. Change both together when changing the tree definition.

## Command-line workflow

Run from this folder using Pro Python. Paths below use the supplied delivery and the representative 250 m pilot; choose a NEW output directory for each changed analysis.

~~~powershell
$proPython = 'C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe'
& $proPython -m canopy inventory 'G:\GIS\2024 Lidar for tower extract' --report scratch\delivery.json
& $proPython -m canopy prepare 'G:\GIS\2024 Lidar for tower extract' scratch\new_pilot --extent 422350 4503350 422600 4503600
& $proPython -m canopy run scratch\new_pilot\prepared.lasd scratch\new_run --extent 422350 4503350 422600 4503600 --tile-size 125
~~~

Inventory reads uncompressed LAS headers and samples classes, returns, and flags without creating source-side statistics. Use --full for exact point counts by class. File creation dates are not acquisition dates. LAZ input is not supported by the direct binary inventory reader.

Prepare extracts new point files into output/points, checks that they are isolated from the delivery, and classifies only that copy. It preserves delivered ground and noise by default. If any copied file has no ground, ground classification runs with reuse of existing ground. Optional --classify-noise enables isolation screening with explicit, recorded parameters; review those thresholds locally.

Buildings are classified before remaining unclassified points are assigned height classes. Defaults: 2 m minimum building height, 10 square metres minimum building area, and class 6 for points below detected roofs and within 3 m above them. --roof-tolerance changes the last threshold; zero disables above-roof classification. Inspect tree overhangs and rooftop vegetation because these settings can remove real vegetation as well as roof equipment. Class 3 spans up to 0.5 m, class 4 up to 2 m, and class 5 up to 80 m above ground. These height labels do not establish that the objects are trees.

The run manifest records parameters, source size/mtime, code fingerprint, runtime, per-tile progress, and final outputs. --resume reuses an unchanged run, including saved raster cores after an interrupted attempt. Changed inputs, code, or parameters require a new directory. Source fingerprints detect normal file changes; they are not cryptographic checksums of all LAS bytes. An explicit --source-files list is required when not using a prepared LAS dataset.

Run outputs are CHM, treetops, crowns, and trees_review. Use tool 5 on the assembled CHM and your zones to produce canopy-cover tables.

## Raster and crown methods

- Ground class 2 supplies the triangulated DTM. Vegetation DSM uses only classes 3/4/5, first or single returns, BINNING MAXIMUM NONE. It cannot interpolate canopy across roads, roofs, or empty vegetation cells.
- Withheld, overlap, and synthetic points are excluded. This policy can reduce coverage and must be checked against delivery provenance.
- A valid ground estimate plus a direct vegetation or recognized non-canopy first/single return establishes an observed cell. Other cells remain NoData. Class 0/1 does not contribute canopy. Non-canopy classes are 2, 6, 9, 10, 11, 13–17, and 20.
- Where a measured class-6 first/single surface is more than 0.35 m above vegetation in the same cell, the CHM reports observed non-canopy. This prevents lower wall or under-roof returns from becoming visible canopy. Canopy above roofs survives. The configurable building-clearance threshold is a processing tolerance, not a surveyed accuracy value. The raw vegetation DSM and building_occlusion mask preserve the evidence.
- Smoothing and maxima operate on the same grid used by crown segmentation. Raw canopy support constrains the flood. No hydrology Fill or Flow Direction operation is used. Unseeded canopy stays unassigned and is reported.
- Crown areas use exact cell counts. Small crowns are excluded from polygons but remain in trees_review with CROWN_TOO_SMALL status. Crown diameter is the diameter of a circle with equivalent area, not a measured canopy width.

Raster creation uses buffered, nonoverlapping tile cores and assembles one canonical CHM. Detection and segmentation then run across that entire AOI. Tests demonstrated that finite crown halos alone cannot guarantee equivalent results, so the runner does not stitch independently grown crowns.

**Detection and crown processing have a hard limit of 4,000,000 cells per AOI** (1 square kilometre at 0.5 m resolution). The runner rejects larger analyses before processing. Citywide crown reconciliation is not implemented; independently run AOIs must not be appended and described as a seamless inventory. Raster-generation seams can still change DTM interpolation slightly; SEAM_REVIEW marks nearby detections for inspection. Cover summarization is independent of the crown limit.

TREE_ID is deterministic for the same source ID, CRS, and raster-cell location. It is suitable for repeat-run joins, but is not longitudinal tree identity: a changed raster peak can change an ID. Preserve reviewed inventory identity separately when reconciling future acquisitions.

## Canopy cover fields

| Field | Meaning |
|---|---|
| ZONE_M2 | Unioned polygon geometry area for the zone ID. |
| GRID_M2 | Cell-centre rasterized area, which can differ from polygon area. |
| CANOPY_M2 / CANOPY_ACRES | Observed cells at or above the requested height threshold. |
| OBSERVED_M2 / MISSING_M2 | Known and unknown rasterized zone area. |
| COVERAGE_PCT | Observed share of GRID_M2. |
| CANOPY_PCT | Full-grid canopy percent only when all zone cells are observed; otherwise null. |
| OBS_CANOPY_PCT | Canopy percent among observed cells only. |
| CANOPY_LOW_PCT / CANOPY_HIGH_PCT | Extreme full-grid percentages if missing cells are all non-canopy or all canopy. These are not confidence intervals. |
| COVER_STATUS | COMPLETE, PARTIAL, NO_DATA, or NO_CELL_CENTERS. |

Duplicate zone IDs are unioned; distinct overlapping zones are analyzed independently. Outside and all-missing zones retain output rows. Very small polygons without cell centres have no rasterized percentage. Processing each unique zone separately prioritizes correct overlap accounting; large zone collections need a performance review.

## Field review and imagery

The tree layer includes TREE_ID, SOURCE_ID, HEIGHT_M, REVIEW_STATUS, SPECIES, DBH_CM, CONDITION, and FIELD_NOTES. Species, DBH, condition, and stem coordinates are not inferred from lidar. Review status starts UNVERIFIED; crown attributes and acceptance status live on the independent trees_review copy. Metadata preserves the estimate warning.

The supplied Nearmap WMS was used for local pilot comparison. The connection and imagery remain in ignored scratch storage; no credential belongs in tracked source or documentation. The endpoint serves latest imagery and does not expose a capture date in the capabilities response used here. The user confirmed lidar capture in 2024 and nominal point spacing of 0.5 m (separate from CHM cell size). The exact flight date and temporal match with Nearmap remain unknown. Imagery can expose roof leakage, omissions, and merged crowns; it is not a field-verified accuracy sample.

Before publishing an inventory: inspect representative parks, street trees, dense canopy, buildings, slopes, and small trees; agree on the minimum tree definition; collect independent reference labels; then measure omissions, false detections, merges/splits, and canopy error. This pilot establishes executable behavior and reveals classification issues. It does not establish a production accuracy percentage.

## Verification

~~~powershell
# Pure logic and mocked utility safeguards; ArcGIS cases skip outside Pro.
python -m unittest discover -s tests -t . -v
# Actual raster/LAS/geodatabase regression fixtures on the Pro workstation.
& $proPython -m unittest discover -s tests -t . -v
~~~

The suite covers a 137-cell ideal crown, diagonal plateaus, adjacent markers, canopy gaps, class-1 exclusion, empty and unknown surfaces, coverage denominators, duplicate/overlapping/outside/tiny zones, units, repeated output creation, global segmentation across raster cores, resume checks, and standalone utility failure safeguards. Hosted editing and publishing are not exercised.


## Optional roof-edge refinement

The stock building classifier can leave roof-edge returns in vegetation classes. An experimental, opt-in refinement is available after prepare and before run:

~~~powershell
& $proPython -m canopy refine-roofs scratch\new_pilot\prepared.lasd scratch\roof_refined
& $proPython -m canopy run scratch\roof_refined\prepared.lasd scratch\roof_run --extent 422350 4503350 422600 4503600 --tile-size 125
~~~

This creates NEW LAS copies. It derives roof-support polygons from eligible class-6 first/single returns, bridging only one-cell gaps. A robust low-slope plane is fitted to each support region of at least 25 square metres. Automatic refinement requires at least 80% plane inliers, residual RMSE at most 0.15 m, and slope below 0.25. These are model-selection thresholds, not survey accuracy claims.

Eligible class-3/4/5 points inside the roof support or within a 1 m raster edge band are assigned class 6 only when between 0.35 m below and 3 m above the fitted roof plane. Parameters --edge-distance, --below-roof, --above-roof, and --min-roof-area are explicit. Lower adjacent canopy and higher overhangs stay unchanged; vegetation falling within the chosen roof-height band can still be affected and must be inspected. Weak, steep, or complex roof fits are not automatically refined.

The output includes roof_review.gdb/roof_outlines, roof and ground rasters, prepared.lasd and copied points, per-point previous classification bytes under changes/, and a preparation.json manifest with before/after counts and plane diagnostics. Only classification bytes are changed; source LAS files, coordinates, returns, and flags are preserved. Legacy and LAS 1.4 point formats have byte-integrity tests.

ROOF_Z_M is median measured roof elevation; ROOF_H_M is median roof elevation minus the interpolated ground surface; FIT_RMSE_M is the plane-fit residual, not elevation accuracy. MODEL_OK and PARTIAL_AOI identify rejected fits and outlines truncated by the analysis boundary. These rasterized roof-support outlines are unverified and should not be described as surveyed building-wall footprints.

The user-supplied OSM layer was checked for the pilot plus a 30 m border and returned no intersecting footprints. It remains useful reference data where it has coverage; it is not used as a blanket canopy exclusion.
