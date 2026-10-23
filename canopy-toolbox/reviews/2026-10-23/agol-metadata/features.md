---
key: features
id: d5effaee6c66497eaeb64e4c2e0f496e
title: Millcreek buildings and canopy cover zones (2023 lidar), planning estimate
summary: Building footprints with lidar roof heights, and tree canopy cover by ownership zone, for Millcreek, Utah, from 2023 lidar. Unvalidated planning estimate; not surveyed or field-verified.
tags: Millcreek, Utah, Salt Lake County, lidar, 2023 lidar, 3DEP, planning estimate, buildings, building footprints, building height, roof height, tree canopy, canopy cover, urban forest
credits: City of Millcreek GIS. Lidar: 2023 Salt Lake Valley QL1 lidar (USGS 3DEP, project UT_2023SaltLakeCo_C24). Building footprints: Salt Lake County Assessor and Surveyor (downloaded October 19, 2026). Parcels: City of Millcreek parcel layer (2025 tax year).
iso_topics: structure, environment, planningCadastre
resolution_m: 0.5
lineage: County building footprints (Salt Lake County, downloaded 2026-10-19) summarised against 0.5 m lidar roof and bare-earth rasters from the 2023 Salt Lake Valley QL1 lidar: roof points where 2 of 3 independent classifications agree, heights as roof minus terrain per cell. Canopy cover from a 0.5 m canopy height model (canopy at least 2 m) summarised over ownership zones from the City parcel layer (2025 tax year). Projected to Web Mercator with WGS_1984_(ITRF08)_To_NAD_1983_2011 and checked against the source library.
---

# Description

{{warning}}

## What it shows
Two layers for Millcreek, Utah:

- **Buildings** (22,042 polygons): Salt Lake County's building footprints inside or crossing the city limits, each with
  roof-height statistics measured from the 2023 lidar. 21,562 footprints have a height; 480 have no lidar roof inside
  them and their height fields are empty (possible reasons include buildings demolished since the County drew them,
  very small structures and roofs hidden under trees).
- **Canopy cover zones** (13 polygons): the share of the ground covered by tree canopy at least 2 m tall, for the whole
  city and for groups of land by ownership (private, public and its owner groups, uncertain owner, and land outside every
  parcel). Citywide canopy cover is **25.59%** of the observed area (2,103 acres).

Typical uses: a citywide look at building heights and massing, finding tall or unusual buildings for review, canopy goals
and comparisons between ownership groups. Heights are **roof minus ground**, not building heights as a building code
defines them.

## How it was made
- **Roofs.** Every lidar point was classified three independent ways: this project's own first classification, the
  IGN FRACTAL model, and Esri's pretrained building model. A point counts as roof when at least two of the three call it
  building. The roof surface is the highest first or single return in each 0.5 m cell from those points.
- **Ground.** The bare-earth terrain is interpolated at 0.5 m from the ground-classified returns (under a building it is
  interpolated from the ground around it).
- **Heights.** For every 0.5 m cell whose centre lies inside a footprint (and inside the city), roof elevation minus
  terrain elevation. A footprint's median (HEIGHT_P50_M), 95th percentile and maximum are taken over the cells that have
  both a roof and terrain value. Footprint shapes and County attributes are unchanged.
- **Canopy.** A canopy height model at 0.5 m: vegetation returns minus terrain, with roofs masked out. Canopy is any
  observed cell at least 2 m above the ground. Cover for a zone is canopy cells as a share of the zone's observed cells,
  counted by cell centres.
- **Zones.** From the City's parcel layer: parcels grouped by owner with fixed rules (named public agencies, schools,
  housing authorities and districts are public; everyone else, including utilities, churches and nonprofits, is private;
  missing or mixed owners are uncertain), dissolved by group and clipped to the city. "No parcel" is the city outside every
  parcel, mostly streets and other rights-of-way. **Zones overlap**: the whole-city zone contains all the others and the
  public owner groups sit inside "Public / government parcels", so do not add areas across rows.

## Accuracy and checks
- **Roof classification**, against 1,217 hand-labelled roof and non-roof parts on one 1 km tile (a deliberately hard
  sample, not a citywide accuracy): 92.8% of roofs found; 2.8% of non-roof parts called roof.
- **Vegetation classification**, same tile: 95.9% of tree parts called vegetation; 10.7% of non-vegetation parts called
  vegetation; shrubs 76.5%.
