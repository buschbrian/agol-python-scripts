# Treetop review evidence, rebuilt (October 22, 2026)

The October 15 treetop evidence (the SUSPECT flags on the October 8 treetops, `runs\treetop-evidence-20261015`) was made by a
script that is not in this repository, nor on U:, nor on GitHub; its run read the SSD as H:, so it was most likely written
on the laptop (look there for something like `treetop_evidence.py` to file it beside this). Brian asked on October 22 to
rebuild it from the manifest's rules and to look for it.

## The rebuilt module: [canopy/treetop_evidence.py](../../../canopy/treetop_evidence.py)
ArcPy-free, from the manifest's definitions and rules (`rules_version` treetop-evidence/2). Settled by matching the stored
values, where the description left a choice open:
- points: the tile's own points plus, from every neighbouring tile, its points within 5 m of their shared edges (October 15's
  `strips\<tile>.npz` are a tile's own edge band, read by its neighbours); all returns, classes as stored;
- near-building: class-6 points within 1 m (count, 90th-percentile Z minus the median class-2 Z within 5 m, HEIGHT_M against
  it); building distance to the nearest class-6 point out to 5 m;
- top: non-ground, non-noise points within 1 m, from the highest down 1 m; top_hag = highest minus ground; shape from
  `triage.eigen_features`; context: non-ground, non-noise points within 3 m at least 0.3 m above ground;
- flags with the manifest's thresholds; CANOPY_RETURNS and FLAT_TOP both need at least 12 top points; SUSPECT = ROOF_HEIGHT,
  FLAT_TOP, WIRE_HINT or WALL_HINT (POLE_HINT and OVERHANG reported, not suspect).
Tests: `tests/test_treetop_evidence.py` (flat roof, overhanging tree, pole, the SUSPECT union).

## Proof: it reproduces October 15 exactly ([reproduction.json](reproduction.json))
`run_evidence.py reproduce` on the October 8 treetops and working LAS: **all 61 tiles, all 607,972 treetops, every one of
16 measurements and 9 flags equal to the stored values** (91,807 SUSPECT), and the CSV byte-identical to October 15's
(same SHA-256 once line endings match; the driver now writes Windows line endings as October 15 did).

## The rebuilt treetops ([summary.json](summary.json); `runs\treetop-evidence-20261022\treetop-evidence.csv`)
`run_evidence.py rebuilt`: the 527,140 treetops of the rebuilt count, measured on the combined classification (consensus
buildings, rules-v2 ground and the rest; other point attributes from the working LAS). Same columns and decimals as October 15.

| | October 8 treetops, October 15 | Rebuilt treetops, October 22 |
|---|---:|---:|
| Treetops | 607,972 | 527,140 |
| **SUSPECT** | 91,807 (15.1%) | **32,986 (6.3%)** |
| ROOF_HEIGHT (peak at roof height) | 86,340 | 29,999 |
| NEAR_BUILDING (class 6 within 1 m) | 115,780 | 53,461 |
| OVERHANG (more than 2 m above the roof) | 16,124 | 16,332 |
| FLAT_TOP | 4,875 | 2,692 |
| WIRE_HINT | 2,413 | 1,098 |
| WALL_HINT | 579 | 404 |
| POLE_HINT (reported, not suspect) | 34,771 | 25,844 |
| CANOPY_RETURNS | 354,882 (58.4%) | 347,353 (65.9%) |

Roof-edge suspects fall by two thirds while trees overhanging roofs stay at about 16,000: the rebuild removed peaks on roof
edges, not the trees beside them. The 32,986 remaining SUSPECT treetops are the review list for the new count.

```
<Myria3D python> reviews\2026-10-22\treetop-evidence\run_evidence.py reproduce NEW_FOLDER --workers 3
<Myria3D python> reviews\2026-10-22\treetop-evidence\run_evidence.py rebuilt NEW_FOLDER --workers 3
```
These are review evidence, never labels: they must not enter reference.gdb, training labels or a score, and a flagged
treetop is not thereby a false detection.
