# Implementation and pilot results — 2026-09-17

**Acquisition correction (2026-09-22):** The 2024 capture and 0.5 m nominal-spacing statements below are retained as historical notes. Delivery metadata establishes acquisition on 7 October–5 November 2023 and nominal point spacing of 0.32 m. See [delivery provenance](../../DELIVERY_PROVENANCE.md).


Latest follow-up: [roof-edge fixes, 55-test validation, and current outputs](ROOF_EDGES.md). The counts below describe the earlier pilot before that follow-up.

The runtime blockers and analytical failures reproduced in the original review have been corrected. A representative real-data pilot now runs through copied-point classification, raster generation, detection, crowns, cover accounting, and field-review outputs on this workstation. Classification remains unvalidated, and citywide crown reconciliation remains outside the implemented bounded-AOI workflow.

## Verification

- Full ArcGIS Pro regression suite: **51 tests passed**, including 12 actual ArcGIS cases. See [final-tests.txt](final-tests.txt).
- Plain Python: 39 tests passed; the 12 ArcGIS cases skip as designed.
- Syntax compilation: 22 Python/toolbox source files passed.
- Toolbox entry points: all five parameter definitions load; detection and delineation execute on the real pilot, including the new derived trees_review output. See [toolbox-smoke.json](toolbox-smoke.json).
- Pilot global recheck: identical TREE_ID/crown-area/height rows on a second independent invocation against the assembled CHM.
- Pilot resume: unchanged output paths; equivalent numeric CLI/API parameters accepted. Changed parameters/code/inputs are rejected by the runner.
- Original pilot LAS file size and modification time remained unchanged after classification and processing. Only newly extracted point files were classified.
- Nearmap credential scan: no token found in Git-visible files. Connection and imagery are ignored scratch data.

Runtime: ArcGIS Pro 3.7.2 build 1901; Python 3.13.13; SciPy 1.16.3; Advanced/ArcInfo license with 3D and Spatial Analyst. Lower Pro license levels and hosted editing were not tested.

## Findings and corrections

| Review finding | Implemented correction | Evidence |
|---|---|---|
| Mixed folder/GDB output assumptions | Ordinary folders for rasters; existing file GDBs for features/tables; validation in functions and toolbox; unique scratch names. | ArcGIS outputs and toolbox execution pass. |
| One-cell crown for a complete cone | Deterministic marker priority flood, seeded by actual raster cells, constrained to measured raw canopy. No Fill/FlowDirection. | The 137-cell cone returns 137 square metres; adjacent fixed markers and disconnected unknown regions pass. |
| Invented canopy in gaps and class-1 leakage | DSM classes 3/4/5 only; no vegetation void filling; explicit observed/support masks; exclude withheld/overlap/synthetic returns. | Synthetic ground gaps, roof class, and class-1 points do not become canopy. |
| Inflated cover denominator | Polygon area, grid area, observed area, missing area, observed-only percentage, and missing-area bounds are separate. Full-zone percentage stays null when incomplete. | Partial/outside/tiny/overlapping/duplicate-ID zones and repeated calls pass. |
| Assumed cell size/units | Projected metre checks, vertical-unit gate, resolution derived from raster, mismatch/nonsquare rejection. | Metre fixtures, feet/geographic rejection, mismatched resolution tests. |
| Unconnected tiling and unstable local IDs | Buffered raster core coordinator, canonical mosaic, UUIDs from source/CRS/location, immutable-input/code resume checks, runtime manifests. | Four-core pilot; repeatable IDs and final crown recheck. |
| Halo seam differences | Whole-AOI detection and segmentation; explicit 4-million-cell limit before processing. Crown area uses cell counts rather than imprecise clipped polygon areas. | A long plateau and a crown spanning tile cores match global results. |
| Missing safeguards and provenance | Finite numeric checks, eight-connected plateau collapse, unique scratch cleanup, empty outputs, persistent estimate warning, independent review copy with rejected-crown status. | Regression fixtures and actual toolbox execution. |

The runner now tiles the raster-building stage; it does not approximate citywide crown growth using finite halos. The 4-million-cell limit is 1 square kilometre at 0.5 m resolution. Raster interpolation can still change slightly with tile layout; SEAM_REVIEW flags nearby detections. Extending exact segmentation to larger AOIs, or reconciling independent AOIs, is future work and is not claimed complete.

The first tiled prototype had 40 crown-area differences from whole-area segmentation and some unflagged discrepancies. Changing to a canonical CHM alone was insufficient. The current whole-AOI approach removes that inconsistency. Earlier prototype artifacts in scratch are retained for traceability; use reviewed_run for current results.

## Delivery and pilot

The read-only delivery inventory found 52 uncompressed LAS files, 1,269,149,276 points, approximately 38.1 GB. Horizontal CRS is NAD83(2011) / UTM zone 12N (EPSG:6341); vertical reference is NAVD88 height with Geoid18 metadata, in metres. Header creation dates are not flight dates. Initial class samples showed predominantly ground and unclassified points, with noise/water/ignored-ground classes in parts of the delivery; vegetation/building preparation was required.

Pilot bounds: 422350, 4503350, 422600, 4503600 — 250 m square. This commercial-campus sample includes large roofs, parking/pavement, landscaped trees, and dense vegetation. It is useful for detecting building leakage; it does not represent every park, slope, species, or stand condition in the delivery.

