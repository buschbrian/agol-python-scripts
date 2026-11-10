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
