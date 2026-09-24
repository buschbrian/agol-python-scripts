# 2023 Salt Lake Valley — acquisition record

**USGS project UT_2023SaltLakeCo_C24**, work unit UT_2023_SaltLakeCo_1_C24 (ID 300624), acquired by
Aero-Graphics, Inc. as the "Salt Lake Valley LiDAR" project. The local copy,
`G:\GIS\2024 Lidar for tower extract`, is a 52-tile extract made before UGRC published the same
dataset.

Generated facts about the local copy are in [acquisition-facts.md](acquisition-facts.md) and
[acquisition.json](acquisition.json); regenerate them rather than editing them (see
[the procedure](../README.md)). This page holds what the vendor declared, what that means for the
toolbox, and what is still open.

## Declared facts

| Fact | Declared value | Source |
|---|---|---|
| Collection dates | **2023-10-07 to 2023-11-05** | USGS project report; both metadata XMLs; swath index |
| Quality level | **QL1**, USGS Lidar Base Specification 2023 Rev. A | Project report |
| Pulse spacing and density | **NPS 0.32 m**, 10.39 pts/m² nominal; aggregate NPS 0.219 m, 20.78 pts/m²; **measured first-return average 18.2 pts/m²** | ClassifiedPointCloud metadata; mapping report §4.6 |
| Vertical accuracy, point cloud | **NVA RMSEz 5.87 cm**, 11.5 cm at 95%; **VVA 8.78 cm** at the 95th percentile | USGS project report |
| Vertical accuracy, DEM | NVA RMSEz 5.97 cm, 11.70 cm at 95%; VVA 10.12 cm | USGS project report |
| Horizontal CRS | **EPSG 6341**, NAD83(2011) / UTM zone 12N | Project report |
| Vertical datum and geoid | **EPSG 5703**, NAVD88; **Geoid18**; metres | Project report |
| Delivered classes | 1, 2, 7, 9, 17, 18, 20 — see below | Project report; point-cloud metadata |
| Flag policy | Withheld bit used; **overlap bit not used** | Point-cloud metadata |
| Sensor and platform | Optech Galaxy T2000 with SwathTrak, up to 8 returns per pulse, Cessna 310; PRF 1,100 kHz, 115 Hz scan, 28° full angle, 977 m swath, 78 flightlines | Metadata; mapping report Exhibit 2 |
| Ground conditions | No snow; rivers at or below normal. **Leaf condition not stated.** | Metadata |
| Control | 20 ground control points; 65 independent checkpoints, 35 NVA and 30 VVA, not used in calibration | Metadata |
| Project extent | About 494 mi² across Salt Lake, Utah and Davis counties; **1363 tiles** on a 1000 m schema | Metadata |
| Delivered products | Classified LAZ 1.4; hydro-flattened bare-earth DEM at 0.5 m; first-return DSM at 0.5 m; max surface height rasters at 1 m; swath separation images; breaklines | Metadata |

**Checked against the data.** The generated facts confirm the declared horizontal and vertical
references in every LAS header, 52 tiles all LAS 1.4 point format 6, and flight dates from
2023-10-07 to 2023-11-04 inside the declared window. The 20.4–34.6 returns per header m² is
consistent with 18.2 first returns per m² plus later returns and retained overage, not anomalous.
The pilot tile 12TVL2804 was flown 2023-11-02 and 2023-11-04.

## Delivered classification

USGS verifies classes only to the Base Specification minimum:

| Class | Meaning |
|---|---|
| 1 | Processed, but unclassified |
| 2 | Bare earth ground |
| 7 | Low point (noise) |
| 9 | Water |
| 17 | Bridge decks |
| 18 | High noise |
| 20 | Ignored ground |

## Consequences for the toolbox

- **No buildings (6) and no vegetation (3/4/5) are delivered**, so the toolbox has to derive both
  on the working copy, and `prepare`'s default of preserving delivered ground and noise is right.
  Classes 7 and 18 are both treated as noise and excluded from surfaces; 9, 17 and 20 are already
  in `NON_CANOPY_CLASSES`. No code change follows.
- **The overlap bit was never populated**, so the toolbox's overlap exclusion is inert on this
  delivery and all sidelap overage remains. The policy is correct; it simply has no effect here.
- **Season.** Late-autumn collection with no stated leaf condition. Deciduous canopy in that
  window is at least partly senescent, so canopy figures from this acquisition are season-limited
  and probably low. Do not compare them against a leaf-on product without saying so. This is an
  inference from the dates, not a statement in the delivery.
