# 3D building massing (October 22, 2026)

Flat blocks (LOD1.2) and roof forms (LOD2.0) for every county footprint with a lidar roof height, from the October 22
consensus roofs, by ArcGIS Pro's Extract LOD2 Buildings ([run_massing.py](run_massing.py)).
Output: `<SSD>\lidar\2023-salt-lake-valley\runs\massing-20261022\massing.gdb` (`lod12`, `lod20`; record `massing.json`,
copied here with the pilot's as `massing-pilot.json`). **Unvalidated planning estimates; heights are roof-minus-terrain,
not code-defined building heights.**

## Method
- Height source: the consensus roof elevation (2 of 3 sources, [roof-consensus](../../2026-10-21/roof-consensus/README.md))
  where there is one, and the unmasked terrain elsewhere, so the tool sees ground around each building.
- Footprints: the library's 22,042 county footprints with ROOF_Z50_M (21,562), each tagged FP_ID = its OBJECTID in
  `buildings.gdb/building_heights`, so every block joins back to its height statistics (all their fields are carried).
- `ExtractLOD2Buildings(height_source, footprints, out, level)` with the tool's defaults, once per level.
- Each block gets BASE_Z and TOP_Z (its lowest and highest Z), TERRAIN_MIN_Z (zonal minimum of the terrain under the
  footprint), TOP_MINUS_ROOF50 and BASE_MINUS_TMIN.
- `clean` then deletes the empty features the tool leaves (zero area, Z = 0).

Two things were settled before the citywide run:
- **Layer extrusion does not work from a script.** Extruding Z polygons through a layer's CIM extrusion and Layer 3D To
  Feature Class gave flat polygons in standalone Python, both on the in-memory layer and through an edited .lyrx. arcpy's
  Multipatch class cannot be built from point arrays, and its JSON form is a binary blob. Extract LOD2 Buildings
  accepts a raster height source, so it was used instead.
- **The tool takes a block's base from the ground around the footprint.** That was the risk with a roof-only surface
  (a fully roofed footprint could get a roof-level base and float). The pilot on 12TVL2804 (591 footprints) showed bases a
  median 0.10 m below the lowest terrain under each footprint and never more than 0.25 m above it, including footprints
  with 95% or more roof cover.

## Results (21,562 footprints; run 21:37 to 22:35, October 22)
| | LOD1.2 (blocks) | LOD2.0 (roof forms) |
|---|---:|---:|
| Time | 78 s | 54 min |
| Features from the tool | 21,569 | 21,569 |
| Empty features removed | 8 | 8 |
| Blocks kept | **21,561** | **21,561** |
| Top minus median roof (m): p5 / median / p95 | -0.53 / -0.05 / 0.00 | 0.00 / +0.92 / +2.39 |
| Base minus lowest terrain (m): p5 / median / p95 | -0.61 / -0.11 / +0.01 | same |

- One block per footprint: the 8 empty features were a spare beside the real block for 7 footprints (FP_ID 659, 1970, 5987,
  10421, 11835, 12681, 15132) and the only output for FP_ID 21952, a 0.5 m2 sliver that gets no block.
- LOD1.2 tops follow the table's median roof closely where the roof is well supported: of 14,229 footprints with at least 95%
  roof support only 13 are more than 1 m off; of the 2,380 with under 80% support, 695 are (median 0.4 m low). 718
  blocks in all are more than 1 m from the median roof (lowest 29.8 m below), almost all low-support footprints.
- LOD2.0 tops sit a median 0.9 m above the median roof, as ridges should; they are the tool's fitted roof planes and have
  not been checked against roof shapes.
- Bases: four blocks sit more than 2 m above the lowest terrain under their footprint (FP_ID 22003 by 7.2 m, 16604 by
  5.9 m, 4881 by 3.9 m, 6917 by 3.6 m), all fully roofed footprints where the tool read the ground near roof level
  (raised or built-over sites); they are kept and listed in `massing.json`. Some bases sit below the lowest terrain (to
  10.9 m), which only hides wall below ground.

## Next
Scene layer packages of both levels: [../hosting/scene-layers](../hosting/scene-layers/README.md). Roof shapes would need
a check against reviewed roofs before anyone reads pitch or ridge height from them.
