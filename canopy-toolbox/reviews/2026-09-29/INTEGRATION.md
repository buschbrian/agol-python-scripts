# September 29 LiDAR integration

The authorized implementation slices are integrated on
`canopy/classification-refinement`, in scoped commits. Original LAS, existing
independent reference labels and historical worktree edits remain preserved.
No new worktree, environment switch, model inference, push or PR was performed.

| Slice | Result and evidence |
|---|---|
| Buildings/footprints | Merged commands and manual CLI hookup; 28 tests and fresh 250 m reconciliation. [BUILDINGS.md](BUILDINGS.md) explains sparse source heights and the empirical median peak-height ratio. |
| Interior roofs | Fixed boundary contamination and discarded fitted intercepts; 22 tests and fresh residential 3302 copies. [ROOF_SURFACE.md](ROOF_SURFACE.md). |
| Shared core | One ArcPy-free LAS reader/decoder and one physical roof-band definition; preserved legacy flags/Extra Bytes and sampling precedence; fresh shared-reader reconciliation. |
| September 23 | Selectively ported declared class-0 background, fresh-statistics guard, building method and dated WMS helper. Old sample/contact QA excluded. [SELECTIVE_PORT.md](SELECTIVE_PORT.md). |
| Evaluation | Primary analytic stratified Taylor/t intervals, finite-population correction and covariance; bootstrap cross-checks retained. [VALIDATION.md](VALIDATION.md). |
| Census/domains | Blind 12-plot packet, independent tree locations, one-to-one object scoring, omission causes, alignment/cross-section requirements and prospective training exclusion. [PLOT_CENSUS.md](PLOT_CENSUS.md). |
| Model preparation | Custom density/HAG experiment inputs and content provenance, tested using mocks. [MODEL_EXPERIMENTS.md](MODEL_EXPERIMENTS.md). |
| Greenness | Four-band NAIP review raster, immutable inputs, actual 250 m pilot. Its service-reported date is 2021-11-13, so it predates the lidar. [NAIP_GREENNESS.md](NAIP_GREENNESS.md). |

The final roof pilot uses 2,523,172 clean class-6 support points. Across eight
prepared files it changed 75,002 eligible class 4/5 points to 6, including 65,107
in the 3302 core. A read-only binary check scanned all **40,330,316** records:
headers and every non-classification point byte matched; flags, noise and other
classes were preserved; every audit index matched its prior class byte and had
at least three votes. Source sizes/timestamps still matched the pre-run manifest.
These are processing/integrity findings, not independently measured accuracy.

The original reference still contains **1,468 units and zero labels**. Batch 1
has 743 blank review units. The new census packet has twelve blank plots and
empty tree/cause tables. Neither absence of labels nor an unreviewed plot is
treated as a zero-error observation. No truth was synthesized from classes,
footprints, NDVI or model agreement.

## Review artifacts and next human step

Use the corrected `independent-plot-census-v2` packet under this task's artifact
directory. Its projected polygons imported into Pro as twelve positive-area
900 m² plots in EPSG:6341. The earlier scratch packet had reversed Esri exterior
ring orientation and is superseded; the ArcGIS regression now checks orientation.
The real ready-to-review feature class is
`canopy-toolbox/scratch/census-review-final-20260929/review.gdb/plots`.

Batch 1 remains at `reference-review-batch1` under the task artifact directory.
Apply the alignment and class-hidden point-cloud procedure before submitting
labels. Freeze blind labels before writing diagnostic causes. Future fine-tuning
must exclude 12TVL3302 plus its prepared halo; it is a prospective holdout after
exploratory use. 12TVL2203 is external transfer, never part of the Millcreek pilot
estimate. No citywide estimate is supported by these three tiles.

The user chose **keep the current environment; defer inference**. Density/HAG
inference, product-copy assembly and associated model accuracy measurements remain
unrun. Independent human census/labels are also pending. The implementation is
ready to support those steps without turning contextual evidence into truth.

## Final verification

The complete ArcGIS Pro Python suite passed **271 tests in 451.298 seconds**,
with one expected delivery-mock skip covered by the real ArcGIS fixtures. The
additional dated-WMS export test also passed in a three-test focused run (6.832 s).
See the final suite log at `canopy-toolbox/scratch/integration-suite-20260929.txt`.
It includes actual ArcGIS fixtures rather than treating skipped geoprocessing as
verification. Separate dated-WMS export verification uses a synthetic response
and actual Pro raster georeferencing, without credentials or network inference.
All new Python modules parse and the repository whitespace check passes.
