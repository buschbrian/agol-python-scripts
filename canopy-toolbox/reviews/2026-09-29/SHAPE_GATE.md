# Shape gate for walls, poles and wires

`shape-gate` implements item 3 of the [classification review](CLASSIFICATION_REVIEW.md):
use point shape to find walls, poles and wires that the height classifier labelled as
vegetation. The earlier review asked to keep shape features as review evidence until they
were calibrated. The command therefore writes **review evidence by default**. It changes
classes only with an explicit `--apply`, and then only on a new prepared copy.

Code: [canopy/shape_gate.py](../../canopy/shape_gate.py) (no ArcPy; the ground raster for the minimum
wall height comes from [canopy/hag.py](../../canopy/hag.py)'s ArcGIS builder, injected by the CLI). Tests:
[tests/test_shape_gate.py](../../tests/test_shape_gate.py).

```powershell
# Both modes need ArcGIS Pro Python (PYTHONNOUSERSITE=1) since 30 September: the minimum wall height
# uses the pipeline DTM. Review evidence: LAS copies with review codes, report, per-point features
python -m canopy shape-gate INPUT\prepared.lasd NEW_REVIEW --extent XMIN YMIN XMAX YMAX [--min-wall-height 0.7]
# Opt-in change on a NEW prepared dataset (ArcGIS Pro Python; creates prepared.lasd)
python -m canopy shape-gate INPUT\prepared.lasd NEW_PREPARED --apply [--extent ...] [--classes 4 5]
python -m canopy run NEW_PREPARED\prepared.lasd NEW_RUN --extent ...
```

The input is any completed preparation: `prepare` output, or `refine-roofs` output. Existing
outputs, and outputs inside the input folder, are refused. The input files are opened read-only.
Their size and modification time are checked again at the end.

## What it computes

The neighbourhood of a point is the point itself and its 16 nearest neighbours in 3D. Only
non-ground, non-noise points count: class 2, 7 and 18 are excluded, and so are withheld,
synthetic and overlap points. This is the 17-point set that PDAL `filters.covariancefeatures`
uses with `knn=16`, as in the [diagnostic](shape_diagnostic.py). A test in ArcGIS Pro Python
checks linearity, planarity, scattering and PDAL's verticality against PDAL 3.5 to 1e-5.

From the square-root eigenvalues s1 ≥ s2 ≥ s3 (PDAL's default SQRT mode):

| Feature | Definition |
|---|---|
| linearity, planarity, scattering | (s1−s2)/s1, (s2−s3)/s1, s3/s1; they sum to 1 |
| normal_z | \|z\| of the plane normal (smallest-eigenvalue eigenvector) |
| axis_z | \|z\| of the principal axis (largest-eigenvalue eigenvector) |
| pdal_verticality | PDAL's `Verticality`, recorded only for comparison |
| single_share | share of the 17 points that are single returns |
| irregular_share | share of the 17 points whose own group is scattered or mixed |
| nearest_building_m | 3D distance to the nearest class-6 point, up to 5 m |
| hag_m | height above ground: Z minus the pipeline-DTM cell containing the point (see [HAG.md](HAG.md)) |

**The diagnostic's wall gate measured something other than its documentation.** Its comment
says `Verticality` is 1 − |normal z|. PDAL instead computes the z share of an
eigenvalue-weighted unary vector. On synthetic shapes, an isotropic vertical wall scores 0.707,
a 45° plane 0.52, and a vertical line 1.0. With the 0.7 gate, a real wall was classed as a wall
only when its neighbourhood spread more vertically than horizontally. `shape-gate` uses the
plane normal, as the diagnostic documented, and keeps PDAL's value in the audit files. On the
pilot extent, the normal-based rule finds 285 class-5 wall-like points; the diagnostic's rule
finds 82.

## Groups and codes (prespecified)

The thresholds are the diagnostic's screening values: dominant share 0.6 and vertical 0.7. A
direction counts as horizontal when its vertical component is at most 1 − 0.7 = 0.3. It counts as
vertical when its horizontal component is at most 0.3; both limits are 17.5°. No threshold was
fitted to data. None was tuned against the fixed reference, whose batch 1 is still being labelled.

| Code | Group | Rule |
|---:|---|---|
| 64 | roof_like | planarity ≥ 0.6, normal not horizontal |
| 65 | wall_like | planarity ≥ 0.6, normal horizontal, **at least 0.7 m above ground** |
| 66 | linear | linearity ≥ 0.6, sloped axis (roof rakes, guy wires, branches) |
| 67 | scattered | scattering ≥ 0.6 |
| 68 | mixed | no dominant shape |
| 69 | wire | linearity ≥ 0.6, horizontal axis |
| 70 | pole | linearity ≥ 0.6, vertical axis |
| 71 | sparse | fewer than 17 points within 5 m, or degenerate |
| 72 | low_wall | wall-shaped (as 65) but less than 0.7 m above ground, or over a ground NoData cell; review only |

Codes 64–68 keep the diagnostic's meanings, except that 66 no longer contains wires and poles.

**Minimum wall height (decided 29 September).** The steepness threshold stays 0.7 (1 − |normal z|).
A wall-shaped point must also stand at least `--min-wall-height` (default **0.7 m**) above ground,
so that curbs, edging and low retaining edges are not walls. Height above ground is Z minus the
value of the 0.5 m pipeline-DTM cell (class-2 ground, natural neighbour) containing the point. It is
the same definition and code as the [HAG dataset](HAG.md). The raster covers the gated extent plus
20 m, clipped to the preparation; the context keeps TIN edge effects out of the gate. HAG is rounded
to 0.1 mm before comparison, so float32 coordinate noise cannot move a point across the boundary.
A point exactly 0.70 m above ground is wall_like. Wall-shaped points below it, or over NoData where
the height cannot be shown, become **low_wall (72)**. That is a separate review group, **never
eligible for `--apply`**, and it does not count as scattered or mixed in the neighbourhood share.
The manifest's `wall_height` block counts wall-shaped, wall_like and low_wall points, and those
without ground.
The footprint review-label copies from `reconcile-buildings` use codes 64–70 with unrelated
meanings; symbolise each file type with its own table. Codes 64–72 exist only in LAS point
formats 6–10, so review mode refuses legacy files. Outside `--extent`, review copies keep their
original classes.

**Review codes and `--apply` selections are never scoring truth.** They are rule outputs and
must not become reference labels, training labels or evaluation answers.

## The apply rule

A point moves from class 4 or 5 (`--classes` can add 3) to class **1** only when all of the
following hold:

1. It is not withheld, synthetic or overlap.
2. Its group is wall_like (so at least 0.7 m above ground; low_wall never qualifies), wire or pole.
3. It is a single return.
4. At least 0.6 of its 17-point neighbourhood are single returns.
5. At most 0.4 of that neighbourhood is scattered or mixed.

Roof-like points are excluded, because hedge tops, car roofs and lawns are roof-like; roof edges
belong to `refine-roofs`. Sloped linear points are excluded because branches are sloped lines.
Walls go to class 1, not class 6, because a vertical plane is not proof of a building.

The output is a complete prepared dataset. Every input file is copied, so `canopy run` reads it
exactly as it reads `refine-roofs` output. With `--extent`, points outside the gated extent are
copied unchanged; `gate_extent` in the manifest records the part that was gated. The output has
the same audit trail:

- `changes/<file>.npz` holds point indices, previous and new class bytes, group, all features,
  neighbour count, own single return, both shares, the nearest building distance and `hag_m`.
- `ground/ground.tif` is the read-only ground raster. The manifest's `ground` block records its
  method, extent, NoData cells and SHA-256.
- `preparation.json` records the thresholds, the rule text, gated and prepared extents, input
  file sizes and modification times, counts at each rule stage, and changes by class, group,
  return type and building proximity. It also records before/after class counts, timings, peak
  working set, and `EXPERIMENTAL_UNVALIDATED`.
- Only classification bytes change. Legacy key-point, synthetic and withheld bits are kept.
  Coordinates, returns, flags, other classes (including noise 7/18) and every other byte are
  unchanged.

## Bounds

Neighbourhoods are capped at 5 m. Each 100 m block is computed from points within 10.02 m of it,
so every neighbour of every neighbour is present. Tests show that small blocks give exactly the
single-pass result. The gated extent plus its halo is limited to 6,250,000 half-metre cells
(a 1.25 km square), the same as the roof local grid. At most 40,000,000 non-ground points are
loaded. An extent within 10.02 m of the prepared edge is flagged as `edge_effects_possible`.
The flag refers to the prepared boundary, not the tile. It is therefore always set for the
default extent, the whole preparation, although the 50 m buffer keeps the tile itself clear of
edge effects. The whole-tile memory and runtime have not yet been measured.

## Pilot (12TVL2804, 250 m, 29 September)

Extent `428250 4504250 428500 4504500` of the baseline preparation. Outputs are in ignored
`scratch/shape-gate-pilot-20260929/`. Record: [shape-gate-pilot-12TVL2804.json](shape-gate-pilot-12TVL2804.json).
Both runs used ArcGIS Pro Python at below-normal priority, CPU only.

| Class | Points | wall_like | wire | pole | linear | roof_like | scattered | mixed | sparse |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 322,272 | 2 | 227 | 4 | 2 | 301,013 | 113 | 20,911 | 0 |
| 4 | 26,282 | 140 | 1,036 | 45 | 108 | 8,038 | 608 | 16,307 | 0 |
| 5 | 186,182 | 285 | 1,080 | 104 | 743 | 17,793 | 15,856 | 150,215 | 106 |

- **Review:** 849,595 points loaded and 534,736 recoded. The run took 15.2 s by its manifest
  (19 s wall clock), with a peak working set of 0.99 GB. The peak includes memory-mapped LAS pages.
- **Apply:** the rule changed **0 points**. The rule-stage counts show why. Of 212,464 class 4/5
  points, 2,690 are wall-like, wire or pole. Only 18 of those are single returns, and 4 pass the
  neighbourhood single-return share. None passes the neighbourhood shape test. The run took
  22.5 s by its manifest (35 s wall clock), with a peak working set of 1.21 GB.
- **Why wires fail:** a pulse that hits a wire usually continues to the ground. The wire return
  is then the first of several: 962 of 1,036 class-4 wire points, and 800 of 1,080 in class 5.
  Walls and poles behave the same way. The review's "single-return" condition removes nearly all
  of them ([breakdown script](shape_gate_breakdown.py)). This is a pilot observation, not a label
  result. The rule was not changed in response.
- **Integrity:** [shape_gate_integrity.py](shape_gate_integrity.py) compared every copied file
  byte by byte with its input and passed for both folders. In the review copy of 12TVL2804.las,
  534,736 bytes differ. All are classification bytes at the logged indices, with the logged
  previous and new values. No other byte differs. The eight apply copies are identical to their
  inputs, and their logs are empty. The source `12TVL2804.las` kept its size (809,475,416 bytes),
  modification time and MD5 `82787095336690d2909344206f9a80fc`. The prepared folder's file
  listing was unchanged.
- **Consumption:** `canopy run` on the apply output (same extent, 125 m tiles) completed in
  42 s.

## Minimum wall height rerun (12TVL2804, 30 September)

Same extent, input and parameters as above, plus `min_wall_height` 0.7. Outputs are in ignored
`scratch/shape-gate-pilot-20260930/{review,apply}`. Record:
[shape-gate-pilot-12TVL2804-20260930.json](shape-gate-pilot-12TVL2804-20260930.json).

| Class | Points | wall_like before → after | low_wall | all other groups |
|---|---:|---:|---:|---|
| 3 | 322,272 | 2 → **0** | **2** | unchanged |
| 4 | 26,282 | 140 → 140 | 0 | unchanged |
| 5 | 186,182 | 285 → 285 | 0 | unchanged |

- **The rule is nearly inert here, by construction.** Preparation's height classes put class 4 at
  0.5–2 m and class 5 above 2 m. Only class 3, which is not in the default `--apply` classes, and
  class 4 between 0.5 and 0.7 m can be affected. The two low_wall points are class-3 points 0.065 m
  and 0.118 m above ground. The lowest remaining wall_like point is 1.03 m above ground. No
  candidate lacked ground (0 of 534,736).
- **Apply:** 0 points changed, as before. The rule-stage counts are identical: 212,464 eligible,
  2,690 in an apply group, 18 own-single, 4 pass the single-return share, 0 changed.
- **Ground check:** the gate raster (428230–428520 E, 4504230–4504520 N, 0 NoData cells) was compared
  cell by cell with the whole-tile HAG raster (`hag-20260929\12TVL2804\ground\ground.tif`). Inside the
  gated extent, 1 of 250,000 cells differs, by 0.12 mm. In the 20 m context rim, cells differ by up to
  0.36 m (99th percentile 3.5 cm). That is the TIN edge effect the context absorbs. Both pilot runs
  built byte-identical gate rasters.
- **Time and memory:** review 52.2 s by the manifest (64 s wall clock), of which 38.2 s was the
  ground raster (previously 15.2 s in total). Apply 60.5 s (70 s wall clock). Peak working set
  1.37 GB for both. The runs used ArcGIS Pro Python at below-normal priority, CPU only.
- **Integrity:** [shape_gate_integrity.py](shape_gate_integrity.py), unmodified, passed every check for
  the apply folder: 8 identical copies and empty logs. For the review folder, every byte check passed:
  534,736 changed bytes, all classification bytes at the logged indices with the logged values, 0
  other bytes, same sizes, identical headers, VLRs and trailing bytes. The one failing field is
  `new_classes_allowed`, because the script allows codes 64–71 and low_wall is 72. A separate
  check confirmed that all review codes lie within 64–72. The script's `range(64, 72)` needs to become
  `range(64, 73)`. That file was outside this change's ownership and was left unchanged. The source
  `12TVL2804.las` kept MD5 `82787095336690d2909344206f9a80fc`, and the prepared folder listing (sizes
  and mtimes) was unchanged.

## Scoring as a variant (after labels exist)

The fixed reference is scored on whole tiles with the baseline grid. For each pilot tile, a
variant needs a whole-tile apply and a run with the baseline parameters:

```powershell
python -m canopy shape-gate {root}\{tile}\prepared\prepared.lasd {root}\shape-gate\{tile}\prepared --apply
python -m canopy run {root}\shape-gate\{tile}\prepared\prepared.lasd {root}\shape-gate\{tile}\run --extent <tile extent>
python reviews/2026-09-29/validation_harness.py score --run baseline={root}\{tile}\run --run shape-gate={root}\shape-gate\{tile}\run
```

Do this only after batch 1 labels are imported, and only as a comparison. With the current rule
it would score as nearly identical to the baseline, since it changes almost nothing. Measure the
whole-tile memory first.

## Known confusions

- **Clipped hedges.** The sides are vertical planes. If they return single echoes, the rule
  moves them to class 1; the synthetic test asserts this. Only returns that penetrate the hedge
  protect it. A hedge over 2 m is class 5 and reaches the CHM.
- **Building facades** become class 1, not 6. Facades under a detected roof are already class 6
  from the building classifier's below-roof option.
- **Roof corners and ridges** are mostly mixed, and roof faces are roof_like; neither is ever
  selected. Branches are sloped linear, or mixed inside crowns, and are not selected.
- **Sparse points** (fewer than 17 within 5 m) are never selected.

## Decisions for the user

1. **Verticality definition.** Settled on 29 September: keep the normal-based steepness threshold
   0.7 and add the 0.7 m minimum height, now implemented. Still open:
   - Should low_wall points over ground NoData (none on the pilot) stay low_wall, or get their own
     code?
   - Should the height rule also apply to wires and poles? It currently does not.
2. **Do not use `--apply` in any pipeline input before labels exist.** It is inert on the pilot
   extent. If a later rule changes points, it is still unvalidated. Treat it only as a scored
   variant.
3. **Calibration, if wanted.** The return condition is what blocks wires and poles. A different
   return rule, such as allowing first-of-many returns, is a calibration choice. Make it on a
   **separate calibration sample**:
   - stratified by shape group and class;
   - drawn outside the fixed reference frame (another tile or a held-out area), never batch 1;
   - labelled from class-hidden lidar cross-sections, with Esri World Imagery (capture date
     recorded per location) for human visual reference only.

   The prespecified rule then stays as the pre-registered comparison. Any recalibrated rule
   would be evaluated once on the fixed reference.
