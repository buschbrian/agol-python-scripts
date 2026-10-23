# Where the lidar products stand, and the road to ArcGIS Online (October 23, 2026)

Brian asked on the morning of October 23 for a roll-up of the overnight work (slope, hillshade, COGs, vector tiles), the
steps left, and a start on getting it all into ArcGIS Online with apps for the public and staff. This note reads the
records; it reruns nothing. **Nothing has been uploaded, published or shared.**

## 1. What finished overnight
Every step of the [hosting plan](../2026-10-22/hosting/PLAN.md) is built and verified locally, and every output is on the
SSD (H: on the laptop, under `lidar\2023-salt-lake-valley\runs`). Checked on disk this morning.

| Plan step | Product | Run folder | Size | Record (branch) |
|---|---|---|---:|---|
| Terrain | slope, aspect, curvature, hillshade, terrain position, 2 m contours at 0.5 m | `terrain-city-20261022` | 16 GB | [terrain-city](../2026-10-22/terrain-city/README.md) (here) |
| 1 | 16 COG masters, lossless, all verified cell for cell | `cog-20261022` | 4.0 GB of COGs | `hosting/cogs/README.md` (`claude/cog-masters-7bc671`) |
| 2 | Feature layers: 22,042 buildings, 13 canopy cover zones | `hosting-features-20261022\features.gdb` | 76 MB | [feature-layers](../2026-10-22/hosting/feature-layers/README.md) (here) |
| 3 | Building scene layers, LOD1.2 blocks and LOD2.0 roofs | `scene-layers-20261022` | 9 + 19 MB | [scene-layers](../2026-10-22/hosting/scene-layers/README.md) (here) |
| 4 | Vector tiles: slope classes (129,352 polygons), treetops, crowns, contours | `slope-tiles-20261022`, `vector-tiles-20261022` | 71 MB | `hosting/vector-tiles/README.md`, `slope-tiles/README.md` (`claude/slope-vector-tiles-d3ff56`) |
| 5 | Hillshade tile package, terrain elevation package (LERC 0.01 m) | `tiles-20261022` | 134 + 228 MB | `hosting/tiles/README.md` (`claude/tiles-elevation-148a15`) |
| 6 | Float COG in an ArcGIS Maps SDK page: draws, exact identify, class renderer | (local servers) | | `hosting/cogs/README.md` (`claude/cog-masters-7bc671`) |

The records of steps 1, 4, 5 and 6 are on three side branches, all forked from `7ecffe4` and not yet merged into
`canopy/classification-refinement`. Each adds its own folder under `reviews/2026-10-22/` and one line to `AGENTS.md`, so
the merge should only conflict on that file.

## 2. Open before publishing

### A datum mismatch between the packages (about 1 m)
The packages do not all take NAD83(2011) to WGS84 / Web Mercator the same way:

| Package | Transformation | Where it is recorded |
|---|---|---|
| Building scene layers (.slpk) | `WGS_1984_(ITRF08)_To_NAD_1983_2011` | `make_slpk.py`, set explicitly |
| Vector tiles (slope, treetops, crowns, contours) | `WGS_1984_(ITRF08)_To_NAD_1983_2011` | each package's `.aprx` map CIM (Pro's default for the map; read October 23) |
| Hillshade and terrain (.tpkx) | **none** (NAD83(2011) taken as WGS84) | `package_tiles.py`, `geographicTransformations = None` |
| Feature layers (features.gdb, EPSG 6341) | decided by ArcGIS Online when it projects them | not tested |

In Utah the two choices differ by about 1 m, so the buildings and vector tiles would sit about a metre off the hillshade
and off the ground in a web scene. The ITRF08 transformation is the one that matches Esri's WGS84 basemaps and World
Elevation, and four of the six packages already use it, so the fix is to rebuild the two `.tpkx` with it (the hillshade cache
took 9 minutes and the terrain 1 minute) and re-run their value checks with the same projection. Publishing the feature
layers projected to Web Mercator with the same transformation takes the guess out of the last row. Until then, any single
layer can go up on its own; the 3D scene (buildings on the city terrain) should wait.

