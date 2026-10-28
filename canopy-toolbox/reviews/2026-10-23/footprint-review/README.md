# Footprint review page (October 23, 2026)

A local browser page for reviewing building footprints one at a time, so the City ends up with complete, accurate and
current building footprints. Brian asked for it on October 23 and will review himself. It is modelled on the October 20
[label page](../../2026-10-20/label-page/README.md): it runs on this machine only, is keyboard-driven, saves atomically
after every answer, and never overwrites one reviewer's answer with another's. **The heights and roof figures it shows are
unvalidated planning estimates from the 2023 LiDAR, not surveyed data.** Nothing is uploaded.

Start it (Windows; opens http://127.0.0.1:8770 in the browser):

```
canopy-toolbox\reviews\2026-10-23\footprint-review\footprint_review.bat serve
```

Keep the server's window open while you review: the page talks to it for every item and answer. If the window is
closed, the page says it can't reach the server; run `serve` again and reload.

Type your initials in the box at the top right first; the page remembers them. Answers are saved after every key press
to `H:\lidar\2023-salt-lake-valley\runs\footprint-review-20261023\data\answers\footprint-review-answers.csv`. After a
sitting, copy them into the repo with `footprint_review.bat backup`, then commit
`reviews/2026-10-23/footprint-review/answers/footprint-review-answers.csv`. The backup never changes an answer already in
the repo unless you add `--replace`.

## The page
Each item shows two views of the same square of ground, side by side:
- **Esri World Imagery.** Here that is Salt Lake County's orthophotos of **April 16, 2025** at 7.6 cm, newer than the
  LiDAR; the date and resolution show above the map. You can zoom and pan; R resets the view.
- **The 2023 LiDAR** (October-November) at 0.5 m: roofs coloured by height above ground (yellow low to magenta 12 m and
  over), trees of 2 m or more in green, and the ground as a grey hillshade. Outside the city it is white.

On both views the item is red, county footprints are white and other candidates dashed cyan. Map outlines come from
the ITRF08 Web Mercator copies, so they sit on the imagery. The side panel gives the item's facts, the question and the
answers.

| Key | Action |
|---|---|
| 1 to 6 | answer (the buttons show which is which; the queues have 3 to 6 answers) |
| → or Enter, ← | next, previous |
| Backspace | clear this item's answer |
| N | type a note (Enter saves it with the answer, Esc leaves the box) |
| R | reset the map view |

"Show: Unanswered" (the default) resumes where you stopped. "Group" narrows a queue, and "All" or "Answered" let you go
back over answers.

## Queues
| Queue | Items | Order | Answers |
|---|---:|---|---|
| **LiDAR candidates** ([footprint-candidates](../footprint-candidates/README.md)) | 6,213 | large and tall (252), detached (2,286), against a county building (other, 1,883), lower roof against a county building (1,386), corner or edge of a county roof (406); north to south within each | 1 ACCEPT (a separate building), 2 PART_OF_EXISTING (an addition, porch or eave strip of the neighbouring county footprint), 3 VEHICLE (not a building: RV, trailer or vehicle), 4 REJECT (not a building: tree or other), 5 UNSURE |
| **County footprints with no 2023 roof** | 586 | by county ID | 1 DEMOLISHED, 2 STILL_THERE (under trees or too small to see), 3 MISPLACED, 4 UNSURE |
| **Possible new buildings** | 208 | by hint number | 1 NEW_BUILDING (in the imagery, not in the 2023 LiDAR), 2 NO_BUILDING, 3 UNSURE |
| **Offset or rebuilt (county + LiDAR)** | 458 | county roof under 10% (60), 10-50% (94), 50-80% (304); weakest roof first | What the red LiDAR piece is: 1 OFFSET (the same building; the county outline is off or the wrong shape), 2 PART_OF_EXISTING (an addition, porch or carport of it), 3 BOTH_REAL (a separate building), 4 REBUILT (its replacement; the county building is gone), 5 NOT_A_BUILDING (RV, trailer, vehicle or tree), 6 REBUILT_MERGE (its replacement, and the red pieces are one building), 7 NEEDS_EDIT (several problems; say what in a note), 8 SHED (a shed or small outbuilding, separate), 9 UNSURE |
| **3D buildings without a detailed roof** (October 26) | 726 | LOD2.0 roof (633), LOD1.2 block (92), no model (1) | 1 SIMPLE_OK, 2 NEEDS_ROOF, 3 GONE, 4 OUTLINE_WRONG, 5 UNDER_TREES, 6 CONSTRUCTION, 7 NEEDS_EDIT, 8 UNSURE |
| **Tree models (CFTree)** (October 26) | 900 | sample (300), many treetops inside (300), trunk inside a county footprint (300) | 1 ONE_TREE, 2 MERGED, 3 PART_OF_TREE, 4 NOT_A_TREE, 5 SHAPE_WRONG, 6 SHRUBS, 7 BRUSH, 8 TREE_WITH_ROOF, 9 UNSURE |
| **Tree models at tile seams** (October 26) | 235 | one item per overlapping pair | 1 SAME_TREE, 2 SPLIT_TREE, 3 SEPARATE_TREES, 4 NOT_A_TREE, 5 SHRUBS, 6 BRUSH, 7 UNSURE |
| **Trees CFTree could not model** (October 26) | 75 | no terrain beneath (38), no valid trunk (37) | 1 MISSED_TREE, 2 NOT_A_TREE, 3 UNSURE |
| **LiDAR outlines vs county** (October 26, after the rebuild) | 6,622 | a sample of 40 per class first: reshaped, LiDAR joins, LiDAR splits, tangles, county only, LiDAR only | 1 LIDAR_RIGHT, 2 KEEP_UNITS, 3 COUNTY_RIGHT, 4 GONE, 5 UNDER_TREES, 6 NOT_A_BUILDING, 7 NEEDS_EDIT, 8 SHED, 9 UNSURE |

The four October 26 queues, their side views of each tree and how they were chosen: [model-review](../../2026-10-26/model-review/README.md).

- **Candidates:** "Large and tall" is 150 m² or more with a P95 height of at least 6 m. "Detached" is more than 2 m from
  a county footprint, and "against a county building" 2 m or less. The facts are area, median and P95 height (m and ft),
  roof support, the nearest county building with its distance, and the parcel. **The queue is blind to Overture**: the
  page carries no Overture outline, id or flag for it.
- **Likely type (candidates):** a highlighted guess above the facts, from the LiDAR and the 2025-tax-year parcel
  snapshot only. LiDAR can't see walls, so a garage and a carport of the same size and roof look alike. The guess uses:
  - **size and P95 height;**
  - **roof form:** P95 minus median height is under 0.2 m for flat or nearly flat roofs, 0.2-0.45 m for a low slope,
    and more above that for pitched;
  - **distance to a county building:** 2 m or less reads as an addition, porch, patio cover or eave;
  - **the parcel:** land use (R residential, C commercial, I industrial), and the assessor's housing units and year
    built of the main building;
  - **the county footprints on the parcel.** A house-sized candidate on a one-unit residential parcel with no county
    building reads as "House: the parcel's main building, built YYYY, with no county footprint".

  The facts also list the roof form, the parcel's use and property-type code, the assessor's main-building figures (year
  built, building ft², units) and the number of county buildings on the parcel. The county and new-building queues get
  the parcel use and assessor figures too. Across the 6,213:

  | Likely type | n |
  |---|---:|
  | Attached to a county building: addition, porch, patio cover or eave | 3,775 |
  | Shed or single garage | 724 |
  | Carport, shade or patio cover | 328 |
  | Small shed, playhouse or shade structure | 301 |
  | Large garage, workshop or covered parking | 199 |
  | Large garage, barn or carport row | 156 |
  | Carport or covered parking | 139 |
  | Garage or large shed | 125 |
  | Covered parking, canopy or low commercial structure | 117 |
  | **House: the parcel's main building, with no county footprint** | **116** |
  | Large low structure: covered parking, warehouse or canopy | 47 |
  | Small tall structure (shed, tower, tree?) | 46 |
  | Large building: apartments, commercial or institutional | 42 |
  | Commercial/industrial building | 29 |
  | House-sized: ADU, second house or large garage with living space | 27 |
  | Two-storey garage or small ADU | 25 |
  | House or small multi-unit building; House-sized: ADU or unmapped house | 17 |

  The guesses are hints and the answer is still Brian's. The 116 houses (for example, LC00115 and LC00128, both on
  parcels whose house was built in 2018) are the clearest gaps in the county layer. `footprint_review.bat facts`
  refreshes the facts in place without rebuilding the chips; it is safe while the page is open.
