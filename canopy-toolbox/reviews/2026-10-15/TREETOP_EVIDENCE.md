# Treetop review evidence for the city count (October 15, 2026)

The October 8 count detected **607,972 candidate treetops**. It used the baseline classification, in which every
above-ground point that Classify LAS Building misses becomes "vegetation" by height. Roof edges, wires and walls
therefore reach the CHM and become peaks. This pass measures, for every treetop, the evidence that it sits on one
of them. **The count itself is not changed. Every flag is a fixed rule output: review evidence, not a label, not an
error and not a correction.** Error rates still need the independent reference labels.

## Result

| Flag (rules `treetop-evidence/2`) | Treetops | Share | What it means |
|---|---:|---:|---|
| NEAR_BUILDING | 115,780 | 19.0% | a class-6 point within 1 m horizontally |
| ROOF_HEIGHT | 86,340 | 14.2% | near a building and no more than 0.5 m above the local roof |
| OVERHANG | 16,124 | 2.7% | near a building and more than 2 m above the roof: probably real canopy over a house |
| FLAT_TOP | 4,875 | 0.8% | the top 1 m is a thin, flat plane with almost no vegetation returns (sheds, carports, vehicles) |
| WIRE_HINT | 2,413 | 0.4% | the above-ground points within 3 m are one horizontal line at least 4 m up, at least 2 m from any building point |
| WALL_HINT | 579 | 0.1% | the top is a thin vertical plane within 2.5 m of a building point |
| POLE_HINT (not in SUSPECT) | 34,771 | 5.7% | a vertical line within 3 m; mostly tall narrow crowns, see correction 1 |
| CANOPY_RETURNS | 354,882 | 58.4% | the top is not a thin surface and at least 30% of its returns are non-last |
| **SUSPECT** (roof height, flat top, wire or wall) | **91,807** | **15.1%** | |
| SUSPECT and no CANOPY_RETURNS | 76,803 | 12.6% | |

Read the result as a range, not a corrected count. If every SUSPECT treetop were a false detection, the count would
be 516,165. If only those without canopy-like returns were, it would be 531,169. Neither is established: a tree
whose top is level with the eaves is ROOF_HEIGHT, and an edge return can look like canopy. NEAR_BUILDING bands:
86,340 at roof height, 11,055 between 0.5 and 2 m above it, 16,124 more than 2 m above it, and 2,261 with no
class-2 point within 5 m.

By parcel ownership, which is physically consistent with the flags (wires run along streets, and roof edges are on houses):

| Ownership | Treetops | SUSPECT | ROOF_HEIGHT | WIRE_HINT | FLAT_TOP | SUSPECT, no canopy returns |
|---|---:|---:|---:|---:|---:|---:|
| Private | 454,849 | 87,060 | 84,051 | 476 | 4,313 | 72,579 |
| Public / government | 75,176 | 1,632 | 1,509 | 24 | 110 | 1,338 |
| No parcel | 59,212 | 2,638 | 437 | 1,906 | 307 | 2,476 |
| Uncertain owner | 18,735 | 477 | 343 | 7 | 145 | 410 |

Tiles with the most suspects are residential: 12TVL2702 (4,362), 2704 (3,632), 2603 (3,188), 3005 and 3006
(3,160 each). Per-tile counts are in [city-evidence-manifest.json](city-evidence-manifest.json).

## Outputs

On the SSD, in a new folder; `city-count-20261008` was not written:

```text
H:\lidar\2023-salt-lake-valley\runs\treetop-evidence-20261015
  treetop-evidence.gdb\treetop_evidence   607,972 points, EPSG 6341, estimate warning in metadata
  treetop-evidence.csv                    same columns, TREE_ID joins to city_treetops
  tiles\<tile>.npz/.json, strips\         per-tile features and neighbour strips
  manifest.json, verification.json, gdb.json
```

In Pro, add `treetop_evidence`, join or relate on TREE_ID if needed, and symbolise on SUSPECT, ROOF_HEIGHT or
WIRE_HINT. Every raw feature is stored, so a threshold can be changed later without reading the LAS again.

## Method

Code: [canopy/treetop_evidence_20261015.py](../../canopy/treetop_evidence_20261015.py) (no ArcPy; definitions in its
docstring), driver [treetop_evidence_driver.py](treetop_evidence_driver.py), tests
[tests/test_treetop_evidence_20261015.py](../../tests/test_treetop_evidence_20261015.py). The module was named
`canopy/treetop_evidence.py` until October 22, when an independent rebuild took that name
([2026-10-22/treetop-evidence](../2026-10-22/treetop-evidence/README.md)).

- **Near-building** is the 29 September [candidates_near_buildings.py](../2026-09-29/candidates_near_buildings.py)
  measurement, unchanged: class-6 points within 1 m, roof = 90th-percentile class-6 Z within 1 m minus the median
  class-2 Z within 5 m, compared with the treetop's HEIGHT_M. A unit test runs that script's loop beside the new code
  on random clouds and requires identical results.
