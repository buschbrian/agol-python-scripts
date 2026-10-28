# Scene layer packages of the buildings (hosting plan step 3, October 22, 2026)

Two scene layer packages of the 3D building massing ([massing](../../massing/README.md)), made by
[make_slpk.py](make_slpk.py). **Not uploaded:** sharing them is Brian's step ([PLAN.md](../PLAN.md)).
Output: `<SSD>\lidar\2023-salt-lake-valley\runs\scene-layers-20261022\` (record `slpk.json`, copied here).

| Package | What | Buildings | Size |
|---|---|---:|---:|
| buildings_lod12.slpk | Flat blocks from the lowest ground to the median roof | 21,561 | 9.2 MB |
| buildings_lod20.slpk | Fitted roof forms (experimental: not checked against roof shapes) | 21,561 | 19.3 MB |

Every building carries its footprint's county attributes and roof-height statistics (FP_ID, ROOF_Z50_M, HEIGHT_P50_M,
HEIGHT_P95_M, ROOF_COV_PCT, HEIGHT_STATUS and the rest) for pop-ups.

## Checks
- **All buildings are in each package:** the package's own FP_ID statistics (read from the .slpk) give 21,561 IDs summing
  to 237,493,394, the same as the source feature class. Pro cannot count features on a scene layer.
- **Validate Scene Layer Package:** passes; its only warning is "vertex normals may be required by Esri products", which
  Esri's own packaging tool produces.
- Packaging took 11 s and 15 s.

## Coordinates
- Horizontal: WGS84 (EPSG 4326), the usual choice for ArcGIS Online global scenes. NAD83(2011) to WGS84 uses the
  transformation WGS_1984_(ITRF08)_To_NAD_1983_2011, named explicitly.
- **Vertical: the packages are labelled EGM96 (EPSG 5773), but their heights are NAVD88 (Geoid18) metres, left as they
  were.** The tool assigned the label because the source had no vertical coordinate system. In the Salt Lake Valley the two
  surfaces differ by well under a metre, so buildings will sit on Esri's world ground within about that. On the city's own
  elevation layer (from the same NAVD88 terrain; [tiles](../tiles/README.md)) they match exactly.

## To share (Brian)
Both are under 1 GB, so they upload in the browser: ArcGIS Online > Content > New item > the .slpk, then Create hosted
layer; or in Pro, Share > Share Package. Add the layer to a web scene with the city elevation layer as ground once that
exists. Sharing a scene layer package is billed as file storage (research: about 1.2 credits per GB per month, so under
1 credit a month for both; check Esri's credits page). Set sharing to your organisation or the public as decided.
