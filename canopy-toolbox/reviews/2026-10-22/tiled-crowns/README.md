# Citywide crowns in tiles (October 22, 2026)

Brian asked for a tiled crown method on October 22. `canopy.crowns.delineate` is bounded to 4,000,000 cells and AGENTS.md
says a finite halo does not guarantee exact seams, so the halo was measured against the single-window method before the
city run, and the city run checked itself.

## Method
- `canopy.crowns.segment`, unchanged: a priority flood on the CHM smoothed by one cell (the treetops' radius), over canopy
  at least 2 m. Each cell goes to the seed it reaches along the path with the highest lowest point; ties break by flood
  distance, then by the seed's integer label.
- **Seeds: every peak of the canonical CHM**, re-detected exactly as the count did (`count_peaks.detect`, default bands).
  The city's 527,140 treetops must equal the re-detected peaks inside the city (checked); they are labels 1 to 527,140 in
  `city-treetops.csv` order, the same in every tile, so ties break the same way everywhere. Peaks outside the city get higher
  labels: they only bound city crowns, and their own crowns are never output. The first version seeded city treetops only,
  and a city crown then flooded across unseeded forest beyond the boundary (12TVL3301: 303,334 cells wrong even with a 40 m
  halo); kept as `runs\*.city-seeds-only` for the record.
- **Tiles:** the October 8 count's 63 planned 950 m cores over the rebuilt canonical CHM, each segmented with a 40 m halo;
  each core keeps only its own cells, so every cell is decided once. Polygons per core (RasterToPolygon NO_SIMPLIFY on the
  accepted labels), dissolved by label across cores; statistics and the 3 m2 minimum as delineate.

## Validation (`runs\tiled-crowns-validate-<tile>\validation.json`; copies here as validation-<tile>.json)
Single-window segment of a whole 1 km tile against the same tile as 250 m cores with a halo, cells whose label differs:

| Tile (canopy share) | Canopy cells | 10 m halo | 20 m | 40 m |
|---|---:|---:|---:|---:|
| 12TVL2804 (24%) | 1,137,143 | 0 | 0 | 0 |
| 12TVL3302 (59%, densest) | 2,351,697 | 179 (4 crowns) | 0 | 0 |
| 12TVL3301 (46%) | 1,359,794 | 0 | 0 | 0 |

The city run uses 40 m, twice the smallest halo that was exact everywhere. Stability: six tiles spread across the city rerun
with an 80 m halo changed 0 cells. Against the 12TVL2804 pilot (single window, `runs\crowns-pilot-20261022`): all 9,963
treetops more than 40 m from the tile edge have exactly the same crown area; the 138 that differ are at the edge, where the
pilot was cut.

## Result (`runs\crowns-20261022\crowns.gdb`)
| | |
|---|---:|
| Treetops (all have crown cells) | 527,140 |
| **Crowns (at least 3 m2)** | **400,063** |
| Treetops whose crown is under 3 m2 (CROWN_TOO_SMALL) | 127,077 |
| Crown area | 826.4 ha (8,263,890 m2) |
| Median crown | 12.25 m2 |
| Canopy no seed reached (mostly beyond the city) | 8.6 ha |

`crowns`: TREE_ID, HEIGHT_M, CROWN_AREA_M2, CROWN_DIAM_M. `trees_review`: the treetops with CROWN_AREA_M2, CROWN_DIAM_M,
CROWN_HEIGHT_M, CROWN_STATUS. Crowns are estimated canopy regions around detected treetops, not surveyed tree crowns; a
broad tree can hold several crowns and a clump of small trees can form one. Crowns near the city boundary can extend into
the 20 m margin.

```
<Pro python> reviews\2026-10-22\tiled-crowns\tiled_crowns.py validate NEW --tile 12TVL3302 --halos 10 20 40
<Pro python> reviews\2026-10-22\tiled-crowns\tiled_crowns.py run NEW --halo 40 --check-tiles 6
<Pro python> reviews\2026-10-22\tiled-crowns\crown_polygons.py NEW
```
