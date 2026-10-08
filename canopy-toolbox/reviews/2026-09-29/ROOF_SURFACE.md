# Interior roof faces and eave extrapolation

`refine-roofs --method local` is an experimental correction on **new prepared LAS
copies**. The plane method remains the default. Local defaults fit class-6
first/single returns, excluding synthetic, withheld and overlap returns. Class 4
and 5 candidates may change to 6; other classes and every non-classification byte
remain unchanged. Key-point flags survive in legacy LAS.

Face anchors and fitting neighbours must lie inside measured roof support, eroded
by a 0.5 m margin plus 0.5 m raster uncertainty. A trimmed local fit retains all
three coefficients, including its intercept. Boundary contamination therefore
cannot anchor a plane, and a rejected anchor outlier cannot move a fitted plane.
Interior faces extend to eaves: a candidate still needs measured roof support
within 1 m, but fitting anchors may lie within 2 m. At least three usable faces
must put it between 0.35 m below and 0.5 m above their predictions.

The coarse height prefilter includes that longer extrapolation reach. Local
support grids are limited to 6,250,000 half-metre cells; whole-AOI detection and
crown segmentation retain their separate 4,000,000-cell limit.

```powershell
python -m canopy refine-roofs INPUT/prepared.lasd NEW_OUTPUT --method local
```

Options belonging to the other method are rejected. The output preparation
manifest records thresholds, interior support, face rejection counts, timings,
input fingerprints and change counts. `changes/*.npz` stores point indices,
previous class bytes, residuals, support and votes. Newly changed points never
become fitting support.

## Verification

22 tests passed in ArcGIS Pro Python on September 29: clean gable and hip roofs,
contaminated upper/lower edges, trimmed anchor outliers, steps, courtyards,
overhanging canopy, lower vegetation, flags, returns and exact changed bytes in
legacy and modern LAS. A fresh residential 12TVL3302 pilot completed at
`scratch/integration-roof-interior-final-20260929`, preserving input file sizes and
timestamps. Its manifest is processing evidence, not an accuracy assessment.

Roof-level vegetation remains ambiguous. Sparse/narrow roof patches may have no
interior anchors; complex/steep faces are rejected. Inspect class-hidden lidar
cross-sections and acquisition-matched imagery before accepting corrected points.
Fitted residuals are not surveyed vertical accuracy, and footprint rule labels
64–70 cannot validate this method.
