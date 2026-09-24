# Acquisition records

One folder per lidar acquisition. Millcreek partners in the county's QL1 collection, which recurs
about every ten years, and an earlier 2013–2014 set also exists, so each acquisition is documented
the same way before any product from it is used or compared with another.

| Acquisition | Record |
|---|---|
| 2023 Salt Lake Valley, USGS UT_2023SaltLakeCo_C24 | [2023-salt-lake-valley](2023-salt-lake-valley/RECORD.md) |

## What a record contains

| File | Written by | Holds |
|---|---|---|
| `acquisition-facts.md` | `canopy index-delivery` | What the data itself says: tiles, points, versions, header CRS, density, flight dates, coverage of the city |
| `acquisition.json` | `canopy index-delivery` | The same facts, machine-readable, for comparing epochs |
| `RECORD.md` | a person, from [TEMPLATE.md](TEMPLATE.md) | What the vendor declared, what it means for the toolbox, discrepancies, open questions |
| `reference/` | copied from the delivery | Metadata, reports, and the tile and swath indexes the other files cite |

The split is deliberate. Generated files are rewritten on every run and must not be edited by
hand; the record holds judgment, which no command can produce. Neither file carries per-file
paths, so neither exposes the server share that mapped drives resolve to. The generated files
record the delivery folder, boundary and index paths as they were passed, except that a network
(UNC) path such as `\\server\share\...` is reduced to its final name, marked as redacted. Pass a
mapped drive letter or a repository-relative path when the full path should appear.

## Documenting a new acquisition

1. **Make the folder**, named `<year>-<area>`, and copy `TEMPLATE.md` into it as `RECORD.md`.
2. **Copy the reference files** into `reference/`: every metadata XML, the project and mapping
   reports, and the tile, product-area and swath indexes. Leave out anything nothing reads and
   that is large — say what was left out in `reference/README.md`.
3. **Generate the facts.** From `canopy-toolbox`, with ArcGIS Pro Python:

   ~~~powershell
   & $proPython -m canopy index-delivery '<delivery folder>' scratch\acquisition_<year> `
       --label '<Year> <Area> — <project ID>' `
       --swaths acquisitions\<folder>\reference\<swath index> `
       --tile-index acquisitions\<folder>\reference\<tile index> `
       --boundary 'G:\GIS\Data\City\Millcreek\GDB\Millcreek_Master_New.gdb\Boundaries\MunicipalBoundary'
   ~~~

   Then copy `acquisition-facts.md` and `acquisition.json` from that output into the folder. The
   rest of the output — the full report with per-file paths, the tile-bounds feature class and its
   layer file — stays in ignored scratch.

   Adjust `--date-field` if the swath index names its date column differently from `DATE_D`, and
   `--tile-field` if the tile index is not keyed by `Tile_Name`. The swath and tile indexes must
   share the delivery's horizontal CRS and are refused otherwise; the boundary may be in any CRS
   and is projected, with the transformation recorded.
4. **Fill the record** from the metadata and reports. Every row of the declared-facts table gets a
   source. Write "not stated" rather than dropping a row.
5. **Fill the comparability table** and check it against every earlier acquisition before any
   surface from this one is differenced against another. A datum or geoid mismatch, or a different
   season, reads as change.
6. **Add the acquisition** to the table above.

## Current limits

- `index-delivery` reads uncompressed LAS headers only. A LAZ delivery must be decompressed first,
  or the header reader extended.
- Flight dates need a swath index with one date per swath. Without one, the facts page omits the
  section and the record should say where dates came from instead.
- Coverage uses header rectangles, not point support. Voids inside a tile are invisible to it; the
  vendor's low-confidence polygons are the check for those.
