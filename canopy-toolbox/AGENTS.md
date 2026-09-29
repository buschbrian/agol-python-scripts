# Canopy toolbox development

ArcGIS Pro Python toolbox and CLI: copied/classified lidar to canopy estimates.
Read README.md and reviews/2026-09-17/IMPLEMENTATION.md for current limits.

## Routing

- Grid, bands, ownership: canopy/bands.py, canopy/tiling.py and pure tests.
- LAS inventory/classification: canopy/preparation.py; source files are immutable.
- Binary LAS layouts/masks: canopy/las_records.py; physical roof bands: canopy/roof_context.py (both ArcPy-free).
- CHM and support: canopy/rasters.py.
- Optional roof-edge refinement and derived roof outlines: canopy/roofs.py.
- Detection and crowns: canopy/treetops.py, canopy/crowns.py.
- Resume, raster cores, whole-AOI analysis: canopy/pipeline.py.
- Cover accounting: canopy/cover.py.
- Tool parameters: CanopyTools.pyt; CLI: canopy/__main__.py.

## Invariants

- bands.py and tiling.py must not import arcpy. Put new pure parameter/grid logic there.
- LAS decoding, roof context, plot census, evaluation domains and greenness modules must also remain ArcPy-free.
- Never run Fill before Flow Direction. The current crown algorithm uses neither.
- Preserve one actual-cell detection per connected plateau.
- Use the classified vegetation DSM, never a delivered highest-hit DSM.
- Preserve raw canopy support; do not interpolate vegetation through unknown cells.
- Cover must remain independent of detections/crowns and retain missing coverage.
- Do not classify original LAS files or mutate input treetop features.
- Keep the estimate warning in dataset metadata and user-facing detection messages.
- Never assume finite halos guarantee exact crown seams. Global analysis is bounded
  to 4,000,000 cells; larger AOIs must fail clearly until another method is validated.
- Keep credentials, imagery, working LAS files, and generated datasets in ignored scratch.

## Verify

From canopy-toolbox: python -m unittest discover -s tests -t . -v
Use ArcGIS Pro Python to execute the ArcPy fixtures; plain Python skips them.
Plain Python: use the repo-root .venv (python -m venv .venv, then pip install -r
canopy-toolbox/requirements-dev.txt). Never pip install --user: Pro's Python 3.13 environments
read the per-user site-packages, which then shadows Pro's own packages. Set PYTHONNOUSERSITE=1
for ArcGIS Pro runs.
Changes to geoprocessing need actual runtime verification and a representative pilot.
