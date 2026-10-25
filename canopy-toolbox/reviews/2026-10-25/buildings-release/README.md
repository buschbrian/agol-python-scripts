# Three-way building hybrid released October 25, 2026

Brian chose the three-way hybrid, preferring roofer LoD2.2 detail despite smoother edges on some Esri LOD2.0 models. He explicitly approved **Public ArcGIS layer and Azure download** on October 25, superseding the earlier staff-only roof-form decision. The validated v2 geometry was released unchanged; no additional smoothing was applied.

## Released items

| Item | ID / location | Access |
|---|---|---|
| New scene layer | `ce3617ac9b884bbcbee7c47a3e166999` | Public, delete-protected |
| New source SLPK | `07919e2df15647ba91ba23a0fd417083` | Private, delete-protected |
| Existing buildings scene | `5b5bdf4a63c9466fad5884039aa7357f` | Public, now references the new layer |
| Existing Buildings in 3D app | `021866adf7ab40fea430d4d10fc3a934` | Updated description/splash; remains private |
| Prior LOD1.2 layer | `5082b5bd063a4a03847f2082dc3533d1` | Retained public and delete-protected |
| Prior source SLPK | `eb613927529347989755b0fcf9e9c8fa` | Retained; no deletion or sharing change |
| Azure blob | `cogs/millcreek-lidar/buildings/20261025/buildings_hybrid_v2.slpk` in `stmillcreeklidar` | Public download |

[Public scene](https://www.arcgis.com/home/webscene/viewer.html?webscene=5b5bdf4a63c9466fad5884039aa7357f) · [New layer and data dictionary](https://www.arcgis.com/home/item.html?id=ce3617ac9b884bbcbee7c47a3e166999) · [Azure SLPK download](https://stmillcreeklidar.blob.core.windows.net/cogs/millcreek-lidar/buildings/20261025/buildings_hybrid_v2.slpk)

The new layer is public before the scene is repointed. The scene keeps its original layer node ID, camera, slides, terrain and other layers. Pop-ups use only fields present in the new package, including LEVEL and modelled roof measurements. The old service is still available to any other consumers; its item ID was not overwritten. Source package items remain private because Azure supplies the public download. No app sharing was expanded.

## Verification

- SLPK: **21,228,379 bytes**, SHA-256 **62674f95c4e7a292c4ce66e8c2b55aac9d60c360e2ea50e3e7bde5521495949f**.
- Hosted model counts: **20,730 roofer LoD2.2; 647 Esri LOD2.0; 184 Esri LOD1.2** (21,561 total).
- Hosted FP_ID count/sum: 21,561 / 237,493,394, matching the validated package/source.
- All 45 hosted fields match the data dictionary; every pop-up field and expression refers to an existing field.
- Six hosted roof-area counts/totals match the local package. Roof metrics cover only the 20,730 retained roofer buildings; all 831 fallback buildings have null roof metrics in the validated source.
- Public Azure HTTP 200 full download: byte count and SHA-256 match. No authentication or SAS token was used to verify the download.
- Anonymous ArcGIS reads confirm the public scene, new and prior services, schema and model/roof statistics. Item metadata and scene/app JSON read back equal to the prepared release plan.
- Signed-out Scene Viewer draws the hybrid on the city terrain. At the Canyon Rim slide, building FP_ID 10476 displays roofer LoD2.2, median height 5.0 m, roof area 193.6 m², roof slopes and the estimate warning. No console warnings/errors were recorded during this check. The private Instant App received API configuration/readback checks; it was not tested in a signed-in browser.
- Package and new layer delete protection verified. Prior items retained.
- Repository suite: **512 tests run, 88 ArcPy-dependent skips, 424 passed**. Separate ArcGIS Pro package validation previously passed without warnings and remains applicable because the SLPK bytes did not change.

Evidence is under `evidence/`. The first share check encountered precompressed I3S JSON; the verifier was corrected to decompress gzip. The original public scene was untouched until that anonymous check passed. No duplicate uploads were made.

The source-lidar agreement is not independent accuracy. Assistant imagery ratings remain preliminary; the City rating file was not filled. Heights remain NAVD88 values with the package's EGM96 label documented. Planning-estimate warnings and County terms remain on the items and in pop-ups.

## Reproduce the Azure upload

The existing public `cogs` container is used. The dated object did not exist before this release. No raster was overwritten and no storage permissions or CORS rules were changed. The upload uses the signed-in Azure CLI identity, not keys or SAS credentials:

```powershell
az storage blob upload --account-name stmillcreeklidar --container-name cogs --auth-mode login --name 'millcreek-lidar/buildings/20261025/buildings_hybrid_v2.slpk' --file 'H:\lidar\2023-salt-lake-valley\runs\roofer-city-v2-20261024\v2\buildings_hybrid_v2.slpk' --overwrite false --content-type 'application/octet-stream' --content-disposition 'attachment; filename=buildings_hybrid_v2.slpk' --content-cache-control 'public, max-age=31536000, immutable' --metadata sha256=62674f95c4e7a292c4ce66e8c2b55aac9d60c360e2ea50e3e7bde5521495949f planning_estimate=true model=three_way_v2
```

For a future release choose a new dated object name; do not overwrite this immutable URL. Existing COG master and display-copy prefixes retain their prior contents.

## ArcGIS release and rollback

The initial upload used `reviews/2026-10-22/hosting/upload/upload.py buildings3d_v2 --go`; its log on H: now records the new IDs. Do not rerun that upload to update text. The canonical metadata is `reviews/2026-10-23/agol-metadata/buildings3d_v2.md`; the styling and app generators now target this release.

From this folder in ArcGIS Pro Python with `PYTHONNOUSERSITE=1`:

```powershell
python release.py prepare --audit-dir evidence
python release.py verify --audit-dir evidence
# Apply a reviewed prepared plan only with authorization:
python release.py apply --audit-dir evidence --go
# Restore the saved pre-release scene/app, retaining every package and service:
python release.py rollback --audit-dir evidence --go
```

Rollback refuses if scene/app data has changed since this release, so later manual edits are not silently overwritten. The saved `before-scene.json` and `before-app.json` contain their pre-release settings and item properties. Rollback does not remove the new public layer or Azure download and does not roll back unrelated apps. Do not delete either source package while a hosted service depends on it.
