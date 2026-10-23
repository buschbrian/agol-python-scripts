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
| 1 to 4 | answer (the buttons show which is which) |
| → or Enter, ← | next, previous |
| Backspace | clear this item's answer |
| N | type a note (Enter saves it with the answer, Esc leaves the box) |
| R | reset the map view |

"Show: Unanswered" (the default) resumes where you stopped. "Group" narrows a queue, and "All" or "Answered" let you go
back over answers.

## Queues
| Queue | Items | Order | Answers |
|---|---:|---|---|
| **LiDAR candidates** ([footprint-candidates](../footprint-candidates/README.md)) | 6,213 | large and tall (252), then detached (2,286), then against a county building (3,675); north to south within each | 1 ACCEPT (a separate building), 2 PART_OF_EXISTING (an addition, porch or eave strip of the neighbouring county footprint), 3 REJECT, 4 UNSURE |
| **County footprints with no 2023 roof** | 586 | by county ID | 1 DEMOLISHED, 2 STILL_THERE (under trees or too small to see), 3 MISPLACED, 4 UNSURE |
| **Possible new buildings** | 208 | by hint number | 1 NEW_BUILDING (in the imagery, not in the 2023 LiDAR), 2 NO_BUILDING, 3 UNSURE |

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
| **All** | **7,007** | | **about 11 h 50 min** | **16** |

The group against a county building is the biggest and most repetitive. A suggestion, Brian's call: answer its first 300
or so, and if nearly all are PART_OF_EXISTING or REJECT, decide whether the rest need a look one by one. That would bring
the total to about 7 hours.

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
| [footprint_review.bat](footprint_review.bat) | serve, backup, build, facts, serve-pilot |
| [serve_footprint_review.py](serve_footprint_review.py) | the local server and `backup` |
| [build_review_data.py](build_review_data.py) | builds `data\index.json` and `data\bundles\b*.json` (chips as PNG data URIs) |
| index.html, app.js, style.css | the page (Leaflet 1.9.4 from cdnjs) |
| `H:\lidar\2023-salt-lake-valley\runs\footprint-review-20261023\data` | the page data and the live answers (data\answers) |
| answers/footprint-review-answers.csv | the repo backup of the answers (created by the first backup) |

## Next
After the review, not now: the merged footprint set. That is the county footprints plus the accepted candidates, with
PART_OF_EXISTING merged into their county footprint, DEMOLISHED flagged, MISPLACED listed for the County, and
NEW_BUILDING sites digitised from the imagery.
