# LiDAR planning products

The delivery can support a shared terrain, surface, canopy, and building-height library. Generate and review those once, then reuse them for planning questions. The collection is QL1 at **0.32 m nominal pulse spacing**, flown 7 October to 5 November 2023, with a tested point-cloud NVA RMSEz of 5.87 cm; see [delivery provenance](DELIVERY_PROVENANCE.md). The pilot uses 0.5 m raster cells, which is a separate choice from the pulse spacing.

The existing tree workflow is retained. The new command adds a bounded planning bundle, with a separate manifest and explicit coverage flags. Outputs are local, unvalidated planning estimates.

## Run a bundle

Use ArcGIS Pro Python with 3D Analyst and Spatial Analyst, from canopy-toolbox:

~~~powershell
& $proPython -m canopy planning scratch\planning_20260922\millcreek_prepared\prepared.lasd scratch\new_planning_run --extent 428100 4504100 428400 4504400 --footprints scratch\planning_20260922\reference.gdb\county_footprints --footprint-id COUNTY_ID
~~~

A completed preparation.json must match the working-copy LAS dataset. Choose a new output folder outside its preparation folder. Footprints are optional; when supplied, they must already be in the LAS horizontal CRS and have a stored, unique, non-null ID. Keep the county ObjectID in a normal field such as COUNTY_ID when importing it. The command does not download or alter a hosted service.

Horizontal and vertical units must be metres. If the LAS has no vertical reference, verify the heights and explicitly use --z-metres. Analysis is limited to **4,000,000 cells**. This implementation is a pilot workflow; it does not provide seamless citywide crowns or catchment-complete citywide drainage.

| Option | Default | Meaning |
|---|---:|---|
| --cell-size | 0.5 m | Common raster cell size |
| --neighborhood | 3 m | Surface-parameter neighborhood radius |
| --tpi-radius | 10 m | Radius for elevation minus neighborhood mean |
| --drainage-area | 1,000 m² | Threshold for candidate concentrated-flow routes |
| --contour-interval | 2 m | Contour spacing; not survey accuracy |

## Products implemented

| Dataset | Use and interpretation |
|---|---|
| dtm.tif | Interpolated class-2 bare-earth terrain |
| ground_direct.tif | Direct class-2 cell maxima; NoData means no direct ground return |
| ground_distance_m.tif | Distance to the nearest directly supported ground cell |
| dsm_all.tif | Listed non-noise first/single-return maximum, including buildings and vegetation; no void filling |
| surface_height_m.tif | DSM minus terrain; visible-object heights |
| dsm_veg.tif, chm.tif | Existing vegetation surface and supported canopy-height model |
| dsm_building.tif | Direct class-6 first/single-return roof surface |
| vegetation_support.tif, observed.tif, building_occlusion.tif | Canopy observation and same-cell roof-occlusion evidence |
| slope_degrees.tif, slope_percent.tif | Terrain slope at the selected neighborhood scale |
| aspect_degrees.tif | Downslope direction from north; flat areas use ArcGIS -1 |
| profile_curvature.tif, tangential_curvature.tif | Along-slope and cross-slope shape |
| hillshade.tif | Terrain relief for visual interpretation |
| terrain_position_m.tif | Local high/low ground relative to the selected neighborhood |
| terrain.gdb/contours | Terrain contours with metre elevations |
| flow_direction_d8.tif | One downstream direction per cell |
| flow_accumulation_cells.tif | Count of upstream cells |
| contributing_area_m2.tif | Contributing ground area, including the receiving cell |
| drainage_paths.tif | Candidate concentrated-flow routes; not a surveyed stream network |
| depression_fill_depth_m.tif | Separate depth-to-spill diagnostic; not inundation |
| flow_boundary_influence.tif | Cells downstream of an AOI edge or NoData neighbor |
| terrain_neighborhood_complete.tif | Whether the full terrain/TPI neighborhood is inside valid terrain |
| planning.gdb/building_heights | Original footprints and attributes plus height statistics and QA |

Generated data stay in ignored scratch. planning.json records the preparation reference, source ID, code hash, runtime, parameters, filter policy, status, and outputs. terrain/terrain.json and surfaces/chm.json record their methods. building-heights.json mirrors the footprint statistics.

## Building fields

The workflow uses class-6 roof returns, not the all-object DSM. Classification errors can still contaminate the result.

| Field | Meaning |
|---|---|
| ROOF_Z50_M | Median roof-cell elevation |
| GROUND_Z50_M | Median interpolated terrain at the same supported roof cells |
| HEIGHT_P50_M | Median paired roof elevation minus terrain |
| HEIGHT_P95_M | 95th percentile of paired height differences |
| HEIGHT_MAX_M | Maximum paired height; sensitive to equipment/outliers |
| FOOTPRINT_M2 | Original polygon area |
| AOI_PCT / PARTIAL_AOI | Geometric share inside the raster / truncation flag |
| GRID_CELLS | Footprint cell centers inside the raster |
| ROOF_CELLS / ROOF_COV_PCT | Paired roof/ground cells and their share of GRID_CELLS |
| NEG_H_CELLS | Negative heights, retained for inspection |
| HEIGHT_STATUS | UNVALIDATED plus missing-support, partial-AOI, negative-height, or tiny-polygon flags |