- **Shape and returns** use clean (not withheld, synthetic or overlap) points other than ground and noise (classes 2,
  7, 18). The top set is the points within 1 m horizontally and within 1 m of the highest of them; the context is
  those within 3 m and at least 0.3 m above the local ground. Eigen features are `triage.eigen_features`. The thresholds are
  triage.py's ROOF, WIRE and WALL cues without their footprint and NAIP parts, which this pass does not use.
- Each tile reads its own prepared LAS plus a 5 m strip from every neighbouring tile, so treetops at tile edges see
  their whole neighbourhood. (The pilot measurement read only its own file; that is kept for the reproduction.)

### Corrections after the first pilot pass

Both were made from the geometry of unlabelled pilot treetops, before the citywide run; no human label was consulted.

Profile script and output: [pilot_feature_profile.py](pilot_feature_profile.py),
[pilot-feature-profile.json](pilot-feature-profile.json).

1. **POLE_HINT left SUSPECT.** On 12TVL2804 it held 2,120 treetops, mostly 8–20 m tall (10th–90th percentile), with a
   median crown of 13 m² and a median non-last share of 0.95 in their top 1 m: tall narrow crowns, which are vertical
   lines too within a 3 m context. Triage used NAIP greenness to separate them and still kept POLE as a hint only.
2. **CANOPY_RETURNS uses a thickness above 0.10 m** (FLAT_TOP's thin-plane limit) instead of triage's 0.25 m. A 1 m
   deep, 1 m radius cap cannot exceed about 0.29 m even when fully volumetric; at 0.25 m only 1,366 of 17,389 pilot
   treetops qualified. On the pilot, the thickness of the top separated the at-roof-height group (median 0.05 m)
   from the overhanging group (median 0.175 m).

## Verification

- **Pilot reproduction** ([pilot-reproduction.json](pilot-reproduction.json)): on the 29 September 12TVL2804 pilot run,
  the module reproduced the published 17,389 candidates, 4,428 within 1 m, the bands 3,293 / 376 / 706 and the 53
  without ground exactly, in 19 s. The source LAS kept its size and modification time.
- **City tile 12TVL2804** ([tile2804-evidence-manifest.json](tile2804-evidence-manifest.json)): 14,578 city treetops,
  2,982 SUSPECT (20.5%; pilot 19.9%), 26.3% near a building (pilot 25.5%). The city preparation's 2804 class counts
  are within 0.1% of the pilot's. The city count has fewer treetops because it used global plateau reconciliation
  and only treetops inside the boundary.
- **Citywide** ([city-evidence-manifest.json](city-evidence-manifest.json),
  [city-evidence-verification.json](city-evidence-verification.json)): 61 tiles in 409 s with four processes; no
  treetop fell outside a tile; all 607,972 TREE_IDs are unique and identical to `city-treetops.csv`, with matching
  X, Y and HEIGHT_M; all 61 LAS fingerprints and the treetop CSV SHA-256 were unchanged after the run. The feature
  class has 607,972 points in EPSG 6341, with the CSV's SUSPECT, ROOF_HEIGHT and WIRE_HINT counts. The two WGS84
  longitude/latitude fields that XY Table To Point added (named TILE_X and TILE_Y) were deleted; the driver now does that itself.
- Plain suite: 475 tests OK, 88 ArcGIS-only skips (454 before; 12 evidence and 9 calibration-sample tests added): [regression-tests.log](regression-tests.log).

## What this does not establish

- No precision, recall or error rate. A flag is a suspect; the count of suspects is not the count of false trees.
- NEAR_BUILDING and ROOF_HEIGHT read our own building class. Where Classify LAS Building missed a whole roof, a roof
  peak can be far from any class-6 point and is flagged only if its top is flat (FLAT_TOP).
- Wires that run through or beside a crown are not one clean line in the 3 m context and are not flagged. Most of
  those peaks are then the tree anyway.
- The rules have no calibration sample. Batch 1 of the reference must never be used to tune them.

## Next

1. **Calibration sample: drawn October 15, waiting for labels.** 350 treetops, blind, in six disjoint strata
   (WIRE, WALL, FLAT_TOP, ROOF_HEIGHT, POLE_ONLY, UNFLAGGED), seed 20261015, outside the evaluation frame and the two
   holdout tiles. See [packets/treetop-calibration-1/README.md](packets/treetop-calibration-1/README.md) and
   [calibration_sample.py](calibration_sample.py). Labelling it gives the first measured rate for each flag and the
   shape-gate calibration sample the 30 September handoff asked for. Batch 1 is not used.
   *Superseded on October 22, never labelled:* label
   [calibration sample 2](../2026-10-22/packets/treetop-calibration-2/README.md), drawn from the October 22 treetops.
2. **Esri Power Line Classification** pretrained model ([Esri](https://doc.arcgis.com/en/pretrained-models/latest/point-cloud/introduction-to-power-line-classification.htm)):
   RandLA-Net, X/Y/Z only, wires 14, poles 15, published validation F1 0.946 for wires and 0.622 for poles, 8 GB
   GPU recommended. It runs through Classify Point Cloud Using Trained Model, so it is the in-licence route for wires
   and belongs on the A4000. Compare its wire points with WIRE_HINT.
3. The evaluation labels (batch 1, 0 of 743), audit 2 (0 of 40) and the 58 training labels remain the gate for
   choosing a model conflict policy and for any corrected count.
