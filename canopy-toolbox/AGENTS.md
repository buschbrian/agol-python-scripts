# Canopy toolbox development

ArcGIS Pro Python toolbox and CLI: copied/classified lidar to canopy estimates.
Read README.md and reviews/2026-09-17/IMPLEMENTATION.md for current limits; the current state of the
classification work, and how to resume it, is reviews/2026-10-20/HANDOFF.md.

## Routing

- LiDAR-first building outlines (Brian, October 26: the LiDAR is the truth for whole buildings, redraw the county
  footprints from it) and the county-vs-LiDAR classes, citywide: reviews/2026-10-26/lidar-footprints. It supersedes the
  attached-candidate reduction in reviews/2026-10-23/review-reduction.
- Where the whole LiDAR project stands, what Brian's first review answers say, and what is next: reviews/2026-10-26/STATUS.md.
  Measured cues for his reported tree and footprint problems (shrubs, brush, roofs and sheds, merges, slopes,
  redeveloped sites): reviews/2026-10-26/model-review/cues.py.
- October 26 roof and tree model review, as four queues on the footprint review page (3D buildings without a detailed
  roof, CFTree samples, tile seams, CFTree rejects; side views of each tree's points): reviews/2026-10-26/model-review.
  It replaces the hosted review layer drafted in reviews/2026-10-26/gis-review, whose upload scripts were never run.
- October 26 stop/drive transfer and unfinished private roof/tree review: reviews/2026-10-26/gis-review/HANDOFF.md. Brian requested a stop and commit. The 61-tile CFTree run is complete; the newer review build is partial and nothing from it was published. Do not restart or publish from the handoff alone.

- October 25 feet/square-feet pop-ups, CSV and app context: reviews/2026-10-25/feet-context/README.md. CFTree is Brian's selected citywide workflow: reviews/2026-10-25/cftree-pilot/README.md and the active all-61-tile run in reviews/2026-10-25/cftree-city/README.md. Remaining examples have separate assistant assessments in reviews/2026-10-25/assistant-review/README.md; these are not human labels or training imports.
- October 25 public three-way roof-form release, verification and rollback: reviews/2026-10-25/buildings-release/README.md. Brian approved public ArcGIS and Azure downloads; the existing public scene now uses v2. Earlier branch reconciliation: reviews/2026-10-23/WRAPUP-2026-10-25.md.

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
- Hosting the products for web GIS (plan, publish-ready feature layers in Web Mercator on the ITRF08 datum, building scene layer packages): reviews/2026-10-22/hosting. Uploads go through reviews/2026-10-22/hosting/upload/upload.py, one item per command and only with `--go` on Brian's word; never share or delete from here. Status, Azure plan for the COGs and app ideas: reviews/2026-10-23/PUBLISHING.md.
- Cloud-optimised GeoTIFF masters of the 0.5 m rasters for a cloud bucket (lossless, every cell proven equal; not uploaded),
  the compression trial, and the local ArcGIS Maps SDK float-COG trial page with its range/CORS server: reviews/2026-10-22/hosting/cogs.
- Slope in 6 classes as polygons and a vector tile package (4 m2 minimum mapping unit, areas proven against the raster): reviews/2026-10-22/slope-tiles. Vector tile packages of treetops, crowns and contours, scripting a Pro map without the UI, upload steps and credit cost: reviews/2026-10-22/hosting/vector-tiles.
- Hosting step 5, hillshade raster tile package (PNG32, drawn capped at 252 because a rendered 253 is the cache's transparent background) and terrain elevation tile package (LERC 0.01 m), .tpkx built headless with Manage/Export Tile Cache, not uploaded; rebuilt October 23 with the ITRF08 datum transformation applied as a 1.197 m source shift, because Manage Tile Cache ignores transformation settings: reviews/2026-10-22/hosting/tiles. Datum of the vector tiles, read from the tiles: reviews/2026-10-22/hosting/vector-tiles/datum_check.py.
- Treetop review evidence (SUSPECT flags), rebuilt from the October 15 manifest and proven byte-identical: canopy/treetop_evidence.py (ArcPy-free); reviews/2026-10-22/treetop-evidence. Its blind calibration sample: reviews/2026-10-22/packets/treetop-calibration-2 (drawn and scored with reviews/2026-10-15/calibration_sample.py).
- Overture land cover (ESA WorldCover 2021, about 1 ha effective) and OSM land use against the LiDAR canopy, with the method check against the 25.59% city cover and the disagreement regions: reviews/2026-10-23/overture-landcover (outputs on Z:\GIS\overture\2026-10-21.0\millcreek\landcover-compare).
- Whether the COGs line up with the hosted layers in a Web Mercator web map (they do: the ArcGIS Maps SDK applies the ITRF08 transformation itself; within about 5 cm of the hosted contours): reviews/2026-10-23/cog-alignment.
- ArcGIS Online cartography of the eight hosted layers (vector tile styles as item resources, feature/scene renderers
  and pop-ups in item data, the three web maps and the web scene; legend key layers for the vector tiles, the scene's grey
  buildings, 3D labels and slide pictures; the terrain-and-slope 3D scene with scene-legend keys; apply_styling.py, dry run by
  default): reviews/2026-10-23/agol-styling. Instant Apps (create, update in place, retire to the recycle bin): reviews/2026-10-23/agol-apps.
- Hosted vector tiles drawing past 1:2,257 (service maxScale=0), read-back checks and restore commands: reviews/2026-10-23/vt-overzoom.
- How the SDK draws the COGs (drawn colour against identify over COGs, zooms, tile edges and interpolation; one fault: a float COG with a class breaks renderer on its first draw, straight at a large scale, draws coarse tiles in a repeating grid; workaround and app advice): reviews/2026-10-23/cog-drawing.
- RFP bidder questions on the tree estimate (treetops by ownership scope, height and crown facts, size-based heritage/specimen screening; drafts only, nothing sent): reviews/2026-10-23/rfp-tree-questions.
- Candidate footprints detected from the LiDAR (roof clusters outside county footprints, regularized; building_heights statistics by the October 19 code, method-checked; Web Mercator copy with Field Maps review fields; LOD1.2 blocks; Overture only as a separate witness, so the layer isn't ODbL-derived; the earlier Overture-outline version is comparison only): reviews/2026-10-23/footprint-candidates.
- Footprint review page (local, keyboard-driven, Esri World Imagery beside a LiDAR view; queues: LiDAR candidates, county footprints with no 2023 roof, possible new buildings from internal Overture hints; answers backed up to the repo, never overwritten across reviewers): reviews/2026-10-23/footprint-review (footprint_review.bat serve).
- County footprint layer against the 2023 LiDAR (per-footprint best shift, local shift field, classes ALIGNED / SYSTEMATIC / REAL_OFFSET / REBUILT_OR_GONE / UNCERTAIN, derived realigned outlines; no systematic shift found): reviews/2026-10-23/county-alignment.
- Making the footprint review smaller (four ideas sized; pre-registered sample of the attached candidates and its rule; evaluate after Brian answers): reviews/2026-10-23/review-reduction.
- FEMA/ORNL USA Structures (CC BY 4.0; in Millcreek mostly 2010 imagery, structures over 42 m2) as a third vote on the review items: reviews/2026-10-23/usa-structures.
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
