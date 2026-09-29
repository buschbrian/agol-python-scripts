# Classification review of the first full tiles — 2026-09-29

Three 1 km USGS tiles went through `prepare` and `run` today. In ArcGIS Pro, the tree candidates
still pick up roof corners, roof edges and other non-tree objects. This review measures where
those come from, tests the existing roof-edge correction at full-tile scale, and ranks the ways
to improve the classification. All results remain **unvalidated estimates**; nothing here is a
measured error rate, because there are no independent reference labels yet.

## What ran

| Tile | Location | prepare | run | Tree candidates | Crowns ≥ 3 m² |
|---|---|---:|---:|---:|---:|
| 12TVL2804 | Millcreek, residential | 2.0 min | 4.7 min | 17,389 | 11,661 |
| 12TVL3302 | Millcreek, east bench | 1.5 min | 5.4 min | 44,285 | 35,734 |
| 12TVL2203 | West of Millcreek (422–423 km E) | 1.1 min | 3.9 min | 11,610 | 7,913 |

Each tile was prepared with a 50 m buffer of neighbouring tiles and run on the exact 1 km tile.
The driver is [pilot_driver.py](pilot_driver.py); timings and peak memory are in
[pilot-timings.csv](pilot-timings.csv). Peak memory was at most 2.5 GB.

