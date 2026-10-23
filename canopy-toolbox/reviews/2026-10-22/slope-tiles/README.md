# Slope classes as polygons and vector tiles (October 22, 2026)

Millcreek slope in six classes from the citywide 0.5 m lidar slope, as a polygon feature class and a vector tile package
for ArcGIS Online. Brian asked for "slopes above 10%, 15%, 20%, 25% and 30% in 6 different vector classes", to set beside
the coarser DEM slope layers already on ArcGIS Online.
Output: `<SSD>\lidar\2023-salt-lake-valley\runs\slope-tiles-20261022` ([run_slope_tiles.py](run_slope_tiles.py)).
**Unvalidated planning estimates, not surveyed surfaces.** Nothing was uploaded or published.

## Products

| File | Meaning |
|---|---|
| millcreek_slope_classes.vtpk | Vector tile package, ArcGIS Online (Web Mercator) scheme, levels 0 to 17; 22.7 MB |
| slope_tiles.gdb/slope_classes | 129,352 polygons, EPSG 6341; SLOPE_CODE (1-6) and SLOPE_CLASS (label) |
| millcreek_slope_classes.aprx | The project the package was made from (one map, the symbolised layer) |
| slope_class.tif | The cleaned class raster the polygons come from (uint8, NoData 0) |
| slope_class_raw.tif | The classes before cleanup |
| classes.json, polygons.json, tiles.json, verify.json, run.log | Run records (copies of the JSONs beside this README) |
| pilot\ | The whole chain on one 1 km window (`pilot.json`) |

| SLOPE_CODE | SLOPE_CLASS | Percent slope | Colour |
|---|---|---|---|
| 1 | Under 10% | below 10 | #FFFFB2 |
| 2 | 10% to 15% | 10 to under 15 | #FED976 |
| 3 | 15% to 20% | 15 to under 20 | #FEB24C |
| 4 | 20% to 25% | 20 to under 25 | #FD8D3C |
| 5 | 25% to 30% | 25 to under 30 | #F03B20 |
| 6 | 30% and over | 30 and above | #BD0026 |

A break value belongs to the class above it (exactly 10.0% is class 2). The colours are ColorBrewer's YlOrRd; the legend
labels are the SLOPE_CLASS text. The source is `terrain-city-20261022\slope_percent.tif` (3 m Surface Parameters
neighbourhood; [terrain-city](../terrain-city/README.md)).

## Cleanup: a 4 m2 minimum mapping unit
Classified as it is, the 0.5 m slope makes 924,458 patches, and 790,523 of them are under 4 m2. Almost all the fragments
are in the four 5-point classes between 10% and 30%: on a graded hillside the slope wanders across a break from cell to
cell, so those classes come out as speckle (189,025 to 244,364 patches each, against 13,685 for under 10% and 11,292 for
30% and over).

The cleanup is a **minimum mapping unit of 16 cells (4 m2)**: every 4-connected patch of one class smaller than that joins
its largest neighbouring patch (GDAL SieveFilter, repeated until none is left; 3,370 small patches after the first pass,
15 after the second, then 1). Nothing else changes, so wherever a patch was 4 m2 or larger its class is exactly the
raster's. There is no simplification: polygon edges are cell edges, so polygon areas equal the cleaned raster's areas.

| Class | Raw ha | Raw % of city | Cleaned ha | Cleaned % | Change (ha) | Change (% of class) | Raw patches | Polygons |
|---|---|---|---|---|---|---|---|---|
| Under 10% | 2,373.99 | 70.96 | 2,389.29 | 71.42 | +15.30 | +0.6% | 13,685 | 8,581 |
| 10% to 15% | 213.49 | 6.38 | 209.48 | 6.26 | -4.02 | -1.9% | 189,025 | 35,783 |
| 15% to 20% | 123.46 | 3.69 | 113.64 | 3.40 | -9.82 | -8.0% | 237,705 | 31,053 |
| 20% to 25% | 82.85 | 2.48 | 72.43 | 2.16 | -10.42 | -12.6% | 244,364 | 25,764 |
| 25% to 30% | 60.45 | 1.81 | 51.38 | 1.54 | -9.06 | -15.0% | 228,387 | 20,408 |
| 30% and over | 491.11 | 14.68 | 509.13 | 15.22 | +18.02 | +3.7% | 11,292 | 7,763 |

The area above each of Brian's thresholds moves by at most about half a point of city area:

| Area at or above | Raw % of city | Polygons % of city | Change (points) |
|---|---|---|---|
| 10% | 29.04 | 28.58 | -0.46 |
| 15% | 22.65 | 22.32 | -0.34 |
| 20% | 18.96 | 18.92 | -0.04 |
| 25% | 16.49 | 16.75 | +0.27 |
| 30% | 14.68 | 15.22 | +0.54 |

