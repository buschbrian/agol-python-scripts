# Consensus roof heights for Millcreek (October 21, 2026)

The October 19 building heights used one opinion of which lidar points are roof: the October 8 native classification. By
October 21 every point of all 61 tiles had three independent opinions. This product combines them, decided with Brian on
October 21: **a point is roof when at least two of the three call it building**.

| Source | What it is | Where |
|---|---|---|
| native | October 8 working classification (the October 19 roofs) | `runs\city-count-20261008\prepared\points` |
| FRACTAL | IGN FRACTAL, majority of three passes with NAIP 2024 colour | `fractal\city-20261019\fractal\<tile>\consensus.las` |
| Esri | Esri's pretrained building point-classification model, batch 8 | `runs\esri-building-20261020\<tile>\building` |

The FRACTAL vote is FRACTAL's own majority, not the rules-v2 refined copy. That copy keeps the native class wherever the
rules did not act (rule 12, building called ground, is still only proposed), so it repeated the native vote: with it, the
consensus called 34 labelled ground parts roof. The first build, with that vote, is kept as `roof-consensus-20261021-rulesv2`.

## Method (consensus_roofs.py)
Exactly the October 19 roof method (`canopy.rasters.build_chm`): the maximum elevation per 0.5 m cell of first and single
returns, without withheld, overlap or synthetic points, on the October 19 city grid, NoData outside the city. ArcGIS bins a
point on a horizontal cell edge into the cell above; reproducing that was needed for an exact match. **Check: the native
raster equals October 19's `roof_elevation_m.tif` on all 23,238,732 city roof cells, with no cell missing, added or
different.** All three files are checked to hold the same points in the same order (raw X, Y and Z) before any vote.

Outputs in `D:\lidar\2023-salt-lake-valley\runs\roof-consensus-20261021`: `roof_elevation_consensus_m.tif`,
`roof_height_consensus_m.tif` (minus the October 19 terrain, negatives kept), `roof_elevation_{native,fractal,esri}_m.tif`,
`building_sources.tif` (1 native + 2 FRACTAL + 4 Esri per cell), `manifest.json`, `verification.json`, and `buildings\`
(footprint statistics, below). The working arrays in `work\` can be deleted.

## Verification (verify_roofs.py)
City cells with any roof: 20.0 M with all three sources, 2.3 M with two (native and Esri 1.15 M, native and FRACTAL 0.69 M,
FRACTAL and Esri 0.42 M), 2.3 M with one only (native 1.37 M, FRACTAL 0.65 M, Esri 0.30 M).

Against Brian's labels on 12TVL2804 (1,217 labelled parts of the three packets; a source calls a part roof when most of its
points are class 6; WALL, MIXED and UNSURE left out):

| | Native (October 19) | FRACTAL | Esri | **Consensus** |
|---|---:|---:|---:|---:|
| Roof parts found (of 444) | 396 (89.2%) | 390 (87.8%) | 363 (81.8%) | **412 (92.8%)** |
| Other parts called roof (of 773) | 108 (14.0%) | 33 (4.3%) | 23 (3.0%) | **22 (2.8%)** |

The consensus is best on both. Its remaining false roofs are mostly other structures (13) and vehicles (3). Native's 108
included 35 ground and 29 tree parts. These units were partly chosen by model disagreement, so the rates compare sources on
a hard sample; they are not city accuracies. The FRACTAL vote was chosen after seeing these labels (see above).

Against the county footprints (cell centres): roof cells outside every footprint native 22.8%, FRACTAL 22.7%, Esri 20.6%,
consensus 20.5%; footprint area with roof support native 94.1%, consensus 92.7%. Roof outside a county footprint is often
real (sheds, garages, decks, new buildings), so this separates the sources only a little.

## Building heights (prepare_buildings.py, then the October 19 summarize_city_buildings.py, unchanged)
`buildings\buildings.gdb\building_heights` and `buildings\building-heights.csv`: the same 22,042 county footprints, terrain,
fields and flags as October 19, from the consensus roofs. The script's own ArcGIS rasterization pilot matched 20 of 20.

| | October 19 (native) | Consensus |
|---|---:|---:|
| Footprints with a height | 21,415 | **21,562** |
| No roof support | 624 | 477 |
| With a negative-height cell (roof below terrain) | 633 | **35** |
| Low roof support (below 80%) | 1,848 | 2,380 |

Median heights hardly move: of 21,401 footprints with a height in both, the median change of HEIGHT_P50_M is -2 mm and 86
move by more than 0.5 m; HEIGHT_P95_M moves more than 0.5 m on 2,314 and HEIGHT_MAX_M on 7,422 (single cells, as expected
when tree and ground cells leave). Negative heights almost vanish because ground called building is gone. The cost is
coverage: 459 footprints fall below 80% support, mostly lower roofs only the native classification saw (in the three largest
changes, native-only cells sat at 4.9 to 6.9 m above terrain). `buildings\comparison.json` holds the counts and
`buildings\height-changes.csv` the 751 footprints whose median moved by more than 0.5 m or whose support status changed,
largest first, for review in Pro beside the two layers (compare_buildings.py).

**Rejected: a hybrid** that also accepts native-only roof points inside a county footprint at least 1, 2 or 3 m above
terrain (all three gave the same result). On the labels it found 419 roof parts (consensus 412) but called 41 other parts
roof (22), 20 of them trees: native-only points in footprints include branches over roofs. Trees counted as roof inflate
roof heights and remove canopy, so the plain consensus stays (October 21).

## Workstation note
Two of three verification runs failed on identical inputs (an in-memory checksum mismatch, then a silent crash), and the
first footprint summary crashed in ArcGIS's geometry engine (ExtTopoEngine.dll, 0xC0000409) at building 4,750. Each
completed on a rerun. See the October 20 handoff, section 5.
