# Vector tile packages for ArcGIS Online (October 22, 2026)

Step 4 of the hosting plan (`hosting/PLAN.md`): vector tile packages of the slope classes, treetops, crowns and 2 m
contours, built and checked locally. **Nothing was uploaded or published**; that is Brian's step, below.
Script: [build_vector_tiles.py](build_vector_tiles.py) (treetops, crowns, contours; `verify` also covers the slope package,
which [slope-tiles](../../slope-tiles/README.md) makes). All four are unvalidated LiDAR planning estimates, and each
package's summary says so.

## The packages

| Package | Source | Features | Size | Levels (scale) | Symbols |
|---|---|---|---|---|---|
| `runs\slope-tiles-20261022\millcreek_slope_classes.vtpk` | slope-tiles `slope_classes` | 129,352 polygons | 22.7 MB | 0-17 (all scales) | 6 slope classes, YlOrRd |
| `runs\vector-tiles-20261022\millcreek_treetops.vtpk` | `millcreek-products-20261022\tree-count.gdb\city_treetops` | 527,140 points | 7.7 MB | 14-17 (1:18,056 and closer) | 5 height classes, YlGn circles |
| `runs\vector-tiles-20261022\millcreek_crowns.vtpk` | `millcreek-products-20261022\crowns.gdb\crowns` | 400,063 polygons | 33.9 MB | 14-17 (1:18,056 and closer) | 5 treetop-height classes, YlGn fills |
| `runs\vector-tiles-20261022\millcreek_contours.vtpk` | `terrain-city-20261022\terrain.gdb\contours` | 15,149 lines | 6.7 MB | 10-17 (1:288,895 and closer) | index lines (INDEX = 1, 10 m) solid at every level; 2 m lines at 60% opacity from 1:18,056. The script set 1.2 pt and 0.5 pt, but the package's style has 1.33 px (1 pt) for both (found October 23 after upload); set widths in the online style |

All four: 71 MB. Heights are classed 2 to 5, 5 to 10, 10 to 15, 15 to 20 and 20 m and over (treetop height; a crown carries
its treetop's). Levels are the ArcGIS Online vector tile scheme (512-pixel tiles, level n = 1:295,828,763.795777 / 2^n,
Web Mercator); level 17 is about 0.23 m per pixel here, and clients overzoom past it. The tiles are indexed: sparse areas
stop at a shallower level and are overzoomed. Each package's `.aprx` (the map it was made from) is beside it.

Contours are generalised at small scales by the tiling itself (each level is simplified to its pixel size), and only the
10 m index lines are drawn below level 14. At 0.5 m the 2 m lines follow curbs and berms.

## What the tiles keep
**No source attributes.** Each tile keeps only Esri's `_symbol` (the class index; the contours have one symbol per layer
and keep nothing) and `__minzoom`. Dropped (`verify.json`, read by decoding one tile of each package):
- slope: SLOPE_CODE, SLOPE_CLASS;
- treetops: TREE_ID, HEIGHT_M, OWNERSHIP, OWNER_GROUP, PARCEL_MATCHES, OCT8 and the empty census fields;
- crowns: TREE_ID, HEIGHT_M, CROWN_AREA_M2, CROWN_DIAM_M;
- contours: Contour, INDEX.

