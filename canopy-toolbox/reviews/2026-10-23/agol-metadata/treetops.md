---
key: treetops
id: 924b993cb23046cb87641253bcf786de
title: Millcreek treetops (2023 lidar), planning estimate
summary: 527,140 treetops at least 2 m tall detected in the 2023 lidar for Millcreek, Utah, by height class. Detections, not a tree census. Unvalidated planning estimate; not surveyed or field-verified.
tags: Millcreek, Utah, Salt Lake County, lidar, 2023 lidar, 3DEP, planning estimate, trees, treetops, tree height, urban forest, tree canopy, vector tiles
credits: City of Millcreek GIS. Lidar: 2023 Salt Lake Valley QL1 lidar (USGS 3DEP, project UT_2023SaltLakeCo_C24).
---

# Description

{{warning}}

## What it shows
The tops of trees across Millcreek, Utah, as found in the 2023 lidar: 527,140 local high points of the canopy at least
2 m above the ground, each drawn as a dot coloured by its height. They give a citywide picture of where trees are and
how tall they are. They are **detections, not a count of trees**: a broad tree can have several tops and a tree under a
taller one can be missed.

## Legend
Shown from 1:18,056 (zoom level 14) inward. Height is the canopy height at the treetop, in metres above the ground. Each
class includes its upper value (a 5.0 m treetop is in "2 to 5 m").

| Class | Height | Feet (about) | Treetops | Share |
|---|---|---|---:|---:|
| 2 to 5 m | 2 to 5 m | 7 to 16 ft | 217,914 | 41.3% |
| 5 to 10 m | over 5 to 10 m | 16 to 33 ft | 190,326 | 36.1% |
| 10 to 15 m | over 10 to 15 m | 33 to 49 ft | 83,369 | 15.8% |
| 15 to 20 m | over 15 to 20 m | 49 to 66 ft | 29,563 | 5.6% |
| 20 m and over | over 20 m (tallest 42.9 m) | over 66 ft | 5,968 | 1.1% |

The legend labels come from the layer's style (one style layer per class). This is a vector tile layer: it **draws
only**. The tiles carry no attributes, so there are no pop-ups, no identify and no filtering; a treetop's exact height,
ID and parcel ownership are kept by City of Millcreek GIS.

## How it was made
1. **Canopy height model.** Every lidar point was classified: this project's own classification refined with the IGN
   FRACTAL model, with buildings decided by a 2-of-3 vote that adds Esri's building model. The canopy height model is the
   vegetation surface minus the bare-earth terrain at 0.5 m, with building roofs excluded.
2. **Treetops.** Local maxima of the canopy height model (smoothed by one cell), searched in a window that grows with
   height: 1 m radius for canopy 2 to 6 m, 1.5 m for 6 to 12 m, 2 m for 12 to 20 m and 2.5 m above 20 m. Peaks under 2 m
   and outside the city limits were dropped.

## Accuracy and checks
- On one hand-labelled 1 km tile (a deliberately hard sample, not a citywide accuracy), 95.9% of tree parts were
  classified as vegetation and 10.7% of non-vegetation parts were wrongly called vegetation.
- **32,986 treetops (6.3%) are flagged SUSPECT** by independent geometric checks (for example a roof edge, a flat top, a
  wire, a pole or a wall nearby). The flags are review hints, not decisions; they have not been reviewed and the SUSPECT
  treetops are still drawn here.
- No treetop has been checked against a field inventory, so the detection rate (trees found) and the false-detection rate
  are not known.
- Every package tile was decoded and its points counted: 527,127 of the 527,140 treetops are accounted for; the last 13
  are most likely on edges between tiles at different levels. Tiles fetched from the hosted layer are byte for byte the
  package's, and points sit a median 6 cm from their source positions (1.6 m if the datum transformation had been left out).

## Limits
- Lidar sees the top of the canopy. Small trees under larger ones, and trees under 2 m, are under-counted; broad or
  multi-stemmed trees can show several tops.
- Some detections are not trees: structures, poles, wires and roof edges can make peaks (see SUSPECT above).
- Heights are canopy height above interpolated ground at 0.5 m, not a measured tree height.
- The lidar was flown in October and November 2023. Trees removed or planted since then are not reflected.

{{coordinates}}

{{lidar}}

{{set}}

{{contact}}

# Terms of use

{{terms}}
