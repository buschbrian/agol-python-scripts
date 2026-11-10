# Building review graded (November 10, 2026)

Brian finished every Decide, Answer and Check group of the outlines2 queue (262 answers, 121 of them since October 27).
`grade_buildings.py` adds them to the November 9 decisions and writes `runs\lidar-footprints-20261109\decisions-20261110.csv`
(copy: `decisions-20261110.csv`). The November 9 file and the answers file are not changed (SHA-256 checked). No merged layer
is built and nothing is uploaded.

| Group | Answers | What they say | Effect |
|---|---:|---|---|
| Tangles (sample) | 40 | Split into separate buildings 28, county 7, units 2, unsure 2, edit 1 | Rule: the 142 waiting are split |
| Reshaped, 10-30% canopy | 82 (all) | LiDAR 31, split 12, edit 11, county 11, add roof 9, other 8 | His answer on each; no rule needed |
| Small, under 20 m² | 40 | Shed 13, vehicle 11, part of a building 4, not a building 4, unsure 4, other 4 | Rules stand (below) |
| Touching a building (check) | 20 | Part of it 8, not a building 4, unsure 3, vehicle 2, shed 2, edit 1 | The join default fails: 286 back to waiting |

**Small-outline rules, all of his small answers by measured cue** (decide_small and the touching check):

| Cue | Answers | Right | Rule |
|---|---:|---:|---|
| Vehicle-shaped or in the street | 11 | 8 vehicles (73%) | 190 stay vehicles |
| Free-standing | 23 | 12 sheds or buildings (52%); 4 not a building, 3 vehicles | 679 stay sheds; about 1 in 3 may be wrong |
| Touching a building | 26 | 12 part of it (46%) | No rule: 286 waiting |

**Decisions now:** Brian 262, rules 5,378, waiting 286. 41 of his answers need work by hand or another look
(20 NEEDS_EDIT, 21 UNSURE); 12 ADD_TO_COUNTY and SHIFT_COUNTY answers need a geometry step that does not exist yet.

**Cleanup queue** (LoD2.2 flags): 17 of 943 answered, all in "no model" (12 outline right, 2 split, 2 edit, 1 trim).
Nothing to grade yet.