The runs are outside the repository at `H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29\`:

- `<tile>\prepared\` — classified LAS copies, `prepared.lasd`, `preparation.json`.
- `<tile>\run\assembly_*\chm.tif` and `inventory.gdb` (treetops, crowns, trees_review);
  `<tile>\run\run.json` is the manifest.
- `12TVL2804\roof-refined\` and `12TVL2804\run-refined\` — the roof-edge test below.
- `shape-diagnostic\` — reports and review LAS files described below.
- `logs\` — full stdout of every step.

## Where the stray "vegetation" comes from

The USGS delivery contains only unclassified (1), ground (2) and noise (7, 18) points, plus a few
class 9/17/20 points on 12TVL2203. **Every class 3, 4, 5 and 6 point is ours**, from the
`prepare` step:

1. `ClassifyLasBuilding` assigns class 6 to roof planes it can detect.
2. `ClassifyLasByHeight` then labels **everything else** by height above ground: class 3 up to
   0.5 m, class 4 up to 2 m, class 5 up to 80 m.

Step 2 is a catch-all. Any above-ground point the building step misses becomes "vegetation":
roof edges and corners, walls, chimneys, poles, wires, vehicles, fences and play structures. The
CHM uses class 3/4/5 first returns, so these objects become canopy and then tree candidates.

## Measurements

### Tree candidates on or against buildings

For every tree candidate, the class-6 points within 1 m horizontally were found in the same
prepared LAS. The candidate's height was then compared with the local roof height (90th-percentile
roof Z minus median ground Z within 5 m).
Script: [candidates_near_buildings.py](candidates_near_buildings.py).

| Tile | Candidates | Within 1 m of a building point | …of those, at roof height (≤ 0.5 m above) | …and crown < 3 m² | > 2 m above the roof |
|---|---:|---:|---:|---:|---:|
| 12TVL2804 | 17,389 | 4,428 (25%) | 3,293 | 2,619 | 706 |
| 12TVL3302 | 44,285 | 2,363 (5%) | 1,748 | 1,315 | 319 |
| 12TVL2203 | 11,610 | 1,093 (9%) | 887 | 721 | 43 |
| **Total** | **73,284** | **7,884** | **5,928** | **4,655** | **1,068** |

About 8% of all candidates are next to a roof and no higher than it. Most of them have tiny
crowns. They match the roof-corner and roof-edge candidates visible in Pro. The 1,068 candidates
well above the roof are more likely real trees that overhang buildings and should be kept. A few
candidates had no ground point within 5 m, so the height split totals are slightly below the
1 m counts. Reports: [candidates-near-buildings.json](candidates-near-buildings.json),
[candidates-vs-roof-height.json](candidates-vs-roof-height.json).

**Imagery check.** Nearmap has two Millcreek surveys, **2023-08-29 and 2023-08-31**, five to ten
weeks before the lidar flights. This closes the "capture date unknown" gap in the 17 September
reviews. Eight random 12TVL2804 candidates from each group were viewed as 30 m chips:

- **At roof height with a crown under 3 m²:** all eight sit on a roof edge, eave or ridge. Four
  are on flat commercial roofs and four on houses.
- **More than 2 m above the roof:** almost all are tree canopy overhanging a house. One low
  (3.4 m) candidate is next to a parked trailer.

Sixteen chips are a visual sanity check, not a measured rate. The chips stay in ignored scratch
and are not committed; Nearmap terms allow only temporary storage.

### The existing roof-edge refinement barely acts on residential roofs

`refine-roofs` was run on 12TVL2804, followed by a new `run`. Two findings:

- **Scale.** The prepared tile is 1,100 m square. At the default 0.5 m roof raster it is 4.84 M
  cells, which exceeds the command's 4 M cell guard. The test used `--cell-size 0.6`. It then
  finished in 1.2 minutes; its memory use was not recorded.
- **Roof model.** The refinement fits **one low-slope plane per roof region**. It accepted
  **70 of 805** regions, which is 16,789 m² of 266,404 m² of roof support. Only 41 regions were
  too steep; 694 failed the fit residual or inlier test, because a gabled or hipped house roof is
  two or more planes. The method was designed on the flat commercial roofs of the 17 September
  pilot, and it does what it was designed to do. It does not fit residential Millcreek.

| 12TVL2804 | Before | After refine-roofs |
|---|---:|---:|
| Points reclassified to 6 | — | 11,993 |
| Tree candidates | 17,389 | 17,285 |
| Candidates within 1 m of a building | 4,428 | 4,352 |
| Canopy ≥ 2 m | 292,709.75 m² | 292,244.25 m² |

No CHM height increased and the NoData mask did not change. The correction is safe, but it removed
only 76 of the 4,428 near-building candidates. Comparison script and report:
[compare_runs.py](compare_runs.py), [12TVL2804-roof-refine-comparison.json](12TVL2804-roof-refine-comparison.json).

### Point shape of the "vegetation" classes

PDAL, which ships with ArcGIS Pro, computed eigenvalue shape features for each non-ground point
from its 16 nearest neighbours. Class 3/4/5 points were grouped as roof-like (planar,
near-horizontal), wall-like (planar, near-vertical), linear, scattered or mixed. Script:
[shape_diagnostic.py](shape_diagnostic.py). The thresholds are screening choices, not validated
class boundaries.

| Class 5 (2–80 m) | 12TVL2804 | 12TVL3302 | 12TVL2203 |
|---|---:|---:|---:|
| Points | 8,818,572 | 16,056,576 | 4,148,377 |
| Single-return | 14.4% | 20.0% | 11.7% |
| Within 1 m (3D) of a building point | 3.2% | 1.3% | 1.0% |
| Roof-like | 6.6% | 6.9% | 5.3% |
| Wall-like | 0.6% | 0.6% | 0.5% |
| Linear | 11.5% | 11.1% | 9.3% |
| Linear and single-return | 2.2% | 2.6% | 1.1% |

Full reports: [12TVL2804](shape-12TVL2804-prepared.json),
[12TVL2804 after refine-roofs](shape-12TVL2804-roof-refined.json),
[12TVL3302](shape-12TVL3302-prepared.json), [12TVL2203](shape-12TVL2203-prepared.json).
The full-tile runs took 2–3.5 minutes each.

Most class-5 points look like vegetation: multiple returns and mixed shape. The problem points
are a small share of the point cloud but concentrated where they matter, at roof edges. Shape
alone does not separate them cleanly; a clipped hedge is planar and branches are linear. It is
still useful as one input among several.

On 12TVL2804, class 4 (0.5–2 m) is 10.4% within 1 m of a building and 17.5% roof-like. Class 3
(below 0.5 m) is mostly flat single returns: lawns, pavement and car roofs. It does not reach the
CHM, which starts at 2 m.

For inspection in Pro, each run of the diagnostic writes a review LAS in `shape-diagnostic\`. In
these files, class 3/4/5 points are recoded to **64 roof-like, 65 wall-like, 66 linear,
67 scattered, 68 mixed**; all other points keep their class. Symbolize by class code.

## Ways to improve the classification, ranked

Ranked by expected yield on this data and workstation, cheapest first.

1. **Replace the one-plane roof model with a local roof surface.** For each class 3/4/5 point with
   class-6 neighbours within about 1 m, estimate the roof surface from those neighbours alone.
   Reclassify the point to 6 when it lies within a narrow band of that surface. Gabled and hipped
   roofs then work, because each point only sees its own roof face. Overhanging canopy well above
   the roof stays vegetation. The candidate measurement above bounds the gain: up to about 5,900
   candidates across the three tiles. It would extend `roofs.py` with the same audit trail (new LAS
   copies, saved previous class bytes, manifest). The 4 M cell guard must also be relaxed for 1 km
   tiles.
2. **Reconcile lidar buildings against footprints** (Salt Lake County, current OSM from Overpass).
   This finds both directions of error:
   - buildings the lidar classifier missed, which are the source of roof-edge "trees";
   - lidar buildings with no footprint, which are either missing footprints or lidar false
     positives.

   It also produces the reference labels every later step needs. This is the next task.
3. **Shape gate for walls, poles and wires.** Wall-like and linear single-return points in
   class 4/5 that are not in a scattered neighbourhood can move to class 1. PDAL in Pro already
   provides the features, so no install is needed.
4. **Imagery greenness check.** Colour the points from 4-band imagery and veto "vegetation" that
   is not green. NAIP for the tiles is gigabytes, so take it from USGS
   or Esri Living Atlas rather than UGRC; UGRC services are fine for small requests only. Caveats: roof lean in the orthophoto moves roof colour onto nearby points, NAIP
   positional accuracy is specified at ±4 m, and the lidar is late autumn (7 October–5 November
   2023), when deciduous trees may already be off-colour. Nearmap true colour can support visual
   review but has no infrared band.
5. **Deep learning, after 1–3.** Esri publishes two pretrained point-cloud models for Pro:
   - [Building Point Classification](https://doc.arcgis.com/en/pretrained-models/latest/point-cloud/introduction-to-building-point-classification.htm)
     (RandLA-Net, X/Y/Z only, outputs building 6 or background);
   - [Tree Point Classification](https://doc.arcgis.com/en/pretrained-models/latest/point-cloud/introduction-to-tree-point-classification.htm)
     (PointCNN, needs number of returns, outputs tree 5 or background).

   Both run through
   [Classify Point Cloud Using Trained Model](https://pro.arcgis.com/en/pro-app/latest/tool-reference/3d-analyst/classify-point-cloud-using-trained-model.htm).
   The training density and region of each are not published, and each recommends **8 GB of
   dedicated GPU memory; this workstation has an RTX 3060 Laptop with 6 GB**. Pro's Python also
   has no PyTorch or `arcgis.learn` yet. The
   [Deep Learning Libraries Installer](https://github.com/esri/deep-learning-frameworks) for
   Pro 3.7 would add them.

   The best use is as a second opinion on one tile: points both models call background but we
   call vegetation are strong false-positive suspects. Fine-tuning in Pro (RandLA-Net, PointCNN or
   SQN) becomes practical once steps 1–3 produce corrected labels. Open-source research models
   such as IGN's [myria3d](https://github.com/IGNF/myria3d) (trained on French national lidar)
   need a separate CUDA environment. They are not a better first step.

   Install into a clone of `arcgispro-py3`, not the environment the toolbox runs in, and only
   after agreeing to it.

## Next: reconcile lidar buildings with footprints

Proposed products for each tile, written to a review geodatabase outside the delivery:

| Product | What it finds |
|---|---|
| **Footprint status.** For each footprint: the share of first returns more than 2 m above ground that are class 6 versus class 3/4/5, and the lidar roof height. | A footprint that is mostly class 3/4/5 at roof height is **a building the classifier missed entirely**, which is a different failure from edge leakage. A footprint with no returns above 2 m is demolished or not yet built at the lidar date. |
| **Lidar-only buildings.** Class-6 roof regions (the `roof_outlines` from `refine-roofs`, all 805 on 12TVL2804) that match no footprint in either source. | A missing footprint, or a lidar false positive such as a truck, container or flat canopy. |
| **Candidate flags.** Each tree candidate marked on-roof (inside a footprint at roof height), roof-edge (within 1 m, at roof height) or overhang (more than 2 m above the roof). | The roof-corner false positives above, kept separate from real overhanging trees. |
| **Label points.** A LAS copy marking points where lidar and both footprint sources agree (confident building, confident non-building), with disagreements left unlabelled. | The reference set that the rule fixes, and any later model fine-tuning, are measured and trained against. |

Footprint sources:

- **Salt Lake County:** the county service, pulled in bounded batches as in the 22 September pilot.
- **OpenStreetMap:** current OSM from Overpass. A test pull for 12TVL2804 returned 718 building
  ways, edited 2017–2026. About two-thirds (481) are imported Microsoft machine-learning
  footprints, so OSM is not an independent survey. A way's timestamp is its last edit, not its
  construction date. Height and levels are almost never tagged.

Disagreements between the sources, or between a footprint and the 2023 lidar, are what a person
adjudicates using the August 2023 Nearmap chips.

## What is not established

- No numbers here are error rates. "At roof height, next to a building" is a strong suspect
  signal, not a label; a tree whose top is level with the eaves would be counted too.
- Only 12TVL2804 was refined; the other two tiles have the baseline classification.
- Footprint currency relative to the 2023 lidar is not yet checked.
- Nearmap imagery is used only as a human visual reference for the lidar work. Nearmap's
  published product terms restrict machine-learning processing of the imagery and its use as
  training data without an added product. Any automated use, such as deriving labels from the
  pixels, needs the City's agreement text or Nearmap's written answer first.
