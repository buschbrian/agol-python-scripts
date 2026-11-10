# Does the ArcGIS Maps SDK draw the COGs correctly? (October 23, 2026)

**Yes, with one fault, and it has a workaround.** In ArcGIS Maps SDK 5.1.27, a float COG whose **first draw** on the
page uses a **class breaks renderer** and **goes straight to a large scale** draws wrong. Coarse overview tiles are laid
in a repeating grid over the right place (`wrong_terrain_m_1-71_interior_nearest.png`), and the view stays that way: still
wrong 15 s later, and again after moving one screen away and back. Every other view tested drew correctly, including the
last (partial) column and row of tiles, tile corners, every zoom from 1:71 to 1:36,112, and both interpolations. Identify
is never affected. The fault explains the bad pictures in [cog-alignment](../cog-alignment/README.md#drawing-an-open-problem-separate-from-the-datum),
whose band renderers were set before the layers' first draws.

**Workaround: let the layer draw once before giving it a classed renderer, or open at the full extent.** Either one alone
was enough.

Read-only, on local servers (the COGs from 127.0.0.1, cross-origin as from a bucket); nothing was uploaded.

## Method
For each test, the COG is drawn in alternating two-colour bands, about six across the middle 80% of the values in view.
Pixels are sampled at random and their drawn colour is compared with the band of the full-resolution value identify
returns there. Identify is exact (cog-alignment), so it is the reference. A pixel counts only if it is **interior**: all
9 identify values on a 3 x 3 grid around it, one drawn-level cell apart, fall in the same band. The drawn-level cell is
the coarsest overview no finer than a screen pixel, or 0.5 m. Averaging in the overviews and bilinear resampling then
cannot fairly change the pixel's colour. Up to 150 interior pixels are counted per view. Each view is shot when the SDK
reports it settled, and again 3 s later (and 15 s later on fresh loads).

Places ([places.py](places.py), [web/places.json](web/places.json)). The grid is 24,501 x 12,247 cells in 512-cell tiles,
so the last column of tiles is 437 cells wide and the last row 471 tall:

| Place | Cell (col, row) | Why |
|---|---|---|
| interior | 12544, 6400 | the middle of a full-resolution tile |
| tile_corner | 12288, 6144 | a corner of tiles at full resolution and the first two overviews |
| last_column | 24368, 2996 | in the last column of tiles; the cell that drew partly in cog-alignment |
| last_row | 19426, 11950 | in the last row of tiles, where the city reaches it |

## Results
**The sweep** ([results/sweep.json](results/sweep.json)): one page, 4 COGs (`terrain_m`, `slope_percent`, `chm_m` float;
`hillshade` 8-bit) x 2 interpolations x 5 scales x 4 places (1:36,112 once, since it shows the whole city): 136 views. 8
were skipped, all at 1:9,028 by the last row, where under 10 of the 49 values in view were data.

| Place | Interior pixels | Wrong |
|---|---:|---:|
| interior | 4,406 | 23 (below) |
| tile_corner | 3,912 | 0 |
| last_column | 3,884 | 0 |
| last_row | 2,037 | 0 |

- **21** were the sweep's first view: terrain at 1:71, the fault below.
- **2** were `chm_m` at 1:9,028, where the full-resolution value is 0 but the overview cells hold 2-8 m (trees within a few
  metres). That is the right colour for what that zoom draws from: the interior test missed thin trees, not a drawing fault.
- Every view was the same 3 s later. Interpolation made no difference anywhere.
- Thin samples: at 1:71 the last row gave 1-6 interior pixels per view (steep, narrow data), and the hillshade's and slope's
  rough values give 4-74 at some places and scales (all listed in the JSON). The last row is covered by 2,037 pixels across
  scales, but only lightly at 1:71.

**Fresh page loads** (`?mode=one`), interior place unless noted:

| COG, scale, interpolation | First draw | Interior pixels wrong at 0 / 3 / 15 s |
|---|---|---:|
| terrain, 1:71, nearest (twice) | bands, straight to the place | 21 / 21 / 21 of 36 |
| terrain, 1:564, nearest | bands, straight to the place | 81 / 81 / 81 of 150 |
| the same, then one screen east and back | | 81 / 81 of 150 |
| terrain, 1:564, bilinear | bands, straight to the place | 78 / 78 / 78 of 150 |
| terrain, 1:2,257, nearest | bands, straight to the place | 69 / 69 / 69 of 150 |
| slope, 1:71, nearest | bands, straight to the place | 22 / 22 / 22 of 54 |
| hillshade (8-bit), 1:564, nearest | bands, straight to the place | 0 of 146 |
| terrain, 1:564, nearest | default renderer, full extent; then bands | 0 of 150 |
| terrain, 1:564, nearest | bands, full extent; then the place | 0 of 150 |
| terrain, 1:564, nearest | default renderer, straight to the place; then bands | 0 of 150 |

So it takes both: a classed renderer on the first draw, and that draw at a large scale. The default (stretch) first draw
straight to 1:564 looked right (`first_default_terrain_m_1-564_interior.png`: no repeats, and the road under the
basemap's "E 3970 S" label lines up), but a stretch cannot be checked by bands, so that is by eye only. The one 8-bit COG
tried did not fail. Only the interior place was tried on fresh loads.

## What it means for the app
- A Millcreek viewer normally opens at the city extent, which never failed. **Shared links** that open straight at street
  level (the planning map's pattern) are the risk, and only with a classed COG layer. Add
  such a layer, or give it its classes, after its first draw (for example, on the layer view's first
  `updating === false`), or open at the full extent and then go to the linked view.
- A slope-class COG layer would be exactly the case that fails. The slope class vector tiles are not affected.
- Smoke test for the app: open a deep link on a fresh page and compare a few pixels with identify, as here.
- Worth reporting to Esri with `wrong_terrain_m_1-564_interior_nearest.png` and this recipe. The SDK documentation calls
  COG support beta.

## How it was run
```
set PYTHONNOUSERSITE=1
python reviews/2026-10-23/cog-drawing/places.py reviews/2026-10-23/cog-drawing/web/places.json
python reviews/2026-10-23/cog-drawing/serve.py H:\lidar\2023-salt-lake-valley\runs\cog-drawing-20261023
```
Then `http://127.0.0.1:8795/?run=1` for the sweep (about 10 minutes), or for one fresh load, for example
`http://127.0.0.1:8795/?mode=one&cog=terrain_m&scale=564&place=interior&interp=nearest&run=1`, adding `warm=full`,
`warm=fullbands` or `warm=place` and `again=1` as in the table. Playwright's Chromium, 1300 x 900, device pixel ratio 1;
`js.arcgis.com/5.1/` reported 5.1.27 (2026-10-07). [web/drawcheck.js](web/drawcheck.js) does the work. Every JSON is
copied to [results/](results/). Screenshots of every failed view (`wrong_*`, with `_first` for the shot when the view
settled) are in `H:\lidar\2023-salt-lake-valley\runs\cog-drawing-20261023`.

Not tested: the other 12 COGs (8-bit categorical ones such as `observed` among them); fresh loads at the edge places; a
unique-value or colormap renderer; a raster function; a SceneView; any SDK other than 5.1.27; reading from Azure.
