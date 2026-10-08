# Millcreek tree count - October 8, 2026

The completed baseline run detected **607,972 candidate treetops at least 2 metres tall** within the municipal boundary, using native ArcGIS building/height classification. These are preliminary lidar detections; biological tree identity and detection accuracy remain unverified.

| Category | Detected treetops | Share of total |
|---|---:|---:|
| Public / government parcels | 75,176 | 12.37% |
| Private parcels | 454,849 | 74.81% |
| No matching parcel | 59,212 | 9.74% |
| Uncertain owner of record | 18,735 | 3.08% |
| Conflicting parcel categories | 0 | 0.00% |
| **Total inside city** | **607,972** | **100%** |

Public plus private is 530,025. The remaining 77,947 detections stay separate as unmatched or uncertain ownership. No detection matched multiple parcel polygons.

Direct observations cover **99.25%** of city grid cells. There are 1,003,064 unknown cells (250,766.00 m²); counts are not extrapolated into them. The rasterized municipal area is 33,453,372.00 m².

| Public owner group | Detected treetops |
|---|---:|
| Salt Lake County | 61,753 |
| Salt Lake City | 4,886 |
| Public schools | 4,880 |
| Millcreek | 1,707 |
| State of Utah | 722 |
| Public districts | 712 |
| Public housing authorities | 322 |
| Federal government | 194 |

Outputs: [CSV](D:/lidar/2023-salt-lake-valley/runs/city-count-20261008/city-treetops.csv) and `tree-count.gdb\city_treetops` in the run directory. Source and method provenance are saved in [city-count-summary.json](city-count-summary.json).

## Agreed definition and inputs

Count unique detected treetop cell centres inside or on the city's
`MunicipalBoundary`, at least 2 metres above ground. Assign parcel ownership at
the treetop location. Keep unmatched locations, missing owners and conflicting
parcel ownership separate. This is a preliminary estimate of candidate trees,
not a field-verified stem census.

The SSD contains 61 original LAS tiles from the 2023 Salt Lake Valley acquisition.
Their header rectangles cover the entire municipal polygon: 33,453,397.07 m².
Header coverage does not establish direct observation coverage; the finished
result reports observed and missing raster cells separately, with no extrapolation.
The acquisition dates are October–November 2023. The folder/delivery name does
not establish 2024 collection. See the [acquisition record](../../acquisitions/2023-salt-lake-valley/RECORD.md).

Sources are `G:\GIS\Data\City\Millcreek\GDB\Millcreek_Master_New.gdb`,
`Boundaries\MunicipalBoundary` and `MillcreekParcels`. Local projected snapshots
use NAD83(2011) / UTM zone 12N, EPSG 6341. The source LAS elevations use NAVD88,
Geoid18, metres. `inputs.json` records the source paths and datum transformations.

The parcel snapshot was read October 8, 2026. There are 21,743 intersecting parcel
polygons; 21,565 have tax-year field 2025 and 178 have no tax year. A tax-year
attribute is not an ownership effective date. Two invalid copied parcel geometries
were repaired with OGC validation; original WKB and hashes were retained. Area
changes were less than 0.000000001 m². Source city layers were unchanged.

## Ownership rules

