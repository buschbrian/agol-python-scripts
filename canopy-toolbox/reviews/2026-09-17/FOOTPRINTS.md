# Footprint validation — 2026-09-17

**Acquisition correction (2026-09-22):** The 2024 capture and 0.5 m nominal-spacing statements below are retained as historical notes. Delivery metadata establishes acquisition on 7 October–5 November 2023 and nominal point spacing of 0.32 m. See [delivery provenance](../../DELIVERY_PROVENANCE.md).


Follows [ROOF_EDGES.md](ROOF_EDGES.md). The derived roof-support outlines have now been
compared against an authoritative building layer. This is the first external reference check
in the pilot; every earlier roof result was self-consistent only.

The user-supplied Millcreek OSM footprint service returned zero features for this extent.
Salt Lake County's [Building Footprints](https://services.slco.org/) layer
(`SLCOGISLIVE.SLCOSU.SLCo_BuildingFootprints_Final`, service item
`4be6c94b65ee408999d2d4483a30febf`) covers it, and a query of the pilot extent returned
**4 commercial footprints**. All geometry was compared in EPSG:6341 (NAD83(2011) / UTM 12N,
metres) after projecting the county polygons from EPSG:3566, and clipped to the pilot AOI
because derived outlines are AOI-truncated.

## The pilot is in Taylorsville, not Millcreek

Every returned footprint carries `CITY: TAYLORSVILLE`, parcels `2102…`. The pilot box
(422350–422600 E) sits at the far southwest corner of the delivery, which spans
422000–435000 E and 4501000–4508000 N. Millcreek's western edge is near 425700 E, roughly
3 km east of the pilot.

The pilot remains a legitimate engineering test for roof leakage — it has the large flat
roofs that produce the failure mode. It is not representative of Millcreek: it is entirely
commercial, with no residential street trees, no park stands, and no foothill slopes. Nothing
measured here transfers to a Millcreek canopy estimate without a second pilot inside the city.

## Agreement

| Metric | Value |
|---|---:|
| County footprint area in AOI | 6,034.37 m² |
| Derived roof-support area in AOI | 6,148.50 m² |
| Intersection | 5,908.17 m² |
| IoU | 0.9416 |
| County area covered by derived support | 97.91% |
| Derived support falling on county-mapped building | 96.09% |

Four of the six derived outlines match a county footprint at 91.4–99.0% of their own area.
Each of the four county footprints is 96.1–100.0% covered.

Derived support is expected to run slightly wide: it is rasterized lidar roof surface at
0.5 m and includes eaves, parapets and rooftop structures, while the county polygons are
digitized wall outlines. The measurements confirm that shape rather than a systematic error —
of the 173.34 m² by which matched outlines exceed their footprints, only 8.36 m² survives a
1 m buffer of the county polygons and none survives 2 m. The excess behaves as a
sub-metre ring around correct buildings.

The 126.19 m² of county area not covered by derived support falls into 4 parts, the largest
51.21 m². These are edge slivers and roof sections without qualifying class-6 first/single
support, not whole missing buildings.

## Two derived outlines have no county footprint

| Derived ID | Centroid (UTM 12N) | Extent | Area | Height above ground | Plane RMSE |
|---|---|---|---:|---:|---:|
| 2 | 422577.31, 4503514.32 | 13.0 × 7.0 m | 38.50 m² | 2.63 m | 0.029 m |
| 5 | 422597.12, 4503392.99 | 5.5 × 8.5 m | 28.50 m² | 3.92 m | 0.029 m |

Both are low, small and extremely planar. A 3 cm plane residual is not achievable from a
tree crown, so these are almost certainly real hard surfaces — most likely accessory
structures the county layer omits, such as shelters, enclosures or canopies. Imagery places
both in parking and driveway areas rather than on any county-mapped building.

Together they are 67 m². If either is in fact vegetation, that is the upper bound on canopy
wrongly excluded by them — 0.6% of the pilot's 10,374.50 m² observed canopy. Both still
warrant a direct look before the roof logic is used in production.

## Roof 4 is a real building that the plane fit rejected

Roof 4 is marked `MODEL_REJECTED` (76.9% inliers, below the 80% threshold) and therefore
received no edge refinement. It overlaps county footprint 937483 at **96.82% of its own
area**, and that footprint is 97.29% covered.

The rejection is a plane-fit quality signal, not a building/non-building decision. A genuine,
county-mapped building was left unrefined because its roof is complex or multi-level. Residual
roof-edge vegetation leakage should be expected there, and the 80% inlier criterion will need
either a multi-plane fit or a documented fallback before citywide use. The criterion is still
doing its job — it correctly refused to reclassify points against a plane that does not
describe the roof.

## No missed buildings

The dark rectangle near 422470, 4503465 that reads as a structure at pilot scale is a curb
and pavement boundary in the parking lot; see [zoom-centre.png](../../scratch/pilot_20260917/footprint_check/zoom-centre.png).
Within the AOI the county layer and the derived support agree on which objects are buildings,
apart from the two small structures above.

## Limits

Four commercial footprints in one 250 m box establish nothing about citywide footprint
accuracy or about residential roofs, which are smaller, pitched, and closer to tree crowns.
The county layer's own positional accuracy is unstated here, and its edit dates are 2019,
five years before the 2024 lidar; a building altered between those dates would register as
disagreement on either side. IoU against a reference layer is not a canopy accuracy measure.
The Nearmap capture date is still unknown, so the imagery in the figures is an aid to
inspection, not a temporal match.

## Artifacts

- [footprint-comparison.json](footprint-comparison.json) — areas, IoU, per-outline and per-footprint overlap.
- [footprint-diffs.json](footprint-diffs.json) — unmatched outlines, buffer decomposition of the excess, missed-area parts.
- [footprint-validation.png](../../scratch/pilot_20260917/footprint_check/footprint-validation.png) — overlay with insets on roofs 2 and 5.
- Comparison geodatabase: `scratch/pilot_20260917/footprint_check/footprint_check.gdb`, including `derived_not_county` and `county_not_derived` difference layers.
- Scripts: `scratch/pilot_20260917/footprint_check/compare_footprints.py`, `inspect_diffs.py`, `figure_footprints.py`.

## Next

Run a second pilot inside Millcreek on residential and park cover. The roof logic is now
externally validated on commercial roofs only, and the tree-relevant failure modes — small
pitched roofs, crowns touching eaves, street trees over driveways — are absent from this AOI.