What it costs: the sieve hands the speckle to whichever class surrounds it, which is usually the large under-10% or
30%-and-over patches. So the narrow middle classes shrink (25% to 30% loses 15% of its area), and real small steep features
under 4 m2 (curb faces, short retaining walls) disappear by design. The cumulative "steeper than" areas, the reading the
request asks for, hold to within 0.54 points. **This is a choice for Brian:** for exact class areas, a package without
cleanup (924,458 polygons) is the same script with `MMU_CELLS = 1`.

Alternatives tried on the whole grid (scratch probes, not kept): majority filters of 3 x 3, 5 x 5 and 9 x 9 cells shrank
the middle classes as much or more (5 x 5: 25% to 30% -19%) and still left 57,000 to 177,000 patches per middle class.
Larger sieves cut the middle classes much harder (25 m2: 25% to 30% -35%; 100 m2: -50%).

Reading the map: a render of the package at 1:9,000 over a residential area shows the 30%-and-over class tracing street
edges and road embankments in the flat valley, as well as the hillsides on the east bench. A coarser DEM slope smooths such
man-made edges away, so expect the lidar layer to show more steep area along streets than the existing layers.

## Vector tile package
Made without the Pro UI: a copy of the install's `Blank.aprx`, one new map, the feature class with a unique value renderer
on SLOPE_CODE (labelled, solid fills, no outlines), then Create Vector Tile Package (ONLINE, INDEXED). What Pro insists on,
found in the pilot:
- the map's metadata needs a description (`ERROR 001117`); the script sets title, summary (with the estimate warning),
  description, tags and credits on `map.metadata`;
- the map must be in Web Mercator, and adding the first layer resets it to the data's EPSG 6341, so the spatial reference
  is set after the layer (`ERROR 000707`);
- scales come from the vector tile scheme (512-pixel tiles, level n = 295,828,763.795777 / 2^n), not the raster scheme
  (`ERROR 001856`);
- RasterToPolygon's per-polygon `Id` field is dropped: a new unique value renderer defaults to it and, with 129k values,
  comes back without settable fields.

Levels 0 to 17 (1:295,828,764 to 1:2,257; at level 17 a pixel is about 0.23 m on the ground here, finer than the 0.5 m
cells). The tiles are indexed, so sparse areas stop at a shallower level and clients overzoom past level 17.

The tiles keep only Esri's `_symbol` (the class index) and `__minzoom`; SLOPE_CODE and SLOPE_CLASS are not in them (see the
[vector tiles README](../hosting/vector-tiles/README.md#what-the-tiles-keep)). The legend labels come from the style:
its six fill layers are named `Slope classes/Under 10%/1` to `Slope classes/30% and over/1`. For identify or queries, use
the feature class.

## How it was checked
- **Polygons equal the cleaned raster.** Area summed from the polygons per class equals the cleaned raster's cells x 0.25
  m2 exactly for all six classes, and the polygon total is the city's 33,453,372 m2 (133,813,488 cells) (`verify.json`).
- **Counts.** 129,352 polygons, equal to the cleaned raster's 4-connected patches (`classes.json`), and every SLOPE_CLASS
  matches its SLOPE_CODE.
- **The cleanup change** is the table above (polygon area against the raw class raster, from `verify.json`).
- **One patch under 4 m2 remains**: a single 30%-and-over cell at the north city edge (431,964 E, 4,507,362 N) that touches
  its class only at a corner and otherwise touches NoData, so it has no 4-connected neighbour to merge into.
- **The package.** Its `p12/root.json` has the Web Mercator scheme (102100/3857), levels 0 to 17, scales 1:295,828,764 to
  1:2,257; its style has the six labelled fill layers in class order with the colours above; Pro adds it to a map as a
  vector tile layer (CIMVectorTileLayer) (`verify.json`).
- **Pilot first.** The chain ran on the terrain-city pilot window (433,149 to 434,149 E, 4,505,133 to 4,506,133 N): 4,014
  polygons, a 4.6 MB package in one minute (`pilot.json`).

Run: classes 21:48 to 22:03, polygons 22:14 to 22:16 and the package 22:18 to 22:26 on October 22, 2026, ArcGIS Pro 3.7.3
on the laptop with the SSD as H:. The run folder holds 259 MB.

## Upload (Brian's step)
See [the vector tiles README](../hosting/vector-tiles/README.md#upload-steps-for-brian): ArcGIS Online, Content > New item >
Your device > `millcreek_slope_classes.vtpk`, and keep "create a hosted vector tile layer" selected.
