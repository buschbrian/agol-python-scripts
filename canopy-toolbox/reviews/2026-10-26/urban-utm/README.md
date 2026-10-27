# Existing buildings, elevation and basemap in UTM 12N for a local ArcGIS Urban model (October 26-27, 2026)

On October 26 Brian approved publishing the roofer LoD2.2 three-way hybrid as the ArcGIS Urban existing buildings, **organization-only**.
He chose **NAD83(2011) UTM 12N, metres** for the Urban model, because every LiDAR 3D product is native UTM. A local Urban model gets no
default buildings or elevation: both must be custom layers in the model's own coordinate system. The public October 25 hybrid is WGS84
for global scenes, so these items are separate UTM copies. Brian created the local Urban model on October 27; on the same day he asked for
a global (Web Mercator) model beside it, with WGS84 buildings carrying FLOORS ([The Urban models](#the-urban-models-october-27)).

## Items

| Item | Layer ID | Source package ID | Type | Access |
|---|---|---|---|---|
| 3D buildings for ArcGIS Urban, UTM 12N | `b8e8ddaceac54876bd4c0cf3f31d92fd` | `c7702ec26f7843ad9572b797888557d6` | Scene Service (3DObject) | Layer: organization; package: private; both delete-protected |
| Building footprints for ArcGIS Urban, UTM 12N | `e74c2216aca54d7f8be2432768b64520` | `32ba9a96f01d43b690f8faa4ce4c6a15` | Feature Service, layer 0 `building_footprints` | Layer: organization; package: private; both delete-protected |
| Bare-earth terrain for ArcGIS Urban, UTM 12N 0.5 m | `83d1a892fd67408b9f8f9fcb754cd479` | `33b6ae61d34e4cd682c45fa42b229095` | Image Service (elevation) | Layer: organization; package: private; both delete-protected |
| Light basemap for ArcGIS Urban, UTM 12N (October 27) | `97b68288dbf14897bcad0c1646467b89` | `de73e628097f4de8ae742808c3b61edd` | Map Service (tile layer, PNG) | Layer: organization; package: private; both delete-protected |
| 3D buildings for ArcGIS Urban, Web Mercator (October 27) | `d4b852fd54314b8bb031fd5f5902fa3a` | `d07dc602a6714c99a098a0570354d2a3` | Scene Service (3DObject), WGS84 | Layer: organization; package: private; both delete-protected |

All of them are in the GISMillcreek folder **Millcreek LiDAR 2023**. No layer is shared with everyone or with a group, and anonymous
requests for the three layers return 403. The public items were not changed: scene layer `ce3617ac9b884bbcbee7c47a3e166999`, web scene
`5b5bdf4a63c9466fad5884039aa7357f` and the LOD1.2 layer `5082b5bd063a4a03847f2082dc3533d1` are still public, and their modified times
are recorded in [evidence/verification.json](evidence/verification.json). Do not delete a source package while its layer depends on it.

## The elevation finding

The existing public terrain `ce1680a5196e458ebfb60ead5150b946` **cannot** be the ground of a UTM local model, so a UTM terrain was
published. [Use 3D base layers](https://doc.esri.com/en/arcgis-urban/latest/help/help-3d-basemap.html) states these requirements:
- Base layers must be in the urban model's coordinate system.
- Default layers are not supported in local models, and a custom elevation layer is required.
- The elevation layer "must have the same coordinate system and tiling scheme as the basemap."

The public terrain is Web Mercator on the ArcGIS Online elevation scheme.

**Before the model works, Urban needs a basemap.** It must be a UTM 12N tiled layer on the tiling scheme in
[elevation_scheme_utm12n.xml](elevation_scheme_utm12n.xml), and it must be in the organization's basemap gallery (Urban accepts only
gallery or ArcGIS Online basemaps). A tile package of the hillshade or imagery built with Manage Tile Cache on that XML (its format
changed from LERC to an image format) would meet the requirement. The basemap was built on October 27; see
[The basemap](#the-basemap-october-27-basemappy).

| Scheme property | Value |
|---|---|
| Coordinate system | NAD83(2011) / UTM zone 12N (EPSG 6341); the services report wkid 102059, latestWkid 6341 |
| Origin | X -5,120,900, Y 9,998,100 (the default for 6341) |
| Tiles | 256 x 256 (elevation tiles store 257 x 257 corner-registered pixels), 96 dpi |
| Levels | 0-14, resolution 8,192 m halving to **0.5 m**; scale 1:30,961,827.84 to 1:1,889.76 (Esri's 39.37 inches to the metre) |
| Format | LERC, maximum error 0.01 m, compact storage |

Why levels 0-14: the finest level matches the source's 0.5 m, so each finest-level pixel sits on a source cell corner. In UTM there is
no Mercator scale factor, so the Web Mercator scheme's level 18 would be 0.597 m here, coarser than the source. A basemap can extend
this scheme with finer levels (0.25 m and below).

## What was built (`urban_utm.py`)

Run from `canopy-toolbox` with ArcGIS Pro Python, `PYTHONNOUSERSITE=1` and `CANOPY_LIDAR_ROOT=H:\lidar`. The output is in
`H:\lidar\2023-salt-lake-valley\runs\urban-utm-20261026`.

```
python reviews/2026-10-26/urban-utm/urban_utm.py prepare   OUT
python reviews/2026-10-26/urban-utm/urban_utm.py slpk      OUT --test [--vcs 5703]
python reviews/2026-10-26/urban-utm/urban_utm.py slpk      OUT --vcs 5703
python reviews/2026-10-26/urban-utm/urban_utm.py footprints OUT
python reviews/2026-10-26/urban-utm/urban_utm.py scheme    OUT
python reviews/2026-10-26/urban-utm/urban_utm.py elevation OUT --pilot
python reviews/2026-10-26/urban-utm/urban_utm.py elevation OUT
python reviews/2026-10-26/urban-utm/urban_utm.py verify    OUT
```

- **Buildings.** The source is `roofer-city-v2-20261024\hybrid.gdb\buildings_three_way`: 21,561 multipatches, key `FP_ID`, absolute
  NAVD88 Z, no address field. It is copied to `urban.gdb\buildings`.
  - Big-integer, date-only, time-only and timestamp-offset fields were to be dropped first. The source has none
    ([evidence/prepare.json](evidence/prepare.json)).
  - `FLOORS` (LONG) is added and set to `HEIGHT_P95_M / 3.5 m` rounded half up (not Python's half-to-even), with a minimum of 1 and
    null where there is no height. No building lacks a height.
  - The copy is packaged by the shared [make_slpk.py](../../2026-10-22/hosting/scene-layers/make_slpk.py), which now takes a feature
    class and `--wkid` / `--vcs` / `--transformation`. The WGS84 + ITRF08 default and its other callers are unchanged. This package is
    6341 + NAVD88 height (5703) with no transformation.
  - The copy keeps OBJECTID, the 26 source attributes and FLOORS (28 fields on the hosted layer).
    It does not carry the October 24 roof-plane attributes of the public
    `buildings_hybrid_v2` package, because the task named `buildings_three_way` as the source.
  - It keeps `PARCEL_ID`, `SOURCE_ID` and `CITY` (identifiers, not owner or address).
- **Footprints.** Multipatch Footprint of the same copy, grouped by FP_ID, gives one polygon per building and none empty. Only
  `FP_ID`, `HEIGHT_P95_M`, `LEVEL` and `FLOORS` are kept, in 6341. The result is copied alone into
  `footprints\urban_footprints.gdb\building_footprints`, because upload.py publishes a whole geodatabase.
- **Elevation.**
  - Source: `millcreek-products-20261019\terrain_context.tif`, the unmasked lidar mosaic. The task named `terrain_m.tif`, which is
    identical on every city cell (terrain-city README) but masked to the city. In a local model this layer is the *only* ground, so the
    masked raster would drop to nothing at the city boundary.
  - No datum shift was needed: source and scheme are both 6341.
  - Caching: Manage Tile Cache on the imported scheme, then Export Tile Cache to `.tpkx`. The cache keeps
    `CacheTileContentType = Elevation` and `PixelType = 32_BIT_FLOAT` on this custom scheme. This was checked on a 1 km pilot window
    before the full build.

## Verification

| Check | Result |
|---|---|
| 20-building test package (7 Esri LOD1.2, 7 Esri LOD2.0, 6 roofer) | FP_ID 20 / 3,401 equal to source; 6341 (+5703 in the VCS variant, `gravity_related_height`, NAVD_1988); node Z 1,466.6-1,486.6 m |
| Full SLPK | **15,907,332 bytes**, SHA-256 `b2361f59d22f9a4064eee6ef601e3c185592edaf2a1f4b0a97a18ed8bae89381`; FP_ID **21,561 / 237,493,394** equal to source; 164 nodes, node Z 1,304.5-1,713.8 m |
| Package validation | One warning: "vertex normals may be required by Esri products" (below) |
| Hosted scene layer | 3DObject, 6341 + 5703, 28 fields incl. FLOORS; FP_ID **21,561 / 237,493,394**; LEVEL 20,730 / 647 / 184; FLOORS sum 32,836, min 1, max 12 |
| Footprint gdb | 21,561 polygons, FP_ID 21,561 / 237,493,394, unique; 4,710,583.49 m² |
| Hosted footprints | Polygon, 6341; FP_ID **21,561 / 237,493,394**; LEVEL_ counts as above; FLOORS sum 32,836 (1-12), 0 null; Shape__Area 4,710,583.49 m² (within 0.001 m² of local) |
| FLOORS distribution | 1: 11,894 · 2: 8,271 · 3: 1,294 · 4: 52 · 5: 25 · 6: 9 · 7: 6 · 8: 4 · 9: 5 · 12: 1 |
| Elevation .tpkx | **190,386,849 bytes**, SHA-256 `acf2c7bd1b1bad5f09d0ef95eff930aa2a7980f366f380ad470c538abd7d19a4`; 5,587 tiles (4,040 at 0.5 m, 3,222 with data); LERC headers all 0.01 m |
| Elevation values (300 city points, 150 flat / 150 steep) | Against the terrain bilinear at the pixel: max **0.0101 m**, median 0.0047 m; none missing. Against the containing cell: steep max 0.683 m (median 0.155), flat max 0.025 m |
| Hosted elevation | `esriImageServiceDataTypeElevation`, cacheType Elevation, 6341, LERC 256 px; origin and 15 LOD resolutions equal the scheme; 8 sampled level-14 tiles byte-identical to the package |
| Sharing | The three layers are `org`, not everyone and in no groups; the three packages are private; all six are protected. Anonymous item requests return 403 |
| Repository suite (ArcGIS Pro Python) | 512 run, 1 skipped, 5 errors, all in `test_fractal_las_writer` and `test_fractal_repeat`: `LasHeader` has no `copy` in Pro's laspy. None of those touch the changed files. `test_roof_release_summary`, which loads upload.py, passes |
| Item text | Applied from `reviews/2026-10-23/agol-metadata/urban_*.md`. A diff afterwards shows no difference on any property or field description |

Evidence, all copied from the run folder or written by `share_org.py`:
- [evidence/](evidence/): prepare.json, slpk*.json, footprints.json, elevation*.json, uploads.json, verification.json,
  normals-warning-check.json.
- [elevation_scheme_utm12n.xml](elevation_scheme_utm12n.xml): the tiling scheme.

**The normals warning.**
- In 6341, Create 3D Object Scene Layer Package writes no vertex normals. The same source packaged in WGS84 has normals for most nodes
  and validates without a warning ([evidence/normals-warning-check.json](evidence/normals-warning-check.json)).
- The original `buildings_three_way` packaged in UTM gives the same warning, so it is not caused by the copy or FLOORS. Clients
  compute shading when normals are absent.
- This is recorded, not fixed.

**Not verified.**
- The terrain, basemap and buildings draw in the local Urban model (October 27, below), seen from above only. The footprint layer
  is not used by the model.
- Convert existing buildings' attribute-driven mode reads "a numeric field in your existing buildings layer"
  ([July 2026 release notes](https://doc.esri.com/en/arcgis-urban/latest/get-started/get-started-release-notes.html)), which is the
  scene layer; FLOORS is on it. Not yet run.
- Whether Urban treats this footprint layer as the scene layer's "accompanying feature layer" is also undocumented. ArcGIS Online
  links a scene layer to a feature layer only when the scene layer is published from it, and this one was published from an SLPK.
- ArcGIS Online renamed `LEVEL` to **`LEVEL_`** in the footprint layer, because LEVEL is a reserved word. The scene layer keeps `LEVEL`.

## Uploading, sharing and the item text

- **Upload.** Each item went up with `reviews/2026-10-22/hosting/upload/upload.py urban_buildings|urban_footprints|urban_terrain --go`,
  one at a time.
  - upload.py now writes a UTM coordinates paragraph and this folder's records line for items marked `"datum": "utm"`, instead of the
    Web Mercator text.
  - It passes per-item `publish_parameters`: the footprints were published with `targetSR` 6341.
  - Its log `runs\hosting-uploads\uploads.json` has the entries; they are copied to evidence/uploads.json.
- **Sharing and protection.**

  ```
  python reviews/2026-10-26/urban-utm/share_org.py verify        # read-only; rewrites evidence/verification.json
  python reviews/2026-10-26/urban-utm/share_org.py apply --go    # layers to the organization, packages private, all protected
  ```

- **Item text** follows the October 23 house style: warning first, a FLOORS explanation, a data dictionary, a UTM coordinates block
  (`{{coordinates_utm}}`) and the planning-estimate terms. To change it, edit `urban_*.md`, then run `apply_metadata.py diff <key>`
  and `apply <key> --go`. Do not run `readback`: it rewrites the October 23 record. The ISO `metadata` step was not run for these
  items.

## The basemap (October 27, `basemap.py`)

Brian chose the UTM 12N local model over a Web Mercator global one, because the buildings and terrain are already UTM, and approved
publishing a light basemap **organization-only** as a hosted tile layer. Urban turns a model local when you select a projected basemap,
and that choice is the only route: the org had no UTM basemap.

```
python reviews/2026-10-26/urban-utm/basemap.py data   OUT   # hillshade of terrain_context.tif + linework projected to 6341
python reviews/2026-10-26/urban-utm/basemap.py map    OUT   # OUT\basemap\basemap.aprx, map "Urban UTM basemap"
python reviews/2026-10-26/urban-utm/basemap.py scheme OUT   # elevation scheme.xml with CacheTileFormat PNG, nothing else changed
python reviews/2026-10-26/urban-utm/basemap.py cache  OUT --pilot
python reviews/2026-10-26/urban-utm/basemap.py cache  OUT   # levels 0-14 on the elevation AOI, then .tpkx
python reviews/2026-10-26/urban-utm/basemap.py verify OUT   # package tileInfo against the hosted terrain's, field by field
```

- **Content.**
  - Hillshade: 315°, 45°, no shadows, z 1, the same parameters as terrain-city. It is computed fresh from the unmasked
    `terrain_context.tif`, because every existing hillshade is masked to the city: 45% of the extent is valid, against 67% for the
    mosaic.
  - Parcel lines draw from level 12.
  - Centerlines_Millcreek streets: CARTOCODE 1-8 are wider. Names show from level 9 (major) and level 11 (local).
  - The Millcreek boundary is dashed, over a 245/245/242 ground fill of the elevation AOI.
  - No buildings: Urban draws its own.
- **Linework.** Parcels (21,744), streets (2,995) and the boundary (1) come from Millcreek's hosted layers in State Plane Utah
  Central feet. They were projected to 6341 with **no datum transformation**, which leaves sub-metre offsets on a basemap.
- **Scheme.** It is the elevation scheme with only the tile format changed (LERC to PNG): the same origin, 256 px, 96 dpi and 15
  LODs. Levels were deliberately not added below 0.5 m, so the scheme stays identical to the terrain's.
- **Cache.** Mixed-format tiles are not used: PNG keeps the area outside the footprint transparent.
  - The pilot (1 km window, levels 12-14) took 41 s.
  - The full cache has 5,600 tiles; level 14 has 4,064.
  - Package: `millcreek_basemap_utm_20261027.tpkx`, **120,744,632 bytes**, SHA-256
    `d80cbd151ce744777ebf7bbcf9859ff9fe3c1649f9df6be7c9997e8ddacaf326`.
- **Upload.** `upload.py urban_basemap --go` published Map Service `97b68288dbf14897bcad0c1646467b89` from package
  `de73e628097f4de8ae742808c3b61edd`. The item text is upload.py's own, with credits for the Millcreek layers and the lidar; the
  `urban_*.md` metadata step was not run. The publish logged the same unverified-HTTPS warnings as the October 23 hillshade.
- **Sharing.** `share_org.py apply --go` shared the layer with the organization and delete-protected the layer and its package. It
  now includes the basemap and checks it with `check_basemap`.

| Check | Result |
|---|---|
| Package scheme against the hosted terrain's tileInfo | wkid 6341, origin, 256 x 256, 96 dpi and all 15 LODs equal ([evidence/basemap-verify.json](evidence/basemap-verify.json)) |
| Hosted service against the hosted terrain | Same five fields equal; PNG; `singleFusedMapCache` true; 9 sampled level-14 tiles byte-identical to the package ([evidence/verification.json](evidence/verification.json)) |
| Sharing | Layer `org`, no groups, protected; package private, protected. The October 26 items still pass |
| Pro local scene (6341) | The hosted basemap as a layer, the hosted terrain as Ground, the buildings scene layer. Buildings sit on the ground, and the draped street names fall on the hillshade's roads ([evidence/local-scene-check-900e-3900s.png](evidence/local-scene-check-900e-3900s.png), 900 E at 3900 S looking north) |

**The basemap gallery (October 27, Brian approved).** Urban lists only basemaps in the organization's basemap gallery or ArcGIS
Online basemaps. The gallery is the custom group "Basemaps" (`1ae1c70310cf457abe2a3e6dbf5a3243`, owned by GISMillcreek; the org's
`basemapGalleryGroupQuery`), which had 37 items, all Web Mercator or unspecified.
- `basemap.py webmap OUT --layer 97b68288dbf14897bcad0c1646467b89 --go` created web map **`8289e4be22534a9f99a7514c795a477b`**,
  "Millcreek light UTM 12N (ArcGIS Urban)". It is in 6341, its only layer is the tile layer as basemap, and its item extent is the tile
  layer's (Urban filters basemaps by item extent). It is organization-only and delete-protected.
- It was then shared to the Basemaps group, which now has 38 items. The web map's access stays `org`, so the public group does not
  expose it outside the organization. Every org user's Map Viewer basemap gallery now lists it.
- The tile layer itself stays in no group. Read back in [evidence/basemap-gallery.json](evidence/basemap-gallery.json).
- To withdraw it from the gallery, unshare the web map from the group; nothing else depends on the group membership.

**Known leftover.** 900 E is CARTOCODE 10 for most of its length (5 for a short stretch), so the study corridor draws at
local-street width. Widening `MAJOR` to 9-10 means a re-cache and a republish, and new item IDs. The basemap is left as published.

## The Urban models (October 27)

**Local model `2dc81c6f3a4b47efba2849dbfff9bf0f`** ("Millcreek, UT, USA", 6341, owner GISMillcreek). Brian created it with the
custom terrain and imported 21,744 parcels. It opened as terrain only, with "Light Gray Canvas cannot be added: Layer needs to be in
NAD 1983 (2011) UTM Zone 12N".
- **Cause: the model's config, not the items.** The model was saved with `schematicVisualization` and `satelliteVisualization`
  `Default` and no `customBasemapItemId`, so Urban loaded its Web Mercator defaults (Open 3D Buildings, Open 3D Trees, Light Gray
  Canvas, the Google mesh), and the 6341 view refused each with `spatial-reference-incompatible`. The UTM items needed no reprojection:
  the terrain drew. In Urban's own create code, Custom and the basemap ID are set only when a basemap is passed to the create.
- Urban's data manager has no Default/Custom switch for a local model
  ([data manager, General](https://doc.esri.com/en/arcgis-urban/latest/data/data-manager-general.html)), so the config was set with
  the app's own mutation, `updateUrbanModelConfig`:

  ```
  python reviews/2026-10-26/urban-utm/urban_model.py show 2dc81c6f3a4b47efba2849dbfff9bf0f        # read-only
  python reviews/2026-10-26/urban-utm/urban_model.py utm  2dc81c6f3a4b47efba2849dbfff9bf0f --go   # what was set
  ```

  Both visualizations are Custom, with basemap web map `8289e4be…` and existing buildings `b8e8ddac…`. Trees are left empty. Before:
  both Default, only `customElevationLayerItemId` set. To undo, set the two visualizations back to `Default` and the four IDs to null.
- After reload there was no "cannot be added" alert. The basemap draws on the terrain, and the buildings draw at street level
  ([evidence/urban-model-utm-config.json](evidence/urban-model-utm-config.json),
  [evidence/urban-model-utm-buildings-3780s.jpg](evidence/urban-model-utm-buildings-3780s.jpg), near 3780 S, from above). The
  oblique view was not checked.

**WGS84 buildings for a global model.** Brian asked to create both a local and a global model. The global model's existing
buildings must be in its coordinate system, and the public `ce3617ac…` layer has no FLOORS (and is not to be changed), so the same
prepared copy was packaged again in WGS84:

```
python reviews/2026-10-26/urban-utm/urban_utm.py slpk OUT --wgs84 --test
python reviews/2026-10-26/urban-utm/urban_utm.py slpk OUT --wgs84
python reviews/2026-10-22/hosting/upload/upload.py urban_buildings_wgs84 --go
python reviews/2026-10-26/urban-utm/share_org.py apply --go
python reviews/2026-10-23/agol-metadata/apply_metadata.py apply urban_buildings_wgs84 --go
```

- It is packaged as the public layer was: WGS84 with `WGS_1984_(ITRF08)_To_NAD_1983_2011` and no vertical CRS, so it is labelled
  EGM96 while the heights stay NAVD88.
- FLOORS is unchanged (P95 / 3.5 m), so both models get the same floors.

| Check | Result |
|---|---|
| 20-building test | FP_ID 20 / 3,401 equal to source; 4326, EGM96 label; validation warns "vertex normals may be required" |
| Full SLPK | **18,198,551 bytes**, SHA-256 `fe55e9ac15485c37661250bf76ea25331ed688987eea4bdc787eac432fe60289`; FP_ID **21,561 / 237,493,394**; 163 nodes; validation: no warnings |
| Hosted scene layer | 3DObject, 4326 + EGM96, 28 fields incl. FLOORS; FP_ID **21,561 / 237,493,394**; LEVEL 20,730 / 647 / 184; FLOORS sum 32,836 (1-12) |
| Sharing | Layer `org`, no groups, protected; package private, protected; every earlier item still passes; public items unchanged ([evidence/verification.json](evidence/verification.json)) |
| Item text | `urban_buildings_wgs84.md` applied; the shared `set_urban` block now names the basemap and the WGS84 layer, and was re-applied to the three UTM layers; the diff afterwards is empty |

**Normals warning, corrected.** The 20-building WGS84 test package also warns about vertex normals, but the full WGS84 package does
not. So the warning is not tied to the projected coordinate system alone, and the earlier explanation is incomplete. It is still
recorded, not fixed.

**Global model: not yet created.** Urban's "Create copy" (data manager, Admin) copies a model to the coordinate system of a chosen
basemap, along with its settings, parcels, type tables and metrics, so a Web Mercator copy keeps the imported parcels. The copy is
owned by whoever runs it, and the Urban API has no copy mutation. For the copy:
- Schematic: Custom, with existing buildings `d4b852fd…` and a Web Mercator basemap.
- Realistic: Default, which is the Google Photorealistic 3D basemap (beta).
- Elevation: the public terrain `ce1680a5…` is on the standard Web Mercator scheme (256 px, origin -20037508.34, 24 LODs), so it
  matches Esri's basemaps; not yet tried in Urban. Without it, Urban uses World Elevation.

## Rollback

Nothing public changed. To withdraw an item, unshare it (`item.sharing.sharing_level = "PRIVATE"`). Deleting it needs delete
protection turned off first, and is Brian's call. Delete the layer before its package.
