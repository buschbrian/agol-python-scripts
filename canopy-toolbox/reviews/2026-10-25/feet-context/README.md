# Feet-first displays and app context — October 25, 2026

Brian asked for feet and for relevant context within the building, canopy and terrain apps. He also
confirmed CFTree as the citywide tree workflow; its separate feasibility pilot is in
[cftree-pilot](../cftree-pilot/README.md).

## Applied

- Existing ArcGIS building pop-ups: heights in international feet, footprint/roof areas in square feet,
  numeric nulls retained and true zero values retained. Source fields and geometry remain metric.
- Building and canopy height legends use feet. Contours explicitly show 6.56 ft and 32.81 ft, the existing
  2 m and 10 m spacing. Slope percentages and roof angles are unchanged.
- All three Instant Apps have expanded opening text and a persistent information panel with controls,
  acquisition dates, method explanations, limits, source links and units. Measurement tools use feet and
  square feet. The terrain app enables an imperial elevation profile. The canopy app describes the CFTree
  development direction and distinguishes inferred trunks from field measurements.
- Public Azure companion CSV: `millcreek-lidar/buildings/20261025/buildings_hybrid_v2_feet.csv`.
  Join using FP_ID. Seven lengths/elevations and eight areas converted; all 21,561 rows checked by reversing
  every conversion to its source value (absolute tolerance 0.000001 in source units). There are 831 blank
  roofer roof-area values on fallback buildings. Angles remain degrees; Z50 columns are elevations.
- No geometry, coordinate system, vertical datum, sharing or package bytes changed. The three apps remain
  private; the building scene/layer and Azure downloads retain their approved public access.

## Verification

Ten item configurations and complete metadata read back equal to the prepared plan, including unchanged
sharing, scene cameras, slides, ground and coordinate definitions. The Azure CSV downloads anonymously
with SHA-256 `93ac857718db1c019780a6f0716c01b380990a8298fa8b191ae0bc2c6a05d625` (5,067,386 bytes).

Signed-out Scene Viewer displayed FP_ID 15350: median 12.9 ft, upper height 19.1 ft, footprint 3,080 sq ft,
roof surface 3,246 sq ft, ridge 23.1 ft, eave 9.4 ft and flat roof area 0. These match the CSV after display
rounding. The private apps were checked through authenticated configuration readback and the deployed
Esri component code, not a signed-in browser session.

Required suite: 512 tests, 424 passed and 88 ArcPy-dependent skips. The sandbox blocked temporary-file
writes on the initial attempts; the same suite passed outside that filesystem sandbox. Source export was
verified in the actual ArcGIS Pro runtime. No geoprocessed geometry was changed by the unit update.

## Reproduce and rollback

`export_feet.py SOURCE_FEATURE_CLASS OUTPUT_CSV` runs in Pro and never edits the source. `update_apps.py`
uses a directory containing `before-*.json` snapshots. `prepare` is offline; `apply --go` checks all item
modification timestamps before sending anything. `verify` reads back every affected item; `revise --go`
first verifies the previous plan and then sends only newly changed items. It retains the original rollback
baseline. Do not rerun `prepare` over a live plan before `revise`.

`evidence/` retains original snapshots, final plans, API verification and test/CSV evidence. Restore an
item by sending its snapshot's `props` and `data` as the REST item update payload; sharing needs no rollback
because it was never changed. The original SLPK and prior public release rollback remain documented in
[buildings-release](../buildings-release/README.md).

Canonical display definitions: `../../2026-10-23/agol-styling/build_definitions.py` and `reader_context.py`.
App values: `../../2026-10-23/agol-apps/make_apps.py`. Original field units remain documented in
`../../2026-10-23/agol-metadata/buildings3d_v2.md`.
