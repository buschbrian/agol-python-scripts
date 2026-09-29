# Building reconciliation

`fetch-footprints` and `reconcile-buildings` are integrated in `python -m canopy`.
The first command fetches bounded reference sources, recording CRS transformation,
coverage and source identifiers. The second reads prepared LAS and writes a new
review GDB, estimated roof/ground heights, candidate flags, layers and a separate
rule-labelled LAS copy. Originals and tree candidate inputs remain immutable.

Example from canopy-toolbox with ArcGIS Pro Python:

```powershell
python -m canopy reconcile-buildings H:/lidar/2023-salt-lake-valley/runs/pilot-2026-09-29/12TVL2804/prepared/prepared.lasd scratch/buildings-check --extent 428000 4504000 429000 4505000 --footprints H:/lidar/2023-salt-lake-valley/runs/pilot-2026-09-29/buildings/reference.gdb --tile 12TVL2804
```

Existing outputs are refused. The driver now imports without launching work,
checks historical completion manifests before skipping existing output, and
writes new timings under its output root. Historical runs are evidence of their
own recorded implementation; they are not automatically rerun with new code.

The statuses compare independent footprint sources with class-6 support. The
same-method LiDAR footprint source never establishes an independent match.
Footprints and rule codes 64–70 are review/training aids, never scoring truth.
Training must exclude the frozen evaluation holdouts and evaluation still needs
independent reference labels. No pseudo-label is imported into reference.gdb.

## County height evidence

The saved county field is sparse before reconciliation. A read-only join on
SOURCE_ID between fetched county features and output footprint_status found no
height-value mismatches:

| Tile | County footprints | Positive BLDGHEIGHT | Null BLDGHEIGHT |
|---|---:|---:|---:|
| 12TVL2804 | 726 | 78 | 648 |
| 12TVL3302 | 276 | 0 | 276 |
| 12TVL2203 | 106 | 0 | 106 |

Thus the missing heights are upstream attribute gaps, not dropped values in the
reconciliation. The field is nullable in the [county layer definition](https://services1.arcgis.com/DJP723NX3ukQ2LtF/ArcGIS/rest/services/SLCo_BuildingFootprints/FeatureServer/0).
The available metadata does not establish why only those buildings were enriched;
that provenance question remains open with the publisher. Spatial service units
do not establish the height field's units.

For 74 pairs with usable class-6 maximum heights on 12TVL2804, the **median**
LiDAR/BLDGHEIGHT ratio is 0.9631, median difference −0.3091 m, and median absolute
difference 0.9600 m. This is consistent with peak/ridge heights in metres for
that subset; it is an empirical interpretation, not a certified field definition
or evidence that the remaining buildings have comparable height quality.

The original reconciliation fixtures passed all 28 tests after integration.
`county-height-coverage.json` in the task artifact directory records the read-only
source/output check. External tile 12TVL2203 is a transfer-test domain and must
not be included in a Millcreek estimate.

The merged CLI also completed a new 250 m representative pilot in 51.2 seconds,
at `scratch/integration-buildings-20260929`. The existing historical reports were
retained. This new pilot writes its own rule-labelled copy and review outputs;
its classifications are not independent accuracy evidence.
