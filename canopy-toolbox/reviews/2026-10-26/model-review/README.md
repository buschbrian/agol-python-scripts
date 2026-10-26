# 3D building and tree model review (October 26, 2026)

Brian asked for a reviewable queue of the roofs and the CFTree trees, built "in here like the other reviewing". These
are four new queues on the existing [footprint review page](../../2026-10-23/footprint-review/README.md), not a hosted
layer. His reason: an old County footprint can stand for a building that is gone, which is one reason roofer made no
model. A missing or fallback model is a cue to look, never a demolition finding. **Everything here is an unvalidated
planning estimate from the 2023 LiDAR (October-November); nothing is uploaded.**

This replaces Codex's private ArcGIS Online review layer (`../gis-review`): `upload_review.py` and
`configure_online.py` stay unexecuted drafts. Its cue rules are reused: the seam rule and the trunk-in-footprint test
below are the same as in `gis-review/review_rules.py`.

## Start

```
canopy-toolbox\reviews\2026-10-23\footprint-review\footprint_review.bat serve
```

Pick a queue at the top. Keys, answers and backups work as in the other queues; the answers go to the same CSV.

## The queues

Sizes from `queues.py` (all 22,042 County footprints, all 119,410 CFTree models, all 527,140 October 22 treetops):

| Queue | Items | What it asks | Answers (key order) |
|---|---:|---|---|
| **3D buildings without a detailed roof** | 726 | The three-way hybrid used a fallback here. What is there? | SIMPLE_OK, NEEDS_ROOF, GONE, OUTLINE_WRONG, UNDER_TREES, CONSTRUCTION, NEEDS_EDIT, UNSURE |
| **Tree models (CFTree)** | 900 | Is the red model one tree? | ONE_TREE, MERGED, PART_OF_TREE, NOT_A_TREE, SHAPE_WRONG, SHRUBS, BRUSH, TREE_WITH_ROOF, UNSURE |
| **Tree models at tile seams** | 235 | Red and magenta come from neighbouring tiles and overlap. What are they? | SAME_TREE, SPLIT_TREE, SEPARATE_TREES, NOT_A_TREE, SHRUBS, BRUSH, UNSURE |
| **Trees CFTree could not model** | 75 | Is there a tree here? | MISSED_TREE, NOT_A_TREE, UNSURE |

**3D buildings.** Of the 22,042 footprints, 20,730 have a roofer LoD 2.2 roof. The other 1,312 are 481 with no model,
184 Esri LOD1.2 blocks and 647 Esri LOD2.0 roofs. **480 of the 481 with no model are already in the queue "County
footprints with no 2023 roof"**, so they are not asked again. The new queue holds the other 726: 633 LOD2.0 roofs (599 where roofer's
roof was broken), 92 LOD1.2 blocks (mostly too few roof points for either model), and one footprint with no model.
Groups are by model; within a group, weakest roof support first. Each item shows the model and why it fell back. The
other facts are the same as the county queue: roof support, canopy over the footprint, parcel and assessor, and
how the outline sits on the LiDAR. A footprint also in the "offset or rebuilt" queue shows that answer.

**Trees.** Each item shows the crown outline (convex hull of the CFTree crown mesh) and the inferred trunk as a dot. Below
the LiDAR view there are **two side views**: the model's own LiDAR points (red), other vegetation within 6 m (grey), the
crown mesh silhouette (black), the inferred trunk (brown box) and the trunk base. Groups:

- **Sample: answer these first** (300): random within five height bands (2-5, 5-8, 8-12, 12-20, 20 m and up; 60 each),
  seed 20261026, drawn before any cue was looked at. These give the error rates.
- **Many treetops inside (merged?)** (300): 100 each with 3-5, 6-10 and 11 or more October 22 treetops inside the
  outline.
- **Trunk inside a county footprint** (300 of 1,610, random): roof contamination, or a tree overhanging a roof.

**Seams.** CFTree ran each 1 km tile with a 100 m halo. Each segment belongs to the tile holding its highest point, but
crowns can still be cut or doubled at tile edges. 237 pairs (404 models) are from different tiles, both near an edge, and
share at least 70% of the smaller outline. A model overlapping two others is paired with the one it shares most with,
so the queue has 235 items covering all 404 models.

**Rejects.** These are all 75 exclusions: 38 with no terrain beneath and 37 with no valid trunk. The dot is the segment's
highest return, and the side view shows its points.

**Answers added after the first sitting** (October 26). Brian found models built from several shrubs, low or dead
trees mixed in beside live ones, and trees that take in part of a roof. Three answers were added: 6 SHRUBS (low shrubs
or a hedge), 7 BRUSH (brush or a scrub thicket taken as one tree) and 8 TREE_WITH_ROOF. UNSURE moved from 6 to 9; he
had not used it. Low or dead trees beside live ones count as MERGED. His two earlier NOT_A_TREE answers predate the
new options and may be worth a second look.

