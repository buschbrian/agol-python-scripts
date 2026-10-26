# Millcreek LiDAR project: where it stands (end of October 26, 2026)

One page for picking the project up. Details are in the linked records; `../../AGENTS.md` routes everything else.

## Released

- **Eight hosted layers from the 2023 LiDAR** (terrain and slope, canopy, treetops and crowns, building heights), public
  since the evening of October 23, with cartography, three web maps and a 3D scene. The three Instant Apps are private
  ([PUBLISHING.md](../2026-10-23/PUBLISHING.md), [agol-styling](../2026-10-23/agol-styling), [agol-apps](../2026-10-23/agol-apps)).
- **3D buildings with roof forms** (October 25): the three-way hybrid (roofer LoD 2.2 on 20,730 footprints, Esri LOD2.0
  or LOD1.2 on the rest), public in the buildings scene and as an Azure SLPK and feet CSV. The old layer is kept for rollback
  ([buildings-release](../2026-10-25/buildings-release/README.md)). The Buildings in 3D Instant App is still private.
- **Feet and square feet** in pop-ups, the CSV and the app text ([feet-context](../2026-10-25/feet-context/README.md)).

All of it is labelled an unvalidated planning estimate.

## Built, not released

- **CFTree trees** (October 25-26): 119,410 draft crown-and-trunk models on all 61 tiles, 75 rejected candidates. Local
  only, on C: in the Codex work folder, with a CityJSON copy on H: ([cftree-city](../2026-10-25/cftree-city/README.md)).
- **The footprint, roof and tree review page** with eight queues ([footprint-review](../2026-10-23/footprint-review/README.md),
  [model-review](model-review/README.md)). It runs on this machine only: `footprint_review.bat serve`.

## Review so far (104 answers by Brian)

| Queue | Answered | What the answers say |
|---|---:|---|
| LiDAR candidates, large and tall | 30 of 252 | 26 separate buildings the county layer lacks, 3 parts of an existing one, 1 unsure |
| Possible new buildings | 12 of 208 | 3 new buildings (NB0005, NB0010, NB0013), 7 nothing there, 2 unsure |
| Offset or rebuilt | 14 of 458 | 5 rebuilt, 5 both real, 2 offset, 2 not a building |
| Trees CFTree could not model | 43 of 75 | **36 not a tree**, 7 unsure: the exclusions are mostly right |
| Tree models (sample first) | 5 of 900 | too few to say anything yet |
| 3D buildings without a detailed roof, county no-roof, tile seams | 0 | not started |

**Notes were lost.** None of the 104 answers has a note: the page wiped a typed note whenever it moved to another item,
and Brian's tab ran the old page until it was reloaded at the end of the day. The page is fixed (a typed note is kept
until it is saved with an answer). What he reported aloud instead, in the Claude Code session of October 26:

- Trees: models that join two or three trees; models built from several shrubs, from low or dead trees beside live
  ones, and from big patches of dense shrubs or scrub; models that take in roofs, or sheds under the crown; and
  hard-to-read side views on sloping ground. CFTree's rejects are mostly low ground clutter, or points on raised
  surfaces with no terrain beneath.
- Roofs: many fallback models are buildings under construction or rebuilt since. MD733329 is a new building where two
  county footprints are demolished buildings and the third is drawn wrong.
- Footprints: LC01389 is a case where the LiDAR is right and the county's four or five outlines are a hodgepodge. Pairs
  can be several problems at once: the county building gone and two LiDAR pieces that are one building.

The page gained answers for each: SHRUBS, BRUSH and TREE_WITH_ROOF (trees), SHRUBS and BRUSH (seams), CONSTRUCTION and
NEEDS_EDIT (roofs), REBUILT_MERGE, NEEDS_EDIT and SHED (pairs). Side views now show the ground and a 2 m line.

## What the measurements say

From [model-review/cues.py](model-review/cues.py), on every tree model and candidate:

