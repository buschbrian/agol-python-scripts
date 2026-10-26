---
key: urban_footprints
id: e74c2216aca54d7f8be2432768b64520
title: Millcreek building footprints for ArcGIS Urban, UTM 12N (2023 lidar), planning estimate
summary: Footprints of the 21,561 Millcreek, Utah, 3D buildings with lidar roof height, model level and an estimated floor count, in UTM 12N for a local ArcGIS Urban model. Unvalidated planning estimate; not surveyed or field-verified.
tags: Millcreek, Utah, Salt Lake County, lidar, 2023 lidar, 3DEP, planning estimate, buildings, building footprints, building height, floors, ArcGIS Urban, UTM
credits: City of Millcreek GIS. Lidar: 2023 Salt Lake Valley QL1 lidar (USGS 3DEP, project UT_2023SaltLakeCo_C24). Building footprints: Salt Lake County Assessor and Surveyor (downloaded October 19, 2026).
iso_topics: structure, planningCadastre
resolution_m: 0.5
lineage: Multipatch Footprint (ArcGIS Pro 3D Analyst) of each building of the October 25, 2026 three-way hybrid, grouped by FP_ID, with HEIGHT_P95_M and LEVEL from the building and FLOORS (HEIGHT_P95_M divided by 3.5 m, rounded, at least 1). Stored in NAD83(2011) UTM 12N (EPSG 6341); published October 26, 2026.
---

# Description

{{warning}}

## What it shows
One polygon for each of the 21,561 buildings in the scene layer **Millcreek 3D buildings for ArcGIS Urban, UTM 12N**, with the same
**FP_ID**, so the two can be joined or used together as the existing buildings of a local ArcGIS Urban model. Each footprint is the
outline of its 3D model seen from above. It carries the roof height, the model level and an **estimated floor count, FLOORS**, for
Urban's **Convert existing buildings** in attribute-driven mode. There are no owner or address fields.

## Floors
FLOORS is the 95th percentile lidar roof height above ground (HEIGHT_P95_M) divided by 3.5 m, rounded to the nearest whole number
(halves up), and never less than 1; it would be empty for a building with no height, and there are none. It is **a planning
estimate from roof height, not a count of storeys**. 11,894 buildings get 1, 8,271 get 2, 1,294 get 3, 101 get 4 to 9 and one
gets 12; the sum is 32,836.

## Data dictionary

{{fields:0}}

## How it was made
1. The 21,561 buildings of the October 25, 2026 three-way hybrid (roofer LoD 2.2 roofs, Esri LOD2.0 and LOD1.2 fallbacks).
2. ArcGIS Pro's Multipatch Footprint, grouped by FP_ID: one polygon per building, none empty.
3. HEIGHT_P95_M and LEVEL copied from the building; FLOORS computed; stored in UTM 12N and published on October 26, 2026.

## Accuracy and checks
- The hosted layer holds 21,561 footprints. FP_ID count and sum (21,561 and 237,493,394) equal the scene layer's and the source's;
  FP_IDs are unique. LEVEL counts are 20,730 roofer LoD2.2, 647 Esri LOD2.0 and 184 Esri LOD1.2. No FLOORS value is empty.
- Shape__Area totals 4,710,583 m2 on the hosted layer, within 0.001 m2 of the area computed in UTM before upload. In UTM,
  Shape__Area and Shape__Length are grid measures: the UTM scale factor is about 0.9997 at Millcreek, so areas read about 0.07%
  under the ground area and lengths about 0.03% under.
- The outlines follow the 3D models, which follow the County footprints; they are not redrawn from the lidar.

## Limits
- **Planning estimates.** Heights are roof minus ground from lidar, not code-defined building heights; FLOORS is an estimate.
- **Footprints are the County's**, as of October 19, 2026; buildings built or removed since are not reflected.
- The field LEVEL is named **LEVEL_** here: ArcGIS Online renames LEVEL, a reserved word, when it publishes. The scene layer keeps
  LEVEL.

{{coordinates_utm}}

{{lidar}}

{{set_urban}}

{{contact}}

# Terms of use

{{terms}}

{{terms_county}}

# Fields layer=0 building_footprints

| Field | Alias | Type | Value type | Units | Description |
|---|---|---|---|---|---|
| OBJECTID | OBJECTID | OID | uniqueIdentifier | | Row number assigned by ArcGIS Online; use FP_ID as the key. |
| FP_ID | Footprint ID | Integer | uniqueIdentifier | | Building identifier, unique; the same FP_ID as the 3D buildings for ArcGIS Urban and the public 3D buildings. |
| HEIGHT_P95_M | Roof height, 95th percentile (m) | Double | measurement | metres | 95th percentile of lidar roof minus terrain over the footprint (0.80 to 42.22 m); not a code-defined building height. |
| LEVEL_ | Model used | String | typeOrCategory | | Model of the 3D building: roofer LoD2.2, Esri LOD2.0 or Esri LOD1.2. Named LEVEL in the scene layer. |
| FLOORS | Estimated floors | Integer | countOrAmount | floors | HEIGHT_P95_M / 3.5 m, rounded (halves up), at least 1 (1 to 12). A planning estimate for ArcGIS Urban, not a count of storeys. |
| Shape__Area | Shape__Area | Double | measurement | square metres | Footprint area computed by ArcGIS Online in UTM 12N (grid area, about 0.07% under the ground area at Millcreek). |
| Shape__Length | Shape__Length | Double | measurement | metres | Footprint perimeter computed by ArcGIS Online in UTM 12N. |