- **Terrain.** The delivery's own reviewed DEM agrees with the toolbox DTM to 0.030 m RMSE where
  ground is directly measured, and is the better surface: see
  [the DEM comparison](../../reviews/2026-09-22/DEM_COMPARISON.md).

## Documented voids

The mapping report records ground voids caused by steam or smoke plumes over an industrial area,
and a Jordan River location where temporary retaining walls produced apparent "floating water"
above valid ground. Both are delineated in `low_confidence_areas.shp` and
`low_confidence_polygons.shp` **in the full delivery, which is not in the local copy**. That file
is the right QA overlay for the `observed` and `ground_distance_m` masks.

## Coverage of Millcreek

The extract covers **98.75%** of the city. It was cut to the city: all 52 tiles touch it. The nine
index tiles still missing hold only edge slivers, 1.25% of the city in total, listed with their
areas in [the generated facts](acquisition-facts.md#coverage-of-the-boundary). They matter for
complete city totals and edge context, not for work inside the city. At the extract's average of
about 0.73 GB per uncompressed LAS tile, all nine are roughly 6.6 GB.

All 52 extract tiles appear in the official 1363-tile index. The extract's bounding rectangle has
39 empty grid cells; all exist in the published index, and six are interior holes — but four of
those six contain no Millcreek at all, so the hole in the extract is a hole in the city.

The boundary used is `Boundaries/MunicipalBoundary` in `Millcreek_Master_New.gdb`. The same GDB
holds `Millcreek_Municipal_Boundary_1`, within 4.1 ha of it, and `Boundaries/CityBoundary`,
12.74 mi² and about 51 ha different, probably older. Which layer is authoritative has not been
confirmed; under `CityBoundary` only 12TVL2601 would drop off the missing list.

## Discrepancies between sources — do not silently resolve

Cite the source rather than a merged number.

- **Sidelap:** the metadata XML says 55%; mapping report Exhibit 2 says 20%.
- **Altitude:** the metadata says "1981 ft above ground level" and the report says 6,500 ft AGL.
  1981 m equals 6,499 ft, so the metadata figure is metres carrying a feet label.
- **Vertical accuracy:** vendor metadata reports point-cloud NVA RMSEz 5.1 cm where the USGS
  project report's tested value is 5.87 cm. Report §4.4 gives a DEM VVA of 5.1 cm where USGS
  reports 10.12 cm. The USGS project report is the accepted result.
- **Horizontal accuracy:** the metadata's "0.36 cm RMSEx / RMSEy horizontal accuracy class" is not
  plausible for this collection. Treat it as a typo and do not quote it.

## Corrections to earlier statements

Before the delivery documents arrived, the repository carried values from recollection:

| Previously recorded | Correct value |
|---|---|
| Capture year 2024 | Collected 2023-10-07 to 2023-11-05; 2024 is the delivery year. Metadata published 2024-06-25; LAS headers stamped 2024-06-30. |
| Nominal point spacing 0.5 m | NPS 0.32 m. The 0.5 m figure is the DEM and pilot raster cell size. |
| Flight dates unknown | Per-tile, from the swath index |
| Vertical accuracy unknown | NVA RMSEz 5.87 cm, point cloud |

## Comparability with other epochs

Record these before differencing this acquisition against any other:

| Property | This acquisition |
|---|---|
| Horizontal CRS | EPSG 6341, NAD83(2011) / UTM 12N |
| Vertical datum and geoid | NAVD88, Geoid18 |
| Season | Mid-October to early November; leaf condition unstated |
| Quality level and density | QL1; 18.2 first returns per m² measured |
| Ground class | Vendor-reviewed class 2 |
| Building and vegetation classes | Not delivered |
| Overlap flagged | No |

## Open questions and next checks

1. Request `low_confidence_areas.shp` and overlay it on the observation masks.
2. Fetch the nine city-edge tiles when complete city totals are needed.
3. Confirm which city boundary layer is authoritative.
4. Find a leaf-on reference before any canopy figure from this acquisition is shared.

Done: the DEM comparison ([result](../../reviews/2026-09-22/DEM_COMPARISON.md)) and per-tile
flight dates on `las_tile_bounds`, now produced by `canopy index-delivery`.

## Source files

Supplied 2026-09-22 as `SLCo_Utah_2023_Metadata.zip`, `SLCo_Utah_2023_Reports.zip`, and
`SLCo_Utah_2023_shps.zip`. Everything cited above is kept in [reference/](reference/README.md):
the three FGDC metadata XMLs, the USGS project report, the Aero-Graphics mapping report, and the
tile index, data product area, and swath index shapefiles. The 40 MB GPS processing appendix and
the 37 MB breaklines GeoPackage are not tracked; see that README for what they are.
