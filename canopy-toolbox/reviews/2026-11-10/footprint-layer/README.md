# Corrected building footprint layer, compared with other footprint datasets (November 10, 2026)

Brian: "rebuild the entire footprint layer and get all of that corrected, and then compare it with ... the other modern
building footprint data sets, as well as what other building footprint models we can use." **Unvalidated planning
estimates; nothing is uploaded, no public layer or 3D model changed, and the County's data is not edited.**

Output: `H:\lidar\2023-salt-lake-valley\runs\footprint-layer-20261110`
- `footprints.gdb\footprints`: the layer, 24,858 outlines in EPSG 6341, repaired so both ArcGIS geometry checks come
  back empty (`finish.json`). Use this copy.
- `footprints.gpkg`: the same before the ArcGIS repair; `footprints.json`, `compare.json`: summaries (copies here).

## How it was built ([build_footprints.py](build_footprints.py), [finish_gdb.py](finish_gdb.py))

Every compare group (the 18,865 matches included) takes its outlines once from `decisions-20261110.csv`, in the order of
authority Brian set on November 9: the regularized LiDAR outline, then his answers, county data last. Defaults he accepted
on November 10: **the roof line is kept** (no wall-line shrink) and **the county address, parcel and year built are carried**
onto the outlines. Parcel fields come by location: parcel id, location, year built and lot use only; owner names are
never read.

| Source of the outline | Outlines | From |
|---|---:|---|
| LIDAR | 22,725 | Matches, LiDAR-redrawn, LiDAR-only, sheds |
| LIDAR_UNITS | 1,524 | LiDAR outer shape cut along the county lines inside it: the 550 joins (November 9), the 142 tangles split by rule, Brian's splits and units over 2+ county outlines |
| COUNTY | 597 | Kept under trees (rule and Brian), sheds the LiDAR missed |
| COUNTY_PLUS_LIDAR | 9 | Brian's "add the extra roof" |
| COUNTY_SHIFTED | 3 | Brian's "shift onto the LiDAR" (best overlap within 5 m, or the October 23 alignment fit) |

