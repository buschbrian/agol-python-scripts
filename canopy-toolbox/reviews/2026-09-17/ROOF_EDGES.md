# Roof-edge follow-up — 2026-09-17

**Acquisition correction (2026-09-22):** The 2024 capture and 0.5 m nominal-spacing statements below are retained as historical notes. Delivery metadata establishes acquisition on 7 October–5 November 2023 and nominal point spacing of 0.32 m. See [delivery provenance](../../DELIVERY_PROVENANCE.md).


The user confirmed **2024 lidar capture and 0.5 m nominal point spacing**. CHM cell size remains a separate processing choice, currently also 0.5 m.

Two corrections now address the observed roof-edge leakage: an optional, auditable classification refinement on new LAS copies, and a building-above-vegetation check in CHM construction. The final imagery comparison shows substantially fewer roof-edge artifacts; the results are still unvalidated inventory candidates.

## Footprint reference

The supplied [Millcreek OSM footprint service](https://services9.arcgis.com/XRrSFvEwSsReIxuA/arcgis/rest/services/Millcreek_Building_Footprints_OSM_2024/FeatureServer) describes a June 2024 OSM extraction. A query for the pilot extent plus 30 m returned zero intersecting footprints. Service/layer metadata and the empty query result are retained under scratch/pilot_20260917/roof_edges.

For this pilot, roof support was derived from measured class-6 first/single returns. Six regions met the minimum support area. Five passed a low-slope plane fit; roof 4 failed the 80% inlier criterion and was not reclassified by the edge-refinement step. Its inlier fraction was approximately 76.9%, despite a small residual among accepted points. This avoids accepting an incomplete or multi-level roof merely because a subset fits well.

The outlines have estimated roof elevations and heights above interpolated ground, plus fit diagnostics and an AOI-truncation flag. They are rasterized roof-support polygons, not surveyed wall footprints. Model-fit residuals are not footprint or height accuracy estimates.

## Classification refinement

The new refine-roofs CLI command:

- Writes new LAS copies and leaves the original delivery and previous preparation unchanged.
- Fits roof planes from measured building support; bridges only one-cell gaps, retaining larger courtyards.
- Reclassifies eligible vegetation-class returns only within the support or a 1 m edge band, from 0.35 m below to 3 m above an accepted roof plane.
- Preserves lower neighbouring canopy and higher overhangs outside that height band. Real vegetation within the band can still be affected and requires inspection.
- Saves per-point indices and previous class bytes, before/after class counts, model diagnostics, and review polygons.

The pilot changed 2,124 class-5 points to class 6. Full binary comparison proved that **only the logged classification bytes changed**. Coordinates, return numbers, flags, point counts, and other LAS bytes were unchanged.

## Same-cell building occlusion

The cross-section identified a second problem: a higher building return and a lower vegetation-class return could share a cell, yet the old CHM accepted the lower vegetation return as canopy.

CHM construction now reports observed non-canopy where a measured class-6 first/single surface is more than 0.35 m above vegetation in the same cell. It applies no lateral footprint buffer. Canopy above buildings remains eligible. The clearance is configurable through the toolbox and CLI, and is a processing tolerance rather than a claimed vertical accuracy.

Each raster tile retains dsm_building.tif and building_occlusion.tif alongside the original vegetation DSM and support/observation masks. This changes derived visible-canopy occupancy; it does not relabel additional LAS points below roofs.

## Measured pilot result

| Metric | Before follow-up | Final |
|---|---:|---:|
| Tree candidates | 868 | 776 |
| Accepted crowns, minimum 3 square metres | 624 | 592 |
| Observed canopy area | 10,619.00 square metres | 10,374.50 square metres |
| Observed area | 62,174.25 square metres | 62,174.25 square metres |
| Missing area | 325.75 square metres | 325.75 square metres |

The edge refinement reduced canopy area by 83.25 square metres. Same-cell occlusion removed another 161.25 square metres. All 1,020 changed CHM cells were within either the permitted roof-refinement band or a measured building-occlusion mask. Outside those masks the CHM did not change; no heights increased and the NoData mask was unchanged.

Candidate-count reductions are not measured false-positive counts. The imagery indicates improvement, but field/reference labels are still needed to measure omissions and over-removal. Latest Nearmap capture date remains unknown.

Full-zone CANOPY_PCT stays null because coverage is incomplete. The final missing-area bounds are 16.5992%–17.1204%; they do not account for classification error and are not confidence intervals.

## Verification and current outputs

**55/55 tests pass** on the Pro workstation; see [roof-visible-tests.txt](roof-visible-tests.txt). Added tests cover accepted/rejected roof models, courtyard preservation, legacy/modern LAS byte integrity, untouched flags/classes, lower vegetation beneath a building, higher canopy above a building, clearance tolerance, and absent building classes. Toolbox parameter definitions load with the new clearance control. Source syntax and git diff whitespace checks pass.

Pilot checks also verified unchanged source/preparation file size and mtime, an unchanged observation mask, no changes outside the allowed masks, and successful resume. See [roof-visible-pilot.json](roof-visible-pilot.json).

Use these current artifacts:

- [Roof detail before/after](../../scratch/pilot_20260917/roof_visible_run/roof-detail.png).
- [Whole-pilot comparison](../../scratch/pilot_20260917/roof_visible_run/pilot-comparison.png).
- [Roof outlines and height map](../../scratch/pilot_20260917/roof_visible_run/roof-outlines.png).
- [Lidar cross-section](../../scratch/pilot_20260917/roof_edge_run/roof-cross-section.png).
- [ArcGIS roof outline layer](../../scratch/pilot_20260917/roof_visible_run/roof_outlines.lyrx).
- [ArcGIS candidate review layer](../../scratch/pilot_20260917/roof_visible_run/classification_qa/classification_review.lyrx).
- [Refined LAS preparation manifest](../../scratch/pilot_20260917/roof_edge_preparation/preparation.json).
- [Current run manifest](../../scratch/pilot_20260917/roof_visible_run/run.json).

The current output geodatabase is scratch/pilot_20260917/roof_visible_run/assembly_d1c43353/inventory.gdb. Tree/crown layers remain UNVERIFIED; the separate review layer prioritizes proximity to building points and small crowns without deleting them.

## Remaining review

Roof 4 is explicitly marked MODEL_REJECTED, and several outlines are truncated by the pilot boundary. Residual façade returns, canopy close to eaves, and isolated rooftop equipment still warrant inspection. The six local outlines do not establish citywide footprint accuracy. The 4-million-cell AOI limit remains; citywide crown reconciliation is not implemented.

The next useful user check is the orange/model-rejected roof and ambiguous crowns at eaves in the supplied layers. No further input is needed to rerun this pilot using the documented commands and new output directories.
