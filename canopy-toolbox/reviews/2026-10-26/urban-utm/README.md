# Existing buildings and elevation in UTM 12N for a local ArcGIS Urban model (October 26, 2026)

On October 26 Brian approved publishing the roofer LoD2.2 three-way hybrid as the ArcGIS Urban existing buildings, **organization-only**.
He chose **NAD83(2011) UTM 12N, metres** for the Urban model, because every LiDAR 3D product is native UTM. A local Urban model gets no
default buildings or elevation: both must be custom layers in the model's own coordinate system. The public October 25 hybrid is WGS84
for global scenes, so these items are separate UTM copies. **The Urban model itself was not created**; Brian does that after his tutorial.

## Items

| Item | Layer ID | Source package ID | Type | Access |
|---|---|---|---|---|
| 3D buildings for ArcGIS Urban, UTM 12N | `b8e8ddaceac54876bd4c0cf3f31d92fd` | `c7702ec26f7843ad9572b797888557d6` | Scene Service (3DObject) | Layer: organization; package: private; both delete-protected |
| Building footprints for ArcGIS Urban, UTM 12N | `e74c2216aca54d7f8be2432768b64520` | `32ba9a96f01d43b690f8faa4ce4c6a15` | Feature Service, layer 0 `building_footprints` | Layer: organization; package: private; both delete-protected |
| Bare-earth terrain for ArcGIS Urban, UTM 12N 0.5 m | `83d1a892fd67408b9f8f9fcb754cd479` | `33b6ae61d34e4cd682c45fa42b229095` | Image Service (elevation) | Layer: organization; package: private; both delete-protected |

All six are in the GISMillcreek folder **Millcreek LiDAR 2023**. No layer is shared with everyone or with a group, and anonymous
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
changed from LERC to an image format) would meet the requirement. No basemap was made here.

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
- None of the three layers has been drawn in a local scene or in ArcGIS Urban. Urban needs the UTM basemap above first.
- Whether Convert existing buildings reads `FLOORS` from the scene layer or from a feature layer is not documented. It is on both.
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

## Rollback

Nothing public changed. To withdraw an item, unshare it (`item.sharing.sharing_level = "PRIVATE"`). Deleting it needs delete
protection turned off first, and is Brian's call. Delete the layer before its package.