- **Roof support.** 2,380 footprints have a lidar roof on less than 80% of their area (LOW_ROOF_SUPPORT). Their heights
  are less reliable: lower roofs, porches and carports are often the part missed. Of the footprints with at least 95%
  support, the 3D blocks built from these heights are within 1 m of the median roof for all but 13 of 14,229.
- **Canopy coverage.** About 99.4% of every zone is observed by the lidar; the low and high bounds in the layer show how far
  the unobserved cells could move each figure (about half a point at most).
- **Copies.** Every value and every footprint shape was checked against the source library before upload (0 rows
  differ), and the projection to Web Mercator was checked vertex by vertex (all within 0.07 mm of Esri's own projection
  with the ITRF08 transformation).
- None of these figures is a field validation. No building height has been compared with a survey or a plan set.

## Limits
- **Heights are roof-minus-terrain estimates**, not code-defined building heights (which are measured to a defined point
  of the roof from a defined grade). Chimneys, rooftop equipment, parapets and branches over a roof raise the maximum;
  the median is the safest single figure.
- Footprints are the County's. A footprint can hold several buildings, a building can have several footprints, and
  buildings built or demolished since the County drew them show up as missing or empty roofs. 22,042 is a count of
  footprint records, not of buildings.
- Many County fields are empty in this snapshot (BLDGHEIGHT, SOURCE, most ADDRESS and BuiltYear values). They are carried
  unchanged so the layer joins back to the County's.
- Canopy at 2 m includes tall shrubs and excludes lower plants. Leaf-off trees in early November may be under-counted
  where few returns came back from bare branches.
- **Do not use `Shape__Area` or `Shape__Length` for measurement.** ArcGIS Online computes them in Web Mercator, which
  inflates areas here by about 1.74 times and lengths by about 1.32 times. Use FOOTPRINT_M2 and ZONE_ACRES, which were
  computed in UTM before upload.

{{coordinates}}

{{lidar}}

## Data dictionary: buildings (layer 0)
Field descriptions below are also stored on the layer's fields (Data tab, and field information in Map Viewer).

{{fields:0}}

### HEIGHT_STATUS flags
Every footprint carries `UNVALIDATED`; the other flags are added, separated by semicolons, when they apply
(for example `UNVALIDATED;LOW_ROOF_SUPPORT`).

| Flag | Footprints | Meaning |
|---|---:|---|
| UNVALIDATED | 22,042 | Every record: no height has been checked against a survey. |
| LOW_ROOF_SUPPORT | 2,380 | Lidar roof on less than 80% of the footprint's cells (ROOF_COV_PCT under 80). A review flag, not an accuracy threshold. |
| NO_ROOF_SUPPORT | 477 | No cell in the footprint has a lidar roof; height fields are empty. Often a demolished, very small or tree-covered building. |
| NEGATIVE_HEIGHT | 35 | At least one cell has its roof below the terrain (NEG_H_CELLS above 0). Those cells are kept; no footprint has a negative median. |
| PARTIAL_AOI | 27 | The footprint crosses the city limit; statistics use only the part inside (AOI_PCT under 100). |
| GEOMETRY_REPAIRED | 5 | The County polygon was invalid and was repaired (area change under 0.000000001 m2). |
| NO_CELL_CENTERS | 3 | A sliver inside the city that holds no 0.5 m cell centre; no statistics. |

## Data dictionary: canopy cover zones (layer 1)

{{fields:1}}

