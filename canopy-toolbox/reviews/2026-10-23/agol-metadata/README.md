# Item text, data dictionary and metadata for the Millcreek LiDAR 2023 items (October 23, 2026)

Brian asked on October 23 to "clean up all of the text inside each one and go into more depth about each field and have a
data dictionary" for the eight layers published that day ([PUBLISHING.md](../PUBLISHING.md), section 3). Everything
applied is in this folder and was applied from it with [apply_metadata.py](apply_metadata.py). **No item was shared,
deleted or retitled.** Styling (renderers, pop-ups, vector tile styles, web maps, thumbnails) is the styling session's
and was not touched.

## Files
| File | What it is |
|---|---|
| `features.md`, `slope.md`, `contours.md`, `treetops.md`, `crowns.md`, `hillshade.md`, `buildings3d.md`, `terrain.md` | One per item: front matter (item ID, title, summary, tags, credits, ISO topics, resolution, lineage), `# Description`, `# Terms of use`, and `# Fields` tables |
| `_shared.md` | Blocks pasted into every item (`{{warning}}`, `{{lidar}}`, `{{coordinates}}`, `{{set}}`, `{{contact}}`, `{{terms}}`, `{{terms_county}}`, `{{terms_parcels}}`) so the wording is the same everywhere |
| `apply_metadata.py` | `check` (render and validate, no sign-in), `diff` (dry run against what is online), `apply ITEM --go`, `metadata ITEM --go`, `readback`, `snapshot` |
| `rendered/*.html` | Each item's text as it is sent, for reading in a browser |
| `record/` | `before-items.json` and `before-fields.json` (online state before any change), `dry-run.txt` (the first dry run), `applied.json` (each write and its answer), `readback.json` and `after-items.json` (state after), `metadata/*.xml` (the metadata uploaded), `packages-before-move.json` |
| [PACKAGES.md](PACKAGES.md) | What deleting the eight uploaded package items would do, their cost, and the recommendation |

```
set PYTHONNOUSERSITE=1
set PY="C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
%PY% apply_metadata.py check
%PY% apply_metadata.py diff features
%PY% apply_metadata.py apply features --go
%PY% apply_metadata.py metadata features --go
%PY% apply_metadata.py readback
```
To change an item's text later, edit its `.md` file, run `diff` for that item, then `apply ITEM --go` and `readback`.
Rerun `metadata ITEM --go` after any text change, so the metadata's dates, topics and lineage are kept (ArcGIS Online
re-syncs the rest of the metadata from the item text on its own).

## What each item now carries
- **Title** unchanged (all eight already follow "Millcreek <product> (2023 lidar), planning estimate", and the styling
  session and web maps find them by title).
- **Summary**, under 250 characters, starting with what the layer is and ending "Unvalidated planning estimate; not
  surveyed or field-verified."
- **Description**: the warning first; what it shows; legend or classes (vector tile and tile layers: what each class
  means, its counts and areas, that the tiles carry no attributes); how it was made; accuracy and checks in plain
  language (every figure from the run records); limits; coordinates (NAD83(2011) to WGS84 with
  `WGS_1984_(ITRF08)_To_NAD_1983_2011`, NAVD88 (Geoid18) metres); the lidar source (USGS project UT_2023SaltLakeCo_C24,
  QL1, flown 2023-10-07 to 2023-11-04); the eight-layer set; contact.
- **Data dictionary** in the description: buildings (30 fields) with the HEIGHT_STATUS flag table, canopy cover zones (12
  fields) with the zone table, and the 3D buildings' 43 fields. The terrain's description has a table of units, datum,
  range, tiles, LERC error and extent.
- **Tags**: a common set (Millcreek, Utah, Salt Lake County, lidar, 2023 lidar, 3DEP, planning estimate) plus the
  layer's own.
- **Credits**: City of Millcreek GIS; the lidar; Salt Lake County Assessor and Surveyor for the footprints; the City
  parcel layer for the zones.
- **Terms of use**: the planning-estimate terms on all eight; Salt Lake County's footprint terms (paraphrased from the
  County item's own terms) on the two building items; the parcel caveat on the feature layer.
- **Field descriptions** on both hosted feature layers (42 fields, with ArcGIS Online's value types), shown in the Data
  tab and Map Viewer's field information. The scene layer's own field definitions were not changed; its fields are documented
  in its description.
- **ISO metadata**: ArcGIS Online already kept each item's metadata in step with its text. Added: publication date
  (2026-10-23), the flight dates as the temporal extent, ISO topic categories, City of Millcreek GIS as originator and
  point of contact, 0.5 m resolution, and a lineage statement.

## What the data showed while writing the dictionary
Read from the hosted layers and the source data on October 23, and written into the text:
- **Shape__Area and Shape__Length are Web Mercator**, about 1.74 and 1.32 times the true values at Millcreek (the city
  zone's Shape__Area is 58,283,002 against a true 33,453,372 m2). The descriptions point to FOOTPRINT_M2 and ZONE_ACRES.
- **Many County fields are empty in this snapshot**: BLDGHEIGHT and SOURCE for every footprint, ADDRESS for 21,960 of
  22,042, BuiltYear present for 21; Carto (1, 2, 6) and BuildType (free text, "Appartments" among it) are undocumented
  by the County.
- **Keys**: SOURCE_ID is the County OBJECTID as text and equals SOURCE_OID; SOURCE_OID is the one key in both the feature
  layer and the scene layer. In the scene layer FP_ID is the building-heights row (1 to 22,042) and ORIG_OID is the LOD
  tool's own input row (equal to FP_ID for only 49 blocks).
- **Extract LOD2 Buildings' RMSE, MEAN_ERR and PCT_HI_ERR are not defined in Esri's tool documentation**; the dictionary
  says so and gives their ranges. MP_VOL was checked: it equals footprint area times block height to 0.1% for 90% of
  blocks.
- Treetop and crown classes include their upper value (ArcGIS class breaks); the tallest treetop is 42.9 m, inside the
  top class's 50 m bound.

## How it was applied (October 23, 2026)
1. `diff` for all eight (`record/dry-run.txt`).
2. One field description sent alone first (SOURCE_OID), read back: the description is stored as a JSON string of value
   and value type; the field's other properties and the layer's drawing info were unchanged.
3. `apply features --go`. Layer 0 took its 30 descriptions; **layer 1 answered success but stored none**. The cause was
   `<owner group>` in the ZONE_ID description: ArcGIS Online drops the whole fields update, silently, when a description
   contains `<` or `>` (the item description's sanitiser had also removed it). Reworded, reapplied, both layers correct;
   `check` now refuses `<` and `>` in field descriptions.
4. `apply --go` for the other seven, then `metadata contours --go` alone and a re-read of its item text (unchanged),
   then the other seven.
5. `readback` (`record/readback.json`): every title, summary, tag list, credit line, description and terms of use
   equals its file (descriptions compared as text, since ArcGIS Online rewrites HTML), and every field description on
   both layers equals its file. All eight items are still **private**.

The styling session had already given the buildings layer a class-breaks renderer before these writes; it was still in
place afterwards.

## Left for others
- **Thumbnails**: none made here. A thumbnail drawn now would show the default styling; better made once the styling
  session has finished (Item page > Edit thumbnail).
- **Sharing**: Brian's step. The text is written for a public audience (no internal paths or repository links).
- **Delete protection**: turned on later on October 23 for the eight packages and the eight hosted layers, on Brian's
  go-ahead (all 16 read back protected; `record/protection.json`).