707 are typed `shed`. Dropped: 417 vehicles, 286 pieces touching a building (Brian's call), 255+3 county footprints
gone, 12 not a building. Brian's 12 "part of the building" pieces are joined to the nearest outline within 1.5 m.

**Flags for hand work (`REVIEW_FLAG`), 56:** NEEDS_EDIT 21, UNSURE 23, and SPLIT_BY_HAND 12: his splits where one
county outline gives no line to cut by.

**Checks:** no LiDAR or county outline used twice; every unused LiDAR outline is in a dropped, county-kept or shifted
group; 469 overlaps between neighbours (regularizing pushes them together) trimmed from the smaller outline, none left;
nothing under 2 m². ArcGIS found 51 self-intersections, duplicate vertices and short segments that shapely accepts,
most where unit cuts meet; Repair Geometry (OGC) cleared them. 164 outlines are multipart. [examples.png](examples.png)
shows one of each kind of fix.

## Against the other footprint datasets ([compare_datasets.py](compare_datasets.py), [compare.json](compare.json))

All already in EPSG 6341 through the ITRF08 transformation. Polygons match when they overlap by 30% of the smaller one
(the October 23 rule).

| Dataset | Polygons in the city | Theirs found in ours | Ours found in theirs (42 m²+) | 1:1 median IoU | Our area / theirs |
|---|---:|---:|---:|---:|---:|
| County footprints | 22,026 | 98.8% | 94.5% | 0.85 | 1.14 |
| OpenStreetMap (Overture) | 21,214 | 99.1% | 93.7% | 0.84 | 1.09 |
| USA Structures (FEMA/ORNL) | 20,603 | 97.5% | 92.2% | 0.72 | 1.18 |
| Microsoft ML Buildings (Overture) | 1,152 | 86.1% | — | 0.73 | 1.16 |

- **OSM here is mostly the county layer again.** 96% of OSM polygons match a county footprint (median IoU 0.85), so
  agreement with OSM is not independent evidence.
- **Microsoft's buildings in Overture are gap fill only**, where OSM had nothing, so they cannot vote on most buildings.
  Esri Community Maps has none in the city.
- **Ours are about 10-18% larger** because they trace the roof edge, not the walls (the 0.39 m eave measured October 26).
- The County footprints missing from ours (267) are the gone and dropped ones. Ours missing from the County (2,949) are
  the LiDAR-only additions, sheds and split pieces.

**What the other sources say about the rules.** The share each set has in another source; "any" is any of OSM, Microsoft
and USA Structures (for the small sets that is mostly OSM, which is largely the County layer). The 30%-of-the-smaller rule
also counts a small piece lying under a much larger polygon, so "same size" counts only matches where the other polygon
is at most 3 times as large. The County itself is a control: it shows 0% of every LiDAR-only set, as it must by
construction (city2 linked any county outline overlapping 10% of the smaller). USA Structures is mostly 2010 imagery and
has nothing under 42 m².

| Set | Count | Any source | Same size | Same size, 42 m²+ | Reading |
|---|---:|---:|---:|---:|---|
| LiDAR-only buildings added (rule) | 2,191 | 58% | 52% | 82% of 1,168 | Supports the rule: buildings the County layer lacks |
| County gone (rule) | 255 | 56% | 53% | 80% of 160 | The sources predate the 2023 LiDAR (USA Structures 2010, OSM from the County), so they show buildings since demolished; not a contradiction, but the large ones are worth a look |
| Kept county under trees (rule) | 478 | 13% | 11% | 38% of 84 | Mostly small sheds no source maps; little evidence either way |
| Shed rule (free-standing, under 20 m²) | 679 | 9% | 2% | — | Below every source's size; no evidence either way |
| Vehicles (rule) | 404 | 15% | 8% | — | Supports the rule |
| Pieces touching a building, dropped (Brian) | 286 | 64% | 4% | — | **60% lie under a larger house outline** (below) |
| Flagged for hand work | 56 | 75% | 64% | 90% of 39 | Real buildings that need their shape fixed |

**The dropped touching pieces are mostly the edge of the same house.** 143 of the 286 lie under a larger OSM outline
that the County outline does not reach (172 under any source's). [drop-pieces.png](drop-pieces.png) shows 9 at random
(`drop_pieces.py`): nearly all are 1-2 m strips along one side of a house, where a lot line runs along the wall and cut
the eave off the roof outline. Dropping them shaves that side of the house; joining them restores the full roof line.
Joining the 143 under an OSM house outline, and dropping the rest, is an option for Brian.

## Footprint models we could run

| Model | Input | Here |
|---|---|---|
| LiDAR-first pipeline (three roof classifiers, consensus, regularize, roofer LoD2.2) | 2023 LiDAR | What this layer is; the best fit for the data we have |
| Esri "Building Footprint Extraction - USA" (Mask R-CNN, average precision 0.718, 165 MB) | 8-bit 3-band imagery at **10-40 cm** | Runs in ArcGIS Pro's Python (torch and arcgis.learn are installed). Needs licensed imagery: NAIP 2024 (0.6 m) is coarser than it expects, UGRC Discover's terms forbid inference, Esri World Imagery cannot be exported, Nearmap is set aside. A County or City orthophoto at 10-40 cm would make it usable as a check on new construction since 2023 |
| Microsoft Global ML Building Footprints (full, not Overture's gap fill) | Dataset | A download (ODbL); Brian's yes needed. Another independent vote, from newer imagery |
| Google Open Buildings | — | Does not cover the US |

Imagery models would be a check on change since the 2023 LiDAR, not a replacement for the LiDAR outlines.

## Next

The 3D rebuild (roofer LoD2.2) on this layer. 164 outlines are multipart: the October 26 prep exploded parts and keyed
them LB x 10 + part to avoid roofer's duplicate-ID crash, and the next prep needs the same on `BLDG_ID`.
