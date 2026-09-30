# Training-label checklist (ArcGIS Pro)

For the person labelling the 1,065 training units on 12TVL2804. You are saying what the lidar returns **inside the yellow
circle and height slab** are (tree, roof, wall...), and nothing beyond them. This is training data only. It is never used to score the model, and the tool will
refuse any spot that is too close to an evaluation sample. Background: [TRAINING_REVIEW.md](../2026-09-29/TRAINING_REVIEW.md).

## Before you start (once per session)

- [ ] The lidar disk is plugged in (it appears as **D:** on the office workstation, **H:** on the laptop).
- [ ] Close any other copy of ArcGIS Pro that has this project open.
- [ ] Open `training_review.aprx` from
      `<lidar disk>\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29\training-review\packet-20260929\`.
- [ ] If Pro shows **Project Item Repair** about `Blank.atbx` when it opens, click **OK**. It is harmless: the
      layers and labels are not affected.
- [ ] In the Catalog pane, the **Training Review** toolbox has no red X. The project was built on another
      machine and remembers that machine's path, so here it may show a red X or be missing. Fix: Catalog >
      Toolboxes > Add Toolbox > your copy of `canopy-toolbox\TrainingReview.pyt` (for example
      `U:\agol-python-scripts\canopy-toolbox\TrainingReview.pyt`), then right-click the broken entry > Remove.
      Or close Pro and run `training_labels.bat repair` once; it adds the working entry and keeps a dated copy of
      the project first (the broken entry still has to be removed by hand).
- [ ] After the tools are updated from git, right-click the **Training Review** toolbox > **Refresh** once. Pro
      keeps the old toolbox file in memory until you do.
- [ ] Check progress: double-click `canopy-toolbox\reviews\2026-09-30\training_labels.bat` for help, or run
      `training_labels.bat status` in a Command Prompt.

## For each unit

1. [ ] Run **Next Training Unit**. It selects the next unlabelled unit and moves the map to it, even if the
       attribute table is the active view (keep the Training review map open, beside the table if you like). If no
       map is open it still selects the unit and says so. The message tells you the height slab to judge (Z low to
       Z high, and metres above ground).
2. [ ] Look at the returns **inside the yellow circle and inside that height slab** only. Use a cross-section
       (LAS layer > Classification > Profile View, a line about 2 m wide through the point). Imagery alone cannot
       show height or overhanging branches. Note: the imagery date may not match the November 2023 lidar.
3. [ ] Run **Label Training Unit**. Fill in **Label**, **Reviewer** (remembered after the first time), and
       **Notes** if useful. Leave **Advanced** closed.
4. [ ] Press **Run**. The tool saves the answer, then jumps to the next unit.
5. [ ] **Change Label every time.** Pro keeps the last dialog values, so the previous answer is still selected.

### Label many units at once

When a group of units is obviously the same thing (for example a row of roofs, or a cluster that is clearly not
trees), label them together:

1. [ ] Select the units: drag a box or lasso with the map's **Select** tool, or pick rows in the attribute table
       (Shift-click for a range), or use **Select By Attributes** (for example `QUEUE = 'Q4_SHAPE'`).
2. [ ] Run **Label Selected Units**, choose the **Label**, and press **Run**. Every selected unit gets that label.
3. [ ] Read the message: `Labelled N units as X`. It is **all or nothing**: if any selected unit fails a check (too
       close to an evaluation sample, a different existing label without *Replace*, a missing reviewer), nothing is
       written and the message names the failures. At most 500 units per run.

Only unlabelled units are visible by default, so a selection cannot reach finished ones. Before a large batch, run
`training_labels.bat save`. Each batch also records what it overwrote in `bulk-history` beside the project.

Skipping a unit is fine. Use **MIXED** (the slab clearly holds two classes) or **UNSURE** (you can't tell) rather
than guessing. Both are kept but not used for training.

### The rule: label only the returns in the patch

The training export gives your label to exactly the points inside the yellow circle and between Z low and Z high. So:

- **Label what those points are, even when something more interesting is beside the circle.** A car, pole or wall next to
  the circle does not make the circle's points VEHICLE, POLE or WALL. Label what is *in* the circle (often GROUND or
  SHRUB_LOW_VEG, lawn included), or use **UNSURE** or **MIXED**.
- **Imagery is a hint from a different date.** A vehicle in the imagery may not be in the lidar at all. Judge from the points
  and the cross-section.
- **Labels are checked against the patch afterwards** (`label_consistency.py`): for example a VEHICLE whose patch tops out at
  0.3 m above ground is flagged for a second look. Flags never change a label.

| Label | Use it when every return in the slab is... |
|---|---|
| TREE | woody tree: crown, branches or trunk (branches over a roof count) |
| BUILDING_ROOF | a roof, including rooftop equipment |
| WALL | a vertical face: facade, retaining wall, solid fence |
| WIRE / POLE | an overhead wire or cable / a utility, light, sign or flag pole |
| OTHER_STRUCTURE | carport, shade sail, playground, bridge, tank |
| SHRUB_LOW_VEG | non-tree vegetation: shrub, hedge, lawn, garden |
| GROUND | bare ground, pavement, gravel, low hardscape |
| VEHICLE / WATER | car, truck, trailer / pool, pond, stream |

**Imagery usable** (optional): YES only if you can see and identify the object in the imagery. Leave blank if unsure.

## Re-check flagged labels

`python reviews/2026-09-30/label_consistency.py NEW_FOLDER` lists labels that the patch's points cannot support and writes
`recheck-select.txt`. Labelled units are hidden by default, so first set the *Training units* layer's definition query to
*Labelled (check answers)*, then **Select By Attributes** with that line. To change a label, run **Label Training Unit** with
**Replace** ticked (under Advanced). Flagged does not mean wrong, and unflagged does not mean right.

## Save your work to the repo (every session, and every ~50 units)

Your labels live in the geodatabase on the lidar disk. **The repo has none until you save.** If the disk is lost,
unsaved labels are lost.

- [ ] Save any edits you made in the attribute table or Attributes pane (the tools save themselves).
- [ ] Run `training_labels.bat save`. It copies every answered unit to
      `canopy-toolbox\reviews\2026-09-29\packets\training-labels\` and makes one git commit of those two files.
      It never pushes.
- [ ] `git push` when you want it on GitHub (and so mirrored to Azure Repos).

`training_labels.bat backup` does the copy without committing. If it prints `CHECK:` lines the labels were still
saved; the lines name units to fix (for example a missing reviewer). Nothing is refused or lost.

## If something goes wrong

| Problem | What to do |
|---|---|
| "Select exactly one training unit" | Run **Next Training Unit** first, or select one point. |
| "Unit already labelled ... tick Replace" | You are changing an earlier answer. Open **Advanced**, tick *Replace*, run again. |
| "refused ... evaluation" | The spot is too close to an evaluation sample. Skip it. This is working as intended. |
| A unit seems missing from the map | The layer only shows unlabelled units. Switch its definition query to *Labelled (check answers)* to see finished ones. |
| Labels vanished (new geodatabase, bad edit) | `training_labels.bat restore` previews putting the repo copy back. Add `--apply` to write it. Conflicts are skipped unless you add `--replace`. |
| The tool seems stuck or Pro crashed | Re-open the project and run **Next Training Unit**. Saved answers are already in the geodatabase. |

## Don't

- Don't label from the evidence layer (`training_units_evidence.lyrx`). It shows model answers and can bias you.
- Don't edit `reference.gdb`, the plot census, or any LAS file. Those are evaluation data or source data.
- Don't copy the geodatabase while Pro has it open for editing.
- Don't run `restore --apply` while you are labelling.

## Not yet checked

The zoom and selection behaviour of the two tools, and the Profile View menu location, need a live Pro session.
The first session should confirm them and report anything awkward. The dialog was simplified after the fixtures were
written: the rarely used options now sit under **Advanced**.
