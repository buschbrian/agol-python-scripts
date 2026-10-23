---
key: buildings3d
id: 5082b5bd063a4a03847f2082dc3533d1
title: Millcreek 3D buildings LOD1.2 (2023 lidar), planning estimate
summary: 21,561 Millcreek, Utah, buildings as flat-roofed 3D blocks (LOD1.2): County footprints raised to their median 2023 lidar roof height. Unvalidated planning estimate; not surveyed or field-verified.
tags: Millcreek, Utah, Salt Lake County, lidar, 2023 lidar, 3DEP, planning estimate, buildings, 3D buildings, LOD1.2, building height, massing, scene layer
credits: City of Millcreek GIS. Lidar: 2023 Salt Lake Valley QL1 lidar (USGS 3DEP, project UT_2023SaltLakeCo_C24). Building footprints: Salt Lake County Assessor and Surveyor (downloaded October 19, 2026).
---

# Description

{{warning}}

## What it shows
Every Salt Lake County building footprint in Millcreek, Utah, that has a lidar roof, as a simple 3D block (CityGML level
of detail 1.2): the footprint's outline, from the ground to a flat top at the building's median roof height. 21,561
buildings. They show the city's massing in a web scene: building heights, the scale of streets and how buildings sit on
the terrain. Roof shapes are **not** modelled.

Each block carries its footprint's County attributes and lidar roof-height statistics (see the data dictionary), so a
pop-up can show its height. The same statistics, for all 22,042 footprints, are in the Millcreek buildings and canopy
cover zones feature layer; the two join on `SOURCE_OID`.

## Using it in a scene
Put the **Millcreek bare-earth terrain** elevation layer in the scene's Ground, above World Elevation. The blocks were
built on that terrain, so they stand on it exactly. On Esri's World Elevation alone they can float or sink by up to about
a metre (see Coordinates).

## How it was made
1. **Heights.** For each County footprint, the median of lidar roof elevation minus bare-earth terrain over its 0.5 m
   cells (roof where at least two of three independent classifications agree that a point is building). The same
   figures as HEIGHT_P50_M in the feature layer.
2. **Blocks.** ArcGIS Pro's Extract LOD2 Buildings tool at LOD1.2, from a 0.5 m surface that is the lidar roof inside
   the roofs and the terrain elsewhere, with the County footprints. Each block runs from the ground around the footprint to
   the median roof. 21,562 footprints with a height went in; one sliver of 0.5 m2 (FP_ID 21952) gave no block.
3. Packaged as a scene layer package in WGS84 and published.

## Accuracy and checks
- Of 14,229 footprints with lidar roof on at least 95% of their area, the block top is within 1 m of the median roof for
  all but 13. Of the 2,380 with less than 80% roof (LOW_ROOF_SUPPORT in HEIGHT_STATUS), 695 are more than 1 m off, mostly
  low. 718 blocks in all are more than 1 m from the median roof (TOP_MINUS_ROOF50).
- Block bases sit a median 0.11 m below the lowest terrain under the footprint. Four sit 3.6 to 7.2 m above it (FP_ID
  22003, 16604, 4881, 6917): fully roofed sites where the tool read the ground near roof level.
- The hosted layer's own statistics give 21,561 buildings with FP_ID 1 to 22,042, exactly the source's.
- Roof classification on one hand-labelled 1 km tile (a hard sample, not a citywide accuracy): 92.8% of roof parts
  found, 2.8% of non-roof parts called roof. No block height has been compared with a survey or plan set.

## Limits
- **Heights are roof-minus-terrain estimates**, not code-defined building heights. Pitched roofs are shown flat at their
  median height, so ridges are higher than the block and eaves lower.
- One block per County footprint. Footprints that hold several buildings, or buildings split across footprints, are shown
  as the County drew them; buildings missing from the County layer or built since are absent.
- Low-support footprints (LOW_ROOF_SUPPORT) often have a lower roof part missed by the lidar classification, so their
  blocks are too low or too high over part of the footprint.

## Coordinates
Horizontal: WGS84, taken from NAD83(2011) with the transformation `WGS_1984_(ITRF08)_To_NAD_1983_2011`, the same as every
layer in the Millcreek LiDAR 2023 set. **Vertical: the layer is labelled EGM96 (EPSG 5773), but its heights are NAVD88
(Geoid18) metres, left as they were measured.** The packaging tool assigned the label because the source carried no
vertical system. In the Salt Lake Valley the two surfaces differ by well under a metre, so on Esri's World Elevation the
blocks sit within about that of the ground; on the Millcreek bare-earth terrain they match exactly. Block elevations run
from 1,294.1 m to 1,764.2 m.

