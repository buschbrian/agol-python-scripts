# Height-above-ground (HAG) dataset

`hag` builds a standing HAG dataset from a prepared tile: new LAS copies in which each point's height
above the pipeline ground surface is either **the Z value** (`z` mode) or **an added Extra Bytes
attribute** with Z untouched (`extrabytes` mode). It was added on 29 September, after the
[building-hag row](MODEL_EXPERIMENTS.md#reference-height-building-hag) showed that the deep-learning
tool's `reference_height` raster only masks coverage. The building model reads XYZ only, so testing
HAG needs a baseline whose Z *is* HAG.

Code: [canopy/hag.py](../../canopy/hag.py). Only `raster_builder()` imports ArcPy; the rest is plain
numpy. Tests: [tests/test_hag.py](../../tests/test_hag.py).

```powershell
# ArcGIS Pro Python, PYTHONNOUSERSITE=1
python -m canopy hag {root}\{tile}\prepared\prepared.lasd NEW_FOLDER [--mode z|extrabytes|both] [--extent XMIN YMIN XMAX YMAX] [--cell 0.5] [--label TEXT] [--epsg 6341]
```

## Definition

| Item | Rule |
|---|---|
| Ground | Class 2 of **every** prepared file (core and halos). Withheld, overlap and synthetic points are excluded. `LasDatasetToRaster TRIANGULATION NATURAL_NEIGHBOR WINDOW_SIZE MINIMUM 1` (the pipeline DTM, `rasters.DTM_INTERPOLATION`), 0.5 m cells, over the union of the file extents snapped outward to the cell grid. The layer reads `prepared.lasd` as `canopy run` does. The raster is written to `ground/ground.tif`, set read-only and fingerprinted, and checked again at the end. |
| Reference | EPSG:6341 required by default (`--epsg`); metre horizontal and vertical units required. |
| Sampling | The value of the raster **cell containing the point**. Points on the east or south raster edge use the edge cell. Nothing is interpolated between cells, and nothing is extrapolated. A point whose cell is NoData or outside the raster is **uncovered**. |
| HAG | Z − ground, in metres. Signed: negative HAG is kept and counted by class, never clamped. |
| `--extent` | Selects which files are written (those it intersects). The ground always comes from every prepared file, so a file's HAG does not depend on `--extent`. |
| Roles | `core` is the file containing the centre of the prepared extent (a tile plus its 50 m halo); the others are `halo`. |

### z mode (`points/`)

Z becomes `round(HAG / Z scale)`. The Z scale is kept, the Z offset becomes 0, and the header's max
and min Z are those of the stored values. **Every other byte is identical to the source**: the other
header fields (point counts, X/Y bounds, dates, software), all VLRs including the WKT, all other
record bytes, and any EVLRs. After writing, the binary check re-reads both files. It confirms that
only the Z offset, max/min Z and record Z bytes differ, and that every stored Z equals the
recomputed HAG. It also checks that the Z scale is kept, the offset is 0 and the header max/min match
the stored values. A file that fails is an error. A verified copy is fingerprinted (SHA-256 and MD5)
and set read-only. This changes protected bytes, so each copy is **its own baseline**. Compare model
outputs on it only with that copy, never index by index with the absolute-Z file.

**A file with any uncovered point is refused**: nothing is written, and the uncovered point indices
go to `uncovered/<file>.npz`. Refused halo files are listed in `refused_z`. The run's `status` is
`complete` only when the **core** copy was written. A refused core gives `status: "refused"` with the
reason in `error`, and the CLI exits 1. Consumers such as the GPU queue can therefore gate on
`status == "complete"` alone.

### extrabytes mode (`points-extrabytes/`)

Each record keeps all its bytes, Z included, and gains 4 bytes. The value is a signed 32-bit
`HeightAboveGround` equal to `round(HAG / Z scale)`, declared by an Extra Bytes VLR (`LASF_Spec` 4,
LAS 1.4 R15 layout) with scale = Z scale, offset 0 and no_data −2147483648. The VLR is inserted after
the existing VLRs. Only the point-data offset, VLR count, record length and (1.4) EVLR start change
in the header. Uncovered points keep their record and hold no_data, so no file is refused for
coverage. A binary check confirms that the original record bytes, VLRs, header and EVLRs are
unchanged and that every stored value is correct.

**Feasibility:** LAS 1.4 only. The Extra Bytes VLR is a LAS 1.4 construct. PDAL 3.5 (ArcGIS Pro
environment) decoded the attribute exactly in a 1.4 format-6 test file, but ignored it in a LAS 1.2
format-1 file, where it would be invisible. Files with version below 1.4, or files that already carry
extra bytes, are therefore skipped with the reason recorded; use z mode for them. ArcGIS Pro created a
LAS dataset over both test files (878 points each), but **Pro symbology or filtering on the attribute
has not been observed**. All pilot tiles are LAS 1.4 format 6.

### Manifest (`manifest.json`)

The manifest is written as `running` first and rewritten after each file. Its final status
(`complete`, `refused` or `failed`) is written **last**. It records: tool, label, mode, definition
text, source fingerprints (SHA-256, MD5, size, mtime) of every prepared file, the ground raster
record (method, reference, extent, NoData cells, z range, SHA-256), and per-file results. Those
cover points by class, uncovered, negative (by class), below −1 m, HAG min/max, verification,
output fingerprint and timings. It also records totals, `refused_z`, `core_z_written`, the source
recheck (point-file SHA-256 plus `.lasd`/`.lasx` size and mtime) and peak working set.

## Datasets (29 September, `H:\lidar\2023-salt-lake-valley\runs\pilot-2026-09-29\hag-20260929\`)

All runs used ArcGIS Pro Python, `PYTHONNOUSERSITE=1`, at below-normal priority, CPU only. In every run,
the prepared point files' SHA-256, and the `.lasd`/`.lasx` sizes and mtimes, were unchanged
afterwards. The 12TVL2804 core source kept MD5 `82787095336690d2909344206f9a80fc`.

| Tile | Role (label) | Mode | Status | Core points | Core uncovered | Core negative HAG (class 2) | Halos written / refused | Run time (ground) | Peak working set |
|---|---|---|---|---:|---:|---:|---|---:|---:|
| 12TVL2804 | pilot / DL experiment tile | z | **complete** | 26,982,464 | 0 | 1,047,401 (562,503) | 3 / 4 | 69.3 s (47.9 s) | 3.16 GB |
| 12TVL3302 | **prospective holdout** | z | **complete** | 34,645,313 | 0 | 1,821,871 (863,849) | 2 / 5 | 117.4 s (72.6 s) | 3.87 GB |
| 12TVL2203 | **external transfer** | both | **refused** (core) | 20,543,740 | 69,664 | 895,880 (478,559), Extra Bytes | z 1 / 3; Extra Bytes 4 / 0 | 68.0 s (50.5 s) | 2.65 GB |

The peak working set includes memory-mapped LAS pages. Records are processed in 2,000,000-point chunks.

**12TVL2804** (`12TVL2804\points\12TVL2804.las`, the GPU queue's input):

- Output SHA-256 `e5bae965bc9a23dea380bace138df14c942f65a15917ce318a5f16216aef00ba`, MD5
  `ee8ad65ec93942740b823f3097c8d288`, 809,475,416 bytes (same size as the source). Binary check
  passed: 0 non-Z record bytes differ and 0 Z values differ from HAG.
- **Ground raster SHA-256 `808b0591ff7e46b5a4b77981f90052f57005fe7689078b2911b88da2c14a6654`**. This
  is byte-identical to the building-hag `ground.tif` made by `dl_reference_height.py` from copies of
  the same files, which is direct evidence that the method is the same. Extent 427950–429050 E,
  4503950–4505050 N, 2200 × 2200 cells, 5,235 NoData cells (outer rim and the SE corner, where no
  12TVL2903 file exists), ground 1318.83–1371.70 m.
- HAG −128.05 to 119.34 m. The extremes are withheld class-7 low noise. 8,778 points lie more than
  1 m below ground: class 6 4,024, class 1 3,558, class 7 1,024, class 2 133, class 3 39. Class-6
  points below the DTM are plausibly sunken entries or light wells, where the ground TIN spans the
  building. This is not checked.
- Halos written: 12TVL2704, 12TVL2803, 12TVL2805 (all verified). Refused: 12TVL2703 (64 uncovered),
  12TVL2705 (252), 12TVL2904 (53), 12TVL2905 (5). These are the corner halos plus the east halo
  beside the missing corner. `dl_run.py` infers on the core file only, so nothing it needs is missing.
  The manifest predates the `core_z_written`/top-level `refused_z` fields. Its core was written, so
  its status would be the same under the current rule.

**12TVL3302** (prospective holdout; keep out of calibration, tuning and fine-tuning):

- Core output SHA-256 `7e33ebe780be8c59ad3b1b906afef709806271d1850854a7483b69dcf3b06546`; source MD5
  `36ac0563d3dd7e39d3f1b2abcac7d4f3`. Ground raster SHA-256 `be6ab55f…` (2200 × 2200, 5,407 NoData
  cells, 1564.16–2014.46 m).
- HAG −1,138.2 m (withheld class 7) to 2,186.8 m (withheld class 18; all 142 points above 150 m are
  class 18). 2,754 points lie more than 1 m below ground: class 6 1,008, class 1 965, class 7 377,
  class 2 298.
- Halos written: 12TVL3202, 12TVL3303. Refused: the corner halos 12TVL3201 (83), 12TVL3203 (13) and
  12TVL3403 (70), plus the two halos beside the missing SE corner (no 12TVL3401 file). Those are the
  south halo **12TVL3301 (68 of 1,732,839 points)** and the east halo 12TVL3402 (40). Like
  12TVL2804, the manifest predates the new top-level fields.

**12TVL2203** (external transfer; evaluation of transfer only):

- **No z-mode core.** 69,664 core points lie over ground NoData, all in the SW corner
  (x ≤ 422,114, y ≤ 4,503,106.5). 66,845 of them are class 6. The tile sits at the acquisition edge:
  the preparation has only 12TVL2204, 12TVL2303 and 12TVL2304 as neighbours, so no ground exists
  beyond a corner building and the TIN leaves it uncovered (24,390 NoData cells). The status is
  `refused`, so a status-gated consumer will skip it.
- The Extra Bytes copies of all four files were written and verified. The core carries 69,664 no_data
  values, and 895,880 covered points have negative HAG. This is the usable HAG artifact for the tile.
- A first z-only run of this tile had written `status: complete` with the core refused. It was
  removed within minutes, before anything referenced it, and rerun after the status rule was made
  core-gated. Its ground raster SHA-256 (`bf9ca9c9…`) matched the rerun's.

## Decisions for the user

1. **Cell lookup, not bilinear.** A coverage probe on 12TVL2804 with the same raster found 374
   uncovered points with cell lookup (all in corner or east halos, 0 in the core). Bilinear
   interpolation between cell centres left 28,739 uncovered. Cell lookup is also the pipeline's own
   CHM arithmetic. Bilinear would be smoother on slopes (a few centimetres within a 0.5 m cell). Keep
   cell lookup unless that matters for a model.
2. **Whole-file refusal vs subset copies in z mode.** Refusal keeps "every other byte identical"
   literally true. It cost 12TVL3302 its 1.7 M-point south halo for 68 points and 12TVL2203 its core.
   The alternatives each change something else:
   - Subset copies: drop uncovered points, recount the header and log the dropped indices. The copy
     is then not index-aligned with its source.
   - Ground from a wider source, such as the neighbouring delivery tiles' class 2. This means a
     larger preparation.
   - The Extra Bytes copy, which keeps every point, already exists for 12TVL2203.
3. **Vertical reference text.** The WKT VLR is copied unchanged, so z-mode files still declare
   NAVD88 (Geoid18) metres although Z is height above ground. Rewriting the VLR would change its
   length and every offset after it. Units are correct for the DL tool. Treat the manifest, not the
   CRS, as the statement of what Z means.
4. **Extra Bytes in ArcGIS Pro.** Written for LAS 1.4 and verified with PDAL. Pro accepted the file,
   but whether its LAS layer offers `HeightAboveGround` for symbology or filters has not been
   observed. Please check in Pro before relying on it. Only 12TVL2203 has Extra Bytes copies so far
   (`--mode extrabytes` on a new folder adds them for the others).
5. **Negative HAG is expected.** Class-2 points often lie a few centimetres below their cell's
   natural-neighbour value: 21% of them on the 12TVL2804 core, 36% on 12TVL3302 and 16% on
   12TVL2203. The minima are withheld noise. Nothing is clamped. A model
   trained on non-negative HAG may need its own clamping policy, recorded as a separate step.
