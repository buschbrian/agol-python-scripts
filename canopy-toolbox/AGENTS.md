# Canopy toolbox development

ArcGIS Pro Python toolbox and CLI: copied/classified lidar to canopy estimates.
Read README.md and reviews/2026-09-17/IMPLEMENTATION.md for current limits; the current state of the
classification work, and how to resume it, is reviews/2026-10-20/HANDOFF.md.

## Routing

- Grid, bands, ownership: canopy/bands.py, canopy/tiling.py and pure tests.
- LAS inventory/classification: canopy/preparation.py; source files are immutable.
- Binary LAS layouts/masks: canopy/las_records.py; physical roof bands: canopy/roof_context.py (both ArcPy-free).
- CHM and support: canopy/rasters.py.
- Optional roof-edge refinement and derived roof outlines: canopy/roofs.py.
- Wall/pole/wire shape evidence and opt-in class-1 gate: canopy/shape_gate.py (ArcPy-free); reviews/2026-09-29/SHAPE_GATE.md.
- Per-treetop roof-edge/wire/wall suspect evidence for a finished count (review only, never labels): the original October 15 module,
  canopy/treetop_evidence_20261015.py (ArcPy-free), reviews/2026-10-15/treetop_evidence_driver.py; reviews/2026-10-15/TREETOP_EVIDENCE.md.
- Training-label review (never evaluation): canopy/training_review.py (ArcPy-free), canopy/training_review_arcpy.py, TrainingReview.pyt, reviews/2026-09-29/training_review_driver.py; reviews/2026-09-29/TRAINING_REVIEW.md. Labels are backed up to the repo with `backup`/`restore` (packets/training-labels); reviewer steps in reviews/2026-09-30/LABELLING_CHECKLIST.md, wrapper training_labels.bat.
- Click-through labelling page (local server, blind by design), refined-cylinder packet, triage auto-accept: reviews/2026-10-20/label-page (label_page.bat; calibration mode for the treetop calibration packets: build_calibration_data.py, serve-calibration), reviews/2026-10-20/refined-cylinders, reviews/2026-10-20/rare-classes (vehicles, wires, poles, fences), reviews/2026-10-20/auto_accept.py. Answers import only through `restore`; never overwrite a human label without asking.
- Citywide FRACTAL (Myria3D) inference and the provisional refined LAS copies (rules v1/v2): reviews/2026-10-19/fractal-city; the pass runner is reviews/2026-09-30/fractal/repeat.py (`--checkpoint` for a fine-tuned model).
- FRACTAL fine-tuning on the training labels (patched Myria3D clone, config, driver, held-out scorer): reviews/2026-10-20/fractal-finetune.
- Esri building model on every tile (copies only): reviews/2026-10-20/esri-city.
- Consensus roofs (2 of 3: native, FRACTAL majority, Esri) and their footprint heights: reviews/2026-10-21/roof-consensus.
- Canopy rasters, treetop recount, crown pilot and cover by zone from the combined classification: reviews/2026-10-22/canopy-rebuild; the current product library: reviews/2026-10-22/PRODUCTS.md (assemble_library.py).
- Citywide crowns in tiles (canopy.crowns.segment, measured halo, every peak as a seed): reviews/2026-10-22/tiled-crowns.
- Citywide terrain products (slope, aspect, curvature, hillshade, terrain position, contours; planning.terrain's calls on the whole grid, proven equal on a window): reviews/2026-10-22/terrain-city.
- 3D building massing (Extract LOD2 Buildings on the consensus roof surface; LOD1.2 blocks and LOD2.0 roofs): reviews/2026-10-22/massing.
- Hosting the products for web GIS (plan, publish-ready feature layers, building scene layer packages; nothing is uploaded from here): reviews/2026-10-22/hosting.
- Cloud-optimised GeoTIFF masters of the 0.5 m rasters for a cloud bucket (lossless, every cell proven equal; not uploaded),
  the compression trial, and the local ArcGIS Maps SDK float-COG trial page with its range/CORS server: reviews/2026-10-22/hosting/cogs.
- Slope in 6 classes as polygons and a vector tile package (4 m2 minimum mapping unit, areas proven against the raster): reviews/2026-10-22/slope-tiles. Vector tile packages of treetops, crowns and contours, scripting a Pro map without the UI, upload steps and credit cost: reviews/2026-10-22/hosting/vector-tiles.
- Hosting step 5, hillshade raster tile package (PNG32, drawn capped at 252 because a rendered 253 is the cache's transparent background) and terrain elevation tile package (LERC 0.01 m), .tpkx built headless with Manage/Export Tile Cache, not uploaded: reviews/2026-10-22/hosting/tiles.
- Treetop review evidence (SUSPECT flags), rebuilt from the October 15 manifest and proven byte-identical: canopy/treetop_evidence.py (ArcPy-free); reviews/2026-10-22/treetop-evidence. Its blind calibration sample: reviews/2026-10-22/packets/treetop-calibration-2 (drawn and scored with reviews/2026-10-15/calibration_sample.py).
- Height above ground (ground surface, Z-replaced and Extra Bytes LAS copies): canopy/hag.py (ArcPy only in raster_builder); reviews/2026-09-29/HAG.md.
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
- Training labels never enter reference.gdb. The evaluation exclusion frame (reference units and census
  plots with a 25 m buffer; 12TVL3302 and 12TVL2203 with halos) is enforced on every training label write,
  snapshot and export.

## Verify

From canopy-toolbox: python -m unittest discover -s tests -t . -v
Use ArcGIS Pro Python to execute the ArcPy fixtures; plain Python skips them.
Plain Python: use the repo-root .venv (python -m venv .venv, then pip install -r
canopy-toolbox/requirements-dev.txt). Never pip install --user: Pro's Python 3.13 environments
read the per-user site-packages, which then shadows Pro's own packages. Set PYTHONNOUSERSITE=1
for ArcGIS Pro runs.
Changes to geoprocessing need actual runtime verification and a representative pilot.
