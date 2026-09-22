# Delivery provenance — G:\GIS\2024 Lidar for tower extract

The 52-tile extract is part of **USGS project UT_2023SaltLakeCo_C24**, work unit
UT_2023_SaltLakeCo_1_C24 (ID 300624), acquired by Aero-Graphics, Inc. as the
"Salt Lake Valley LiDAR" project. The local copy predates the UGRC publication of the same
dataset. Facts below come from the delivery's own metadata and reports; they replace values
previously recorded from recollection.

## Corrections to earlier statements

| Previously recorded | Correct value | Source |
|---|---|---|
| "Capture year **2024**" | Collected **2023-10-07 to 2023-11-05** | USGS project report; both metadata XMLs; swath index |
| "Nominal point spacing **0.5 m**" | **NPS 0.32 m**, nominal density 10.39 pts/m²; aggregate NPS 0.219 m / 20.78 pts/m²; **measured first-return average 18.2 pts/m²** | ClassifiedPointCloud metadata; mapping report §4.6 |
| "Exact flight date … unknown" | Per-tile dates, below | Swath index, 79 dated swaths |
| "Validated vertical accuracy remains unknown" | Point cloud **NVA RMSEz 5.87 cm**, 11.5 cm at 95%; **VVA 8.78 cm** at the 95th percentile | USGS project report |
| "2024 Lidar" folder name | 2024 is the **delivery** year. Metadata published 2024-06-25; LAS header file-creation stamp is day 182 of 2024, or 2024-06-30. | Metadata; LAS headers |

The 20.4–34.6 million returns per km² measured in the delivery index is therefore expected
rather than anomalous: 18.2 first returns per m² plus later returns, with swath overage retained.

## Acquisition and specification

- Quality Level **1**, USGS Lidar Base Specification 2023 Rev. A. Project area about 494 mi²
  across Salt Lake, Utah, and Davis counties; **1363 tiles** on a 1000 m by 1000 m schema.
- Sensor Optech Galaxy T2000 with SwathTrak, up to 8 returns per pulse, on a Cessna 310.
  PRF 1,100 kHz, scan frequency 115 Hz, full scan angle 28°, swath width 977 m, 78 flightlines.
- Horizontal **EPSG 6341**, NAD83(2011) / UTM 12N; vertical **EPSG 5703**, NAVD88; **Geoid18**;
  metres. This matches the WKT in every LAS header in the extract.
- Ground conditions: no snow, rivers at or below normal. 20 ground control points and 65
  independent checkpoints, 35 NVA and 30 VVA, which were not used in calibration.
- Delivered products include a hydro-flattened bare-earth **DEM at 0.5 m**, a first-return
  **DSM at 0.5 m**, maximum surface height rasters at 1 m, swath separation images, and
  breaklines. Only the point cloud is in the local extract.

## Delivered classification

USGS-verified classes are limited to the Base Specification minimum:

| Class | Meaning |
|---|---|
| 1 | Processed, but unclassified |
| 2 | Bare earth ground |
| 7 | Low point (noise) |
| 9 | Water |
| 17 | Bridge decks |
| 18 | High noise |
| 20 | Ignored ground |

**No buildings (6) and no vegetation (3/4/5) are delivered.** This confirms that the toolbox
has to derive them on the working copy, and that the `prepare` policy of preserving delivered
ground and noise is the right default. Classes 7 and 18 are both treated as noise and excluded
from surfaces; 9, 17, and 20 are already in `NON_CANOPY_CLASSES`. No code change follows from
this table.

**Withheld points are flagged; swath overage points are not.** The metadata states that the LAS
overlap bit was not used. The toolbox excludes withheld, overlap, and synthetic points, so the
overlap half of that policy is inert on this delivery and all sidelap overage remains in the
data. The README's instruction to check that policy against delivery provenance is now
discharged: the policy is correct, and it has no effect here.

## Seasonal timing — open question for canopy work

Acquisition ran **October 7 to November 5, 2023**. Neither metadata XML nor the mapping report
states a leaf-on or leaf-off condition anywhere; the only stated ground condition concerns snow
and river level. Given Salt Lake Valley phenology, deciduous canopy in that window is at least
partly senescent. Until a leaf-on reference is available, treat the pilot's 23.4%-of-observed
canopy figure as a **season-limited estimate, probably low for deciduous cover**, and do not
compare it against a leaf-on canopy product without saying so. This is an inference from the
dates, not a statement in the delivery.

## Documented voids

The mapping report records ground voids caused by steam or smoke plumes over an industrial area,
and a Jordan River location where temporary retaining walls produced apparent "floating water"
above valid ground. Both are delineated in `low_confidence_areas.shp` and
`low_confidence_polygons.shp` **in the full delivery, which is not in the local copy**. That
shapefile is the right QA overlay for the `observed` and `ground_distance_m` masks and should be
requested.

## Per-tile acquisition dates for the extract

Derived by intersecting the 52 header footprints with the 79 dated swath polygons in
`Salt_Lake_Valley_Lidar_Swath_Index`. Swaths overlap, so several tiles carry more than one date.
The pilot tile **12TVL2804 was flown 2023-11-02 and 2023-11-04**. Reproduce the table with
`canopy index-delivery <delivery> <output> --swaths reference/index/Salt_Lake_Valley_Lidar_Swath_Index.shp`,
which writes the same dates onto `las_tile_bounds`.

