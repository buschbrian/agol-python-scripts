# USA Structures as a third footprint source (October 23, 2026)

Brian asked whether other building footprint datasets had been used to validate the review, then to "pull USA
Structures for Millcreek (bounded to the city) and use it as a third check on the candidates, the county no-roof
footprints and the new-building hints" ([usa_structures.py](usa_structures.py)). **The LiDAR figures are unvalidated
planning estimates.** Nothing was uploaded, and no county or city data was edited.

Output: `H:\lidar\2023-salt-lake-valley\runs\usa-structures-20261023`.
- **usa_structures.gpkg:** layers `usa_structures` (20,615 touching the city, EPSG 6341) and
  `not_in_county_or_candidates` (409, with their 2023 roof share and why the detection holds no roof there).
- **votes.csv:** one vote per review item.
- **raw/:** the GeoJSON pages as fetched.
- **fetch.json, compare.json:** the summaries (copies here).

## The source
- **What it is:** Esri US Federal Data's "USA Structures" layer
  ([item 0ec8512ad21e4bb987d7e848d14e7e24](https://www.arcgis.com/home/item.html?id=0ec8512ad21e4bb987d7e848d14e7e24)):
  the FEMA Geospatial Response Office and Oak Ridge National Laboratory inventory of structures over 450 ft². The
  layer says it is current to June 6, 2025, with Utah updated in that cycle.
- **Licence:** CC BY 4.0, so attribution is required but there is no share-alike. The review page carries the line
  "USA Structures: FEMA Geospatial Response Office and Oak Ridge National Laboratory, via Esri (CC BY 4.0)".
- **How it was pulled:** 42,892 structures in the city's bounding box, in 22 pages of 2,000 as WGS84 GeoJSON. They
  were projected to EPSG 6341 with WGS_1984_(ITRF08)_To_NAD_1983_2011, the same transformation as the county
  footprints and Overture, and the 20,615 touching the city were kept.
- **It is old here.** 19,169 of the 20,615 (93%) were traced from imagery dated September 18, 2010. Another 1,050 are
  from August 18, 2019 and 396 from May 4, 2020. The outbuilding flag is empty everywhere. So it can say a structure
  stood somewhere in 2010-2020, never that something is new since the 2023 LiDAR.
- **It lists nothing under 42 m².** It can't vote on small sheds.
- **A "yes" is about the place, not the building.** All 20 houses Brian accepted were built in 2018-2021 per the
  assessor. USA Structures has 9 of them: 6 traced from the August 2019 imagery, and 3 (LC00128, LC00546, LC00596)
  matching the 2010 house each replaced.

## The votes
A candidate or county footprint counts as "in USA Structures" when they overlap by at least 30% of either, the rule
used for Overture. A new-building hint counts when a structure lies at least half inside its box.

| Item | In USA Structures | What it says |
|---|---:|---|
| County footprints (all 22,042) | 19,525 (88.6%) | the two agree on most buildings; the rest are mostly sheds under its size floor |
| LiDAR candidates, all | 1,261 of 6,213 (20%) | most candidates are under 42 m² |
| LiDAR candidates of 42 m² or more | 803 of 1,752 (46%) | |
| … detached | 558 of 856 (65%) | real outbuildings that stood by 2010 or 2019-20 and the 2019 county layer misses |
| … large and tall | 68 of 252 (27%) | mostly newer than its imagery, like the 2018-2021 houses Brian accepted |
| … against a county building | 16-38% by group | additions newer than 2010, or drawn into the house outline |
| County footprints with no 2023 roof | 155 of 586; 139 of the 210 of 42 m² or more (66%) | stood in 2010-20, so gone since or hidden by trees |
| New-building hints | 24 of 208 (12%) | a structure stood there in 2010-20 and the LiDAR saw none in 2023: likely gone, not new |
| In USA Structures, under 30% covered by any county footprint or candidate | 409 (of 42 m² or more) | no standing building missed: 320 have under 10% 2023 roof, 86 have 10-50%, 3 have 50-80%, none 80% or more |

None of its imagery postdates the LiDAR, so it can't confirm a post-2023 building.

## On the review page
Every candidate, county no-roof item and new-building hint now shows "USA Structures (FEMA, 2010-2020 imagery)". It
reads one of:
- "yes: residential, imagery 2010-09-18 (a structure stood here then)";
- "no structure here in its imagery (2010-2020)";
- "no record (it lists only structures over 42 m²)".

Each pair shows the same for its LiDAR pieces. Applied with `footprint_review.bat facts` (it reads votes.csv when
present). Brian's answers are untouched. The sample protocol notes the added fact; it was added before any sample
answer.

## Does USA Structures hold buildings the county and the LiDAR both miss?
No standing ones. Brian asked to look at the structures it has on solid 2023 roof that neither the county nor the
candidates hold, and to add them to the review if they were real gaps.

The first count, 549 of which 138 sat on solid roof, was wrong. It matched each county footprint to its single best
structure, so a structure spanning two county footprints (a house and garage drawn as one, a duplex) looked
unmatched. The 138 were 89% covered by county footprints at the median, and every one was at least 15% under a county
footprint or candidate.

Counted from the USA side, 409 structures of 42 m² or more are less than 30% covered by any county footprint or
candidate:
- **No roof (320, under 10%):** gone by 2023, or hidden by trees. Most come from the 2010 imagery, and the 2019 county
  layer doesn't have them either.
- **Some roof (89, 10-80%):** mostly 2010 outlines that sit slightly off, clipping the edge of a county building or
  falling between buildings (`uncovered-examples.png`).
- **Solid roof (none, 80% or more).**
- **Fragmented roof (8):** the only possible misses, structures of 43-480 m² whose roof the detection dropped as too
  thin or too small: 16101209, 16134057, 16149322, 3669959, 3711950, 3683117, 3718848, 3723640. They are a broken-up
  low roof, perhaps a carport, trellis or shed partly under trees.

Eight items don't justify a new queue. They are listed here and in the GeoPackage (DETECTION = "fragmented roof")
for a look in Pro.

## Rerun
From `canopy-toolbox`, ArcGIS Pro env `millcreek-py3`, `PYTHONNOUSERSITE=1`:
```
python -I reviews/2026-10-23/usa-structures/usa_structures.py fetch OUT
python -I reviews/2026-10-23/usa-structures/usa_structures.py compare OUT
```