Explicit aliases identify the city, county, state, federal government, public
schools, housing authorities and public districts. Tax exemption alone does not
establish government ownership. Private utilities, churches, nonprofits and
named private owners stay in the private category.
Federally chartered credit unions and the Federal Home Loan Mortgage Corporation
are not classified as government agencies merely because their names contain
"federal". FHFA describes [Freddie Mac as a private company](https://www.fhfa.gov/about-fannie-mae-freddie-mac).

The parcel classification has 435 public/government parcels, 21,235 private
parcels and 73 with uncertain owners. **These are parcel counts, not tree counts.**
Public district identification includes [Mt. Olympus Improvement District](https://www.utah.gov/pmn/sitemap/notice/813603.html).
Exact aliases and ambiguity rules are in [parcel_ownership.py](../../canopy/parcel_ownership.py).

A point on a parcel edge uses `INTERSECTS`. Multiple matching parcels with the
same category count once. Different categories produce `OWNERSHIP_CONFLICT`.
Missing/truncated/mixed owners produce `UNKNOWN_OWNER`. `NO_PARCEL` means no
matching parcel polygon; it does not prove that the location is a public road.
The saved owner-classification review lists nonprivate owners and their basis.

## Processing and verification

Original LAS files remain immutable. Extraction and native building classification
run on isolated working copies. Building settings are STANDARD, minimum height
2 m, minimum area 10 m², below-roof class 6 and above-roof tolerance 3 m.
Ground and noise are retained from the delivery.

Native point-ground height classification failed on 12TVL2503 with error 050157
and later terminated on 12TVL2303. Raster-ground SURFACE mode succeeded on the
failing tile. Recovery builds class-2 ground using
`TRIANGULATION NATURAL_NEIGHBOR WINDOW_SIZE MINIMUM 1`, 0.5 m cells and 50 m
buffers, then classifies working files using upper thresholds 0.5, 2 and 80 m
for classes 3, 4 and 5. Only provisional vegetation labels absent in the delivered
classes are reset. Prior working class bytes are backed up. SHA-256 verifies
every byte outside the classification byte before/after recovery, including
record order, elevations, flags, header, VLRs and tail. Original source size/mtime
fingerprints are also checked.

ArcGIS terminated in a reused raster worker after several jobs. Each raster tile
and native height classification therefore runs in a fresh process. Completed
ground surfaces are retained; incomplete attempts are preserved separately.
Tile 12TVL3204 also failed with native exit 3221226505 and error 999999. Rebuilding
statistics and using a LAS dataset containing its nine intersecting neighbors
resolved the failure. Canopy raster workers likewise index all working files whose
header rectangles intersect their requested halos. Every possible input point
inside a raster extent is retained. Height workers operate on disjoint files,
with separate backups and per-file integrity checks.

The CHM uses first/single vegetation returns, no vegetation interpolation,
excluded withheld/overlap/synthetic flags, known noncanopy observations and the
existing 0.35 m building-occlusion rule. Ground cores form a cached mosaic.
A real 200 m pilot showed all seven CHM products exactly equal when the same
ground raster was cached. See [ground-reuse-verification.json](ground-reuse-verification.json).

Raster cores are 950 m, with 20 m halos. One disk-backed canonical CHM precedes
detection. Height bands and radii are 2–6 m: 1 m; 6–12 m: 1.5 m; 12–20 m: 2 m;
20+ m: 2.5 m; smoothing radius is one cell. Global eight-connected plateau
reconciliation selects one actual cell at maximum raw height, nearest plateau
centroid, then row-major tie break. It does not append independent tile inventories.
No crowns are produced and existing crown/AOI limits remain unchanged.

The count detector reproduced all 17,389 peaks on the original 4-million-cell
pilot and matched the original method on a 5,242,880-cell synthetic fixture.
Ninety ownership cases, including interiors, exact vertices and gaps, matched
ArcGIS spatial-filter results. The plain regression suite passed 454 tests,
skipping 88 ArcGIS-only fixtures; cached-ground products were checked in actual
ArcGIS execution. These are method checks, not evidence of tree detection accuracy.

Run directory: `D:\lidar\2023-salt-lake-valley\runs\city-count-20261008`.
[run_city_count.py](run_city_count.py), [recover_city_ground.py](recover_city_ground.py)
and [verify_city_count.py](verify_city_count.py) preserve the runnable workflow.

Final verification passed for all 607,972 unique UUIDs: every detection is inside
or on the municipal boundary and at least 2 m tall; CSV and GIS attributes match;
ownership and observation totals conserve; all 63 raster cores are present;
original and prepared LAS size/mtime fingerprints are unchanged; all 61 protected
height-recovery hashes match; delivered ground and noise class counts are retained.
Every feature remains `UNVERIFIED`. See [city-count-verification.json](city-count-verification.json)
and [city-preparation-verification.json](city-preparation-verification.json).

## Limits

Treetop locations can fall on a different parcel from the stem. Low or suppressed
trees can be missed, broad trees can have several peaks, height-classified objects
can include structures, and building classification can remove real canopy.
Native raster interpolation can differ near ground-core seams. Autumn collection
limits deciduous canopy observations. Current parcel ownership is applied to
2023 detections, so this is not a reconstruction of ownership at collection time.
No model or classification accuracy percentage is inferred from these counts.
