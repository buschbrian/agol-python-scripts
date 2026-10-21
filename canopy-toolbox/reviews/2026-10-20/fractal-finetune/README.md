# Fine-tuning FRACTAL on the training labels (October 20, 2026)

Brian chose this route after the full system crash on October 20: refine the classification from the labels by fine-tuning the
IGN FRACTAL RandLA-Net (the model of `../../2026-10-19/fractal-city`) on 12TVL2804, rather than adding more hand rules.
Everything here reads the labels and the lidar copies; it never touches a source LAS, a review geodatabase or live GIS data.

## Data (make_training_las.py)
- Labels: the two October 20 snapshots (packet-20260929 and packet-20261020-refined), 938 exportable units. Splits and stacked
  refined layers are honoured by `training_review.export_training_las`.
- Classes: TREE and SHRUB_LOW_VEG → 5 vegetation, BUILDING_ROOF → 6, GROUND → 2, WATER → 9, POLE and OTHER_STRUCTURE → 64,
  VEHICLE and WIRE → 1. **WALL is left unlabelled**: our walls mix building facades (FRACTAL building) with garden walls and
  fences (FRACTAL permanent structure). Noise (7, 18) becomes 65, which Myria3D drops.
- Every other point is 250: it stays in each 50 m block as context and is ignored by the loss.
- Hold-out by 50 m block (`training_review.point_split`, fixed seed): 747 units train, 191 validate. `train/` and `val/` each hold
  the whole tile with only their own side's labels, so no label is seen by both.
- HDF5: 235 training and 72 validation 50 m blocks, every one with labels (86,335 and 19,950 labelled points after
  Myria3D's own preparation). Blocks without a labelled point are dropped (`pre_filter_no_labels`); the first build counted
  noise as a label and kept 466 empty blocks, so it was rebuilt.

## Myria3D changes (myria3d-finetune.patch)
The full diff of the clone at `%USERPROFILE%\tools\myria3d` against upstream; it includes the September 30 Windows changes
(`../../2026-09-30/fractal/myria3d-windows.patch`), so apply this one instead. Fine-tuning needs:
- `transforms.py`: code 250 maps to index 7 (one past the 7 classes);
- `metric_callbacks.py`: every metric ignores index 7; the validation hook gets its Lightning 2 name so validation is logged;
- `train.py`: the finetune task passes the configured criterion (with `ignore_index: 7`) when it reloads the checkpoint;
- `pctl/dataset/hdf5.py`: HDF5 paths joined with "/" (Windows put every sample at the file root);
- `pctl/datamodule/hdf5.py`: no worker process for the test loader (Windows cannot pickle the transforms);
- `pctl/dataset/utils.py`: `pre_filter_no_labels`.

## Configuration (make_config.py)
The released inference config supplies the network, the class mapping and the evaluation transforms, so the architecture
matches the checkpoint. The rest comes from Myria3D's own configs: training preparations (`points_budget`), light augmentation
(x and y flips), Adam at lr 1e-4 (the original 0.0039 would relearn rather than adjust), ReduceLROnPlateau (patience 3),
up to 30 epochs with early stopping on validation loss (patience 5), CSV logs, no Comet. `run.py` chooses its launcher from
`task.task_name` on the command line, not from the YAML.

## Running (run_finetune.py)
```
make_config.py DATA_DIR RUN_DIR          then run.py ... task.task_name=create_hdf5 (see make_config's output)
run_finetune.py RUN_DIR [--wait-for-log building.log]
```
The driver waits for the Esri building run to finish and for 8 GB of commit headroom (the October 20 crashes began at the commit
limit), then: a 5-batch GPU smoke test, the fine-tune, three prediction passes of the best checkpoint over the colourised
12TVL2804 (`repeat.py --checkpoint`, the same protocol as the citywide run) and the score. A CPU smoke test (batch 1, two
training and one validation batch) ran cleanly on October 20 before the chain was queued.

## Scoring (evaluate_finetune.py)
On the held-out labels only, by point and by labelled part (plurality class of a part's points against its label; the part
score is the one to quote because points in a patch are not independent), with a paired sign test between models.
The units were labelled where the reviewer looked, partly from model-disagreement queues, so this compares models on the same
hard sample; it is not a citywide accuracy.

Released FRACTAL on the held-out side (October 20):

| Prediction | Points | Parts | Ground | Vegetation | Building | Other (vehicle, wire) | Structure (pole, other) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Consensus of 3 passes | 93.7% | 189 of 208 | 35 of 35 | 58 of 61 | 94 of 96 | 2 of 12 | 0 of 4 |
| Pass 1 alone | 93.9% | 187 of 208 | 35 of 35 | 56 of 61 | 94 of 96 | 2 of 12 | 0 of 4 |

Nearly all the misses are vehicles, wires and poles, the classes with the fewest labels (about 2,300 training points each),
so a gain will be small in parts and needs the sign test, and 16 held-out parts cannot show much for those two classes.
A fine-tuned model replaces the released one citywide only if it is no worse on ground, vegetation and building parts and
better overall; that decision is Brian's.

## Result of run-1 (October 20, 15:15 to 16:13)
Training stopped early after 11 epochs (about 4.5 minutes each); the best validation loss was epoch 5's (0.271, against 0.294
after the first epoch). Three prediction passes of `epoch_005.ckpt` over 12TVL2804 agreed unanimously on 97.6% of points.
The first scoring attempt crashed natively (0xC0000005) five seconds in, with 12.9 GB headroom on the rerun; the rerun is
`evaluation.json`, copied here as [evaluation-run1.json](evaluation-run1.json) with the training log
[metrics-run1.csv](metrics-run1.csv) (epochs counted from 0).

