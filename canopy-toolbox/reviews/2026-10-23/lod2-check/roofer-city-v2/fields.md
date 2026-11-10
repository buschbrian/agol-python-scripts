# Packaged v2 fields

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
