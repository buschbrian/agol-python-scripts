# SSD and A4000 results — October 8, 2026

The RTX A4000 completed the paired FRACTAL experiment on the full 12TVL2804
tile: **26,982,464 points, three independent passes with each imagery year**.
All six outputs and both consensuses passed source-dimension and point-order
checks. The original prepared LAS, imagery, training packet and label backup
retained their recorded hashes. No training answers were changed.

Accepted outputs are on the SSD under:

```text
D:\lidar\2023-salt-lake-valley\fractal\full-tile-20261008-a4000-chunked
  naip2021\manifest.json, consensus.las, repeat-1..3\
  naip2024\manifest.json, consensus.las, repeat-1..3\
  comparison\summary.json, patches.csv, paired-points.json,
              paired-point-transitions.csv, paired-point-review.png,
              alignment-review.png
  experiment.json
```

Use this group for comparisons. The earlier `full-tile-20261008-a4000`
inference results and `full-tile-20261008-a4000-ordered` attempt are superseded;
they remain for diagnosis. The colorized inputs in the first directory were
verified and reused unchanged in the accepted experiment.

## Repeat consistency and imagery comparison

Both variants used the same checkpoint, model code, batch size 10 and unseeded
sampling. Imagery dates are November 13, 2021 and July 7, 2024. No registration
shift was applied. The accepted inference, consensus and training comparison
took about 15.7 minutes; individual model calls took about 125–126 seconds,
excluding interpreter startup. Colorization and earlier failed attempts are
outside that duration.

| Full-tile metric | NAIP 2021 | NAIP 2024 |
|---|---:|---:|
| Pairwise agreement between three passes | 98.28–98.33% | 98.39–98.41% |
| Unanimous points | 26,306,421 | 26,344,075 |
| Three-way ties | 19,514 | 17,183 |

Withheld, synthetic and overlap flags exclude 70,600 points from diagnostics,
leaving 26,911,864 eligible points. The paired consensuses differ at 426,736
eligible points (1.586%), including tie codes. Among the 26,876,716 points
resolved in both consensuses, 392,729 differ (1.461%). These differences combine
imagery sensitivity with residual stochastic inference variation; they are
not classification errors or an accuracy estimate.

Machine-readable evidence: [experiment.json](experiment.json),
[paired-points.json](paired-points.json) and
[point transitions](paired-point-transitions.csv). The transition matrix and
10 m difference map are in the SSD `comparison\paired-point-review.png`.

## Existing training labels

A fresh backup contains 58 answered units out of 1,065, with no structural
backup CHECK failures. Protocol `fractal-training-comparison/1` was written
before this experiment. It compares each circle and height slab, requires at
least 12 eligible points and a strict model-family majority, and retains ties
and weak point votes in the denominator. TREE and SHRUB_LOW_VEG both map to
VEGETATION. Other human structure labels are not forced into a building match.

| Human label | Comparable units | Agreement, 2021 | Agreement, 2024 |
|---|---:|---:|---:|
| BUILDING_ROOF | 23 | 22 | 22 |
| GROUND | 11 | 10 | 10 |
| TREE → VEGETATION | 7 | 7 | 7 |
| SHRUB_LOW_VEG → VEGETATION | 2 | 0 | 0 |
| Total | 43 | 39 (90.70%) | 39 (90.70%) |

Fifteen labels have no comparable model family. There were no sparse, partially
covered or abstaining patches. All 43 comparable patches kept the same model
family between imagery years. The two shrub patches were predicted as ground;
inspect their point patches before deciding whether the model or labels need
correction. The vegetation agreement does not establish tree/shrub separation.

These are training diagnostics, not independent evaluation. They provide no
accuracy evidence to prefer one imagery year. Evidence and patch details are
in [training-comparison.json](training-comparison.json) and
[training-patches.csv](training-patches.csv). The 40-unit audit remains blind
and unlabelled; this comparison only uses existing answered training units.

## Windows fixes and verification

The first run exposed a point-order failure: one output differed from the
source by index, and the consensus guard rejected it. Myria3D reads the cloud
twice and attaches predictions by index. Every LAS reader in
`pctl/dataset/utils.py` now uses `threads=1`. Two complete serial reads matched
source XYZ and GPS time by index ([reader check](reader-order-check.json)).
Reordering only the final output would not repair potentially misattached
predictions, so the six accepted passes were rerun with the fixed reader.

The next attempt failed during native PDAL output writing in `pdalcpp.dll`
with integer divide-by-zero (`0xc0000094`). A chunked laspy writer now checks
XYZ and GPS time against prediction indices, copies every original dimension,
preserves the LAS header/CRS and adds only the requested model channels. It
refuses existing output/partial files and publishes the completed file after
writing succeeds. This changes serialization, not weights, logits or sampling.
The portable [Windows patch](../2026-09-30/fractal/myria3d-windows.patch)
contains both fixes; its reverse application check passed against the installed
runtime. The repeat manifest records hashes of the reader and writer modules.

Validation: all 21 focused FRACTAL tests passed in the Myria3D environment,
including laspy integration; the complete repository suite ran 446 tests and
passed with 88 skips ([log](regression-tests.log)). Those skips include ArcPy
and laspy-dependent tests unavailable in the plain repository environment.
All six real full-tile outputs then passed the stronger runtime checks.

## Review readiness and next actions

The label-height consistency check still flags seven units:
Q3-0002, Q6-0008, Q6-0019, Q2-0060, Q6-0119, Q6-0147 and Q6-0148.
These are recheck requests, not automatic corrections. See
[label-consistency.csv](label-consistency.csv) and the selection expression in
[recheck-select.txt](recheck-select.txt).

The review project now contains its map and the missing 3D scene, with no
broken layers on programmatic readback ([project check](review-project-check.json)).
The original project was backed up as
`training_review.before-scene-20261008-085134.aprx` beside `training_review.aprx`
in `D:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29\training-review\packet-20260929`.
Map/scene following, bulk tools and warnings still need a live Pro check.

1. Open that project in Pro and recheck the seven flagged answers and four
   model disagreements, using the patch's actual height slab.
2. Complete all 40 audit answers before viewing audit proposals, then back up
   and score them using the [audit instructions](../2026-09-30/audit-2/README.md).
3. Measure imagery-to-lidar roof-edge offsets. The SSD's
   `comparison\alignment-review.png` shows four existing labelled training
   roofs with both imagery years; it is a visual aid, not a measured offset.
4. Use those results to decide whether FRACTAL helps triage and whether more
   training-tile inference or fine-tuning is justified. Keep 12TVL3302 plus
   its halos and external tile 12TVL2203 out of training.

LAS files and imagery remain outside git. The small JSON/CSV snapshots here
preserve the accepted run's evidence for pickup on another machine.
