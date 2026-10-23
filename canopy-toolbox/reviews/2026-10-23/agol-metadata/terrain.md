---
key: terrain
id: ce1680a5196e458ebfb60ead5150b946
title: Millcreek bare-earth terrain 0.5 m (2023 lidar), planning estimate
summary: Bare-earth ground elevation for Millcreek, Utah, at 0.5 m from the 2023 lidar, in metres NAVD88, as an elevation layer for 3D scenes. Unvalidated planning estimate; not surveyed or field-verified.
tags: Millcreek, Utah, Salt Lake County, lidar, 2023 lidar, 3DEP, planning estimate, elevation, terrain, bare earth, DEM, ground, elevation layer, 3D
credits: City of Millcreek GIS. Lidar: 2023 Salt Lake Valley QL1 lidar (USGS 3DEP, project UT_2023SaltLakeCo_C24).
---

# Description

{{warning}}

## What it shows
The elevation of the bare ground (buildings and vegetation removed) across Millcreek, Utah, and the surrounding lidar
coverage, at 0.5 m. It is an **elevation layer**: use it as the ground of a web scene, where it replaces Esri's coarser
World Elevation with the 2023 lidar ground. The Millcreek 3D buildings were built on this terrain and stand on it
exactly.

## Using it in a scene
In Scene Viewer, add this layer to the scene's **Ground**, above World Elevation. Keep World Elevation underneath: this
layer covers only the lidar area (51.0 km2, about 1.5 times the city), and World Elevation fills in around it. Where the
two meet, mostly in the foothills and neighbouring cities, expect a small step along the edge of the lidar tiles.

## Values
| Property | Value |
|---|---|
| Units | Metres |
| Vertical datum | NAVD88, geoid model Geoid18 (orthometric heights, the same kind as World Elevation) |
| Elevation range | 1,289.94 m to 2,488.74 m (about 4,232 ft to 8,165 ft) |
| Ground resolution | 0.5 m source; finest tile level 18, about 0.45 m per pixel on the ground |
| Tiles | 32-bit float, one band, LERC compression, 257 x 257 pixels, levels 0 to 18 on the ArcGIS Online elevation scheme |
| LERC maximum error | **0.01 m** (1 cm): the compression changes no value by more than this. Esri's default is 0.1 m, as large as the lidar's own specified accuracy, so 0.01 m was used. |
| Extent | The whole lidar mosaic over Millcreek (51.0 km2), not just the city; no data outside it |

## How it was made
1. The lidar's ground-classified returns (class 2) were interpolated to a 0.5 m bare-earth surface. Under buildings and
   dense vegetation the ground is interpolated from the nearest ground returns.
2. The surface was cached as elevation tiles (LERC, 0.01 m) on the ArcGIS Online elevation tiling scheme, in Web Mercator
   with the ITRF08 transformation, and published as a hosted elevation layer.

## Accuracy and checks
- **Compression and tiling.** 300 points sampled from the package (150 flat, 150 steep) against the source terrain at the
  same position: median difference 0.005 m; maximum 0.010 m on flat ground and 0.012 m on steep ground. Read 1.2 m off
  (no datum transformation), steep points would differ by up to 2.8 m.
- Against the source cell a clicked point falls in, differences reach 0.8 m on steep ground (median 0.06 m), from
  re-gridding to 0.45 m tiles, not from compression.
- Tiles fetched from the hosted layer are byte for byte the package's, and the tile counts per level equal the
  package's.
- **The ground itself has not been checked against field survey.** QL1 lidar is specified to 10 cm vertically (RMSEz) on
  open, non-vegetated ground; this project's vendor accuracy report has not been reviewed. Errors are larger under dense
  vegetation and buildings, where the ground is interpolated.

## Limits
- Ground as it was in October and November 2023; grading since then is not reflected.
- Under buildings the ground is interpolated, so building sites are smoothed.
- Not for engineering design, grading, flood elevations or surveying.
- The edge of the coverage follows the 1 km lidar tiles, so it is a staircase.

{{coordinates}}

{{lidar}}

{{set}}

{{contact}}

# Terms of use

{{terms}}
