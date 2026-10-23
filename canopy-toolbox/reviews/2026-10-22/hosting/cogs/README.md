# Cloud-optimised GeoTIFF masters and a float COG web trial (October 22, 2026)

Steps 1 and 6 of the hosting plan (`hosting/PLAN.md`, written by the main session): cloud-optimised GeoTIFF (COG) masters
of the 0.5 m lidar rasters, ready for a cloud bucket, and a trial of one float COG in an ArcGIS Maps SDK for JavaScript
page. **Nothing has been uploaded.** The masters are on the SSD, checked, and wait for Brian's choice of bucket (plan
decision 1). **Unvalidated planning estimates, not surveyed or field-verified data**; the warning is written into every
COG's metadata (`WARNING` and `MEANING` items).

Output: `<SSD>\lidar\2023-salt-lake-valley\runs\cog-20261022` (16 COGs, `build.json`, `verify.json`, `compare.json`,
`cog-run.json`, logs; the compression trial copies in `trials\`). Copies of the JSON records are in [run/](run/).

## The masters
16 files, 4.02 GB in all (the sources take 8.81 GB, mostly uncompressed terrain rasters). Sizes in MB; "x" is the ratio
to uncompressed (float32 or 8-bit) cells; every row passed every check below.

| COG | Type | Resampling | Source | COG | Full res. | Overviews | x |
|---|---|---|---:|---:|---:|---:|---:|
| chm_m | float | AVERAGE | 140.4 | 240.6 | 141.2 | 99.4 | 5.0 |
| terrain_m | float | AVERAGE | 1,208.3 | 260.9 | 188.8 | 72.0 | 4.6 |
| roof_elevation_m | float | AVERAGE | 41.7 | 78.9 | 50.1 | 28.8 | 15.2 |
| roof_height_m | float | AVERAGE | 63.8 | 98.4 | 58.5 | 39.8 | 12.2 |
| observed | 8-bit | NEAREST | 1.7 | 2.4 | 1.7 | 0.7 | 127 |
| vegetation_support | 8-bit | NEAREST | 8.5 | 12.9 | 8.6 | 4.3 | 23 |
| building_occlusion | 8-bit | NEAREST | 1.1 | 1.6 | 1.1 | 0.5 | 193 |
| building_sources | 8-bit | NEAREST | 5.1 | 8.1 | 5.2 | 2.8 | 37 |
| slope_degrees | float | AVERAGE | 1,208.6 | 549.7 | 406.7 | 142.9 | 2.2 |
| slope_percent | float | AVERAGE | 1,208.6 | 550.1 | 407.2 | 142.9 | 2.2 |
| aspect_degrees | float | NEAREST | 1,208.6 | 505.8 | 371.0 | 134.8 | 2.4 |
| profile_curvature | float | AVERAGE | 1,208.6 | 615.3 | 455.9 | 159.4 | 2.0 |
| tangential_curvature | float | AVERAGE | 1,208.6 | 616.9 | 457.0 | 159.9 | 2.0 |
| terrain_position_m | float | AVERAGE | 1,208.6 | 385.3 | 231.3 | 154.0 | 3.1 |
| hillshade | 8-bit | AVERAGE | 85.1 | 87.5 | 62.0 | 25.5 | 3.4 |
| terrain_neighborhood_complete | 8-bit | NEAREST | 4.8 | 0.7 | 0.5 | 0.2 | 400 |

Meanings are in [PRODUCTS.md](../../PRODUCTS.md) and the [terrain README](../../terrain-city/README.md); each COG also
carries its meaning in a `MEANING` metadata item. All are EPSG:6341 (NAD83(2011) / UTM 12N), 0.5 m, 24,501 x 12,247
cells, the city only with NoData outside; classic (not Big) TIFF; 512 x 512 tiles; six overviews down to 382 x 191.

How they are encoded ([cogs.py](cogs.py) `build`, GDAL 3.12.2e in ArcGIS Pro's Python):
- **Lossless.** Floats DEFLATE with the floating-point predictor (3); hillshade DEFLATE with the horizontal predictor (2);
  masks and classes DEFLATE without a predictor. Every overview uses the same codec and predictor (checked in the files'
  own tags, below).
- **Overviews rebuilt**, not copied: the terrain rasters carry ArcGIS `.ovr` pyramids, which the COG driver would otherwise
  reuse (`OVERVIEWS=IGNORE_EXISTING`). NEAREST for `aspect_degrees`, `observed`, `vegetation_support`,
  `building_occlusion`, `building_sources` and `terrain_neighborhood_complete` (averaging angles or classes makes values
  that mean nothing: the average of 350 and 10 degrees is not 180); AVERAGE for the continuous rasters, hillshade
  included. NoData cells are left out of averages.
- **EPSG:6341 written as a code** (ProjectedCSTypeGeoKey = 6341). The ArcGIS Maps SDK reads COGs only with an EPSG code or
  Esri WKT. The script checks that each source's CRS is the same as EPSG:6341 before assigning it, so no cell moves.
- **One file per raster.** No `.aux.xml` sidecars are read or written (`GDAL_PAM_ENABLED=NO`). The two ArcGIS value
  attribute tables (`hillshade`, `terrain_neighborhood_complete`) hold only VALUE and COUNT and are not carried.
- Sizes: the terrain floats are 2 to 5 times smaller than uncompressed float32; slope and curvature, which vary from cell
  to cell, compress least. `chm_m`, the roof rasters and the masks come out *larger* than their library files, which are
  already compressed and have no overviews: the overviews add 40 to 70% (averages of noisy floats barely compress), and at
  full resolution the floating-point predictor gains nothing on these mostly-empty rasters (`chm_m`: 141.2 MB with it,
  142.3 MB without).

### How they were checked ([cogs.py](cogs.py) `verify`; `run/verify.json`)
Every master passed every check:
- **COG layout:** GDAL's `validate_cloud_optimized_geotiff` with `full_check=True`: no errors, no warnings (IFDs at the
  start, tiles in order, overviews before the full-resolution data).
- **Every cell equals its source**, NoData included: each raster read in 512-row strips from source and COG and compared
  byte for byte, so every float bit pattern counts. Size, geotransform, data type, NoData value and CRS also equal.
  The counts agree with the library: `chm_m` has a value on 133,058,292 cells (the observed city cells in
  [PRODUCTS.md](../../PRODUCTS.md)), `terrain_m` and the terrain products on all 133,813,488 city cells, and
  `terrain_neighborhood_complete` is 0 on exactly the 650 cells the [terrain README](../../terrain-city/README.md) lists.
- **Overviews:** on a 1,024 x 1,024 window of overview level 1 at the centre of the grid, every NEAREST overview value is one
  of the source cells it covers, and every AVERAGE value lies within the range of the valid cells it covers, with NoData
  only where all of them are NoData. (The grid is odd-sized, so an overview cell covers 1.9998 source cells; the check uses
  each cell's true footprint.) The check catches the wrong method: run on `building_occlusion` as if it were AVERAGE, or on
  `chm_m` as if it were NEAREST, it fails.
- **Every image directory** is DEFLATE with the intended predictor, read from the TIFF tags.
- **Sources:** the eight library rasters' SHA-256 equal `library.json`'s; every source's and master's SHA-256 is in
  `build.json`.

## Compression trial ([cogs.py](cogs.py) `compare`; `run/compare.json`)
Three floats rebuilt four ways, everything else as the masters. LERC's stated error is `MAX_Z_ERROR=0.01` in the
raster's units (0.01 m for terrain and CHM, 0.01 percentage points for slope), at full resolution and in the overviews.
Sizes in MB; read times are GDAL decoding from the OS file cache (best of 3; the laptop was running other work, and
single timings varied by 2x), so they compare codecs, not disks or networks.

| Raster | Encoding | COG | Full res. | Overviews | x | Read all (s) | ms per 512 tile | Exact? |
|---|---|---:|---:|---:|---:|---:|---:|---|
| slope_percent | **DEFLATE, predictor 3 (master)** | 550.1 | 407.2 | 142.9 | 2.2 | 4.3 | 3.5 | yes |
| | DEFLATE, no predictor | 637.7 | 477.7 | 160.0 | 1.9 | 3.9 | 2.5 | yes |
| | ZSTD, predictor 3 | 542.7 | 401.7 | 141.0 | 2.2 | 1.9 | 1.4 | yes |
| | LERC 0.01 | 219.2 | 158.6 | 60.5 | 5.5 | 1.9 | 1.2 | max error 0.01001 |
| terrain_m | **DEFLATE, predictor 3 (master)** | 260.9 | 188.8 | 72.0 | 4.6 | 2.9 | 2.0 | yes |
| | DEFLATE, no predictor | 473.8 | 347.5 | 126.3 | 2.5 | 3.3 | 2.3 | yes |
| | ZSTD, predictor 3 | 249.8 | 180.7 | 69.1 | 4.8 | 1.9 | 1.3 | yes |
| | LERC 0.01 | 134.0 | 93.5 | 40.5 | 9.0 | 1.8 | 1.2 | max error 0.01001 |
| chm_m | **DEFLATE, predictor 3 (master)** | 240.6 | 141.2 | 99.4 | 5.0 | 2.7 | 1.8 | yes |
| | DEFLATE, no predictor | 229.9 | 142.3 | 87.6 | 5.2 | 2.3 | 1.5 | yes |
| | ZSTD, predictor 3 | 231.2 | 134.8 | 96.4 | 5.2 | 1.7 | 1.2 | yes |
| | LERC 0.01 | 185.6 | 141.9 | 43.7 | 6.5 | 1.7 | 1.1 | max error 0.01000 |

"Exact" was checked on every cell: the DEFLATE and ZSTD copies equal the master; the LERC copies keep NoData on exactly
the same cells, and the largest difference on a valid cell is 0.0100098 (the 0.01 bound plus float32 rounding at values
near 1,300 m or 800%).

**Recommendation: keep DEFLATE with the floating-point predictor for the masters, and upload those.**
- ZSTD is the same size (1 to 4% smaller) and decodes about twice as fast in GDAL, but the ArcGIS Maps SDK cannot read it
  (below), so it would cut off the web clients the bucket is for.
- LERC 0.01 is 2.5 times smaller than the master for slope and twice for terrain, decodes fastest, and the SDK reads it.
  It is lossy, so it is not a master. It is a good *display copy* for a public slope or terrain viewer: the web trial
  fetched full-resolution slope tiles of up to about 0.8 MB from the DEFLATE master on steep ground, and LERC would cut
  them by about 2.5 times. Classes only change for cells within 0.01 of a break. It saves little on the CHM (23%), whose size is
  mostly overviews and empty tiles.
- The floating-point predictor is worth keeping: it saves 14% on slope and 45% on terrain, and costs 5% on the CHM (in
  its overviews).

Two GDAL behaviours found on the way (ArcGIS Pro's GDAL 3.12.2e), both handled in the script:
- With `COMPRESS=LERC` or `ZSTD`, the COG driver wrote DEFLATE overviews. The `OVERVIEW_COMPRESS` creation option was
  ignored once `NUM_THREADS` and the other options were set, and the config option `COMPRESS_OVERVIEW` was honoured. The
  `compare` step now refuses any file whose overview tags don't match the codec it asked for. The masters are DEFLATE
  throughout, so they were not affected.
- The build writes an ESRI PE string beside the EPSG key and then reads the CRS back without its code; a raster written
  from these files without `outputSRS="EPSG:6341"` gets a user-defined CRS (key 32767). The checks read the key from the
  file itself.

## Web trial: slope percent in the ArcGIS Maps SDK ([web/](web/))
**It works.** An `ImageryTileLayer` pointed at the `slope_percent` COG URL draws it, returns the true float value at a
click, and draws a class renderer correctly once interpolation is set to nearest. Results: [web/trial-results.json](web/trial-results.json).

Setup:
- The SDK's documentation (5.1, checked October 22) still calls COG support **beta** and lists NONE, JPEG, DEFLATE, LZW and
  LERC compression, not ZSTD, and requires an EPSG code or Esri WKT. The page loads `https://js.arcgis.com/5.1/`, which
  is pinned to the 5.1 line; the build it loaded reports itself as **5.1.27** (2026-10-07). js.arcgis.com does not offer
  a patch-level URL, so a later 5.1 patch would load without the page changing; the page shows the version it got.
- [web/serve.py](web/serve.py) serves the page on `127.0.0.1:8791` and the COG folder on `127.0.0.1:8792`, so every COG
  read is cross-origin, as from a bucket. It answers single byte ranges (206 with `Content-Range`, 416 out of range),
  answers the CORS preflight, and logs each request with the bytes sent. Checked with curl before the browser.
  (Port 8765 was already taken by another process; Python's `http.server` would have shared it silently on Windows, so
  the script refuses a port that is in use.)
- [web/make_points.py](web/make_points.py) picks 19 check points ([web/points.json](web/points.json)), cell centres with
  their value read by GDAL from the *source* raster: two random cells in each class (under 10, 10-15, 15-20, 20-25,
  25-30, 30% and over), the cell nearest each break (10.000001, 14.999999, 19.999998, 25.000004 and 30.000002%), and two
  NoData cells outside the city.
- With `?check=1` the page identifies each point twice: as an EPSG:6341 point, and projected to the view's Web Mercator
  as a click would be. It then zooms to the cell (about 30 screen pixels per cell) and reads the colour drawn at the
  screen centre, checking that the centre is that cell.
- The browser pane in the Claude app runs the page, but while the pane is hidden Chromium throttles it: one load waited
  68 seconds before its first COG request. The recorded runs used Playwright's Chromium.

Results (SDK 5.1.27, Web Mercator basemap unless noted):

| COG | Draws | Identify (19 points) | Class colour (19 cells) | First draw |
|---|---|---|---|---|
| slope_percent master (DEFLATE, predictor 3) | yes | **19 exact** | **19** with `interpolation: "nearest"` | 5.0-6.1 s |
| the same, the layer's default bilinear interpolation | yes | 19 exact | 14 | 5.0 s |
| the same in an EPSG:6341 view, no basemap | yes | 19 exact | inconclusive (below) | 3.0 s |
| DEFLATE without predictor (trial copy) | yes | 19 exact | 19 | 5.0 s |
| LERC 0.01 (trial copy) | yes | 19 within 0.0095 | 17: the two cells within 0.000004 of a break move across it | 5.0 s |
| ZSTD (trial copy) | **no**: "this tiff is not supported: unsupported tag compression 50000" | | | |

- **Values are exact.** Identify returns the float32 cell value bit for bit, the same through a Web Mercator point as
  through a 6341 point, and nothing for NoData cells. A real mouse click on the map (cell 22524, 5591) returned
  1.4267847537994385, GDAL's value for that cell, in 5 ms. The floating-point predictor is not a problem for the reader.
- **Set `interpolation: "nearest"` for classes.** The layer resamples bilinearly by default, which blends neighbouring
  cells before classing them; 5 of 19 cells drew in another class (2 random cells on steep ground, 3 of the 5 cells at a
  break). With
  nearest, all 19 drew in their class, including the five cells within 0.000004 of a break, so the renderer classes the
  true float values and does not bin them.
- **NoData** draws transparent and identifies as no value, although `serviceRasterInfo.noDataValue` reports `null`.
  The SDK also asks for `slope_percent.tif.aux.xml` (404 here; harmless). A sidecar with statistics would give the default
  stretch renderer sensible limits, but is not needed for a class renderer.
- **Reprojection:** the layer's CRS is 6341 and the view's Web Mercator (102100); the SDK projects the tiles in the
  browser, and at 30 pixels per cell each check cell was drawn under its own centre, so the projection is accurate to well
  within a cell. In a 6341 view with no basemap the zoom stops at the layer's finest level, one screen pixel per cell, so
  the screen-centre colour check is inconclusive there: an earlier, unrecorded run passed 19 of 19, and the recorded run
  found the centre pixel on the diagonal neighbour of every cell, with a different window size. Identify was exact in both. Loosening the view's zoom
  limits in that view moved the drawn centre 32 cells off the view centre, so the page leaves them alone.
- **Load:** reading the layer's metadata takes about 0.3 s (one 1 MiB range request for the header and tile index). The
  first full-city draw needs 1.17 MB in all, the 1 MiB header and one 120 KB overview tile (plus the `.aux.xml` probe), and
  appears 5 to 6 seconds after the page starts, most of it SDK and basemap start-up. Zoomed in on steep ground,
  full-resolution tiles were up to about 0.8 MB each. These are local reads. From a bucket each request adds a network
  round trip, and the bytes are the figure to watch: the 4 GB in the bucket is only read a tile at a time.

What the trial does not show: behaviour over a real network and CDN, other browsers, mobile devices, and ArcGIS Online
itself. A COG URL item in ArcGIS Online, or a hosted imagery layer, is a different path; plan decision 2 covers it.

## Is a Web Mercator copy needed?
**No, not for these masters.** The ArcGIS Maps SDK draws the EPSG:6341 COG on a Web Mercator basemap and projects it in
the browser (above). ArcGIS Pro, QGIS and GDAL read EPSG:6341 directly. A Web Mercator copy is needed only for a client
that cannot reproject rasters, such as a viewer that wants ready-made XYZ or WMTS tiles, and that is step 5's job: the
hillshade tile package uses the Web Mercator tiling scheme. A COG in Web Mercator (GDAL's
`TILING_SCHEME=GoogleMapsCompatible`) would resample every cell onto a new grid, so it should never replace the 0.5 m
masters, which keep the lidar grid exactly.

## Display copies (October 23)
Brian approved LERC display copies for the click-anywhere web viewer on October 23, as the compression trial recommended.
The masters stay lossless DEFLATE and remain the files to use for analysis. Output:
`<SSD>\lidar\2023-salt-lake-valley\runs\cog-display-20261023` ([cogs.py](cogs.py) `display`; `run/display.json`).

| Display copy | MB | Master MB | Share | Full res. | Overviews | Largest difference from the master |
|---|---:|---:|---:|---:|---:|---:|
| slope_percent.lerc-0.01.tif | 219.2 | 550.1 | 40% | 158.6 | 60.5 | 0.0100098% |
| slope_degrees.lerc-0.01.tif | 199.8 | 549.7 | 36% | 144.1 | 55.7 | 0.0100021 degrees |
| terrain_m.lerc-0.01.tif | 134.0 | 260.9 | 51% | 93.5 | 40.5 | 0.0100098 m |

553 MB in all, against 1,361 MB for the three masters. Each copy is built from the source like the master (same 512
tiles, AVERAGE overviews, EPSG:6341 key, `WARNING` and `MEANING` metadata), with `COMPRESS=LERC`,
`MAX_Z_ERROR=0.01` and, through the `COMPRESS_OVERVIEW` config option, LERC overviews with the same error. A `NOTE`
metadata item says it is a display copy and names the master folder.

Checked for each copy (all passed; building and checking the three took under 2 minutes):
- **COG layout:** `validate_cloud_optimized_geotiff` with `full_check=True`, no errors or warnings; classic TIFF.
- **Codec:** every image directory, full resolution and all six overviews, is LERC (from the TIFF tags).
- **Against the master**, at full resolution and at each of the six overview levels separately, read in strips: NoData on
  exactly the master's cells, and every valid cell within 0.0101 of the master's value. The largest differences are in
  the table: 0.01 plus float32 rounding, as in the October 22 trial. Size, geotransform, data type, NoData value,
  overview sizes and the EPSG:6341 key also match.
- **In the web page** ([web/display-trial-results.json](web/display-trial-results.json)): the trial page, served from the
  display folder on another port, read `slope_percent.lerc-0.01.tif` with SDK 5.1.27. Identify was within 0.0095 of
  GDAL's source value at all 19 check points, through EPSG:6341 points and Web Mercator points alike, and NoData
  identified as empty. 17 of 19 cells drew in their class. The other two are the cells at 19.999998% and 25.000004%:
  LERC moved them to 20.0089% and 24.9959%, across the break, so a class edge in the viewer can sit up to one cell
  differently from the master's. A first draw needed 3 requests and 1.14 MB. The checked run was slow, an 82 s first draw
  while the laptop was busy; a reload a few minutes later loaded in 0.23 s and drew in 6.0 s, as on October 22.

Not made: `aspect_degrees`, because its flat cells hold exactly -1, which LERC could turn into values like -0.995 that
no longer match a `-1` test, and because 0 and 360 degrees meet. The CHM, because LERC saves only 23% on it (trial
above). If the viewer shows aspect, it should read the lossless master.

Uploading the copies, once Brian approves that upload (Azure, the account's chosen container; a separate prefix keeps them
apart from the masters):

```bash
azcopy copy "H:/lidar/2023-salt-lake-valley/runs/cog-display-20261023/*.tif" "https://ACCOUNT.blob.core.windows.net/CONTAINER/millcreek-lidar/display-20261023/?SAS_TOKEN" --content-type image/tiff --cache-control "public, max-age=604800"
```

The checks after upload (below) apply unchanged, with `slope_percent.lerc-0.01.tif` and
`Content-Range: bytes 0-1023/219208429`; `run/display.json` has each copy's size and SHA-256.

## Uploading, once Brian picks a bucket
Not run: nothing goes up without Brian's go-ahead for that upload. None of these command-line tools is installed on the
laptop yet (AWS CLI v2 for S3 and R2, AzCopy and the Azure CLI for Azure). Each recipe uploads only the 16 masters (not
`trials\`), under a dated prefix so a later rebuild never overwrites these in place, then sets CORS so a web page on
another origin can make range requests. Replace the capitalised placeholders. Whether the bucket is public (anyone with
the URL can read the rasters) or private (signed URLs, or a CDN in front) is decision 1 in the plan.

The CORS rule all three need: GET and HEAD from the web map's origin (`*` while trialling; the city's web origin later),
the `Range` request header allowed, and `Content-Range`, `Accept-Ranges`, `Content-Length` and `ETag` exposed. The
local server ([web/serve.py](web/serve.py)) sends exactly these, and the trial worked with them.

**Cloudflare R2** (S3-compatible API; R2 does not charge for downloads). Make an R2 API token with write access to the
bucket, then `aws configure --profile r2` with its key pair and region `auto`. Save the CORS rule as `cors.json`:

```json
{"CORSRules": [{"AllowedOrigins": ["*"], "AllowedMethods": ["GET", "HEAD"],
  "AllowedHeaders": ["Range", "If-None-Match", "If-Modified-Since"],
  "ExposeHeaders": ["Content-Range", "Accept-Ranges", "Content-Length", "ETag"], "MaxAgeSeconds": 3600}]}
```

```bash
aws s3 cp H:/lidar/2023-salt-lake-valley/runs/cog-20261022/ s3://BUCKET/millcreek-lidar/20261022/ --recursive --exclude "*" --include "*.tif" --exclude "trials/*" --content-type image/tiff --cache-control "public, max-age=604800" --profile r2 --endpoint-url https://ACCOUNT_ID.r2.cloudflarestorage.com
```

```bash
aws s3api put-bucket-cors --bucket BUCKET --cors-configuration file://cors.json --profile r2 --endpoint-url https://ACCOUNT_ID.r2.cloudflarestorage.com
```

Public reads need a custom domain on the bucket (the `r2.dev` address is rate-limited and meant for development). If the
upload fails with a checksum error (recent AWS CLI versions send checksums that some S3-compatible services have
rejected), set `AWS_REQUEST_CHECKSUM_CALCULATION=when_required` and rerun.

**Amazon S3.** `aws configure` with a key that can write the bucket; the same `cors.json`.

```bash
aws s3 cp H:/lidar/2023-salt-lake-valley/runs/cog-20261022/ s3://BUCKET/millcreek-lidar/20261022/ --recursive --exclude "*" --include "*.tif" --exclude "trials/*" --content-type image/tiff --cache-control "public, max-age=604800"
```

```bash
aws s3api put-bucket-cors --bucket BUCKET --cors-configuration file://cors.json
```

Public reads need Block Public Access relaxed for the bucket and a bucket policy allowing `s3:GetObject` on
`millcreek-lidar/*`, or CloudFront in front of a private bucket.

**Azure Blob Storage.** AzCopy with a SAS token for the container (write and create), and the Azure CLI signed in
(`az login`) for CORS, which is set per storage account. The source wildcard without `--recursive` takes only the top
folder, so `trials\` stays behind.

```bash
azcopy copy "H:/lidar/2023-salt-lake-valley/runs/cog-20261022/*.tif" "https://ACCOUNT.blob.core.windows.net/CONTAINER/millcreek-lidar/20261022/?SAS_TOKEN" --content-type image/tiff --cache-control "public, max-age=604800"
```

```bash
az storage cors add --account-name ACCOUNT --services b --methods GET HEAD OPTIONS --origins "*" --allowed-headers Range If-None-Match If-Modified-Since --exposed-headers Content-Range Accept-Ranges Content-Length ETag --max-age 3600
```

Public reads need the container's anonymous access level set to Blob (and anonymous access allowed on the account), or
SAS URLs.

**After any upload, check before using it** (BASE is the public URL of the prefix):

```bash
curl -s -D - -o /dev/null -r 0-1023 -H "Origin: https://example.com" BASE/slope_percent.tif
```

expects `206 Partial Content`, `Content-Range: bytes 0-1023/550143658` and `Access-Control-Allow-Origin`. Then GDAL reads
it in place, and the trial page reads it with `?data=BASE/`:

```bash
"C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" -m osgeo_utils.samples.validate_cloud_optimized_geotiff --full-check=yes /vsicurl/BASE/slope_percent.tif
```

The uploaded files' sizes and SHA-256 can be compared with `run/cog-run.json`.

## Files
- [cogs.py](cogs.py): `build`, `verify`, `compare`, `summary`, and `display` for the October 23 display copies (ArcGIS
  Pro Python; `CANOPY_LIDAR_ROOT=H:\lidar`, `PYTHONNOUSERSITE=1`). On October 22 the build took 6 minutes, verify 4 and
  compare 5.
- [web/](web/): `index.html` and `trial.js` (the trial page), `serve.py` (the range and CORS server), `make_points.py`
  and `points.json` (the check points), `trial-results.json` and `display-trial-results.json` (what the page reported).
- [run/](run/): copies of `build.json`, `verify.json`, `compare.json`, `cog-run.json` and `display.json`.

To open the trial page, start the servers (they stop when the terminal closes) and open http://127.0.0.1:8791/ ; add
`?check=1` to run the point checks, `file=trials/slope_percent.lerc-0.01.tif&tol=0.0101` for the LERC copy, or
`data=BASE/` for an uploaded copy:

```bash
"C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" canopy-toolbox/reviews/2026-10-22/hosting/cogs/web/serve.py H:/lidar/2023-salt-lake-valley/runs/cog-20261022
```

For the display copies, serve their folder on other ports (`serve.py H:/lidar/2023-salt-lake-valley/runs/cog-display-20261023
--page-port 8793 --data-port 8794`) and open
`http://127.0.0.1:8791/?check=1&tol=0.0101&data=http://127.0.0.1:8794/&file=slope_percent.lerc-0.01.tif`.

Rerun:

```bash
"C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe" canopy-toolbox/reviews/2026-10-22/hosting/cogs/cogs.py build H:/lidar/2023-salt-lake-valley/runs/cog-20261022
```

then `verify`, `compare` and `summary` on the same folder.
