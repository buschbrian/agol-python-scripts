---
key: urban_terrain
id: 83d1a892fd67408b9f8f9fcb754cd479
title: Millcreek bare-earth terrain for ArcGIS Urban, UTM 12N 0.5 m (2023 lidar), planning estimate
summary: Bare-earth ground elevation for Millcreek, Utah, at 0.5 m from the 2023 lidar, metres NAVD88, as the elevation layer of a local ArcGIS Urban model in UTM 12N. Unvalidated planning estimate; not surveyed or field-verified.
tags: Millcreek, Utah, Salt Lake County, lidar, 2023 lidar, 3DEP, planning estimate, elevation, terrain, bare earth, DEM, ground, elevation layer, 3D, ArcGIS Urban, UTM
credits: City of Millcreek GIS. Lidar: 2023 Salt Lake Valley QL1 lidar (USGS 3DEP, project UT_2023SaltLakeCo_C24).
iso_topics: elevation
resolution_m: 0.5
lineage: Bare-earth terrain interpolated at 0.5 m from ground returns of the 2023 Salt Lake Valley QL1 lidar (the unmasked mosaic), cached as LERC elevation tiles (maximum error 0.01 m) on a NAD83(2011) UTM 12N tiling scheme, levels 0 to 14 halving from 8,192 m to 0.5 m pixels, with no datum transformation; NAVD88 (Geoid18) metres. Published October 26, 2026.
---

# Description

{{warning}}

## What it shows
The elevation of the bare ground (buildings and vegetation removed) across Millcreek, Utah, and the surrounding lidar coverage, at
0.5 m, as an **elevation layer in NAD83(2011) UTM zone 12N**. It is the ground for a **local ArcGIS Urban model** or a local scene in
that coordinate system, where Esri's World Elevation cannot be used. The public **Millcreek bare-earth terrain 0.5 m** layer holds the
same ground in Web Mercator for global scenes.

## Using it in ArcGIS Urban
- A local Urban model has no default ground, so this layer is its whole ground. Outside the lidar coverage there is no elevation.
- **Urban requires the elevation layer and the basemap to share a coordinate system and a tiling scheme.** The model's basemap must
  therefore be a tiled layer in UTM 12N on this layer's tiling scheme (origin, tile size and levels below). The tiling scheme file is
  kept with the processing records; a basemap built on it may add finer levels (0.25 m and below).
- The 3D buildings for ArcGIS Urban were built on this terrain and use the same coordinates and heights.

## Values
| Property | Value |
|---|---|
| Units | Metres |
| Vertical datum | NAVD88, geoid model Geoid18 (orthometric heights) |
| Elevation range | 1,289.94 m to 2,488.74 m (about 4,232 ft to 8,165 ft) |
| Coordinate system | NAD83(2011) / UTM zone 12N (EPSG 6341), no datum transformation |
| Tiling scheme | Tile origin X -5,120,900, Y 9,998,100; 256 x 256 tiles (257 x 257 elevation pixels, corner-registered); 96 dpi; levels 0 to 14 at 8,192, 4,096, ... 1, 0.5 m per pixel (scale 1:30,961,827.84 to 1:1,889.76) |
| Tiles | 32-bit float, one band, LERC, maximum error **0.01 m**; 5,587 tiles, 4,040 at 0.5 m |
| Extent | The whole lidar mosaic over Millcreek (about 51 km2), not just the city |

## How it was made
1. The lidar's ground-classified returns (class 2) were interpolated to a 0.5 m bare-earth surface. Under buildings and dense
   vegetation the ground is interpolated from the nearest ground returns. The unmasked mosaic is used: on every city cell it is
   identical to the city terrain, and it carries the ground on past the city boundary.
2. A tiling scheme was generated in UTM 12N whose finest level is the source's 0.5 m, so each finest-level pixel sits on a source cell
   corner and no level is coarser than the data needs. The surface was cached on it as LERC elevation tiles (0.01 m) and published as a
   hosted elevation layer on October 26, 2026.

## Accuracy and checks
- **Compression and tiling.** 300 points (150 flat, 150 steep) at their nearest 0.5 m pixel against the city terrain interpolated at
  the same place: median difference 0.005 m, maximum 0.010 m.
- Against the source cell a clicked point falls in, differences reach 0.68 m on steep ground (median 0.16 m) and 0.025 m on flat
  ground: the pixel sits on a cell corner, not the cell centre.
- The hosted service is an elevation layer in 6341 with the same origin and levels as the package; tiles fetched from it are byte
  for byte the package's.
- **The ground itself has not been checked against field survey.** QL1 lidar is specified to 10 cm vertically (RMSEz) on open,
  non-vegetated ground; this project's vendor accuracy report has not been reviewed.
- **Not yet seen in a local scene or in ArcGIS Urban**, which needs a basemap on the same tiling scheme first.

## Limits
- Ground as it was in October and November 2023; grading since then is not reflected.
- Under buildings the ground is interpolated, so building sites are smoothed.
- Not for engineering design, grading, flood elevations or surveying.
- The edge of the coverage follows the 1 km lidar tiles, so it is a staircase.

{{coordinates_utm}}

{{lidar}}

{{set_urban}}

{{contact}}

# Terms of use

{{terms}}
