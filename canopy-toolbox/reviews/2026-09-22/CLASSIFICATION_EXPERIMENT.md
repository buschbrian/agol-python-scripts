# Millcreek building-classification experiment — 2026-09-22

## Purpose and controls

The current prepare workflow preserves delivered ground, runs Esri Classify LAS Building, then assigns remaining class-0/1 points to LAS classes 3/4/5 by height. These last classes are **height-based canopy candidates**, not verified vegetation. This experiment varied only the Classify LAS Building method: CONSERVATIVE, STANDARD, or AGGRESSIVE. STANDARD remains the toolbox default.

Each method extracted a new, isolated working copy from source tile 12TVL2804 over 428075–428425 E and 4504075–4504425 N. Each then ran the same canopy run settings over the 300 × 300 m grid 428100–428400 E and 4504100–4504400 N, at 0.5 m cells and 2 m canopy threshold. Source LiDAR remained unchanged. The copied LAS files have 1,824,463 points in matching order and coordinates. Manifests and pointwise transitions are in ignored scratch files [building-method-comparison.json](../../scratch/planning_20260922/building-method-comparison.json) and [building-method-outputs.json](../../scratch/planning_20260922/building-method-outputs.json).

| Method | Building class 6 points | Observed canopy m² | Tree candidates | Accepted crowns | Candidate points on county footprints |
|---|---:|---:|---:|---:|---:|
| CONSERVATIVE | 345,586 | 20,995.00 | 1,541 | 1,006 | 102 |
| STANDARD | 346,212 | 20,962.75 | 1,530 | 1,004 | 99 |
| AGGRESSIVE | 371,797 | 20,094.25 | 1,484 | 974 | 106 |

Relative to STANDARD, CONSERVATIVE changed 4,590 point class codes, removed 245 canopy cells, and added 374. AGGRESSIVE changed 33,739 point class codes, removed 3,857 canopy cells, and added 383. Its net canopy reduction is 868.50 m² (4.1% of the STANDARD estimate). The observed-cell masks changed by 3 and 32 cells respectively. The [change map](../../scratch/planning_20260922/building-method-change-map.png) overlays these canopy changes on April 2025 orthophotography.

These differences are **sensitivity results, not accuracy results**. Candidate positions can shift after CHM changes, and a point inside a county footprint may be a real tree overhang. AGGRESSIVE did not lower the count of candidates directly on footprints. None of the three settings is validated as the preferred Millcreek classifier.

## Validation path for both requested outputs

1. **Freeze a reference sample before tuning.** Use stratified imagery review in the existing trees_footprint_review layer: clear trees away from roofs, direct roof contacts, points within 2 m of eaves, small crowns, and complex canopy. Record TREE, ROOF_OR_OTHER, or UNCERTAIN and whether each crown is merged or split. Include sites where imagery shows likely trees that have no candidate. Prefer imagery close to the 2023 LiDAR acquisition; the available county image is 12 April 2025 and therefore supports only preliminary interpretation.
2. **Validate canopy area separately.** Sample fixed plots across roofs, yards, streets, parks, and foothills. Manually delineate visible canopy in those plots or label a systematic set of cells, recording obscured/uncertain areas. Compare canopy area, omission, and commission for the same plots under each method. Do not use candidate counts as a proxy for canopy accuracy.
3. **Compare methods on identical AOIs.** Preserve the extracted copies, parameters, run manifests, footprint review, and per-point class transitions. Compare tree precision/recall and merge/split errors, canopy-area error, coverage/NoData, and roof-contact subsets. Choose a method only if it improves the reference metrics without unacceptable overhang loss.
4. **Refine roof geometry locally.** The current optional roof-plane model accepts relatively flat single-plane roofs. Test pitched or multi-plane residential roofs separately, using supported class-6 returns, local roof facets, and the county footprints as review geometry. Never blanket-delete canopy inside footprint polygons: branches can overhang roofs.
5. **Evaluate semantic point-cloud classification later.** Return structure, local roughness, and intensity may help distinguish vegetation from roofs, but need local labels and held-out evaluation. This workstation has an NVIDIA RTX A4000 with 16 GB VRAM; the ArcGIS Pro Python environment currently lacks torch. Esri's [point-cloud classifier](https://pro.arcgis.com/en/pro-app/latest/tool-reference/3d-analyst/classify-point-cloud-using-trained-model.htm) requires deep-learning frameworks and data attributes/density comparable to training data. Preserve verified ground/building classes when testing a model.

The immediate next work is the reference sample and paired evaluation. Changing the above-roof tolerance or running AGGRESSIVE citywide before that would only move the tradeoff, not establish better classification.
