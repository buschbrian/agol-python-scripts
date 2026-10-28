---
key: buildings3d_v2
id: ce3617ac9b884bbcbee7c47a3e166999
title: Millcreek 3D buildings with roof forms (2023 lidar), planning estimate
summary: 21,561 Millcreek, Utah, buildings in 3D. Roof forms (gables, hips, dormers, flat roofs) from the 2023 lidar where supported, with simpler Esri roofs or blocks elsewhere. Unvalidated planning estimate; not surveyed or field-verified.
tags: Millcreek, Utah, Salt Lake County, lidar, 2023 lidar, 3DEP, planning estimate, buildings, 3D buildings, LOD2.2, roof forms, building height, roof area, scene layer
credits: City of Millcreek GIS. Lidar: 2023 Salt Lake Valley QL1 lidar (USGS 3DEP, project UT_2023SaltLakeCo_C24). Building footprints: Salt Lake County Assessor and Surveyor (downloaded October 19, 2026). Roof reconstruction: roofer, 3DBAG and TU Delft (https://github.com/3DBAG/roofer).
iso_topics: structure, elevation
resolution_m: 0.5
lineage: County building footprints extruded to the 2023 lidar roof. Roof forms by roofer 1.0.0 (CityGML-style LoD 2.2) from consensus roof points (a point is roof when at least two of three classification methods agree) on each footprint; ArcGIS Pro Extract LOD2 Buildings (LOD2.0, then LOD1.2) where roofer's model failed a check against the lidar roof. Packaged as a scene layer package in WGS84 (WGS_1984_(ITRF08)_To_NAD_1983_2011); heights NAVD88 (Geoid18) metres, labelled EGM96.
---

# Description

{{warning}}

## What it shows
Every Salt Lake County building footprint in Millcreek, Utah, that has a lidar roof, as a 3D building: 21,561 of them. **For most
(20,730) the roof has a modelled shape**: gables, hips, dormers, stepped and flat roofs, taken from the 2023 lidar. For the rest the
roof is simpler (Esri's LOD2.0 roof forms for 647, flat LOD1.2 blocks at the median roof height for 184), because the lidar could
not support a roof form or the roof form failed a check. The **LEVEL** field says which model a building has.

## Fields
The scene and building app display heights in **international feet** and roof/footprint areas in **square feet**.
The original stored fields and geometry retain their documented metric units. One foot is exactly 0.3048 meter.
A [companion CSV in feet and square feet](https://stmillcreeklidar.blob.core.windows.net/cogs/millcreek-lidar/buildings/20261025/buildings_hybrid_v2_feet.csv)
contains all 21,561 building records; join it to this layer using **FP_ID**. Blank measurements mean unavailable,
not zero. Z50 fields are elevations; other height fields are above local ground. Roof angles remain in degrees.

Each building carries its footprint's County attributes and lidar roof-height statistics (see the data dictionary), so a pop-up
can show its height. Buildings whose LEVEL is **roofer LoD2.2** also carry roof attributes; for the others they are empty.

| Field | Stored type | Meaning |
|---|---|---|
| OBJECTID | OID | Package row identifier; use FP_ID to identify the source footprint. |
| Name | String | Model object name. |
| FP_ID | Integer | Footprint identifier used by the massing and roof comparison runs. |
| PARTS | Integer | Number of converted model parts. |
| RF_ROOF_TYPE | String | Roof type inferred by roofer. |
| RF_ROOF_PLANES | Integer | Roof plane count reported by roofer. |
| RF_RIDGELINES | Integer | Ridgeline count reported by roofer. |
| RF_RMSE_LOD22 | Double | Roofer model fit RMSE (metres); not independent accuracy. |
| RF_H_GROUND | Double | Roofer ground elevation (metres). |
| RF_H_ROOF_MAX | Double | Maximum roof elevation reported by roofer (metres). |
| RF_PT_DENSITY | Double | Point density reported by roofer (points per square metre). |
| RF_EXTRUSION | String | Roofer extrusion status. |
| SOURCE_ID | String | County source footprint identifier, as text. |
| PARCEL_ID | String | County parcel identifier carried with the footprint. |
| CITY | String | County city attribute. |
| FOOTPRINT_M2 | Double | County footprint area (square metres). |
| ROOF_COV_PCT | Double | Share of footprint cells with classified lidar roof support (percent). |
| ROOF_Z50_M | Double | Median classified lidar roof elevation (metres). |
| GROUND_Z50_M | Double | Median ground elevation under the footprint (metres). |
| HEIGHT_P50_M | Double | Median lidar roof height above ground (metres); not code-defined height. |
| HEIGHT_P95_M | Double | 95th percentile lidar roof height above ground (metres). |
| HEIGHT_STATUS | String | Processing and support flags, including UNVALIDATED. |
| LEVEL | String | Model used: roofer LoD2.2, Esri LOD2.0 or Esri LOD1.2. |
| CHECK_VERDICT | String | Check result recorded when the hybrid was assembled. |
| ROOFER_VERDICT | String | Roofer comparison verdict against the source lidar. |
| ESRI_VERDICT | String | Esri LOD2.0 comparison verdict against the source lidar. |
| FALLBACK_REASON | String | Reason the model falls back from roofer to Esri. |
| ROOF_PLANES | Integer | Roof planes of 1 m2 or more in plan, from the lidar roof (roofer). Null for Esri fallback buildings. |
| ROOF_PLAN_M2 | Double | Area of those planes seen from above. Null for Esri fallback buildings. |
| ROOF_AREA_M2 | Double | True (sloped) area of those planes. Null for Esri fallback buildings. |
| ROOF_SLOPE_MEAN | Double | Slope from horizontal, weighted by plane area. Null for Esri fallback buildings. |
| ROOF_SLOPE_MAIN | Double | Slope of the largest plane. Null for Esri fallback buildings. |
| ROOF_AZIMUTH_MAIN | Double | Compass bearing of the largest plane's downslope direction (0 north, clockwise); empty if flat. Null for Esri fallback buildings. |
| RIDGE_HT_M | Double | Highest roof point minus the building's ground elevation. Null for Esri fallback buildings. |
| EAVE_HT_M | Double | Lowest roof point minus the building's ground elevation. Null for Esri fallback buildings. |
| BLDG_HT_M | Double | Same as the ridge height: highest roof point above the building's ground. Null for Esri fallback buildings. |
| FLAT_AREA_M2 | Double | Surface area of planes under 5 degrees. Null for Esri fallback buildings. |
| SOUTH_AREA_M2 | Double | Surface area of planes of 5 to 70 degrees facing 135 to 225 degrees. Null for Esri fallback buildings. |
| EAST_AREA_M2 | Double | Same, facing 45 to 135 degrees. Null for Esri fallback buildings. |
| WEST_AREA_M2 | Double | Same, facing 225 to 315 degrees. Null for Esri fallback buildings. |
| NORTH_AREA_M2 | Double | Same, facing 315 to 45 degrees. Null for Esri fallback buildings. |
| RF_VOLUME_M3 | Double | Volume of roofer's LoD 2.2 solid. Null for Esri fallback buildings. |
| TINY_FACES | Integer | Roof faces under 0.5 m2 in plan (quality screening). Null for Esri fallback buildings. |
| SLIVER_FACES | Integer | Roof faces narrower than about 0.4 m (quality screening). Null for Esri fallback buildings. |
| STEEP_FACES | Integer | Roof faces steeper than 75 degrees (quality screening). Null for Esri fallback buildings. |

## Using it in a scene
Put the **Millcreek bare-earth terrain** elevation layer in the scene's Ground, above World Elevation. The buildings were built on that
terrain. Ground estimates and vertical datum labels can still produce offsets; inspect placement before relying on it.

## How it was made
1. **Roof points.** A lidar point is roof when at least two of three classification methods call it building.
2. **Roof forms.** For each footprint, roofer finds the roof planes in those points, splits the footprint into roof parts and extrudes them
   to a closed 3D model, with each footprint's ground from nearby ground points.
3. **Check and choice.** Each roofer model is compared with the lidar roof on the same 0.5 m cells. A building takes roofer's model when it
   passes (not above the lidar roof by more than 1 m, not short of it over more than 5% of its cells, not at ground level over 10% of its
   footprint, and not clearly worse than a flat block); otherwise it takes Esri's LOD2.0 roof if that passes, otherwise a flat block.
4. Packaged as a scene layer package in WGS84 and published on October 25, 2026.

## Accuracy and checks
- On the cells where the lidar saw roof, the buildings are within 0.5 m of the lidar roof on 96.7% of cells and within 1 m on 98.1%
  (flat blocks alone: 56.9% and 80.4%). The lidar is also what the roofs were built from, so this measures fidelity to the lidar, not an
  independent accuracy.
- An assistant reviewed 109 imagery crops, including 97 buildings using roofer. These are preliminary visual observations, not City-reviewed accuracy results. The separate blank rating file remains for the City reviewer.
- The package and hosted layer have 21,561 buildings. Their FP_ID count and sum match the source; source IDs are unique. ArcGIS Pro package validation passed without warnings. Hosted model counts and roof-area totals match the validated package.
- Roof attributes apply to 20,730 retained roofer buildings: 4,855,408.3 m² of roof surface, including 1,230,559.8 m² under 5 degrees. The 831 Esri fallback buildings have null roof attributes and are excluded from these totals.

## Limits
- **Planning estimates, not surveyed buildings.** Heights are roof-minus-ground from lidar, not code-defined building heights.
- **Complex roofs can come out fragmented**: many small facets where one or two planes are real. Chimneys and dormers are modelled when the
  lidar sees them and may be missing or merged where it does not.
- **Footprints are the County's.** Footprints that hold several buildings, or buildings built or removed since, are as the County drew them;
  stale footprints can cause the fallback to model a roof over ground or a demolished structure. These need review; they are not corrected building records.
- **Under trees, glass roofs and dark roofs the lidar sees less**, and those buildings are the ones that fall back to simpler models.
- Roof attributes (slope, azimuth, areas) are geometry from the lidar roof. They are **not a solar production estimate**: no shading, panel
  layout or weather.

## Coordinates
Horizontal: WGS84, taken from NAD83(2011) with the transformation `WGS_1984_(ITRF08)_To_NAD_1983_2011`, as every other layer in the set.
Vertical: heights are NAVD88 (Geoid18) metres; the package's vertical label is EGM96 (see the scene-layers README).

## Download
The [scene layer package (SLPK, 20.2 MiB)](https://stmillcreeklidar.blob.core.windows.net/cogs/millcreek-lidar/buildings/20261025/buildings_hybrid_v2.slpk) contains the same three-way hybrid used by this hosted layer. Release: October 25, 2026; 21,228,379 bytes.

SHA-256: `62674f95c4e7a292c4ce66e8c2b55aac9d60c360e2ea50e3e7bde5521495949f`.


{{lidar}}

{{contact}}

# Terms of use

{{terms}}

{{terms_county}}