{{lidar}}

## Data dictionary (43 fields)
Field names are shown as stored (the scene layer has no aliases). Fields from SOURCE_ID to BuiltYear and GlobalID to
Editor are Salt Lake County's, carried unchanged; FOOTPRINT_M2 to HEIGHT_STATUS are the lidar statistics (identical to the
feature layer); FP_ID onward were added when the blocks were built. Values are for the 21,561 blocks.

{{fields:scene}}

### HEIGHT_STATUS flags
Every block carries `UNVALIDATED`, plus any of: `LOW_ROOF_SUPPORT` (lidar roof on under 80% of the footprint's cells; a
review flag, not an accuracy threshold), `NEGATIVE_HEIGHT` (at least one cell with roof below terrain, kept),
`PARTIAL_AOI` (the footprint crosses the city limit; statistics use the part inside) and `GEOMETRY_REPAIRED` (the County
polygon was invalid and was repaired). Footprints with no roof support have no block.

{{set}}

{{contact}}

# Terms of use

{{terms}}

{{terms_county}}

# Fields document scene

| Field | Alias | Type | Value type | Units | Description |
|---|---|---|---|---|---|
| OBJECTID | OBJECTID | OID | uniqueIdentifier | | Row number of the block in the package (9 to 21,569, with gaps where empty features were removed). Not a key; use SOURCE_OID or FP_ID. |
| SOURCE_ID | SOURCE_ID | String | uniqueIdentifier | | Salt Lake County's OBJECTID for the footprint, as text (same number as SOURCE_OID). |
| SOURCE_OID | SOURCE_OID | Integer | uniqueIdentifier | | Salt Lake County's OBJECTID for the footprint, as a number. Join key to the Millcreek buildings feature layer and to the County footprints. |
| ADDRESS | ADDRESS | String | locationOrPlaceName | | County address attribute; empty for almost every footprint in this snapshot. |
| CITY | CITY | String | locationOrPlaceName | | County city attribute (mostly MILLCREEK). Not used to select footprints. |
| COUNTY | COUNTY | String | locationOrPlaceName | | County attribute (SALT LAKE COUNTY). |
| PARCEL_ID | PARCEL_ID | String | uniqueIdentifier | | County parcel number recorded on the footprint; not checked against current parcels. |
| SOURCE | SOURCE | String | description | | County attribute; empty for every footprint in this snapshot. |
| BuildType | BuildType | String | typeOrCategory | | County free-text building type; mostly empty; values include Appartments [sic], Residential, Commercial, Government and numeric codes. Not documented by the County. |
| Carto | Carto | SmallInteger | typeOrCategory | | County attribute with values 1, 2 and 6 on a few footprints; meaning not documented by the County. |
| JURISDICTION | JURISDICTION | String | locationOrPlaceName | | County jurisdiction attribute (mostly Millcreek; some empty). |
| BLDGHEIGHT | BLDGHEIGHT | Double | measurement | | County height field; empty for every footprint. Not used: the block height comes from the lidar. |
| BuiltYear | BuiltYear | SmallInteger | dateAndTime | year | County year built; present for only a handful of footprints. |
| GlobalID | GlobalID | String | uniqueIdentifier | | County editor-tracking global ID, carried unchanged (dropped from the feature layer). |
| CreationDate | CreationDate | Date | dateAndTime | | County editor tracking: when the County created the footprint record. |
| Creator | Creator | String | nameOrTitle | | County editor tracking: the County account that created the record. |
| EditDate | EditDate | Date | dateAndTime | | County editor tracking: when the County last edited the record. |
| Editor | Editor | String | nameOrTitle | | County editor tracking: the County account that last edited the record. |
| FOOTPRINT_M2 | FOOTPRINT_M2 | Double | measurement | square metres | True ground area of the whole footprint, computed in NAD83(2011) / UTM 12N. |
| AOI_PCT | AOI_PCT | Double | percentageOrRatio | percent | Share of the footprint inside the Millcreek city limits, 0 to 100. |
| ROOF_COV_PCT | ROOF_COV_PCT | Double | percentageOrRatio | percent | Roof support: share of the footprint's 0.5 m cells with a lidar roof and terrain. Under 80 sets LOW_ROOF_SUPPORT. A review indicator, not an accuracy. |
| ROOF_Z50_M | ROOF_Z50_M | Double | measurement | metres, NAVD88 (Geoid18) | Median lidar roof elevation over the footprint's roof cells. |
| GROUND_Z50_M | GROUND_Z50_M | Double | measurement | metres, NAVD88 (Geoid18) | Median bare-earth terrain elevation in the same cells (interpolated under the building). |
| HEIGHT_P50_M | HEIGHT_P50_M | Double | measurement | metres | Median roof minus terrain: the height the block is built to (0.80 to 37.06). Not a code-defined building height. |
| HEIGHT_P95_M | HEIGHT_P95_M | Double | measurement | metres | 95th percentile of roof minus terrain; close to the highest roof parts. |
| HEIGHT_MAX_M | HEIGHT_MAX_M | Double | measurement | metres | Highest single cell of roof minus terrain; can be a chimney, rooftop unit, branch or noise. |
| GRID_CELLS | GRID_CELLS | Integer | countOrAmount | cells of 0.25 m2 | 0.5 m cells whose centres fall inside the footprint's part within the city. |
| ROOF_CELLS | ROOF_CELLS | Integer | countOrAmount | cells of 0.25 m2 | Of those, cells with both a lidar roof and terrain; the cells the statistics use. |
| NEG_H_CELLS | NEG_H_CELLS | Integer | countOrAmount | cells of 0.25 m2 | Cells with roof below terrain (kept in the statistics). |
| PARTIAL_AOI | PARTIAL_AOI | Integer | binary | | 1 if the footprint crosses the city limit, otherwise 0. |
| HEIGHT_STATUS | HEIGHT_STATUS | String | typeOrCategory | | Review flags separated by semicolons; see HEIGHT_STATUS flags below. |
| FP_ID | FP_ID | Integer | uniqueIdentifier | | The footprint's row number in the lidar building-heights table (1 to 22,042), used to join each block back to its statistics when the blocks were built. Unique per block. |
| ORIG_OID | ORIG_OID | Integer | uniqueIdentifier | | Written by Extract LOD2 Buildings; by its name and range, the row number of the footprint in the tool's input (1 to 21,562). Internal to the build; not the same as FP_ID. Do not use as a key. |
| RMSE | RMSE | Double | measurement | metres (presumed) | Written by Extract LOD2 Buildings; Esri's tool documentation does not define it. By its name and values a fit statistic of the block against the lidar height surface (median 1.04, range 0.02 to 19.43). Not reviewed; do not use as an accuracy. |
| MEAN_ERR | MEAN_ERR | Double | measurement | metres (presumed) | Written by Extract LOD2 Buildings; not defined in Esri's tool documentation. By its name and values a mean fit difference (median 0.66, range 0.01 to 13.74). Not reviewed; do not use as an accuracy. |
| PCT_HI_ERR | PCT_HI_ERR | Double | percentageOrRatio | fraction 0 to 1 | Written by Extract LOD2 Buildings; not defined in Esri's tool documentation. A fraction from 0 to 1 (median 0.45; 262 blocks 0, 4 blocks 1), by its name the share of the surface with a high fit difference. Not reviewed. |
| LOD | LOD | Double | orderedOrRanked | | Level of detail of the block: 1.2 for every block (flat roof at the building's median height). |
| MP_VOL | MP_VOL | Double | measurement | cubic metres | Volume of the block (0.06 to 264,766 m3); equals footprint area times block height (TOP_Z minus BASE_Z) to within 0.1% for 90% of blocks. Ground to median roof, not an interior volume. |
| BASE_Z | BASE_Z | Double | measurement | metres, NAVD88 (Geoid18) | Elevation of the block's base, its lowest point (1,294.10 to 1,750.30). |
| TOP_Z | TOP_Z | Double | measurement | metres, NAVD88 (Geoid18) | Elevation of the block's flat top, its highest point (1,295.55 to 1,764.18). |
| TERRAIN_MIN_Z | TERRAIN_MIN_Z | Double | measurement | metres, NAVD88 (Geoid18) | Lowest bare-earth terrain cell under the footprint (1,294.30 to 1,750.51). |
| TOP_MINUS_ROOF50 | TOP_MINUS_ROOF50 | Double | measurement | metres | TOP_Z minus ROOF_Z50_M: how far the block top is from the median lidar roof (median -0.05; -29.75 to +0.10). Large negatives are low-support footprints. |
| BASE_MINUS_TMIN | BASE_MINUS_TMIN | Double | measurement | metres | BASE_Z minus TERRAIN_MIN_Z: the block base against the lowest terrain under it (median -0.11; -10.91 to +7.17). Negative only hides wall below ground; four blocks are 3.6 to 7.2 m above. |
