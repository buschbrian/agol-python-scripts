---
key: hillshade
id: cab8824e44384d479e1f302cdf34daf9
title: Millcreek hillshade 0.5 m (2023 lidar), planning estimate
summary: Shaded relief of the bare ground in Millcreek, Utah, at 0.5 m from the 2023 lidar, for use as a background under other layers. Display only. Unvalidated planning estimate; not surveyed or field-verified.
tags: Millcreek, Utah, Salt Lake County, lidar, 2023 lidar, 3DEP, planning estimate, hillshade, shaded relief, terrain, basemap, tile layer
credits: City of Millcreek GIS. Lidar: 2023 Salt Lake Valley QL1 lidar (USGS 3DEP, project UT_2023SaltLakeCo_C24).
iso_topics: elevation, imageryBaseMapsEarthCover
resolution_m: 0.5
lineage: Hillshade (azimuth 315, altitude 45, no shadows) of the 0.5 m bare-earth terrain of the 2023 Salt Lake Valley QL1 lidar, clipped to the city and cached as PNG32 tiles, levels 0 to 18, on the ArcGIS Online scheme (WGS_1984_(ITRF08)_To_NAD_1983_2011).
---

# Description

{{warning}}

## What it shows
The shape of the bare ground across Millcreek, Utah, lit as if by a sun in the north-west, with buildings and trees
removed. It is a detailed background for other layers: streets, channels, terraces, embankments and the east-bench
foothills stand out at 0.5 m. It is transparent outside the city limits, so it sits over any basemap.

## Legend
Grey levels from dark (ground facing away from the light) to light (ground facing it). The grey values are **for display
only**: they are not elevations or slopes and should not be measured or classified. For elevation use the Millcreek
bare-earth terrain layer; for slope use the Millcreek slope classes layer.

Useful from about 1:2,311,162 (zoom level 8) inward; the finest level is 18 (about 0.45 m per pixel on the ground). It
works well under other layers with a multiply blend or partial transparency.

## How it was made
1. The 0.5 m bare-earth terrain, interpolated from the lidar's ground returns.
2. Hillshade with the sun at 315 degrees (north-west) and 45 degrees above the horizon, without cast shadows, computed on
   the whole lidar mosaic and clipped to the city.
3. Packaged as 256-pixel PNG tiles with transparency, zoom levels 0 to 18, on the ArcGIS Online tiling scheme. The
   brightest values (253 and 254, on 0.18% of cells) were lowered to 252 because the tiling tool treats 253 as
   transparent.

## Accuracy and checks
- At level 18, 2,752 tiles hold the city and all are present; no transparent pixel appears inside the city.
- Sampled tile pixels match the source hillshade to a median of 1 grey level (95th percentile 3), when read in the right
  position; read 1.2 m off (no datum transformation) they would differ by a median of 3 and up to 107 levels.
- Tiles fetched from the hosted layer are byte for byte the package's.
- The terrain under it has not been checked against field survey (QL1 lidar is specified to 10 cm vertically on open
  ground).

## Limits
- Under buildings the ground is interpolated, so building sites look smoother than they are.
- At zoom levels 10 to 12 a thin sliver at the city edge is not drawn; at levels 0 to 4 the city is under two pixels
  across.
- It shows the ground as it was in October and November 2023.

{{coordinates}}

{{lidar}}

{{set}}

{{contact}}

# Terms of use

{{terms}}
