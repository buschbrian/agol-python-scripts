# Millcreek sequential point-cloud model validation — 2026-09-22

## Matched pilot

The Building Point Classification DLPK, followed by the Tree Point Classification DLPK, ran on a **new copy** of the STANDARD prepared 2023 tile `12TVL2804.las`. Ground (class 2) was preserved in both stages, building (class 6) in the tree stage, and noise classes 7/18 were excluded. Both stages refreshed LAS statistics. The prepared source copy retained its original SHA-256. The ArcGIS class-parameter validator rejected preserving 7/18 in a computed-statistics layer; using the documented excluded-class parameter succeeded. The [stage manifest](../../scratch/models/millcreek_building_tree_trial_v2/model_trial.json) records point-class counts and parameters.

All three runs used the same 300 × 300 m extent, 0.5 m grid, 2 m canopy threshold, and crown settings. Both DLPK runs interpreted model class 0 as predicted background via `--classified-background-zero`.

| Result | STANDARD | Tree DLPK | Building then tree DLPKs |
|---|---:|---:|---:|
| Observed canopy area, m² | 20,962.75 | 20,308.25 | 20,435.50 |
| Tree candidates | 1,530 | 1,345 | 1,299 |
| Accepted crowns | 1,004 | 943 | 952 |
| Missing 0.5 m cells | 1,911 | 1,480 | 1,480 |

Against STANDARD, building then tree removed 4,204 canopy cells and added 2,095, a net reduction of 527.25 m². Against tree only, it removed 1,853 cells and added 2,362, a net gain of 127.25 m². On the same peak-ID grid, 1,050 peaks are shared by STANDARD and the combined run; 480 occur only in STANDARD and 249 only in the combined run. The [paired metrics](../../scratch/models/building_tree_comparison.json) and [April 2025 imagery overlay](../../scratch/models/building_tree_change_map.png) show the locations. The overlay shows changes both near roofs and in treed yards. No direction can yet be called correct from the 2025 image.

## Current OSM building check

Following the user's direction, a live Overpass query retrieved **162 closed OSM building ways** around the current Millcreek pilot, all converted to NAD83(2011) / UTM zone 12N. The earlier zero-feature OSM result was for the **Taylorsville demo tile**, not this Millcreek pilot. The Overpass database timestamp was 2026-09-22 22:20:51 UTC. The latest edit timestamps for 98 of the 162 ways are after the LiDAR collection ended in November 2023; an edit timestamp does not show whether the footprint geometry changed. [Raw response](../../scratch/planning_20260922/overpass_buildings_latest.json) · [OSM review manifest](../../scratch/models/osm_model_comparison.json).

| Candidate peak relative to current OSM footprint | STANDARD | Tree DLPK | Building then tree |
|---|---:|---:|---:|
| On footprint | 90 | 49 | 51 |
| Within 2 m, outside footprint | 325 | 243 | 196 |
| Elsewhere | 1,115 | 1,053 | 1,052 |

This check prioritizes roof/eave review. A valid tree overhang can have its peak within a footprint, and the footprint data are current rather than frozen at the 2023 capture date. Lower contact counts are **not** measured precision. The public primary Overpass endpoint returned HTTP 406 and another endpoint returned HTTP 504; a later request to a listed global instance succeeded. The successful endpoint and exact query are retained in the raw response.

## Fixed validation sample

The [unlabeled review sample](../../scratch/models/model_imagery_sample.json) includes 206 candidate peaks, selected deterministically across method-presence patterns and OSM contact groups. Its `candidate_image_sample` layer has empty fields for imagery source/date, tree/non-tree/uncertain judgment, crown merge/split judgment, and notes. The `canopy_plot_sample` layer has 24 disjoint 10 × 10 m plots: eight high-gain, eight high-loss, and eight stable-canopy controls. It records canopy area, detected tree counts, and OSM footprint area for each plot under all three methods. Fields for manually interpreted canopy area and tree count remain empty. Plot sampling is intentionally stratified and cannot directly estimate citywide accuracy without weighting.

The available orthophoto is 12 April 2025, while this LiDAR was captured in November 2023. It supports provisional visual triage only. Fall 2023 Nearmap tiles, if made available through the proposed date-filtered API, can be applied to these fixed samples without changing the method outputs or sample locations. Independent labels, including missed trees, must precede any choice of production classifier or precision/recall claim.

## September 23 follow-up

The reported roof patch and point transitions were reproduced with unchanged LAS hashes. See [the September 23 checkpoint](TODAY_2026-09-23.md) for exact findings, missing intermediate-stage evidence, dated-imagery review, test status and remaining work. Learned alternatives remain experimental.
