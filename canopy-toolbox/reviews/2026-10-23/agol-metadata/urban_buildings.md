---
key: urban_buildings
id: b8e8ddaceac54876bd4c0cf3f31d92fd
title: Millcreek 3D buildings for ArcGIS Urban, UTM 12N (2023 lidar), planning estimate
summary: 21,561 Millcreek, Utah, buildings in 3D, with roof forms from the 2023 lidar and an estimated floor count, in UTM 12N for a local ArcGIS Urban model. Unvalidated planning estimate; not surveyed or field-verified.
tags: Millcreek, Utah, Salt Lake County, lidar, 2023 lidar, 3DEP, planning estimate, buildings, 3D buildings, LOD2.2, roof forms, building height, floors, scene layer, ArcGIS Urban, UTM
credits: City of Millcreek GIS. Lidar: 2023 Salt Lake Valley QL1 lidar (USGS 3DEP, project UT_2023SaltLakeCo_C24). Building footprints: Salt Lake County Assessor and Surveyor (downloaded October 19, 2026). Roof reconstruction: roofer, 3DBAG and TU Delft (https://github.com/3DBAG/roofer).
iso_topics: structure, elevation
resolution_m: 0.5
lineage: The October 25, 2026 three-way hybrid (roofer LoD 2.2 where it passed a check against the lidar roof, Esri LOD2.0 or LOD1.2 otherwise), with FLOORS added (95th percentile roof height divided by 3.5 m, rounded, at least 1). Packaged as a scene layer package in NAD83(2011) UTM 12N (EPSG 6341) with NAVD88 height (EPSG 5703) and no datum transformation; published October 26, 2026.
---

# Description

{{warning}}

## What it shows
The same 21,561 Millcreek, Utah, buildings as the public **Millcreek 3D buildings with roof forms** layer, in **NAD83(2011) UTM
zone 12N** instead of WGS84, for the existing buildings of a **local ArcGIS Urban model** in that coordinate system. For 20,730 the roof
has a modelled shape from the 2023 lidar (roofer LoD 2.2); 647 use Esri's LOD2.0 roof forms and 184 are flat LOD1.2 blocks. The
**LEVEL** field says which.

## Floors for ArcGIS Urban
**FLOORS** is an estimated floor count for Urban's **Convert existing buildings** (attribute-driven mode): the 95th percentile lidar
roof height above ground (HEIGHT_P95_M) divided by 3.5 m, rounded to the nearest whole number (halves up), and never less than 1.
No building lacks a height, so none is empty. It is **a planning estimate from roof height, not a count of storeys**: a tall
single-storey building, a pitched roof or a split-level house can be given the wrong number.

| FLOORS | Buildings |
|---|---|
| 1 | 11,894 |
| 2 | 8,271 |
| 3 | 1,294 |
| 4 | 52 |
| 5 to 9 | 49 |
| 12 | 1 |

The footprints, with the same FP_ID and FLOORS, are the companion feature layer **Millcreek building footprints for ArcGIS Urban,
UTM 12N**.

## Fields
Every building carries its County footprint attributes, the lidar roof-height statistics and the model it uses. Unlike the public
layer, this copy does not carry the roof-plane attributes (areas, slopes, azimuth) added on October 24; use the public layer for those.
Heights and elevations are metres; Z50 fields are elevations, other height fields are above local ground.

{{fields:scene}}

## How it was made
1. The three-way hybrid buildings of October 25, 2026 (see the public layer for how roofer and the Esri fallbacks were chosen).
2. Field types a scene layer package cannot carry were to be dropped first (big integer, date only, time only, timestamp offset); the
   source has none. FLOORS was added.
3. Packaged as a scene layer package in UTM 12N (EPSG 6341) with NAVD88 height (EPSG 5703), no transformation, and published on
   October 26, 2026. A 20-building test package was built and checked first.

## Accuracy and checks
- The package and the hosted layer hold 21,561 buildings; their FP_ID count and sum (21,561 and 237,493,394) equal the source's, and
  the model counts per LEVEL match. FLOORS on the hosted layer sums to 32,836, from 1 to 12.
- ArcGIS Pro's package validation reports one warning: "vertex normals may be required by Esri products". Pro writes no vertex
  normals for a package in a projected coordinate system (the same source packaged in WGS84 has them and no warning); viewers then
  compute shading themselves.
- On the cells where the lidar saw roof, the buildings are within 0.5 m of the lidar roof on 96.7% of cells and within 1 m on 98.1%.
  The lidar is also what the roofs were built from, so this is fidelity to the lidar, not independent accuracy.
- Seen drawing in the local ArcGIS Urban model on October 27, 2026, on the UTM basemap and terrain (seen from above only).

## Limits
- **Planning estimates, not surveyed buildings.** Heights are roof minus ground from lidar, not code-defined building heights.
- **Footprints are the County's**, as of October 19, 2026; buildings built or removed since are not reflected.
- Complex roofs can come out fragmented; under trees, glass and dark roofs the lidar sees less.

{{coordinates_utm}}

{{lidar}}

{{set_urban}}

{{contact}}

# Terms of use

{{terms}}

{{terms_county}}

# Fields document

| Field | Alias | Type | Value type | Units | Description |
|---|---|---|---|---|---|
| OBJECTID | OBJECTID | OID | uniqueIdentifier | | Package row identifier; use FP_ID to identify a building. |
| Name | Name | String | nameOrTitle | | Model object name. |
| FP_ID | FP_ID | Integer | uniqueIdentifier | | Footprint identifier, unique per building; the key to the footprint layer and the public 3D buildings. |
| PARTS | PARTS | Integer | countOrAmount | | Number of converted model parts. |
| RF_ROOF_TYPE | RF_ROOF_TYPE | String | typeOrCategory | | Roof type inferred by roofer. |
| RF_ROOF_PLANES | RF_ROOF_PLANES | Integer | countOrAmount | | Roof plane count reported by roofer. |
| RF_RIDGELINES | RF_RIDGELINES | Integer | countOrAmount | | Ridgeline count reported by roofer. |
| RF_RMSE_LOD22 | RF_RMSE_LOD22 | Double | measurement | metres | Roofer model fit RMSE; not independent accuracy. |
| RF_H_GROUND | RF_H_GROUND | Double | measurement | metres | Roofer ground elevation, NAVD88. |
| RF_H_ROOF_MAX | RF_H_ROOF_MAX | Double | measurement | metres | Maximum roof elevation reported by roofer, NAVD88. |
| RF_PT_DENSITY | RF_PT_DENSITY | Double | measurement | points per m2 | Point density reported by roofer. |
| RF_EXTRUSION | RF_EXTRUSION | String | typeOrCategory | | Roofer extrusion status. |
| SOURCE_ID | SOURCE_ID | String | uniqueIdentifier | | County source footprint identifier, as text. |
| PARCEL_ID | PARCEL_ID | String | uniqueIdentifier | | County parcel identifier carried with the footprint. |
| CITY | CITY | String | locationOrPlaceName | | County city attribute. |
| FOOTPRINT_M2 | FOOTPRINT_M2 | Double | measurement | square metres | County footprint area. |
| ROOF_COV_PCT | ROOF_COV_PCT | Double | percentageOrRatio | percent | Share of footprint cells with classified lidar roof support. |
| ROOF_Z50_M | ROOF_Z50_M | Double | measurement | metres | Median classified lidar roof elevation, NAVD88. |
| GROUND_Z50_M | GROUND_Z50_M | Double | measurement | metres | Median ground elevation under the footprint, NAVD88. |
| HEIGHT_P50_M | HEIGHT_P50_M | Double | measurement | metres | Median lidar roof height above ground; not code-defined height. |
| HEIGHT_P95_M | HEIGHT_P95_M | Double | measurement | metres | 95th percentile lidar roof height above ground (0.80 to 42.22); FLOORS is computed from it. |
| HEIGHT_STATUS | HEIGHT_STATUS | String | description | | Processing and support flags, including UNVALIDATED. |
| LEVEL | LEVEL | String | typeOrCategory | | Model used: roofer LoD2.2, Esri LOD2.0 or Esri LOD1.2. |
| CHECK_VERDICT | CHECK_VERDICT | String | typeOrCategory | | Check result recorded when the hybrid was assembled. |
| ROOFER_VERDICT | ROOFER_VERDICT | String | typeOrCategory | | Roofer comparison verdict against the source lidar. |
| ESRI_VERDICT | ESRI_VERDICT | String | typeOrCategory | | Esri LOD2.0 comparison verdict against the source lidar. |
| FALLBACK_REASON | FALLBACK_REASON | String | description | | Reason the model falls back from roofer to Esri. |
| FLOORS | Estimated floors | Integer | countOrAmount | floors | HEIGHT_P95_M / 3.5 m, rounded (halves up), at least 1. A planning estimate for ArcGIS Urban, not a count of storeys. |
