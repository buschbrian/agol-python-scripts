# Handoff: where the classification work stands (October 20, 2026; updated October 21)

Everything is committed on branch `canopy/classification-refinement` (PR
[buschbrian/agol-python-scripts#11](https://github.com/buschbrian/agol-python-scripts/pull/11)). Large data is not in git: it is on
the lidar SSD (`D:\lidar` on MC-PC13, the A4000 workstation; set `CANOPY_LIDAR_ROOT` to its root on any other machine).
Start here, then follow the links. The [September 30 handoff](../2026-09-30/HANDOFF.md) still holds the machine setup.

## PICK UP HERE (end of October 22: the A4000 work is complete)
**State:** every GPU and lidar-processing step is done and committed; nothing is running; the label servers are off; every
label answer is imported and backed up (original 1,019; refined 116 of 225; rare classes 253 of 257). Brian is continuing
the other analyses on a different machine.

**The current products are the [October 22 library](../2026-10-22/PRODUCTS.md)**, one folder on the lidar SSD:
`<SSD>\lidar\2023-salt-lake-valley\runs\millcreek-products-20261022` (D: on MC-PC13; `library.json` lists every file's
source and SHA-256). It holds the canopy height, observed, support and occlusion rasters and terrain; consensus roof
elevation and height and building heights for 22,042 footprints; **527,140 treetops** with ownership; **400,063 crowns**;
**treetop evidence** (32,986 SUSPECT); cover by zone (city **25.59%** of observed area); and `review\` change files. The
October 19 library and October 8 count stay beside it, unchanged, for comparison.

How each was made and checked (each rebuild first reproduced the October product exactly on the old classification):
- combined classification: consensus roofs ([roof-consensus](../2026-10-21/roof-consensus/README.md)) plus FRACTAL rules v2;
- canopy, treetops, crown pilot, cover: [canopy-rebuild](../2026-10-22/canopy-rebuild/README.md);
- citywide crowns: [tiled-crowns](../2026-10-22/tiled-crowns/README.md) (validated exact from a 20 m halo; run at 40 m);
- treetop evidence: [treetop-evidence](../2026-10-22/treetop-evidence/README.md) (`canopy/treetop_evidence.py`, rebuilt from
  the October 15 manifest and byte-identical on all 607,972 October 15 rows; the original, found on the laptop, is filed as `canopy/treetop_evidence_20261015.py`).

**On another machine:** clone or pull branch `canopy/classification-refinement`
([PR #11](https://github.com/buschbrian/agol-python-scripts/pull/11)); attach the SSD and set `CANOPY_LIDAR_ROOT` to its
`lidar` folder (unset, `canopy.lidar_root` uses H:\lidar; the label-page and training batch files also look for D:\lidar). Analyses that only read the October 22 products need ArcGIS Pro
or plain Python with GDAL, not the A4000. The Myria3D environment and the patched clone (`fractal-finetune/myria3d-finetune.patch`)
are only needed to rerun FRACTAL.

**Open (Brian's choice):** publish or share October 22 products (a manual staff step: live GIS data is never written from
here); review the 32,986 SUSPECT treetops (the blind
[calibration sample 2](../2026-10-22/packets/treetop-calibration-2/README.md), 350 points, is built and ready to label in Pro); a building-only fine-tune (the one place fine-tuning helped); the smaller items below.

**Smaller open items:** relabel Q2-0010 for the official audit-2 score; the 46 UNSURE rare-class answers could be rechecked
with the imagery map; batch-1 control of the Esri model on 12TVL2804. These can be deleted: the working arrays in
`runs\roof-consensus-20261021\work` (4.8 GB) and `runs\canopy-rebuild-20261022\work` (about 5 GB),
`runs\city-count-20261022\canonical-chm-native.bin` (1.2 GB), and the failed attempts `runs\city-count-20261022.failed-1`
and `.failed-2`.

## 1. Where things stand

| Area | State on October 20 | Record |
|---|---|---|
| Citywide FRACTAL inference | **Complete**, 61 tiles, 1,344,971,548 points, three passes each | [fractal-city/README.md](../2026-10-19/fractal-city/README.md) |
| Refined LAS copies | Rules v2 is current (`runs/refined-fractal-20261020`): 39.8% of points changed, mostly class-3 bare surface to ground. Provisional copies; originals untouched | same |
| Training labels, original packet | 1,019 units in the review geodatabase and the repo backup; 960 answers on the label page. Q1-0114 and Q2-0010 removed as ambiguous | [label-page/README.md](label-page/README.md), [TRAINING_REVIEW.md](../2026-09-29/TRAINING_REVIEW.md) |
| Training labels, refined cylinders | 225 sub-units from 167 MIXED/UNSURE parents; **116 labelled**, imported and backed up | label-page/README.md |
| Training labels, rare classes | 257 new 0.5 m units aimed at vehicles, wires, poles and fences (FRACTAL's misses), port 8767 (`label_page.bat serve-rare`). **253 of 257 labelled** (October 21), imported and backed up: vehicle 54, other structure 51, wire 36, building roof 32, tree 11, pole 8, shrub 8, wall 5, ground 1, MIXED 1, UNSURE 46 | [rare-classes/README.md](rare-classes/README.md) |
| Auto-accepted triage answers | Triage v2 roof and tree candidates, REVIEWER `triage-v2`, never walls | [audit-2/README.md](../2026-09-30/audit-2/README.md) |
| Audit 2 (blind, 40 units) | 36 or 37 of 40 before Q2-0010 was removed; **official score waits for Q2-0010 to be relabelled** | audit-2/README.md |
| FRACTAL fine-tune | **Run-1 done** (15:15 to 16:13): 191 of 208 held-out parts against the released model's 189 (p = 0.63), no measurable difference; changes 1.35% of 12TVL2804's points. Not swapped in. **Run-2** (all rare-class and newer refined labels; 1,157 units, 242 held out) done October 21: on 258 held-out parts released 208, run-1 212, run-2 208, none significant; structure never learned (FRACTAL files fences and poles as "other"); buildings a little better. **Fine-tuning stopped; the released model plus rules v2 stays current** | [fractal-finetune/README.md](fractal-finetune/README.md) |
| Esri building model, citywide | **Complete**, all 61 tiles (October 21, 10:45); every first-try failure completed on retry | [esri-city/README.md](esri-city/README.md) |
| Consensus roof heights | **Complete** (October 21): roof where 2 of 3 sources (native, FRACTAL majority, Esri) say building; on the labels 92.8% of roofs found, 2.8% false (native: 89.2%, 14.0%); 21,562 footprints with heights, negative-height footprints 633 to 35. `runs\roof-consensus-20261021` | [roof-consensus/README.md](../2026-10-21/roof-consensus/README.md) |

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
1. **Fine-tune: stopped (October 21).** Neither run-1 nor run-2 (with the 252 rare-class labels) beat the released model on the
   held-out labels; FRACTAL files fences and poles as "other" and the fine-tunes never learned "structure"; they help buildings a
   little and cost a little elsewhere ([fractal-finetune/README.md](fractal-finetune/README.md)). The released model plus rules
   v2 stays the current classification. The labels are now the yardstick for rules and products.
2. **Esri building run:** complete (October 21). Outputs in `runs\esri-building-20261020\<tile>\building`.
3. **Labels:** relabel Q2-0010 on the page, import (`label_page.bat import --apply`), back up with
   `training_labels.bat save`, then score audit 2 (`audit-2/README.md`). Refined and rare-class answers are all imported.
4. **Canopy from the combined classification:** rasters rebuilt and compared (October 22); treetops, crowns and cover wait
   for Brian's review (see PICK UP HERE).
5. Then: a batch-1 control of the Esri model on 12TVL2804 on this card.

## 4. Open decisions for Brian
1. Whether to try a building-only fine-tune later (the one place both runs helped), or leave models as they are.
2. Rule 12 (18.7 M building points FRACTAL calls ground) and rule 15 (water or bridge): still proposed only.
3. Whether the consensus building layer replaces the October 19 one in the products people use (it is a separate
   layer for now), and how to treat the 459 footprints whose lower roofs only the native classification saw.
4. Whether the combined classification feeds the canopy surface, and so the treetops and cover (step 4 above tests it).

## 5. Workstation health
On October 20 the workstation crashed outright (bugcheck 0x3B, access violation in kernel code; minidump
`C:\WINDOWS\Minidump\102026-15265-01.dmp`) with WHEA 17 corrected PCI Express errors logged, on top of the September record in
the [September 30 handoff](../2026-09-30/HANDOFF.md#7-workstation-health-found-september-30-read-from-the-windows-event-log).
No label or answer was lost (the page writes atomically; the geodatabases opened intact). Earlier the same day, passes crashed
at the memory commit limit with Chrome and Teams open. Guards now in place: jobs wait for commit headroom (6 GB for FRACTAL
inference, 8 GB for the fine-tune), crashed passes rerun on their own, uneven passes are rejected.
For IT: memory test, GPU reseat and PCIe link check, WinDbg on the minidump; a larger page file. Not ours to change.

On October 21, before a GPU job: **quit** (from the system tray, not just the window) ChatGPT, Teams and Chrome. ChatGPT kept
3 GB after its window closed; Chrome grew to 4.9 GB during labelling; Teams and other desktop apps also take GPU memory, which
pushed fine-tune run-2 over the card's 16 GB into shared memory and made it two to three times slower. One data build crashed
silently at about 7 GB of headroom and succeeded on rerun. The Esri building run's first-try failures (ERROR 999999 in the
classify tool, about 1 tile in 6) all succeeded on retry.
**A likely memory fault, October 21, 15:15:** the same roof verification ran three times on identical code and data. The first
stopped with "Exclusion frame digest mismatch" although every packet's frame verifies on disk and in a fresh process; the
second died silently; the third completed. A checksum changing in memory points at RAM, so it strengthens the case for the
memory test. The guards did their job: no wrong result was written. Treat a single odd result on this machine as a reason
to rerun.

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
