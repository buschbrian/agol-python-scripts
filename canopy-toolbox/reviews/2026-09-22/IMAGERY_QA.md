# Preliminary imagery QA — Millcreek 300 m pilot

The 300 × 300 m residential pilot was overlaid with [Esri World Imagery](https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer). The service's [citation layer](https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/4) identifies the displayed source as **Salt Lake County 2025 orthophotography**, collected **12 April 2025**, at the pilot center and four corners. The point cloud at this tile was acquired **2 and 4 November 2023**. The different dates and seasons make this an inspection aid, not a reference for a detection accuracy rate.

[Overlay of imagery, crowns, candidates, and flagged buildings](../../scratch/planning_20260922/imagery-qa.png) · [ArcGIS review layer](../../scratch/planning_20260922/footprint-review.lyrx) · [counts and example IDs](../../scratch/planning_20260922/imagery-qa.json)

## Review result

The overlay shows crowns that follow visible trees, crowns that contact house eaves, and small or fragmented outlines over some roof and paved surfaces. The latter two patterns need classification review. A tree can genuinely overhang a county footprint, and the imagery postdates the LiDAR, so footprint contact alone does not prove a false detection.

The `canopy review-footprints` CLI copied `trees_review` and ran a planar Near analysis against county building footprints within 2 m. Its output is `imagery_qa.gdb/trees_footprint_review`, with `FOOT_QA`, `NEAR_DIST`, and `NEAR_FID`. The original candidate and crown layers were not changed.

| Candidate point location | All candidates | Accepted crown | Crown too small |
|---|---:|---:|---:|
| On or inside a county footprint | 99 | 45 | 54 |
| Within 2 m of a footprint | 334 | 166 | 168 |
| Farther than 2 m | 1,097 | 793 | 304 |
| **Total** | **1,530** | **1,004** | **526** |

The reusable `canopy review-footprints` command reproduced these counts on all 1,530 points. Its ArcGIS regression checks on-footprint, within-radius, and distant points, verifies the source remains unchanged, and refuses an existing output.

The 99 on-footprint candidates are first in the manual review queue, especially the 45 with accepted crowns. Inspect the point cloud's class-5 and class-6 returns at these coordinates alongside imagery and county geometry before changing classification or deleting a candidate. The 334 near-footprint candidates are a second queue for tree/eave contact. The 2 m distance is a review threshold, not a tree classifier or positional accuracy claim.

## Toolbox validation performed in this pass

Building-height rasterization now uses each footprint's grid-aligned window instead of allocating a full-AOI mask for every feature. An ArcGIS test covers an offset window as well as overlap, partial, tiny, outside, and missing-roof cases. A fresh run across all 115 pilot footprints matched every saved summary field; numeric differences were below 1e-6. Runtime was **539 seconds** for 115 footprints. Per-feature ArcGIS operations remain the bottleneck; no speedup is claimed without a comparable baseline.

Historical 2024 capture and 0.5 m nominal-spacing statements in earlier reviews are marked superseded, and generated overview and imagery figures now say 2023 and 0.32 m. The 0.5 m CHM cell size remains a separate processing setting.

## Limits and next check

This is visual and spatial triage. No independent tree labels, imagery interpretation sample, or field checks were used, so the 1,530 candidates and 1,004 crowns remain unvalidated estimates. Review a stratified set of clear trees, roof artifacts, eave contacts, parks, and foothills before using counts as inventory totals. Keep a separate record of confirmed false detections, misses, and merges/splits.
