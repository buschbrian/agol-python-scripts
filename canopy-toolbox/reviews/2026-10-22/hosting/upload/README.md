# Uploading the hosting packages to ArcGIS Online (October 23, 2026)

[upload.py](upload.py) uploads and publishes **one item per command, and only with `--go`**. Without `--go` it is a dry run:
it checks the file and prints exactly what would be sent. It has been dry-run on all eight items; **nothing has been
uploaded yet**.

```
set CANOPY_LIDAR_ROOT=H:\lidar
set PYTHONNOUSERSITE=1
set PY="C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe"
%PY% reviews\2026-10-22\hosting\upload\upload.py list
%PY% reviews\2026-10-22\hosting\upload\upload.py features
%PY% reviews\2026-10-22\hosting\upload\upload.py features --go
```

`PYTHONNOUSERSITE=1` matters: without it, Pro's Python loads the per-user pandas in `AppData\Roaming\Python\Python313`.

## What `--go` does, and does not do
- Signs in with **ArcGIS Pro's active portal** (`GIS("pro")`: have Pro open and signed in to the city's organisation), or
  with `--url https://<org>.maps.arcgis.com --username <user>` and a password prompt. No password is stored.
- Refuses if an item with the same title is already in your content (`--allow-duplicate` overrides), or if the log
  already records the item as published (`--again` overrides, for a layer you have deleted).
- Adds the file to the folder **Millcreek LiDAR 2023** (created if missing), with title, summary, description, tags,
  credits and terms of use set. Every summary and the terms of use carry the planning-estimate warning, and every
  description states the datum (ITRF08 transformation, NAVD88 heights).
- Publishes it, and logs the package and layer item IDs, URLs, file size and SHA-256 to
  `<SSD>\lidar\2023-salt-lake-valley\runs\hosting-uploads\uploads.json`. The file geodatabase is sent as a zip made there.
- **Never shares** (every item stays private to you), **never deletes** (the package item stays until you delete it) and
  **never overwrites**.

## The items, in upload order

| Item | File (on the SSD, under `runs\`) | Publishes as | Size |
|---|---|---|---:|
| `features` | `hosting-features-20261023\features.gdb` (buildings and canopy cover zones, Web Mercator) | Feature Service, two layers | 7.8 MB |
| `slope` | `slope-tiles-20261022\millcreek_slope_classes.vtpk` | Vector Tile Service | 22.7 MB |
| `contours` | `vector-tiles-20261022\millcreek_contours.vtpk` | Vector Tile Service | 6.7 MB |
| `hillshade` | `tiles-20261023\millcreek_hillshade_20261023.tpkx` | Map Service (tile layer) | 134.0 MB |
| `treetops` | `vector-tiles-20261022\millcreek_treetops.vtpk` | Vector Tile Service | 7.7 MB |
| `crowns` | `vector-tiles-20261022\millcreek_crowns.vtpk` | Vector Tile Service | 33.9 MB |
| `buildings3d` | `scene-layers-20261022\buildings_lod12.slpk` | Scene Service | 9.6 MB |
| `terrain` | `tiles-20261023\millcreek_terrain_20261023.tpkx` | Image Service (elevation layer) | 228.1 MB |

Not included: the LOD2.0 roofs (experimental), the COGs (they go to Azure Blob storage, not ArcGIS Online:
[PUBLISHING.md](../../../2026-10-23/PUBLISHING.md)), and the superseded October 22 tile packages.

## Untested until the first real run
The publish calls come from the API's own handling of each package type (ArcGIS API for Python 2.4.3), read from its
source, not from a run against the portal. Go one item at a time and look at each before the next:
- `features` (a zipped file geodatabase) and the `.vtpk` and `.slpk` items use the API's default publish for their type.
- The `.tpkx` items are published with `build_initial_cache=True`, which unpacks the package's own tiles (the cache already
  exists, so Esri's page expects no tile-generation credits). The script prints the type it got and warns if it differs
  from the table. The **terrain** should come out as an Image Service, which is how ArcGIS Online stores an elevation
  layer. If it does not, stop and check the item before adding it to a scene.

## After each upload
1. Open the item page the script prints and check the layer draws: in Map Viewer for the 2D layers, in Scene Viewer for
   `buildings3d` and `terrain` (terrain in the scene's Ground, above World Elevation). The README of each product says what
   to look for. Since every package carries the same datum, the buildings should stand on the terrain and the treetops
   should sit on the hillshade's trees.
2. Delete the package item (the ID the script prints) once the layer works, so its storage is not counted twice.
3. Share only once the audience is decided ([PUBLISHING.md](../../../2026-10-23/PUBLISHING.md), Applications).
