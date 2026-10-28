# Do the COGs line up with the hosted layers in a Web Mercator web map? (October 23, 2026)

**Yes.** The ArcGIS Maps SDK for JavaScript (5.1.27) puts the EPSG:6341 COGs where `WGS_1984_(ITRF08)_To_NAD_1983_2011`
puts them (or a transformation within a few millimetres of it: the ITRF00 one differs here by about 6 mm), the
transformation every hosted package carries ([PUBLISHING.md](../PUBLISHING.md#datum-resolved-october-23)).
Nobody has to name it: the SDK picks it. Against the published contours the COG sits within about 5 cm. Read-only test, on
local servers; nothing was uploaded or shared.

The question came from the web app plan: the hillshade and terrain packages had sat 1.197 m off the rest until they were
rebuilt with the transformation, and the COG trial ([cogs](../../2026-10-22/hosting/cogs/README.md#web-trial-slope-percent-in-the-arcgis-maps-sdk))
proved the values but never the position. The two candidates differ by 1.579 m in Web Mercator (1.197 m on the ground):
(-1.301, +0.894) m from the transformed position to the untransformed one.

## Results
**1. The SDK's own projection.** `projectOperator.execute` from 6341 to Web Mercator, with no transformation named, lands
on the ITRF08 position of all 8 check cells (differences under 2e-9 m) and 1.197 m from the untransformed one.

**2. Identify and drawing, cell by cell.** Eight steep cells (slope 50-65%) in the east-bench foothills, each with a float32
value no cell within 20 cells shares ([cells.py](cells.py), [web/cells.json](web/cells.json)). *Identify*: the
`slope_percent` COG queried on a 6 cm grid of Web Mercator points around both candidate positions; the centroid of the
points that return the cell's own value. *Drawn*: a renderer that colours only that value, the view at 1:70 (0.019 m a
pixel, the cell about 35 px across), the centroid of the coloured pixels.

| Cell (col, row) | Identify, from ITRF08 | from none | Drawn, from ITRF08 | from none |
|---|---:|---:|---:|---:|
| 24368, 2996 | 0.004 m | 1.199 m | see below | |
| 23744, 4284 | 0.005 | 1.200 | 0.004 | 1.194 |
| 21208, 10342 | 0.005 | 1.200 | 0.002 | 1.199 |
| 21136, 1364 | 0.004 | 1.200 | 0.002 | 1.197 |
| 22648, 2740 | 0.004 | 1.200 | 0.002 | 1.199 |
| 23624, 6389 | 0.005 | 1.200 | 0.007 | 1.195 |
| 23104, 5533 | 0.005 | 1.200 | 0.004 | 1.193 |
| 23728, 2148 | 0.004 | 1.200 | 0.004 | 1.194 |

Ground metres. The 4-5 mm left in identify is the 6 cm grid's centroid. The terrain COG's identify was also checked at the
same 8 cells: GDAL's value bit for bit, through a Web Mercator point and through a 6341 point.

Cell 24368, 2996 did not draw whole in the scripted runs: 19 px of the cell's colour with the view centred between the two
candidates, then 29 px with it centred on the ITRF08 position (1.26 m away), in every fresh run. Drawn by hand afterwards
in the same session at the same scale, it drew whole (1,296 px) and centred on the ITRF08 position to the pixel
(`cell0_by_hand_1-70.png`). It is the only cell in the COGs' last column of 512-cell tiles (column 24,064 onwards; the
grid is 24,501 wide); see *Drawing* below. No cause is claimed.

**3. Against the published contours.** 640 vertices of the hosted 2 m contours, 80 from the level 16 tile holding each
check cell, fetched from the Vector Tile Service and decoded ([contour_vertices.py](contour_vertices.py)). The tiles carry
no attributes, but every line is a 2 m contour, so the terrain under a vertex should be a multiple of 2 m. The terrain COG
was identified through the SDK at each vertex, moved by a trial shift:

| Vertices moved by | Distance from a 2 m multiple, median | mean |
|---|---:|---:|
| nothing | **0.070 m** | 0.097 m |
| the untransformed offset | 0.461 | 0.471 |
| the untransformed offset, reversed | 0.470 | 0.465 |

A uniform guess would average 0.5 m. Searching shifts on a 0.35 m grid (to 1.75 m each way) and then a 0.07 m grid around
the best, the best shift is (0, 0); its neighbours 7 cm away score 0.097-0.099, so the COG and the contours agree to within
that step, about 5 cm on the ground. This agrees with the contours' own 6 cm from their transformed source (the tile grid
is 15 cm at level 16; [vector-tiles](../../2026-10-22/hosting/vector-tiles/README.md#datum)).

Every result is in [results.json](results.json) (the final run, cell 1, 1:564).

## Drawing: an open problem, separate from the datum
**Resolved the same day in [cog-drawing](../cog-drawing/README.md):** a float COG whose first draw uses a class breaks
renderer and goes straight to a large scale draws coarse tiles in a repeating grid and stays that way. The band renderers
here were set before the terrain layer's first draw, which went straight to the picture's scale. Once past that first
draw, every place and zoom tested, the last tile column and row included, drew correctly. The notes below are as written
before that.

The pictures meant to show the contours over the terrain COG, drawn in alternating height bands, did not come out right,
although identify was exact throughout and the data server answered all 341 range requests behind them with 206 (the
only other answers were 404s for the optional `.aux.xml` sidecars):
- **In the last tile column** (the steep spot by cell 24368, 2996): at 1:564 and 1:2,257 the terrain drew with strips
  missing and strips repeated (`bands_only_cell0_1-2257.png`, `dbg_terrain_default_500.png`, the default renderer too).
- **Well inside the grid** (cell 23744, 4284), drawn colour checked against identify at 300 random pixels each
  ([drawn_vs_identify.json](drawn_vs_identify.json)): terrain at 1:2,257 in 10 m bands disagreed with the
  full-resolution identify at **40 of 300** pixels. At that zoom the SDK draws from a coarser, averaged overview, so pixels
  near a band edge can fairly take the other colour; that is not shown to be wrong. Terrain at 1:564 and 1:70, and slope
  at 1:2,257 and 1:70, disagreed at none. Yet a fresh page's 10 m band picture at 1:564
  (`contours_and_bands_cell1_1-564.png`) shows seams at fixed screen lines and bands about three times as dense as the
  index contours. That picture also draws the contours overzoomed through the proxy's added levels (below), so it may be
  wrong on either side. Not resolved.

So drawing the COGs needs its own check before an app relies on it: which COGs, which zooms, the last tile column and row
(the grid is 12,247 rows, so the last row of tiles is partial too), and whether interpolation matters. Identify, and
therefore exact values on click, is not affected by anything seen here. The shift score of the band pictures in
`results.json` (`contours`) is not used, for the same reason.

## How it was run
- [cells.py](cells.py) (Pro Python): the check cells from the `slope_percent` COG, each centre projected to Web Mercator
  with arcpy, with the transformation and with none. Its `steep_edge` (cell 0) was the first runs' picture spot; the page
  now takes the spot from `?at=` (default cell 1), because cell 0 is in the last tile column.
- [serve.py](serve.py) (Pro Python, signed in to the portal): the page on 127.0.0.1:8793, the COGs on 8794 (the COG trial's
  range and CORS server, so every read is cross-origin), and `/proxy/contours/...` to the private hosted contours with
  `arcpy.GetSigninToken()` and its bound referer. The token never reaches the page or the log; it lasts about 30 minutes.
  The hosted service stops at 1:2,257 (level 17) and the SDK suspends the layer past it even with `maxScale = 0`, so the
  proxy adds levels 18-22 to the service description; the style says `maxzoom` 17, so those levels draw from level 17
  tiles. Only the pictures use it; the vertices come from the tiles as served.
- [web/align.js](web/align.js): the measurements; [contour_vertices.py](contour_vertices.py): the vertices. Pictures and
  every run's JSON are in `H:\lidar\2023-salt-lake-valley\runs\cog-alignment-20261023`.
- Playwright's Chromium, 1300 x 900, device pixel ratio 1; SDK from `js.arcgis.com/5.1/`, which reported 5.1.27
  (2026-10-07).

```
set PYTHONNOUSERSITE=1
python reviews/2026-10-23/cog-alignment/cells.py reviews/2026-10-23/cog-alignment/web/cells.json
python reviews/2026-10-23/cog-alignment/serve.py H:\lidar\2023-salt-lake-valley\runs\cog-alignment-20261023
python reviews/2026-10-23/cog-alignment/contour_vertices.py reviews/2026-10-23/cog-alignment/web/contour_vertices.json
```
then open `http://127.0.0.1:8793/?at=1&scale=564&search=20&run=1`.

Not tested: COGs other than `slope_percent` (drawn and identified) and `terrain_m` (identified, drawn in bands); a
SceneView; another SDK version (js.arcgis.com/5.1 moves with 5.1 patches); the COGs from Azure rather than 127.0.0.1.
