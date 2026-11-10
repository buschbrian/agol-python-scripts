# Citywide terrain products (October 22, 2026)

Slope, aspect, curvature, hillshade, terrain position and contours for all of Millcreek at 0.5 m, from the lidar terrain.
Brian asked for them on October 22, to set beside the products already on ArcGIS Online from coarser DEMs.
Output: `<SSD>\lidar\2023-salt-lake-valley\runs\terrain-city-20261022` ([run_terrain.py](run_terrain.py)).
**Unvalidated planning estimates, not surveyed surfaces.**

## Which terrain
The bare-earth terrain is the one in the October 19 and October 22 libraries (`terrain_m.tif`), interpolated from the
October 8 class-2 ground returns. The October 21-22 reclassification changed buildings and vegetation, not ground, so these
products would be the same from any of those runs. The difference from a public DEM is the source and resolution: QL1 lidar
at 0.32 m pulse spacing gridded at 0.5 m, against the 1 m to 10 m of most published DEMs.

Everything is computed on the unmasked mosaic (`millcreek-products-20261019\terrain_context.tif`, 200,540,655 cells,
identical to the city terrain on all 133,813,488 city cells) and masked to the city only at the end, so slope and terrain
position at the city edge use their full neighbourhood wherever the mosaic reaches.

## Products
In the run folder (city only; NoData outside), with the unmasked versions in `context\`:

| File | Meaning |
|---|---|
| slope_degrees.tif, slope_percent.tif | Slope over a 3 m neighbourhood (Surface Parameters) |
| aspect_degrees.tif | Downslope direction from north; flat cells -1 |
| profile_curvature.tif, tangential_curvature.tif | Curvature along and across the slope |
| hillshade.tif | Sun from 315 degrees at 45 degrees, no shadows; for display |
| terrain_position_m.tif | Elevation minus the mean terrain within 10 m: positive on rises, negative in hollows |
| terrain_neighborhood_complete.tif | 1 where the whole 10 m neighbourhood is terrain; 0 near the edge of the mosaic |
| terrain.gdb/contours | 2 m contours of the city terrain; INDEX = 1 every 10 m |

Drainage, which the pilot bundle also made, is left out: routing needs the whole contributing catchment, not a city-shaped
grid ([PLANNING_PRODUCTS.md](../../../PLANNING_PRODUCTS.md#drainage-interpretation)).

## How it was checked
- **Same method as the pilot.** `run_terrain.py pilot` ran `canopy.planning.terrain`, unchanged, and this script's `derive()`
  on the same 1 km window (433149-434149 E, 4505133-4506133 N: the fully covered city window with the most relief, 467 m;
  2,000 x 2,000 cells, the pilot's limit). All seven rasters are identical on every cell, NoData included
  (`pilot\pilot.json`; copies of pilot.json, verify.json and terrain.json are beside this README). A first window had only 280,800 terrain cells and was replaced.
- **The citywide run equals the pilot.** On that window, 11 m in from its edges (3,825,936 cells), every citywide product
  equals the pilot's exactly (`verify.json`), so processing the whole grid at once changed nothing.
- **The mask.** Every one of the 133,813,488 city cells has a value in every product, and no product has a value outside
  the city (`verify.json`).
- **Edges.** 198,724,185 of the mosaic's 200,540,655 cells have their whole 10 m neighbourhood; inside the city only 650
  cells do not (terrain_neighborhood_complete = 0).

## Figures
- Slope (percent) across the city: median 4.5, 90th percentile 47.3, 99th 84.8; 22.7% of the city is steeper than 15%, 14.7%
  steeper than 30% (almost all in the east-bench foothills).
- Contours: 15,149 lines, 3,260 of them index contours, 2,447 km in all. At 0.5 m they follow every curb and berm; for a
  small-scale map, symbolise INDEX = 1 only or generalise a copy.

Run: 20:10 to 21:06 on October 22, 2026, ArcGIS Pro on the laptop with the SSD as H: (`run.log`, `terrain.json`). The run
folder holds 8.4 GB, 7.1 GB of it the unmasked `context\` copies, which can be deleted if space is needed.