### Zones
| ZONE_ID | ZONE_NAME | Acres | Canopy cover | What it is |
|---|---|---:|---:|---|
| CITY | Millcreek (whole city) | 8,266.5 | 25.59% | The municipal boundary. Contains every other zone. |
| OWNERSHIP:PRIVATE | Private parcels | 5,751.0 | 29.10% | Parcels with a private owner (people, companies, utilities, churches, nonprofits). |
| OWNERSHIP:PUBLIC_GOVERNMENT | Public / government parcels | 838.9 | 24.91% | Parcels owned by a government body; split into the PUBLIC zones below. |
| OWNERSHIP:UNKNOWN_OWNER | Uncertain owner | 206.3 | 19.59% | Owner missing, truncated or mixed in the parcel record. |
| OWNERSHIP:NO_PARCEL | No parcel (streets, rights-of-way) | 1,470.4 | 13.12% | The city outside every parcel, mostly streets. Not proof of public ownership. |
| PUBLIC:SALT_LAKE_COUNTY | Salt Lake County | 536.1 | 29.08% | Parcels owned by Salt Lake County. |
| PUBLIC:PUBLIC_SCHOOL | Public schools | 162.6 | 8.06% | Parcels of public schools. |
| PUBLIC:SALT_LAKE_CITY | Salt Lake City | 53.3 | 50.53% | Parcels owned by Salt Lake City inside Millcreek. |
| PUBLIC:MILLCREEK | Millcreek (city-owned) | 32.6 | 26.43% | Parcels owned by the City of Millcreek. |
| PUBLIC:PUBLIC_DISTRICT | Public districts | 31.2 | 6.87% | Public districts (for example Mt. Olympus Improvement District). |
| PUBLIC:STATE_OF_UTAH | State of Utah | 13.8 | 11.48% | Parcels owned by the State of Utah. |
| PUBLIC:PUBLIC_HOUSING | Public housing | 5.4 | 8.64% | Parcels of public housing authorities. |
| PUBLIC:FEDERAL | Federal | 3.9 | 10.00% | Parcels owned by the federal government. |

{{set}}

{{contact}}

# Terms of use

{{terms}}

{{terms_county}}

{{terms_parcels}}

# Fields layer=0 buildings

