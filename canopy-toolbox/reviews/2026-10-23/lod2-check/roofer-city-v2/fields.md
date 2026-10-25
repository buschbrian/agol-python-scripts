| Field | Meaning |
|---|---|
| ROOF_PLANES | Roof planes of 1 m2 or more in plan, from the lidar roof (roofer). Empty where LEVEL is not roofer LoD2.2. |
| ROOF_PLAN_M2 | Area of those planes seen from above. Empty where LEVEL is not roofer LoD2.2. |
| ROOF_AREA_M2 | True (sloped) area of those planes. Empty where LEVEL is not roofer LoD2.2. |
| ROOF_SLOPE_MEAN | Slope from horizontal, weighted by plane area. Empty where LEVEL is not roofer LoD2.2. |
| ROOF_SLOPE_MAIN | Slope of the largest plane. Empty where LEVEL is not roofer LoD2.2. |
| ROOF_AZIMUTH_MAIN | Compass bearing of the largest plane's downslope direction (0 north, clockwise); empty if flat. Empty where LEVEL is not roofer LoD2.2. |
| RIDGE_HT_M | Highest roof point minus the building's ground elevation. Empty where LEVEL is not roofer LoD2.2. |
| EAVE_HT_M | Lowest roof point minus the building's ground elevation. Empty where LEVEL is not roofer LoD2.2. |
| BLDG_HT_M | Same as the ridge height: highest roof point above the building's ground. Empty where LEVEL is not roofer LoD2.2. |
| FLAT_AREA_M2 | Surface area of planes under 5 degrees. Empty where LEVEL is not roofer LoD2.2. |
| SOUTH_AREA_M2 | Surface area of planes of 5 to 70 degrees facing 135 to 225 degrees. Empty where LEVEL is not roofer LoD2.2. |
| EAST_AREA_M2 | Same, facing 45 to 135 degrees. Empty where LEVEL is not roofer LoD2.2. |
| WEST_AREA_M2 | Same, facing 225 to 315 degrees. Empty where LEVEL is not roofer LoD2.2. |
| NORTH_AREA_M2 | Same, facing 315 to 45 degrees. Empty where LEVEL is not roofer LoD2.2. |
| RF_VOLUME_M3 | Volume of roofer's LoD 2.2 solid. Empty where LEVEL is not roofer LoD2.2. |
| TINY_FACES | Roof faces under 0.5 m2 in plan (quality screening). Empty where LEVEL is not roofer LoD2.2. |
| SLIVER_FACES | Roof faces narrower than about 0.4 m (quality screening). Empty where LEVEL is not roofer LoD2.2. |
| STEEP_FACES | Roof faces steeper than 75 degrees (quality screening). Empty where LEVEL is not roofer LoD2.2. |
| LEVEL | Model used |
| CHECK_VERDICT | Check against the lidar |
| ROOFER_VERDICT | Roofer's check |
| ESRI_VERDICT | Esri LOD2.0's check |
| FALLBACK_REASON | Why not roofer |
| LOD20_GROUND_PCT | Share of footprint at ground (%) |
