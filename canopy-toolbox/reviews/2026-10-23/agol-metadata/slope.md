---
key: slope
id: 3b5b1a9110f14e93af68752be89e0df2
title: Millcreek slope classes 0.5 m (2023 lidar), planning estimate
summary: Ground slope in six classes (under 10% to 30% and over) for Millcreek, Utah, from the 0.5 m bare-earth terrain of the 2023 lidar. Unvalidated planning estimate; not surveyed or field-verified.
tags: Millcreek, Utah, Salt Lake County, lidar, 2023 lidar, 3DEP, planning estimate, slope, steep slopes, hillside, terrain, vector tiles
credits: City of Millcreek GIS. Lidar: 2023 Salt Lake Valley QL1 lidar (USGS 3DEP, project UT_2023SaltLakeCo_C24).
iso_topics: elevation, planningCadastre
resolution_m: 0.5
lineage: Percent slope from the 0.5 m bare-earth terrain of the 2023 Salt Lake Valley QL1 lidar (ArcGIS Pro Surface Parameters, 3 m neighbourhood), classified at 10, 15, 20, 25 and 30 percent, patches under 4 m2 merged into their largest neighbour, converted to polygons and packaged as vector tiles (WGS_1984_(ITRF08)_To_NAD_1983_2011).
---

# Description

{{warning}}

## What it shows
The steepness of the bare ground across Millcreek, Utah, in six classes of percent slope, mapped at 0.5 m from the 2023
lidar. It answers questions such as "where is the ground steeper than 30%?" for hillside planning, and shows far more
detail than slope layers made from 1 m to 10 m elevation models: street edges, embankments, retaining walls and
channels appear as well as the east-bench hillsides.

Percent slope is rise over run times 100: 10% is a 1 m rise in 10 m (about 5.7 degrees); 30% is about 16.7 degrees;
100% is 45 degrees.

## Legend
Each polygon belongs to one class. A break value belongs to the class above it (exactly 10.0% is "10% to 15%").

| Class | Percent slope | Area (ha) | Share of city | Polygons |
|---|---|---:|---:|---:|
| Under 10% | below 10 | 2,389.3 | 71.42% | 8,581 |
| 10% to 15% | 10 to under 15 | 209.5 | 6.26% | 35,783 |
| 15% to 20% | 15 to under 20 | 113.6 | 3.40% | 31,053 |
| 20% to 25% | 20 to under 25 | 72.4 | 2.16% | 25,764 |
| 25% to 30% | 25 to under 30 | 51.4 | 1.54% | 20,408 |
| 30% and over | 30 and above | 509.1 | 15.22% | 7,763 |

Share of the city at or above each threshold: 10%: 28.58%; 15%: 22.32%; 20%: 18.92%; 25%: 16.75%; 30%: 15.22%.

The legend labels come from the layer's style (one style layer per class). This is a vector tile layer: it **draws
only**. The tiles carry no attributes, so there are no pop-ups, no identify and no filtering by class. Classes can be
switched on and off, or recoloured, in the style.

## How it was made
1. Slope in percent from the 0.5 m bare-earth terrain with ArcGIS Pro's Surface Parameters over a 3 m neighbourhood,
   computed on the whole lidar mosaic and then clipped to the city, so cells at the city limit use their full
   neighbourhood.
2. Each cell put into one of the six classes.
3. **Cleanup (4 m2 minimum mapping unit).** Classified as it is, the 0.5 m slope makes 924,458 patches, most under 4 m2,
   because on a graded hillside slope wanders back and forth across a class break. Every patch smaller than 16 cells
   (4 m2) was merged into its largest neighbouring patch; nothing else changed. Polygon edges follow the 0.5 m cells; there
   is no smoothing.
4. Converted to 129,352 polygons and packaged as vector tiles (levels 0 to 17; clients draw deeper by overzooming).

## Accuracy and checks
- The polygons' areas equal the cleaned class raster's cells exactly for every class, and together they cover the whole
  city (33,453,372 m2).
- The cleanup moves the area at or above each threshold by at most 0.54 points of city area, but it shrinks the narrow
  middle classes (25% to 30% loses 15% of its area to its neighbours) and removes real steep features smaller than 4 m2,
  such as curb faces and short walls. For exact class areas, use the uncleaned version, available from City of Millcreek
  GIS.
- Tiles fetched from the hosted layer are byte for byte the package's; the tile vertices sit a median 6 cm from the source
  polygons (half a tile unit), against 0.7 m if the datum transformation had been left out.
- The slope itself has not been checked against field measurements. Its accuracy follows the terrain's: QL1 lidar is
  specified to 10 cm vertically on open ground, and errors are larger under dense vegetation and buildings, where the
  ground is interpolated.

## Limits
- Slope over 3 m measures the local ground surface, including man-made edges. Expect much more "30% and over" along
  streets, driveways and embankments than on slope maps from coarser elevation models.
- Under buildings the terrain is interpolated, so slope there is not meaningful.
- Not a geotechnical or hazard assessment. Slope alone says nothing about soil, stability or ordinance status.

{{coordinates}}

{{lidar}}

{{set}}

{{contact}}

# Terms of use

{{terms}}