| Dates | Count | Tiles |
|---|---:|---|
| 2023-11-02 | 16 | 2203, 2303, 2403, 2503, 2602, 2603, 2606, 2701, 2702, 2703, 2706, 2802, 2803, 2806, 2906, 2907 |
| 2023-11-02, 11-04 | 12 | 2204, 2304, 2404, 2504, 2604, 2605, 2704, 2705, 2804, 2805, 2904, 2905 |
| 2023-10-07 | 12 | 3106, 3107, 3201, 3202, 3203, 3206, 3302, 3303, 3306, 3402, 3403, 3406 |
| 2023-10-07, 11-04 | 8 | 3104, 3105, 3204, 3205, 3304, 3305, 3404, 3405 |
| 2023-10-07, 11-02 | 2 | 3006, 3007 |
| 2023-10-07, 11-02, 11-04 | 2 | 3004, 3005 |

All tile names carry the `12TVL` prefix. No tile in the extract went unmatched.

## Coverage against the official tile index

All **52** extract tiles appear in the official 1363-tile index, so the extract is a clean subset
with no unofficial or renamed tiles. The gaps inside the extract's bounding rectangle are
selection, not absence: all **39** missing grid cells exist in the published index and can be
obtained from UGRC.

Six of them are interior holes surrounded by delivered tiles —
`12TVL2902`, `12TVL3002`, `12TVL3102`, `12TVL2903`, `12TVL3003`, `12TVL3103` — but four of those
contain no Millcreek at all; the hole in the extract is a hole in the city. See the city coverage
below before requesting anything.

The remaining 33 are on the west and outer edges: 2201, 2301, 2401, 2501, 2601, 2801, 2901, 3001,
3101, 3301, 3401 in row 4501; 2202, 2302, 2402, 2502 in 4502; 2205, 2305, 2405, 2505 in 4505;
2206, 2306, 2406, 2506 in 4506; 2207, 2307, 2407, 2507, 2607, 2707, 2807, 3207, 3307, 3407 in 4507.

## Coverage of Millcreek

Intersecting the official tile index with `Boundaries/MunicipalBoundary` in
`G:\GIS\Data\City\Millcreek\GDB\Millcreek_Master_New.gdb` (33.45 km², 12.92 mi²): the city touches
**61 tiles**. All 52 extract tiles are among them, so the extract was cut to the city, and it
covers **98.75% of the city's area**. The nine missing tiles hold only edge slivers:

| Tile | City area inside | Share of city |
|---|---:|---:|
| 12TVL3301 | 13.82 ha | 0.41% |
| 12TVL3207 | 7.71 ha | 0.23% |
| 12TVL3101 | 6.55 ha | 0.20% |
| 12TVL3102 | 4.71 ha | 0.14% |
| 12TVL3307 | 3.14 ha | 0.09% |
| 12TVL2607 | 3.02 ha | 0.09% |
| 12TVL2902 | 1.48 ha | 0.04% |
| 12TVL2502 | 1.30 ha | 0.04% |
| 12TVL2601 | 0.15 ha | <0.01% |

Together they are 41.9 ha, 1.25% of the city. They matter for complete city totals and for edge
context in canopy and terrain processing, but not for working inside the city. At the extract's
average of about 0.73 GB per uncompressed LAS tile, all nine are roughly 6.6 GB.

The same GDB holds `Millcreek_Municipal_Boundary_1`, which agrees with `MunicipalBoundary` within
4.1 ha, and `Boundaries/CityBoundary`, which is 12.74 mi² and differs from both by about 51 ha,
probably an older boundary. Which layer is authoritative has not been confirmed; the tile list
above does not change under `CityBoundary` except that 12TVL2601 drops out.

## Internal discrepancies — do not silently resolve

The supplied documents disagree in four places. Cite the source rather than a merged number.

- **Sidelap:** the metadata XML says 55%; mapping report Exhibit 2 says 20%.
- **Altitude:** the metadata says "1981 ft above ground level" and the report says 6,500 ft AGL.
  1981 m equals 6,499 ft, so the metadata figure is metres carrying a feet label.
- **Vertical accuracy:** vendor metadata reports point-cloud NVA RMSEz 5.1 cm where the USGS
  project report's tested value is 5.87 cm. Report §4.4 gives a DEM VVA of 5.1 cm where USGS
  reports 10.12 cm. The USGS project report is the accepted result.
- **Horizontal accuracy:** the metadata's "0.36 cm RMSEx / RMSEy horizontal accuracy class" is not
  a plausible value for this collection. Treat it as a typo and do not quote it.

## Useful next checks

1. Compare the delivery's own 0.5 m hydro-flattened DEM against the toolbox DTM over the pilot
   AOI. It is an independent surface at the same cell size, and it would be the first real check
   on the interpolated terrain, which nothing has validated yet.
2. Request `low_confidence_areas.shp` and overlay it on the observation masks.
3. Fetch the nine city-edge tiles above when complete city totals are needed; nothing inside
   the city is waiting on them.
4. Record the per-tile flight date on `las_tile_bounds` so canopy results carry their season.

## Source files

Supplied 2026-09-22 as `SLCo_Utah_2023_Metadata.zip`, `SLCo_Utah_2023_Reports.zip`, and
`SLCo_Utah_2023_shps.zip`. Everything cited above is kept in [reference/](reference/README.md):
the three FGDC metadata XMLs, the USGS project report, the Aero-Graphics mapping report, and the
tile index, data product area, and swath index shapefiles. The 40 MB GPS processing appendix and
the 37 MB breaklines GeoPackage are not tracked; see that README for what they are.
