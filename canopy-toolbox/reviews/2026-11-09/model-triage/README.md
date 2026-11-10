# Can a model take the simple calls? Two blind tests (November 9, 2026)

Brian asked which review items a model could take. These two tests ask one simple question per item and grade it against
answers he has already given. Nothing here changes `footprint-review-answers.csv`, a public layer or a training label.

## Rules fixed before any model read a sheet

**Test A, small outlines (31 items).** The `outlines` queue items Brian answered in groups `decide_small` (15) and
`auto_vehicles` (16). None of these were used in the first model pass. Question: real structure or not?
- REAL_STRUCTURE = his SHED, PART_OF_BUILDING, OFFSET_SHED or LIDAR_RIGHT.
- NOT_STRUCTURE = his NOT_A_BUILDING or VEHICLE.
- Any other answer of his is not scored.

The 24 `small` items from the first pass are read too and reported as a secondary tally. They do not count toward the rule,
because this simple question was chosen after seeing how the models did on them.

**Test B, tree models (113 items).** The `trees` sample items Brian answered. Question: one good tree, or a problem?
- ONE_TREE = his ONE_TREE.
- PROBLEM = his SHRUBS, BRUSH, MERGED, PART_OF_TREE, NOT_A_TREE, SHAPE_WRONG or TREE_WITH_ROOF.
- UNSURE is not scored.

**Pass rule, per test and per direction** (for example "NOT_STRUCTURE" in Test A):
1. At least 10 scored items where the model made that call at high confidence.
2. At least 85% of those match Brian.
3. That match rate is above the share of that direction's majority answer among the same scored items, so always giving
   one answer cannot pass.

A direction that passes may settle open items provisionally, only at high confidence, and only after Brian has spot-checked a
random sample of them. Every other item stays with him. An UNSURE from the model is never settled.

**Limits known in advance.** Test B's 113 answers are all trees under 8 m (59 in the 2-5 m band, 54 in 5-8 m), so a pass covers
only trees under 8 m. Test A is small and vehicle-heavy.

## Method

`export_tests.py` draws one blind sheet per item from the review page's data and local NAIP 2024 (no Esri World Imagery, no
UGRC Discover), with opaque sheet numbers. Tree sheets add the page's two side views. Models get the sheet and a short list of
facts. They do not get the item id, group, address, parcel, rule proposal or any answer of Brian's. `grade_tests.py` applies the
rule above and writes `results/`.

## Results (Sonnet 5.5, medium effort, one read per sheet)

The brief gained one sentence explaining the side views' black crown shape and brown trunk after the sheets were checked and
before any model read them. The rules above did not change. `results/` holds every call and `summary.json`.

**Test A, small outlines: failed.** 28 of 31 were scorable (8 real structures, 20 not). Sonnet made only 2 high-confidence calls,
both right, and none for REAL_STRUCTURE, so neither direction reached 10. At any confidence, 17 of 22 answered calls matched, and
6 were UNSURE. Its REAL_STRUCTURE calls were right on 7 of 12.

An observation, not a pass: all 13 NOT_STRUCTURE calls across Test A and the secondary tally matched Brian (10 and 3, 95%
interval 77-100%). This pattern was noticed after grading, on a mix of confidence levels, so it needs fresh items.

**Test B, tree models: PROBLEM passed, ONE_TREE did not.** 107 of 113 were scorable (37 one tree, 70 a problem).
- PROBLEM at high confidence: 31 of 35 matched (88.6%, 95% interval 74-95%), above the 65.4% majority share. **Passes**.
- ONE_TREE at high confidence: 7 of 8. Too few to pass.
- All answered calls: 77 of 106. Of the 14 problems called ONE_TREE, 6 were SHAPE_WRONG.

**What the pass allows, in practice: almost nothing.** Open trees under 8 m are 7 in the sample, 56 merged and 105 over roofs; the
619 open trees of 8 m or more are not covered. The sample's 7 must stay human, because settling them by model confidence would
bias the error rates the sample exists to measure. The merged and over-roof queues were picked by the same cues the model saw as
facts, and Brian has answered none of them, so this test says nothing about them. PROBLEM is not an answer on the review page and
does not say which fix applies. Nothing was run on open items. `footprint-review-answers.csv` was checked unchanged (SHA-256
before and after).

## Checks after grading

**The measured cues do as well as the model, for free.** The October 26 proposed thresholds in `../../2026-10-26/STATUS.md`, unchanged
and set before these answers existed (under 3 m; low and wide; 25% over county footprints or trunk inside one; six or more
treetops or wider than 15 m), flag 24 of the 107 scored trees, and 22 of those are problems (91.7%). Sonnet's high-confidence
PROBLEM calls: 31 of 35 (88.6%). 21 of those 35 are also flagged by a cue. Prefer the cues.

**The 13 NOT_STRUCTURE matches are mostly the vehicle rule again.** 7 are in the group already settled by the vehicle-shape rule, where
14 of 15 scored answers are NOT_STRUCTURE. 6 are from the small-outline groups.