- **The 527,140 treetops vs 119,410 trees gap is merging, not missed trees.** 91% of the October 22 treetops fall inside
  a CFTree outline. Half the models hold three or more, and 29,622 hold six or more or are wider than 15 m.
- **Brian's tree problems, sized** (thresholds are proposals until the 300-tree sample is answered):
  - 3,499 under 3 m tall. CFTree keeps vegetation from 2 m up, so these are tall shrubs and hedges, not ground cover.
  - 1,162 low, wide masses: under 6 m, at least 40 m² of crown, less than half as tall as wide (brush, scrub oak).
  - 5,267 over roofs or sheds: a quarter of the outline over a county footprint or a LiDAR candidate building, or the
    trunk inside a footprint.
  - 22,134 on ground that rises 3 m or more under the crown (the east bench and the canyons). This is not a model error:
    it is what made the side views hard to read, and they now draw the ground.
- **Redeveloped sites like LC01389:** 12 LiDAR buildings of 100 m² or more sit within 3 m of two or more county
  outlines under 80% roof support (`runs\model-review-20261026\redeveloped-sites.csv`). They touch 25 county footprints:
  12 in the roof queue and 7 in the county no-roof queue. The Chambers Avenue site holds LC01389, LC01423 and MD733329.
  Under 50% roof support found only 5 and missed LC01389, because the new building roofs part of the old outlines.

## Later on October 26: the LiDAR is the truth for buildings

After more answers and notes, Brian decided the county footprints should be redrawn from the LiDAR rather than kept and
patched ([lidar-footprints](lidar-footprints/README.md)). Built without the county layer, the LiDAR gives 23,327 building
outlines. Against the 22,042 county footprints:
- 17,245 match one to one;
- 1,636 are reshaped;
- 2,260 sit under 1,023 LiDAR buildings that each cover several;
- 733 have no 2023 roof, 480 of them under trees;
- 3,080 LiDAR buildings have no county footprint.

His REBUILT, OFFSET and ACCEPT answers fall in the classes they should. The review page also gained a LIDAR_RIGHT answer,
and notes now save without an answer. His 12 notes typed without one are recovered.

## Next, in order

1. **Answer the 300-tree sample** with the new answers (about 50 minutes). It sets the error rates and calibrates the
   flags above. Then decide between publishing CFTree with flagged models held back, and a second run.
2. **A second CFTree run, if the sample says so:** remove points over county footprints and LiDAR candidate buildings
   before segmentation (roofs, sheds), drop or label models under 3 m, and split crowns holding several treetops. CPU
   only; about one night with two workers.
3. **Roof and footprint review:** the 726 roof fallbacks and the 586 county no-roof footprints, starting with the 12
   redeveloped sites. Then the merged footprint set planned on October 23: county footprints, plus accepted candidates and
   new buildings, minus demolished ones, with misplaced ones listed for the County.
4. **Merge PR #11** (Brian, after one Pro run of the old `CanopyTools.pyt` tools). A push to `main` copies every branch
   to the City's Azure Repos.
5. **Classification items still open from October 20** ([HANDOFF](../2026-10-20/HANDOFF.md)): 222 examples for human
   review (55 unsure), 32,986 SUSPECT treetops with calibration sample 2 ready, Q2-0010, rules 12 and 15, and whether the
   consensus building layer replaces the October 19 one.

Back up review answers after each sitting: `footprint_review.bat backup`, then commit
`reviews/2026-10-23/footprint-review/answers/footprint-review-answers.csv`.

## The other project: centerlines

`V:\Developer\millcreek-addressing-platform`, branch `codex/review-blockers`, 12 commits ahead of `origin/main` and not
pushed. The routing-lock safeguard and the VECC preflight are done. A review draft is marked NOT FOR SUBMISSION, with
84 roads to check and blocker decisions for Brian and Matt in `docs/plan.md`. 591 core tasks remain; VECC delivery is
targeted for November 30.
