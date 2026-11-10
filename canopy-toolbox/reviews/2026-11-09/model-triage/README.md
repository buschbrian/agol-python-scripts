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

**Later answers not used here.** These tests graded the 113 tree answers in the repo backup at the time. The page's live file already
held 117 more from November 9, including trees of 8 m and up. They were not read by the model or used in this result.

## Test C, held out: the 116 newer tree answers (rules fixed November 10, before any read)

The tree-sample answers Brian gave on November 9 that test B did not use: 116 with an answer (109 at 8 m and up, 7 under 8 m).
The question, simple codes, brief, sheet layout, model (Sonnet 5.5) and effort (medium) are the same as test B.

- **C-8plus is judged** by the pass rule above, per direction. It is the only test of trees 8 m and up.
- **C-under8 (7 items) is reported only.** It is too small to judge.
- **The cues from the checks above are reported on the same items**, unchanged: under 3 m, low and wide, 25% over county footprints
  or trunk inside one, six or more treetops or wider than 15 m. A PROBLEM direction that passes is preferred as a cue rule, not a
  model, if the cues match its rate within 5 points.

Sheets come from `export_tests.py OUT KEY`, where KEY is test A and B's `key.csv`, so no test B tree is read again.

### Test C results (Sonnet 5.5, medium; every reviewer's replies confirmed as Sonnet 5.5 in its transcript)

**C-8plus, trees 8 m and up: both directions pass.** 91 of 109 scorable (30 one tree, 61 a problem); 3 model UNSURE.
- ONE_TREE at high confidence: 16 of 18 (88.9%, 95% interval 67-97%), above the 67% majority share. **Passes.** The two misses were
  PART_OF_TREE and MERGED.
- PROBLEM at high confidence: 21 of 22 (95.5%, 78-99%). **Passes.**
- 40 of 91 (44%) got a high-confidence call. At any confidence, 68 of 88 answered calls matched.

**Cues on the same items:** 30 flagged, 28 problems (93.3%, 79-98%), almost all from the merged cue (24 of 26). That is within 5 points
of the model's PROBLEM rate, so by the rule fixed above, **use the cues, not the model, to flag problems**. 18 of the model's 22
PROBLEM calls are also flagged by a cue. The cues cannot say a tree is fine, so **ONE_TREE is the one call only the model adds**.

**C-under8:** 6 scorable, all 6 matched. Reported only.

**Limits.** A pass here is on a random height-band sample. The open tall trees are in the merged (244) and over-roof (195) queues,
which were chosen by the same cues the model saw as facts. Their mix of problems is different, so the ONE_TREE rate is not
established there until Brian answers a blind sample from them. The tree sample's 30 open trees of 20 m and up stay his, because
they measure the error rates.

## The open tall trees and a blind spot-check (rules fixed November 10, before any read)

Brian, November 10: run the model on the open trees 8 m and up in the merged and over-roof queues, then check it blind.

1. Sonnet 5.5 (medium) reads every open tree of 8 m and up in `merged` and `over_roof` (439 when counted), with test C's question,
   brief and sheets (`export_tests.py OUT --open-tall`).
2. `spot_check.py add` moves 30 random confident ONE_TREE calls (seed 20261110) and 15 random other trees into one new group,
   "Spot-check: answer these first", in random order. The page shows no model call, and nothing on it tells checks from filler.
3. Brian answers that group with the usual tree answers. `spot_check.py score` then applies the rule.

**Pass rule:** at least 20 of the 30 checks answered other than UNSURE, and at least 85% of those answered ONE_TREE.

**If it passes,** the other confident ONE_TREE calls are a proposal only: "one tree, by the model, spot-checked". Nothing is settled
until Brian agrees, and none of it is ever written into his answers file. Problems are left to the cues (test C). If it fails, every
tree stays his.

### The open tall trees: the spot-check was not set up

Sonnet 5.5 read all 439 (every reviewer confirmed as Sonnet 5.5). Calls are in `runs\model-triage-open-20261110\results` on H:, not in git.

| Queue | Trees | ONE_TREE, high | PROBLEM, high | Medium or low | UNSURE |
|---|---:|---:|---:|---:|---:|
| merged | 244 | 23 | 91 | 124 | 6 |
| over_roof | 195 | 3 | 97 | 86 | 9 |

Only 26 confident ONE_TREE calls exist, fewer than the 30 checks the rule asked for. A spot-check would take all 26 and leave
nothing to settle, so it would cost Brian 41 answers and save none. It was not added to the page, and the page's data is unchanged.
The 188 confident PROBLEM calls add little, because these queues were already chosen by the problem cues that test C found right
93% of the time.
