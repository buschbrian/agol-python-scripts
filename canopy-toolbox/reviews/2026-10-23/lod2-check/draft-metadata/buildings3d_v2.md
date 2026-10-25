---
key: buildings3d_v2
id: [set when the item is published]
title: Millcreek 3D buildings with roof forms (2023 lidar), planning estimate
summary: 21,561 Millcreek, Utah, buildings in 3D. Roof forms (gables, hips, dormers, flat roofs) from the 2023 lidar where it supports them, otherwise flat blocks. Unvalidated planning estimate; not surveyed or field-verified.
tags: Millcreek, Utah, Salt Lake County, lidar, 2023 lidar, 3DEP, planning estimate, buildings, 3D buildings, LOD2.2, roof forms, building height, roof area, scene layer
credits: City of Millcreek GIS. Lidar: 2023 Salt Lake Valley QL1 lidar (USGS 3DEP, project UT_2023SaltLakeCo_C24). Building footprints: Salt Lake County Assessor and Surveyor (downloaded October 19, 2026). Roof reconstruction: roofer, 3DBAG and TU Delft (https://github.com/3DBAG/roofer).
iso_topics: structure, elevation
resolution_m: 0.5
lineage: County building footprints extruded to the 2023 lidar roof. Roof forms by roofer 1.0.0 (CityGML-style LoD 2.2) from consensus roof points (a point is roof when at least two of three independent classifications agree) on each footprint; ArcGIS Pro Extract LOD2 Buildings (LOD2.0, then LOD1.2) where roofer's model failed a check against the lidar roof. Packaged as a scene layer package in WGS84 (WGS_1984_(ITRF08)_To_NAD_1983_2011); heights NAVD88 (Geoid18) metres, labelled EGM96.
---

# Description

{{warning}}

## What it shows
Every Salt Lake County building footprint in Millcreek, Utah, that has a lidar roof, as a 3D building: 21,561 of them. **For most
(20,730) the roof has its real shape**: gables, hips, dormers, stepped and flat roofs, taken from the 2023 lidar. For the rest the
roof is simpler (Esri's LOD2.0 roof forms for 647, flat LOD1.2 blocks at the median roof height for 184), because the lidar could
not support a roof form or the roof form failed a check. The **LEVEL** field says which model a building has.

## Fields
Each building carries its footprint's County attributes and lidar roof-height statistics (see the data dictionary), so a pop-up
can show its height. Buildings whose LEVEL is **roofer LoD2.2** also carry roof attributes; for the others they are empty.

[the table in fields.md goes here]

## Using it in a scene
Put the **Millcreek bare-earth terrain** elevation layer in the scene's Ground, above World Elevation. The buildings were built on that
terrain, so they stand on it exactly; on Esri's World Elevation alone they can float or sink by up to about a metre.

## How it was made
1. **Roof points.** A lidar point is roof when at least two of three independent classifications call it building.
2. **Roof forms.** For each footprint, roofer finds the roof planes in those points, splits the footprint into roof parts and extrudes them
   to a closed 3D model, with each footprint's ground from nearby ground points.
3. **Check and choice.** Each roofer model is compared with the lidar roof on the same 0.5 m cells. A building takes roofer's model when it
   passes (not above the lidar roof by more than 1 m, not short of it over more than 5% of its cells, not at ground level over 10% of its
   footprint, and not clearly worse than a flat block); otherwise it takes Esri's LOD2.0 roof if that passes, otherwise a flat block.
4. Packaged as a scene layer package in WGS84 and published.

## Accuracy and checks
- On the cells where the lidar saw roof, the buildings are within 0.5 m of the lidar roof on 96.7% of cells and within 1 m on 98.1%
  (flat blocks alone: 56.9% and 80.4%). The lidar is also what the roofs were built from, so this measures fidelity to the lidar, not an
  independent accuracy.
- [To confirm after a City review of a sample.] On aerial imagery, 97 randomly chosen buildings with roofer's model were compared: about
  two thirds matched the roof form; most of the rest had the right idea with wrong detail (often fragmented facets on complex roofs); a few
  could not be judged under trees. None was clearly wrong.
- 21,561 buildings; the FP_ID statistics of the hosted layer equal the source's.

## Limits
- **Planning estimates, not surveyed buildings.** Heights are roof-minus-ground from lidar, not code-defined building heights.
- **Complex roofs can come out fragmented**: many small facets where one or two planes are real. Chimneys and dormers are modelled when the
  lidar sees them and may be missing or merged where it does not.
- **Footprints are the County's.** Footprints that hold several buildings, or buildings built or removed since, are as the County drew them;
  a demolished building with a footprint still has a model of whatever the lidar saw there.
- **Under trees, glass roofs and dark roofs the lidar sees less**, and those buildings are the ones that fall back to simpler models.
- Roof attributes (slope, azimuth, areas) are geometry from the lidar roof. They are **not a solar production estimate**: no shading, panel
  layout or weather.

## Coordinates
Horizontal: WGS84, taken from NAD83(2011) with the transformation `WGS_1984_(ITRF08)_To_NAD_1983_2011`, as every other layer in the set.
Vertical: heights are NAVD88 (Geoid18) metres; the package's vertical label is EGM96 (see the scene-layers README).