### Brian's decisions (from the plan, still open)
1. **Cloud bucket** for the COGs (R2, S3, Azure or the city's). Gates only the COGs.
2. **ArcGIS Image for ArcGIS Online**: gates the COGs as hosted imagery with pixel values and online raster analysis. The
   web-app route from a bucket does not need it.
3. **Audience per product** (public or internal), below.
4. **Slope cleanup**: keep the 4 m2 minimum mapping unit (129,352 polygons; middle classes lose up to 15% of their area,
   the "steeper than" areas hold within 0.54 points) or publish the uncleaned classes (924,458 polygons).

### Not ready to go public
- The **LOD2.0 roofs** are marked experimental, not checked against roof shapes. LOD1.2 is the one to publish.
- **Vector tiles carry no attributes**: no pop-ups, identify or filters on treetops, crowns or slope. An app that needs a
  tree's height or crown size on click also needs a hosted feature layer of it, which costs more (feature storage is billed
  far above tile storage).
- Treetops and crowns are unvalidated detections; the 32,986 SUSPECT treetops and calibration sample 2 are unreviewed.

## 3. Uploading
Ready for the browser upload now (Content > New item > Your device), each with written steps in its README:

| Order | Item | Becomes | Size | Credits a month (Esri rates read October 22) |
|---:|---|---|---:|---:|
| 1 | `features.gdb` (via Pro, Share > Web Layer) | hosted feature layers: buildings, cover zones | a few MB | a few |
| 2 | `millcreek_slope_classes.vtpk`, `millcreek_contours.vtpk` | hosted vector tile layers | 29 MB | < 0.1 |
| 3 | `millcreek_hillshade_20261022.tpkx` (after the datum rebuild) | hosted tile layer | 134 MB | about 0.2 |
| 4 | `millcreek_treetops.vtpk`, `millcreek_crowns.vtpk` | hosted vector tile layers | 42 MB | < 0.1 |
| 5 | `buildings_lod12.slpk` | hosted scene layer | 9 MB | < 0.1 |
| 6 | `millcreek_terrain_20261022.tpkx` (after the datum rebuild) | hosted elevation layer | 228 MB | about 0.3 |
| 7 | the 16 COGs | bucket, then a web app or ArcGIS Image | 4 GB | decision 1 or 2 |

Delete each package item once its layer works, so storage is not counted twice. Publishing does not share; share each
layer only once its audience is decided.

The uploads can also be scripted with the ArcGIS API for Python (`gis.content.add` then `publish`), in the same way
`add_badelf_fields_to_agol.py` connects (`GIS(url, username, password)`), so each one is a single command run on Brian's
go-ahead. Not written yet.

## 4. Applications, a first sketch
| App | Audience | Built from | ArcGIS Online app |
|---|---|---|---|
| Slope and terrain viewer | staff (planning, engineering); public later | slope classes, contours, hillshade, building heights | web map + Instant Apps (Sidebar or Basic) |
| Tree canopy explorer | public | cover zones, crowns, treetops, hillshade | web map + Instant Apps or Experience Builder; pop-ups need the feature layers |
| Canopy cover by zone | public and council | the 13 cover zones (October 19 against October 22) | Dashboard |
| Millcreek in 3D | public | LOD1.2 buildings on the city terrain, treetops as 3D trees | web scene + Instant Apps 3D Viewer (after the datum fix) |
| How the lidar products were made | public | method, limits, the estimate warning | StoryMap |
| SUSPECT treetop review | staff | calibration sample 2 as an editable layer | Field Maps or a Survey123 form |

Every app carries the estimate warning: these are unvalidated lidar planning estimates, not surveyed or field-verified data.
