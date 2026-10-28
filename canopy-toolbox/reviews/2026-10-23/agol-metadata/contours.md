---
key: contours
id: 50573eeba93f405a869a1d78a08d68e8
title: Millcreek 2 m contours (2023 lidar), planning estimate
summary: Ground contours every 2 m (index lines every 10 m) for Millcreek, Utah, from the 0.5 m bare-earth terrain of the 2023 lidar. Unvalidated planning estimate; not surveyed or field-verified.
tags: Millcreek, Utah, Salt Lake County, lidar, 2023 lidar, 3DEP, planning estimate, contours, elevation, topography, terrain, vector tiles
credits: City of Millcreek GIS. Lidar: 2023 Salt Lake Valley QL1 lidar (USGS 3DEP, project UT_2023SaltLakeCo_C24).
iso_topics: elevation
resolution_m: 0.5
lineage: 2 m contours (10 m index) traced from the 0.5 m bare-earth terrain of the 2023 Salt Lake Valley QL1 lidar, interpolated from ground returns, and packaged as vector tiles (WGS_1984_(ITRF08)_To_NAD_1983_2011).
---

# Description

{{warning}}

## What it shows
Lines of equal ground elevation across Millcreek, Utah, drawn from the 0.5 m bare-earth terrain of the 2023 lidar.

- **Interval: 2 metres** (about 6.56 ft). **Index contours every 10 metres** (about 32.8 ft). The contours are in
  **metres above NAVD88**, not feet.
- 15,149 lines (3,260 of them index contours), 2,447 km in all, from 1,290 m to 2,080 m (about 4,232 ft to 6,824 ft).

## Legend and scales
| Lines | Shown from | Meaning |
|---|---|---|
| Index contours | 1:288,895 (zoom level 10) inward | Every 10 m of elevation (1,290, 1,300, 1,310 m ...) |
| 2 m contours | 1:18,056 (zoom level 14) inward | Every 2 m between the index lines |

Index lines are drawn heavier, the 2 m lines thinner. **Map Viewer's legend does not list vector tile layers**, so this table is the key to the lines. The layer draws down to about 1:2,257 (zoom level 17); ArcGIS web maps and apps stop drawing it at larger scales. This is a vector tile layer: it **draws only**. The tiles carry no attributes, so the lines have no elevation labels, no
pop-ups and no identify. To read an elevation, count from a labelled index line or use the Millcreek bare-earth terrain
layer. At small scales the tiling simplifies the lines to the pixel size.

## How it was made
Contours at a 2 m interval were traced from the 0.5 m bare-earth terrain (interpolated from the lidar's ground returns),
for the city only; every fifth line (each multiple of 10 m) is marked as an index contour. They were packaged as vector
tiles for levels 10 to 17.

## Accuracy and checks
- The hosted lines fall on 2 m multiples of the source terrain with no shift (the best-fitting shift on a 7 cm search grid is
  zero), and tiles fetched from the hosted layer are byte for byte the package's.
- Tile vertices sit a median 6 cm from the source lines (half a tile unit), against 0.9 m if the datum transformation
  had been left out.
- The terrain has not been checked against field survey. QL1 lidar is specified to 10 cm vertically on open ground;
  errors are larger under dense vegetation and buildings, where the ground is interpolated.

## Limits
- At 0.5 m the 2 m lines follow every curb, berm and driveway cut. They show the ground as it was in late 2023.
- Under buildings the ground is interpolated, so lines crossing a building are not observed ground.
- Not for engineering design, grading plans or flood elevations; those need a survey.

{{coordinates}}

{{lidar}}

{{set}}

{{contact}}

# Terms of use

{{terms}}
