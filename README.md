# agol-python-scripts

Python utilities for ArcGIS Online and ArcGIS Pro. The scripts at the root
are self-contained single files with nothing to install; larger tools that
need more than one file live in their own folder.

| Script | What it does | Runs with |
|---|---|---|
| `assign_polygon_colors.py` | Assigns integer IDs to `Color_ID` so no two adjacent polygons share a value (greedy graph coloring over a Polygon Neighbors table). Takes the polygon layer and neighbor table as CLI arguments; preserves the existing integer field contract. | ArcGIS Pro's Python (`arcpy`) |
| `add_badelf_fields_to_agol.py` | Adds the Bad Elf Flex (2025) GNSS metadata fields and coded-value domains to a hosted feature layer, so surveyed points keep correction type, geoid model, antenna height, and final heights. Existing fields are checked for compatible types and domains; --dry-run previews additions. | ArcGIS API for Python (`arcgis`) |
| `sketch_layer_to_template_schema.py` | Rebuilds an ArcGIS Online Map Viewer sketch layer as a feature class carrying a production dataset's full schema — fields, domains, subtypes, GlobalIDs and attribute rules — reprojecting with an explicit datum transformation and loading with rules disabled. Set the paths at the top and run once with `DRY_RUN = True`. | ArcGIS Pro's Python (`arcpy`) |
| [`canopy-toolbox/`](canopy-toolbox/) | ArcGIS Pro Python toolbox (`CanopyTools.pyt`) turning a classified lidar point cloud into canopy cover and an individual-tree layer — vegetation-only CHM, height-banded treetop detection, watershed crown delineation, zonal cover rollup. Five tools plus a working-copy preparation and bounded-AOI runner; see its README for limits and pilot evidence. | ArcGIS Pro + 3D and Spatial Analyst |

The LiDAR work now also includes a [planning-products workflow](canopy-toolbox/PLANNING_PRODUCTS.md) for terrain, building heights, and drainage screening, with a separate Millcreek pilot and quality flags.

## Environment

For `add_badelf_fields_to_agol.py`, any Python ≥ 3.10 with `arcgis` — for
example the `arcgis-online` pixi environment (`pixi shell` in its folder), or
`pip install arcgis`.

## Usage

### Polygon coloring

Run from ArcGIS Pro's Python environment:

```bash
python assign_polygon_colors.py "C:/gis/maps.gdb/polygons" "C:/gis/maps.gdb/neighbors" --dry-run
python assign_polygon_colors.py "C:/gis/maps.gdb/polygons" "C:/gis/maps.gdb/neighbors"
```

The neighbor table must have `src_OBJECTID` and `nbr_OBJECTID`; rows that
pair a polygon with itself are ignored. The polygon identifier defaults to
`OID@`, the layer's ObjectID field whatever it is named; use `--id-field` for
another field. Both inputs must use the same identifiers.

Output stays numeric: `Color_ID` is a SHORT integer field when newly created,
with IDs from 1 through 9 by default. Use `--color-field colorID` for a layer
whose existing field has that spelling, or `--max-colors N` to change the
limit (1–32767). Existing short, long and big integer fields are accepted;
text and floating-point fields are rejected before writing. The field types
follow Esri's [Field](https://pro.arcgis.com/en/pro-app/latest/arcpy/classes/field.htm)
and [Add Field](https://pro.arcgis.com/en/pro-app/latest/tool-reference/data-management/add-field.htm)
contracts.

Polygons with no neighbors receive ID 1. A dry run includes them and writes
nothing. Too few color IDs raises an error before any field is added or rows
are updated. Each polygon is updated once; apply your preferred colors through
ArcGIS symbology. The unmerged rescue draft's hex palettes are not part of
this integer-output CLI.

Pure coloring and simulated ArcPy I/O tests run without ArcGIS:

```bash
python3 -m unittest discover -s tests -v
```

Before merging the CLI rewrite, validate a dry run and a write on a disposable
copy in ArcGIS Pro, including a layer with an existing `Color_ID` field and
one without it. The local tests do not exercise a real geodatabase.

### Bad Elf fields

```bash
python add_badelf_fields_to_agol.py --url https://myorg.maps.arcgis.com --item <item-id> --username <user>
```

The password is prompted for. Use `--layer N` when the item has more than one
sublayer. `--password` exists for automation only — prefer the prompt so the
password never lands in shell history.

## Folders

`canopy-toolbox/` is a multi-file ArcGIS Pro toolbox rather than a script.
Its band and tiling logic is deliberately free of `arcpy` so it can be
unit-tested off a Pro machine:

```bash
cd canopy-toolbox && python3 -m unittest discover -s tests -t .
```

## History

Started as `colorID.py` (the polygon coloring script alone); renamed
2026-09-07 when the Bad Elf script joined it. The sketch layer script was
added 2026-09-11, and `canopy-toolbox/` on 2026-09-12 — the first entry
that is a folder rather than a single script.

## Licence

MIT — see [LICENSE](LICENSE).