So a hosted vector tile layer draws and has a legend (the style's layer names carry the class labels, for example
`Treetops by height/10 to 15 m`), but has no pop-ups, no identify, and no filtering by value. For those, publish the
feature class as a hosted feature layer too (feature storage costs far more per GB; see the plan's step 2), or use the
vector tiles for drawing and the feature layer only for queries.

## Datum
All four packages carry `WGS_1984_(ITRF08)_To_NAD_1983_2011` from NAD83(2011) to WGS84 / Web Mercator, the transformation
of the building scene layers and the rebuilt hillshade and terrain packages ([tiles](../tiles/README.md#datum-rebuilt-october-23)).
The script sets none; Pro gives a map in Web Mercator that transformation by default, and each `.aprx` records it. Because
Manage Tile Cache ignores transformation settings, the packages were checked from the tiles themselves on October 23
([datum_check.py](datum_check.py), `datum.json`): every vertex in the four tiles nearest the city centre at the deepest
level (16), against the nearest source vertex projected each way.

| Package | Tile vertices | Median distance, with ITRF08 | Median distance, no transformation |
|---|---:|---:|---:|
| slope classes | 139,373 | 0.060 m | 0.732 m |
| treetops | 11,551 | 0.059 m | 1.576 m |
| crowns | 233,264 | 0.061 m | 0.734 m |
| contours | 18,090 | 0.064 m | 0.946 m |

About 6 cm is half a level-16 tile unit (15 cm), the tiles' own rounding. The treetops show the 1.58 m Web Mercator shift
cleanly; polygon and line vertices on the 0.5 m grid often land near another vertex when shifted, so their wrong-choice
distances are smaller, but still ten times the right one.

## How it was checked
- **Pilot first**: each layer clipped to one 1 km window in the middle of the city (427,774 to 428,774 E, 4,503,821 to
  4,504,821 N: 11,216 treetops, 8,614 crowns, 527 contours), packaged in under a minute each (`pilot.json`).
- **Feature counts in** equal the sources: 527,140 treetops, 400,063 crowns, 15,149 contours, 129,352 slope polygons.
- **Points in the tiles.** Every treetop tile was decoded and its points counted inside the tile's own extent. In the
  pilot, 11,212 points are inside tiles and 4 sit exactly on a tile edge after rounding (x = 4096 in one tile, -1 in the
  next): all 11,216. In the city package the leaf tiles hold 526,997 points and 130 on edges, 527,127 of 527,140; the last
  13 (0.002%) are not accounted for by this census, most likely edge points between neighbouring tiles at different levels.
  Nothing in it suggests thinning: level 14 alone holds 525,806 points.
- **The packages**: `p12/root.json` has the Web Mercator scheme (102100/3857) and the scale range above; the styles have the
  labelled class layers with the minimum zooms above; Pro adds each package to a map as a vector tile layer
  (CIMVectorTileLayer) (`verify.json`).
- **They draw**: each package was rendered on a Pro layout at 1:9,000 and 1:20,000 over a residential area with foothills
  (not kept). Crowns and treetops draw from 1:18,056 inward; at 1:20,000 the contours show only index lines.

Run: 22:23 to 22:34 on October 22, 2026, ArcGIS Pro 3.7.3 on the laptop with the SSD as H: (`run.log`, `packages.json`).

## How the map is scripted
No Pro UI: copy the install's `Resources\ArcToolBox\Services\routingservices\data\Blank.aprx`, delete its maps,
`createMap`, add the layers, symbolise, then pass the Map object to Create Vector Tile Package. What Pro insists on:
- the map needs a description in its metadata (`ERROR 001117`): set `map.metadata` fields and `save()` it;
- the map must be in Web Mercator, and adding the first layer resets it to the data's EPSG 6341: set
  `map.spatialReference` after adding layers (`ERROR 000707`);
- scales must be on the 512-pixel vector scheme (`ERROR 001856` for the raster scheme's 1:591,657,528);
- graduated-colour labels set through `arcpy.mp` are rewritten when the renderer is assigned: set them in the layer's CIM
  (`getDefinition`/`setDefinition`);
- a new unique value renderer defaults to the first field; with a per-feature `Id` its fields cannot be set.

## Upload steps for Brian
Do these only when you decide to publish; each upload is a separate go-ahead.
1. Sign in to ArcGIS Online with an account that can create content and publish hosted tile layers.
2. Content > My content > New item > Your device, and choose the `.vtpk` (paths above; all under 40 MB, so the browser
   upload is fine).
3. Keep the option to add the package **and create a hosted vector tile layer**. Give a title and tags (the package's
   summary and tags carry over as a starting point; keep the estimate warning in the description).
4. Save. ArcGIS Online unpacks the tiles; open the new tile layer in Map Viewer and check it draws at the scales above.
5. Once the layer works, delete the uploaded package item (not the tile layer) so the storage is not counted twice.
6. Share it as decided (plan decision 3: public or internal).

## Hosting cost
Esri's credits page (doc.arcgis.com, "Understand credits", checked October 22, 2026) puts vector tile layers under file
and other content storage: **1.2 credits per GB per month**, calculated hourly. Assuming the hosted tiles take about the
package size (to confirm on the item page after upload), the four layers are about 0.071 GB:

| | GB | Credits per month | Credits per year |
|---|---|---|---|
| Tile layers only (packages deleted) | 0.071 | 0.09 | about 1 |
| Tile layers and packages kept | 0.142 | 0.17 | about 2 |

Esri also lists tile generation (1 credit per 10,000 tiles generated). The packages arrive already tiled, so this should
not apply to them, but the page does not say so for packages: check the organisation's credit report after the first
upload.
