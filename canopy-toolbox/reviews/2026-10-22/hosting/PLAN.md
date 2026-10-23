# Hosting the lidar products for web GIS: plan (October 22, 2026)

Brian asked on October 22 for plans in the order the hosting research suggested, and for work to start on them. The research
(two Sonnet agents, summarised in the session) is not independently verified; the points this plan relies on are marked
"(research)" and each step checks them before depending on them.

**Rule for every step: build and verify locally, then stop.** Nothing is uploaded to ArcGIS Online or to cloud storage, and
nothing is published or shared, without Brian's go-ahead for that specific upload. Publishing is outward-facing and costs
credits; the city GIS is never written from the repo. Each step ends with a file that is ready to upload, a record of how it
was checked, and the exact upload step written out for Brian.

## Decisions for Brian (none blocks the local work)
1. **Cloud bucket for the raster masters:** which provider (Cloudflare R2, AWS S3, Azure Blob, or one the city already
   uses), public or private, and who owns the account. Without one, step 1 stops at local COGs.
2. **ArcGIS Image for ArcGIS Online:** whether to buy it. It is needed for tiled imagery layers that keep pixel values and for
   raster analysis online (research: whether it applies to Professional Plus is unclear; ask Esri).
3. **Audience per product:** public web map or internal staff, which decides sharing and which format fits (table below).

## Steps, in the research's order

| # | Step | Products | Output (local) | Where it runs |
|---|---|---|---|---|
| 1 | Cloud-optimised raster masters | 0.5 m float and mask rasters | COGs on the SSD, validated | its own session |
| 2 | Small feature layers | 22,042 footprints with heights, 13 canopy zones | a publish-ready file geodatabase | this session |
| 3 | Scene layer for buildings | LOD1.2 blocks and LOD2.0 roofs (massing run) | `.slpk` packages | this session, after the massing |
| 4 | Vector tiles | slope classes, 527,140 treetops, 400,063 crowns, 2 m contours | `.vtpk` packages | the slope session |
| 5 | Hillshade tiles and 3D ground | hillshade, terrain | a raster `.tpkx` and an elevation (LERC) `.tpkx` | its own session |
| 6 | Trial a float COG in a web app | one float COG (slope percent) | a local ArcGIS Maps SDK page reading the COG | the step 1 session |

### 1. Cloud-optimised raster masters
- Inputs: the October 22 library rasters (`chm_m`, `terrain_m`, `roof_elevation_m`, `roof_height_m`, `observed`,
  `vegetation_support`, `building_occlusion`, `building_sources`) and the terrain products (`slope_degrees`, `slope_percent`,
  `aspect_degrees`, `profile_curvature`, `tangential_curvature`, `hillshade`, `terrain_position_m`,
  `terrain_neighborhood_complete`).
- Method: GDAL's COG driver. Float rasters lossless (DEFLATE with the floating-point predictor, which is the research's
  safest choice for Esri clients; compare ZSTD and LERC with a stated error on one raster and record the sizes).
  Overviews: NEAREST for aspect, masks and class rasters, AVERAGE for continuous values.
- Checks: each COG validates as a COG; every cell equals its source (NoData included) for the lossless ones; sizes recorded.
- Stop: the upload, until decision 1.

### 2. Small feature layers
- A publish-ready file geodatabase with the footprints and their height statistics, and the canopy cover zones. Readable
  field aliases, the estimate warning in the metadata, no working fields.
- Checks: record counts and values equal the library's.
- Stop: publishing as hosted feature layers (research: about 240 credits per GB per month; both are small).

### 3. Scene layer for buildings
- From the citywide massing (`runs\massing-20261022`, LOD1.2 blocks and LOD2.0 roofs; reviews/2026-10-22/massing): Create
  3D Object Scene Layer Package, one `.slpk` per level, with the height statistics as attributes.
- Checks: feature counts equal the multipatch counts; the package opens in Pro.
- Stop: sharing the package (research: under 1 GB uploads in the browser; larger needs Share Package).

### 4. Vector tiles
- The slope-class session already makes a `.vtpk` and works out how to script a Pro map; it extends that to treetops (points),
  crowns (polygons) and contours (lines, INDEX lines styled heavier).
- Checks: feature counts in the source layers; the packages open in Pro; tile levels suited to each layer.
- Stop: uploading the packages.

### 5. Hillshade tiles and 3D ground
- The hillshade as a raster tile package (Web Mercator scheme). The terrain as an elevation tile package (LERC, the ArcGIS
  Online elevation tiling scheme) for scenes.
- Checks: tile counts and levels recorded; elevation values at sample points match the terrain within the LERC tolerance.
- Stop: uploading and publishing the tile and elevation layers.

### 6. Trial a float COG in a web app
- A small local page with the ArcGIS Maps SDK for JavaScript `ImageryTileLayer` reading the slope COG from a local server
  that supports HTTP range requests and CORS (research: COG support is beta).
- Checks: the layer draws, a click returns the true float slope value, and a class renderer works.
- Stop: no hosting; the result decides whether the bucket route is worth it.

## Status
- Started October 22: steps 1 and 6 in one session, step 5 in another, step 4 sent to the slope session, steps 2 and 3 here.
- Step 2 ready (October 22): [feature-layers](feature-layers/README.md), 22,042 buildings and 13 canopy zones, checked equal to the library.
- Step 3 ready (October 22): [scene-layers](scene-layers/README.md), 21,561 buildings in each of two packages (9.2 and 19.3 MB),
  from the citywide [massing](../massing/README.md).
