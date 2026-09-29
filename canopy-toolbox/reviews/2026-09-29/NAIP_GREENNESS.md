# NAIP greenness review screen

The last slice computes `(NIR - red) / (NIR + red)` from verified four-band NAIP.
Unsigned imagery is converted to floating point before subtraction; zero sums,
NoData and invalid values remain unknown. The default NDVI threshold 0.3 is an
exploratory review setting, not a calibrated tree/roof classifier. Output is a
bounded review raster and provenance JSON; no LAS classes, candidates or
independent reference labels are modified.

```powershell
python reviews/2026-09-29/naip_review.py FOUR_BAND.tif METADATA.json NEW_OUTPUT --threshold 0.3
```

Metadata must declare source=NAIP, survey_date, verified RGB/NIR band mapping
`{"red":1,"green":2,"blue":3,"nir":4}`, and an image SHA-256 fingerprint produced
by `canopy.run_safeguards.fingerprint`. The script rejects changed images, RGB
previews, unverified band layouts, non-metre/nonsquare grids, more than 4 million
pixels, invalid thresholds and existing output directories. It preserves input
NoData and records the exact threshold and source date.

[The USGS NAIP service](https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer)
reports four bands: red/green/blue and near-infrared, with a raw `None` raster
function. A NaturalColor JPEG or NDVI_Color RGB preview is unsuitable for numeric
NDVI. Fetch an unrendered TIFF with bandIds=0,1,2,3 and lockRasterIds from the
catalog; preserve the primary scene IDs, dates, CRS, export extent, resampling
and service URL in metadata. USGS service defaults may mix dates and overviews.
[USGS's archive description](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-aerial-photography-national-agriculture-imagery-program-naip)
also distinguishes natural-colour from four-band imagery.

## Actual pilot evidence

A new 250 m patch at 428250, 4504250, 428500, 4504500 completed in
`scratch/naip-review-20260929`. It locked primary scene IDs 198399 and 198401,
both catalogued as four-band 2021 imagery with acquisition_date **2021-11-13**.
That is the service-reported date; verify local capture-date metadata before
interpreting seasonal differences. The exported TIFF is 500 × 500 pixels,
0.5 m projected cells (resampled from source imagery), with all four raw bands.
The NDVI review found 230,025 low-greenness pixels, 19,975 pixels with spectral
support, and no unknown pixels at threshold 0.3. These are image-pixel screens,
not tree counts or accuracy statistics. The input image hash remained unchanged.

The 2021 image predates the 2023 lidar by two years. Changes, leaf-off/seasonal
colour, shadows, non-green trees, lawns, positional error and roof lean can all
break a pointwise interpretation. Inspect neighbourhoods and registered
cross-sections; do not automatically veto low-NDVI vegetation or promote high
NDVI to truth. Independent labels and holdout policy remain mandatory before
selecting a production threshold.

Synthetic tests verify unsigned arithmetic, NoData, band count, immutable input
and output refusal. The real NAIP pilot verifies the four-band raster path in the
unchanged current Pro environment; it performs no model inference.
