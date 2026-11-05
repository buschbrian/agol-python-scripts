---
key: crowns
id: d9388dc83f894edbb63e0510a8c62fa8
title: Millcreek tree crowns (2023 lidar), planning estimate
summary: 400,063 estimated tree crown areas around lidar treetops for Millcreek, Utah, by treetop height class. Estimated canopy regions, not surveyed crowns. Unvalidated planning estimate; not surveyed or field-verified.
tags: Millcreek, Utah, Salt Lake County, lidar, 2023 lidar, 3DEP, planning estimate, trees, tree crowns, crown area, urban forest, tree canopy, vector tiles
credits: City of Millcreek GIS. Lidar: 2023 Salt Lake Valley QL1 lidar (USGS 3DEP, project UT_2023SaltLakeCo_C24).
iso_topics: biota, environment
resolution_m: 0.5
lineage: Canopy at least 2 m tall in the 0.5 m canopy height model from the 2023 Salt Lake Valley QL1 lidar, divided among the detected treetops by a priority flood in 950 m tiles with a 40 m overlap, crowns under 3 m2 dropped, and packaged as vector tiles by treetop height class (WGS_1984_(ITRF08)_To_NAD_1983_2011).
---

# Description

{{warning}}

## What it shows
The canopy of Millcreek, Utah, divided into estimated crowns: for each lidar treetop, the patch of canopy at least 2 m
tall that belongs to it. 400,063 crowns of at least 3 m2 cover 826.4 ha (median crown 12.25 m2, about 4 m across). They
show the shape and spread of the urban forest and which canopy belongs to which treetop. They are **estimated canopy
regions, not surveyed crowns**: a broad tree can be split into several crowns and a clump of small trees can form one.

## Legend
Shown from 1:18,056 (zoom level 14) inward. Crowns are coloured by the height of their treetop, in the same classes as
the Millcreek treetops layer. Each class includes its upper value.

| Class | Treetop height | Feet (about) | Crowns | Crown area (ha) |
|---|---|---|---:|---:|
| 2 to 5 m | 2 to 5 m | 7 to 16 ft | 117,799 | 88.7 |
| 5 to 10 m | over 5 to 10 m | 16 to 33 ft | 164,451 | 279.6 |
| 10 to 15 m | over 10 to 15 m | 33 to 49 ft | 81,276 | 260.4 |
| 15 to 20 m | over 15 to 20 m | 49 to 66 ft | 30,404 | 154.4 |
| 20 m and over | over 20 m (tallest 42.9 m) | over 66 ft | 6,133 | 43.3 |

Fills run from pale yellow-green (2 to 5 m) to dark green (20 m and over) (ColorBrewer YlGn), the same colours as the treetops. **Map Viewer's legend does not list vector tile layers**, so this table is the key to the colours. The layer draws down to about 1:2,257 (zoom level 17); ArcGIS web maps and apps stop drawing it at larger scales. The class names come from the layer's style (one style layer per class). This is a vector tile layer: it **draws
only**. The tiles carry no attributes, so there are no pop-ups, no identify and no filtering; each crown's area,
diameter and height are kept by City of Millcreek GIS.

## How it was made
1. **Seeds.** Every treetop of the Millcreek treetops layer (527,140), plus peaks just outside the city, which only stop
   city crowns from spreading past the boundary.
2. **Growing crowns.** A priority flood over the canopy at least 2 m tall (smoothed by one cell): each canopy cell goes to
   the treetop it reaches along the path that stays highest, so crowns divide along the low saddles between trees.
3. **Tiles.** The city was processed in 63 tiles of 950 m, each with a 40 m overlap; each cell was decided once. Crowns
   smaller than 3 m2 were dropped: 127,077 treetops have no crown in this layer for that reason.

## Accuracy and checks
- **Tiling.** On three test tiles, including the densest canopy in the city, crowns grown in tiles with a 20 m overlap
  were identical, cell for cell, to crowns grown in one piece; the city run used twice that overlap, and rerunning six
  tiles with an 80 m overlap changed no cell.
- Tiles fetched from the hosted layer are byte for byte the package's; crown vertices sit a median 6 cm from the source
  polygons (0.7 m if the datum transformation had been left out).
- No crown has been compared with a field-measured crown or a tree inventory.

## Limits
- Crowns depend on the treetops: a missed treetop's canopy goes to a neighbour, and a false treetop (see the treetops
  layer's SUSPECT flags, 6.3%) takes canopy from one.
- Canopy that no treetop reached (8.6 ha, mostly beyond the city) is not drawn. Crowns near the city limits can extend up
  to 20 m past them.
- Crown area counts canopy at least 2 m tall seen from above; overlapping crowns of different trees are divided, not
  shared.

{{coordinates}}

{{lidar}}

{{set}}

{{contact}}

# Terms of use

{{terms}}
