# The eight uploaded package items: what deleting them would do (October 23, 2026)

`upload.py` added each package (the file geodatabase zip, four `.vtpk`, two `.tpkx`, one `.slpk`) as an item and then
published a hosted layer from it. This note answers Brian's question of what to do with those eight package items.
**Nothing was deleted.** The only change made: the eight package items were moved into a new folder,
**Millcreek LiDAR 2023 source packages** (ArcGIS Online has no subfolders, so it is a sibling of *Millcreek LiDAR 2023*,
which now holds only the eight hosted layers). All eight are still private and every hosted layer still answers
(checked after the move). Record: `record/packages-before-move.json`.

## What ties them to the layers
Read from ArcGIS Online on October 23: each package item has exactly one relationship, `Service2Data`, from its hosted
layer (the layer records which file it was published from). No other item depends on any of them (`dependent_to` is
empty for all eight), none is shared, none has delete protection.

| Package item | Type | Size online | Hosted layer it published |
|---|---|---:|---|
| `ee182c9a7eec4994b7e19d2be8dd27b5` | File Geodatabase | 4.3 MB | buildings and canopy cover zones (Feature Service `d5effaee…`) |
| `bec13573a71c4df2b4642fda4a559021` | Vector Tile Package | 22.7 MB | slope classes (`3b5b1a91…`) |
| `377dd1de82204e63addb6905a9322bb3` | Vector Tile Package | 6.7 MB | 2 m contours (`50573eeb…`) |
| `2dcae544e70c47589f8226dc0ad74351` | Vector Tile Package | 7.7 MB | treetops (`924b993c…`) |
| `d3ca707cda6544dd9962390c1e7e00db` | Vector Tile Package | 33.9 MB | tree crowns (`d9388dc8…`) |
| `2d4f5092edfd4c54a9898a1a7dda5dd1` | Compact Tile Package | 134.0 MB | hillshade (Map Service `cab8824e…`) |
| `eb613927529347989755b0fcf9e9c8fa` | Scene Package | 9.6 MB | 3D buildings (Scene Service `5082b5bd…`) |
| `7a520038be1b4e55accdfe6bed3a0a71` | Compact Tile Package | 228.1 MB | terrain (Image Service `ce1680a5…`) |
| **All eight** | | **447.0 MB** | |

## What deleting each would do (Esri's documentation, read October 23)
- **The hosted layers would keep working.** Each hosted layer has its own copy of the data (their own sizes, 464 MB in
  all, are billed separately), and Esri's publishing pages for vector tile, tile and scene layers each say the package
  can be deleted once the layer works, "only if you are certain you no longer need" it. The elevation layer's page says
  nothing either way; it was published from a tile package in the same way as the hillshade.
- **The file geodatabase is the exception.** Esri's *Overwrite hosted feature layers* page lists "deleted the associated
  source file" among the reasons the overwrite option is unavailable. Overwriting (replacing all the buildings and zones
  with a corrected `features.gdb` of the same name and schema, keeping the item ID, URL, styling and pop-ups) is the
  natural way to publish a corrected version, for example after the SUSPECT review or a height fix. Delete this item and
  a correction means a new layer with a new ID, and every web map and app would have to be repointed.
- For the tile, vector tile, scene and elevation layers, Esri's pages do not say whether a later update needs the
  package item; a corrected product would be republished from a new package in any case. Every package is also on the
  SSD (`runs\` folders listed in `hosting/upload/README.md`), with its SHA-256 in `hosting-uploads\uploads.json`.
- A deleted item goes to the organisation's recycle bin for 14 days before it is removed for good (Esri, *Delete
  items*); an item with delete protection cannot be deleted until the protection is turned off.

## Cost of keeping them
Esri bills file, tile and package storage at 1.2 credits per GB per month (Esri's credits page, read October 22, as in
the tiles README). 447 MB is about **0.54 credits a month, 6.4 a year**. The two `.tpkx` are 81% of it (0.43 credits a
month); the file geodatabase is under 0.01. For comparison, the eight hosted layers are about 464 MB: the tile layers at the
same storage rate (that the elevation layer is billed so is not confirmed), the feature layer (21.5 MB) at the
feature-storage rate, about 5 credits a month.

## Recommendation
1. **Keep all eight**, in the new folder, **private**. The whole cost is about 6 credits a year, and they are the only
   copies online of exactly what was published. Never share them: a shared package can be downloaded whole.
2. **Turn on delete protection** for the eight packages and the eight hosted layers, so a clean-up of the folder cannot
   remove them by mistake. Not done here (only the move was approved). In ArcGIS Online: item page > Settings >
   *Delete protection*; or from the repo with ArcGIS Pro's Python:
   ```
   from arcgis.gis import GIS
   gis = GIS("pro")
   for i in ["ee182c9a7eec4994b7e19d2be8dd27b5", "bec13573a71c4df2b4642fda4a559021", "377dd1de82204e63addb6905a9322bb3",
             "2dcae544e70c47589f8226dc0ad74351", "d3ca707cda6544dd9962390c1e7e00db", "2d4f5092edfd4c54a9898a1a7dda5dd1",
             "eb613927529347989755b0fcf9e9c8fa", "7a520038be1b4e55accdfe6bed3a0a71"]:
       print(i, gis.content.get(i).protect(enable=True))
   ```
3. If storage ever matters, the two `.tpkx` (362 MB, 0.43 credits a month) are the ones worth deleting, since the SSD
   holds them; **never the file geodatabase** while the feature layer may need overwriting.