Extraction created 2,745,665 working-copy points. Existing ground (1,237,618 points) and noise (79 low + 4,903 high) were preserved. Standard roof-plane classification left visible rooftop equipment and roof-edge points in vegetation classes. The revised pass classifies points below detected roofs and within 3 m above them as buildings before height classification. The setting is configurable and must be reviewed for overhanging vegetation.

Building-class points increased from 185,590 to 204,884 compared with the first pilot preparation. Most rooftop-equipment candidates disappeared in the imagery check, but some roof-edge false candidates remain. This is an improvement demonstrated visually, not a measured classification-accuracy rate. See the [Esri building-classification parameters](https://pro.arcgis.com/en/pro-app/latest/tool-reference/3d-analyst/classify-las-building.htm) for the stock tool's above/below-roof controls.

Earlier pilot results, before the roof-edge follow-up:

| Result | Value |
|---|---:|
| Detected candidates | 868 |
| Accepted crowns, minimum 3 square metres | 624 |
| Candidates below minimum crown area | 244 |
| Observed canopy at 2 m threshold | 10,619 square metres |
| Rasterized zone area | 62,500 square metres |
| Observed area | 62,174.25 square metres |
| Missing area | 325.75 square metres |
| Observation coverage | 99.4788% |
| Full-zone CANOPY_PCT | Null, because coverage is incomplete |
| Missing-area bounds | 16.9904%–17.5116% |
| Unseeded canopy | 55.75 square metres |

The bounds address missing coverage only. They do not include classification error, detection error, imagery-date mismatch, or field uncertainty. Do not publish 868 as a tree census or the cover bounds as a validated accuracy interval.

## Review artifacts

- [Pilot evidence](pilot-summary.json): counts, runtime, parameters, source-integrity check, resume/global recheck, imagery provenance, and absolute dataset paths.
- [Current run manifest](../../scratch/pilot_20260917/reviewed_run/run.json).
- [Whole-pilot imagery comparison](../../scratch/pilot_20260917/reviewed_run/imagery-comparison.png).
- [Roof detail before/after](../../scratch/pilot_20260917/reviewed_run/roof-comparison.png).
- Earlier geodatabase: ../../scratch/pilot_20260917/reviewed_run/assembly_b303f1f9/inventory.gdb. Primary layers: treetops, crowns, trees_review, pilot_boundary, canopy_cover. Verification/ui-prefixed layers are additional test outputs.
- [Working-copy preparation manifest](../../scratch/pilot_20260917/refined_preparation/preparation.json).

Nearmap latest WMS was requested in EPSG:26912 with an explicit ArcGIS datum transformation from the LAS CRS. Its capabilities response did not provide capture dates or feature-info formats. The user confirmed lidar capture in 2024 and confirmed 0.5 m nominal point spacing, separately from the chosen raster cell size. The Nearmap capture date and temporal match remain unknown. The credential is not included in any report or source file.

## Other repository utilities

- Bad Elf helper now rejects negative layer indices, checks existing field type/length/domain compatibility, and offers a true schema --dry-run. No hosted changes were made.
- Sketch schema helper reads attribute rules without exporting during dry-run, restores originally enabled rules even after a failed load, and explicitly projects differing coordinate systems. Mocked failed-append and dry-run cases pass; production schema loading was not executed.
- Polygon coloring skips self-neighbours, uses OID@, and fails before feature edits if its palette is exhausted. A ten-node complete graph verifies the failure safeguard.

## Remaining process work

Inspect and correct residual building-edge candidates and potential tree-overhang losses; record the exact 2024 flight date and imagery capture date; validate ground and vegetation across additional settings; calibrate bands and tree definition using independent reference labels; measure precision/recall and merge/split errors; and validate a larger-AOI strategy before citywide crown production. Species, DBH, condition, and longitudinal tree identity require field review or another supported source. No production publishing or hosted inventory update was performed.


## Follow-up: user-confirmed capture year and classification review

The user confirmed lidar capture in 2024 and reported 0.5 m resolution. The user subsequently confirmed that 0.5 m means nominal point spacing. This pilot already uses 0.5 m CHM cells. Exact flight date, leaf condition, and Nearmap capture date remain unconfirmed.

A separate [ArcGIS review layer](../../scratch/pilot_20260917/reviewed_run/classification_qa/classification_review.lyrx) preserves all 868 candidates and adds BUILDING_DIST_M, QA_REASON, and QA_PRIORITY. The original trees_review feature class is unchanged. Proximity is measured to eligible first/single class-6 point XY locations, excluding withheld, synthetic, and overlap flags. The 2 m threshold is an inspection aid, not a tree/building classifier.

| Review category | Candidates |
|---|---:|
| Within 2 m of building points, accepted crown | 56 |
| Within 2 m of building points, small crown | 128 |
| Small crown away from building points | 116 |
| General review | 568 |

The pilot has 1,659,645 eligible first/single returns, averaging 26.55 points per square metre over the 250 m box. This is an area-average count, not certified pulse spacing or vertical accuracy, and should not be equated with the user's 0.5 m product resolution. See [classification-qa.json](classification-qa.json) for counts, review-layer paths, and example candidate IDs/coordinates.

The next useful reference inputs are authoritative building footprints, any field-verified tree observations, and two or three specific remaining error examples. Tree overhangs must be reviewed when changing roof exclusions.
