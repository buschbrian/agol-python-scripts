# Rare-class labelling queue (October 20, 2026)

Fine-tune run-1 tied the released FRACTAL model (191 against 189 of 208 held-out parts). Ground, vegetation and buildings were
already at or near the ceiling; the misses left were vehicles and wires (FRACTAL "other", 2 of 12 parts) and poles and
structures (FRACTAL "permanent structure", 0 of 4), the classes with the fewest labels. Brian asked for more training on those
classes, so this packet puts 257 more of them in front of him.

## Labelling it
```
reviews\2026-10-20\label-page\label_page.bat serve-rare            http://127.0.0.1:8767
reviews\2026-10-20\label-page\label_page.bat import-rare --apply   (Pro closed) into the packet's own review geodatabase
```
Same page, keys and rules as the other two packets ([label-page/README.md](../label-page/README.md)). The patches are small
(0.5 m, a median of 8 points), so lean on the 3D view, the sections and the imagery map. **Fences and freestanding walls
(garden, retaining, property-line) are OTHER_STRUCTURE; WALL is a building facade only** (decided October 20). Many units will
turn out to be something common (a branch, a roof edge, ground): label what is there. Those answers are useful too, because they
are exactly where the model was tempted to say "other" or "structure".

## How the units were chosen (build_rare_packet.py)
On 12TVL2804, the training tile, inside the same evaluation exclusion frame as the other packets, from the clean returns only:

| Queue | Candidate points | Clusters | Units |
|---|---:|---:|---:|
| R1: released FRACTAL unanimous "other", 0.3 to 3 m above ground | 117,913 (before cleaning) | 1,191 | 80 |
| R2: the same above 3 m (wires, high clutter) | 11,044 (before cleaning) | 227 | 70 |
| R3: unanimous "permanent structure" | 58,944 (before cleaning) | 138 | 27 |
| R4: released and fine-tuned models disagree, one says other, bridge or structure | 110,005 | 1,859 | 80 |

Candidate points are grouped into 1 m-cell clusters. Each unit is a 0.5 m cylinder at a cluster's central point (up to three
spaced 5 m apart in a long cluster), with its slab over the candidates' heights plus 10 cm, never lower than 20 cm above
ground. Units are dropped when the frame refuses them, when they come within 1.5 m of any unit of the earlier packets, or when
they hold fewer than 4 candidate points. A first build counted withheld and overlap returns, which the page and export skip,
and left 16 empty patches; it is kept on the SSD as `packet-20261020-rare.discarded-unclean`.

The model chose *where* to look, which is fine for training labels and makes these units useless for an accuracy figure.
The page stays blind: the units carry no model field, all four queues share the `R-` prefix and are interleaved, so nothing on
the page says which class put a unit there.

## Into the next fine-tune (run-2)
Once labelled and imported, in ArcGIS Pro Python from `canopy-toolbox`:
`training_review_driver.py snapshot <packet-20261020-rare> <runs\pilot-2026-09-29\training-review\snapshots\packet-20261020-rare-DATE>`
([TRAINING_REVIEW.md](../../2026-09-29/TRAINING_REVIEW.md), "Snapshot, validation and audit"), then in the Myria3D Python
`make_training_las.py NEW_DIR --snapshot <packet-20261020-rare> <that snapshot>`, and `make_config.py`, `create_hdf5` and
`run_finetune.py` into a new run folder, as for run-1. Run-1's held-out blocks are frozen, so run-2 is
scored on run-1's 191 held-out units plus the new units that fall in held-out or newly drawn blocks
([../fractal-finetune/README.md](../fractal-finetune/README.md)).
