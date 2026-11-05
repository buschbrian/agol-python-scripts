# Millcreek classification refinement pilot

The baseline, local roof refinement and unanimous FRACTAL policy completed a
comparison on three development sites within 12TVL2804. All processing and
integrity checks passed. Local roof refinement reduced candidate counts while
preserving observation coverage; FRACTAL made larger changes and introduced
some additional unknown coverage. Neither result establishes improved accuracy:
the independent reference still has 1,468 unlabelled units.

Local roof refinement is the first configuration to inspect manually because it
preserved coverage and changes fewer points. No configuration was selected as
an accuracy winner or applied to the production city products.

## Comparison results

Each core is 150 m square, with a 20 m processing halo. Development counts and
areas below exclude the fixed reference/census locations and their 25 m buffers.
The regions are separate diagnostic windows; their totals are not a seamless
tree inventory.

| Development area | Baseline candidates | Local roof candidates | FRACTAL-policy candidates |
|---|---:|---:|---:|
| Large roofs | 100 | 75 | 61 |
| Smaller roofs | 198 | 150 | 124 |
| More baseline canopy | 114 | 106 | 99 |
| **Development-window total** | **412** | **331** | **284** |

| Development-window measurement | Baseline | Local roofs | FRACTAL policy |
|---|---:|---:|---:|
| Observed canopy at least 2 m, m² | 7,533.75 | 7,327.50 | 7,308.50 |
| Observed area, m² | 28,008.00 | 28,008.00 | 27,948.50 |
| Additional unknown area, m² | 0 | 0 | 59.50 |

Local refinement changed 206.25 m² of baseline canopy to observed cells below 2 m.
The FRACTAL policy changed 290.50 m² to observed cells below 2 m and 1.00 m² to
unknown, while adding 66.25 m² of canopy elsewhere. Thus the lower FRACTAL
canopy total is mostly a classification/surface change rather than missing
coverage. Its correctness still requires independent answers.

Building comparisons contain 174 rows: the same 58 footprint/core intersections
under each configuration. These are context statistics on whole core
intersections, not independently measured building-height errors. The largest
matched change in HEIGHT_P95_M was about 1.47 m, for county SOURCE_ID 736188
under the FRACTAL policy. SOURCE_ID 729789 lost its only paired roof cell under
that policy; just 1.02 percent of that footprint intersects the core, so this
is an edge case rather than evidence that an entire building disappeared.

## Open the outputs

Output folder:
`D:\lidar\2023-salt-lake-valley\runs\classification-pilot-20261019`.

- `classification_comparison.aprx`: three site maps, each with baseline, local
  roofs and FRACTAL groups. Only the baseline group starts visible. Height
  breaks are shared across groups: 2, 6, 12, 20, 40 and 80 m. Each group includes
  its CHM, unverified development candidates and a hidden point-cloud layer for
  diagnostic cross-sections.
- `comparison.png`: nine panels on one continuous 0-40 m height scale. Orange
  dots are development candidates; grey pixels are NoData. The image retains
  core context outside the development domain, while candidate counts exclude
  the evaluation buffers.
- `comparison.csv`: candidate, canopy and observation changes by site/configuration.
- `building-comparison.csv`: paired roof/terrain statistics by site, configuration
  and stored county SOURCE_ID. Support and partial-footprint flags are retained.
- `products/<site>/<configuration>/review.gdb/treetops`: candidates with IN_CORE
  and DEVELOPMENT fields. DEVELOPMENT = 1 is the domain used for the headline
  development counts.

## Independent review

Open `independent-review/blind_reference_review.aprx` and enter answers in
`independent-review/ready/labels.csv`. Keep `packet.json` with that worksheet.
The ready packet is bound to the copied reference geodatabase on D:; its
743 sampled IDs are unchanged. A dry-run import passed, and all answer cells
remain blank. The earlier copied worksheet and packet are retained as provenance;
use the files in **ready** for review.

Work through each sample type in its saved REVIEW_ORDER. Keep diagnostic
comparison maps and class colours hidden while answering. Use elevation-coloured
lidar cross-sections and check imagery date/alignment. Use UNSURE when the
evidence is insufficient; do not infer labels from model agreement or footprints.
The 58 saved training labels remain training data and were not used as an
independent accuracy score.

The fixed reference includes Millcreek and external-transfer samples; report
those domains separately. 12TVL3302 and its halo remain excluded from tuning.
Independent labels are required before an accuracy ranking; the existing scoring
harness also requires predictions on matching reference grids. This pilot's
three small windows do not stand in for those complete grids or for a citywide
evaluation.

## Frozen inputs and checks

All variants started from an exact copy of the October 8 12TVL2804 working file,
containing 26,982,464 points. The local method used existing defaults without
tuning. The model variant reused the completed October 8 NAIP 2024 FRACTAL
consensus and the existing `refine_city.rules` policy. It required three
unanimous votes and additionally protected every withheld, synthetic and overlap
point. Ground/noise/vendor classes were retained; ground disagreements stayed
proposals. The 0.5 m/2 m/80 m vegetation height bands were retained.

Local refinement changed 97,724 classification bytes; the FRACTAL policy changed
477,895. Every other header, VLR, record and trailing byte matched the baseline.
Changed-point indices and previous classes matched the saved audits exactly.
All variants used identical cached terrain, grids, smoothing and detection bands.
The common terrain was verified cell by cell in every site. No crowns were
generated and no existing AOI limits were changed.

Original city working LAS, raw consensus, reference geometry and reference
labels were unchanged. The blind reference copy matches the source geometry
and labels. No inference or training ran for this pilot; the separately running
city FRACTAL job was left alone. Runtime was ArcGIS Pro 3.7.3.

`experiment.json`, `verification.json`, `projects.json` and the ready-packet
preview preserve the full evidence on the SSD. Small verification copies are
saved beside this report. The runnable scripts are `run_pilot.py`,
`verify_and_plot.py`, `build_projects.py` and `bind_review_packet.py`.