| Field | Alias | Type | Value type | Units | Description |
|---|---|---|---|---|---|
| OBJECTID | OBJECTID | OID | uniqueIdentifier | | Row number assigned by ArcGIS Online. Not stable if the layer is republished; do not use it as a key. Use SOURCE_OID to join to the County footprints or to the 3D buildings layer. |
| SOURCE_ID | County building ID | String (40) | uniqueIdentifier | | Salt Lake County's OBJECTID for this footprint, as text (the same number as SOURCE_OID). Unique and never empty. From the County's public Building Footprints service, downloaded October 19, 2026. |
| SOURCE_OID | SOURCE_OID | Integer | uniqueIdentifier | | Salt Lake County's OBJECTID for this footprint, as a number (719,802 to 1,077,673). Unique and never empty. The join key to the County footprints and to the Millcreek 3D buildings scene layer, which carries the same field. |
| ADDRESS | Address | String (75) | locationOrPlaceName | | County address attribute, carried unchanged. Empty for 21,960 of 22,042 footprints in this snapshot; not a complete address list. |
| CITY | CITY | String (35) | locationOrPlaceName | | County city attribute, carried unchanged: MILLCREEK (21,945), UNINCORPORATED (73), SALT LAKE CITY (19), MURRAY (4), empty (1). Footprints were selected by their position inside the Millcreek boundary, not by this field. |
| COUNTY | COUNTY | String (20) | locationOrPlaceName | | County attribute, carried unchanged: SALT LAKE COUNTY (22,038), SALT LAKE (3), empty (1). |
| PARCEL_ID | Parcel ID | String (25) | uniqueIdentifier | | County parcel number recorded on the footprint, carried unchanged. Empty for 103 footprints. Not checked against the current parcel layer. |
| SOURCE | SOURCE | String (30) | description | | County attribute, carried unchanged. Empty for every footprint in this snapshot. |
| BuildType | Building type | String (50) | typeOrCategory | | County building-type attribute, carried unchanged; free text, not documented by the County. Empty for 21,879. Values seen: Appartments [sic] 56, Residential 42, Commercial 33, Government 5, numeric codes (111, 112, 114, 142, 566, 954, 115 10-19) and "?". |
| Carto | Carto | SmallInteger | typeOrCategory | | County attribute, carried unchanged; its meaning is not documented by the County. Empty for 21,906; values 1 (98), 6 (33) and 2 (5). |
| JURISDICTION | JURISDICTION | String (50) | locationOrPlaceName | | County jurisdiction attribute, carried unchanged: Millcreek (20,266), empty (1,677), Unincorporated SLCo (73), Salt Lake (20), MILLCREEK CITY (5), MURRAY (1). |
| BLDGHEIGHT | County height field | Double | measurement | | The County's own building-height field, carried unchanged. Empty for every footprint in this snapshot and not used in any calculation. For a height, use HEIGHT_P50_M or HEIGHT_P50_FT. |
| BuiltYear | Year built | SmallInteger | dateAndTime | year | County year-built attribute, carried unchanged. Present for only 21 footprints (1956 to 2021); empty otherwise. |
| FOOTPRINT_M2 | Footprint area (m2) | Double | measurement | square metres | True ground area of the whole footprint polygon, computed in NAD83(2011) / UTM 12N before upload (0.10 to 19,324.6 m2). Use this for area, not Shape__Area. Multiply by 10.7639 for square feet. |
| AOI_PCT | AOI_PCT | Double | percentageOrRatio | percent | Share of the footprint's area inside the Millcreek city limits, 0 to 100. Under 100 for the 27 footprints that cross the boundary (PARTIAL_AOI = 1); their statistics use only the part inside. |
| ROOF_COV_PCT | Roof support (% of footprint cells) | Double | percentageOrRatio | percent | Roof support: ROOF_CELLS as a percentage of GRID_CELLS, 0 to 100. The share of the footprint's 0.5 m cells that have a lidar roof (2 of 3 classifiers agree) and terrain. Under 80 sets LOW_ROOF_SUPPORT. A review indicator, not an accuracy. Empty for the 3 footprints with no cell centre. |
| ROOF_Z50_M | Median roof elevation (m, NAVD88) | Double | measurement | metres, NAVD88 (Geoid18) | Median elevation of the lidar roof cells in the footprint, in metres above the NAVD88 datum (Geoid18), 1,297.6 to 1,764.2. Empty for the 480 footprints with no roof cell. |
| GROUND_Z50_M | Median ground elevation (m, NAVD88) | Double | measurement | metres, NAVD88 (Geoid18) | Median bare-earth terrain elevation in the same cells as the roof statistics, in metres NAVD88 (Geoid18), 1,294.4 to 1,757.9. Under a building the terrain is interpolated from the ground around it. Empty for the 480 footprints with no roof cell. |
| HEIGHT_P50_M | Median roof height (m) | Double | measurement | metres | Main height estimate: the median of roof elevation minus terrain over the footprint's cells with both values, in metres (0.80 to 37.06). Roof minus ground, not a code-defined building height. Empty for the 480 footprints with no roof cell. Feet: HEIGHT_P50_FT. |
| HEIGHT_P95_M | 95th percentile roof height (m) | Double | measurement | metres | 95th percentile of roof minus terrain over the same cells, in metres (0.80 to 42.22): close to the highest roof parts but not set by one stray cell. Empty for the 480 footprints with no roof cell. Feet: HEIGHT_P95_FT. |
| HEIGHT_MAX_M | Maximum roof height (m) | Double | measurement | metres | Highest single cell of roof minus terrain, in metres (0.80 to 43.32). Can be a chimney, antenna, rooftop unit, overhanging branch or noise; use with care. Empty for the 480 footprints with no roof cell. |
| GRID_CELLS | GRID_CELLS | Integer | countOrAmount | cells of 0.25 m2 | Number of 0.5 m grid cells (0.25 m2 each) whose centres fall inside the part of the footprint within the city (0 to 77,312). 0 means a sliver with no cell centre (NO_CELL_CENTERS). |
| ROOF_CELLS | ROOF_CELLS | Integer | countOrAmount | cells of 0.25 m2 | Number of those cells with both a lidar roof value and a terrain value; the cells the height statistics use (0 to 68,926). 0 means no roof support (NO_ROOF_SUPPORT). |
| NEG_H_CELLS | Cells with roof below terrain | Integer | countOrAmount | cells of 0.25 m2 | Number of cells whose roof is below the terrain (negative height), 0 to 9. They are kept in the statistics; any sets NEGATIVE_HEIGHT (35 footprints). |
| PARTIAL_AOI | PARTIAL_AOI | Integer | binary | | 1 if the footprint extends outside the Millcreek city limits (27 footprints), otherwise 0. Statistics use only the part inside the city. |
| HEIGHT_STATUS | Height flags | String (160) | typeOrCategory | | Review flags, separated by semicolons. Always UNVALIDATED, plus any of: LOW_ROOF_SUPPORT (roof on under 80% of cells, 2,380), NO_ROOF_SUPPORT (no roof cell, 477), NEGATIVE_HEIGHT (35), PARTIAL_AOI (crosses city limit, 27), GEOMETRY_REPAIRED (5), NO_CELL_CENTERS (3). Example: UNVALIDATED;LOW_ROOF_SUPPORT. |
| HEIGHT_P50_FT | Median roof height (ft) | Double | measurement | feet | HEIGHT_P50_M in feet (multiplied by 3.280839895, rounded to 0.01 ft; 2.64 to 121.60). Empty where HEIGHT_P50_M is empty. Roof minus ground, not a code-defined building height. |
| HEIGHT_P95_FT | 95th percentile roof height (ft) | Double | measurement | feet | HEIGHT_P95_M in feet (multiplied by 3.280839895, rounded to 0.01 ft; 2.64 to 138.52). Empty where HEIGHT_P95_M is empty. |
| Shape__Area | Shape__Area | Double | measurement | Web Mercator square metres | Polygon area computed by ArcGIS Online in Web Mercator. Not a true area: about 1.74 times too large at Millcreek's latitude. Use FOOTPRINT_M2. |
| Shape__Length | Shape__Length | Double | measurement | Web Mercator metres | Perimeter computed by ArcGIS Online in Web Mercator. Not a true length: about 1.32 times too long at Millcreek's latitude. |