The percentile of roof-minus-ground is computed cell by cell; subtracting separate roof and ground percentiles gives a different statistic on slopes. Cells are equally weighted, not individual LAS points. Overlapping footprints are processed independently. Outside buildings and polygons without cell centers retain records with null heights.

Support below 80% is a review flag, not a calibrated acceptance criterion. Roof elevation, height above interpolated terrain, eave height, and a zoning ordinance's building height are different measurements. These outputs do not measure finished-floor elevation.

## Drainage interpretation

ArcGIS Derive Continuous Flow routes on the original DTM with D8 and NORMAL edge behavior. The workflow does not fill the DTM before routing. A separate Fill operation computes a depression-depth diagnostic afterward; that surface never feeds routing.

No real-depression inventory is supplied, so some genuine closed basins may be routed through. Roads, bridges, retaining walls, classification errors, and missing culverts can redirect modeled routes. Underground storm drains are absent. For catchment work, process the contributing watershed and reconcile the drainage network before clipping to Millcreek.

The boundary mask traces downstream from every valid raster edge and cell beside missing terrain. It is conservative: 1 means potentially incomplete upstream coverage; 0 is not proof of a complete watershed. The neighborhood mask marks the separate edge effect on local terrain statistics. Ground-distance values measure raster support, not vertical error.

## Next useful datasets, in order

| Priority | Product family | Reuse / additional inputs |
|---|---|---|
| 1 | Citywide terrain, slope, contours, support coverage | Classified ground; terrain mosaic, seam checks, storage plan |
| 1 | Building heights and simple 3D massing | Reviewed county footprints and roof classes; roof planes/multipatches need a separate model |
| 1 | Canopy area and height classes by parcel, park, neighborhood, and ROW | Existing CHM/cover tool plus authoritative zones; retain missing-area bounds |
| 1 | Residential, park, and foothill tree validation | Independent labels; review pitched roofs, canopy/eave contact, merges/splits, slopes |
| 2 | Drainage paths, depressions, catchments, culvert-review locations | Larger hydrologic extent, streams, storm drains, culverts, bridges, real depressions |
| 2 | Roof form, slope, aspect, ridge/eave estimates, 3D buildings | Roof-point segmentation and review; footprints alone do not define roof planes |
| 2 | Street/sidewalk/park shade at chosen dates and times | Reviewed surfaces/3D objects, surrounding context, target surfaces, scenarios |
| 2 | Solar-exposure and roof-solar screening | Roofs, surrounding obstructions, atmospheric/date assumptions |
| 2 | Viewsheds, visual impact, tower screening | Observer/target positions and heights; terrain and obstruction scenarios; not radio propagation |
| 2 | Planting opportunities and canopy-equity summaries | Canopy, parcels/ROW, impervious cover, utilities, easements, ownership, context layers |
| 3 | Vegetation height strata and vertical structure | Normalized point cloud, density QA; understory may be incompletely sampled |
| 3 | Land cover / impervious surfaces | Date-matched multispectral imagery and labels; height or intensity alone is insufficient |
| 3 | Canopy/building/terrain change | A second compatible acquisition plus registration and seasonal checks |
| 3 | Biomass/carbon or fuel screening | Species/forest-type information, local models, field calibration |
| 3 | Grading/earthwork and terrain constraints | Proposed design or earlier surface, aligned datums and suitable accuracy |

Species, DBH, condition, legal ownership, exact stems, structural roof condition, finished floors, and hydraulic flood depth are not delivered as measured attributes.

The delivery is at **G:\GIS\2024 Lidar for tower extract**, a 52-tile extract of the 1363-tile 2023 Salt Lake Valley collection. Compare its footprint against the city and desired contributing watersheds before a full run; the folder name establishes neither the capture year nor complete city coverage. The 39 grid cells missing from the extract all exist in the published index and can be obtained from UGRC — see [delivery provenance](DELIVERY_PROVENANCE.md). Preserve the original LAS and delivery metadata.

## Other project work

Root utilities remain separate: polygon adjacency coloring, Bad Elf GNSS metadata fields, and converting a sketch layer into a production schema. GNSS metadata and schema templates could support later field verification, but they are not LiDAR classification inputs. Existing review notes and the September 17 footprint comparison remain intact.

## References

- [Esri: How Surface Parameters works](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/3d-analyst/how-surface-parameters-works.html) explains the local terrain measures.
- [Esri: Derive Continuous Flow](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/spatial-analyst/derive-continuous-flow.html) documents routing, true depressions, and edge behavior.
- [Esri: LAS Building Multipatch](https://doc.esri.com/en/arcgis-pro/latest/tool-reference/3d-analyst/las-building-multipatch.html) describes a later 3D building path.
- [Esri: Modeling solar radiation](https://pro.arcgis.com/en/pro-app/3.5/tool-reference/spatial-analyst/modeling-solar-radiation.htm) explains terrain and surface obstructions.
- [USGS: LiDAR applications](https://www.usgs.gov/3d-elevation-program/lidar-applications-and-business-uses-factsheets) provides broader planning and infrastructure uses.

