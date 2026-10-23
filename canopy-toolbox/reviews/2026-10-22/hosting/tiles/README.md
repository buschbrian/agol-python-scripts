# Hillshade tile package and terrain elevation package (October 22, 2026)

Step 5 of the hosting plan: the citywide hillshade as a raster tile package and the bare-earth terrain as an elevation tile
package, both `.tpkx` on the ArcGIS Online Web Mercator schemes, built and checked on the laptop.
**Nothing has been uploaded, published or shared.** Both are **unvalidated LiDAR planning estimates**, not surveyed surfaces.

Output: `<SSD>\lidar\2023-salt-lake-valley\runs\tiles-20261022` ([package_tiles.py](package_tiles.py)):

| File | Size | What it is |
|---|---|---|
| `millcreek_hillshade_20261022.tpkx` | 122,828,479 bytes (123 MB) | Hillshade, PNG tiles, levels 0-18, city only |
| `millcreek_terrain_20261022.tpkx` | 228,117,372 bytes (228 MB) | Terrain in metres, LERC tiles (0.01 m), levels 0-18, the whole lidar mosaic |

Also in the run folder: `caches\` (the tile caches the packages were exported from, 379 MB), `schemes\`, `layer\` (the hillshade
layer file and the areas of interest), `pilot\`, `check\check.aprx`, and logs. Copies of run.json, verify.json, pilot.json,
schemes.json, layer.json and the two scheme files are beside this README.

## How it is driven without the Pro UI
Create Map Tile Package needs a map, so it is not used. **Manage Tile Cache** takes a raster dataset, or a raster layer file
(`.lyrx`), as its data source and writes a cache on an imported tiling scheme; **Export Tile Cache** with `TILE_PACKAGE_TPKX` /
`COMPACT_V2` turns the cache into a `.tpkx`. The layer file is made headless with `arcpy.mp.CreateArcGISProject`, `createMap`,
`addDataFromPath`, a CIM edit of the colorizer and `saveACopy`. A `.mapx` also worked as a data source in the pilot.
The slope-vector-tiles branch had no commits when this was built. The findings are in the shared notes folder for that session.

Quirks found on the way: the scales passed to Manage Tile Cache must be the exact values in its list (a computed
`591657527.591555/2**18` is refused, ERROR 000800); a cache of levels 0-1 only fails (ERROR 001517); a `.tpkx` carries
`root.json` and `iteminfo.json`, not `conf.xml`.

## Choices
- **Levels 0-18.** Level 18 is 0.597 m in Web Mercator, which is 0.597 x cos(40.69 degrees) = 0.45 m on the ground at Millcreek:
  the first level at least as fine as the 0.5 m source. Level 17 is 0.91 m on the ground; level 19 would be 4x the tiles with
  nothing new in them. Scales and resolutions are from the scheme the tool wrote (`schemes/*.xml`): level 18 is 1:2,256.994353.
- **Hillshade: PNG, not JPEG and not the default MIXED.** The hillshade is masked to the city, so edge tiles need transparency.
  JPEG has none: in a first scratch run on the pilot window (not in pilot.json), 2,966 of 4,320 sampled JPEG pixels were
  opaque over NoData, which would show as a fill outside the city boundary over the basemap. MIXED (JPEG inside, PNG at the
  edges, quality 75) is the tool's default and was 0.35x the size in the pilot (1.84 MB against 5.34 MB for levels 16-18).
  But it is lossy on 0.5 m detail, and it would save about 80 MB, well under 0.1 credits a month (below). PNG is lossless
  and the cost is negligible.
- **Hillshade rendering: a layer file with no stretch.** Given the raster itself, Manage Tile Cache renders it with Pro's
  default, a 2-standard-deviation stretch around the mean of 184. In the pilot that sent every value below about 115 to black
  (mean tile minus source -42). The layer file `layer\hillshade_identity.lyrx` has a min-max stretch fixed at 0-255, no gamma
  and bilinear display resampling. The tiles then equal the source: mean difference -0.01, median 1, 95th percentile 3 grey
  levels over 7,262 sampled pixels (verify.json; the spread is bilinear tiles against the nearest source cell).
- **Terrain: the unmasked mosaic, `terrain_context.tif`, not `terrain_m.tif`.** The two are identical on every city cell
  (terrain-city README). In a web scene the ground is a stack: where the custom layer has no value, the next layer
  (World Elevation) shows through. The "hard drop" at the city edge only happens if the custom layer is the only ground
  layer. With World Elevation underneath, the masked raster would put a seam (different source, resolution and
  interpolation) along the city boundary, through neighbourhoods and under the step 3 buildings that sit on it. The unmasked
  one moves the seam to the mosaic edge, in the foothills and neighbouring cities. That edge follows the 1 km lidar tiles,
  so it is a staircase. Cost: 51.0 km² instead of 33.7, about 1.5x the tiles. The extra ground is the same acquisition and is
  equally unvalidated. The mosaic's NoData (+3.4e38) is honoured: edge tiles carry a LERC mask. In the scratch pilot
  run, a partially covered tile was 39% valid, with masked cells and no spikes. In the package, valid level 18 values run
  from 1,289.94 to 2,488.73 m, which is the source's range (1,289.94 to 2,488.74 m), and 938 of the 4,864 stored tiles are
  fully masked (read separately after verify.json, by the same tile reader).
- **LERC maximum error 0.01 m, not the scheme's 0.1 m.** The ArcGIS Online elevation scheme in Pro defaults to 0.1 m
  (`schemes.json`). That is the same size as QL1 lidar's vertical accuracy (USGS QL1 specification: RMSEz ≤ 10 cm in
  non-vegetated terrain; the accuracy report for this acquisition is not in `acquisition-facts.md`), so it would add an
  error as large as the data's own to anything measured in a scene. At 0.01 m the package adds a tenth of that. In the
  pilot it was 1.67x the size of 0.1 m (6.78 MB against 4.06 MB at level 18), about 90 MB for the city: 0.1 credits a month.
- **No geographic transformation.** With `env.geographicTransformations` unset the tool takes NAD83(2011) as WGS84 when it
  projects to Web Mercator (they differ by about 1 m in Utah). The pilot proved this: tile values matched bilinear source
  values to within the LERC tolerance only when the check projected the same way. Steep cells would have shown metres of
  difference otherwise. The vector tiles and building scene layers should make the same choice or they will misregister by
  about a metre against these. This is noted in the shared notes folder.
- **Vertical datum.** NAVD88 (Geoid18) metres, from `acquisitions/2023-salt-lake-valley/acquisition-facts.md`. The rasters carry
  no vertical coordinate system and LERC tiles carry only numbers. World Elevation is orthometric too, so the two blend.
- **Areas of interest.** Hillshade: the municipal boundary buffered 5 m (33.7 km²). Terrain: the mosaic footprint
  (10 m blocks with any valid cell, buffered 15 m; 51.0 km²). The tool still writes some tiles past the area of interest.
  It writes transparent PNGs and masked LERC tiles there, which are counted below as "stored, no data".

## Tiles per level
"Stored" is every tile in the package; "with data" has at least one opaque pixel (hillshade) or valid cell (terrain).
Read from the bundle indexes inside each `.tpkx` (verify.json `levels`).

| Level | Ground m/px | Hillshade stored | Hillshade with data | Terrain stored | Terrain with data |
|---:|---:|---:|---:|---:|---:|
| 0-8 | 118,600-463 | 9 (1 each) | 4 (levels 5-8) | 9 (1 each) | 7 (levels 2-8) |
| 9 | 232 | 2 | 2 | 2 | 2 |
| 10 | 116 | 4 | 2 | 4 | 4 |
| 11 | 58 | 4 | 2 | 4 | 4 |
| 12 | 29 | 6 | 3 | 6 | 5 |
| 13 | 14.5 | 11 | 9 | 12 | 11 |
| 14 | 7.2 | 34 | 22 | 35 | 27 |
| 15 | 3.6 | 106 | 61 | 108 | 86 |
| 16 | 1.81 | 386 | 209 | 398 | 292 |
| 17 | 0.91 | 1,216 | 761 | 1,312 | 1,046 |
| 18 | 0.45 | 3,760 | 2,752 | 4,864 | 3,926 |
| **All** | | **5,538** | **3,827** | **6,754** | **5,410** |

Level 18 holds 66% of the hillshade package's bytes (80.9 MB) and 70% of the terrain's (158.8 MB).

## How it was checked
- **Pilot** (`pilot.json`, 1 km window at the north-east corner of the grid, where the city edge and the mosaic edge cross;
  levels 16-18): the defaults against these settings, as above. Elevation pixels are 257 x 257 and corner-registered (pixel i
  of tile column c sits at x = origin + (256c + i) x resolution); the cache resamples bilinearly.
- **Both packages open in Pro's engine** (`verify.json` `opens_in_pro`, `check\check.aprx`): a new project made by arcpy,
  with the hillshade package in a map and the terrain package in a scene. Both are raster datasets (`Describe`), CIMRasterLayers,
  and not broken. This is Pro's engine through arcpy, not a check in the Pro window. arcpy (3.7.3) has no call that adds a
  source to a scene's ground (`ElevationSurface` has no `addSource`), so using the terrain as ground was not tested locally.
- **Elevation values against `terrain_m.tif`** (`terrain_samples`): 300 city points away from the mask edge, 150 flat (slope
  under 2 degrees) and 150 steep (over 25 degrees). Each was moved to its nearest level 18 elevation pixel and compared with
  terrain_m.tif interpolated bilinearly at that pixel, with the same no-transformation projection.

  | | Max abs difference | Median | Against the LERC tolerance |
  |---|---:|---:|---|
  | Flat (150) | 0.0099 m | 0.0041 m | within 0.01 m |
  | Steep (150) | 0.0112 m | 0.0048 m | 1.2 mm over |
  | All (300) | 0.0112 m | 0.0044 m | |

  The LERC headers of 98 level 18 tiles all record a maximum error of 0.01 m, and on flat ground the difference stays
  inside it. The extra 1.2 mm appears only on steep cells. That fits sub-millimetre differences between the tool's
  reprojection and resampling and this check's float64 bilinear, multiplied by slopes up to about 80 degrees. This is an
  inference: it cannot be split from the LERC error without the tool's own resampled input. Against the source cell that
  each original point falls in (what someone comparing a click with the 0.5 m raster would see), differences reach
  0.335 m on steep ground (median 0.066 m) and 0.03 m on flat ground. That comes from re-gridding to 0.45 m, not from
  compression. No sample point was missing from the package.
- **Hillshade covers the city at every level that can show it** (`hillshade_coverage`). The expected tiles are those that
  hold a valid hillshade cell centre: every edge cell, and interior cells every 10th row and column. A level 18 tile is
  about 230 cells across, so no all-interior tile can be missed. Coarser levels are their parents.
  - Levels 13-18 and 5-9: every expected tile is present with data (level 18: 2,752 expected, 2,752 present, none extra).
  - Levels 10, 11, 12: one expected tile each is transparent. It holds a sliver on the boundary (392 sampled edge cells across
    two level 18 tiles), narrower than half a pixel at 29-116 m a pixel, so bilinear display leaves it empty. It is present
    from level 13 on.
  - Levels 0-4: the single tile is transparent. The city is under two pixels across at those zooms.
  - At level 18, 7,269 sampled pixels over valid hillshade were opaque except 7 at the edge, and no pixel over NoData was opaque.

## Credit cost of hosting
Esri's credits page (https://doc.arcgis.com/en/arcgis-online/administer/credits.htm, read October 22, 2026; the page shows no
date) says: file, tile and other content storage is **1.2 credits per GB per month, calculated hourly**, and lists tile
packages under it. Tile generation is 1 credit per 10,000 tiles, but that is for caches built in ArcGIS Online. Esri's tile
layer page says publishing from a tile package needs no build ("The cache already exists"), so no generation credits are
expected.

| | Size | While the package item is kept | After deleting the package item |
|---|---:|---:|---:|
| Hillshade | 0.123 GB | about 0.30 credits/month | about 0.15 credits/month (1.8 a year) |
| Terrain | 0.228 GB | about 0.55 credits/month | about 0.27 credits/month (3.3 a year) |
| Both | 0.351 GB | about 0.84 credits/month | about 0.42 credits/month (5 a year) |

Not confirmed:
- The size of the hosted layer after unpacking. These figures assume it is about the size of the package.
- That a hosted *elevation* layer is billed at the tile storage rate. The credits page does not mention elevation layers.
- Whether "GB" means 10^9 or 2^30 bytes (about 7%).

Esri's publish page does confirm that the uploaded package remains an item in My content. It says the package can be
deleted once the layer works, so that its storage is no longer charged. At these sizes the choice of format and LERC
tolerance changes the cost by less than 0.1 credits a month.

## Upload and publish steps for Brian (not done; each needs your go-ahead)
Sign in to ArcGIS Online with an account that can publish hosted tile layers. Upload the files from the SSD.

**Hillshade (hosted tile layer)**
1. Content > My content > **New item** > **Your device**. Pick `millcreek_hillshade_20261022.tpkx`.
2. Choose **Add millcreek_hillshade_20261022.tpkx and create a hosted tile layer** > **Next**.
3. Title: `Millcreek hillshade 0.5 m (2023 lidar), planning estimate`. Pick a folder. Tags: `Millcreek, hillshade, lidar, 2023, planning estimate`. **Save**.
   ArcGIS Online unpacks the tiles; this can take several minutes.
4. On the new tile layer's item page, set the summary: `Unvalidated LiDAR planning estimate. Hillshade (sun 315/45) of the
   0.5 m bare-earth terrain from the 2023 Salt Lake Valley QL1 lidar, for display only; not a surveyed surface.` Paste the
   same text and a link to this README into the description.
5. Optional: Settings > visible range from about 1:2,311,162 (level 8) inward. At levels 0-4 the city is under two pixels.
6. Check it over the basemap in Map Viewer, and that it is transparent outside the city. Then delete the package item to stop
   paying for its storage, if you are sure you no longer need it there (the `.tpkx` stays on the SSD).

**Terrain (hosted elevation layer, custom ground)**
1. Content > My content > **New item** > **Your device**. Pick `millcreek_terrain_20261022.tpkx`.
2. Choose the option that adds the package and creates a hosted layer. For a LERC package Esri's "Publish hosted elevation
   layers" page says this creates a hosted elevation layer. The exact wording of the option for an elevation package was
   not checked; if it only offers to add the file, stop and send me what it shows.
3. Title: `Millcreek bare-earth terrain 0.5 m (2023 lidar), planning estimate`. Tags as above plus `elevation, ground`. **Save**.
4. Summary: `Unvalidated LiDAR planning estimate. Bare-earth elevation in metres, NAVD88 (Geoid18), interpolated at 0.5 m from
   class-2 ground returns of the 2023 Salt Lake Valley QL1 lidar; LERC error 0.01 m. For 3D ground; not a surveyed surface.`
5. Check it in Scene Viewer: New scene > **Add layers** > find the elevation layer > add it to the **Ground**. Keep World
   Elevation in the ground below it so the area outside the mosaic still has terrain. Look along the mosaic edge in the
   foothills for the seam.
6. Then, as for the hillshade, delete the package item if the layer works.

Do not share either layer beyond your account until you decide to. Publishing alone does not share them.

## Reproduce
```
set CANOPY_LIDAR_ROOT=H:\lidar
set PYTHONNOUSERSITE=1
"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" reviews\2026-10-22\hosting\tiles\package_tiles.py scheme H:\lidar\2023-salt-lake-valley\runs\tiles-20261022
```
then `layer`, `pilot`, `build` and `verify` with the same folder. Times on the laptop, with the SSD as H: (`run.json`): hillshade cache
92 s and export 2 s; terrain cache 61 s and export 1 s; the verification takes a few minutes.