- **County footprints:** the footprints in `buildings.gdb/building_heights` with under 10% roof support, or no roof
  cells at all (very small footprints). The facts include how much of the footprint is under canopy of 2 m or more,
  which points to "still there, under trees". The LiDAR view shows whether trees cover it.
- **Possible new buildings:** where the 2025 imagery may show a building the 2023 LiDAR can't. The hints are the
  Overture comparison's outlines with no LiDAR roof and no county footprint (OVERTURE_ONLY + NO_ROOF), used internally to
  say where to look, which ODbL allows. The page shows only a yellow box (the outline's extent plus 5 m) and never the
  Overture outline. Items are numbered NB0001-NB0208; their Overture ids stay in `data\newbuild-hints.json` on the SSD.
  **A confirmed new building must be digitised from the imagery or reported to the County, not copied from Overture.**
  Nothing Overture-derived goes into the output layer.
- **Corner of the same roof** (added October 23, from Brian's answers). Brian pointed out that some LiDAR "buildings"
  are a small uncovered corner of a county house whose outline is a little off: PR724355 / LC02031, a 10 m² piece
  beside a 271 m² house, 0.6 m below its median roof. Its 52% roof support comes from trees over the west half, not
  from the outline. Sliding the county outline up to 3 m did not explain it (roof only rose from 52% to 65%). Size did:
  - **The rule:** a piece within 2 m of a county building is a corner or edge of its roof when it is under 15 m²,
    under 10% of that building's area, and its median roof is between 1.5 m below and 1 m above the building's.
  - **Why these numbers:** the four pieces Brian called BOTH_REAL are 17-77 m² and 13-85% of their building, so the
    rule keeps clear of all of them. That rests on one positive example, so widen it only when more answers support it.
  - **What it changes:** 406 candidates move to the group "Corner or edge of a county roof", and 24 pairs get the guess
    "…answer Offset". Candidates more than 1.5 m below the building's roof go to "Lower roof against a county
    building" (1,386: porches, patio covers, carports, additions); the rest stay as "other" (1,883).
  - **Shown on the page:** each candidate's facts include "Roof vs nearest county building" (height difference and
    share of area). `footprint_review.bat facts` applied it in place, and Brian's 28 answers were unchanged.
- **County outline vs the LiDAR** (added October 23): every candidate, pair and county item says how its county outline
  sits on the 2023 roof, from [county-alignment](../county-alignment/README.md): aligned, offset (distance and
  direction), trees over it, part roofed, or rebuilt or gone. That study found no systematic shift in the county layer
  (median 0.36 m per building, no shared neighbourhood shift). Realigning outlines explains only 4 candidates and 2
  pairs, which move to the last group, "Explained by realigning the county outline".
- **USA Structures vote** (October 23, [usa-structures](../usa-structures/README.md)): every candidate, county
  no-roof item, new-building hint and pair shows whether FEMA/ORNL USA Structures has a structure there, with its
  imagery date. Here that is mostly 2010, and it lists nothing under 42 m², so a "yes" means a structure stood there
  then, not necessarily this building.
- **Sample first** (October 23, [review-reduction](../review-reduction/README.md)): the attached candidates are now
  grouped "Sample: answer these first" (300, pre-registered in PROTOCOL.md), "Needs eyes" (443), then the earlier
  attached groups (2,928). Answering the sample lets a pre-registered rule settle up to 3,228 attached pieces, if Brian
  adopts it.
- **Answers revised** (October 23, after Brian hit an RV in the pairs queue). The pairs question now asks what the red
  LiDAR piece is, with six answers instead of four, adding Part of it and Not a building. Keys 1 (Offset) and 3 (Both
  real) kept their meaning; Rebuilt moved from 2 to 4 and Unsure from 4 to 6. The candidates queue splits Reject into
  3 VEHICLE (RV, trailer or vehicle) and 4 REJECT (tree or other), and Unsure moved to 5. Brian had used none of the
  moved keys in the candidates queue; all his answers keep their codes.
- **Length × width and a vehicle hint.** Every candidate shows its length × width (minimum rotated rectangle). The
  guess starts "Possibly a vehicle (RV, trailer or truck…)" when the piece is 12-45 m², at most 3.3 m wide, at least
  2.5 times as long as wide, 2.3-4.5 m high and flat or low slope, and more than 2 m from a county building. Nearer
  than that, the same shape is usually an eave or porch strip; the first version without that rule flagged 792. With
  it: 103 detached candidates and 2 pairs. LC00057, a 12.7 × 3 m box on a gravel lot that is gone in the 2025
  imagery, is one. "Roof vs nearest county building" now shows only within 10 m.
- **Offset or rebuilt** (added October 23, after Brian's first answers): county footprints whose outline is slightly
  off, or whose building was rebuilt beside or over its old footprint. These are the county footprints with under 80%
  2023 roof support and a LiDAR candidate within 3 m: 458 footprints and 489 candidates. Each item draws the county
  outline in magenta and the candidates beside it in red, on both views. The facts give the county roof support, the
  candidates' sizes, their combined area against the county outline, how much of the outline lies within 3 m of them,
  and the parcel. Any answer already given on those candidates in the first queue appears as "Your answer on LC…".
  Among Brian's first 23 answers, LC00292 (PART_OF_EXISTING) is one: a 197 m² LiDAR building wrapped around a 65 m²
  county outline with 25% roof. Added with `footprint_review.bat add-pairs`, which writes new bundle files (p0001…) and
  appends to the index without touching other items or answers; restart `serve` afterwards.

- **Compound pairs and lost notes** (October 26). Brian met pairs with several problems at once: the county building
  gone and the red pieces really one building, or more needing hand edits. Two answers were added: 6 REBUILT_MERGE
  (its replacement, and the red pieces are one building) and 7 NEEDS_EDIT (several problems; say what in a note).
  UNSURE moved from 6 to 8; he had not used it in this queue. His first notes of the day never reached the server: the
  note box was wiped whenever the page moved to another item, so a note typed before answering, or before moving on,
  was lost. A typed note is now kept per item (in the browser) until it is saved with an answer, and Enter in the note
  on an unanswered item keeps it and asks for the answer key. Later the same day: 8 SHED (UNSURE to 9, still unused
  here), and "Part of it" now reads "recombine with the county building".

## How long it should take
From Brian's own pace on the label page (968 answers: median 4 s per answer, about 6 s on average including short pauses),
plus about a second for the next item to appear:

| Queue / group | Items | Seconds each (estimate) | Time | Sittings of about 45 minutes |
|---|---:|---:|---:|---:|
| Large and tall | 252 | 8 | about 35 min | 1 |
| Detached | 2,286 | 6 | about 3 h 50 min | 5 |
| Against a county building | 3,675 | 5 | about 5 h 10 min | 7 |
| County footprints with no 2023 roof | 586 | 10 | about 1 h 40 min | 2 |
| Possible new buildings | 208 | 10 | about 35 min | 1 |
| Offset or rebuilt | 458 | 10 | about 1 h 15 min | 2 |
| **All** | **7,465** | | **about 13 h 5 min** | **18** |

The group against a county building is the biggest and most repetitive. A suggestion, Brian's call: answer its first 300
or so, and if nearly all are PART_OF_EXISTING or REJECT, decide whether the rest need a look one by one. That would bring
the total to about 8 hours.

## Pilot (October 23)
The page was first built for 20 candidates (7 large and tall, 7 detached, 6 against a county building;
`footprint_review.bat serve-pilot`, port 8771) and checked in the browser:
- **Same ground in both views:** the map and the LiDAR view cover the same square, and outlines sit on the roofs in
  both.
- **Keys:** answers save and the page moves on. The next item appears in about a second, with the next two preloaded.
- **Imagery date:** read from the World Imagery service's own footprint layer.
- **The server refused** an answer from a second reviewer, an answer from another queue's set, an unknown item, and a
  clear by another reviewer.

Those test answers (reviewer TST) were cleared; the pilot's log keeps them as its first lines. Two fixes came out of the
full build:
- **Bundles of 50 items:** the SSD allocates 1 MB per file, so one file per item would have used some 14 GB.
- **No NaN in the data:** empty county fields were written as NaN, which browsers reject. The builder now writes "—" and
  refuses NaN outright; the first full build is in `superseded\`.

## Files
| File | Meaning |
|---|---|
| [footprint_review.bat](footprint_review.bat) | serve, backup, build, add-pairs, facts, serve-pilot |
| [serve_footprint_review.py](serve_footprint_review.py) | the local server and `backup` |
| [build_review_data.py](build_review_data.py) | builds `data\index.json` and `data\bundles\b*.json` (chips as PNG data URIs) |
| index.html, app.js, style.css | the page (Leaflet 1.9.4 from cdnjs) |
| `H:\lidar\2023-salt-lake-valley\runs\footprint-review-20261023\data` | the page data and the live answers (data\answers) |
| answers/footprint-review-answers.csv | the repo backup of the answers (created by the first backup) |

## Next
After the review, not now: the merged footprint set. That is the county footprints plus the accepted candidates, with
PART_OF_EXISTING merged into their county footprint, DEMOLISHED flagged, MISPLACED listed for the County, and
NEW_BUILDING sites digitised from the imagery.
