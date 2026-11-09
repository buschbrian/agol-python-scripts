# Regularized LiDAR-first outlines, checked against LoD2.2 (November 9, 2026)

Brian, November 9: the LiDAR-first outlines are the base, regularized, with roofer LoD2.2 as a cross-check. County data is the
last option, and newer data should fill what the LiDAR cannot settle. **Unvalidated planning estimates; nothing is uploaded.**

`regularize_outlines.py` runs Regularize Building Footprint (right angles and diagonals, 0.75 m tolerance) on the 24,459 final
city2 outlines, which had been cut at lot lines and filled under trees after their first regularization. Output:
`runs\lidar-footprints-20261109\regularized.gdb\buildings`, with `REG_STATUS`, `REG_IOU` and `REG_AREA_M2`.

| Result | Outlines |
|---|---:|
| Regularized | 20,462 |
| Regularized after a 0.5 m close (slits and spikes from tree fill) | 3,644 |
| Kept: moved too far (IoU under 0.85) | 295 |
| Kept: the tool produced an invalid polygon | 50 |
| Kept: the tool failed | 8 |

An invalid polygon makes roofer drop its whole tile while exiting 0, so `restore_invalid` puts the input back and then
runs an OGC repair on whatever is still invalid (49 features). The first run lost two tiles this way.

`lod22_check.py` runs roofer 1.0.0 on those outlines with the October points and settings, and writes
`roofer\lod22-flags.csv`: 23,516 OK, 860 with a fit error over 0.5 m, 83 with a part that has no model. The 0.5 m cut is a
proposal, not calibrated (median 0.19 m, 99th percentile 0.75 m). A flag means look at it. It does not say the outline is wrong.

County data still enters in two places: the tree fill, and the test that rejoins pieces across a lot line. Decisions are
unchanged until Brian settles the 550 joins in `../../2026-10-26/lidar-footprints/DECISIONS.md`.
