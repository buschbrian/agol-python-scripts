# Publish-ready feature layers (hosting plan step 2, October 22, 2026; projected October 23)

Two small layers for ArcGIS Online, prepared by [prepare_features.py](prepare_features.py) from the October 22 library and
checked against it. **Not uploaded:** publishing them is Brian's step ([PLAN.md](../PLAN.md)).

Output: `<SSD>\lidar\2023-salt-lake-valley\runs\hosting-features-20261023\features.gdb` (record: `features.json`, copied
here), in **Web Mercator (EPSG 3857)**, projected with `WGS_1984_(ITRF08)_To_NAD_1983_2011`, the transformation every
other hosted package carries, so ArcGIS Online never has to choose one. The EPSG 6341 copies are beside it in `work.gdb`.
The October 22 build (`hosting-features-20261022`, EPSG 6341) is superseded.

| Layer | Features | What changed from the library |
|---|---:|---|
| buildings | 22,042 county footprints (21,562 with a roof height) | County editor-tracking fields dropped (GlobalID, CreationDate, Creator, EditDate, Editor); HEIGHT_P50_FT and HEIGHT_P95_FT added; readable field aliases |
| canopy_cover_zones | 13 zones | ZONE_NAME and the October 22 cover figures added from cover-comparison.csv (canopy %, low and high bounds, canopy acres, observed %, October 19 %) |

Both carry the estimate warning in their metadata. Coordinates stay EPSG 6341; ArcGIS Online reprojects for web maps.

## Checks
- buildings: 22,042 in, 22,042 out, keyed by SOURCE_OID; every copied attribute and every geometry (WKB) equal to the
  library's: 0 rows differ.
- canopy_cover_zones: 13 zones, canopy % and zone acres equal to cover-comparison.csv for all 13.
- **Projection** (`checks.projection`): every vertex of every output shape is within 0.07 mm of Esri's own projection
  of the source with the ITRF08 transformation, and at least 1.578 m from its projection without one, for all 22,042
  buildings and 13 zones (no vertex count differs). No attribute changed in projecting, and the metadata summary
  carries the estimate warning.

## To publish (Brian)
`upload.py features --go` ([upload](../upload/README.md)) publishes both layers as one hosted feature service, private
to you. Or in ArcGIS Pro, signed in to the city's ArcGIS Online organisation: add both layers to a map, set the symbology,
then Share > Web Layer > Feature. Both are small (7.8 MB), so hosted feature-layer storage is a few credits a month
(research: 2.4 credits per 10 MB per month; check Esri's credits page). Check the metadata summary carries the estimate
warning on the item page.
