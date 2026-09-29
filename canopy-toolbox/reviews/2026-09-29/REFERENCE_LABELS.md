# Fixed-sample reference labelling — September 29, 2026

This slice makes the independent-label step runnable before classification tuning.
It adds a blind CSV worksheet, strict import preview, transactional application,
and before/after audit records. It does not create reference answers automatically.

The first batch contains 743 units selected by the existing seeded BATCH field:
314 treetops, 153 omission-search points, 180 CHM-cell points, and 96 crown outlines.
The complete reference remains 1,468 units. Round-up within strata means batch 1
contains slightly more than half the units. No new draws or variant-based
prioritization were introduced.

The packet is in
`C:\Users\Brian\.codex\visualizations\2026\09\29\01a0eed4-e40e-7762-9845-97159217cf5b\reference-review-batch1\`:

- `REVIEW.md`: review rules, label definitions and a link to the existing ArcGIS project.
- `labels.csv`: answer worksheet, with the first batch in REVIEW_ORDER per sample type.
- `packet.json`: coordinator metadata binding the worksheet to the reference frame.
- `preview-check.json`: read-only check of the actual exported packet, including reference-state digest.

Open the existing project at
`H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29\validation\review\validation_review.aprx`.
Find a worksheet SAMPLE_ID in its corresponding sample layer. Label using
acquisition-matched reference imagery or independent field evidence. Disable
baseline CHM/full crown overlays for point questions; for crown questions inspect
the sampled outline. Keep stratum diagnostics and all variants hidden. If height,
imagery alignment or object identity is unclear, use UNSURE and document why.
Do not select only easy cases: the stratified estimator assumes random usable
labels within each stratum. Review a prefix in the saved order.

Only edit LABEL, ROOF_IN_OUTLINE, REVIEWER, REVIEW_DATE and NOTES. SAMPLE,
SAMPLE_ID, REVIEW_ORDER and UNIT_TOKEN identify the fixed review unit. Point and
crown labels have distinct domains. Roof inclusion applies to crowns only and
may be left unassessed. Reviewer and a YYYY-MM-DD date are required for each
submitted nonblank label. Unreviewed labels stay blank. UNSURE counts as reviewed
but does not contribute a usable object label to accuracy estimates.

From `V:\Developer\agol-python-scripts\canopy-toolbox`, in PowerShell:

```powershell
$python = 'C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe'
$packet = 'C:\Users\Brian\.codex\visualizations\2026\09\29\01a0eed4-e40e-7762-9845-97159217cf5b\reference-review-batch1'

# Preview completed or partially completed answers. This does not change the GDB.
& $python -B reviews/2026-09-29/validation_harness.py import-labels "$packet\labels.csv"

# After independent review, apply with a new audit directory for this attempt.
& $python -B reviews/2026-09-29/validation_harness.py import-labels "$packet\labels.csv" --apply --audit-dir scratch/label-import-first-batch

# Compare variants on the same reference answers.
& $python -B reviews/2026-09-29/validation_harness.py score
```

For a fresh packet, use `export-labels --packet-dir NEW_PATH --batch 1`,
`--batch 2`, or `--batch all`. Global `--out` precedes the command and denotes the
existing validation directory containing reference.gdb. Do not call `sample` on
the labelled reference to refresh a worksheet.

Partial CSV files are accepted, but their submitted rows must belong to the
packet. Duplicate IDs, edited tokens/order, foreign references, changed sample
geometry or sampling design, malformed columns, out-of-domain labels, overlong
fields, and invalid/missing reviewer dates all fail before application. Blank
labels never delete answers. A repeated identical answer leaves the first
reviewer's metadata intact. Replacing an existing conflicting answer requires
explicit `--replace-existing`; the preview and audit show both values.

The frame token covers identity, geometry and design while excluding review
answers, so a packet remains valid after labels are added. The submitted CSV and
packet bytes are captured once; the audit records those exact bytes even if a
file changes later. The reference and existing answers are revalidated inside the
edit session. Updates touch only review fields. An interruption raised during an
edit rolls back the whole batch, including changes made before the failure.
This follows the [ArcGIS Editor transaction contract](https://doc.esri.com/en/arcgis-pro/latest/arcpy/data-access/editor.html).

Each application writes `import.json` and `submitted-labels.csv` in a new audit
directory. Status APPLIED is written after commit; ROLLED_BACK describes a failed
edit transaction. PENDING/PENDING_COMMIT indicates an interrupted attempt whose
final outcome needs checking against the stored before/after values, including
the narrow window between database commit and final audit-file write. Preview
requires no edit session and does not create an application audit.

Real first-batch export/preview passed with zero proposed changes and the complete
reference state unchanged. No real pilot labels or LAS were edited in this slice.
Synthetic ArcGIS cases verify actual application, idempotent reimport, invalid
mixed-batch rejection, moved-reference rejection and rollback after a first write.

The final complete ArcGIS Pro Python suite ran 177 tests in 524.788 seconds:
176 passed and one expected delivery mock test was skipped because the real
ArcPy fixtures cover it. This includes 14 pure worksheet tests and five actual
ArcGIS label-exchange tests. The full run also exposed a failed-preparation
fixture from the preceding slice that polluted the shared test workspace; that
fixture now has a dedicated directory. Its ordered pair with the tiled-run test
passed, followed by the complete suite. Production preparation guards were kept.
