# Canopy Tools for ArcGIS Pro

Classified LAS to an observed canopy-height model, canopy cover by zone, estimated treetops, and crown polygons. The toolbox also provides a field-review layer. These are candidate trees and estimated crowns, not a stem census.

The source acquisition, its tested accuracy, delivered classes, and per-tile flight dates are recorded in [the 2023 acquisition record](acquisitions/2023-salt-lake-valley/RECORD.md); the [acquisition procedure](acquisitions/README.md) documents each new one the same way. The [original review](reviews/2026-09-17/README.md) records the baseline failures. The [implementation report](reviews/2026-09-17/IMPLEMENTATION.md) records the core fixes; the [roof-edge follow-up](reviews/2026-09-17/ROOF_EDGES.md) contains the latest 55-test validation, imagery comparison, and current pilot layers.

## Terrain, buildings, and other planning products

The new **planning** CLI command creates terrain/slope/contour rasters, surface heights, drainage-screening layers, and optional county-footprint height summaries on a prepared LAS copy. See the [product catalog and expansion roadmap](PLANNING_PRODUCTS.md) for output definitions, QA flags, limits, and the runnable example. The [September 22 Millcreek pilot report](reviews/2026-09-22/PLANNING_PILOT.md) records the real-data results. The [preliminary imagery QA](reviews/2026-09-22/IMAGERY_QA.md) flags tree candidates on or near county footprints for manual review. The [building-classification experiment](reviews/2026-09-22/CLASSIFICATION_EXPERIMENT.md) compares CONSERVATIVE, STANDARD, and AGGRESSIVE methods on the same pilot without declaring an accuracy winner. The [deep-learning setup report](reviews/2026-09-22/DL_SETUP.md) records the installed Pro 3.7 libraries, two Esri point-cloud DLPKs, and isolated GPU smoke tests.

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
& $proPython -m canopy index-delivery 'G:\GIS\2024 Lidar for tower extract' scratch\delivery_index --swaths acquisitions\2023-salt-lake-valley\reference\index\Salt_Lake_Valley_Lidar_Swath_Index.shp
& $proPython -m canopy prepare 'G:\GIS\2024 Lidar for tower extract' scratch\new_pilot --extent 422350 4503350 422600 4503600
& $proPython -m canopy run scratch\new_pilot\prepared.lasd scratch\new_run --extent 422350 4503350 422600 4503600 --tile-size 125
~~~

Inventory reads uncompressed LAS headers and samples classes, returns, and flags without creating source-side statistics. Use --full for exact point counts by class. File creation dates are not acquisition dates. LAZ input is not supported by the direct binary inventory reader.

Index-delivery maps the same headers to a `las_tile_bounds` feature class, a layer file, and a JSON report, all outside the delivery. With --swaths it stamps FLIGHT_FIRST, FLIGHT_LAST, FLIGHT_DATES, and SWATH_COUNT on each tile from the swath polygons that intersect its header rectangle. The swath index must use the delivery's horizontal CRS; a tile that several swaths cross carries every date, because a header rectangle does not say which swath supplied which point. Header bounds are screening coverage, not a verified point-support or city-coverage footprint, and returns per bounding area is not nominal pulse density.

The same run writes the acquisition record: `acquisition.json` and `acquisition-facts.md`, which carry tile names but no per-file paths. With --boundary it measures the share of a polygon, normally the city, inside the header rectangles; the boundary may be in any CRS and is projected with a recorded datum transformation. Adding --tile-index (and --tile-field if the index is not keyed by `Tile_Name`) lists the official tiles that touch the boundary but are not in hand, with the boundary area in each. A delivery tile holds an index tile when its rectangle covers at least half of it, so file names need not match the index. The [acquisition procedure](acquisitions/README.md) describes documenting each new acquisition this way.

Prepare extracts new point files into output/points, checks that they are isolated from the delivery, and classifies only that copy. It preserves delivered ground and noise by default. If any copied file has no ground, ground classification runs with reuse of existing ground. Optional --classify-noise enables isolation screening with explicit, recorded parameters; review those thresholds locally.

Buildings are classified before remaining unclassified points are assigned height classes. Defaults: 2 m minimum building height, 10 square metres minimum building area, STANDARD building method, and class 6 for points below detected roofs and within 3 m above them. --building-method selects CONSERVATIVE, STANDARD, or AGGRESSIVE for a new working copy and records it in preparation.json; compare candidate settings on the same pilot before adopting one. --roof-tolerance changes the above-roof threshold; zero disables above-roof classification. Inspect tree overhangs and rooftop vegetation because these settings can remove real vegetation as well as roof equipment. Class 3 spans up to 0.5 m, class 4 up to 2 m, and class 5 up to 80 m above ground. These height labels do not establish that the objects are trees.

The run manifest records parameters, source size/mtime, code fingerprint, runtime, per-tile progress, and final outputs. --resume reuses an unchanged run, including saved raster cores after an interrupted attempt. Changed inputs, code, or parameters require a new directory. Source fingerprints detect normal file changes; they are not cryptographic checksums of all LAS bytes. An explicit --source-files list is required when not using a prepared LAS dataset.