| Consensus of 3 passes | Points | Parts | Ground | Vegetation | Building | Other (vehicle, wire) | Structure (pole, other) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Released FRACTAL | 93.7% | 189 of 208 | 35 of 35 | 58 of 61 | 94 of 96 | 2 of 12 | 0 of 4 |
| Fine-tuned, run-1 | 94.6% | 191 of 208 | 35 of 35 | 58 of 61 | 95 of 96 | 3 of 12 | 0 of 4 |

Paired by part: 188 right in both, 3 only with the fine-tuned model, 1 only with the released one, 16 in neither; sign test
p = 0.63. **No measurable difference**: the fine-tuned model is no worse anywhere and two parts better, which this sample cannot
tell from chance. Across the whole tile it changes the class of 1.35% of points, with no single class swap reaching 100,000
points; class totals move by less than 1% except water and bridge (a few thousand points each).

What would move it: more labels in the weak classes (vehicles, wires, poles, fences), since ground, vegetation and building are
already at or near the ceiling on these units; and a held-out sample large enough to show a gain there. A higher learning
rate or longer training would mostly fit the 747 training units harder. Not swapped in citywide (October 20); Brian decides.

## Next: run-2 with the rare-class labels
Brian chose more labels in the weak classes ([../rare-classes/README.md](../rare-classes/README.md), 257 units). Also decided
on October 20: fences and freestanding walls are labelled OTHER_STRUCTURE (64) from now on; WALL stays out of training.
`make_training_las.py --snapshot PACKET SNAPSHOT` adds a packet's labels to run-1's; a newer snapshot of one of run-1's packets
adds only the units run-1 did not have, and refuses any whose label changed. Run-1's 50 m block split is frozen: a
new unit in a run-1 held-out block is held out, in a run-1 training block it trains, and only blocks no run-1 unit touched are
split anew (20%). The data folder gets `holdout_units.json`, which `evaluate_finetune.py` uses, so run-2's score contains
run-1's 191 held-out units and run-1 can be scored on run-2's held-out set for a like-for-like comparison.

**Run-2 (October 21):** data in `fractal\finetune-20261021\data` from run-1's snapshots plus the October 21 snapshots of the
refined packet (116 labelled, 15 new) and the rare-class packet (85 labelled): 1,015 units, 801 training and 214 held out (run-1's
191 and 23 new). The rare-class patches are small, so the gain in labelled points is modest: "other" 2,281 to 2,713 training
points, "structure" 2,301 to 2,361. HDF5: 239 training and 73 held-out blocks, all with labels. Queued at 08:29 behind the Esri
run with `run_finetune.py ... --wait-for-log building.log --compare run1=<run-1 consensus>`, so the score sets the released
model, run-1 and run-2 side by side on run-2's held-out units.
