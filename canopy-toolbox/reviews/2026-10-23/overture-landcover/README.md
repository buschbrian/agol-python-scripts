# Overture land cover against the 2023 LiDAR canopy, October 23, 2026

Record of `Z:\GIS\overture\2026-10-21.0\millcreek\landcover-compare` (the GeoPackage and summary.json stay there).
`python -I ../landcover_compare.py` (ArcGIS Pro env `millcreek-py3`). Overture release 2026-10-21.0 land cover and land use
against `H:\lidar\2023-salt-lake-valley\runs\millcreek-products-20261022`: canopy is `chm_m.tif` at least 2 m on observed
cells (`observed.tif` = 1), the same rule as the city cover figure. Everything is counted on the LiDAR's 0.5 m grid (EPSG
6341) inside the city zone of `cover.gdb/zones`. LiDAR flown October-November 2023; Overture's land cover is the 2021
WorldCover map, so two years of planting, removal and construction separate them. These are unvalidated planning estimates,
like the LiDAR products they're built on.

**Method check.** Before measuring Overture, the script rasterizes the city zone itself and recounts the cover. It matches
`cover_rebuilt` CITY exactly: 133,813,488 zone cells (the same cells `observed.tif` marks as city), 133,058,292 observed,
34,044,344 canopy, **25.59%**. Overture's own Millcreek boundary is 3,334.0 ha against 3,345.3 ha for the city zone, with
30.4 ha between them. The city zone is used throughout, so every share below has the 25.59% denominator.

## What Overture land cover is in Millcreek
- **One source, ESA WorldCover 2021.** Every land cover feature's `sources` is `ESA WorldCover` (provider `esa`, resource
  `esa_worldcover`, version 2021, CC-BY-4.0). There is no OSM or local data in land cover. Overture land use, by contrast,
  is all OpenStreetMap.
- **Two copies of the same cover.** One generalized `forest` and one `urban` polygon (min_zoom 0-7) repeat the cover for
  small-scale maps. The detailed tier (min_zoom 8-15, 77 features) is the one used here; counting both would double the
  area.
- **Classes overlap and are stacked.** Inside the city the detailed polygons overlap one another by 408 ha. Overture's
  `cartography.sort_key` sets the draw order: urban (1) at the bottom, then forest (2), barren (3), shrub (4), grass (5)
  and crop (6) on top. Forest polygons cover 582.9 ha, but other classes are drawn over 79.3 ha of them where they meet
  shrub, 26.8 ha where they meet grass and 16.6 ha where they meet barren. Each cell takes the class drawn on top, as the
  map shows it. Whole-polygon figures are in summary.json too.
- **Effective resolution is about 1 ha, not 10 m.** WorldCover is 10 m pixels, but Overture's polygons are heavily
  generalized. Of the 39 polygons wholly inside the city, the smallest is 0.97 ha and the median 2.5 ha. There are only 2
  holes (36-67 m²), and edges run in straight segments of 24 to 67 m (5th to 75th percentile; median 47 m). A street of
  trees, a wooded yard or a 0.5 ha park can't appear. 75% of the city is a single `urban` class.

## Canopy under each class (cells drawn as each class)
| Overture class | Polygons | City ha | Share of city | **LiDAR canopy ≥ 2 m** | 0.5-2 m vegetation | Share of the city's canopy |
|---|---:|---:|---:|---:|---:|---:|
| forest | 16 | 483.3 | 14.45% | **45.9%** | 9.6% | 25.9% |
| shrub | 15 | 268.8 | 8.03% | 15.5% | 13.0% | 4.9% |
| grass | 21 | 53.0 | 1.58% | 23.9% | 18.1% | 1.5% |
| barren | 18 | 15.1 | 0.45% | 20.6% | 5.7% | 0.4% |
| crop | 1 | 1.0 | 0.03% | 1.0% | 0.8% | 0.0% |
| urban | 6 | 2,524.2 | 75.45% | 22.9% | 3.5% | **67.4%** |
| **City** | | 3,345.3 | | **25.59%** | | |

City ha and share of city include unobserved cells; the canopy and vegetation columns are shares of observed cells only. Every city cell is under some Overture class. Observed coverage is 99.2-99.8% in every class. The 0.5-2 m column is the
share of observed cells whose CHM falls in that band (bare ground, pavement and roofs are 0 in the CHM).

## Overture's tree area against the LiDAR's 25.59%
- **Overture calls 14.44% of the city forest; the LiDAR finds canopy on 25.59%.** The two mostly don't coincide:
  - Only **45.9%** of Overture forest has canopy at least 2 m.
  - Only **25.9%** of the LiDAR canopy lies in Overture forest. 67.4% is in `urban`.
