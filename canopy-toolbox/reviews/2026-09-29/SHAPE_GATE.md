# Shape gate for walls, poles and wires

`shape-gate` implements item 3 of the [classification review](CLASSIFICATION_REVIEW.md):
use point shape to find walls, poles and wires that the height classifier labelled as
vegetation. The earlier review asked to keep shape features as review evidence until they
were calibrated. The command therefore writes **review evidence by default**. It changes
classes only with an explicit `--apply`, and then only on a new prepared copy.

Code: [canopy/shape_gate.py](../../canopy/shape_gate.py) (no ArcPy). Tests:
[tests/test_shape_gate.py](../../tests/test_shape_gate.py).

```powershell
# Review evidence (no ArcPy needed): LAS copies with review codes, report, per-point features
python -m canopy shape-gate INPUT\prepared.lasd NEW_REVIEW --extent XMIN YMIN XMAX YMAX
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
| 65 | wall_like | planarity ≥ 0.6, normal horizontal |
| 66 | linear | linearity ≥ 0.6, sloped axis (roof rakes, guy wires, branches) |
| 67 | scattered | scattering ≥ 0.6 |
| 68 | mixed | no dominant shape |
| 69 | wire | linearity ≥ 0.6, horizontal axis |
| 70 | pole | linearity ≥ 0.6, vertical axis |
| 71 | sparse | fewer than 17 points within 5 m, or degenerate |

Codes 64–68 keep the diagnostic's meanings, except that 66 no longer contains wires and poles.
The footprint review-label copies from `reconcile-buildings` use codes 64–70 with unrelated
meanings; symbolise each file type with its own table. Codes 64 and above exist only in LAS point
formats 6–10, so review mode refuses legacy files. Outside `--extent`, review copies keep their
original classes.

**Review codes and `--apply` selections are never scoring truth.** They are rule outputs and
must not become reference labels, training labels or evaluation answers.

## The apply rule

A point moves from class 4 or 5 (`--classes` can add 3) to class **1** only when all of the
following hold:

1. It is not withheld, synthetic or overlap.
2. Its group is wall_like, wire or pole.
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
  neighbour count, own single return, both shares and the nearest building distance.
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

1. **Verticality definition.** The normal-based wall definition follows the diagnostic's
   documentation, not its code. Please confirm that it should be canonical.
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