Run outputs are CHM, treetops, crowns, and trees_review. Use tool 5 on the assembled CHM and your zones to produce canopy-cover tables.

## Raster and crown methods

- Ground class 2 supplies the triangulated DTM. Vegetation DSM uses only classes 3/4/5, first or single returns, BINNING MAXIMUM NONE. It cannot interpolate canopy across roads, roofs, or empty vegetation cells.
- Withheld, overlap, and synthetic points are excluded. This policy can reduce coverage and must be checked against delivery provenance. On the 2023 Salt Lake Valley delivery the overlap bit was never populated, so the exclusion has no effect there and all swath overage is retained.
- A valid ground estimate plus a direct vegetation or recognized non-canopy first/single return establishes an observed cell. Other cells remain NoData. Class 0/1 does not contribute canopy by default. Non-canopy classes are 2, 6, 9, 10, 11, 13–17, and 20. After a point-cloud model explicitly assigns class 0 to background on a complete working copy, --classified-background-zero additionally treats class-0 first/single returns as observed non-canopy. Do not use that flag on ordinary unclassified LAS.
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

## Footprint-contact review

Use county or other reviewed building footprints to prioritize candidate trees touching roofs. This copies the candidate layer and adds `FOOT_QA` and ArcGIS Near fields; it never deletes detections or changes the input. A point on a footprint can be a real tree overhang, so review imagery and LAS classes before changing classification.

~~~powershell
& $proPython -m canopy review-footprints scratch\new_run\inventory.gdb\trees_review path\to\footprints scratch\review.gdb --distance 2
~~~

Create the output file geodatabase first. Inputs must be projected metres in the same horizontal CRS. The output feature class name defaults to `trees_footprint_review`; `--name` selects a different unused name. `NEAR_FID` is a transient footprint ObjectID, while `NEAR_DIST` is distance in metres; `-1` means no footprint within the search radius. The [Millcreek imagery QA](reviews/2026-09-22/IMAGERY_QA.md) is a worked example.

## Field review and imagery

The tree layer includes TREE_ID, SOURCE_ID, HEIGHT_M, REVIEW_STATUS, SPECIES, DBH_CM, CONDITION, and FIELD_NOTES. Species, DBH, condition, and stem coordinates are not inferred from lidar. Review status starts UNVERIFIED; crown attributes and acceptance status live on the independent trees_review copy. Metadata preserves the estimate warning.

The supplied Nearmap WMS was used for local pilot comparison. The connection and imagery remain in ignored scratch storage; no credential belongs in tracked source or documentation. That earlier endpoint serves latest imagery and did not expose a capture date. A dated [Custom WMS handoff](reviews/2026-09-22/NEARMAP_HISTORICAL_WMS.md), pilot [GeoJSON AOI](reviews/2026-09-22/millcreek_nearmap_aoi.geojson), and [historical WMS helper](nearmap_historical_wms.py) were used to retrieve the August 31, 2023 survey tile for the Millcreek pilot. The [September 23 checkpoint](reviews/2026-09-22/TODAY_2026-09-23.md) records the review and remaining date/registration uncertainty. Credentials and imagery stay in ignored or private local storage. The lidar was collected 7 October to 5 November 2023 at 0.32 m nominal pulse spacing, with a measured first-return average of 18.2 points per square metre; see [the acquisition record](acquisitions/2023-salt-lake-valley/RECORD.md) for per-tile flight dates and the reasons the earlier "2024, 0.5 m" note was wrong. The temporal match with the earlier latest-only Nearmap imagery remains unknown. Imagery can expose roof leakage, omissions, and merged crowns; it is not a field-verified accuracy sample.

Before publishing an inventory: inspect representative parks, street trees, dense canopy, buildings, slopes, and small trees; agree on the minimum tree definition; collect independent reference labels; then measure omissions, false detections, merges/splits, and canopy error. This pilot establishes executable behavior and reveals classification issues. It does not establish a production accuracy percentage.

## Deep-learning model pilot

The [Pro 3.7 setup and model smoke tests](reviews/2026-09-22/DL_SETUP.md) record the installed libraries and Esri DLPKs. The [Millcreek tree-model pilot](reviews/2026-09-22/DL_PILOT.md) and [sequential model and current OSM validation](reviews/2026-09-22/DL_VALIDATION.md) compare model-classified canopy and trees with the STANDARD baseline. Model inference edits the supplied LAS copy, so use a new copy; refresh LAS dataset statistics after inference. For a custom LAS dataset, canopy run also requires --source-files. Only pass --classified-background-zero when every relevant class-0 point was explicitly classified by the model as background; the flag and effective non-canopy codes are recorded in the run and CHM manifests.

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

The user-supplied 2024 OSM layer was checked for the earlier Taylorsville demo tile plus a 30 m border and returned no intersecting footprints. A live Overpass query returned 162 building ways for the later Millcreek residential pilot; see [sequential model validation](reviews/2026-09-22/DL_VALIDATION.md). It remains useful reference data where it has coverage; it is not used as a blanket canopy exclusion.
