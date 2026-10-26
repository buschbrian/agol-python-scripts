# LiDAR-first building outlines (October 26, 2026)

**Brian's decision, October 26:** for whole buildings, the LiDAR is right more often than the county footprints, and it
is newer. So the county footprints should be redrawn from the LiDAR, not kept and patched with LiDAR pieces. His
words: "we need to just get rid of those and take the LiDAR as the truth over the county footprints". The decision came
from his answers and notes on the LiDAR candidates, the possible new buildings and the roof fallbacks (LC00421 "redo all
- lidar has correct shape", LC00618 "redo the whole footprint", NB0020 "one building is gone the lidar is correct",
LC01389). **Unvalidated planning estimates from the 2023 LiDAR (October-November); nothing is uploaded or edited.**

## Why the candidates came out in pieces

The October 23 candidates ([lidar_candidates.py](../../2026-10-23/footprint-candidates/lidar_candidates.py)) kept only
roof cells **more than 1.5 m from every county footprint**. A LiDAR building that overlapped a wrong county outline was
cut into the part outside it, and the rest showed up as an "offset or rebuilt" pair. The outlines here use the same rules
without that step (`clusters(..., exclude_m=None)`): every 2-of-3 consensus roof cluster after a 3 × 3 opening, at least
10 m² and 2 m median height, regularized the same way. The county layer is used only afterwards, to compare.

## How the county layer compares

[lidar_footprints.py](lidar_footprints.py) `compare` groups county footprints and LiDAR outlines that overlap (at least
10% of the smaller one) and gives each group one class. The pilot covers 426000-430500 E, 4504500-4507200 N, about
40% of the city and most of Brian's examples:

| Class | Groups | County footprints | Meaning |
|---|---:|---:|---|
| MATCH | 6,240 | 6,240 | one each, intersection over union at least 0.6 |
| RESHAPED | 844 | 844 | one each, IoU under 0.6: offset, wrong shape or rebuilt |
| LIDAR_JOINS | 482 | 1,064 | one LiDAR building over several county footprints |
| LIDAR_SPLITS | 49 | 49 | one county footprint over several LiDAR buildings |
| TANGLE | 4 | 9 | several of each |
| LIDAR_ONLY | 903 | 0 | no county footprint |
| COUNTY_ONLY | 406 | 406 | no LiDAR roof: 289 have 30% or more canopy over them, 179 are under 20 m² |

**Against Brian's answers in the window:**
- 23 of the 27 candidates he accepted are LIDAR_ONLY. The other four are reshaped, joined or matched groups, where his
  candidate was a piece of a whole LiDAR building.
- His "part of the existing building" candidates fall in MATCH (5): the piece is part of one whole LiDAR building.
- His "both real" pairs are LIDAR_SPLITS.
- The roof fallbacks he called simple-but-fine, gone, under trees or unsure are COUNTY_ONLY. The LiDAR has too little
  roof there to draw an outline, which is why they fell back.

**Citywide** (the same run without a window; `runs\lidar-footprints-20261026\city`): 23,327 LiDAR outlines against
22,042 county footprints.

| Class | Groups | County footprints |
|---|---:|---:|
| MATCH | 17,245 | 17,245 (78%) |
| RESHAPED | 1,636 | 1,636 |
| LIDAR_JOINS | 1,023 | 2,260 |
| LIDAR_SPLITS | 137 | 137 |
| TANGLE | 13 | 31 |
| LIDAR_ONLY | 3,080 | 0 |
| COUNTY_ONLY | 733 | 733 (480 with 30% or more canopy over them) |

The median eave offset on MATCH groups is again 0.39 m (quartiles 0.16-0.58 m).

Against all of Brian's answers so far:
- All 5 pairs he called REBUILT are COUNTY_ONLY: the old county building has no 2023 roof.
- Both OFFSET pairs are RESHAPED.
- 26 of his 34 accepted candidates are LIDAR_ONLY.
- His 16 "part of the existing building" candidates are 9 MATCH, 4 RESHAPED and 3 LIDAR_JOINS, all one whole LiDAR building.

The LiDAR-only groups (3,080) are fewer than the October 23 candidates (6,213), because a piece against a county
building is now part of that building's whole outline.

**Chambers Avenue** (LC01389, LC01423, MD733329) is one LiDAR building of 1,418 m². The county has three outlines over
it, totalling 481 m², and more around it for buildings that are gone. County 738630, a 3,274 m² outline nearby, has no
2023 roof at all.

![County footprints (white) against the LiDAR-first outlines (blue) at Brian's examples](pilot-examples.png)

## Where the LiDAR is not the truth

- **Under trees** the LiDAR sees only part of a roof, so its outline is a lower bound there (LC00109, MD733380
  "covered with trees and not the full roof"). COUNTY_ONLY groups under canopy are hidden buildings, not demolitions.
- **Small buildings:** sheds and garages under about 10 m², or with too few roof returns, have no LiDAR outline. 179 of
  the 406 county-only footprints are under 20 m².
- **Eaves:** on MATCH groups the LiDAR edge sits a median 0.39 m outside the county outline (quartiles 0.15-0.58 m). The
  LiDAR traces the drip line and the county the walls. Nothing was shrunk; whether the product should be the roof
  outline or a wall line is Brian's call.
- **Attached units:** LIDAR_JOINS includes townhouses and duplexes, where the county splits one roof by unit. The LiDAR
  outer shape is right, but it cannot see party walls. Addresses, parcels and year built live on the county rows and
  would be carried across.
- **Date:** the LiDAR is October-November 2023. Buildings since then are the new-building hints' job, from imagery.

## Files

| File | Meaning |
|---|---|
| [lidar_footprints.py](lidar_footprints.py) | `detect` (ArcGIS Pro Python; `--window` for a pilot) and `compare` (ArcPy-free, with the answers cross-tab) |
| [pilot-examples.png](pilot-examples.png) | the five examples above, drawn on the review page's LiDAR view |
| `runs\lidar-footprints-20261026\pilot`, `...\city` | `lidar.gdb\buildings`, `clusters.tif`, `stage.tif`, `detect.json`, `compare.csv` (one row per group), `compare.json` |