# Fields layer=1 canopy_cover_zones

| Field | Alias | Type | Value type | Units | Description |
|---|---|---|---|---|---|
| OBJECTID | OBJECTID | OID | uniqueIdentifier | | Row number assigned by ArcGIS Online; use ZONE_ID as the key. |
| ZONE_ID | ZONE_ID | String (80) | uniqueIdentifier | | Zone code: CITY (whole city); OWNERSHIP:PRIVATE, OWNERSHIP:PUBLIC_GOVERNMENT, OWNERSHIP:UNKNOWN_OWNER, OWNERSHIP:NO_PARCEL (land outside every parcel); PUBLIC:OWNER_GROUP for each public owner group (for example PUBLIC:SALT_LAKE_COUNTY). Zones overlap: CITY holds all others and the PUBLIC zones sit inside OWNERSHIP:PUBLIC_GOVERNMENT. |
| ZONE_NAME | Zone | String (60) | nameOrTitle | | Readable zone name for legends and pop-ups, one per ZONE_ID (for example "Private parcels", "No parcel (streets, rights-of-way)"). |
| ZONE_ACRES | Zone area (acres) | Double | measurement | acres | True area of the zone polygon in acres (square metres / 4,046.8564224), computed in NAD83(2011) / UTM 12N, rounded to 0.1 acre. Do not add across rows: zones overlap. |
| OBSERVED_PCT | Lidar coverage (% observed) | Double | percentageOrRatio | percent | Share of the zone's 0.5 m cells (by cell centre) where the lidar could tell whether canopy is present, 99.06 to 99.76. The rest are unobserved and are left out of CANOPY_PCT. |
| CANOPY_PCT | Canopy cover (% of observed area) | Double | percentageOrRatio | percent | Tree canopy cover: cells with vegetation at least 2 m above the ground as a percentage of the zone's observed cells. The figure to quote (city 25.59). Unvalidated planning estimate from 2023 lidar. |
| CANOPY_LOW_PCT | Canopy cover, low bound (%) | Double | percentageOrRatio | percent | Canopy as a percentage of all the zone's cells, counting every unobserved cell as no canopy. With CANOPY_HIGH_PCT it bounds what the unobserved cells could do to the figure. A coverage bound, not a statistical confidence interval. |
| CANOPY_HIGH_PCT | Canopy cover, high bound (%) | Double | percentageOrRatio | percent | Canopy as a percentage of all the zone's cells, counting every unobserved cell as canopy. A coverage bound, not a statistical confidence interval. |
| CANOPY_ACRES | Canopy (acres) | Double | measurement | acres | Area of canopy at least 2 m tall in the zone: canopy cells times 0.25 m2, in acres, rounded to 0.1 acre (city 2,103.1). Counts observed canopy only. |
| CANOPY_PCT_OCT19 | Canopy cover, October 19 (%) | Double | percentageOrRatio | percent | The same measure from the October 19, 2026 canopy, built from an earlier single classification of the same lidar. For comparison only: the current figures are 0.2 to 1.7 points lower, mostly because roof edges and structures left the canopy. |
| Shape__Area | Shape__Area | Double | measurement | Web Mercator square metres | Polygon area computed by ArcGIS Online in Web Mercator; about 1.74 times the true area here. Use ZONE_ACRES. |
| Shape__Length | Shape__Length | Double | measurement | Web Mercator metres | Perimeter computed by ArcGIS Online in Web Mercator; about 1.32 times the true length here. |
