# Handoff: where the classification work stands (October 20, 2026)

Everything is committed on branch `canopy/classification-refinement` (PR
[buschbrian/agol-python-scripts#11](https://github.com/buschbrian/agol-python-scripts/pull/11)). Large data is not in git: it is on
the lidar SSD (`D:\lidar` on MC-PC13, the A4000 workstation; set `CANOPY_LIDAR_ROOT` to its root on any other machine).
Start here, then follow the links. The [September 30 handoff](../2026-09-30/HANDOFF.md) still holds the machine setup.

**Stopped cleanly at 16:50 on October 20 so the SSD could leave the workstation:** no job running, the three label-page
servers stopped, every page answer imported into its packet's review geodatabase and backed up to the repo
(`reviews/2026-09-29/packets/training-labels`, `-refined`, `-rare`).

## 1. Where things stand

| Area | State on October 20 | Record |
|---|---|---|
| Citywide FRACTAL inference | **Complete**, 61 tiles, 1,344,971,548 points, three passes each | [fractal-city/README.md](../2026-10-19/fractal-city/README.md) |
| Refined LAS copies | Rules v2 is current (`runs/refined-fractal-20261020`): 39.8% of points changed, mostly class-3 bare surface to ground. Provisional copies; originals untouched | same |
| Training labels, original packet | 1,019 units in the review geodatabase and the repo backup; 960 answers on the label page. Q1-0114 and Q2-0010 removed as ambiguous | [label-page/README.md](label-page/README.md), [TRAINING_REVIEW.md](../2026-09-29/TRAINING_REVIEW.md) |
| Training labels, refined cylinders | 225 sub-units from 167 MIXED/UNSURE parents; **116 labelled**, imported and backed up | label-page/README.md |
| Training labels, rare classes | 257 new 0.5 m units aimed at vehicles, wires, poles and fences (FRACTAL's misses), port 8767 (`label_page.bat serve-rare`). **252 of 257 labelled** (October 21), imported and backed up: vehicle 54, other structure 50, wire 36, building roof 32, tree 11, pole 8, shrub 8, wall 5, ground 1, MIXED 1, UNSURE 46 | [rare-classes/README.md](rare-classes/README.md) |
| Auto-accepted triage answers | Triage v2 roof and tree candidates, REVIEWER `triage-v2`, never walls | [audit-2/README.md](../2026-09-30/audit-2/README.md) |
| Audit 2 (blind, 40 units) | 36 or 37 of 40 before Q2-0010 was removed; **official score waits for Q2-0010 to be relabelled** | audit-2/README.md |
| FRACTAL fine-tune | **Run-1 done** (15:15 to 16:13): 191 of 208 held-out parts against the released model's 189 (p = 0.63), no measurable difference; changes 1.35% of 12TVL2804's points. Not swapped in. **Run-2** (all rare-class and newer refined labels; 1,157 units, 242 held out) started October 21 (it waits for 8 GB of commit headroom first) | [fractal-finetune/README.md](fractal-finetune/README.md) |
| Esri building model, citywide | **Complete**, all 61 tiles (October 21, 10:45); every first-try failure completed on retry | [esri-city/README.md](esri-city/README.md) |

## 2. Decisions recorded on October 20
- Lawn is GROUND; SHRUB_LOW_VEG is shrub, hedge, garden bed or tall grass. Rules v2 therefore moves unanimous vegetation called
  ground to class 2 (code 7).
- The label page stays blind: no model class, baseline class or triage proposal in its data.
- Triage v2 roof and tree AUTO candidates become training answers; walls never.
- MIXED and UNSURE answers are re-asked as refined 0.5 m cylinders cut at vertical gaps, in their own packet.
- Refinement from the labels is done by fine-tuning FRACTAL (chosen over more hand rules). WALL labels are left out of its
  training because our walls mix facades (FRACTAL building) with garden walls and fences (permanent structure).
- The Esri building run waits; nothing depends on it. (Resumed at 16:15 after the fine-tune.)
- Fences and freestanding walls (garden, retaining, property-line) are OTHER_STRUCTURE, trained as FRACTAL permanent structure;
  WALL is a building facade only. Earlier WALL answers stay WALL and stay out of training.
- After run-1 tied, more labels go to the classes FRACTAL misses (the rare-class packet). Run-1's held-out blocks are frozen so
  later runs are scored on the same units.

## 3. Resume, in order
1. **Fine-tune:** run-1 showed no measurable gain (`fractal\finetune-20261020\run-1\evaluation.json`). The misses left are
   vehicles, wires and poles, so the rare-class packet was labelled (252 of 257) and run-2 trains on it
   (`fractal\finetune-20261021-full\run-2`; read its `evaluation.json`, or `driver.log` if it stopped); see
   [rare-classes/README.md](rare-classes/README.md) and [fractal-finetune/README.md](fractal-finetune/README.md). A model is swapped in only if it is no worse on ground,
   vegetation and building parts and better overall; that is Brian's call. Then: citywide inference with `repeat.py --checkpoint`
   and refinement rules v3.
2. **Esri building run:** complete (October 21). Outputs in `runs\esri-building-20261020\<tile>\building`.
3. **Labels:** relabel Q2-0010 on the page, import (`label_page.bat import --apply`, `import-refined --apply`), back up with
   `training_labels.bat save`, then score audit 2 (`audit-2/README.md`).
4. Then: a batch-1 control of the Esri model on 12TVL2804 on this card; the consensus roof-height product (design not yet
   discussed); the treetop candidates the refinement points at (a rebuilt canopy surface decides them).

## 4. Open decisions for Brian
1. Whether to keep fine-tuning (run-1 tied the released model) and so whether to label more vehicles, wires and poles.
2. Rule 12 (18.7 M building points FRACTAL calls ground) and rule 15 (water or bridge): still proposed only.
3. The consensus roof-height product: which sources (October 8 native, FRACTAL, Esri) and how they combine.
4. Whether the refined copies feed the canopy surface, and so the treetops and cover, or stay review layers.

## 5. Workstation health
On October 20 the workstation crashed outright (bugcheck 0x3B, access violation in kernel code; minidump
`C:\WINDOWS\Minidump\102026-15265-01.dmp`) with WHEA 17 corrected PCI Express errors logged, on top of the September record in
the [September 30 handoff](../2026-09-30/HANDOFF.md#7-workstation-health-found-september-30-read-from-the-windows-event-log).
No label or answer was lost (the page writes atomically; the geodatabases opened intact). Earlier the same day, passes crashed
at the memory commit limit with Chrome and Teams open. Guards now in place: jobs wait for commit headroom (6 GB for FRACTAL
inference, 8 GB for the fine-tune), crashed passes rerun on their own, uneven passes are rejected.
For IT: memory test, GPU reseat and PCIe link check, WinDbg on the minidump; a larger page file. Not ours to change.

## 6. Where things are on the SSD (under `D:\lidar\2023-salt-lake-valley`)
| What | Path |
|---|---|
| Working LAS (October 8) | `runs\city-count-20261008\prepared\points` |
| FRACTAL inputs, passes, consensus | `fractal\city-20261019\colorized`, `fractal\city-20261019\fractal\<tile>` |
| Refined copies v1, v2 | `runs\refined-fractal-20261019`, `runs\refined-fractal-20261020` |
| Review packets, page data, answers, snapshots | `runs\pilot-2026-09-29\training-review\` (`packet-20260929`, `packet-20261020-refined`, `snapshots`) |
| Fine-tune data and run | `fractal\finetune-20261020\data`, `...\run-1` |
| Esri building run | `runs\esri-building-20261020\<tile>`, `building.log` |

The Myria3D clone at `%USERPROFILE%\tools\myria3d` carries local changes; their full diff is
[fractal-finetune/myria3d-finetune.patch](fractal-finetune/myria3d-finetune.patch).
