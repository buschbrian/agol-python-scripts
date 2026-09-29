# Selected September 23 integration

Ported from `02d9977` by selected files and manually merged hunks: class-0 CHM
background policy, missing/stale LAS statistics rejection, `prepare
--building-method`, and the dated Nearmap WMS helper. The old sample and
footprint-contact QA were excluded. Today's fixed-reference sampling and
reconciliation remain authoritative.

Class 0 stays unknown by default. `run --classified-background-zero` is an
explicit declaration that **this working copy's class 0 represents model-predicted
non-canopy**. Never apply it to unclassified delivery points or partially inferred
tiles. Class 1 always remains unknown. This option changes direct-return
observation coverage, never vegetation classes or canopy interpolation, and enters
both the CHM provenance and pipeline resume signature. Refresh statistics only
on the derived copy after classification; CHM creation refuses missing/stale
statistics without refreshing source files itself.

`prepare --building-method CONSERVATIVE|STANDARD|AGGRESSIVE` defaults to STANDARD
and records the choice. Existing delivered ground/noise and source LAS remain
protected. These are Esri plane-detection tolerances, not accuracy rankings; see
[Classify LAS Building](https://pro.arcgis.com/en/pro-app/latest/tool-reference/3d-analyst/classify-las-building.htm).

The dated helper accepts a private URL file, lists exact dated WMS layers and
fetches only a layer/date pair present in capabilities:

```powershell
python nearmap_historical_wms.py --url-file PRIVATE_FILE list --year 2023
python nearmap_historical_wms.py --url-file PRIVATE_FILE fetch --layer EXACT_LAYER --date YYYY-MM-DD --output scratch/dated.tif
```

Its AOI is the documented 300 m pilot. Output sidecars carry survey date, layer,
CRS and dimensions; URLs/API keys never enter output metadata. It uses installed
ArcPy coordinate/raster tools when optional pyproj/rasterio are absent. No
environment changes or package installations are required in Pro.

ArcGIS tests verify undeclared class 0 remains unknown, declared background is
observed zero, missing statistics fail, and invalid building methods create no
output. A fresh 250 m pipeline pilot completed at `scratch/integration-port-run-20260929`.
A fresh 50 m CONSERVATIVE preparation completed at
`scratch/integration-building-method-20260929`. Neither uses deep learning.
Historical G: and USGS outputs remain distinct acquisitions/processing inputs;
counts from September 23 are not comparative accuracy evidence.
