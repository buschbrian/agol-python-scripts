# Millcreek tree-model pilot — 2026-09-22

## Method

The publicly downloaded Esri Tree Point Classification DLPK was run on a NEW copy of the STANDARD prepared tile over 428075–428425 E, 4504075–4504425 N. The GPU run used batch size 1, predicted classes 0/background and 5/tree, and preserved existing classes 2/ground, 6/building, 7/low noise, and 18/high noise. The 1,824,463-point input changed from classes 1/2/3/4/5/6/7/18 to 0/2/5/6/7/18. The prior prepared LAS copy's SHA-256 remained unchanged. See the ignored [model trial manifest](../../scratch/models/millcreek_tree_trial/model_trial.json).

ArcGIS LAS dataset statistics must be refreshed after DLPK inference. A stale LAS dataset made the CHM builder report no ground despite 285,194 class-2 points in the LAS file. Recreating the derived LAS dataset with computed statistics resolved this. The CHM builder now rejects missing or stale LAS statistics with a specific error before rasterization. The custom model LAS dataset also needs an explicit source-files list for runner provenance.

The model's class-0 output is a predicted **background** class. The ordinary toolbox interprets class 0 as unclassified/unknown. A first run without model-background semantics made 88,066 previously observed 0.5 m cells newly missing. The toolbox now has an explicit run option, --classified-background-zero, which adds class-0 first/single returns to known non-canopy observation on that model-classified copy. Default runs still leave class 0 unknown. The flag and effective non-canopy classes are written into the run/CHM manifests. A real ArcGIS regression test checks both policies.

## Paired 300 m analysis

All runs used the same 428100–428400 E, 4504100–4504400 N grid, 0.5 m cells, 2 m canopy threshold, detection bands, and 3 m² minimum crown area.

| Result | STANDARD height-classified baseline | Tree DLPK with explicit background |
|---|---:|---:|
| Observed cells | 358,089 | 358,520 |
| Missing cells | 1,911 | 1,480 |
| Observed canopy area | 20,962.75 m² | 20,308.25 m² |
| Tree candidates | 1,530 | 1,345 |
| Accepted crowns | 1,004 | 943 |
| Candidate points on county footprints | 99 | 68 |
| Candidate points within 2 m of footprints | 334 | 244 |

Relative to baseline, the model trial removes 2,618 canopy cells (654.50 m²) and adds no canopy cells; it adds 431 observed cells and makes none newly missing. The candidate total falls by 185 and accepted crowns by 61. Of the deterministic peak IDs, 1,150 remain at the same cell, 380 are baseline-only, and 195 are model-only. See the [preliminary imagery change map](../../scratch/models/tree_model_change_map.png) and [paired comparison](../../scratch/models/tree_model_comparison_valid.json). The incorrect class-0-as-unknown run is retained there as a diagnostic, not a valid canopy comparison.

These are **sensitivity measurements, not accuracy estimates**. Lower roof-contact counts may represent removed artifacts, lost real overhangs, or shifted peaks. The model was not locally trained, and existing class-6 building points were preserved, including any prior tree/roof errors. The available orthophotography is dated April 2025; the LiDAR here was collected November 2023. Imagery can guide preliminary review but cannot certify 2023 tree labels.

## Next validation

Review the changed canopy cells and lost/shifted candidates in representative roofs, eaves, street trees, and parks. Build a fixed sample of independent tree and canopy labels, including omissions. Score canopy commission/omission and tree precision/recall separately before promoting this model to the main workflow. The building-then-tree DLPK path and a live OSM footprint check have since been run on the same pilot; see [sequential model validation](DL_VALIDATION.md).