**After the second sitting** (October 26). In the roof queue Brian found sites rebuilt or under construction, such as
MD733329: a new building where two county footprints are demolished buildings and the third is drawn wrong. That
footprint has 21% roof support, an 87 ft median height (a crane or a frame) and no assessor building on its parcel. Two
answers were added: 6 CONSTRUCTION (under construction in 2023, or rebuilt since) and 7 NEEDS_EDIT (several problems;
say what in a note). The seam queue gained 5 SHRUBS and 6 BRUSH. Neither queue had answers yet, so UNSURE moved to the end.

He also found the side views hard to read on slopes and in big shrub patches. They now colour each point by its height
above the October 22 terrain at that point: points under 2 m (the threshold CFTree and the canopy products use) are
pale, orange for this model and pink for the other. They also draw the terrain under the view's centre line and a dashed line 2 m
above it. The views were redrawn in place with `add_model_queues.py --refresh-profiles`, which changes only the images.

## How long it should take

At the pace the October 23 page assumed (about 10 seconds an item where two views have to be compared):

| Queue / group | Items | Time |
|---|---:|---:|
| Tree sample (answer first) | 300 | about 50 min |
| Merged? and trunk in a footprint | 600 | about 1 h 40 min |
| Tile seams | 235 | about 40 min |
| Trees CFTree could not model | 75 | about 10 min |
| 3D buildings without a detailed roof | 726 | about 2 h |
| **All** | **1,936** | **about 5 h 20 min** |

The tree sample alone decides most of what happens next: whether the CFTree models are good enough to publish, and
whether merging needs a second segmentation pass.

## What the counts already say

The October 22 products have 527,140 treetops; CFTree made 119,410 models. **The gap is mostly merging, not missed
trees.** 481,200 treetops (91%) fall inside a CFTree outline, and the 45,940 outside are mostly small: 30,331 are under
5 m. Inside the outlines, 62,049 models (52%) hold 3 or more treetops and 8,692 hold more than 10. The page can't tell
from counts alone whether CFTree merges neighbouring crowns (segmentation 2.5/1.5/3, at least 50 points) or the October
22 detector splits one crown into several peaks (every local maximum is a seed; 32,986 are flagged SUSPECT). The
"merged?" group is built to answer that.

## Not reviewable here

- **Trunk diameter and height** come from allometry and the terrain, not from the LiDAR. They need field measurements,
  not imagery.
- **Accuracy of crown shape** beyond "badly off": the side views compare the mesh with its own points only.

## How the answers map to the earlier vocabulary

Codex's draft review layer (`gis-review/review_rules.py`) had longer decision codes. If a hosted layer comes later:

| Here | Codex `ROOF_DECISIONS` / `TREE_DECISIONS` |
|---|---|
| SIMPLE_OK | present_match |
| NEEDS_ROOF | present_model_issue |
| GONE | absent_2023 (or removed_after_2023 when dated evidence says so) |
| OUTLINE_WRONG | footprint_mismatch |
| UNDER_TREES | present_model_issue, with a note |
| ONE_TREE | accept_model |
| MERGED | merged_trees |
| PART_OF_TREE, SAME_TREE, SPLIT_TREE | split_duplicate |
| NOT_A_TREE | not_tree |
| SHAPE_WRONG | geometry_issue |
| SHRUBS, BRUSH | not_tree (a shrub or brush class would need adding) |
| TREE_WITH_ROOF | geometry_issue, with a note |
| MISSED_TREE | tree_reprocess |

## Files and reproduction

| File | Meaning |
|---|---|
| [queues.py](queues.py) | sizes every queue (ArcPy-free); writes `roof-queue.csv`, `tree-cues.csv`, `tree-outlines.parquet`, `summary.json` to `runs\model-review-20261026` |
| [add_model_queues.py](add_model_queues.py) | appends the four queues to the page data (bundles `m0001...`); `--pilot` writes 5 items per queue to a separate folder |
| [summary.json](summary.json) | the counts above, copied from the run |
| [cues.py](cues.py) | measures Brian's reported problems on every tree and candidate; [cues-summary.json](cues-summary.json), [redeveloped-sites.csv](redeveloped-sites.csv) (per-model flags in `runs\model-review-20261026\tree-flags.csv`) |

```
footprint_review.bat model-queues     (about 10 minutes)
footprint_review.bat add-models       (once; refuses if the queues are already there; then restart serve)
footprint_review.bat serve-model-pilot
```

Inputs: `millcreek-products-20261022` (County footprints, rasters, treetops). The three-way hybrid's levels come from
`buildings_hybrid_v2_feet.csv`, the CSV Codex published to Azure, because the multipatch layer can't be read without
ArcPy. The CFTree run is `C:\Users\Brian\Documents\Codex\2026-10-24\go-x20\work\cftree-city-20261025` (config hash in
summary.json): its CityJSON shards, `models.sqlite` for model-to-segment links, and `segmentation.xyz` for the points.
That run is on C: and its segmentation files are not in the H: handoff copy, so rebuild the tree queues on this machine.

Map outlines go through Web Mercator on the ITRF08 datum. ArcPy's `WGS_1984_(ITRF08)_To_NAD_1983_2011`, sampled on a
6 × 6 grid over the city, is fitted as a plane on top of pyproj. It is about 1.3 m west and 0.9 m north, varying by 3 mm
across the city. Before the build continues, the fit is checked against 200 County footprints' own ArcPy-projected web
copies.
