# Hillshade tile package and terrain elevation package (October 22, 2026; rebuilt October 23)

Step 5 of the hosting plan: the citywide hillshade as a raster tile package and the bare-earth terrain as an elevation tile
package, both `.tpkx` on the ArcGIS Online Web Mercator schemes, built and checked on the laptop.
**Rebuilt October 23 with the datum transformation the other packages use** (see [Datum](#datum-rebuilt-october-23)); the
October 22 packages in `runs\tiles-20261022` sit 1.2 m off the buildings and vector tiles and are superseded (left on
the SSD; deleting them is Brian's call). **Nothing has been uploaded, published or shared.** Both are **unvalidated LiDAR planning estimates**, not surveyed surfaces.

Output: `<SSD>\lidar\2023-salt-lake-valley\runs\tiles-20261023` ([package_tiles.py](package_tiles.py)):

| File | Size | What it is |
|---|---|---|
| `millcreek_hillshade_20261023.tpkx` | 133,998,959 bytes (134 MB) | Hillshade, PNG32 tiles, levels 0-18, city only |
| `millcreek_terrain_20261023.tpkx` | 228,112,957 bytes (228 MB) | Terrain in metres, LERC tiles (0.01 m), levels 0-18, the whole lidar mosaic |

Also in the run folder:
- `caches\`: the tile caches the packages were exported from (390 MB);
- `layer\`: the shifted hillshade display copy and its layer file, the shifted terrain VRT, and the areas of interest;
- `schemes\`, `pilot\`, `check\check.aprx`, and logs.

Beside this README are copies of run.json, verify.json, pilot.json, schemes.json, layer.json and the two scheme files.

## How it is driven without the Pro UI
Create Map Tile Package needs a map, so it is not used. Two tools take raster input directly:
- **Manage Tile Cache** takes a raster dataset, or a raster layer file (`.lyrx`), as its data source and writes a cache on
  an imported tiling scheme.
- **Export Tile Cache** with `TILE_PACKAGE_TPKX` / `COMPACT_V2` turns the cache into a `.tpkx`.

The layer file is made headless: `arcpy.mp.CreateArcGISProject`, `createMap`, `addDataFromPath`, a CIM edit of the
colorizer, then `saveACopy`. A `.mapx` also worked as a data source in the pilot. The slope-vector-tiles branch had no
commits when this was built; the findings are in the shared notes folder for that session.

Quirks found on the way:
- The scales passed to Manage Tile Cache must be the exact values in its list. A computed `591657527.591555/2**18` is
  refused (ERROR 000800).
- A cache of levels 0-1 only fails (ERROR 001517).
- A `.tpkx` carries `root.json` and `iteminfo.json`, not `conf.xml`.

## Choices
- **Levels 0-18.** Level 18 is 0.597 m in Web Mercator. On the ground at Millcreek that is 0.597 x cos(40.69 degrees) =
  0.45 m, the first level at least as fine as the 0.5 m source. Level 17 is 0.91 m on the ground; level 19 would be 4x the
  tiles with nothing new in them. Scales and resolutions come from the scheme the tool wrote (`schemes/*.xml`): level 18
  is 1:2,256.994353.
- **Hillshade: PNG32, not JPEG and not the default MIXED.** The hillshade is masked to the city, so edge tiles need
  transparency, and JPEG has none. In a first scratch run on the pilot window (not in pilot.json), 2,966 of 4,320 sampled
  JPEG pixels were opaque over NoData, which would show as a fill outside the city boundary over the basemap. MIXED (JPEG
  inside, PNG at the edges, quality 75) is the tool's default. It was 0.35x the size of PNG in the pilot (1.84 MB against
  5.34 MB for levels 16-18), but it is lossy on 0.5 m detail and would save about 85 MB, under 0.1 credits a month (below).
  Plain `PNG` was tried first. Pro writes it as grey RGB with a (253, 253, 253) transparency key, so PNG32, with a real
  alpha channel, is used instead. It made the package 8 MB larger.
- **Hillshade rendering: a capped display copy with no stretch.** Given the raster itself, Manage Tile Cache renders it with
  Pro's default 2-standard-deviation stretch around the mean of 184. In the pilot that sent every value below about 115 to
  black (mean tile minus source -42). A min-max layer fixed that, but the full package then had 4,709 single-pixel holes:
  transparent pixels inside the city, on the brightest slopes (source 251-254, mostly 253). Manage Tile Cache treats a
  rendered (253, 253, 253) as its transparent background, in PNG and PNG32 alike, and bilinear display makes 253 from
  neighbouring 252 and 254. The tiles are therefore drawn from `layer\hillshade_display.tif`, a copy with 253 and 254 set to
  252, via `layer\hillshade_identity.lyrx` (no stretch, no gamma, bilinear resampling). That changes 241,733 of 133,813,488
  cells (0.18%) by 1-2 grey levels at the very top of the scale. Custom stretch settings were tried as well. They were
  either ignored ("MinimumMaximum" uses the dataset's 0-254) or applied as breakpoint classes ("Custom"); neither was a
  reliable linear map.
- **Terrain: the unmasked mosaic, `terrain_context.tif`, not `terrain_m.tif`.** The two are identical on every city cell
  (terrain-city README).
  - In a web scene the ground is a stack: where the custom layer has no value, the next layer (World Elevation) shows
    through. The "hard drop" at the city edge only happens if the custom layer is the only ground layer.
  - With World Elevation underneath, the masked raster would put a seam (different source, resolution and interpolation)
    along the city boundary, through neighbourhoods and under the step 3 buildings that sit on it. The unmasked one moves
    the seam to the mosaic edge, in the foothills and neighbouring cities. That edge follows the 1 km lidar tiles, so it is
    a staircase.
  - Cost: 51.0 km² instead of 33.7, about 1.5x the tiles. The extra ground is the same acquisition and equally unvalidated.
  - The mosaic's NoData (+3.4e38) is honoured: edge tiles carry a LERC mask. In the scratch pilot run, a partially covered
    tile was 39% valid, with masked cells and no spikes. In the October 22 package, valid level 18 values run from 1,289.94
    to 2,488.73 m, the source's range (1,289.94 to 2,488.74 m), and 938 of the 4,864 stored level 18 tiles are fully
    masked (940 in the October 23 package, verify.json `levels`). The range was read separately with the same tile reader
    and is not in verify.json.
- **LERC maximum error 0.01 m, not the scheme's 0.1 m.** The ArcGIS Online elevation scheme in Pro defaults to 0.1 m
  (`schemes.json`). That equals QL1 lidar's vertical accuracy (USGS QL1 specification: RMSEz ≤ 10 cm in non-vegetated
  terrain; this acquisition's accuracy report is not in `acquisition-facts.md`). So it would add an error as large as the
  data's own to anything measured in a scene; at 0.01 m the package adds a tenth of that. In the pilot, 0.01 m was 1.67x
  the size of 0.1 m (6.78 MB against 4.06 MB at level 18). For the city that is about 90 MB, or 0.1 credits a month.
- **Datum: WGS_1984_(ITRF08)_To_NAD_1983_2011**, as the building scene layers and the vector tiles (next section).
- **Elevation content type survives the edited scheme.** The terrain cache built on the imported scheme carries
  `CacheTileContentType = Elevation` and `PixelType = 32_BIT_FLOAT` in `conf.properties`, as a cache built with
  `ARCGISONLINE_ELEVATION_SCHEME` does. A `.tpkx` exported from that default cache has `root.json` and `iteminfo.json`
  identical to ours except for `lercError`. So the 0.01 m edit changes nothing that ArcGIS Online could use to recognise
  an elevation package.
- **Vertical datum.** NAVD88 (Geoid18) metres, from `acquisitions/2023-salt-lake-valley/acquisition-facts.md`. The rasters
  carry no vertical coordinate system and LERC tiles carry only numbers. World Elevation is orthometric too, so the two blend.
- **Areas of interest** (in true coordinates; the 5 m and 15 m buffers cover the 1.2 m source shift, and the coverage
  check below is the arbiter).
  - Hillshade: the municipal boundary buffered 5 m (33.7 km²).
  - Terrain: the mosaic footprint, as 10 m blocks with any valid cell buffered 15 m (51.0 km²).
  - The tool still writes some tiles past the area of interest: transparent PNGs and masked LERC tiles, counted below as
    "stored" but not "with data".

## Tiles per level
"Stored" is every tile in the package. "With data" has at least one opaque pixel (hillshade) or valid cell (terrain).
Counts are read from the bundle indexes inside each `.tpkx` (verify.json `levels`). They equal the October 22 build's at
every level except terrain level 18, which has two fewer tiles with data at the mosaic edge (3,926 then).

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
| 18 | 0.45 | 3,760 | 2,752 | 4,864 | 3,924 |
| **All** | | **5,538** | **3,827** | **6,754** | **5,408** |

Level 18 holds 67% of the hillshade's tile bytes (87.1 MB) and 71% of the terrain's (158.8 MB).

## Datum (rebuilt October 23)
The building scene layers ([scene-layers](../scene-layers/README.md)) name `WGS_1984_(ITRF08)_To_NAD_1983_2011` (Esri
wkid 108363) for NAD83(2011) to WGS84, and the vector tile packages carry it too: their maps' datum transformation, and
read from the tiles themselves ([vector-tiles datum check](../vector-tiles/README.md#datum)). The October 22 build of
these two packages used none, so they sat **1.197 m on the ground** (1.58 m in Web Mercator) from the others, which in a
web scene would have put the buildings beside their own ground. ITRF08 is the one to match, because Esri's basemaps and
World Elevation are WGS84.

What the tools allow, found on the pilot window (each tested by reading the tiles back, below):
- **Manage Tile Cache ignores `arcpy.env.geographicTransformations`.** With it set to the transformation, the tiles still
  matched the untransformed projection (terrain within 0.012 m of it, up to 3 m from the transformed one).
- **A map applies its datum transformation**, and Manage Tile Cache takes a `.mapx` as its source: a hillshade cache from a
  map in Web Mercator (Pro gives such a map the ITRF08 transformation by default) matched the transformed projection. Two
  traps: `createMap` added the default Topographic basemap, which the cache drew into the tiles, and the cache is written one
  folder deeper (`<name>\<map name>`).
- **An elevation cache refuses a map as its source** (ERROR 000242), so the terrain cannot take that route.

So the transformation is applied to the sources, the same way for both packages: each is drawn from a copy whose
georeferencing is translated by the transformation's offset in UTM, so the tool's untransformed projection puts every
cell where the transformation would. The offset, taken from Esri's engine on a 9 x 9 grid over the mosaic
(`layer.json` `source_shift`), is dx -0.9823 m, dy +0.6848 m (1.1974 m), and departs from its mean by at most 0.81 mm
anywhere in the mosaic: the 7-parameter transformation is a translation to under a millimetre over 12 km. The copies are
`layer\hillshade_display.tif` (the capped display copy, now also translated) and `layer\terrain_shifted.vrt` (a VRT over
the mosaic with its origin translated: no cell copied or changed). They are working inputs, not products: their
coordinates are deliberately 1.2 m off. No cell value changes and nothing extra is resampled.

The verifier does not reuse that offset: it fits the transformation separately, as a plane in Web Mercator from Esri's
engine (`verify.json` `datum_shift`: residual 0.0015 mm), and every value and coverage check below is run with it. The
value checks are also run as if the tiles were untransformed, so the packages show which choice they carry:

| | Tiles read with ITRF08 | Same tiles read untransformed |
|---|---|---|
| Terrain, 150 flat points: max, median | 0.0100 m, 0.0051 m | 0.140 m, 0.019 m |
| Terrain, 150 steep points: max, median | 0.0119 m, 0.0049 m | 2.845 m, 0.562 m |
| Hillshade, 7,269 pixels: median, 95th percentile, max (grey levels) | 1, 3, 21 | 3, 17, 107 |

## How it was checked
- **Pilot** (`pilot.json`, levels 16-18): a 1 km window at the north-east corner of the grid, where the city edge and the
  mosaic edge cross. It compared the defaults with these settings, as above. The October 22 pilot was from the plain-PNG,
  min-max layer stage; the hillshade fixes after it were tested on a 500 m window and then on the full package. The
  October 23 pilot (the copy here) ran the shifted sources: terrain within 0.017 m of the transformed projection on this,
  the steepest window (4.38 m from the untransformed one), and the hillshade's median and 95th percentile 1 and 5 grey
  levels (4 and 24 untransformed).
  - Elevation pixels are 257 x 257 and corner-registered: pixel i of tile column c sits at x = origin + (256c + i) x
    resolution.
  - The cache resamples bilinearly.
- **Both packages open in Pro's engine** (`verify.json` `opens_in_pro`, `check\check.aprx`).
  - A new project made by arcpy holds the hillshade package in a map and the terrain package in a scene.
  - Both are raster datasets (`Describe`), CIMRasterLayers, and not broken.
  - This is Pro's engine through arcpy, not a check in the Pro window.
  - arcpy (3.7.3) has no call that adds a source to a scene's ground (`ElevationSurface` has no `addSource`), so using the
    terrain as ground was not tested locally.
- **Elevation values against `terrain_m.tif`** (`terrain_samples`): 300 city points away from the mask edge, 150 flat (slope
  under 2 degrees) and 150 steep (over 25 degrees). Each was moved to its nearest level 18 elevation pixel and compared with
  terrain_m.tif interpolated bilinearly at that pixel, projected the same way (with the transformation).

  | | Max abs difference | Median | Against the LERC tolerance | October 22 build (untransformed check) |
  |---|---:|---:|---|---|
  | Flat (150) | 0.0100 m | 0.0051 m | within 0.01 m | 0.0099 m, 0.0041 m |
  | Steep (150) | 0.0119 m | 0.0049 m | 1.9 mm over | 0.0112 m, 0.0048 m |
  | All (300) | 0.0119 m | 0.0050 m | | 0.0112 m, 0.0044 m |

  - The LERC headers of 98 level 18 tiles all record a maximum error of 0.01 m, and on flat ground the difference stays
    inside it.
  - The extra 1.9 mm (1.2 mm in the October 22 build) appears only on steep cells. That fits sub-millimetre differences
    between the tool's reprojection and resampling and this check's float64 bilinear, multiplied by slopes up to about 80
    degrees; the source shift's 0.81 mm approximation adds to it on the steepest cells. This is an inference: it cannot be
    split from the LERC error without the tool's own resampled input.
  - Against the source cell each original point falls in (what someone comparing a click with the 0.5 m raster would see),
    differences reach 0.809 m on steep ground (median 0.062 m) and 0.019 m on flat ground (October 22: 0.335 m, 0.066 m,
    0.03 m; the sampled pixels moved with the shift). That comes from re-gridding to 0.45 m, not from compression.
  - No sample point was missing from the package.
- **Hillshade covers the city at every level that can show it** (`hillshade_coverage`).
  - Expected tiles are those holding a valid hillshade cell centre. Every edge cell is checked, plus interior cells every
    10th row and column; a level 18 tile is about 230 cells across, so no all-interior tile can be missed. Coarser levels
    are their parents.
  - Levels 13-18 and 5-9: every expected tile is present with data (level 18: 2,752 expected, 2,752 present, none extra).
  - Levels 10, 11, 12: one expected tile each is transparent. It holds a sliver on the boundary (392 sampled edge cells
    across two level 18 tiles), narrower than half a pixel at 29-116 m a pixel, so bilinear display leaves it empty. It is
    present from level 13 on.
  - Levels 0-4: the single tile is transparent. The city is under two pixels across at those zooms.
  - At level 18, the 163,438,220 opaque pixels contain no transparent pixel surrounded by opaque ones (`hillshade_holes_L18`).
    No pixel is brighter than 252.
  - Of 7,269 sampled pixels over valid hillshade, 7,268 are opaque; the other is at the edge. No pixel over NoData is
    opaque. Tile minus capped source: mean -0.07, median 1, 95th percentile 3 grey levels. The spread is bilinear tiles
    against the nearest source cell.

## Credit cost of hosting
Esri's credits page (https://doc.arcgis.com/en/arcgis-online/administer/credits.htm, read October 22, 2026; the page shows no
date) sets two rates:
- File, tile and other content storage: **1.2 credits per GB per month, calculated hourly**. Tile packages are listed under it.
- Tile generation: 1 credit per 10,000 tiles, for caches built in ArcGIS Online. Esri's tile layer page says publishing from
  a tile package needs no build ("The cache already exists"), so no generation credits are expected.

| | Size | While the package item is kept | After deleting the package item |
|---|---:|---:|---:|
| Hillshade | 0.134 GB | about 0.32 credits/month | about 0.16 credits/month (1.9 a year) |
| Terrain | 0.228 GB | about 0.55 credits/month | about 0.27 credits/month (3.3 a year) |
| Both | 0.362 GB | about 0.87 credits/month | about 0.43 credits/month (5.2 a year) |

Not confirmed:
- The size of the hosted layer after unpacking. These figures assume it is about the size of the package.
- That a hosted *elevation* layer is billed at the tile storage rate. The credits page does not mention elevation layers.
- Whether "GB" means 10^9 or 2^30 bytes (about 7%).

Esri's publish page does confirm that the uploaded package remains an item in My content. It says the package can be
deleted once the layer works, so that its storage is no longer charged. At these sizes the choice of format and LERC
tolerance changes the cost by less than 0.1 credits a month.

## Upload and publish steps for Brian (not done; each needs your go-ahead)
Sign in to ArcGIS Online with an account that can publish hosted tile layers, and upload the files from the SSD.

**Hillshade (hosted tile layer)**
1. Content > My content > **New item** > **Your device**. Pick `millcreek_hillshade_20261023.tpkx`.
2. Choose **Add millcreek_hillshade_20261023.tpkx and create a hosted tile layer**, then **Next**.
3. Title: `Millcreek hillshade 0.5 m (2023 lidar), planning estimate`. Pick a folder. Tags: `Millcreek, hillshade, lidar, 2023, planning estimate`. **Save**.
   ArcGIS Online unpacks the tiles, which can take several minutes.
4. On the new tile layer's item page, set the summary:
   `Unvalidated LiDAR planning estimate. Hillshade (sun 315/45) of the 0.5 m bare-earth terrain from the 2023 Salt Lake
   Valley QL1 lidar, for display only; not a surveyed surface.`
   Put the same text and a link to this README in the description.
5. Optional: Settings > visible range from about 1:2,311,162 (level 8) inward. At levels 0-4 the city is under two pixels.
6. Check it over the basemap in Map Viewer, including that it is transparent outside the city. Then delete the package item
   to stop paying for its storage, if you are sure you no longer need it there (the `.tpkx` stays on the SSD).

**Terrain (hosted elevation layer, custom ground)**
1. Content > My content > **New item** > **Your device**. Pick `millcreek_terrain_20261023.tpkx`.
2. Choose the option that adds the package and creates a hosted layer. Esri's "Publish hosted elevation layers" page says
   this creates a hosted elevation layer for a LERC package. The exact wording of the option for an elevation package was
   not checked; if it only offers to add the file, stop and send me what it shows.
3. Title: `Millcreek bare-earth terrain 0.5 m (2023 lidar), planning estimate`. Use the tags above plus `elevation, ground`. **Save**.
4. Summary:
   `Unvalidated LiDAR planning estimate. Bare-earth elevation in metres, NAVD88 (Geoid18), interpolated at 0.5 m from
   class-2 ground returns of the 2023 Salt Lake Valley QL1 lidar; LERC error 0.01 m. For 3D ground; not a surveyed surface.`
5. Check it in Scene Viewer: New scene > **Add layers**, find the elevation layer, and add it to the **Ground**. Keep World
   Elevation in the ground below it, so the area outside the mosaic still has terrain. Look along the mosaic edge in the
   foothills for the seam, and add the LOD1.2 building scene layer: the buildings should stand on this ground, not 1.2 m
   beside it.
6. Then, as for the hillshade, delete the package item if the layer works.

Publishing alone does not share either layer. Do not share them beyond your account until you decide to.

## Reproduce
```
set CANOPY_LIDAR_ROOT=H:\lidar
set PYTHONNOUSERSITE=1
"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe" reviews\2026-10-22\hosting\tiles\package_tiles.py scheme H:\lidar\2023-salt-lake-valley\runs\tiles-20261023
```
Then run `layer`, `pilot`, `build` and `verify` with the same folder.

Times on the laptop with the SSD as H: (`run.json`):
- October 23: hillshade cache 951 s (the laptop was also running the vector tile datum check), export 3 s; terrain cache
  82 s, export 2 s.
- October 22: hillshade cache 531 s, export 2 s. The display copy has no pyramids; the first cache, from the original
  raster with its overviews, took 92 s. Terrain cache 57 s, export 1 s.
- verification about half a minute.
