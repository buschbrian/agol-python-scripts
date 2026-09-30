# Independent-evidence triage of the training-review units (September 30, 2026)

Option 2 of the labelling plan: propose a label for a unit only when evidence that does **not** come from our models
agrees, and send everything else to a person. Inputs are the raw points' geometry (never a classification byte),
County Surveyor and OSM building footprints, and the tile-wide NAIP image ([NAIP_GREENNESS.md](../2026-09-29/NAIP_GREENNESS.md)).
Baseline classes, the Esri tree and building models and the shape-gate rules are **not** inputs, because the project rule
is that model output, baseline classes and rule codes are never truth.

Code: [canopy/triage.py](../../canopy/triage.py) (rules, no ArcPy, 10 tests), [triage_units.py](triage_units.py) (reads the
points, NAIP and footprints; read-only; about 70 s for all units). Results: [triage/](triage/).

A proposal is a suggestion, not a label. Nothing is written to the review geodatabase by this step.

## What it found on the 1,065 units of 12TVL2804

| | Units |
|---|---:|
| AUTO candidate (exactly one class fits every cue) | **164 (15.4%)** |
| Review | 901 (84.6%) |
| of which no class has all its cues | 813 |
| of which too few points in the patch (under 12) | 63 |
| of which a pole or wire hint (cannot be separated from a bare trunk in leaf-off imagery) | 25 |

AUTO candidates by class: building roof 69, ground 54, tree 38, wall 2, shrub or low vegetation 1.
By queue: Q6 random 77 of 193 (40%), Q2 32 of 173, Q4 27 of 165, Q1 18 of 170, Q3 8 of 182, Q5 2 of 182.
**The packet is deliberately full of hard cases** (tree over roof, model disagreements, roof edges), so its 15% is not the
rate for ordinary points: the random queue is the better guide, and even there only 40% clear the strict bar.

Footprint state of the units: 326 inside, 648 outside both layers, 91 unknown (the County and OSM layers disagree).

### Against the 15 units a person had labelled when this ran
Six were AUTO and all six matched the person (all roofs); nine went to review, which is what the hard queues should do.
**This is not an accuracy figure.** The rules were corrected after the first run showed them against these same 15 labels
(see the header of `canopy/triage.py`), so these 15 cannot test them.

### Where the independent evidence disagrees with the models (after the fact, not an input)
- Of 69 roofs proposed, the **building model called 46 (67%) a building**; the baseline classes called 66 (96%) a building.
  So about a third of the independently judged roofs are ones the building model missed.
- Of 38 trees proposed, the tree model called 34 (89%) a tree; the baseline called 36 (95%).

## Limits
- **NAIP is leaf-off (2021-11-13).** Only 15% of its pixels are green. A tree is therefore never proposed without high
  greenness, and low greenness never rules a tree out. That is why only 38 trees clear the bar.
- **A bare trunk looks like a pole or wire.** Both are hints for a person and never AUTO. Twenty-four pole hints need a look.
- **Heights use this code's own ground estimate** (5th percentile of a 12 m neighbourhood), which is typically 0.3 m below
  the baseline ground surface and up to about 2 m below on slopes. On a slope it over-states heights. That
  keeps ground units out of AUTO, but it could also let a low object pass a height cue (tree 2.5 m, roof 2 m).
- NAIP and the lidar are two years apart; roof lean and shadow apply.
- The footprint layers can be out of date. A new building that neither layer has would look like "outside footprints".

## How to measure its accuracy (still to do)
Accuracy must come from a fresh, randomly drawn human sample of the AUTO candidates, labelled blind (without seeing the
proposal). One-sided 95% lower bounds on the share of AUTO candidates that are right, for an audit of n units:

| n audited | 0 disagree | 1 disagree | 2 disagree |
|---:|---:|---:|---:|
| 30 | 0.905 | 0.851 | 0.805 |
| 40 | 0.928 | 0.887 | 0.851 |
| 60 | 0.951 | 0.923 | 0.899 |

The first sample of 40 is drawn and ready: [audit-1/README.md](audit-1/README.md); [audit_sample.py](audit_sample.py)
draws and scores it.

Only after such an audit, and a recorded decision, should any AUTO candidate be written as a training label. Until then
they are prefills to confirm in bulk with **Label Selected Units**.

## What would raise the share handled automatically
1. A second independent opinion: the IGN FRACTAL RandLA-Net model (needs NAIP colour, now available).
2. A slope-robust ground estimate, and building-scale roof planes instead of a 1 m patch.
3. Leaf-on imagery, which would let trees be proposed far more often.
