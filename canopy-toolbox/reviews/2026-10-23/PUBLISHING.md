# Where the lidar products stand, and the road to ArcGIS Online (October 23, 2026)

Brian asked on the morning of October 23 for a roll-up of the overnight work (slope, hillshade, COGs, vector tiles), the
steps left, and a start on getting it all into ArcGIS Online with apps for the public and staff. This note reads the
records; it reruns nothing. **Nothing has been uploaded, published or shared.**

## 1. What finished overnight
Every step of the [hosting plan](../2026-10-22/hosting/PLAN.md) is built and verified locally, and every output is on the
SSD (H: on the laptop, under `lidar\2023-salt-lake-valley\runs`). Checked on disk this morning.

| Plan step | Product | Run folder | Size | Record |
|---|---|---|---:|---|
| Terrain | slope, aspect, curvature, hillshade, terrain position, 2 m contours at 0.5 m | `terrain-city-20261022` | 16 GB | [terrain-city](../2026-10-22/terrain-city/README.md) |
| 1 | 16 COG masters, lossless, all verified cell for cell | `cog-20261022` | 4.0 GB of COGs | [cogs](../2026-10-22/hosting/cogs/README.md) |
| 2 | Feature layers: 22,042 buildings, 13 canopy cover zones | `hosting-features-20261022\features.gdb` | 76 MB | [feature-layers](../2026-10-22/hosting/feature-layers/README.md) |
| 3 | Building scene layers, LOD1.2 blocks and LOD2.0 roofs | `scene-layers-20261022` | 9 + 19 MB | [scene-layers](../2026-10-22/hosting/scene-layers/README.md) |
| 4 | Vector tiles: slope classes (129,352 polygons), treetops, crowns, contours | `slope-tiles-20261022`, `vector-tiles-20261022` | 71 MB | [vector-tiles](../2026-10-22/hosting/vector-tiles/README.md), [slope-tiles](../2026-10-22/slope-tiles/README.md) |
| 5 | Hillshade tile package, terrain elevation package (LERC 0.01 m), rebuilt October 23 for the datum | `tiles-20261023` | 134 + 228 MB | [tiles](../2026-10-22/hosting/tiles/README.md) |
| 6 | Float COG in an ArcGIS Maps SDK page: draws, exact identify, class renderer | (local servers) | | [cogs](../2026-10-22/hosting/cogs/README.md#web-trial-slope-percent-in-the-arcgis-maps-sdk) |

The records of steps 1, 4, 5 and 6 were built on three side branches (`claude/cog-masters-7bc671`,
`claude/slope-vector-tiles-d3ff56`, `claude/tiles-elevation-148a15`) and merged into `canopy/classification-refinement`
on October 23; the only conflicts were the one-line entries in `AGENTS.md`, all kept.

## 2. Open before publishing

### Datum: resolved October 23
The packages did not all take NAD83(2011) to WGS84 / Web Mercator the same way: the hillshade and terrain `.tpkx` used no
transformation and sat **1.197 m on the ground** (1.58 m in Web Mercator) from the buildings and vector tiles. They were
rebuilt on October 23 to match; every packaged layer now carries the same transformation, each proven from its own output:

| Package | Transformation | How it is known |
|---|---|---|
| Building scene layers (.slpk) | `WGS_1984_(ITRF08)_To_NAD_1983_2011` | named in `make_slpk.py` and passed to the tool |
| Vector tiles (slope, treetops, crowns, contours) | `WGS_1984_(ITRF08)_To_NAD_1983_2011` | read from the tiles: vertices 6 cm from the transformed source, 0.7-1.6 m from the untransformed ([vector-tiles](../2026-10-22/hosting/vector-tiles/README.md#datum)) |
| Hillshade and terrain (.tpkx), rebuilt | `WGS_1984_(ITRF08)_To_NAD_1983_2011` | read from the tiles: steep terrain within 0.012 m transformed, 2.8 m untransformed ([tiles](../2026-10-22/hosting/tiles/README.md#datum-rebuilt-october-23)) |
| Feature layers (features.gdb), reprojected | `WGS_1984_(ITRF08)_To_NAD_1983_2011`, to Web Mercator before upload | every vertex within 0.07 mm of Esri's transformed projection, 1.58 m from the untransformed ([feature-layers](../2026-10-22/hosting/feature-layers/README.md)) |
| COGs (EPSG:6341) in an ArcGIS Maps SDK web map | `WGS_1984_(ITRF08)_To_NAD_1983_2011`, chosen by the SDK (5.1.27) with nothing named | identify and drawn cells within 7 mm of the transformed position, 1.20 m from the untransformed; the hosted contours' vertices fall on 2 m multiples of the COG terrain with no shift (best shift 0 on a 7 cm grid) ([cog-alignment](cog-alignment/README.md)) |

Manage Tile Cache ignores transformation settings and an elevation cache refuses a map as its source, so the rebuild
translates the two sources' georeferencing by the transformation's 1.197 m offset (constant to 0.81 mm over the mosaic);
no cell changes. The October 22 packages (`runs\tiles-20261022`) are superseded and left on the SSD. The feature layers
are now projected to Web Mercator with the same transformation before upload (`runs\hosting-features-20261023`).

### Brian's decisions (made October 23)
1. **Cloud bucket** for the COGs: **Azure**, the city's own subscription, in a new storage account with a **public-read
   container** and CORS for the city's sites (proposal in section 3). The Azure CLI and AzCopy may be installed with winget.
2. **ArcGIS Image for ArcGIS Online: not now.** The web-app route from Azure does not need it; revisit when someone needs
   raster analysis online.
3. **Audience:** public for terrain, slope classes, hillshade, contours, LOD1.2 buildings and the canopy cover zones (with
   the building heights). **Staff only** for treetops and crowns until the SUSPECT review, for the LOD2.0 roofs, and for the
   Overture and address disagreement layers. Each layer is shared only after it has been checked online.
4. **Slope cleanup:** publish the 4 m2 minimum mapping unit version (129,352 polygons). The uncleaned classes (924,458
   polygons) only if someone needs exact class areas.
5. **Uploads:** run from the repo with `upload.py`, one item at a time, each checked before Brian approves the next.
6. **Later the same day:** Brian has looked at the layers ("they look fine"). **All eight go public**, treetops and crowns
   included, replacing the staff-only line in decision 3; Brian shares them himself. He approved all three Azure steps
   (create the storage, open public read, upload the COGs). The layers get professional styling (symbology, blend modes,
   legends) and full item text (summaries, descriptions, tags, a data dictionary), done from the repo. The uploaded package
   items cannot simply be deleted because the hosted layers depend on them; what to do with them is to be worked out.

### Overture licences (checked October 23)
From `Z:\GIS\overture\2026-10-21.0\millcreek\LICENSES.md` (the Overture comparison session; not legal advice):
- **ODbL, share-alike:** buildings (OSM and Microsoft ML outlines), road segments, land use, water, infrastructure. A map or
  tile layer drawn from them is a Produced Work (attribution only: "© OpenStreetMap contributors, Overture Maps
  Foundation"). A **queryable or downloadable** layer of them, or a City layer built from them, must be offered under ODbL.
  That covers the candidate footprints: keep them staff-only, and ask the City Attorney before any public release.
- **Addresses:** National Address Database, public domain (keep USDOT's disclaimer). **Places:** CDLA-Permissive-2.0.
  **Land cover:** ESA WorldCover, CC BY 4.0 (credit it wherever it is shown).
- The 2.8 ft address offset was the comparison script's own default transformation, not a difference in the data: with
  an ITRF transformation the City and Overture points agree to 0.01 m. The building comparison had the same default and
  has been rerun with ITRF08.

### Not ready to go public
- The **LOD2.0 roofs** are marked experimental, not checked against roof shapes. LOD1.2 is the one to publish.
- **Vector tiles carry no attributes**: no pop-ups, identify or filters on treetops, crowns or slope. An app that needs a
  tree's height or crown size on click also needs a hosted feature layer of it, which costs more (feature storage is billed
  far above tile storage).
- **Drawing the COGs in the SDK** (5.1.27) has one fault: a float COG whose first draw uses a class breaks renderer and
  goes straight to a large scale (a deep link, say) draws coarse tiles in a repeating grid and stays wrong. Open at the
  full extent, or give the layer its classes after its first draw, and it draws correctly at every place and zoom tested,
  the partial last tile column and row included ([cog-drawing](cog-drawing/README.md)). Identify (exact values on click)
  was never affected.
- Treetops and crowns are unvalidated detections; the 32,986 SUSPECT treetops and calibration sample 2 are unreviewed.

## 3. Uploading
[upload.py](../2026-10-22/hosting/upload/README.md) uploads and publishes one item per command, only with `--go`, private
to you, never sharing or deleting (`upload.py list` shows the status). Each README also has the browser steps
(Content > New item > Your device).

| Order | Item | Becomes | Size | Credits a month (Esri rates read October 22) |
|---:|---|---|---:|---:|
| 1 | `features.gdb` (`upload.py features`) | hosted feature layers: buildings, cover zones | 7.8 MB | a few |
| 2 | `millcreek_slope_classes.vtpk`, `millcreek_contours.vtpk` | hosted vector tile layers | 29 MB | < 0.1 |
| 3 | `millcreek_hillshade_20261023.tpkx` | hosted tile layer | 134 MB | about 0.2 |
| 4 | `millcreek_treetops.vtpk`, `millcreek_crowns.vtpk` | hosted vector tile layers | 42 MB | < 0.1 |
| 5 | `buildings_lod12.slpk` | hosted scene layer | 9 MB | < 0.1 |
| 6 | `millcreek_terrain_20261023.tpkx` | hosted elevation layer | 228 MB | about 0.3 |
| 7 | the 16 COGs | Azure Blob storage (below), then a web app | 4 GB | Azure, not credits |

**Uploaded so far** (account GISMillcreek, folder Millcreek LiDAR 2023, all private; full log in
`runs\hosting-uploads\uploads.json`):
- `features`, October 23: Feature Service `d5effaee6c66497eaeb64e4c2e0f496e` (package item `ee182c9a7eec4994b7e19d2be8dd27b5`).
  Checked online: 22,042 buildings (21,562 with a roof height) and 13 zones, Web Mercator, field aliases kept, city canopy
  25.59%, positions identical to the local file, summary carries the warning. Hosted size 21.5 MB (about 5 credits a month
  at 2.4 credits per 10 MB).
- `slope`, October 23: Vector Tile Service `3b5b1a9110f14e93af68752be89e0df2` (package item
  `bec13573a71c4df2b4642fda4a559021`). Checked online: Web Mercator, 512-pixel tiles, levels 0-17; the style's six fill
  layers carry the class labels and YlOrRd colours in order; 16 tiles fetched at levels 10, 13, 15 and 16 are byte for byte
  the package's (the package's deepest level is 16 here; clients overzoom). Hosted size 22.6 MB (under 0.1 credits a month).
  Checking an online tile needs the signed-in session (`gis.session`); `GIS("pro")` gives no token for plain requests.
- `contours`, October 23: Vector Tile Service `50573eeba93f405a869a1d78a08d68e8` (package item
  `377dd1de82204e63addb6905a9322bb3`). Checked online: Web Mercator, levels 10-17 (1:288,895 inward); index contours from
  level 10 and the 2 m lines from level 14, as built; 21 tiles fetched at levels 10-16 are byte for byte the package's.
  Hosted size 6.6 MB. **One difference from the README:** both line layers are 1.33 px (1 pt) wide in the style; the
  index lines are set apart only by opacity (solid against 60%). The script asked for 1.2 pt and 0.5 pt, and the package's
  own style already has 1.33 px for both, so Pro's export flattened the widths. Fix in the style, not the tiles: save a
  copy of the style in ArcGIS Online's Vector Tile Style Editor with the index lines about 1.6 px and the 2 m lines about
  0.7 px, or set the widths when the layer is added to a web map.
- `hillshade`, October 23: Map Service (hosted tile layer) `cab8824e44384d479e1f302cdf34daf9` (package item
  `2d4f5092edfd4c54a9898a1a7dda5dd1`). Checked online: Web Mercator, 256-pixel PNG32 tiles on the ArcGIS Online scheme;
  16 tiles with data at levels 8, 12, 15, 17 and 18 are byte for byte the package's. Hosted size 134 MB (about 0.16
  credits a month once the package item is deleted). **During the publish the ArcGIS API made four HTTPS requests to
  www.arcgis.com without certificate verification** (urllib3 InsecureRequestWarning), although the signed-in session
  verifies certificates; the call site is inside the API, not `upload.py`. `upload.py` now logs the call stack of any such
  request to `runs\hosting-uploads\unverified-https.log`, so the terrain publish (the other `.tpkx`) will show where it
  comes from.
- `treetops`, October 23: Vector Tile Service `924b993cb23046cb87641253bcf786de` (package item
  `2dcae544e70c47589f8226dc0ad74351`). **Staff only** (decision 3): share with the organisation or a staff group, not the
  public, until the SUSPECT review. Checked online: Web Mercator, levels 14-17 (1:18,056 inward); the style's five circle
  layers carry the height classes (2-5, 5-10, 10-15, 15-20, 20 m and over) in YlGn, all 2.4 px; 13 tiles across every
  package level are byte for byte the package's. Hosted size 7.6 MB. No unverified HTTPS requests during this publish.
- `crowns`, October 23: Vector Tile Service `d9388dc83f894edbb63e0510a8c62fa8` (package item
  `d3ca707cda6544dd9962390c1e7e00db`). **Staff only**, as the treetops. Checked online: Web Mercator, levels 14-17; the
  style's five fill layers carry the treetop-height classes in YlGn with a dark green outline; 14 tiles across every
  package level are byte for byte the package's. Hosted size 33.8 MB. No unverified HTTPS requests.
- `buildings3d`, October 23: Scene Service `5082b5bd063a4a03847f2082dc3533d1` (package item
  `eb613927529347989755b0fcf9e9c8fa`). Checked online: a 3D object layer in WGS84 (4326) labelled EGM96 (5773), as
  packaged (heights are NAVD88 metres; scene-layers README); z from 1,294.1 to 1,764.2 m; 43 fields including FP_ID and the
  roof-height statistics; the service's own FP_ID statistics give 21,561 buildings summing to 237,493,394, IDs 1 to 22,042,
  exactly the source's. Hosted size 9.3 MB. No unverified HTTPS requests.
- `terrain`, October 23: Image Service `ce1680a5196e458ebfb60ead5150b946`, type keyword **Elevation 3D Layer** (package
  item `7a520038be1b4e55accdfe6bed3a0a71`). Checked online: F32, one band, LERC, 257-pixel elevation tiles, TilesOnly;
  the stored tiles per level equal the package's (108, 398, 1,312 and 4,864 at levels 15-18; 6,754 in all; "PARTIAL"
  in the admin status only means the rectangle would hold more than the area of interest); 17 tiles with data at levels
  8, 12, 15, 17 and 18 are byte for byte the package's, elevations 1,290.8 to 2,146.6 m. Hosted size 228.1 MB (about
  0.27 credits a month once the package item is deleted). Tiles returned 404 for a minute or two after `upload.py`
  finished, while ArcGIS Online imported the cache (`cacheExecutionStatus: PROCESSING`); they served once it read `NONE`.
  No unverified HTTPS requests, so the four during the hillshade publish come from the map-service (tile layer) path
  only.

**All eight items are published** (private). Next, in ArcGIS Online: look at each in Map Viewer or Scene Viewer, delete
the eight package items, then share by audience (decision 3). The 3D check is a web scene with `terrain` in the Ground
above World Elevation and `buildings3d` on it.

Delete each package item once its layer works, so storage is not counted twice. Publishing does not share; share each
layer only once its audience is decided.

### The COGs on the city's Azure (proposal; nothing created)
The city's estate ([millcreek-azure](https://github.com/buschbrian/millcreek-azure)) is one subscription, *Azure Cloud –
Brian (Application Development)*, with Brian as its only Owner. Its one storage account, `stmillcreekpipeline`, holds the
minutes pipeline's file share and has public blob access off, so the COGs get their own account rather than loosening that one:
- **A new resource group and account**, for example `rg-millcreek-lidar` and `stmillcreeklidar` in westus3 beside the
  rest: StorageV2, Standard LRS, hot tier, HTTPS only, TLS 1.2. One container, `cogs`, under the dated prefix
  `millcreek-lidar/20261022/` the COG README's recipes already use.
- **Read access:** public read on that container only (the account must allow blob public access), or private with a
  long-lived read-only SAS in the web app. Public is simplest for a public viewer; these are planning products, not
  sensitive data, but it is the city's call.
- **CORS** on the blob service: GET, HEAD and OPTIONS from the city's web origins (`https://*.gis.millcreekut.gov`,
  `https://*.arcgis.com`, and `*` only while testing), allowing the `Range` header and exposing `Content-Range`,
  `Accept-Ranges`, `Content-Length` and `ETag`, exactly as the local trial server sent them.
- **A friendly address** later: `lidar.gis.millcreekut.gov` in the city's zone. Blob storage serves a custom domain only over
  HTTP, so HTTPS on it needs Azure Front Door (or a CDN profile) in front; the plain `blob.core.windows.net` address works
  over HTTPS without it.
- **Cost:** about 4 GB of hot LRS storage is well under a dollar a month; reads are billed as egress after Azure's
  monthly free allowance, and a viewer reads one tile at a time (the trial's full-city first draw was 1.2 MB).
- **Tools:** neither the Azure CLI nor AzCopy is installed on the laptop. The upload is the AzCopy recipe in the
  [COG README](../2026-10-22/hosting/cogs/README.md#uploading-once-brian-picks-a-bucket), followed by the range-request check
  there. The new account and its settings should go into `millcreek-azure`'s inventory and runbooks like the rest of the
  estate.

Creating the account, opening public read and uploading are each Brian's go-ahead.

The uploads can also be scripted with the ArcGIS API for Python (`gis.content.add` then `publish`), in the same way
`add_badelf_fields_to_agol.py` connects (`GIS(url, username, password)`), so each one is a single command run on Brian's
go-ahead. Not written yet.

## 4. Applications, a first sketch
| App | Audience | Built from | ArcGIS Online app |
|---|---|---|---|
| Slope and terrain viewer | staff (planning, engineering); public later | slope classes, contours, hillshade, building heights | web map + Instant Apps (Sidebar or Basic) |
| Tree canopy explorer | public | cover zones, crowns, treetops, hillshade | web map + Instant Apps or Experience Builder; pop-ups need the feature layers |
| Canopy cover by zone | public and council | the 13 cover zones (October 19 against October 22) | Dashboard |
| Millcreek in 3D | public | LOD1.2 buildings on the city terrain, treetops as 3D trees | web scene + Instant Apps 3D Viewer |
| How the lidar products were made | public | method, limits, the estimate warning | StoryMap |
| SUSPECT treetop review | staff | calibration sample 2 as an editable layer | Field Maps or a Survey123 form |

Every app carries the estimate warning: these are unvalidated lidar planning estimates, not surveyed or field-verified data.