- **A 10 m map could reach about 22%.** Counted in 10 m cells (WorldCover's pixel), 22.09% of the city has canopy on
  most of the cell. 51.68% has canopy on at least a tenth of the cell. WorldCover's tree cover class is any area
  "dominated by trees with a cover of 10% or more" ([WorldCover legend](https://docs.terrabyte.lrz.de/datasets/esaworldcover/)),
  so on cover alone the 10 m answer for Millcreek could sit anywhere between those two figures. Overture's 14.44% is
  below both, because generalizing to about 1 ha absorbs scattered urban trees into `urban`.
- **Overture land cover can't stand in for canopy cover here.** It overlaps the canopy where stands are large and misses
  most of the urban forest.

## Where they disagree most
Canopy and Overture forest were summed over 30 m blocks, at WorldCover's scale rather than single trees. Only blocks at
least half observed city count (37,102 blocks). Two kinds of block disagree:
- **Overture forest, little canopy:** at least half forest, under 20% canopy. 946 of 5,335 forest blocks (85.1 ha of
  480.2 ha).
- **Dense canopy that Overture doesn't call forest:** at least 60% canopy, under half forest. 1,440 of 3,060 dense blocks
  (129.6 ha of 275.4 ha).

Connected blocks of each kind of at least 1 ha are the polygons in the GeoPackage: 10 forest regions (29.8 ha, 8.9% canopy)
and 12 dense-canopy regions (28.6 ha, 79.1% canopy). Most disagreement is in smaller patches. Places are named from Overture
land use, places and road names only.

**Overture "forest" with little canopy.** These are two different cases:
- **Foothill scrub under 2 m.** The largest regions are on the east bench:
  - Region 13: 9.8 ha, 7.7% canopy, along the Bonneville Shoreline Trail (Mount Olympus section) above Ledgemont Drive.
  - Region 14: 6.7 ha, 6.5% canopy, inside OSM's Uinta-Wasatch-Cache National Forest at 40.7043, -111.7843.
  - Regions 16 and 18: about 2 ha each.

  Their vegetation is low: 25-30% of cells are 0.5-2 m and almost none reach 5 m. WorldCover calls this tree cover; at the
  2 m canopy threshold the LiDAR doesn't.
- **Neighbourhoods that are mostly open ground and roofs.** These regions are 83-89% under 0.5 m and have 9.5-12%
  canopy:
  - Region 20: 1.4 ha at Dominguez Park Apartments, 3990 South and 750 West.
  - Region 15: 2.3 ha by Lois Lane and Mount Olympus Way.
  - Regions 17 and 21: about 1-2 ha each, by 3600 South and Brookburn Road.

  Here the 2021 map may be wrong, or trees may have come down since. The LiDAR alone can't say which.

**Dense canopy that Overture calls something else.** Eleven of twelve regions are `urban`. In six of them, half or more
of the cells are at least 10 m tall. Examples:
- Region 1: 6.4 ha, 88.1% canopy, 59.8% of cells at least 10 m, along the Van Winkle Expressway near 1140 and 1200 East.
- Region 2: 4.6 ha, 77.6% canopy, between Highland Drive, East 3345 South and Murphys Lane.
- Region 3: 2.7 ha, 79.5% canopy, by 4370 South and Olive Drive.
- Region 5: 2.2 ha, 79.1% canopy, on Millstream Lane by Evergreen Park.
- Region 12: 1.1 ha, 74.9% canopy, about a fifth of it on Oakridge School's grounds.

The one non-urban region is Overture `shrub`. Region 6 is 1.7 ha with 78.1% canopy, on the Grandeur Peak section of the
Bonneville Shoreline Trail. Its canopy is 2-10 m (78% of cells), short trees or tall scrub that WorldCover read as shrub.

## Tree-related land use (OpenStreetMap)
Land use polygons overlap one another (parks sit inside residential areas), so each class is counted on its own.

| Land use (OSM) | City ha | LiDAR canopy ≥ 2 m | Overture forest |
|---|---:|---:|---:|
| residential | 1,886.4 | 30.3% | 15.8% |
| protected / forest (Uinta-Wasatch-Cache National Forest, the part inside the city) | 150.6 | 19.2% | 13.0% |
| park (18; Big Cottonwood Regional Park, Canyon Rim Park, Evergreen Park, ...) | 82.3 | 23.5% | 8.3% |
| school | 64.0 | 6.4% | 2.2% |
| cemetery (Wasatch Lawn Memorial Park, Elysian Burial Gardens) | 26.6 | 18.2% | 0.0% |
| managed grass | 16.4 | 12.6% | 3.4% |
| religious | 13.9 | 19.9% | 0.0% |
| nature reserve (Parley's Historic Nature Park, the part inside the city) | 1.2 | 47.1% | 82.4% |
| wilderness (Mount Olympus Wilderness, the part inside the city) | 0.6 | 18.7% | 33.1% |
| industrial | 122.6 | 7.1% | 0.0% |
| retail | 56.7 | 5.4% | 1.0% |

OSM's "forest" here is the National Forest boundary, an administrative line, not tree cover: 19.2% of it has canopy.
Residential land has more canopy (30.3%) than any large land use class, including parks (23.5%). Per-feature figures for
every named park, school, cemetery and reserve of at least 0.5 ha are in summary.json.

## Files
| File | Meaning |
|---|---|
| landcover_vs_lidar.gpkg / disagreement | The 22 disagreement regions of at least 1 ha. KIND (FOREST_LOW_CANOPY, DENSE_CANOPY_NOT_FOREST), CITY_HA, OBS_PCT, CANOPY_PCT, Overture class mix (OV_*_PCT, OV_MAIN_CLASS), CHM height bands (H_*_PCT, of observed cells), the most-overlapping named land use (LU_NAME, LU_CLASS, LU_SHARE), Overture places inside (PLACES), named roads within 15 m (ROADS), LON/LAT of a point inside |
| landcover_vs_lidar.gpkg / overture_land_cover | The 77 detailed-tier Overture land cover polygons clipped to the city, with sort_key and CANOPY_PCT_WHOLE (canopy share under the whole polygon, including parts drawn over by other classes) |
| summary.json | Every figure above: method check, sources and tiers, overlaps, geometry detail, per-class and whole-polygon counts with height bands, the forest comparison, land use by class and by named feature, disagreement block counts and the largest regions |
| landcover_compare.py | The script, a copy of the one that ran. It reads the Overture extract beside it, so run it from `Z:\GIS\overture\2026-10-21.0\millcreek` |
